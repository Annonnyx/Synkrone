import assert from "node:assert/strict";
import test from "node:test";
import { mergeContainerEnv } from "../src/lib/runtime/env";

test("empty user env does not wipe the Discord token", () => {
  const env = mergeContainerEnv(
    { PYTHONUNBUFFERED: "1" },
    { DISCORD_TOKEN: "", BOT_TOKEN: "" },
    { DISCORD_TOKEN: "real-token", BOT_TOKEN: "real-token", BOT_PREFIX: "!" },
  );
  assert.equal(env.DISCORD_TOKEN, "real-token");
  assert.equal(env.BOT_TOKEN, "real-token");
  assert.equal(env.BOT_PREFIX, "!");
});
