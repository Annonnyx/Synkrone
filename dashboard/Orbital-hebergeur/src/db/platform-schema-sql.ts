/** Columns added after the first drizzle push — applied on boot without drizzle-kit. */
export const PLATFORM_SCHEMA_SQL = `
ALTER TABLE services ADD COLUMN IF NOT EXISTS last_owner_activity_at TIMESTAMPTZ;
ALTER TABLE services ADD COLUMN IF NOT EXISTS suspended_at TIMESTAMPTZ;
ALTER TABLE services ADD COLUMN IF NOT EXISTS inactivity_notified_at TIMESTAMPTZ;
ALTER TABLE services ADD COLUMN IF NOT EXISTS deletion_warned_at TIMESTAMPTZ;
ALTER TABLE services ADD COLUMN IF NOT EXISTS storage_overflow_at TIMESTAMPTZ;
UPDATE services
  SET last_owner_activity_at = NOW()
  WHERE last_owner_activity_at IS NULL;
`;
