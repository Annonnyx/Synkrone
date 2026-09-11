import assert from "node:assert/strict";
import test from "node:test";
import { explainError } from "../src/lib/errors";

test("docker unreachable is explained in both locales", () => {
  const fr = explainError("Docker engine not reachable at /var/run/docker.sock", "fr");
  const en = explainError("Docker engine not reachable at /var/run/docker.sock", "en");
  assert.equal(fr.title, "Moteur de conteneurs injoignable");
  assert.equal(en.title, "Container engine unreachable");
  assert.ok(fr.action && en.action);
});

test("missing discord token suggests the Token tab", () => {
  const hit = explainError("BOT_TOKEN is not set", "fr");
  assert.equal(hit.title, "Token Discord manquant");
  assert.match(hit.action ?? "", /Token/);
});

test("rate limit is recognized", () => {
  const hit = explainError("Too many requests, slow down", "en");
  assert.equal(hit.title, "Too many requests");
});

test("path traversal is a security refusal", () => {
  const hit = explainError("Path escapes service root", "fr");
  assert.equal(hit.title, "Chemin refusé");
});

test("unknown errors fall back with the raw message as detail", () => {
  const hit = explainError("some weird backend failure", "fr");
  assert.equal(hit.title, "L'action a échoué");
  assert.equal(hit.action, "some weird backend failure");
});

test("first matching rule wins over generic ones", () => {
  // "not found" appears in the socket rule too; the engine rule must win.
  const hit = explainError("Docker socket /run/docker.sock not found", "en");
  assert.equal(hit.title, "Container engine unreachable");
});

test("postgres down is distinguished from a generic network error", () => {
  const hit = explainError("The database is unreachable", "fr");
  assert.equal(hit.title, "Base de données injoignable");
  assert.match(hit.action ?? "", /Postgres/);
});

test("disallowed discord intents point at the portal or the panel toggles", () => {
  const en = explainError("Used disallowed intents", "en");
  assert.equal(en.title, "Discord intents refused");
  assert.match(en.action ?? "", /uncheck GuildMembers/);
  const fr = explainError(
    "Used disallowed intents. Enable Server Members Intent in the Discord developer portal",
    "fr",
  );
  assert.equal(fr.title, "Intents Discord refusés");
  assert.match(fr.action ?? "", /décochez/);
});
