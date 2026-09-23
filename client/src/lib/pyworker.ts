// Web Worker running CPython (Pyodide). One run at a time; the page terminates the
// worker when the 10-second limit is exceeded, which is the only way to stop a
// runaway `while True` without SharedArrayBuffer.
/// <reference lib="webworker" />
import type { PyodideInterface } from "pyodide";

interface RunMessage {
  id: number;
  code: string;
  files: Record<string, ArrayBuffer>;
}

const ctx = self as unknown as DedicatedWorkerGlobalScope;
let pyodide: PyodideInterface | null = null;

async function load(): Promise<PyodideInterface> {
  if (pyodide) return pyodide;
  const url = "/pyodide/pyodide.mjs";
  const module = (await import(/* @vite-ignore */ url)) as {
    loadPyodide: (options: { indexURL: string; stdout?: (s: string) => void }) => Promise<PyodideInterface>;
  };
  pyodide = await module.loadPyodide({ indexURL: "/pyodide/", stdout: () => undefined });
  return pyodide;
}

ctx.onmessage = async (event: MessageEvent<RunMessage | { warmup: true }>) => {
  const data = event.data;
  if ("warmup" in data) {
    try {
      await load();
      ctx.postMessage({ ready: true });
    } catch (error) {
      ctx.postMessage({ ready: false, error: String(error) });
    }
    return;
  }
  const started = performance.now();
  let stdout = "";
  let stderr = "";
  try {
    const py = await load();
    py.setStdout({ batched: (text: string) => { stdout += text + "\n"; } });
    py.setStderr({ batched: (text: string) => { stderr += text + "\n"; } });
    const fs = py.FS;
    try {
      fs.mkdir("/work");
    } catch {
      // exists from a previous run
    }
    for (const name of fs.readdir("/work") as string[]) {
      if (name !== "." && name !== "..") fs.unlink(`/work/${name}`);
    }
    for (const [name, buffer] of Object.entries(data.files)) {
      fs.writeFile(`/work/${name}`, new Uint8Array(buffer));
    }
    py.runPython("import os, sys; os.chdir('/work'); sys.argv = ['main.py']");
    await py.runPythonAsync(data.code);
    ctx.postMessage({ id: data.id, ok: true, stdout, stderr, ms: performance.now() - started });
  } catch (error) {
    const text = String(error instanceof Error ? error.message : error);
    ctx.postMessage({ id: data.id, ok: false, stdout, stderr: stderr + cleanTraceback(text), ms: performance.now() - started });
  }
};

function cleanTraceback(text: string): string {
  // Drop Pyodide's own frames: the student only needs the lines of their program.
  const lines = text.split("\n").filter((line) => !line.includes("/lib/python3") && !line.includes("_pyodide"));
  return lines.join("\n");
}
