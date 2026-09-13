export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  try {
    const { ensureAccountSchema } = await import("./db/ensure-schema");
    await ensureAccountSchema();
  } catch (err) {
    console.error("[db] account schema:", err instanceof Error ? err.message : err);
  }
}
