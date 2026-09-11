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

type Coeff = { base: number; ramGb: number; cpu: number; storagePer10Gb: number; db?: number };

function monthlyCost(coeff: Coeff, ramMb: number, cpuMillicores: number, storageMb: number, db = false) {
  const ramGb = Math.max(0, ramMb / 1024);
  const cpu = Math.max(0, cpuMillicores / 1000);
  const storageGb = Math.max(0, storageMb / 1024);
  return (
    coeff.base +
    ramGb * coeff.ramGb +
    cpu * coeff.cpu +
    Math.ceil(storageGb / 10) * coeff.storagePer10Gb +
    (db ? coeff.db ?? 0 : 0)
  );
}

export function hostingCost(
  type: "discord" | "minecraft" | "web",
  input: { memoryMb: number; cpuMillicores: number; storageMb: number; db?: boolean },
) {
  const coeff = type === "minecraft" ? MC_COEFF : type === "web" ? WEB_COEFF : DISCORD_COEFF;
  return Math.max(1, Math.round(monthlyCost(coeff, input.memoryMb, input.cpuMillicores, input.storageMb, input.db)));
}
