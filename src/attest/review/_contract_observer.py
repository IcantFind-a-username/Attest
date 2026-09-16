"""Standalone, bounded shadow recorder copied into an instrumented test tree.

Runs inside the reviewed interpreter: records are NOT trusted certification evidence.
No attest imports, model calls, controller keys or receipt authority live here.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import math
import os
import sys
import types
from pathlib import Path
from typing import Any

PREFIX = "ATTEST_CONTRACT_SHADOW_V3="
_events: list[dict[str, Any]] = []
_pending: dict[str, tuple[dict[str, Any], Any]] = {}
_truncated = False


def snapshot(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        raise ValueError("snapshot depth")
    kind = type(value)
    if value is None or kind in (bool, int):
        if kind is int and value.bit_length() > 256:
            raise ValueError("large integer")
        return {"kind": "none" if value is None else kind.__name__, "value": value}
    if kind is str and len(value) <= 256:
        return {"kind": "str", "value": value}
    if kind is float and math.isfinite(value):
        return {"kind": "float", "value": value}
    if kind is dict:
        if len(value) > 16 or any(type(k) is not str or len(k) > 80 for k in value):
            raise ValueError("mapping shape")
        return {"kind": "dict", "items": [[k, snapshot(v, depth + 1)] for k, v in value.items()]}
    label = (
        type.__getattribute__(kind, "__module__") + "." + type.__getattribute__(kind, "__name__")
    )
    if kind is list or isinstance(value, tuple):
        values = list.__iter__(value) if kind is list else tuple.__iter__(value)
        length = list.__len__(value) if kind is list else tuple.__len__(value)
        if length > 16:
            raise ValueError("sequence size")
        return {
            "kind": "list" if kind is list else "tuple",
            "type": label,
            "items": [snapshot(v, depth + 1) for v in values],
        }
    raise ValueError("unsupported value type: " + label)


def _state(receiver: Any) -> Any:
    if receiver is None:
        return None
    state = object.__getattribute__(receiver, "__dict__")
    if type(state) is not dict:
        raise ValueError("receiver has no plain state mapping")
    kind = type(receiver)
    return {"type": kind.__module__ + "." + kind.__qualname__, "state": snapshot(state)}


def call(site: str, function: Any, /, *args: Any, **kwargs: Any) -> Any:
    global _truncated
    if len(_events) >= 32:
        _truncated = True
        return function(*args, **kwargs)
    # A consistency label supplied by pytest, not an authenticated witness.
    current = os.environ.get("PYTEST_CURRENT_TEST", "")
    node = current.removesuffix(" (call)") if current.endswith(" (call)") else ""
    event: dict[str, Any] = {"site": site, "node": node, "error": "", "compared": False}
    _events.append(event)
    try:
        method = type(function) is types.MethodType
        fn = function.__func__ if method else function
        if type(fn) is not types.FunctionType:
            raise ValueError("callee is not a Python function or bound method")
        code = fn.__code__
        path = Path(code.co_filename).resolve()
        root = Path(__file__).resolve().parent
        payload = path.read_bytes()
        if len(payload) > 400_000:
            raise ValueError("callee file size")
        event.update(
            callee={
                "file": path.relative_to(root).as_posix(),
                "name": code.co_name,
                "line": code.co_firstlineno,
                "qualname": fn.__qualname__,
                "source_digest": hashlib.sha256(payload).hexdigest(),
            },
            receiver=_state(function.__self__ if method else None),
            args=snapshot(args),
            kwargs=snapshot(kwargs),
        )
    except Exception as exc:
        event["error"] = type(exc).__name__ + ": " + str(exc)[:160]
    try:
        value = function(*args, **kwargs)
    except BaseException as exc:
        event["raised"] = type(exc).__name__
        raise
    try:
        event["returned"] = snapshot(value)
    except Exception as exc:
        event["error"] = type(exc).__name__ + ": " + str(exc)[:160]
    _pending[site] = (event, value)
    return value


def compare(site: str, left: Any, right: Any) -> Any:
    pending = _pending.pop(site, None)
    try:
        result = left == right
    except BaseException as exc:
        if pending is not None:
            pending[0]["raised"] = type(exc).__name__
        raise
    if pending is not None:
        event, original = pending
        try:
            event.update(
                compared=True,
                expected=snapshot(right),
                left=snapshot(left),
                same_object=original is left,
                equal=result if type(result) is bool else None,
            )
        except Exception as exc:
            event["error"] = type(exc).__name__ + ": " + str(exc)[:160]
    return result


def _finish() -> None:
    # Emission after pytest closes capture keeps passing-node observations visible.
    # The controller checks truncation, duplicates and run identity; this interpreter
    # can still forge its own output, so no consumer may issue a receipt from it.
    record = {
        "schema": "attest.runtime-contract-shadow.v3",
        "events": _events,
        "truncated": _truncated,
        "receipt_eligible": False,
    }
    sys.stdout.write("\n" + PREFIX + json.dumps(record, ensure_ascii=True) + "\n")
    sys.stdout.flush()


atexit.register(_finish)
