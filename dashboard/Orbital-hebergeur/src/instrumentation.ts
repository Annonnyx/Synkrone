export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return;
  try {
    const { ensureAccountSchema, ensurePlatformSchema } = await import("./db/ensure-schema");
    await ensureAccountSchema();
    await ensurePlatformSchema();
  } catch (err) {
    console.error("[db] schema:", err instanceof Error ? err.message : err);
  }
  try {
    const { startPlatformTick } = await import("./lib/jobs/tick");
    startPlatformTick();
  } catch (err) {
    console.error("[tick] start:", err instanceof Error ? err.message : err);
  }
}
