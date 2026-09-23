import { expect, test } from "@playwright/test";

import { answerOf, instanceIdFrom, onboard, submitAnswer, typeAnswer, uniqueId } from "./helpers";

test("onboarding → daily → coins → floor by extern → exam, with the onboarding timer", async ({ page }) => {
  const started = Date.now();
  await onboard(page, uniqueId());
  await typeAnswer(page, await answerOf(instanceIdFrom(page)));
  await page.getByTestId("submit-answer").click();
  await expect(page.getByTestId("answer-result")).toContainText("🪙");
  // Design doc 11.2: first coins within the first minute, onboarding under 3 minutes.
  expect(Date.now() - started).toBeLessThan(60_000);
  await page.getByTestId("to-dailies").click();
  expect(Date.now() - started).toBeLessThan(180_000);

  // A daily task: the balance grows.
  const before = Number(await page.getByTestId("balance").textContent());
  await page.getByTestId("today-item").first().click();
  await expect(page.getByTestId("task-screen")).toBeVisible();
  await typeAnswer(page, await answerOf(instanceIdFrom(page)));
  await submitAnswer(page);
  await expect(page.getByTestId("answer-result")).toContainText("+");
  await page.goto("/");
  await expect(page.getByTestId("balance")).not.toHaveText(String(before));

  // Floor 2 by extern: three tasks at difficulty 4, all correct.
  await page.goto("/path/2");
  await page.getByRole("button", { name: /Экстерн/ }).click();
  await expect(page).toHaveURL(/\/trial\/\d+/);
  for (let i = 0; i < 3; i++) {
    const open = page.locator(".card").filter({ hasText: "решить" });
    await expect(open).toHaveCount(3 - i); // wait for the fresh trial state
    await open.first().click();
    await typeAnswer(page, await answerOf(instanceIdFrom(page)));
    await submitAnswer(page);
    await page.getByRole("button", { name: "К испытанию" }).click();
  }
  await page.goto("/path");
  await expect(page.getByTestId("floor-2")).toContainText("освоены");

  // Exam: a training block is free and ends with a score.
  await page.goto("/exam");
  await page.getByText("Тренировочный режим").click();
  await page.getByTestId("start-block").click();
  await page.getByRole("button", { name: "Завершить", exact: true }).click();
  await page.getByTestId("exam-finish").click();
  await expect(page.getByTestId("exam-result")).toContainText("первичных");
});
