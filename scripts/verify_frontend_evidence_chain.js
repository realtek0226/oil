const { chromium } = require("playwright");

const BASE_URL = process.env.OIL_RESEARCH_BASE_URL || "http://127.0.0.1:8036";
const USERNAME = process.env.OIL_RESEARCH_USERNAME || "admin";
const PASSWORD = process.env.OIL_RESEARCH_PASSWORD || "CHANGE_ME";

const REQUIRED_LABELS = [
  "价格锚点",
  "原油输入",
  "成品油资讯",
  "事件快讯",
  "标签口径",
  "点位映射",
  "区间口径",
  "政策窗口",
];

async function run() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 980 }, deviceScaleFactor: 1 });
  try {
    await page.goto(`${BASE_URL}/login`, { waitUntil: "domcontentloaded" });
    await page.fill("#login-username", USERNAME);
    await page.fill("#login-password", PASSWORD);
    await page.click("#login-submit");
    await page.waitForTimeout(2500);
    await page.goto(`${BASE_URL}/workbench#home`, { waitUntil: "domcontentloaded" });
    await page.waitForSelector(".evidence-chain-card", { timeout: 15000 });
    await page.waitForTimeout(1000);

    const result = await page.evaluate((requiredLabels) => {
      const cards = [...document.querySelectorAll(".evidence-chain-card")].map((element) => ({
        text: element.innerText,
        overflow:
          element.scrollWidth > element.clientWidth + 2 ||
          element.scrollHeight > element.clientHeight + 3,
      }));
      const allText = cards.map((card) => card.text).join("\n");
      return {
        url: location.href,
        card_count: cards.length,
        cards,
        missing_labels: requiredLabels.filter((label) => !allText.includes(label)),
        overflow_cards: cards.filter((card) => card.overflow),
        has_internal_english_reason: /local_market_overrides|local_factor_overlay/.test(allText),
        has_raw_label_code: /\bbullish_active\b|\bneutral_flat\b|\bbearish_selling\b|\bmedium\b|\bextreme\b/.test(allText),
      };
    }, REQUIRED_LABELS);

    console.log(JSON.stringify(result, null, 2));

    const failures = [];
    if (result.missing_labels.length) failures.push(`Missing labels: ${result.missing_labels.join(", ")}`);
    if (result.overflow_cards.length) failures.push(`Overflow cards: ${result.overflow_cards.length}`);
    if (result.has_internal_english_reason) failures.push("Evidence chain exposes internal English market-data reason.");
    if (result.has_raw_label_code) failures.push("Evidence chain exposes raw enum label code.");
    if (failures.length) {
      throw new Error(failures.join("\n"));
    }
  } finally {
    await browser.close();
  }
}

run().catch((error) => {
  console.error(error.message || error);
  process.exitCode = 1;
});
