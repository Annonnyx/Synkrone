import assert from "node:assert/strict";
import test from "node:test";
import {
  commitHistoryEntry,
  HISTORY_LIMIT,
  parseHistory,
  searchHistory,
} from "../src/lib/console/history";

test("parseHistory keeps non-empty strings and drops junk", () => {
  assert.deepEqual(parseHistory(null), []);
  assert.deepEqual(parseHistory("not-json"), []);
  assert.deepEqual(parseHistory(JSON.stringify(["say hi", 1, "", "list"])), ["say hi", "list"]);
});

test("commitHistoryEntry skips blanks and consecutive duplicates, then caps", () => {
  assert.deepEqual(commitHistoryEntry(["a"], "  "), ["a"]);
  assert.deepEqual(commitHistoryEntry(["a"], "a"), ["a"]);
  assert.deepEqual(commitHistoryEntry(["a"], "b"), ["a", "b"]);
  const many = Array.from({ length: HISTORY_LIMIT }, (_, i) => String(i));
  const next = commitHistoryEntry(many, "x");
  assert.equal(next.length, HISTORY_LIMIT);
  assert.equal(next[0], "1");
  assert.equal(next.at(-1), "x");
});

test("searchHistory is newest-first and substring matches", () => {
  const entries = ["say one", "list", "say two"];
  assert.deepEqual(searchHistory(entries, ""), ["say two", "list", "say one"]);
  assert.deepEqual(searchHistory(entries, "SAY"), ["say two", "say one"]);
});
