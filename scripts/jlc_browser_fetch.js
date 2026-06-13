const fs = require('fs');
const os = require('os');
const path = require('path');
const { chromium } = require('playwright');

const LIVE_HOT_URL = 'https://oil.315i.com/cmlc/001002-jdxw-hy';
const ARCHIVE_FIRST_PAGE_URL = 'https://oil.315i.com/cmlc/Nav-001002001-qcy';
const ARCHIVE_PAGE_URL = (pageIndex) =>
  `https://oil.315i.com/common/goArticleList?pageIndex=${pageIndex}&productIds=001002&columnIds=001007,001009,001015,001016&clickable=1&type=1&pageId=41&staticUrls=http://oil.315i.com&`;

function getArg(name, fallback) {
  const index = process.argv.indexOf(`--${name}`);
  if (index === -1 || index + 1 >= process.argv.length) {
    return fallback;
  }
  return process.argv[index + 1];
}

function getBooleanArg(name, fallback = false) {
  const value = getArg(name, fallback ? 'true' : 'false');
  return String(value).toLowerCase() === 'true';
}

function findChromiumExecutable() {
  const envPath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
  if (envPath && fs.existsSync(envPath)) {
    return envPath;
  }

  const root = path.join(os.homedir(), 'AppData', 'Local', 'ms-playwright');
  if (!fs.existsSync(root)) {
    return null;
  }

  const candidates = fs
    .readdirSync(root, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && entry.name.startsWith('chromium-'))
    .map((entry) => path.join(root, entry.name, 'chrome-win64', 'chrome.exe'))
    .filter((candidate) => fs.existsSync(candidate))
    .sort()
    .reverse();

  return candidates[0] || null;
}

function cleanText(value) {
  return String(value || '').replace(/\s+/g, ' ').trim();
}

function buildDirectionHint(text) {
  const positiveKeywords = ['上调', '上涨', '推涨', '挺价', '支撑', '偏强', '去库', '检修', '停工'];
  const negativeKeywords = ['下调', '下跌', '回落', '承压', '促销', '宽松', '累库', '疲弱', '下行'];
  let positive = 0;
  let negative = 0;
  for (const keyword of positiveKeywords) {
    if (text.includes(keyword)) {
      positive += 1;
    }
  }
  for (const keyword of negativeKeywords) {
    if (text.includes(keyword)) {
      negative += 1;
    }
  }
  if (positive > negative) {
    return { directionHint: 'bullish_refined', majorScore: Math.min(positive - negative, 5) };
  }
  if (negative > positive) {
    return { directionHint: 'bearish_refined', majorScore: Math.min(negative - positive, 5) };
  }
  return { directionHint: 'flat_refined', majorScore: 0 };
}

function scoreTitle(title) {
  let score = 0;
  if (title.includes('山东')) score += 12;
  if (title.includes('地炼')) score += 10;
  if (title.includes('汽柴油')) score += 8;
  if (title.includes('成品油')) score += 8;
  if (title.includes('市场概况')) score += 6;
  if (title.includes('价格汇总表')) score += 6;
  if (title.includes('价格快报')) score += 5;
  if (title.includes('批发价格明细表')) score += 4;
  if (title.includes('船单报价')) score += 4;
  if (title.includes('主营')) score += 3;
  return score;
}

function isRelevantTitle(title) {
  const requiredTokens = [
    '汽柴油',
    '成品油',
    '汽油',
    '柴油',
    '地炼',
    '主营',
    '价格汇总表',
    '价格快报',
    '市场概况',
    '船单报价',
  ];
  return requiredTokens.some((token) => title.includes(token));
}

function normalizeHotItem(title, url) {
  const cleanTitle = cleanText(title);
  const cleanUrl = cleanText(url);
  const { directionHint, majorScore } = buildDirectionHint(cleanTitle);
  return {
    headline: cleanTitle,
    title: cleanTitle,
    url: cleanUrl,
    source: 'jlc_refinedoil_hot_browser',
    section_name: '金联创-即时资讯24小时热点',
    priority_score: scoreTitle(cleanTitle),
    direction_hint: directionHint,
    major_score: majorScore,
  };
}

