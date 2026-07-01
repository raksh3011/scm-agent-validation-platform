"""The 9-stage validation pipeline controller.

repository_analysis -> dependency_resolution -> runtime_environment_build ->
agent_initialization -> entry_point_discovery -> sandbox_validation ->
business_scenario_execution -> business_decision_validation -> trust_score_calculation

`sandbox_validation` is a cheap one-scenario preflight, not the full suite: if the
agent's entrypoint is unreachable, we find that out in one subprocess call instead of
burning the full scenario count (and several minutes of wall-clock time) re-proving
the same crash hundreds of times. Downstream stages are then marked `skipped`, every
generated scenario is still listed (transparency — no hidden test cases) with
`execution_state="unreachable"`, and trust dimensions that depend on business
validation are `unknown` rather than 0.
"""
import hashlib
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from ..asd import conformance as asd_conformance
from ..core import db
from ..core.config import REPORTS_DIR, REPRODUCIBILITY_SAMPLE_SIZE
from ..core.models import PIPELINE_STAGES, RuntimeEnvironment, Scenario, ScenarioExecutionResult, StageResult
from ..defects import architectural_defect_engine, defect_engine, root_cause_engine
from ..detection import agent_classifier, workflow_graph
from ..execution import decision_trace, scenario_executor
from ..kpi import kpi_engine
from ..ingestion import repo_ingestor
from ..plugins import registry
from ..reporting import pdf_builder
from ..runtime import agent_initializer, detector, entrypoint_discovery, environment_builder
from ..scenarios import generator
from ..scenarios.catalogue import ScenarioCatalogue
from ..scoring import trust_engine
from ..static_analysis import static_analyzer
from ..validation import decision_validator
from ..understanding import business_capability_graph


def _dedup_defects(defects: list) -> list:
    """Safety net against duplicate/contradictory findings: collapse defects that share
    a (category, defect_type) — multiple detectors firing on the same underlying issue
    should be reported once, with their evidence merged, not as separate line items."""
    merged: dict[tuple[str, str], object] = {}
    order: list[tuple[str, str]] = []
    for d in defects:
        key = (d.category, d.defect_type)
        if key not in merged:
            merged[key] = d
            order.append(key)
            continue
        existing = merged[key]
        existing.scenario_refs = sorted(set(existing.scenario_refs) | set(d.scenario_refs))
        existing.evidence_refs = sorted(set(existing.evidence_refs) | set(d.evidence_refs))
        existing.violated_requirement = sorted(set(existing.violated_requirement) | set(d.violated_requirement))
        sev_rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        if sev_rank.get(d.severity, 1) > sev_rank.get(existing.severity, 1):
            existing.severity = d.severity
        existing.confidence = max(existing.confidence, d.confidence)
    return [merged[k] for k in order]


def subject_id_for(agent_name: str, source_ref: str | None) -> str:
    raw = f"{agent_name}::{source_ref or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _ensure_subject(subject_id: str, label: str):
    with db.session() as conn:
        existing = conn.execute("SELECT 1 FROM subjects WHERE subject_id=?", (subject_id,)).fetchone()
        if not existing:
            conn.execute("INSERT INTO subjects (subject_id, label, created_at) VALUES (?,?,?)",
                         (subject_id, label, datetime.now(timezone.utc).isoformat()))


def _previous_run(subject_id: str, exclude_run_id: str) -> dict | None:
    with db.session() as conn:
        row = conn.execute(
            "SELECT * FROM runs WHERE subject_id=? AND run_id!=? AND status='completed' "
            "ORDER BY created_at DESC LIMIT 1",
            (subject_id, exclude_run_id),
        ).fetchone()
        return dict(row) if row else None


def mark_failed(run_id: str, error: str):
    with db.session() as conn:
        conn.execute("UPDATE runs SET status='failed', error=?, updated_at=? WHERE run_id=?",
                     (error, datetime.now(timezone.utc).isoformat(), run_id))


def _write_progress(run_id: str, payload: dict):
    """Best-effort live progress so the UI can show real stage/scenario movement
    instead of a single spinner for the whole multi-minute run."""
    try:
        with db.session() as conn:
            conn.execute("UPDATE runs SET progress=?, updated_at=? WHERE run_id=?",
                         (db.dump(payload), datetime.now(timezone.utc).isoformat(), run_id))
    except Exception:
        pass


