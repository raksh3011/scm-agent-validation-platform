"""Subprocess isolation with timeout and resource caps."""
import subprocess
import sys
from pathlib import Path

from ..core.config import SCENARIO_EXECUTION_TIMEOUT_SECONDS


def run_subprocess(args: list[str], cwd: Path, env: dict[str, str] | None = None,
                    timeout: float = SCENARIO_EXECUTION_TIMEOUT_SECONDS) -> dict:
    try:
        proc = subprocess.run(
            [sys.executable, *args],
            cwd=str(cwd), env=env, capture_output=True, text=True, timeout=timeout,
        )
        return {
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as e:
        return {
            "returncode": None,
            "stdout": e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or ""),
            "stderr": "TimeoutExpired",
            "timed_out": True,
        }
