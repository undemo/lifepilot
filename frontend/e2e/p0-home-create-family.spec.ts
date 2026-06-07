import { test, expect } from "@playwright/test";
import { createPlanFromHome, expectNoRawMachineTerms, expectToolTraceCompact, saveShot } from "./p0-helpers";

test("p0-home-create-family", async ({ page }) => {
  await createPlanFromHome(page, "今天下午想和老婆孩子出去玩几个小时，老婆最近减脂，孩子5岁，别太远。");
  await expect(page.getByText(/老婆|孩子|减脂|清淡|低负担/).first()).toBeVisible();
  await expect(page.getByRole("button", { name: "确认模拟执行" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "发起投票" })).toHaveCount(0);
  await expectNoRawMachineTerms(page);
  await expectToolTraceCompact(page);
  await saveShot(page, "p0-home-create-family");
});
