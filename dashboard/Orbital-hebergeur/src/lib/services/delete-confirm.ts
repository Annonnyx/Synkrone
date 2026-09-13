export type DeleteValidation =
  | { ok: true }
  | { ok: false; code: "DELETE_NAME_MISMATCH" | "DELETE_CONFIRM_REQUIRED" };

/** Exact service name + explicit disk-gone checkbox. No password. */
export function validateServiceDelete(
  serviceName: string,
  typedName: string,
  confirmDiskGone: boolean,
): DeleteValidation {
  if (confirmDiskGone !== true) return { ok: false, code: "DELETE_CONFIRM_REQUIRED" };
  if (typedName !== serviceName) return { ok: false, code: "DELETE_NAME_MISMATCH" };
  return { ok: true };
}

export function deleteValidationMessage(code: "DELETE_NAME_MISMATCH" | "DELETE_CONFIRM_REQUIRED"): string {
  if (code === "DELETE_NAME_MISMATCH") {
    return "Type the exact service name to confirm deletion.";
  }
  return "Tick the box confirming that the disk will be permanently erased.";
}
