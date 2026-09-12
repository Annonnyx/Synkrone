import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import test from "node:test";

test("panel session lasts three weeks", () => {
  const source = readFileSync(path.join(process.cwd(), "src/lib/auth.ts"), "utf8");
  assert.match(source, /24 \* 21/);
});
