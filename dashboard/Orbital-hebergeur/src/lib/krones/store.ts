import { readFile } from "node:fs/promises";
import path from "node:path";
import { desc, eq } from "drizzle-orm";
import { db, pool } from "@/db";
import { ensureAccountSchema } from "@/db/ensure-schema";
import { walletLedger, wallets } from "@/db/schema";
import { discordIdForUser } from "@/lib/oauth/accounts";
import { isDiscordSnowflake } from "@/lib/oauth/identity-link";
import { synkroneRepoRoot } from "@/lib/repo-root";
import { DISCORD_COEFF, MC_COEFF, WEB_COEFF, hostingCost } from "./pricing";
import {
  applyPrivilegePlan,
  LOW_BALANCE,
  resolveKronesPrivilege,
  type KronesPrivilege,
} from "./privilege";

export { DISCORD_COEFF, MC_COEFF, WEB_COEFF, hostingCost };

const LEDGER_CAP = 200;
export const GRADE_ORDER = ["Aucun", "Kronium", "Synkral", "Kronalloy", "Synkronite", "Kronix"];

export type LedgerEntry = {
  id: string;
  type: "credit" | "debit";
  amount: number;
  reason: string;
  at: number;
  balanceAfter: number;
};

export type Wallet = {
  balance: number;
  plan: string;
  ledger: LedgerEntry[];
};

type CatalogStore = {
  packs: Array<{ id: string; label: string; krones: number }>;
  subscriptions: Array<{ id: string; name: string; krones: number; period: string; perk: string }>;
  minecraft: typeof MC_COEFF;
  discord?: typeof DISCORD_COEFF;
  web?: typeof WEB_COEFF;
};

const JOIN_BONUS = 100;
const JOIN_BONUS_REASON = "discord:join";

async function isGuildMember(discordId: string) {
  const token = String(process.env.DISCORD_BOT_TOKEN || "").trim();
  const guildId = String(process.env.DISCORD_GUILD_ID || "").trim();
  if (!token || !guildId || !isDiscordSnowflake(discordId)) return false;
  try {
    const res = await fetch(`https://discord.com/api/v10/guilds/${guildId}/members/${discordId}`, {
      headers: { Authorization: `Bot ${token}` },
      signal: AbortSignal.timeout(2000),
    });
    return res.ok;
  } catch {
    return false;
  }
}

function dataPath() {
  return path.join(synkroneRepoRoot(), "apps/www/data/krones.json");
}

async function readCatalog(): Promise<CatalogStore> {
  try {
    const raw = await readFile(dataPath(), "utf8");
    const parsed = JSON.parse(raw) as CatalogStore;
    return {
      packs: Array.isArray(parsed.packs) ? parsed.packs : [],
      subscriptions: Array.isArray(parsed.subscriptions) ? parsed.subscriptions : [],
      minecraft: { ...MC_COEFF, ...(parsed.minecraft ?? {}) },
      discord: { ...DISCORD_COEFF, ...(parsed.discord ?? {}) },
      web: { ...WEB_COEFF, ...(parsed.web ?? {}) },
    };
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code !== "ENOENT") throw err;
    return {
      packs: [],
      subscriptions: [],
      minecraft: { ...MC_COEFF },
      discord: { ...DISCORD_COEFF },
      web: { ...WEB_COEFF },
    };
  }
}

function appendLedgerLocal(
  type: "credit" | "debit",
  amount: number,
  reason: string,
  balanceAfter: number,
): LedgerEntry {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    type,
    amount,
    reason: String(reason || "").slice(0, 200),
    at: Date.now(),
    balanceAfter,
  };
}

async function loadLedger(userId: string): Promise<LedgerEntry[]> {
  const rows = await db
    .select()
    .from(walletLedger)
    .where(eq(walletLedger.userId, userId))
    .orderBy(desc(walletLedger.at))
    .limit(LEDGER_CAP);
  return rows.map((row) => ({
    id: row.id,
    type: row.type === "debit" ? "debit" : "credit",
    amount: row.amount,
    reason: row.reason,
    at: row.at.getTime(),
    balanceAfter: row.balanceAfter,
  }));
}

