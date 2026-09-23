// Curator mode (design doc 9, 11.9): the «Ученики» tab.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { CoinsChart } from "../components/charts";
import { Button, Card, Chip, ConfidenceBar, Empty, ErrorView, Section, Sheet, Spinner, Toggle, useToast } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { clock, dateShort } from "../lib/format";
import { useBackButton } from "../lib/hooks";
import type { ProgressDay, StudentRow } from "../lib/types";

interface Dashboard {
  students: StudentRow[];
  nudges: Record<string, string>;
}

export function StudentsScreen() {
  const navigate = useNavigate();
  const query = useQuery({ queryKey: ["students"], queryFn: () => api.get<Dashboard>("/curator/students") });
  if (query.isLoading) return <Spinner />;
  if (query.error || !query.data) return <ErrorView error={query.error} onRetry={() => void query.refetch()} />;
  const { students } = query.data;
  if (!students.length) {
    return (
      <Empty title="Учеников пока нет">
        <p>Ученик присылает ссылку‑приглашение из профиля «Байта». Откройте её — и он появится здесь.</p>
      </Empty>
    );
  }
  return (
    <div className="screen" data-testid="students">
      <p className="muted small">Сверху — кому нужно внимание: нет активности, падает уверенность, сорвана серия.</p>
      {students.map((s) => {
        const streak = typeof s.streak === "number" ? s.streak : s.streak?.current;
        return (
          <Card key={s.student_id} onClick={() => navigate(`/students/${s.student_id}`)}>
            <div className="row between">
              <strong>{s.name}</strong>
              {s.risk >= 1 ? <Chip tone="bad">внимание</Chip> : <Chip tone="good">в ритме</Chip>}
            </div>
            <div className="muted small">
              🔥 {streak ?? "—"} · порог сегодня: {s.threshold_today ? "да" : "нет"} · {s.days_idle ? `не заходил ${s.days_idle} дн.` : "заходил сегодня"}
            </div>
          </Card>
        );
      })}
    </div>
  );
}

interface StudentCard {
  student_id: number;
  name: string;
  access: string;
  role: string;
  focus: number[];
  league_enabled: boolean;
  streak?: { current: number; best: number };
  threshold_today?: boolean;
  rank?: string;
  coins_by_day?: { date: string; coins: number; threshold: number; easy: boolean; vacation: boolean }[];
  confidence?: { task_no: number; value: number }[];
  forecast?: { primary: number; test: number; margin: number };
  exams?: { id: number; kind: string; primary: number; test: number; finished_at: string }[];
  subtypes?: { subtype: string; task_no: number; mastery: number; attempts: number }[];
  reasons?: Record<string, number>;
  attempts?: { task_no: number; answer: string; correct: boolean; time_spent_s: number; at: string }[];
  time_spent?: number;
}

