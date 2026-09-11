import assert from "node:assert/strict";
import test from "node:test";
import { applicationIdFromToken, discordBotInviteUrl, isDiscordToken } from "../src/lib/discord/token";

function fakeToken(applicationId: string) {
  const head = Buffer.from(applicationId, "utf8").toString("base64url");
  return `${head}.Gg0abc.xxxxxxxxxxxxxxxxxxxx`;
}

test("application id is read from the first token segment", () => {
  const token = fakeToken("1368235294192570520");
  assert.equal(isDiscordToken(token), true);
  assert.equal(applicationIdFromToken(token), "1368235294192570520");
});

test("invite url is built from the application id only", () => {
  const href = discordBotInviteUrl("1368235294192570520");
  assert.ok(href);
  const url = new URL(href);
  assert.equal(url.origin + url.pathname, "https://discord.com/oauth2/authorize");
  assert.equal(url.searchParams.get("client_id"), "1368235294192570520");
  assert.equal(url.searchParams.get("scope"), "bot applications.commands");
  assert.equal(url.searchParams.get("permissions"), "8");
  assert.equal(discordBotInviteUrl("not-an-id"), null);
});
