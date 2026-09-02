import re
from typing import Optional, Union

import discord
from discord.ext import commands

try:
    from cogs.developpeur.commands.embed_type.utils import config_manager
except ImportError:
    config_manager = None


class ConfirmDeleteView(discord.ui.View):
    def __init__(self, cog, ctx: commands.Context, target: Union[discord.abc.GuildChannel, discord.Role]):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx
        self.target = target
        self.author_id = ctx.author.id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Seul l'auteur de la commande peut utiliser ce menu.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirmer", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button):
        try:
            await self.target.delete(reason=f"Suppression demandee par {self.ctx.author}")
            embed = self.cog.make_embed(
                interaction,
                "✅ Suppression effectuee",
                f"L'element **{getattr(self.target, 'name', str(self.target))}** a ete supprime.",
            )
            await interaction.response.edit_message(embed=embed, view=None)
        except Exception as e:
            embed = self.cog.make_embed(interaction, "❌ Echec", f"Impossible de supprimer l'element: {e}")
            await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button):
        embed = self.cog.make_embed(interaction, "❎ Action annulee", "Suppression annulee.")
        await interaction.response.edit_message(embed=embed, view=None)


class SupCommand(commands.Cog):
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

    def _resolve_channel_or_role(
        self, guild: discord.Guild, raw: str
    ) -> Optional[Union[discord.abc.GuildChannel, discord.Role]]:
        raw = raw.strip()
        if raw.startswith("<#"):
            cid = self._extract_id(raw)
            return guild.get_channel(cid) if cid else None
        if raw.startswith("<@&"):
            rid = self._extract_id(raw)
            return guild.get_role(rid) if rid else None

        target_id = self._extract_id(raw)
        if target_id is not None:
            return guild.get_channel(target_id) or guild.get_role(target_id)
        return discord.utils.get(guild.channels, name=raw) or discord.utils.get(guild.roles, name=raw)

    @commands.hybrid_command(name="sup", description="Supprime un salon ou un role apres confirmation.")
    @commands.has_permissions(manage_channels=True, manage_roles=True)
    async def sup(self, ctx: commands.Context, *, cible: str):
        target = self._resolve_channel_or_role(ctx.guild, cible)
        if not target:
            return await ctx.send(embed=self.make_embed(ctx, "❌ Introuvable", "Aucun salon/role correspondant."))

        target_name = getattr(target, "mention", None) or f"**{target.name}**"
        embed = self.make_embed(
            ctx,
            "⚠️ Confirmation",
            f"Confirmez-vous la suppression de {target_name} ?",
        )
        await ctx.send(embed=embed, view=ConfirmDeleteView(self, ctx, target))


async def setup(bot: commands.Bot):
    await bot.add_cog(SupCommand(bot))
