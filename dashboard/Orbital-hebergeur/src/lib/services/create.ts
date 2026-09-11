import { eq } from "drizzle-orm";
import { db } from "@/db";
import {
  discordBots,
  domains,
  envVars,
  minecraftServers,
  projects,
  services,
  webProjects,
} from "@/db/schema";
import { encryptSecret, fingerprint, shortId, slugify } from "@/lib/crypto";
import { audit } from "@/lib/audit";
import { createJob, dispatch } from "@/lib/jobs/queue";
import { PROVISION_STEPS, provisionService } from "@/lib/jobs/handlers";
import { allocateBedrockPort, allocateMinecraftPort, allocateWebPort } from "@/lib/ports";
import {
  MINECRAFT_SOFTWARE,
  resolveGatewayIntents,
  type WebTemplateId,
} from "@/lib/runtime/templates";
import { DEFAULT_PROPERTIES } from "@/lib/runtime/minecraft";
import { normalizeProperties } from "@/lib/minecraft/properties";
import { applicationIdFromToken, isDiscordToken } from "@/lib/discord/token";
import { SFTPManager } from "@/lib/sftp/manager";
import { defaultMaxRestarts, defaultRestartPolicy } from "@/lib/services/defaults";
import type { ServiceType } from "@/lib/paths";
import { HttpError } from "@/lib/auth";
import { publicBaseDomain, suggestedHostname } from "@/lib/domains/public";
import { syncTraefikConfig } from "@/lib/domains/traefik";
import { assertGithubRepoAccess } from "@/lib/oauth/github";
import { debitWallet, hostingCost } from "@/lib/krones/store";
import {
  COMMAND_CATALOG,
  DISCORD_COMMANDS,
  flavorFromModules,
  isOfficialFlavor,
  officialBot,
} from "@/lib/discord/catalog";

export type CreateServiceInput = {
  type: ServiceType;
  name: string;
  description?: string;
  projectId?: string;
  cpuMillicores: number;
  memoryMb: number;
  storageMb: number;
  restartPolicy?: "no" | "on-failure" | "always";
  autoStart?: boolean;
  env?: Record<string, string>;
  discord?: {
    token?: string;
    applicationId?: string;
    prefix: string;
    slashCommands: boolean;
    flavor?: string;
    modules: string[];
    commands: string[];
    intents?: string[];
  };
  minecraft?: {
    software: string;
    version: string;
    bedrockEnabled: boolean;
    eulaAccepted: boolean;
    properties?: Record<string, string>;
  };
  web?: {
    template: WebTemplateId;
    source: "empty" | "github";
    repoUrl?: string;
    branch?: string;
    installCommand?: string;
    buildCommand?: string;
    startCommand?: string;
    autoDeploy?: boolean;
  };
};

async function ensureProject(userId: string, projectId?: string, fallbackName = "Default") {
  if (projectId) {
    const [row] = await db.select().from(projects).where(eq(projects.id, projectId)).limit(1);
    if (!row || row.ownerId !== userId) throw new HttpError(404, "Project not found");
    return row.id;
  }
  const existing = await db.select().from(projects).where(eq(projects.ownerId, userId)).limit(1);
  if (existing.length) return existing[0].id;
  const [created] = await db
    .insert(projects)
    .values({ ownerId: userId, name: fallbackName })
    .returning({ id: projects.id });
  return created.id;
}

function assertCreateInput(input: CreateServiceInput) {
  if (!input.name?.trim()) throw new HttpError(400, "A name is required");
  if (!["discord", "minecraft", "web"].includes(input.type))
    throw new HttpError(400, "Unsupported service type");
  if (input.type === "discord") {
    const d = input.discord;
    if (!d) throw new HttpError(400, "Discord configuration is required");
    const token = d.token?.trim();
    if (token && !isDiscordToken(token))
      throw new HttpError(
        400,
        "That does not look like a bot token. Copy it from Developer Portal > Bot > Reset Token.",
      );
  }
  if (input.type === "minecraft") {
    const m = input.minecraft;
    if (!m) throw new HttpError(400, "Minecraft configuration is required");
    if (!MINECRAFT_SOFTWARE.some((s) => s.id === m.software))
      throw new HttpError(400, `Unknown Minecraft software: ${m.software}`);
    if (!/^[0-9][0-9A-Za-z.\-_]{0,31}$/.test(m.version ?? ""))
      throw new HttpError(400, "A Minecraft version is required");
  }
  if (input.type === "web") {
    const w = input.web;
    if (!w) throw new HttpError(400, "Web configuration is required");
    if (w.source === "github" && !w.repoUrl) throw new HttpError(400, "Repository URL required");
  }
}

