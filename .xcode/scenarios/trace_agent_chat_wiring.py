"""
Trace XcodeHandler._agent_chat end-to-end.

Spins up the REAL XcodeHandler (via ThreadingHTTPServer) in-process, substitutesa fake `roy-agent` shim in PATH so subprocess.run returns predictable ANSI-
colored structured output, fires an HTTP POST to /api/agent/chat, and lets
XcodeTracer observe the full call chain:

  HTTP POST
    -> XcodeHandler.do_POST
    -> XcodeHandler._read_body
    -> XcodeHandler._agent_chat
        -> subprocess.run(["roy-agent", "act", ...])
        -> XcodeHandler._strip_ansi
        -> XcodeHandler._extract_agent_reply
        -> XcodeHandler._extract_actions
    -> XcodeHandler._send_json

Covers the new HEAD feature that wires the webview Agent chat to the real
xcode-scenario-runner sub-agent.
"""
from __future__ import annotations

import http.client
import json
import os
import shutil
import socket
import sys
import tempfile
import threading

# Make xcode-core/python importable so we import the *real* XcodeHandler.
_XCODE_CORE_PY = os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "xcode-core", "python",
))
if _XCODE_CORE_PY not in sys.path:
    sys.path.insert(0, _XCODE_CORE_PY)

SCENARIO_NAME = "trace_agent_chat_wiring"
START_MARKER = f"[scenario:{SCENARIO_NAME}] start"
END_MARKER = f"[scenario:{SCENARIO_NAME}] end"
FALLBACK_MARKER = f"[scenario:{SCENARIO_NAME}] FALLBACK"


# ----------------------------------------------------------------------------
# Fake `roy-agent` shim
# ----------------------------------------------------------------------------
def _make_fake_roy_agent(tempdir: str) -> None:
    """Drop a tiny bash shim named `roy-agent` in tempdir that prints
    ANSI-colored structured output, including all three action keywords
    (`gen-scenario`, `run-scenario`, `show-trace`) so _extract_actions
    returns a non-empty list."""
    shim = os.path.join(tempdir, "roy-agent")
    body = (
        "#!/usr/bin/env bash\n"
        "set -e\n"
        "cat <<'EOF'\n"
        "\x1b[32m## Result\x1b[0m\n"
        "\x1b[36mWired up xcode-scenario-runner. Will:\x1b[0m\n"
        "\x1b[36m  - gen-scenario for trace_demo\x1b[0m\n"
        "\x1b[36m  - run-scenario trace_demo (with react-fix loop)\x1b[0m\n"
        "\x1b[36m  - show-trace tree\x1b[0m\n"
        "\n"
        "\x1b[33m## Next steps\x1b[0m\n"
        "\x1b[33mWatch the trace tree at /api/trace/trace_demo.\x1b[0m\n"
        "EOF\n"
    )
    with open(shim, "w", encoding="utf-8") as f:
        f.write(body)
    os.chmod(shim, 0o755)


# ----------------------------------------------------------------------------
# Server bootstrap
# ----------------------------------------------------------------------------
def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server(port: int):
    """Start ThreadingHTTPServer with the REAL XcodeHandler on127.0.0.1:port."""
    from xcode_server import ThreadingHTTPServer, XcodeHandler  # type: ignore
    server = ThreadingHTTPServer(("127.0.0.1", port), XcodeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _post_chat(port: int, message: str, timeout: int = 30) -> dict:
    body = json.dumps({"message": message, "timeout": timeout}).encode("utf-8")
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout + 5)
    try:
        conn.request("POST", "/api/agent/chat", body=body, headers={
            "Content-Type": "application/json",
        })
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"_raw": raw, "_status": resp.status}
    finally:
        conn.close()


# ----------------------------------------------------------------------------
# Tracer options shim — replicates the argparse Namespace the real tracer expects# ----------------------------------------------------------------------------
class _TracerOpts:
    def __init__(self, script: str):
        self.include_stdlib = False
        self.filter = []
        self.exclude = []
        self.max_depth = 999
        self.no_args = False
        self.include_dunders = False
        self.script = script


