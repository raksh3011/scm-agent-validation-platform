"""Phase 0 applicability gate test. Run with: python tests/test_phase0_applicability.py
Bare-assert script (no pytest dependency in this project)."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engine import static_analyzer, rule_engine_v2 as rule_engine


def test_trivial_non_scm_fixture_rejected():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "add.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
        facts = static_analyzer.build_repo_facts(root)
        is_applicable, reason = rule_engine.check_applicability(facts)
        assert is_applicable is False, f"expected non-applicable, got applicable. reason={reason!r}"
        assert reason, "expected a non-empty reason"
        print(f"PASS: trivial non-SCM fixture rejected. reason={reason!r}")


def test_real_scm_agent_accepted():
    root = Path(__file__).resolve().parent.parent.parent.parent  # repo root containing smart_reorder_agent.py
    agent_path = root / "smart_reorder_agent.py"
    assert agent_path.exists(), f"expected fixture at {agent_path}"
    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        (tmp_root / "smart_reorder_agent.py").write_text(agent_path.read_text(encoding="utf-8"), encoding="utf-8")
        facts = static_analyzer.build_repo_facts(tmp_root)
        is_applicable, reason = rule_engine.check_applicability(facts)
        assert is_applicable is True, f"expected applicable, got rejected. reason={reason!r}"
        print("PASS: real SCM agent (smart_reorder_agent.py) accepted by applicability gate")


if __name__ == "__main__":
    test_trivial_non_scm_fixture_rejected()
    test_real_scm_agent_accepted()
    print("\nAll Phase 0 tests passed.")
