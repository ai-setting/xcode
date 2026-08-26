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

function getWorkspaceRoot(): string {
  const cfg = vscode.workspace.getConfiguration('xcode').get<string>('workspaceRoot') || '';
  if (cfg) return cfg;
  return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '';
}

function shouldAutoStart(): boolean {
  return vscode.workspace.getConfiguration('xcode').get<boolean>('autoStartBackend') !== false;
}

function startBackend(extensionPath: string): void {
  if (backendProcess) {
    return;
  }
  // 从 xcode-vscode 找到 xcode-core/python
  const serverScript = path.resolve(extensionPath, '..', 'xcode-core', 'python', 'xcode_server.py');
  if (!fs.existsSync(serverScript)) {
    console.warn(`[xcode] Server script not found at ${serverScript}`);
    return;
  }
  console.log(`[xcode] Starting backend: python3 ${serverScript}`);
  backendProcess = spawn('python3', [serverScript, '--port', '7800'], {
    stdio: ['ignore', 'pipe', 'pipe'],
    detached: false,
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

  const workspaceRoot = getWorkspaceRoot();
  const initData = {
    serverUrl: backendUrl,
    workspaceRoot,
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
    .replace('${nonce}', nonce)
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

  const workspaceRoot = getWorkspaceRoot();
  const absolutePath = path.isAbsolute(filePath)
    ? filePath
    : path.join(workspaceRoot || '', filePath);

  if (!fs.existsSync(absolutePath)) {
    vscode.window.showErrorMessage(`xcode: file not found: ${absolutePath}`);
    return;
  }

  try {
    const doc = await vscode.workspace.openTextDocument(absolutePath);
    const editor = await vscode.window.showTextDocument(doc);
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