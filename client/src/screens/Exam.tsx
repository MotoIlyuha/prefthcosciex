// «Экзамен» (design doc 8): KEGE-style sheet, timer that keeps running, results.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { FileChips, Figures } from "../components/Assets";
import { LineChart } from "../components/charts";
import { CodePanel } from "../components/CodePanel";
import { Button, Card, Chip, ErrorView, Section, Sheet, Spinner, Toggle, useToast } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { ANSWER_HINTS, clock, dateShort } from "../lib/format";
import { useBackButton, useMe, useNow } from "../lib/hooks";
import { Markdown } from "../lib/markdown";
import { setClosingConfirmation } from "../lib/tg";
import type { ExamView } from "../lib/types";

interface Offer {
  formats: { kind: string; tasks: number; minutes: number | string; price: number }[];
  free_full_left: number;
  tickets: number;
  balance: number;
}

interface History {
  id: number;
  kind: string;
  training: boolean;
  started_at: string;
  finished_at: string | null;
  primary: number | null;
  test: number | null;
}

const KIND_TITLE: Record<string, string> = { full: "Полный вариант", half: "Половина (1–15)", block: "Блок: 5 заданий темы" };

export function ExamHome() {
  const navigate = useNavigate();
  const toast = useToast((s) => s.show);
  const client = useQueryClient();
  const [training, setTraining] = useState(false);
  const [blockTask, setBlockTask] = useState(15);
  const [busy, setBusy] = useState<string | null>(null);
  const query = useQuery({ queryKey: ["exams"], queryFn: () => api.get<{ offer: Offer; history: History[] }>("/exams") });
  if (query.isLoading) return <Spinner />;
  if (query.error || !query.data) return <ErrorView error={query.error} onRetry={() => void query.refetch()} />;
  const { offer, history } = query.data;
  const active = history.find((h) => !h.finished_at);

  const start = async (kind: string) => {
    setBusy(kind);
    try {
      const exam = await api.post<ExamView>("/exams", { kind, training, task_no: kind === "block" ? blockTask : null });
      client.setQueryData(["exam", exam.id], exam);
      navigate(`/exam/${exam.id}`);
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Не получилось", "bad");
    } finally {
      setBusy(null);
    }
  };

  const price = (kind: string, value: number) => {
    if (training) return "бесплатно";
    if (kind === "full" && offer.free_full_left > 0) return "бесплатно (раз в месяц)";
    if (kind === "full" && offer.tickets > 0) return "билет";
    return `${value} 🪙`;
  };

  return (
    <div className="screen" data-testid="exam-home">
      {active ? (
        <Card onClick={() => navigate(`/exam/${active.id}`)}>⏱ Продолжить начатый экзамен</Card>
      ) : null}
      <Section title="Формат">
        <Toggle label="Тренировочный режим" checked={training} onChange={setTraining}
          hint="С паузой и без оплаты; не влияет на прогноз и уверенность" />
        {offer.formats.map((f) => (
          <Card key={f.kind}>
            <div className="row between">
              <div>
                <strong>{KIND_TITLE[f.kind]}</strong>
                <div className="muted small">{f.tasks} заданий · {f.minutes} мин</div>
              </div>
              <Chip tone="accent">{price(f.kind, f.price)}</Chip>
            </div>
            {f.kind === "block" ? (
              <label className="field row gap">
                Задание
                <select className="input" value={blockTask} onChange={(e) => setBlockTask(Number(e.target.value))}>
                  {Array.from({ length: 27 }, (_, i) => i + 1).map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
              </label>
            ) : null}
            <Button onClick={() => void start(f.kind)} busy={busy === f.kind} disabled={Boolean(active)} testId={`start-${f.kind}`}>Начать</Button>
          </Card>
        ))}
        <p className="muted small">Баланс {offer.balance} 🪙 · билетов {offer.tickets}. Разборы всех ошибок после экзамена — бесплатно.</p>
      </Section>
      {history.length ? (
        <Section title="История">
          {history.filter((h) => h.finished_at).map((h) => (
            <Card key={h.id} onClick={() => navigate(`/exam/${h.id}`)}>
              <div className="row between">
                <span>{KIND_TITLE[h.kind]}{h.training ? " · тренировка" : ""}</span>
                <span>{h.primary ?? "—"}{h.test ? ` / ${h.test}` : ""} · {dateShort(h.finished_at ?? h.started_at)}</span>
              </div>
            </Card>
          ))}
        </Section>
      ) : null}
    </div>
  );
}

export function ExamRun() {
  const { id } = useParams();
  const examId = Number(id);
  const navigate = useNavigate();
  const toast = useToast((s) => s.show);
  const client = useQueryClient();
  const me = useMe();
  const query = useQuery({ queryKey: ["exam", examId], queryFn: () => api.get<ExamView>(`/exams/${examId}`) });
  const [position, setPosition] = useState(1);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [code, setCode] = useState<Record<number, string>>({});
  const [confirm, setConfirm] = useState(false);
  const [finishing, setFinishing] = useState(false);
  const [openedAt, setOpenedAt] = useState(Date.now());
  const now = useNow();
  const back = useCallback(() => navigate("/exam"), [navigate]);
  useBackButton(back);
  const exam = query.data;
  const running = Boolean(exam && !exam.finished);

  useEffect(() => {
    setClosingConfirmation(running);
    return () => setClosingConfirmation(false);
  }, [running]);

  useEffect(() => {
    if (!exam) return;
    setAnswers((prev) => {
      const next = { ...prev };
      for (const item of exam.sheet) if (next[item.position] === undefined) next[item.position] = item.answer ?? "";
      return next;
    });
  }, [exam]);

  const deadline = useMemo(() => (exam ? Date.now() + exam.seconds_left * 1000 : 0), [exam]);
  const left = exam?.paused ? exam.seconds_left : Math.max(0, Math.round((deadline - now) / 1000));

  useEffect(() => {
    if (running && !exam?.paused && left === 0) void query.refetch();
  }, [left, running, exam?.paused, query]);

  if (query.isLoading) return <Spinner />;
  if (query.error || !exam) return <ErrorView error={query.error} onRetry={() => void query.refetch()} />;
  if (exam.finished) return <ExamResultView exam={exam} />;

  const item = exam.sheet.find((s) => s.position === position) ?? exam.sheet[0]!;
  const save = async () => {
    try {
      await api.post(`/exams/${examId}/answers`, {
        position: item.position,
        answer: answers[item.position] ?? "",
        time_spent_s: item.time_spent_s + Math.round((Date.now() - openedAt) / 1000),
      }, false);
      await query.refetch();
      toast("Сохранено", "good");
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Не сохранилось", "bad");
    }
  };
  const go = (p: number) => {
    setPosition(p);
    setOpenedAt(Date.now());
  };
  const finish = async () => {
    setFinishing(true);
    try {
      await api.post(`/exams/${examId}/finish`);
      await client.invalidateQueries({ queryKey: ["exams"] });
      await query.refetch();
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Не получилось", "bad");
    } finally {
      setFinishing(false);
      setConfirm(false);
    }
  };
  const pause = async (paused: boolean) => {
    await api.post(`/exams/${examId}/${paused ? "pause" : "resume"}`, {}, false);
    await query.refetch();
  };

  return (
    <div className="screen exam-run" data-testid="exam-run">
      <div className="exam-bar">
        <strong className={left < 300 ? "timer warn" : "timer"}>⏱ {clock(left)}</strong>
        {exam.training ? (
          <Button small kind="ghost" onClick={() => void pause(!exam.paused)}>{exam.paused ? "Продолжить" : "Пауза"}</Button>
        ) : null}
        <Button small kind="danger" onClick={() => setConfirm(true)}>Завершить</Button>
      </div>
      <div className="exam-list" role="tablist">
        {exam.sheet.map((s) => (
          <button key={s.position} role="tab" aria-selected={s.position === position}
            className={`exam-cell${s.position === position ? " active" : ""}${s.answered ? " answered" : ""}`}
            onClick={() => go(s.position)}>
            {exam.kind === "block" ? s.position : s.task_no}
          </button>
        ))}
      </div>
      {exam.paused ? (
        <Card><p>Пауза. Задания скрыты, таймер стоит.</p></Card>
      ) : (
        <>
          <h2>Задание {item.task_no}</h2>
          <Markdown source={item.instance.statement_md} className="md statement" />
          <Figures assets={item.instance.assets} />
          <FileChips instanceId={item.instance.id} assets={item.instance.assets} />
          <CodePanel key={item.instance.id} instance={item.instance} code={code[item.position] ?? ""}
            onCode={(v) => setCode((c) => ({ ...c, [item.position]: v }))} serverRun={Boolean(me.data?.settings.run_code_on_server)} />
          <div className="answer-box">
            <label className="muted small">Ответ ({ANSWER_HINTS[item.instance.answer_kind] ?? ""})</label>
            <input className="input answer" data-testid="exam-answer" value={answers[item.position] ?? ""}
              onChange={(e) => setAnswers((a) => ({ ...a, [item.position]: e.target.value }))} />
            <div className="row gap">
              <Button onClick={() => void save()} testId="exam-save">Сохранить</Button>
              {position < exam.sheet.length ? <Button kind="secondary" onClick={() => go(position + 1)}>Следующее →</Button> : null}
            </div>
            <small className="muted">{item.answered ? "✓ ответ дан" : "ответа нет"}</small>
          </div>
        </>
      )}
      <Sheet open={confirm} onClose={() => setConfirm(false)} title="Завершить экзамен?">
        <p>Отвечено {exam.sheet.filter((s) => s.answered).length} из {exam.sheet.length}. Несохранённые ответы не засчитаются.</p>
        <Button kind="danger" onClick={() => void finish()} busy={finishing} testId="exam-finish">Завершить и проверить</Button>
      </Sheet>
    </div>
  );
}

function ExamResultView({ exam }: { exam: ExamView }) {
  const navigate = useNavigate();
  const result = exam.result;
  if (!result) return <Spinner />;
  const points = [...result.history.map((h) => ({ label: dateShort(h.finished_at), value: h.primary })), { label: "сейчас", value: result.primary ?? 0 }];
  const max = exam.kind === "full" ? 29 : exam.kind === "half" ? 15 : 5;
  return (
    <div className="screen" data-testid="exam-result">
      <Card className="forecast">
        <div className="big">{result.primary} первичных{result.test ? ` · ${result.test} тестовых` : ""}</div>
        <div className="muted small">{KIND_TITLE[exam.kind]}{exam.training ? " · тренировка" : ""}</div>
      </Card>
      {result.lost_most.length ? <p className="note">Больше всего потеряно на: {result.lost_most.map((t) => `${t}‑м`).join(", ")}.</p> : null}
      {points.length > 1 ? (
        <Section title="Сравнение с прошлыми">
          <LineChart points={points} max={max} />
        </Section>
      ) : null}
      <Section title="По заданиям">
        {result.per_position.map((p) => (
          <Card key={p.position} onClick={() => navigate(`/task/${p.instance_id}`)}>
            <div className="row between">
              <span>{exam.kind === "block" ? `${p.position}.` : ""} Задание {p.task_no}</span>
              <span>
                <Chip tone={p.correct ? "good" : p.points ? "warn" : "bad"}>{p.points} б.</Chip>{" "}
                <span className="muted small">{clock(p.time_spent_s)}</span>
              </span>
            </div>
          </Card>
        ))}
      </Section>
      <p className="muted small">Нажмите на задание — разбор бесплатный.</p>
    </div>
  );
}
