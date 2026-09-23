// «Экран задачи» (design doc 11.4).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { FileChips, Figures } from "../components/Assets";
import { CodePanel, useDraftSaver } from "../components/CodePanel";
import { Button, Card, Chip, ErrorView, Sheet, Spinner, useToast } from "../components/ui";
import { api, ApiError, newKey } from "../lib/api";
import { ANSWER_HINTS, REASONS, answerWarning, clock, minutes } from "../lib/format";
import { useBackButton, useMainButton, useMe, useNow } from "../lib/hooks";
import { Markdown } from "../lib/markdown";
import { haptic, setClosingConfirmation } from "../lib/tg";
import type { AnswerResult, InstanceView, Solution } from "../lib/types";

const OPEN = new Set(["planned", "issued", "attempted"]);

function AnswerInput({ kind, taskNo, value, onChange, onSubmit }: {
  kind: string;
  taskNo: number;
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
}) {
  if (kind === "two_ints") {
    const [a = "", b = ""] = value.split(" ");
    const set = (x: string, y: string) => onChange(`${x.trim()} ${y.trim()}`.trimEnd());
    return (
      <div>
        <div className="row gap">
          <input className="input answer" inputMode="numeric" aria-label="Первое число" placeholder={taskNo === 27 ? "Файл A" : "Первое"}
            value={a} onChange={(e) => set(e.target.value, b)} />
          <input className="input answer" inputMode="numeric" aria-label="Второе число" placeholder={taskNo === 27 ? "Файл B" : "Второе"}
            value={b} onChange={(e) => set(a, e.target.value)} onKeyDown={(e) => e.key === "Enter" && onSubmit()} />
        </div>
        {taskNo === 27 ? <small className="muted block">Проверь: первое число — для файла A. На ЕГЭ — в одну строку через пробел.</small> : null}
      </div>
    );
  }
  return (
    <input
      className="input answer"
      data-testid="answer-input"
      inputMode={kind === "int" ? "numeric" : "text"}
      autoCapitalize={kind === "letters" ? "characters" : "off"}
      autoComplete="off"
      placeholder={ANSWER_HINTS[kind] ?? "Ответ"}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={(e) => e.key === "Enter" && onSubmit()}
    />
  );
}

function SolutionView({ solution }: { solution: Solution }) {
  return (
    <Card className="solution">
      <h3>Разбор</h3>
      <ol>
        {solution.steps.map((step, i) => (
          <li key={i}><Markdown source={step} /></li>
        ))}
      </ol>
      {solution.reference_code ? (
        <pre className="code-block"><code>{solution.reference_code}</code></pre>
      ) : null}
      <p>Ответ: <strong data-testid="solution-answer">{solution.answer}</strong></p>
    </Card>
  );
}

