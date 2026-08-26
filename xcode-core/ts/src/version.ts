/**
 * Build metadata for xcode.
 * Date/commit are injected at build time; we fall back to ISO today / "dev".
 */
import { execSync } from "node:child_process";
import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

function readPkgVersion(): string {
  // dist/version.js lives in <pkg-root>/dist/, package.json is one level up.
  // In dev (src/), we still go up two levels.
  const candidates = [
    join(__dirname, "..", "package.json"),
    join(__dirname, "..", "..", "package.json"),
  ];
  for (const p of candidates) {
    if (existsSync(p)) {
      try {
        const pkg = JSON.parse(readFileSync(p, "utf8")) as { version?: string };
        if (pkg.version) return pkg.version;
      } catch {
        // ignore
      }
    }
  }
  return "0.0.0-dev";
}

function readGitCommit(): string {
  try {
    return execSync("git rev-parse --short HEAD", {
      cwd: join(__dirname, "..", ".."),
      stdio: ["ignore", "pipe", "ignore"],
    })
      .toString()
      .trim();
  } catch {
    return "dev";
  }
}

export const PKG_VERSION = readPkgVersion();
export const BUILD_DATE = new Date().toISOString().slice(0, 10);
export const GIT_COMMIT = readGitCommit();
