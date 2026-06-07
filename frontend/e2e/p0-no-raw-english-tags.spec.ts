import { test } from "@playwright/test";
import { createPlanFromHome, expectNoRawMachineTerms, saveShot } from "./p0-helpers";

const samples = [
  "今天下午想和老婆孩子出去玩几个小时，老婆最近减脂，孩子5岁，别太远。",
  "下午和朋友出去玩，4个人，别太远，别太贵，想轻松一点。",
  "想和老婆过一下结婚纪念日，不想太夸张，但希望她觉得我用心。",
  "我想下午一个人找个地方散散心。"
];

for (const [index, sample] of samples.entries()) {
  test(`p0-no-raw-english-tags-${index + 1}`, async ({ page }) => {
    await createPlanFromHome(page, sample);
    await expectNoRawMachineTerms(page);
    await saveShot(page, `p0-no-raw-english-tags-${index + 1}`);
  });
}
