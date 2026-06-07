import { test, expect } from "@playwright/test";
import { createPlanFromHome, expectNoRawMachineTerms, saveShot } from "./p0-helpers";

test("p0-friend-vote-button-condition", async ({ page }) => {
  await createPlanFromHome(page, "下午和朋友出去玩，4个人，别太远，别太贵，想轻松一点。");
  await expect(page.getByRole("button", { name: "发起投票" })).toBeVisible();
  await expect(page.getByRole("button", { name: "确认模拟执行" })).toBeEnabled();
  await expectNoRawMachineTerms(page);
  await saveShot(page, "p0-friend-vote-button-condition");
});
