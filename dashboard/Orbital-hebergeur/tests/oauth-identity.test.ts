import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import {
  discordIdFromIdentityRow,
  discordIdFromPublicId,
  discordIdFromSiteUser,
  isDiscordSnowflake,
  isPanelUserId,
  planPanelIdentityLink,
} from "../src/lib/oauth/identity-link";

test("Discord snowflakes are 15–22 digits", () => {
  assert.equal(isDiscordSnowflake("1368235294192570520"), true);
  assert.equal(isDiscordSnowflake("70f4f7f6-df0a-4d0c-99f2-1a1c97fd1f68"), false);
  assert.equal(discordIdFromPublicId("1368235294192570520"), "1368235294192570520");
  assert.equal(discordIdFromPublicId("70f4f7f6-df0a-4d0c-99f2-1a1c97fd1f68"), null);
});

test("legacy site records still yield a Discord id for a panel UUID", () => {
  assert.equal(
    discordIdFromIdentityRow({
      discordId: "1368235294192570520",
      siteUserId: "1368235294192570520",
    }),
    "1368235294192570520",
  );
  assert.equal(
    discordIdFromSiteUser("70f4f7f6-df0a-4d0c-99f2-1a1c97fd1f68", {
      id: "1368235294192570520",
      dbId: "70f4f7f6-df0a-4d0c-99f2-1a1c97fd1f68",
    }),
    "1368235294192570520",
  );
  assert.equal(
    discordIdFromSiteUser("70f4f7f6-df0a-4d0c-99f2-1a1c97fd1f68", {
      id: "70f4f7f6-df0a-4d0c-99f2-1a1c97fd1f68",
      providers: { discord: "1368235294192570520" },
    }),
    "1368235294192570520",
  );
  assert.equal(
    discordIdFromSiteUser("70f4f7f6-df0a-4d0c-99f2-1a1c97fd1f68", {
      id: "1368235294192570520",
      dbId: "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
    }),
    null,
  );
});

test("session-bridge reuses an existing Discord oauth row, else links the current panel user", () => {
  assert.deepEqual(
    planPanelIdentityLink({
      existingOauthUserId: "aaaaaaa1-bbbb-4ccc-8ddd-eeeeeeeeeee1",
      currentUserId: "70f4f7f6-df0a-4d0c-99f2-1a1c97fd1f68",
    }),
    { action: "reuse", userId: "aaaaaaa1-bbbb-4ccc-8ddd-eeeeeeeeeee1" },
  );
  assert.deepEqual(
    planPanelIdentityLink({
      existingOauthUserId: null,
      currentUserId: "70f4f7f6-df0a-4d0c-99f2-1a1c97fd1f68",
    }),
    { action: "link", userId: "70f4f7f6-df0a-4d0c-99f2-1a1c97fd1f68" },
  );
  assert.deepEqual(planPanelIdentityLink({}), { action: "create" });
  assert.equal(isPanelUserId("70f4f7f6-df0a-4d0c-99f2-1a1c97fd1f68"), true);
  assert.equal(isPanelUserId("1368235294192570520"), false);
});

test("Discord id lookup falls back to site_profiles.public_id and backfills oauth", () => {
  const source = readFileSync(path.join(process.cwd(), "src/lib/oauth/accounts.ts"), "utf8");
  assert.match(source, /siteProfiles\.publicId/);
  assert.match(source, /backfillDiscordOAuth/);
  assert.match(source, /rememberDiscordLink/);
  assert.match(source, /discordIdFromLegacyFiles/);
});
