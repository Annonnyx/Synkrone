import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

test("discord boot installs packages on the volume, not pip --user", async () => {
  const source = await readFile(
    path.join(import.meta.dirname, "../src/lib/runtime/discord.ts"),
    "utf8",
  );
  assert.match(source, /pip install --target \/app\/\.orbital\/py/);
  assert.match(source, /python -c "import discord"/);
  assert.doesNotMatch(source, /pip install --user/);
});
