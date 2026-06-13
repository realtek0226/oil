const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const storageStatePath = process.env.OILCHEM_STORAGE_STATE || "configs/oilchem_storage_state.json";

const queries = [
  "山东地炼 低价资源 扫空",
  "山东地炼 抢货 贸易商",
  "山东地炼 抛货 贸易商",
  "山东地炼 出货节奏 顺畅 承压",
  "山东地炼 封单 惜售",
  "山东地炼 成交重心 低端上移",
];

const targetWords = [
  "低价资源",
  "扫空",
  "抢货",
  "抛货",
  "贸易商",
  "出货",
  "出货节奏",
  "顺畅",
  "承压",
  "封单",
  "惜售",
  "成交重心",
  "低端",
  "上移",
];

const memberWords = [
  "会员",
  "登录",
  "权限",
  "购买",
  "开通",
  "试看",
  "数据终端",
  "VIP",
  "付费",
];

function compactText(value, limit = 220) {
  return String(value || "").replace(/\s+/g, " ").trim().slice(0, limit);
}

function classifyAccess(text) {
  const compact = compactText(text, 2000);
  const memberHit = memberWords.filter((word) => compact.includes(word));
  const targetHit = targetWords.filter((word) => compact.includes(word));
  return {
    hasTargetWords: targetHit.length > 0,
    targetHit,
    looksMemberGated: memberHit.length > 0 && compact.length < 2500,
    memberHit,
  };
}

async function safeGoto(page, url) {
  try {
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 45000 });
    await page.waitForTimeout(1800);
    return { ok: true };
  } catch (error) {
    return { ok: false, error: String(error.message || error) };
  }
}

async function snapshot(page, limit = 5000) {
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      return await page.evaluate((limit) => {
        const text = (document.body?.innerText || "").replace(/\s+/g, " ").trim();
        const links = [...document.querySelectorAll("a[href]")]
          .map((a) => ({
            text: (a.textContent || "").replace(/\s+/g, " ").trim(),
            href: a.href,
          }))
          .filter((item) => item.text && /^https?:\/\//.test(item.href))
          .slice(0, 80);
        return {
          url: location.href,
          title: document.title,
          text: text.slice(0, limit),
          links,
        };
      }, limit);
    } catch (error) {
      if (attempt === 2) throw error;
      await page.waitForTimeout(1000);
    }
  }
}

function pickCandidateLinks(links) {
  const seen = new Set();
  const candidates = [];
  for (const link of links) {
    const blob = `${link.text} ${link.href}`;
    if (!targetWords.some((word) => blob.includes(word)) && !/oilchem\.net/.test(link.href)) continue;
    if (seen.has(link.href)) continue;
    seen.add(link.href);
    candidates.push(link);
    if (candidates.length >= 2) break;
  }
  return candidates;
}

async function probeQuery(context, query) {
  const page = await context.newPage();
  const searchUrl = `https://search.oilchem.net/solrSearch/select.htm?keyword=${encodeURIComponent(query)}`;
  const gotoResult = await safeGoto(page, searchUrl);
  const searchSnapshot = gotoResult.ok ? await snapshot(page) : { url: searchUrl, title: "", text: "", links: [] };
  const candidates = pickCandidateLinks(searchSnapshot.links);

  const details = [];
  for (const candidate of candidates.slice(0, 1)) {
    const detailPage = await context.newPage();
    const detailGoto = await safeGoto(detailPage, candidate.href);
    const detailSnapshot = detailGoto.ok ? await snapshot(detailPage, 8000) : { url: candidate.href, title: "", text: "", links: [] };
    details.push({
      title: compactText(candidate.text),
      url: candidate.href,
      goto: detailGoto,
      pageTitle: detailSnapshot.title,
      access: classifyAccess(detailSnapshot.text),
      excerpt: compactText(detailSnapshot.text, 700),
    });
    await detailPage.close();
  }

  await page.close();
  return {
    query,
    searchUrl,
    goto: gotoResult,
    searchTitle: searchSnapshot.title,
    searchAccess: classifyAccess(searchSnapshot.text),
    searchExcerpt: compactText(searchSnapshot.text, 500),
    candidateLinks: candidates.map((item) => ({ title: compactText(item.text), url: item.href })),
    details,
  };
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const contextOptions = {
    viewport: { width: 1365, height: 900 },
    userAgent:
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0 Safari/537.36",
  };
  if (fs.existsSync(storageStatePath)) {
    contextOptions.storageState = storageStatePath;
  }
  const context = await browser.newContext(contextOptions);

  const results = [];
  for (const query of queries) {
    results.push(await probeQuery(context, query));
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }

  await browser.close();

  const output = {
    generatedAt: new Date().toISOString(),
    storageStateUsed: fs.existsSync(storageStatePath),
    queries: results,
  };
  const outPath = path.join("artifacts", "oilchem_spot_qualitative_probe.json");
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(output, null, 2), "utf8");

  console.log(outPath);
  console.log(
    JSON.stringify(
      results.map((item) => ({
        query: item.query,
        searchTitle: item.searchTitle,
        searchTargetHit: item.searchAccess.targetHit,
        searchMemberHit: item.searchAccess.memberHit,
        candidates: item.candidateLinks.length,
        firstDetail: item.details[0]
          ? {
              title: item.details[0].title,
              targetHit: item.details[0].access.targetHit,
              memberHit: item.details[0].access.memberHit,
              looksMemberGated: item.details[0].access.looksMemberGated,
            }
          : null,
      })),
      null,
      2
    )
  );
})();
