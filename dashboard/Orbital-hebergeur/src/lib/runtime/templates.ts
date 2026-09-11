import { NETWORKS } from "@/lib/docker/networks";
import { MINECRAFT_SOFTWARE as SOFTWARE, type MinecraftSoftware as Software } from "@/lib/minecraft/software";
import type { RuntimeTemplate } from "./types";

/**
 * Two image modes:
 *  - "registry" (production): uses the images built from ./docker/** and pushed
 *    to your registry, e.g. registry.example.com/platform/discord-runtime:1.0
 *  - "public" (default / self-hosted single node): uses pinned upstream base
 *    images so a fresh install works before you build & push your own.
 * Set RUNTIME_IMAGE_MODE=registry and RUNTIME_REGISTRY=... to switch.
 */
const MODE = process.env.RUNTIME_IMAGE_MODE === "registry" ? "registry" : "public";
const REGISTRY = process.env.RUNTIME_REGISTRY ?? "registry.example.com/platform";

function image(own: string, publicImage: string): string {
  return MODE === "registry" ? `${REGISTRY}/${own}` : publicImage;
}

/* ------------------------------- Discord -------------------------------- */

export const DISCORD_TEMPLATE: RuntimeTemplate = {
  id: "discord-bot-runtime",
  type: "discord",
  label: "Discord Bot Runtime (Python)",
  image: image("discord-python:1.0", "python:3.12-slim"),
  environment: { PYTHONUNBUFFERED: "1", PYTHONDONTWRITEBYTECODE: "1" },
  mountPath: "/app",
  command: ["sh", "-lc", "sh /app/.orbital/boot.sh"],
  user: "0:0",
  networks: [NETWORKS.discord],
};

/* ------------------------------ Minecraft -------------------------------- */

export { MINECRAFT_SOFTWARE, type MinecraftSoftware } from "@/lib/minecraft/software";

export function minecraftTemplate(
  software: Software,
  version: string,
  memoryMb: number,
): RuntimeTemplate {
  const entry = SOFTWARE.find((s) => s.id === software) ?? SOFTWARE[1];
  return {
    id: entry.runtime,
    type: "minecraft",
    label: `${entry.label} ${version}`,
    // Each software family maps to its own specialised runtime image.
    image: image(`${entry.runtime}:1.0`, "itzg/minecraft-server:java21"),
    defaultPort: 25565,
    environment: {
      TYPE: software.toUpperCase(),
      VERSION: version,
      MEMORY: "",
      JVM_XX_OPTS: `-XX:MaxRAMPercentage=75`,
      INIT_MEMORY: `${Math.max(512, Math.floor(memoryMb * 0.5))}M`,
      MAX_MEMORY: `${Math.max(768, Math.floor(memoryMb * 0.8))}M`,
      USE_AIKAR_FLAGS: "true",
      ENABLE_RCON: "false",
      STOP_SERVER_ANNOUNCE_DELAY: "0",
      SETUP_ONLY: "false",
      UID: "1000",
      GID: "1000",
    },
    mountPath: "/data",
    user: "1000:1000",
    networks: [NETWORKS.minecraft],
  };
}

/* --------------------------------- Web ----------------------------------- */

export type WebTemplateId =
  | "static"
  | "javascript"
  | "typescript"
  | "react"
  | "next"
  | "node";

export const WEB_TEMPLATES: Array<{
  id: WebTemplateId;
  label: string;
  runtime: string;
  install?: string;
  build?: string;
  start?: string;
  port: number;
}> = [
  { id: "static", label: "Static HTML/CSS/JS", runtime: "web-static", port: 80 },
  {
    id: "javascript",
    label: "JavaScript (Node)",
    runtime: "web-node",
    install: "npm install",
    start: "node index.js",
    port: 3000,
  },
  {
    id: "typescript",
    label: "TypeScript (Node)",
    runtime: "web-node",
    install: "npm install",
    build: "npm run build",
    start: "node dist/index.js",
    port: 3000,
  },
  {
    id: "react",
    label: "React (Vite)",
    runtime: "web-react",
    install: "npm install",
    build: "npm run build",
    start: "npx --yes serve -s dist -l 3000",
    port: 3000,
  },
  {
    id: "next",
    label: "Next.js",
    runtime: "web-next",
    install: "npm install",
    build: "npm run build",
    start: "npm run start",
    port: 3000,
  },
  {
    id: "node",
    label: "Node.js server",
    runtime: "web-node",
    install: "npm install",
    start: "npm run start",
    port: 3000,
  },
];

export function webTemplate(id: WebTemplateId): RuntimeTemplate {
  const entry = WEB_TEMPLATES.find((t) => t.id === id) ?? WEB_TEMPLATES[0];
  if (entry.id === "static") {
    return {
      id: entry.runtime,
      type: "web",
      label: entry.label,
      // The hardening policy drops every capability, so the runtime must not
      // need CAP_CHOWN at startup nor CAP_NET_BIND_SERVICE to listen: the
      // unprivileged nginx image runs as uid 101 and serves on 8080.
      image: image("web-static:1.0", "nginxinc/nginx-unprivileged:1.27-alpine"),
      defaultPort: 8080,
      environment: {},
      mountPath: "/usr/share/nginx/html",
      user: "101:101",
      networks: [NETWORKS.web, NETWORKS.proxy],
    };
  }
  return {
    id: entry.runtime,
    type: "web",
    label: entry.label,
    image: image(`${entry.runtime}:1.0`, "node:20-alpine"),
    defaultPort: entry.port,
    environment: { NODE_ENV: "production", PORT: String(entry.port) },
    mountPath: "/srv/app",
    command: ["sh", "-lc", "sh /srv/app/.orbital/start.sh"],
    user: "1000:1000",
    networks: [NETWORKS.web, NETWORKS.proxy],
  };
}

/* ------------------------------ Discord meta ----------------------------- */

export {
  DISCORD_COMMANDS,
  DISCORD_MODULES,
  DISALLOWED_INTENTS_FATAL,
  GATEWAY_INTENTS,
  PRIVILEGED_INTENT_IDS,
  intentsBitfield,
  intentsForModules,
  isPrivilegedIntent,
  mergeIntentsForModules,
  resolveGatewayIntents,
  suggestedPrivilegedIntents,
} from "@/lib/discord/intents";
