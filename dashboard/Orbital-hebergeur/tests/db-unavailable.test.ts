import assert from "node:assert/strict";
import test from "node:test";
import { isDatabaseUnavailable, isUndefinedTable } from "../src/lib/db-errors";

test("connection refused to Postgres is treated as unavailable", () => {
  const cause = Object.assign(new Error("connect ECONNREFUSED 127.0.0.1:5432"), {
    code: "ECONNREFUSED",
  });
  const err = new Error("Failed query: select 1");
  err.cause = cause;
  assert.equal(isDatabaseUnavailable(err), true);
});

test("a normal query error is not a connectivity failure", () => {
  assert.equal(isDatabaseUnavailable(new Error("Failed query: syntax error")), false);
});

test("a missing relation is detected from Postgres 42P01", () => {
  const cause = Object.assign(new Error('relation "site_profiles" does not exist'), {
    code: "42P01",
  });
  const err = new Error(
    'Failed query: select "user_id" from "site_profiles" where "site_profiles"."user_id" = $1',
  );
  err.cause = cause;
  assert.equal(isUndefinedTable(err), true);
  assert.equal(isUndefinedTable(new Error("Failed query: syntax error")), false);
});
