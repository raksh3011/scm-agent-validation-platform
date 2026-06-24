"""Phase 3 invariant test suite smoke test. Run with: python tests/test_phase3_invariants.py

Uses plain in-process callables here (not the sandbox) -- sandboxing itself
is already covered by test_phase2_sandbox.py. This file is testing the
invariant *logic*, i.e. that a correct agent passes all required checks and
a deliberately broken one (sign error, random supplier) fails the right ones.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engine.invariant_tests import run_invariant_tests


def correct_run_decision(scenario: dict) -> dict:
    product = scenario["product"]
    suppliers = scenario["suppliers"]
    if not suppliers:
        return {"action": "HOLD", "qty": 0, "supplier_id": None, "rop": None, "error": "no suppliers available"}

    demand = product["avg_daily_sales"]
    on_hand = product["on_hand_qty"]
    safety_stock = product["safety_stock"]

    def score(s):
        return 0.4 * (1 / s["unit_price"]) + 0.3 * s["reliability"] + 0.3 * (1 / s["lead_time_days"])

    best = max(suppliers, key=score)
    lead = best["lead_time_days"]
    rop = demand * lead + safety_stock

    if on_hand < 0:
        return {"action": "HOLD", "qty": 0, "supplier_id": None, "rop": rop, "error": "negative on-hand quantity (data error)"}

    if on_hand <= rop:
        target = demand * (lead + 7) + safety_stock
        qty = max(0, round(target - on_hand))
        return {"action": "REORDER", "qty": qty, "supplier_id": best["supplier_id"], "rop": rop, "error": None}
    return {"action": "HOLD", "qty": 0, "supplier_id": best["supplier_id"], "rop": rop, "error": None}


def broken_run_decision(scenario: dict) -> dict:
    import random
    product = scenario["product"]
    suppliers = scenario["suppliers"]
    if not suppliers:
        raise IndexError("no suppliers")  # crashes instead of failing safely

    demand = product["avg_daily_sales"]
    on_hand = product["on_hand_qty"]
    safety_stock = product["safety_stock"]
    lead = suppliers[0]["lead_time_days"]

    rop = demand * lead - safety_stock  # SIGN ERROR: subtracts instead of adds
    chosen = random.choice(suppliers)  # random selection, ignores Pareto dominance

    qty = round(demand * lead - on_hand)  # can go negative
    return {"action": "REORDER", "qty": qty, "supplier_id": chosen["supplier_id"], "rop": rop, "error": None}


def test_correct_agent_passes_all_required():
    results = run_invariant_tests(correct_run_decision)
    failed = [r for r in results if not r.passed]
    assert not failed, f"correct agent unexpectedly failed: {[(r.test_id, r.detail) for r in failed]}"
    print(f"PASS: correct agent passes all {len(results)} required invariants")


def test_broken_agent_fails_expected_invariants():
    results = run_invariant_tests(broken_run_decision)
    by_id = {r.test_id: r for r in results}
    assert not by_id["INV_ROP_MONOTONIC_SAFETY_STOCK"].passed, "expected safety-stock sign error to be caught"
    assert not by_id["INV_PARETO_SUPPLIER_NOT_CHOSEN"].passed, "expected random supplier choice to be caught"
    assert not by_id["INV_NO_SUPPLIERS_FAILS_SAFELY"].passed, "expected crash-on-no-suppliers to be caught"
    print("PASS: broken agent correctly fails INV_ROP_MONOTONIC_SAFETY_STOCK, INV_PARETO_SUPPLIER_NOT_CHOSEN, INV_NO_SUPPLIERS_FAILS_SAFELY")
    failed_ids = [r.test_id for r in results if not r.passed]
    print(f"      full failed list: {failed_ids}")


if __name__ == "__main__":
    test_correct_agent_passes_all_required()
    test_broken_agent_fails_expected_invariants()
    print("\nAll Phase 3 invariant tests passed.")
