"""Drives every scenario in a catalogue through the runtime execution adapter and
collects raw outcomes + evidence. Business pass/fail judgement happens one stage
later in validation.decision_validator — this stage only answers 'what happened'."""
from dataclasses import dataclass
from pathlib import Path

from ..core.models import Evidence, Scenario
from ..runtime.entrypoint_discovery import EntrypointCandidate
from ..runtime.execution_adapter import execute_scenario


@dataclass
class RawExecutionOutcome:
    scenario: Scenario
    candidate: str | None
    return_value: dict | None
    exception: dict | None
    db_diff: dict
    runtime_ms: float
    evidence: list[Evidence]


def run_suite(workspace: Path, candidates: list[EntrypointCandidate], scenarios: list[Scenario],
              sandbox_db_path: Path, env: dict[str, str], on_progress=None) -> list[RawExecutionOutcome]:
    outcomes = []
    total = len(scenarios)
    for i, scenario in enumerate(scenarios):
        result = execute_scenario(workspace, candidates, scenario, sandbox_db_path, env)
        outcomes.append(RawExecutionOutcome(
            scenario=scenario,
            candidate=result["candidate"],
            return_value=result["return_value"],
            exception=result["exception"],
            db_diff=result["db_diff"],
            runtime_ms=result["runtime_ms"],
            evidence=result["evidence"],
        ))
        if on_progress and (i % 5 == 0 or i == total - 1):
            on_progress(i + 1, total)
    return outcomes
