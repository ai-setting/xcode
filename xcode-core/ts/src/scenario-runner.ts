/**
 * XCodeScenarioRunner — execute a scenario with react-fix retry.
 *
 * Flow:
 *   1. ensure <workspace>/.xcode/scenarios/<name>.py exists
 *   2. run `python3 xcode_trace.py <scenario> --output /tmp/xcode_traces/<ts>.json`
 *   3. if success: copy trace to <workspace>/.xcode/traces/<name>.json
 *   4. if failure: classify error → call XCodeScenarioGen.fix → retry
 *
 * The loop bails after `maxAttempts` and surfaces the last error to the user.
 */
import { existsSync, mkdirSync, copyFileSync } from "node:fs";
import { dirname, join, resolve as resolvePath } from "node:path";
import { fileURLToPath } from "node:url";
import { XCodeTraceRunner } from "./trace-runner.js";
import { XCodeScenarioGen } from "./scenario-gen.js";
import { classifyFailure } from "./failure-classifier.js";
import type {
  FailureAnalysis,
  RunOptions,
  TraceEntry,
  TraceResult,
} from "./types.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

export interface RunAttempt {
  attempt: number;
  result: TraceResult;
  analysis?: FailureAnalysis;
  fixed: boolean;
}

export interface RunReport {
  name: string;
  workspace: string;
  success: boolean;
  attempts: RunAttempt[];
  final_output?: string;
  duration_ms: number;
}

export class XCodeScenarioRunner {
  private runner = new XCodeTraceRunner();
  private gen = new XCodeScenarioGen();

  async run(name: string, opts: RunOptions): Promise<RunReport> {
    const workspace = resolvePath(opts.workspace);
    const start = Date.now();
    const attempts: RunAttempt[] = [];
    let lastAnalysis: FailureAnalysis | undefined;

    for (let attempt = 1; attempt <= opts.maxAttempts; attempt++) {
      const log = (msg: string) =>
        console.log(`[xcode] [${name}] attempt ${attempt}/${opts.maxAttempts} — ${msg}`);

      // 1. Ensure scenario exists
      const scenarioPath = join(workspace, ".xcode", "scenarios", `${name}.py`);
      if (!existsSync(scenarioPath)) {
        if (!opts.description) {
          const report: RunReport = {
            name,
            workspace,
            success: false,
            attempts,
            duration_ms: Date.now() - start,
          };
          attempts.push({
            attempt,
            fixed: false,
            result: {
              success: false,
              entries: [],
              duration_ms: 0,
              error: `scenario '${name}' not found and no --description provided to auto-generate`,
            },
          });
          return report;
        }
        log(`scenario missing — generating (description: ${opts.description.slice(0, 60)}…)`);
        await this.gen.generate(name, {
          description: opts.description,
          workspace,
          language: "python",
        });
      }

      // 2. Run trace
      const stamp = new Date().toISOString().replace(/[:.]/g, "-");
      const traceOut = `/tmp/xcode_traces/${name}-${stamp}.json`;
      log(`tracing → ${traceOut}`);
      const result = await this.runner.run(scenarioPath, {
        output: traceOut,
        filter: [],
        maxDepth: 20,
      });

      // 3. Success?
      if (result.success) {
        log(`✅ success — ${result.entries.length} entries`);
        // copy to .xcode/traces/<name>.json
        const tracesDir = join(workspace, ".xcode", "traces");
        if (!existsSync(tracesDir)) mkdirSync(tracesDir, { recursive: true });
        const finalPath = join(tracesDir, `${name}.json`);
        try {
          copyFileSync(traceOut, finalPath);
          log(`trace archived at ${finalPath}`);
        } catch (e) {
          log(`warn: failed to copy trace to .xcode/traces/ — ${(e as Error).message}`);
        }
        attempts.push({ attempt, fixed: false, result });
        return {
          name,
          workspace,
          success: true,
          attempts,
          final_output: finalPath,
          duration_ms: Date.now() - start,
        };
      }

      // 4. Failure classification
      lastAnalysis = classifyFailure(result);
      log(`❌ failed — ${lastAnalysis.category}: ${lastAnalysis.reason.slice(0, 80)}`);
      attempts.push({ attempt, fixed: false, result, analysis: lastAnalysis });

      if (!opts.react || attempt >= opts.maxAttempts) break;

      // 5. React-fix
      log(`🔧 react-fix: ${lastAnalysis.fix_hint.slice(0, 80)}`);
      const body = XCodeScenarioGen.readScenario(name, workspace) || "";
      await this.gen.fix(name, workspace, body, lastAnalysis);
      attempts[attempts.length - 1].fixed = true;
    }

    return {
      name,
      workspace,
      success: false,
      attempts,
      duration_ms: Date.now() - start,
      error_summary: lastAnalysis?.reason,
    } as RunReport & { error_summary?: string };
  }

  /** Pretty-print a trace tree from entries (call entries only). */
  renderTree(entries: TraceEntry[]): string {
    if (!entries.length) return "(empty trace)";

    type Node = {
      id: number;
      name: string;
      file: string;
      line: number;
      depth: number;
      children: Node[];
    };

    const calls = entries.filter((e) => (e.type ?? "call") === "call");
    const byId: Record<number, Node> = {};
    const roots: Node[] = [];

    for (const e of calls) {
      const id = e.id ?? e.call_id ?? 0;
      const name = e.func ?? e.func_name ?? e.qualname ?? "<anon>";
      const file = e.file || "?";
      const line = e.line ?? 0;
      byId[id] = { id, name, file, line, depth: e.depth ?? 0, children: [] };
    }

    // build parent->child using caller.caller_id
    for (const e of calls) {
      const id = e.id ?? e.call_id ?? 0;
      const node = byId[id];
      if (!node) continue;
      const cid = e.caller?.caller_id ?? null;
      if (cid != null && byId[cid]) {
        byId[cid].children.push(node);
      } else {
        roots.push(node);
      }
    }

    const lines: string[] = [];
    const walk = (n: Node, prefix: string) => {
      lines.push(
        `${prefix}├─ ${n.name} (${n.file.replace(process.cwd(), ".")}:${n.line})`
      );
      for (const c of n.children) walk(c, prefix + "│  ");
    };
    if (!roots.length && calls.length) {
      // fallback: shallow list
      for (const e of calls) {
        const name = e.func ?? e.func_name ?? "<anon>";
        lines.push(`├─ ${name} (${e.file}:${e.line})`);
      }
    } else {
      for (const r of roots) walk(r, "");
    }
    return lines.join("\n");
  }
}
