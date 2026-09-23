import { expect, test } from "@playwright/test";

import { answerOf, instanceIdFrom, onboard, typeAnswer, uniqueId } from "./helpers";

/** A well-formed but wrong answer of the same kind as the real one. */
function wrongLike(answer: string): string {
  if (/^[-\d\s]+$/.test(answer)) return answer.split(" ").map((x) => String(Number(x) + 1)).join(" ");
  return answer.split("").reverse().join("") === answer ? answer.slice(1) + answer[0] : answer.split("").reverse().join("");
}

test("three wrong answers close a task and the reveal of the day is free", async ({ page }) => {
  await onboard(page, uniqueId());
  const wrong = wrongLike(await answerOf(instanceIdFrom(page)));
  for (let attempt = 0; attempt < 3; attempt++) {
    await typeAnswer(page, wrong);
    await page.getByTestId("submit-answer").click();
    await expect(page.getByTestId("answer-result")).toContainText(attempt < 2 ? "Ещё попытка" : "закрыта");
    const skip = page.getByRole("button", { name: "Пропустить" });
    await skip.click();
  }
  await expect(page.getByTestId("answer-result")).toContainText("Задача закрыта");
  await page.getByTestId("reveal").click();
  await expect(page.getByTestId("solution-answer")).not.toBeEmpty();
});

test("Python runs in the browser with the task's files", async ({ page }) => {
  await onboard(page, uniqueId());
  await page.getByRole("tab", { name: /Python/ }).click();
  const editor = page.locator(".cm-content");
  await expect(editor).toBeVisible();
  // On touch devices CodeMirror takes text through input events, as a phone keyboard sends it.
  await editor.fill("import os\nprint(sum(range(10)), sorted(os.listdir('.')))");
  await page.getByTestId("run-code").click();
  await expect(page.getByTestId("run-output")).toContainText("45", { timeout: 90_000 });
});
