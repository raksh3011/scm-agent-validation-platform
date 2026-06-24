"""Fixed deterministic scoring with positive signals factored in.

Scoring model (deterministic, repeatable):
  dimension_score = clamp(0, 100, 100 - sum(finding deductions in dim) + capped signal bonus for dim)

Key rules that keep results honest:
  - Positive-signal bonuses are DIMENSION-SPECIFIC (a SCM-logic signal only lifts
    SCM Logic Quality, not AI/LLM Risk Controls). This prevents good structure
    from masking a fragile LLM integration.
  - Bonus per dimension is capped (SIGNAL_BONUS_CAP) so signals can never fully
    erase a High/Critical finding in that dimension.
  - Any High finding caps its dimension at MAX_WITH_HIGH; any Critical caps at
    MAX_WITH_CRITICAL, regardless of bonuses.

Dimensions (weights sum to 1.0):
  Specification Completeness   15%
  Reliability & Error Handling 20%
  AI/LLM Risk Controls         25%
  SCM Logic Quality            15%
  Observability / Traceability 10%
  Demo Readiness               10%
  Production Readiness          5%
"""
from dataclasses import dataclass
from .rule_engine_v2 import RawFinding
from ..report_schema import DIMENSIONS, ScoreBreakdownItem, DemoReadiness, ProductionReadiness

DIMENSION_MAX = 100.0
SIGNAL_BONUS_CAP = 20.0          # most a dimension can gain from positive signals
MAX_WITH_HIGH = 80.0             # a dimension with a High finding can't score above this
MAX_WITH_CRITICAL = 60.0         # a dimension with a Critical finding can't score above this

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

# Each positive signal lifts ONE specific dimension by N points (before the cap).
# signal_substring -> (dimension, points). Matched by substring so detector wording
# can evolve without breaking scoring.
SIGNAL_BONUS: list[tuple[str, str, float]] = [
    # Structure / SCM logic
    ("Perceive-Decide-Act structure documented", "SCM Logic Quality", 6),
    ("Perceive phase function", "SCM Logic Quality", 3),
    ("Decide phase function", "SCM Logic Quality", 3),
    ("Act phase function", "SCM Logic Quality", 3),
    ("Deterministic supplier/option selection", "SCM Logic Quality", 5),
    ("Supply chain arithmetic patterns", "SCM Logic Quality", 8),
    ("Reorder Point calculation includes lead time", "SCM Logic Quality", 5),
    ("Reorder Point calculation includes safety stock", "SCM Logic Quality", 5),
    ("Multi-factor supplier selection", "SCM Logic Quality", 6),
    ("Demand adjustment/forecasting integrated", "SCM Logic Quality", 5),
    ("Target stock calculation for review period", "SCM Logic Quality", 4),
    ("Rule-based or weighted scoring logic", "SCM Logic Quality", 4),
    # AI/LLM risk controls (positive containment of the LLM)
    ("LLM judgment isolated in dedicated function", "AI/LLM Risk Controls", 8),
    ("LLM client imported within judgment function", "AI/LLM Risk Controls", 4),
    # Demo readiness
    ("Mock vs live mode separation", "Demo Readiness", 10),
    ("Mock vs live mode selectable at runtime", "Demo Readiness", 8),
    ("Mock/test mode with recorded decisions", "Demo Readiness", 8),
    # Specification
    ("README/documentation present", "Specification Completeness", 8),
    ("Module docstring or extensive comments", "Specification Completeness", 5),
    ("Inline comments explaining logic", "Specification Completeness", 4),
    # Observability / audit
    ("Decision reasoning/justification returned", "Observability / Traceability", 8),
    ("Intermediate decision values exposed", "Observability / Traceability", 6),
    ("Supplier selection decision included in output", "Observability / Traceability", 4),
    # Reliability
    ("Try-except error handling present", "Reliability & Error Handling", 6),
    ("Input validation / assertions present", "Reliability & Error Handling", 5),
]


@dataclass
class ScoringResult:
    breakdown: list[ScoreBreakdownItem]
    overall_score: float
    demo_readiness: DemoReadiness
    production_readiness: ProductionReadiness


def _bonus_for_dimension(dimension: str, positive_signals: list[str]) -> tuple[float, int]:
    """Return (capped_bonus, num_signals_applied) for a dimension."""
    total = 0.0
    count = 0
    for signal in positive_signals:
        for substr, dim, pts in SIGNAL_BONUS:
            if dim == dimension and substr.lower() in signal.lower():
                total += pts
                count += 1
                break
    return min(total, SIGNAL_BONUS_CAP), count


DERIVED_DIMENSIONS = {"Demo Readiness", "Production Readiness"}


