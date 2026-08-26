/**
 * xcode serve — start the HTTP backend (python xcode_server.py).
 */
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join, resolve as resolvePath } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

function findServerScript(): string {
  const candidates = [
    join(__dirname, "..", "..", "python", "xcode_server.py"),
    join(__dirname, "..", "..", "..", "python", "xcode_server.py"),
  ];
  for (const p of candidates) if (existsSync(p)) return p;
  return candidates[0];
}

export function serveCommand(opts: { port: string; host: string }) {
  const script = findServerScript();
  if (!existsSync(script)) {
    console.error(`[xcode] xcode_server.py not found at ${script}`);
    process.exit(1);
  }
  const proc = spawn("python3", [script, "--port", opts.port, "--host", opts.host], {
    stdio: "inherit",
  });
  proc.on("close", (code) => process.exit(code ?? 0));
}
