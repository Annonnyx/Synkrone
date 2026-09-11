import assert from "node:assert/strict";
import { test } from "node:test";
import { normalizePlatform } from "../src/lib/platform-settings";
import {
  creationDisabledMessage,
  firstCreateHref,
  isCreationEnabled,
} from "../src/lib/services/creation-flags";

test("missing flags default to creation enabled", () => {
  const settings = normalizePlatform({});
  assert.equal(settings.discordEnabled, true);
  assert.equal(settings.minecraftEnabled, true);
  assert.equal(settings.webEnabled, true);
  assert.equal(isCreationEnabled(settings, "discord"), true);
  assert.equal(firstCreateHref(settings), "/dashboard/new/discord");
});

test("disabled flags block only that type", () => {
  const settings = normalizePlatform({
    discordEnabled: false,
    minecraftEnabled: true,
    webEnabled: false,
  });
  assert.equal(isCreationEnabled(settings, "discord"), false);
  assert.equal(isCreationEnabled(settings, "minecraft"), true);
  assert.equal(isCreationEnabled(settings, "web"), false);
  assert.equal(firstCreateHref(settings), "/dashboard/new/minecraft");
  assert.match(creationDisabledMessage("discord"), /bots Discord/);
});

test("all types off leaves no create href", () => {
  const settings = normalizePlatform({
    discordEnabled: false,
    minecraftEnabled: false,
    webEnabled: false,
  });
  assert.equal(firstCreateHref(settings), null);
});
