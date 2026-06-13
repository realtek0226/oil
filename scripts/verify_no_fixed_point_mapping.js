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

function inspectPrediction(prediction) {
  const pointMapping = prediction.raw_context?.point_mapping || {};
  const failures = [];
  if (pointMapping.method !== "historical_bucket_distribution_mapping") {
    failures.push(`point_mapping.method should be historical_bucket_distribution_mapping, got ${pointMapping.method || "missing"}`);
  }
  for (const forbiddenKey of ["intercept", "slope", "horizon_multiplier"]) {
    if (Object.prototype.hasOwnProperty.call(pointMapping, forbiddenKey)) {
      failures.push(`point_mapping exposes ${forbiddenKey}`);
    }
  }
  if (pointMapping.method === "expert_prior_fixed_point_mapping") {
    failures.push("point_mapping.method is expert_prior_fixed_point_mapping");
  }
  if (String(pointMapping.formula || "").includes("horizon_multiplier")) {
    failures.push("point_mapping.formula mentions horizon_multiplier");
  }
  if (String(pointMapping.formula || "").includes("intercept") || String(pointMapping.formula || "").includes("slope")) {
    failures.push("point_mapping.formula mentions linear calibration");
  }
  return {
    horizon: prediction.horizon,
    method: pointMapping.method,
    status: pointMapping.status,
    bucket: pointMapping.bucket,
    sample_size: pointMapping.sample_size,
    predicted_delta: pointMapping.predicted_delta,
    range_half_width: pointMapping.range_half_width,
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
