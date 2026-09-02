import discord
from discord.ext import commands

try:
    from cogs.developpeur.commands.embed_type.utils import config_manager
except ImportError:
    config_manager = None


class ViewLock(commands.Cog):
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
        return discord.Embed(title=title, description=description, color=discord.Color.orange())

    @commands.hybrid_command(name="view", description="Verrouille le salon: lecture oui, ecriture non.")
    @commands.has_permissions(manage_channels=True)
    async def view(self, ctx: commands.Context):
        channel = ctx.channel
        guild = ctx.guild
        everyone = guild.default_role

        overwrite = channel.overwrites_for(everyone)
        overwrite.send_messages = False
        overwrite.create_public_threads = False
        overwrite.create_private_threads = False
        overwrite.send_messages_in_threads = False

        await channel.set_permissions(everyone, overwrite=overwrite, reason=f"view lock par {ctx.author}")

        embed = self.make_embed(
            ctx,
            "🔒 Salon verrouillé",
            f"Le salon {channel.mention} est maintenant en mode lecture seule.",
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(ViewLock(bot))
