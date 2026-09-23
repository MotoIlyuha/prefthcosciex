import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api } from "../src/lib/api";
import { useAuth } from "../src/lib/auth";

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => {
  vi.unstubAllGlobals();
  useAuth.getState().logout();
});

describe("api client", () => {
  it("sends the bearer token and an Idempotency-Key on mutations", async () => {
    useAuth.getState().setTokens("A1", "R1");
    const fetchMock = vi.fn(async () => json(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    await api.post("/shop/buy", { item: "freeze" });
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    const headers = init.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer A1");
    expect(headers["Idempotency-Key"]).toMatch(/.{8,}/);
  });

  it("refreshes once on 401 and retries with the new token", async () => {
    useAuth.getState().setTokens("old", "R1");
    const calls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init: RequestInit) => {
      calls.push(`${url} ${(init.headers as Record<string, string>).Authorization ?? ""}`);
      if (url.endsWith("/auth/refresh")) return json(200, { access_token: "new", refresh_token: "R2" });
      return (init.headers as Record<string, string>).Authorization === "Bearer new"
        ? json(200, { id: 1 })
        : json(401, { detail: { code: "token_expired", message: "Сессия истекла" } });
    }));
    await expect(api.get<{ id: number }>("/me")).resolves.toEqual({ id: 1 });
    expect(calls).toEqual(["/api/me Bearer old", "/api/auth/refresh ", "/api/me Bearer new"]);
    expect(useAuth.getState().refreshToken).toBe("R2");
  });

  it("turns error details into ApiError with the server's Russian message", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json(402, { detail: { code: "insufficient_funds", message: "Нужно 50 🪙", price: 50 } })));
    const error = await api.post("/shop/buy", { item: "freeze" }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("insufficient_funds");
    expect((error as ApiError).message).toBe("Нужно 50 🪙");
    expect((error as ApiError).extra.price).toBe(50);
  });

  it("signs out when the refresh fails", async () => {
    useAuth.getState().setTokens("old", "R1");
    vi.stubGlobal("fetch", vi.fn(async () => json(401, { detail: { code: "bad_refresh", message: "Войдите заново" } })));
    await expect(api.get("/me")).rejects.toBeInstanceOf(ApiError);
    expect(useAuth.getState().accessToken).toBeNull();
  });
});
