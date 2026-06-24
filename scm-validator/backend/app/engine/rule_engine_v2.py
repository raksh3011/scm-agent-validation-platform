"""Deterministic rule checks over RepoFacts.

Version 2: Focused on LLM-specific risks, SCM logic, and real operational concerns.
Avoids generic lint in favor of business-critical checks.

Performance: rules read from already-cached file content (RepoFacts.corpus_lower
and FileFact.content). No rule re-reads files from disk, so a repo with hundreds
of files is scanned in roughly O(total bytes), not O(rules x files).
"""
import re
from dataclasses import dataclass, field
from .static_analyzer import RepoFacts, FileFact


@dataclass
class RawFinding:
    rule_id: str
    severity: str          # Critical | High | Medium | Low
    category: str          # maps to a scoring dimension
    title: str
    description: str
    why_it_matters: str
    score_impact: float
    evidence: list[dict] = field(default_factory=list)


SEVERITY_DEFAULT_IMPACT = {"Critical": 25, "High": 15, "Medium": 8, "Low": 3}

# Compiled once. Detect a live LLM API call (Anthropic / OpenAI styles).
LLM_CALL_RE = re.compile(r"client\.messages\.create|chatcompletion\.create|openai\.chat\.completions|\.chat\.completions\.create")


def _f(rule_id, severity, category, title, description, why, impact=None, evidence=None):
    return RawFinding(
        rule_id=rule_id, severity=severity, category=category, title=title,
        description=description, why_it_matters=why,
        score_impact=impact if impact is not None else SEVERITY_DEFAULT_IMPACT[severity],
        evidence=evidence or [],
    )


def _py_files(facts: RepoFacts) -> list[FileFact]:
    return [f for f in facts.files if f.ext == ".py"]


# ---- Specification & Contract ----

def check_missing_io_contract(facts: RepoFacts) -> list[RawFinding]:
    """Missing explicit input/output contract (docstring, comment, or schema)."""
    content = facts.corpus_lower
    has_io_doc = bool(re.search(r"(input|output|returns|args:|param:|:return)", content))
    has_schema = bool(re.search(r"(pydantic|basemodel|dataclass|typeddict|interface)", content))
    if has_io_doc or has_schema:
        return []
    return [_f(
        "SPEC_NO_IO_CONTRACT", "Medium", "Specification Completeness",
        "No explicit input/output contract documented",
        "The agent's interface (what it takes in, what it outputs) is not documented via docstrings, comments, or type hints.",
        "Integrators cannot understand data format expectations without reading all code or trial-and-error.",
        evidence=[{"file_path": "<repo>", "reason": "no I/O documentation found"}],
    )]


def check_missing_dependency_manifest(facts: RepoFacts) -> list[RawFinding]:
    if facts.dependency_files:
        return []
    return [_f(
        "SPEC_NO_DEPENDENCY_FILE", "Medium", "Specification Completeness",
        "No dependency manifest (requirements.txt, pyproject.toml, package.json)",
        "The project dependencies are not listed in a standard format.",
        "Reproducibility and environment setup become manual and error-prone.",
        evidence=[{"file_path": "<repo root>", "reason": "no recognized dependency file present"}],
    )]


def check_missing_readme(facts: RepoFacts) -> list[RawFinding]:
    if facts.has_readme:
        return []
    return [_f(
        "SPEC_NO_README", "Low", "Specification Completeness",
        "No README describing agent purpose and usage",
        "There is no README.md or equivalent explaining what the agent does and how to use it.",
        "Reviewers have to read code to understand the agent's scope and assumptions.",
        evidence=[{"file_path": "<repo root>", "reason": "no readme.* file detected"}],
    )]


# ---- LLM / AI Risk Controls ----

