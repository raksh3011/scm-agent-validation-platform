"""Resolves a submission's adapter (existing or auto-generated) and produces a
uniform, never-raising run_decision callable wired through the sandbox.

This is the glue between Phase 1 (adapter_contract), Phase 2 (sandbox_runner),
and Phases 3/4 (invariant_tests / golden_scenario_runner), which all expect a
plain `Callable[[dict], dict]` that never raises.
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import adapter_contract, sandbox_runner

ADAPTER_STATUS_NOT_ATTEMPTED = "not_attempted"
ADAPTER_STATUS_LOADED = "loaded"
ADAPTER_STATUS_AUTO_GENERATED = "auto_generated"
ADAPTER_STATUS_FAILED = "failed"

_SMOKE_SCENARIO = {
    "product": {"product_id": "SMOKE", "avg_daily_sales": 10, "safety_stock": 5, "on_hand_qty": 50},
    "suppliers": [{"supplier_id": "SMOKE_S1", "unit_price": 1, "lead_time_days": 1, "reliability": 1.0}],
    "context": "",
    "mode": "mock",
}


@dataclass
class ResolvedAdapter:
    status: str                      # loaded | auto_generated | failed | not_attempted
    adapter_path: Path | None
    run_decision: Callable[[dict], dict] | None


def resolve_adapter(run_id: str, workspace: Path, facts) -> ResolvedAdapter:
    """Finds or generates an adapter, smoke-tests it once, and returns a
    never-raising run_decision callable (or None if nothing usable exists)."""
    existing = workspace / adapter_contract.ADAPTER_FILENAME
    if existing.exists():
        adapter_path = existing
        status = ADAPTER_STATUS_LOADED
    else:
        stub_source = adapter_contract.auto_generate_adapter_stub(facts)
        if adapter_contract.NO_ENTRYPOINT_MARKER in stub_source:
            return ResolvedAdapter(status=ADAPTER_STATUS_FAILED, adapter_path=None, run_decision=None)
        tmp_dir = Path(tempfile.gettempdir()) / "scm_harness_auto_adapters"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        adapter_path = tmp_dir / f"{run_id}_auto_adapter.py"
        adapter_path.write_text(stub_source, encoding="utf-8")
        status = ADAPTER_STATUS_AUTO_GENERATED

    smoke = sandbox_runner.run_scenario(workspace, adapter_path, _SMOKE_SCENARIO, timeout=10)
    if smoke.crashed and not smoke.ok and smoke.result is None and smoke.error and "import" in (smoke.error or "").lower():
        return ResolvedAdapter(status=ADAPTER_STATUS_FAILED, adapter_path=None, run_decision=None)
    # A clean import that simply produced a handled error/timeout for the smoke
    # scenario is NOT an adapter failure -- it's a legitimate behavior result
    # (e.g. the agent genuinely can't handle this scenario). Only a failure to
    # even import/call the adapter at all counts as "adapter failed".
    if smoke.error and "could not detect" in (smoke.error or "").lower():
        return ResolvedAdapter(status=ADAPTER_STATUS_FAILED, adapter_path=None, run_decision=None)

    def run_decision(scenario: dict) -> dict:
        r = sandbox_runner.run_scenario(workspace, adapter_path, scenario, timeout=10)
        if r.timed_out:
            return {"action": "HOLD", "qty": 0, "supplier_id": None, "rop": None, "error": f"timeout: {r.error}"}
        if r.crashed or not r.ok or r.result is None:
            return {"action": "HOLD", "qty": 0, "supplier_id": None, "rop": None, "error": r.error or "adapter call failed"}
        result = dict(r.result)
        result.setdefault("error", None)
        result.setdefault("qty", 0)
        result.setdefault("supplier_id", None)
        result.setdefault("rop", None)
        result.setdefault("action", "HOLD")
        return result

    return ResolvedAdapter(status=status, adapter_path=adapter_path, run_decision=run_decision)
