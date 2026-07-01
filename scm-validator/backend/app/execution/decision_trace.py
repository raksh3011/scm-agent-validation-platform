"""Builds an explainable, ordered decision trace for a scenario by re-running the
same pure reference-math functions the business validator already used — not by
instrumenting the agent's own code, which the validator does not control or trust."""
from ..core.models import ScenarioExecutionResult
from ..validation import decision_validator as dv
from ..validation.business_rules import forecast_baseline, reorder_math


def _step(name: str, value) -> dict:
    return {"step": name, "value": value}


def _smart_reorder_trace(result: ScenarioExecutionResult, capability_graph: dict | None = None) -> list[dict]:
    inv = result.scenario.inputs["inventory"]
    dem = result.scenario.inputs["demand"]
    sup = result.scenario.inputs["supplier"]

    ip = reorder_math.inventory_position(inv)
    add = reorder_math.avg_daily_demand(dem)
    rp = reorder_math.reorder_point(inv, dem)
    expected_reorder = reorder_math.should_reorder(inv, dem)
    ref_qty = reorder_math.reference_order_quantity(inv, dem, sup) if expected_reorder else 0.0

    actual = result.actual_behaviour.get("return_value")
    policy = (capability_graph or {}).get("primary_policy", "unknown")
    caps = [c.get("name") for c in (capability_graph or {}).get("supported_capabilities", []) if isinstance(c, dict)]
    return [
        _step("repository_policy", policy),
        _step("supported_capabilities", caps),
        _step("inventory_position", round(ip, 1)),
        _step("avg_daily_demand", round(add, 2)),
        _step("safety_stock", inv.get("safety_stock", 0)),
        _step("reorder_point", round(rp, 1)),
        _step("expected_decision", "reorder" if expected_reorder else "hold"),
        _step("reference_order_quantity", round(ref_qty, 0)),
        _step("supplier_considered", sup.get("supplier_id")),
        _step("agent_decision", "reorder" if dv._extract_bool_decision(actual) else "hold"),
        _step("agent_quantity", dv._extract_quantity(actual)),
        _step("evidence_basis", "repository policy + runtime output + fallback SCM reference + scenario constraints"),
        _step("confidence", result.confidence),
        _step("validation_result", result.status),
    ]


def _demand_forecasting_trace(result: ScenarioExecutionResult, capability_graph: dict | None = None) -> list[dict]:
    dem = result.scenario.inputs["demand"]
    baseline = forecast_baseline.naive_baseline_forecast(dem)
    expected_dir = forecast_baseline.expected_direction(dem)
    scaled = baseline * dem.get("demand_multiplier", 1.0)
    actual = result.actual_behaviour.get("return_value")
    actual_forecast = dv._extract_forecast(actual)

    return [
        _step("repository_policy", (capability_graph or {}).get("primary_policy", "unknown")),
        _step("naive_baseline_forecast", round(baseline, 1)),
        _step("demand_multiplier", dem.get("demand_multiplier", 1.0)),
        _step("expected_direction", expected_dir),
        _step("scaled_reference_forecast", round(scaled, 1)),
        _step("agent_forecast", actual_forecast),
        _step("mape_vs_reference", round(forecast_baseline.mape(scaled, actual_forecast), 2)
              if actual_forecast is not None else None),
        _step("evidence_basis", "runtime forecast + scenario demand signal + fallback naive reference"),
        _step("confidence", result.confidence),
        _step("validation_result", result.status),
    ]


_TRACE_FUNCS = {
    "smart_reorder": _smart_reorder_trace,
    "demand_forecasting": _demand_forecasting_trace,
}


def build(agent_type: str, result: ScenarioExecutionResult, capability_graph: dict | None = None) -> list[dict]:
    if result.execution_state == "unreachable":
        exc = (result.actual_behaviour or {}).get("exception") or {}
        return [_step("execution_blocked", f"Never reached the decision stage — "
                       f"{exc.get('type', 'failure')}: {exc.get('message', result.business_explanation)}")]
    if result.execution_state == "crashed":
        exc = (result.actual_behaviour or {}).get("exception") or {}
        return [_step("execution_blocked", f"Crashed before reaching a decision — "
                       f"{exc.get('type', 'failure')}: {exc.get('message', result.business_explanation)}")]
    fn = _TRACE_FUNCS.get(agent_type)
    if not fn or result.status == "error":
        return []
    return fn(result, capability_graph)
