/**
 * Find a compatible Python (3.12 or 3.13) on the host and build .venv.
 *
 * Why this script exists: `python -m venv .venv` is too fragile for a
 * public repo. Whatever `python` maps to differs per OS and install
 * method, and Python 3.14 silently builds a venv that then fails the
 * pip install because build123d / pypdfium2 don't ship 3.14 wheels yet.
 *
 * Strategy: try a short list of candidate commands (most-specific first),
 * for each run `<cmd> --version` and parse `Python MAJOR.MINOR.PATCH`.
 * Accept 3.12.x or 3.13.x; skip anything else. Stop at first match.
 * Print the chosen interpreter, then `<cmd> -m venv .venv`.
 *
 * If no candidate qualifies, print every command we tried and why, and
 * exit non-zero so `npm run setup:backend` bails before a half-built venv.
 */
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";

// Ordered by specificity: exact-version commands first, then generic.
// `py -3.13` / `py -3.12` are Windows's standard launcher.
const CANDIDATES = [
  ["python3.13"],
  ["python3.12"],
  ["py", "-3.13"],
  ["py", "-3.12"],
  ["python3"],
  ["python"],
];

const SUPPORTED_MINORS = new Set([12, 13]);
const VERSION_RE = /Python\s+(\d+)\.(\d+)\.(\d+)/i;

function tryProbe([cmd, ...args]) {
  const result = spawnSync(cmd, [...args, "--version"], {
    encoding: "utf8",
    shell: false,
  });
  if (result.error || result.status !== 0) {
    return { ok: false, reason: "not found on PATH" };
  }
  const output = `${result.stdout ?? ""}${result.stderr ?? ""}`;
  const m = VERSION_RE.exec(output);
  if (!m) {
    return { ok: false, reason: `unexpected version output: ${output.trim()}` };
  }
  const major = Number(m[1]);
  const minor = Number(m[2]);
  const patch = Number(m[3]);
  if (major !== 3 || !SUPPORTED_MINORS.has(minor)) {
    return {
      ok: false,
      reason: `reports ${major}.${minor}.${patch}; need 3.12.x or 3.13.x`,
    };
  }
  return { ok: true, version: `${major}.${minor}.${patch}` };
}

function describe([cmd, ...args]) {
  return args.length ? `${cmd} ${args.join(" ")}` : cmd;
}

// Skip if .venv already exists — the user can delete it manually to re-create.
const venvDir = path.join(process.cwd(), ".venv");
if (existsSync(venvDir)) {
  console.log("pedal-bench: .venv already exists, skipping creation.");
  console.log("(Delete .venv first if you want to rebuild it with a different Python.)");
  process.exit(0);
}

const tried = [];
let chosen = null;

for (const candidate of CANDIDATES) {
  const probe = tryProbe(candidate);
  if (probe.ok) {
    chosen = { candidate, version: probe.version };
    break;
  }
  tried.push({ candidate, reason: probe.reason });
}

if (!chosen) {
  console.error("pedal-bench: could not find a compatible Python (3.12 or 3.13).");
  console.error("Tried:");
  for (const t of tried) {
    console.error(`  ${describe(t.candidate).padEnd(16)} — ${t.reason}`);
  }
  console.error("");
  console.error("Install Python 3.12 or 3.13 and re-run `npm run setup:backend`.");
  console.error("3.14 isn't supported yet: build123d / pypdfium2 don't ship 3.14 wheels.");
  process.exit(1);
}

const [cmd, ...args] = chosen.candidate;
console.log(`pedal-bench: creating .venv with ${describe(chosen.candidate)} (Python ${chosen.version})`);

const venvResult = spawnSync(cmd, [...args, "-m", "venv", ".venv"], {
  stdio: "inherit",
  shell: false,
});

if (venvResult.error) {
  console.error(`Failed to run ${describe(chosen.candidate)}: ${venvResult.error.message}`);
  process.exit(1);
}

process.exit(venvResult.status ?? 1);
