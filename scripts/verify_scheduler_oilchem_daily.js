const BASE_URL = process.env.OIL_RESEARCH_BASE_URL || "http://127.0.0.1:8036";
const USERNAME = process.env.OIL_RESEARCH_USERNAME || "admin";
const PASSWORD = process.env.OIL_RESEARCH_PASSWORD || "CHANGE_ME";

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}: ${await response.text()}`);
  }
  return response;
}

async function login() {
  const response = await requestJson(`${BASE_URL}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username: USERNAME,
      password: PASSWORD,
      remember_me: false,
    }),
  });
  const setCookie = response.headers.get("set-cookie");
  if (!setCookie) throw new Error("Login response did not include a session cookie.");
  return setCookie.split(";")[0];
}

function findJob(payload, key) {
  return (payload.jobs || []).find((job) => job.job_key === key);
}

function assertJob(condition, message, failures) {
  if (!condition) failures.push(message);
}

async function run() {
  const cookie = await login();
  const response = await requestJson(`${BASE_URL}/api/v1/system/scheduler`, {
    headers: { Cookie: cookie },
  });
  const payload = await response.json();
  const oilchemSpot = findJob(payload, "oilchem_spot_report_fetch");
  const oilchemDaily = findJob(payload, "oilchem_daily_fetch");
  const policyEvent = findJob(payload, "policy_event_refresh");
  const failures = [];

  assertJob(Boolean(payload.enabled), "scheduler is disabled", failures);
  assertJob(Boolean(oilchemSpot), "oilchem_spot_report_fetch job is missing", failures);
  assertJob(oilchemSpot?.enabled === true, "oilchem_spot_report_fetch is not enabled", failures);
  assertJob(oilchemSpot?.mode === "daily", "oilchem_spot_report_fetch is not daily", failures);
  assertJob(oilchemSpot?.schedule_value === "06:00", "oilchem_spot_report_fetch is not scheduled at 06:00", failures);
  assertJob(Boolean(oilchemDaily), "oilchem_daily_fetch job is missing", failures);
  assertJob(oilchemDaily?.enabled === false, "oilchem_daily_fetch should remain disabled", failures);
  assertJob(Boolean(policyEvent), "policy_event_refresh job is missing", failures);
  assertJob(policyEvent?.enabled === true, "policy_event_refresh is not enabled", failures);
  assertJob(policyEvent?.schedule_value === "300秒", "policy_event_refresh is not scheduled every 300 seconds", failures);

  console.log(
    JSON.stringify(
      {
        base_url: BASE_URL,
        enabled: payload.enabled,
        timezone: payload.timezone,
        checked_jobs: {
          oilchem_spot_report_fetch: oilchemSpot,
          oilchem_daily_fetch: oilchemDaily,
          policy_event_refresh: policyEvent,
        },
        failures,
      },
      null,
      2
    )
  );

  if (failures.length) process.exitCode = 1;
}

run().catch((error) => {
  console.error(error.message || error);
  process.exitCode = 1;
});
