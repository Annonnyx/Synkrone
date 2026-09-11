import assert from "node:assert/strict";
import test from "node:test";
import {
  encryptSecret,
  decryptSecret,
  hashPassword,
  verifyPassword,
  fingerprint,
  slugify,
} from "../src/lib/crypto";
import { sha512Crypt } from "../src/lib/sha512crypt";
import { sftpUserConfLine } from "../src/lib/sftp/format";

test("secrets round-trip through AES-256-GCM", () => {
  const secret = "MTIzNDU2Nzg5.discord.token";
  const enc = encryptSecret(secret);
  assert.notEqual(enc, secret);
  assert.equal(decryptSecret(enc), secret);
});

test("tampered ciphertext does not decrypt", () => {
  const enc = encryptSecret("hello");
  assert.equal(decryptSecret(`${enc}x`), null);
});

test("passwords use salted scrypt", () => {
  const hash = hashPassword("correct horse battery");
  assert.ok(verifyPassword("correct horse battery", hash));
  assert.ok(!verifyPassword("wrong", hash));
  assert.notEqual(hash, hashPassword("correct horse battery"));
});

test("fingerprints are stable and non reversible", () => {
  assert.equal(fingerprint("abc"), fingerprint("abc"));
  assert.equal(fingerprint("abc").length, 12);
});

test("slugify produces container safe names", () => {
  assert.equal(slugify("My Bot!! éàç"), "my-bot-eac");
});

test("sha512 crypt matches openssl passwd -6", () => {
  assert.equal(
    sha512Crypt("password", "saltsalt"),
    "$6$saltsalt$qFmFH.bQmmtXzyBY0s9v7Oicd2z4XSIecDzlB5KiA2/jctKu9YterLp8wwnSq.qc.eoxqOmSuNp2xS0ktL3nh/",
  );
  assert.equal(
    sha512Crypt("p@ss:word", "abc./DEF12345678"),
    "$6$abc./DEF12345678$dG8aPtD1.6fmacjSBgOGn6FLHNBg7UtLIHfP89fdsFymaJT0fEwHlgqFDJpoom95ebC5RHgkzY483SssXOsxd1",
  );
});

test("sftp users.conf uses crypt when present and leaves password empty otherwise", () => {
  const crypt =
    "$6$saltsalt$qFmFH.bQmmtXzyBY0s9v7Oicd2z4XSIecDzlB5KiA2/jctKu9YterLp8wwnSq.qc.eoxqOmSuNp2xS0ktL3nh/";
  assert.equal(
    sftpUserConfLine("web_site_6d74fb", "/data/web/abc", crypt),
    `web_site_6d74fb:${crypt}:e:1000:1000:data/web/abc`,
  );
  assert.equal(
    sftpUserConfLine("web_site_6d74fb", "/data/web/abc", null),
    "web_site_6d74fb::1000:1000:data/web/abc",
  );
});
