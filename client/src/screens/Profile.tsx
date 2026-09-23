// «Профиль / Настройки» (design doc 11.8) and everything reachable from it.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button, Card, Chip, ErrorView, Section, Sheet, Spinner, Toggle, useToast } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { dateShort } from "../lib/format";
import { useBackButton, useMe } from "../lib/hooks";
import { share } from "../lib/tg";
import type { CuratorLinkView } from "../lib/types";

const NOTIFICATION_TITLES: Record<string, string> = {
  dailies_open: "Дейлики открыты",
  threshold_missed: "Порог дня не достигнут (20:00)",
  streak_risk: "Серия под угрозой (22:00)",
  floor_unlocked: "Новый этаж / экстерн",
  exam_checked: "Экзамен проверен",
  weekly_summary: "Итоги недели",
  curator_nudge: "Пинок от куратора",
  curator_focus: "Фокус‑тема от куратора",
  demo_approved: "Новости демоверсии ФИПИ",
  cur_digest: "Куратору: ежедневная сводка",
  cur_milestone: "Куратору: вехи серии",
  cur_floor: "Куратору: открыт этаж",
  cur_exam: "Куратору: экзамен сдан",
  cur_idle: "Куратору: 2 дня без активности",
  cur_weekly: "Куратору: воскресный отчёт",
  cur_revoked: "Куратору: доступ закрыт",
  cur_invite: "Приглашения стать куратором",
};

const ACCESS_TITLE: Record<string, string> = {
  fact: "Только факт",
  progress: "Прогресс",
  full: "Полный",
};

function useBack(to: string) {
  const navigate = useNavigate();
  const back = useCallback(() => navigate(to), [navigate, to]);
  useBackButton(back);
}

export function ProfileScreen() {
  const navigate = useNavigate();
  const me = useMe();
  if (me.isLoading) return <Spinner />;
  if (me.error || !me.data) return <ErrorView error={me.error} />;
  const m = me.data;
  const links: [string, string, string][] = [
    ["Настройки", "/profile/settings", "⚙️"],
    ["Кураторы", "/profile/curators", "👥"],
    ["Магазин", "/profile/shop", "🛍"],
    ["Кошелёк", "/profile/wallet", "🪙"],
    ["Лига группы", "/league", "🏆"],
    ["Мои обращения", "/profile/reports", "✉️"],
    ["Данные и приватность", "/profile/privacy", "🔒"],
  ];
  if (m.is_admin) links.push(["Админка", "/admin", "🛠"]);
  return (
    <div className="screen" data-testid="profile">
      <Card>
        <h2>{m.first_name}</h2>
        <p className="muted">{m.wallet.rank} · {m.wallet.xp} XP · 🔥 {m.streak.current} · 🪙 {m.wallet.balance}</p>
        {m.delete_requested_at ? <p className="note">Аккаунт будет удалён через 7 дней после запроса. Вход отменяет удаление.</p> : null}
      </Card>
      {links.map(([title, to, icon]) => (
        <Card key={to} onClick={() => navigate(to)}>
          {icon} {title}
          {to === "/profile/curators" && m.curator_requests ? <Chip tone="warn"> {m.curator_requests} </Chip> : null}
        </Card>
      ))}
    </div>
  );
}

