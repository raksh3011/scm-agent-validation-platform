"""Deterministic dynamic test-case generator. Same repo content + same agent type
always produces the same scenario suite (same IDs, same inputs) — generation is seeded
purely from a hash of the repo content, never from wall-clock or randomness.
"""
from ..connectors.mock_erp import SKUS, SUPPLIERS
from ..connectors.mock_wms import WAREHOUSES
from ..core.config import MAX_SCENARIOS_PER_RUN
from ..core.models import Scenario
from ..detection.agent_classifier import TYPE_SIGNATURES
from ..evalgen import pairwise as evalgen_pairwise
from ..rules.loader import axes_for_agent_type
from ..rules.schema import ScenarioAxis

# Repository-aware generation: these "other axis" categories represent a distinct SCM
# domain (supplier selection, procurement, warehouse ops) that not every agent
# implements. Only generate them when the repo's own decision-function vocabulary
# actually references that domain. Universal robustness axes (runtime faults,
# concurrency, stress, security, replay) apply regardless of business domain and are
# never filtered this way.
_AXIS_CAPABILITY_KEYWORDS = {
    "supplier": TYPE_SIGNATURES["supplier_selection"] | {"supplier", "supplier_id"},
    "procurement": TYPE_SIGNATURES["procurement_agent"],
    "warehouse": TYPE_SIGNATURES["warehouse_agent"],
}

# ASD-gated axis categories: business-domain axes a spec can explicitly declare in or out
# of scope. Universal robustness axes (runtime/concurrency/stress/security/replay) and the
# baseline inventory/demand axes are never gated by the ASD — every agent needs to be
# robust regardless of which optional SCM sub-domains it implements.
_ASD_AXIS_KEYWORDS = {
    "supplier": ("supplier", "vendor", "supplier ranking", "supplier selection"),
    "procurement": ("purchase order", "procurement", "po creation"),
    "warehouse": ("warehouse", "capacity", "receiving"),
}


def _graph_capability_names(capability_graph: dict | None) -> set[str]:
    if not capability_graph:
        return set()
    return {c.get("name") for c in capability_graph.get("supported_capabilities", []) if isinstance(c, dict)}


def _asd_text_blob(asd: dict, *fields: str) -> str:
    parts = []
    for f in fields:
        v = asd.get(f) or []
        parts.extend(v if isinstance(v, list) else [str(v)])
    return " ".join(parts).lower()


def _asd_scope_decision(category: str, asd: dict | None) -> bool | None:
    """ASD as single source of truth for optional business-domain axes:
    True  -> ASD explicitly declares this in scope/mandatory, generate it regardless of
             how strong the repo's own signal is (a declared-but-unimplemented capability
             is exactly the gap the validator should surface).
    False -> ASD explicitly lists it out of scope, never generate it even if the repo
             happens to contain matching code (it isn't a requirement, so failing it isn't
             a real defect).
    None  -> ASD doesn't mention it either way; fall back to repo-capability detection.
    """
    if not asd or category not in _ASD_AXIS_KEYWORDS:
        return None
    keywords = _ASD_AXIS_KEYWORDS[category]
    out_of_scope_text = _asd_text_blob(asd, "out_of_scope")
    if any(k in out_of_scope_text for k in keywords):
        return False
    in_scope_text = _asd_text_blob(asd, "scope", "inputs", "outputs", "responsibilities", "workflows", "decision_policies")
    if any(k in in_scope_text for k in keywords):
        return True
    return None


def _capability_supported(category: str, aggregate_names: dict[str, float] | None,
                          capability_graph: dict | None = None, asd: dict | None = None) -> bool:
    asd_decision = _asd_scope_decision(category, asd)
    if asd_decision is not None:
        return asd_decision

    graph_caps = _graph_capability_names(capability_graph)
    if category == "supplier" and graph_caps:
        return "supplier_ranking" in graph_caps or "moq" in graph_caps
    if category == "procurement" and graph_caps:
        return "purchase_order" in graph_caps
    if category == "warehouse" and graph_caps:
        return "warehouse_constraints" in graph_caps
    if aggregate_names is None or category not in _AXIS_CAPABILITY_KEYWORDS:
        return True
    keywords = _AXIS_CAPABILITY_KEYWORDS[category]
    return any(aggregate_names.get(k, 0) > 0 for k in keywords)


