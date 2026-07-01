"""Adapter Synthesis: when a candidate entrypoint's parameters don't match our
generic scenario shape (sku/inventory/demand/supplier/warehouse), infer what shape
each parameter actually wants by statically analyzing how it's used in the function
body (iterated + subscripted => list of dicts; subscripted directly => dict; neither
=> scalar/string), then render real arguments from the scenario's business data into
that shape. This is what lets the validator drive arbitrary real-world signatures
like `decide(product, suppliers, context, live)` instead of only "the function takes
one context dict" style agents.
"""
import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ShapeSpec:
    kind: str  # "dict" | "list_of_dict" | "scalar"
    keys: set[str] = field(default_factory=set)


def _const_str(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _find_function_node(tree: ast.AST, function_name: str, class_name: str | None) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if class_name:
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == function_name:
                        return item
        elif isinstance(node, ast.FunctionDef) and node.name == function_name:
            return node
    return None


def _direct_shape(target: ast.FunctionDef, p: str) -> ShapeSpec | None:
    list_item_keys: set[str] = set()
    dict_keys: set[str] = set()
    attr_keys: set[str] = set()
    is_list = False
    loop_vars: set[str] = set()

    for node in ast.walk(target):
        if isinstance(node, (ast.For, ast.comprehension)) and isinstance(node.iter, ast.Name) and node.iter.id == p:
            is_list = True
            if isinstance(node.target, ast.Name):
                loop_vars.add(node.target.id)

    if loop_vars:
        for sub in ast.walk(target):
            if isinstance(sub, ast.Subscript) and isinstance(sub.value, ast.Name) and sub.value.id in loop_vars:
                key = _const_str(sub.slice)
                if key:
                    list_item_keys.add(key)

    for node in ast.walk(target):
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == p:
            key = _const_str(node.slice)
            if key:
                dict_keys.add(key)
        # Dataclass/object-style access (`product.on_hand_qty`) rather than dict
        # subscript — common for typed parameters built from a @dataclass.
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == p:
            attr_keys.add(node.attr)

    if is_list and list_item_keys:
        return ShapeSpec("list_of_dict", list_item_keys)
    if dict_keys:
        return ShapeSpec("dict", dict_keys)
    if attr_keys:
        return ShapeSpec("object", attr_keys)
    return None


def _find_any_function(tree: ast.AST, name: str) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _find_class_method(tree: ast.AST, class_name: str, method_name: str) -> ast.FunctionDef | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return item
    return None


def _resolve_callee(tree: ast.AST, call: ast.Call, class_name: str | None) -> ast.FunctionDef | None:
    if isinstance(call.func, ast.Name):
        return _find_any_function(tree, call.func.id)
    # `self.helper(...)` — a bound method call on the same instance. Decision
    # functions very commonly delegate to sibling methods (e.g. `decide()` calling
    # `self.inventory_position(product)`) rather than module-level functions, so this
    # has to be followed too or the parameter's real shape is invisible.
    if (isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name)
            and call.func.value.id == "self" and class_name):
        return _find_class_method(tree, class_name, call.func.attr)
    return None


def _interprocedural_shape(tree: ast.AST, target: ast.FunctionDef, p: str, depth: int,
                            class_name: str | None = None) -> ShapeSpec | None:
    """If `p` is never used directly in `target` but is forwarded as an argument to
    another function (module-level, or a sibling method via `self.foo(...)`), infer
    its shape from how THAT function uses its corresponding parameter — bounded-depth
    call-graph tracing, since a real agent's decision function very commonly just
    delegates (e.g. `decide()` calling `self.inventory_position(product)`).

    A parameter is very often forwarded to MULTIPLE call sites (e.g. `product` goes
    to `self.inventory_position(product)` AND `self.reorder_point(product, ...)`,
    each reading different fields off it) — every call site is merged into one shape
    rather than stopping at the first match, or only a subset of the real fields the
    object needs would ever get synthesized."""
    if depth <= 0:
        return None
    merged: ShapeSpec | None = None

    def _merge(shape: ShapeSpec | None):
        nonlocal merged
        if shape is None:
            return
        if merged is None:
            merged = ShapeSpec(shape.kind, set(shape.keys))
        elif merged.kind == shape.kind:
            merged.keys |= shape.keys

    for node in ast.walk(target):
        if not isinstance(node, ast.Call):
            continue
        callee = _resolve_callee(tree, node, class_name)
        if callee is None:
            continue
        # `self.foo(product)` -> skip the implicit `self` slot when matching positions.
        callee_params = [a for a in callee.args.args if a.arg not in ("self", "cls")]
        for i, arg in enumerate(node.args):
            if isinstance(arg, ast.Name) and arg.id == p and i < len(callee_params):
                callee_param = callee_params[i].arg
                _merge(_direct_shape(callee, callee_param))
                _merge(_interprocedural_shape(tree, callee, callee_param, depth - 1, class_name))
        for kw in node.keywords:
            if isinstance(kw.value, ast.Name) and kw.value.id == p and kw.arg:
                _merge(_direct_shape(callee, kw.arg))
    return merged


