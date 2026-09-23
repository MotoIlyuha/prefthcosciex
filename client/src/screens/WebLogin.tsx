// Web version sign-in (11.10): a one-time link from the bot (`?token=`) or the
// Telegram login redirect (`#tgAuthResult=` — the Login Widget without its script,
// because the CSP allows no third-party scripts).
import { useEffect, useRef, useState } from "react";

import { Spinner } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";

interface SessionResponse {
  access_token: string;
  refresh_token: string;
}

export function decodeAuthResult(hash: string): Record<string, string | number> | null {
  const match = /tgAuthResult=([^&]+)/.exec(hash);
  if (!match?.[1]) return null;
  try {
    const padded = match[1].replace(/-/g, "+").replace(/_/g, "/");
    const json = decodeURIComponent(escape(atob(padded)));
    return JSON.parse(json) as Record<string, string | number>;
  } catch {
    return null;
  }
}

export function WebLoginScreen({ onDone }: { onDone: () => void }) {
  const setTokens = useAuth((s) => s.setTokens);
  const [error, setError] = useState<string | null>(null);
  const started = useRef(false);
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void (async () => {
      try {
        const token = new URLSearchParams(window.location.search).get("token");
        const widget = decodeAuthResult(window.location.hash);
        let session: SessionResponse;
        if (token) session = await api.post<SessionResponse>("/auth/web-link", { token }, false);
        else if (widget) session = await api.post<SessionResponse>("/auth/widget", widget, false);
        else throw new ApiError(401, "no_credentials", "Ссылка неполная. Попросите новую у бота: /web");
        setTokens(session.access_token, session.refresh_token);
        window.history.replaceState(null, "", "/");
        onDone();
      } catch (e) {
        setError(e instanceof ApiError ? e.message : "Не удалось войти");
      }
    })();
  }, [onDone, setTokens]);
  if (error) {
    return (
      <div className="screen center-screen">
        <h1>Вход не удался</h1>
        <p>{error}</p>
      </div>
    );
  }
  return <Spinner label="Входим в веб‑версию…" />;
}
