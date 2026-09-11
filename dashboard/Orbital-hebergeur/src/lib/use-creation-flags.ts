"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/client";
import type { CreationFlags } from "@/lib/services/creation-flags";

export function useCreationFlags() {
  const [flags, setFlags] = useState<CreationFlags | null>(null);

  useEffect(() => {
    void api<CreationFlags>("/api/platform", { silent: true })
      .then((data) =>
        setFlags({
          discordEnabled: data.discordEnabled !== false,
          minecraftEnabled: data.minecraftEnabled !== false,
          webEnabled: data.webEnabled !== false,
        }),
      )
      .catch(() =>
        setFlags({
          discordEnabled: true,
          minecraftEnabled: true,
          webEnabled: true,
        }),
      );
  }, []);

  return flags;
}
