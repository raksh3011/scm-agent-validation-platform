"""Agent Initialization + Sandbox Validation preflight: before committing to a full
scenario suite, run ONE smoke scenario against each ranked entrypoint candidate. This
is the fix for the failure mode where an unreachable agent burns the full suite (and
wall-clock time) just to prove the same crash hundreds of times. The first candidate
that survives the smoke scenario is locked in and reused for the entire run — no more
per-scenario candidate retry ladder once a working candidate is known."""
from dataclasses import dataclass, field
from pathlib import Path

from . import recovery_advisor
from .entrypoint_discovery import EntrypointCandidate
from .execution_adapter import execute_scenario
from ..core.models import Scenario


@dataclass
class InitResult:
    success: bool
    working_candidate: EntrypointCandidate | None
    exception_type: str | None = None
    exception_message: str | None = None
    traceback: str | None = None
    recovery_suggestion: str | None = None
    attempts: list[dict] = field(default_factory=list)


def initialize(workspace: Path, candidates: list[EntrypointCandidate], smoke_scenario: Scenario,
               sandbox_db_path: Path, env: dict[str, str]) -> InitResult:
    if not candidates:
        return InitResult(
            success=False, working_candidate=None,
            exception_type="EntrypointUnreachable", exception_message="No candidate decision function was found.",
            recovery_suggestion="Expose a top-level function (or class method) that takes business data "
                                 "(inventory/demand/supplier/sku) and returns a structured decision dict.",
        )

    attempts = []
    for candidate in candidates[:5]:
        result = execute_scenario(workspace, [candidate], smoke_scenario, sandbox_db_path, env)
        attempts.append({
            "candidate": f"{candidate.class_name + '.' if candidate.class_name else ''}{candidate.function_name}",
            "exception": result["exception"],
        })
        if not result["exception"]:
            return InitResult(success=True, working_candidate=candidate, attempts=attempts)

    last_exc = attempts[-1]["exception"] if attempts else {}
    exc_type = last_exc.get("type")
    exc_message = last_exc.get("message")
    return InitResult(
        success=False, working_candidate=None,
        exception_type=exc_type, exception_message=exc_message, traceback=last_exc.get("traceback"),
        recovery_suggestion=recovery_advisor.suggest(exc_type, exc_message),
        attempts=attempts,
    )
