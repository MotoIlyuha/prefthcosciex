// «Сегодня» (design doc 11.3).
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { Ring } from "../components/charts";
import { Button, Card, Chip, Empty, ErrorView, Section, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { useMe } from "../lib/hooks";
import type { Today, TodayItem } from "../lib/types";

const SLOT_TITLE: Record<string, string> = {
  new: "Новое",
  strengthen: "Укрепление",
  consolidate: "Закрепление",
  repeat: "Повтор",
  challenge: "Вызов",
  python: "Python‑минимум",
};

function ItemCard({ item, onOpen }: { item: TodayItem; onOpen: () => void }) {
  const done = item.state === "solved";
  const closed = ["failed", "revealed", "expired"].includes(item.state);
  return (
    <Card onClick={onOpen} className={done ? "done" : closed ? "closed" : ""} testId="today-item">
      <div className="row between">
        <div>
          <div className="muted small">{SLOT_TITLE[item.slot] ?? item.slot}</div>
          <strong>{item.task_no ? `${item.task_no}. ` : ""}{item.title}</strong>
        </div>
        <div className="right">
          {done ? <Chip tone="good">✓</Chip> : closed ? <Chip tone="bad">закрыто</Chip> : <Chip tone="accent">{item.reward ? `${item.reward} 🪙` : "🐍"}</Chip>}
          <div className="muted small">~{item.minutes} мин</div>
        </div>
      </div>
    </Card>
  );
}

export function TodayScreen() {
  const navigate = useNavigate();
  const me = useMe();
  const query = useQuery({ queryKey: ["today"], queryFn: () => api.get<Today>("/today") });
  if (query.isLoading) return <Spinner />;
  if (query.error || !query.data) return <ErrorView error={query.error} onRetry={() => void query.refetch()} />;
  const today = query.data;
  const mandatory = today.items.filter((i) => i.mandatory);
  const bonus = today.items.filter((i) => !i.mandatory);
  const { progress } = today;
  const nextOpen = new Date(today.next_open_at);
  const banner = me.data?.fipi.banner;
  return (
    <div className="screen" data-testid="today">
      <header className="today-head">
        <div className="stat">🔥 <strong>{today.streak.current}</strong><span className="muted small">серия</span></div>
        <Ring value={progress.earned} threshold={progress.threshold} cap={progress.cap} />
        <div className="stat">🪙 <strong data-testid="balance">{today.wallet.balance}</strong><span className="muted small">{today.wallet.rank}</span></div>
      </header>
      <p className="muted center small">
        {progress.threshold_met ? "Порог дня взят. " : `До порога ${Math.max(0, progress.threshold - progress.earned)} 🪙. `}
        {progress.easy_day ? "Лёгкий день: порог 10." : `Кэп дня ${progress.cap}.`}
      </p>
      {banner ? <p className="note small">{banner}</p> : null}
      {me.data?.band_suggestion ? (
        <Card onClick={() => navigate("/profile/settings")}>
          Похоже, тебе подходит диапазон {me.data.band_suggestion}. Нажми, чтобы выбрать.
        </Card>
      ) : null}

      {today.all_done && !bonus.some((b) => ["planned", "issued", "attempted"].includes(b.state)) ? (
        <Empty title="На сегодня всё">
          <p>
            Завтра: {mandatory.map((i) => `${i.task_no}‑е`).join(" и ") || "новые задачи"} — с{" "}
            {nextOpen.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}.
          </p>
        </Empty>
      ) : null}

      <Section title="Дейлики">
        {mandatory.map((item) => (
          <ItemCard key={item.instance_id} item={item} onOpen={() => navigate(`/task/${item.instance_id}`)} />
        ))}
      </Section>
      {bonus.length ? (
        <Section title="Бонус">
          {bonus.map((item) => (
            <ItemCard key={item.instance_id} item={item} onOpen={() => navigate(`/task/${item.instance_id}`)} />
          ))}
        </Section>
      ) : null}
      {today.reveal_candidate && today.free_reveal_available ? (
        <Card onClick={() => navigate(`/task/${today.reveal_candidate}`)}>📖 Разбор дня: бесплатно</Card>
      ) : null}
      <Section title={today.free_practice ? "Свободная практика" : "Практика"}>
        <p className="muted small">
          {today.free_practice
            ? "Кэп дня достигнут — дальше без монет, но уверенность растёт."
            : "Любая задача с открытых этажей — во вкладке «Путь» или «Уверенность»."}
        </p>
        <div className="row gap wrap">
          <Button kind="secondary" small onClick={() => navigate("/confidence")}>Выбрать тему</Button>
          <Button kind="secondary" small onClick={() => navigate("/exam")}>Экзамен</Button>
        </div>
      </Section>
    </div>
  );
}
