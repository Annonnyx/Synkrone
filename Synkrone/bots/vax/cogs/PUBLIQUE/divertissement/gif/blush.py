import os
import aiohttp
import discord
from discord.ext import commands
import random
from utils.config_theme import config_manager
from utils.config_emoji import Emoji as E

class Blush(commands.Cog):
    """Commande /blush — Rougir de timidité/gêne."""

    FALLBACK_URLS = [
        "https://media.giphy.com/media/1gbqiEQYceEFO/giphy.gif",
        "https://media.giphy.com/media/Z5zuypybI5dYc/giphy.gif",
        "https://media.giphy.com/media/xT0GqnOEBhPshOQVSU/giphy.gif",
        "https://media.giphy.com/media/2iZNuiivXA2Kk/giphy.gif"
    ]

    def __init__(self, bot):
        self.bot = bot

    async def _resolve_gif_url(self) -> str:
        api_key = os.getenv("GIPHY_API_KEY") or os.getenv("GIPHY_KEY")
        if api_key:
            url = f"https://api.giphy.com/v1/gifs/search?api_key={api_key}&q=anime+blush+shy&limit=25&rating=pg-13"
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

    @commands.hybrid_command(name="blush", description="Montre que tu es gêné(e) ou timide.")
    async def blush(self, ctx: commands.Context):
        await ctx.defer()
        try:
            gif_url = await self._resolve_gif_url()

            if config_manager:
                embed = config_manager.get_formatted_embed(
                    guild=ctx.guild, user=ctx.author, bot=self.bot,
                    title=f"{getattr(E, 'QUESTION', '❓')} Oups...",
                    description=f"{ctx.author.mention} rougit intensément... {getattr(E, 'COEUR', '❤️')}",
                    target_id=ctx.guild.id if ctx.guild else None
                )
            else:
                embed = discord.Embed(
                    title=f"{getattr(E, 'QUESTION', '❓')} Oups...",
                    description=f"{ctx.author.mention} rougit intensément... {getattr(E, 'COEUR', '❤️')}",
                    color=0xff9ff3
                )
            embed.set_image(url=gif_url)
            await ctx.send(embed=embed)
        except Exception as e:
            print(f"[blush.py] Erreur inattendue : {e}")
            await ctx.send(f"{getattr(E, 'ERREUR', '❌')} Une erreur est survenue.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Blush(bot))