"""Deterministic rule checks over RepoFacts.

Version 2: Focused on LLM-specific risks, SCM logic, and real operational concerns.
Avoids generic lint in favor of business-critical checks.
"""
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


def _f(rule_id, severity, category, title, description, why, impact=None, evidence=None):
    return RawFinding(
        rule_id=rule_id, severity=severity, category=category, title=title,
        description=description, why_it_matters=why,
        score_impact=impact if impact is not None else SEVERITY_DEFAULT_IMPACT[severity],
        evidence=evidence or [],
    )


# ---- Specification & Contract ----

def check_missing_io_contract(facts: RepoFacts) -> list[RawFinding]:
    """Missing explicit input/output contract (docstring, comment, or schema)."""
    content = ""
    for f in facts.files:
        try:
            path = facts.root / f.rel_path
            content += path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass

    # Look for documented I/O
    import re
    has_io_doc = bool(re.search(r"(input|output|returns|args:|param:|Returns:)", content, re.IGNORECASE))
    has_schema = bool(re.search(r"(pydantic|BaseModel|dataclass|TypedDict|interface)", content, re.IGNORECASE))

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
    findings = []
    content = ""
    for f in facts.files:
        try:
            path = facts.root / f.rel_path
            content += path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass

    import re
    # Pattern: string slicing + json.loads without try/except
    # Typical anti-pattern: txt[txt.find("{"):txt.rfind("}")+1]  then json.loads(...)
    if re.search(r'\.find\(.*\).*\.rfind\(.*\)', content) and re.search(r'json\.loads', content):
        # Check if it's protected by try/except
        if not re.search(r'try.*json\.loads', content, re.DOTALL):
            findings.append(_f(
                "LLM_FRAGILE_JSON_PARSING", "High", "AI/LLM Risk Controls",
                "Fragile LLM JSON parsing without error handling",
                "The agent extracts JSON from LLM output using string slicing (e.g., find/rfind) without try/except. If LLM output format changes, parsing fails silently or crashes.",
                "LLM output format is unpredictable. Agents relying on fragile parsing make supply chain decisions on malformed data.",
                evidence=[{"file_path": "<repo>", "reason": "string slicing + json.loads without try/except detected"}],
            ))

    return findings


def check_llm_output_validation(facts: RepoFacts) -> list[RawFinding]:
    """LLM-generated numeric outputs not validated / clamped."""
    findings = []
    content = ""
    for f in facts.files:
        try:
            path = facts.root / f.rel_path
            content += path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass

    import re
    # Look for "multiplier" or "factor" from LLM not being clamped
    if re.search(r'(multiplier|factor|adjustment).*json.*loads', content, re.IGNORECASE):
        # Check for clamping / validation
        has_min_max = bool(re.search(r'(min|max|clamp|bound|range|0.*1|1\.0)', content))
        if not has_min_max:
            findings.append(_f(
                "LLM_NO_OUTPUT_VALIDATION", "High", "AI/LLM Risk Controls",
                "LLM-generated numeric values not validated or clamped",
                "The agent uses numeric values from LLM output (e.g., demand multiplier) without bounds checking. LLM could return 0, negative, or unrealistic values.",
                "Unclamped multipliers can cause demand forecasts or order quantities to become 0, negative, or astronomical.",
                evidence=[{"file_path": "<repo>", "reason": "LLM numeric values (multiplier/factor) used without bounds checking"}],
            ))

    return findings


def check_llm_call_error_handling(facts: RepoFacts) -> list[RawFinding]:
    """LLM API call not wrapped in try/except."""
    findings = []
    code_files = [f for f in facts.files if f.ext == ".py"]

    for f in code_files:
        try:
            path = facts.root / f.rel_path
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        import re
        # Look for client.messages.create / openai.ChatCompletion.create without try/except
        if re.search(r'(client\.messages\.create|ChatCompletion\.create|openai\.chat\.completions)', content):
            # Check if surrounded by try/except
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if re.search(r'(client\.messages\.create|ChatCompletion\.create|openai\.chat\.completions)', line):
                    # Look backwards for try, forwards for except
                    has_try = any('try:' in lines[j] for j in range(max(0, i-10), i))
                    has_except = any('except' in lines[j] for j in range(i, min(len(lines), i+10)))
                    if not (has_try and has_except):
                        findings.append(_f(
                            "LLM_NO_ERROR_HANDLING", "High", "AI/LLM Risk Controls",
                            "LLM API call not wrapped in try/except",
                            f"Line ~{i+1}: LLM call (Anthropic/OpenAI) is not protected by error handling.",
                            "Network failures, API rate limits, or service outages will crash the agent or hang indefinitely.",
                            evidence=[{"file_path": f.rel_path, "line_start": i+1, "reason": "LLM call without try/except"}],
                        ))
                        break  # One finding per file is enough

    return findings


