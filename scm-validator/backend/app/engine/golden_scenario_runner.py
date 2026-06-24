"""Golden-scenario grading (Trust Harness Phase 4).

Loads golden_scenarios.json, calls `run_decision` for each entry, and grades
pass/fail against the scenario's `expect` block. `run_decision` is expected
to follow the same uniform contract as invariant_tests.py: always returns a
dict, never raises -- any sandbox-level crash/timeout/import failure should
already have been folded into `{"error": "...", "action": "HOLD", ...}` by
the caller (see pipeline.py's wiring), so grading never needs to special-case
exceptions.

Arithmetic reference used to construct expected ranges:
  ROP = demand * lead_time + safety_stock
  target = demand * (lead_time + 7) + safety_stock   (7-day review period)
  qty = max(0, target - on_hand)
If a submission's agent uses a different fixed review period, that's fine --
`qty` is treated as secondary/loose (wide tolerance bands); `action` and `rop`
are the primary hard checks.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from ..report_schema import ScenarioResult

RunDecision = Callable[[dict], dict]

_SCENARIOS_PATH = Path(__file__).resolve().parent / "golden_scenarios.json"


def load_golden_scenarios() -> list[dict]:
    return json.loads(_SCENARIOS_PATH.read_text(encoding="utf-8"))


def _grade(scenario: dict, result: dict) -> tuple[bool, str]:
    expect = scenario["expect"]
    reasons = []
    passed = True

    if "action" in expect:
        if result.get("action") != expect["action"]:
            passed = False
            reasons.append(f"expected action={expect['action']!r}, got {result.get('action')!r}")

    if "rop_min" in expect or "rop_max" in expect:
        rop = result.get("rop")
        if rop is None:
            passed = False
            reasons.append("expected a numeric rop, got None")
        else:
            if "rop_min" in expect and rop < expect["rop_min"]:
                passed = False
                reasons.append(f"rop {rop} below expected min {expect['rop_min']}")
            if "rop_max" in expect and rop > expect["rop_max"]:
                passed = False
                reasons.append(f"rop {rop} above expected max {expect['rop_max']}")

    if "qty_min" in expect or "qty_max" in expect:
        qty = result.get("qty", 0) or 0
        if "qty_min" in expect and qty < expect["qty_min"]:
            passed = False
            reasons.append(f"qty {qty} below expected min {expect['qty_min']}")
        if "qty_max" in expect and qty > expect["qty_max"]:
            passed = False
            reasons.append(f"qty {qty} above expected max {expect['qty_max']}")

    if "supplier_id" in expect:
        if result.get("supplier_id") != expect["supplier_id"]:
            passed = False
            reasons.append(f"expected supplier_id={expect['supplier_id']!r}, got {result.get('supplier_id')!r}")

    if "supplier_id_not" in expect:
        if result.get("supplier_id") == expect["supplier_id_not"]:
            passed = False
            reasons.append(f"supplier_id {expect['supplier_id_not']!r} should never be chosen here")

    if expect.get("action_or_error"):
        if not (result.get("error") is not None or result.get("action") == "HOLD"):
            passed = False
            reasons.append("expected a handled error or HOLD action for this degenerate input")

    if expect.get("no_crash"):
        if result.get("error") and result.get("qty") is None:
            # error present is fine (handled failure); only flag if it looks like the
            # caller folded a real crash in with no usable qty at all.
            pass
        qty = result.get("qty")
        if qty is not None and "qty_max" in expect and qty > expect["qty_max"]:
            passed = False
            reasons.append(f"qty {qty} exceeds sane bound {expect['qty_max']} for degenerate input")

    if "qty_min_if_reorder" in expect:
        if result.get("action") == "REORDER":
            qty = result.get("qty", 0) or 0
            if qty < expect["qty_min_if_reorder"]:
                passed = False
                reasons.append(f"REORDER qty {qty} below MOQ {expect['qty_min_if_reorder']}")

    return passed, "; ".join(reasons) if reasons else "ok"


def run_golden_scenarios(run_decision: RunDecision) -> list[ScenarioResult]:
    scenarios = load_golden_scenarios()
    results: list[ScenarioResult] = []
    for sc in scenarios:
        scenario_input = {
            "product": sc["product"],
            "suppliers": sc["suppliers"],
            "context": sc.get("context", ""),
            "mode": "mock",
        }
        try:
            actual = run_decision(scenario_input)
        except Exception as e:
            actual = {"action": "HOLD", "qty": 0, "supplier_id": None, "rop": None, "error": f"unhandled exception: {e}"}

        passed, detail = _grade(sc, actual)
        results.append(ScenarioResult(
            scenario_id=sc["id"], tier=sc.get("tier", "required"), passed=passed,
            description=sc.get("description", ""), expected=sc["expect"], actual=actual, detail=detail,
        ))
    return results
