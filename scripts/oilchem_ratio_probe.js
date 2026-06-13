const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const username = process.env.OILCHEM_USER || "";
const password = process.env.OILCHEM_PASSWORD || "";
const storageStatePath = process.env.OILCHEM_STORAGE_STATE || "";

const keywordPattern = /山东|地炼|地方炼厂|成品油|汽油|柴油|产销率|产销|开工率|日度|数据终端/;

async function safeGoto(page, url, waitUntil = "domcontentloaded") {
  try {
    await page.goto(url, { waitUntil, timeout: 45000 });
  } catch (error) {
    return { ok: false, error: String(error.message || error) };
  }
  return { ok: true };
}

async function textSnapshot(page, limit = 1800) {
  return page.evaluate((limit) => {
    const text = (document.body?.innerText || "").replace(/\s+/g, " ").trim();
    const links = [...document.querySelectorAll("a[href]")]
      .map((a) => ({ text: a.textContent.trim().replace(/\s+/g, " ").slice(0, 100), href: a.href }))
      .filter((item) => item.text)
      .slice(0, 120);
    return {
      url: location.href,
      title: document.title,
      text: text.slice(0, limit),
      links,
    };
  }, limit);
}

function summarizeSnapshot(snapshot) {
  const matches = snapshot.links.filter((item) => keywordPattern.test(item.text) || keywordPattern.test(item.href));
  const textMatches = [];
  for (const key of ["山东", "地炼", "地方炼厂", "产销率", "产销", "开工率", "数据终端"]) {
    const index = snapshot.text.indexOf(key);
    if (index >= 0) {
      textMatches.push({
        key,
        excerpt: snapshot.text.slice(Math.max(0, index - 80), Math.min(snapshot.text.length, index + 180)),
      });
    }
  }
  return {
    url: snapshot.url,
    title: snapshot.title,
    link_matches: matches.slice(0, 20),
    text_matches: textMatches.slice(0, 10),
  };
}

async function checkLoginState(page) {
  const tokenResponse = await page.request.get("https://passport.oilchem.net/member/login/checkToken").catch(() => null);
  const tokenText = tokenResponse ? (await tokenResponse.text().catch(() => "")) : "";
  const state = await page.evaluate(() => ({
    topText: document.querySelector("#header_menu_top_login")?.innerText || "",
    loginBoxDisplay: document.querySelector("#loginBox") ? getComputedStyle(document.querySelector("#loginBox")).display : "",
    cookieNames: document.cookie.split(";").map((item) => item.trim().split("=")[0]).filter(Boolean),
  })).catch(() => ({}));
  return { tokenOk: tokenText.trim() === "true", tokenText: tokenText.trim().slice(0, 40), state };
}

async function tryPasswordLogin(page) {
  const authEvents = [];
  page.on("response", async (response) => {
    const url = response.url();
    if (!/login|check|dun|passport|member/i.test(url)) return;
    const contentType = response.headers()["content-type"] || "";
    if (/image|font|octet-stream/i.test(contentType)) return;
    let body = "";
    try {
      body = (await response.text())
        .replace(/[\u0000-\u001f\u007f-\u009f]/g, " ")
        .replace(/\s+/g, " ")
        .trim()
        .slice(0, 220);
    } catch (_) {
      body = "";
    }
    authEvents.push({ status: response.status(), url, body });
  });

  await safeGoto(page, "https://www.oilchem.net/", "networkidle");
  await page.evaluate(() => {
    if (typeof openAlert === "function") openAlert();
  }).catch(() => {});
  await page.waitForTimeout(1200);

  if (!username || !password) {
    return { attempted: false, reason: "missing_env_credentials", authEvents: [] };
  }

  await page.fill("#dialogUsername", username).catch(() => {});
  await page.fill("#dialogPassword", password).catch(() => {});
  await page.click("#smsValid").catch(() => {});
  await page.waitForTimeout(9000);

  const state = await checkLoginState(page);
  const captchaBlocked = authEvents.some(
    (item) => item.url.includes("dun.163.com") && item.body.includes('"result":false')
  );
  return {
    attempted: true,
    captchaBlocked,
    tokenOk: state.tokenOk,
    tokenText: state.tokenText,
    state: state.state,
    authEvents: authEvents.slice(-12),
  };
}

async function probeSearch(page) {
  const queries = [
    "山东地炼 成品油 日度 产销率",
    "山东地炼汽油产销率",
    "山东地炼成品油产销率",
    "地方炼厂 产销率 汽油 柴油",
    "隆众 山东地炼 产销率",
  ];
  const results = [];
  for (const query of queries) {
    const url = `https://search.oilchem.net/solrSearch/select.htm?keyword=${encodeURIComponent(query)}`;
    await safeGoto(page, url);
    await page.waitForTimeout(2500);
    const snapshot = await textSnapshot(page);
    results.push({ query, ...summarizeSnapshot(snapshot) });
  }
  return results;
}

async function probeColumns(page) {
  const urls = [
    "https://oil.oilchem.net/oil/oil_china_dilian.shtml",
    "https://oil.oilchem.net/oil/refinedoil.shtml",
    "https://oil.oilchem.net/444/",
    "https://oil.oilchem.net/445/",
    "https://dc.oilchem.net/page/#/list?channelIdNew=1695&name=%E6%B1%BD%E6%B2%B9&businessType=3",
    "https://dc.oilchem.net/page/#/list?channelIdNew=1695&name=%E6%9F%B4%E6%B2%B9&businessType=3",
    "https://www.oilchem.net/dt/",
    "https://dt.oilchem.net/home",
  ];
  const results = [];
  for (const url of urls) {
    await safeGoto(page, url);
    await page.waitForTimeout(4500);
    const snapshot = await textSnapshot(page);
    results.push({ probeUrl: url, ...summarizeSnapshot(snapshot) });
  }
  return results;
}

(async () => {
  const launchOptions = { headless: true };
  const browser = await chromium.launch(launchOptions);
  const contextOptions = { viewport: { width: 1365, height: 900 } };
  if (storageStatePath && fs.existsSync(storageStatePath)) {
    contextOptions.storageState = storageStatePath;
  }
  const context = await browser.newContext(contextOptions);
  const page = await context.newPage();

  const login = storageStatePath && fs.existsSync(storageStatePath)
    ? await checkLoginState(page)
    : await tryPasswordLogin(page);
  const search = await probeSearch(page);
  const columns = await probeColumns(page);

  await browser.close();

  const output = {
    generatedAt: new Date().toISOString(),
    login,
    search,
    columns,
  };
  const outPath = path.join("artifacts", "oilchem_ratio_probe_result.json");
  fs.mkdirSync("artifacts", { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(output, null, 2), "utf8");
  console.log(outPath);
  console.log(JSON.stringify({
    login: {
      attempted: login.attempted ?? Boolean(storageStatePath),
      captchaBlocked: login.captchaBlocked ?? false,
      tokenOk: login.tokenOk,
    },
    searchMatches: search.map((item) => ({
      query: item.query,
      linkCount: item.link_matches.length,
      textCount: item.text_matches.length,
      firstLinks: item.link_matches.slice(0, 3),
    })),
    columnMatches: columns.map((item) => ({
      url: item.probeUrl,
      linkCount: item.link_matches.length,
      textCount: item.text_matches.length,
      firstLinks: item.link_matches.slice(0, 3),
    })),
  }, null, 2));
})();
