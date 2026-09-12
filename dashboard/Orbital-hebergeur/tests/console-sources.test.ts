import assert from "node:assert/strict";
import test from "node:test";
import { consoleLineFields, formatConsoleClock, stripDockerTimestamp } from "../src/lib/console/docker-log";
import { canEditCommandSources, isProtectedBotSource, isVolumeRoot } from "../src/lib/discord/source-lock";
import { isConsoleNoise } from "../src/lib/console/line-gate";

test("docker rfc3339 prefixes become ISO at and a clean message", () => {
  const parsed = stripDockerTimestamp(
    "2026-09-12T13:27:42.123456789Z [bot] ready",
  );
  assert.equal(parsed.message, "[bot] ready");
  assert.ok(parsed.at);
  assert.equal(new Date(parsed.at!).toISOString().slice(0, 19), "2026-09-12T13:27:42");
});

test("lines without docker timestamps are left alone", () => {
  const parsed = stripDockerTimestamp("[bot] ready");
  assert.equal(parsed.message, "[bot] ready");
  assert.equal(parsed.at, undefined);
});

test("console clock is 24h H:MM:SS", () => {
  const stamp = formatConsoleClock("2026-09-12T13:27:42.000Z");
  assert.match(stamp, /^\d{2}:\d{2}:\d{2}$/);
});

test("consoleLineFields prefers the docker timestamp over the fallback", () => {
  const fields = consoleLineFields(
    "2026-09-12T13:27:42.000Z [bot] ready",
    "2026-09-12T15:00:00.000Z",
  );
  assert.equal(fields.message, "[bot] ready");
  assert.equal(new Date(fields.at!).toISOString().slice(0, 19), "2026-09-12T13:27:42");
});

test("cogs paths are protected, config is not", () => {
  assert.equal(isProtectedBotSource("cogs/PUBLIC/ping/pingpong.py"), true);
  assert.equal(isProtectedBotSource("/cogs"), true);
  assert.equal(isProtectedBotSource("synkrone_slash.py"), true);
  assert.equal(isProtectedBotSource("synkrone_custom.py"), true);
  assert.equal(isProtectedBotSource("config/bot.json"), false);
  assert.equal(isProtectedBotSource("main.py"), false);
  assert.equal(isVolumeRoot("/"), true);
});

test("command sources unlock from Kronalloy", () => {
  assert.equal(canEditCommandSources({ plan: "Synkral" }), false);
  assert.equal(canEditCommandSources({ plan: "Kronalloy" }), true);
  assert.equal(canEditCommandSources({ plan: "Aucun", privilege: "admin" }), true);
});

test("antiscam debug and gateway resume are console noise", () => {
  assert.equal(
    isConsoleNoise(
      "[ANTISCAM][DEBUG][23:46:24][G:1] Message ignoré (ni lien ni image): U:1",
    ),
    true,
  );
  assert.equal(
    isConsoleNoise("Shard ID None has successfully RESUMED session abc."),
    true,
  );
  assert.equal(isConsoleNoise("[bot] ready"), false);
});
