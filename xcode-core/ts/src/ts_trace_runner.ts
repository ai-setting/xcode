/**
 * XCode TS Trace Runner — non-invasive TypeScript / JavaScript trace runner.
 *
 * Mirrors `xcode_trace.py` semantics (used by the Python trace runner):
 *   - double location (def + caller)
 *   - args + return value serialization
 *   - filter by file (workspace match)
 *   - max-depth limit
 *   - output a single JSON file consumable by the IDE/VSCode side
 *
 * Strategy
 * --------
 * Node has nothing like Python's `sys.settrace`, and ESM `import()` bypasses
 * `Module._load` entirely, so in-process monkey-patching is unreliable across
 * the four TS/JS module flavors (.cjs/.mjs/.ts/.js). We instead:
 *
 *   1. ship a CommonJS preload (`_ts_trace_preload.cjs`) which patches
 *      `Module._load` BEFORE the target's modules are required;
 *   2. invoke the preload via `node --require=<preload>` in a child process;
 *   3. let the preload synchronously `require()` the target, accumulating
 *      entries into a shared state object;
 *   4. on exit (or when the scenario finishes), the preload writes the
 *      JSON trace to `--output` and exits.
 *
 * The runner class wraps that orchestration, parses the resulting JSON,
 * and surfaces `success`/`entries` for the existing CLI surface so
 * `xcode trace ...` works uniformly for Python and TS targets.
 *
 * Usage (CLI):
 *
 *   xcode trace <script.ts|cjs|mjs|js> --output /tmp/x.json --filter foo --max-depth 25
 *
 * Usage (library, called from `commands/trace.ts`):
 *
 *   const runner = new XCodeTsTraceRunner();
 *   const result = await runner.run(targetScript, { output, filter, maxDepth });
 *
 * @module xcode/ts-trace-runner
 */

import { spawn } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve as resolvePath } from "node:path";
import { fileURLToPath } from "node:url";

// ============================================================================
// Types — mirror the Python trace runner's output schema
// ============================================================================

export interface TsTraceCaller {
  caller_id: number | null;
  caller_file: string;
  caller_line: number;
  caller_func: string;
}

export interface TsTraceEntry {
  id: number;
  type: "call" | "return" | "exception";
  depth: number;
  func: string;
  qualname: string;
  file: string;
  line: number;
  current_line?: number;
  args?: Record<string, string>;
  return_value?: string;
  exception?: string;
  caller?: TsTraceCaller | null;
  duration_ms?: number;
  timestamp: number;
}

export interface TsTraceResult {
  success: boolean;
  tool: string;
  version: string;
  target: string;
  filter: string[];
  max_depth: number;
  total_calls: number;
  total_returns: number;
  total_exceptions: number;
  duration_ms: number;
  entries: TsTraceEntry[];
  error?: string;
}

export interface TsTraceOptions {
  output: string;
  /** Whitelist — at least one token must match abs path or symbol name. */
  filter?: string[];
  /** Hard limit on call depth (Python side default 20). */
  maxDepth?: number;
  /** Optional workspace root for relative-path display. Defaults to cwd. */
  workspace?: string;
}

// ============================================================================
// Helpers
// ============================================================================

const TOOL_VERSION = "0.1.0";

function findPreload(): string {
  // dist/ts_trace_runner.js → src/_ts_trace_preload.cjs (sibling)
  const candidates = [
    join(dirname(fileURLToPath(import.meta.url)), "_ts_trace_preload.cjs"),
    join(
      dirname(fileURLToPath(import.meta.url)),
      "..",
      "src",
      "_ts_trace_preload.cjs",
    ),
  ];
  for (const p of candidates) {
    if (existsSync(p)) return p;
  }
  return candidates[0];
}

// ============================================================================
// XCodeTsTraceRunner
// ============================================================================

export class XCodeTsTraceRunner {
  constructor(workspaceRoot?: string) {
    void workspaceRoot;
  }

