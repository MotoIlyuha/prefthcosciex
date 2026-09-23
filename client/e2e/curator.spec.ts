import { expect, test } from "@playwright/test";

import { onboard, uniqueId } from "./helpers";

test("a parent accepts an invite and sees the student after the student chooses access", async ({ browser }) => {
  const student = await browser.newPage();
  await onboard(student, uniqueId());
  const token = await student.evaluate(async () => {
    const session = JSON.parse(sessionStorage.getItem("bayt.session")!) as { accessToken: string };
    const r = await fetch("/api/curators/invite", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${session.accessToken}` },
      body: JSON.stringify({ role: "parent" }),
    });
    return ((await r.json()) as { token: string }).token;
  });
  const parent = await browser.newPage();
  await parent.goto(`/?dev=${uniqueId()}&name=${encodeURIComponent("Мама")}&startapp=cur_${token}`);
  await expect(parent.getByTestId("onboarding").or(parent.getByTestId("students"))).toBeVisible();

  await student.goto("/profile/curators");
  await expect(student.getByTestId("curators")).toContainText("Мама");
  await student.getByRole("button", { name: "Прогресс" }).click();
  await student.getByRole("button", { name: "Так вас видит куратор" }).click();
  await expect(student.getByRole("dialog")).toContainText("Прогноз балла");
  await expect(student.getByRole("dialog")).not.toContainText("История попыток");
});
