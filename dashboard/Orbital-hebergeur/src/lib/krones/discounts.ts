export type DiscountTarget = "all" | "discord" | "minecraft" | "web" | "ram" | "cpu" | "storage";

export type PromoDiscount = {
  id: string;
  label: string;
  targets: DiscountTarget[];
  percent: number;
  startsAt: number;
  endsAt: number;
  enabled?: boolean;
};

export function activeDiscounts(discounts: PromoDiscount[] | undefined, at = Date.now()) {
  return (discounts ?? []).filter(
    (row) => row && row.enabled !== false && Number(row.startsAt) <= at && at < Number(row.endsAt),
  );
}

function factor(discounts: PromoDiscount[] | undefined, keys: DiscountTarget[]) {
  const wanted = new Set(keys);
  return activeDiscounts(discounts).reduce((acc, row) => {
    if (!row.targets.some((target) => wanted.has(target))) return acc;
    return acc * Math.max(0, 1 - Number(row.percent || 0) / 100);
  }, 1);
}

export function applyHostingDiscount(
  parts: { base: number; ram: number; cpu: number; storage: number; db?: number },
  type: "discord" | "minecraft" | "web",
  discounts?: PromoDiscount[],
) {
  const ram = parts.ram * factor(discounts, ["ram"]);
  const cpu = parts.cpu * factor(discounts, ["cpu"]);
  const storage = parts.storage * factor(discounts, ["storage"]);
  const subtotal = parts.base + ram + cpu + storage + (parts.db ?? 0);
  return Math.max(0, Math.round(subtotal * factor(discounts, [type, "all"])));
}
