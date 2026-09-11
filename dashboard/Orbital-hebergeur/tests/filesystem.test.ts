import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs/promises";
import path from "node:path";
import os from "node:os";

process.env.PLATFORM_DATA_DIR = await fs.mkdtemp(path.join(os.tmpdir(), "orbital-"));
const { FilesystemManager } = await import("../src/lib/filesystem/manager");

const fsm = new FilesystemManager("discord", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee");

test("write/read/list inside the volume", async () => {
  await fsm.write("config/bot.json", '{"prefix":"!"}');
  assert.equal(await fsm.read("config/bot.json"), '{"prefix":"!"}');
  const entries = await fsm.list("/");
  assert.ok(entries.some((e) => e.name === "config" && e.type === "directory"));
});

test("path traversal is rejected", async () => {
  await assert.rejects(() => fsm.read("../../etc/passwd"));
  await assert.rejects(() => fsm.write("../escape.txt", "nope"));
});

test("absolute paths are confined to the volume", async () => {
  await fsm.write("/inside.txt", "ok");
  assert.equal(await fsm.read("inside.txt"), "ok");
});

test("symlink escape is rejected", async () => {
  await fs.symlink("/etc", path.join(fsm.root, "escape"));
  await assert.rejects(() => fsm.read("escape/passwd"));
});

test("volume root cannot be deleted", async () => {
  await assert.rejects(() => fsm.remove("/"));
});