export function SettingsScreen() {
  useBack("/profile");
  const me = useMe();
  const client = useQueryClient();
  const toast = useToast((s) => s.show);
  const [vacation, setVacation] = useState({ from: "", days: 3 });
  if (!me.data) return <Spinner />;
  const s = me.data.settings;
  const patch = async (body: Record<string, unknown>) => {
    try {
      const updated = await api.patch("/me/settings", body);
      client.setQueryData(["me"], updated);
      void client.invalidateQueries({ queryKey: ["today"] });
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Не сохранилось", "bad");
    }
  };
  const bookVacation = async () => {
    const start = new Date(vacation.from);
    const days = Array.from({ length: vacation.days }, (_, i) => {
      const d = new Date(start);
      d.setDate(d.getDate() + i);
      return d.toISOString().slice(0, 10);
    });
    try {
      await api.post("/me/vacation", { days }, false);
      toast("Отпуск записан: серия не сгорит", "good");
      void client.invalidateQueries({ queryKey: ["me"] });
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Не получилось", "bad");
    }
  };
  const easyDay = async () => {
    try {
      await api.post("/me/easy-day", {}, false);
      toast("Сегодня лёгкий день: порог 10 🪙", "good");
      void client.invalidateQueries();
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Не получилось", "bad");
    }
  };
  return (
    <div className="screen" data-testid="settings">
      <Section title="Цель">
        <div className="segmented">
          {(["A", "B", "C"] as const).map((b) => (
            <button key={b} className={s.band === b ? "active" : ""} onClick={() => void patch({ band: b })}>
              {b === "A" ? "40–64" : b === "B" ? "65–84" : "85–100"}
            </button>
          ))}
        </div>
      </Section>
      <Section title="Python">
        <div className="segmented">
          {(["none", "little", "yes"] as const).map((p) => (
            <button key={p} className={s.python_level === p ? "active" : ""} onClick={() => void patch({ python_level: p })}>
              {p === "none" ? "Нет" : p === "little" ? "Чуть‑чуть" : "Да"}
            </button>
          ))}
        </div>
        <Toggle label="Выполнять код на сервере" checked={s.run_code_on_server} onChange={(v) => void patch({ run_code_on_server: v })}
          hint="Для слабых устройств: Python не загружается в телефон" />
        <Toggle label="Показывать таймер в задачах" checked={s.show_timer} onChange={(v) => void patch({ show_timer: v })} />
        <Toggle label="Вызовы (сложные задачи за 40 🪙)" checked={s.challenge_enabled} onChange={(v) => void patch({ challenge_enabled: v })} />
      </Section>
      <Section title="Время">
        <label className="field">Дейлики — напоминание
          <input className="input" type="time" defaultValue={s.daily_time} onBlur={(e) => void patch({ daily_time: e.target.value })} />
        </label>
        <label className="field">Часовой пояс
          <input className="input" defaultValue={me.data.tz} onBlur={(e) => e.target.value !== me.data?.tz && void patch({ tz: e.target.value })} />
        </label>
      </Section>
      <Section title="Уведомления">
        {Object.keys(NOTIFICATION_TITLES).filter((k) => k in s.notifications).map((kind) => (
          <Toggle key={kind} label={NOTIFICATION_TITLES[kind] ?? kind} checked={Boolean(s.notifications[kind])}
            onChange={(v) => void patch({ notifications: { [kind]: v } })} />
        ))}
        <p className="muted small">Не больше двух в день; тихие часы 23:00–08:00 по вашему времени.</p>
      </Section>
      <Section title="Отпуск и лёгкий день">
        <p className="muted small">До 7 дней отпуска в месяц, минимум за день. Лёгкий день (порог 10) — раз в неделю.</p>
        <div className="row gap wrap">
          <input className="input" type="date" value={vacation.from} onChange={(e) => setVacation({ ...vacation, from: e.target.value })} />
          <select className="input" value={vacation.days} onChange={(e) => setVacation({ ...vacation, days: Number(e.target.value) })}>
            {[1, 2, 3, 4, 5, 6, 7].map((n) => <option key={n} value={n}>{n} дн.</option>)}
          </select>
          <Button small onClick={() => void bookVacation()} disabled={!vacation.from}>Взять отпуск</Button>
        </div>
        {s.vacation_days.length ? <p className="muted small">Отпуск: {s.vacation_days.map(dateShort).join(", ")}</p> : null}
        <Button kind="secondary" onClick={() => void easyDay()}>Сегодня — лёгкий день</Button>
      </Section>
    </div>
  );
}

export function CuratorsScreen() {
  useBack("/profile");
  const client = useQueryClient();
  const toast = useToast((s) => s.show);
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [username, setUsername] = useState("");
  const query = useQuery({ queryKey: ["curators"], queryFn: () => api.get<CuratorLinkView[]>("/curators") });
  const invite = async (role: "parent" | "tutor") => {
    try {
      const r = await api.post<{ link: string; delivered_to_username: boolean }>("/curators/invite", { role, username: username || null });
      share(r.link, "Стань моим куратором в «Байте»");
      toast(r.delivered_to_username ? "Приглашение отправлено в бота" : "Ссылка готова (48 часов)", "good");
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Не получилось", "bad");
    }
  };
  const setAccess = async (id: number, access: string) => {
    await api.patch(`/curators/${id}/access`, { access });
    await client.invalidateQueries({ queryKey: ["curators"] });
    await client.invalidateQueries({ queryKey: ["me"] });
  };
  const revoke = async (id: number) => {
    await api.del(`/curators/${id}`);
    await client.invalidateQueries({ queryKey: ["curators"] });
  };
  const showPreview = async (id: number) => setPreview(await api.get<Record<string, unknown>>(`/curators/${id}/preview`));
  if (query.isLoading) return <Spinner />;
  if (query.error || !query.data) return <ErrorView error={query.error} />;
  return (
    <div className="screen" data-testid="curators">
      <p className="muted">Куратор — родитель или репетитор. Вы решаете, что он видит, и можете закрыть доступ в один тап.</p>
      {query.data.map((c) => (
        <Card key={c.id}>
          <div className="row between">
            <strong>{c.name}{c.username ? ` (@${c.username})` : ""}</strong>
            <Chip tone={c.status === "active" ? "good" : "warn"}>{c.role === "tutor" ? "репетитор" : "родитель"}</Chip>
          </div>
          {c.status === "pending" ? <p className="note small">Куратор принял приглашение. Выберите, что ему будет видно:</p> : null}
          <div className="segmented">
            {(["fact", "progress", "full"] as const).map((a) => (
              <button key={a} className={c.access === a && c.status === "active" ? "active" : ""} onClick={() => void setAccess(c.id, a)}>
                {ACCESS_TITLE[a]}
              </button>
            ))}
          </div>
          <div className="row gap">
            <Button small kind="ghost" onClick={() => void showPreview(c.id)}>Так вас видит куратор</Button>
            <Button small kind="danger" onClick={() => void revoke(c.id)}>Отозвать доступ</Button>
          </div>
        </Card>
      ))}
      <Section title="Добавить куратора">
        <input className="input" placeholder="@username (необязательно)" value={username} onChange={(e) => setUsername(e.target.value)} />
        <div className="row gap">
          <Button onClick={() => void invite("parent")} testId="invite-parent">Родитель</Button>
          <Button kind="secondary" onClick={() => void invite("tutor")}>Репетитор</Button>
        </div>
        <p className="muted small">До двух кураторов. Ссылка живёт 48 часов.</p>
      </Section>
      <Sheet open={Boolean(preview)} onClose={() => setPreview(null)} title="Так вас видит куратор">
        <ul className="plain">
          {preview ? Object.keys(preview).filter((k) => !["student_id", "name"].includes(k)).map((k) => <li key={k}>✓ {PREVIEW_TITLES[k] ?? k}</li>) : null}
        </ul>
      </Sheet>
    </div>
  );
}

