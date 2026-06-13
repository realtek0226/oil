const fs = require("fs");
const path = require("path");

const SEARCH_URL = "https://search.oilchem.net/article/search";
const STORAGE_STATE = process.env.OILCHEM_STORAGE_STATE || "configs/oilchem_storage_state.json";

const searchQueries = [
  "山东成品油日评",
  "山东地炼汽柴油日评",
  "山东独立炼厂 汽柴油 日评",
  "山东地炼 成品油 日评 出货 成交",
];

const keywordGroups = {
  low_price_resource: ["低价资源", "低价货源", "低端资源", "低端货源", "低价促销", "低位资源", "低端价格"],
  trader_grab: ["抢货", "抄底", "入市采购", "集中采购", "补货", "拿货积极", "备货"],
  trader_dump: ["抛货", "出货意愿增强", "降价出货", "让利出货", "甩货"],
  wait_and_see: ["观望", "谨慎", "按需采购", "刚需采购", "采购谨慎"],
  shipment_good: ["出货顺畅", "出货较好", "出货好转", "出货量大增", "出货尚可", "成交放量"],
  shipment_weak: ["出货承压", "出货清淡", "出货放缓", "成交清淡", "成交一般", "交投清淡"],
  sealed_or_reluctant: ["封单", "停售", "惜售", "控量", "限量", "暂停报价"],
  deal_center: ["成交重心", "低端上移", "低端回落", "高端上移", "高端回落", "商谈重心"],
  refinery_raise: ["炼厂推涨", "价格推涨", "上调", "涨价", "挺价"],
  refinery_cut: ["下调", "跌价", "降价", "价格下跌", "让利"],
};

