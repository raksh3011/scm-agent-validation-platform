"""Static structural facts. These never drive pass/fail or trust score on their own —
they only corroborate conclusions already reached from runtime evidence (e.g. a
'missing PO creation' defect is more confident if the source also has no persistence
call at all)."""
import ast
from pathlib import Path

from .maturity_analyzer import analyze_maturity

PERSISTENCE_HINTS = ("execute", "insert", "commit", "save", "create_purchase_order", "session.add")
ERROR_HANDLING_HINTS = (ast.Try,)


def analyze(python_files: list[Path], workspace: Path | None = None) -> dict:
    facts = {
        "has_persistence_call": False,
        "has_error_handling": False,
        "has_logging": False,
        "total_files": len(python_files),
        "total_lines": 0,
    }
    for path in python_files:
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        facts["total_lines"] += text.count("\n")
        lowered = text.lower()
        if any(h in lowered for h in PERSISTENCE_HINTS):
            facts["has_persistence_call"] = True
        if "logging" in lowered or "logger" in lowered:
            facts["has_logging"] = True
        try:
            tree = ast.parse(text)
            if any(isinstance(n, ast.Try) for n in ast.walk(tree)):
                facts["has_error_handling"] = True
        except SyntaxError:
            continue
    facts["maturity"] = analyze_maturity(workspace or (python_files[0].parent if python_files else Path(".")), python_files)
    return facts
