import discord
from discord.ext import commands
from .utils import EmbedCustomizerView

class ServEmbed(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="servembed", help="Personnaliser les embeds du serveur.")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def servembed(self, ctx: commands.Context):
        if ctx.interaction: 
            await ctx.defer(ephemeral=True)
            
        view = EmbedCustomizerView(True, ctx.guild.id, self.bot, ctx.author.id)
        await ctx.send(embed=view.generate_preview_embed(ctx.author, ctx.guild), view=view)

    @servembed.error
    async def servembed_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, commands.MissingPermissions):
            return await ctx.send("❌ Accès restreint aux administrateurs du serveur.")
        raise error

async def setup(bot):
    await bot.add_cog(ServEmbed(bot))