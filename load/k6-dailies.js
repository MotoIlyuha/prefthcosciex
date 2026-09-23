// Load test of the core loop (design doc 12.6: p95 < 200 ms, generation < 200 ms).
// Synthetic students sign in with initData signed by the bot token — run it only
// against your own stand:  BASE=https://stage BOT_TOKEN=... k6 run load/k6-dailies.js
import crypto from "k6/crypto";
import http from "k6/http";
import { check, sleep } from "k6";

const BASE = (__ENV.BASE || "http://localhost:8080").replace(/\/$/, "");
const TOKEN = __ENV.BOT_TOKEN;

export const options = {
  scenarios: {
    students: {
      executor: "ramping-vus",
      stages: [
        { duration: "30s", target: Number(__ENV.VUS || 50) },
        { duration: __ENV.HOLD || "2m", target: Number(__ENV.VUS || 50) },
        { duration: "20s", target: 0 },
      ],
    },
  },
  thresholds: {
    "http_req_duration{kind:read}": ["p(95)<200"],
    "http_req_duration{kind:answer}": ["p(95)<400"],
    http_req_failed: ["rate<0.01"],
  },
};

function initData(id) {
  const fields = {
    auth_date: String(Math.floor(Date.now() / 1000)),
    query_id: `load${id}`,
    user: JSON.stringify({ id, first_name: `Load${id}`, language_code: "ru" }),
  };
  const check_string = Object.keys(fields).sort().map((k) => `${k}=${fields[k]}`).join("\n");
  const secret = crypto.hmac("sha256", "WebAppData", TOKEN, "binary");
  const hash = crypto.hmac("sha256", secret, check_string, "hex");
  return Object.entries({ ...fields, hash }).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join("&");
}

export function setup() {
  if (!TOKEN) throw new Error("BOT_TOKEN is required to sign synthetic initData");
}

// A repeated answer to an already closed task returns 409 by design (7.4).
http.setResponseCallback(http.expectedStatuses({ min: 200, max: 299 }, 409));

let session = null;

function signIn(id) {
  const auth = http.post(`${BASE}/api/auth/telegram`, JSON.stringify({ init_data: initData(id) }), {
    headers: { "Content-Type": "application/json" },
    tags: { kind: "auth" },
  });
  check(auth, { "signed in": (r) => r.status === 200 });
  if (auth.status !== 200) return null;
  const headers = { Authorization: `Bearer ${auth.json("access_token")}`, "Content-Type": "application/json" };
  http.patch(`${BASE}/api/me/onboarding`, JSON.stringify({ privacy_consent: true, step: 5, done: true }), { headers });
  return headers;
}

export default function () {
  const id = 9_000_000_000 + __VU;
  // Like the app: one sign-in per student, then the 15-minute access token.
  session = session || signIn(id);
  if (!session) {
    sleep(5);
    return;
  }
  const headers = session;
  const today = http.get(`${BASE}/api/today`, { headers, tags: { kind: "read" } });
  check(today, { "today ok": (r) => r.status === 200 });
  const items = today.status === 200 ? today.json("items") : [];
  for (const item of items.slice(0, 3)) {
    const task = http.get(`${BASE}/api/instances/${item.instance_id}`, { headers, tags: { kind: "read" } });
    check(task, { "task ok": (r) => r.status === 200 });
    sleep(1 + Math.random() * 2);
    const answer = http.post(
      `${BASE}/api/instances/${item.instance_id}/answer`,
      JSON.stringify({ answer: "0", time_spent_s: 120 }),
      { headers: { ...headers, "Idempotency-Key": `${id}-${item.instance_id}-${__ITER}` }, tags: { kind: "answer" } },
    );
    check(answer, { "answer accepted": (r) => r.status === 200 || r.status === 409 });
  }
  http.get(`${BASE}/api/confidence`, { headers, tags: { kind: "read" } });
  http.get(`${BASE}/api/progress?range=30d`, { headers, tags: { kind: "read" } });
  sleep(2);
}
