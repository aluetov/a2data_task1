import http from "k6/http";
import exec from "k6/execution";
import { check } from "k6";
import { Counter } from "k6/metrics";

const baseUrl = (__ENV.BASE_URL || "http://localhost:8000").replace(/\/$/, "");
const duration = __ENV.DURATION || "30s";
const virtualUsers = Number.parseInt(__ENV.VUS || "50", 10);
const clientsPerVu = Number.parseInt(__ENV.CLIENTS_PER_VU || "100", 10);
const warmupDuration = __ENV.WARMUP_DURATION || "5s";
const runId = __ENV.RUN_ID || String(Date.now());

const allowedResponses = new Counter("allowed_responses");
const deniedResponses = new Counter("denied_responses");
const validationErrors = new Counter("response_validation_errors");

export const options = {
  scenarios: {
    warmup: {
      executor: "constant-vus",
      exec: "exerciseLimiter",
      vus: Math.min(virtualUsers, 10),
      duration: warmupDuration,
      gracefulStop: "0s",
      tags: { phase: "warmup" },
    },
    measured: {
      executor: "constant-vus",
      exec: "exerciseLimiter",
      vus: virtualUsers,
      duration,
      startTime: warmupDuration,
      gracefulStop: "5s",
      tags: { phase: "measured" },
    },
  },
  thresholds: {
    "checks{phase:measured}": ["rate==1"],
    "http_req_failed{phase:measured}": ["rate==0"],
    "http_req_duration{phase:measured}": ["p(95)<1000"],
    "http_reqs{phase:measured}": ["rate>0"],
    response_validation_errors: ["count==0"],
  },
  summaryTrendStats: ["avg", "min", "med", "max", "p(90)", "p(95)", "p(99)"],
};

export function exerciseLimiter() {
  const phase = exec.scenario.name;
  const clientNumber = exec.scenario.iterationInInstance % clientsPerVu;
  const clientId = `load_${runId}_${phase}_${exec.vu.idInTest}_${clientNumber}`;
  const response = http.post(
    `${baseUrl}/check`,
    JSON.stringify({ client_id: clientId }),
    {
      headers: { "Content-Type": "application/json" },
      tags: { phase },
    },
  );

  let payload = null;
  try {
    payload = response.json();
  } catch (_error) {
    payload = null;
  }

  const validContract =
    payload !== null &&
    typeof payload.allowed === "boolean" &&
    Number.isInteger(payload.remaining) &&
    Number.isInteger(payload.reset_at);

  const valid = check(
    response,
    {
      "status is 200": (result) => result.status === 200,
      "response contract is valid": () => validContract,
    },
    { phase },
  );

  if (phase !== "measured") {
    return;
  }

  if (!valid) {
    validationErrors.add(1);
  } else if (payload.allowed) {
    allowedResponses.add(1);
  } else {
    deniedResponses.add(1);
  }
}
