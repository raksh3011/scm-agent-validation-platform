"""Clusters crashed/unreachable scenario executions into one RootCause per distinct
failure signature, instead of reporting the same exception hundreds of times."""
import re
import uuid

from ..core.models import RootCause, ScenarioExecutionResult
from ..runtime import recovery_advisor

_NUMERIC_RE = re.compile(r"\d+")
_PATH_RE = re.compile(r"[A-Za-z]:\\[^\s\"']+|/[^\s\"']+")


def _normalize(message: str) -> str:
    msg = _PATH_RE.sub("<path>", message or "")
    msg = _NUMERIC_RE.sub("#", msg)
    return msg.strip()


def correlate(results: list[ScenarioExecutionResult]) -> list[RootCause]:
    groups: dict[tuple[str, str], list[ScenarioExecutionResult]] = {}
    tracebacks: dict[tuple[str, str], str] = {}

    for r in results:
        if r.execution_state not in ("crashed", "unreachable"):
            continue
        exc = (r.actual_behaviour or {}).get("exception") if isinstance(r.actual_behaviour, dict) else None
        exc_type = (exc or {}).get("type") or "Unknown"
        message = (exc or {}).get("message") or r.error or r.business_explanation or ""
        key = (exc_type, _normalize(message))
        groups.setdefault(key, []).append(r)
        if key not in tracebacks and exc and exc.get("traceback"):
            tracebacks[key] = exc["traceback"]

    total = len(results) or 1
    causes = []
    for (exc_type, norm_message), affected in groups.items():
        causes.append(RootCause(
            id=uuid.uuid4().hex[:10],
            exception_type=exc_type,
            normalized_message=norm_message,
            confidence=round(min(0.99, len(affected) / total + 0.3), 2),
            recovery_suggestion=recovery_advisor.suggest(exc_type, norm_message),
            affected_scenario_ids=[r.scenario.id for r in affected],
            affected_count=len(affected),
            representative_traceback=tracebacks.get((exc_type, norm_message), ""),
        ))
    causes.sort(key=lambda c: c.affected_count, reverse=True)
    return causes