# ----------------------------------------------------------------------------
# Main scenario
# ----------------------------------------------------------------------------
def main():
    print(START_MARKER)
    print(f"[scenario:{SCENARIO_NAME}] cwd = {os.getcwd()}")
    print(f"[scenario:{SCENARIO_NAME}] sys.path head = {sys.path[:3]}")

    # 1) Install fake `roy-agent` so subprocess.run inside _agent_chat succeeds.
    fake_bin = tempfile.mkdtemp(prefix=f"xcode-{SCENARIO_NAME}-bin-")
    _make_fake_roy_agent(fake_bin)
    saved_path = os.environ.get("PATH", "")
    os.environ["PATH"] = fake_bin + os.pathsep + saved_path
    print(f"[scenario:{SCENARIO_NAME}] installed fake roy-agent in {fake_bin}")

    saved_cwd_server_dir = None
    trace_path = None
    response = None
    tracer = None
    server = None
    thread = None

    try:
        # 2) Import the REAL XcodeHandler (or fall back gracefully).
        try:
            from xcode_server import XcodeHandler  # type: ignore  # noqa: F401
            print(f"[scenario:{SCENARIO_NAME}] imported REAL XcodeHandler "
 f"from xcode_server.py")
        except ImportError as e:
            print(FALLBACK_MARKER)
            print(f"[scenario:{SCENARIO_NAME}] cannot import xcode_server: {e}")
            print(f"[scenario:{SCENARIO_NAME}] cannot trace _agent_chat — "
                  f"server module unavailable")
            print(END_MARKER)
            return {"ok": False, "reason": f"xcode_server import failed: {e}"}

        # 3) Import the REAL XcodeTracer (or run untraced).
        try:
            from xcode_trace import XcodeTracer  # type: ignore
            tracer = XcodeTracer(_TracerOpts(__file__))
            # Make all NEW threads (incl. ThreadingHTTPServer's request
            # handlers) inherit this tracer. Available since Python 3.10.
            threading.settrace(tracer)
            print(f"[scenario:{SCENARIO_NAME}] installed XcodeTracer on "
                  f"threading.settrace (new threads inherit it)")
        except ImportError as e:
            print(FALLBACK_MARKER)
            print(f"[scenario:{SCENARIO_NAME}] xcode_trace unavailable: {e}")
            print(f"[scenario:{SCENARIO_NAME}] running untraced — call "
                  f"chain will not be recorded")
            tracer = None

        # 4) Boot the real HTTP server in-process.
        port = _pick_free_port()
        server, thread = _start_server(port)
        print(f"[scenario:{SCENARIO_NAME}] server listening on "
              f"http://127.0.0.1:{port}")

        # 5) Fire HTTP POST — this drives the full _agent_chat pipeline.
        response = _post_chat(
            port,
            message="please wire up xcode-scenario-runner for trace_demo",
            timeout=30,
        )
        print(f"[scenario:{SCENARIO_NAME}] POST /api/agent/chat returned "
              f"keys = {sorted(response.keys())}")
        print(f"[scenario:{SCENARIO_NAME}] subagent        = "
              f"{response.get('subagent')!r}")
        print(f"[scenario:{SCENARIO_NAME}] subagent_exit   = "
              f"{response.get('subagent_exit')!r}")
        print(f"[scenario:{SCENARIO_NAME}] actions         = "
              f"{response.get('actions')!r}")
        rt = response.get('response', '')
        print(f"[scenario:{SCENARIO_NAME}] response head = "
              f"{rt[:120].replace(chr(10), ' / ') if rt else rt!r}")
        if response.get('stderr_tail'):
            print(f"[scenario:{SCENARIO_NAME}] stderr_tail     = "
                  f"{response['stderr_tail'][:120]!r}")

    finally:
        # 6) Teardown: stop server, restore PATH, drop fake bin.
        if server is not None:
            try:
                server.shutdown()
                server.server_close()
            except Exception as e:
                print(f"[scenario:{SCENARIO_NAME}] server teardown error: {e}")
        if thread is not None:
            thread.join(timeout=2)
        os.environ["PATH"] = saved_path
        shutil.rmtree(fake_bin, ignore_errors=True)

        # 7) Save the trace (or report no-tracer fallback).
        if tracer is not None:
            fd, trace_path = tempfile.mkstemp(
                suffix=".json",
                prefix=f"xcode-{SCENARIO_NAME}-",
            )
            os.close(fd)
            tracer.save(trace_path)
            print(f"[scenario:{SCENARIO_NAME}] trace saved at {trace_path}")
            print(f"[scenario:{SCENARIO_NAME}] traced calls by qualname = "
                  f"{dict(sorted(tracer.call_count.items()))}")
            print(f"[scenario:{SCENARIO_NAME}] exception_count = "
                  f"{tracer.exception_count}")
        else:
            print(f"[scenario:{SCENARIO_NAME}] no trace file produced "
                  f"(tracer unavailable)")

    print(END_MARKER)
    return {
        "ok": True,
        "response": response,
        "trace_path": trace_path,
    }


if __name__ == "__main__":
    main()
