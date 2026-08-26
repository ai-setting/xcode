/**
 * xcode trace <script> — wrap a script in xcode_trace and print a summary.
 *
 * Auto-dispatches:
 *   - .py → python3 xcode_trace.py (existing Python sidecar)
 *   - .ts / .js / .mjs / .cjs → XCodeTsTraceRunner (Node-side monkey-patch)
 */
import { XCodeTraceRunner } from "../trace-runner.js";
import { XCodeTsTraceRunner } from "../ts_trace_runner.js";

export async function traceCommand(
  script: string,
  opts: { output: string; filter?: string[]; maxDepth: string },
) {
  const lower = script.toLowerCase();
  const isJs =
    lower.endsWith(".ts") ||
    lower.endsWith(".js") ||
    lower.endsWith(".mjs") ||
    lower.endsWith(".cjs");

  if (isJs) {
    const tsRunner = new XCodeTsTraceRunner();
    const result = await tsRunner.run(script, {
      output: opts.output,
      filter: opts.filter ?? [],
      maxDepth: Number(opts.maxDepth) || 25,
    });
    if (!result.success) {
      console.error(
        `[xcode] ts trace failed: ${result.error ?? "exceptions > 0"}`,
      );
      for (const e of result.entries.filter((x) => x.type === "exception").slice(0, 3)) {
        console.error(`  exception: ${e.qualname} — ${e.exception}`);
      }
      process.exit(1);
    }
    console.log(
      `[xcode] traced ${result.total_calls} call entries → ${result.target} (${result.duration_ms}ms)`,
    );
    console.log(`[xcode] output: ${opts.output}`);
    return;
  }

  // Default: dispatch to Python sidecar.
  const runner = new XCodeTraceRunner();
  const result = await runner.run(script, {
    output: opts.output,
    filter: opts.filter ?? [],
    maxDepth: Number(opts.maxDepth) || 20,
  });
  if (!result.success) {
    console.error(`[xcode] trace failed: ${result.error}`);
    if (result.raw_stderr)
      console.error(result.raw_stderr.split("\n").slice(-5).join("\n"));
    process.exit(1);
  }
  console.log(
    `[xcode] traced ${result.entries.length} call entries → ${result.output_path} (${result.duration_ms}ms)`,
  );
}
