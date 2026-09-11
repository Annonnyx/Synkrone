import assert from "node:assert/strict";
import test from "node:test";
import { tabCompleteMinecraft } from "../src/lib/console/mc-commands";

test("Tab completes the first token from known commands", () => {
  assert.equal(tabCompleteMinecraft("sa", 0), "save-all");
  assert.equal(tabCompleteMinecraft("sa", 1), "save-off");
  assert.equal(tabCompleteMinecraft("  op", 0), "  op");
});

test("Tab does not invent Brigadier argument completion", () => {
  assert.equal(tabCompleteMinecraft("say hello", 0), null);
  assert.equal(tabCompleteMinecraft("whitelist add steve", 0), null);
});

test("empty input cycles the known list", () => {
  const first = tabCompleteMinecraft("", 0);
  const second = tabCompleteMinecraft("", 1);
  assert.ok(first && first.length > 0);
  assert.ok(second && second !== first);
});
