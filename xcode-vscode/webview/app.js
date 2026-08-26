// Xcode webview - scenario list + trace tree + agent chat

const init = window.__XCODE_INIT__ || {};
const SERVER_URL = init.serverUrl || 'http://localhost:7800';
const WORKSPACE_ROOT = init.workspaceRoot || '';
const vscode = (typeof acquireVsCodeApi === 'function') ? acquireVsCodeApi() : null;

// === Debug panel ===
document.getElementById('debug-serverUrl').textContent = SERVER_URL;
document.getElementById('debug-workspaceRoot').textContent = WORKSPACE_ROOT || '(none)';
if (init.csp) document.getElementById('debug-csp').textContent = init.csp;
if (init.cspTokens) document.getElementById('debug-tokens').textContent = init.cspTokens.join('\n');

// === fetchWithDetails ===
async function fetchWithDetails(url, options = {}) {
  try {
    const response = await fetch(url, options);
    const ct = response.headers.get('content-type') || '';
    let data = null;
    if (ct.includes('json')) {
      data = await response.json();
    } else {
      data = await response.text();
    }
    return {
      ok: response.ok,
      status: response.status,
      statusText: response.statusText,
      url,
      data,
    };
  } catch (e) {
    let hint = 'Check network / server URL';
    if (e.message && e.message.includes('Failed to fetch')) {
      hint = `Cannot reach backend at ${SERVER_URL}. Verify the Python server is running and CORS allows this origin.`;
    }
    return {
      ok: false,
      error: true,
      errorKind: 'network',
      errorMessage: e.message || String(e),
      url,
      hint,
    };
  }
}

function renderError(err) {
  return `<div class="error">
    <strong>Network error</strong><br>
    URL: <code>${escapeHtml(err.url || '?')}</code><br>
    Kind: ${escapeHtml(err.errorKind || '?')}<br>
    Message: ${escapeHtml(err.errorMessage || '?')}<br>
    Hint: ${escapeHtml(err.hint || '')}
  </div>`;
}

