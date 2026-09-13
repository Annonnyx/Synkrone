import assert from "node:assert/strict";
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
