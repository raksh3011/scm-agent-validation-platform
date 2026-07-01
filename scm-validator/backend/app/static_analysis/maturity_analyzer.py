"""Static architecture/maturity analysis — independent of scenario execution.

The dynamic scenario engine answers "does the agent behave correctly on these
inputs?". It can score highly even when the agent is a thin, non-production
prototype: hardcoded predictions instead of a model, simulated actions that
never touch a database, no retries around an external API call, no real SCM
entities, no tests. Those are structural facts about the source code, not
runtime outcomes, so they have to be detected here and fed into the trust
score as their own dimension — otherwise a well-behaved toy script and a
production-grade agent are indistinguishable to the validator.

Every flag is anchored to the actual file/line/function that triggered it
when one exists (a specific function's body, a specific assignment). Checks
that are genuinely repo-wide absences (no test files anywhere, no CI config)
have no single line to blame and are reported without a misleading fallback
location — citing an unrelated file is worse than citing none.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ML_IMPORTS = {"numpy", "pandas", "sklearn", "scikit-learn", "statsmodels", "scipy", "torch", "tensorflow", "prophet"}
LLM_IMPORTS = {"anthropic", "openai", "cohere", "google.generativeai"}
SCM_ENTITY_TABLE_PATTERNS = {
    "purchase_order": r"purchase_orders?\b",
    "shipment": r"shipments?\b",
    "receipt": r"receipts?\b",
    "transaction": r"(inventory_)?transactions?\b",
}
PHASE_NAME_KEYWORDS = {
    "observe": ("perceive", "observe", "sense", "ingest"),
    "analyze": ("analyze", "analyse", "classify", "diagnose"),
    "plan": ("plan", "decide", "recommend"),
    "execute": ("execute", "act", "apply", "send", "create"),
    "monitor": ("monitor", "track", "watch", "alert"),
    "learn": ("learn", "retrain", "update", "feedback", "fine"),
}
WEIGHT_NAME_RE = re.compile(r"^[A-Z_]*(WEIGHT|_W)$")
MUTATING_SQL_RE = re.compile(r"\b(INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM)\b", re.I)
ACTION_FN_HINT_RE = re.compile(r"\b(erp|finance|purchase[_ ]?order|alert|on[_ ]?order)\b", re.I)
REORDER_FN_NAME_RE = re.compile(r"reorder|target_stock|order_quantity|decide", re.I)
CONTEXT_OPEN_RE = re.compile(r"context", re.I)


class Loc:
    """A specific (file, line, function) a flag is anchored to. `None` fields are
    honest gaps — better than guessing a fallback file."""
    __slots__ = ("file", "line", "function")

    def __init__(self, file: Path | None = None, line: int | None = None, function: str | None = None):
        self.file = file
        self.line = line
        self.function = function


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="ignore")
    except OSError:
        return ""


def _safe_parse(text: str) -> ast.Module | None:
    try:
        return ast.parse(text)
    except SyntaxError:
        return None


def _imports(tree: ast.Module) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def _func_source_span(node: ast.FunctionDef, text_lines: list[str]) -> str:
    end = getattr(node, "end_lineno", node.lineno + 20)
    return "\n".join(text_lines[node.lineno - 1:min(end, len(text_lines))])


def _enclosing_function(tree: ast.Module, node: ast.AST) -> str | None:
    best = None
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef) and fn.lineno <= node.lineno <= getattr(fn, "end_lineno", node.lineno):
            best = fn.name
    return best


def analyze_maturity(workspace: Path, python_files: list[Path]) -> dict:
    flags: dict[str, dict] = {}

    def flag(name: str, loc: Loc | None, detail: str):
        flags.setdefault(name, {"present": True, "occurrences": []})
        file_str = None
        if loc and loc.file:
            try:
                file_str = str(loc.file.relative_to(workspace))
            except ValueError:
                file_str = loc.file.name
        flags[name]["occurrences"].append({
            "file": file_str, "line": loc.line if loc else None,
            "function": loc.function if loc else None, "detail": detail,
        })

    all_imports: set[str] = set()
    all_text = ""
    function_names: set[str] = set()
    has_raise_or_assert = False
    found_static_dict_lookup_predict: Loc | None = None
    found_no_confidence_in_predict: Loc | None = None
    found_predict_loc: Loc | None = None
    weight_constants_hardcoded: list[tuple[str, Loc]] = []
    weight_constants_configurable: set[str] = set()
    choose_supplier_loc: Loc | None = None
    mutating_sql_files: set[Path] = set()
    db_path_hardcoded_loc: Loc | None = None
    db_path_configurable = False
    action_fn_loc: Loc | None = None
    context_open_loc: Loc | None = None
    reorder_fn_loc: Loc | None = None
    schema_file: Path | None = None

    for path in python_files:
        text = _read(path)
        if not text:
            continue
        all_text += "\n" + text
        if re.search(r"CREATE\s+TABLE", text, re.I) and schema_file is None:
            schema_file = path
        tree = _safe_parse(text)
        if tree is None:
            continue
        all_imports |= _imports(tree)
        lines = text.splitlines()

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                function_names.add(node.name.lower())
                if REORDER_FN_NAME_RE.search(node.name) and reorder_fn_loc is None:
                    reorder_fn_loc = Loc(path, node.lineno, node.name)
                if ACTION_FN_HINT_RE.search(_func_source_span(node, lines)) and action_fn_loc is None:
                    action_fn_loc = Loc(path, node.lineno, node.name)

            if isinstance(node, (ast.Raise, ast.Assert)):
                has_raise_or_assert = True

            if isinstance(node, ast.Call):
                callee = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                if callee == "open":
                    for arg in node.args:
                        if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and CONTEXT_OPEN_RE.search(arg.value):
                            context_open_loc = Loc(path, node.lineno, _enclosing_function(tree, node))
                        if isinstance(arg, ast.Name) and CONTEXT_OPEN_RE.search(arg.id):
                            context_open_loc = Loc(path, node.lineno, _enclosing_function(tree, node))

            if isinstance(node, ast.Assign):
                # Normalize both `W = 0.4` and tuple-unpacking `A, B, C = 0.4, 0.3, 0.3` into
                # a list of (target_name, value_expr) pairs.
                pairs: list[tuple[str, ast.expr]] = []
                if isinstance(node.targets[0], ast.Name) and not isinstance(node.value, ast.Tuple):
                    pairs.append((node.targets[0].id, node.value))
                elif isinstance(node.targets[0], (ast.Tuple, ast.List)) and isinstance(node.value, (ast.Tuple, ast.List)) \
                        and len(node.targets[0].elts) == len(node.value.elts):
                    for t_elt, v_elt in zip(node.targets[0].elts, node.value.elts):
                        if isinstance(t_elt, ast.Name):
                            pairs.append((t_elt.id, v_elt))

                for tgt, value_expr in pairs:
                    nested_calls = [n for n in ast.walk(value_expr) if isinstance(n, ast.Call)]
                    reads_from_env = any(
                        (getattr(c.func, "attr", None) or getattr(c.func, "id", None)) in ("getenv", "get")
                        and ("environ" in ast.dump(c.func) or "getenv" in ast.dump(c.func))
                        for c in nested_calls
                    )
                    loc = Loc(path, node.lineno, _enclosing_function(tree, node))
                    if WEIGHT_NAME_RE.match(tgt):
                        if reads_from_env:
                            weight_constants_configurable.add(tgt)
                        elif isinstance(value_expr, ast.Constant) or nested_calls:
                            weight_constants_hardcoded.append((tgt, loc))
                    if tgt.upper() in ("DB", "DB_PATH", "DATABASE_PATH"):
                        if reads_from_env:
                            db_path_configurable = True
                        elif isinstance(value_expr, ast.Constant) and isinstance(value_expr.value, str):
                            db_path_hardcoded_loc = loc

            if isinstance(node, ast.FunctionDef) and re.search(r"predict|forecast", node.name, re.I):
                loc = Loc(path, node.lineno, node.name)
                found_predict_loc = loc
                span = _func_source_span(node, lines)
                has_dict_literal = any(isinstance(n, ast.Dict) and len(n.keys) >= 1 for n in ast.walk(node))
                has_keyword_chain = bool(re.search(r"\bin\s+(text|context)\b", span, re.I))
                if has_dict_literal or has_keyword_chain:
                    found_static_dict_lookup_predict = loc
                if not re.search(r"confidence|uncertaint|variance|interval|stderr|std_dev", span, re.I):
                    found_no_confidence_in_predict = loc

            if isinstance(node, ast.FunctionDef) and re.search(r"choose_supplier|select_supplier", node.name, re.I):
                arg_names = {a.arg.lower() for a in node.args.args}
                if not any("product" in a for a in arg_names):
                    span = _func_source_span(node, lines)
                    if "product" not in span.lower():
                        choose_supplier_loc = Loc(path, node.lineno, node.name)

            if isinstance(node, ast.Call):
                callee = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                if callee in ("create",) and isinstance(node.func, ast.Attribute):
                    # heuristic for client.messages.create(...) / chat.completions.create(...)
                    src_repr = ast.dump(node.func)
                    if "messages" in src_repr or "completions" in src_repr or "chat" in src_repr:
                        in_try = any(isinstance(p, ast.Try) for p in ast.walk(tree)
                                     if isinstance(p, ast.Try) and p.lineno <= node.lineno <= getattr(p, "end_lineno", p.lineno))
                        if not in_try:
                            flag("no_retry_or_error_handling_for_external_api_calls",
                                 Loc(path, node.lineno, _enclosing_function(tree, node)),
                                 "LLM API call is not wrapped in a try/except — no retry or recovery on failure.")

                if callee == "loads" and getattr(node.func, "value", None) is not None:
                    in_try = any(isinstance(p, ast.Try) for p in ast.walk(tree)
                                 if isinstance(p, ast.Try) and p.lineno <= node.lineno <= getattr(p, "end_lineno", p.lineno))
                    if not in_try and re.search(r"anthropic|openai", text, re.I):
                        flag("unvalidated_llm_output_parsing",
                             Loc(path, node.lineno, _enclosing_function(tree, node)),
                             "json.loads() on an LLM response with no try/except and no schema validation.")

        if MUTATING_SQL_RE.search(text) or re.search(r"\.commit\s*\(", text):
            mutating_sql_files.add(path)

    if found_predict_loc and not (all_imports & ML_IMPORTS):
        flag("no_statistical_or_ml_forecasting_model", found_predict_loc,
             "A predict/forecast function exists but no ML/statistical library is imported anywhere in the "
             "repository — predictions are not generalizable beyond hardcoded or keyword-rule lookups.")
    if found_static_dict_lookup_predict:
        flag("hardcoded_or_rule_based_predictions", found_static_dict_lookup_predict,
             "The prediction function is driven by a fixed lookup table or keyword/string match, not a "
             "trained model or computed trend — it cannot generalize to unseen products or contexts.")
    if found_no_confidence_in_predict:
        flag("no_uncertainty_or_confidence_estimation", found_no_confidence_in_predict,
             "The prediction function returns a single point estimate with no confidence, variance, or "
             "uncertainty interval attached to it.")

    # Tokenize every function name on underscores (snake_case) — a plain `\bkeyword\b`
    # regex never matches inside e.g. `update_feedback_loop` because the underscores
    # on either side of "feedback" are word characters, so no word boundary exists
    # there at all. Exact-token matching after splitting sidesteps that entirely.
    name_tokens: set[str] = set()
    for fn_name in function_names:
        name_tokens.update(t for t in fn_name.split("_") if t)
    phase_hits = {phase: bool(name_tokens & set(keywords)) for phase, keywords in PHASE_NAME_KEYWORDS.items()}
    missing_phases = [p for p, hit in phase_hits.items() if not hit]
    if len(missing_phases) >= 3:
        flag("incomplete_scm_state_machine", None,
             f"Only {6 - len(missing_phases)}/6 SCM agent lifecycle phases (observe/analyze/plan/execute/monitor/learn) "
             f"are represented across the repository's function names; missing: {', '.join(missing_phases)}.")
    if not phase_hits.get("learn"):
        flag("no_feedback_or_learning_loop", None,
             "No function anywhere in the repository corresponds to a feedback/learning phase — the agent "
             "never updates its own predictions or scoring weights based on observed outcomes.")
    if not phase_hits.get("monitor"):
        flag("no_continuous_monitoring", None,
             "No function anywhere in the repository corresponds to a monitoring phase — there is no "
             "closed-loop tracking of decisions after they are made.")

    if choose_supplier_loc:
        flag("supplier_selection_ignores_product_context", choose_supplier_loc,
             "Supplier scoring is computed from a single global supplier list with no product-specific "
             "filtering — the same 'best' supplier is chosen regardless of which product is being ordered.")

    if weight_constants_hardcoded and not weight_constants_configurable:
        name, loc = weight_constants_hardcoded[0]
        flag("hardcoded_business_weights", loc,
             f"Scoring weight(s) {', '.join(n for n, _ in weight_constants_hardcoded)} are hardcoded numeric "
             "literals rather than configuration values — tuning the business policy requires a code change.")

    if not mutating_sql_files:
        flag("no_real_persistence_simulated_actions_only", action_fn_loc,
             "No INSERT/UPDATE/DELETE or commit() call was found anywhere in the repository — actions such "
             "as creating a purchase order or marking ERP status are simulated/printed, not persisted." +
             (f" The function that appears to perform this action is `{action_fn_loc.function}`." if action_fn_loc else ""))

    present_entities = {name for name, pattern in SCM_ENTITY_TABLE_PATTERNS.items() if re.search(pattern, all_text, re.I)}
    missing_entities = set(SCM_ENTITY_TABLE_PATTERNS) - present_entities
    if missing_entities:
        flag("missing_core_scm_entities", Loc(schema_file) if schema_file else None,
             f"No table/entity definitions found for: {', '.join(sorted(missing_entities))}. A production SCM "
             "agent needs durable records for these beyond the decision itself.")

    if context_open_loc and not (all_imports & {"requests", "httpx", "aiohttp"}):
        flag("static_demand_context_no_realtime_integration", context_open_loc,
             "Demand context is read from a static local text file with no network/API call anywhere in the "
             "repository — there is no real-time data integration.")

    if not re.search(r"\bmoq\b|min_order_qty", all_text, re.I):
        flag("reorder_logic_ignores_moq", reorder_fn_loc,
             "Reorder quantity logic has no reference to MOQ/minimum order quantity anywhere in the source.")
    if not re.search(r"capacity", all_text, re.I):
        flag("reorder_logic_ignores_capacity_constraints", reorder_fn_loc,
             "Reorder logic has no reference to supplier/warehouse capacity constraints anywhere in the source.")

    if not has_raise_or_assert:
        flag("no_business_input_validation", None,
             "No raise/assert was found anywhere in the source — negative stock, invalid suppliers, or other "
             "malformed business inputs are never explicitly rejected.")

    if len(python_files) <= 2 and sum(len(_read(p).splitlines()) for p in python_files) > 80:
        largest = max(python_files, key=lambda p: len(_read(p).splitlines())) if python_files else None
        flag("monolithic_single_file_architecture", Loc(largest) if largest else None,
             "The entire agent (data access, business logic, scoring, and execution) lives in one or two "
             "files with no separation of concerns into modules/layers.")

    if db_path_hardcoded_loc and not db_path_configurable:
        flag("hardcoded_database_path", db_path_hardcoded_loc,
             "The database path is a hardcoded string literal rather than being read from configuration or "
             "an environment variable — there is no deployment flexibility.")

    has_tests = any(re.search(r"^test_.*\.py$|.*_test\.py$", p.name) for p in python_files) or \
        any(p.is_dir() and p.name == "tests" for p in (workspace.iterdir() if workspace.exists() else []))
    if not has_tests:
        flag("no_automated_tests", None,
             "No test_*.py / *_test.py files or tests/ directory were found in the submission.")

    has_ci = (workspace / ".github" / "workflows").exists()
    has_readme = any((workspace / n).exists() for n in ("README.md", "README.rst", "readme.md"))
    if not has_ci or not has_readme:
        missing = []
        if not has_ci:
            missing.append("CI workflow (.github/workflows)")
        if not has_readme:
            missing.append("README")
        flag("missing_ci_or_documentation", None, f"Missing: {', '.join(missing)}.")

    if not (all_imports & {"logging"}):
        flag("no_structured_logging", None,
             "No `logging` module usage was found anywhere in the repository — output is print-only.")

    return flags
