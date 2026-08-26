/**
 * Wrapper around python3 xcode_trace.py — non-invasive Python trace runner.
 *
 * Spawns the python sidecar and parses its JSON output into TraceEntry[].
 *
 * The python sidecar writes a JSON file to `--output` then prints a
 * one-line summary to stdout.
 */
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join, resolve as resolvePath } from "node:path";
import { fileURLToPath } from "node:url";
import { mkdirSync, readFileSync } from "node:fs";
import type { TraceEntry, TraceOptions, TraceResult } from "./types.js";

const __dirname = dirname(fileURLToPath(import.meta.url));

function findPythonTraceScript(): string {
  // dist/trace-runner.js → ../python/xcode_trace.py
  const candidates = [
    join(__dirname, "..", "python", "xcode_trace.py"),
    join(__dirname, "..", "..", "python", "xcode_trace.py"),
  ];
  for (const p of candidates) {
    if (existsSync(p)) return p;
  }
  return candidates[0]; // best guess; let python error out
}

function ensureParentDir(filePath: string) {
  const dir = dirname(filePath);
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
}

export class XCodeTraceRunner {
  /** Run a python script under xcode_trace.py and return parsed trace. */
  async run(script: string, opts: TraceOptions): Promise<TraceResult> {
    const scriptAbs = resolvePath(script);
    if (!existsSync(scriptAbs)) {
      return {
        success: false,
        entries: [],
        duration_ms: 0,
        error: `script not found: ${scriptAbs}`,
      };
    }

    const traceScript = findPythonTraceScript();
    if (!existsSync(traceScript)) {
      return {
        success: false,
        entries: [],
        duration_ms: 0,
        error: `xcode_trace.py not found (looked at ${traceScript})`,
      };
    }

    ensureParentDir(opts.output);

    const args = [
      traceScript,
      scriptAbs,
      "--output",
      opts.output,
      "--max-depth",
      String(opts.maxDepth),
    ];
    if (opts.filter?.length) {
      args.push("--filter", ...opts.filter);
    }

    const start = Date.now();
    return await new Promise<TraceResult>((resolve) => {
      const proc = spawn("python3", args, { stdio: ["ignore", "pipe", "pipe"] });
      let stdout = "";
      let stderr = "";
      proc.stdout.on("data", (d) => (stdout += d.toString()));
      proc.stderr.on("data", (d) => (stderr += d.toString()));
      proc.on("error", (err) => {
        resolve({
          success: false,
          entries: [],
          duration_ms: Date.now() - start,
          error: `spawn python3 failed: ${err.message}`,
          raw_stderr: stderr,
        });
      });
      proc.on("close", (code) => {
        const duration = Date.now() - start;
        const ok = code === 0;
        if (!ok) {
          resolve({
            success: false,
            entries: [],
            output_path: opts.output,
            duration_ms: duration,
            error: `xcode_trace.py exited with code ${code}: ${stderr.trim().split("\n").slice(-3).join(" | ")}`,
            raw_stdout: stdout,
            raw_stderr: stderr,
          });
          return;
        }

        // Parse output JSON
        let entries: TraceEntry[] = [];
        let totalExceptions = 0;
        try {
          if (existsSync(opts.output)) {
            const data = JSON.parse(readFileSync(opts.output, "utf8")) as {
              entries?: TraceEntry[];
              total_exceptions?: number;
            };
            entries = Array.isArray(data.entries) ? data.entries : [];
            totalExceptions = data.total_exceptions ?? 0;
          }
        } catch (e) {
          resolve({
            success: false,
            entries: [],
            output_path: opts.output,
            duration_ms: duration,
            error: `failed to parse trace output: ${(e as Error).message}`,
            raw_stdout: stdout,
            raw_stderr: stderr,
          });
          return;
        }

        // v0.2.0: even if python exited 0, treat exceptions traced as failure
        // so the react-fix loop can patch the scenario.
        const success = entries.length > 0 && totalExceptions === 0;
        if (!success && totalExceptions > 0) {
          const exceptionLines = entries
            .filter((e) => (e.type ?? "call") === "exception")
            .slice(0, 3)
            .map((e) => (e as any).exception || "?")
            .join(" | ");
          resolve({
            success: false,
            entries,
            output_path: opts.output,
            duration_ms: duration,
            error: `trace recorded ${totalExceptions} exception(s): ${exceptionLines}`,
            raw_stdout: stdout,
            raw_stderr: stderr,
          });
          return;
        }

        resolve({
          success,
          entries,
          output_path: opts.output,
          duration_ms: duration,
          raw_stdout: stdout,
          raw_stderr: stderr,
        });
      });
    });
  }
}
