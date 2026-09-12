"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/client";
import { useT } from "@/lib/i18n";

type Channel = { id: string; name: string; type: number };
type Guild = { id: string; name: string };

type BotConfig = {
  guilds: Guild[];
  selectedGuildId: string;
  channels: Channel[];
  stats: {
    uptimeSeconds: number;
    guildCount: number;
    uniqueUsers: number;
    commandsTotal: number;
    commandsMonth: number;
    commandsToday: number;
    updatedAt: string | null;
  };
  welcome: { channel_id: string; embed_title: string; embed_description: string; content_message: string };
  goodbye: { channel_id: string; embed_title: string; embed_description: string; content_message: string };
  embed: { color: string; footer: string; author: string; thumbnail: string; image: string };
  hasToken: boolean;
};

function formatUptime(seconds: number) {
  const s = Math.max(0, Math.floor(seconds || 0));
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  const m = Math.floor((s % 3600) / 60);
  if (d) return `${d} j ${h} h`;
  if (h) return `${h} h ${m} min`;
  return `${m} min`;
}

function ChannelField({
  label,
  value,
  channels,
  onChange,
}: {
  label: string;
  value: string;
  channels: Channel[];
  onChange: (id: string) => void;
}) {
  return (
    <label className="block space-y-1">
      <span className="label">{label}</span>
      {channels.length > 0 ? (
        <select className="input w-full" value={value} onChange={(e) => onChange(e.target.value)}>
          <option value="">—</option>
          {channels.map((ch) => (
            <option key={ch.id} value={ch.id}>
              {ch.name}
            </option>
          ))}
        </select>
      ) : (
        <input
          className="input w-full"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder="ID du salon"
        />
      )}
    </label>
  );
}

export function DiscordGuildConfig({ serviceId }: { serviceId: string }) {
  const t = useT();
  const [data, setData] = useState<BotConfig | null>(null);
  const [guildId, setGuildId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(
    async (nextGuild?: string) => {
      const q = nextGuild ? `?guildId=${encodeURIComponent(nextGuild)}` : "";
      const res = await api<BotConfig>(`/api/services/${serviceId}/bot-config${q}`, { silent: true });
      setData(res);
      setGuildId(res.selectedGuildId || "");
    },
    [serviceId],
  );

  useEffect(() => {
    void load().catch((err: Error) => setError(err.message));
  }, [load]);

  async function save() {
    if (!data || !guildId) return;
    setBusy(true);
    setError("");
    try {
      await api(`/api/services/${serviceId}/bot-config`, {
        method: "PATCH",
        json: {
          guildId,
          welcome: data.welcome,
          goodbye: data.goodbye,
          embed: data.embed,
        },
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function onAvatar(file: File | null) {
    if (!file) return;
    if (file.size > 8 * 1024 * 1024) {
      setError(t("service.avatarTooBig"));
      return;
    }
    const dataUrl = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ""));
      reader.onerror = () => reject(reader.error || new Error("read failed"));
      reader.readAsDataURL(file);
    });
    setBusy(true);
    try {
      await api(`/api/services/${serviceId}/bot-config`, {
        method: "PATCH",
        json: { avatarDataUrl: dataUrl },
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Avatar failed");
    } finally {
      setBusy(false);
    }
  }

  if (!data) {
    return <p className="text-sm text-[var(--muted)]">{t("service.loading")}</p>;
  }

  const stats = data.stats;

  return (
    <div className="space-y-4">
      {error && <p className="text-sm text-[var(--danger)]">{error}</p>}
      <div className="panel p-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <div className="label">{t("service.uptime")}</div>
          <div className="font-medium">{formatUptime(stats.uptimeSeconds)}</div>
        </div>
        <div>
          <div className="label">{t("service.guildCount")}</div>
          <div className="font-medium">{stats.guildCount}</div>
        </div>
        <div>
          <div className="label">{t("service.uniqueUsers")}</div>
          <div className="font-medium">{stats.uniqueUsers}</div>
        </div>
        <div>
          <div className="label">{t("service.commandsRun")}</div>
          <div className="font-medium">
            {stats.commandsTotal} / {stats.commandsMonth} / {stats.commandsToday}
          </div>
        </div>
      </div>

      <div className="panel p-4 space-y-4">
        <label className="block space-y-1">
          <span className="label">{t("service.guild")}</span>
          {data.guilds.length > 0 ? (
            <select
              className="input w-full"
              value={guildId}
              onChange={(e) => {
                const next = e.target.value;
                setGuildId(next);
                void load(next);
              }}
            >
              {data.guilds.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                </option>
              ))}
            </select>
          ) : (
            <input
              className="input w-full"
              value={guildId}
              onChange={(e) => setGuildId(e.target.value)}
              placeholder={t("service.guildIdFallback")}
            />
          )}
        </label>

        <div className="grid gap-3 md:grid-cols-2">
          <ChannelField
            label={t("service.welcomeChannel")}
            value={data.welcome.channel_id}
            channels={data.channels}
            onChange={(id) => setData({ ...data, welcome: { ...data.welcome, channel_id: id } })}
          />
          <ChannelField
            label={t("service.goodbyeChannel")}
            value={data.goodbye.channel_id}
            channels={data.channels}
            onChange={(id) => setData({ ...data, goodbye: { ...data.goodbye, channel_id: id } })}
          />
        </div>

        <label className="block space-y-1">
          <span className="label">{t("service.welcomeMessage")}</span>
          <textarea
            className="input min-h-[5rem] w-full"
            value={data.welcome.content_message}
            onChange={(e) => setData({ ...data, welcome: { ...data.welcome, content_message: e.target.value } })}
          />
        </label>
        <label className="block space-y-1">
          <span className="label">{t("service.goodbyeMessage")}</span>
          <textarea
            className="input min-h-[5rem] w-full"
            value={data.goodbye.content_message}
            onChange={(e) => setData({ ...data, goodbye: { ...data.goodbye, content_message: e.target.value } })}
          />
        </label>

        <div className="grid gap-3 md:grid-cols-2">
          <label className="block space-y-1">
            <span className="label">{t("service.embedColor")}</span>
            <input
              className="input w-full"
              value={data.embed.color}
              onChange={(e) => setData({ ...data, embed: { ...data.embed, color: e.target.value } })}
            />
          </label>
          <label className="block space-y-1">
            <span className="label">{t("service.embedFooter")}</span>
            <input
              className="input w-full"
              value={data.embed.footer}
              onChange={(e) => setData({ ...data, embed: { ...data.embed, footer: e.target.value } })}
            />
          </label>
        </div>

        <label className="block space-y-1">
          <span className="label">{t("service.botAvatar")}</span>
          <input
            type="file"
            accept="image/png,image/jpeg"
            onChange={(e) => void onAvatar(e.target.files?.[0] || null)}
          />
        </label>

        <button className="btn btn-primary" disabled={busy || !guildId} onClick={() => void save()}>
          {t("service.saveGuildConfig")}
        </button>
      </div>
    </div>
  );
}
