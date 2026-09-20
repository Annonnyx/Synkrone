import assert from "node:assert/strict";
import test from "node:test";
import { parseVolumeOwner } from "../src/lib/runtime/ownership";

test("parseVolumeOwner maps runtime users to volume owners", () => {
  assert.deepEqual(parseVolumeOwner("1000:1000"), { uid: 1000, gid: 1000 });
  assert.deepEqual(parseVolumeOwner("101:101"), { uid: 101, gid: 101 });
  assert.equal(parseVolumeOwner("0:0"), null);
  assert.equal(parseVolumeOwner(undefined), null);
  assert.equal(parseVolumeOwner("not-a-user"), null);
});