function normalizeArchiveItem(item) {
  const title = cleanText(item.title);
  const { directionHint, majorScore } = buildDirectionHint(title);
  return {
    headline: title,
    title,
    url: cleanText(item.url),
    source: 'jlc_refinedoil_archive_browser',
    section_name: '金联创-汽柴油归档标题',
    publish_date: cleanText(item.publish_date),
    publish_time: `${cleanText(item.publish_date)} 08:00`,
    priority_score: scoreTitle(title),
    direction_hint: directionHint,
    major_score: majorScore,
  };
}

async function bypassCaptchaIfNeeded(page) {
  const title = await page.title();
  if (!title.includes('安全验证')) {
    return { captchaPresent: false, bypassSuccess: true };
  }

  const payload = await page.evaluate(async () => {
    if (!window.captcha) {
      return { ok: false, reason: 'captcha_missing' };
    }
    const redirect = window.location.href;
    const response = await fetch(
      'https://www.315i.com/captcha/verify?redirect=' + encodeURIComponent(redirect),
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        cache: 'no-cache',
        body: JSON.stringify({ datas: [0, 1, 0, 2, 1, 3, 1] }),
      }
    );
    const body = await response.json();
    return { ok: response.ok, body };
  });

  if (!payload.ok || !payload.body || payload.body.code !== 200 || !payload.body.redirect) {
    return { captchaPresent: true, bypassSuccess: false, payload };
  }

  await page.goto(payload.body.redirect, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(350);
  return { captchaPresent: true, bypassSuccess: !(await page.title()).includes('安全验证'), payload };
}

async function fetchHotItems(page, limit) {
  await page.goto(LIVE_HOT_URL, { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForTimeout(2500);

  const rawItems = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('a[href]'))
      .map((anchor) => ({
        title: (anchor.textContent || '').replace(/\s+/g, ' ').trim(),
        url: anchor.href,
      }))
      .filter((item) => item.title && item.url.includes('/infodetail/infodetail?') && item.url.includes('columnId=jyd'));
  });

  const seen = new Set();
  const items = [];
  for (const item of rawItems) {
    const normalized = normalizeHotItem(item.title, item.url);
    const key = `${normalized.title}||${normalized.url}`;
    if (!normalized.title || !normalized.url || seen.has(key)) {
      continue;
    }
    seen.add(key);
    items.push(normalized);
  }

  items.sort((left, right) => {
    if (right.priority_score !== left.priority_score) {
      return right.priority_score - left.priority_score;
    }
    return left.title.localeCompare(right.title, 'zh-CN');
  });
  return items.slice(0, limit);
}

async function extractArchiveItems(page) {
  return page.evaluate(() => {
    return Array.from(document.querySelectorAll('ul.list.list14time li'))
      .map((listing) => {
        const dateNode = listing.querySelector('span.fr');
        const anchors = Array.from(listing.querySelectorAll('a[href]')).filter(
          (anchor) => anchor.href && !anchor.href.startsWith('javascript:')
        );
        const anchor = anchors[anchors.length - 1];
        if (!dateNode || !anchor) {
          return null;
        }
        return {
          publish_date: (dateNode.textContent || '').replace(/\s+/g, ' ').trim(),
          title: (anchor.textContent || '').replace(/\s+/g, ' ').trim(),
          url: anchor.href,
        };
      })
      .filter(Boolean);
  });
}

