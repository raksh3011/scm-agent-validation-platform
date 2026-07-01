"""Repository-aware business validation.

The validator does not assume one universal replenishment policy. It first uses the
repository capability graph to infer the intended policy/capabilities, then combines
multiple evidence sources: runtime output, discovered capabilities, SCM fallback math,
scenario constraints, and consistency/sanity invariants. Low-evidence disagreements
reduce confidence or become partial results instead of speculative critical failures.
"""
from __future__ import annotations

from ..core.models import ScenarioExecutionResult
from ..execution.scenario_executor import RawExecutionOutcome
from .business_rules import forecast_baseline, reorder_math

_DECISION_BOOL_KEYS = ("should_reorder", "reorder", "needs_reorder", "replenish")
_ACTION_KEYS = ("action", "decision", "status")
_QTY_KEYS = ("quantity", "order_quantity", "recommended_quantity", "recommended_qty", "reorder_quantity",
             "reorder_qty", "order_qty", "qty")
_FORECAST_KEYS = ("forecast", "predicted_demand", "forecast_quantity", "prediction", "forecasted_demand")


def _flatten(obj, depth=0) -> dict:
    flat = {}
    if not isinstance(obj, dict) or depth > 3:
        return flat
    for k, v in obj.items():
        flat[str(k).lower()] = v
        if isinstance(v, dict):
            flat.update(_flatten(v, depth + 1))
    return flat


def _extract_bool_decision(return_value) -> bool | None:
    flat = _flatten(return_value)
    for key in _DECISION_BOOL_KEYS:
        if key in flat and isinstance(flat[key], bool):
            return flat[key]
    for key in _ACTION_KEYS:
        if key in flat and isinstance(flat[key], str):
            val = flat[key].lower()
            if val in ("reorder", "order", "replenish", "buy", "yes", "true", "reorder_now"):
                return True
            if val in ("hold", "skip", "no_action", "wait", "no", "false", "do_not_reorder"):
                return False
    return None


def _extract_quantity(return_value) -> float | None:
    flat = _flatten(return_value)
    for key in _QTY_KEYS:
        if key in flat and isinstance(flat[key], (int, float)):
            return float(flat[key])
    return None


def _extract_forecast(return_value) -> float | None:
    flat = _flatten(return_value)
    for key in _FORECAST_KEYS:
        if key in flat and isinstance(flat[key], (int, float)):
            return float(flat[key])
    return None


def _supported(capability_graph: dict | None) -> set[str]:
    if not capability_graph:
        return set()
    return {c.get("name") for c in capability_graph.get("supported_capabilities", []) if isinstance(c, dict)}


def _policy(capability_graph: dict | None) -> tuple[str, float]:
    if not capability_graph:
        return "canonical_reference_fallback", 0.25
    return capability_graph.get("primary_policy", "canonical_reference_fallback"), capability_graph.get("policy_confidence", 0.25)


def _result(outcome: RawExecutionOutcome, status, explanation, confidence) -> ScenarioExecutionResult:
    return ScenarioExecutionResult(
        scenario=outcome.scenario, status=status,
        actual_behaviour={"return_value": outcome.return_value, "candidate": outcome.candidate,
                          "exception": outcome.exception},
        business_explanation=explanation, confidence=round(float(confidence), 2),
        runtime_ms=outcome.runtime_ms,
        execution_state="crashed" if outcome.exception else "executed",
        evidence=outcome.evidence, error=outcome.exception.get("message") if outcome.exception else None,
    )


