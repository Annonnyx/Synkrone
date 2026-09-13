export function isDiscordSnowflake(value: string | null | undefined): boolean {
  return /^\d{15,22}$/.test(String(value || "").trim());
}

export function isPlaceholderEmail(email: string | null | undefined): boolean {
  return /@oauth\.synkrone\.local$/i.test(String(email || ""));
}

export function discordIdFromPublicId(publicId: string | null | undefined): string | null {
  const id = String(publicId || "").trim();
  return isDiscordSnowflake(id) ? id : null;
}

export function discordIdFromIdentityRow(
  row: { discordId?: string; siteUserId?: string } | null | undefined,
): string | null {
  if (!row) return null;
  return discordIdFromPublicId(row.discordId) || discordIdFromPublicId(row.siteUserId);
}

export function discordIdFromSiteUser(
  panelUserId: string,
  user: { id?: string; dbId?: string; providers?: { discord?: string } } | null | undefined,
): string | null {
  if (!user) return null;
  const uid = String(panelUserId || "").trim();
  if (!uid) return null;
  if (String(user.dbId || "").trim() !== uid && String(user.id || "").trim() !== uid) return null;
  return (
    discordIdFromPublicId(user.id) || discordIdFromPublicId(user.providers?.discord)
  );
}

export type PanelIdentityPlan =
  | { action: "reuse"; userId: string }
  | { action: "link"; userId: string }
  | { action: "merge"; userId: string; fromUserId: string }
  | { action: "conflict" }
  | { action: "create" };

export function mergeDirection(input: {
  currentUserId: string;
  otherUserId: string;
  currentHasDiscord?: boolean;
  otherHasDiscord?: boolean;
  differentDiscord?: boolean;
}): { into: string; from: string } | { reject: true } {
  const current = String(input.currentUserId || "").trim();
  const other = String(input.otherUserId || "").trim();
  if (!current || !other || current === other) return { into: current || other, from: other };
  if (input.differentDiscord) return { reject: true };
  if (input.otherHasDiscord && !input.currentHasDiscord) {
    return { into: other, from: current };
  }
  return { into: current, from: other };
}

export function planPanelIdentityLink(input: {
  existingOauthUserId?: string | null;
  currentUserId?: string | null;
  currentHasDiscord?: boolean;
  existingHasDiscord?: boolean;
  differentDiscord?: boolean;
}): PanelIdentityPlan {
  const existing = String(input.existingOauthUserId || "").trim();
  const current = String(input.currentUserId || "").trim();
  if (current && existing && existing !== current) {
    const direction = mergeDirection({
      currentUserId: current,
      otherUserId: existing,
      currentHasDiscord: Boolean(input.currentHasDiscord),
      otherHasDiscord: Boolean(input.existingHasDiscord),
      differentDiscord: Boolean(input.differentDiscord),
    });
    if ("reject" in direction) return { action: "conflict" };
    return { action: "merge", userId: direction.into, fromUserId: direction.from };
  }
  if (current) return { action: "link", userId: current };
  if (existing) return { action: "reuse", userId: existing };
  return { action: "create" };
}

export function isPanelUserId(value: string | null | undefined): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
    String(value || "").trim(),
  );
}

export function pickCanonicalUserId(
  candidates: Array<{
    userId: string;
    hasDiscord?: boolean;
    publicIdIsSnowflake?: boolean;
    services?: number;
    wallet?: number;
  }>,
  fallbackUserId?: string | null,
): string | null {
  const ids = candidates.filter((row) => String(row.userId || "").trim());
  if (!ids.length) return String(fallbackUserId || "").trim() || null;
  let best = ids[0];
  let bestScore = -Infinity;
  for (const row of ids) {
    let score = 0;
    if (row.hasDiscord) score += 1000;
    if (row.publicIdIsSnowflake) score += 500;
    score += Math.max(0, Number(row.services) || 0) * 10;
    score += Math.max(0, Number(row.wallet) || 0) / 1000;
    if (fallbackUserId && row.userId === fallbackUserId) score += 1;
    if (score > bestScore) {
      best = row;
      bestScore = score;
    }
  }
  return best.userId;
}

