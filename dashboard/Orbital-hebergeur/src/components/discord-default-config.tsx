"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/client";
import { useT } from "@/lib/i18n";
import { ALLOW_KEYS, MODULES, defaultConfig, type DefaultConfig } from "@/lib/discord/custom-config";

const ALLOW_I18N: Record<(typeof ALLOW_KEYS)[number], string> = {
  displayName: "customAllowDisplayName",
  avatar: "customAllowAvatar",
  embedColor: "customAllowEmbedColor",
  embedPalette: "customAllowPalette",
  embedLogo: "customAllowLogo",
  embedFooter: "customAllowFooter",
  font: "customAllowFont",
  whiteLabel: "customAllowWhiteLabel",
  texts: "customAllowTexts",
  channels: "customAllowChannels",
  roles: "customAllowRoles",
  modules: "customAllowModules",
  cooldowns: "customAllowCooldowns",
  commandPerms: "customAllowCommandPerms",
};

const MODULE_I18N: Record<(typeof MODULES)[number]["id"], string> = {
  welcome: "customModWelcome",
  goodbye: "customModGoodbye",
  logs: "customModLogs",
  tickets: "customModTickets",
  mute: "customModMute",
};

export function DiscordDefaultConfig({ serviceId }: { serviceId: string }) {
  const t = useT();
  const [data, setData] = useState<DefaultConfig | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [ok, setOk] = useState(false);

  const load = useCallback(async () => {
    const res = await api<{ defaults: DefaultConfig }>(`/api/services/${serviceId}/bot-config`, { silent: true });
    setData(res.defaults || defaultConfig());
  }, [serviceId]);

  useEffect(() => {
    void load().catch((err: Error) => setError(err.message));
  }, [load]);

  async function save() {
    if (!data) return;
    setBusy(true);
    setError("");
    setOk(false);
    try {
      await api(`/api/services/${serviceId}/bot-config`, { method: "PATCH", json: { defaults: data } });
      setOk(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  if (!data) {
    return <p className="text-sm text-[var(--muted)]">{t("service.loading")}</p>;
  }

  return (
    <div className="panel space-y-4 p-4">
      <div>
        <div className="label">{t("service.customDefaultTitle")}</div>
        <p className="mt-1 text-sm leading-relaxed text-[var(--muted)]">{t("service.customDefaultHint")}</p>
      </div>
      {error && <p className="text-sm text-[var(--danger)]">{error}</p>}
      {ok && <p className="text-sm text-[var(--muted)]">{t("service.customDefaultSaved")}</p>}

      <div className="grid gap-3 md:grid-cols-2">
        <label className="block space-y-1">
          <span className="label">{t("service.customDefaultName")}</span>
          <input
            className="input w-full"
            maxLength={32}
            value={data.identity.displayName}
            onChange={(e) => setData({ ...data, identity: { ...data.identity, displayName: e.target.value } })}
          />
        </label>
        <label className="block space-y-1">
          <span className="label">{t("service.embedColor")}</span>
          <div className="flex gap-2">
            <input
              type="color"
              className="h-10 w-12 cursor-pointer border border-[var(--line)] bg-transparent"
              value={/^#[0-9a-fA-F]{6}$/.test(data.identity.embedColor) ? data.identity.embedColor : "#660099"}
              onChange={(e) => setData({ ...data, identity: { ...data.identity, embedColor: e.target.value } })}
            />
            <input
              className="input w-full"
              value={data.identity.embedColor}
              onChange={(e) => setData({ ...data, identity: { ...data.identity, embedColor: e.target.value } })}
            />
          </div>
        </label>
        <label className="block space-y-1">
          <span className="label">{t("service.customActivityType")}</span>
          <select
            className="select w-full"
            value={data.identity.activityType}
            onChange={(e) => setData({ ...data, identity: { ...data.identity, activityType: e.target.value } })}
          >
            {["playing", "watching", "listening", "streaming", "competing"].map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <label className="block space-y-1">
          <span className="label">{t("service.customActivityText")}</span>
          <input
            className="input w-full"
            value={data.identity.activityText}
            onChange={(e) => setData({ ...data, identity: { ...data.identity, activityText: e.target.value } })}
          />
        </label>
      </div>
      <label className="block space-y-1">
        <span className="label">{t("service.embedFooter")}</span>
        <input
          className="input w-full"
          value={data.identity.embedFooter}
          onChange={(e) => setData({ ...data, identity: { ...data.identity, embedFooter: e.target.value } })}
        />
      </label>

      <div>
        <div className="label mb-2">{t("service.customAllowTitle")}</div>
        <p className="mb-3 text-sm text-[var(--muted)]">{t("service.customAllowHint")}</p>
        <div className="grid gap-2">
          {ALLOW_KEYS.map((key) => (
            <label key={key} className="flex items-center justify-between gap-3 text-sm">
              <span>{t(`service.${ALLOW_I18N[key]}`)}</span>
              <input
                type="checkbox"
                checked={data.allow[key]}
                onChange={(e) => setData({ ...data, allow: { ...data.allow, [key]: e.target.checked } })}
              />
            </label>
          ))}
        </div>
      </div>

      <div>
        <div className="label mb-2">{t("service.customInstallTitle")}</div>
        <div className="space-y-3">
          {MODULES.map((mod) => (
            <div key={mod.id} className="grid gap-2 md:grid-cols-2">
              <label className="block space-y-1">
                <span className="label">{t(`service.${MODULE_I18N[mod.id]}`)}</span>
                <select
                  className="select w-full"
                  value={data.install[mod.id]?.provision || "manual"}
                  onChange={(e) =>
                    setData({
                      ...data,
                      install: {
                        ...data.install,
                        [mod.id]: {
                          ...data.install[mod.id],
                          provision: e.target.value === "auto" ? "auto" : "manual",
                        },
                      },
                    })
                  }
                >
                  <option value="manual">{t("service.customProvisionManual")}</option>
                  <option value="auto">{t("service.customProvisionAuto")}</option>
                </select>
              </label>
              <label className="block space-y-1">
                <span className="label">{t("service.customAutoName")}</span>
                <input
                  className="input w-full"
                  value={data.install[mod.id]?.autoName || mod.autoName}
                  onChange={(e) =>
                    setData({
                      ...data,
                      install: {
                        ...data.install,
                        [mod.id]: { ...data.install[mod.id], autoName: e.target.value },
                      },
                    })
                  }
                />
              </label>
            </div>
          ))}
        </div>
      </div>

      <div>
        <div className="label mb-2">{t("service.customModulesDefault")}</div>
        <div className="grid gap-2">
          {MODULES.map((mod) => (
            <label key={mod.id} className="flex items-center justify-between gap-3 text-sm">
              <span>
                {t(`service.${MODULE_I18N[mod.id]}`)} — {t("service.customModuleOn")}
              </span>
              <input
                type="checkbox"
                checked={data.modules[mod.id]?.enabled !== false}
                onChange={(e) =>
                  setData({
                    ...data,
                    modules: { ...data.modules, [mod.id]: { enabled: e.target.checked } },
                  })
                }
              />
            </label>
          ))}
        </div>
      </div>

      <label className="block space-y-1">
        <span className="label">{t("service.customQuota")}</span>
        <input
          className="input w-full"
          type="number"
          min={0}
          max={100}
          value={data.limits.autoCreatedMax}
          onChange={(e) =>
            setData({
              ...data,
              limits: { ...data.limits, autoCreatedMax: Number(e.target.value) || 0 },
            })
          }
        />
      </label>

      <button className="btn btn-primary" disabled={busy} onClick={() => void save()}>
        {t("service.saveDefaultConfig")}
      </button>
    </div>
  );
}
