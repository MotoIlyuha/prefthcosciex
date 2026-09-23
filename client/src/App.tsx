// App shell: sign-in, deep links, the five tabs (+ «Ученики» for curators), routes.
import { useQuery } from "@tanstack/react-query";
import { useSignal, viewportContentSafeAreaInsets, viewportSafeAreaInsets } from "@telegram-apps/sdk-react";
import { useEffect, useRef, useState } from "react";
import { NavLink, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";

import { Button, ErrorView, Spinner, Toaster } from "./components/ui";
import { api, ApiError } from "./lib/api";
import { useAuth } from "./lib/auth";
import { useMe } from "./lib/hooks";
import { cloudGet, cloudSet, initTelegram, isTelegram, rawInitData, startParam } from "./lib/tg";
import { AdminScreen } from "./screens/Admin";
import { StudentScreen, StudentsScreen } from "./screens/Curator";
import { ExamHome, ExamRun } from "./screens/Exam";
import { LegalScreen } from "./screens/Legal";
import { OnboardingScreen } from "./screens/Onboarding";
import { FloorScreen, PathScreen, TrialScreen } from "./screens/Path";
import {
  CuratorsScreen,
  LeagueScreen,
  PrivacyScreen,
  ProfileScreen,
  ReportsScreen,
  SettingsScreen,
  ShopScreen,
  WalletScreen,
} from "./screens/Profile";
import { ConfidenceScreen, ConfidenceTaskScreen, ProgressScreen, TheoryScreen } from "./screens/Stats";
import { TaskScreen } from "./screens/Task";
import { TodayScreen } from "./screens/Today";
import { WebLoginScreen } from "./screens/WebLogin";

interface SessionResponse {
  access_token: string;
  refresh_token: string;
  start_param?: string | null;
}

const REFRESH_KEY = "bayt_refresh";

type Boot = "loading" | "ready" | "signed_out" | "error";

async function signIn(): Promise<string | undefined> {
  const { setTokens, accessToken, refreshToken } = useAuth.getState();
  const params = new URLSearchParams(window.location.search);
  const devId = import.meta.env.DEV || import.meta.env.VITE_E2E ? params.get("dev") : null;
  if (devId) {
    const r = await api.post<SessionResponse>("/auth/dev", { tg_id: Number(devId), first_name: params.get("name") ?? "Тест" }, false);
    setTokens(r.access_token, r.refresh_token);
    return undefined;
  }
  const initData = rawInitData();
  if (initData) {
    const r = await api.post<SessionResponse>("/auth/telegram", { init_data: initData }, false);
    setTokens(r.access_token, r.refresh_token);
    void cloudSet(REFRESH_KEY, r.refresh_token);
    return r.start_param ?? undefined;
  }
  if (accessToken) return undefined;
  const stored = refreshToken ?? (await cloudGet(REFRESH_KEY));
  // The web version keeps the refresh token in an httpOnly cookie: an empty body works.
  const r = await api.post<SessionResponse>("/auth/refresh", stored ? { refresh_token: stored } : {}, false);
  setTokens(r.access_token, r.refresh_token);
  return undefined;
}

function routeForStart(param: string): string | null {
  if (param.startsWith("task_")) return `/task/${param.slice(5)}`;
  if (param.startsWith("exam")) return "/exam";
  if (param.startsWith("students")) return "/students";
  const screens: Record<string, string> = {
    today: "/", path: "/path", progress: "/progress", confidence: "/confidence", profile: "/profile",
  };
  const [screen] = param.split("_");
  return screens[screen ?? ""] ?? null;
}

/** Safe-area insets from Telegram (fullscreen on iOS/Android) as CSS variables. */
function SafeArea() {
  const content = useSignal(viewportContentSafeAreaInsets);
  const device = useSignal(viewportSafeAreaInsets);
  useEffect(() => {
    const style = document.documentElement.style;
    style.setProperty("--safe-top", `${(content?.top ?? 0) + (device?.top ?? 0)}px`);
    style.setProperty("--safe-bottom", `${(content?.bottom ?? 0) + (device?.bottom ?? 0)}px`);
  }, [content, device]);
  return null;
}

function Tabbar({ curator }: { curator: boolean }) {
  const tabs: [string, string, string][] = [
    ...(curator ? ([["/students", "Ученики", "👥"]] as [string, string, string][]) : []),
    ["/", "Сегодня", "☀️"],
    ["/path", "Путь", "🧭"],
    ["/progress", "Прогресс", "📈"],
    ["/confidence", "Уверенность", "🎯"],
    ["/profile", "Профиль", "👤"],
  ];
  return (
    <nav className="tabbar">
      {tabs.map(([to, title, icon]) => (
        <NavLink key={to} to={to} end={to === "/"} className={({ isActive }) => (isActive ? "active" : "")}>
          <span aria-hidden>{icon}</span>
          <span>{title}</span>
        </NavLink>
      ))}
    </nav>
  );
}

function Main() {
  const me = useMe();
  const location = useLocation();
  if (me.isLoading) return <Spinner />;
  if (me.error || !me.data) return <ErrorView error={me.error} onRetry={() => void me.refetch()} />;
  const legal = location.pathname === "/privacy";
  if (!me.data.settings.onboarding_done && !location.pathname.startsWith("/task/") && !legal) {
    return <OnboardingScreen />;
  }
  const curator = me.data.is_curator;
  return (
    <>
      <main className="content">
        <Routes>
          <Route path="/" element={<TodayScreen />} />
          <Route path="/task/:id" element={<TaskScreen />} />
          <Route path="/path" element={<PathScreen />} />
          <Route path="/path/:floor" element={<FloorScreen />} />
          <Route path="/trial/:id" element={<TrialScreen />} />
          <Route path="/progress" element={<ProgressScreen />} />
          <Route path="/confidence" element={<ConfidenceScreen />} />
          <Route path="/confidence/:task" element={<ConfidenceTaskScreen />} />
          <Route path="/theory/:task" element={<TheoryScreen />} />
          <Route path="/exam" element={<ExamHome />} />
          <Route path="/exam/:id" element={<ExamRun />} />
          <Route path="/profile" element={<ProfileScreen />} />
          <Route path="/profile/settings" element={<SettingsScreen />} />
          <Route path="/profile/curators" element={<CuratorsScreen />} />
          <Route path="/profile/shop" element={<ShopScreen />} />
          <Route path="/profile/wallet" element={<WalletScreen />} />
          <Route path="/profile/reports" element={<ReportsScreen />} />
          <Route path="/profile/privacy" element={<PrivacyScreen />} />
          <Route path="/league" element={<LeagueScreen />} />
          <Route path="/students" element={<StudentsScreen />} />
          <Route path="/students/:id" element={<StudentScreen />} />
          <Route path="/admin" element={me.data.is_admin ? <AdminScreen /> : <Navigate to="/" replace />} />
          <Route path="/privacy" element={<LegalScreen />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <Tabbar curator={curator} />
    </>
  );
}

export function App() {
  const [boot, setBoot] = useState<Boot>("loading");
  const [bootError, setBootError] = useState<unknown>(null);
  const navigate = useNavigate();
  const location = useLocation();
  const started = useRef(false);
  const token = useAuth((s) => s.accessToken);
  const onWebLogin = location.pathname.startsWith("/web/login");

  useEffect(() => {
    if (started.current || onWebLogin) return;
    started.current = true;
    initTelegram();
    void (async () => {
      try {
        const fromAuth = await signIn();
        const param = fromAuth ?? startParam();
        if (param?.startsWith("cur_")) {
          try {
            await api.post("/curators/accept", { token: param.slice(4) }, false);
            navigate("/students", { replace: true });
          } catch {
            navigate("/", { replace: true });
          }
        } else if (param) {
          const target = routeForStart(param);
          if (target) navigate(target, { replace: true });
        }
        setBoot("ready");
      } catch (error) {
        if (error instanceof ApiError && error.status === 401) setBoot("signed_out");
        else {
          setBootError(error);
          setBoot("error");
        }
      }
    })();
  }, [navigate, onWebLogin]);

  useEffect(() => {
    if (!token && boot === "ready") setBoot("signed_out");
  }, [token, boot]);

  if (onWebLogin) return <WebLoginScreen onDone={() => { setBoot("ready"); started.current = true; navigate("/", { replace: true }); }} />;
  if (boot === "loading") return <Spinner label="Входим…" />;
  if (boot === "error") return <ErrorView error={bootError} onRetry={() => window.location.reload()} />;
  if (boot === "signed_out") {
    if (location.pathname === "/privacy") return <LegalScreen />;
    return <SignedOut />;
  }
  return (
    <div className="app">
      {isTelegram() ? <SafeArea /> : null}
      <Main />
      <Toaster />
    </div>
  );
}

function SignedOut() {
  const config = useQuery({
    queryKey: ["public-config"],
    queryFn: () => api.get<{ bot_username: string; bot_id: number | null }>("/config/public"),
  });
  const origin = window.location.origin;
  const botId = config.data?.bot_id;
  const oauth = botId
    ? `https://oauth.telegram.org/auth?bot_id=${botId}&origin=${encodeURIComponent(origin)}&request_access=write&return_to=${encodeURIComponent(origin + "/web/login")}`
    : null;
  return (
    <div className="screen center-screen" data-testid="signed-out">
      <h1>Байт</h1>
      <p className="lead">Подготовка к ЕГЭ‑2027 по информатике: 15 минут в день.</p>
      {isTelegram() ? (
        <p>Не удалось войти. Закройте и откройте приложение ещё раз.</p>
      ) : (
        <>
          <p>Веб‑версия — для решения за компьютером. Войдите через Telegram:</p>
          {oauth ? <Button onClick={() => window.location.assign(oauth)}>Войти через Telegram</Button> : null}
          <p className="muted small">
            Или напишите боту {config.data?.bot_username ? `@${config.data.bot_username}` : ""} команду /web — он пришлёт одноразовую ссылку.
          </p>
        </>
      )}
    </div>
  );
}
