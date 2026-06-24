"""Runs a submission's run_decision() in an isolated subprocess.

This is non-negotiable once third-party code is being executed: never call
run_decision() in-process inside the API server.

What this MVP actually enforces:
  - Process isolation (separate Python process, not a thread/in-process call).
  - Hard wall-clock timeout (subprocess.run(..., timeout=...)); a hang is killed
    and reported as a timeout, not left to block the server.
  - No outbound network from the subprocess: socket.socket is monkeypatched to
    raise before the adapter module is even imported. Combined with the harness
    always passing mode="mock", this means a real LLM/HTTP call inside the
    agent will error out rather than ever reaching a live, paid API.
  - The subprocess's own stdout is captured separately from the JSON result
    line, so an agent that prints/logs internally can't corrupt the result
    parsing.

What this MVP does NOT enforce (documented limitation, not silently skipped):
  - Memory limits. Python's `resource.setrlimit` is POSIX-only and this
    deployment target is Windows, so no hard memory cap is applied. The
    wall-clock timeout is the only resource bound in this version. A more
    robust deployment should run this in a container with a memory limit
    (e.g. `docker run --memory=256m`) -- noted here, not implemented, because
    containerizing the whole harness is out of scope for this pass.
"""
from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DEFAULT_TIMEOUT_SECONDS = 10

_SUBPROCESS_ENTRY = '''
import sys, os, json, importlib.util, io, contextlib, traceback


def _block_network():
    import socket

    class _BlockedSocket(socket.socket):
        def connect(self, *a, **k):
            raise OSError("network access is disabled inside the harness sandbox")
        def connect_ex(self, *a, **k):
            raise OSError("network access is disabled inside the harness sandbox")

    socket.socket = _BlockedSocket


def main():
    _block_network()
    workspace = sys.argv[1]
    adapter_path = sys.argv[2]
    sys.path.insert(0, workspace)

    scenario = json.loads(sys.stdin.read())

    spec = importlib.util.spec_from_file_location("scm_adapter_under_test", adapter_path)
    module = importlib.util.module_from_spec(spec)

    try:
        spec.loader.exec_module(module)
        run_decision = getattr(module, "run_decision")
    except Exception as e:
        print(json.dumps({"ok": False, "crashed": True, "phase": "import",
                           "error": str(e), "traceback": traceback.format_exc()}))
        return

    # Swallow whatever the agent prints internally so it can't corrupt the
    # single JSON line we rely on for the result.
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(captured):
            result = run_decision(scenario)
        print(json.dumps({"ok": True, "crashed": False, "result": result}))
    except Exception as e:
        print(json.dumps({"ok": False, "crashed": True, "phase": "call",
                           "error": str(e), "traceback": traceback.format_exc()}))


if __name__ == "__main__":
    main()
'''


@dataclass
class SandboxRunResult:
    ok: bool
    crashed: bool
    timed_out: bool
    result: Optional[dict]
    error: Optional[str]
    raw_stderr: str = ""


def _entry_script_path() -> Path:
    """Write the subprocess entry script to a stable temp file once per process."""
    path = Path(tempfile.gettempdir()) / "scm_harness_sandbox_entry.py"
    try:
        existing = path.read_text(encoding="utf-8") if path.exists() else None
    except Exception:
        existing = None
    if existing != _SUBPROCESS_ENTRY:
        path.write_text(_SUBPROCESS_ENTRY, encoding="utf-8")
    return path


def run_scenario(
    workspace: Path,
    adapter_path: Path,
    scenario: dict,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> SandboxRunResult:
    """Executes run_decision(scenario) from adapter_path, inside a fresh subprocess,
    with a hard wall-clock timeout and no network access."""
    entry = _entry_script_path()
    try:
        proc = subprocess.run(
            [sys.executable, str(entry), str(workspace), str(adapter_path)],
            input=json.dumps(scenario),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        return SandboxRunResult(
            ok=False, crashed=False, timed_out=True, result=None,
            error=f"agent did not respond within {timeout}s (hung or too slow)",
            raw_stderr=(e.stderr or "") if isinstance(e.stderr, str) else "",
        )

    stdout = (proc.stdout or "").strip()
    last_line = stdout.splitlines()[-1] if stdout else ""
    try:
        payload = json.loads(last_line)
    except (ValueError, IndexError):
        return SandboxRunResult(
            ok=False, crashed=True, timed_out=False, result=None,
            error=f"subprocess produced no parseable JSON result (exit code {proc.returncode})",
            raw_stderr=proc.stderr or "",
        )

    return SandboxRunResult(
        ok=bool(payload.get("ok")),
        crashed=bool(payload.get("crashed")),
        timed_out=False,
        result=payload.get("result"),
        error=payload.get("error"),
        raw_stderr=proc.stderr or "",
    )
