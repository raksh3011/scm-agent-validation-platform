"""AST-based discovery of the likely SCM agent entrypoint (function or class+method)."""
import ast
from dataclasses import dataclass
from pathlib import Path

DECISION_NAME_HINTS = (
    "reorder", "replenish", "forecast", "predict", "select", "decide", "evaluate",
    "process", "run", "execute", "recommend", "optimize", "plan", "schedule",
)
# Deliberately disjoint from DECISION_NAME_HINTS so a trivial CLI wrapper named
# e.g. "run" doesn't get double-counted against a real decision function like
# "decide" that takes actual business parameters.
ENTRY_NAME_HINTS = ("main", "handle", "agent")

# A function whose ONLY required parameter is an infrastructure handle (a DB
# connection, session, client, etc.) can't be driven by scenario business data —
# calling it with our generic dict just produces a misleading AttributeError, not a
# real business-logic signal. Exclude these entirely rather than let them rank.
_INFRA_PARAM_NAMES = {"con", "conn", "connection", "db", "session", "client", "cursor", "cur", "engine"}

# A required parameter named like this means the function CONSUMES an already-made
# decision (an action-executor/persistence step) rather than PRODUCING one. Scoring
# these highly rewards exactly the wrong function — e.g. an `execute_action(decision,
# ...)` that just records a precomputed result outranking the actual `decide(...)`
# that computes it, because it happens to take more parameters.
_DOWNSTREAM_CONSUMER_PARAM_HINTS = ("decision", "result", "outcome", "response", "action_result")

# Keys that, if present in a function's own returned dict literal, are strong direct
# evidence that THIS function is the one producing the business decision — much
# stronger evidence than "it returns a dict-shaped thing" or "it has many parameters".
_DECISION_RETURN_KEY_HINTS = {
    "action", "decision", "status", "should_reorder", "reorder", "qty", "quantity",
    "recommended_qty", "recommended_quantity", "order_quantity",
}


@dataclass
class EntrypointCandidate:
    module_path: Path
    function_name: str
    class_name: str | None
    param_names: list[str]
    score: float
    required_param_names: list[str] = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.required_param_names is None:
            self.required_param_names = list(self.param_names)


def _score_name(name: str, hints: tuple[str, ...]) -> float:
    lname = name.lower()
    return max((1.0 if h in lname else 0.0 for h in hints), default=0.0)


def _required_param_names(node: ast.FunctionDef) -> list[str]:
    args = node.args.args
    n_defaults = len(node.args.defaults)
    required = args[: len(args) - n_defaults] if n_defaults else args
    return [a.arg for a in required if a.arg not in ("self", "cls")]


def _return_dict_keys(node: ast.AST) -> set[str]:
    """Lowercased string keys from every dict literal the function returns. Only a
    literal `return {...}` counts — an arbitrary `return some_call(...)` tells us
    nothing about the shape of what comes back, so it earns no bonus on its own."""
    keys: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict):
            for k in n.value.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    keys.add(k.value.lower())
    return keys


def _score_function(node: ast.FunctionDef, class_decision_bonus: float = 0.0) -> tuple[float, list[str], list[str]]:
    params = [a.arg for a in node.args.args if a.arg not in ("self", "cls")]
    required = _required_param_names(node)
    optional = [p for p in params if p not in required]

    if required and all(p.lower() in _INFRA_PARAM_NAMES for p in required):
        return 0.0, params, required

    infra_count = sum(1 for p in required if p.lower() in _INFRA_PARAM_NAMES)
    consumer_count = sum(1 for p in required if any(h in p.lower() for h in _DOWNSTREAM_CONSUMER_PARAM_HINTS))
    clean_required = [p for p in required if p.lower() not in _INFRA_PARAM_NAMES
                       and not any(h in p.lower() for h in _DOWNSTREAM_CONSUMER_PARAM_HINTS)]

    score = _score_name(node.name, DECISION_NAME_HINTS) * 2.5
    score += _score_name(node.name, ENTRY_NAME_HINTS) * 0.5
    score += class_decision_bonus
    # Functions that actually take business data as required parameters rank far
    # above no-arg/flag-only CLI wrappers that read everything from globals/files —
    # but capped, so an over-parameterized downstream consumer can't out-rank a
    # focused decision function purely by accepting more arguments.
    score += 0.7 * min(len(clean_required), 4)
    score += 0.1 * min(len(optional), 5)
    # A parameter that needs internal wiring (a live DB connection) or that expects
    # someone else's decision as input are both signals this isn't the decision
    # producer — penalize rather than reward.
    score -= 1.0 * infra_count
    score -= 2.5 * consumer_count

    return_keys = _return_dict_keys(node)
    if return_keys:
        score += 1.0
        if return_keys & _DECISION_RETURN_KEY_HINTS:
            score += 2.0

    return max(score, 0.0), params, required


def discover(workspace: Path, python_files: list[Path]) -> list[EntrypointCandidate]:
    candidates: list[EntrypointCandidate] = []
    for path in python_files:
        try:
            tree = ast.parse(path.read_text(errors="ignore"))
        except SyntaxError:
            continue

        class_method_ids = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                class_method_ids.update(id(item) for item in node.body if isinstance(item, ast.FunctionDef))

        for node in ast.walk(tree):
            # ast.walk recurses into class bodies too, so a method would otherwise be
            # double-counted here as a bogus module-level (no `self`) candidate in
            # addition to the correctly class-qualified one added below.
            if isinstance(node, ast.FunctionDef) and not node.name.startswith("_") and id(node) not in class_method_ids:
                score, params, required = _score_function(node)
                if score > 0:
                    candidates.append(EntrypointCandidate(path, node.name, None, params, score, required))
            if isinstance(node, ast.ClassDef):
                class_bonus = _score_name(node.name, DECISION_NAME_HINTS)
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and not item.name.startswith("_"):
                        score, params, required = _score_function(item, class_bonus)
                        if score > 0:
                            candidates.append(EntrypointCandidate(path, item.name, node.name, params, score, required))

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates
