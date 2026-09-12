import assert from "node:assert/strict";
import test from "node:test";

const { computeCpuPercent, cpuSampleReady, mergeCpuSamples } = await import("../src/lib/docker/engine");
const { cpuPercentOfQuota } = await import("../src/lib/runtime/cpu");

const busy = {
  cpu_stats: {
    cpu_usage: { total_usage: 2_000_000_000 },
    system_cpu_usage: 16_000_000_000,
    online_cpus: 8,
  },
  precpu_stats: {
    cpu_usage: { total_usage: 1_000_000_000 },
    system_cpu_usage: 8_000_000_000,
  },
};

test("empty precpu sample is not a usable reading", () => {
  const empty = {
    cpu_stats: { cpu_usage: { total_usage: 1_000_000_000 }, system_cpu_usage: 8_000_000_000, online_cpus: 8 },
    precpu_stats: { cpu_usage: { total_usage: 0 }, system_cpu_usage: 0 },
  };
  assert.equal(cpuSampleReady(empty), false);
});

test("two Podman snapshots are merged into a real CPU delta", () => {
  const first = {
    cpu_stats: { cpu_usage: { total_usage: 1_000_000_000 }, system_cpu_usage: 8_000_000_000, online_cpus: 8 },
    precpu_stats: { cpu_usage: { total_usage: 0 }, system_cpu_usage: 0 },
  };
  const second = {
    cpu_stats: { cpu_usage: { total_usage: 2_000_000_000 }, system_cpu_usage: 16_000_000_000, online_cpus: 8 },
    precpu_stats: { cpu_usage: { total_usage: 0 }, system_cpu_usage: 0 },
  };
  const merged = mergeCpuSamples(first, second);
  assert.equal(cpuSampleReady(merged), true);
  assert.equal(computeCpuPercent(merged), 100);
});

test("Docker one-core percent of 50 on a 0.5-core plan is 100% of the quota", () => {
  assert.equal(computeCpuPercent(busy), 100);
  assert.equal(cpuPercentOfQuota(50, 500), 100);
  assert.equal(cpuPercentOfQuota(0, 500), 0);
});
