import { pool } from "@/db";
import { ensureAccountSchema } from "@/db/ensure-schema";
import { isPlaceholderEmail, isPanelUserId } from "./identity-link";

const GRADE_ORDER = ["Aucun", "Kronium", "Synkral", "Kronalloy", "Synkronite", "Kronix"];

type Queryable = { query: (sql: string, params?: unknown[]) => Promise<{ rows: Array<Record<string, unknown>> }> };

function pickPlan(a: string, b: string): string {
  const ia = GRADE_ORDER.indexOf(String(a || "Aucun"));
  const ib = GRADE_ORDER.indexOf(String(b || "Aucun"));
  return GRADE_ORDER[Math.max(ia, ib, 0)] || "Aucun";
}

async function tableExists(client: Queryable, name: string): Promise<boolean> {
  const found = await client.query(`SELECT to_regclass($1) AS rel`, [`public.${name}`]);
  return Boolean(found.rows[0]?.rel);
}

async function userExists(client: Queryable, userId: string): Promise<boolean> {
  const found = await client.query(`SELECT id FROM users WHERE id = $1 LIMIT 1`, [userId]);
  return Boolean(found.rows[0]?.id);
}

/**
 * Absorb `fromId` into `intoId` (oauth, services, wallet max not sum, site profile).
 * Keeps `intoId`. Safe no-op when ids match or a side is missing.
 *
 * One-shot recovery if a split is already in prod and the user cannot log in with Discord:
 *   -- preview
 *   SELECT id, email, name FROM users;
 *   SELECT user_id, provider, provider_account_id FROM oauth_accounts;
 *   SELECT owner_id, name FROM services;
 *   SELECT user_id, balance FROM wallets;
 *   SELECT user_id, public_id FROM site_profiles;
 * Next Discord login / Google-GitHub link runs this merge automatically when identities overlap.
 */
