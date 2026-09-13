import assert from "node:assert/strict";
import test from "node:test";
import { normalizePlatform } from "../src/lib/platform-settings";
import { clampResources } from "../src/lib/services/clamp-resources";
import {
  CPU_PRESETS,
  TYPE_CPU_HARD_CAP,
  cpuPresetsFor,
  defaultCpuMillicores,
  formatCpuCores,
} from "../src/lib/services/resource-presets";

test("discord and web CPU caps are 1 vCPU even if platform.json still says 2000", () => {
  const settings = normalizePlatform({
    limits: {
      discord: { cpuMillicores: 2000, memoryMb: 2048, storageMb: 10240 },
      web: { cpuMillicores: 2000, memoryMb: 4096, storageMb: 20480 },
      minecraft: { cpuMillicores: 4000, memoryMb: 8192, storageMb: 51200 },
    },
  });
  assert.equal(settings.limits.discord.cpuMillicores, 1000);
  assert.equal(settings.limits.web.cpuMillicores, 1000);
  assert.equal(settings.limits.minecraft.cpuMillicores, 4000);
  assert.equal(TYPE_CPU_HARD_CAP.discord, 1000);
  assert.equal(TYPE_CPU_HARD_CAP.web, 1000);
});

test("clampResources refuses discord CPU above 1000 millicores", () => {
  const settings = normalizePlatform({});
  const discord = clampResources(settings, "discord", { cpuMillicores: 4000, memoryMb: 512, storageMb: 5120 });
  assert.equal(discord.cpuMillicores, 1000);
  const web = clampResources(settings, "web", { cpuMillicores: 2500, memoryMb: 512, storageMb: 5120 });
  assert.equal(web.cpuMillicores, 1000);
  const mc = clampResources(settings, "minecraft", { cpuMillicores: 4000, memoryMb: 4096, storageMb: 20480 });
  assert.equal(mc.cpuMillicores, 4000);
});

test("discord default allocation is 500 millicores, web 1000", () => {
  const settings = normalizePlatform({});
  assert.equal(defaultCpuMillicores("discord"), 500);
  assert.equal(defaultCpuMillicores("web"), 1000);
  assert.equal(clampResources(settings, "discord", {}).cpuMillicores, 500);
  assert.equal(clampResources(settings, "web", {}).cpuMillicores, 1000);
});

test("CPU presets match the product: 0.25/0.5/1 for discord+web, up to 4 for minecraft", () => {
  assert.deepEqual(CPU_PRESETS.discord, [250, 500, 1000]);
  assert.deepEqual(cpuPresetsFor("discord", 1000), [250, 500, 1000]);
  assert.deepEqual(cpuPresetsFor("web", 1000), [250, 500, 1000]);
  assert.deepEqual(cpuPresetsFor("minecraft", 4000), [500, 1000, 2000, 4000]);
  assert.equal(formatCpuCores(250), "0.25");
  assert.equal(formatCpuCores(500), "0.5");
  assert.equal(formatCpuCores(1000), "1");
});
