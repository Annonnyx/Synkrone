import re
from typing import Optional, Union

import discord
from discord.ext import commands

try:
    from cogs.developpeur.commands.embed_type.utils import config_manager
except ImportError:
    config_manager = None


class AccesAddCommand(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def make_embed(self, source, title: str, description: str) -> discord.Embed:
        user = source.user if isinstance(source, discord.Interaction) else source.author
        guild = source.guild
        if config_manager:
            embed = config_manager.get_formatted_embed(
                guild=guild,
                user=user,
                bot=self.bot,
                title=title,
                description=description,
                target_id=guild.id if guild else None,
            )
            embed.remove_author()
            return embed
        return discord.Embed(title=title, description=description, color=0x2B2D31)

    def _extract_id(self, raw: str) -> Optional[int]:
        if raw.isdigit():
            return int(raw)
        match = re.search(r"(\d{15,21})", raw)
        return int(match.group(1)) if match else None

    def _resolve_member_or_role(self, guild: discord.Guild, raw: str) -> Optional[Union[discord.Member, discord.Role]]:
        target_id = self._extract_id(raw)
        if target_id is None:
            return None
        return guild.get_member(target_id) or guild.get_role(target_id)

    @commands.hybrid_command(name="accesadd", description="Ajoute acces lecture/ecriture au salon actuel.")
    @commands.has_permissions(manage_channels=True)
    async def accesadd(self, ctx: commands.Context, cible: str):
        target = self._resolve_member_or_role(ctx.guild, cible)
        if not target:
            return await ctx.send(embed=self.make_embed(ctx, "❌ Introuvable", "Utilisateur/role introuvable."))

        overwrite = ctx.channel.overwrites_for(target)
        overwrite.view_channel = True
        overwrite.send_messages = True
        overwrite.create_public_threads = True
        overwrite.create_private_threads = True
        overwrite.send_messages_in_threads = True
        await ctx.channel.set_permissions(target, overwrite=overwrite, reason=f"Acces ajoute par {ctx.author}")

        mention = target.mention if hasattr(target, "mention") else f"**{target.name}**"
        await ctx.send(embed=self.make_embed(ctx, "✅ Acces ajoute", f"Acces accorde a {mention}."))


async def setup(bot: commands.Bot):
    await bot.add_cog(AccesAddCommand(bot))