async function fetchArchiveItems(page, startDate, endDate, maxPages, itemLimit) {
  const seen = new Set();
  const items = [];
  const pageDebug = [];

  for (let pageIndex = 1; pageIndex <= maxPages; pageIndex += 1) {
    const url = pageIndex === 1 ? ARCHIVE_FIRST_PAGE_URL : ARCHIVE_PAGE_URL(pageIndex);
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
    await page.waitForTimeout(350);
    const bypass = await bypassCaptchaIfNeeded(page);
    const currentTitle = await page.title();
    if (!bypass.bypassSuccess) {
      pageDebug.push({ pageIndex, url, title: currentTitle, bypassSuccess: false });
      break;
    }

    const pageItems = await extractArchiveItems(page);
    if (!pageItems.length) {
      pageDebug.push({ pageIndex, url, title: currentTitle, bypassSuccess: true, itemCount: 0 });
      break;
    }

    pageDebug.push({
      pageIndex,
      url,
      title: currentTitle,
      bypassSuccess: true,
      itemCount: pageItems.length,
      firstDate: pageItems[0].publish_date,
      lastDate: pageItems[pageItems.length - 1].publish_date,
    });

    let oldestDate = null;
    for (const item of pageItems) {
      const normalized = normalizeArchiveItem(item);
      if (!isRelevantTitle(normalized.title)) {
        continue;
      }

      const publishDate = normalized.publish_date.slice(0, 10);
      if (!publishDate) {
        continue;
      }
      oldestDate = oldestDate ? (publishDate < oldestDate ? publishDate : oldestDate) : publishDate;
      if (publishDate < startDate || publishDate > endDate) {
        continue;
      }

      const key = `${normalized.title}||${normalized.url}`;
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      items.push(normalized);
      if (items.length >= itemLimit) {
        break;
      }
    }

    if (items.length >= itemLimit) {
      break;
    }
    if (oldestDate && oldestDate < startDate) {
      break;
    }
  }

  items.sort((left, right) => {
    if (left.publish_date !== right.publish_date) {
      return right.publish_date.localeCompare(left.publish_date, 'zh-CN');
    }
    if (right.priority_score !== left.priority_score) {
      return right.priority_score - left.priority_score;
    }
    return left.title.localeCompare(right.title, 'zh-CN');
  });

  return { items: items.slice(0, itemLimit), pageDebug };
}

async function probeDetail(page, url) {
  const result = {
    requested_url: url,
    captcha_present: false,
    bypass_success: false,
    login_required: false,
    content_unlocked: false,
    title: null,
  };

  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(1200);
  const bypass = await bypassCaptchaIfNeeded(page);
  result.captcha_present = bypass.captchaPresent;
  result.bypass_success = bypass.bypassSuccess;
  result.title = await page.title();

  const bodyText = await page.evaluate(() => document.body.innerText || '');
  result.login_required = bodyText.includes('请您登录') || bodyText.includes('注册即可免费浏览');
  result.content_unlocked = result.bypass_success && !result.login_required && bodyText.length > 1000;
  return result;
}

async function main() {
  const mode = getArg('mode', 'live');
  const limit = Number.parseInt(getArg('limit', '12'), 10);
  const itemLimit = Number.parseInt(getArg('item-limit', '200'), 10);
  const maxPages = Number.parseInt(getArg('max-pages', '20'), 10);
  const startDate = cleanText(getArg('start-date', '1900-01-01'));
  const endDate = cleanText(getArg('end-date', '2999-12-31'));
  const probeFirstDetail = getBooleanArg('probe-detail', false);
  const executablePath = findChromiumExecutable();

  const browser = await chromium.launch(
    executablePath ? { headless: true, executablePath } : { headless: true }
  );

  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 2000 } });

    if (mode === 'archive') {
      const archiveResult = await fetchArchiveItems(
        page,
        startDate,
        endDate,
        Number.isNaN(maxPages) ? 20 : maxPages,
        Number.isNaN(itemLimit) ? 200 : itemLimit
      );
      process.stdout.write(
        JSON.stringify(
          {
            ok: true,
            mode,
            source: 'jlc_refinedoil_archive_browser',
            generated_at: new Date().toISOString(),
            items: archiveResult.items,
            meta: {
              archive_first_page_url: ARCHIVE_FIRST_PAGE_URL,
              executable_path: executablePath,
              page_debug: archiveResult.pageDebug,
            },
          },
          null,
          2
        )
      );
      return;
    }

    const items = await fetchHotItems(page, Number.isNaN(limit) ? 12 : limit);
    let detailProbe = null;
    if (probeFirstDetail && items.length > 0) {
      detailProbe = await probeDetail(page, items[0].url);
    }

    process.stdout.write(
      JSON.stringify(
        {
          ok: true,
          mode,
          source: 'jlc_refinedoil_hot_browser',
          generated_at: new Date().toISOString(),
          items,
          detail_probe: detailProbe,
          meta: {
            list_url: LIVE_HOT_URL,
            executable_path: executablePath,
          },
        },
        null,
        2
      )
    );
  } finally {
    await browser.close();
  }
}

main().catch((error) => {
  process.stderr.write(`${error.stack || String(error)}\n`);
  process.exit(1);
});
