"""Classifies the primary SCM agent type from workflow-graph signals: the business
entities/variables referenced by decision functions, their branching structure, and
(when available) the shape of values returned at runtime. This is a multi-signal
weighted scorer over the whole decision surface, not a single keyword/substring match
on file content — a file that merely mentions a word in a comment scores nothing
because only identifiers reachable from a *branching, structured-return* decision
function are counted.
"""
from collections import Counter

from .workflow_graph import DecisionFunction
from ..core.models import AgentClassification

# Each agent type's signature: business-entity / variable-name terms expected to
# appear inside its decision functions. Plugins may extend this registry.
TYPE_SIGNATURES: dict[str, set[str]] = {
    "smart_reorder": {
        "reorder", "reorder_point", "safety_stock", "lead_time", "on_hand", "on_order",
        "inventory_position", "replenish", "replenishment", "eoq", "moq", "stockout",
    },
    "demand_forecasting": {
        "forecast", "demand", "seasonality", "trend", "moving_average", "mape", "bias",
        "predict", "historical_demand", "forecast_error", "promotion",
    },
    "supplier_selection": {
        "supplier", "moq", "reliability", "lead_time", "capacity", "supplier_score",
        "vendor", "rfq", "award",
    },
    "procurement_agent": {
        "purchase_order", "po", "budget", "approval", "procurement", "requisition",
        "emergency_order", "urgent",
    },
    "warehouse_agent": {
        "warehouse", "picking", "putaway", "storage", "transfer", "bin", "slot",
    },
    "inventory_optimization": {
        "inventory_turnover", "working_capital", "excess_inventory", "optimal_stock",
        "carrying_cost",
    },
    "transportation_agent": {
        "shipment", "carrier", "route", "freight", "transit_time", "load",
    },
    "production_planning": {
        "production_plan", "capacity_plan", "mrp", "bom", "work_order",
    },
    "manufacturing_agent": {
        "manufacturing", "production_line", "yield", "machine", "shift",
    },
}


def classify(decision_functions: list[DecisionFunction]) -> AgentClassification:
    if not decision_functions:
        return AgentClassification(primary_type="unknown", confidence=0.0, secondary_capabilities=[], signals={})

    aggregate_names: Counter = Counter()
    for fn in decision_functions:
        weight = 1 + fn.branch_count * 0.3 + (0.5 if fn.returns_structured else 0)
        for name in fn.referenced_names:
            aggregate_names[name] += weight

    scores: dict[str, float] = {}
    for agent_type, sig_terms in TYPE_SIGNATURES.items():
        matched = sum(aggregate_names[t] for t in sig_terms if t in aggregate_names)
        scores[agent_type] = matched

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    if not ranked or ranked[0][1] == 0:
        return AgentClassification(primary_type="unrecognized", confidence=0.0, secondary_capabilities=[],
                                    signals={"top_terms": aggregate_names.most_common(10)})

    total = sum(s for _, s in ranked) or 1.0
    primary_type, primary_score = ranked[0]
    confidence = min(0.99, primary_score / total + 0.15)
    secondary = [t for t, s in ranked[1:] if s > 0 and s >= primary_score * 0.4][:3]

    return AgentClassification(
        primary_type=primary_type,
        confidence=round(confidence, 2),
        secondary_capabilities=secondary,
        signals={"scores": scores, "top_terms": aggregate_names.most_common(15),
                 "aggregate_names": dict(aggregate_names)},
    )
