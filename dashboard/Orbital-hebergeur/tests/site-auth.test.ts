import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";
import { normalizePanelReturnTo, siteEnterPanel } from "../src/lib/site-auth";

test("panel returnTo stays under /hebergement and skips the login loop", () => {
  assert.equal(normalizePanelReturnTo("/hebergement/dashboard/services"), "/hebergement/dashboard/services");
  assert.equal(normalizePanelReturnTo("/dashboard/new/discord"), "/hebergement/dashboard/new/discord");
  assert.equal(normalizePanelReturnTo("/hebergement/login"), "/hebergement/dashboard");
  assert.equal(normalizePanelReturnTo("https://evil.example/"), "/hebergement/dashboard");
});

test("enter-panel URL points at the public site", () => {
  const prev = process.env.PUBLIC_SITE_ORIGIN;
  process.env.PUBLIC_SITE_ORIGIN = "https://synkrone.app";
  try {
    assert.equal(
      siteEnterPanel("/dashboard"),
      "https://synkrone.app/api/auth/enter-panel?returnTo=%2Fhebergement%2Fdashboard",
    );
  } finally {
    if (prev === undefined) delete process.env.PUBLIC_SITE_ORIGIN;
    else process.env.PUBLIC_SITE_ORIGIN = prev;
  }
});

test("session-bridge keeps Discord on the existing panel user when the site sends userId", () => {
  const source = readFileSync(
    path.join(process.cwd(), "src/app/api/internal/admin/session-bridge/route.ts"),
    "utf8",
  );
  assert.match(source, /currentUserId: body\.userId/);
  assert.match(source, /ensurePanelIdentity/);
});


test("panel returnTo stays under /hebergement and skips the login loop", () => {
  assert.equal(normalizePanelReturnTo("/hebergement/dashboard/services"), "/hebergement/dashboard/services");
  assert.equal(normalizePanelReturnTo("/dashboard/new/discord"), "/hebergement/dashboard/new/discord");
  assert.equal(normalizePanelReturnTo("/hebergement/login"), "/hebergement/dashboard");
  assert.equal(normalizePanelReturnTo("https://evil.example/"), "/hebergement/dashboard");
});

test("enter-panel URL points at the public site", () => {
  const prev = process.env.PUBLIC_SITE_ORIGIN;
  process.env.PUBLIC_SITE_ORIGIN = "https://synkrone.app";
  try {
    assert.equal(
      siteEnterPanel("/dashboard"),
      "https://synkrone.app/api/auth/enter-panel?returnTo=%2Fhebergement%2Fdashboard",
    );
  } finally {
    if (prev === undefined) delete process.env.PUBLIC_SITE_ORIGIN;
    else process.env.PUBLIC_SITE_ORIGIN = prev;
  }
});
