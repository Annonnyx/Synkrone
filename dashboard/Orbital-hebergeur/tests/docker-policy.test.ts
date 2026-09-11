import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs/promises";
import path from "node:path";
import os from "node:os";

process.env.PLATFORM_DATA_DIR = await fs.mkdtemp(path.join(os.tmpdir(), "orbital-docker-"));
const { buildContainerSpec, DockerPolicyError } = await import("../src/lib/docker/adapter");
const { dataRoot } = await import("../src/lib/paths");

const base = {
  name: "discord-test-abc",
  image: "node:20-alpine",
  env: { BOT_TOKEN: "secret" },
  volumeHostPath: path.join(dataRoot(), "discord", "svc1"),
  volumeMountPath: "/app",
  networks: ["orbital-discord"],
  cpuMillicores: 1000,
  memoryMb: 512,
  restartPolicy: "on-failure" as const,
};

test("resource limits are really applied", () => {
  const spec = buildContainerSpec(base) as Record<string, any>;
  assert.equal(spec.HostConfig.Memory, 512 * 1024 * 1024);
  assert.equal(spec.HostConfig.NanoCpus, 1_000_000_000);
  assert.equal(spec.HostConfig.Privileged, false);
  assert.deepEqual(spec.HostConfig.CapDrop, ["ALL"]);
  assert.equal(spec.User, "1000:1000");
});

test("binds outside the data root are refused", () => {
  assert.throws(
    () => buildContainerSpec({ ...base, volumeHostPath: "/var/run" }),
    DockerPolicyError,
  );
  assert.throws(() => buildContainerSpec({ ...base, volumeHostPath: "/" }), DockerPolicyError);
});

test("privileged host ports and absurd limits are refused", () => {
  assert.throws(
    () => buildContainerSpec({ ...base, ports: [{ containerPort: 80, hostPort: 80 }] }),
    DockerPolicyError,
  );
  assert.throws(() => buildContainerSpec({ ...base, memoryMb: 1 }), DockerPolicyError);
  assert.throws(() => buildContainerSpec({ ...base, cpuMillicores: 999_999 }), DockerPolicyError);
});

test("dangerous env keys are stripped", () => {
  const spec = buildContainerSpec({
    ...base,
    env: { DOCKER_HOST: "tcp://evil", LD_PRELOAD: "/x.so", OK: "1" },
  }) as Record<string, any>;
  assert.deepEqual(spec.Env, ["OK=1"]);
});
