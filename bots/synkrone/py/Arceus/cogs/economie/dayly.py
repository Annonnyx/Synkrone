import time

from discord.ext import commands

from .utils import EconomyService


DAILY_REWARD = 1500
DAILY_COOLDOWN_SECONDS = 24 * 60 * 60


class DailyCog(commands.Cog):
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
            row = conn.execute("SELECT dayly FROM claim_cooldowns WHERE user_id = ?", (user_id,)).fetchone()
            return int(row["dayly"]) if row else 0

    def _set_last_claim(self, user_id: int, claim_ts: int):
        with self.eco._get_conn() as conn:
            conn.execute(
                "UPDATE claim_cooldowns SET dayly = ? WHERE user_id = ?",
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

    @commands.hybrid_command(name="daily", description="Gagne des Pokédollars tous les jours.")
    async def daily(self, ctx: commands.Context[commands.Bot]):
        user_id = ctx.author.id
        self.eco.ensure_user(user_id)

        now = int(time.time())
        last_claim = self._get_last_claim(user_id)
        elapsed = now - last_claim

        if elapsed < DAILY_COOLDOWN_SECONDS:
            remaining = DAILY_COOLDOWN_SECONDS - elapsed
            await ctx.send(
                f"⏳ Tu as déjà récupéré ton daily. Réessaie dans {self._format_remaining(remaining)}.",
                reference=ctx.message,
            )
            return

        with self.eco._get_conn() as conn:
            conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (DAILY_REWARD, user_id))

        self._set_last_claim(user_id, now)
        await ctx.send(
            f"✅ daily récupéré: +{DAILY_REWARD} Pokédollars. Prochain dans 24 heures.",
            reference=ctx.message,
        )


async def setup(bot: commands.Bot):
    if bot.get_cog("DailyCog"):
        await bot.remove_cog("DailyCog")
    await bot.add_cog(DailyCog(bot))
