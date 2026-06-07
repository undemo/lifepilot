import { test, expect } from "@playwright/test";
import { createPlanFromHome, expectNoRawMachineTerms, expectToolTraceCompact, saveShot } from "./p0-helpers";

test("p0-solo-mood-relief", async ({ page }) => {
  await createPlanFromHome(page, "我想下午一个人找个地方散散心。");
  await expect(page.getByText(/一个人|散心|低压力|放松/).first()).toBeVisible();
  await expect(page.getByText(/安静独处|放松情绪|轻松走走|低压力/).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "发起投票" })).toHaveCount(0);
  await expectNoRawMachineTerms(page);
  await expectToolTraceCompact(page);
  await saveShot(page, "p0-solo-mood-relief");
});
