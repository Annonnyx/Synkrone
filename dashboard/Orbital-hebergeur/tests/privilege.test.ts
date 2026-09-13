import assert from "node:assert/strict";
import test from "node:test";
import { applyPrivilegePlan, privilegeFromRecord } from "../src/lib/krones/roles";

test("privilegeFromRecord maps site roles without a live database", () => {
  assert.equal(privilegeFromRecord({ isTeamOwner: true, role: "Krobi" }), "admin");
  assert.equal(privilegeFromRecord({ role: "Admin" }), "admin");
  assert.equal(privilegeFromRecord({ role: "Dev" }), "dev");
  assert.equal(privilegeFromRecord({ role: "Équipe" }), "dev");
  assert.equal(privilegeFromRecord({ role: "staff" }), "dev");
  assert.equal(privilegeFromRecord({ role: "Krobi" }), null);
  assert.equal(privilegeFromRecord(null), null);
});

test("dev privilege lifts the plan up to Synkral", () => {
  const wallet = { plan: "Aucun" };
  assert.equal(applyPrivilegePlan(wallet, "dev", ["Aucun", "Kronium", "Synkral", "Kronix"]), true);
  assert.equal(wallet.plan, "Synkral");
  assert.equal(applyPrivilegePlan(wallet, "dev", ["Aucun", "Kronium", "Synkral", "Kronix"]), false);
  assert.equal(applyPrivilegePlan({ plan: "Aucun" }, "admin", ["Aucun", "Synkral"]), false);
});
