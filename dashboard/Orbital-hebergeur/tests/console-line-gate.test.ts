import assert from "node:assert/strict";
import test from "node:test";
import { createLineGate, createLineSplitter, isConsoleNoise } from "../src/lib/console/line-gate";

test("line gate drops overflow inside a window and reports it", () => {
  const gate = createLineGate(2, 60_000);
  assert.equal(gate.allow(2), 2);
  assert.equal(gate.allow(3), 0);
  assert.equal(gate.takeDropped(), 3);
  assert.equal(gate.takeDropped(), 0);
});

test("line splitter holds a partial tail until the newline", () => {
  const lines: Array<[string, string]> = [];
  const split = createLineSplitter((stream, line) => lines.push([stream, line]));
  split.push("stdout", "hel");
  assert.deepEqual(lines, []);
  split.push("stdout", "lo\nwor");
  split.push("stderr", "err\n");
  assert.deepEqual(lines, [
    ["stdout", "hello"],
    ["stderr", "err"],
  ]);
  split.flush();
  assert.deepEqual(lines.at(-1), ["stdout", "wor"]);
});

test("console noise hides pip, voice and rate-limit chatter", () => {
  assert.equal(isConsoleNoise("Dropped 1 log lines (rate limit)"), true);
  assert.equal(isConsoleNoise("WARNING: Running pip as the 'root' user can result in broken permissions"), true);
  assert.equal(isConsoleNoise("PyNaCl is not installed, voice will NOT be supported"), true);
  assert.equal(isConsoleNoise("[bot] loaded cogs.ADMIN.moderation.ban.ban"), false);
  assert.equal(isConsoleNoise("[synkrone] starting bot"), false);
});
