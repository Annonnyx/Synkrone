from datetime import timezone

import discord
from discord.ext import commands

try:
    from cogs.config_manager.utils import config_manager
except ImportError:
    config_manager = None

try:
    from cogs.config_manager.stats_store import stats_db
except ImportError:
    stats_db = None


def _fmt_uptime(seconds: int) -> str:
    seconds = max(0, int(seconds or 0))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days} j")
    if hours or days:
        parts.append(f"{hours} h")
    parts.append(f"{minutes} min")
    if not days and not hours:
        parts.append(f"{secs} s")
    return " ".join(parts)


class BotStats(commands.Cog, name="BotStats"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="stats", description="Statistiques runtime du bot.")
    async def stats_cmd(self, ctx: commands.Context):
        snap = stats_db.snapshot(self.bot) if stats_db else {}
        total, month, today = stats_db.get_stats() if stats_db else (0, 0, 0)
        unique = stats_db.unique_users() if stats_db else 0
        start = getattr(self.bot, "start_time", None)
        uptime = snap.get("uptimeSeconds") or 0
        if not uptime and start is not None:
            now = discord.utils.utcnow()
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            uptime = max(0, int((now - start).total_seconds()))
        desc = (
            f"**Disponibilité :** {_fmt_uptime(uptime)}\n"
            f"**Serveurs :** {len(self.bot.guilds)}\n"
            f"**Utilisateurs uniques (commandes) :** {unique}\n\n"
            f"**Commandes :** {total:,} au total · {month:,} ce mois · {today:,} aujourd'hui"
        )
        if config_manager:
            embed = config_manager.get_formatted_embed(
                ctx.guild, ctx.author, self.bot, "Statistiques", desc,
                ctx.guild.id if ctx.guild else None,
            )
        else:
            embed = discord.Embed(title="Statistiques", description=desc, color=0x2b2d31)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(BotStats(bot))
