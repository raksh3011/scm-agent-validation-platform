"""Execution-based invariant tests (Trust Harness Phase 3).

Each test calls `run_decision` (a plain callable: dict -> dict; the caller is
responsible for routing this through sandbox_runner rather than calling a raw
agent function in-process) with systematically varied scenarios and asserts a
relationship that any correct SCM reorder agent must satisfy. No golden
dataset needed -- these are properties, not fixed expected values.

Required-tier failures are hard blockers (principles 1, 2, 3, 4, 6, 7 from the
mission brief). There are no recommended-tier invariant tests in this module;
MOQ/demand-direction softness lives in the golden scenarios instead (Phase 4),
since those need concrete expected numbers rather than a pure relationship.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..report_schema import InvariantResult

RunDecision = Callable[[dict], dict]

BASE_PRODUCT = {"product_id": "T1", "avg_daily_sales": 50, "safety_stock": 100, "on_hand_qty": 300}
BASE_SUPPLIERS = [{"supplier_id": "S1", "unit_price": 10, "lead_time_days": 5, "reliability": 0.9}]


def _scenario(product=None, suppliers=None, context="", mode="mock") -> dict:
    return {
        "product": product or BASE_PRODUCT,
        "suppliers": suppliers if suppliers is not None else BASE_SUPPLIERS,
        "context": context,
        "mode": mode,
    }


def test_rop_monotonic_in_lead_time(run_decision: RunDecision):
    short = run_decision(_scenario(suppliers=[{**BASE_SUPPLIERS[0], "lead_time_days": 3}]))
    long = run_decision(_scenario(suppliers=[{**BASE_SUPPLIERS[0], "lead_time_days": 15}]))
    rop_short, rop_long = short.get("rop"), long.get("rop")
    assert rop_short is not None and rop_long is not None, f"rop missing from result(s): short={short}, long={long}"
    assert rop_long > rop_short, f"ROP did not increase with lead time (short={rop_short}, long={rop_long}) -- possible sign error"


def test_rop_monotonic_in_safety_stock(run_decision: RunDecision):
    low = run_decision(_scenario(product={**BASE_PRODUCT, "safety_stock": 10}))
    high = run_decision(_scenario(product={**BASE_PRODUCT, "safety_stock": 500}))
    rop_low, rop_high = low.get("rop"), high.get("rop")
    assert rop_low is not None and rop_high is not None, f"rop missing from result(s): low={low}, high={high}"
    assert rop_high > rop_low, f"ROP did not increase with safety stock (low={rop_low}, high={rop_high}) -- likely subtracted instead of added"


def test_qty_never_negative(run_decision: RunDecision):
    for on_hand in [0, 1_000_000]:
        result = run_decision(_scenario(product={**BASE_PRODUCT, "on_hand_qty": on_hand}))
        qty = result.get("qty", 0)
        assert qty >= 0, f"qty was negative ({qty}) for on_hand_qty={on_hand}: {result}"


def test_pareto_dominated_supplier_never_chosen(run_decision: RunDecision):
    dominated = {"supplier_id": "BAD", "unit_price": 20, "lead_time_days": 20, "reliability": 0.3}
    dominant = {"supplier_id": "GOOD", "unit_price": 8, "lead_time_days": 4, "reliability": 0.95}
    result = run_decision(_scenario(suppliers=[dominated, dominant]))
    assert result.get("supplier_id") != "BAD", f"Pareto-dominated supplier BAD was selected: {result}"


def test_no_suppliers_fails_safely(run_decision: RunDecision):
    result = run_decision(_scenario(suppliers=[]))
    assert result.get("error") is not None or result.get("action") == "HOLD", \
        f"zero suppliers did not produce a handled error or HOLD: {result}"


def test_negative_on_hand_does_not_crash(run_decision: RunDecision):
    result = run_decision(_scenario(product={**BASE_PRODUCT, "on_hand_qty": -50}))
    qty = result.get("qty", 0)
    ok = result.get("error") is not None or (qty >= 0 and qty < 1_000_000)
    assert ok, f"negative on-hand quantity produced a nonsensical/unbounded result: {result}"


def test_deterministic_repeat(run_decision: RunDecision):
    scenario = _scenario()
    r1 = run_decision(scenario)
    r2 = run_decision(scenario)
    assert r1 == r2, f"same input produced different output in mock mode -- hidden nondeterminism: {r1} != {r2}"


@dataclass
class InvariantCheck:
    test_id: str
    tier: str
    fn: Callable[[RunDecision], None]


ALL_INVARIANTS: list[InvariantCheck] = [
    InvariantCheck("INV_ROP_MONOTONIC_LEAD_TIME", "required", test_rop_monotonic_in_lead_time),
    InvariantCheck("INV_ROP_MONOTONIC_SAFETY_STOCK", "required", test_rop_monotonic_in_safety_stock),
    InvariantCheck("INV_QTY_NEVER_NEGATIVE", "required", test_qty_never_negative),
    InvariantCheck("INV_PARETO_SUPPLIER_NOT_CHOSEN", "required", test_pareto_dominated_supplier_never_chosen),
    InvariantCheck("INV_NO_SUPPLIERS_FAILS_SAFELY", "required", test_no_suppliers_fails_safely),
    InvariantCheck("INV_NEGATIVE_ON_HAND_NO_CRASH", "required", test_negative_on_hand_does_not_crash),
    InvariantCheck("INV_DETERMINISTIC_REPEAT", "required", test_deterministic_repeat),
]


def run_invariant_tests(run_decision: RunDecision) -> list[InvariantResult]:
    """Runs every invariant check; a check raising any exception (not just
    AssertionError -- a crash inside run_decision should also fail its check,
    not abort the whole suite) counts as a failure with the exception text
    as the detail."""
    results: list[InvariantResult] = []
    for check in ALL_INVARIANTS:
        try:
            check.fn(run_decision)
            results.append(InvariantResult(test_id=check.test_id, tier=check.tier, passed=True, detail="ok"))
        except AssertionError as e:
            results.append(InvariantResult(test_id=check.test_id, tier=check.tier, passed=False, detail=str(e)))
        except Exception as e:
            results.append(InvariantResult(test_id=check.test_id, tier=check.tier, passed=False, detail=f"check itself errored: {e}"))
    return results
