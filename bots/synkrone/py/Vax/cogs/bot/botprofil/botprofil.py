import discord
from discord.ext import commands
from datetime import datetime, timezone
from .util_embed import EmbedManager, ProfileButtons

# --- Configuration ---
INVITE_VAX = "https://discord.com/oauth2/authorize?client_id=1367891720871874560&permissions=8&integration_type=0&scope=bot+applications.commands"
VOTE_LINK = "https://top.gg/fr/bot/1367891720871874560"
SUPPORT_LINK = "https://discord.gg/p768u2Pgp3"
# Configuration du fuseau horaire avec fallback
try:
    from zoneinfo import ZoneInfo
    FRENCH_TIMEZONE = ZoneInfo('Europe/Berlin')
except ImportError:
    # Fallback si zoneinfo n'est pas disponible
    FRENCH_TIMEZONE = timezone.utc
except Exception:
    # Fallback si le fuseau horaire n'est pas trouvé
    FRENCH_TIMEZONE = timezone.utc

class BotProfile(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if not hasattr(self.bot, 'start_time'):
            self.bot.start_time = datetime.now(FRENCH_TIMEZONE)
        self.embed_manager = None
        
    async def cog_load(self):
        """Initialisation asynchrone du cog"""
        self.embed_manager = await EmbedManager.create(self.bot)
        
    async def get_profile_embed(self, guild: discord.Guild = None):
        """Récupère l'embed du profil depuis l'EmbedManager"""
        if not self.embed_manager:
            self.embed_manager = await EmbedManager.create(self.bot)
            
        return await self.embed_manager.get_bot_profile_embed(guild)

    @commands.hybrid_command(name="bot", description="Affiche le profil du bots.")
    async def botprofil(self, ctx: commands.Context):
        """Affiche les statistiques du bot"""
        async with ctx.typing():
            embed, file, view = await self.get_profile_embed(ctx.guild)
            await ctx.send(
                embed=embed,
                view=view
            )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Répond à la mention du bot"""
        if message.author.bot or not self.bot.user:
            return
        
        if message.content in (f"<@{self.bot.user.id}>", f"<@!{self.bot.user.id}>"):
            ctx = await self.bot.get_context(message)
            await self.botprofil(ctx)

async def setup(bot):
    await bot.add_cog(BotProfile(bot))