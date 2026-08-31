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
                    'GET  /api/scenarios/mtime',
                    'POST /api/scenarios/{name}/run',
                    'GET  /api/trace/{name}',
                    'POST /api/agent/chat',
                ],
            })

        if path == '/api/health':
            return self._send_json({'status': 'ok', 'time': time.time()})

        if path == '/api/scenarios':
            return self._send_json({'scenarios': self._list_scenarios()})

        if path == '/api/scenarios/mtime':
            return self._send_json(self._scenarios_mtime())

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

    def _scenarios_mtime(self):
        """返回 scenarios 目录的最新 mtime + count（用于 webview 轮询）"""
        if not SCENARIOS_DIR.exists():
            return {'mtime': 0, 'count': 0}
        files = list(SCENARIOS_DIR.glob('*.py'))
        if not files:
            return {'mtime': 0, 'count': 0}
        mtime = max(f.stat().st_mtime for f in files)
        return {'mtime': mtime, 'count': len(files)}

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
        """真正调用 roy-agent xcode-scenario-runner sub-agent。

        通过 subprocess 调 `roy-agent act -a xcode-scenario-runner <message>`，
        解析 stdout/stderr，提取 actions（gen-scenario / run-scenario / show-trace）。
        """
        message = body.get('message', '').strip()
        if not message:
            return self._send_json({'error': 'Empty message'}, status=400)

        # 5 分钟超时。sub-agent 可能要 gen-scenario + run-scenario + react-fix loop
        timeout_sec = int(body.get('timeout', 300))

        # 自动追加 cwd hint（让 agent 知道在 xcode 项目目录跑）
        cwd = body.get('cwd') or str(SERVER_DIR.parent.parent)  # /home/.../xcode
        # 在 prompt 里告诉 agent 工作目录
        enriched_message = (
            f"{message}\n\n"
            f"[Context] cwd={cwd} (use this as the target git repo for xcode CLI)\n"
            f"[Context] Xcode backend already serving at http://localhost:7800\n"
            f"[Context] Scenarios dir: {SCENARIOS_DIR}\n"
            f"[Context] Traces dir: {TRACES_DIR}\n"
            f"[Context] If you want to add/trace scenarios in this workspace, "
            f"cd into it and use `xcode init` / `xcode gen-scenario` / `xcode run-scenario` / `xcode show-trace`."
        )

        try:
            result = subprocess.run(
                [
                    'roy-agent', 'act',
                    '-a', 'xcode-scenario-runner',
                    enriched_message,
                    '--no-reasoning',
                    '--no-tool-calls',
                    '--quiet',
                ],
                capture_output=True,
                text=True,
                timeout=timeout_sec,
                cwd=cwd,
                env={**os.environ, 'NO_COLOR': '1'},  # strip ANSI colors
            )
        except subprocess.TimeoutExpired:
            return self._send_json({
                'response': (
                    f'⏱ Sub-agent timed out after {timeout_sec}s. '
                    f'Try a simpler request or break it into steps.'
                ),
                'subagent': 'xcode-scenario-runner',
                'actions': [],
            }, status=504)
        except FileNotFoundError:
            return self._send_json({
                'response': (
                    '❌ `roy-agent` CLI not found in PATH. '
                    'Install it or set PATH to include the roy-agent binary.'
                ),
                'subagent': 'xcode-scenario-runner',
                'actions': [],
            }, status=500)
        except Exception as e:
            return self._send_json({
                'response': f'❌ Sub-agent error: {e}',
                'subagent': 'xcode-scenario-runner',
                'actions': [],
            }, status=500)

        # 解析输出
        stdout = (result.stdout or '').strip()
        stderr = (result.stderr or '').strip()

        # 提取最后一段干净文本（去掉 ANSI 控制字符 + 空行）
        clean_stdout = self._strip_ansi(stdout)
        clean_stderr = self._strip_ansi(stderr)

        # 如果 stdout 看起来是结构化（包含 reasoning/tool-calls），提取 ## Result 之后的部分
        response_text = self._extract_agent_reply(clean_stdout)

        if result.returncode != 0 and not response_text:
            response_text = f'[sub-agent exit={result.returncode}]\n{clean_stderr or clean_stdout or "(no output)"}'

        if not response_text:
            response_text = '(sub-agent produced no response)'

        # 截断太长输出
        if len(response_text) > 30000:
            response_text = response_text[:30000] + '\n\n... (truncated, see server log for full output)'

        actions = self._extract_actions(clean_stdout + '\n' + clean_stderr)

        return self._send_json({
            'response': response_text,
            'subagent': 'xcode-scenario-runner',
            'subagent_exit': result.returncode,
            'actions': actions,
            'stderr_tail': clean_stderr[-500:] if clean_stderr else '',
        })

    def _strip_ansi(self, text: str) -> str:
        """去掉 ANSI 控制字符（颜色码等）"""
        import re
        if not text:
            return ''
        ansi_re = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')
        return ansi_re.sub('', text)

    def _extract_agent_reply(self, text: str) -> str:
        """从 sub-agent stdout 提取干净回复。

        roy-agent act 输出格式大致是：
          <reasoning>...
          ## Result
          <final answer>
          ## Next steps
          ...
        """
        if not text:
            return ''
        # 优先提取 ## Result 之后到下一个 ## 之前的部分
        import re
        m = re.search(r'##\s*Result\s*\n+(.*?)(?=\n##\s|\Z)', text, re.DOTALL | re.IGNORECASE)
        if m:
            return m.group(1).strip()
        # 否则返回整个文本（去掉 leading 空白）
        return text.strip()

    def _extract_actions(self, text: str) -> list:
        """从 sub-agent 回复中提取 action 提示（gen-scenario / run-scenario / show-trace）。"""
        actions = []
        lower = text.lower()
        # 如果 agent 提到了具体 scenario 名字和命令，提取它们
        if 'gen-scenario' in lower or 'generate scenario' in lower:
            actions.append({'type': 'gen-scenario', 'label': '🔧 Generate Scenario'})
        if 'run-scenario' in lower or 'run scenario' in lower or 'react-fix' in lower:
            actions.append({'type': 'run-scenario', 'label': '▶ Run Scenario'})
        if 'show-trace' in lower or 'show trace' in lower or 'trace tree' in lower:
            actions.append({'type': 'show-trace', 'label': '🌳 Show Trace Tree'})
        return actions


def main():
    parser = argparse.ArgumentParser(description='Xcode Backend HTTP Server')
    parser.add_argument('--port', type=int, default=7800)
    parser.add_argument('--host', default='0.0.0.0')
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