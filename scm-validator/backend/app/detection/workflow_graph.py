"""Builds a lightweight call graph and flags 'decision functions' (functions that
branch and return a structured decision) — used both for classification and to
locate injection points for scenario generation."""
import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DecisionFunction:
    module_path: Path
    name: str
    class_name: str | None
    branch_count: int
    returns_structured: bool
    referenced_names: set[str] = field(default_factory=set)


def _collect_names(node: ast.AST) -> set[str]:
    names = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Name):
            names.add(n.id.lower())
        elif isinstance(n, ast.Attribute):
            names.add(n.attr.lower())
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            names.add(n.value.lower())
    return names


def _branch_count(node: ast.AST) -> int:
    return sum(1 for n in ast.walk(node) if isinstance(n, (ast.If, ast.For, ast.While)))


def _returns_structured(node: ast.AST) -> bool:
    for n in ast.walk(node):
        if isinstance(n, ast.Return) and isinstance(n.value, (ast.Dict, ast.Call)):
            return True
    return False


def build(python_files: list[Path]) -> list[DecisionFunction]:
    decisions: list[DecisionFunction] = []
    for path in python_files:
        try:
            tree = ast.parse(path.read_text(errors="ignore"))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.FunctionDef):
                        bc = _branch_count(item)
                        structured = _returns_structured(item)
                        if bc >= 1 or structured:
                            decisions.append(DecisionFunction(
                                path, item.name, node.name, bc, structured, _collect_names(item)))
            elif isinstance(node, ast.FunctionDef):
                # skip ones already captured as methods
                bc = _branch_count(node)
                structured = _returns_structured(node)
                if bc >= 1 or structured:
                    decisions.append(DecisionFunction(path, node.name, None, bc, structured, _collect_names(node)))

    # de-dupe (top-level walk visits methods twice via nested FunctionDef under ClassDef)
    seen = set()
    deduped = []
    for d in decisions:
        key = (str(d.module_path), d.class_name, d.name)
        if key not in seen:
            seen.add(key)
            deduped.append(d)
    return deduped
