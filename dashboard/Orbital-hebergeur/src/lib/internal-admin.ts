import { timingSafeEqual } from "node:crypto";
import { NextRequest } from "next/server";
import { HttpError } from "@/lib/auth";

export function requireInternalAdmin(req: NextRequest) {
  const expected = String(process.env.PLATFORM_SECRET_KEY || "").trim();
  const auth = req.headers.get("authorization") || "";
  const token = auth.startsWith("Bearer ") ? auth.slice(7).trim() : "";
  if (expected.length < 16 || token.length !== expected.length) {
    throw new HttpError(401, "Unauthorized");
  }
  if (!timingSafeEqual(Buffer.from(token), Buffer.from(expected))) {
    throw new HttpError(401, "Unauthorized");
  }
}
