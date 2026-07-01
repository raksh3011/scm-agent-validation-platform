import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Form, UploadFile, File, HTTPException

from ..asd.parser import parse_asd_bytes
from ..core import db
from ..core.auth import require_owner
from ..core.config import MAX_ASD_UPLOAD_BYTES, MAX_UPLOAD_BYTES
from ..ingestion import repo_ingestor
from ..pipeline import orchestrator

router = APIRouter(prefix="/api/runs", tags=["runs"])

ZIP_EXT = ".zip"


def _new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def _create_run_row(run_id: str, subject_id: str, agent_name: str, source_type: str,
                     source_ref: str | None, use_case: str | None, description: str | None,
                     owner_key: str):
    now = datetime.now(timezone.utc).isoformat()
    with db.session() as conn:
        conn.execute(
            """INSERT INTO runs (run_id, subject_id, agent_name, source_type, source_ref, use_case,
               description, status, created_at, updated_at, owner_key) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (run_id, subject_id, agent_name, source_type, source_ref, use_case, description,
             "queued", now, now, owner_key),
        )


def _set_status(run_id: str, status: str):
    with db.session() as conn:
        conn.execute("UPDATE runs SET status=?, updated_at=? WHERE run_id=?",
                     (status, datetime.now(timezone.utc).isoformat(), run_id))


def _execute_run(run_id: str, workspace: Path, context: dict, source_type: str, source_ref: str | None):
    try:
        _set_status(run_id, "running")
        result = orchestrator.run_validation(run_id, workspace, context)
        orchestrator.persist_result(result, source_type, source_ref, context)
    except Exception as e:
        orchestrator.mark_failed(run_id, str(e))


def _execute_repo_run(run_id: str, repo_url: str, context: dict):
    try:
        _set_status(run_id, "running")
        workspace = repo_ingestor.ingest_repo_url(run_id, repo_url)
        result = orchestrator.run_validation(run_id, workspace, context)
        orchestrator.persist_result(result, "repo_url", repo_url, context)
    except Exception as e:
        orchestrator.mark_failed(run_id, str(e))


@router.post("")
async def create_run(
    background_tasks: BackgroundTasks,
    agent_name: str = Form(...),
    repo_url: str | None = Form(None),
    use_case: str | None = Form(None),
    description: str | None = Form(None),
    files: list[UploadFile] = File(default=[]),
    asd_file: UploadFile | None = File(None),
    owner_key: str = Depends(require_owner),
):
    if not repo_url and not files:
        raise HTTPException(400, "Provide either a repo_url or at least one uploaded file.")

    # Opportunistic retention sweep — no separate scheduler process to run this,
    # so piggyback it on every new submission. Non-blocking; best-effort.
    background_tasks.add_task(repo_ingestor.cleanup_stale_workspaces)

    run_id = _new_run_id()
    context = {"agent_name": agent_name, "use_case": use_case, "description": description, "run_id": run_id}

    if asd_file and asd_file.filename:
        asd_bytes = await asd_file.read()
        if len(asd_bytes) > MAX_ASD_UPLOAD_BYTES:
            raise HTTPException(400, f"Agent Specification Document exceeds the {MAX_ASD_UPLOAD_BYTES // (1024*1024)} MB limit.")
        try:
            context["asd_spec"] = parse_asd_bytes(asd_file.filename, asd_bytes)
        except Exception as e:
            raise HTTPException(400, f"Could not parse Agent Specification Document: {e}")

    if repo_url:
        source_type, source_ref = "repo_url", repo_url
        context["source_ref"] = source_ref
        subject_id = orchestrator.subject_id_for(agent_name, source_ref)
        _create_run_row(run_id, subject_id, agent_name, source_type, source_ref, use_case, description, owner_key)
        background_tasks.add_task(_execute_repo_run, run_id, repo_url, context)
        return {"run_id": run_id, "status": "queued"}

    non_empty = [f for f in files if f.filename]
    if len(non_empty) == 1 and non_empty[0].filename.lower().endswith(ZIP_EXT):
        source_type, source_ref = "zip", non_empty[0].filename
        context["source_ref"] = source_ref
        subject_id = orchestrator.subject_id_for(agent_name, source_ref)
        _create_run_row(run_id, subject_id, agent_name, source_type, source_ref, use_case, description, owner_key)
        zip_bytes = await non_empty[0].read()
        if len(zip_bytes) > MAX_UPLOAD_BYTES:
            orchestrator.mark_failed(run_id, "Uploaded zip exceeds the size limit.")
            raise HTTPException(400, f"Uploaded zip exceeds the {MAX_UPLOAD_BYTES // (1024*1024)} MB limit.")
        tmp_zip = repo_ingestor.WORKSPACES_DIR / f"{run_id}_upload.zip"
        tmp_zip.parent.mkdir(parents=True, exist_ok=True)
        tmp_zip.write_bytes(zip_bytes)
        try:
            workspace = repo_ingestor.ingest_zip(run_id, tmp_zip)
        except (ValueError, OSError) as e:
            tmp_zip.unlink(missing_ok=True)
            orchestrator.mark_failed(run_id, str(e))
            raise HTTPException(400, str(e))
        tmp_zip.unlink(missing_ok=True)
    else:
        source_type, source_ref = "files", ", ".join(f.filename for f in non_empty)
        context["source_ref"] = source_ref
        subject_id = orchestrator.subject_id_for(agent_name, source_ref)
        _create_run_row(run_id, subject_id, agent_name, source_type, source_ref, use_case, description, owner_key)
        file_data = [(f.filename, await f.read()) for f in non_empty]
        if sum(len(c) for _, c in file_data) > MAX_UPLOAD_BYTES:
            orchestrator.mark_failed(run_id, "Uploaded files exceed the size limit.")
            raise HTTPException(400, f"Uploaded files exceed the {MAX_UPLOAD_BYTES // (1024*1024)} MB limit.")
        try:
            workspace = repo_ingestor.ingest_files(run_id, file_data)
        except (ValueError, OSError) as e:
            orchestrator.mark_failed(run_id, str(e))
            raise HTTPException(400, str(e))

    background_tasks.add_task(_execute_run, run_id, workspace, context, source_type, source_ref)
    return {"run_id": run_id, "status": "queued"}


@router.get("/{run_id}/status")
def get_status(run_id: str, owner_key: str = Depends(require_owner)):
    with db.session() as conn:
        row = conn.execute(
            "SELECT run_id, status, error, progress, owner_key FROM runs WHERE run_id=?", (run_id,)
        ).fetchone()
    if not row or row["owner_key"] != owner_key:
        raise HTTPException(404, "Run not found")
    d = dict(row)
    del d["owner_key"]
    d["progress"] = db.load(d.get("progress"))
    return d


@router.get("/{run_id}/results")
def get_results(run_id: str, owner_key: str = Depends(require_owner)):
    with db.session() as conn:
        run = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if not run or run["owner_key"] != owner_key:
            raise HTTPException(404, "Run not found")
        if run["status"] != "completed":
            raise HTTPException(409, f"Run is not completed yet (status={run['status']})")

        run_d = dict(run)
        if not run["applicable"]:
            return {"summary": run_d, "applicable": False}

        scenarios = [dict(r) for r in conn.execute("SELECT * FROM scenarios WHERE run_id=?", (run_id,))]
        for s in scenarios:
            s["inputs"] = db.load(s["inputs"])
            s["initial_state"] = db.load(s["initial_state"])

        executions = [dict(r) for r in conn.execute("SELECT * FROM scenario_executions WHERE run_id=?", (run_id,))]
        for e in executions:
            e["actual_behaviour"] = db.load(e["actual_behaviour"])

        evidence = [dict(r) for r in conn.execute("SELECT * FROM evidence WHERE run_id=?", (run_id,))]
        for e in evidence:
            e["detail"] = db.load(e["detail"])

        defects = [dict(r) for r in conn.execute("SELECT * FROM defects WHERE run_id=?", (run_id,))]
        for d in defects:
            d["verification_steps"] = db.load(d["verification_steps"])
            d["scenario_refs"] = db.load(d["scenario_refs"])
            d["evidence_refs"] = db.load(d["evidence_refs"])
            d["violated_requirement"] = db.load(d.get("violated_requirement")) or []

        trust_scores = [dict(r) for r in conn.execute("SELECT * FROM trust_scores WHERE run_id=?", (run_id,))]
        for t in trust_scores:
            t["evidence_refs"] = db.load(t["evidence_refs"])

        delta_row = conn.execute("SELECT * FROM historical_deltas WHERE run_id=?", (run_id,)).fetchone()
        delta = None
        if delta_row:
            delta = dict(delta_row)
            delta["new_defects"] = db.load(delta["new_defects"])
            delta["resolved_defects"] = db.load(delta["resolved_defects"])
            delta["regressions"] = db.load(delta["regressions"])

        kpis = [dict(r) for r in conn.execute("SELECT * FROM kpi_results WHERE run_id=?", (run_id,))]

        trace_rows = conn.execute("SELECT * FROM decision_traces WHERE run_id=?", (run_id,)).fetchall()
        decision_traces = {r["scenario_id"]: db.load(r["steps"]) for r in trace_rows}

        stages = [dict(r) for r in conn.execute(
            "SELECT * FROM pipeline_stages WHERE run_id=? ORDER BY stage_order", (run_id,))]
        for s in stages:
            s["recovery_suggestions"] = db.load(s["recovery_suggestions"]) or []

        root_causes = [dict(r) for r in conn.execute("SELECT * FROM root_causes WHERE run_id=?", (run_id,))]
        for rc in root_causes:
            rc["affected_scenario_ids"] = db.load(rc["affected_scenario_ids"]) or []
        root_causes.sort(key=lambda rc: rc["affected_count"], reverse=True)

        for s in scenarios:
            s["traceability"] = db.load(s.get("traceability")) or {}

        graph_row = conn.execute("SELECT graph FROM capability_graphs WHERE run_id=?", (run_id,)).fetchone()
        capability_graph = db.load(graph_row["graph"]) if graph_row else None

        asd_row = conn.execute("SELECT spec FROM agent_specifications WHERE run_id=?", (run_id,)).fetchone()
        asd_spec = db.load(asd_row["spec"]) if asd_row else None

        conformance_row = conn.execute("SELECT * FROM conformance_summary WHERE run_id=?", (run_id,)).fetchone()
        conformance = dict(conformance_row) if conformance_row else None

        requirement_conformance = [dict(r) for r in conn.execute(
            "SELECT * FROM requirement_conformance WHERE run_id=?", (run_id,))]
        for rc in requirement_conformance:
            rc["repository_evidence"] = db.load(rc["repository_evidence"]) or []
            rc["scenario_refs"] = db.load(rc["scenario_refs"]) or []
            rc["evidence_refs"] = db.load(rc["evidence_refs"]) or []
        if conformance is not None:
            conformance["requirements"] = requirement_conformance

        evalgen_row = conn.execute("SELECT * FROM evalgen_stats WHERE run_id=?", (run_id,)).fetchone()
        evalgen_stats = dict(evalgen_row) if evalgen_row else None
        if evalgen_stats:
            evalgen_stats["parameters"] = db.load(evalgen_stats["parameters"]) or []

    return {
        "summary": run_d, "applicable": True, "scenarios": scenarios, "executions": executions,
        "evidence": evidence, "defects": defects, "trust_scores": trust_scores, "historical_delta": delta,
        "kpis": kpis, "decision_traces": decision_traces, "stages": stages, "root_causes": root_causes,
        "asd_spec": asd_spec, "conformance": conformance, "evalgen_stats": evalgen_stats,
        "capability_graph": capability_graph,
    }


@router.get("")
def list_runs(owner_key: str = Depends(require_owner)):
    with db.session() as conn:
        rows = conn.execute(
            """SELECT run_id, subject_id, agent_name, source_type, status, applicable,
                      not_applicable_reason, primary_agent_type, overall_trust_score,
                      production_readiness, created_at FROM runs WHERE owner_key=? ORDER BY created_at DESC""",
            (owner_key,),
        ).fetchall()
    return [dict(r) for r in rows]


@router.post("/{subject_id}/rerun")
def rerun_subject(subject_id: str, background_tasks: BackgroundTasks, owner_key: str = Depends(require_owner)):
    """Triggers a fresh validation run against the same source as the most recent run
    for this subject — the hook point for scheduled continuous audits."""
    with db.session() as conn:
        row = conn.execute(
            "SELECT * FROM runs WHERE subject_id=? AND owner_key=? ORDER BY created_at DESC LIMIT 1",
            (subject_id, owner_key),
        ).fetchone()
    if not row:
        raise HTTPException(404, "Unknown subject_id")
    row = dict(row)
    run_id = _new_run_id()
    context = {"agent_name": row["agent_name"], "use_case": row["use_case"], "description": row["description"],
               "run_id": run_id, "source_ref": row["source_ref"]}
    _create_run_row(run_id, subject_id, row["agent_name"], row["source_type"], row["source_ref"],
                     row["use_case"], row["description"], owner_key)
    if row["source_type"] == "repo_url":
        background_tasks.add_task(_execute_repo_run, run_id, row["source_ref"], context)
    else:
        raise HTTPException(400, "Continuous re-run currently only supports repo_url sources.")
    return {"run_id": run_id, "status": "queued"}
