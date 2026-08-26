/**
 * xcode trace <script> — wrap a Python script in xcode_trace.py and print a summary.
 */
import { XCodeTraceRunner } from "../trace-runner.js";

export async function traceCommand(
  script: string,
  opts: { output: string; filter?: string[]; maxDepth: string }
) {
  const runner = new XCodeTraceRunner();
  const result = await runner.run(script, {
    output: opts.output,
    filter: opts.filter ?? [],
    maxDepth: Number(opts.maxDepth) || 20,
  });
  if (!result.success) {
    console.error(`[xcode] trace failed: ${result.error}`);
    if (result.raw_stderr) console.error(result.raw_stderr.split("\n").slice(-5).join("\n"));
    process.exit(1);
  }
  console.log(
    `[xcode] traced ${result.entries.length} call entries → ${result.output_path} (${result.duration_ms}ms)`
  );
}