def infer_param_shapes(module_path: Path, function_name: str, class_name: str | None,
                        param_names: list[str]) -> dict[str, ShapeSpec]:
    try:
        tree = ast.parse(module_path.read_text(errors="ignore"))
    except SyntaxError:
        return {}
    target = _find_function_node(tree, function_name, class_name)
    if target is None:
        return {}

    shapes: dict[str, ShapeSpec] = {}
    for p in param_names:
        direct = _direct_shape(target, p)
        indirect = _interprocedural_shape(tree, target, p, depth=2, class_name=class_name)
        if direct and indirect and direct.kind == indirect.kind:
            shapes[p] = ShapeSpec(direct.kind, direct.keys | indirect.keys)
        else:
            shapes[p] = direct or indirect or ShapeSpec("scalar")
    return shapes


_STRING_NAME_HINTS = ("context", "text", "note", "description", "comment", "reason", "message")
_BOOL_FALSE_HINTS = ("live", "debug", "verbose", "dry_run", "mock", "test_mode", "production", "prod")


def _build_field_pool(generic_inputs: dict) -> dict:
    inv = generic_inputs.get("inventory") or {}
    dem = generic_inputs.get("demand") or {}
    sup = generic_inputs.get("supplier") or {}
    wh = generic_inputs.get("warehouse") or {}
    sku = generic_inputs.get("sku")
    history = dem.get("history") or [0]
    avg_daily = sum(history) / max(len(history), 1) / 30.0 * dem.get("demand_multiplier", 1.0)

    return {
        "product_id": sku, "sku": sku, "id": sku, "item_id": sku,
        "product_name": f"Product {sku}", "name": f"Product {sku}",
        "avg_daily_sales": round(avg_daily, 2), "daily_sales": round(avg_daily, 2),
        "demand": round(avg_daily, 2), "avg_demand": round(avg_daily, 2),
        "demand_multiplier": dem.get("demand_multiplier", 1.0), "multiplier": dem.get("demand_multiplier", 1.0),
        "reorder_multiple": 1, "preferred_days_cover": inv.get("lead_time_days", 7),
        "on_order_qty": inv.get("on_order"), "allocated_qty": inv.get("allocated"),
        "min_order_qty": sup.get("moq"),
        "on_hand_qty": inv.get("on_hand"), "on_hand": inv.get("on_hand"), "quantity_on_hand": inv.get("on_hand"),
        "stock": inv.get("on_hand"), "inventory": inv.get("on_hand"),
        "safety_stock": inv.get("safety_stock"),
        "lead_time_days": inv.get("lead_time_days"), "lead_time": inv.get("lead_time_days"),
        "unit_price": inv.get("unit_cost"), "price": inv.get("unit_cost"), "cost": inv.get("unit_cost"),
        "unit_cost": inv.get("unit_cost"),
        "supplier_id": sup.get("supplier_id"), "supplier_name": sup.get("supplier_id"),
        "reliability": sup.get("reliability_score"), "reliability_score": sup.get("reliability_score"),
        "moq": sup.get("moq"), "capacity_per_week": sup.get("capacity_per_week"),
        # Capacity *ceilings* (max order size, warehouse storage limit) are
        # semantically the opposite of an order/stock quantity — defaulting them
        # through the generic "*qty*" heuristic (a small placeholder) would silently
        # cap every order at that placeholder instead of leaving room to reorder a
        # realistic amount.
        "max_order_qty": sup.get("capacity_per_week") or 100_000, "supplier_max_order": sup.get("capacity_per_week") or 100_000,
        "warehouse_capacity": wh.get("available_units") or 1_000_000, "storage_capacity": wh.get("available_units") or 1_000_000,
        "warehouse_id": wh.get("warehouse_id"), "available_units": wh.get("available_units"),
        "on_order": inv.get("on_order"), "allocated": inv.get("allocated"), "reserved": inv.get("reserved"),
        "shipping_mode": "standard",
        # Forecast/statistical-result fields — a typed forecast object (mean,
        # confidence interval, std dev) passed as its own parameter rather than
        # embedded in inventory/demand, common in agents with real statistical
        # forecasting instead of a single demand_multiplier.
        "daily_mean": round(avg_daily, 2), "mean": round(avg_daily, 2),
        "daily_std": round(max(avg_daily * 0.2, 0.1), 2), "std": round(max(avg_daily * 0.2, 0.1), 2),
        "ci_low": round(max(avg_daily * 0.7, 0.0), 2), "ci_high": round(avg_daily * 1.3, 2),
        "lower_bound": round(max(avg_daily * 0.7, 0.0), 2), "upper_bound": round(avg_daily * 1.3, 2),
        "method": "synthetic_baseline", "rationale": "Synthesized scenario input — no real forecast history.",
        "learned_bias": 0.0, "bias": 0.0, "confidence": 0.8,
    }