export type IdentityState = {
  users: Record<string, { email: string; name: string }>;
  oauth: Array<{ userId: string; provider: string; providerAccountId: string; email?: string | null }>;
  services: Array<{ id: string; ownerId: string }>;
  wallets: Record<string, number>;
  profiles: Record<string, string>;
  seq?: number;
};

export function mergeIdentityState(
  state: IdentityState,
  fromId: string,
  intoId: string,
  opts?: { preferFromProviders?: string[] },
): IdentityState {
  const from = String(fromId || "").trim();
  const into = String(intoId || "").trim();
  if (!from || !into || from === into) return state;
  if (!state.users[from] || !state.users[into]) return state;
  const next: IdentityState = {
    users: { ...state.users },
    oauth: state.oauth.map((row) => ({ ...row })),
    services: state.services.map((row) => ({ ...row })),
    wallets: { ...state.wallets },
    profiles: { ...state.profiles },
    seq: state.seq,
  };
  const prefer = new Set(opts?.preferFromProviders || []);
  const intoByProvider = new Map(
    next.oauth.filter((row) => row.userId === into).map((row) => [row.provider, row]),
  );
  const moved: typeof next.oauth = [];
  for (const row of next.oauth) {
    if (row.userId !== from) {
      if (row.userId === into && prefer.has(row.provider)) continue;
      moved.push(row);
      continue;
    }
    const existing = intoByProvider.get(row.provider);
    if (existing && !prefer.has(row.provider)) continue;
    moved.push({ ...row, userId: into });
  }
  next.oauth = moved;
  next.services = next.services.map((row) => (row.ownerId === from ? { ...row, ownerId: into } : row));
  next.wallets[into] = Math.max(next.wallets[into] ?? 0, next.wallets[from] ?? 0);
  delete next.wallets[from];
  const fromPublic = next.profiles[from];
  const intoPublic = next.profiles[into];
  if (fromPublic && (!intoPublic || (isDiscordSnowflake(fromPublic) && !isDiscordSnowflake(intoPublic)))) {
    next.profiles[into] = fromPublic;
  }
  delete next.profiles[from];
  const intoEmail = next.users[into].email;
  const fromEmail = next.users[from].email;
  if (isPlaceholderEmail(intoEmail) && fromEmail && !isPlaceholderEmail(fromEmail)) {
    next.users[into] = { ...next.users[into], email: fromEmail };
  }
  delete next.users[from];
  return next;
}

function discordOf(state: IdentityState, userId: string): string | null {
  const oauth = state.oauth.find((row) => row.userId === userId && row.provider === "discord");
  if (oauth && isDiscordSnowflake(oauth.providerAccountId)) return oauth.providerAccountId;
  return discordIdFromPublicId(state.profiles[userId]);
}

function healIdentityState(state: IdentityState, userId: string): { state: IdentityState; userId: string } {
  const seed = String(userId || "").trim();
  if (!seed || !state.users[seed]) return { state, userId: seed };
  const related = new Set<string>([seed]);
  const snowflake = discordOf(state, seed);
  const emails = new Set<string>();
  const seedEmail = String(state.users[seed]?.email || "").trim().toLowerCase();
  if (seedEmail && !isPlaceholderEmail(seedEmail)) emails.add(seedEmail);
  if (snowflake) {
    for (const [id, user] of Object.entries(state.users)) {
      if (discordOf(state, id) === snowflake) related.add(id);
      if (user.email === `discord-${snowflake}@oauth.synkrone.local`) related.add(id);
    }
    for (const [id, publicId] of Object.entries(state.profiles)) {
      if (publicId === snowflake) related.add(id);
    }
  }
  for (const [id, user] of Object.entries(state.users)) {
    const email = String(user.email || "").trim().toLowerCase();
    if (email && emails.has(email)) related.add(id);
  }
  const candidates = [...related]
    .filter((id) => state.users[id])
    .map((id) => ({
      userId: id,
      hasDiscord: Boolean(discordOf(state, id)),
      publicIdIsSnowflake: Boolean(discordIdFromPublicId(state.profiles[id])),
      services: state.services.filter((row) => row.ownerId === id).length,
      wallet: state.wallets[id] ?? 0,
    }));
  const canonical = pickCanonicalUserId(candidates, seed);
  if (!canonical) return { state, userId: seed };
  let next = state;
  for (const id of related) {
    if (id !== canonical) next = mergeIdentityState(next, id, canonical);
  }
  return { state: next, userId: canonical };
}

