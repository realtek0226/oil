const fs = require("fs");
const path = require("path");
const readline = require("readline");
const { chromium } = require("playwright");

const outputPath = process.env.OILCHEM_STORAGE_STATE || "configs/oilchem_storage_state.json";

function ask(question) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => {
    rl.question(question, (answer) => {
      rl.close();
      resolve(answer);
    });
  });
}

(async () => {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({ viewport: { width: 1365, height: 900 } });
  const page = await context.newPage();
  await page.goto("https://www.oilchem.net/", { waitUntil: "domcontentloaded" });
  console.log("请在打开的浏览器中手动登录隆众资讯。");
  await ask("登录完成后回到这里按回车保存登录态...");
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  await context.storageState({ path: outputPath });
  await browser.close();
  console.log(`已保存登录态: ${outputPath}`);
})();
