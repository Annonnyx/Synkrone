import discord
from discord.ext import commands

try:
    from cogs.developpeur.commands.embed_type.utils import config_manager, EmbedCustomizerView
except ImportError:
    config_manager = None
    EmbedCustomizerView = None


class EditCommand(commands.Cog):
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

    @commands.hybrid_command(name="edit", description="Lance l'assistant de style/theme serveur.")
    @commands.has_permissions(administrator=True)
    async def edit(self, ctx: commands.Context):
        if EmbedCustomizerView is None:
            return await ctx.send(
                embed=self.make_embed(ctx, "⚠️ Indisponible", "Le module de personnalisation n'est pas disponible.")
            )

        view = EmbedCustomizerView(True, ctx.guild.id if ctx.guild else None, self.bot, ctx.author.id)
        embed = view.generate_preview_embed(ctx.author, ctx.guild)
        await ctx.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(EditCommand(bot))