def _pipeline_health(stages: list[StageResult]) -> float:
    weights = {"ok": 1.0, "partial": 0.5, "failed": 0.0}
    counted = [s for s in stages if s.status in weights]
    if not counted:
        return 0.0
    return sum(weights[s.status] for s in counted) / len(counted)


def _unreachable_results(scenarios: list[Scenario], exception_type: str | None,
                          exception_message: str | None, traceback_text: str | None) -> list[ScenarioExecutionResult]:
    detail = f"{exception_type}: {exception_message}" if exception_type else (exception_message or "Entrypoint unreachable.")
    out = []
    for s in scenarios:
        out.append(ScenarioExecutionResult(
            scenario=s, status="not_executed",
            actual_behaviour={"return_value": None, "candidate": None,
                               "exception": {"type": exception_type, "message": exception_message, "traceback": traceback_text}},
            business_explanation=f"Not executed — sandbox validation failed before this scenario could run ({detail}).",
            confidence=0.0, runtime_ms=0.0, execution_state="unreachable", evidence=[], error=detail,
        ))
    return out


def run(run_id: str, workspace: Path, context: dict) -> dict:
    agent_name = context.get("agent_name") or "Unnamed Agent"
    subject_id = subject_id_for(agent_name, context.get("source_ref"))
    _ensure_subject(subject_id, agent_name)
    asd_spec = context.get("asd_spec")
    asd_dict = asd_spec.to_dict() if asd_spec else None

    stages: list[StageResult] = []

    def run_stage(name, fn):
        _write_progress(run_id, {"current_stage": name, "stages_done": len(stages), "stages_total": len(PIPELINE_STAGES)})
        start = time.time()
        try:
            status, detail, recovery = fn()
        except Exception as e:  # a stage implementation bug should not crash the whole run
            status, detail, recovery = "failed", f"Unexpected error in '{name}': {e}", []
        stages.append(StageResult(stage=name, status=status, detail=detail,
                                   recovery_suggestions=recovery, duration_ms=(time.time() - start) * 1000))
        _write_progress(run_id, {"current_stage": name, "stages_done": len(stages), "stages_total": len(PIPELINE_STAGES),
                                  "last_stage_status": status})
        return status

    def skip_rest(from_index: int, reason: str):
        for name in PIPELINE_STAGES[from_index:]:
            if any(s.stage == name for s in stages):
                continue
            stages.append(StageResult(stage=name, status="skipped", detail=reason))

    # ---- Stage 1: repository_analysis ----
    profile = None
    static_facts: dict = {}

    def _repo_analysis():
        nonlocal profile, static_facts
        profile = detector.detect(workspace)
        if profile.language != "python" or not profile.python_files:
            return "failed", "No Python source files were found in this submission.", \
                   ["Ensure the repository or upload contains .py files implementing the agent."]
        static_facts = static_analyzer.analyze(profile.python_files, workspace)
        return "ok", f"{len(profile.python_files)} Python file(s) analyzed.", []

    if run_stage("repository_analysis", _repo_analysis) == "failed":
        skip_rest(1, "Repository analysis failed.")
        _persist_not_applicable(run_id, subject_id, "No Python SCM agent source was found in this submission.")
        return {"run_id": run_id, "subject_id": subject_id, "applicable": False}

    decision_functions = workflow_graph.build(profile.python_files)
    classification = agent_classifier.classify(decision_functions)
    capability_graph = business_capability_graph.build(classification, decision_functions, profile.python_files, static_facts)
    static_facts["business_capability_graph"] = capability_graph.to_dict()
    note = registry.coverage_note(classification.primary_type)
    if not registry.is_fully_supported(classification.primary_type):
        reason = note or f"Agent type '{classification.primary_type}' is not yet supported for deep validation."
        skip_rest(1, reason)
        _persist_not_applicable(run_id, subject_id, reason, classification=classification)
        return {"run_id": run_id, "subject_id": subject_id, "applicable": False}

    repo_hash = repo_ingestor.repo_content_hash(workspace)
    scenarios, evalgen_stats = generator.generate(
        classification.primary_type,
        repo_hash,
        aggregate_names=classification.signals.get("aggregate_names"),
        capability_graph=capability_graph.to_dict(),
        asd=asd_dict,
    )
    catalogue = ScenarioCatalogue(scenarios)

    # ---- Stage 2: dependency_resolution ----
    install_log: list[str] = []

    def _deps():
        nonlocal install_log
        install_log = environment_builder.install_dependencies(workspace, profile)
        failures = [l for l in install_log if l.startswith("failed")]
        if failures:
            return "partial", "; ".join(install_log), \
                   ["Verify every requirements.txt entry is installable; pin a known-good version if a build fails."]
        return "ok", ("; ".join(install_log) if install_log else "No dependency files declared."), []

    run_stage("dependency_resolution", _deps)

    # ---- Stage 3: runtime_environment_build ----
    runtime_env = None

    def _env_build():
        nonlocal runtime_env
        bootstrap_log = environment_builder.run_db_bootstrap_scripts(workspace)
        sandbox_db_path = environment_builder.build_sandbox_db(workspace)
        env_vars = {**os.environ, **environment_builder.SAFE_ENV_DEFAULTS,
                    "DATABASE_URL": f"sqlite:///{sandbox_db_path}"}
        runtime_env = RuntimeEnvironment(
            workspace=workspace, language=profile.language, framework=profile.framework,
            entrypoint=None, sandbox_db_path=sandbox_db_path, env_vars=env_vars,
            synthetic_data={"install_log": install_log, "db_bootstrap_log": bootstrap_log},
        )
        detail = "Sandbox database and synthetic SCM datasets ready."
        if bootstrap_log:
            detail += " " + "; ".join(bootstrap_log)
        return "ok", detail, []

    run_stage("runtime_environment_build", _env_build)

    # ---- Stage 4: agent_initialization (entrypoint candidate discovery) ----
    candidates = []

    def _agent_init():
        nonlocal candidates
        candidates = entrypoint_discovery.discover(workspace, profile.python_files)
        if not candidates:
            return "failed", "No callable decision function was discovered in the repository.", \
                   ["Expose a top-level function or class method that takes business data "
                    "(inventory/demand/supplier/sku) and returns a structured decision."]
        return "ok", f"{len(candidates)} candidate entrypoint(s) identified.", []

    if run_stage("agent_initialization", _agent_init) == "failed":
        return _finalize_unreachable(run_id, subject_id, context, agent_name, stages, classification, profile,
                                      static_facts, scenarios, catalogue, "EntrypointUnreachable",
                                      "No candidate decision function was found.", None,
                                      ["Expose a top-level function or class method that takes business data "
                                       "and returns a structured decision."], capability_graph, asd_spec, evalgen_stats)

    # ---- Stage 5: entry_point_discovery ----
    top = candidates[0]
    top_desc = f"{top.class_name + '.' if top.class_name else ''}{top.function_name}"
    run_stage("entry_point_discovery", lambda: (
        "ok", f"Top-ranked candidate: {top_desc} (score {top.score:.1f}).", []))

    # ---- Stage 6: sandbox_validation (smoke test + recovery ladder) ----
    init_result = None

    def _sandbox_validation():
        nonlocal init_result
        smoke = scenarios[0] if scenarios else None
        if smoke is None:
            return "failed", "No scenarios were generated to smoke-test against.", []
        init_result = agent_initializer.initialize(workspace, candidates, smoke,
                                                     runtime_env.sandbox_db_path, runtime_env.env_vars)
        if init_result.success:
            return "ok", f"Smoke scenario executed successfully via {top_desc}.", []
        return "failed", f"{init_result.exception_type}: {init_result.exception_message}", \
               [init_result.recovery_suggestion] if init_result.recovery_suggestion else []

    if run_stage("sandbox_validation", _sandbox_validation) == "failed":
        exc_type = init_result.exception_type if init_result else "EntrypointUnreachable"
        exc_msg = init_result.exception_message if init_result else "No scenarios generated."
        tb = init_result.traceback if init_result else None
        suggestion = init_result.recovery_suggestion if init_result else None
        return _finalize_unreachable(run_id, subject_id, context, agent_name, stages, classification, profile,
                                      static_facts, scenarios, catalogue, exc_type, exc_msg, tb,
                                      [suggestion] if suggestion else [], capability_graph, asd_spec, evalgen_stats)

    working_candidates = [init_result.working_candidate]

    # ---- Stage 7: business_scenario_execution ----
    raw_outcomes = []

    def _scenario_exec():
        nonlocal raw_outcomes

        def _on_progress(done, total):
            _write_progress(run_id, {"current_stage": "business_scenario_execution",
                                      "stages_done": len(stages), "stages_total": len(PIPELINE_STAGES),
                                      "scenarios_done": done, "scenarios_total": total})

        raw_outcomes = scenario_executor.run_suite(workspace, working_candidates, list(catalogue),
                                                     runtime_env.sandbox_db_path, runtime_env.env_vars,
                                                     on_progress=_on_progress)
        crashed = sum(1 for o in raw_outcomes if o.exception)
        if raw_outcomes and crashed == len(raw_outcomes):
            return "partial", f"All {crashed} scenarios crashed despite a successful smoke test " \
                               "(likely a data-dependent failure mode).", []
        return "ok", f"{len(raw_outcomes) - crashed}/{len(raw_outcomes)} scenarios executed without crashing.", []

    run_stage("business_scenario_execution", _scenario_exec)

    # ---- Stage 8: business_decision_validation ----
    results: list[ScenarioExecutionResult] = []

    def _business_validation():
        nonlocal results
        results = [decision_validator.validate(classification.primary_type, o, capability_graph.to_dict())
                   for o in raw_outcomes]
        return "ok", f"{len(results)} scenario(s) validated using repository policy, invariants, runtime evidence, and SCM fallback references.", []

    run_stage("business_decision_validation", _business_validation)

    # Reproducibility check: re-execute a deterministic sample and compare outcome status.
    sample = list(catalogue)[:REPRODUCIBILITY_SAMPLE_SIZE]
    repro_outcomes = scenario_executor.run_suite(workspace, working_candidates, sample,
                                                   runtime_env.sandbox_db_path, runtime_env.env_vars)
    repro_results = [decision_validator.validate(classification.primary_type, o, capability_graph.to_dict())
                     for o in repro_outcomes]
    first_status_by_id = {r.scenario.id: r.status for r in results}
    repro_pairs = [(r.scenario.id, first_status_by_id.get(r.scenario.id, r.status), r.status) for r in repro_results]

    defects = defect_engine.correlate(classification.primary_type, results, static_facts)
    arch_defects = architectural_defect_engine.correlate(static_facts)
    defects = _dedup_defects(defects + arch_defects)
    root_causes = root_cause_engine.correlate(results)
    kpis = kpi_engine.compute(classification.primary_type, results)
    traces = {r.scenario.id: decision_trace.build(classification.primary_type, r, capability_graph.to_dict()) for r in results}
    traces = {sid: steps for sid, steps in traces.items() if steps}

    conformance = asd_conformance.evaluate(asd_spec, capability_graph.to_dict(), static_facts, scenarios, results)

    # ---- Stage 9: trust_score_calculation ----
    pipeline_health = _pipeline_health(stages)
    trust_scores, overall_score, readiness_label = trust_engine.compute(
        results, defects, static_facts, repro_pairs, kpis=kpis, pipeline_health_fraction=pipeline_health,
        conformance=conformance, evalgen_stats=evalgen_stats, arch_defects=arch_defects)
    run_stage("trust_score_calculation", lambda: (
        "ok", f"Overall trust score {overall_score}/100 ({readiness_label}).", []))

    previous = _previous_run(subject_id, run_id)
    historical_delta = _compute_historical_delta(previous, overall_score, defects)

    ctx = {
        "run_id": run_id, "agent_name": agent_name, "timestamp": datetime.now(timezone.utc).isoformat(),
        "classification": classification, "profile": profile, "static_facts": static_facts,
        "scenarios": scenarios, "results": results, "defects": defects, "trust_scores": trust_scores,
        "overall_score": overall_score, "readiness_label": readiness_label, "historical_delta": historical_delta,
        "kpis": kpis, "decision_traces": traces, "stages": stages, "root_causes": root_causes,
        "asd_spec": asd_spec, "conformance": conformance, "evalgen_stats": evalgen_stats,
    }
    pdf_path = REPORTS_DIR / f"{run_id}.pdf"
    pdf_builder.build_report(ctx, pdf_path)

    return {
        "run_id": run_id, "applicable": True, "subject_id": subject_id, "classification": classification,
        "scenarios": scenarios, "catalogue": catalogue, "results": results, "defects": defects,
        "trust_scores": trust_scores, "overall_score": overall_score, "readiness_label": readiness_label,
        "static_facts": static_facts, "historical_delta": historical_delta, "pdf_path": pdf_path,
        "context": context, "kpis": kpis, "decision_traces": traces, "stages": stages, "root_causes": root_causes,
        "asd_spec": asd_spec, "conformance": conformance, "evalgen_stats": evalgen_stats,
    }


