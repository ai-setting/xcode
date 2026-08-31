"""
Minimal hello-world trace scenario: greet() -> format() -> return.

Defines a small real call chain in this file, then drives the REAL xcode
tracer over it (when available) so the trace tree shows the call edges
between greet and format. Falls back to an untraced run if xcode_trace
cannot be imported.
"""
from __future__ import annotations

import os
import sys

SCENARIO_NAME = "hello_test"
START_MARKER = f"[scenario:{SCENARIO_NAME}] start"
END_MARKER = f"[scenario:{SCENARIO_NAME}] end"
FALLBACK_MARKER = f"[scenario:{SCENARIO_NAME}] FALLBACK"


def format(name: str) -> str:
    """Inner helper - formats the greeting fragment."""
    return f"hello, {name}!"


def greet(name: str) -> str:
    """Outer entry - composes format() into the final greeting."""
    fragment = format(name)
    return f"Greeting -> {fragment}"


def run_with_tracer() -> dict:
    """Run greet('world') under the REAL xcode tracer."""
    from xcode_trace import XcodeTracer  # type: ignore

    tracer = XcodeTracer({"include_stdlib": False})

    def _driver(frame, event, arg):
        return tracer(frame, event, arg)

    sys.settrace(_driver)
    try:
        result = greet("world")
    finally:
        sys.settrace(None)

    return {"result": result, "trace": tracer}


def main():
    print(START_MARKER)
    print(f"[scenario:{SCENARIO_NAME}] greet -> format -> return")

    tracer = None
    trace_path = None

    try:
        from xcode_trace import XcodeTracer  # type: ignore  # noqa: F401
        tracer_available = True
    except ImportError as e:
        tracer_available = False
        print(FALLBACK_MARKER)
        print(f"[scenario:{SCENARIO_NAME}] xcode_trace unavailable: {e}")
        print(f"[scenario:{SCENARIO_NAME}] running untraced - call chain "
              f"will not be recorded")

    if tracer_available:
        outcome = run_with_tracer()
        result = outcome["result"]
        tracer = outcome["trace"]
        print(f"[scenario:{SCENARIO_NAME}] greet('world') = {result}")
        print(f"[scenario:{SCENARIO_NAME}] traced calls by qualname = "
              f"{dict(sorted(tracer.call_count.items()))}")

        import tempfile
        fd, trace_path = tempfile.mkstemp(
            suffix=".json", prefix=f"xcode-{SCENARIO_NAME}-",
        )
        os.close(fd)
        tracer.save(trace_path)
        print(f"[scenario:{SCENARIO_NAME}] trace saved at {trace_path}")
    else:
        # Untraced fallback - still exercise the call chain.
        result = greet("world")
        print(f"[scenario:{SCENARIO_NAME}] greet('world') = {result}")

    print(END_MARKER)
    return {"result": result, "trace_path": trace_path}


if __name__ == "__main__":
    main()
