const fs = require("fs");
const path = require("path");

const SEARCH_URL = "https://search.oilchem.net/article/search";
const STORAGE_STATE = process.env.OILCHEM_STORAGE_STATE || "configs/oilchem_storage_state.json";

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
  "顺畅",
  "承压",
  "封单",
  "惜售",
  "成交重心",
  "低端上移",
  "成交一般",
  "出货较好",
];

const gateWords = ["会员", "登录", "权限", "购买", "开通", "试看", "数据终端", "VIP", "付费"];

function storageCookies() {
  if (!fs.existsSync(STORAGE_STATE)) return "";
  const state = JSON.parse(fs.readFileSync(STORAGE_STATE, "utf8"));
  return (state.cookies || [])
    .filter((cookie) => /oilchem\.net$/.test(cookie.domain.replace(/^\./, "")) || cookie.domain.includes("oilchem.net"))
    .map((cookie) => `${cookie.name}=${cookie.value}`)
    .join("; ");
}

function cleanHtml(value) {
  return String(value || "")
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

function hits(text, words) {
  return words.filter((word) => text.includes(word));
}

function classify(text) {
  const targetHit = hits(text, targetWords);
  const gateHit = hits(text, gateWords);
  return {
    readableChars: text.length,
    targetHit,
    gateHit,
    likelyGated: gateHit.length > 0 && text.length < 3500,
  };
}

function compact(text, size = 500) {
  return String(text || "").replace(/\s+/g, " ").trim().slice(0, size);
}

function scoreItem(item) {
  const title = cleanHtml(item.title || "");
  const content = cleanHtml(item.content || "");
  let score = 0;
  if (/山东.*成品油|山东地炼.*汽柴|山东成品油日评|山东地炼汽柴油日评/.test(title)) score += 10;
  if (/成品油|汽油|柴油|地炼|地方炼厂/.test(title)) score += 5;
  score += hits(`${title} ${content}`, targetWords).length;
  return score;
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const text = await response.text();
  try {
    return { ok: response.ok, status: response.status, json: JSON.parse(text), text };
  } catch {
    return { ok: response.ok, status: response.status, json: null, text };
  }
}

async function main() {
  const cookie = storageCookies();
  const headers = {
    "User-Agent":
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
  };
  if (cookie) headers.Cookie = cookie;

  const results = [];
  for (const query of queries) {
    const url = `${SEARCH_URL}?${new URLSearchParams({
      keyword: query,
      pageNo: "1",
      pageSize: "5",
      highlightFields: "title,content",
    })}`;
    const search = await fetchJson(url, { headers });
    const items = search.json?.response?.list || [];
    const ranked = items
      .map((item) => ({
        articleId: item.articleId,
        title: cleanHtml(item.title),
        url: item.url,
        publishTime: item.publishTime ? new Date(item.publishTime).toISOString() : null,
        columnName: item.columnName,
        contentExcerpt: compact(cleanHtml(item.content), 260),
        targetHit: hits(`${cleanHtml(item.title)} ${cleanHtml(item.content)}`, targetWords),
        score: scoreItem(item),
      }))
      .sort((a, b) => b.score - a.score);

    const detailCandidate = ranked.find((item) => item.url && item.score >= 5) || ranked[0];
    let detail = null;
    if (detailCandidate?.url) {
      const detailResponse = await fetch(detailCandidate.url, { headers });
      const html = await detailResponse.text();
      const text = cleanHtml(html);
      detail = {
        status: detailResponse.status,
        url: detailCandidate.url,
        title: detailCandidate.title,
        access: classify(text),
        excerpt: compact(text, 800),
      };
    }

    results.push({
      query,
      status: search.status,
      total: search.json?.response?.total ?? null,
      topItems: ranked.slice(0, 3),
      detail,
    });
    await new Promise((resolve) => setTimeout(resolve, 1200));
  }

  const output = {
    generatedAt: new Date().toISOString(),
    storageStateUsed: Boolean(cookie),
    results,
  };
  const outPath = path.join("artifacts", "oilchem_spot_qualitative_api_probe.json");
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(output, null, 2), "utf8");
  console.log(outPath);
  console.log(
    JSON.stringify(
      results.map((item) => ({
        query: item.query,
        total: item.total,
        topTitle: item.topItems[0]?.title || "",
        topHits: item.topItems[0]?.targetHit || [],
        detailReadableChars: item.detail?.access.readableChars || 0,
        detailTargetHit: item.detail?.access.targetHit || [],
        detailGateHit: item.detail?.access.gateHit || [],
        likelyGated: item.detail?.access.likelyGated || false,
      })),
      null,
      2
    )
  );
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
