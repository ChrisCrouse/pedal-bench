/**
 * Run the project's .venv Python with forwarded args, cross-platform.
 *
 * Called by package.json scripts so `npm run dev:backend`, `npm run test`,
 * etc. hit the right interpreter on Windows (.venv/Scripts/python.exe)
 * and on macOS/Linux (.venv/bin/python) without hardcoded paths.
 *
 * Usage: node scripts/run-venv-python.mjs <python args...>
 *
 * Seed idea from a community contributor; I kept their shape and added a
 * clearer "run setup first" error when the venv hasn't been built yet.
 */
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

const isWindows = process.platform === "win32";
const venvPython = isWindows
  ? path.join(process.cwd(), ".venv", "Scripts", "python.exe")
  : path.join(process.cwd(), ".venv", "bin", "python");

const displayPath = isWindows
  ? ".venv\\Scripts\\python.exe"
  : "./.venv/bin/python";

const argv = process.argv.slice(2);

if (argv.length === 0) {
  console.error("Usage: node scripts/run-venv-python.mjs <python args...>");
  process.exit(2);
}

if (!existsSync(venvPython)) {
  console.error(
    `pedal-bench: virtualenv Python not found at ${displayPath}.\n` +
      `Run "npm run setup:backend" first (creates the .venv and installs deps).`,
  );
  process.exit(1);
}

const result = spawnSync(venvPython, argv, { stdio: "inherit" });

if (result.error) {
  console.error(`Failed to start ${displayPath}: ${result.error.message}`);
  process.exit(1);
}

process.exit(result.status ?? 1);
