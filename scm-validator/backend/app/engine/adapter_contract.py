"""Uniform calling contract between the harness and a submitted agent.

Every submission that wants execution-based scoring (Phases 2-5 of the Trust
Harness) needs a `scm_adapter.py` at its workspace root exposing:

    def run_decision(scenario: dict) -> dict: ...

`scenario` and the return value are both validated against the strict
Pydantic models below -- duck-typing is not enough here because we are about
to execute third-party code against it.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Callable, Optional

from pydantic import BaseModel, ConfigDict, Field

ADAPTER_FILENAME = "scm_adapter.py"
NO_ENTRYPOINT_MARKER = "AUTO_ADAPTER_NO_ENTRYPOINT"


class SupplierInput(BaseModel):
    model_config = ConfigDict(extra="allow")  # agents may carry extra fields through

    supplier_id: str
    unit_price: float
    lead_time_days: float
    reliability: float
    moq: Optional[float] = None
    eligible_skus: Optional[list[str]] = None


class ProductInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    product_id: str
    avg_daily_sales: float
    safety_stock: float
    on_hand_qty: float


class ScenarioInput(BaseModel):
    product: ProductInput
    suppliers: list[SupplierInput] = Field(default_factory=list)
    context: str = ""
    mode: str = "mock"


class DecisionOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    action: str  # "REORDER" | "HOLD"
    qty: float = 0
    supplier_id: Optional[str] = None
    rop: Optional[float] = None
    error: Optional[str] = None


# ---- Loading an existing adapter from a submission's workspace ----

def load_adapter(workspace_path: Path) -> Optional[Callable]:
    """Imports scm_adapter.py from the submission root and returns its run_decision
    function, or None if the file is missing or doesn't import cleanly.

    NOTE: this import happens in-process. It is only safe to call this for static
    inspection (e.g. confirming the function exists) -- actual *execution* of
    run_decision() against scenarios must go through sandbox_runner, never here.
    """
    adapter_path = workspace_path / ADAPTER_FILENAME
    if not adapter_path.exists():
        return None

    import importlib.util
    try:
        spec = importlib.util.spec_from_file_location("scm_adapter", adapter_path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        fn = getattr(module, "run_decision", None)
        return fn if callable(fn) else None
    except Exception:
        return None


# ---- Best-effort auto-generated adapter stub ----

DECISION_VERB_RE = re.compile(
    r"(decide|choose|select|recommend|optimize|plan|reorder|forecast|allocate|predict|evaluate)",
    re.IGNORECASE,
)

# Common entrypoint shapes we know how to bridge automatically.
KNOWN_PARAM_SHAPES = [
    # (required_param_names_in_order, live_param_name_or_None)
    (["product", "suppliers", "context", "live"], "live"),
    (["product", "suppliers", "context"], None),
    (["product", "suppliers"], None),
]


def _find_decision_function(facts) -> tuple[Optional[str], Optional[str], Optional[list[str]]]:
    """Returns (module_rel_path, function_name, param_names) of the best candidate
    decision entrypoint, or (None, None, None) if nothing confident was found."""
    best = None
    for f in facts.files:
        if f.ext != ".py" or not f.content:
            continue
        try:
            tree = ast.parse(f.content)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not DECISION_VERB_RE.search(node.name):
                continue
            params = [a.arg for a in node.args.args]
            for shape, _live_param in KNOWN_PARAM_SHAPES:
                if all(p in params for p in shape):
                    best = (f.rel_path, node.name, params)
                    break
            if best:
                break
        if best:
            break
    return best or (None, None, None)


def auto_generate_adapter_stub(facts) -> str:
    """Best-effort: detect the most likely decision entrypoint and emit a draft
    scm_adapter.py that bridges the harness's ScenarioInput shape onto it.

    This is intentionally conservative -- it only matches a small set of known
    parameter shapes (product, suppliers[, context[, live]]). If nothing
    confident is found, it returns a stub that always errors clearly, so a
    submitter knows manual adaptation is required rather than silently
    getting zero-effort wrong results.
    """
    module_path, fn_name, params = _find_decision_function(facts)

    if not fn_name:
        return (
            f"# {NO_ENTRYPOINT_MARKER}\n"
            "# AUTO-GENERATED ADAPTER STUB -- could not confidently detect a decision\n"
            "# entrypoint in this submission. Manual scm_adapter.py is required.\n"
            "def run_decision(scenario: dict) -> dict:\n"
            "    return {\n"
            "        \"action\": \"HOLD\",\n"
            "        \"qty\": 0,\n"
            "        \"supplier_id\": None,\n"
            "        \"rop\": None,\n"
            "        \"error\": \"auto-adapter could not detect a decision entrypoint; "
            "submit a manual scm_adapter.py\",\n"
            "    }\n"
        )

    module_name = module_path.rsplit(".", 1)[0].replace("/", ".")
    has_live = "live" in params
    has_context = "context" in params

    call_args = "scenario[\"product\"], scenario[\"suppliers\"]"
    if has_context:
        call_args += ", scenario.get(\"context\", \"\")"
    if has_live:
        call_args += ", live=(scenario.get(\"mode\") != \"mock\")"

    return (
        f"# AUTO-GENERATED ADAPTER STUB -- best-effort mapping onto {module_name}.{fn_name}.\n"
        f"# Detected parameters: {params}. Review before trusting harness results;\n"
        f"# this stub does not know your function's exact return shape and does a\n"
        f"# best-effort field mapping below -- adjust if your function returns differently.\n"
        f"from {module_name} import {fn_name}\n\n"
        f"def run_decision(scenario: dict) -> dict:\n"
        f"    try:\n"
        f"        result = {fn_name}({call_args})\n"
        f"    except Exception as e:\n"
        f"        return {{\"action\": \"HOLD\", \"qty\": 0, \"supplier_id\": None, \"rop\": None, \"error\": str(e)}}\n"
        f"    if not isinstance(result, dict):\n"
        f"        return {{\"action\": \"HOLD\", \"qty\": 0, \"supplier_id\": None, \"rop\": None,\n"
        f"                \"error\": \"decision function did not return a dict; auto-adapter cannot map it\"}}\n"
        f"    supplier = result.get(\"supplier\") or {{}}\n"
        f"    return {{\n"
        f"        \"action\": result.get(\"action\", \"HOLD\"),\n"
        f"        \"qty\": result.get(\"qty\", 0),\n"
        f"        \"supplier_id\": supplier.get(\"supplier_id\") if isinstance(supplier, dict) else result.get(\"supplier_id\"),\n"
        f"        \"rop\": result.get(\"rop\"),\n"
        f"        \"error\": result.get(\"error\"),\n"
        f"    }}\n"
    )