def _baseline_params(axes: list[ScenarioAxis]) -> dict[str, dict]:
    return {axis.category: axis.levels[0].params for axis in axes}


def _merge_inputs(sku_idx: int, overrides: dict[str, dict]) -> dict:
    sku = SKUS[sku_idx % len(SKUS)]
    supplier = SUPPLIERS[sku_idx % len(SUPPLIERS)]
    warehouse = WAREHOUSES[sku_idx % len(WAREHOUSES)]

    inventory = {"on_hand": 200, "allocated": 0, "on_order": 0, "reserved": 0, "safety_stock": 40,
                 "unit_cost": sku["unit_cost"], "lead_time_days": sku["lead_time_days"]}
    demand = {"demand_multiplier": 1.0, "volatility": "low",
              "history": [40, 42, 38, 45, 41, 39, 44, 43, 40, 46, 41, 39]}
    supplier_state = {"supplier_id": supplier["supplier_id"], "reliability_score": supplier["reliability_score"],
                       "moq": supplier["moq"], "capacity_per_week": supplier["capacity_per_week"]}
    warehouse_state = {"warehouse_id": warehouse["warehouse_id"], "available_units": warehouse["available_units"]}
    fault = None
    meta: dict = {}
    base_history_pattern = demand["history"]

    for category, params in overrides.items():
        if category == "inventory":
            inventory.update(params)
        elif category == "demand":
            demand.update(params)
        elif category == "data_quality":
            demand.update(params)
        elif category == "supplier":
            supplier_state.update(params)
        elif category == "procurement":
            supplier_state.update(params)
        elif category == "warehouse":
            warehouse_state.update(params)
        elif category == "runtime":
            fault = params.get("inject_fault")
        elif category in ("concurrency", "stress", "security", "replay"):
            meta[category] = params
            # Generic pass-through: a param matching an existing field name on a
            # known sub-object gets real effect (e.g. security's on_hand=-50,
            # supplier_id=None) rather than being purely informational.
            for k, v in params.items():
                if k in inventory:
                    inventory[k] = v
                elif k in supplier_state:
                    supplier_state[k] = v
                elif k in demand:
                    demand[k] = v
            if category == "stress" and "history_length" in params:
                n = min(params["history_length"], 240)
                demand["history"] = [base_history_pattern[i % len(base_history_pattern)] for i in range(n)]

    return {"sku": sku["sku"], "inventory": inventory, "demand": demand,
            "supplier": supplier_state, "warehouse": warehouse_state, "fault": fault, "meta": meta}


def _spec_requirement_ids(asd: dict | None, category: str) -> list[str]:
    """Requirements from the parsed ASD whose keywords/category text overlap this
    scenario axis category — used for scenario traceability (which requirement
    motivated this test case)."""
    if not asd:
        return []
    cat_words = category.replace("_", " ").split()
    out = []
    for req in asd.get("requirements", []):
        haystack = " ".join(req.get("keywords", [])) + " " + req.get("category", "") + " " + req.get("text", "")
        haystack = haystack.lower()
        if any(w and w in haystack for w in cat_words):
            out.append(req.get("id"))
    return out


_EVALGEN_VALUE_MAP = {
    "inventory_level": {"category": "inventory", "field": "on_hand",
                         "values": {"zero": 0, "below_safety": 20, "at_reorder_point": 40, "healthy": 150, "excess": 400}},
    "lead_time": {"category": "inventory", "field": "lead_time_days",
                  "values": {"short": 3, "normal": 7, "delayed": 21}},
    "safety_stock": {"category": "inventory", "field": "safety_stock",
                      "values": {"none": 0, "normal": 40, "high": 120}},
    "demand_signal": {"category": "demand", "field": "demand_multiplier",
                       "values": {"normal": 1.0, "spike": 2.5, "collapse": 0.2}},
    "forecast_confidence": {"category": "demand", "field": "volatility",
                             "values": {"low": "high", "medium": "medium", "high": "low"}},
    "moq": {"category": "supplier", "field": "moq", "values": {"none": 1, "standard": 50, "high": 500}},
    "supplier_reliability": {"category": "supplier", "field": "reliability_score",
                              "values": {"high": 0.95, "medium": 0.7, "low": 0.3}},
    "supplier_availability": {"category": "supplier", "field": "capacity_per_week",
                               "values": {"available": 500, "delayed": 50, "blackout": 0}},
    "warehouse_capacity": {"category": "warehouse", "field": "available_units",
                            "values": {"available": 5000, "tight": 200, "full": 0}},
}


