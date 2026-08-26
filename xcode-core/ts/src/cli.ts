#!/usr/bin/env node
/**
 * @fileoverview xcode CLI entry — top-level command dispatch.
 *
 * Subcommands:
 *   xcode serve                          # 启动 HTTP 后端（python xcode_server.py）
 *   xcode trace <script.py>              # 直接运行 trace runner（无侵入）
 *   xcode gen-scenario <name>            # 生成 scenario 脚本（基于 LLM 调用）
 *   xcode run-scenario <name>            # 运行 scenario（含 react 修复）
 *   xcode list                           # 列出 .xcode/scenarios/
 *   xcode show-trace <name>              # 打印 trace tree
 *   xcode init                           # 在当前项目初始化 .xcode/
 *   xcode install                        # 注册到 ~/.local/bin + npm link
 *   xcode --version | -V
 *   xcode --help | -h
 */
import { Command } from "commander";
import { serveCommand } from "./commands/serve.js";
import { traceCommand } from "./commands/trace.js";
import { genScenarioCommand } from "./commands/gen-scenario.js";
import { runScenarioCommand } from "./commands/run-scenario.js";
import { listCommand } from "./commands/list.js";
import { showTraceCommand } from "./commands/show-trace.js";
import { initCommand } from "./commands/init.js";
import { installCommand } from "./commands/install.js";
import { PKG_VERSION, BUILD_DATE, GIT_COMMIT } from "./version.js";

const HELP = `xcode — non-invasive multi-language trace + AI scenario runner

Usage:
  xcode serve                          启动 HTTP 后端（默认 7800）
  xcode trace <script.py>              无侵入 trace 一个 Python 脚本
  xcode gen-scenario <name> --description "..." --workspace <path>
                                       生成 scenario 脚本
  xcode run-scenario <name> [--no-react] [--max-attempts 5]
                                       运行 scenario（含 react 修复）
  xcode list                           列出 .xcode/scenarios/*.py
  xcode show-trace <name>              显示 trace tree（CLI 渲染）
  xcode init                           在当前项目创建 .xcode/
  xcode install [--no-register]        全局安装 + 注册
  xcode --version | -V
  xcode --help | -h

Sub-agent flow (LLM-assisted, react 修复):
  1. \`xcode init\`                              — 创建 .xcode/{scenarios,traces}/
  2. \`xcode gen-scenario <name> --description "..."\`
     — sub-agent 根据描述 + 代码分析生成 scenario 脚本
  3. \`xcode run-scenario <name>\`                — 运行 + 修复（最多 5 次）
  4. \`xcode show-trace <name>\`                  — CLI 渲染 trace tree

输出：
  - .xcode/scenarios/<name>.py
  - /tmp/xcode_traces/<name>-<timestamp>.json
  - .xcode/traces/<name>.json（最后一次成功 trace 的副本）
`;

const program = new Command();
program
  .name("xcode")
  .version(`${PKG_VERSION} (build ${BUILD_DATE} commit ${GIT_COMMIT})`)
  .description("xcode — non-invasive multi-language trace + AI scenario runner")
  .addHelpText("after", HELP);

program
  .command("serve")
  .description("启动 HTTP 后端服务（python xcode_server.py）")
  .option("--port <port>", "监听端口", "7800")
  .option("--host <host>", "监听地址", "127.0.0.1")
  .action((opts) => serveCommand(opts));

program
  .command("trace <script>")
  .description("无侵入 trace Python 脚本")
  .option("--output <file>", "输出文件", "/tmp/xcode_traces/trace.json")
  .option("--filter <patterns...>", "只 trace 匹配的文件/函数（glob）")
  .option("--max-depth <n>", "最大 call depth", "20")
  .action((script, opts) => traceCommand(script, opts));

program
  .command("gen-scenario <name>")
  .description("生成 scenario 脚本")
  .requiredOption("--description <desc>", "功能线描述")
  .option("--workspace <path>", "项目路径", ".")
  .option("--language <lang>", "python|typescript|go|rust", "python")
  .action((name, opts) => genScenarioCommand(name, opts));

program
  .command("run-scenario <name>")
  .description("运行 scenario（含 react 修复机制）")
  .option("--workspace <path>", "项目路径", ".")
  .option("--no-react", "禁用 react 修复（不重试）")
  .option("--max-attempts <n>", "最多尝试次数", "5")
  .option("--description <desc>", "scenario 描述（gen 用）")
  .action((name, opts) => runScenarioCommand(name, opts));

program
  .command("list")
  .description("列出所有 scenario")
  .option("--workspace <path>", "项目路径", ".")
  .action((opts) => listCommand(opts));

program
  .command("show-trace <name>")
  .description("显示 trace tree（CLI 渲染）")
  .option("--workspace <path>", "项目路径", ".")
  .action((name, opts) => showTraceCommand(name, opts));

program
  .command("init")
  .description("在当前项目创建 .xcode/（scenarios/, traces/）")
  .option("--force", "覆盖已存在的 .xcode/")
  .action((opts) => initCommand(opts));

program
  .command("install")
  .description("全局安装 xcode + 注册到 roy-agent sub-agents")
  .option("--no-register", "不注册 sub-agent")
  .action((opts) => installCommand(opts));

program.parseAsync(process.argv).catch((err) => {
  console.error(`[xcode] error: ${err?.message || err}`);
  if (process.env.XCODE_DEBUG) console.error(err?.stack);
  process.exit(1);
});
