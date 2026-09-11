import { NextRequest } from "next/server";
import { and, desc, eq } from "drizzle-orm";
import { db } from "@/db";
import { serviceDatabases } from "@/db/schema";
import { body, fail, route } from "@/lib/api";
import { audit } from "@/lib/audit";
import { requireUser } from "@/lib/auth";
import { encryptSecret } from "@/lib/crypto";
import { DatabaseManager } from "@/lib/database/manager";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return route(async () => {
    const user = await requireUser();
    const rows = await db
      .select()
      .from(serviceDatabases)
      .where(eq(serviceDatabases.ownerId, user.id))
      .orderBy(desc(serviceDatabases.createdAt));
    return { databases: rows.map((r) => ({ ...r, passwordEnc: undefined })) };
  });
}

export async function POST(req: NextRequest) {
  return route(async () => {
    const user = await requireUser();
    const { name, serviceId } = await body<{ name: string; serviceId?: string }>(req);
    const provisioned = await DatabaseManager.create(name || "app");
    const [row] = await db
      .insert(serviceDatabases)
      .values({
        ownerId: user.id,
        serviceId: serviceId ?? null,
        engine: "postgres",
        dbName: provisioned.dbName,
        dbUser: provisioned.dbUser,
        passwordEnc: encryptSecret(provisioned.password),
        host: provisioned.host,
        port: provisioned.port,
      })
      .returning();
    await audit({ userId: user.id, action: "database.create", detail: provisioned.dbName });
    return {
      database: { ...row, passwordEnc: undefined },
      password: provisioned.password,
      connectionString: DatabaseManager.connectionString(provisioned),
    };
  });
}

export async function PATCH(req: NextRequest) {
  return route(async () => {
    const user = await requireUser();
    const { id } = await body<{ id: string }>(req);
    const [row] = await db
      .select()
      .from(serviceDatabases)
      .where(and(eq(serviceDatabases.id, id), eq(serviceDatabases.ownerId, user.id)))
      .limit(1);
    if (!row) return fail("Database not found", 404);
    const password = await DatabaseManager.resetPassword(row.dbUser);
    await db
      .update(serviceDatabases)
      .set({ passwordEnc: encryptSecret(password) })
      .where(eq(serviceDatabases.id, row.id));
    await audit({ userId: user.id, action: "database.reset_password", detail: row.dbName });
    return {
      password,
      connectionString: DatabaseManager.connectionString({
        dbName: row.dbName,
        dbUser: row.dbUser,
        password,
        host: row.host,
        port: row.port,
      }),
    };
  });
}

export async function DELETE(req: NextRequest) {
  return route(async () => {
    const user = await requireUser();
    const id = new URL(req.url).searchParams.get("id");
    if (!id) return fail("id is required");
    const [row] = await db
      .select()
      .from(serviceDatabases)
      .where(and(eq(serviceDatabases.id, id), eq(serviceDatabases.ownerId, user.id)))
      .limit(1);
    if (!row) return fail("Database not found", 404);
    await DatabaseManager.drop(row.dbName, row.dbUser);
    await db.delete(serviceDatabases).where(eq(serviceDatabases.id, row.id));
    await audit({ userId: user.id, action: "database.delete", detail: row.dbName });
    return { ok: true };
  });
}
