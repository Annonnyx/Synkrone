import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import path from "node:path";
import { patchHelpMemberCounts } from "../src/lib/discord/help-patch";

const GUILLAUME = `        total_members = guild.member_count
        bots_count = sum(1 for member in guild.members if member.bot)
        humans_count = total_members - bots_count`;

const TEMPLATE = `        total_members = guild.member_count if guild else 0
        bots_count = sum(1 for member in guild.members if member.bot) if guild else 0
        humans_count = total_members - bots_count`;

test("help patch makes member_count None-safe for the live traceback shape", () => {
  const patched = patchHelpMemberCounts(GUILLAUME);
  assert.equal(patched.includes("humans_count = total_members - bots_count"), false);
  assert.equal(patched.includes("int((guild.member_count if guild else 0)"), true);
  assert.equal(patched.includes("max(0, total_members - bots_count)"), true);
});

test("help patch also covers the template variant", () => {
  const patched = patchHelpMemberCounts(TEMPLATE);
  assert.equal(patched.includes("max(0, total_members - bots_count)"), true);
  assert.equal(patched.includes("total_members = guild.member_count if guild else 0"), false);
});

test("already patched help.py is left alone", () => {
  const once = patchHelpMemberCounts(GUILLAUME);
  assert.equal(patchHelpMemberCounts(once), once);
});

test("template help.py no longer subtracts from a raw member_count", () => {
  const file = readFileSync(
    path.join(process.cwd(), "..", "..", "templates", "discord", "cogs", "help.py"),
    "utf8",
  );
  assert.match(file, /int\(\(guild\.member_count if guild else 0\)/);
  assert.doesNotMatch(file, /total_members = guild\.member_count if guild else 0/);
});
