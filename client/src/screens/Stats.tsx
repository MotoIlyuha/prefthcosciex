// «Прогресс» (11.6), «Уверенность» (11.7) and the method cards.
import { useQuery } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { CoinsChart, Heatmap } from "../components/charts";
import { Button, Card, Chip, ConfidenceBar, ErrorView, Section, Spinner, useToast } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { plural } from "../lib/format";
import { useBackButton } from "../lib/hooks";
import { Markdown } from "../lib/markdown";
import type { ConfidenceView, InstanceView, ProgressView } from "../lib/types";

const RANGES = [
  { key: "7d", label: "7 дней" },
  { key: "30d", label: "30 дней" },
  { key: "90d", label: "90 дней" },
  { key: "all", label: "Всё" },
];

export function ProgressScreen() {
  const [range, setRange] = useState("30d");
  const query = useQuery({ queryKey: ["progress", range], queryFn: () => api.get<ProgressView>(`/progress?range=${range}`) });
  const heat = useQuery({ queryKey: ["progress", "90d"], queryFn: () => api.get<ProgressView>("/progress?range=90d") });
  if (query.isLoading) return <Spinner />;
  if (query.error || !query.data) return <ErrorView error={query.error} onRetry={() => void query.refetch()} />;
  const p = query.data;
  const t = p.totals;
  return (
    <div className="screen" data-testid="progress">
      <div className="segmented">
        {RANGES.map((r) => (
          <button key={r.key} className={range === r.key ? "active" : ""} onClick={() => setRange(r.key)}>{r.label}</button>
        ))}
      </div>
      <Section title="Монеты по дням">
        <CoinsChart days={p.days} threshold={p.threshold} cap={p.cap} />
        <p className="muted small">Линии: порог {p.threshold} и кэп {p.cap}. Серые — лёгкие дни и отпуск.</p>
      </Section>
      <Section title="Серия">
        {heat.data ? <Heatmap days={heat.data.days} /> : null}
        <p>🔥 {t.streak} {plural(t.streak, "день", "дня", "дней")} · лучшая {t.best_streak}</p>
        <div className="row gap wrap">
          {p.milestones.map((m) => <Chip key={m} tone={t.best_streak >= m ? "good" : "neutral"}>{m}</Chip>)}
        </div>
      </Section>
      <Section title="Итого">
        <div className="stats-grid">
          <div><strong>{t.solved}</strong><span>задач решено</span></div>
          <div><strong>{t.hours}</strong><span>часов практики</span></div>
          <div><strong>{t.active_days}</strong><span>дней с задачами</span></div>
          <div><strong>{t.rank}</strong><span>{t.next_rank_xp ? `${t.xp} / ${t.next_rank_xp} XP` : `${t.xp} XP`}</span></div>
        </div>
      </Section>
      <Section title="Неделя">
        <div className="week">
          {p.week.map((w) => (
            <div key={w.day} className="week-day">
              <div className="week-bar" style={{ height: `${Math.min(100, w.avg_tasks * 20)}%` }} />
              <span>{w.day}</span>
            </div>
          ))}
        </div>
        <p className="muted small">Среднее число задач по дням недели — видно, когда идёт лучше.</p>
      </Section>
    </div>
  );
}

const TREND = { up: "↑", down: "↓", flat: "→" } as const;

