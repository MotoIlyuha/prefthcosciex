// Copies the Pyodide runtime from node_modules into public/pyodide so it is served
// from our own origin (no CDN: the CSP allows 'self' only, design doc 11.10).
import { cpSync, existsSync, mkdirSync, readdirSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const source = join(root, "node_modules", "pyodide");
const target = join(root, "public", "pyodide");
const FILES = ["pyodide.mjs", "pyodide.asm.js", "pyodide.asm.wasm", "python_stdlib.zip", "pyodide-lock.json"];

if (!existsSync(source)) {
  console.error("pyodide is not installed: run npm ci first");
  process.exit(1);
}
rmSync(target, { recursive: true, force: true });
mkdirSync(target, { recursive: true });
for (const file of FILES) cpSync(join(source, file), join(target, file));
console.log(`pyodide vendored: ${readdirSync(target).join(", ")}`);
