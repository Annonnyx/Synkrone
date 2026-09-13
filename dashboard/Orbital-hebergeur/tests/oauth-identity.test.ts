import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import {
  applyOAuthIdentity,
  discordIdFromIdentityRow,
  discordIdFromPublicId,
  discordIdFromSiteUser,
  isDiscordSnowflake,
  isPanelUserId,
  mergeIdentityState,
  pickCanonicalUserId,
  planPanelIdentityLink,
  type IdentityState,
} from "../src/lib/oauth/identity-link";

const DISCORD_USER = "70f4f7f6-df0a-4d0c-99f2-1a1c97fd1f68";
const GOOGLE_USER = "aaaaaaa1-bbbb-4ccc-8ddd-eeeeeeeeeee1";
const SNOW = "1368235294192570520";

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

test("a logged-in user keeps their id when the provider is already on another account", () => {
  assert.deepEqual(
    planPanelIdentityLink({
      existingOauthUserId: GOOGLE_USER,
      currentUserId: DISCORD_USER,
      currentHasDiscord: true,
      existingHasDiscord: false,
    }),
    { action: "merge", userId: DISCORD_USER, fromUserId: GOOGLE_USER },
  );
  assert.deepEqual(
    planPanelIdentityLink({
      existingOauthUserId: DISCORD_USER,
      currentUserId: GOOGLE_USER,
      currentHasDiscord: false,
      existingHasDiscord: true,
    }),
    { action: "merge", userId: DISCORD_USER, fromUserId: GOOGLE_USER },
  );
  assert.deepEqual(
    planPanelIdentityLink({
      existingOauthUserId: null,
      currentUserId: DISCORD_USER,
    }),
    { action: "link", userId: DISCORD_USER },
  );
  assert.deepEqual(planPanelIdentityLink({}), { action: "create" });
  assert.equal(isPanelUserId(DISCORD_USER), true);
  assert.equal(isPanelUserId(SNOW), false);
});

test("two Discord identities do not merge into each other", () => {
  assert.deepEqual(
    planPanelIdentityLink({
      existingOauthUserId: GOOGLE_USER,
      currentUserId: DISCORD_USER,
      currentHasDiscord: true,
      existingHasDiscord: true,
      differentDiscord: true,
    }),
    { action: "conflict" },
  );
});

test("canonical user prefers Discord + services over a stale empty UUID", () => {
  assert.equal(
    pickCanonicalUserId(
      [
        { userId: GOOGLE_USER, hasDiscord: false, services: 0, wallet: 50 },
        { userId: DISCORD_USER, hasDiscord: true, publicIdIsSnowflake: true, services: 1, wallet: 1200 },
      ],
      GOOGLE_USER,
    ),
    DISCORD_USER,
  );
});

function discordAccount(): IdentityState {
  return {
    users: { [DISCORD_USER]: { email: `discord-${SNOW}@oauth.synkrone.local`, name: "Onyx" } },
    oauth: [{ userId: DISCORD_USER, provider: "discord", providerAccountId: SNOW }],
    services: [{ id: "svc-bot", ownerId: DISCORD_USER }],
    wallets: { [DISCORD_USER]: 1200 },
    profiles: { [DISCORD_USER]: SNOW },
    seq: 1,
  };
}

test("logged-in Discord user links Google then GitHub without changing user, services or wallet", () => {
  let { state, userId } = applyOAuthIdentity(discordAccount(), {
    provider: "google",
    providerAccountId: "google-sub-1",
    intent: "link",
    currentUserId: DISCORD_USER,
    email: "onyx@gmail.com",
    emailVerified: true,
    name: "Onyx",
  });
  assert.equal(userId, DISCORD_USER);
  ({ state, userId } = applyOAuthIdentity(state, {
    provider: "github",
    providerAccountId: "99",
    intent: "link",
    currentUserId: DISCORD_USER,
    name: "onyx",
  }));
  assert.equal(userId, DISCORD_USER);
  assert.equal(state.services.filter((row) => row.ownerId === DISCORD_USER).length, 1);
  assert.equal(state.wallets[DISCORD_USER], 1200);
  assert.equal(Object.keys(state.users).length, 1);
  assert.ok(state.oauth.some((row) => row.provider === "google" && row.userId === DISCORD_USER));
  assert.ok(state.oauth.some((row) => row.provider === "github" && row.userId === DISCORD_USER));
});

