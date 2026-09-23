// Onboarding: five screens, under three minutes, ending with a first win (11.2).
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button, Card, Toggle, useToast } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { useMe } from "../lib/hooks";
import type { InstanceView } from "../lib/types";

const BANDS = [
  { code: "A", title: "Сдать уверенно · 40–64", text: "15 заданий первой части, без 24–27. Реально за полгода по 15 минут в день." },
  { code: "B", title: "Хороший вуз · 65–84", text: "Вся первая часть и основные задания с кодом: 16–23, 25–26." },
  { code: "C", title: "Топ‑вуз · 85–100", text: "Все 27, включая 24–27 на время. Нужен уверенный Python." },
];

const PYTHON = [
  { code: "none", title: "Нет" },
  { code: "little", title: "Чуть‑чуть" },
  { code: "yes", title: "Да" },
];

export function OnboardingScreen() {
  const me = useMe();
  const client = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast((s) => s.show);
  const [step, setStep] = useState(Math.min(4, Math.max(0, me.data?.settings.onboarding_step ?? 0)));
  const [consent, setConsent] = useState(false);
  const [notify, setNotify] = useState(true);
  const [time, setTime] = useState("16:00");
  const [tz, setTz] = useState(() => Intl.DateTimeFormat().resolvedOptions().timeZone || "Europe/Moscow");
  const [busy, setBusy] = useState(false);

  const save = async (body: Record<string, unknown>, next: number) => {
    setBusy(true);
    try {
      await api.patch("/me/onboarding", { ...body, step: next });
      setStep(next);
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Не получилось", "bad");
    } finally {
      setBusy(false);
    }
  };

  const firstTask = async () => {
    setBusy(true);
    try {
      await api.patch("/me/onboarding", { step: 5, done: true });
      const task = await api.post<InstanceView>("/onboarding/first-task");
      await client.invalidateQueries({ queryKey: ["me"] });
      navigate(`/task/${task.id}`, { replace: true });
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Не получилось", "bad");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="screen onboarding" data-testid="onboarding">
      <div className="dots" aria-label={`Шаг ${step + 1} из 5`}>
        {[0, 1, 2, 3, 4].map((i) => <span key={i} className={i <= step ? "dot on" : "dot"} />)}
      </div>
      {step === 0 ? (
        <>
          <h1>Привет, {me.data?.first_name || "друг"}!</h1>
          <p className="lead">15 минут в день — и к июню ты знаешь, что решать.</p>
          <Card>
            <label className="check">
              <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} data-testid="consent" />
              <span>
                Согласен на обработку данных по{" "}
                <a href="/privacy" onClick={(e) => { e.preventDefault(); navigate("/privacy"); }}>политике конфиденциальности</a>
              </span>
            </label>
          </Card>
          <Button onClick={() => void save({ privacy_consent: true }, 1)} disabled={!consent} busy={busy} testId="next">Дальше</Button>
        </>
      ) : null}
      {step === 1 ? (
        <>
          <h1>Какая цель?</h1>
          {BANDS.map((b) => (
            <Card key={b.code} onClick={() => void save({ band: b.code }, 2)} testId={`band-${b.code}`}>
              <strong>{b.title}</strong>
              <p className="muted small">{b.text}</p>
            </Card>
          ))}
          <Button kind="ghost" onClick={() => void save({ band: "unknown" }, 2)}>Не знаю → подскажите после 5 задач</Button>
        </>
      ) : null}
      {step === 2 ? (
        <>
          <h1>Писал на Python?</h1>
          <p className="muted">Если нет — добавим короткий трек «Python‑минимум» прямо в дейлики.</p>
          {PYTHON.map((p) => (
            <Button key={p.code} kind="secondary" onClick={() => void save({ python_level: p.code }, 3)} testId={`python-${p.code}`}>
              {p.title}
            </Button>
          ))}
        </>
      ) : null}
      {step === 3 ? (
        <>
          <h1>Время и уведомления</h1>
          <Card>
            <label className="field">
              Часовой пояс
              <input className="input" value={tz} onChange={(e) => setTz(e.target.value)} />
              <small className="muted">Определён по устройству. Дейлики открываются в 05:00 по этому времени.</small>
            </label>
            <label className="field">
              Когда напоминать о дейликах
              <input className="input" type="time" value={time} onChange={(e) => setTime(e.target.value)} />
            </label>
            <Toggle label="Присылать уведомления в боте" checked={notify} onChange={setNotify}
              hint="Не больше двух в день, никогда с 23:00 до 08:00" />
          </Card>
          <Button onClick={() => void save({ tz, daily_time: time, notifications_consent: notify }, 4)} busy={busy} testId="next">
            Дальше
          </Button>
          <p className="muted small">Куратора (родителя или репетитора) можно добавить позже в профиле.</p>
        </>
      ) : null}
      {step === 4 ? (
        <>
          <h1>Первая задача</h1>
          <p className="lead">Одна простая задача — около минуты. Поехали?</p>
          <Button onClick={() => void firstTask()} busy={busy} testId="first-task">Решить первую задачу</Button>
        </>
      ) : null}
    </div>
  );
}
