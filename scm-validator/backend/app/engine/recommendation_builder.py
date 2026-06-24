"""Maps each rule_id to a concrete, actionable fix. Deterministic: same finding -> same recommendation text."""
import hashlib

from .rule_engine import RawFinding
from ..report_schema import Recommendation

SEVERITY_TO_PRIORITY = {"Critical": "Immediate", "High": "High", "Medium": "Medium", "Low": "Low"}

FIX_LIBRARY: dict[str, dict] = {
    "SPEC_NO_README": dict(
        title="Add a README describing purpose, inputs, and outputs",
        recommendation="Create a README.md that states the agent's SCM purpose, exact input schema, exact output schema, external dependencies, and known assumptions/limitations.",
        impact="Specification Completeness",
    ),
    "SPEC_NO_DEPENDENCY_FILE": dict(
        title="Add a dependency manifest",
        recommendation="Add a requirements.txt (or pyproject.toml/package.json) pinning the exact libraries and versions the agent needs to run.",
        impact="Specification Completeness",
    ),
    "SPEC_NO_USE_CASE": dict(
        title="Declare the SCM use case explicitly",
        recommendation="Provide a one-paragraph use case statement at submission time (or in the README) naming the SCM process this agent supports, e.g. 'inventory reorder recommendation for retail SKUs'.",
        impact="Specification Completeness",
    ),
    "IMPL_NO_ENTRYPOINT": dict(
        title="Add a clear entrypoint file",
        recommendation="Add a main.py / app.py / run.py that is the single documented place execution starts, and reference it in the README.",
        impact="Implementation Hygiene",
    ),
    "IMPL_SYNTAX_ERROR": dict(
        title="Fix the syntax error before resubmitting",
        recommendation="Run the file through a Python interpreter or linter locally and resolve the reported syntax error; this file cannot be evaluated further until it parses.",
        impact="Implementation Hygiene",
    ),
    "IMPL_EMPTY_FILE": dict(
        title="Remove or populate the empty file",
        recommendation="Either implement the intended contents of this file or remove it from the submission to avoid confusion about unfinished functionality.",
        impact="Implementation Hygiene",
    ),
    "REL_NO_ERROR_HANDLING": dict(
        title="Add error handling around external calls and decision logic",
        recommendation="Wrap external API calls, file/DB I/O, and any decision-critical computation in try/except blocks that log the failure and fail safely (e.g. fall back to a conservative default decision) rather than crashing.",
        impact="Reliability & Error Handling",
    ),
    "REL_NO_RETRY_TIMEOUT": dict(
        title="Add retry/backoff and explicit timeouts for external calls",
        recommendation="Use a retry library (e.g. tenacity) with exponential backoff and set explicit timeout values on all network/API calls so the agent degrades gracefully instead of hanging.",
        impact="Reliability & Error Handling",
    ),
    "SEC_HARDCODED_SECRET": dict(
        title="Remove hardcoded credential and rotate it",
        recommendation="Remove the secret from source code, rotate/revoke the exposed credential immediately, and load it via environment variables or a secrets manager instead.",
        impact="Security Hygiene",
    ),
    "SEC_NO_ENV_TEMPLATE": dict(
        title="Add a .env.example template",
        recommendation="Add a .env.example listing required environment variable names (without real values) so secrets are externalized by convention rather than hardcoded.",
        impact="Security Hygiene",
    ),
    "IO_NO_SCHEMA": dict(
        title="Define explicit input/output schemas",
        recommendation="Add Pydantic models (Python) or TypedDicts/interfaces (TS) describing exact input and output fields, types, and required/optional status, and validate against them at the agent boundary.",
        impact="Input / Output Contract Clarity",
    ),
    "OBS_NO_LOGGING": dict(
        title="Add structured logging at key decision points",
        recommendation="Use the logging module to record, at minimum: inputs received, the decision made, the reasoning/rule that drove it, and any errors -- at INFO level or above.",
        impact="Observability / Traceability",
    ),
    "SCM_NO_RELEVANCE_SIGNAL": dict(
        title="Clarify the SCM domain mapping",
        recommendation="In the README or code comments, explicitly name the SCM entities the agent operates on (e.g. SKU, supplier, lead time, reorder point) so domain relevance is unambiguous to reviewers.",
        impact="SCM Readiness / Business Fit",
    ),
}

DEFAULT_FIX = dict(
    title="Address the identified issue",
    recommendation="Review the finding description and resolve the underlying gap before resubmission.",
    impact="General",
)


def _rec_id(run_id: str, idx: int) -> str:
    return f"rec_{hashlib.sha1(f'{run_id}:{idx}'.encode()).hexdigest()[:10]}"


def build_recommendations(run_id: str, findings: list[RawFinding], finding_ids: list[str]) -> list[Recommendation]:
    """finding_ids is index-aligned with findings (assigned by the pipeline)."""
    recs = []
    for idx, (finding, finding_id) in enumerate(zip(findings, finding_ids)):
        fix = FIX_LIBRARY.get(finding.rule_id, DEFAULT_FIX)
        recs.append(Recommendation(
            id=_rec_id(run_id, idx),
            finding_id=finding_id,
            title=fix["title"],
            recommendation=fix["recommendation"],
            priority=SEVERITY_TO_PRIORITY.get(finding.severity, "Medium"),
            expected_impact=f"Improves '{fix['impact']}' score; resolves a {finding.severity.lower()}-severity finding.",
        ))
    return recs
