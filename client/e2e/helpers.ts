import { expect, type Page } from "@playwright/test";
import pg from "pg";

const url = process.env.E2E_DATABASE_URL ?? "postgresql://bayt:bayt@localhost:5432/bayt";

/** Test-only: read an instance's answer straight from the database. */
export async function answerOf(instanceId: number): Promise<string> {
  const client = new pg.Client({ connectionString: url });
  await client.connect();
  try {
    const result = await client.query<{ answer: string }>("select answer from instances where id = $1", [instanceId]);
    return result.rows[0]!.answer;
  } finally {
    await client.end();
  }
}

export function uniqueId(): number {
  return 700_000 + Math.floor(Math.random() * 200_000);
}

export async function signIn(page: Page, tgId: number, name = "Аня"): Promise<void> {
  await page.goto(`/?dev=${tgId}&name=${encodeURIComponent(name)}`);
}

export async function onboard(page: Page, tgId: number): Promise<void> {
  await signIn(page, tgId);
  await expect(page.getByTestId("onboarding")).toBeVisible();
  await page.getByTestId("consent").check();
  await page.getByTestId("next").click();
  await page.getByTestId("band-B").click();
  await page.getByTestId("python-little").click();
  await page.getByTestId("next").click();
  await page.getByTestId("first-task").click();
  await expect(page.getByTestId("task-screen")).toBeVisible();
}

export function instanceIdFrom(page: Page): number {
  const match = /\/task\/(\d+)/.exec(page.url());
  if (!match) throw new Error(`not on a task page: ${page.url()}`);
  return Number(match[1]);
}

export async function typeAnswer(page: Page, answer: string): Promise<void> {
  const parts = answer.split(" ");
  const pair = page.getByLabel("Первое число");
  if ((await pair.count()) > 0) {
    await pair.fill(parts[0] ?? "");
    await page.getByLabel("Второе число").fill(parts[1] ?? "");
  } else {
    await page.getByTestId("answer-input").fill(answer);
  }
}

/** Submit the answer; if the method check appears (too fast), pick the listed method. */
export async function submitAnswer(page: Page): Promise<void> {
  await page.getByTestId("submit-answer").click();
  const result = page.getByTestId("answer-result");
  const dialog = page.getByRole("dialog");
  await expect(result.or(dialog)).toBeVisible();
  if (await dialog.isVisible()) {
    await dialog.getByRole("button").nth(1).click();
    await expect(result).toBeVisible();
  }
}
