"""Deterministic rule checks over RepoFacts. Every rule is pure: same facts in -> same findings out.

Each rule returns zero or more RawFinding. No LLM calls happen here.
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
    score_impact: float    # positive number, points deducted from that dimension's max
    evidence: list[dict] = field(default_factory=list)  # {file_path, line_start, line_end, snippet, reason}


SEVERITY_DEFAULT_IMPACT = {"Critical": 25, "High": 15, "Medium": 8, "Low": 3}


def _f(rule_id, severity, category, title, description, why, impact=None, evidence=None):
    return RawFinding(
        rule_id=rule_id, severity=severity, category=category, title=title,
        description=description, why_it_matters=why,
        score_impact=impact if impact is not None else SEVERITY_DEFAULT_IMPACT[severity],
        evidence=evidence or [],
    )


# ---- Specification Completeness ----

def check_missing_readme(facts: RepoFacts) -> list[RawFinding]:
    if facts.has_readme:
        return []
    return [_f(
        "SPEC_NO_README", "High", "Specification Completeness",
        "No README or specification document found",
        "The repository does not contain a README (or equivalent) describing the agent's purpose, inputs, outputs, or assumptions.",
        "Without documentation, customers and reviewers cannot verify what the agent is supposed to do, making trust assessment unreliable.",
        evidence=[{"file_path": "<repo root>", "reason": "No readme.* file detected at scan time"}],
    )]


def check_missing_dependency_manifest(facts: RepoFacts) -> list[RawFinding]:
    if facts.dependency_files:
        return []
    return [_f(
        "SPEC_NO_DEPENDENCY_FILE", "Medium", "Specification Completeness",
        "No dependency manifest found",
        "No requirements.txt, pyproject.toml, package.json, or similar dependency file was found.",
        "Without a manifest, the agent's runtime environment cannot be reproduced or audited reliably.",
        evidence=[{"file_path": "<repo root>", "reason": "No recognized dependency file present"}],
    )]


def check_use_case_clarity(facts: RepoFacts, use_case: str | None, description: str | None) -> list[RawFinding]:
    if (use_case and use_case.strip()) or (description and description.strip()):
        return []
    return [_f(
        "SPEC_NO_USE_CASE", "Medium", "Specification Completeness",
        "SCM use case not declared",
        "No use case or description was provided with this submission, and none could be inferred from the README.",
        "Validators and customers need an explicit business purpose to judge whether the agent's behavior is fit for that purpose.",
        evidence=[{"file_path": "<submission metadata>", "reason": "use_case and description fields empty"}],
    )]


# ---- Implementation Hygiene ----

def check_no_entrypoint(facts: RepoFacts) -> list[RawFinding]:
    if facts.entrypoints or facts.total_code_files <= 1:
        return []
    return [_f(
        "IMPL_NO_ENTRYPOINT", "Medium", "Implementation Hygiene",
        "No recognizable entrypoint detected",
        "Multiple code files were found but none match common entrypoint names (main.py, app.py, agent.py, run.py, server.py, index.ts/js).",
        "Reviewers cannot easily identify where execution begins, slowing down validation and increasing integration risk.",
        evidence=[{"file_path": f.rel_path, "reason": "code file present, none matched entrypoint heuristics"} for f in facts.files[:3]],
    )]


def check_parse_errors(facts: RepoFacts) -> list[RawFinding]:
    findings = []
    for f in facts.files:
        if f.parse_error:
            findings.append(_f(
                "IMPL_SYNTAX_ERROR", "Critical", "Implementation Hygiene",
                f"Syntax error in {f.rel_path}",
                f"The file failed to parse: {f.parse_error}",
                "A file that cannot be parsed cannot run, and cannot be statically verified for any other quality dimension.",
                evidence=[{"file_path": f.rel_path, "reason": f.parse_error}],
            ))
    return findings


def check_empty_files(facts: RepoFacts) -> list[RawFinding]:
    findings = []
    for f in facts.files:
        if f.size == 0:
            findings.append(_f(
                "IMPL_EMPTY_FILE", "Low", "Implementation Hygiene",
                f"Empty source file: {f.rel_path}",
                "This source file is empty.",
                "Empty files may indicate incomplete implementation or dead scaffolding left in the submission.",
                evidence=[{"file_path": f.rel_path, "reason": "file size is 0 bytes"}],
            ))
    return findings


# ---- Reliability & Error Handling ----

def check_no_error_handling(facts: RepoFacts) -> list[RawFinding]:
    code_files = [f for f in facts.files if f.ext == ".py"]
    if not code_files:
        return []
    with_try = [f for f in code_files if f.has_try_except]
    if with_try:
        return []
    return [_f(
        "REL_NO_ERROR_HANDLING", "High", "Reliability & Error Handling",
        "No error handling detected across code files",
        "No try/except blocks were found in any analyzed source file.",
        "SCM agents make decisions from external data (supplier APIs, inventory feeds, forecasts). Without error handling, a single bad input or failed call can crash the agent or silently corrupt a decision.",
        evidence=[{"file_path": f.rel_path, "reason": "no try/except found"} for f in code_files[:3]],
    )]


def check_no_retry_or_timeout(facts: RepoFacts) -> list[RawFinding]:
    code_files = [f for f in facts.files if f.ext in {".py", ".js", ".ts"}]
    if not code_files:
        return []
    if any(f.has_retry_pattern or f.has_timeout_pattern for f in code_files):
        return []
    return [_f(
        "REL_NO_RETRY_TIMEOUT", "Medium", "Reliability & Error Handling",
        "No retry, backoff, or timeout pattern detected",
        "No code file shows evidence of retry logic, backoff, or explicit timeouts.",
        "External SCM systems (ERP, supplier portals, logistics APIs) are frequently slow or transiently unavailable. Agents without retry/timeout handling are fragile in production.",
        evidence=[{"file_path": f.rel_path, "reason": "no retry/backoff/timeout keywords found"} for f in code_files[:3]],
    )]


# ---- Security Hygiene ----

def check_hardcoded_secrets(facts: RepoFacts) -> list[RawFinding]:
    findings = []
    for f in facts.files:
        for lineno, line in f.secret_hits:
            findings.append(_f(
                "SEC_HARDCODED_SECRET", "Critical", "Security Hygiene",
                f"Possible hardcoded secret in {f.rel_path}",
                "A pattern resembling a hardcoded API key, token, or password was found in source code.",
                "Hardcoded credentials checked into source are a critical, well-known security risk: they leak via version control, logs, and code sharing.",
                evidence=[{"file_path": f.rel_path, "line_start": lineno, "line_end": lineno, "snippet": line, "reason": "matched secret-like pattern"}],
            ))
    return findings


def check_no_env_example(facts: RepoFacts) -> list[RawFinding]:
    if any("env" in c.lower() for c in facts.config_files) or not facts.dependency_files:
        return []
    return [_f(
        "SEC_NO_ENV_TEMPLATE", "Low", "Security Hygiene",
        "No .env.example or config template found",
        "No environment/config template file was found alongside a dependency manifest.",
        "Without a template, secrets are more likely to be hardcoded directly into source rather than externalized.",
        evidence=[{"file_path": "<repo root>", "reason": "no .env.example or config template detected"}],
    )]


# ---- Input / Output Contract Clarity ----

def check_no_schema_hints(facts: RepoFacts) -> list[RawFinding]:
    code_files = [f for f in facts.files if f.ext in {".py", ".ts", ".tsx"}]
    if not code_files:
        return []
    if any(f.has_schema_hint for f in code_files):
        return []
    return [_f(
        "IO_NO_SCHEMA", "High", "Input / Output Contract Clarity",
        "No structured input/output schema detected",
        "No Pydantic models, dataclasses, TypedDicts, or equivalent schema constructs were found defining the agent's inputs or outputs.",
        "Without an explicit contract, downstream SCM systems integrating with this agent cannot validate data going in or out, increasing integration risk and silent failures.",
        evidence=[{"file_path": f.rel_path, "reason": "no schema/type construct detected"} for f in code_files[:3]],
    )]


# ---- Observability / Traceability ----

def check_no_logging(facts: RepoFacts) -> list[RawFinding]:
    code_files = [f for f in facts.files if f.ext in {".py", ".js", ".ts"}]
    if not code_files:
        return []
    if any(f.has_logging for f in code_files):
        return []
    return [_f(
        "OBS_NO_LOGGING", "High", "Observability / Traceability",
        "No logging detected anywhere in the agent",
        "No logging or print-based tracing statements were found in any code file.",
        "Without logs, there is no way to audit what decision the agent made, when, or why -- a baseline requirement for trusting an autonomous SCM decision.",
        evidence=[{"file_path": f.rel_path, "reason": "no logging/print statements found"} for f in code_files[:3]],
    )]


# ---- SCM Readiness / Business Fit ----

SCM_KEYWORDS = [
    "inventory", "supplier", "procurement", "forecast", "demand", "reorder",
    "lead time", "leadtime", "logistics", "shipment", "warehouse", "stock",
    "purchase order", "moq", "sku", "replenish",
]


def check_scm_relevance(facts: RepoFacts) -> list[RawFinding]:
    haystack = (facts.readme_excerpt or "").lower()
    for f in facts.files:
        haystack += " ".join(f.functions + f.classes + f.imports).lower()
    if any(k in haystack for k in SCM_KEYWORDS):
        return []
    return [_f(
        "SCM_NO_RELEVANCE_SIGNAL", "Medium", "SCM Readiness / Business Fit",
        "No clear supply-chain domain signals detected",
        "No supply-chain-related keywords (inventory, supplier, forecast, reorder, logistics, etc.) were found in code identifiers or documentation.",
        "This platform validates SCM agents specifically; an agent with no detectable SCM vocabulary may be out of scope or mislabeled, which affects how its trust score should be interpreted.",
        evidence=[{"file_path": "<repo wide scan>", "reason": "no SCM keyword matches in code or docs"}],
    )]


ALL_RULES = [
    lambda facts, ctx: check_missing_readme(facts),
    lambda facts, ctx: check_missing_dependency_manifest(facts),
    lambda facts, ctx: check_use_case_clarity(facts, ctx.get("use_case"), ctx.get("description")),
    lambda facts, ctx: check_no_entrypoint(facts),
    lambda facts, ctx: check_parse_errors(facts),
    lambda facts, ctx: check_empty_files(facts),
    lambda facts, ctx: check_no_error_handling(facts),
    lambda facts, ctx: check_no_retry_or_timeout(facts),
    lambda facts, ctx: check_hardcoded_secrets(facts),
    lambda facts, ctx: check_no_env_example(facts),
    lambda facts, ctx: check_no_schema_hints(facts),
    lambda facts, ctx: check_no_logging(facts),
    lambda facts, ctx: check_scm_relevance(facts),
]


def run_all_rules(facts: RepoFacts, context: dict) -> list[RawFinding]:
    """Rules run in a fixed, sorted order so output ordering is also deterministic."""
    findings: list[RawFinding] = []
    for rule in ALL_RULES:
        findings.extend(rule(facts, context))
    findings.sort(key=lambda r: r.rule_id)
    return findings
