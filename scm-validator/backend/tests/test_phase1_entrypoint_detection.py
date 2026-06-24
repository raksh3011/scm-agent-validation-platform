"""Phase 1 entrypoint-detection regression test. Run with:
python tests/test_phase1_entrypoint_detection.py

Regression: a helper function whose name happens to match the decision-verb
regex (e.g. choose_supplier) and whose params happen to overlap a weaker
known shape must NOT be picked over the true top-level entrypoint (decide)
that matches a stronger, more specific shape -- regardless of source order.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engine import static_analyzer, adapter_contract as ac

FIXTURE = '''
def choose_supplier(suppliers, product=None):
    """A helper whose name matches the decision-verb regex ("choose") and whose
    params (suppliers, product) coincidentally match a weaker known shape."""
    return suppliers[0]


def decide(product, suppliers, context, live):
    """The true top-level entrypoint -- must win despite appearing after
    choose_supplier in source order."""
    s = choose_supplier(suppliers, product)
    return {"action": "HOLD", "supplier": s, "qty": 0, "rop": 0}
'''


def test_stronger_shape_wins_over_earlier_weaker_match():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "agent.py").write_text(FIXTURE, encoding="utf-8")
        facts = static_analyzer.build_repo_facts(root)
        rel_path, fn_name, params = ac._find_decision_function(facts)
        assert fn_name == "decide", f"expected 'decide' to win, got {fn_name!r} with params {params}"
        print(f"PASS: 'decide' (4-param shape) correctly wins over 'choose_supplier' (2-param shape) despite source order")


if __name__ == "__main__":
    test_stronger_shape_wins_over_earlier_weaker_match()
    print("\nAll Phase 1 entrypoint-detection tests passed.")
