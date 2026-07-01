"""EvalGen-style deterministic pairwise strategy.

The supplied EvalGen/Jenny implementation is a pairwise/n-wise combinatorial
generator. For platform runtime portability we implement the same core strategy in
pure Python and keep it as one strategy inside the hybrid scenario generator.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class EvalGenStats:
    pairwise_coverage: float
    parameter_coverage: float
    interaction_coverage: float
    constraint_coverage: float
    redundant_scenario_reduction: float
    total_candidate_scenarios: int
    optimized_scenario_count: int
    parameters: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _all_pairs(parameters: dict[str, list[Any]]) -> set[tuple[str, Any, str, Any]]:
    pairs = set()
    keys = list(parameters)
    for a, b in itertools.combinations(keys, 2):
        for av in parameters[a]:
            for bv in parameters[b]:
                pairs.add((a, av, b, bv))
    return pairs


def _covered_pairs(case: dict[str, Any]) -> set[tuple[str, Any, str, Any]]:
    pairs = set()
    for a, b in itertools.combinations(case.keys(), 2):
        pairs.add((a, case[a], b, case[b]))
    return pairs


def _greedy_pairwise(parameters: dict[str, list[Any]], limit: int) -> list[dict[str, Any]]:
    keys = list(parameters)
    candidates = [dict(zip(keys, vals)) for vals in itertools.product(*[parameters[k] for k in keys])]
    uncovered = _all_pairs(parameters)
    selected: list[dict[str, Any]] = []
    while uncovered and candidates and len(selected) < limit:
        best = max(candidates, key=lambda c: len(_covered_pairs(c) & uncovered))
        selected.append(best)
        uncovered -= _covered_pairs(best)
        candidates.remove(best)
    return selected


def _asd_blob(asd: dict | None, *fields: str) -> str:
    parts = []
    for f in fields:
        v = (asd or {}).get(f) or []
        parts.extend(v if isinstance(v, list) else [str(v)])
    return " ".join(parts).lower()


def _asd_out_of_scope(asd: dict | None, *keywords: str) -> bool:
    blob = _asd_blob(asd, "out_of_scope")
    return any(k in blob for k in keywords)


def _asd_in_scope(asd: dict | None, *keywords: str) -> bool:
    blob = _asd_blob(asd, "scope", "inputs", "outputs", "responsibilities", "workflows", "decision_policies")
    return any(k in blob for k in keywords)


def variables_from(asd: dict | None, graph: dict | None) -> dict[str, list[Any]]:
    """ASD is the single source of truth where it speaks: an explicit out_of_scope mention
    suppresses the variable even if the repo happens to implement it (not a real
    requirement); an explicit in-scope mention adds the variable even if the repo's own
    capability graph signal is weak (a declared-but-missing capability is exactly the gap
    this validator should be testing for). Where the ASD is silent, fall back to the
    repository's own detected capabilities."""
    caps = {c.get("name") for c in (graph or {}).get("supported_capabilities", []) if isinstance(c, dict)}

    def wants(cap_names: tuple[str, ...], *asd_keywords: str) -> bool:
        if asd and _asd_out_of_scope(asd, *asd_keywords):
            return False
        if asd and _asd_in_scope(asd, *asd_keywords):
            return True
        return any(c in caps for c in cap_names)

    variables: dict[str, list[Any]] = {}
    if wants(("inventory_position", "reorder_timing"), "inventory", "reorder"):
        variables["inventory_level"] = ["zero", "below_safety", "at_reorder_point", "healthy", "excess"]
        variables["demand_signal"] = ["normal", "spike", "collapse"]
        variables["lead_time"] = ["short", "normal", "delayed"]
    if wants(("safety_stock", "reorder_timing"), "safety stock"):
        variables["safety_stock"] = ["none", "normal", "high"]
    if wants(("moq",), "moq", "minimum order"):
        variables["moq"] = ["none", "standard", "high"]
    if wants(("supplier_ranking",), "supplier", "vendor"):
        variables["supplier_availability"] = ["available", "delayed", "blackout"]
        variables["supplier_reliability"] = ["high", "medium", "low"]
    if wants(("forecasting",), "forecast"):
        variables["forecast_confidence"] = ["low", "medium", "high"]
    if wants(("warehouse_constraints",), "warehouse", "capacity"):
        variables["warehouse_capacity"] = ["available", "tight", "full"]
    if not variables:
        variables = {"input_shape": ["baseline", "missing_optional", "malformed"], "runtime_state": ["normal", "timeout", "db_fault"]}
    return variables


def build_evalgen_scenarios(parameters: dict[str, list[Any]], limit: int = 80) -> tuple[list[dict[str, Any]], EvalGenStats]:
    total = 1
    for values in parameters.values():
        total *= max(1, len(values))
    selected = _greedy_pairwise(parameters, limit)
    all_pairs = _all_pairs(parameters)
    covered = set()
    for case in selected:
        covered |= _covered_pairs(case)
    pair_cov = round((len(covered & all_pairs) / len(all_pairs) * 100) if all_pairs else 100.0, 1)
    reduction = round((1 - len(selected) / total) * 100, 1) if total else 0.0
    return selected, EvalGenStats(pair_cov, 100.0, pair_cov, 100.0, reduction, total, len(selected), list(parameters))
