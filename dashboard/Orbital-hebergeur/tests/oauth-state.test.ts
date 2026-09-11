import assert from "node:assert/strict";
import test from "node:test";
import {
  codeChallenge,
  createCodeVerifier,
  createOAuthState,
  sanitizeReturnTo,
  signOAuthState,
  verifyOAuthState,
} from "../src/lib/oauth/state";

test("OAuth state round-trips and rejects tampering", () => {
  const started = createOAuthState({
    provider: "github",
    intent: "login",
    returnTo: "/dashboard/new/web",
  });
  const parsed = verifyOAuthState(started.cookie);
  assert.ok(parsed);
  assert.equal(parsed.p, "github");
  assert.equal(parsed.i, "login");
  assert.equal(parsed.n, started.nonce);
  assert.equal(parsed.cv, started.verifier);
  assert.equal(parsed.r, "/dashboard/new/web");
  assert.equal(verifyOAuthState(`${started.cookie}x`), null);
  assert.equal(verifyOAuthState(started.cookie.replace(/\./, ".x")), null);
});

test("expired OAuth state is rejected", () => {
  const token = signOAuthState({
    v: 1,
    n: "nonce",
    p: "google",
    i: "link",
    exp: Date.now() - 1000,
    cv: "verifier",
  });
  assert.equal(verifyOAuthState(token), null);
});

test("PKCE challenge is S256 base64url", () => {
  const verifier = createCodeVerifier();
  const challenge = codeChallenge(verifier);
  assert.match(challenge, /^[A-Za-z0-9_-]+$/);
  assert.equal(challenge, codeChallenge(verifier));
  assert.notEqual(challenge, verifier);
});

test("sanitizeReturnTo only allows in-app paths", () => {
  assert.equal(sanitizeReturnTo("/dashboard/account/profile"), "/dashboard/account/profile");
  assert.equal(sanitizeReturnTo("//evil.example"), undefined);
  assert.equal(sanitizeReturnTo("https://evil.example"), undefined);
  assert.equal(sanitizeReturnTo("/\\evil"), undefined);
  assert.equal(sanitizeReturnTo("dashboard"), undefined);
});
