// Page side of the in-browser Python runner (design doc 7.3): lazy, cached by the
// Service Worker, 10 seconds per run like the server runner.
export interface PyResult {
  ok: boolean;
  stdout: string;
  stderr: string;
  ms: number;
  timedOut: boolean;
}

export type PyStatus = "idle" | "loading" | "ready" | "error";

const LIMIT_MS = 10_000;
let worker: Worker | null = null;
let readyPromise: Promise<void> | null = null;
let counter = 0;
const listeners = new Set<(status: PyStatus) => void>();
let status: PyStatus = "idle";

function setStatus(next: PyStatus): void {
  status = next;
  listeners.forEach((fn) => fn(next));
}

export function pythonStatus(): PyStatus {
  return status;
}

export function onPythonStatus(fn: (status: PyStatus) => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function spawn(): Worker {
  worker = new Worker(new URL("./pyworker.ts", import.meta.url), { type: "module" });
  return worker;
}

export function warmUp(): Promise<void> {
  if (readyPromise) return readyPromise;
  setStatus("loading");
  const w = worker ?? spawn();
  readyPromise = new Promise<void>((resolve, reject) => {
    const handler = (event: MessageEvent<{ ready?: boolean; error?: string }>) => {
      if (event.data.ready === undefined) return;
      w.removeEventListener("message", handler);
      if (event.data.ready) {
        setStatus("ready");
        resolve();
      } else {
        setStatus("error");
        readyPromise = null;
        reject(new Error(event.data.error ?? "Python не загрузился"));
      }
    };
    w.addEventListener("message", handler);
    w.postMessage({ warmup: true });
  });
  return readyPromise;
}

export async function runPython(code: string, files: Record<string, Blob>): Promise<PyResult> {
  await warmUp();
  const w = worker ?? spawn();
  const id = ++counter;
  const buffers: Record<string, ArrayBuffer> = {};
  for (const [name, blob] of Object.entries(files)) buffers[name] = await blob.arrayBuffer();
  return new Promise<PyResult>((resolve) => {
    const timer = window.setTimeout(() => {
      w.removeEventListener("message", handler);
      // The only reliable stop for a runaway loop: kill the worker, start a new one.
      w.terminate();
      worker = null;
      readyPromise = null;
      setStatus("idle");
      resolve({ ok: false, stdout: "", stderr: "Превышен лимит времени: 10 с", ms: LIMIT_MS, timedOut: true });
    }, LIMIT_MS);
    const handler = (event: MessageEvent<{ id?: number; ok: boolean; stdout: string; stderr: string; ms: number }>) => {
      if (event.data.id !== id) return;
      window.clearTimeout(timer);
      w.removeEventListener("message", handler);
      resolve({ ...event.data, timedOut: false });
    };
    w.addEventListener("message", handler);
    w.postMessage({ id, code, files: buffers }, Object.values(buffers));
  });
}
