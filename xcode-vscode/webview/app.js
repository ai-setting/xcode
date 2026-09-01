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

// 全局 trace 节点索引（按 id），供 toggleTraceChildren 使用
let traceNodeById = {};

function renderTraceTree(entries, summary) {
  if (!entries.length) {
    return '<div class="error">Empty trace</div>';
  }

  // 配对 call + return
  const callById = new Map();
  const nodes = [];
  for (const e of entries) {
    if (e.type === 'call') {
      const depth = e.depth || 0;
      callById.set(e.id, {
        id: e.id,
        depth,
        qualname: e.qualname || e.func || '?',
        file: e.file || '',
        line: e.line || 0,
        current_line: e.current_line || 0,
        caller: e.caller || null,
        args: e.args || {},
        result: null,
        ts: e.timestamp || 0,
        children: [],
        // 默认折叠策略：depth > 1 默认折叠
        _collapsed: depth > 1,
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

  // 构造嵌套 tree：用 caller.caller_id 关联父子
  // 加 robust fallback：v0.3.17 改 caller 检测（_unwrap_frame 跳过 wrapper）后，
  // 某些节点的 caller_id 可能指向没被 trace 的函数（如 sync_wrapper），
  // callById 里找不到，会被错误当 root，tree 结构错乱 → 折叠按钮失效。
  // 两遍构建：
  //   第一遍：caller_id 直接关联
  //   第二遍：剩下的节点按 depth 找父节点（depth=n.depth-1 的最后 sibling）
  const arr = Array.from(callById.values()).sort((a, b) => a.ts - b.ts);
  const roots = [];
  // 索引：便于后续根据 id 找节点
  traceNodeById = {};
  arr.forEach(n => { traceNodeById[n.id] = n; });

  // 第一遍：caller_id 关联
  for (const n of arr) {
    const callerId = n.caller && n.caller.caller_id;
    if (callerId != null && callById.has(callerId)) {
      const parent = callById.get(callerId);
      parent.children.push(n);
      n._parent = parent;
    }
  }
  // 第二遍：fallback——按 depth 找父节点
  // 对于还没被分配 parent 的节点，找 depth = n.depth - 1 的最近节点作为父节点。
  // 这样处理 v0.3.17 caller 检测改动后的"orphan"节点：
  //   - 它们没找到 caller_id，但 trace 顺序还保留了 depth 信息
  //   - 用深度减 1 的最近节点作为父节点，可以保证 tree 结构稳定、折叠按钮正常
  // 同时跟踪每个深度最近出现的节点（lastByDepth），fallback 时直接查表
  const lastByDepth = {};
  for (const n of arr) {
    lastByDepth[n.depth] = n;
  }
  for (const n of arr) {
    if (n._parent) continue;
    if (n.depth === 0) {
      roots.push(n);
      continue;
    }
    // 找最近的、不是 fallback 上来的 depth = n.depth - 1 节点
    let parent = null;
    for (let d = n.depth - 1; d >= 0; d--) {
      const candidate = lastByDepth[d];
      if (candidate && !candidate._isFallback) {
        parent = candidate;
        break;
      }
    }
    if (parent) {
      parent.children.push(n);
      n._parent = parent;
      // 标记 n 为 fallback 节点：避免更深层 orphan 把它当父节点
      n._isFallback = true;
    } else {
      // 实在找不到（truly orphan），就当 root
      roots.push(n);
    }
  }

  // 清掉临时标记
  arr.forEach(n => { delete n._parent; delete n._isFallback; });
  const html = roots.map(r => renderTraceNode(r, 0, [])).join('');
  const summaryHtml = summary ? renderSummary(summary) : '';
  return summaryHtml + html;
}

function renderSummary(s) {
  return `<div class="success">
    Calls: ${s.total_calls}, Returns: ${s.total_returns}, Exceptions: ${s.total_exceptions}, Duration: ${s.duration_ms}ms
  </div>`;
}

function renderTraceNode(n, depth, ancestors) {
  const loc = `${basename(n.file)}:${n.line}`;
  // 折叠按钮：只有有子节点的节点才显示 ▼/▶
  const hasChildren = n.children && n.children.length > 0;
  const collapseBtn = hasChildren
    ? `<button class="xc-collapse-btn" data-node-id="${n.id}" data-collapsed="${n._collapsed ? '1' : '0'}" title="${n._collapsed ? 'Expand children' : 'Collapse children'}">${n._collapsed ? '▶' : '▼'}</button>`
    : `<span class="xc-collapse-spacer"></span>`;
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

  // ancestors：祖先节点 id 列表（用于 CSS 折叠子节点）
  const ancestorsAttr = ancestors.length ? ` data-ancestors="${ancestors.join(',')}"` : '';

  // 继承隐藏：如果任一祖先 _collapsed，子节点初始就 display:none
  // 自己 _collapsed 不会让自己隐藏（自己的 ▶/▼ 按钮仍可见）
  let displayStyle = '';
  for (const ancestorId of ancestors) {
    const ancestor = traceNodeById[ancestorId];
    if (ancestor && ancestor._collapsed) {
      displayStyle = 'display: none;';
      break;
    }
  }
  // 如果 _collapsed，渲染的 children 会通过 CSS 隐藏（不需要 skip rendering）

  // data-parent-id：父节点 id（如果非 root），便于 CSS display 切换
  const parentAttr = ancestors.length > 0
    ? ` data-parent-id="${ancestors[ancestors.length - 1]}"`
    : '';

  let html = `
    <div class="trace-node ${statusClass}" data-depth="${depth}" data-node-id="${n.id}"${ancestorsAttr}${parentAttr} style="${displayStyle}">
      <div class="trace-header">
        ${collapseBtn}
        <span class="trace-status">${statusIcon}</span>
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

  // 始终渲染子节点（不用 _collapsed 跳过）
  // 子节点初始可见性由 CSS display 决定（受祖先 _collapsed 影响）
  // 这样 toggleTraceChildren 用 CSS display 切换，不删/重建 DOM
  if (hasChildren) {
    const childAncestors = [...ancestors, n.id];
    for (const child of n.children) {
      html += renderTraceNode(child, depth + 1, childAncestors);
    }
  }

  return html;
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
  // 折叠/展开按钮：用 data-collapsed 属性保存状态
  document.querySelectorAll('.xc-collapse-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const nodeId = e.currentTarget.dataset.nodeId;
      toggleTraceChildren(nodeId);
    });
  });
}

/**
 * 切换节点的折叠状态。
 * 实现：修改数据的 _collapsed 字段，然后用 CSS display 切换可见性。
 *
 * 关键改进（v0.3.20）：
 * - 不删除/重建子节点 DOM（避免 args/result 折叠状态丢失）
 * - 不重新绑定按钮事件（避免重复绑定）
 * - 用 data-parent-id 找到所有直接子节点，批量切换 display
 *
 * 关键改进（v0.3.22）：
 * - 折叠时递归隐藏所有后代（不仅是直接子节点），孙节点继承隐藏
 * - 展开时检查每个后代的祖先链（_collapsed），如祖先折叠则保持隐藏
 * - 通过 BFS 遍历后代 DOM，避免重复查询
 */
function getAllDescendantsEl(rootId) {
  // BFS 找所有后代 DOM 元素（子节点、孙子、曾孙...）
  const all = [];
  const queue = [String(rootId)];
  while (queue.length > 0) {
    const current = queue.shift();
    const children = document.querySelectorAll(`.trace-node[data-parent-id="${current}"]`);
    children.forEach(child => {
      all.push(child);
      const childId = child.dataset.nodeId;
      if (childId) queue.push(childId);
    });
  }
  return all;
}

function toggleTraceChildren(nodeId) {
  // 找到当前节点的 data
  const node = traceNodeById[parseInt(nodeId, 10)] || traceNodeById[String(nodeId)];
  if (!node) {
    console.warn('[xcode] toggleTraceChildren: node not found:', nodeId);
    return;
  }
  // 翻转状态
  node._collapsed = !node._collapsed;

  // 找到所有后代 DOM 元素（BFS，包括子节点、孙子、曾孙...）
  const allDescendants = getAllDescendantsEl(nodeId);

  // 应用 display：
  // - 当前节点折叠 → 所有后代隐藏
  // - 当前节点展开 → 后代展示（除非它的某祖先 _collapsed）
  for (const desc of allDescendants) {
    if (node._collapsed) {
      desc.style.display = 'none';
    } else {
      // 检查祖先链是否折叠
      const ancestorsAttr = desc.dataset.ancestors || '';
      const ancestorIds = ancestorsAttr.split(',').filter(Boolean).map(Number);
      let shouldHide = false;
      for (const aId of ancestorIds) {
        const a = traceNodeById[aId];
        if (a && a._collapsed) {
          shouldHide = true;
          break;
        }
      }
      desc.style.display = shouldHide ? 'none' : '';
    }
  }

  // 更新按钮文字（▶ 折叠 / ▼ 展开）
  const btn = document.querySelector(`.xc-collapse-btn[data-node-id="${nodeId}"]`);
  if (btn) {
    btn.textContent = node._collapsed ? '▶' : '▼';
    btn.setAttribute('data-collapsed', node._collapsed ? '1' : '0');
    btn.setAttribute('title', node._collapsed ? 'Expand children' : 'Collapse children');
  }

  console.log(`[xcode] toggleTraceChildren(${nodeId}) collapsed=${node._collapsed} descendants=${allDescendants.length}`);
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

  // 获取 vscode 当前打开的 workspace 根
  const cwd = vscode ? (vscode.workspaceRoot || '') : '';

  const r = await fetchWithDetails(`${SERVER_URL}/api/agent/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: text, timeout: 600, cwd }),
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
