// Admin panel (build prompt, stage 10): economy health, funnel, generators, tickets,
// live config (prices, FIPI toggles), users, broadcasts, audit.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button, Card, Chip, ErrorView, Section, Spinner, useToast } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { useBackButton } from "../lib/hooks";

const TABS = [
  ["economy", "Экономика"],
  ["funnel", "Воронка"],
  ["generators", "Генераторы"],
  ["issues", "Тикеты"],
  ["config", "Конфиг"],
  ["users", "Пользователи"],
  ["misc", "Прочее"],
] as const;

type Tab = (typeof TABS)[number][0];

function Json({ value }: { value: unknown }) {
  return <pre className="code-block small">{JSON.stringify(value, null, 2)}</pre>;
}

function Economy() {
  const q = useQuery({ queryKey: ["admin", "economy"], queryFn: () => api.get<Record<string, unknown>>("/admin/economy") });
  if (!q.data) return q.error ? <ErrorView error={q.error} /> : <Spinner />;
  const d = q.data as {
    earned: number; spent: number; spent_to_earned: number | null; spent_to_earned_ok: boolean;
    average_balance_active: number; average_balance_ok: boolean; reveal_after_error: number | null; reveal_after_error_ok: boolean;
    by_reason: { reason: string; sum: number; count: number }[];
  };
  const flag = (ok: boolean) => <Chip tone={ok ? "good" : "bad"}>{ok ? "в норме" : "вне цели"}</Chip>;
  return (
    <>
      <Card>Заработано {d.earned} · потрачено {d.spent}</Card>
      <Card>Потрачено/заработано: {d.spent_to_earned ?? "—"} (цель 0,7–0,95) {flag(d.spent_to_earned_ok)}</Card>
      <Card>Средний баланс активных: {d.average_balance_active} (цель &lt; 400) {flag(d.average_balance_ok)}</Card>
      <Card>Разбор после ошибки: {d.reveal_after_error ?? "—"} (цель 0,3–0,5) {flag(d.reveal_after_error_ok)}</Card>
      <Section title="По причинам">
        {d.by_reason.map((r) => <div key={r.reason} className="tx"><span>{r.reason} × {r.count}</span><span>{r.sum}</span></div>)}
      </Section>
    </>
  );
}

function Funnel() {
  const q = useQuery({ queryKey: ["admin", "funnel"], queryFn: () => api.get<Record<string, unknown>>("/admin/funnel") });
  if (!q.data) return q.error ? <ErrorView error={q.error} /> : <Spinner />;
  return <Json value={q.data} />;
}

