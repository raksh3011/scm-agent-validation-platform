"""Detects positive trust signals in SCM agent code.

Positive signals are deterministic patterns that indicate good design,
not subjective quality assessments. They are paired with the rule_engine
findings to produce a balanced score.
"""
import re
from pathlib import Path
from .static_analyzer import RepoFacts, FileFact


def _content_for_analysis(root: Path, files: list[FileFact]) -> str:
    """Concatenate all code files for pattern matching."""
    content = ""
    for f in files:
        try:
            path = root / f.rel_path
            content += path.read_text(encoding="utf-8", errors="ignore")
            content += "\n"
        except Exception:
            pass
    return content.lower()


# ---- Structural / Architectural signals ----

def detect_perceive_decide_act_structure(facts: RepoFacts) -> list[str]:
    """Agent has clearly separated perceive, decide, act phases."""
    signals = []
    content = _content_for_analysis(facts.root, facts.files)

    # Look for function names matching the pattern
    if re.search(r"\bdef\s+(perceive|sense|read|load|fetch)[\s\(]", content):
        signals.append("Perceive phase function detected")
    if re.search(r"\bdef\s+(decide|judge|plan|score|recommend)[\s\(]", content):
        signals.append("Decide phase function detected")
    if re.search(r"\bdef\s+(act|execute|apply|output|send)[\s\(]", content):
        signals.append("Act phase function detected")

    # Look for section comments
    if re.search(r"#.*perceive", content) and re.search(r"#.*decide", content) and re.search(r"#.*act", content):
        signals.append("Perceive-Decide-Act structure documented in comments")

    return signals


def detect_isolated_judgment_seams(facts: RepoFacts) -> list[str]:
    """AI/LLM judgment is isolated in dedicated functions, not mixed with core logic."""
    signals = []
    content = _content_for_analysis(facts.root, facts.files)

    # LLM calls isolated in named functions
    if re.search(r"def\s+\w*llm\w*\s*\(", content) or re.search(r"def\s+\w*predict\w*\s*\(", content):
        signals.append("LLM judgment isolated in dedicated function(s)")

    # Anthropic/OpenAI imports in separate scope
    if re.search(r"import\s+anthropic", content) and re.search(r"def\s+.*llm", content):
        signals.append("LLM client imported within judgment function")

    # Mock vs live branching
    if re.search(r"if\s+live", content) or re.search(r"if\s+\w*mock\b", content):
        signals.append("Mock vs live mode separation detected")

    return signals


def detect_deterministic_core_logic(facts: RepoFacts) -> list[str]:
    """Core decision logic is deterministic (arithmetic, rule-based, not LLM-driven)."""
    signals = []
    content = _content_for_analysis(facts.root, facts.files)

    # Arithmetic patterns typical of supply chain (ROP, safety stock, lead time)
    if re.search(r"(rop|reorder.point|lead.time|safety.stock|demand)", content):
        signals.append("Supply chain arithmetic patterns detected (ROP, lead time, safety stock)")

    # Weighted scoring / rule-based logic
    if re.search(r"(weight|score|rank|max|min)", content) and re.search(r"[\*\+\-/]", content):
        signals.append("Rule-based or weighted scoring logic detected")

    # Min/max supplier selection patterns
    if re.search(r"(min|max)\s*\(\s*\w+\s*,\s*key", content):
        signals.append("Deterministic supplier/option selection (min/max) detected")

    return signals


def detect_documented_objectives(facts: RepoFacts) -> list[str]:
    """Agent's business objective and flow are documented."""
    signals = []

    if facts.has_readme:
        signals.append("README/documentation present describing agent purpose")

    content = _content_for_analysis(facts.root, facts.files)

    # Module docstring
    if re.search(r'""".*?"""', content, re.DOTALL) or re.search(r"'''.*?'''", content, re.DOTALL):
        signals.append("Module docstring or extensive comments documenting objective")

    # Section comments explaining flow
    if content.count("#") > 20:
        signals.append("Inline comments explaining logic and decisions")

    return signals


def detect_auditable_outputs(facts: RepoFacts) -> list[str]:
    """Agent returns decision reasoning, not just actions."""
    signals = []
    content = _content_for_analysis(facts.root, facts.files)

    # Return dict with multiple fields including reasoning
    if re.search(r'return\s*\{[^}]*"(why|reason|explain|justif)', content):
        signals.append("Decision reasoning/justification returned with action")

    # Intermediate values exposed for audit
    if re.search(r'return.*d_adj.*rop.*mult', content) or re.search(r'"d_adj".*"rop".*"mult"', content):
        signals.append("Intermediate decision values exposed for auditability")

    # Supplier info in output
    if re.search(r'return.*supplier', content):
        signals.append("Supplier selection decision included in output")

    return signals


# ---- SCM-specific positive signals ----

def detect_scm_patterns(facts: RepoFacts) -> list[str]:
    """Agent implements classic SCM decision patterns correctly."""
    signals = []
    content = _content_for_analysis(facts.root, facts.files)

    # Reorder point logic
    if re.search(r"(rop|reorder.point)\s*=.*lead", content):
        signals.append("Reorder Point calculation includes lead time")

    if re.search(r"(rop|reorder.point).*safety.stock", content):
        signals.append("Reorder Point calculation includes safety stock")

    # Multi-supplier comparison
    if re.search(r"(choose|select|pick).*supplier", content) and re.search(r"(price|reliability|lead)", content):
        signals.append("Multi-factor supplier selection (price, reliability, lead time)")

    # Demand adjustment / forecasting
    if re.search(r"demand.*multiplier|demand.*adjust|forecast", content):
        signals.append("Demand adjustment/forecasting integrated into decision")

    # Target stock calculation
    if re.search(r"target.*=.*demand.*\(.*lead.*review", content):
        signals.append("Target stock calculation for review period implemented")

    return signals


# ---- Reliability signals ----

def detect_error_handling_patterns(facts: RepoFacts) -> list[str]:
    """Error handling is present in key code paths."""
    signals = []
    code_files = [f for f in facts.files if f.ext in {".py"}]

    if any(f.has_try_except for f in code_files):
        signals.append("Try-except error handling present")

    content = _content_for_analysis(facts.root, code_files)
    if re.search(r"\bassert\b", content):
        signals.append("Input validation / assertions present")

    return signals


def detect_mock_mode(facts: RepoFacts) -> list[str]:
    """Agent supports mock/demo mode without external calls."""
    signals = []
    content = _content_for_analysis(facts.root, facts.files)

    if re.search(r"(mock|demo|test|recorded|default)", content):
        signals.append("Mock/test mode with recorded decisions available")

    # Conditional LLM vs mock
    if re.search(r"if.*live|if.*mock", content):
        signals.append("Mock vs live mode selectable at runtime")

    return signals


def collect_all_positive_signals(facts: RepoFacts) -> list[str]:
    """Collect all positive signals in order of importance."""
    all_signals = []

    all_signals.extend(detect_perceive_decide_act_structure(facts))
    all_signals.extend(detect_isolated_judgment_seams(facts))
    all_signals.extend(detect_mock_mode(facts))
    all_signals.extend(detect_deterministic_core_logic(facts))
    all_signals.extend(detect_scm_patterns(facts))
    all_signals.extend(detect_documented_objectives(facts))
    all_signals.extend(detect_auditable_outputs(facts))
    all_signals.extend(detect_error_handling_patterns(facts))

    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for sig in all_signals:
        if sig not in seen:
            unique.append(sig)
            seen.add(sig)

    return unique
