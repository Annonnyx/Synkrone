import { db } from "@/db";
import { minecraftServers, webProjects } from "@/db/schema";

const MC_RANGE_START = 25565;
const BEDROCK_RANGE_START = 19132;
const WEB_RANGE_START = 8100;

async function usedPorts(): Promise<Set<number>> {
  const mc = await db
    .select({ java: minecraftServers.javaPort, bedrock: minecraftServers.bedrockPort })
    .from(minecraftServers);
  const web = await db.select({ port: webProjects.port }).from(webProjects);
  const set = new Set<number>();
  mc.forEach((r) => {
    set.add(r.java);
    set.add(r.bedrock);
  });
  web.forEach((r) => set.add(r.port));
  return set;
}

async function allocate(start: number, step = 1): Promise<number> {
  const used = await usedPorts();
  let port = start;
  while (used.has(port) && port < start + 2000) port += step;
  return port;
}

export const allocateMinecraftPort = () => allocate(MC_RANGE_START);
export const allocateBedrockPort = () => allocate(BEDROCK_RANGE_START);
export const allocateWebPort = () => allocate(WEB_RANGE_START);