function Generators() {
  const toast = useToast((s) => s.show);
  const [smoke, setSmoke] = useState<{ task_no: number; ok: boolean; checked: number; problems: string[]; seconds: number }[] | null>(null);
  const [busy, setBusy] = useState(false);
  const q = useQuery({
    queryKey: ["admin", "generators"],
    queryFn: () => api.get<{ task_no: number; issued: number; reported: number; confirmed: number; open: number; confirmed_rate: number; ok: boolean }[]>("/admin/generators"),
  });
  const run = async () => {
    setBusy(true);
    try {
      setSmoke(await api.post("/admin/generators/smoke", {}, false));
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Не получилось", "bad");
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <Button onClick={() => void run()} busy={busy}>Смоук‑прогон всех 27 генераторов</Button>
      {smoke ? smoke.map((s) => (
        <div key={s.task_no} className="tx">
          <span>{s.task_no}: {s.checked} экз. · {s.seconds} с</span>
          <span>{s.ok ? "✓" : `✗ ${s.problems[0] ?? ""}`}</span>
        </div>
      )) : null}
      <Section title="Ошибки за 30 дней (цель < 0,3 %)">
        {q.data?.map((g) => (
          <div key={g.task_no} className="tx">
            <span>{g.task_no}: выдано {g.issued}, жалоб {g.reported}, подтверждено {g.confirmed}</span>
            <Chip tone={g.ok ? "good" : "bad"}>{(g.confirmed_rate * 100).toFixed(2)}%</Chip>
          </div>
        ))}
      </Section>
    </>
  );
}

interface Issue {
  id: number; text: string; task_no: number; subtype: string; difficulty: number; seed: number;
  gen_version: string; statement_md: string; expected: string; student_answers: string[];
}

function Issues() {
  const client = useQueryClient();
  const q = useQuery({ queryKey: ["admin", "issues"], queryFn: () => api.get<Issue[]>("/admin/issues") });
  const resolve = async (id: number, confirmed: boolean) => {
    await api.post(`/admin/issues/${id}/resolve`, { confirmed, resolution: confirmed ? "Ошибка подтверждена, генератор исправляется" : "Ошибки в задаче нет" }, false);
    await client.invalidateQueries({ queryKey: ["admin", "issues"] });
  };
  if (!q.data) return q.error ? <ErrorView error={q.error} /> : <Spinner />;
  if (!q.data.length) return <p className="muted">Открытых тикетов нет.</p>;
  return (
    <>
      {q.data.map((i) => (
        <Card key={i.id}>
          <strong>#{i.id} · задание {i.task_no} ({i.subtype}, ур. {i.difficulty})</strong>
          <p>{i.text}</p>
          <p className="muted small">seed {i.seed} · версия {i.gen_version} · эталон {i.expected} · ответы: {i.student_answers.join(", ") || "—"}</p>
          <details><summary>Условие</summary><pre className="code-block small">{i.statement_md}</pre></details>
          <div className="row gap">
            <Button small onClick={() => void resolve(i.id, true)}>Подтвердить (+20 🪙)</Button>
            <Button small kind="ghost" onClick={() => void resolve(i.id, false)}>Отклонить</Button>
          </div>
        </Card>
      ))}
    </>
  );
}

function Config() {
  const toast = useToast((s) => s.show);
  const [section, setSection] = useState("fipi");
  const [patch, setPatch] = useState("{\n  \"t10\": {\"answer_transform\": \"octet_sum\"}\n}");
  const q = useQuery({ queryKey: ["admin", "config"], queryFn: () => api.get<Record<string, unknown>>("/admin/config") });
  const apply = async (remove = false) => {
    try {
      const body = remove ? null : (JSON.parse(patch) as Record<string, unknown>);
      await api.put(`/admin/config/${section}`, { patch: body });
      toast("Применено без деплоя", "good");
      await q.refetch();
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Неверный JSON", "bad");
    }
  };
  return (
    <>
      <p className="muted small">
        Переопределение поверх YAML. Цены меняются только вместе с season_id (5.6). Переключатели ФИПИ: t10.answer_transform,
        t23.graph_input_format, t27.answer_layout.
      </p>
      <select className="input" value={section} onChange={(e) => setSection(e.target.value)}>
        {["fipi", "economy", "floors", "curriculum"].map((s) => <option key={s}>{s}</option>)}
      </select>
      <textarea className="input mono" rows={8} value={patch} onChange={(e) => setPatch(e.target.value)} />
      <div className="row gap">
        <Button onClick={() => void apply()}>Применить</Button>
        <Button kind="ghost" onClick={() => void apply(true)}>Сбросить раздел</Button>
      </div>
      {q.data ? <details><summary>Текущая конфигурация</summary><Json value={(q.data as Record<string, unknown>)[section]} /></details> : null}
    </>
  );
}

function Users() {
  const toast = useToast((s) => s.show);
  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<{ id: number; tg_id: number; name: string; username: string | null; balance: number }[]>([]);
  const search = async () => setRows(await api.get(`/admin/users?q=${encodeURIComponent(query)}`));
  const grant = async (id: number) => {
    const delta = Number(window.prompt("Сколько монет (можно отрицательное)?", "20"));
    const reason = window.prompt("Причина (попадёт в аудит)") ?? "";
    if (!delta || !reason) return;
    try {
      await api.post(`/admin/users/${id}/coins`, { delta, reason }, false);
      toast("Начислено", "good");
      await search();
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Не получилось", "bad");
    }
  };
  return (
    <>
      <div className="row gap">
        <input className="input" placeholder="id, tg id или @username" value={query} onChange={(e) => setQuery(e.target.value)} />
        <Button small onClick={() => void search()} disabled={!query}>Найти</Button>
      </div>
      {rows.map((u) => (
        <div key={u.id} className="tx">
          <span>{u.name} {u.username ? `@${u.username}` : ""} · tg {u.tg_id}</span>
          <span>{u.balance} 🪙 <Button small kind="ghost" onClick={() => void grant(u.id)}>±🪙</Button></span>
        </div>
      ))}
    </>
  );
}

function Misc() {
  const toast = useToast((s) => s.show);
  const [summary, setSummary] = useState("");
  const anomalies = useQuery({ queryKey: ["admin", "anomalies"], queryFn: () => api.get<unknown[]>("/admin/anomalies") });
  const other = useQuery({ queryKey: ["admin", "other"], queryFn: () => api.get<{ subtype: string; count: number; texts: string[] }[]>("/admin/feedback/other") });
  const audit = useQuery({ queryKey: ["admin", "audit"], queryFn: () => api.get<{ id: number; action: string; target: string; created_at: string }[]>("/admin/audit") });
  const broadcast = async () => {
    const r = await api.post<{ scheduled: number }>("/admin/broadcast/demo", { summary }, false);
    toast(`Запланировано: ${r.scheduled}`, "good");
  };
  return (
    <>
      <Section title="«Утверждена демоверсия» — рассылка">
        <textarea className="input" value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="Что изменилось в 10, 13, 23, 27" />
        <Button onClick={() => void broadcast()} disabled={summary.length < 10}>Разослать</Button>
      </Section>
      <Section title="Аномалии (сигнал, без санкций)"><Json value={anomalies.data ?? []} /></Section>
      <Section title="«Другое» для методиста">
        {other.data?.map((o) => (
          <details key={o.subtype}><summary>{o.subtype} · {o.count}</summary><ul>{o.texts.map((t, i) => <li key={i}>{t}</li>)}</ul></details>
        ))}
      </Section>
      <Section title="Аудит">
        {audit.data?.map((a) => <div key={a.id} className="tx"><span>{a.action} {a.target}</span><span>{a.created_at.slice(0, 16)}</span></div>)}
      </Section>
    </>
  );
}

export function AdminScreen() {
  const navigate = useNavigate();
  const back = useCallback(() => navigate("/profile"), [navigate]);
  useBackButton(back);
  const [tab, setTab] = useState<Tab>("economy");
  return (
    <div className="screen admin" data-testid="admin">
      <div className="tabs-scroll">
        {TABS.map(([key, title]) => (
          <button key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>{title}</button>
        ))}
      </div>
      {tab === "economy" ? <Economy /> : null}
      {tab === "funnel" ? <Funnel /> : null}
      {tab === "generators" ? <Generators /> : null}
      {tab === "issues" ? <Issues /> : null}
      {tab === "config" ? <Config /> : null}
      {tab === "users" ? <Users /> : null}
      {tab === "misc" ? <Misc /> : null}
    </div>
  );
}