const PREVIEW_TITLES: Record<string, string> = {
  streak: "Серия",
  threshold_today: "Достигнут ли порог сегодня",
  rank: "Ранг",
  coins_by_day: "Монеты по дням",
  confidence: "Уверенность по 27 заданиям",
  forecast: "Прогноз балла",
  exams: "Результаты экзаменов",
  subtypes: "Разбивка по подтипам",
  reasons: "Причины затруднений (без текста)",
  attempts: "История попыток с ответами",
  time_spent: "Время на задачи",
};

interface ShopView {
  freeze: { price: number; have: number; max: number };
  restore: { price: number | null; lost_value: number };
  exam_ticket: { price: number; have: number; max: number };
  cosmetics: { id: string; kind: string; title: string; price: number; owned: boolean }[];
}

export function ShopScreen() {
  useBack("/profile");
  const client = useQueryClient();
  const toast = useToast((s) => s.show);
  const query = useQuery({ queryKey: ["shop"], queryFn: () => api.get<ShopView>("/shop") });
  const buy = async (item: string) => {
    try {
      const r = await api.post<{ balance: number }>("/shop/buy", { item });
      toast(`Готово. Баланс ${r.balance} 🪙`, "good");
      await client.invalidateQueries();
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Не получилось", "bad");
    }
  };
  if (query.isLoading) return <Spinner />;
  if (query.error || !query.data) return <ErrorView error={query.error} />;
  const shop = query.data;
  return (
    <div className="screen" data-testid="shop">
      <Section title="Серия">
        <Card>
          <div className="row between">
            <span>❄️ Заморозка ({shop.freeze.have}/{shop.freeze.max})</span>
            <Button small onClick={() => void buy("freeze")} disabled={shop.freeze.have >= shop.freeze.max}>{shop.freeze.price} 🪙</Button>
          </div>
        </Card>
        {shop.restore.price != null ? (
          <Card>
            <div className="row between">
              <span>🔥 Восстановить серию {shop.restore.lost_value}</span>
              <Button small onClick={() => void buy("restore")}>{shop.restore.price} 🪙</Button>
            </div>
          </Card>
        ) : null}
      </Section>
      <Section title="Экзамены">
        <Card>
          <div className="row between">
            <span>🎫 Билет на полный вариант ({shop.exam_ticket.have}/{shop.exam_ticket.max})</span>
            <Button small onClick={() => void buy("exam_ticket")} disabled={shop.exam_ticket.have >= shop.exam_ticket.max}>{shop.exam_ticket.price} 🪙</Button>
          </div>
        </Card>
      </Section>
      <Section title="Косметика">
        {shop.cosmetics.map((c) => (
          <Card key={c.id}>
            <div className="row between">
              <span>{c.title}</span>
              {c.owned ? <Chip tone="good">есть</Chip> : <Button small onClick={() => void buy(`cosmetic:${c.id}`)}>{c.price} 🪙</Button>}
            </div>
          </Card>
        ))}
      </Section>
    </div>
  );
}