def _evalgen_case_overrides(case: dict) -> dict[str, dict]:
    overrides: dict[str, dict] = {}
    for var, value in case.items():
        mapping = _EVALGEN_VALUE_MAP.get(var)
        if not mapping:
            continue
        overrides.setdefault(mapping["category"], {})[mapping["field"]] = mapping["values"].get(value, value)
    return overrides


def generate(agent_type: str, repo_hash: str, aggregate_names: dict[str, float] | None = None,
             capability_graph: dict | None = None, asd: dict | None = None) -> tuple[list[Scenario], object]:
    """Returns (scenarios, evalgen_stats). evalgen_stats is None if the pairwise
    generator found no usable business variables."""
    axes = axes_for_agent_type(agent_type)
    axes = [a for a in axes if _capability_supported(a.category, aggregate_names, capability_graph, asd)]
    if not axes:
        return [], None

    baseline = _baseline_params(axes)
    scenarios: list[Scenario] = []
    counter = 0

    core_axes = [a for a in axes if a.category in ("inventory", "demand")]
    other_axes = [a for a in axes if a.category not in ("inventory", "demand")]
    all_axes = core_axes + other_axes

    def _add(name: str, category: str, description: str, overrides: dict, severity: str,
              generated_by: str = "capability_driven", requirement_ids: list[str] | None = None):
        nonlocal counter
        counter += 1
        sid = f"SC-{counter:04d}"
        inputs = _merge_inputs(counter, overrides)
        req_ids = requirement_ids if requirement_ids is not None else _spec_requirement_ids(asd, category)
        scenarios.append(Scenario(
            id=sid, name=name, category=category,
            business_objective=f"Validate {agent_type.replace('_', ' ')} behaviour under: {description}",
            inputs=inputs, initial_state={k: v for k, v in inputs.items() if k != "sku"},
            expected_behaviour=description, severity_if_failed=severity,
            traceability={"generated_by": [generated_by] + (["specification_driven"] if req_ids else []),
                          "requirement_ids": req_ids},
        ))

    # 1. Single-axis variation across every dimension (inventory/demand/supplier/
    #    procurement/warehouse/runtime/...): each level tested independently against
    #    baseline elsewhere. Cheap (sum of level counts, not their cartesian product)
    #    and isolates exactly which single axis a failure traces back to.
    for axis in all_axes:
        for level in axis.levels:
            overrides = dict(baseline)
            overrides[axis.category] = level.params
            _add(level.name, axis.category, level.description, overrides, level.severity_if_failed)
            if counter >= MAX_SCENARIOS_PER_RUN:
                break

    # 2. Pairwise testing generator owns ALL cross-axis interaction coverage (what a
    #    brute-force full cartesian product or composite-sampling step used to do at
    #    far higher cost): a deterministic greedy pairwise combinatorial algorithm
    #    covers every pairwise variable interaction — including inventory x demand,
    #    the most expensive cross to enumerate fully — in a fraction of the scenario
    #    count, so the suite stays fast without losing interaction coverage.
    evalgen_stats = None
    variables = evalgen_pairwise.variables_from(asd, capability_graph)
    pairwise_budget = max(0, MAX_SCENARIOS_PER_RUN - counter)
    if variables and pairwise_budget > 0:
        cases, evalgen_stats = evalgen_pairwise.build_evalgen_scenarios(variables, limit=pairwise_budget)
        for case in cases:
            overrides = dict(baseline)
            for cat, fields in _evalgen_case_overrides(case).items():
                overrides[cat] = {**overrides.get(cat, {}), **fields}
            name = "pairwise_" + "_".join(f"{k}={v}" for k, v in case.items())
            description = "; ".join(f"{k.replace('_', ' ')}={v}" for k, v in case.items())
            req_ids = []
            for var in case:
                req_ids += _spec_requirement_ids(asd, var)
            _add(name, "pairwise_testing", description, overrides, "medium",
                 generated_by="pairwise_testing", requirement_ids=sorted(set(req_ids)))

    return scenarios, evalgen_stats


_SEV_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def _sev_rank(sev: str) -> int:
    return _SEV_ORDER.get(sev, 1)
