"""Trust Harness Phase 5: combines the static-rule "hygiene" score (secondary
signal) with the execution-based "behavior" score (dominant signal) into the
gated overall scoring model.

    if Applicability Gate fails:  overall = None,  not scored at all (Phase 0, in pipeline.py)
    elif adapter fails:           overall = 0,     "Not Ready" (no agent could be executed)
    else:
        hygiene_score  = existing static engine score (0-100)
        behavior_score = weighted(invariant_pass_rate, golden_scenario_pass_rate)
                         -- any single Required-tier failure caps behavior_score at 40;
                            Recommended-tier failures cost smaller, uncapped deductions
        overall = 0.25 * hygiene_score + 0.75 * behavior_score

        "Production Ready"   only if behavior_score >= 95 and hygiene_score >= 70
        "Requires Hardening" if behavior_score >= 70
        "Not Ready"           otherwise
"""
from __future__ import annotations

from dataclasses import dataclass

from ..report_schema import InvariantResult, ScenarioResult, DemoReadiness, ProductionReadiness

HYGIENE_WEIGHT = 0.25
BEHAVIOR_WEIGHT = 0.75
REQUIRED_FAILURE_CAP = 40.0
RECOMMENDED_FAILURE_PENALTY = 8.0


@dataclass
class BehaviorScoreResult:
    behavior_score: float
    required_total: int
    required_passed: int
    recommended_total: int
    recommended_passed: int
    any_required_failed: bool


def compute_behavior_score(
    invariant_results: list[InvariantResult],
    scenario_results: list[ScenarioResult],
) -> BehaviorScoreResult:
    required = [r for r in invariant_results if r.tier == "required"] + \
               [r for r in scenario_results if r.tier == "required"]
    recommended = [r for r in invariant_results if r.tier == "recommended"] + \
                  [r for r in scenario_results if r.tier == "recommended"]

    required_total = len(required)
    required_passed = sum(1 for r in required if r.passed)
    recommended_total = len(recommended)
    recommended_passed = sum(1 for r in recommended if r.passed)

    required_pass_rate = (required_passed / required_total) if required_total else 1.0
    any_required_failed = required_passed < required_total

    score = required_pass_rate * 100.0
    if any_required_failed:
        score = min(score, REQUIRED_FAILURE_CAP)

    score -= RECOMMENDED_FAILURE_PENALTY * (recommended_total - recommended_passed)
    score = max(0.0, min(100.0, score))

    return BehaviorScoreResult(
        behavior_score=round(score, 1),
        required_total=required_total,
        required_passed=required_passed,
        recommended_total=recommended_total,
        recommended_passed=recommended_passed,
        any_required_failed=any_required_failed,
    )


def compute_production_readiness(behavior_score: float, hygiene_score: float) -> ProductionReadiness:
    if behavior_score >= 95 and hygiene_score >= 70:
        return "Production Ready"
    if behavior_score >= 70:
        return "Requires Hardening"
    return "Not Ready"


def compute_demo_readiness(behavior_score: float) -> DemoReadiness:
    """Demo readiness uses a lower bar than production -- a wrong-but-non-crashing
    agent might be fine to demo with caveats but should never ship."""
    if behavior_score >= 70:
        return "Demo Ready"
    if behavior_score >= 40:
        return "Conditionally Ready"
    return "Not Ready"


def compute_overall(hygiene_score: float, behavior_score: float) -> float:
    return round(HYGIENE_WEIGHT * hygiene_score + BEHAVIOR_WEIGHT * behavior_score, 1)