export function TaskScreen() {
  const { id } = useParams();
  const instanceId = Number(id);
  const navigate = useNavigate();
  const client = useQueryClient();
  const toast = useToast((s) => s.show);
  const me = useMe();
  const query = useQuery({
    queryKey: ["instance", instanceId],
    queryFn: () => api.get<InstanceView>(`/instances/${instanceId}`),
  });
  const task = query.data;
  const [answer, setAnswer] = useState("");
  const [code, setCode] = useState("");
  const [result, setResult] = useState<AnswerResult | null>(null);
  const [methodQuestion, setMethodQuestion] = useState<AnswerResult | null>(null);
  const [askReason, setAskReason] = useState(false);
  const [otherText, setOtherText] = useState("");
  const [reaction, setReaction] = useState<string | null>(null);
  const [card, setCard] = useState<string | null>(null);
  const [hints, setHints] = useState<string[]>([]);
  const [solution, setSolution] = useState<Solution | null>(null);
  const [checklistDone, setChecklistDone] = useState<Set<number>>(new Set());
  const [report, setReport] = useState(false);
  const [reportText, setReportText] = useState("");
  const started = useRef(Date.now());
  const answerKey = useRef(newKey());
  const saveDraft = useDraftSaver(instanceId);
  const now = useNow();

  useEffect(() => {
    if (!task) return;
    setAnswer(task.draft.answer ?? "");
    setCode(task.draft.code ?? "");
    setHints(task.hints ?? []);
    setSolution(task.solution ?? null);
    started.current = Date.now();
    setResult(null);
    answerKey.current = newKey();
  }, [task?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const isOpen = task ? OPEN.has(task.state) && !(result && (result.status === "correct" || result.attempts_left === 0)) : false;

  useEffect(() => {
    setClosingConfirmation(isOpen);
    return () => setClosingConfirmation(false);
  }, [isOpen]);

  const back = useCallback(() => navigate(-1), [navigate]);
  useBackButton(back);

  const submit = useMutation({
    mutationFn: (methodChoice?: string) =>
      api.post<AnswerResult>(`/instances/${instanceId}/answer`, {
        answer,
        time_spent_s: Math.round((Date.now() - started.current) / 1000),
        code: code.trim() ? code : null,
        method_choice: methodChoice ?? null,
      }, answerKey.current),
    onSuccess: (r) => {
      if (r.status === "method_check") {
        setMethodQuestion(r);
        return;
      }
      setMethodQuestion(null);
      if (r.status === "format_error") {
        toast(r.message ?? "Проверьте формат ответа", "bad");
        answerKey.current = newKey();
        return;
      }
      answerKey.current = newKey();
      setResult(r);
      haptic(r.status === "correct" ? "success" : "error");
      if (r.ask_reason) setAskReason(true);
      void client.invalidateQueries({ queryKey: ["today"] });
      void client.invalidateQueries({ queryKey: ["me"] });
      void query.refetch();
    },
    onError: (error) => toast(error instanceof ApiError ? error.message : "Нет связи", "bad"),
  });

  const warning = task ? answerWarning(task.answer_kind, answer) : null;
  const checklistNeeded = task?.checklist?.length ? checklistDone.size < task.checklist.length : false;
  const canSubmit = Boolean(task && isOpen && !warning && !checklistNeeded && !submit.isPending);
  const doSubmit = useCallback(() => {
    if (canSubmit) submit.mutate(undefined);
  }, [canSubmit, submit]);
  const pageButton = useMainButton(task && isOpen ? { text: "Ответить", enabled: canSubmit, loading: submit.isPending, onClick: doSubmit } : null);

  const buyHint = async () => {
    try {
      const r = await api.post<{ hint: string; price: number }>(`/instances/${instanceId}/hint`);
      setHints((h) => [...h, r.hint]);
      void client.invalidateQueries({ queryKey: ["me"] });
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Не получилось", "bad");
    }
  };

  const reveal = async () => {
    try {
      const r = await api.post<{ solution: Solution; price: number; free: boolean }>(`/instances/${instanceId}/reveal`);
      setSolution(r.solution);
      toast(r.free ? "Разбор дня — бесплатно" : `Разбор: −${r.price} 🪙`);
      void client.invalidateQueries({ queryKey: ["me"] });
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Не получилось", "bad");
    }
  };

  const sendReason = async (reason: string) => {
    try {
      const r = await api.post<{ bonus: number; reaction: { note: string; card_id?: string } }>(
        `/instances/${instanceId}/feedback`, { reason, text: reason === "other" ? otherText : null },
      );
      setReaction(r.reaction.note + (r.bonus ? ` +${r.bonus} 🪙 за ответ.` : ""));
      if (r.reaction.card_id) setCard(r.reaction.card_id);
    } catch {
      // the question is optional; a failure must not block the student
    }
    setAskReason(false);
  };

  const similar = async () => {
    try {
      const r = await api.post<InstanceView>("/instances/similar", { instance_id: instanceId });
      navigate(`/task/${r.id}`, { replace: true });
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Не получилось", "bad");
    }
  };

  const startPlacement = async () => {
    try {
      const first = await api.post<InstanceView>("/placement/start");
      navigate(`/task/${first.id}`, { replace: true });
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Не получилось", "bad");
    }
  };

  const sendReport = async () => {
    try {
      await api.post("/reports/issue", { instance_id: instanceId, text: reportText });
      setReport(false);
      toast("Спасибо! Проверим в течение суток.", "good");
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Не получилось", "bad");
    }
  };

  const cardQuery = useQuery({
    queryKey: ["card", card],
    queryFn: () => api.get<{ body_md: string }>(`/theory/card/${encodeURIComponent(card ?? "")}`),
    enabled: Boolean(card),
  });

  const placement = result?.context_result?.placement;
  const trial = result?.context_result?.kind ? result.context_result : null;
  const initialTab = useMemo(() => (task?.requires_code ? "python" as const : null), [task?.requires_code]);

  if (query.isLoading) return <Spinner />;
  if (query.error || !task) return <ErrorView error={query.error} onRetry={() => void query.refetch()} />;

  const title = task.task_no ? `Задание ${task.task_no}` : "Python‑минимум";
  const closedWithError = !isOpen && task.state !== "solved" && result?.status !== "correct";
  return (
    <div className="screen task" data-testid="task-screen">
      <header className="task-head">
        <h1>{title} · ур. {task.difficulty}</h1>
        <div className="row gap wrap">
          <Chip>{minutes(task.target_seconds)}</Chip>
          {task.reward ? <Chip tone="accent">{task.reward} 🪙</Chip> : null}
          {task.context === "placement" ? <Chip>Стартовый тест</Chip> : null}
          {task.context === "extern" ? <Chip>Экстерн</Chip> : null}
          {task.context === "boss" ? <Chip>Босс этажа</Chip> : null}
          {task.slot === "challenge" ? <Chip tone="warn">Вызов</Chip> : null}
          {me.data?.settings.show_timer && isOpen ? <Chip>⏱ {clock((now - started.current) / 1000)}</Chip> : null}
        </div>
      </header>

      <Markdown source={task.statement_md} className="md statement" />
      <Figures assets={task.assets} />
      <FileChips instanceId={task.id} assets={task.assets} />
      {task.code_rule ? <p className="note">ℹ️ {task.code_rule}</p> : null}

      <CodePanel
        instance={task}
        code={code}
        onCode={setCode}
        serverRun={Boolean(me.data?.settings.run_code_on_server)}
        initialTab={initialTab}
      />

      {hints.length ? (
        <Card className="hints">
          {hints.map((h, i) => (
            <div key={i} className="hint"><strong>Подсказка {i + 1}.</strong> <Markdown source={h} /></div>
          ))}
        </Card>
      ) : null}

      {isOpen && task.checklist?.length ? (
        <Card className="checklist">
          <strong>Перед ответом проверь условие:</strong>
          {task.checklist.map((q, i) => (
            <label key={i} className="check">
              <input type="checkbox" checked={checklistDone.has(i)} onChange={() => setChecklistDone((s) => {
                const next = new Set(s);
                if (next.has(i)) next.delete(i); else next.add(i);
                return next;
              })} />
              {q}
            </label>
          ))}
        </Card>
      ) : null}

      {isOpen ? (
        <div className="answer-box">
          <label className="muted small">{task.flags.includes("format_hint") ? "⚠️ " : ""}Формат: {ANSWER_HINTS[task.answer_kind] ?? "ответ"}</label>
          <AnswerInput kind={task.answer_kind} taskNo={task.task_no} value={answer} onSubmit={doSubmit}
            onChange={(v) => { setAnswer(v); saveDraft("answer", v); }} />
          {task.flags.includes("check_step") && answer ? <small className="muted block">Проверь ответ ещё раз перед отправкой.</small> : null}
          {pageButton ? <Button onClick={doSubmit} disabled={!canSubmit} busy={submit.isPending} testId="submit-answer">Ответить</Button> : null}
          <div className="row gap wrap">
            {task.hint_price != null && (task.hints_left ?? 0) > hints.length - (task.hints?.length ?? 0) ? (
              <Button kind="ghost" small onClick={() => void buyHint()}>Подсказка · {task.hint_price} 🪙</Button>
            ) : null}
            <Button kind="ghost" small onClick={() => setCard(task.method_card_id)}>Не понимаю условие</Button>
          </div>
        </div>
      ) : null}

      {result ? (
        <Card className={`result result-${result.status}`} testId="answer-result">
          {result.status === "correct" ? <div className="confetti" aria-hidden /> : null}
          <h2>{result.verdict_text}</h2>
          {result.coins ? <p className="big">+{result.coins} 🪙</p> : null}
          {result.capped ? <p className="muted">Кэп дня достигнут: дальше — свободная практика.</p> : null}
          {result.method_note ? <p className="muted">{result.method_note}</p> : null}
          {result.confidence ? (
            <p>Уверенность по {result.confidence.task_no}‑му: {result.confidence.before} → <strong>{result.confidence.after}</strong></p>
          ) : null}
          {result.status === "wrong" && (result.attempts_left ?? 0) > 0 ? <p>Осталось попыток: {result.attempts_left}</p> : null}
          {result.threshold_met ? <p>🔥 Порог дня взят — серия продолжается.</p> : null}
          {result.milestones?.length ? <p>🏅 Серия {result.milestones.join(", ")} дней!</p> : null}
          {result.rank_up ? <p>Новый ранг: {result.rank}</p> : null}
          {task.context === "onboarding" && result.status === "correct" ? (
            <div className="stack">
              <p>Стартовый тест уровня (≈ 10 минут) или сразу к дейликам?</p>
              <Button onClick={() => void startPlacement()} testId="start-placement">Проверь меня</Button>
              <Button kind="secondary" onClick={() => navigate("/", { replace: true })} testId="to-dailies">К дейликам</Button>
            </div>
          ) : null}
        </Card>
      ) : null}

      {reaction ? <p className="note">{reaction}</p> : null}

      {placement ? (
        <Card>
          {placement.finished ? (
            <>
              <h3>Стартовый тест пройден: {placement.correct} из {placement.total}</h3>
              <p>Открыты этажи: {placement.floors?.join(", ")}.{placement.challenge ? " Вызовы доступны с первого дня." : ""}</p>
              <Button onClick={() => navigate("/", { replace: true })}>К дейликам</Button>
            </>
          ) : placement.next_instance_id ? (
            <Button onClick={() => navigate(`/task/${placement.next_instance_id}`, { replace: true })}>
              Дальше ({placement.answered} из {placement.total})
            </Button>
          ) : null}
        </Card>
      ) : null}

      {trial ? (
        <Card>
          <p>{trial.kind === "extern" ? "Экстерн" : "Босс"}: верно {trial.correct} из {trial.total}.</p>
          {trial.finished ? (
            <p><strong>{trial.passed ? (trial.kind === "extern" ? "Этаж открыт!" : "Босс побеждён!") : "Не в этот раз. Можно завтра."}</strong></p>
          ) : null}
          <Button kind="secondary" onClick={() => navigate(`/trial/${trial.trial_id}`, { replace: true })}>К испытанию</Button>
        </Card>
      ) : null}

      {!isOpen && !solution && closedWithError && task.reveal_price != null ? (
        <Button kind="secondary" onClick={() => void reveal()} testId="reveal">
          {task.free_reveal_available || task.context === "exam" ? "Разбор дня — бесплатно" : `Разбор · ${task.reveal_price} 🪙`}
        </Button>
      ) : null}
      {solution ? <SolutionView solution={solution} /> : null}

      {!isOpen && task.context !== "placement" && task.context !== "extern" && task.context !== "boss" && task.task_no ? (
        <Button kind="secondary" onClick={() => void similar()}>Похожая задача (бесплатно)</Button>
      ) : null}
      <button className="link-btn" onClick={() => setReport(true)}>Сообщить об ошибке в задаче</button>

      <Sheet open={Boolean(methodQuestion)} onClose={() => setMethodQuestion(null)} title={methodQuestion?.question ?? "Каким способом решали?"}>
        <p className="muted">Быстрый ответ — отлично. Один вопрос для честности рейтинга.</p>
        {methodQuestion?.options?.map((option) => (
          <Button key={option} kind="secondary" onClick={() => submit.mutate(option)}>{option}</Button>
        ))}
      </Sheet>

      <Sheet open={askReason} onClose={() => setAskReason(false)} title="Что было сложным?">
        <div className="reasons">
          {REASONS.map((r) => (
            <Button key={r.code} kind="secondary" small onClick={() => (r.code === "other" && !otherText ? setOtherText(" ") : void sendReason(r.code))}>
              {r.text}
            </Button>
          ))}
        </div>
        {otherText ? (
          <div>
            <textarea className="input" maxLength={1000} value={otherText.trimStart()} onChange={(e) => setOtherText(e.target.value)} placeholder="Коротко опишите" />
            <Button onClick={() => void sendReason("other")}>Отправить</Button>
          </div>
        ) : null}
        <Button kind="ghost" onClick={() => setAskReason(false)}>Пропустить</Button>
      </Sheet>

      <Sheet open={Boolean(card)} onClose={() => setCard(null)} title="Карточка метода">
        {cardQuery.data ? <Markdown source={cardQuery.data.body_md} /> : <Spinner />}
      </Sheet>

      <Sheet open={report} onClose={() => setReport(false)} title="Ошибка в задаче">
        <p className="muted">Если подтвердится — вернём монеты и добавим 20 🪙.</p>
        <textarea className="input" value={reportText} maxLength={2000} onChange={(e) => setReportText(e.target.value)} placeholder="Что не так?" />
        <Button onClick={() => void sendReport()} disabled={reportText.trim().length < 5}>Отправить</Button>
      </Sheet>
    </div>
  );
}