export function applyOAuthIdentity(
  state: IdentityState,
  input: {
    provider: string;
    providerAccountId: string;
    intent: "login" | "link";
    currentUserId?: string | null;
    email?: string | null;
    emailVerified?: boolean;
    name?: string;
  },
): { state: IdentityState; userId: string; created: boolean } {
  const providerId = String(input.providerAccountId || "").trim();
  const provider = String(input.provider || "").trim();
  const current = String(input.currentUserId || "").trim() || null;
  const email = String(input.email || "").trim().toLowerCase();
  const byProvider = state.oauth.find(
    (row) => row.provider === provider && row.providerAccountId === providerId,
  );
  const currentHasDiscord = current ? Boolean(discordOf(state, current)) : false;
  const existingHasDiscord = byProvider ? Boolean(discordOf(state, byProvider.userId)) : false;
  const currentDiscord = current ? discordOf(state, current) : null;
  const existingDiscord = byProvider ? discordOf(state, byProvider.userId) : null;
  const plan = planPanelIdentityLink({
    existingOauthUserId: byProvider?.userId,
    currentUserId: input.intent === "link" || current ? current : null,
    currentHasDiscord,
    existingHasDiscord,
    differentDiscord: Boolean(currentDiscord && existingDiscord && currentDiscord !== existingDiscord),
  });

  let next = state;
  let userId: string | null = null;
  let created = false;

  if (plan.action === "conflict") {
    const err = new Error("OAUTH_LINKED_OTHER");
    err.name = "OAUTH_LINKED_OTHER";
    throw err;
  }
  if ((input.intent === "link" || current) && !current && plan.action !== "reuse" && plan.action !== "merge") {
    const err = new Error("OAUTH_LINK_REQUIRED");
    err.name = "OAUTH_LINK_REQUIRED";
    throw err;
  }
  if (plan.action === "merge") {
    next = mergeIdentityState(next, plan.fromUserId, plan.userId, { preferFromProviders: [provider] });
    userId = plan.userId;
  } else if (plan.action === "link") {
    userId = plan.userId;
  } else if (plan.action === "reuse") {
    userId = plan.userId;
  } else {
    if (email && input.emailVerified) {
      const byEmail = Object.entries(next.users).find(
        ([, user]) => String(user.email || "").toLowerCase() === email,
      );
      if (byEmail) userId = byEmail[0];
    }
    if (!userId) {
      const seq = (next.seq || 0) + 1;
      userId = `00000000-0000-4000-8000-${String(seq).padStart(12, "0")}`;
      next = {
        ...next,
        seq,
        users: {
          ...next.users,
          [userId]: {
            email: email || `${provider}-${providerId}@oauth.synkrone.local`,
            name: String(input.name || provider),
          },
        },
        wallets: { ...next.wallets, [userId]: next.wallets[userId] ?? 0 },
      };
      created = true;
    }
  }

  if (!userId || !next.users[userId]) {
    const err = new Error("OAUTH_LINK_REQUIRED");
    err.name = "OAUTH_LINK_REQUIRED";
    throw err;
  }

  const without = next.oauth.filter(
    (row) => !(row.userId === userId && row.provider === provider),
  );
  next = {
    ...next,
    oauth: [
      ...without,
      { userId, provider, providerAccountId: providerId, email: email || null },
    ],
  };
  if (provider === "discord" && isDiscordSnowflake(providerId) && !discordIdFromPublicId(next.profiles[userId])) {
    next = { ...next, profiles: { ...next.profiles, [userId]: next.profiles[userId] || providerId } };
  }
  const healed = healIdentityState(next, userId);
  return { state: healed.state, userId: healed.userId, created };
}
