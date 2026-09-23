// Tools of the task screen (11.4): Python (browser or server), Table, Draft.
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react";

import { api } from "../lib/api";
import { explainLine } from "../lib/explain";
import { parseBlocks } from "../lib/markdown";
import { onPythonStatus, pythonStatus, runPython, type PyStatus } from "../lib/python";
import { parseCsv, type Table } from "../lib/sheet";
import type { InstanceView } from "../lib/types";
import { downloadAsset } from "./Assets";
import { Grid, type Walls } from "./Grid";
import { Button, Spinner, useToast } from "./ui";

const Editor = lazy(() => import("./Editor"));

interface RunView {
  ok: boolean;
  stdout: string;
  stderr: string;
  ms: number;
  where: "browser" | "server";
}

export function useDraftSaver(instanceId: number) {
  const timer = useRef<number | null>(null);
  const pending = useRef<Record<string, string>>({});
  useEffect(() => () => {
    if (timer.current) window.clearTimeout(timer.current);
  }, []);
  return (field: "answer" | "code" | "notes", value: string) => {
    pending.current[field] = value;
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      const body = pending.current;
      pending.current = {};
      void api.patch(`/instances/${instanceId}/draft`, body).catch(() => undefined);
    }, 800);
  };
}

function firstCodeBlock(markdown: string): string | null {
  const block = parseBlocks(markdown).find((b) => b.type === "code");
  return block && block.type === "code" ? block.text : null;
}