async function trimLedger(client: { query: (sql: string, params?: unknown[]) => Promise<unknown> }, userId: string) {
  await client.query(
    `DELETE FROM wallet_ledger
     WHERE user_id = $1 AND id NOT IN (
       SELECT id FROM wallet_ledger WHERE user_id = $1 ORDER BY at DESC LIMIT $2
     )`,
    [userId, LEDGER_CAP],
  );
}

async function ensureWalletRow(userId: string) {
  await ensureAccountSchema();
  await db
    .insert(wallets)
    .values({ userId, balance: 0, plan: "Aucun" })
    .onConflictDoNothing({ target: wallets.userId });
}

function walletView(
  userId: string,
  wallet: { balance: number; plan: string },
  ledger: LedgerEntry[],
  privilege: KronesPrivilege,
  discordId: string | null,
) {
  const unlimited = privilege === "admin";
  return {
    id: discordId || userId,
    linkedDiscord: Boolean(discordId),
    balance: wallet.balance,
    plan: wallet.plan,
    ledger,
    unlimited,
    privilege,
    shopUrl: "/krones",
    lowBalance: !unlimited && wallet.balance < LOW_BALANCE,
  };
}

/** Same Postgres user as the site — the panel UUID. */
export async function walletAccountId(userId: string): Promise<string> {
  return userId;
}

export async function getWallet(userId: string) {
  await ensureAccountSchema();
  const privilege = await resolveKronesPrivilege(userId);
  const discordId = await discordIdForUser(userId);
  await ensureWalletRow(userId);
  const [row] = await db.select().from(wallets).where(eq(wallets.userId, userId)).limit(1);
  let plan = row?.plan || "Aucun";
  let balance = row?.balance ?? 0;
  let joinBonusAt = row?.joinBonusAt ?? null;
  const planWallet = { plan };
  const planChanged = applyPrivilegePlan(planWallet, privilege, GRADE_ORDER);
  if (planChanged) {
    plan = planWallet.plan;
    await db.update(wallets).set({ plan, updatedAt: new Date() }).where(eq(wallets.userId, userId));
  }
  const canClaim = !joinBonusAt && discordId && (await isGuildMember(discordId));
  if (canClaim) {
    const client = await pool.connect();
    try {
      await client.query("BEGIN");
      const locked = await client.query<{ balance: number; join_bonus_at: Date | null }>(
        "SELECT balance, join_bonus_at FROM wallets WHERE user_id = $1 FOR UPDATE",
        [userId],
      );
      const current = locked.rows[0];
      if (current && !current.join_bonus_at) {
        balance = Number(current.balance || 0) + JOIN_BONUS;
        const entry = appendLedgerLocal("credit", JOIN_BONUS, JOIN_BONUS_REASON, balance);
        await client.query(
          "UPDATE wallets SET balance = $2, join_bonus_at = NOW(), updated_at = NOW() WHERE user_id = $1",
          [userId, balance],
        );
        await client.query(
          `INSERT INTO wallet_ledger (id, user_id, type, amount, reason, at, balance_after)
           VALUES ($1, $2, $3, $4, $5, NOW(), $6)`,
          [entry.id, userId, entry.type, entry.amount, entry.reason, entry.balanceAfter],
        );
        await trimLedger(client, userId);
        joinBonusAt = new Date();
      }
      await client.query("COMMIT");
    } catch (err) {
      await client.query("ROLLBACK");
      throw err;
    } finally {
      client.release();
    }
  }
  const ledger = await loadLedger(userId);
  return walletView(userId, { balance, plan }, ledger, privilege, discordId);
}

