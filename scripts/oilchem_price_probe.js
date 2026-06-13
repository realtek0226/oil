const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const STORAGE_STATE = process.env.OILCHEM_STORAGE_STATE || "configs/oilchem_storage_state.json";
const OUT_PATH = path.join("artifacts", "oilchem_price_probe_result.json");
const PRICE_API = "https://dc.oilchem.net/ndc/price/list/queryPricePage";
const PRICE_API_MARK = "/ndc/price/list/queryPricePage";

const targetRegions = ["中国", "山东", "华东", "华南", "华北", "华中", "西北", "西南", "东北"];

const products = [
  {
    product: "汽油",
    productCode: "gasoline",
    channelId: 1694,
    varietiesId: 3145,
    spec: "92#",
    pageUrl: "https://dc.oilchem.net/page/#/list?channelIdNew=1694&name=%E6%B1%BD%E6%B2%B9&businessType=3",
  },
  {
    product: "柴油",
    productCode: "diesel",
    channelId: 1695,
    varietiesId: 115,
    spec: "国Ⅵ",
    pageUrl: "https://dc.oilchem.net/page/#/list?channelIdNew=1695&name=%E6%9F%B4%E6%B2%B9&businessType=3",
  },
];

function normalizeText(value) {
  return String(value || "").replace(/\s+/g, "").trim();
}

function normalizeRegion(value) {
  return String(value || "")
    .replace(/地区|省|市|自治区|回族|维吾尔|壮族/g, "")
    .replace(/-.*$/g, "")
    .trim();
}

function flattenRows(payload) {
  const body = payload?.response?.priceBodyMap || {};
  return Object.values(body).flatMap((items) => (Array.isArray(items) ? items : []));
}

function latestDateFromPayload(payload) {
  const dates = [];
  const add = (value) => {
    if (/^\d{4}\/\d{2}\/\d{2}$/.test(String(value || ""))) dates.push(String(value));
  };

  for (const item of payload?.response?.priceHeadList || []) {
    add(item.cnFiled || item.cnField || item.field || item.name || item.label);
  }
  for (const item of payload?.response?.dateList || []) add(item);

  for (const row of flattenRows(payload)) {
    for (const key of Object.keys(row)) add(key);
  }

  return dates.sort().at(-1) || null;
}

function rowMatchesProduct(row, product) {
  if (product.productCode === "gasoline") {
    return normalizeText(row.specificationsName) === "92#";
  }
  return normalizeText(row.standard).includes("国Ⅵ") || normalizeText(row.specificationsName).includes("0#");
}

function rowRegion(row) {
  for (const value of [row.internalMarketName, row.regionName, row.marketName]) {
    const region = normalizeRegion(value);
    if (targetRegions.includes(region)) return region;
  }
  return null;
}

function rowMatchesPriceType(row, region) {
  const priceType = normalizeText(row.priceTypeName);
  if (region === "山东") return priceType === "库提现汇市场价";
  return priceType === "库提现汇";
}

function selectionRank(row, region) {
  const internal = String(row.internalMarketName || "").trim();
  const regionName = normalizeRegion(row.regionName);
  if (internal === region) return 0;
  if (internal.startsWith(`${region}-`)) return 1;
  if (regionName === region) return 2;
  return 3;
}

function getPriceCell(row, latestDate) {
  const cell = latestDate ? row?.[latestDate] : null;
  if (!cell) return { price: null, riseOrFall: null };
  const priceMap = cell.price || {};
  const riseMap = cell.dataRiseOrFall || {};
  return {
    price: priceMap["主流价"] || Object.values(priceMap)[0] || null,
    riseOrFall: riseMap["主流价"] || Object.values(riseMap)[0] || null,
  };
}

function extractRows(payload, product) {
  const latestDate = latestDateFromPayload(payload);
  const selected = [];

  for (const row of flattenRows(payload)) {
    if (!rowMatchesProduct(row, product)) continue;
    const region = rowRegion(row);
    if (!region || !rowMatchesPriceType(row, region)) continue;
    const { price, riseOrFall } = getPriceCell(row, latestDate);
    selected.push({
      product: product.product,
      region,
      selection_rank: selectionRank(row, region),
      date: latestDate,
      price,
      rise_or_fall: riseOrFall,
      price_type: row.priceTypeName || "",
      standard: row.standard || "",
      specification: row.specificationsName || "",
      unit: row.unitValuationName || "",
      market: row.marketName || "",
      internal_market: row.internalMarketName || "",
      business_id: row.businessId || row.id || "",
    });
  }

  const uniqueByRegion = new Map();
  for (const row of selected) {
    const current = uniqueByRegion.get(row.region);
    if (!current || row.selection_rank < current.selection_rank) uniqueByRegion.set(row.region, row);
  }
  return targetRegions
    .map((region) => uniqueByRegion.get(region))
    .filter(Boolean)
    .map(({ selection_rank, ...row }) => row);
}

