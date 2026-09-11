"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/client";
import { useI18n, useT } from "@/lib/i18n";
import { usePoll } from "@/lib/use-poll";
import { ErrorText } from "@/components/panel";
import { PageHeader } from "@/components/ui";
import { Table, Td, Th } from "@/components/ui/table";

type Wallet = {
  balance: number;
  plan: string;
  linkedDiscord: boolean;
  ledger: Array<{ id: string; type: string; amount: number; reason: string; at: number; balanceAfter: number }>;
};

type Catalog = {
  packs: Array<{ id: string; label: string; krones: number }>;
  subscriptions: Array<{ id: string; name: string; krones: number; perk: string }>;
};

export default function KronesPage() {
  const t = useT();
  const { locale } = useI18n();
  const [wallet, setWallet] = useState<Wallet | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [w, c] = await Promise.all([
        api<Wallet>("/api/krones", { silent: true }),
        api<Catalog>("/api/krones/catalog", { silent: true }),
      ]);
      setWallet(w);
      setCatalog(c);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  usePoll(load, 15000);

  const credit = async (amount: number, reason: string) => {
    await api("/api/krones/credit", { json: { amount, reason } });
    await load();
  };

  const loc = locale === "en" ? "en-GB" : "fr-FR";

  return (
    <div>
      <PageHeader title={t("krones.title")} subtitle={t("krones.subtitle")} />
      <ErrorText error={error} />
      <div className="mb-6 grid gap-3 md:grid-cols-3">
        <div className="panel p-4">
          <div className="label">{t("krones.balance")}</div>
          <div className="mt-1 font-serif text-3xl text-[var(--gold)]">
            {(wallet?.balance ?? 0).toLocaleString(loc)} ₭
          </div>
          <p className="hint mt-1">{t("krones.plan", { name: wallet?.plan || t("common.none") })}</p>
        </div>
        <div className="panel p-4">
          <div className="label">{t("krones.identity")}</div>
          <p className="mt-2 text-sm leading-relaxed text-[var(--muted)]">
            {wallet?.linkedDiscord ? t("krones.linked") : t("krones.unlinked")}
          </p>
          {!wallet?.linkedDiscord && (
            <Link href="/dashboard/account/profile" className="btn mt-3">
              {t("krones.linkDiscord")}
            </Link>
          )}
        </div>
        <div className="panel p-4">
          <div className="label">{t("krones.publicSite")}</div>
          <p className="mt-2 text-sm leading-relaxed text-[var(--muted)]">{t("krones.publicHint")}</p>
        </div>
      </div>

      <div className="mb-6">
        <h2 className="mb-3 text-sm font-semibold">{t("krones.packs")}</h2>
        <div className="flex flex-wrap gap-2">
          {(catalog?.packs ?? []).map((pack) => (
            <button
              key={pack.id}
              type="button"
              className="btn"
              onClick={() => void credit(pack.krones, `pack:${pack.id}`)}
            >
              {pack.label} · {pack.krones.toLocaleString(loc)} ₭
            </button>
          ))}
        </div>
      </div>

      <h2 className="mb-3 text-sm font-semibold">{t("krones.ledger")}</h2>
      <div className="panel p-0">
        <Table>
          <thead>
            <tr>
              <Th>{t("krones.date")}</Th>
              <Th>{t("krones.type")}</Th>
              <Th>{t("krones.amount")}</Th>
              <Th>{t("krones.reason")}</Th>
              <Th>{t("krones.balance")}</Th>
            </tr>
          </thead>
          <tbody>
            {(wallet?.ledger ?? []).slice(0, 30).map((row) => (
              <tr key={row.id}>
                <Td>{new Date(row.at).toLocaleString(loc)}</Td>
                <Td>{row.type}</Td>
                <Td>{row.amount.toLocaleString(loc)}</Td>
                <Td>{row.reason}</Td>
                <Td>{row.balanceAfter.toLocaleString(loc)}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
        {(wallet?.ledger ?? []).length === 0 && (
          <p className="hint px-3 py-4">{t("krones.empty")}</p>
        )}
      </div>
    </div>
  );
}