export function ConfidenceScreen() {
  const navigate = useNavigate();
  const query = useQuery({ queryKey: ["confidence"], queryFn: () => api.get<ConfidenceView>("/confidence") });
  if (query.isLoading) return <Spinner />;
  if (query.error || !query.data) return <ErrorView error={query.error} onRetry={() => void query.refetch()} />;
  const c = query.data;
  return (
    <div className="screen" data-testid="confidence">
      <Card className="forecast">
        <div className="muted small">Прогноз балла</div>
        <div className="big">≈ {c.forecast.primary} первичных / {c.forecast.test} тестовых (±{c.forecast.margin})</div>
        <div className="muted small">
          Цель: {c.band.title} ({c.band.range[0]}–{c.band.range[1]}){c.forecast.from_exam ? " · учтён последний экзамен" : ""}
        </div>
      </Card>
      {c.focus.length ? <p className="note">Куратор попросил уделить внимание: {c.focus.map((t) => `${t}‑му`).join(", ")}.</p> : null}
      {c.tasks.map((t) => (
        <Card key={t.task_no} onClick={() => navigate(`/confidence/${t.task_no}`)} className="conf-row">
          <div className="row between">
            <span><strong>{t.task_no}</strong> {t.title}</span>
            <span className={`trend trend-${t.trend}`}>{Math.round(t.value)}% {TREND[t.trend]}</span>
          </div>
          <ConfidenceBar value={t.value} />
          <div className="muted small">
            {t.attempts} {plural(t.attempts, "попытка", "попытки", "попыток")}
            {t.points === 2 ? " · 2 балла" : ""}
            {t.arbiter_note ? ` · ${t.arbiter_note}` : ""}
          </div>
        </Card>
      ))}
    </div>
  );
}

interface ConfidenceDetail {
  task_no: number;
  title: string;
  subtypes: { subtype: string; title: string; mastery: number; attempts: number; card_id: string }[];
  reasons: { code: string; text: string; count: number }[];
  top_reason: string | null;
  method_card_id: string | null;
}

export function ConfidenceTaskScreen() {
  const { task } = useParams();
  const navigate = useNavigate();
  const toast = useToast((s) => s.show);
  const back = useCallback(() => navigate("/confidence"), [navigate]);
  useBackButton(back);
  const query = useQuery({ queryKey: ["confidence", task], queryFn: () => api.get<ConfidenceDetail>(`/confidence/${task}`) });
  if (query.isLoading) return <Spinner />;
  if (query.error || !query.data) return <ErrorView error={query.error} />;
  const d = query.data;
  const practice = async (subtype?: string) => {
    try {
      const inst = await api.post<InstanceView>("/instances/similar", { task_no: d.task_no, subtype: subtype ?? null });
      navigate(`/task/${inst.id}`);
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Не получилось", "bad");
    }
  };
  return (
    <div className="screen">
      <h1>{d.task_no}. {d.title}</h1>
      {d.top_reason ? <p className="note">{d.top_reason}</p> : null}
      <div className="row gap wrap">
        <Button onClick={() => void practice()} testId="practice-now">Практиковать сейчас</Button>
        <Button kind="secondary" onClick={() => navigate(`/theory/${d.task_no}`)}>Карточка метода</Button>
      </div>
      <Section title="Подтипы">
        {d.subtypes.map((s) => (
          <Card key={s.subtype}>
            <div className="row between">
              <span>{s.title}</span>
              <span className="muted">{Math.round(s.mastery)}%</span>
            </div>
            <ConfidenceBar value={s.mastery} />
            <Button small kind="ghost" onClick={() => void practice(s.subtype)}>Задача этого типа</Button>
          </Card>
        ))}
      </Section>
      {d.reasons.length ? (
        <Section title="Что мешает">
          {d.reasons.map((r) => <p key={r.code}>{r.text} — {r.count}</p>)}
        </Section>
      ) : null}
    </div>
  );
}

export function TheoryScreen() {
  const { task } = useParams();
  const navigate = useNavigate();
  const back = useCallback(() => navigate(-1), [navigate]);
  useBackButton(back);
  const query = useQuery({
    queryKey: ["theory", task],
    queryFn: () => api.get<{ task_no: number; cards: { id: string; subtype: string | null; body_md: string }[] }>(`/theory/${task}`),
  });
  if (query.isLoading) return <Spinner />;
  if (query.error || !query.data) return <ErrorView error={query.error} />;
  return (
    <div className="screen theory">
      <h1>Задание {query.data.task_no}: методы</h1>
      {query.data.cards.map((c) => (
        <Card key={c.id}>
          <Markdown source={c.body_md} />
        </Card>
      ))}
    </div>
  );
}