def _score_demo_dimension(findings: list[RawFinding], positive_signals: list[str]) -> tuple[float, str]:
    """Derived: readiness to demo safely. Driven by mock-mode availability and blocking risks."""
    score = DIMENSION_MAX
    notes = []
    has_mock = any("mock" in s.lower() for s in positive_signals)
    if not has_mock:
        score -= 40
        notes.append("no mock/demo mode (-40)")
    else:
        notes.append("mock/demo mode available")
    if any(f.severity == "Critical" for f in findings):
        score -= 30
        notes.append("critical finding blocks demo (-30)")
    return max(0.0, score), "; ".join(notes)


def _score_production_dimension(findings: list[RawFinding], positive_signals: list[str]) -> tuple[float, str]:
    """Derived: readiness to run against live systems. Driven by LLM hardening, logging, criticals."""
    score = DIMENSION_MAX
    notes = []
    llm_high = [f for f in findings if f.category == "AI/LLM Risk Controls" and f.severity in ("High", "Critical")]
    for _ in llm_high:
        score -= 18
    if llm_high:
        notes.append(f"{len(llm_high)} unhardened LLM risk(s) (-{18*len(llm_high)})")
    if any(r.rule_id == "OBS_NO_LOGGING" for r in findings):
        score -= 15
        notes.append("no audit logging (-15)")
    if any(r.rule_id == "REL_NO_ERROR_HANDLING" for r in findings):
        score -= 12
        notes.append("no error handling (-12)")
    if any(f.severity == "Critical" for f in findings):
        score -= 25
        notes.append("critical finding (-25)")
    if not notes:
        notes.append("no production blockers detected")
    return max(0.0, score), "; ".join(notes)


def score_dimension(dimension: str, findings: list[RawFinding], positive_signals: list[str]) -> ScoreBreakdownItem:
    if dimension == "Demo Readiness":
        score, remarks = _score_demo_dimension(findings, positive_signals)
        return ScoreBreakdownItem(dimension=dimension, score=round(score, 1), max_score=DIMENSION_MAX, remarks=remarks)
    if dimension == "Production Readiness":
        score, remarks = _score_production_dimension(findings, positive_signals)
        return ScoreBreakdownItem(dimension=dimension, score=round(score, 1), max_score=DIMENSION_MAX, remarks=remarks)

    relevant = [f for f in findings if f.category == dimension]
    deduction = sum(f.score_impact for f in relevant)
    bonus, signal_count = _bonus_for_dimension(dimension, positive_signals)

    score = DIMENSION_MAX - deduction + bonus

    # Severity ceilings: a serious finding must keep the dimension visibly below max.
    if any(f.severity == "Critical" for f in relevant):
        score = min(score, MAX_WITH_CRITICAL)
    elif any(f.severity == "High" for f in relevant):
        score = min(score, MAX_WITH_HIGH)

    score = max(0.0, min(DIMENSION_MAX, score))

    parts = []
    if relevant:
        parts.append(f"{len(relevant)} finding(s) reduced score by {deduction:.0f}")
    if bonus > 0:
        parts.append(f"{signal_count} positive signal(s) added {bonus:.0f}")
    if not parts:
        parts.append("No issues detected")

    return ScoreBreakdownItem(
        dimension=dimension,
        score=round(score, 1),
        max_score=DIMENSION_MAX,
        remarks="; ".join(parts),
    )


def compute_demo_readiness(score: float, findings: list[RawFinding], positive_signals: list[str]) -> DemoReadiness:
    """Can the agent be safely demoed (typically in mock mode, no live side effects)?"""
    has_mock = any("mock" in s.lower() for s in positive_signals)
    critical = any(f.severity == "Critical" for f in findings)

    if critical:
        return "Not Ready"
    if score >= 70 and has_mock:
        return "Demo Ready"
    if score >= 55:
        return "Conditionally Ready"
    return "Not Ready"


def compute_production_readiness(score: float, findings: list[RawFinding], positive_signals: list[str]) -> ProductionReadiness:
    """Can the agent run safely against live systems?"""
    critical = any(f.severity == "Critical" for f in findings)
    llm_high = [f for f in findings if f.category == "AI/LLM Risk Controls" and f.severity in ("High", "Critical")]
    has_logging = not any(r.rule_id == "OBS_NO_LOGGING" for r in findings)

    if score >= 85 and not critical and not llm_high and has_logging:
        return "Production Ready"
    if score >= 65 and not critical:
        return "Requires Hardening"
    return "Not Ready"


def compute_score(findings: list[RawFinding], positive_signals: list[str] | None = None) -> ScoringResult:
    if positive_signals is None:
        positive_signals = []

    breakdown = [score_dimension(d, findings, positive_signals) for d in DIMENSIONS]
    overall = sum(item.score * DIMENSION_WEIGHTS[item.dimension] for item in breakdown)
    overall = round(overall, 1)

    return ScoringResult(
        breakdown=breakdown,
        overall_score=overall,
        demo_readiness=compute_demo_readiness(overall, findings, positive_signals),
        production_readiness=compute_production_readiness(overall, findings, positive_signals),
    )
