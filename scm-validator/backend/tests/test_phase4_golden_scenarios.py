"""Phase 4 golden scenario grading smoke test. Run with: python tests/test_phase4_golden_scenarios.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engine.golden_scenario_runner import run_golden_scenarios


def correct_run_decision(scenario: dict) -> dict:
    product = scenario["product"]
    suppliers = scenario["suppliers"]
    if not suppliers:
        return {"action": "HOLD", "qty": 0, "supplier_id": None, "rop": None, "error": "no suppliers available"}

    demand = product["avg_daily_sales"]
    on_hand = product["on_hand_qty"]
    safety_stock = product["safety_stock"]

    # Eligibility filter (GS-07): only consider suppliers that declare this SKU,
    # unless none declare eligibility lists at all (backward compatible).
    pid = product["product_id"]
    any_declare = any(s.get("eligible_skus") for s in suppliers)
    eligible = [s for s in suppliers if not any_declare or pid in (s.get("eligible_skus") or [])]
    if not eligible:
        eligible = suppliers

    def score(s):
        return 0.4 * (1 / s["unit_price"]) + 0.3 * s["reliability"] + 0.3 * (1 / s["lead_time_days"])

    best = max(eligible, key=score)
    lead = best["lead_time_days"]
    rop = demand * lead + safety_stock

    if on_hand < 0:
        return {"action": "HOLD", "qty": 0, "supplier_id": None, "rop": rop, "error": "negative on-hand quantity (data error)"}

    if on_hand <= rop:
        target = demand * (lead + 7) + safety_stock
        qty = max(0, round(target - on_hand))
        moq = best.get("moq")
        if moq and qty > 0:
            qty = max(qty, moq)
        return {"action": "REORDER", "qty": qty, "supplier_id": best["supplier_id"], "rop": rop, "error": None}
    return {"action": "HOLD", "qty": 0, "supplier_id": best["supplier_id"], "rop": rop, "error": None}


def broken_run_decision(scenario: dict) -> dict:
    product = scenario["product"]
    suppliers = scenario["suppliers"]
    if not suppliers:
        return {"action": "HOLD", "qty": 0, "supplier_id": None, "rop": None, "error": "unhandled exception: no suppliers"}

    demand = product["avg_daily_sales"]
    on_hand = product["on_hand_qty"]
    lead = suppliers[0]["lead_time_days"]
    rop = demand * lead  # ignores safety stock entirely -- still a real bug, no eligibility check either

    # Deterministically takes the first declared supplier with no comparison and no
    # product-eligibility filter at all -- mirrors the actual choose_supplier(suppliers)
    # defect: takes no `product` param, so it can't tell suppliers apart on fit or quality.
    chosen = suppliers[0]

    qty = max(0, round(demand * lead - on_hand))
    action = "REORDER" if on_hand <= rop else "HOLD"
    return {"action": action, "qty": qty, "supplier_id": chosen["supplier_id"], "rop": rop, "error": None}


def test_correct_agent_passes_all_required_scenarios():
    results = run_golden_scenarios(correct_run_decision)
    required_failed = [r for r in results if r.tier == "required" and not r.passed]
    assert not required_failed, f"correct agent failed required scenarios: {[(r.scenario_id, r.detail) for r in required_failed]}"
    print(f"PASS: correct agent passes all required golden scenarios ({sum(1 for r in results if r.tier=='required')} of them)")


def test_broken_agent_fails_gs06_and_gs07():
    results = run_golden_scenarios(broken_run_decision)
    by_id = {r.scenario_id: r for r in results}
    assert not by_id["GS-06"].passed, "expected Pareto-dominated supplier (random choice) to be caught by GS-06"
    assert not by_id["GS-07"].passed, "expected ineligible-supplier selection (random choice, no eligibility check) to be caught by GS-07"
    print("PASS: broken agent (no comparison, no eligibility check -- always picks first supplier) correctly fails GS-06 and GS-07")
    print(f"      full result: {[(r.scenario_id, r.passed) for r in results]}")


if __name__ == "__main__":
    test_correct_agent_passes_all_required_scenarios()
    test_broken_agent_fails_gs06_and_gs07()
    print("\nAll Phase 4 golden scenario tests passed.")
