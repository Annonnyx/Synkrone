import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { COMMAND_CATALOG, COMMAND_COGS, customCategories } from "../src/lib/discord/catalog";
import { hostingCost } from "../src/lib/krones/pricing";
import { PANEL_BASE_PATH, withPanelBase } from "../src/lib/panel-base";
import { panelUrl, publicOrigin } from "../src/lib/oauth/providers";

test("command catalog has 179 commands mapped", () => {
  const count = COMMAND_CATALOG.categories.reduce((n, cat) => n + cat.commands.length, 0);
  assert.equal(count, 179);
  assert.equal(COMMAND_CATALOG.count, 179);
  for (const cat of COMMAND_CATALOG.categories) {
    for (const cmd of cat.commands) {
      assert.ok(COMMAND_COGS[cmd.id] || COMMAND_COGS[cmd.name], `missing cog map for ${cmd.id}`);
    }
  }
});

test("public and panel command catalogs stay identical", () => {
  const panel = readFileSync(path.join(import.meta.dirname, "../src/lib/discord/command-catalog.json"), "utf8");
  const www = readFileSync(
    path.join(import.meta.dirname, "../../../apps/www/data/command-catalog.json"),
    "utf8",
  );
  assert.equal(panel, www);
});

test("custom categories only expose template cogs", () => {
  const ids = customCategories().map((c) => c.id);
  assert.deepEqual(ids.sort(), ["admin", "configuration", "moderation", "public"].sort());
  for (const cat of customCategories()) {
    const withFile = cat.commands.filter((cmd) => (COMMAND_COGS[cmd.id] ?? COMMAND_COGS[cmd.name])?.file);
    assert.ok(withFile.length > 0, `${cat.id} should have at least one template cog`);
  }
});

test("hosting cost follows the published formulas", () => {
  assert.equal(hostingCost("minecraft", { memoryMb: 1024, cpuMillicores: 1000, storageMb: 10240 }), 160);
  assert.ok(hostingCost("discord", { memoryMb: 512, cpuMillicores: 1000, storageMb: 5120 }) >= 40);
  assert.ok(hostingCost("web", { memoryMb: 512, cpuMillicores: 1000, storageMb: 5120 }) >= 50);
});

test("hosting CPU cost is millicores/1000 times the CPU coefficient", () => {
  const noCpu = hostingCost("minecraft", { memoryMb: 1024, cpuMillicores: 0, storageMb: 10240 });
  const oneCore = hostingCost("minecraft", { memoryMb: 1024, cpuMillicores: 1000, storageMb: 10240 });
  const halfCore = hostingCost("minecraft", { memoryMb: 1024, cpuMillicores: 500, storageMb: 10240 });
  assert.equal(oneCore - noCpu, 25);
  assert.equal(halfCore - noCpu, 13);
});

test("panel URLs stay under /hebergement", () => {
  assert.equal(PANEL_BASE_PATH, "/hebergement");
  assert.equal(withPanelBase("/api/krones"), "/hebergement/api/krones");
  assert.equal(withPanelBase("/hebergement/login"), "/hebergement/login");
  const prev = process.env.SYNKRONE_PANEL_ORIGIN;
  try {
    process.env.SYNKRONE_PANEL_ORIGIN = "http://127.0.0.1:3668/hebergement";
    assert.equal(publicOrigin(), "http://127.0.0.1:3668/hebergement");
    assert.equal(panelUrl(publicOrigin(), "/login").href, "http://127.0.0.1:3668/hebergement/login");
    assert.equal(
      panelUrl(publicOrigin(), "/api/auth/oauth/discord/callback").pathname,
      "/hebergement/api/auth/oauth/discord/callback",
    );
  } finally {
    if (prev === undefined) delete process.env.SYNKRONE_PANEL_ORIGIN;
    else process.env.SYNKRONE_PANEL_ORIGIN = prev;
  }
});
