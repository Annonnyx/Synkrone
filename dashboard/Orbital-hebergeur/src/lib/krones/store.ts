import { mkdir, open, readFile, rename, unlink, writeFile } from "node:fs/promises";
import path from "node:path";
import { synkroneRepoRoot } from "@/lib/repo-root";
import { getOAuthAccount } from "@/lib/oauth/accounts";
import { DISCORD_COEFF, MC_COEFF, WEB_COEFF, hostingCost } from "./pricing";

export { DISCORD_COEFF, MC_COEFF, WEB_COEFF, hostingCost };

const LEDGER_CAP = 200;
const LOCK_STALE_MS = 15_000;
const LOCK_WAIT_MS = 10_000;
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

type Store = {
  wallets: Record<string, Wallet>;
  packs: Array<{ id: string; label: string; krones: number }>;
  subscriptions: Array<{ id: string; name: string; krones: number; period: string; perk: string }>;
  minecraft: typeof MC_COEFF;
  discord?: typeof DISCORD_COEFF;
  web?: typeof WEB_COEFF;
};

let writeChain: Promise<unknown> = Promise.resolve();

function withProcessLock<T>(fn: () => Promise<T>): Promise<T> {
  const run = writeChain.then(fn, fn);
  writeChain = run.then(
    () => undefined,
    () => undefined,
  );
  return run;
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function dataPath() {
  return path.join(synkroneRepoRoot(), "apps/www/data/krones.json");
}

function lockPath() {
  return `${dataPath()}.lock`;
}

async function acquireFileLock() {
  const file = lockPath();
  const started = Date.now();
  while (true) {
    try {
      const handle = await open(file, "wx");
      await handle.writeFile(JSON.stringify({ pid: process.pid, at: Date.now() }));
      return handle;
    } catch (err) {
      if ((err as NodeJS.ErrnoException).code !== "EEXIST") throw err;
      try {
        const raw = await readFile(file, "utf8");
        const meta = JSON.parse(raw) as { at?: number };
        if (Date.now() - Number(meta.at || 0) > LOCK_STALE_MS) {
          await unlink(file).catch(() => undefined);
          continue;
        }
      } catch {
        await unlink(file).catch(() => undefined);
        continue;
      }
      if (Date.now() - started > LOCK_WAIT_MS) throw new Error("Krônes: verrou indisponible.");
      await sleep(25);
    }
  }
}

async function withFileLock<T>(fn: () => Promise<T>): Promise<T> {
  return withProcessLock(async () => {
    const handle = await acquireFileLock();
    try {
      return await fn();
    } finally {
      await handle.close().catch(() => undefined);
      await unlink(lockPath()).catch(() => undefined);
    }
  });
}

async function readStore(): Promise<Store> {
  try {
    const raw = await readFile(dataPath(), "utf8");
    const parsed = JSON.parse(raw) as Store;
    return {
      wallets: parsed.wallets && typeof parsed.wallets === "object" ? parsed.wallets : {},
      packs: Array.isArray(parsed.packs) ? parsed.packs : [],
      subscriptions: Array.isArray(parsed.subscriptions) ? parsed.subscriptions : [],
      minecraft: { ...MC_COEFF, ...(parsed.minecraft ?? {}) },
      discord: { ...DISCORD_COEFF, ...(parsed.discord ?? {}) },
      web: { ...WEB_COEFF, ...(parsed.web ?? {}) },
    };
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code !== "ENOENT") throw err;
    return {
      wallets: {},
      packs: [],
      subscriptions: [],
      minecraft: { ...MC_COEFF },
      discord: { ...DISCORD_COEFF },
      web: { ...WEB_COEFF },
    };
  }
}

async function persistStore(store: Store) {
  const file = dataPath();
  await mkdir(path.dirname(file), { recursive: true });
  const tmp = `${file}.${process.pid}.tmp`;
  await writeFile(tmp, JSON.stringify(store, null, 2), "utf8");
  await rename(tmp, file);
}

export async function walletAccountId(userId: string): Promise<string> {
  const discord = await getOAuthAccount(userId, "discord");
  if (discord?.providerAccountId) return discord.providerAccountId;
  return `panel:${userId}`;
}

function ensureWallet(store: Store, id: string): { wallet: Wallet; created: boolean } {
  if (store.wallets[id]) return { wallet: store.wallets[id], created: false };
  store.wallets[id] = { balance: id.startsWith("panel:") ? 2000 : 0, plan: "Aucun", ledger: [] };
  return { wallet: store.wallets[id], created: true };
}

function appendLedger(wallet: Wallet, type: "credit" | "debit", amount: number, reason: string) {
  const entry: LedgerEntry = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    type,
    amount,
    reason: String(reason || "").slice(0, 200),
    at: Date.now(),
    balanceAfter: wallet.balance,
  };
  wallet.ledger = [entry, ...(wallet.ledger ?? [])].slice(0, LEDGER_CAP);
}

export async function getWallet(userId: string) {
  return withFileLock(async () => {
    const store = await readStore();
    const id = await walletAccountId(userId);
    const { wallet, created } = ensureWallet(store, id);
    if (created) await persistStore(store);
    return { id, linkedDiscord: !id.startsWith("panel:"), ...wallet };
  });
}

export async function getCatalog() {
  const store = await readStore();
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
  return withFileLock(async () => {
    const store = await readStore();
    const id = await walletAccountId(userId);
    const { wallet } = ensureWallet(store, id);
    wallet.balance += Math.trunc(amount);
    appendLedger(wallet, "credit", Math.trunc(amount), reason);
    store.wallets[id] = wallet;
    await persistStore(store);
    return wallet;
  });
}

export async function debitWallet(userId: string, amount: number, reason: string) {
  if (!Number.isFinite(amount) || amount <= 0) throw new Error("Montant invalide.");
  return withFileLock(async () => {
    const store = await readStore();
    const id = await walletAccountId(userId);
    const { wallet } = ensureWallet(store, id);
    const cost = Math.trunc(amount);
    if (wallet.balance < cost) {
      const err = new Error("Solde insuffisant.");
      (err as Error & { code?: string; balance?: number }).code = "INSUFFICIENT_KRONES";
      (err as Error & { balance?: number }).balance = wallet.balance;
      throw err;
    }
    wallet.balance -= cost;
    appendLedger(wallet, "debit", cost, reason);
    store.wallets[id] = wallet;
    await persistStore(store);
    return wallet;
  });
}
