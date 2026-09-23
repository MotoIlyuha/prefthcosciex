import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api } from "./api";
import { showBackButton, applyMainButton, type MainButtonSpec } from "./tg";
import type { Me } from "./types";

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => api.get<Me>("/me"), staleTime: 30_000 });
}

export function useRefreshAll() {
  const client = useQueryClient();
  return () => client.invalidateQueries();
}

/** Telegram's MainButton when inside Telegram; `true` means render an on-page button. */
export function useMainButton(spec: MainButtonSpec | null): boolean {
  const [fallback, setFallback] = useState(true);
  const text = spec?.text;
  const enabled = spec?.enabled;
  const loading = spec?.loading;
  const onClick = spec?.onClick;
  useEffect(() => {
    if (!text || !onClick) return;
    const cleanup = applyMainButton({ text, enabled, loading, onClick });
    setFallback(cleanup === false);
    return cleanup === false ? undefined : cleanup;
  }, [text, enabled, loading, onClick]);
  return fallback;
}

export function useBackButton(onBack: (() => void) | null) {
  useEffect(() => {
    if (!onBack) return;
    return showBackButton(onBack);
  }, [onBack]);
}

export function useNow(intervalMs = 1000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return now;
}