def _finalize_unreachable(run_id, subject_id, context, agent_name, stages, classification, profile, static_facts,
                           scenarios, catalogue, exc_type, exc_msg, tb, recovery_suggestions,
                           capability_graph=None, asd_spec=None, evalgen_stats=None) -> dict:
    """The agent's entrypoint never became reachable. Scenarios are listed (not hidden)
    but every execution is a cheap, instantly-constructed 'unreachable' placeholder —
    no subprocesses are spawned. Business-dependent trust dimensions are `unknown`."""
    for name in PIPELINE_STAGES:
        if not any(s.stage == name for s in stages):
            stages.append(StageResult(stage=name, status="skipped",
                                       detail="Skipped — the agent's entrypoint never became reachable."))

    results = _unreachable_results(scenarios, exc_type, exc_msg, tb)
    defects = defect_engine.correlate(classification.primary_type, results, static_facts)
    arch_defects = architectural_defect_engine.correlate(static_facts)
    defects = _dedup_defects(defects + arch_defects)
    root_causes = root_cause_engine.correlate(results)
    traces = {r.scenario.id: decision_trace.build(classification.primary_type, r) for r in results}
    traces = {sid: steps for sid, steps in traces.items() if steps}

    conformance = asd_conformance.evaluate(asd_spec, (capability_graph.to_dict() if capability_graph else {}),
                                            static_facts, scenarios, results)

    pipeline_health = _pipeline_health(stages)
    trust_scores, overall_score, readiness_label = trust_engine.compute_unreachable(pipeline_health, arch_defects=arch_defects)

    previous = _previous_run(subject_id, run_id)
    historical_delta = _compute_historical_delta(previous, overall_score, defects)

    ctx = {
        "run_id": run_id, "agent_name": agent_name, "timestamp": datetime.now(timezone.utc).isoformat(),
        "classification": classification, "profile": profile, "static_facts": static_facts,
        "scenarios": scenarios, "results": results, "defects": defects, "trust_scores": trust_scores,
        "overall_score": overall_score, "readiness_label": readiness_label, "historical_delta": historical_delta,
        "kpis": [], "decision_traces": traces, "stages": stages, "root_causes": root_causes,
        "asd_spec": asd_spec, "conformance": conformance, "evalgen_stats": evalgen_stats,
    }
    pdf_path = REPORTS_DIR / f"{run_id}.pdf"
    pdf_builder.build_report(ctx, pdf_path)

    return {
        "run_id": run_id, "applicable": True, "subject_id": subject_id, "classification": classification,
        "scenarios": scenarios, "catalogue": catalogue, "results": results, "defects": defects,
        "trust_scores": trust_scores, "overall_score": overall_score, "readiness_label": readiness_label,
        "static_facts": static_facts, "historical_delta": historical_delta, "pdf_path": pdf_path,
        "context": context, "kpis": [], "decision_traces": traces, "stages": stages, "root_causes": root_causes,
        "asd_spec": asd_spec, "conformance": conformance, "evalgen_stats": evalgen_stats,
    }