export async function mergePanelUsersWithClient(
  client: Queryable,
  fromId: string,
  intoId: string,
  opts?: { preferFromProviders?: string[] },
): Promise<string> {
  const from = String(fromId || "").trim();
  const into = String(intoId || "").trim();
  if (!from || !into || from === into) return into || from;
  if (!(await userExists(client, from)) || !(await userExists(client, into))) return into;

  const prefer = new Set(opts?.preferFromProviders || []);

  if (await tableExists(client, "oauth_accounts")) {
    const intoOauth = await client.query(
      `SELECT id, provider, provider_account_id FROM oauth_accounts WHERE user_id = $1`,
      [into],
    );
    const fromOauth = await client.query(
      `SELECT id, provider, provider_account_id FROM oauth_accounts WHERE user_id = $1`,
      [from],
    );
    const intoByProvider = new Map(
      intoOauth.rows.map((row) => [String(row.provider), row]),
    );
    for (const row of fromOauth.rows) {
      const provider = String(row.provider);
      const existing = intoByProvider.get(provider);
      if (existing && prefer.has(provider)) {
        await client.query(`DELETE FROM oauth_accounts WHERE id = $1`, [existing.id]);
        await client.query(`UPDATE oauth_accounts SET user_id = $2, updated_at = NOW() WHERE id = $1`, [
          row.id,
          into,
        ]);
      } else if (existing) {
        await client.query(`DELETE FROM oauth_accounts WHERE id = $1`, [row.id]);
      } else {
        await client.query(`UPDATE oauth_accounts SET user_id = $2, updated_at = NOW() WHERE id = $1`, [
          row.id,
          into,
        ]);
      }
    }
  }

  if (await tableExists(client, "services")) {
    await client.query(`UPDATE services SET owner_id = $2 WHERE owner_id = $1`, [from, into]);
  }
  if (await tableExists(client, "projects")) {
    await client.query(`UPDATE projects SET owner_id = $2 WHERE owner_id = $1`, [from, into]);
  }
  if (await tableExists(client, "project_members")) {
    await client.query(
      `DELETE FROM project_members a
       USING project_members b
       WHERE a.user_id = $1 AND b.user_id = $2 AND a.project_id = b.project_id`,
      [from, into],
    );
    await client.query(`UPDATE project_members SET user_id = $2 WHERE user_id = $1`, [from, into]);
  }
  if (await tableExists(client, "sessions")) {
    await client.query(`UPDATE sessions SET user_id = $2 WHERE user_id = $1`, [from, into]);
  }
  if (await tableExists(client, "service_databases")) {
    await client.query(`UPDATE service_databases SET owner_id = $2 WHERE owner_id = $1`, [from, into]);
  }
  if (await tableExists(client, "api_keys")) {
    await client.query(`UPDATE api_keys SET user_id = $2 WHERE user_id = $1`, [from, into]);
  }
  if (await tableExists(client, "webhooks")) {
    await client.query(`UPDATE webhooks SET user_id = $2 WHERE user_id = $1`, [from, into]);
  }
  if (await tableExists(client, "audit_logs")) {
    await client.query(`UPDATE audit_logs SET user_id = $2 WHERE user_id = $1`, [from, into]);
  }
  if (await tableExists(client, "jobs")) {
    await client.query(`UPDATE jobs SET user_id = $2 WHERE user_id = $1`, [from, into]);
  }

  if (await tableExists(client, "wallets")) {
    await client.query(
      `INSERT INTO wallets (user_id, balance, plan, join_bonus_at, updated_at)
       VALUES ($1, 0, 'Aucun', NULL, NOW())
       ON CONFLICT (user_id) DO NOTHING`,
      [into],
    );
    await client.query(
      `INSERT INTO wallets (user_id, balance, plan, join_bonus_at, updated_at)
       VALUES ($1, 0, 'Aucun', NULL, NOW())
       ON CONFLICT (user_id) DO NOTHING`,
      [from],
    );
    const a = await client.query(
      `SELECT balance, plan, join_bonus_at FROM wallets WHERE user_id = $1 FOR UPDATE`,
      [from],
    );
    const b = await client.query(
      `SELECT balance, plan, join_bonus_at FROM wallets WHERE user_id = $1 FOR UPDATE`,
      [into],
    );
    const fromBal = Math.max(0, Math.trunc(Number(a.rows[0]?.balance) || 0));
    const intoBal = Math.max(0, Math.trunc(Number(b.rows[0]?.balance) || 0));
    const plan = pickPlan(String(a.rows[0]?.plan || "Aucun"), String(b.rows[0]?.plan || "Aucun"));
    const join =
      fromBal >= intoBal
        ? a.rows[0]?.join_bonus_at || b.rows[0]?.join_bonus_at || null
        : b.rows[0]?.join_bonus_at || a.rows[0]?.join_bonus_at || null;
    await client.query(
      `UPDATE wallets SET balance = $2, plan = $3, join_bonus_at = $4, updated_at = NOW() WHERE user_id = $1`,
      [into, Math.max(fromBal, intoBal), plan, join],
    );
    await client.query(`DELETE FROM wallets WHERE user_id = $1`, [from]);
  }
  if (await tableExists(client, "wallet_ledger")) {
    await client.query(`UPDATE wallet_ledger SET user_id = $2 WHERE user_id = $1`, [from, into]);
  }

  if (await tableExists(client, "site_profiles")) {
    const fromProfile = await client.query(`SELECT * FROM site_profiles WHERE user_id = $1 LIMIT 1`, [from]);
    const intoProfile = await client.query(`SELECT * FROM site_profiles WHERE user_id = $1 LIMIT 1`, [into]);
    const fromPublic = String(fromProfile.rows[0]?.public_id || "");
    const intoPublic = String(intoProfile.rows[0]?.public_id || "");
    const preferPublic =
      /^\d{15,22}$/.test(fromPublic) && !/^\d{15,22}$/.test(intoPublic) ? fromPublic : intoPublic || fromPublic;
    if (fromProfile.rows[0]) {
      await client.query(
        `UPDATE site_profiles SET public_id = $2, updated_at = NOW() WHERE user_id = $1`,
        [from, `merged:${from}`],
      );
    }
    if (intoProfile.rows[0] && preferPublic && preferPublic !== intoPublic) {
      await client.query(
        `UPDATE site_profiles SET public_id = $2, updated_at = NOW() WHERE user_id = $1`,
        [into, preferPublic],
      );
    } else if (!intoProfile.rows[0] && fromProfile.rows[0]) {
      await client.query(
        `UPDATE site_profiles SET user_id = $2, public_id = $3, updated_at = NOW() WHERE user_id = $1`,
        [from, into, preferPublic || fromPublic],
      );
    }
    await client.query(`DELETE FROM site_profiles WHERE user_id = $1`, [from]);
  }

  const emails = await client.query(`SELECT id, email FROM users WHERE id = ANY($1::text[])`, [[from, into]]);
  const fromUser = emails.rows.find((row) => row.id === from);
  const intoUser = emails.rows.find((row) => row.id === into);
  const fromEmail = String(fromUser?.email || "");
  const intoEmail = String(intoUser?.email || "");
  if (isPlaceholderEmail(intoEmail) && fromEmail && !isPlaceholderEmail(fromEmail)) {
    try {
      await client.query(`UPDATE users SET email = $2 WHERE id = $1`, [into, fromEmail]);
    } catch {
      /* unique email on a third row — keep into as-is */
    }
  }

  await client.query(`DELETE FROM users WHERE id = $1`, [from]);
  return into;
}

export async function mergePanelUsers(
  fromId: string,
  intoId: string,
  opts?: { preferFromProviders?: string[] },
): Promise<string> {
  const from = String(fromId || "").trim();
  const into = String(intoId || "").trim();
  if (!isPanelUserId(from) || !isPanelUserId(into) || from === into) return into || from;
  await ensureAccountSchema();
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    const kept = await mergePanelUsersWithClient(client, from, into, opts);
    await client.query("COMMIT");
    return kept;
  } catch (err) {
    await client.query("ROLLBACK");
    throw err;
  } finally {
    client.release();
  }
}