def check_llm_call_timeout(facts: RepoFacts) -> list[RawFinding]:
    """LLM API call has no explicit timeout."""
    findings = []
    code_files = [f for f in facts.files if f.ext == ".py"]

    for f in code_files:
        try:
            path = facts.root / f.rel_path
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        import re
        if re.search(r'(client\.messages\.create|ChatCompletion\.create|openai\.chat\.completions)', content):
            # Check for timeout parameter
            if not re.search(r'timeout', content):
                findings.append(_f(
                    "LLM_NO_TIMEOUT", "Medium", "AI/LLM Risk Controls",
                    "LLM API call has no explicit timeout",
                    "The LLM API call does not specify a timeout value.",
                    "If the API service is slow or unresponsive, the agent will hang and block supply chain operations.",
                    evidence=[{"file_path": f.rel_path, "reason": "LLM call without timeout parameter"}],
                ))
                break

    return findings


def check_llm_call_retry(facts: RepoFacts) -> list[RawFinding]:
    """LLM API call has no retry / fallback logic."""
    findings = []
    content = ""
    for f in facts.files:
        try:
            path = facts.root / f.rel_path
            content += path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass

    import re
    if re.search(r'(client\.messages\.create|ChatCompletion\.create|openai\.chat\.completions)', content):
        # Check for retry/fallback
        has_retry = bool(re.search(r'(retry|tenacity|backoff|for.*in.*range.*try)', content, re.IGNORECASE))
        has_fallback = bool(re.search(r'(except.*:.*return|fallback|default)', content, re.IGNORECASE))

        if not (has_retry or has_fallback):
            findings.append(_f(
                "LLM_NO_RETRY_FALLBACK", "Medium", "AI/LLM Risk Controls",
                "LLM API call has no retry or fallback logic",
                "A transient API failure will cause the agent to fail completely with no recovery strategy.",
                "Single transient network glitch or API hiccup blocks supply chain reorder decisions.",
                evidence=[{"file_path": "<repo>", "reason": "no retry or fallback detected around LLM call"}],
            ))

    return findings


# ---- Reliability / Error Handling ----

def check_no_error_handling_critical_paths(facts: RepoFacts) -> list[RawFinding]:
    """Code paths that could fail (DB reads, file I/O) not protected."""
    findings = []
    code_files = [f for f in facts.files if f.ext == ".py"]

    if not code_files:
        return []

    # If no files have try/except at all, flag it
    if not any(f.has_try_except for f in code_files):
        findings.append(_f(
            "REL_NO_ERROR_HANDLING", "Medium", "Reliability & Error Handling",
            "No error handling around database or file I/O",
            "Database reads, file operations, or external calls are not wrapped in try/except.",
            "A corrupt database, missing file, or network error will crash the agent.",
            evidence=[{"file_path": f.rel_path, "reason": "no try/except found"} for f in code_files[:2]],
        ))

    return findings


def check_database_connection_not_closed(facts: RepoFacts) -> list[RawFinding]:
    """Database connections opened but no explicit close or context manager."""
    findings = []
    content = ""
    for f in facts.files:
        try:
            path = facts.root / f.rel_path
            content += path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass

    import re
    if re.search(r'(sqlite\.connect|psycopg|pymongo|\.connect\()', content):
        # Check for close or context manager
        has_close = bool(re.search(r'\.close\(\)', content))
        has_with = bool(re.search(r'with.*as.*:', content))

        if not (has_close or has_with):
            findings.append(_f(
                "REL_NO_DB_CLOSE", "Low", "Reliability & Error Handling",
                "Database connection not explicitly closed",
                "Database connection is opened but not closed in a finally block or context manager.",
                "Resource leaks can accumulate if the agent runs repeatedly, exhausting database connections.",
                evidence=[{"file_path": "<repo>", "reason": "db.connect() without .close() or with statement"}],
            ))

    return findings


