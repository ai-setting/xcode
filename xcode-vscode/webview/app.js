// Xcode webview - scenario list + trace tree + agent chat

const init = window.__XCODE_INIT__ || {};
const SERVER_URL = init.serverUrl || 'http://localhost:7800';
const vscode = (typeof acquireVsCodeApi === 'function') ? acquireVsCodeApi() : null;

function renderDebug() {
  const serverEl = document.getElementById('debug-serverUrl');
  const cspEl = document.getElementById('debug-csp');
  const tokensEl = document.getElementById('debug-tokens');
  
  if (serverEl) serverEl.textContent = SERVER_URL || '(not set)';
  if (cspEl) cspEl.textContent = init.csp || '(not set)';
  if (tokensEl && init.cspTokens) tokensEl.textContent = init.cspTokens.join('\n');
}


// === Debug panel ===
document.getElementById('debug-serverUrl').textContent = SERVER_URL;
if (init.csp) document.getElementById('debug-csp').textContent = init.csp;
if (init.cspTokens) document.getElementById('debug-tokens').textContent = init.cspTokens.join('\n');

// === fetchWithDetails ===
async function fetchWithDetails(url, options = {}) {
  // 支持超时（避免长时间挂起）
  const timeoutMs = options.timeout || 600000;  // 默认 10 分钟
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  
  try {
    const response = await fetch(url, { ...options, signal: controller.signal });
    clearTimeout(timeoutId);
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
    clearTimeout(timeoutId);
    let hint = 'Check network / server URL';
    let errorKind = 'network';
    if (e.name === 'AbortError') {
      errorKind = 'timeout';
      hint = `Request exceeded ${timeoutMs}ms timeout. Try a simpler request.`;
    } else if (e.message && e.message.includes('Failed to fetch')) {
      hint = `Cannot reach backend at ${SERVER_URL}. Verify the Python server is running and CORS allows this origin.`;
    }
    return {
      ok: false,
      error: true,
      errorKind: errorKind,
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

renderDebug();

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
  const scenariosDir = (r.data && r.data.scenarios_dir) || '';
  const tracesDir = (r.data && r.data.traces_dir) || '';
  status.textContent = `ONLINE (${scenarios.length})`;
  renderScenarios(scenarios, scenariosDir, tracesDir);
}

function renderScenarios(scenarios, scenariosDir, tracesDir) {
  const el = document.getElementById('xc-scenarios');
  // Render scenarios dir info (helps user verify backend is watching the right folder)
  const dirInfo = (scenariosDir || tracesDir)
    ? `<div class="xc-dir-info">📁 ${escapeHtml(scenariosDir || '(unset)')}<br>📊 ${escapeHtml(tracesDir || '(unset)')}</div>`
    : '';
  if (!scenarios.length) {
    el.innerHTML = dirInfo + '<div class="error">No scenarios found in this directory</div>';
    return;
  }
  el.innerHTML = dirInfo + scenarios.map(s => `
    <div class="scenario">
      <span class="scenario-name" title="${escapeHtml(s.file)}">${escapeHtml(s.name)}</span>
      <span class="scenario-actions">
        <button class="xc-btn-mini" data-action="run" data-name="${escapeHtml(s.name)}">Run</button>
        <button class="xc-btn-mini" data-action="trace" data-name="${escapeHtml(s.name)}">Trace</button>
      </span>
    </div>
  `).join('');
  
  // 用 addEventListener 绑定（避免内联 onclick 被 CSP 阻止）
  el.querySelectorAll('[data-action="run"]').forEach(btn => {
    btn.addEventListener('click', () => window.runScenario(btn.dataset.name));
  });
  el.querySelectorAll('[data-action="trace"]').forEach(btn => {
    btn.addEventListener('click', () => window.showTrace(btn.dataset.name));
  });
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
  const indent = n.depth * 24;
  const loc = `${basename(n.file)}:${n.line}`;
  // Tree connector（│ 树形连接符）
  const treePrefix = n.depth > 0 ? '<span class="trace-tree-prefix">' + '│ '.repeat(n.depth) + '└─</span> ' : '';
  // Caller 信息
  const caller = n.caller && n.caller.caller_func
    ? `<span class="trace-caller">from ${escapeHtml(basename(n.caller.caller_file || '?'))}:${n.caller.caller_line || 0}</span>`
    : '<span class="trace-caller">root</span>';
  // 跳转按钮
  const defBtn = `<button class="xc-jump-btn jump-def-btn"
                       data-file="${escapeHtml(n.file)}"
                       data-line="${n.line}"
                       title="Jump to definition">
                    ↓ def
                  </button>`;
  const callerBtn = n.caller && n.caller.caller_file
    ? `<button class="xc-jump-btn jump-call-btn"
                 data-file="${escapeHtml(n.caller.caller_file || '')}"
                 data-line="${n.caller.caller_line || 0}"
                 title="Open caller in split">
              ↑ call
            </button>`
    : '';
  
  // 详情块
  const argsJson = JSON.stringify(n.args || {}, null, 2);
  const argsBlock = Object.keys(n.args || {}).length
    ? `<pre class="xc-detail hidden" id="args-${n.id}">args: ${escapeHtml(argsJson)}</pre>`
    : '';
  const resultBlock = n.result !== null && n.result !== undefined
    ? `<pre class="xc-detail hidden" id="result-${n.id}">result: ${escapeHtml(n.result)}</pre>`
    : '';
  const excBlock = n.exception
    ? `<pre class="xc-detail">exception: ${escapeHtml(n.exception)}</pre>`
    : '';
  
  // 状态图标
  let statusIcon = '●';
  let statusClass = 'trace-ok';
  if (n.exception) {
    statusIcon = '✗';
    statusClass = 'trace-err';
  }
  
  return `
    <div class="trace-node ${statusClass}" data-depth="${n.depth}">
      <div class="trace-header" style="padding-left: ${indent}px;">
        ${treePrefix}<span class="trace-status">${statusIcon}</span>
        <span class="trace-func">${escapeHtml(n.qualname)}</span>
        <span class="trace-loc">${escapeHtml(loc)}</span>
        ${caller}
        <span class="trace-spacer"></span>
        ${defBtn}
        ${callerBtn}
        <button class="xc-jump-btn toggle-args-btn" data-target="args-${n.id}">args</button>
        ${n.result !== null && n.result !== undefined ? `<button class="xc-jump-btn toggle-result-btn" data-target="result-${n.id}">result</button>` : ''}
        ${n.duration_ms ? `<span class="trace-duration">${n.duration_ms}ms</span>` : ''}
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
  const status = document.getElementById('xc-status');

  messages.appendChild(msgEl('user', text));
  input.value = '';
  messages.scrollTop = messages.scrollHeight;

  // 显示 "typing..." 占位
  const placeholderId = 'agent-placeholder-' + Date.now();
  const placeholder = msgEl('agent', '⏳ Calling xcode-scenario-runner sub-agent (may take up to 5 min)...');
  placeholder.id = placeholderId;
  messages.appendChild(placeholder);
  messages.scrollTop = messages.scrollHeight;
  if (status) status.textContent = 'Agent thinking...';

  const r = await fetchWithDetails(`${SERVER_URL}/api/agent/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: text, timeout: 600 }),
  }, {
    timeout: 600000,  // 浏览器侧 10 分钟超时
  });

  // 移除 placeholder
  const ph = document.getElementById(placeholderId);
  if (ph) ph.remove();

  if (r.error || !r.ok) {
    // 显示后端返回的错误信息（如果有）+ 状态码
    let errMsg = r.errorMessage || r.statusText || '?';
    if (r.data && r.data.response) {
      errMsg = r.data.response;
    } else if (r.data && r.data.error) {
      errMsg = r.data.error;
    }
    const kindLabel = {
      'timeout': '⏱ 超时',
      'network': '🌐 网络',
    }[r.errorKind] || '❌';
    messages.appendChild(msgEl('error', `${kindLabel} [${r.status || '?'}] ${errMsg}`));
    if (status) status.textContent = `Agent failed: ${r.status || ''}`;
  } else {
    const resp = r.data?.response || '(empty response)';
    const actions = r.data?.actions || [];
    const subagent = r.data?.subagent || 'agent';
    const exit = r.data?.subagent_exit;

    // 渲染 agent 回复 + 可选 action 按钮
    const div = document.createElement('div');
    div.className = 'msg agent';
    // 把 markdown-ish text 转成 <pre> 保留换行
    const pre = document.createElement('pre');
    pre.className = 'xc-agent-reply';
    pre.textContent = resp;
    div.appendChild(pre);

    // header: which sub-agent + exit code
    if (subagent || exit !== undefined) {
      const meta = document.createElement('div');
      meta.className = 'xc-agent-meta';
      const exitOk = exit === 0 ? '✅' : (exit === undefined ? '🔵' : '⚠️');
      meta.textContent = `${exitOk} sub-agent: ${subagent}${exit !== undefined ? ` (exit=${exit})` : ''}`;
      div.appendChild(meta);
    }

    // action 按钮（如果有）
    if (actions.length > 0) {
      const actionsBar = document.createElement('div');
      actionsBar.className = 'xc-agent-actions';
      actions.forEach((a) => {
        const btn = document.createElement('button');
        btn.className = 'xc-jump-btn xc-action-btn';
        btn.dataset.action = a.type;
        btn.textContent = a.label || a.type;
        btn.addEventListener('click', () => handleAgentAction(a.type));
        actionsBar.appendChild(btn);
      });
      div.appendChild(actionsBar);
    }

    messages.appendChild(div);
    if (status) status.textContent = `Agent done (exit=${exit ?? 'n/a'})`;
  }
  messages.scrollTop = messages.scrollHeight;
}

