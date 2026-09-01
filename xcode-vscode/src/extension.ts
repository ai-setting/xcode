import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { randomBytes } from 'crypto';
import { spawn, ChildProcess } from 'child_process';

let backendProcess: ChildProcess | null = null;
let backendUrl = 'http://localhost:7800';

function getServerUrl(): string {
  return vscode.workspace.getConfiguration('xcode').get<string>('serverUrl') || 'http://localhost:7800';
}

function shouldAutoStart(): boolean {
  return vscode.workspace.getConfiguration('xcode').get<boolean>('autoStartBackend') !== false;
}

function startBackend(extensionPath: string): void {
  // 先 kill 任何旧的后端进程（防止用旧版本 trace runner）
  if (backendProcess) {
    try {
      backendProcess.kill('SIGTERM');
    } catch {}
    backendProcess = null;
  }
  // 从 xcode-vscode 找到 xcode-core/python
  const serverScript = path.resolve(extensionPath, '..', 'xcode-core', 'python', 'xcode_server.py');
  if (!fs.existsSync(serverScript)) {
    console.warn(`[xcode] Server script not found at ${serverScript}`);
    return;
  }
  // workspace：用户工作区（或 cwd）
  const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || process.cwd();
  
  // scenarios_dir 与 TS CLI 保持一致：<workspace>/.xcode/scenarios
  const scenariosDir = path.join(workspaceRoot, '.xcode', 'scenarios');
  const tracesDir = path.join(workspaceRoot, '.xcode', 'traces');
  
  // 确保目录存在
  try {
    fs.mkdirSync(scenariosDir, { recursive: true });
    fs.mkdirSync(tracesDir, { recursive: true });
  } catch (e) {
    console.warn(`[xcode] Failed to create dirs: ${e}`);
  }
  
  console.log(`[xcode] Starting backend: python3 ${serverScript}`);
  console.log(`[xcode] workspace: ${workspaceRoot}`);
  console.log(`[xcode] scenarios_dir: ${scenariosDir}`);
  
  backendProcess = spawn('python3', [
    serverScript,
    '--host', '0.0.0.0',
    '--port', '7800',
    '--scenarios-dir', scenariosDir,
    '--traces-dir', tracesDir,
  ], {
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: false,
    cwd: workspaceRoot,  // 让 subprocess cwd = workspace
  });
  backendProcess.stdout?.on('data', (d) => console.log(`[xcode-backend] ${d.toString().trim()}`));
  backendProcess.stderr?.on('data', (d) => console.error(`[xcode-backend] ${d.toString().trim()}`));
  backendProcess.on('exit', (code) => {
    console.log(`[xcode] Backend exited with code ${code}`);
    backendProcess = null;
  });
}

export function activate(context: vscode.ExtensionContext) {
  backendUrl = getServerUrl();
  console.log(`[xcode] Activated. serverUrl=${backendUrl}`);

  if (shouldAutoStart()) {
    startBackend(context.extensionPath);
  }

  context.subscriptions.push(
    vscode.commands.registerCommand('xcode.showPanel', () => showPanel(context)),
    vscode.commands.registerCommand('xcode.runScenario', () => showPanel(context)),
    vscode.commands.registerCommand('xcode.showTrace', () => showPanel(context)),
  );

  // 监听配置变更
  context.subscriptions.push(
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration('xcode.serverUrl')) {
        backendUrl = getServerUrl();
        console.log(`[xcode] serverUrl changed to ${backendUrl}`);
      }
    })
  );

  // Webview → extension 消息
  // 通过 panel.webview.onDidReceiveMessage 在 showPanel 里注册
}

function cspConnectTokens(serverUrl: string): string[] {
  const tokens = new Set<string>();
  tokens.add('http:');
  tokens.add('https:');
  tokens.add('ws:');
  tokens.add('wss:');
  try {
    const parsed = new URL(serverUrl);
    tokens.add(`${parsed.protocol}//${parsed.hostname}`);
    if (parsed.port) {
      tokens.add(`${parsed.protocol}//${parsed.hostname}:${parsed.port}`);
    }
    tokens.add(parsed.hostname);
  } catch {}
  return Array.from(tokens);
}

