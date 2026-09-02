import os
import aiohttp
import discord
from discord.ext import commands
from discord import app_commands
import random
from utils.config_theme import config_manager
from utils.config_emoji import Emoji as E

class Hug(commands.Cog):
    """Commande /hug — Envoie un câlin virtuel à un membre."""

    FALLBACK_URLS = [
        "https://media.giphy.com/media/od5H3PmEG5EVq/giphy.gif",
        "https://media.giphy.com/media/wnsgren9NtITS/giphy.gif",
        "https://media.giphy.com/media/3M4NpbEpLj6yPuz05v/giphy.gif",
        "https://media.giphy.com/media/lrr9VkYWGkkZa/giphy.gif"
    ]

    def __init__(self, bot):
        self.bot = bot

    async def _resolve_gif_url(self) -> str:
        api_key = os.getenv("GIPHY_API_KEY") or os.getenv("GIPHY_KEY")
        if api_key:
            url = f"https://api.giphy.com/v1/gifs/search?api_key={api_key}&q=anime+hug+cuddle&limit=25&rating=pg-13"
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            gifs = data.get("data", [])
                            if gifs:
                                return random.choice(gifs)["images"]["original"]["url"]
            except Exception:
                pass
        
        return random.choice(self.FALLBACK_URLS)

    @commands.hybrid_command(name="hug", description="Envoie un câlin à un membre.")
    @app_commands.describe(membre="Le membre à prendre dans tes bras")
    async def hug(self, ctx: commands.Context, membre: discord.Member):
        await ctx.defer()
        try:
            gif_url = await self._resolve_gif_url()

            if config_manager:
                embed = config_manager.get_formatted_embed(
                    guild=ctx.guild, user=ctx.author, bot=self.bot,
                    title=f"{getattr(E, 'COEUR', '❤️')} Un gros câlin chaleureux !",
                    description=f"{ctx.author.mention} fait un câlin à {membre.mention} {getattr(E, 'COEUR', '❤️')}",
                    target_id=ctx.guild.id if ctx.guild else None
                )
            else:
                embed = discord.Embed(
                    title=f"{getattr(E, 'COEUR', '❤️')} Un gros câlin chaleureux !",
                    description=f"{ctx.author.mention} fait un câlin à {membre.mention} {getattr(E, 'COEUR', '❤️')}",
                    color=0x3498db
                )
            embed.set_image(url=gif_url)
            await ctx.send(content=membre.mention, embed=embed)
        except Exception as e:
            print(f"[hug.py] Erreur inattendue : {e}")
            await ctx.send(f"{getattr(E, 'ERREUR', '❌')} Une erreur est survenue.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Hug(bot))