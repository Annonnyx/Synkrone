import assert from "node:assert/strict";
import test from "node:test";
import { DEFAULT_CONSOLE_PREFS, parseConsolePrefs } from "../src/lib/console/prefs";

test("parseConsolePrefs falls back to defaults", () => {
  assert.deepEqual(parseConsolePrefs(null), DEFAULT_CONSOLE_PREFS);
  assert.deepEqual(parseConsolePrefs("nope"), DEFAULT_CONSOLE_PREFS);
});

test("parseConsolePrefs accepts known font and height choices", () => {
  assert.deepEqual(parseConsolePrefs(JSON.stringify({ wrap: false, fontPx: 15, heightPx: 640 })), {
    wrap: false,
    fontPx: 15,
    heightPx: 640,
  });
  assert.equal(parseConsolePrefs(JSON.stringify({ fontPx: 99, heightPx: 12 })).fontPx, 13);
});