def check_llm_json_parsing_fragility(facts: RepoFacts) -> list[RawFinding]:
    """LLM JSON parsing without error handling or validation."""
    content = facts.corpus_lower
    # Anti-pattern: extract JSON via string slicing then json.loads, not wrapped in try.
    if re.search(r"\.find\([^)]*\)[^\n]*\.rfind\(", content) and "json.loads" in content:
        if not re.search(r"try\s*:[\s\S]{0,400}json\.loads", content):
            return [_f(
                "LLM_FRAGILE_JSON_PARSING", "High", "AI/LLM Risk Controls",
                "Fragile LLM JSON parsing without error handling",
                "The agent extracts JSON from LLM output using string slicing (e.g., find/rfind) without try/except. If LLM output format changes, parsing fails or crashes.",
                "LLM output format is unpredictable. Agents relying on fragile parsing make supply chain decisions on malformed data.",
                evidence=[{"file_path": "<repo>", "reason": "string slicing + json.loads without try/except detected"}],
            )]
    return []


def check_llm_output_validation(facts: RepoFacts) -> list[RawFinding]:
    """LLM-generated numeric outputs not validated / clamped."""
    content = facts.corpus_lower
    if re.search(r"(multiplier|factor|adjustment)[\s\S]{0,200}json[\s\S]{0,40}loads", content):
        has_bounds = bool(re.search(r"(min\(|max\(|clamp|bound|np\.clip)", content))
        if not has_bounds:
            return [_f(
                "LLM_NO_OUTPUT_VALIDATION", "High", "AI/LLM Risk Controls",
                "LLM-generated numeric values not validated or clamped",
                "The agent uses numeric values from LLM output (e.g., demand multiplier) without bounds checking. The LLM could return 0, negative, or unrealistic values.",
                "Unclamped multipliers can cause demand forecasts or order quantities to become 0, negative, or astronomical.",
                evidence=[{"file_path": "<repo>", "reason": "LLM numeric values used without bounds checking"}],
            )]
    return []


def check_llm_call_error_handling(facts: RepoFacts) -> list[RawFinding]:
    """LLM API call not wrapped in try/except (reported per file with a line number)."""
    findings = []
    for f in _py_files(facts):
        content = f.content
        if not LLM_CALL_RE.search(content.lower()):
            continue
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if LLM_CALL_RE.search(line.lower()):
                has_try = any("try:" in lines[j] for j in range(max(0, i - 12), i))
                has_except = any("except" in lines[j] for j in range(i, min(len(lines), i + 12)))
                if not (has_try and has_except):
                    findings.append(_f(
                        "LLM_NO_ERROR_HANDLING", "High", "AI/LLM Risk Controls",
                        "LLM API call not wrapped in try/except",
                        f"{f.rel_path} (~line {i + 1}): LLM call (Anthropic/OpenAI) is not protected by error handling.",
                        "Network failures, API rate limits, or service outages will crash the agent or hang indefinitely.",
                        evidence=[{"file_path": f.rel_path, "line_start": i + 1, "snippet": line.strip()[:160], "reason": "LLM call without try/except"}],
                    ))
                break
    return findings


def check_llm_call_timeout(facts: RepoFacts) -> list[RawFinding]:
    """LLM API call has no explicit timeout, checked in the file that makes the call."""
    for f in _py_files(facts):
        content_l = f.content.lower()
        if LLM_CALL_RE.search(content_l) and "timeout" not in content_l:
            return [_f(
                "LLM_NO_TIMEOUT", "Medium", "AI/LLM Risk Controls",
                "LLM API call has no explicit timeout",
                f"{f.rel_path}: the LLM API call does not specify a timeout value.",
                "If the API service is slow or unresponsive, the agent will hang and block supply chain operations.",
                evidence=[{"file_path": f.rel_path, "reason": "LLM call without timeout parameter in this file"}],
            )]
    return []


def check_llm_call_retry(facts: RepoFacts) -> list[RawFinding]:
    """LLM API call has no retry / fallback logic, checked in the file that makes the call."""
    for f in _py_files(facts):
        content_l = f.content.lower()
        if not LLM_CALL_RE.search(content_l):
            continue
        has_retry = bool(re.search(r"(retry|tenacity|backoff)", content_l))
        has_fallback = bool(re.search(r"except[\s\S]{0,160}(return|fallback|default)", content_l))
        if not (has_retry or has_fallback):
            return [_f(
                "LLM_NO_RETRY_FALLBACK", "Medium", "AI/LLM Risk Controls",
                "LLM API call has no retry or fallback logic",
                f"{f.rel_path}: a transient API failure will fail the agent with no recovery strategy.",
                "A single transient network glitch or API hiccup blocks supply chain reorder decisions.",
                evidence=[{"file_path": f.rel_path, "reason": "no retry or fallback detected in this file's LLM path"}],
            )]
    return []


