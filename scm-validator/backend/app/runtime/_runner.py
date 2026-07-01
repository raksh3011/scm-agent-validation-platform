"""Executed as a standalone subprocess: imports the candidate entrypoint, calls it with
scenario inputs, and writes a JSON result. Kept dependency-free so it works inside any
sandboxed interpreter without needing this package importable.
"""
import contextlib
import importlib.util
import inspect
import io
import json
import os
import sys
import traceback


def _fake_response(data):
    class _FakeResp:
        status_code = 200

        def json(self):
            return data

        @property
        def text(self):
            return json.dumps(data)

    return _FakeResp()


class _AttrDict(dict):
    """A dict that also supports attribute access. Synthesized/scenario arguments are
    always plain JSON dicts on the wire, but a candidate's real parameter might be a
    @dataclass-style object accessed as `param.field` rather than `param["field"]` —
    rather than have to correctly guess which style ahead of time, make every
    dict-shaped argument support both."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        self[name] = value


def _wrap_dual_access(value):
    if isinstance(value, dict):
        return _AttrDict({k: _wrap_dual_access(v) for k, v in value.items()})
    if isinstance(value, list):
        return [_wrap_dual_access(v) for v in value]
    return value


def _serialize(obj):
    try:
        json.dumps(obj)
        return obj
    except TypeError:
        if hasattr(obj, "__dict__"):
            return {k: _serialize(v) for k, v in obj.__dict__.items()}
        if isinstance(obj, (list, tuple)):
            return [_serialize(v) for v in obj]
        if isinstance(obj, dict):
            return {k: _serialize(v) for k, v in obj.items()}
        return str(obj)


def main():
    workspace, module_abs, callable_name, class_name, scenario_path, result_path = sys.argv[1:7]
    sys.path.insert(0, workspace)

    with open(scenario_path) as f:
        scenario = json.load(f)

    mock_calls = []
    try:
        import requests

        def _fake(method):
            def _call(url, *a, **kw):
                mock_calls.append({"method": method, "url": str(url)})
                return _fake_response({"mocked": True})
            return _call

        for m in ("get", "post", "put", "patch", "delete"):
            setattr(requests, m, _fake(m))
    except ImportError:
        pass

    result = {"return_value": None, "exception": None, "stdout": "", "mock_calls": mock_calls}
    stdout_buf = io.StringIO()
    try:
        spec = importlib.util.spec_from_file_location("agent_under_test", module_abs)
        mod = importlib.util.module_from_spec(spec)
        # Required for @dataclass (and anything else that introspects
        # sys.modules[cls.__module__]) to work when the target file also uses
        # `from __future__ import annotations` — without this, dataclass's own
        # postponed-annotation resolution crashes with
        # "'NoneType' object has no attribute '__dict__'" before the agent's code
        # ever runs, for every candidate, indistinguishable from a real failure.
        sys.modules[spec.name] = mod
        with contextlib.redirect_stdout(stdout_buf):
            spec.loader.exec_module(mod)
            if class_name and class_name != "None":
                cls = getattr(mod, class_name)
                instance = cls()
                fn = getattr(instance, callable_name)
            else:
                fn = getattr(mod, callable_name)

            inputs = {k: _wrap_dual_access(v) for k, v in scenario.get("inputs", {}).items()}
            # Only fall back to passing the whole input dict as one positional
            # argument when the function's single parameter NAME suggests it wants
            # "the whole scenario" (context/inputs/data/...). A single param named
            # after a specific business noun (e.g. "suppliers", "con", "product")
            # means the function wants just that one thing, not our whole dict —
            # blindly dumping the dict in there produces a misleading secondary
            # exception that masks the real "wrong candidate" diagnostic.
            GENERIC_CONTAINER_NAMES = {"context", "ctx", "input", "inputs", "data", "payload",
                                        "request", "event", "scenario", "kwargs", "args"}
            try:
                params = list(inspect.signature(fn).parameters.values())
            except (TypeError, ValueError):
                params = None
            single_generic_param = (
                params is not None and len(params) == 1
                and params[0].kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.POSITIONAL_ONLY)
                and params[0].name.lower() in GENERIC_CONTAINER_NAMES
            )
            if single_generic_param:
                try:
                    ret = fn(**inputs)
                except TypeError:
                    ret = fn(inputs)
            else:
                ret = fn(**inputs)
        result["return_value"] = _serialize(ret)
    except Exception as e:
        result["exception"] = {
            "type": type(e).__name__,
            "message": str(e),
            "traceback": traceback.format_exc()[-2000:],
        }
    result["stdout"] = stdout_buf.getvalue()[-4000:]

    with open(result_path, "w") as f:
        json.dump(result, f, default=str)


if __name__ == "__main__":
    main()
