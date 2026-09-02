import os
import aiohttp
import discord
from discord.ext import commands
import random

from utils.config_theme import config_manager
from utils.config_emoji import Emoji as E


class Dog(commands.Cog):
    """Commande /dog — Envoie un gif de chien."""

    FALLBACK_URLS = [
        "https://media.giphy.com/media/26BRv0ThflsHCqDrG/giphy.gif",
        "https://media.giphy.com/media/3oEduSbSGpGaRX2Vri/giphy.gif",
        "https://media.giphy.com/media/11sBLVxNs7v6WA/giphy.gif",
        "https://media.giphy.com/media/4Zo41lhzKt6iZ8xff9/giphy.gif",
    ]

    def __init__(self, bot):
        self.bot = bot

    async def _resolve_gif_url(self) -> str:
        api_key = os.getenv("GIPHY_API_KEY") or os.getenv("GIPHY_KEY")
        if api_key:
            url = f"https://api.giphy.com/v1/gifs/search?api_key={api_key}&q=dog+cute&limit=25&rating=pg-13"
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

    @commands.hybrid_command(name="dog", description="Affiche un gif de chien.")
    async def dog(self, ctx: commands.Context):
        await ctx.defer()
        try:
            gif_url = await self._resolve_gif_url()

            if config_manager:
                embed = config_manager.get_formatted_embed(
                    guild=ctx.guild,
                    user=ctx.author,
                    bot=self.bot,
                    title=f"{getattr(E, 'EXCELLENT', '🌟')} Doggo incoming !",
                    description=f"{ctx.author.mention} invoque un chien adorable.",
                    target_id=ctx.guild.id if ctx.guild else None,
                )
            else:
                embed = discord.Embed(
                    title=f"{getattr(E, 'EXCELLENT', '🌟')} Doggo incoming !",
                    description=f"{ctx.author.mention} invoque un chien adorable.",
                    color=0xF39C12,
                )

            embed.set_image(url=gif_url)
            await ctx.send(embed=embed)
        except Exception as e:
            print(f"[dog.py] Erreur inattendue : {e}")
            await ctx.send(f"{getattr(E, 'ERREUR', '❌')} Une erreur est survenue.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Dog(bot))