function storageCookies() {
  if (!fs.existsSync(STORAGE_STATE)) return "";
  const state = JSON.parse(fs.readFileSync(STORAGE_STATE, "utf8"));
  return (state.cookies || [])
    .filter((cookie) => cookie.domain.includes("oilchem.net"))
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

function compact(value, limit = 700) {
  return String(value || "").replace(/\s+/g, " ").trim().slice(0, limit);
}

function extractMainText(text) {
  const startMarkers = ["今日摘要", "市场摘要", "山东地炼价格", "山东独立炼厂汽油均价", "当前位置："];
  const endMarkers = ["免责声明", "最新文章", "版权声明", "相关资讯"];
  let start = -1;
  for (const marker of startMarkers) {
    const index = text.indexOf(marker);
    if (index >= 0) {
      start = start < 0 ? index : Math.min(start, index);
    }
  }
  let main = start >= 0 ? text.slice(start) : text;
  let end = -1;
  for (const marker of endMarkers) {
    const index = main.indexOf(marker);
    if (index >= 0) {
      end = end < 0 ? index : Math.min(end, index);
    }
  }
  if (end >= 0) main = main.slice(0, end);
  return main.trim();
}

function classifyArticle(item) {
  const title = cleanHtml(item.title || "");
  const content = cleanHtml(item.content || "");
  let score = 0;
  if (/山东成品油日评|山东地炼汽柴油日评/.test(title)) score += 30;
  if (/山东.*地炼|山东.*成品油|独立炼厂/.test(title)) score += 12;
  if (/汽油|柴油|汽柴|成品油|地炼/.test(title)) score += 8;
  if (/日评|日报|市场/.test(title)) score += 5;
  if (/石油焦|甲苯|原油|沥青|船燃|轻循环油/.test(title) && !/汽柴|成品油|地炼/.test(title)) score -= 12;
  for (const words of Object.values(keywordGroups)) {
    for (const word of words) {
      if (`${title} ${content}`.includes(word)) score += 1;
    }
  }
  return score;
}

function extractHits(text) {
  const result = {};
  for (const [field, words] of Object.entries(keywordGroups)) {
    const hits = words.filter((word) => text.includes(word));
    result[field] = hits;
  }
  return result;
}

function windowsAroundHits(text, words, limit = 6) {
  const snippets = [];
  for (const word of words) {
    let index = text.indexOf(word);
    while (index >= 0 && snippets.length < limit) {
      snippets.push({
        keyword: word,
        text: compact(text.slice(Math.max(0, index - 90), Math.min(text.length, index + 180)), 320),
      });
      index = text.indexOf(word, index + word.length);
    }
  }
  return snippets;
}

function inferLabels(hitMap) {
  const trader =
    hitMap.trader_grab.length > 0
      ? "抢货/补货"
      : hitMap.trader_dump.length > 0
        ? "抛货/让利"
        : hitMap.wait_and_see.length > 0
          ? "观望/刚需"
          : "未识别";
  const shipment =
    hitMap.shipment_good.length > 0
      ? "出货偏强"
      : hitMap.shipment_weak.length > 0
        ? "出货偏弱"
        : "未识别";
  const lowPrice =
    hitMap.low_price_resource.length > 0
      ? "出现低价资源/低价促销线索"
      : "未识别";
  const sealed =
    hitMap.sealed_or_reluctant.length > 0
      ? "出现封单/惜售/控量线索"
      : "未识别";
  return { trader, shipment, lowPrice, sealed };
}

async function fetchJson(url, headers) {
  const response = await fetch(url, { headers });
  const text = await response.text();
  return { status: response.status, json: JSON.parse(text) };
}

async function main() {
  const cookie = storageCookies();
  const headers = {
    "User-Agent":
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
  };
  if (cookie) headers.Cookie = cookie;

  const seen = new Map();
  for (const keyword of searchQueries) {
    const url = `${SEARCH_URL}?${new URLSearchParams({
      keyword,
      pageNo: "1",
      pageSize: "10",
      highlightFields: "title,content",
    })}`;
    const payload = await fetchJson(url, headers);
    for (const item of payload.json?.response?.list || []) {
      if (!item.url) continue;
      const score = classifyArticle(item);
      const existing = seen.get(item.url);
      if (!existing || score > existing.score) {
        seen.set(item.url, {
          articleId: item.articleId,
          title: cleanHtml(item.title),
          url: item.url,
          publishTime: item.publishTime ? new Date(item.publishTime).toISOString() : null,
          columnName: item.columnName,
          searchContentExcerpt: compact(cleanHtml(item.content), 300),
          score,
        });
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 900));
  }

  const candidates = [...seen.values()]
    .filter((item) => item.score >= 20)
    .sort((a, b) => {
      const timeDelta = Date.parse(b.publishTime || 0) - Date.parse(a.publishTime || 0);
      return timeDelta || b.score - a.score;
    })
    .slice(0, 5);

  const allWords = [...new Set(Object.values(keywordGroups).flat())];
  const articles = [];
  for (const candidate of candidates) {
    const response = await fetch(candidate.url, { headers });
    const html = await response.text();
    const rawText = cleanHtml(html);
    const text = extractMainText(rawText);
    const hitMap = extractHits(text);
    articles.push({
      ...candidate,
      detailStatus: response.status,
      readableChars: text.length,
      likelyMemberReadable: Boolean(cookie) && text.length > 3000,
      inferredLabels: inferLabels(hitMap),
      hitMap,
      snippets: windowsAroundHits(text, allWords, 10),
    });
    await new Promise((resolve) => setTimeout(resolve, 1200));
  }

  const fieldCoverage = {};
  for (const field of Object.keys(keywordGroups)) {
    fieldCoverage[field] = articles.filter((article) => article.hitMap[field]?.length).length;
  }

  const output = {
    generatedAt: new Date().toISOString(),
    storageStateUsed: Boolean(cookie),
    candidateCount: candidates.length,
    fieldCoverage,
    articles,
  };
  const outPath = path.join("artifacts", "oilchem_spot_daily_round.json");
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(output, null, 2), "utf8");

  console.log(outPath);
  console.log(
    JSON.stringify(
      {
        storageStateUsed: output.storageStateUsed,
        candidateCount: output.candidateCount,
        fieldCoverage,
        articles: articles.map((article) => ({
          title: article.title,
          publishTime: article.publishTime,
          readableChars: article.readableChars,
          labels: article.inferredLabels,
          hitFields: Object.fromEntries(
            Object.entries(article.hitMap)
              .filter(([, value]) => value.length)
              .map(([key, value]) => [key, value])
          ),
        })),
      },
      null,
      2
    )
  );
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
