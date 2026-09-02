import os
import aiohttp
import discord
from discord.ext import commands
import random
from utils.config_theme import config_manager
from utils.config_emoji import Emoji as E

class Cry(commands.Cog):
    """Commande /cry — Pleurer de tristesse."""

    FALLBACK_URLS = [
        "https://media.giphy.com/media/ROF8OQvDsvvXQ/giphy.gif",
        "https://media.giphy.com/media/8YutMatqkTfSE/giphy.gif",
        "https://media.giphy.com/media/qscdhWs5o3yb6/giphy.gif"
    ]

    def __init__(self, bot):
        self.bot = bot

    async def _resolve_gif_url(self) -> str:
        api_key = os.getenv("GIPHY_API_KEY") or os.getenv("GIPHY_KEY")
        if api_key:
            url = f"https://api.giphy.com/v1/gifs/search?api_key={api_key}&q=anime+cry+sad&limit=25&rating=pg-13"
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

    @commands.hybrid_command(name="cry", description="Exprime ta tristesse.")
    async def cry(self, ctx: commands.Context):
        await ctx.defer()
        try:
            gif_url = await self._resolve_gif_url()

            if config_manager:
                embed = config_manager.get_formatted_embed(
                    guild=ctx.guild, user=ctx.author, bot=self.bot,
                    title=f"{getattr(E, 'COEUR_BRISE', '💔')} Oh non...",
                    description=f"{ctx.author.mention} fond en larmes... {getattr(E, 'COEUR_BRISE', '💔')}",
                    target_id=ctx.guild.id if ctx.guild else None
                )
            else:
                embed = discord.Embed(
                    title=f"{getattr(E, 'COEUR_BRISE', '💔')} Oh non...",
                    description=f"{ctx.author.mention} fond en larmes... {getattr(E, 'COEUR_BRISE', '💔')}",
                    color=0x2980b9
                )
            embed.set_image(url=gif_url)
            await ctx.send(embed=embed)
        except Exception as e:
            print(f"[cry.py] Erreur inattendue : {e}")
            await ctx.send(f"{getattr(E, 'ERREUR', '❌')} Une erreur est survenue.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Cry(bot))