export async function getCatalog() {
  const store = await readCatalog();
  return {
    unit: "Krônes",
    packs: store.packs,
    subscriptions: store.subscriptions,
    minecraft: store.minecraft,
    discord: store.discord ?? DISCORD_COEFF,
    web: store.web ?? WEB_COEFF,
  };
}

export function allowOpenCredit() {
  return process.env.NODE_ENV !== "production" || process.env.SYNKRONE_KRONES_DEMO === "1";
}

export async function creditWallet(userId: string, amount: number, reason: string) {
  if (!Number.isFinite(amount) || amount <= 0) throw new Error("Montant invalide.");
  const parsed = Math.trunc(amount);
  await ensureWalletRow(userId);
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    const locked = await client.query<{ balance: number; plan: string }>(
      "SELECT balance, plan FROM wallets WHERE user_id = $1 FOR UPDATE",
      [userId],
    );
    const current = locked.rows[0] || { balance: 0, plan: "Aucun" };
    const balance = Number(current.balance || 0) + parsed;
    const entry = appendLedgerLocal("credit", parsed, reason, balance);
    await client.query("UPDATE wallets SET balance = $2, updated_at = NOW() WHERE user_id = $1", [
      userId,
      balance,
    ]);
    await client.query(
      `INSERT INTO wallet_ledger (id, user_id, type, amount, reason, at, balance_after)
       VALUES ($1, $2, $3, $4, $5, NOW(), $6)`,
      [entry.id, userId, entry.type, entry.amount, entry.reason, entry.balanceAfter],
    );
    await trimLedger(client, userId);
    await client.query("COMMIT");
    return { balance, plan: current.plan, ledger: await loadLedger(userId) };
  } catch (err) {
    await client.query("ROLLBACK");
    throw err;
  } finally {
    client.release();
  }
}

export async function debitWallet(userId: string, amount: number, reason: string) {
  if (!Number.isFinite(amount) || amount <= 0) throw new Error("Montant invalide.");
  const privilege = await resolveKronesPrivilege(userId);
  const parsed = Math.trunc(amount);
  await ensureWalletRow(userId);
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    const locked = await client.query<{ balance: number; plan: string }>(
      "SELECT balance, plan FROM wallets WHERE user_id = $1 FOR UPDATE",
      [userId],
    );
    const current = locked.rows[0] || { balance: 0, plan: "Aucun" };
    const planWallet = { plan: current.plan };
    applyPrivilegePlan(planWallet, privilege, GRADE_ORDER);
    if (privilege === "admin") {
      await client.query("UPDATE wallets SET plan = $2, updated_at = NOW() WHERE user_id = $1", [
        userId,
        planWallet.plan,
      ]);
      await client.query("COMMIT");
      return { balance: Number(current.balance || 0), plan: planWallet.plan, ledger: await loadLedger(userId) };
    }
    const balance = Number(current.balance || 0);
    if (balance < parsed) {
      const err = new Error("Solde insuffisant.") as Error & { code?: string; balance?: number };
      err.code = "INSUFFICIENT_KRONES";
      err.balance = balance;
      throw err;
    }
    const next = balance - parsed;
    const entry = appendLedgerLocal("debit", parsed, reason, next);
    await client.query(
      "UPDATE wallets SET balance = $2, plan = $3, updated_at = NOW() WHERE user_id = $1",
      [userId, next, planWallet.plan],
    );
    await client.query(
      `INSERT INTO wallet_ledger (id, user_id, type, amount, reason, at, balance_after)
       VALUES ($1, $2, $3, $4, $5, NOW(), $6)`,
      [entry.id, userId, entry.type, entry.amount, entry.reason, entry.balanceAfter],
    );
    await trimLedger(client, userId);
    await client.query("COMMIT");
    return { balance: next, plan: planWallet.plan, ledger: await loadLedger(userId) };
  } catch (err) {
    await client.query("ROLLBACK");
    throw err;
  } finally {
    client.release();
  }
}