# ---- Reliability / Error Handling ----

def check_no_error_handling_critical_paths(facts: RepoFacts) -> list[RawFinding]:
    """Code paths that could fail (DB reads, file I/O) not protected anywhere."""
    code_files = _py_files(facts)
    if not code_files:
        return []
    if not any(f.has_try_except for f in code_files):
        return [_f(
            "REL_NO_ERROR_HANDLING", "Medium", "Reliability & Error Handling",
            "No error handling around database or file I/O",
            "Database reads, file operations, or external calls are not wrapped in try/except anywhere in the analyzed code.",
            "A corrupt database, missing file, or network error will crash the agent.",
            evidence=[{"file_path": f.rel_path, "reason": "no try/except found"} for f in code_files[:2]],
        )]
    return []


def check_database_connection_not_closed(facts: RepoFacts) -> list[RawFinding]:
    """Database connections opened but no explicit close or context manager."""
    content = facts.corpus_lower
    if re.search(r"(sqlite3?\.connect|psycopg|pymongo|\.connect\()", content):
        if not (".close()" in content or re.search(r"with[^\n]*connect", content)):
            return [_f(
                "REL_NO_DB_CLOSE", "Low", "Reliability & Error Handling",
                "Database connection not explicitly closed",
                "A database connection is opened but not closed in a finally block or context manager.",
                "Resource leaks can accumulate if the agent runs repeatedly, exhausting database connections.",
                evidence=[{"file_path": "<repo>", "reason": "connect() without .close() or with-statement"}],
            )]
    return []


# ---- SCM Logic Quality ----

def check_supplier_selection_too_generic(facts: RepoFacts) -> list[RawFinding]:
    """Supplier selection doesn't check product-supplier compatibility."""
    content = facts.corpus_lower
    if re.search(r"(choose|select|pick)[\s\S]{0,40}supplier", content):
        has_eligibility = bool(re.search(r"(sku|product[_\s]?id|eligib|compat|can[_\s]?supply)", content))
        if not has_eligibility:
            return [_f(
                "SCM_NO_SUPPLIER_ELIGIBILITY", "Medium", "SCM Logic Quality",
                "Supplier selection doesn't validate product-supplier compatibility",
                "The agent picks suppliers without checking whether they supply the specific product/SKU.",
                "The agent could place orders with suppliers that don't stock that product.",
                evidence=[{"file_path": "<repo>", "reason": "supplier selection lacks SKU/product eligibility check"}],
            )]
    return []


# ---- Observability ----

def check_no_logging(facts: RepoFacts) -> list[RawFinding]:
    """No structured logging of decisions for an audit trail."""
    code_files = _py_files(facts)
    if not code_files:
        return []
    if not any(f.has_logging for f in code_files):
        return [_f(
            "OBS_NO_LOGGING", "Medium", "Observability / Traceability",
            "No logging of decisions for audit trail",
            "The agent does not log decisions, inputs, or reasoning for post-hoc audit.",
            "If a bad reorder decision is made, there's no trace of what the agent saw or decided.",
            evidence=[{"file_path": f.rel_path, "reason": "no logging/print detected"} for f in code_files[:2]],
        )]
    return []


ALL_RULES = [
    check_missing_io_contract,
    check_missing_dependency_manifest,
    check_missing_readme,
    check_llm_json_parsing_fragility,
    check_llm_output_validation,
    check_llm_call_error_handling,
    check_llm_call_timeout,
    check_llm_call_retry,
    check_no_error_handling_critical_paths,
    check_database_connection_not_closed,
    check_supplier_selection_too_generic,
    check_no_logging,
]


def run_all_rules(facts: RepoFacts, context: dict) -> list[RawFinding]:
    """Rules run in a fixed order; output is sorted by rule_id for determinism."""
    findings: list[RawFinding] = []
    for rule in ALL_RULES:
        findings.extend(rule(facts))
    findings.sort(key=lambda r: r.rule_id)
    return findings