def _validate_smart_reorder(outcome: RawExecutionOutcome, capability_graph: dict | None = None) -> ScenarioExecutionResult:
    scenario = outcome.scenario
    inventory = scenario.inputs["inventory"]
    demand = scenario.inputs["demand"]
    supplier = scenario.inputs["supplier"]
    caps = _supported(capability_graph)
    policy_name, policy_confidence = _policy(capability_graph)

    if outcome.exception:
        return _result(outcome, "error",
                       f"Execution raised {outcome.exception.get('type')}: {outcome.exception.get('message')}",
                       0.9)

    actual_bool = _extract_bool_decision(outcome.return_value)
    actual_qty = _extract_quantity(outcome.return_value)
    if actual_bool is None:
        return _result(outcome, "error",
                       "Could not locate a reorder decision in the agent output; no recognizable decision field was returned.",
                       0.4)

    ip = reorder_math.inventory_position(inventory)
    rp = reorder_math.reorder_point(inventory, demand)
    expected_reorder = reorder_math.should_reorder(inventory, demand)
    expected_qty = reorder_math.reference_order_quantity(inventory, demand, supplier) if expected_reorder else 0.0

    timing_matches_reference = actual_bool == expected_reorder
    severe_stockout_risk = ip <= min(0, inventory.get("safety_stock", 0))
    evidence_votes: list[str] = []
    positive_votes = 0
    risk_votes = 0

    if timing_matches_reference:
        positive_votes += 1
        evidence_votes.append("runtime decision aligns with fallback reorder-point reference")
    else:
        evidence_votes.append("runtime decision differs from fallback reorder-point reference")
        if severe_stockout_risk and actual_bool is False:
            risk_votes += 2
            evidence_votes.append("inventory is at/below safety stock or zero and the agent still held")
        else:
            risk_votes += 1

    qty_reasonable = True
    if actual_qty is not None:
        if actual_qty < 0:
            qty_reasonable = False
            risk_votes += 2
            evidence_votes.append("agent returned a negative order quantity")
        elif expected_reorder and expected_qty > 0:
            ratio = actual_qty / expected_qty
            if 0.3 <= ratio <= 3.0:
                positive_votes += 1
                evidence_votes.append("quantity is within a broad EOQ/MOQ reasonableness band")
            elif "reorder_quantity" in caps or "moq" in caps:
                qty_reasonable = False
                risk_votes += 1
                evidence_votes.append("quantity is outside the inferred quantity-policy tolerance band")
            else:
                evidence_votes.append("quantity differs from EOQ fallback, but quantity policy was not explicit")

        if "moq" in caps and actual_bool and actual_qty < supplier.get("moq", 0):
            qty_reasonable = False
            risk_votes += 1
            evidence_votes.append("agent quantity violates discovered MOQ capability")

    if policy_name != "canonical_reference_fallback":
        positive_votes += 1
        evidence_votes.append(f"repository policy inferred as {policy_name}; canonical formula used as corroboration")
    else:
        evidence_votes.append("no explicit replenishment policy was inferred; canonical SCM math used as fallback")

    if timing_matches_reference and qty_reasonable:
        status = "pass"
        confidence = min(0.96, 0.58 + 0.10 * positive_votes + 0.15 * policy_confidence)
    elif risk_votes >= 3:
        status = "fail"
        confidence = min(0.94, 0.55 + 0.10 * risk_votes + 0.10 * policy_confidence)
    else:
        status = "partial"
        confidence = max(0.35, min(0.72, 0.42 + 0.06 * positive_votes + 0.05 * risk_votes))

    explanation = (
        f"Repository-aware validation: inferred policy={policy_name} ({policy_confidence:.0%}). "
        f"Fallback reference: inventory position={ip:.1f}, reorder point={rp:.1f}, "
        f"reference reorder={expected_reorder}, reference qty~{expected_qty:.0f}. "
        f"Agent decided reorder={actual_bool}"
        + (f", qty={actual_qty:.0f}. " if actual_qty is not None else ". ")
        + "Evidence: " + "; ".join(evidence_votes[:6]) + "."
    )
    return _result(outcome, status, explanation, confidence)


def _validate_demand_forecasting(outcome: RawExecutionOutcome, capability_graph: dict | None = None) -> ScenarioExecutionResult:
    scenario = outcome.scenario
    demand = scenario.inputs["demand"]

    if outcome.exception:
        return _result(outcome, "error",
                       f"Execution raised {outcome.exception.get('type')}: {outcome.exception.get('message')}",
                       0.9)

    baseline = forecast_baseline.naive_baseline_forecast(demand)
    expected_dir = forecast_baseline.expected_direction(demand)
    actual_forecast = _extract_forecast(outcome.return_value)
    if actual_forecast is None:
        return _result(outcome, "error", "Could not locate a forecast value in the agent output.", 0.4)

    if expected_dir == "increase":
        direction_correct = actual_forecast > baseline * 1.05
    elif expected_dir == "decrease":
        direction_correct = actual_forecast < baseline * 0.95
    else:
        direction_correct = abs(actual_forecast - baseline) <= baseline * 0.3

    m = forecast_baseline.mape(baseline * demand.get("demand_multiplier", 1.0), actual_forecast)
    magnitude_reasonable = m <= 0.5
    if direction_correct and magnitude_reasonable:
        status, confidence = "pass", 0.82
    elif direction_correct:
        status, confidence = "partial", 0.62
    else:
        status, confidence = "partial", 0.48

    explanation = (
        f"Repository-aware forecast validation uses the naive baseline as corroborating evidence, not a universal oracle. "
        f"Baseline forecast={baseline:.1f}, expected direction={expected_dir}, "
        f"multiplier={demand.get('demand_multiplier', 1.0)}. Agent forecast={actual_forecast:.1f}; "
        f"MAPE vs scaled baseline={m:.2f}."
    )
    return _result(outcome, status, explanation, confidence)


VALIDATORS = {
    "smart_reorder": _validate_smart_reorder,
    "demand_forecasting": _validate_demand_forecasting,
}


def validate(agent_type: str, outcome: RawExecutionOutcome, capability_graph: dict | None = None) -> ScenarioExecutionResult:
    validator = VALIDATORS.get(agent_type)
    if validator is None:
        return ScenarioExecutionResult(
            scenario=outcome.scenario, status="error",
            actual_behaviour={"return_value": outcome.return_value},
            business_explanation=f"No business validator registered yet for agent type '{agent_type}'.",
            confidence=0.0, runtime_ms=outcome.runtime_ms, evidence=outcome.evidence,
        )
    return validator(outcome, capability_graph)
