import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Form, UploadFile, File, HTTPException

from .. import db
from ..engine import repo_ingestor, pipeline
from ..report_schema import (
    ValidationResult, Summary, ScoreBreakdownItem, Finding, Recommendation, Evidence,
    InvariantResult, ScenarioResult,
)

router = APIRouter(prefix="/api/runs", tags=["runs"])

ZIP_EXT = ".zip"


def _new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def _create_run_row(run_id: str, agent_name: str, source_type: str, source_ref: str | None,
                     use_case: str | None, expected_io: str | None, description: str | None,
                     enable_llm_insights: bool):
    now = datetime.now(timezone.utc).isoformat()
    with db.get_conn() as conn:
        conn.execute(
            """INSERT INTO runs (run_id, agent_name, source_type, source_ref, use_case, expected_io,
                                  description, enable_llm_insights, status, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (run_id, agent_name, source_type, source_ref, use_case, expected_io, description,
             int(enable_llm_insights), "queued", now, now),
        )


def _set_status(run_id: str, status: str):
    now = datetime.now(timezone.utc).isoformat()
    with db.get_conn() as conn:
        conn.execute("UPDATE runs SET status=?, updated_at=? WHERE run_id=?", (status, now, run_id))


def _execute_run(run_id: str, workspace: Path, context: dict, source_type: str, source_ref: str | None):
    try:
        _set_status(run_id, "running")
        result = pipeline.run_validation(run_id, workspace, context)
        pipeline.persist_result(result, source_type, source_ref, context)
    except Exception as e:
        pipeline.mark_failed(run_id, str(e))


def _execute_repo_run(run_id: str, repo_url: str, context: dict):
    """Clone happens here (in the background) so the HTTP request doesn't block on a slow clone."""
    try:
        _set_status(run_id, "running")
        workspace = repo_ingestor.ingest_repo_url(run_id, repo_url)
        result = pipeline.run_validation(run_id, workspace, context)
        pipeline.persist_result(result, "repo_url", repo_url, context)
    except Exception as e:
        pipeline.mark_failed(run_id, str(e))


@router.post("")
async def create_run(
    background_tasks: BackgroundTasks,
    agent_name: str = Form(...),
    repo_url: str | None = Form(None),
    use_case: str | None = Form(None),
    expected_io: str | None = Form(None),
    description: str | None = Form(None),
    enable_llm_insights: bool = Form(False),
    files: list[UploadFile] = File(default=[]),
):
    if not repo_url and not files:
        raise HTTPException(400, "Provide either a repo_url or at least one uploaded file.")

    run_id = _new_run_id()
    context = {
        "agent_name": agent_name,
        "use_case": use_case,
        "description": description,
        "expected_io": expected_io,
        "enable_llm_insights": enable_llm_insights,
    }

    if repo_url:
        source_type, source_ref = "repo_url", repo_url
        _create_run_row(run_id, agent_name, source_type, source_ref, use_case, expected_io, description, enable_llm_insights)
        # Clone in the background so this request returns immediately instead of blocking on a slow clone.
        background_tasks.add_task(_execute_repo_run, run_id, repo_url, context)
        return {"run_id": run_id, "status": "queued"}
    else:
        non_empty = [f for f in files if f.filename]
        if len(non_empty) == 1 and non_empty[0].filename.lower().endswith(ZIP_EXT):
            source_type, source_ref = "zip", non_empty[0].filename
            _create_run_row(run_id, agent_name, source_type, source_ref, use_case, expected_io, description, enable_llm_insights)
            zip_bytes = await non_empty[0].read()
            tmp_zip = repo_ingestor.WORKSPACES / f"{run_id}_upload.zip"
            tmp_zip.parent.mkdir(parents=True, exist_ok=True)
            tmp_zip.write_bytes(zip_bytes)
            workspace = repo_ingestor.ingest_zip(run_id, tmp_zip)
            tmp_zip.unlink(missing_ok=True)
        else:
            source_type, source_ref = "files", ", ".join(f.filename for f in non_empty)
            _create_run_row(run_id, agent_name, source_type, source_ref, use_case, expected_io, description, enable_llm_insights)
            file_data = [(f.filename, await f.read()) for f in non_empty]
            workspace = repo_ingestor.ingest_files(run_id, file_data)

    background_tasks.add_task(_execute_run, run_id, workspace, context, source_type, source_ref)
    return {"run_id": run_id, "status": "queued"}


@router.get("/{run_id}/status")
def get_status(run_id: str):
    with db.get_conn() as conn:
        row = conn.execute("SELECT run_id, status, error FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Run not found")
    return {"run_id": row["run_id"], "status": row["status"], "error": row["error"]}


@router.get("/{run_id}/results", response_model=ValidationResult)
def get_results(run_id: str):
    with db.get_conn() as conn:
        run = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if not run:
            raise HTTPException(404, "Run not found")
        if run["status"] != "completed":
            raise HTTPException(409, f"Run is not completed yet (status={run['status']})")

        summary = Summary(
            agent_name=run["agent_name"], run_id=run_id, timestamp=run["updated_at"],
            applicable=bool(run["applicable"]),
            not_applicable_reason=run["not_applicable_reason"],
            overall_trust_score=run["overall_trust_score"],
            hygiene_score=run["hygiene_score"],
            behavior_score=run["behavior_score"],
            demo_readiness=run["demo_readiness"],
            production_readiness=run["production_readiness"],
            status=run["status"],
        )

        if not summary.applicable:
            return ValidationResult(summary=summary, adapter_status=run["adapter_status"] or "not_attempted")

        breakdown_rows = conn.execute("SELECT * FROM score_breakdown WHERE run_id=?", (run_id,)).fetchall()
        finding_rows = conn.execute("SELECT * FROM findings WHERE run_id=?", (run_id,)).fetchall()
        rec_rows = conn.execute("SELECT * FROM recommendations WHERE run_id=?", (run_id,)).fetchall()
        evidence_rows = conn.execute("SELECT * FROM evidence WHERE run_id=?", (run_id,)).fetchall()
        insight_rows = conn.execute("SELECT insight FROM ai_insights WHERE run_id=?", (run_id,)).fetchall()
        signal_rows = conn.execute("SELECT signal FROM positive_signals WHERE run_id=?", (run_id,)).fetchall()
        invariant_rows = conn.execute("SELECT * FROM invariant_results WHERE run_id=?", (run_id,)).fetchall()
        scenario_rows = conn.execute("SELECT * FROM scenario_results WHERE run_id=?", (run_id,)).fetchall()

    return ValidationResult(
        summary=summary,
        score_breakdown=[ScoreBreakdownItem(dimension=r["dimension"], score=r["score"], max_score=r["max_score"], remarks=r["remarks"]) for r in breakdown_rows],
        positive_signals=[r["signal"] for r in signal_rows],
        findings=[Finding(id=r["id"], severity=r["severity"], category=r["category"], title=r["title"],
                           description=r["description"], why_it_matters=r["why_it_matters"], score_impact=r["score_impact"],
                           evidence_refs=db.load_refs(r["evidence_refs"])) for r in finding_rows],
        recommendations=[Recommendation(id=r["id"], finding_id=r["finding_id"], title=r["title"],
                                         recommendation=r["recommendation"], priority=r["priority"],
                                         expected_impact=r["expected_impact"]) for r in rec_rows],
        evidence=[Evidence(id=r["id"], file_path=r["file_path"], line_start=r["line_start"], line_end=r["line_end"],
                            snippet=r["snippet"], reason=r["reason"]) for r in evidence_rows],
        ai_insights=[r["insight"] for r in insight_rows],
        invariant_results=[InvariantResult(test_id=r["test_id"], tier=r["tier"], passed=bool(r["passed"]), detail=r["detail"] or "") for r in invariant_rows],
        scenario_results=[ScenarioResult(scenario_id=r["scenario_id"], tier=r["tier"], passed=bool(r["passed"]),
                                          description=r["description"] or "", expected=db.load_refs(r["expected"]) or {},
                                          actual=db.load_refs(r["actual"]) or {}, detail=r["detail"] or "") for r in scenario_rows],
        adapter_status=run["adapter_status"] or "not_attempted",
    )


@router.get("")
def list_runs():
    with db.get_conn() as conn:
        rows = conn.execute(
            """SELECT run_id, agent_name, source_type, status, applicable, not_applicable_reason,
                      overall_trust_score, hygiene_score, behavior_score, demo_readiness, production_readiness, created_at
               FROM runs ORDER BY created_at DESC"""
        ).fetchall()
    return [dict(r) for r in rows]
