import { HttpError } from "@/lib/auth";
import { readPlatformSettings } from "@/lib/platform-settings";
import { creationDisabledMessage, isCreationEnabled } from "@/lib/services/creation-flags";
import { clampResources, limitsFor } from "@/lib/services/clamp-resources";

export type { ServiceKind } from "@/lib/services/limits-types";
export { clampResources, limitsFor };

export async function assertCreationAllowed(type: string) {
  const settings = await readPlatformSettings();
  if (!isCreationEnabled(settings, type)) {
    throw new HttpError(403, creationDisabledMessage(type));
  }
  return settings;
}
