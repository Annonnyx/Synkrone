import assert from "node:assert/strict";
import test from "node:test";
import { deleteValidationMessage, validateServiceDelete } from "../src/lib/services/delete-confirm";
import {
  DELETE_WARNING_LEAD_MS,
  IDLE_BEFORE_SUSPEND_MS,
  PAUSE_BEFORE_DELETE_MS,
  deletionDeadline,
  inactivityAction,
  shouldRecordActivity,
} from "../src/lib/services/inactivity";
import { extraBytesWouldExceed, isOverQuota } from "../src/lib/services/storage-quota";

const DAY = 24 * 60 * 60 * 1000;

test("delete requires the exact service name and the disk-gone checkbox", () => {
  assert.deepEqual(validateServiceDelete("My Bot", "My Bot", true), { ok: true });
  assert.equal(validateServiceDelete("My Bot", "my bot", true).ok, false);
  assert.equal(validateServiceDelete("My Bot", "My Bot", false).ok, false);
  const name = validateServiceDelete("My Bot", "My Bot ", true);
  assert.equal(name.ok, false);
  if (!name.ok) {
    assert.equal(name.code, "DELETE_NAME_MISMATCH");
    assert.match(deleteValidationMessage(name.code), /exact service name/i);
  }
});

test("inactivity: 30 days idle suspends even if a container would still be running", () => {
  const now = Date.parse("2026-09-13T12:00:00Z");
  assert.equal(
    inactivityAction({
      now,
      lastOwnerActivityAt: now - IDLE_BEFORE_SUSPEND_MS + DAY,
      suspendedAt: null,
      deletionWarnedAt: null,
    }),
    "none",
  );
  assert.equal(
    inactivityAction({
      now,
      lastOwnerActivityAt: now - IDLE_BEFORE_SUSPEND_MS,
      suspendedAt: null,
      deletionWarnedAt: null,
    }),
    "suspend",
  );
});

test("inactivity: J-3 warn then delete 14 days after pause, resume is the only escape", () => {
  const now = Date.parse("2026-09-13T12:00:00Z");
  const suspendedAt = now - (PAUSE_BEFORE_DELETE_MS - DELETE_WARNING_LEAD_MS);
  assert.equal(
    inactivityAction({
      now,
      lastOwnerActivityAt: now - 40 * DAY,
      suspendedAt,
      deletionWarnedAt: null,
    }),
    "warn-delete",
  );
  assert.equal(
    inactivityAction({
      now,
      lastOwnerActivityAt: now - 40 * DAY,
      suspendedAt,
      deletionWarnedAt: suspendedAt,
    }),
    "none",
  );
  assert.equal(
    inactivityAction({
      now,
      lastOwnerActivityAt: now - 50 * DAY,
      suspendedAt: now - PAUSE_BEFORE_DELETE_MS,
      deletionWarnedAt: now - 4 * DAY,
    }),
    "delete",
  );
  assert.equal(deletionDeadline(suspendedAt), suspendedAt + PAUSE_BEFORE_DELETE_MS);
});

test("creating/deleting services are skipped by the inactivity job", () => {
  const now = Date.now();
  assert.equal(
    inactivityAction({
      now,
      lastOwnerActivityAt: 0,
      suspendedAt: null,
      deletionWarnedAt: null,
      state: "CREATING",
    }),
    "none",
  );
});

test("activity debounce avoids writing on every panel poll", () => {
  const now = 1_000_000;
  assert.equal(shouldRecordActivity(now - 60_000, now), false);
  assert.equal(shouldRecordActivity(now - 6 * 60_000, now), true);
  assert.equal(shouldRecordActivity(null, now), true);
});

test("storage quota is a hard ceiling on extra writes", () => {
  assert.equal(extraBytesWouldExceed(5 * 1024 * 1024, 1024, 5), true);
  assert.equal(extraBytesWouldExceed(4 * 1024 * 1024, 100, 5), false);
  assert.equal(isOverQuota(5.1, 5), true);
  assert.equal(isOverQuota(5, 5), false);
});
