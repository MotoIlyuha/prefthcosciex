import { expect, test } from "@playwright/test";

import { answerOf, onboard, uniqueId } from "./helpers";

test("a training block exam: save answers, finish, see the score", async ({ page }) => {
  await onboard(page, uniqueId());
  await page.goto("/exam");
  await page.getByText("Тренировочный режим").click();
  await page.getByTestId("start-block").click();
  await expect(page.getByTestId("exam-run")).toBeVisible();
  const examId = Number(/\/exam\/(\d+)/.exec(page.url())![1]);
  const response = await page.request.get(`/api/exams/${examId}`, {
    headers: { Authorization: `Bearer ${await page.evaluate(() => JSON.parse(sessionStorage.getItem("bayt.session")!).accessToken)}` },
  });
  const exam = (await response.json()) as { sheet: { position: number; instance: { id: number } }[] };
  const first = exam.sheet[0]!;
  await page.getByTestId("exam-answer").fill(await answerOf(first.instance.id));
  await page.getByTestId("exam-save").click();
  await page.getByRole("button", { name: "Завершить", exact: true }).click();
  await page.getByTestId("exam-finish").click();
  await expect(page.getByTestId("exam-result")).toContainText("1 первичных");
});
