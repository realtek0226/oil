const BASE_URL = process.env.OIL_RESEARCH_BASE_URL || "http://127.0.0.1:8036";
const USERNAME = process.env.OIL_RESEARCH_USERNAME || "admin";
const PASSWORD = process.env.OIL_RESEARCH_PASSWORD || "CHANGE_ME";

const REQUEST_BODY = {
  horizon: "D1",
  horizons: ["D1", "D3", "W1", "M1"],
  use_llm_explainer: false,
  enable_refined_news: true,
  enable_event_risk: true,
  persist_run: false,
};

function pickPredictionFields(payload) {
  return (payload.outright_predictions || []).map((prediction) => ({
    horizon: prediction.horizon,
    point_value: prediction.point_value,
    range_lower: prediction.range_lower,
    range_upper: prediction.range_upper,
    score_value: prediction.score_value,
    confidence_score: prediction.confidence_score,
    direction_label: prediction.direction_label,
    input_hash: prediction.raw_context?.input_hash,
  }));
}

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

function diffPredictions(first, second) {
  const diffs = [];
  const length = Math.max(first.length, second.length);
  for (let index = 0; index < length; index += 1) {
    const left = first[index];
    const right = second[index];
    if (JSON.stringify(left) !== JSON.stringify(right)) {
      diffs.push({ first: left, second: right });
    }
  }
  return diffs;
}

async function run() {
  const cookie = await login();
  const firstResponse = await postJson(`${BASE_URL}/api/v1/dashboard/shandong-gasoline-92`, REQUEST_BODY, cookie);
  const firstPayload = await firstResponse.json();
  const secondResponse = await postJson(`${BASE_URL}/api/v1/dashboard/shandong-gasoline-92`, REQUEST_BODY, cookie);
  const secondPayload = await secondResponse.json();

  const first = pickPredictionFields(firstPayload);
  const second = pickPredictionFields(secondPayload);
  const diffs = diffPredictions(first, second);
  const result = {
    base_url: BASE_URL,
    as_of_date: firstPayload.as_of_date,
    checked_fields: Object.keys(first[0] || {}),
    first,
    second,
    diffs,
  };

  console.log(JSON.stringify(result, null, 2));
  if (diffs.length) {
    process.exitCode = 1;
  }
}

run().catch((error) => {
  console.error(error.message || error);
  process.exitCode = 1;
});