export function CodePanel({
  instance,
  code,
  onCode,
  serverRun,
  initialTab,
}: {
  instance: InstanceView;
  code: string;
  onCode: (code: string) => void;
  serverRun: boolean;
  initialTab?: "python" | "table" | "draft" | null;
}) {
  const tables = instance.assets.filter((a) => a.kind === "csv");
  const [tab, setTab] = useState<"python" | "table" | "draft" | null>(initialTab ?? null);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<RunView | null>(null);
  const [status, setStatus] = useState<PyStatus>(pythonStatus());
  const [notes, setNotes] = useState(instance.draft.notes ?? "");
  const [table, setTable] = useState<{ name: string; data: Table } | null>(null);
  const [walls, setWalls] = useState<Walls | null>(null);
  const [line, setLine] = useState("");
  const [explained, setExplained] = useState<string[] | null>(null);
  const toast = useToast((s) => s.show);
  const saveDraft = useDraftSaver(instance.id);
  useEffect(() => onPythonStatus(setStatus), []);

  const files = useMemo(() => instance.assets.filter((a) => a.kind !== "svg"), [instance.assets]);

  const run = async () => {
    setRunning(true);
    try {
      if (serverRun) {
        const r = await api.post<{ ok: boolean; stdout: string; stderr: string; duration_ms: number }>(
          `/instances/${instance.id}/run`, { code }, false,
        );
        setResult({ ok: r.ok, stdout: r.stdout, stderr: r.stderr, ms: r.duration_ms, where: "server" });
      } else {
        const blobs: Record<string, Blob> = {};
        for (const file of files) blobs[file.name] = await downloadAsset(instance.id, file.name);
        const r = await runPython(code, blobs);
        setResult({ ok: r.ok, stdout: r.stdout, stderr: r.stderr, ms: r.ms, where: "browser" });
        // Counts as "ran the program at least once" for the anti-cheat rule (7.5.2).
        void api.post(`/instances/${instance.id}/ran`, { code }, false).catch(() => undefined);
      }
    } catch (error) {
      toast(error instanceof Error ? error.message : "Не удалось запустить", "bad");
    } finally {
      setRunning(false);
    }
  };

  const insertTemplate = async () => {
    try {
      const card = await api.get<{ body_md: string }>(`/theory/card/${encodeURIComponent(instance.method_card_id)}`);
      const template = firstCodeBlock(card.body_md);
      if (template) onCode(code.trim() ? `${code}\n\n${template}` : template);
      else toast("У этой карточки нет шаблона кода");
    } catch {
      toast("Шаблон не загрузился", "bad");
    }
  };

  const openTable = async (name: string) => {
    try {
      const blob = await downloadAsset(instance.id, name);
      setTable({ name, data: parseCsv(await blob.text()) });
      // Task 18: the robot's walls are drawn as bold borders on the grid.
      if (instance.assets.some((a) => a.name === "walls.json") && !walls) {
        const raw = await (await downloadAsset(instance.id, "walls.json")).text();
        setWalls(JSON.parse(raw) as Walls);
      }
    } catch {
      toast("Таблица не загрузилась", "bad");
    }
  };

  return (
    <div className="tools">
      <div className="tool-tabs" role="tablist">
        <button role="tab" aria-selected={tab === "python"} className={tab === "python" ? "active" : ""} onClick={() => setTab(tab === "python" ? null : "python")}>
          🐍 Python
        </button>
        {tables.length ? (
          <button role="tab" aria-selected={tab === "table"} className={tab === "table" ? "active" : ""} onClick={() => { setTab(tab === "table" ? null : "table"); if (!table && tables[0]) void openTable(tables[0].name); }}>
            ▦ Таблица
          </button>
        ) : null}
        <button role="tab" aria-selected={tab === "draft"} className={tab === "draft" ? "active" : ""} onClick={() => setTab(tab === "draft" ? null : "draft")}>
          ✎ Черновик
        </button>
      </div>
      {tab === "python" ? (
        <div className="tool-body">
          <Suspense fallback={<Spinner label="Открываю редактор…" />}>
            <Editor value={code} onChange={(v) => { onCode(v); saveDraft("code", v); }} onLine={(l) => { setLine(l); setExplained(null); }} />
          </Suspense>
          <div className="row gap">
            <Button onClick={() => void run()} busy={running} testId="run-code">▶ Запустить</Button>
            <Button kind="ghost" small onClick={() => void insertTemplate()}>Шаблон</Button>
            <Button kind="ghost" small onClick={() => setExplained(explainLine(line))} testId="explain-line">Объяснить строку</Button>
            {!serverRun && status === "loading" ? <span className="muted">Загружаю Python (~10 МБ, один раз)…</span> : null}
          </div>
          {explained ? (
            <div className="note small" data-testid="explanation">
              <code>{line.trim() || "(пустая строка)"}</code>
              <ul>{explained.map((e, i) => <li key={i}>{e}</li>)}</ul>
            </div>
          ) : null}
          {files.length ? (
            <small className="muted block">
              Файлы доступны программе по имени: {files.map((f) => f.name).join(", ")}. Запуск — не дольше 10 с.
            </small>
          ) : null}
          {result ? (
            <div className={`output${result.ok ? "" : " output-err"}`} data-testid="run-output">
              <pre>{result.stdout || (result.ok ? "(пустой вывод)" : "")}</pre>
              {result.stderr ? <pre className="stderr">{result.stderr}</pre> : null}
              <small className="muted">
                {result.where === "server" ? "Сервер" : "Браузер"} · {Math.round(result.ms)} мс
              </small>
            </div>
          ) : null}
        </div>
      ) : null}
      {tab === "table" ? (
        <div className="tool-body">
          {tables.length > 1 ? (
            <div className="chips">
              {tables.map((t) => (
                <button key={t.name} className={`chip-btn${table?.name === t.name ? " active" : ""}`} onClick={() => void openTable(t.name)}>
                  {t.name}
                </button>
              ))}
            </div>
          ) : null}
          {table ? <Grid table={table.data} walls={walls} /> : <Spinner />}
        </div>
      ) : null}
      {tab === "draft" ? (
        <div className="tool-body">
          <textarea
            className="input draft"
            value={notes}
            placeholder="Записи для себя: сохраняются в этой задаче"
            onChange={(e) => { setNotes(e.target.value); saveDraft("notes", e.target.value); }}
          />
        </div>
      ) : null}
    </div>
  );
}
