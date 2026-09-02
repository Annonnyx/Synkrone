import datetime
import json
import time
from pathlib import Path

from discord.ext import commands

from .utils import EconomyService


WEEKLY_REWARD = 6000
WEEKLY_COOLDOWN_SECONDS = 7 * 24 * 60 * 60
VOTE_WINDOW_SECONDS = 6 * 3600
VOTE_DATA_DIR = Path.cwd() / "data" / "public" / "data_vote"
VOTE_DATA_FILE = VOTE_DATA_DIR / "users.json"


class WeeklyCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.eco = EconomyService(bot)
        self._ensure_claim_table()

    def _ensure_claim_table(self):
        with self.eco._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS claim_cooldowns (
                    user_id INTEGER PRIMARY KEY,
                    hourly INTEGER NOT NULL DEFAULT 0,
                    dayly INTEGER NOT NULL DEFAULT 0,
                    weekly INTEGER NOT NULL DEFAULT 0,
                    monthly INTEGER NOT NULL DEFAULT 0
                )
                """
            )

    def _get_last_claim(self, user_id: int) -> int:
        with self.eco._get_conn() as conn:
            conn.execute("INSERT OR IGNORE INTO claim_cooldowns (user_id) VALUES (?)", (user_id,))
            row = conn.execute("SELECT weekly FROM claim_cooldowns WHERE user_id = ?", (user_id,)).fetchone()
            return int(row["weekly"]) if row else 0

    def _get_last_vote_timestamp(self, user_id: int) -> int:
        if not VOTE_DATA_FILE.exists():
            return 0
        try:
            with open(VOTE_DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return 0
        user_data = data.get(str(user_id), {})
        return int(user_data.get("vote_check_timestamp") or user_data.get("vote_reward_timestamp") or 0)

    def _has_recent_vote(self, user_id: int) -> bool:
        last_vote = self._get_last_vote_timestamp(user_id)
        return last_vote > 0 and (time.time() - last_vote) <= VOTE_WINDOW_SECONDS

    def _set_last_claim(self, user_id: int, claim_ts: int):
        with self.eco._get_conn() as conn:
            conn.execute(
                "UPDATE claim_cooldowns SET weekly = ? WHERE user_id = ?",
                (claim_ts, user_id),
            )

    @staticmethod
    def _format_remaining(seconds: int) -> str:
        minutes, sec = divmod(max(0, seconds), 60)
        hours, minutes = divmod(minutes, 60)
        days, hours = divmod(hours, 24)
        if days:
            return f"{days}j {hours}h"
        if hours:
            return f"{hours}h {minutes}m"
        if minutes:
            return f"{minutes}m {sec}s"
        return f"{sec}s"

    @commands.hybrid_command(name="weekly", description="Gagne des Pokédollars une fois par semaine.")
    async def weekly(self, ctx: commands.Context[commands.Bot]):
        user_id = ctx.author.id
        if not self._has_recent_vote(user_id):
            await ctx.send("❌ Tu dois avoir voté dans les 6 dernières heures pour utiliser cette commande.", reference=ctx.message)
            return

        self.eco.ensure_user(user_id)

        now = int(time.time())
        last_claim = self._get_last_claim(user_id)
        elapsed = now - last_claim

        if elapsed < WEEKLY_COOLDOWN_SECONDS:
            remaining = WEEKLY_COOLDOWN_SECONDS - elapsed
            await ctx.send(
                f"⏳ Tu as déjà récupéré ton weekly. Réessaie dans {self._format_remaining(remaining)}.",
                reference=ctx.message,
            )
            return

        with self.eco._get_conn() as conn:
            conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (WEEKLY_REWARD, user_id))

        self._set_last_claim(user_id, now)
        await ctx.send(
            f"✅ Weekly récupéré: +{WEEKLY_REWARD} Pokédollars. Prochain weekly dans 7 jours.",
            reference=ctx.message,
        )


async def setup(bot: commands.Bot):
    if bot.get_cog("WeeklyCog"):
        await bot.remove_cog("WeeklyCog")
    await bot.add_cog(WeeklyCog(bot))
