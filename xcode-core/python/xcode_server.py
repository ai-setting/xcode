"""Xcode Backend Server - lightweight HTTP API for VSCode/Cursor plugin.

Uses only Python stdlib (http.server + json) — no external dependencies.
Designed to be launched by the VSCode extension or run manually.

Endpoints:
  GET  /                       — root info
  GET  /api/scenarios          — list scenario files
  POST /api/scenarios/{name}/run — run scenario through tracer
  GET  /api/trace/{name}       — fetch trace JSON
  POST /api/agent/chat         — agent chat stub
  GET  /api/health             — health check
"""
import sys
import os
import json
import time
import argparse
import subprocess
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

TRACES_DIR = Path('/tmp/xcode_traces')
TRACES_DIR.mkdir(exist_ok=True)
SCENARIOS_DIR = Path('/home/dzk/work/codework/personal/roy_world/xcode/xcode-tests/scenarios')
SERVER_DIR = Path(os.path.dirname(os.path.abspath(__file__)))


class XcodeHandler(BaseHTTPRequestHandler):
    """HTTP request handler with simple routing."""

    # Quiet logging
    def log_message(self, fmt, *args):
        sys.stderr.write(f"[xcode-server] {self.address_string()} - {fmt % args}\n")

    # ---- helpers ----
    def _send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text, status=200, content_type='text/plain; charset=utf-8'):
        body = text.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get('Content-Length') or 0)
        if not length:
            return {}
        raw = self.rfile.read(length).decode('utf-8')
        try:
            return json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return {}

    # ---- HTTP verbs ----
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/') or '/'

        if path == '/' or path == '':
            return self._send_json({
                'name': 'xcode',
                'version': '0.1.0',
                'api': [
                    'GET  /api/health',
                    'GET  /api/scenarios',
                    'POST /api/scenarios/{name}/run',
                    'GET  /api/trace/{name}',
                    'POST /api/agent/chat',
                ],
            })

        if path == '/api/health':
            return self._send_json({'status': 'ok', 'time': time.time()})

        if path == '/api/scenarios':
            return self._send_json({'scenarios': self._list_scenarios()})

        if path.startswith('/api/trace/'):
            name = path[len('/api/trace/'):]
            return self._get_trace(name)

        if path == '/favicon.ico':
            return self._send_text('', status=204)

        return self._send_json({'error': f'Not found: {path}'}, status=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/') or '/'

        if path.startswith('/api/scenarios/') and path.endswith('/run'):
            name = path[len('/api/scenarios/'):-len('/run')]
            return self._run_scenario(name)

        if path == '/api/agent/chat':
            body = self._read_body()
            return self._agent_chat(body)

        return self._send_json({'error': f'Not found: {path}'}, status=404)

    # ---- handlers ----
    def _list_scenarios(self):
        scenarios = []
        if SCENARIOS_DIR.exists():
            for f in sorted(SCENARIOS_DIR.glob('*.py')):
                scenarios.append({'name': f.stem, 'file': str(f)})
        return scenarios

    def _run_scenario(self, name: str):
        scenario_file = SCENARIOS_DIR / f'{name}.py'
        if not scenario_file.exists():
            return self._send_json({'error': f'Scenario not found: {name}'}, status=404)

        output = TRACES_DIR / f'{name}.json'
        trace_runner = SERVER_DIR / 'xcode_trace.py'
        if not trace_runner.exists():
            return self._send_json({'error': f'Trace runner not found: {trace_runner}'}, status=500)

        try:
            result = subprocess.run(
                [sys.executable, str(trace_runner), str(scenario_file), '--output', str(output)],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            return self._send_json({'error': 'Scenario timeout (120s)'}, status=500)

        if result.returncode != 0 and not output.exists():
            return self._send_json({
                'error': 'Scenario failed',
                'stderr': result.stderr[-1000:],
                'stdout': result.stdout[-500:],
            }, status=500)

        try:
            with open(output) as f:
                trace = json.load(f)
        except Exception as e:
            return self._send_json({'error': f'Failed to load trace: {e}'}, status=500)

        return self._send_json({
            'status': 'ok',
            'trace_file': str(output),
            'summary': {
                'calls': trace.get('total_calls', 0),
                'returns': trace.get('total_returns', 0),
                'exceptions': trace.get('total_exceptions', 0),
            },
            'stdout_tail': result.stdout[-500:],
        })

    def _get_trace(self, name: str):
        trace_file = TRACES_DIR / f'{name}.json'
        if not trace_file.exists():
            return self._send_json({'error': f'Trace not found: {name}'}, status=404)
        try:
            with open(trace_file) as f:
                data = json.load(f)
            return self._send_json(data)
        except Exception as e:
            return self._send_json({'error': f'Failed to read trace: {e}'}, status=500)

    def _agent_chat(self, body: dict):
        message = body.get('message', '').strip()
        if not message:
            return self._send_json({'error': 'Empty message'}, status=400)
        return self._send_json({
            'response': (
                f'Received: "{message[:200]}".\n\n'
                'Suggested steps:\n'
                '1) Describe the function you want to test (e.g. "test ontology build + reason").\n'
                '2) Click "Run" next to a scenario in the sidebar.\n'
                '3) View the trace tree — every span shows where the function is defined AND where it was called from.\n'
                '4) Click ↓def or ↑call to jump to the source location.'
            ),
            'actions': [],
        })


def main():
    parser = argparse.ArgumentParser(description='Xcode Backend HTTP Server')
    parser.add_argument('--port', type=int, default=7800)
    parser.add_argument('--host', default='127.0.0.1')
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), XcodeHandler)
    print(f"[xcode-server] Listening on http://{args.host}:{args.port}")
    print(f"[xcode-server] Scenarios: {SCENARIOS_DIR}")
    print(f"[xcode-server] Traces:    {TRACES_DIR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n[xcode-server] Shutting down...')
        server.server_close()


if __name__ == '__main__':
    main()