"""Maps each rule_id to a concrete, actionable fix. Deterministic: same finding -> same recommendation text."""
import hashlib

from .rule_engine_v2 import RawFinding
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
    "SPEC_NO_IO_CONTRACT": dict(
        title="Document the input/output contract",
        recommendation="Add a docstring, type hints, or comments describing what the agent expects as input and what it outputs. Include field names, types, and valid ranges where relevant.",
        impact="Specification Completeness",
    ),
    "LLM_FRAGILE_JSON_PARSING": dict(
        title="Wrap LLM JSON parsing in error handling and validation",
        recommendation="Replace string slicing with try/except around json.loads(). Better: use a JSON decoder that returns error details on malformed input. Consider using regex to extract JSON more robustly.",
        impact="AI/LLM Risk Controls",
    ),
    "LLM_NO_OUTPUT_VALIDATION": dict(
        title="Add bounds checking / clamping for LLM-generated values",
        recommendation="If LLM generates numeric values (multiplier, quantity, price), clamp them to valid ranges. E.g., demand_multiplier = max(0.5, min(2.0, llm_multiplier)). Log any clamping action.",
        impact="AI/LLM Risk Controls",
    ),
    "LLM_NO_ERROR_HANDLING": dict(
        title="Add try/except around LLM API calls",
        recommendation="Wrap the LLM client call (client.messages.create, etc.) in a try/except block. On exception, log the error and return a fallback decision or raise with a clear message.",
        impact="AI/LLM Risk Controls",
    ),
    "LLM_NO_TIMEOUT": dict(
        title="Set explicit timeout on LLM API calls",
        recommendation="Pass a timeout parameter (e.g., timeout=30) to the LLM API call. If the API doesn't respond within the timeout, catch the exception and fall back to a default decision.",
        impact="AI/LLM Risk Controls",
    ),
    "LLM_NO_RETRY_FALLBACK": dict(
        title="Add retry logic or fallback for LLM failures",
        recommendation="Implement retry with exponential backoff (e.g., tenacity library) or a fallback path. Example: on LLM failure, use mock/deterministic demand multiplier instead of failing.",
        impact="AI/LLM Risk Controls",
    ),
    "REL_NO_ERROR_HANDLING": dict(
        title="Add try/except around database and file I/O",
        recommendation="Wrap db.connect(), file operations, and external API calls in try/except blocks. Log errors and provide a safe fallback (e.g., return a conservative order recommendation).",
        impact="Reliability & Error Handling",
    ),
    "REL_NO_DB_CLOSE": dict(
        title="Explicitly close database connections or use context manager",
        recommendation="Replace conn = db.connect(); ... conn.close() or use 'with' statement: with db.connect() as conn: ... This prevents resource leaks.",
        impact="Reliability & Error Handling",
    ),
    "SCM_NO_SUPPLIER_ELIGIBILITY": dict(
        title="Validate product-supplier compatibility before ordering",
        recommendation="Before selecting a supplier, check that they stock the product/SKU. Add a 'can_supply' flag or similar, or filter eligible suppliers before scoring.",
        impact="SCM Logic Quality",
    ),
    "OBS_NO_LOGGING": dict(
        title="Add structured logging of decisions and reasoning",
        recommendation="Use Python logging module to record: inputs, intermediate calculations, LLM output, decision made, and any fallbacks. At minimum, log at INFO level when an order is recommended.",
        impact="Observability / Traceability",
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
