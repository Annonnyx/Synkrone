import { applyHostingDiscount, type PromoDiscount } from "./discounts";

export const MC_COEFF = {
  unit: "Krônes/mois",
  base: 80,
  ramGb: 40,
  cpu: 25,
  storagePer10Gb: 15,
  db: 60,
};

export const DISCORD_COEFF = { unit: "Krônes/mois", base: 40, ramGb: 20, cpu: 15, storagePer10Gb: 8 };
export const WEB_COEFF = { unit: "Krônes/mois", base: 50, ramGb: 25, cpu: 20, storagePer10Gb: 10 };

export function hostingParts(
  type: "discord" | "minecraft" | "web",
  input: { memoryMb: number; cpuMillicores: number; storageMb: number; db?: boolean },
) {
  const coeff = type === "minecraft" ? MC_COEFF : type === "web" ? WEB_COEFF : DISCORD_COEFF;
  const ramGb = Math.max(0, input.memoryMb / 1024);
  const cpu = Math.max(0, input.cpuMillicores / 1000);
  const storageGb = Math.max(0, input.storageMb / 1024);
  return {
    base: coeff.base,
    ram: ramGb * coeff.ramGb,
    cpu: cpu * coeff.cpu,
    storage: Math.ceil(storageGb / 10) * coeff.storagePer10Gb,
    db: input.db && "db" in coeff ? Number(coeff.db ?? 0) : 0,
  };
}

export function hostingCost(
  type: "discord" | "minecraft" | "web",
  input: { memoryMb: number; cpuMillicores: number; storageMb: number; db?: boolean },
  discounts?: PromoDiscount[],
) {
  return applyHostingDiscount(hostingParts(type, input), type, discounts);
}
