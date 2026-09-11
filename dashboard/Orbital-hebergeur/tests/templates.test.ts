import assert from "node:assert/strict";
import test from "node:test";
import {
  DISCORD_TEMPLATE,
  minecraftTemplate,
  webTemplate,
  intentsForModules,
  intentsBitfield,
  resolveGatewayIntents,
} from "../src/lib/runtime/templates";

test("each family uses a distinct runtime and network", () => {
  const mc = minecraftTemplate("paper", "1.21.1", 4096);
  const web = webTemplate("next");
  assert.notEqual(DISCORD_TEMPLATE.image, mc.image);
  assert.notEqual(mc.image, web.image);
  assert.deepEqual(DISCORD_TEMPLATE.networks, ["orbital-discord"]);
  assert.ok(mc.networks.includes("orbital-minecraft"));
  assert.ok(web.networks.includes("orbital-web"));
  assert.equal(DISCORD_TEMPLATE.mountPath, "/app");
  assert.equal(mc.environment.STOP_SERVER_ANNOUNCE_DELAY, "0");
  assert.equal(web.mountPath, "/srv/app");
});

test("minecraft software families map to different runtimes", () => {
  assert.notEqual(
    minecraftTemplate("paper", "1.21.1", 2048).id,
    minecraftTemplate("fabric", "1.21.1", 2048).id,
  );
  assert.notEqual(
    minecraftTemplate("forge", "1.21.1", 2048).id,
    minecraftTemplate("neoforge", "1.21.1", 2048).id,
  );
});

test("discord runtime is python, not node stubs", () => {
  assert.match(DISCORD_TEMPLATE.image, /python/i);
  assert.match(DISCORD_TEMPLATE.label, /Python/i);
  assert.deepEqual(DISCORD_TEMPLATE.command, ["sh", "-lc", "sh /app/.orbital/boot.sh"]);
});

test("intents are derived from the enabled modules", () => {
  const intents = intentsForModules(["moderation", "fun"]);
  assert.ok(!intents.includes("MessageContent"));
  assert.ok(!intents.includes("GuildMembers"));
  assert.ok(intents.includes("GuildMessages"));
  assert.ok(intentsBitfield(intents) > 0);
});

test("privileged intents are kept only when the user requested them", () => {
  const implied = resolveGatewayIntents(undefined, ["moderation", "welcome"]);
  assert.ok(!implied.includes("GuildMembers"));
  assert.ok(!implied.includes("MessageContent"));
  const explicit = resolveGatewayIntents(
    ["Guilds", "GuildMembers", "MessageContent"],
    ["moderation"],
  );
  assert.ok(explicit.includes("GuildMembers"));
  assert.ok(explicit.includes("MessageContent"));
});
