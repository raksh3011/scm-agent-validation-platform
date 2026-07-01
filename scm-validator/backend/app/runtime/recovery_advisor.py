"""Pattern-matched recovery suggestions for runtime/sandbox failures. Deterministic
substring matching on exception type/message — no LLM required, works offline."""

_PATTERNS: list[tuple[str, tuple[str, ...], str]] = [
    ("OperationalError", ("no such table",),
     "The repository's bundled database is missing its schema (no CREATE TABLE statement "
     "found or executed). Commit a populated database file, or add a schema-creation step "
     "the validator can run before validation."),
    ("OperationalError", ("no such column",),
     "The repository's database schema doesn't match what the entrypoint expects. Verify "
     "the bundled database/migration matches the current code."),
    ("ModuleNotFoundError", ()),
    ("ImportError", ()),
    ("FileNotFoundError", (),
     "The agent expects a file (config, data, or asset) that isn't present in this "
     "submission. Make sure all files the entrypoint reads are committed to the repository."),
    ("TypeError", ("argument", "positional"),
     "The entrypoint's parameters don't match a standard SCM decision signature (simple "
     "business objects like inventory/demand/supplier/sku). Expose a function that accepts "
     "those directly, or document the expected call contract."),
    ("KeyError", (),
     "The agent expects a specific key in its input/config that the sandbox didn't supply. "
     "Check for hardcoded config or environment-specific keys."),
    ("ConnectionError", (),
     "The agent tries to reach a live external service. Provide a mock-friendly code path "
     "or environment flag so it can run fully offline in a sandbox."),
]

_DEFAULT_SUGGESTION = "Inspect the exception traceback in Runtime Evidence to diagnose the root cause."


def suggest(exception_type: str | None, message: str | None) -> str:
    message_lower = (message or "").lower()
    for exc_type, keywords, *rest in _PATTERNS:
        if exception_type != exc_type:
            continue
        if keywords and not any(kw in message_lower for kw in keywords):
            continue
        if rest:
            return rest[0]
        if exc_type in ("ModuleNotFoundError", "ImportError"):
            return ("A required dependency is missing or failed to install. Check that "
                    "requirements.txt lists every package the entrypoint imports, and that "
                    "the package name/version is installable in a clean environment.")
    return _DEFAULT_SUGGESTION
