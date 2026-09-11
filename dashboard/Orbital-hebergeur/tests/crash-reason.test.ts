import assert from "node:assert/strict";
import test from "node:test";
import { crashReasonFromLogs, isConfigFatalLogs } from "../src/lib/runtime/crash";

test("extracts the [fatal] line from discord boot logs", () => {
  const logs = [
    "[orbital] booting discord runtime",
    "[orbital] starting bot",
    "[fatal] BOT_TOKEN is not set - the panel must inject it",
  ].join("\n");
  assert.equal(
    crashReasonFromLogs(logs, 1),
    "BOT_TOKEN is not set - the panel must inject it",
  );
});

test("reports OOM before parsing logs", () => {
  assert.equal(crashReasonFromLogs("irrelevant", 137, true), "Container was killed (out of memory)");
});

test("falls back to the exit code", () => {
  assert.equal(crashReasonFromLogs("", 1), "exit code 1");
});

test("disallowed intents are a config fatal even without [fatal]", () => {
  assert.equal(isConfigFatalLogs("Error: Used disallowed intents"), true);
  assert.equal(isConfigFatalLogs("[bot] loaded 26 commands"), false);
});

test("an invalid token is a config fatal", () => {
  assert.equal(isConfigFatalLogs("An invalid token was provided"), true);
});

test("extracts the disallowed-intents fatal line", () => {
  const logs = [
    "[bot] loaded 26 commands",
    "[fatal] Used disallowed intents. Enable Server Members Intent and Message Content Intent in the Discord developer portal (Application → Bot), or uncheck GuildMembers, MessageContent and GuildPresences in the panel.",
  ].join("\n");
  assert.match(crashReasonFromLogs(logs, 0), /disallowed intents/i);
});
