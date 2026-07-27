import http from 'k6/http';
import { check } from 'k6';
import exec from 'k6/execution';
import { Counter, Gauge, Trend } from 'k6/metrics';

const TARGET_URL = __ENV.TARGET_URL || 'http://service-a:8000';
const RPS = Number(__ENV.RPS || 10);
const WARMUP_S = Number(__ENV.WARMUP_S || 30);
const MEASURE_S = Number(__ENV.MEASURE_S || 90);
const COOLDOWN_S = Number(__ENV.COOLDOWN_S || 15);
const ITEM_COUNT = Number(__ENV.ITEM_COUNT || 5000);

const TOTAL_S = WARMUP_S + MEASURE_S + COOLDOWN_S;
// Generous headroom so the arrival-rate executor is never VU-starved;
// starvation would silently distort the measured RPS.
const MAX_VUS = Math.max(20, RPS * 4);

// Headline stats must come only from the measurement phase -- warmup ramp-up
// and cooldown drain-off otherwise contaminate p95/p99/error rate.
const measureLatency = new Trend('measure_latency', true);
const measureRequests = new Counter('measure_requests');
const measureFailed = new Counter('measure_failed');
// exec.scenario.startTime is only readable from within a VU context (inside
// default()); handleSummary runs outside one, so we smuggle it out through a
// metric. It's the same value on every VU/iteration, so any write is fine.
const scenarioStartEpochMs = new Gauge('scenario_start_epoch_ms');

export const options = {
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  scenarios: {
    experiment: {
      executor: 'constant-arrival-rate',
      rate: RPS,
      timeUnit: '1s',
      duration: `${TOTAL_S}s`,
      preAllocatedVUs: Math.max(10, Math.ceil(RPS / 2)),
      maxVUs: MAX_VUS,
    },
  },
};

function currentPhase() {
  const elapsedS = (Date.now() - exec.scenario.startTime) / 1000;
  if (elapsedS < WARMUP_S) return 'warmup';
  if (elapsedS < WARMUP_S + MEASURE_S) return 'measure';
  return 'cooldown';
}

export default function () {
  scenarioStartEpochMs.add(exec.scenario.startTime);
  const phase = currentPhase();
  const id = Math.floor(Math.random() * ITEM_COUNT) + 1;
  const res = http.get(`${TARGET_URL}/work?id=${id}`, {
    timeout: '10s',
    tags: { phase },
  });
  const ok = check(res, {
    'status is 200': (r) => r.status === 200,
  });

  if (phase === 'measure') {
    measureLatency.add(res.timings.duration);
    measureRequests.add(1);
    if (!ok) measureFailed.add(1);
  }
}

export function handleSummary(data) {
  const m = data.metrics;
  const latency = m.measure_latency ? m.measure_latency.values : {};
  const totalRequests = m.measure_requests ? m.measure_requests.values.count : 0;
  const failedRequests = m.measure_failed ? m.measure_failed.values.count : 0;
  const scenarioStart = m.scenario_start_epoch_ms ? m.scenario_start_epoch_ms.values.value : null;

  const summary = {
    run_config: {
      target_url: TARGET_URL,
      rps: RPS,
      warmup_s: WARMUP_S,
      measure_s: MEASURE_S,
      cooldown_s: COOLDOWN_S,
      total_s: TOTAL_S,
      item_count: ITEM_COUNT,
    },
    // Absolute epoch-ms boundaries of the measurement window, so downstream
    // tooling can align application-side samples to the exact same window
    // instead of re-deriving it from wall-clock guesses.
    measure_window:
      scenarioStart != null
        ? {
            start_epoch_ms: scenarioStart + WARMUP_S * 1000,
            end_epoch_ms: scenarioStart + (WARMUP_S + MEASURE_S) * 1000,
          }
        : null,
    total_requests: totalRequests,
    failed_requests: failedRequests,
    success_requests: totalRequests - failedRequests,
    error_rate: totalRequests > 0 ? failedRequests / totalRequests : null,
    throughput_rps: MEASURE_S > 0 ? totalRequests / MEASURE_S : null,
    latency_ms: {
      p50: latency['med'] ?? null,
      p95: latency['p(95)'] ?? null,
      p99: latency['p(99)'] ?? null,
      avg: latency['avg'] ?? null,
      min: latency['min'] ?? null,
      max: latency['max'] ?? null,
    },
  };

  return {
    stdout: JSON.stringify(summary, null, 2) + '\n',
    '/results/summary.json': JSON.stringify(summary, null, 2),
  };
}
