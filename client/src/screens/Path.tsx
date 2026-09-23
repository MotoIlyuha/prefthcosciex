// «Путь»: the floor map, a floor, and the extern / boss trials (design doc 11.5, 3.3).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Button, Card, Chip, ConfidenceBar, ErrorView, Section, Spinner, useToast } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { useBackButton, useMe } from "../lib/hooks";
import type { InstanceView, PathView, Trial } from "../lib/types";

const BANDS = [
  { code: "A", label: "40–64" },
  { code: "B", label: "65–84" },
  { code: "C", label: "85–100" },
];

export function PathScreen() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["path"], queryFn: () => api.get<PathView>("/path") });
  if (query.isLoading) return <Spinner />;
  if (query.error || !query.data) return <ErrorView error={query.error} onRetry={() => void query.refetch()} />;
  const path = query.data;
  const setBand = async (band: string) => {
    await api.patch("/me/settings", { band });
    await client.invalidateQueries();
  };
  return (
    <div className="screen" data-testid="path">
      <div className="segmented" role="radiogroup" aria-label="Цель">
        {BANDS.map((b) => (
          <button key={b.code} role="radio" aria-checked={path.band === b.code} className={path.band === b.code ? "active" : ""}
            onClick={() => void setBand(b.code)}>
            {b.label}
          </button>
        ))}
      </div>
      <div className="floors">
        {[...path.floors].reverse().map((f) => {
          const state = f.state === "locked" ? `закрыт: ${f.price} 🪙 или экстерн` : f.boss_passed ? "босс пройден" : `${f.mastered} из ${f.total} освоены`;
          return (
            <Card key={f.number} onClick={() => navigate(`/path/${f.number}`)} className={`floor floor-${f.state}${f.number === path.current ? " floor-current" : ""}`} testId={`floor-${f.number}`}>
              <div className="row between">
                <div>
                  <strong>{f.number}. {f.title}</strong>
                  <div className="muted small">{state}</div>
                </div>
                <div className="right">
                  {f.required ? <Chip tone="accent">нужен</Chip> : <Chip>бонус</Chip>}
                  {f.state === "locked" ? " 🔒" : f.boss_passed ? " 👑" : ""}
                </div>
              </div>
            </Card>
          );
        })}
      </div>
      <Button kind="secondary" onClick={() => navigate("/exam")}>Экзамен</Button>
    </div>
  );
}

export function FloorScreen() {
  const { floor } = useParams();
  const number = Number(floor);
  const navigate = useNavigate();
  const client = useQueryClient();
  const toast = useToast((s) => s.show);
  const me = useMe();
  const [busy, setBusy] = useState<string | null>(null);
  const back = useCallback(() => navigate("/path"), [navigate]);
  useBackButton(back);
  const query = useQuery({ queryKey: ["path"], queryFn: () => api.get<PathView>("/path") });
  if (query.isLoading) return <Spinner />;
  if (query.error || !query.data) return <ErrorView error={query.error} />;
  const info = query.data.floors.find((f) => f.number === number);
  if (!info) return <ErrorView error={new ApiError(404, "not_found", "Нет такого этажа")} />;
  const locked = info.state === "locked";

  const act = async (kind: "unlock" | "extern" | "boss") => {
    setBusy(kind);
    try {
      if (kind === "unlock") {
        await api.post(`/path/${number}/unlock`);
        toast(`Этаж ${number} открыт`, "good");
        await client.invalidateQueries();
      } else {
        const trial = await api.post<Trial>(`/path/${number}/${kind}`);
        client.setQueryData(["trial", trial.trial_id], trial);
        navigate(`/trial/${trial.trial_id}`);
      }
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Не получилось", "bad");
    } finally {
      setBusy(null);
    }
  };

  const practice = async (taskNo: number) => {
    try {
      const inst = await api.post<InstanceView>("/instances/similar", { task_no: taskNo });
      navigate(`/task/${inst.id}`);
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Не получилось", "bad");
    }
  };

  return (
    <div className="screen">
      <h1>Этаж {info.number}. {info.title}</h1>
      <p className="muted">Python: {info.python}</p>
      <Section title="Задания">
        {info.tasks.map((t) => (
          <Card key={t.task_no}>
            <div className="row between">
              <strong>{t.task_no}. {t.title}</strong>
              <span className="muted">{Math.round(t.confidence)}%</span>
            </div>
            <ConfidenceBar value={t.confidence} />
            <div className="row gap wrap">
              <Button small kind="secondary" disabled={locked} onClick={() => void practice(t.task_no)}>Практика</Button>
              <Button small kind="ghost" onClick={() => navigate(`/theory/${t.task_no}`)}>Карточка метода</Button>
            </div>
          </Card>
        ))}
      </Section>
      {locked ? (
        <Section title="Как открыть">
          <Button onClick={() => void act("unlock")} busy={busy === "unlock"} disabled={(me.data?.wallet.balance ?? 0) < info.price}>
            Открыть за {info.price} 🪙
          </Button>
          <Button kind="secondary" onClick={() => void act("extern")} busy={busy === "extern"} disabled={!query.data.extern_available}>
            Экстерн: 3 из 3 на ур. 4 — бесплатно
          </Button>
          {!query.data.extern_available ? <p className="muted small">Экстерн — раз в сутки. Завтра можно снова.</p> : null}
        </Section>
      ) : (
        <Section title="Босс этажа">
          <p className="muted small">Три задачи на экзаменационной сложности. {info.boss_passed ? "Уже пройден 👑" : ""}</p>
          <Button kind="secondary" onClick={() => void act("boss")} busy={busy === "boss"}>Сразиться с боссом</Button>
        </Section>
      )}
    </div>
  );
}

export function TrialScreen() {
  const { id } = useParams();
  const navigate = useNavigate();
  const trialId = Number(id);
  const back = useCallback(() => navigate("/path"), [navigate]);
  useBackButton(back);
  const query = useQuery({
    queryKey: ["trial", trialId],
    queryFn: () => api.get<Trial>(`/path/trials/${trialId}`),
    refetchOnMount: "always",
  });
  if (query.isLoading) return <Spinner />;
  const trial = query.data;
  if (query.error || !trial) return <ErrorView error={query.error} onRetry={() => void query.refetch()} />;
  const rows = trial.instances;
  return (
    <div className="screen">
      <h1>{trial.kind === "extern" ? "Экстерн" : "Босс"} · этаж {trial.floor}</h1>
      <p className="muted">Одна попытка на задачу, без подсказок. Нужно 3 из 3.</p>
      {rows.map((inst, i) => (
        <Card key={inst.id} onClick={() => navigate(`/task/${inst.id}`)}>
          <div className="row between">
            <strong>{i + 1}. Задание {inst.task_no}</strong>
            <Chip tone={inst.state === "solved" ? "good" : ["failed", "expired"].includes(inst.state) ? "bad" : "neutral"}>
              {inst.state === "solved" ? "верно" : ["failed", "expired"].includes(inst.state) ? "неверно" : "решить"}
            </Chip>
          </div>
        </Card>
      ))}
    </div>
  );
}
