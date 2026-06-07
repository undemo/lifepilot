import { test } from "@playwright/test";
import { createPlanFromHome, expectToolTraceCompact, saveShot } from "./p0-helpers";

test("p0-tool-trace-dedup", async ({ page }) => {
  await createPlanFromHome(page, "我想下午一个人找个地方散散心。");
  await expectToolTraceCompact(page);
  await saveShot(page, "p0-tool-trace-dedup");
});
