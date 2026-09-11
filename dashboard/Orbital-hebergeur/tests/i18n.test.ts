import assert from "node:assert/strict";
import test from "node:test";
import { fr } from "../src/lib/i18n/fr";
import { en } from "../src/lib/i18n/en";
import { LOCALES } from "../src/lib/i18n/shared";

type Tree = Record<string, unknown>;

function flatten(tree: Tree, prefix = ""): string[] {
  return Object.entries(tree).flatMap(([key, value]) =>
    value !== null && typeof value === "object"
      ? flatten(value as Tree, `${prefix}${key}.`)
      : [`${prefix}${key}`],
  );
}

test("fr and en dictionaries expose the exact same keys", () => {
  const frKeys = flatten(fr as unknown as Tree).sort();
  const enKeys = flatten(en as unknown as Tree).sort();
  assert.deepEqual(enKeys, frKeys);
});

test("no dictionary value is empty", () => {
  for (const dict of [fr, en] as unknown as Tree[]) {
    for (const key of flatten(dict)) {
      const value = key.split(".").reduce<unknown>((node, k) => (node as Tree)[k], dict);
      assert.ok(
        typeof value === "string" && value.trim().length > 0,
        `empty translation at ${key}`,
      );
    }
  }
});

test("declared locales are fr and en", () => {
  assert.deepEqual([...LOCALES].sort(), ["en", "fr"]);
});