export function StudentScreen() {
  const { id } = useParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const toast = useToast((s) => s.show);
  const back = useCallback(() => navigate("/students"), [navigate]);
  useBackButton(back);
  const [nudgeOpen, setNudgeOpen] = useState(false);
  const [focusOpen, setFocusOpen] = useState(false);
  const [focus, setFocus] = useState<number[]>([]);
  const card = useQuery({ queryKey: ["student", id], queryFn: () => api.get<StudentCard>(`/curator/students/${id}`) });
  const dash = useQuery({ queryKey: ["students"], queryFn: () => api.get<Dashboard>("/curator/students") });
  if (card.isLoading) return <Spinner />;
  if (card.error || !card.data) return <ErrorView error={card.error} />;
  const s = card.data;
  const nudge = async (code: string) => {
    try {
      await api.post(`/curator/students/${id}/nudge`, { code }, false);
      toast("Отправлено", "good");
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Не получилось", "bad");
    }
    setNudgeOpen(false);
  };
  const saveFocus = async () => {
    try {
      await api.post(`/curator/students/${id}/focus`, { task_nos: focus }, false);
      toast("Фокус‑тема назначена на неделю", "good");
      await client.invalidateQueries({ queryKey: ["student", id] });
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Не получилось", "bad");
    }
    setFocusOpen(false);
  };
  const setLink = async (body: Record<string, unknown>) => {
    try {
      await api.patch(`/curator/students/${id}/link`, body);
      await client.invalidateQueries({ queryKey: ["student", id] });
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Не получилось", "bad");
    }
  };
  const openReport = async () => {
    const html = await api.get<string>(`/curator/students/${id}/report`);
    const url = URL.createObjectURL(new Blob([html], { type: "text/html" }));
    window.open(url, "_blank", "noopener");
    window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
  };
  const days: ProgressDay[] = (s.coins_by_day ?? []).map((d) => ({
    date: d.date, coins: d.coins, tasks: 0, threshold_met: d.coins >= d.threshold, easy: d.easy, vacation: d.vacation, today: false,
  }));
  return (
    <div className="screen" data-testid="student-card">
      <h1>{s.name}</h1>
      <p className="muted small">Доступ: {s.access === "fact" ? "только факт" : s.access === "progress" ? "прогресс" : "полный"} · выбирает ученик</p>
      <Card>
        🔥 {s.streak?.current ?? 0} (лучшая {s.streak?.best ?? 0}) · порог сегодня: {s.threshold_today ? "да" : "нет"} · {s.rank}
      </Card>
      <div className="row gap wrap">
        <Button onClick={() => setNudgeOpen(true)}>Пинок</Button>
        {s.role === "tutor" ? <Button kind="secondary" onClick={() => { setFocus(s.focus); setFocusOpen(true); }}>Фокус‑тема</Button> : null}
        <Button kind="secondary" onClick={() => void openReport()}>Недельный отчёт</Button>
      </div>
      {s.focus.length ? <p className="note">Фокус недели: {s.focus.join(", ")}</p> : null}
      {s.forecast ? <Card className="forecast">Прогноз: ≈ {s.forecast.primary} первичных / {s.forecast.test} тестовых (±{s.forecast.margin})</Card> : null}
      {days.length ? (
        <Section title="Монеты по дням">
          <CoinsChart days={days} threshold={30} cap={120} />
        </Section>
      ) : null}
      {s.confidence ? (
        <Section title="Уверенность">
          {s.confidence.map((c) => (
            <div key={c.task_no} className="conf-mini">
              <span>{c.task_no}</span>
              <ConfidenceBar value={c.value} />
            </div>
          ))}
        </Section>
      ) : null}
      {s.exams?.length ? (
        <Section title="Экзамены">
          {s.exams.map((e) => <p key={e.id}>{dateShort(e.finished_at)}: {e.primary}{e.test ? ` / ${e.test}` : ""}</p>)}
        </Section>
      ) : null}
      {s.reasons && Object.keys(s.reasons).length ? (
        <Section title="Причины затруднений">
          {Object.entries(s.reasons).map(([code, n]) => <p key={code}>{code}: {n}</p>)}
        </Section>
      ) : null}
      {s.attempts?.length ? (
        <Section title="Последние попытки">
          {s.attempts.slice(0, 20).map((a, i) => (
            <div key={i} className="tx">
              <span>{a.task_no}: {a.answer}</span>
              <span className={a.correct ? "good" : "bad"}>{a.correct ? "✓" : "✗"} {clock(a.time_spent_s)}</span>
            </div>
          ))}
        </Section>
      ) : null}
      <Section title="Настройки связи">
        {s.role === "tutor" ? (
          <Toggle label="Лига группы (место по XP за неделю)" checked={s.league_enabled} onChange={(v) => void setLink({ league_enabled: v })} />
        ) : null}
        <label className="field">Ежедневная сводка в
          <input className="input" type="time" onBlur={(e) => e.target.value && void setLink({ daily_digest_time: e.target.value })} />
        </label>
      </Section>
      <Sheet open={nudgeOpen} onClose={() => setNudgeOpen(false)} title="Пинок (не чаще раза в день)">
        {Object.entries(dash.data?.nudges ?? {}).map(([code, text]) => (
          <Button key={code} kind="secondary" onClick={() => void nudge(code)}>{text}</Button>
        ))}
      </Sheet>
      <Sheet open={focusOpen} onClose={() => setFocusOpen(false)} title="Фокус‑тема на неделю (до 3 заданий)">
        <div className="task-picker">
          {Array.from({ length: 27 }, (_, i) => i + 1).map((n) => (
            <button key={n} className={focus.includes(n) ? "active" : ""}
              onClick={() => setFocus((f) => (f.includes(n) ? f.filter((x) => x !== n) : f.length < 3 ? [...f, n] : f))}>
              {n}
            </button>
          ))}
        </div>
        <Button onClick={() => void saveFocus()} disabled={!focus.length}>Назначить</Button>
      </Sheet>
    </div>
  );
}