async function directPostPage(context, product, pageNum) {
  const response = await context.request.post(PRICE_API, {
    headers: {
      "content-type": "application/json;charset=UTF-8",
      origin: "https://dc.oilchem.net",
      referer: product.pageUrl,
    },
    data: {
      varietiesId: product.varietiesId,
      businessType: "3",
      twoLevelBusinessType: 0,
      timeType: 0,
      pageNum,
      pageSize: 100,
    },
    timeout: 30000,
  });
  return {
    pageNum,
    status: response.status(),
    payload: await response.json().catch(() => null),
  };
}

function mergePayloads(payloads) {
  const merged = {
    response: {
      priceHeadList: payloads.find((payload) => payload?.response?.priceHeadList)?.response?.priceHeadList || [],
      dateList: payloads.find((payload) => payload?.response?.dateList)?.response?.dateList || [],
      priceBodyMap: {},
    },
  };
  for (const payload of payloads) {
    const body = payload?.response?.priceBodyMap || {};
    for (const [key, rows] of Object.entries(body)) {
      if (!Array.isArray(rows)) continue;
      if (!merged.response.priceBodyMap[key]) merged.response.priceBodyMap[key] = [];
      merged.response.priceBodyMap[key].push(...rows);
    }
  }
  return merged;
}

async function directPost(context, product) {
  const pageAttempts = [];
  const payloads = [];
  for (const pageNum of [1, 2, 3]) {
    const attempt = await directPostPage(context, product, pageNum);
    const rowCount = attempt.payload ? flattenRows(attempt.payload).length : 0;
    pageAttempts.push({ pageNum, status: attempt.status, rowCount });
    if (rowCount > 0) payloads.push(attempt.payload);
    if (rowCount < 100) break;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }

  const payload = mergePayloads(payloads);
  const rows = extractRows(payload, product);
  return {
    method: "direct_post",
    status: pageAttempts.map((attempt) => attempt.status).join(","),
    pages: pageAttempts,
    captured: rows.length > 0,
    latestDate: payload ? latestDateFromPayload(payload) : null,
    rows,
  };
}

async function pageCapture(context, product) {
  const page = await context.newPage();
  let capturedPayload = null;

  page.on("response", async (response) => {
    if (!response.url().includes(PRICE_API_MARK)) return;
    try {
      const payload = await response.json();
      if (flattenRows(payload).length > 0) capturedPayload = payload;
    } catch (_) {
      // Ignore blocked/non-JSON responses.
    }
  });

  await page.goto(product.pageUrl, { waitUntil: "domcontentloaded", timeout: 45000 });
  await page.waitForTimeout(9000);
  const pageTextSample = await page
    .locator("body")
    .innerText({ timeout: 5000 })
    .then((text) => text.replace(/\s+/g, " ").trim().slice(0, 300))
    .catch(() => "");
  await page.close();

  const rows = capturedPayload ? extractRows(capturedPayload, product) : [];
  return {
    method: "page_capture",
    captured: rows.length > 0,
    latestDate: capturedPayload ? latestDateFromPayload(capturedPayload) : null,
    rows,
    pageTextSample,
  };
}

async function captureProduct(context, product) {
  const direct = await directPost(context, product).catch((error) => ({
    method: "direct_post",
    captured: false,
    error: String(error.message || error),
    rows: [],
  }));
  if (direct.captured) return { product: product.product, pageUrl: product.pageUrl, attempts: [direct], rows: direct.rows };

  const browserCapture = await pageCapture(context, product).catch((error) => ({
    method: "page_capture",
    captured: false,
    error: String(error.message || error),
    rows: [],
  }));
  return {
    product: product.product,
    pageUrl: product.pageUrl,
    attempts: [direct, browserCapture],
    rows: browserCapture.rows || [],
  };
}

async function main() {
  const storageState = fs.existsSync(STORAGE_STATE) ? STORAGE_STATE : undefined;
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    storageState,
    viewport: { width: 1440, height: 1000 },
    userAgent:
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0 Safari/537.36",
  });

  const results = [];
  for (const product of products) {
    results.push(await captureProduct(context, product));
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }

  await browser.close();

  const output = {
    generatedAt: new Date().toISOString(),
    storageStateUsed: Boolean(storageState),
    requestPlan: "汽油、柴油各一次价格接口探测；直接接口失败时各打开一次价格页监听页面接口；不写数据库。",
    results,
  };

  fs.mkdirSync(path.dirname(OUT_PATH), { recursive: true });
  fs.writeFileSync(OUT_PATH, JSON.stringify(output, null, 2), "utf8");

  console.log(OUT_PATH);
  console.table(results.flatMap((item) => item.rows));
  console.log(
    JSON.stringify(
      {
        storageStateUsed: output.storageStateUsed,
        summary: results.map((item) => ({
          product: item.product,
          rows: item.rows.length,
          attempts: item.attempts.map((attempt) => ({
            method: attempt.method,
            status: attempt.status,
            pages: attempt.pages,
            captured: attempt.captured,
            latestDate: attempt.latestDate,
            error: attempt.error,
          })),
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
