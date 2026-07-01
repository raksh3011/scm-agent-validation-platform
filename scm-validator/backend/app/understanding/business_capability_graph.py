"""Repository understanding engine.

This module converts workflow/static signals into a semantic capability graph used by
scenario generation and business validation. It deliberately infers the repository's
own policy surface first; canonical SCM equations are fallback evidence, not the only
truth.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Capability:
    name: str
    confidence: float
    evidence: list[str] = field(default_factory=list)


@dataclass
class BusinessCapabilityGraph:
    business_objective: str
    primary_policy: str
    policy_confidence: float
    supported_capabilities: list[Capability]
    decision_variables: list[str]
    business_entities: list[str]
    thresholds: dict[str, Any]
    optimization_objectives: list[str]
    assumptions: list[str]
    unsupported_capabilities: list[str]
    evidence_summary: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


CAPABILITY_TERMS = {
    "inventory_position": {"inventory_position", "on_hand", "on_order", "allocated", "reserved"},
    "reorder_timing": {"reorder", "reorder_point", "rop", "replenish", "stockout"},
    "reorder_quantity": {"quantity", "qty", "order_quantity", "reorder_quantity", "eoq", "target_stock"},
    "safety_stock": {"safety_stock", "buffer_stock"},
    "lead_time": {"lead_time", "lead_time_days"},
    "moq": {"moq", "minimum_order_quantity"},
    "supplier_ranking": {"supplier_score", "reliability", "capacity", "vendor", "supplier_id"},
    "purchase_order": {"purchase_order", "po", "create_purchase_order", "commit", "insert", "save"},
    "forecasting": {"forecast", "moving_average", "trend", "seasonality", "predict"},
    "warehouse_constraints": {"warehouse", "capacity", "bin", "slot", "transfer"},
}

POLICY_TERMS = {
    "reorder_point": {"reorder_point", "rop", "safety_stock", "lead_time", "inventory_position"},
    "eoq": {"eoq", "economic_order_quantity", "holding_cost", "order_cost"},
    "min_max": {"min_stock", "max_stock", "min_level", "max_level", "target_stock"},
    "days_of_supply": {"days_of_supply", "coverage_days", "dos"},
    "forecast_driven": {"forecast", "predicted_demand", "trend", "seasonality"},
    "periodic_review": {"review_period", "cycle", "periodic"},
    "supplier_driven": {"supplier", "moq", "capacity", "reliability"},
    "heuristic": {"threshold", "rule", "score", "priority"},
}

ENTITY_TERMS = {
    "inventory": {"inventory", "sku", "stock", "on_hand"},
    "demand": {"demand", "sales", "forecast", "history"},
    "supplier": {"supplier", "vendor", "moq", "reliability"},
    "purchase_order": {"purchase_order", "po", "order"},
    "warehouse": {"warehouse", "bin", "storage"},
}

OBJECTIVE_TERMS = {
    "stockout_risk_reduction": {"stockout", "reorder", "replenish", "safety_stock"},
    "working_capital_control": {"eoq", "holding_cost", "carrying_cost", "excess"},
    "supplier_reliability": {"reliability", "capacity", "lead_time", "supplier_score"},
    "forecast_accuracy": {"forecast", "mape", "bias", "trend"},
    "operational_execution": {"purchase_order", "commit", "save", "erp"},
}


def _score_terms(names: Counter, terms: set[str]) -> tuple[float, list[str]]:
    hits = []
    raw = 0.0
    for term in sorted(terms):
        for name, weight in names.items():
            normalized = name.strip("_")
            if normalized == term or term in normalized:
                hits.append(term)
                raw += weight
                break
    hits = sorted(set(hits))
    return raw, hits


def _read_numeric_thresholds(python_files: list[Path]) -> dict[str, Any]:
    thresholds: dict[str, Any] = {}
    for path in python_files:
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        for key in ("reorder_point", "safety_stock", "min_stock", "max_stock", "threshold", "lead_time"):
            if key in text.lower():
                thresholds.setdefault(key, "referenced")
    return thresholds


def build(classification, decision_functions: list, python_files: list[Path], static_facts: dict) -> BusinessCapabilityGraph:
    names: Counter = Counter()
    for fn in decision_functions:
        weight = 1 + fn.branch_count * 0.3 + (0.5 if fn.returns_structured else 0)
        for name in fn.referenced_names:
            names[name] += weight

    capabilities: list[Capability] = []
    unsupported: list[str] = []
    for cap, terms in CAPABILITY_TERMS.items():
        score, hits = _score_terms(names, terms)
        if score > 0:
            capabilities.append(Capability(cap, round(min(0.98, 0.45 + score / 10), 2), hits[:8]))
        else:
            unsupported.append(cap)

    policy_scores = []
    for policy, terms in POLICY_TERMS.items():
        score, hits = _score_terms(names, terms)
        policy_scores.append((score, policy, hits))
    policy_scores.sort(reverse=True)
    if classification.primary_type == "smart_reorder":
        score_by_policy = {p: (s, h) for s, p, h in policy_scores}
        rp_score, rp_hits = score_by_policy.get("reorder_point", (0, []))
        eoq_score, eoq_hits = score_by_policy.get("eoq", (0, []))
        if rp_score > 0 and eoq_score > 0:
            best_score, policy, hits = rp_score + eoq_score, "reorder_point_eoq_hybrid", sorted(set(rp_hits + eoq_hits))
        elif rp_score > 0:
            best_score, policy, hits = rp_score, "reorder_point", rp_hits
        elif eoq_score > 0:
            best_score, policy, hits = eoq_score, "eoq", eoq_hits
        else:
            best_score, policy, hits = policy_scores[0] if policy_scores else (0, "unknown", [])
    else:
        best_score, policy, hits = policy_scores[0] if policy_scores else (0, "unknown", [])
    if best_score <= 0:
        policy, confidence = "canonical_reference_fallback", 0.25
    else:
        confidence = round(min(0.95, 0.40 + best_score / 12), 2)

    entities = [name for name, terms in ENTITY_TERMS.items() if _score_terms(names, terms)[0] > 0]
    objectives = [name for name, terms in OBJECTIVE_TERMS.items() if _score_terms(names, terms)[0] > 0]
    decision_vars = [name for name, _ in names.most_common(30)]

    if classification.primary_type == "smart_reorder":
        objective = "Determine when and how replenishment should occur for inventory items."
    elif classification.primary_type == "demand_forecasting":
        objective = "Forecast future demand from historical demand signals."
    else:
        objective = f"Execute {classification.primary_type.replace('_', ' ')} decisions."

    evidence = [
        f"Primary agent classification: {classification.primary_type} ({classification.confidence:.0%}).",
        f"Inferred policy: {policy} ({confidence:.0%}) from terms: {', '.join(hits[:8]) or 'none'}.",
        f"Detected capabilities: {', '.join(c.name for c in capabilities) or 'none'}.",
    ]
    if static_facts.get("has_persistence_call"):
        evidence.append("Static evidence indicates persistence or operational write capability.")
    if static_facts.get("has_error_handling"):
        evidence.append("Static evidence indicates explicit exception handling.")

    return BusinessCapabilityGraph(
        business_objective=objective,
        primary_policy=policy,
        policy_confidence=confidence,
        supported_capabilities=capabilities,
        decision_variables=decision_vars,
        business_entities=entities,
        thresholds=_read_numeric_thresholds(python_files),
        optimization_objectives=objectives,
        assumptions=["Canonical SCM equations are used only as fallback/corroborating evidence."],
        unsupported_capabilities=unsupported,
        evidence_summary=evidence,
    )
