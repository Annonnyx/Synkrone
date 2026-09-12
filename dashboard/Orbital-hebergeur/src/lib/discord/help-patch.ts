/** Discord.py `Guild.member_count` is None when the guild is unavailable or not
 *  fully populated (often without the privileged members intent). `/help` used
 *  to subtract a bot count from that None. */
const BUGGY_COUNTS =
  /^([ \t]*)total_members = guild\.member_count(?: if guild else 0)?\r?\n\1bots_count = sum\(1 for member in guild\.members if member\.bot\)(?: if guild else 0)?\r?\n\1humans_count = total_members - bots_count/m;

export function patchHelpMemberCounts(source: string): string {
  const text = String(source ?? "");
  if (!BUGGY_COUNTS.test(text)) return text;
  return text.replace(
    BUGGY_COUNTS,
    (_all, indent: string) =>
      `${indent}total_members = int((guild.member_count if guild else 0) or (len(guild.members) if guild else 0) or 0)\n` +
      `${indent}bots_count = sum(1 for member in guild.members if member.bot) if guild else 0\n` +
      `${indent}humans_count = max(0, total_members - bots_count)`,
  );
}
