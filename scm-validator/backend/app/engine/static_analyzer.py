"""Deterministic structural extraction: no scoring, no opinions — just facts about the codebase."""
import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

CODE_EXTS = {".py", ".js", ".ts", ".tsx", ".jsx"}
DOC_NAMES = {"readme.md", "readme.rst", "readme.txt", "readme"}
DEP_FILES = {"requirements.txt", "pyproject.toml", "package.json", "pipfile", "environment.yml"}
CONFIG_FILES = {".env.example", "config.yaml", "config.yml", "config.json", "settings.py", "settings.json"}

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password|passwd)\s*[=:]\s*[\"'][A-Za-z0-9_\-/+]{8,}[\"']"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
]
LOGGING_PATTERNS = [re.compile(r"\blogging\.|logger\.|console\.log|print\("), ]
RETRY_PATTERNS = [re.compile(r"(?i)retry|backoff|tenacity|circuit.?breaker")]
TIMEOUT_PATTERNS = [re.compile(r"(?i)timeout\s*=")]
EXCEPT_PATTERN = re.compile(r"\bexcept\b")
TRY_PATTERN = re.compile(r"\btry\s*:")
SCHEMA_PATTERNS = [re.compile(r"(?i)pydantic|BaseModel|dataclass|TypedDict|interface\s+\w+|zod|jsonschema")]


# Performance caps so a real-world repo (hundreds of files, tens of MB) stays bounded.
MAX_FILE_BYTES = 200_000        # don't analyze the content of a single file beyond this
MAX_CODE_FILES = 600            # analyze at most this many code files
MAX_CORPUS_BYTES = 4_000_000    # combined corpus the rule engine scans, capped


@dataclass
class FileFact:
    rel_path: str
    ext: str
    size: int
    content: str = ""           # cached file text (capped at MAX_FILE_BYTES); read once
    line_count: int = 0
    has_try_except: bool = False
    has_logging: bool = False
    has_retry_pattern: bool = False
    has_timeout_pattern: bool = False
    has_schema_hint: bool = False
    secret_hits: list[tuple[int, str]] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    docstring: str | None = None
    parse_error: str | None = None


@dataclass
class RepoFacts:
    root: Path
    files: list[FileFact] = field(default_factory=list)
    has_readme: bool = False
    readme_excerpt: str = ""
    dependency_files: list[str] = field(default_factory=list)
    config_files: list[str] = field(default_factory=list)
    entrypoints: list[str] = field(default_factory=list)
    total_code_files: int = 0
    total_loc: int = 0
    truncated: bool = False      # True if file/byte caps were hit
    _corpus_lower: str | None = field(default=None, repr=False)

    @property
    def corpus_lower(self) -> str:
        """Lowercased concatenation of all analyzed file content, built once and cached.
        Rules scan this instead of re-reading every file from disk per check."""
        if self._corpus_lower is None:
            parts = []
            total = 0
            for f in self.files:
                if not f.content:
                    continue
                parts.append(f.content)
                total += len(f.content)
                if total >= MAX_CORPUS_BYTES:
                    break
            self._corpus_lower = "\n".join(parts).lower()
        return self._corpus_lower


def _analyze_python(content: str, fact: FileFact):
    try:
        tree = ast.parse(content)
    except SyntaxError as e:
        fact.parse_error = str(e)
        return
    fact.docstring = ast.get_docstring(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            fact.functions.append(node.name)
        elif isinstance(node, ast.ClassDef):
            fact.classes.append(node.name)
        elif isinstance(node, ast.Import):
            fact.imports.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            fact.imports.append(node.module)


def analyze_file(path: Path, root: Path) -> FileFact:
    rel = str(path.relative_to(root)).replace("\\", "/")
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        raw = ""
    full_size = len(raw)
    # Cap the content we keep/scan; oversized files (generated, vendored) only count toward size.
    content = raw[:MAX_FILE_BYTES]
    fact = FileFact(rel_path=rel, ext=path.suffix.lower(), size=full_size, content=content)
    fact.line_count = content.count("\n") + 1 if content else 0

    if path.suffix == ".py" and full_size <= MAX_FILE_BYTES:
        _analyze_python(content, fact)

    fact.has_try_except = bool(TRY_PATTERN.search(content) and EXCEPT_PATTERN.search(content))
    fact.has_logging = any(p.search(content) for p in LOGGING_PATTERNS)
    fact.has_retry_pattern = any(p.search(content) for p in RETRY_PATTERNS)
    fact.has_timeout_pattern = any(p.search(content) for p in TIMEOUT_PATTERNS)
    fact.has_schema_hint = any(p.search(content) for p in SCHEMA_PATTERNS)

    for lineno, line in enumerate(content.splitlines(), start=1):
        for pattern in SECRET_PATTERNS:
            if pattern.search(line):
                fact.secret_hits.append((lineno, line.strip()[:160]))
                break
    return fact


def build_repo_facts(root: Path) -> RepoFacts:
    from .repo_ingestor import list_source_files, IGNORE_DIRS

    facts = RepoFacts(root=root)
    for path in list_source_files(root):
        name_lower = path.name.lower()
        rel = str(path.relative_to(root)).replace("\\", "/")

        if name_lower in DOC_NAMES or name_lower.startswith("readme"):
            facts.has_readme = True
            try:
                facts.readme_excerpt = path.read_text(encoding="utf-8", errors="ignore")[:1500]
            except Exception:
                pass
            continue

        if name_lower in DEP_FILES:
            facts.dependency_files.append(rel)
            continue

        if name_lower in CONFIG_FILES or name_lower.startswith(".env"):
            facts.config_files.append(rel)
            continue

        if path.suffix.lower() in CODE_EXTS:
            if facts.total_code_files >= MAX_CODE_FILES:
                facts.truncated = True
                continue
            fact = analyze_file(path, root)
            facts.files.append(fact)
            facts.total_code_files += 1
            facts.total_loc += fact.line_count
            if name_lower in {"main.py", "app.py", "agent.py", "run.py", "index.js", "index.ts", "server.py"}:
                facts.entrypoints.append(rel)

    return facts
