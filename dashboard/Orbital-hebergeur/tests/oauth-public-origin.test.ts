import assert from "node:assert/strict";
import test from "node:test";
import {
  isLoopbackOrigin,
  oauthRedirectUri,
  pickPublicOrigin,
  publicPanelOrigin,
} from "../src/lib/oauth/public-origin";
import { authorizationUrl } from "../src/lib/oauth/providers";

function withEnv(values, fn) {
  const prev = {};
  for (const key of Object.keys(values)) prev[key] = process.env[key];
  try {
    for (const [key, value] of Object.entries(values)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
    return fn();
  } finally {
    for (const [key, value] of Object.entries(prev)) {
      if (value === undefined) delete process.env[key];
      else process.env[key] = value;
    }
  }
}

const CLEAR = {
  PUBLIC_ORIGIN: undefined,
  PUBLIC_SITE_ORIGIN: undefined,
  SYNKRONE_PANEL_ORIGIN: undefined,
  ORBITAL_PUBLIC_ORIGIN: undefined,
  NODE_ENV: "development",
};

test("loopback hosts are detected", () => {
  assert.equal(isLoopbackOrigin("http://127.0.0.1:3668/auth/google/callback"), true);
  assert.equal(isLoopbackOrigin("https://synkrone.app/auth/google/callback"), false);
});

test("PUBLIC_ORIGIN wins over a leftover localhost panel origin", () => {
  withEnv(
    {
      ...CLEAR,
      PUBLIC_ORIGIN: "https://synkrone.app",
      SYNKRONE_PANEL_ORIGIN: "http://127.0.0.1:3668/hebergement",
    },
    () => {
      assert.equal(publicPanelOrigin("http://127.0.0.1:3000"), "https://synkrone.app/hebergement");
      assert.equal(
        oauthRedirectUri("google", "http://127.0.0.1:3000"),
        "https://synkrone.app/hebergement/api/auth/oauth/google/callback",
      );
      assert.equal(
        oauthRedirectUri("github", "http://127.0.0.1:3668"),
        "https://synkrone.app/hebergement/api/auth/oauth/github/callback",
      );
    },
  );
});

test("production falls back to synkrone.app when every origin is loopback", () => {
  withEnv({ ...CLEAR, NODE_ENV: "production", SYNKRONE_PANEL_ORIGIN: "http://127.0.0.1:3668/hebergement" }, () => {
    assert.equal(pickPublicOrigin(["http://127.0.0.1:3668"], { NODE_ENV: "production" }), "https://synkrone.app");
    assert.equal(
      oauthRedirectUri("google", "http://127.0.0.1:3668"),
      "https://synkrone.app/hebergement/api/auth/oauth/google/callback",
    );
  });
});

test("Google authorize URL does not embed the Next listen address", () => {
  withEnv({ ...CLEAR, PUBLIC_ORIGIN: "https://synkrone.app" }, () => {
    const url = new URL(
      authorizationUrl({
        provider: "google",
        config: { id: "google", clientId: "cid", clientSecret: "secret" },
        origin: "http://127.0.0.1:3000",
        nonce: "n",
        verifier: "v".repeat(43),
        intent: "login",
      }),
    );
    assert.equal(
      url.searchParams.get("redirect_uri"),
      "https://synkrone.app/hebergement/api/auth/oauth/google/callback",
    );
  });
});
