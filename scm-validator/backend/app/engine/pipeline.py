"""Orchestrates the deterministic-first validation flow: ingest -> analyze -> rules ->
score -> evidence -> recommendations -> (optional) LLM insights -> persist."""
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from . import repo_ingestor, static_analyzer
from . import rule_engine_v2 as rule_engine
from . import scoring_engine_v2 as scoring_engine
from . import positive_signals, evidence_builder, recommendation_builder, llm_insights
from ..report_schema import Finding, Summary, ValidationResult
from .. import db


def _finding_id(run_id: str, idx: int) -> str:
    return f"f_{hashlib.sha1(f'{run_id}:{idx}'.encode()).hexdigest()[:10]}"


def run_validation(run_id: str, workspace: Path, context: dict) -> ValidationResult:
    facts = static_analyzer.build_repo_facts(workspace)

    # Collect positive signals
    positive_signals_list = positive_signals.collect_all_positive_signals(facts)

    # Run deterministic rules
    raw_findings = rule_engine.run_all_rules(facts, context)

    finding_ids = [_finding_id(run_id, i) for i in range(len(raw_findings))]
    evidence_list, refs_per_finding = evidence_builder.build_evidence(run_id, raw_findings)

    findings = [
        Finding(
            id=finding_ids[i],
            severity=rf.severity,
            category=rf.category,
            title=rf.title,
            description=rf.description,
            why_it_matters=rf.why_it_matters,
            score_impact=rf.score_impact,
            evidence_refs=refs_per_finding[i],
        )
        for i, rf in enumerate(raw_findings)
    ]

    # Compute score with positive signals factored in
    scoring = scoring_engine.compute_score(raw_findings, positive_signals_list)
    recommendations = recommendation_builder.build_recommendations(run_id, raw_findings, finding_ids)

    ai_insights = []
    if context.get("enable_llm_insights"):
        ai_insights = llm_insights.generate_insights(
            context.get("agent_name", ""), context.get("use_case"), scoring.breakdown, findings
        )

    summary = Summary(
        agent_name=context.get("agent_name", "Unnamed Agent"),
        run_id=run_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        overall_trust_score=scoring.overall_score,
        demo_readiness=scoring.demo_readiness,
        production_readiness=scoring.production_readiness,
        status="completed",
    )

    return ValidationResult(
        summary=summary,
        score_breakdown=scoring.breakdown,
        positive_signals=positive_signals_list,
        findings=findings,
        recommendations=recommendations,
        evidence=evidence_list,
        ai_insights=ai_insights,
    )


def persist_result(result: ValidationResult, source_type: str, source_ref: str | None, context: dict):
    run_id = result.summary.run_id
    now = datetime.now(timezone.utc).isoformat()
    with db.get_conn() as conn:
        conn.execute(
            """UPDATE runs SET status=?, overall_trust_score=?, demo_readiness=?, production_readiness=?, updated_at=? WHERE run_id=?""",
            (result.summary.status, result.summary.overall_trust_score, result.summary.demo_readiness, result.summary.production_readiness, now, run_id),
        )
        for item in result.score_breakdown:
            conn.execute(
                "INSERT INTO score_breakdown (run_id, dimension, score, max_score, remarks) VALUES (?,?,?,?,?)",
                (run_id, item.dimension, item.score, item.max_score, item.remarks),
            )
        for signal in result.positive_signals:
            conn.execute("INSERT INTO positive_signals (run_id, signal) VALUES (?,?)", (run_id, signal))
        for f in result.findings:
            conn.execute(
                """INSERT INTO findings (id, run_id, severity, category, title, description, why_it_matters, score_impact, evidence_refs)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (f.id, run_id, f.severity, f.category, f.title, f.description, f.why_it_matters, f.score_impact, db.dump_refs(f.evidence_refs)),
            )
        for r in result.recommendations:
            conn.execute(
                """INSERT INTO recommendations (id, run_id, finding_id, title, recommendation, priority, expected_impact)
                   VALUES (?,?,?,?,?,?,?)""",
                (r.id, run_id, r.finding_id, r.title, r.recommendation, r.priority, r.expected_impact),
            )
        for e in result.evidence:
            conn.execute(
                """INSERT INTO evidence (id, run_id, file_path, line_start, line_end, snippet, reason)
                   VALUES (?,?,?,?,?,?,?)""",
                (e.id, run_id, e.file_path, e.line_start, e.line_end, e.snippet, e.reason),
            )
        for insight in result.ai_insights:
            conn.execute("INSERT INTO ai_insights (run_id, insight) VALUES (?,?)", (run_id, insight))


def mark_failed(run_id: str, error: str):
    now = datetime.now(timezone.utc).isoformat()
    with db.get_conn() as conn:
        conn.execute("UPDATE runs SET status='failed', error=?, updated_at=? WHERE run_id=?", (error, now, run_id))
