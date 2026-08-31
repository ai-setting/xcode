"""
Trace the xcode tracer pipeline end-to-end.

Builds a tiny synthetic call chain (parent -> child -> grandchild), drives
XcodeTracer via sys.settrace, then serializes + saves the trace JSON.
This is the "meta" scenario - it exercises the very tracer used by xcode.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

# Make xcode-core/python importable so we use the *real* tracer.
XCODE_CORE_PY = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "xcode-core", "python",
)
XCODE_CORE_PY = os.path.abspath(XCODE_CORE_PY)
if XCODE_CORE_PY not in sys.path:
    sys.path.insert(0, XCODE_CORE_PY)


def grandchild(x: int) -> int:
    """innermost call - gives the trace depth > 1"""
    return x * 2


def child(x: int) -> int:
    """middle call - composes two grandchildren"""
    a = grandchild(x)
    b = grandchild(x + 1)
    return a + b


def parent(x: int) -> int:
    """outer call - the trace entry point"""
    return child(x) + 1


def run_with_tracer() -> dict:
    """Drive XcodeTracer over parent() and return the saved trace."""
    from xcode_trace import XcodeTracer  # type: ignore

    tracer = XcodeTracer({"include_stdlib": False})

    def _driver(frame, event, arg):
        return tracer(frame, event, arg)

    sys.settrace(_driver)
    try:
        result = parent(7)
    finally:
        sys.settrace(None)

    fd, path = tempfile.mkstemp(suffix=".json", prefix="xcode-tracer-meta-")
    os.close(fd)
    tracer.save(path)

    with open(path, "r", encoding="utf-8") as f:
        trace_obj = json.load(f)

    print(f"[scenario] parent(7) = {result}")
    print(f"[scenario] trace entries = {len(trace_obj.get('calls', []))}")
    print(f"[scenario] trace saved at {path}")
    return {"result": result, "entries": len(trace_obj.get('calls', [])), "path": path}


if __name__ == "__main__":
    print("=== Trace xcode-tracer meta scenario ===")
    out = run_with_tracer()
    print(f"=== Done: entries={out['entries']} result={out['result']} ===")
