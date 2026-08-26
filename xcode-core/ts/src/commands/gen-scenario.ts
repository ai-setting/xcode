/**
 * xcode gen-scenario <name> — generate (or regenerate) a scenario script.
 */
import { XCodeScenarioGen } from "../scenario-gen.js";

export async function genScenarioCommand(
  name: string,
  opts: { description: string; workspace: string; language: string }
) {
  const gen = new XCodeScenarioGen();
  const path = await gen.generate(name, {
    description: opts.description,
    workspace: opts.workspace,
    language: (opts.language as any) || "python",
  });
  console.log(`[xcode] scenario generated → ${path}`);
}
