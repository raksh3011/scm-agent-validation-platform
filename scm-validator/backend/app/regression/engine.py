"""Continuous Audit / Regression Engine — compares any two completed runs (the same
repository at two points in time, or two different implementations of the same agent
type) and reports what actually changed: which defects were introduced or resolved,
which trust dimensions moved, which scenarios flipped status, and how KPIs and
specification conformance evolved.

Deliberately stateless and computed on demand from the existing persisted tables —
re-running the same comparison twice always yields the same result, and there is no
separate "comparison" table to go stale or fall out of sync with the underlying runs.

Scenario-level comparison is keyed by scenario `name` rather than `id`: ids are
sequential per run (SC-0001, SC-0002, ...) and not stable across runs, but the
deterministic generator produces the same axis-derived names for any two runs sharing
an agent type, so name is the stable join key across versions/repos."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from ..core import db

_SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


@dataclass
class RunSnapshot:
    run_id: str
    agent_name: str
    primary_agent_type: str | None
    overall_trust_score: float | None
    production_readiness: str | None
    created_at: str


@dataclass
class DefectDelta:
    defect_type: str
    category: str
    title: str
    status: Literal["new", "resolved", "persisting"]
    severity_before: str | None = None
    severity_after: str | None = None
    severity_change: Literal["worse", "better", "unchanged", None] = None


@dataclass
class TrustDimensionDelta:
    dimension: str
    category: str
    score_before: float | None
    score_after: float | None
    max_score: float
    delta: float | None
    state_before: str
    state_after: str


@dataclass
class KpiDelta:
    name: str
    value_before: float | None
    value_after: float | None
    delta: float | None
    unit: str


@dataclass
class ConformanceDelta:
    metric: str
    before: float | None
    after: float | None
    delta: float | None


@dataclass
class ScenarioFlip:
    name: str
    category: str
    status_before: str
    status_after: str
    direction: Literal["regression", "improvement"]


@dataclass
class ComparisonReport:
    run_a: RunSnapshot
    run_b: RunSnapshot
    verdict: Literal["improved", "regressed", "mixed", "unchanged", "not_comparable"]
    score_delta: float | None
    defect_deltas: list[DefectDelta] = field(default_factory=list)
    trust_deltas: list[TrustDimensionDelta] = field(default_factory=list)
    kpi_deltas: list[KpiDelta] = field(default_factory=list)
    conformance_deltas: list[ConformanceDelta] = field(default_factory=list)
    scenario_flips: list[ScenarioFlip] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _snapshot(conn, run_id: str) -> RunSnapshot:
    row = conn.execute(
        "SELECT run_id, agent_name, primary_agent_type, overall_trust_score, production_readiness, created_at "
        "FROM runs WHERE run_id=?", (run_id,),
    ).fetchone()
    if not row:
        raise ValueError(f"Run {run_id} not found")
    return RunSnapshot(**dict(row))


def _defects(conn, run_id: str) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT category, defect_type, title, severity FROM defects WHERE run_id=?", (run_id,))]


def _defect_deltas(defects_a: list[dict], defects_b: list[dict]) -> list[DefectDelta]:
    by_type_a = {d["defect_type"]: d for d in defects_a}
    by_type_b = {d["defect_type"]: d for d in defects_b}
    types_a, types_b = set(by_type_a), set(by_type_b)

    deltas: list[DefectDelta] = []
    for t in sorted(types_b - types_a):
        d = by_type_b[t]
        deltas.append(DefectDelta(defect_type=t, category=d["category"], title=d["title"],
                                   status="new", severity_after=d["severity"]))
    for t in sorted(types_a - types_b):
        d = by_type_a[t]
        deltas.append(DefectDelta(defect_type=t, category=d["category"], title=d["title"],
                                   status="resolved", severity_before=d["severity"]))
    for t in sorted(types_a & types_b):
        da, db_ = by_type_a[t], by_type_b[t]
        ra, rb = _SEV_RANK.get(da["severity"], 1), _SEV_RANK.get(db_["severity"], 1)
        change = "unchanged" if ra == rb else ("worse" if rb < ra else "better")
        deltas.append(DefectDelta(defect_type=t, category=db_["category"], title=db_["title"],
                                   status="persisting", severity_before=da["severity"],
                                   severity_after=db_["severity"], severity_change=change))
    return deltas


def _trust_scores(conn, run_id: str) -> dict[str, dict]:
    return {r["dimension"]: dict(r) for r in conn.execute(
        "SELECT dimension, category, score, max_score, state FROM trust_scores WHERE run_id=?", (run_id,))}


def _trust_deltas(ta: dict[str, dict], tb: dict[str, dict]) -> list[TrustDimensionDelta]:
    deltas = []
    for dim in sorted(set(ta) | set(tb)):
        a, b = ta.get(dim), tb.get(dim)
        score_a = a["score"] if a and a["state"] == "computed" else None
        score_b = b["score"] if b and b["state"] == "computed" else None
        delta = round(score_b - score_a, 2) if score_a is not None and score_b is not None else None
        deltas.append(TrustDimensionDelta(
            dimension=dim, category=(b or a)["category"], score_before=score_a, score_after=score_b,
            max_score=(b or a)["max_score"], delta=delta,
            state_before=a["state"] if a else "unknown", state_after=b["state"] if b else "unknown",
        ))
    return deltas


def _kpis(conn, run_id: str) -> dict[str, dict]:
    return {r["name"]: dict(r) for r in conn.execute(
        "SELECT name, value, unit FROM kpi_results WHERE run_id=?", (run_id,))}


def _kpi_deltas(ka: dict[str, dict], kb: dict[str, dict]) -> list[KpiDelta]:
    deltas = []
    for name in sorted(set(ka) | set(kb)):
        a, b = ka.get(name), kb.get(name)
        va = a["value"] if a else None
        vb = b["value"] if b else None
        delta = round(vb - va, 2) if va is not None and vb is not None else None
        deltas.append(KpiDelta(name=name, value_before=va, value_after=vb, delta=delta, unit=(b or a)["unit"]))
    return deltas


def _conformance(conn, run_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM conformance_summary WHERE run_id=?", (run_id,)).fetchone()
    return dict(row) if row else None


def _conformance_deltas(ca: dict | None, cb: dict | None) -> list[ConformanceDelta]:
    if not ca and not cb:
        return []
    metrics = ["conformance_score", "requirement_coverage", "functional_coverage", "input_coverage",
               "output_coverage", "constraint_coverage", "integration_coverage", "kpi_coverage", "decision_coverage"]
    deltas = []
    for m in metrics:
        before = ca.get(m) if ca else None
        after = cb.get(m) if cb else None
        delta = round(after - before, 1) if before is not None and after is not None else None
        deltas.append(ConformanceDelta(metric=m, before=before, after=after, delta=delta))
    return deltas


def _scenarios_with_status(conn, run_id: str) -> list[dict]:
    return [dict(r) for r in conn.execute(
        """SELECT s.name, s.category, e.status FROM scenarios s
           JOIN scenario_executions e ON e.run_id = s.run_id AND e.scenario_id = s.id
           WHERE s.run_id=?""", (run_id,))]


_STATUS_RANK = {"pass": 0, "partial": 1, "error": 2, "fail": 3, "not_executed": 4}


def _scenario_flips(scen_a: list[dict], scen_b: list[dict]) -> list[ScenarioFlip]:
    by_name_a = {s["name"]: s for s in scen_a}
    by_name_b = {s["name"]: s for s in scen_b}
    flips = []
    for name in sorted(set(by_name_a) & set(by_name_b)):
        a, b = by_name_a[name], by_name_b[name]
        if a["status"] == b["status"]:
            continue
        direction = "regression" if _STATUS_RANK.get(b["status"], 1) > _STATUS_RANK.get(a["status"], 1) else "improvement"
        flips.append(ScenarioFlip(name=name, category=b["category"], status_before=a["status"],
                                   status_after=b["status"], direction=direction))
    return flips


def compare(run_id_a: str, run_id_b: str) -> ComparisonReport:
    with db.session() as conn:
        snap_a, snap_b = _snapshot(conn, run_id_a), _snapshot(conn, run_id_b)
        defect_deltas = _defect_deltas(_defects(conn, run_id_a), _defects(conn, run_id_b))
        trust_deltas = _trust_deltas(_trust_scores(conn, run_id_a), _trust_scores(conn, run_id_b))
        kpi_deltas = _kpi_deltas(_kpis(conn, run_id_a), _kpis(conn, run_id_b))
        conformance_deltas = _conformance_deltas(_conformance(conn, run_id_a), _conformance(conn, run_id_b))
        scenario_flips = _scenario_flips(_scenarios_with_status(conn, run_id_a), _scenarios_with_status(conn, run_id_b))

    score_delta = None
    if snap_a.overall_trust_score is not None and snap_b.overall_trust_score is not None:
        score_delta = round(snap_b.overall_trust_score - snap_a.overall_trust_score, 1)

    new_defects = [d for d in defect_deltas if d.status == "new"]
    resolved_defects = [d for d in defect_deltas if d.status == "resolved"]
    worsened = [d for d in defect_deltas if d.severity_change == "worse"]
    regressions = [f for f in scenario_flips if f.direction == "regression"]
    improvements = [f for f in scenario_flips if f.direction == "improvement"]

    if score_delta is None:
        verdict = "not_comparable"
    elif new_defects or worsened or regressions:
        verdict = "regressed" if not (resolved_defects or improvements) and score_delta < 0 else "mixed"
        if score_delta > 0 and not (new_defects or worsened or regressions):
            verdict = "improved"
    elif resolved_defects or improvements or score_delta > 0:
        verdict = "improved"
    else:
        verdict = "unchanged"

    summary = (
        f"{snap_b.agent_name} moved from {snap_a.overall_trust_score} to {snap_b.overall_trust_score} "
        f"({'+' if (score_delta or 0) >= 0 else ''}{score_delta}). "
        f"{len(new_defects)} new defect(s), {len(resolved_defects)} resolved, "
        f"{len(regressions)} scenario regression(s), {len(improvements)} scenario improvement(s)."
    )

    return ComparisonReport(
        run_a=snap_a, run_b=snap_b, verdict=verdict, score_delta=score_delta,
        defect_deltas=defect_deltas, trust_deltas=trust_deltas, kpi_deltas=kpi_deltas,
        conformance_deltas=conformance_deltas, scenario_flips=scenario_flips, summary=summary,
    )