# ---- SCM Logic Quality ----

def check_scm_logic_quality(facts: RepoFacts) -> list[RawFinding]:
    """SCM logic is implemented correctly (no obvious flaws)."""
    # Positive check: if ROP logic is present, don't flag it
    # We'll rely on positive_signals to highlight strengths
    # Here we only flag if SCM patterns are broken or incomplete
    return []


def check_supplier_selection_too_generic(facts: RepoFacts) -> list[RawFinding]:
    """Supplier selection doesn't check product-supplier compatibility."""
    findings = []
    content = ""
    for f in facts.files:
        try:
            path = facts.root / f.rel_path
            content += path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass

    import re
    # Look for supplier selection
    if re.search(r'(choose|select|pick).*supplier', content, re.IGNORECASE):
        # Check if it validates product-supplier compatibility
        has_sku_check = bool(re.search(r'(sku|product.*id|eligib|compat)', content, re.IGNORECASE))
        if not has_sku_check:
            findings.append(_f(
                "SCM_NO_SUPPLIER_ELIGIBILITY", "Medium", "SCM Logic Quality",
                "Supplier selection doesn't validate product-supplier compatibility",
                "The agent picks suppliers without checking if they supply the specific product/SKU.",
                "Agent could place orders with suppliers that don't stock that product.",
                evidence=[{"file_path": "<repo>", "reason": "supplier selection logic lacks SKU/product eligibility check"}],
            ))

    return findings


# ---- Observability ----

def check_no_logging(facts: RepoFacts) -> list[RawFinding]:
    """No structured logging of decisions for audit trail."""
    code_files = [f for f in facts.files if f.ext == ".py"]
    if not code_files:
        return []

    if not any(f.has_logging for f in code_files):
        return [_f(
            "OBS_NO_LOGGING", "Medium", "Observability / Traceability",
            "No logging of decisions for audit trail",
            "The agent does not log decisions, inputs, or reasoning for post-hoc audit.",
            "If a bad reorder decision is made, there's no trace of what the agent saw or decided.",
            evidence=[{"file_path": f.rel_path, "reason": "no logging/logging module detected"} for f in code_files[:2]],
        )]

    return []


# ---- Demo vs Production Readiness ----

def check_demo_ready_signals(facts: RepoFacts) -> list[RawFinding]:
    """Agent can run in mock/demo mode."""
    content = ""
    for f in facts.files:
        try:
            path = facts.root / f.rel_path
            content += path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            pass

    import re
    if re.search(r'(mock|demo|test|recorded)', content, re.IGNORECASE):
        # Demo mode detected as positive signal, not a finding
        return []

    # No demo mode is not critical, just a flag
    return []


ALL_RULES = [
    lambda facts, ctx: check_missing_io_contract(facts),
    lambda facts, ctx: check_missing_dependency_manifest(facts),
    lambda facts, ctx: check_missing_readme(facts),
    lambda facts, ctx: check_llm_json_parsing_fragility(facts),
    lambda facts, ctx: check_llm_output_validation(facts),
    lambda facts, ctx: check_llm_call_error_handling(facts),
    lambda facts, ctx: check_llm_call_timeout(facts),
    lambda facts, ctx: check_llm_call_retry(facts),
    lambda facts, ctx: check_no_error_handling_critical_paths(facts),
    lambda facts, ctx: check_database_connection_not_closed(facts),
    lambda facts, ctx: check_supplier_selection_too_generic(facts),
    lambda facts, ctx: check_no_logging(facts),
    lambda facts, ctx: check_demo_ready_signals(facts),
]


def run_all_rules(facts: RepoFacts, context: dict) -> list[RawFinding]:
    """Rules run in a fixed, sorted order so output ordering is also deterministic."""
    findings: list[RawFinding] = []
    for rule in ALL_RULES:
        findings.extend(rule(facts, context))
    findings.sort(key=lambda r: r.rule_id)
    return findings