test("linking Google already on an empty user merges into Discord and keeps the higher wallet", () => {
  const split: IdentityState = {
    ...discordAccount(),
    users: {
      [DISCORD_USER]: { email: `discord-${SNOW}@oauth.synkrone.local`, name: "Onyx" },
      [GOOGLE_USER]: { email: "onyx@gmail.com", name: "Onyx" },
    },
    oauth: [
      { userId: DISCORD_USER, provider: "discord", providerAccountId: SNOW },
      { userId: GOOGLE_USER, provider: "google", providerAccountId: "google-sub-1", email: "onyx@gmail.com" },
    ],
    wallets: { [DISCORD_USER]: 1200, [GOOGLE_USER]: 50 },
  };
  const { state, userId } = applyOAuthIdentity(split, {
    provider: "google",
    providerAccountId: "google-sub-1",
    intent: "link",
    currentUserId: DISCORD_USER,
    email: "onyx@gmail.com",
    emailVerified: true,
  });
  assert.equal(userId, DISCORD_USER);
  assert.equal(state.users[GOOGLE_USER], undefined);
  assert.equal(state.services[0].ownerId, DISCORD_USER);
  assert.equal(state.wallets[DISCORD_USER], 1200);
  assert.equal(state.wallets[GOOGLE_USER], undefined);
  assert.ok(state.oauth.some((row) => row.provider === "google" && row.userId === DISCORD_USER));
});

test("Discord login after a split session restores services onto the Discord user", () => {
  const split: IdentityState = {
    users: {
      [DISCORD_USER]: { email: `discord-${SNOW}@oauth.synkrone.local`, name: "Onyx" },
      [GOOGLE_USER]: { email: "onyx@gmail.com", name: "Onyx" },
    },
    oauth: [
      { userId: DISCORD_USER, provider: "discord", providerAccountId: SNOW },
      { userId: GOOGLE_USER, provider: "google", providerAccountId: "google-sub-1", email: "onyx@gmail.com" },
    ],
    services: [{ id: "svc-bot", ownerId: DISCORD_USER }],
    wallets: { [DISCORD_USER]: 1200, [GOOGLE_USER]: 50 },
    profiles: { [DISCORD_USER]: SNOW, [GOOGLE_USER]: "google:google-sub-1" },
    seq: 2,
  };
  const merged = mergeIdentityState(split, GOOGLE_USER, DISCORD_USER, { preferFromProviders: ["google"] });
  assert.equal(merged.users[GOOGLE_USER], undefined);
  assert.equal(merged.services[0].ownerId, DISCORD_USER);
  assert.equal(merged.wallets[DISCORD_USER], 1200);
  const { userId, state } = applyOAuthIdentity(split, {
    provider: "discord",
    providerAccountId: SNOW,
    intent: "login",
    email: "onyx@gmail.com",
    emailVerified: true,
  });
  assert.equal(userId, DISCORD_USER);
  assert.equal(state.services.filter((row) => row.ownerId === DISCORD_USER).length, 1);
});

test("oauth callback switches the session when merge lands on another user", () => {
  const source = readFileSync(
    path.join(process.cwd(), "src/app/api/auth/oauth/[provider]/callback/route.ts"),
    "utf8",
  );
  assert.match(source, /current\.id !== result\.userId/);
  assert.match(source, /bridgeSiteSession\(provider, profile, result\.userId\)/);
});

test("completeOAuthLogin merges overlapping users instead of hopping the session", () => {
  const source = readFileSync(path.join(process.cwd(), "src/lib/oauth/accounts.ts"), "utf8");
  assert.match(source, /healOverlappingUsers/);
  assert.match(source, /mergePanelUsers/);
  assert.match(source, /preferFromProviders/);
  const merge = readFileSync(path.join(process.cwd(), "src/lib/oauth/merge-users.ts"), "utf8");
  assert.match(merge, /UPDATE services SET owner_id/);
  assert.match(merge, /Math\.max\(fromBal, intoBal\)/);
  const bridge = readFileSync(
    path.join(process.cwd(), "src/app/api/internal/admin/session-bridge/route.ts"),
    "utf8",
  );
  assert.match(bridge, /linkProvider/);
  assert.match(bridge, /currentUserId: identity\.userId/);
});

test("Discord id lookup falls back to site_profiles.public_id and backfills oauth", () => {
  const source = readFileSync(path.join(process.cwd(), "src/lib/oauth/accounts.ts"), "utf8");
  assert.match(source, /siteProfiles\.publicId/);
  assert.match(source, /backfillDiscordOAuth/);
  assert.match(source, /rememberDiscordLink/);
  assert.match(source, /discordIdFromLegacyFiles/);
});
