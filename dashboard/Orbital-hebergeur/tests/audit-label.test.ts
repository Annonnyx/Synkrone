import assert from "node:assert/strict";
import test from "node:test";
import { auditActionLabel } from "../src/lib/audit-label";

test("audit labels translate lifecycle actions", () => {
  assert.equal(auditActionLabel("service.restart", "fr"), "Redémarrage du service");
  assert.equal(auditActionLabel("service.restart", "en"), "Service restarted");
  assert.equal(auditActionLabel("service.start", "fr"), "Démarrage du service");
  assert.equal(auditActionLabel("service.kill", "fr"), "Arrêt forcé du service");
});

test("audit labels cover dynamic actions", () => {
  assert.equal(auditActionLabel("service.create.discord", "fr"), "Bot Discord créé");
  assert.equal(auditActionLabel("service.create.minecraft", "en"), "Minecraft server created");
  assert.equal(auditActionLabel("minecraft.plugin.install", "fr"), "Plugin installé");
  assert.equal(auditActionLabel("minecraft.mod.upload", "en"), "Mod uploaded");
  assert.equal(auditActionLabel("oauth.link.github", "fr"), "Compte GitHub lié");
  assert.equal(auditActionLabel("oauth.login.discord", "en"), "Signed in with Discord");
  assert.equal(auditActionLabel("discord.token.rotate", "fr"), "Token Discord remplacé");
  assert.equal(auditActionLabel("database.reset_password", "fr"), "Mot de passe de la base régénéré");
  assert.equal(auditActionLabel("auth.password_change", "en"), "Password changed");
});

test("audit labels fall back to the raw action when unknown", () => {
  assert.equal(auditActionLabel("something.new", "fr"), "something.new");
  assert.equal(auditActionLabel("something.new", "en"), "something.new");
});
