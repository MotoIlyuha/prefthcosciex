import { expect, test } from "@playwright/test";

import { onboard, uniqueId } from "./helpers";

test.use({ viewport: { width: 360, height: 740 } });

test("360 px: no horizontal scroll on the main screens", async ({ page }) => {
  await onboard(page, uniqueId());
  for (const path of ["/", "/path", "/progress", "/confidence", "/profile", "/profile/settings", "/exam", page.url()]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `horizontal overflow on ${path}`).toBeLessThanOrEqual(0);
  }
});
