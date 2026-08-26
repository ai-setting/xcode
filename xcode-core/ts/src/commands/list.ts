/**
 * xcode list — show all scenarios in .xcode/scenarios/.
 */
import { XCodeScenarioGen } from "../scenario-gen.js";

export function listCommand(opts: { workspace: string }) {
  const scenarios = XCodeScenarioGen.listScenariosPublic(opts.workspace);
  if (!scenarios.length) {
    console.log("(no scenarios — run `xcode init` and then `xcode gen-scenario` first)");
    return;
  }
  console.log(`Scenarios in ${opts.workspace}/.xcode/scenarios/:`);
  for (const s of scenarios) console.log(`  - ${s}`);
}
