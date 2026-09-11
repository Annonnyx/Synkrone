import type { ServiceType } from "@/lib/paths";

/** Discord config fatals (token / intents) must not restart-loop the console. */
export function defaultRestartPolicy(type: ServiceType): "no" | "on-failure" {
  return type === "discord" ? "no" : "on-failure";
}

export function defaultMaxRestarts(type: ServiceType): number {
  return type === "discord" ? 0 : 5;
}
