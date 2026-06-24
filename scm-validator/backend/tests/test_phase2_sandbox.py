"""Phase 2 sandbox runner test. Run with: python tests/test_phase2_sandbox.py"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engine import sandbox_runner

BASE_SCENARIO = {
    "product": {"product_id": "T1", "avg_daily_sales": 50, "safety_stock": 100, "on_hand_qty": 300},
    "suppliers": [{"supplier_id": "S1", "unit_price": 10, "lead_time_days": 5, "reliability": 0.9}],
    "context": "",
    "mode": "mock",
}


def _write(tmp: Path, name: str, content: str) -> Path:
    p = tmp / name
    p.write_text(content, encoding="utf-8")
    return p


def test_normal_decision():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        adapter = _write(root, "scm_adapter.py", """
def run_decision(scenario):
    return {"action": "REORDER", "qty": 42, "supplier_id": "S1", "rop": 350, "error": None}
""")
        r = sandbox_runner.run_scenario(root, adapter, BASE_SCENARIO)
        assert r.ok, r
        assert r.result["action"] == "REORDER"
        assert r.result["qty"] == 42
        print("PASS: normal decision executes and returns expected result")


def test_crash_is_reported_not_raised():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        adapter = _write(root, "scm_adapter.py", """
def run_decision(scenario):
    raise ValueError("boom")
""")
        r = sandbox_runner.run_scenario(root, adapter, BASE_SCENARIO)
        assert r.ok is False
        assert r.crashed is True
        assert "boom" in (r.error or "")
        print("PASS: agent exception is reported as a crash, doesn't propagate")


def test_timeout():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        adapter = _write(root, "scm_adapter.py", """
import time
def run_decision(scenario):
    time.sleep(30)
    return {"action": "HOLD"}
""")
        r = sandbox_runner.run_scenario(root, adapter, BASE_SCENARIO, timeout=2)
        assert r.timed_out is True
        print("PASS: hanging agent is killed and reported as a timeout, not left to hang")


def test_network_is_blocked():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        adapter = _write(root, "scm_adapter.py", """
import socket
def run_decision(scenario):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("example.com", 80))
    return {"action": "HOLD"}
""")
        r = sandbox_runner.run_scenario(root, adapter, BASE_SCENARIO)
        assert r.ok is False
        assert r.crashed is True
        assert "network" in (r.error or "").lower()
        print("PASS: outbound network call from the agent is blocked inside the sandbox")


def test_agent_internal_print_does_not_corrupt_result():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        adapter = _write(root, "scm_adapter.py", """
def run_decision(scenario):
    print("Smart Reorder Agent [MOCK]")
    print("=" * 70)
    return {"action": "HOLD", "qty": 0, "supplier_id": None, "rop": 100, "error": None}
""")
        r = sandbox_runner.run_scenario(root, adapter, BASE_SCENARIO)
        assert r.ok, r
        assert r.result["action"] == "HOLD"
        print("PASS: agent's own print() output does not corrupt the JSON result parsing")


if __name__ == "__main__":
    test_normal_decision()
    test_crash_is_reported_not_raised()
    test_timeout()
    test_network_is_blocked()
    test_agent_internal_print_does_not_corrupt_result()
    print("\nAll Phase 2 sandbox tests passed.")
