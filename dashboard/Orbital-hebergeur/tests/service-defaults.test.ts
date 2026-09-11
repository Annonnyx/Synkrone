import assert from "node:assert/strict";
import test from "node:test";
import { defaultMaxRestarts, defaultRestartPolicy } from "../src/lib/services/defaults";

test("discord defaults do not restart-loop a config crash", () => {
  assert.equal(defaultRestartPolicy("discord"), "no");
  assert.equal(defaultMaxRestarts("discord"), 0);
});

test("minecraft and web keep on-failure retries", () => {
  assert.equal(defaultRestartPolicy("minecraft"), "on-failure");
  assert.equal(defaultMaxRestarts("web"), 5);
});
