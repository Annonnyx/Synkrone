import assert from "node:assert/strict";
import test from "node:test";
import {
  LEGACY_SFTP_ACCOUNT_MARKER,
  generateSftpSecret,
  isPerServiceSftpSecret,
  sftpPasswordMatches,
} from "../src/lib/sftp/password";

test("SFTP secrets are per-service passwords, not the account marker", () => {
  const issued = generateSftpSecret();
  assert.notEqual(issued.password, LEGACY_SFTP_ACCOUNT_MARKER);
  assert.ok(issued.password.length >= 20);
  assert.ok(issued.crypt.startsWith("$6$"));
  assert.equal(isPerServiceSftpSecret(issued.password), true);
  assert.equal(isPerServiceSftpSecret(LEGACY_SFTP_ACCOUNT_MARKER), false);
  assert.equal(isPerServiceSftpSecret(null), false);
});

test("SFTP auth matches the service password and rejects the account marker", () => {
  const issued = generateSftpSecret();
  assert.equal(sftpPasswordMatches(issued.password, issued.password), true);
  assert.equal(sftpPasswordMatches(issued.password, "wrong-password"), false);
  assert.equal(sftpPasswordMatches(LEGACY_SFTP_ACCOUNT_MARKER, "anything"), false);
  assert.equal(sftpPasswordMatches(null, issued.password), false);
});
