import fs from "fs";
import path from "path";
import { expect, type Page } from "@playwright/test";

export const rawMachineTerms = [
  "quiet_alone",
  "mood_relief",
  "rain_safe",
  "mock_route",
  "restaurant_capacity",
  "mock_api",
  "tool_log",
  "verifier_log",
  "executor_log",
  "constraint_log",
  "reserve_restaurant",
  "book_activity",
  "failure_injection",
  "Prompt",
  "chain_of_thought",
  "API Key"
];

export async function createPlanFromHome(page: Page, input: string) {
  await page.goto("/");
  await page.locator(".mobile-frame[data-hydrated='true']").waitFor({ state: "visible" });
  const inputBox = page.locator("textarea");
  const generateButton = page.getByRole("button", { name: "生成计划", exact: true });
  await expect(generateButton).toBeEnabled();
  await inputBox.fill(input);
  await expect(inputBox).toHaveValue(input);
  await page.waitForTimeout(300);
  await generateButton.click();
  await page.waitForURL(/\/plans\/creating/);
  const clarificationCard = page.getByLabel("补充偏好工具步骤");
  const needsClarification = await clarificationCard.waitFor({ state: "visible", timeout: 1000 }).then(() => true).catch(() => false);
  if (needsClarification) {
    for (let index = 0; index < 3; index += 1) {
      const autoButton = page.getByRole("button", { name: "你来定", exact: true });
      if (await autoButton.isVisible().catch(() => false)) {
        await autoButton.click();
      } else {
        await clarificationCard.locator(".choice-chip").first().click();
      }
      await page.waitForTimeout(300);
      if (!(await clarificationCard.isVisible().catch(() => false))) break;
    }
  }
  const openPlanButton = page.getByRole("button", { name: "查看完整计划", exact: true });
  await openPlanButton.waitFor({ state: "visible", timeout: 45_000 });
  await openPlanButton.click();
  await page.waitForURL(/\/plans\/plan_/, { timeout: 20_000 });
  await expect(page.getByText("目标理解")).toBeVisible();
  await expect(page.getByRole("heading", { name: "时间线" })).toBeVisible();
}

export async function expectNoRawMachineTerms(page: Page) {
  const body = await page.locator("body").innerText();
  for (const term of rawMachineTerms) {
    expect(body, `ordinary page must not show ${term}`).not.toContain(term);
  }
}

export async function expectToolTraceCompact(page: Page) {
  const panel = page.locator("section.card", { hasText: "可行性检查摘要" });
  await expect(panel).toBeVisible();
  const rows = await panel.locator(".row-between").count();
  expect(rows).toBeLessThanOrEqual(8);
  await expect(panel.locator(".tool-call-row").first()).toBeVisible();
  await expect(panel.locator(".tool-call-row").nth(2)).toBeVisible();
}

export async function saveShot(page: Page, name: string) {
  const dir = path.resolve(__dirname, "../../reports/screenshots");
  fs.mkdirSync(dir, { recursive: true });
  await page.screenshot({ path: path.join(dir, `${name}.png`), fullPage: true });
}
