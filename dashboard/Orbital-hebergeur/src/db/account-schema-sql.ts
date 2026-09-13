/** Shared with apps/www/lib/pg-account.js — either process can create these tables. */
export const ACCOUNT_SCHEMA_SQL = `
CREATE TABLE IF NOT EXISTS site_profiles (
  user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  public_id TEXT NOT NULL UNIQUE,
  role TEXT NOT NULL DEFAULT 'Krobi',
  is_team_owner BOOLEAN NOT NULL DEFAULT FALSE,
  last_seen_at TIMESTAMPTZ,
  last_login_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  profile JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS wallets (
  user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  balance INTEGER NOT NULL DEFAULT 0,
  plan TEXT NOT NULL DEFAULT 'Aucun',
  join_bonus_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS wallet_ledger (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  type TEXT NOT NULL,
  amount INTEGER NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  balance_after INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS wallet_ledger_user_at_idx ON wallet_ledger (user_id, at DESC);
`;
