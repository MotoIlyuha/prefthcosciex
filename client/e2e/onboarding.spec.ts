import { expect, test } from "@playwright/test";

import { answerOf, instanceIdFrom, onboard, typeAnswer, uniqueId } from "./helpers";

test("onboarding ends with a first win and opens the dailies", async ({ page }) => {
  await onboard(page, uniqueId());
  const answer = await answerOf(instanceIdFrom(page));
  await typeAnswer(page, answer);
  await page.getByTestId("submit-answer").click();
  const result = page.getByTestId("answer-result");
  await expect(result).toContainText("Верно");
  await expect(result).toContainText("+12 🪙");
  await page.getByTestId("to-dailies").click();
  await expect(page.getByTestId("today")).toBeVisible();
  await expect(page.getByTestId("today-item").first()).toBeVisible();
  expect(await page.getByTestId("today-item").count()).toBeGreaterThanOrEqual(3);
  await expect(page.getByTestId("balance")).toHaveText("12");
});
