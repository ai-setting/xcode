/**
 * xcode run-scenario <name> — run a scenario with optional react-fix loop.
 */
import { XCodeScenarioRunner } from "../scenario-runner.js";

export async function runScenarioCommand(
  name: string,
  opts: {
    workspace: string;
    react: boolean;
    maxAttempts: string;
    description?: string;
  }
) {
  const runner = new XCodeScenarioRunner();
  const report = await runner.run(name, {
    workspace: opts.workspace,
    react: opts.react,
    maxAttempts: Number(opts.maxAttempts) || 5,
    description: opts.description,
  });

  console.log("\n=== run-scenario report ===");
  console.log(`name:       ${report.name}`);
  console.log(`workspace:  ${report.workspace}`);
  console.log(`attempts:   ${report.attempts.length}`);
  console.log(`duration:   ${report.duration_ms}ms`);
  console.log(`success:    ${report.success}`);
  if (report.final_output) console.log(`trace:      ${report.final_output}`);
  if (!report.success) {
    console.log("\nAttempts detail:");
    for (const a of report.attempts) {
      const fixMark = a.fixed ? " (react-fixed)" : "";
      console.log(
        `  #${a.attempt}${fixMark}: ${a.analysis?.category ?? "?"} — ${
          a.result.error?.split("\n")[0].slice(0, 100) ?? "(no error)"
        }`
      );
    }
    process.exit(1);
  }

  // success → render tree
  const last = report.attempts[report.attempts.length - 1];
  console.log("\n=== trace tree ===");
  console.log(runner.renderTree(last.result.entries));
}
