import assert from "node:assert/strict";
import test from "node:test";
import { discordSiteLinkEnv, publicSiteOriginFromEnv, containerNeedsSiteLinkEnv } from "../src/lib/discord/site-link-env";

test("panel origin with /hebergement becomes the public site origin", () => {
  assert.equal(
    publicSiteOriginFromEnv({ SYNKRONE_PANEL_ORIGIN: "https://synkrone.app/hebergement" }),
    "https://synkrone.app",
  );
});

test("PUBLIC_ORIGIN wins over the panel origin", () => {
  assert.equal(
    publicSiteOriginFromEnv({
      PUBLIC_ORIGIN: "https://synkrone.app",
      SYNKRONE_PANEL_ORIGIN: "http://127.0.0.1:3668/hebergement",
    }),
    "https://synkrone.app",
  );
});

test("site link env injects origin and the platform secret", () => {
  const env = discordSiteLinkEnv({
    SYNKRONE_PANEL_ORIGIN: "https://synkrone.app/hebergement",
    PLATFORM_SECRET_KEY: "platform-secret-value",
  });
  assert.equal(env.PUBLIC_SITE_ORIGIN, "https://synkrone.app");
  assert.equal(env.BOT_CONFIG_SECRET, "platform-secret-value");
  assert.equal(env.SESSION_SECRET, "platform-secret-value");
});

test("an existing container without PUBLIC_SITE_ORIGIN must be recreated", () => {
  const expected = discordSiteLinkEnv({
    PUBLIC_ORIGIN: "https://synkrone.app",
    PLATFORM_SECRET_KEY: "platform-secret-value",
  });
  assert.equal(
    containerNeedsSiteLinkEnv(["BOT_TOKEN=abc", "BOT_CONFIG_SECRET=platform-secret-value"], expected),
    true,
  );
  assert.equal(
    containerNeedsSiteLinkEnv(
      [
        "BOT_TOKEN=abc",
        "PUBLIC_SITE_ORIGIN=https://synkrone.app",
        "BOT_CONFIG_SECRET=platform-secret-value",
      ],
      expected,
    ),
    false,
  );
});
