import assert from "node:assert/strict";
import test from "node:test";
import { isDatabaseUnavailable } from "../src/lib/db-errors";

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
