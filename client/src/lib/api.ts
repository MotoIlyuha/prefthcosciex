// HTTP client for the Bayt API: bearer token, transparent refresh, Idempotency-Key.
import { useAuth } from "./auth";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public extra: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

const BASE = import.meta.env.VITE_API_BASE ?? "/api";

export function newKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

type Detail = { code?: string; message?: string; [key: string]: unknown };

async function parseError(response: Response): Promise<ApiError> {
  let detail: Detail;
  try {
    const body = (await response.json()) as { detail?: Detail | string };
    detail = typeof body.detail === "string" ? { message: body.detail } : (body.detail ?? {});
  } catch {
    detail = {};
  }
  const { code, message, ...extra } = detail;
  return new ApiError(
    response.status,
    code ?? "http_" + response.status,
    message ?? "Что-то пошло не так. Попробуйте ещё раз.",
    extra,
  );
}

let refreshing: Promise<boolean> | null = null;

async function refreshTokens(): Promise<boolean> {
  const { refreshToken, setTokens, logout } = useAuth.getState();
  const response = await fetch(`${BASE}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "same-origin",
    body: JSON.stringify({ refresh_token: refreshToken }),
  });
  if (!response.ok) {
    logout();
    return false;
  }
  const data = (await response.json()) as { access_token: string; refresh_token: string };
  setTokens(data.access_token, data.refresh_token);
  return true;
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  idempotent?: boolean | string;
  raw?: boolean;
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const method = options.method ?? (options.body === undefined ? "GET" : "POST");
  const key =
    typeof options.idempotent === "string"
      ? options.idempotent
      : options.idempotent
        ? newKey()
        : undefined;
  const send = () => {
    const headers: Record<string, string> = {};
    const token = useAuth.getState().accessToken;
    if (token) headers.Authorization = `Bearer ${token}`;
    if (options.body !== undefined) headers["Content-Type"] = "application/json";
    if (key) headers["Idempotency-Key"] = key;
    return fetch(`${BASE}${path}`, {
      method,
      headers,
      credentials: "same-origin",
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
  };
  let response = await send();
  if (response.status === 401 && useAuth.getState().refreshToken) {
    refreshing ??= refreshTokens().finally(() => {
      refreshing = null;
    });
    if (await refreshing) response = await send();
  }
  if (!response.ok) throw await parseError(response);
  if (response.status === 204) return undefined as T;
  if (options.raw) return (await response.blob()) as T;
  const type = response.headers.get("Content-Type") ?? "";
  if (type.includes("text/html")) return (await response.text()) as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown = {}, idempotent: boolean | string = true) =>
    request<T>(path, { method: "POST", body, idempotent }),
  patch: <T>(path: string, body: unknown) => request<T>(path, { method: "PATCH", body }),
  put: <T>(path: string, body: unknown) => request<T>(path, { method: "PUT", body }),
  del: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  blob: (path: string) => request<Blob>(path, { raw: true }),
};