function escapeHtml(s) {
  if (s === null || s === undefined) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function basename(p) {
  if (!p) return '?';
  const parts = p.split('/');
  return parts[parts.length - 1] || p;
}

// === Scenarios ===
async function loadScenarios() {
  const r = await fetchWithDetails(`${SERVER_URL}/api/scenarios`);
  const el = document.getElementById('xc-scenarios');
  const status = document.getElementById('xc-status');
  if (r.error || !r.ok) {
    el.innerHTML = renderError(r);
    status.textContent = 'OFFLINE';
    return;
  }
  const scenarios = (r.data && r.data.scenarios) || [];
  status.textContent = `ONLINE (${scenarios.length})`;
  renderScenarios(scenarios);
}

function renderScenarios(scenarios) {
  const el = document.getElementById('xc-scenarios');
  if (!scenarios.length) {
    el.innerHTML = '<div class="error">No scenarios found</div>';
    return;
  }
  el.innerHTML = scenarios.map(s => `
    <div class="scenario">
      <span class="scenario-name" title="${escapeHtml(s.file)}">${escapeHtml(s.name)}</span>
      <span class="scenario-actions">
        <button class="xc-btn-mini" onclick="runScenario('${escapeHtml(s.name)}')">Run</button>
        <button class="xc-btn-mini" onclick="showTrace('${escapeHtml(s.name)}')">Trace</button>
      </span>
    </div>
  `).join('');
}

window.runScenario = async function(name) {
  const status = document.getElementById('xc-status');
  status.textContent = `Running ${name}...`;
  const r = await fetchWithDetails(`${SERVER_URL}/api/scenarios/${encodeURIComponent(name)}/run`, {
    method: 'POST',
  });
  if (r.error || !r.ok) {
    status.textContent = 'OFFLINE';
    document.getElementById('xc-scenarios').insertAdjacentHTML(
      'beforeend',
      `<div class="error">Run failed: ${escapeHtml(r.errorMessage || r.statusText || '?')}</div>`
    );
    return;
  }
  status.textContent = `${name}: ${r.data.summary.calls} calls`;
  await showTrace(name);
};

window.showTrace = async function(name) {
  const r = await fetchWithDetails(`${SERVER_URL}/api/trace/${encodeURIComponent(name)}`);
  const el = document.getElementById('xc-trace');
  document.getElementById('xc-trace-title').textContent = `Trace · ${name}`;
  if (r.error || !r.ok) {
    el.innerHTML = renderError(r);
    return;
  }
  const entries = (r.data && r.data.entries) || [];
  el.innerHTML = renderTraceTree(entries, r.data);
  bindTraceButtons();
};

// === Trace tree ===
function renderTraceTree(entries, summary) {
  if (!entries.length) {
    return '<div class="error">Empty trace</div>';
  }

  // 配对 call + return
  const callById = new Map();
  const nodes = [];
  for (const e of entries) {
    if (e.type === 'call') {
      callById.set(e.id, {
        id: e.id,
        depth: e.depth || 0,
        qualname: e.qualname || e.func || '?',
        file: e.file || '',
        line: e.line || 0,
        current_line: e.current_line || 0,
        caller: e.caller || null,
        args: e.args || {},
        result: null,
        ts: e.timestamp || 0,
      });
    } else if (e.type === 'return') {
      const node = callById.get(e.id);
      if (node) {
        node.result = e.result;
        node.rt_ts = e.timestamp || 0;
        node.duration_ms = node.rt_ts && node.ts ? Math.round((node.rt_ts - node.ts) * 1000) : 0;
      }
    } else if (e.type === 'exception') {
      const node = callById.get(e.id);
      if (node) {
        node.exception = e.exception;
      }
    }
  }

  const arr = Array.from(callById.values()).sort((a, b) => a.ts - b.ts);
  const html = arr.map(renderTraceNode).join('');
  const summaryHtml = summary ? renderSummary(summary) : '';
  return summaryHtml + html;
}

function renderSummary(s) {
  return `<div class="success">
    Calls: ${s.total_calls}, Returns: ${s.total_returns}, Exceptions: ${s.total_exceptions}, Duration: ${s.duration_ms}ms
  </div>`;
}

function renderTraceNode(n) {
  const indent = n.depth * 18;
  const loc = `${basename(n.file)}:${n.line}`;
  const caller = n.caller && n.caller.caller_func
    ? `<button class="xc-jump-btn jump-call-btn"
              data-file="${escapeHtml(n.caller.caller_file || '')}"
              data-line="${n.caller.caller_line || 0}">
         ↑ ${escapeHtml(basename(n.caller.caller_file || ''))}:${n.caller.caller_line || 0}
       </button>`
    : '';
  const defBtn = `<button class="xc-jump-btn jump-def-btn"
                       data-file="${escapeHtml(n.file)}"
                       data-line="${n.line}">
                    ↓ def:${n.line}
                  </button>`;

  const argsJson = JSON.stringify(n.args || {}, null, 2);
  const argsBlock = Object.keys(n.args || {}).length
    ? `<pre class="xc-detail hidden" id="args-${n.id}">${escapeHtml(argsJson)}</pre>`
    : '';
  const resultBlock = n.result !== null && n.result !== undefined
    ? `<pre class="xc-detail hidden" id="result-${n.id}">${escapeHtml(n.result)}</pre>`
    : '';
  const excBlock = n.exception
    ? `<pre class="xc-detail" id="exc-${n.id}">${escapeHtml(n.exception)}</pre>`
    : '';

  return `
    <div class="trace-node" style="margin-left: ${indent}px;">
      <div class="trace-header">
        <span class="trace-func trace-type-call">${escapeHtml(n.qualname)}</span>
        <span class="trace-loc">${escapeHtml(loc)}</span>
        ${defBtn}
        ${caller}
        <button class="xc-jump-btn toggle-args-btn" data-target="args-${n.id}">args</button>
        ${n.result !== null && n.result !== undefined ? `<button class="xc-jump-btn toggle-result-btn" data-target="result-${n.id}">result</button>` : ''}
        ${n.duration_ms ? `<span class="trace-loc">${n.duration_ms}ms</span>` : ''}
      </div>
      ${argsBlock}
      ${resultBlock}
      ${excBlock}
    </div>
  `;
}

function bindTraceButtons() {
  document.querySelectorAll('.jump-def-btn, .jump-call-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const t = e.currentTarget;
      const file = t.dataset.file;
      const line = parseInt(t.dataset.line || '1', 10);
      if (vscode) {
        vscode.postMessage({ type: 'openFile', path: file, line });
      } else {
        console.log(`[xcode] would open ${file}:${line}`);
      }
    });
  });
  document.querySelectorAll('.toggle-args-btn, .toggle-result-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const target = document.getElementById(e.currentTarget.dataset.target);
      if (target) target.classList.toggle('hidden');
    });
  });
}

// === Refresh ===
document.getElementById('xc-refresh').addEventListener('click', () => {
  loadScenarios();
});

// === Agent chat ===
document.getElementById('xc-send').addEventListener('click', sendAgentMessage);

async function sendAgentMessage() {
  const input = document.getElementById('xc-input');
  const text = (input.value || '').trim();
  if (!text) return;

  const messages = document.getElementById('xc-messages');
  messages.appendChild(msgEl('user', text));
  input.value = '';
  messages.scrollTop = messages.scrollHeight;

  const r = await fetchWithDetails(`${SERVER_URL}/api/agent/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: text }),
  });

  if (r.error || !r.ok) {
    messages.appendChild(msgEl('error', `Failed: ${r.errorMessage || r.statusText}`));
  } else {
    const resp = r.data?.response || '(empty response)';
    messages.appendChild(msgEl('agent', resp));
  }
  messages.scrollTop = messages.scrollHeight;
}

function msgEl(kind, text) {
  const div = document.createElement('div');
  div.className = `msg ${kind}`;
  div.textContent = text;
  return div;
}

// Allow Enter to send (Shift+Enter for newline)
document.getElementById('xc-input').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendAgentMessage();
  }
});

// === Boot ===
loadScenarios();