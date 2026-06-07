import { test, expect } from "@playwright/test";
import { createPlanFromHome, saveShot } from "./p0-helpers";

test("p0-confirm-button-condition", async ({ page }) => {
  await createPlanFromHome(page, "想和老婆过一下结婚纪念日，不想太夸张，但希望她觉得我用心。");
  const refresh = page.getByRole("button", { name: "刷新可执行窗口" });
  if (await refresh.count()) {
    await expect(refresh).toBeEnabled();
  } else {
    await expect(page.getByRole("button", { name: "确认模拟执行" })).toBeEnabled();
  }
  await saveShot(page, "p0-confirm-button-condition");
});
