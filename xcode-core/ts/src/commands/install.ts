/**
 * xcode install — globally link the CLI + register the sub-agent + skill.
 *
 * Default behavior:
 *   1. `npm link` so `xcode` is available on PATH
 *   2. copy `agents/xcode/prompt.md` to ~/.config/roy-agent/agents/xcode/ ...
 *      (we just print the user-facing instruction — manual copying is safer)
 */
import { execSync } from "node:child_process";
import { chdir } from "node:process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

export function installCommand(opts: { register?: boolean }) {
  // 1. global link (run from the package root so `npm link` works)
  try {
    const pkgDir = join(__dirname, "..");
    chdir(pkgDir);
    execSync("npm link", { stdio: "inherit" });
  } catch (e) {
    console.error(`[xcode] npm link failed: ${(e as Error).message}`);
    process.exit(1);
  }

  if (opts.register === false) {
    console.log("[xcode] installed (skipped sub-agent registration)");
    return;
  }

  // 2. Print where to drop the agent + skill (manual step to avoid surprise writes)
  console.log("\n[xcode] next steps (manual):");
  console.log("  1. sub-agent: copy `xcode-core/agents/xcode-scenario-runner/` into your");
  console.log("     `<roy-agent>/agents/` folder");
  console.log("  2. skill: symlink `xcode-core/skills/xcode` into `<roy-agent>/skills/`");
}