const REASON_TITLE: Record<string, string> = {
  task_reward: "Задача",
  feedback_bonus: "Ответ «что было сложным»",
  hint: "Подсказка",
  reveal: "Разбор",
  floor_unlock: "Этаж",
  freeze: "Заморозка",
  restore: "Восстановление серии",
  exam_ticket: "Билет",
  exam_full: "Экзамен",
  exam_half: "Полэкзамена",
  exam_block: "Блок",
  cosmetic: "Косметика",
  issue_compensation: "Компенсация за ошибку",
  admin_grant: "Начисление поддержки",
};

export function WalletScreen() {
  useBack("/profile");
  const query = useQuery({
    queryKey: ["wallet-tx"],
    queryFn: () => api.get<{ items: { id: number; delta: number; reason: string; balance_after: number; created_at: string }[] }>("/wallet/tx"),
  });
  if (query.isLoading) return <Spinner />;
  if (query.error || !query.data) return <ErrorView error={query.error} />;
  return (
    <div className="screen">
      <h1>Кошелёк</h1>
      {query.data.items.map((t) => (
        <div key={t.id} className="tx">
          <span>{REASON_TITLE[t.reason] ?? t.reason} · {dateShort(t.created_at)}</span>
          <span className={t.delta > 0 ? "good" : "bad"}>{t.delta > 0 ? "+" : ""}{t.delta}</span>
        </div>
      ))}
    </div>
  );
}

export function ReportsScreen() {
  useBack("/profile");
  const query = useQuery({
    queryKey: ["reports"],
    queryFn: () => api.get<{ id: number; task_no: number; status: string; resolution: string; created_at: string }[]>("/reports"),
  });
  if (query.isLoading) return <Spinner />;
  if (query.error || !query.data) return <ErrorView error={query.error} />;
  return (
    <div className="screen">
      <h1>Мои обращения</h1>
      {!query.data.length ? <p className="muted">Кнопка «Сообщить об ошибке» — внизу каждой задачи.</p> : null}
      {query.data.map((r) => (
        <Card key={r.id}>
          <div className="row between">
            <span>Задание {r.task_no} · {dateShort(r.created_at)}</span>
            <Chip tone={r.status === "confirmed" ? "good" : r.status === "rejected" ? "bad" : "neutral"}>
              {r.status === "open" ? "на проверке" : r.status === "confirmed" ? "подтверждено" : "не подтвердилось"}
            </Chip>
          </div>
          {r.resolution ? <p className="small">{r.resolution}</p> : null}
        </Card>
      ))}
    </div>
  );
}

export function PrivacyScreen() {
  useBack("/profile");
  const navigate = useNavigate();
  const toast = useToast((s) => s.show);
  const logout = useAuth((s) => s.logout);
  const [confirm, setConfirm] = useState(false);
  const exportData = async () => {
    const data = await api.get<unknown>("/me/export");
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "bayt-export.json";
    a.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 5000);
  };
  const remove = async () => {
    try {
      await api.del("/me");
      logout();
      toast("Аккаунт будет удалён через 7 дней. Вход отменит удаление.");
      navigate("/", { replace: true });
    } catch (error) {
      toast(error instanceof ApiError ? error.message : "Не получилось", "bad");
    }
  };
  return (
    <div className="screen">
      <h1>Данные и приватность</h1>
      <Card onClick={() => navigate("/privacy")}>📄 Политика конфиденциальности</Card>
      <Button kind="secondary" onClick={() => void exportData()}>Скачать мои данные (JSON)</Button>
      <Button kind="danger" onClick={() => setConfirm(true)}>Удалить аккаунт</Button>
      <Sheet open={confirm} onClose={() => setConfirm(false)} title="Удалить аккаунт?">
        <p>Все данные будут удалены через 7 дней. Пока не прошло 7 дней, вход отменит удаление. Скачайте данные заранее, если нужно.</p>
        <Button kind="danger" onClick={() => void remove()}>Удалить</Button>
      </Sheet>
    </div>
  );
}

export function LeagueScreen() {
  useBack("/profile");
  const query = useQuery({
    queryKey: ["league"],
    queryFn: () => api.get<{ tutor: string; week_start: string; table: { place: number; name: string; xp: number; me: boolean }[] }[]>("/league"),
  });
  if (query.isLoading) return <Spinner />;
  if (query.error || !query.data) return <ErrorView error={query.error} />;
  return (
    <div className="screen">
      <h1>Лига группы</h1>
      {!query.data.length ? <p className="muted">Лигу включает репетитор для своей группы. Сейчас её нет.</p> : null}
      {query.data.map((league) => (
        <Section key={league.tutor + league.week_start} title={`Группа: ${league.tutor}`}>
          {league.table.map((row) => (
            <div key={row.place} className={`tx${row.me ? " me" : ""}`}>
              <span>{row.place}. {row.name}</span>
              <span>{row.xp} XP</span>
            </div>
          ))}
        </Section>
      ))}
    </div>
  );
}