  async run(
    script: string,
    opts: Omit<TsTraceOptions, "workspace"> & { workspace?: string },
  ): Promise<TsTraceResult> {
    const start = Date.now();
    const scriptAbs = resolvePath(script);
    if (!existsSync(scriptAbs)) {
      return this.fail(
        `script not found: ${scriptAbs}`,
        start,
        scriptAbs,
        opts.filter ?? [],
        opts.maxDepth ?? 25,
      );
    }

    const out = resolvePath(opts.output);
    const maxDepth = opts.maxDepth ?? 25;
    const filter = opts.filter ?? [];
    const workspace = opts.workspace ?? process.cwd();

    const preload = findPreload();
    if (!existsSync(preload)) {
      return this.fail(
        `_ts_trace_preload.cjs not found (looked at ${preload})`,
        start,
        scriptAbs,
        filter,
        maxDepth,
      );
    }

    const args = [
      "--require",
      preload,
      scriptAbs,
      "--output",
      out,
      "--max-depth",
      String(maxDepth),
      "--workspace",
      workspace,
    ];
    if (filter.length) args.push("--filter", filter.join(","));

    let stdout = "";
    let stderr = "";
    await new Promise<void>((resolve) => {
      const proc = spawn(process.execPath, args, {
        stdio: ["ignore", "pipe", "pipe"],
      });
      proc.stdout.on("data", (d) => (stdout += d.toString()));
      proc.stderr.on("data", (d) => (stderr += d.toString()));
      proc.on("error", () => resolve());
      proc.on("close", () => resolve());
    });

    if (!existsSync(out)) {
      return {
        success: false,
        tool: "xcode-ts-trace",
        version: TOOL_VERSION,
        target: scriptAbs,
        filter,
        max_depth: maxDepth,
        total_calls: 0,
        total_returns: 0,
        total_exceptions: 0,
        duration_ms: Date.now() - start,
        entries: [],
        error: `preload did not produce output (${stderr.trim().split("\n").slice(-3).join(" | ")})`,
      };
    }
    let parsed: TsTraceResult;
    try {
      parsed = JSON.parse(readFileSync(out, "utf8")) as TsTraceResult;
    } catch (e) {
      return {
        success: false,
        tool: "xcode-ts-trace",
        version: TOOL_VERSION,
        target: scriptAbs,
        filter,
        max_depth: maxDepth,
        total_calls: 0,
        total_returns: 0,
        total_exceptions: 0,
        duration_ms: Date.now() - start,
        entries: [],
        error: `failed to parse trace output: ${(e as Error).message}`,
      };
    }
    parsed.duration_ms = Date.now() - start;
    // Echo any stdout from the scenario into stderr for diagnostics.
    if (stdout.trim()) process.stdout.write(`[scenario stdout]\n${stdout}`);
    return parsed;
  }

  private fail(
    error: string,
    start: number,
    target: string,
    filter: string[],
    maxDepth: number,
  ): TsTraceResult {
    return {
      success: false,
      tool: "xcode-ts-trace",
      version: TOOL_VERSION,
      target,
      filter,
      max_depth: maxDepth,
      total_calls: 0,
      total_returns: 0,
      total_exceptions: 0,
      duration_ms: Date.now() - start,
      entries: [],
      error,
    };
  }
}

// ============================================================================
// CLI (so we can `npx tsx ts_trace_runner.ts foo.ts`)
// ============================================================================

async function main() {
  const args = process.argv.slice(2);
  if (args.length === 0) {
    console.error(
      "usage: ts_trace_runner.ts <target.cjs|mjs|js|ts> [--output file] [--filter tok] [--max-depth n]",
    );
    process.exit(2);
  }
  const target = args[0];
  const opts: TsTraceOptions = {
    output: "/tmp/xcode_traces/ts_trace.json",
    filter: [],
    maxDepth: 25,
  };
  for (let i = 1; i < args.length; i++) {
    const a = args[i];
    if (a === "--output" && args[i + 1]) opts.output = args[++i];
    else if (a === "--filter" && args[i + 1])
      opts.filter = args[++i].split(",").map((s) => s.trim());
    else if (a === "--max-depth" && args[i + 1])
      opts.maxDepth = parseInt(args[++i], 10);
  }
  const runner = new XCodeTsTraceRunner();
  const r = await runner.run(target, opts);
  if (!r.success) {
    console.error(`[xcode-ts-trace] FAILED: ${r.error ?? "(exceptions)"}`);
    process.exit(1);
  }
  console.log(
    `[xcode-ts-trace] calls=${r.total_calls} returns=${r.total_returns} exceptions=${r.total_exceptions} → ${opts.output} (${r.duration_ms}ms)`,
  );
}

const isDirect =
  process.argv[1] && fileURLToPath(import.meta.url) === resolvePath(process.argv[1]);
if (isDirect) {
  main().catch((e) => {
    console.error(e);
    process.exit(1);
  });
}
