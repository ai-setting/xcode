/**
 * xcode show-trace <name> — print the latest trace tree for a scenario.
 */
import { existsSync, readFileSync } from "node:fs";
import { join, resolve as resolvePath } from "node:path";
import { XCodeScenarioRunner } from "../scenario-runner.js";

export function showTraceCommand(name: string, opts: { workspace: string }) {
  const traceFile = join(resolvePath(opts.workspace), ".xcode", "traces", `${name}.json`);
  if (!existsSync(traceFile)) {
    console.error(`[xcode] no trace found at ${traceFile} — run \`xcode run-scenario ${name}\` first`);
    process.exit(1);
  }
  const data = JSON.parse(readFileSync(traceFile, "utf8")) as { entries: any[] };
  const runner = new XCodeScenarioRunner();
  console.log(runner.renderTree(data.entries || []));
}