def _compute_historical_delta(previous: dict | None, overall_score: float | None, defects: list) -> dict | None:
    if not previous:
        return None
    with db.session() as conn:
        prev_defects = [dict(r) for r in conn.execute(
            "SELECT * FROM defects WHERE run_id=?", (previous["run_id"],))]
    prev_types = {d["defect_type"] for d in prev_defects}
    cur_types = {d.defect_type for d in defects}
    return {
        "previous_run_id": previous["run_id"],
        "score_delta": round((overall_score or 0) - (previous["overall_trust_score"] or 0), 1),
        "new_defects": sorted(cur_types - prev_types),
        "resolved_defects": sorted(prev_types - cur_types),
        "regressions": sorted(cur_types - prev_types),
    }


def _persist_not_applicable(run_id: str, subject_id: str, reason: str, classification=None):
    now = datetime.now(timezone.utc).isoformat()
    with db.session() as conn:
        conn.execute(
            """UPDATE runs SET status='completed', applicable=0, not_applicable_reason=?,
               primary_agent_type=?, classification_confidence=?, updated_at=? WHERE run_id=?""",
            (reason, classification.primary_type if classification else None,
             classification.confidence if classification else None, now, run_id),
        )


def persist_result(result: dict, source_type: str, source_ref: str | None, context: dict):
    run_id = result["run_id"]
    now = datetime.now(timezone.utc).isoformat()

    if not result.get("applicable"):
        with db.session() as conn:
            conn.execute("UPDATE runs SET source_type=?, source_ref=?, updated_at=? WHERE run_id=?",
                         (source_type, source_ref, now, run_id))
        return

    classification = result["classification"]
    with db.session() as conn:
        conn.execute(
            """UPDATE runs SET status='completed', applicable=1, source_type=?, source_ref=?,
               primary_agent_type=?, classification_confidence=?, secondary_capabilities=?,
               suite_hash=?, overall_trust_score=?, production_readiness=?, updated_at=?
               WHERE run_id=?""",
            (source_type, source_ref, classification.primary_type, classification.confidence,
             db.dump(classification.secondary_capabilities), result["catalogue"].suite_hash(),
             result["overall_score"], result["readiness_label"], now, run_id),
        )

        for s in result["scenarios"]:
            conn.execute(
                """INSERT INTO scenarios (id, run_id, name, category, business_objective, inputs,
                   initial_state, expected_behaviour, severity_if_failed, traceability) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (s.id, run_id, s.name, s.category, s.business_objective, db.dump(s.inputs),
                 db.dump(s.initial_state), s.expected_behaviour, s.severity_if_failed, db.dump(s.traceability)),
            )

        for r in result["results"]:
            conn.execute(
                """INSERT INTO scenario_executions (run_id, scenario_id, status, execution_state, actual_behaviour,
                   business_explanation, confidence, runtime_ms, error) VALUES (?,?,?,?,?,?,?,?,?)""",
                (run_id, r.scenario.id, r.status, r.execution_state, db.dump(r.actual_behaviour),
                 r.business_explanation, r.confidence, r.runtime_ms, r.error),
            )
            for e in r.evidence:
                conn.execute(
                    "INSERT INTO evidence (id, run_id, scenario_id, evidence_type, detail) VALUES (?,?,?,?,?)",
                    (e.id, run_id, e.scenario_id, e.evidence_type, db.dump(e.detail)),
                )

        for d in result["defects"]:
            conn.execute(
                """INSERT INTO defects (id, run_id, category, defect_type, title, severity, confidence,
                   business_impact, technical_explanation, recommendation, verification_steps,
                   scenario_refs, evidence_refs, file_path, function_name, violated_requirement, root_cause,
                   line_number, governance_refs) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (d.id, run_id, d.category, d.defect_type, d.title, d.severity, d.confidence,
                 d.business_impact, d.technical_explanation, d.recommendation, db.dump(d.verification_steps),
                 db.dump(d.scenario_refs), db.dump(d.evidence_refs), d.file_path, d.function_name,
                 db.dump(d.violated_requirement), d.root_cause, d.line_number, db.dump(d.governance_refs)),
            )

        for ts in result["trust_scores"]:
            conn.execute(
                """INSERT INTO trust_scores (run_id, dimension, category, score, max_score, rationale,
                   state, reason, evidence_refs) VALUES (?,?,?,?,?,?,?,?,?)""",
                (run_id, ts.dimension, ts.category, ts.score, ts.max_score, ts.rationale,
                 ts.state, ts.reason, db.dump(ts.evidence_refs)),
            )

        if result.get("historical_delta"):
            hd = result["historical_delta"]
            conn.execute(
                """INSERT INTO historical_deltas (run_id, previous_run_id, subject_id, score_delta,
                   new_defects, resolved_defects, regressions) VALUES (?,?,?,?,?,?,?)""",
                (run_id, hd["previous_run_id"], result["subject_id"], hd["score_delta"],
                 db.dump(hd["new_defects"]), db.dump(hd["resolved_defects"]), db.dump(hd["regressions"])),
            )

        for k in result.get("kpis", []):
            conn.execute(
                "INSERT INTO kpi_results (run_id, name, value, unit, description) VALUES (?,?,?,?,?)",
                (run_id, k.name, k.value, k.unit, k.description),
            )

        for scenario_id, steps in result.get("decision_traces", {}).items():
            conn.execute(
                "INSERT INTO decision_traces (run_id, scenario_id, steps) VALUES (?,?,?)",
                (run_id, scenario_id, db.dump(steps)),
            )

        for i, stage in enumerate(result.get("stages", [])):
            conn.execute(
                """INSERT INTO pipeline_stages (run_id, stage, status, detail, recovery_suggestions,
                   duration_ms, stage_order) VALUES (?,?,?,?,?,?,?)""",
                (run_id, stage.stage, stage.status, stage.detail, db.dump(stage.recovery_suggestions),
                 stage.duration_ms, i),
            )

        for rc in result.get("root_causes", []):
            conn.execute(
                """INSERT INTO root_causes (id, run_id, exception_type, normalized_message, confidence,
                   recovery_suggestion, affected_scenario_ids, affected_count, representative_traceback)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (rc.id, run_id, rc.exception_type, rc.normalized_message, rc.confidence, rc.recovery_suggestion,
                 db.dump(rc.affected_scenario_ids), rc.affected_count, rc.representative_traceback),
            )

        pdf_bytes = Path(result["pdf_path"]).read_bytes()
        conn.execute("INSERT INTO reports (run_id, pdf_path, generated_at, pdf_data) VALUES (?,?,?,?)",
                     (run_id, str(result["pdf_path"]), now, pdf_bytes if db.USE_POSTGRES else sqlite3.Binary(pdf_bytes)))

        capability_graph = (result.get("static_facts") or {}).get("business_capability_graph")
        if capability_graph:
            conn.execute("INSERT INTO capability_graphs (run_id, graph) VALUES (?,?)",
                         (run_id, db.dump(capability_graph)))

        asd_spec = result.get("asd_spec")
        if asd_spec:
            conn.execute("INSERT INTO agent_specifications (run_id, spec) VALUES (?,?)",
                         (run_id, db.dump(asd_spec.to_dict())))

        conformance = result.get("conformance")
        if conformance:
            conn.execute(
                """INSERT INTO conformance_summary (run_id, conformance_score, requirement_coverage,
                   functional_coverage, input_coverage, output_coverage, constraint_coverage,
                   integration_coverage, kpi_coverage, decision_coverage) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (run_id, conformance.conformance_score, conformance.requirement_coverage,
                 conformance.functional_coverage, conformance.input_coverage, conformance.output_coverage,
                 conformance.constraint_coverage, conformance.integration_coverage, conformance.kpi_coverage,
                 conformance.decision_coverage),
            )
            for rc in conformance.requirements:
                conn.execute(
                    """INSERT INTO requirement_conformance (run_id, requirement_id, status, confidence, rationale,
                       repository_evidence, scenario_refs, evidence_refs) VALUES (?,?,?,?,?,?,?,?)""",
                    (run_id, rc.requirement_id, rc.status, rc.confidence, rc.rationale,
                     db.dump(rc.repository_evidence), db.dump(rc.scenario_refs), db.dump(rc.evidence_refs)),
                )

        evalgen_stats = result.get("evalgen_stats")
        if evalgen_stats:
            conn.execute(
                """INSERT INTO evalgen_stats (run_id, pairwise_coverage, parameter_coverage, interaction_coverage,
                   constraint_coverage, redundant_scenario_reduction, total_candidate_scenarios,
                   optimized_scenario_count, parameters) VALUES (?,?,?,?,?,?,?,?,?)""",
                (run_id, evalgen_stats.pairwise_coverage, evalgen_stats.parameter_coverage,
                 evalgen_stats.interaction_coverage, evalgen_stats.constraint_coverage,
                 evalgen_stats.redundant_scenario_reduction, evalgen_stats.total_candidate_scenarios,
                 evalgen_stats.optimized_scenario_count, db.dump(evalgen_stats.parameters)),
            )
