"""Fixed deterministic scoring. No LLM input ever reaches this module.

Each dimension starts at its max_score (out of 100, weighted) and findings
in that category deduct score_impact points, floored at 0. The overall
trust score is a fixed weighted average across dimensions.
"""
from dataclasses import dataclass

from .rule_engine import RawFinding
from ..report_schema import DIMENSIONS, ScoreBreakdownItem

DIMENSION_MAX = 100.0

DIMENSION_WEIGHTS = {
    "Specification Completeness": 0.15,
    "Implementation Hygiene": 0.10,
    "Reliability & Error Handling": 0.20,
    "Security Hygiene": 0.20,
    "Input / Output Contract Clarity": 0.15,
    "Observability / Traceability": 0.10,
    "SCM Readiness / Business Fit": 0.10,
}

assert abs(sum(DIMENSION_WEIGHTS.values()) - 1.0) < 1e-6

VERDICT_THRESHOLDS = [
    (80.0, "Demo Ready"),
    (55.0, "Conditionally Ready"),
    (0.0, "High Risk"),
]


@dataclass
class ScoringResult:
    breakdown: list[ScoreBreakdownItem]
    overall_score: float
    verdict: str


def score_dimension(dimension: str, findings: list[RawFinding]) -> ScoreBreakdownItem:
    relevant = [f for f in findings if f.category == dimension]
    deduction = sum(f.score_impact for f in relevant)
    score = max(0.0, DIMENSION_MAX - deduction)
    if not relevant:
        remarks = "No issues detected for this dimension."
    else:
        remarks = f"{len(relevant)} finding(s) reduced this score by {deduction:.0f} points."
    return ScoreBreakdownItem(dimension=dimension, score=round(score, 1), max_score=DIMENSION_MAX, remarks=remarks)


def compute_verdict(overall: float) -> str:
    for threshold, verdict in VERDICT_THRESHOLDS:
        if overall >= threshold:
            return verdict
    return "High Risk"


def compute_score(findings: list[RawFinding]) -> ScoringResult:
    breakdown = [score_dimension(d, findings) for d in DIMENSIONS]
    overall = sum(item.score * DIMENSION_WEIGHTS[item.dimension] for item in breakdown)
    overall = round(overall, 1)
    verdict = compute_verdict(overall)
    return ScoringResult(breakdown=breakdown, overall_score=overall, verdict=verdict)
