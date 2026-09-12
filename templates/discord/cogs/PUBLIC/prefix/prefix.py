import json
import os
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

try:
    from cogs.config_manager.utils import config_manager
except ImportError:
    config_manager = None

try:
    from synkrone_slash import runtime_prefix
except ImportError:
    def runtime_prefix(bot=None, default="*"):
        return default


class PrefixCog(commands.Cog, name="Prefix"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _embed(self, ctx: commands.Context, title: str, desc: str):
        if config_manager:
            return config_manager.get_formatted_embed(
                ctx.guild, ctx.author, self.bot, title, desc,
                ctx.guild.id if ctx.guild else None,
            )
        return discord.Embed(title=title, description=desc, color=0x2b2d31)

    def _write_prefix(self, prefix: str):
        admin = self.bot.cogs.get("BotAdmin")
        if admin and hasattr(admin, "default_prefix"):
            admin.default_prefix = prefix
            if hasattr(admin, "_save_config"):
                admin._save_config()
            return
        panel = Path("config") / "bot.json"
        data = {}
        if panel.exists():
            try:
                data = json.loads(panel.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        if not isinstance(data, dict):
            data = {}
        data["prefix"] = prefix
        panel.parent.mkdir(parents=True, exist_ok=True)
        panel.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.environ["PREFIX"] = prefix
        os.environ["BOT_PREFIX"] = prefix

    @commands.hybrid_command(name="prefix", description="Afficher ou changer le préfixe du bot.")
    @app_commands.describe(nouveau="Nouveau préfixe (owner uniquement)")
    async def prefix_cmd(self, ctx: commands.Context, nouveau: str | None = None):
        current = runtime_prefix(self.bot)
        if not nouveau:
            await ctx.send(embed=self._embed(ctx, "Préfixe", f"Préfixe actuel : `{current}`"))
            return
        if not await self.bot.is_owner(ctx.author):
            await ctx.send("Seul le propriétaire de l'application peut changer le préfixe.", ephemeral=True)
            return
        next_prefix = nouveau.strip()[:10]
        if not next_prefix:
            await ctx.send("Préfixe vide.", ephemeral=True)
            return
        self._write_prefix(next_prefix)
        await ctx.send(embed=self._embed(ctx, "Préfixe", f"Nouveau préfixe : `{next_prefix}`"))


async def setup(bot: commands.Bot):
    await bot.add_cog(PrefixCog(bot))
