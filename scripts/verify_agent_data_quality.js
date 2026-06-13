const BASE_URL = process.env.OIL_RESEARCH_BASE_URL || "http://127.0.0.1:8036";
const USERNAME = process.env.OIL_RESEARCH_USERNAME || "admin";
const PASSWORD = process.env.OIL_RESEARCH_PASSWORD || "CHANGE_ME";

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
  if (!setCookie) throw new Error("Login response did not include a session cookie.");
  return setCookie.split(";")[0];
}

function validateDataQuality(claim) {
  const quality = claim.structured_payload?.data_quality;
  const failures = [];
  if (!quality || typeof quality !== "object") {
    failures.push("missing data_quality object");
    return failures;
  }
  if (typeof quality.available_count !== "number") failures.push("available_count is not numeric");
  if (typeof quality.missing_count !== "number") failures.push("missing_count is not numeric");
  if (typeof quality.coverage_ratio !== "number") failures.push("coverage_ratio is not numeric");
  if (!Array.isArray(quality.missing_fields)) failures.push("missing_fields is not an array");
  if (quality.missing_count > 0 && !quality.missing_fields.length) {
    failures.push("missing_count > 0 but missing_fields is empty");
  }
  if (quality.missing_count > 0 && !String(quality.note || "").includes("按0分")) {
    failures.push("missing field note does not state zero-score handling");
  }
  return failures;
}

async function run() {
  const cookie = await login();
  const response = await postJson(
    `${BASE_URL}/api/v1/dashboard/shandong-gasoline-92`,
    {
      horizon: "D1",
      horizons: ["D1", "D3", "W1", "M1"],
      use_llm_explainer: false,
      enable_refined_news: true,
      enable_event_risk: true,
      persist_run: false,
    },
    cookie
  );
  const payload = await response.json();
  const predictions = payload.outright_predictions || [];
  const summary = predictions.flatMap((prediction) => {
    const claims = prediction.agent_claims || [];
    const ruleClaims = claims.filter((claim) => !String(claim.agent_name || "").startsWith("llm_"));
    return ruleClaims.map((claim) => {
      const quality = claim.structured_payload?.data_quality || {};
      return {
        horizon: prediction.horizon,
        agent_name: claim.agent_name,
        available_count: quality.available_count,
        missing_count: quality.missing_count,
        coverage_ratio: quality.coverage_ratio,
        missing_fields: quality.missing_fields || [],
        failures: validateDataQuality(claim),
      };
    });
  });
  const failures = summary.filter((item) => item.failures.length);
  console.log(
    JSON.stringify(
      {
        base_url: BASE_URL,
        as_of_date: payload.as_of_date,
        checked_horizons: predictions.map((prediction) => prediction.horizon),
        checked_agent_outputs: summary.length,
        summary,
        failures,
      },
      null,
      2
    )
  );
  if (!summary.length || failures.length) {
    process.exitCode = 1;
  }
}

run().catch((error) => {
  console.error(error.message || error);
  process.exitCode = 1;
});
