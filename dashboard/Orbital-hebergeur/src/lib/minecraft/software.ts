/**
 * Server software catalogue. Kept free of any Node dependency so the creation
 * wizard and the service page can import it from the browser bundle.
 */

export type MinecraftSoftware =
  | "vanilla"
  | "paper"
  | "purpur"
  | "spigot"
  | "fabric"
  | "forge"
  | "neoforge"
  | "quilt";

export const MINECRAFT_SOFTWARE: Array<{
  id: MinecraftSoftware;
  label: string;
  kind: "plugin" | "mod" | "none";
  runtime: string;
}> = [
  { id: "vanilla", label: "Vanilla", kind: "none", runtime: "minecraft-vanilla-runtime" },
  { id: "paper", label: "Paper", kind: "plugin", runtime: "minecraft-paper-runtime" },
  { id: "purpur", label: "Purpur", kind: "plugin", runtime: "minecraft-paper-runtime" },
  { id: "spigot", label: "Spigot", kind: "plugin", runtime: "minecraft-paper-runtime" },
  { id: "fabric", label: "Fabric", kind: "mod", runtime: "minecraft-fabric-runtime" },
  { id: "forge", label: "Forge", kind: "mod", runtime: "minecraft-forge-runtime" },
  { id: "neoforge", label: "NeoForge", kind: "mod", runtime: "minecraft-neoforge-runtime" },
  { id: "quilt", label: "Quilt", kind: "mod", runtime: "minecraft-fabric-runtime" },
];

export const SOFTWARE_KIND: Record<MinecraftSoftware, "plugin" | "mod" | "none"> =
  Object.fromEntries(MINECRAFT_SOFTWARE.map((s) => [s.id, s.kind])) as Record<
    MinecraftSoftware,
    "plugin" | "mod" | "none"
  >;

/** Modrinth loader id matching each software, when it accepts add-ons. */
export const SOFTWARE_LOADER: Record<MinecraftSoftware, string | null> = {
  vanilla: null,
  paper: "paper",
  purpur: "purpur",
  spigot: "spigot",
  fabric: "fabric",
  forge: "forge",
  neoforge: "neoforge",
  quilt: "quilt",
};

/**
 * Loaders a given server software can actually load, most specific first.
 * Bukkit-family plugins are interchangeable, and Quilt loads Fabric mods.
 */
export function loaderCompat(software: MinecraftSoftware | string): string[] {
  switch (software) {
    case "paper":
      return ["paper", "spigot", "bukkit"];
    case "purpur":
      return ["purpur", "paper", "spigot", "bukkit"];
    case "spigot":
      return ["spigot", "bukkit"];
    case "fabric":
      return ["fabric"];
    case "quilt":
      return ["quilt", "fabric"];
    case "forge":
      return ["forge"];
    case "neoforge":
      return ["neoforge"];
    default:
      return [];
  }
}

export function addonKind(software: MinecraftSoftware | string): "plugin" | "mod" | "none" {
  return SOFTWARE_KIND[software as MinecraftSoftware] ?? "none";
}

export function addonDirectory(kind: "plugin" | "mod"): string {
  return kind === "plugin" ? "plugins" : "mods";
}
