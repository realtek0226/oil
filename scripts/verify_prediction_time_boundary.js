const BASE_URL = process.env.OIL_RESEARCH_BASE_URL || "http://127.0.0.1:8036";
const USERNAME = process.env.OIL_RESEARCH_USERNAME || "admin";
const PASSWORD = process.env.OIL_RESEARCH_PASSWORD || "CHANGE_ME";

const REQUEST_BODY = {
  horizons: ["D1", "D3", "W1", "M1"],
  use_llm_explainer: false,
  enable_refined_news: true,
  enable_event_risk: true,
  persist_run: false,
};

const HORIZON_STEPS = {
  D1: 1,
  D3: 3,
  W1: 5,
  M1: 20,
};

async function postJson(url, body, cookie) {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(cookie ? { Cookie: cookie } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}: ${await response.text()}`);
  }
  return response;
}

async function login() {
  const response = await postJson(`${BASE_URL}/api/v1/auth/login`, {
    username: USERNAME,
    password: PASSWORD,
    remember_me: false,
  });
  const setCookie = response.headers.get("set-cookie");
  if (!setCookie) {
    throw new Error("Login response did not include a session cookie.");
  }
  return setCookie.split(";")[0];
}

function parseYmd(value) {
  const [year, month, day] = String(value || "").split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day));
}

function formatYmd(date) {
  return date.toISOString().slice(0, 10);
}

function addBusinessDays(value, steps) {
  const date = parseYmd(value);
  let remaining = Number(steps || 0);
  while (remaining > 0) {
    date.setUTCDate(date.getUTCDate() + 1);
    const day = date.getUTCDay();
    if (day !== 0 && day !== 6) remaining -= 1;
  }
  return formatYmd(date);
}

function inspectPrediction(prediction) {
  const raw = prediction.raw_context || {};
  const horizon = prediction.horizon;
  const expectedCutoff = `${prediction.as_of_date}T07:00:00`;
  const expectedTarget = addBusinessDays(prediction.as_of_date, HORIZON_STEPS[horizon]);
  const failures = [];

  for (const key of ["prediction_news_cutoff", "refined_news_cutoff", "event_news_cutoff"]) {
    if (raw[key] !== expectedCutoff) {
      failures.push(`${key} should be ${expectedCutoff}, got ${raw[key] || "missing"}`);
    }
  }

  if (prediction.target_date !== expectedTarget) {
    failures.push(`target_date should be ${expectedTarget}, got ${prediction.target_date || "missing"}`);
  }

  const brentBasis = raw.brent_forecast_basis || {};
  if (!brentBasis.forecast_source) {
    failures.push("brent_forecast_basis.forecast_source is missing");
  }
  if (horizon === "D1" && brentBasis.scorecard_change_source === "daily_point_minus_realtime") {
    failures.push("D1 Brent scorecard change must not use realtime price as the anchor");
  }

  return {
    horizon,
    as_of_date: prediction.as_of_date,
    target_date: prediction.target_date,
    expected_target_date: expectedTarget,
    cutoff: expectedCutoff,
    prediction_news_cutoff: raw.prediction_news_cutoff,
    refined_news_cutoff: raw.refined_news_cutoff,
    event_news_cutoff: raw.event_news_cutoff,
    refined_news_count: raw.refined_news_count,
    event_news_count: raw.event_news_count,
    brent_forecast_source: brentBasis.forecast_source,
    brent_change_source: brentBasis.scorecard_change_source,
    failures,
  };
}

async function run() {
  const cookie = await login();
  const response = await postJson(`${BASE_URL}/api/v1/dashboard/shandong-gasoline-92`, REQUEST_BODY, cookie);
  const payload = await response.json();
  const results = (payload.outright_predictions || []).map(inspectPrediction);
  const failures = results.flatMap((item) => item.failures.map((failure) => `${item.horizon}: ${failure}`));

  console.log(JSON.stringify({ base_url: BASE_URL, as_of_date: payload.as_of_date, results, failures }, null, 2));
  if (failures.length) {
    process.exitCode = 1;
  }
}

run().catch((error) => {
  console.error(error.message || error);
  process.exitCode = 1;
});
