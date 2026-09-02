import re
from typing import Optional

import discord
from discord.ext import commands

try:
    from cogs.developpeur.commands.embed_type.utils import config_manager
except ImportError:
    config_manager = None


class DelRoleCommand(commands.Cog):
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

    @commands.hybrid_command(name="delrole", description="Retire un role specifique a un utilisateur.")
    @commands.has_permissions(manage_roles=True)
    async def delrole(self, ctx: commands.Context, membre_ref: str, role_ref: str):
        user_id = self._extract_id(membre_ref)
        role_id = self._extract_id(role_ref)
        membre = ctx.guild.get_member(user_id) if user_id else None
        role = ctx.guild.get_role(role_id) if role_id else None
        if not membre or not role:
            return await ctx.send(
                embed=self.make_embed(ctx, "❌ Parametres invalides", "Utilise: ?delrole <@user/ID> <@role/ID>.")
            )

        await membre.remove_roles(role, reason=f"Role retire par {ctx.author}")
        await ctx.send(embed=self.make_embed(ctx, "✅ Role retire", f"{role.mention} retire a {membre.mention}."))


async def setup(bot: commands.Bot):
    await bot.add_cog(DelRoleCommand(bot))