async function showPanel(context: vscode.ExtensionContext) {
  const panel = vscode.window.createWebviewPanel(
    'xcode-panel',
    'Xcode',
    vscode.ViewColumn.One,
    {
      enableScripts: true,
      retainContextWhenHidden: true,
      localResourceRoots: [
        vscode.Uri.file(path.join(context.extensionPath, 'webview')),
      ],
    }
  );

  const nonce = randomBytes(16).toString('base64');
  const styleUri = panel.webview.asWebviewUri(
    vscode.Uri.file(path.join(context.extensionPath, 'webview', 'style.css'))
  );
  const scriptUri = panel.webview.asWebviewUri(
    vscode.Uri.file(path.join(context.extensionPath, 'webview', 'app.js'))
  );

  const cspTokens = cspConnectTokens(backendUrl);
  const csp = [
    `default-src 'none'`,
    `style-src ${panel.webview.cspSource} 'nonce-${nonce}'`,
    `script-src 'nonce-${nonce}'`,
    `img-src ${panel.webview.cspSource} https: data:`,
    `font-src ${panel.webview.cspSource}`,
    `connect-src ${panel.webview.cspSource} ${cspTokens.join(' ')}`,
  ].join('; ');

  const initData = {
    serverUrl: backendUrl,
    csp,
    cspTokens,
    nonce,
  };

  const htmlPath = path.join(context.extensionPath, 'webview', 'index.html');
  let html = fs.readFileSync(htmlPath, 'utf8');
  html = html
    .replace('${styleUri}', styleUri.toString())
    .replace('${scriptUri}', scriptUri.toString())
    .replace('${csp}', csp)
    .replace(/\$\{nonce\}/g, nonce)
    .replace('${initData}', JSON.stringify(initData));

  panel.webview.html = html;

  // 处理 webview 消息
  panel.webview.onDidReceiveMessage(
    async (msg) => {
      if (msg?.type === 'openFile') {
        await openFileFromTrace(msg.path, msg.line);
      } else if (msg?.type === 'reload') {
        panel.webview.html = html;
      }
    },
    undefined,
    context.subscriptions
  );
}

async function openFileFromTrace(filePath: string, line: number) {
  if (!filePath) {
    vscode.window.showErrorMessage('xcode: empty file path in trace entry');
    return;
  }

  const absolutePath = filePath;
  if (!fs.existsSync(absolutePath)) {
    vscode.window.showErrorMessage(`xcode: file not found: ${absolutePath}`);
    return;
  }

  try {
    // 先打开文档（如果未打开），得到 document 对象
    let doc: vscode.TextDocument;
    try {
      doc = await vscode.workspace.openTextDocument(absolutePath);
    } catch (e: any) {
      vscode.window.showErrorMessage(`xcode: cannot open document: ${e?.message ?? e}`);
      return;
    }

    // 用 tabGroups 查找文件是否已打开（覆盖 visible + hidden 的所有 tab）
    // tabGroups 是所有 tab 的分组（每个 view column 一个 group）
    let existingEditor: vscode.TextEditor | undefined;
    let existingColumn: vscode.ViewColumn | undefined;
    for (const tabGroup of vscode.window.tabGroups.all) {
      for (const tab of tabGroup.tabs) {
        if (
          tab.input instanceof vscode.TabInputText &&
          tab.input.uri.fsPath === doc.uri.fsPath
        ) {
          // 文件已在某 tab 打开
          existingEditor = vscode.window.visibleTextEditors.find(
            e => e.document === doc || e.document.uri.fsPath === doc.uri.fsPath
          );
          if (existingEditor) {
            existingColumn = tabGroup.viewColumn;
            break;
          }
        }
      }
      if (existingEditor) break;
    }

    let editor: vscode.TextEditor;
    if (existingEditor && existingColumn !== undefined) {
      // 复用现有 tab（同一个 view column）
      editor = await vscode.window.showTextDocument(doc, {
        viewColumn: existingColumn,
        preserveFocus: false,
        preview: false,
      });
    } else {
      // 新 tab（在 Beside 分窗打开）
      editor = await vscode.window.showTextDocument(doc, {
        viewColumn: vscode.ViewColumn.Beside,
        preserveFocus: false,
        preview: false,
      });
    }

    // 跳到目标行
    const targetLine = Math.max(0, (line || 1) - 1);
    const range = new vscode.Range(targetLine, 0, targetLine, 0);
    editor.revealRange(range, vscode.TextEditorRevealType.InCenter);
    editor.selection = new vscode.Selection(range.start, range.start);
  } catch (e: any) {
    vscode.window.showErrorMessage(`xcode: failed to open file: ${e.message}`);
  }
}

export function deactivate() {
  if (backendProcess) {
    try {
      backendProcess.kill('SIGTERM');
    } catch {}
    backendProcess = null;
  }
}