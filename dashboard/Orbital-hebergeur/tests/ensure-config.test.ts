import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { COMMAND_COGS } from "../src/lib/discord/catalog";
import {
  CONFIG_COG_FILE,
  CONFIG_COG_MODULE,
  CONFIG_COMMAND,
  hasConfigHybridCommand,
  withConfigCogEnabled,
  withRequiredConfigCommand,
} from "../src/lib/discord/ensure-config";

const TEMPLATE = readFileSync(
  path.join(process.cwd(), "..", "..", "templates", "discord", CONFIG_COG_FILE),
  "utf8",
);

test("catalog maps /config to the template hub cog", () => {
  assert.equal(COMMAND_COGS.config?.custom, true);
  assert.equal(COMMAND_COGS.config?.file, CONFIG_COG_FILE);
  assert.equal(CONFIG_COG_MODULE, "cogs.ADMIN.configuration.confighub.config");
});

test("template config.py exposes the hybrid /config command", () => {
  assert.equal(hasConfigHybridCommand(TEMPLATE), true);
  assert.equal(hasConfigHybridCommand("async def config_cmd"), false);
});

test("enabled_cogs always includes the config hub module", () => {
  assert.deepEqual(withConfigCogEnabled(["cogs.PUBLIC.ping.pingpong"]), [
    "cogs.PUBLIC.ping.pingpong",
    CONFIG_COG_MODULE,
  ]);
  assert.deepEqual(withConfigCogEnabled([CONFIG_COG_MODULE, CONFIG_COG_FILE]), [CONFIG_COG_MODULE]);
});

test("command lists cannot drop or disable /config", () => {
  const forced = withRequiredConfigCommand([
    { name: "ban", enabled: true },
    { name: CONFIG_COMMAND, enabled: false },
  ]);
  assert.equal(forced.find((c) => c.name === CONFIG_COMMAND)?.enabled, true);
  const added = withRequiredConfigCommand([{ name: "ping", enabled: true }]);
  assert.equal(added.some((c) => c.name === CONFIG_COMMAND && c.enabled), true);
});