async function handleAgentAction(action) {
  // agent 回复中提到的 actions：把对应的命令塞回输入框，让用户点 send 执行。
  // 或者更激进：直接 fetch /api/scenarios/{name}/{action}
  const status = document.getElementById('xc-status');
  const input = document.getElementById('xc-input');

  // 如果 action 有具体 target（run-scenario / show-trace），从最近一次 agent 回复解析 scenario 名字
  const lastReply = document.querySelector('.xc-agent-reply');
  const scenarioName = lastReply ? extractScenarioName(lastReply.textContent || '') : '';

  if (action === 'gen-scenario') {
    if (input) {
      input.value = 'generate a scenario for the latest trace target';
      input.focus();
      if (status) status.textContent = 'Edit prompt and press Enter';
    }
    return;
  }

  if (action === 'run-scenario' && scenarioName) {
    if (status) status.textContent = `Running scenario ${scenarioName}...`;
    if (window.runScenario) await window.runScenario(scenarioName);
    return;
  }

  if (action === 'show-trace' && scenarioName) {
    if (status) status.textContent = `Showing trace ${scenarioName}...`;
    if (window.showTrace) await window.showTrace(scenarioName);
    return;
  }

  // fallback：塞回输入框
  if (input) {
    input.value = `${action} ${scenarioName}`.trim();
    input.focus();
    if (status) status.textContent = 'Edit prompt and press Enter';
  }
}

function extractScenarioName(text) {
  // 优先匹配 backtick 包裹的 scenario 名字
  const m = text.match(/`([a-z0-9_\-]+)`/i);
  return m ? m[1] : '';
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

// === Polling: scenarios 自动同步 ===
let lastMtime = 0;

async function pollScenarios() {
  try {
    const r = await fetchWithDetails(`${SERVER_URL}/api/scenarios/mtime`);
    if (r.error || !r.ok) return;
    const newMtime = (r.data && r.data.mtime) || 0;
    if (newMtime !== lastMtime) {
      lastMtime = newMtime;
      loadScenarios();
    }
  } catch (e) {
    // 静默失败，不打扰用户
  }
}

// 每 5 秒轮询
setInterval(pollScenarios, 5000);

// === Boot ===
loadScenarios();
