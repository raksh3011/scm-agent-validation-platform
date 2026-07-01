"""Uniform 'call the agent with scenario inputs -> capture output + evidence' contract.

Retry ladder per scenario: direct call with our generic scenario shape -> if that
fails with a signature mismatch, adapter-synthesize real arguments for this specific
candidate's actual parameter shapes (list-of-dict / dict / scalar, inferred by static
analysis of how each parameter is used in the function body) and retry once -> if
still unreachable, fall through to the next ranked candidate. Every attempt runs in
its own subprocess so a crash in one scenario can't take down the run.
"""
import json
import sqlite3
import tempfile
import time
import uuid
from pathlib import Path

from . import adapter_synthesizer, sandbox
from .entrypoint_discovery import EntrypointCandidate
from ..core.models import Evidence

_RUNNER = Path(__file__).resolve().parent / "_runner.py"


def _snapshot_db(db_path: Path) -> dict:
    if not db_path.exists():
        return {}
    try:
        conn = sqlite3.connect(db_path)
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        # Table names come back from sqlite_master, not directly from a request, but
        # the agent under test has full write access to *this* sandbox db and could
        # create a table with an adversarial name (e.g. containing a quote) — quote
        # the identifier properly rather than f-string interpolating it into SQL.
        snap = {t: conn.execute(f'SELECT COUNT(*) FROM "{t.replace(chr(34), chr(34)*2)}"').fetchone()[0] for t in tables}
        conn.close()
        return snap
    except sqlite3.Error:
        return {}


def _is_signature_mismatch(exc: dict | None) -> bool:
    if not exc or exc.get("type") != "TypeError":
        return False
    return any(kw in exc.get("message", "").lower() for kw in ("argument", "positional"))


def _call(workspace: Path, candidate: EntrypointCandidate, payload: dict, sandbox_db_path: Path,
          env: dict[str, str]) -> tuple[dict | None, str | None, float]:
    with tempfile.TemporaryDirectory() as tmp:
        scenario_path = Path(tmp) / "scenario.json"
        result_path = Path(tmp) / "result.json"
        scenario_path.write_text(json.dumps({"inputs": payload}, default=str))

        start = time.time()
        proc = sandbox.run_subprocess(
            [str(_RUNNER), str(workspace), str(candidate.module_path), candidate.function_name,
             candidate.class_name or "None", str(scenario_path), str(result_path)],
            cwd=workspace, env=env,
        )
        runtime_ms = (time.time() - start) * 1000

        if proc["timed_out"]:
            return None, "timeout", runtime_ms
        if not result_path.exists():
            return None, (proc["stderr"][-500:] if proc["stderr"] else "no result produced"), runtime_ms
        return json.loads(result_path.read_text()), None, runtime_ms


def execute_scenario(workspace: Path, candidates: list[EntrypointCandidate], scenario,
                      sandbox_db_path: Path, env: dict[str, str]) -> dict:
    """Runs the scenario through each candidate in ranked order until one executes
    without an immediate import/attribute error. Returns evidence + raw outcome."""
    last_error = None
    before_snapshot = _snapshot_db(sandbox_db_path)

    for candidate in candidates[:5]:
        generic_payload = {**scenario.inputs, "db_path": str(sandbox_db_path)}
        raw, err, runtime_ms = _call(workspace, candidate, generic_payload, sandbox_db_path, env)

        if raw is None:
            last_error = err
            continue

        if _is_signature_mismatch(raw.get("exception")):
            # Generic shape didn't fit — synthesize real arguments for this
            # candidate's actual parameter shapes and retry once before giving up
            # on it entirely.
            required = getattr(candidate, "required_param_names", None) or candidate.param_names
            shapes = adapter_synthesizer.infer_param_shapes(
                candidate.module_path, candidate.function_name, candidate.class_name, required)
            rendered = adapter_synthesizer.render_args(shapes, scenario.inputs)
            raw2, err2, runtime_ms2 = _call(workspace, candidate, rendered, sandbox_db_path, env)
            if raw2 is not None and not _is_signature_mismatch(raw2.get("exception")):
                raw, runtime_ms = raw2, runtime_ms2
            else:
                last_error = (raw2 or {}).get("exception", {}).get("message") if raw2 else err2
                continue

        after_snapshot = _snapshot_db(sandbox_db_path)
        db_diff = {t: after_snapshot.get(t, 0) - before_snapshot.get(t, 0)
                   for t in set(before_snapshot) | set(after_snapshot)
                   if after_snapshot.get(t, 0) != before_snapshot.get(t, 0)}

        evidence = []
        if raw.get("stdout"):
            evidence.append(Evidence(id=uuid.uuid4().hex[:10], evidence_type="stdout",
                                      detail={"text": raw["stdout"]}, scenario_id=scenario.id))
        if raw.get("mock_calls"):
            evidence.append(Evidence(id=uuid.uuid4().hex[:10], evidence_type="mock_call",
                                      detail={"calls": raw["mock_calls"]}, scenario_id=scenario.id))
        if db_diff:
            evidence.append(Evidence(id=uuid.uuid4().hex[:10], evidence_type="db_mutation",
                                      detail={"row_count_delta": db_diff}, scenario_id=scenario.id))
        if raw.get("exception"):
            evidence.append(Evidence(id=uuid.uuid4().hex[:10], evidence_type="exception",
                                      detail=raw["exception"], scenario_id=scenario.id))

        return {
            "candidate": f"{candidate.class_name + '.' if candidate.class_name else ''}{candidate.function_name}",
            "return_value": raw.get("return_value"),
            "exception": raw.get("exception"),
            "db_diff": db_diff,
            "runtime_ms": runtime_ms,
            "evidence": evidence,
        }

    return {
        "candidate": None,
        "return_value": None,
        "exception": {"type": "EntrypointUnreachable", "message": last_error or "no candidate executed"},
        "db_diff": {},
        "runtime_ms": 0.0,
        "evidence": [Evidence(id=uuid.uuid4().hex[:10], evidence_type="exception",
                               detail={"message": last_error or "no candidate executed"}, scenario_id=scenario.id)],
    }
