"""Business KPI Engine — aggregates supply-chain KPIs purely from data the pipeline
already produced (scenario inputs + executed decisions). No new execution is run;
this is a deterministic aggregation pass, like the trust engine."""
from dataclasses import dataclass

from ..core.models import ScenarioExecutionResult
from ..validation import decision_validator as dv
from ..validation.business_rules import forecast_baseline, reorder_math


@dataclass
class KpiResult:
    name: str
    value: float
    unit: str
    description: str


def _smart_reorder_kpis(results: list[ScenarioExecutionResult]) -> list[KpiResult]:
    judged = [r for r in results if r.status != "error"]
    if not judged:
        return []

    inventory_positions, reorder_points, turns_samples = [], [], []
    order_qty_ratios = []
    stockout_misses = 0
    stockout_candidates = 0
    emergency_hits = 0
    emergency_candidates = 0
    lead_times = []

    for r in judged:
        inv = r.scenario.inputs["inventory"]
        dem = r.scenario.inputs["demand"]
        sup = r.scenario.inputs["supplier"]
        ip = reorder_math.inventory_position(inv)
        rp = reorder_math.reorder_point(inv, dem)
        inventory_positions.append(ip)
        reorder_points.append(rp)

        annual_demand = reorder_math.avg_daily_demand(dem) * 365
        if ip > 0:
            turns_samples.append(annual_demand / ip if ip else 0)

        expected_reorder = reorder_math.should_reorder(inv, dem)
        actual_bool = dv._extract_bool_decision(r.actual_behaviour.get("return_value"))
        actual_qty = dv._extract_quantity(r.actual_behaviour.get("return_value"))

        if ip <= inv.get("safety_stock", 0):
            stockout_candidates += 1
            if actual_bool is not True:
                stockout_misses += 1

        if expected_reorder and actual_qty is not None:
            ref_qty = reorder_math.reference_order_quantity(inv, dem, sup)
            if ref_qty > 0:
                order_qty_ratios.append(actual_qty / ref_qty)
            lead_times.append(inv.get("lead_time_days", 0))

        if r.scenario.category == "procurement" and "emergency" in r.scenario.name:
            emergency_candidates += 1
            if actual_bool is True:
                emergency_hits += 1

    kpis = []
    if turns_samples:
        kpis.append(KpiResult("inventory_turns", round(sum(turns_samples) / len(turns_samples), 2),
                               "turns/year", "Average annual demand divided by inventory position."))
    if stockout_candidates:
        service_level = 1 - (stockout_misses / stockout_candidates)
        kpis.append(KpiResult("service_level_proxy", round(service_level * 100, 1), "%",
                               "Share of below-safety-stock scenarios where the agent correctly reordered."))
        kpis.append(KpiResult("stockout_risk_rate", round((stockout_misses / stockout_candidates) * 100, 1), "%",
                               "Share of below-safety-stock scenarios the agent failed to act on."))
    if order_qty_ratios:
        avg_ratio = sum(order_qty_ratios) / len(order_qty_ratios)
        kpis.append(KpiResult("working_capital_efficiency", round(min(100, 100 / max(avg_ratio, 0.01)), 1), "%",
                               "How close recommended order quantities track the EOQ reference (100% = exact)."))
    if lead_times:
        kpis.append(KpiResult("avg_order_cycle_time", round(sum(lead_times) / len(lead_times), 1), "days",
                               "Average supplier lead time across scenarios that triggered a reorder."))
    if emergency_candidates:
        kpis.append(KpiResult("emergency_order_handling", round((emergency_hits / emergency_candidates) * 100, 1), "%",
                               "Share of emergency-replenishment scenarios correctly identified as needing reorder."))
    return kpis


def _demand_forecasting_kpis(results: list[ScenarioExecutionResult]) -> list[KpiResult]:
    judged = [r for r in results if r.status != "error"]
    if not judged:
        return []

    mapes, biases, direction_hits = [], [], 0
    for r in judged:
        dem = r.scenario.inputs["demand"]
        baseline = forecast_baseline.naive_baseline_forecast(dem)
        scaled = baseline * dem.get("demand_multiplier", 1.0)
        actual_forecast = dv._extract_forecast(r.actual_behaviour.get("return_value"))
        if actual_forecast is None:
            continue
        mapes.append(forecast_baseline.mape(scaled, actual_forecast))
        biases.append(forecast_baseline.bias(scaled, actual_forecast))
        expected_dir = forecast_baseline.expected_direction(dem)
        if expected_dir == "increase" and actual_forecast > baseline:
            direction_hits += 1
        elif expected_dir == "decrease" and actual_forecast < baseline:
            direction_hits += 1
        elif expected_dir == "stable":
            direction_hits += 1

    kpis = []
    if mapes:
        kpis.append(KpiResult("forecast_accuracy", round((1 - sum(mapes) / len(mapes)) * 100, 1), "%",
                               "1 - mean absolute percentage error vs the scaled naive baseline."))
        kpis.append(KpiResult("forecast_bias", round((sum(biases) / len(biases)) * 100, 1), "%",
                               "Average signed bias (positive = over-forecasting)."))
        kpis.append(KpiResult("forecast_direction_accuracy", round((direction_hits / len(mapes)) * 100, 1), "%",
                               "Share of scenarios where the forecast moved in the expected direction."))
    return kpis


_KPI_FUNCS = {
    "smart_reorder": _smart_reorder_kpis,
    "demand_forecasting": _demand_forecasting_kpis,
}


def compute(agent_type: str, results: list[ScenarioExecutionResult]) -> list[KpiResult]:
    fn = _KPI_FUNCS.get(agent_type)
    return fn(results) if fn else []
