"""Detects language, framework, and dependency manifest for a workspace."""
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RepoProfile:
    language: str
    framework: str | None
    dependency_files: list[Path] = field(default_factory=list)
    declared_dependencies: list[str] = field(default_factory=list)
    python_files: list[Path] = field(default_factory=list)
    entry_candidates: list[Path] = field(default_factory=list)


PY_FRAMEWORK_MARKERS = {
    "fastapi": "fastapi",
    "flask": "flask",
    "django": "django",
    "langchain": "langchain",
    "crewai": "crewai",
}


def detect(workspace: Path) -> RepoProfile:
    py_files = [p for p in workspace.rglob("*.py") if "__pycache__" not in p.parts and ".venv" not in p.parts]
    requirements_files = [p for p in workspace.rglob("requirements*.txt")]
    pyproject = list(workspace.rglob("pyproject.toml"))

    if not py_files:
        # Fall back: no python detected, treat as unsupported for the deep slice.
        return RepoProfile(language="unknown", framework=None)

    declared = []
    for rf in requirements_files:
        try:
            for line in rf.read_text(errors="ignore").splitlines():
                line = line.strip().lower()
                if line and not line.startswith("#"):
                    declared.append(line.split("==")[0].split(">=")[0].strip())
        except OSError:
            continue

    framework = None
    combined_text = " ".join(declared)
    for marker, name in PY_FRAMEWORK_MARKERS.items():
        if marker in combined_text:
            framework = name
            break

    entry_candidates = [p for p in py_files if p.name in ("main.py", "agent.py", "app.py", "run.py", "__main__.py")]
    if not entry_candidates:
        entry_candidates = py_files[:20]

    return RepoProfile(
        language="python",
        framework=framework,
        dependency_files=requirements_files + pyproject,
        declared_dependencies=declared,
        python_files=py_files,
        entry_candidates=entry_candidates,
    )
