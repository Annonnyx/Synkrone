import assert from "node:assert/strict";
import test from "node:test";

const {
  computeCpuPercent,
  cpuSampleReady,
  mergeCpuSamples,
  parseStatFrames,
  resolveCachedCpuSample,
  clearCpuSampleCache,
  wallDeltaNs,
} = await import("../src/lib/docker/engine");
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

test("Podman without system_cpu_usage uses the wall-clock interval", () => {
  const first = {
    read: "2026-09-13T10:00:00.000Z",
    cpu_stats: { cpu_usage: { total_usage: 1_000_000_000 }, online_cpus: 1 },
    precpu_stats: { cpu_usage: { total_usage: 0 }, system_cpu_usage: 0 },
  };
  const second = {
    read: "2026-09-13T10:00:00.350Z",
    cpu_stats: { cpu_usage: { total_usage: 1_350_000_000 }, online_cpus: 1 },
    precpu_stats: { cpu_usage: { total_usage: 0 }, system_cpu_usage: 0 },
  };
  const merged = mergeCpuSamples(first, second);
  assert.equal(cpuSampleReady(merged), true);
  assert.equal(Math.round(computeCpuPercent(merged)), 100);
});

test("wall-clock wins over a host online_cpus inflation", () => {
  const sample = {
    read: "2026-09-13T10:00:01.000Z",
    preread: "2026-09-13T10:00:00.000Z",
    cpu_stats: {
      cpu_usage: { total_usage: 1_500_000_000 },
      system_cpu_usage: 16_000_000_000,
      online_cpus: 32,
    },
    precpu_stats: {
      cpu_usage: { total_usage: 1_000_000_000 },
      system_cpu_usage: 8_000_000_000,
    },
  };
  assert.equal(Math.round(computeCpuPercent(sample)), 50);
});

test("a later poll reuses the previous sample when this one has no CPU delta", () => {
  clearCpuSampleCache();
  const first = {
    read: "2026-09-13T10:00:00.000Z",
    cpu_stats: { cpu_usage: { total_usage: 1_000_000_000 } },
    precpu_stats: { cpu_usage: { total_usage: 0 }, system_cpu_usage: 0 },
  };
  const second = {
    read: "2026-09-13T10:00:08.000Z",
    cpu_stats: { cpu_usage: { total_usage: 1_800_000_000 } },
    precpu_stats: { cpu_usage: { total_usage: 0 }, system_cpu_usage: 0 },
  };
  assert.equal(cpuSampleReady(resolveCachedCpuSample("c1", first)), false);
  const merged = resolveCachedCpuSample("c1", second);
  assert.equal(cpuSampleReady(merged), true);
  assert.equal(Math.round(computeCpuPercent(merged)), 10);
});

test("a too-short ready window is discarded in favor of the previous sample", () => {
  clearCpuSampleCache();
  const first = {
    read: "2026-09-13T10:00:00.000Z",
    cpu_stats: { cpu_usage: { total_usage: 1_000_000_000 } },
    precpu_stats: { cpu_usage: { total_usage: 0 }, system_cpu_usage: 0 },
  };
  const short = {
    read: "2026-09-13T10:00:08.010Z",
    preread: "2026-09-13T10:00:08.000Z",
    cpu_stats: {
      cpu_usage: { total_usage: 1_800_000_000 },
      system_cpu_usage: 16_000_000_000,
      online_cpus: 32,
    },
    precpu_stats: {
      cpu_usage: { total_usage: 1_790_000_000 },
      system_cpu_usage: 8_000_000_000,
    },
  };
  resolveCachedCpuSample("c2", first);
  const merged = resolveCachedCpuSample("c2", short);
  assert.equal(cpuSampleReady(short), false);
  assert.equal(cpuSampleReady(merged), true);
  assert.equal(Math.round(computeCpuPercent(merged)), 10);
});

test("Podman zero-date preread is not a usable reading", () => {
  const sample = {
    read: "2026-09-13T10:00:01.000Z",
    preread: "0001-01-01T00:00:00Z",
    cpu_stats: {
      cpu_usage: { total_usage: 2_000_000_000 },
      system_cpu_usage: 16_000_000_000,
      online_cpus: 32,
    },
    precpu_stats: {
      cpu_usage: { total_usage: 1_000_000_000 },
      system_cpu_usage: 8_000_000_000,
    },
  };
  assert.equal(wallDeltaNs(sample), 0);
  assert.equal(cpuSampleReady(sample), false);
  assert.equal(computeCpuPercent(sample), 0);
});

test("two Podman snapshots with zero-date preread merge into wall-clock CPU %", () => {
  const first = {
    read: "2026-09-13T10:00:00.000Z",
    preread: "0001-01-01T00:00:00Z",
    cpu_stats: {
      cpu_usage: { total_usage: 542_932_000 },
      system_cpu_usage: 415_754_597_000,
      online_cpus: 32,
    },
    precpu_stats: { cpu_usage: { total_usage: 0 }, system_cpu_usage: 0 },
  };
  const second = {
    read: "2026-09-13T10:00:00.350Z",
    preread: "0001-01-01T00:00:00Z",
    cpu_stats: {
      cpu_usage: { total_usage: 717_932_000 },
      system_cpu_usage: 416_085_433_000,
      online_cpus: 32,
    },
    precpu_stats: { cpu_usage: { total_usage: 0 }, system_cpu_usage: 0 },
  };
  const merged = mergeCpuSamples(first, second);
  assert.equal(cpuSampleReady(merged), true);
  const oneCore = computeCpuPercent(merged);
  assert.equal(Math.round(oneCore), 50);
  assert.equal(Math.round(cpuPercentOfQuota(oneCore, 500)), 100);
});

test("parseStatFrames reads NDJSON and skips a trailing incomplete object", () => {
  const frames = parseStatFrames(
    '{"cpu_stats":{"cpu_usage":{"total_usage":1}}}\n{"cpu_stats":{"cpu_usage":{"total_usage":2}}}\n{"cpu',
  );
  assert.equal(frames.length, 2);
  assert.equal(frames[1].cpu_stats?.cpu_usage?.total_usage, 2);
});