export async function createService(userId: string, input: CreateServiceInput) {
  assertCreateInput(input);

  let githubRepoUrl: string | null = null;
  if (input.type === "web" && input.web?.source === "github") {
    const parsed = await assertGithubRepoAccess(userId, input.web.repoUrl!);
    githubRepoUrl = parsed.httpsUrl;
  }

  const cost = hostingCost(input.type, {
    memoryMb: input.memoryMb,
    cpuMillicores: input.cpuMillicores,
    storageMb: input.storageMb,
  });
  try {
    await debitWallet(userId, cost, `host:${input.type}:${input.name}`);
  } catch (err) {
    if (err instanceof Error && (err as Error & { code?: string }).code === "INSUFFICIENT_KRONES") {
      throw new HttpError(403, `Solde insuffisant (${cost} Krônes requis).`, "INSUFFICIENT_KRONES");
    }
    throw err;
  }

  const projectId = await ensureProject(userId, input.projectId, `${input.name} project`);
  const slug = `${slugify(input.name)}-${shortId(4)}`;

  const [svc] = await db
    .insert(services)
    .values({
      projectId,
      ownerId: userId,
      type: input.type,
      name: input.name.trim(),
      slug,
      description: input.description ?? null,
      state: "CREATING",
      cpuLimit: Math.min(Math.max(input.cpuMillicores || 1000, 100), 16000),
      memoryLimitMb: Math.min(Math.max(input.memoryMb || 512, 64), 65536),
      storageLimitMb: Math.max(input.storageMb || 5120, 512),
      restartPolicy: input.restartPolicy ?? defaultRestartPolicy(input.type),
      maxRestarts: defaultMaxRestarts(input.type),
    })
    .returning();

  if (input.type === "discord") {
    const d = input.discord;
    if (!d) throw new HttpError(400, "Discord configuration is required");
    const flavor = isOfficialFlavor(d.flavor) ? d.flavor : flavorFromModules(d.modules ?? []);
    const official = flavor !== "custom" ? officialBot(flavor) : null;
    const modules = official ? [`official:${official.id}`] : (d.modules ?? []).filter((id) => id in DISCORD_COMMANDS);
    const selected = new Set(d.commands ?? []);
    const commands = official
      ? COMMAND_CATALOG.categories.flatMap((cat) =>
          cat.commands
            .filter((cmd) => cmd.source.toLowerCase().includes(official.name.toLowerCase()))
            .map((cmd) => ({
              name: cmd.name,
              module: cat.id,
              enabled: true,
              description: cmd.description,
              permission: "",
              cooldown: 3,
              logging: false,
            })),
        )
      : Object.entries(DISCORD_COMMANDS)
          .filter(([moduleId]) => modules.includes(moduleId))
          .flatMap(([moduleId, list]) =>
            list.map((c) => ({
              name: c.name,
              module: moduleId,
              enabled: selected.size === 0 ? true : selected.has(c.name),
              description: c.description,
              permission: c.permission,
              cooldown: 3,
              logging: false,
            })),
          );
    const token = d.token?.trim() || undefined;
    await db.insert(discordBots).values({
      serviceId: svc.id,
      tokenEnc: token ? encryptSecret(token) : null,
      tokenFingerprint: token ? fingerprint(token) : null,
      applicationId:
        d.applicationId?.trim() || (token ? applicationIdFromToken(token) : null) || null,
      prefix: official?.prefix || d.prefix || "!",
      slashCommands: d.slashCommands ?? true,
      flavor: official?.id ?? "custom",
      intents: resolveGatewayIntents(d.intents, modules),
      modules,
      commands,
    });
  }

  if (input.type === "minecraft") {
    const m = input.minecraft!;
    const javaPort = await allocateMinecraftPort();
    await db.insert(minecraftServers).values({
      serviceId: svc.id,
      software: m.software,
      version: m.version,
      javaPort,
      bedrockEnabled: m.bedrockEnabled,
      bedrockPort: await allocateBedrockPort(),
      eulaAccepted: m.eulaAccepted,
      properties: {
        ...DEFAULT_PROPERTIES,
        ...normalizeProperties(m.properties ?? {}),
        "server-port": String(javaPort),
      },
    });
  }

  if (input.type === "web") {
    const w = input.web!;
    const repoUrl = githubRepoUrl ?? w.repoUrl ?? null;
    await db.insert(webProjects).values({
      serviceId: svc.id,
      template: w.template,
      source: w.source,
      repoUrl,
      branch: w.branch || "main",
      installCommand: w.installCommand ?? null,
      buildCommand: w.buildCommand ?? null,
      startCommand: w.startCommand ?? null,
      autoDeploy: w.autoDeploy ?? false,
      webhookSecretEnc: encryptSecret(shortId(24)),
      port: await allocateWebPort(),
    });
    const base = publicBaseDomain();
    if (base.configured) {
      const hostname = suggestedHostname(slug);
      await db
        .insert(domains)
        .values({ serviceId: svc.id, hostname, kind: "default", https: true, status: "PENDING" })
        .catch(() => undefined);
      await syncTraefikConfig(svc.id).catch(() => undefined);
    }
  }

  for (const [key, value] of Object.entries(input.env ?? {})) {
    if (!key.trim()) continue;
    await db.insert(envVars).values({
      serviceId: svc.id,
      key: key.trim(),
      valueEnc: encryptSecret(value),
      secret: /token|secret|password|key/i.test(key),
    });
  }

  await SFTPManager.issue(svc.id, input.type, slug).catch(() => undefined);

  const jobId = await createJob({
    type: "CREATE_CONTAINER",
    serviceId: svc.id,
    userId,
    steps: PROVISION_STEPS,
  });
  dispatch(provisionService(jobId, svc.id, input.autoStart ?? true));

  await audit({
    userId,
    projectId,
    serviceId: svc.id,
    action: `service.create.${input.type}`,
    detail: svc.name,
  });

  return { service: svc, jobId };
}