def _resolve_key(key: str, pool: dict):
    if key in pool and pool[key] is not None:
        return pool[key]
    kl = key.lower()
    # A *ceiling* field (max order size, capacity, limit) is semantically the
    # opposite of the quantity it bounds — must be checked before the generic
    # "qty"-ish heuristic below, or e.g. "max_order_qty" would match "qty" and
    # get the small placeholder, silently capping every order to ~nothing.
    if any(h in kl for h in ("max_", "capacity", "limit", "ceiling")):
        return 100_000
    if any(h in kl for h in ("price", "cost", "rate", "score", "reliability", "weight")):
        return 1.0
    if any(h in kl for h in ("qty", "stock", "count", "days", "units", "amount", "demand")):
        return 10
    if any(h in kl for h in ("name", "id")):
        return "synthetic"
    return None


def render_args(shapes: dict[str, ShapeSpec], generic_inputs: dict) -> dict:
    pool = _build_field_pool(generic_inputs)
    args = {}
    for p, spec in shapes.items():
        if spec.kind == "dict":
            args[p] = {k: _resolve_key(k, pool) for k in spec.keys}
        elif spec.kind == "list_of_dict":
            args[p] = [{k: _resolve_key(k, pool) for k in spec.keys}]
        elif spec.kind == "object":
            args[p] = {k: _resolve_key(k, pool) for k in spec.keys}
        else:
            pl = p.lower()
            tokens = set(pl.split("_"))
            if (pl in _BOOL_FALSE_HINTS or tokens & set(_BOOL_FALSE_HINTS)) or pl.startswith(("is_", "use_", "enable")):
                # Default flags (e.g. live/debug/dry_run) to False/off rather than a
                # truthy dict — we never want to accidentally trigger a "real LLM /
                # live external service" code path inside the sandbox.
                args[p] = False
            elif pl in _STRING_NAME_HINTS or tokens & set(_STRING_NAME_HINTS):
                args[p] = f"Standard operating conditions for {generic_inputs.get('sku', 'this SKU')}."
            else:
                # Unknown scalar shape: try resolving the parameter name itself
                # against the business-data pool/keyword heuristics (e.g.
                # `demand_multiplier`, `lead_time_days`) before giving up — a
                # plausible number beats `None`, which turns any arithmetic the
                # function does on this parameter into a guaranteed crash.
                resolved = _resolve_key(p, pool)
                args[p] = resolved if resolved is not None else None
    return args
