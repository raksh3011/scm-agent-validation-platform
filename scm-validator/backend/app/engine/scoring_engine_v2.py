"""Fixed deterministic scoring with positive signals factored in.

Dimensions (v2):
- Specification Completeness (15%)
- Reliability & Error Handling (20%)
- AI/LLM Risk Controls (25%) ← expanded, was buried in generic checks
- SCM Logic Quality (15%)
- Observability / Traceability (10%)
- Demo Readiness (10%)
- Production Readiness (5%) ← bonus dimension
"""
from dataclasses import dataclass
from .rule_engine_v2 import RawFinding
from ..report_schema import DIMENSIONS, ScoreBreakdownItem, DemoReadiness, ProductionReadiness

DIMENSION_MAX = 100.0

DIMENSION_WEIGHTS = {
    "Specification Completeness": 0.15,
    "Reliability & Error Handling": 0.20,
    "AI/LLM Risk Controls": 0.25,
    "SCM Logic Quality": 0.15,
    "Observability / Traceability": 0.10,
    "Demo Readiness": 0.10,
    "Production Readiness": 0.05,
}

assert abs(sum(DIMENSION_WEIGHTS.values()) - 1.0) < 1e-6

# Positive signal bonuses (minor boost, not a free pass)
SIGNAL_BONUS = {
    "Perceive-Decide-Act structure documented in comments": 5,
    "LLM judgment isolated in dedicated function(s)": 5,
    "Mock vs live mode selectable at runtime": 10,
    "Deterministic core logic detected": 5,
    "Supply chain arithmetic patterns detected (ROP, lead time, safety stock)": 10,
    "Reorder Point calculation includes lead time": 5,
    "Reorder Point calculation includes safety stock": 5,
    "Multi-factor supplier selection (price, reliability, lead time)": 5,
    "Demand adjustment/forecasting integrated into decision": 5,
    "README/documentation present describing agent purpose": 8,
    "Module docstring or extensive comments documenting objective": 5,
    "Decision reasoning/justification returned with action": 8,
}

@dataclass
class ScoringResult:
    breakdown: list[ScoreBreakdownItem]
    overall_score: float
    demo_readiness: DemoReadiness
    production_readiness: ProductionReadiness


def score_dimension(dimension: str, findings: list[RawFinding], positive_signals: list[str] = None) -> ScoreBreakdownItem:
    """Score a dimension: start at max, deduct for findings, add for signals."""
    if positive_signals is None:
        positive_signals = []

    relevant_findings = [f for f in findings if f.category == dimension]
    deduction = sum(f.score_impact for f in relevant_findings)

    # Add bonuses from positive signals
    bonus = 0
    for signal in positive_signals:
        bonus += SIGNAL_BONUS.get(signal, 0)

    score = max(0.0, min(DIMENSION_MAX, DIMENSION_MAX - deduction + bonus))

    remarks = []
    if relevant_findings:
        remarks.append(f"{len(relevant_findings)} finding(s) reduced score by {deduction:.0f} points")
    if bonus > 0:
        remarks.append(f"{len([s for s in positive_signals if SIGNAL_BONUS.get(s, 0) > 0])} positive signal(s) added {bonus:.0f} points")
    if not remarks:
        remarks.append("No issues detected for this dimension")

    return ScoreBreakdownItem(
        dimension=dimension,
        score=round(score, 1),
        max_score=DIMENSION_MAX,
        remarks="; ".join(remarks),
    )


def compute_demo_readiness(score: float, findings: list[RawFinding], positive_signals: list[str]) -> DemoReadiness:
    """Demo readiness: can the agent run in a safe mock environment?"""
    # Demo Ready: score ≥70 AND has mock mode available
    # Conditionally Ready: score ≥50
    # Not Ready: score < 50

    has_mock = any("mock" in sig.lower() for sig in positive_signals)

    if score >= 70 and has_mock:
        return "Demo Ready"
    elif score >= 50:
        return "Conditionally Ready"
    else:
        return "Not Ready"


def compute_production_readiness(score: float, findings: list[RawFinding], positive_signals: list[str]) -> ProductionReadiness:
    """Production readiness: can the agent run safely in production?"""
    # Production Ready: score ≥85, no Critical findings, LLM calls protected
    # Requires Hardening: score ≥70, has some LLM protections
    # Not Ready: score < 70 OR has critical unresolved LLM risks

    critical_count = len([f for f in findings if f.severity == "Critical"])
    llm_high_count = len([f for f in findings if "LLM" in f.category and f.severity == "High"])

    # Check if key error handling is in place
    has_llm_error_handling = not any(r.rule_id == "LLM_NO_ERROR_HANDLING" for r in findings)
    has_logging = not any(r.rule_id == "OBS_NO_LOGGING" for r in findings)

    if score >= 85 and critical_count == 0 and has_llm_error_handling and has_logging:
        return "Production Ready"
    elif score >= 70 and llm_high_count <= 1:
        return "Requires Hardening"
    else:
        return "Not Ready"


def compute_score(findings: list[RawFinding], positive_signals: list[str] = None) -> ScoringResult:
    """Compute deterministic score with signal bonuses."""
    if positive_signals is None:
        positive_signals = []

    breakdown = [score_dimension(d, findings, positive_signals) for d in DIMENSIONS]
    overall = sum(item.score * DIMENSION_WEIGHTS[item.dimension] for item in breakdown)
    overall = round(overall, 1)

    demo_ready = compute_demo_readiness(overall, findings, positive_signals)
    prod_ready = compute_production_readiness(overall, findings, positive_signals)

    return ScoringResult(
        breakdown=breakdown,
        overall_score=overall,
        demo_readiness=demo_ready,
        production_readiness=prod_ready,
    )
