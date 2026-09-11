import assert from "node:assert/strict";
import test from "node:test";
import { githubCloneUrl, parseGithubRepo, redactSecrets } from "../src/lib/oauth/urls";

test("parseGithubRepo accepts common GitHub forms", () => {
  assert.deepEqual(parseGithubRepo("https://github.com/acme/site.git")?.fullName, "acme/site");
  assert.deepEqual(parseGithubRepo("git@github.com:acme/site.git")?.fullName, "acme/site");
  assert.deepEqual(parseGithubRepo("acme/site")?.fullName, "acme/site");
  assert.equal(parseGithubRepo("https://gitlab.com/acme/site"), null);
});

test("githubCloneUrl embeds the token and redactSecrets hides it", () => {
  const url = githubCloneUrl("https://github.com/acme/site.git", "gho_supersecret");
  assert.ok(url?.includes("x-access-token"));
  assert.ok(url?.includes("gho_supersecret"));
  assert.equal(redactSecrets(url ?? "").includes("gho_supersecret"), false);
  assert.match(redactSecrets("clone https://x-access-token:abc@github.com/acme/site"), /x-access-token:\*\*\*@/);
});
