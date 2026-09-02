import os
import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
import random

from utils.config_theme import config_manager
from utils.config_emoji import Emoji as E


class Gif(commands.Cog):
    """Commande /gif — Recherche un gif selon un mot-clé."""

    FALLBACK_URLS = [
        "https://media.giphy.com/media/l0HlBO7eyXzSZkJri/giphy.gif",
        "https://media.giphy.com/media/3orieUe6ejxSFxYCXe/giphy.gif",
        "https://media.giphy.com/media/26tPplGWjN0xLybiU/giphy.gif",
        "https://media.giphy.com/media/xUPGcguWZHRC2HyBRS/giphy.gif",
    ]

    def __init__(self, bot):
        self.bot = bot

    async def _resolve_gif_url(self, keyword: str) -> str:
        query = (keyword or "anime").strip()
        api_key = os.getenv("GIPHY_API_KEY") or os.getenv("GIPHY_KEY")
        if api_key:
            url = f"https://api.giphy.com/v1/gifs/search?api_key={api_key}&q={query}&limit=25&rating=pg-13"
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

    @commands.hybrid_command(name="gif", description="Recherche un gif selon un mot-clé.")
    @app_commands.describe(keyword="Mot-clé recherché (ex: happy, dance, anime)")
    async def gif(self, ctx: commands.Context, *, keyword: str):
        await ctx.defer()
        try:
            gif_url = await self._resolve_gif_url(keyword)

            if config_manager:
                embed = config_manager.get_formatted_embed(
                    guild=ctx.guild,
                    user=ctx.author,
                    bot=self.bot,
                    title=f"{getattr(E, 'RECHERCHE', '🔎')} Résultat GIF",
                    description=f"Mot-clé recherché : `{keyword}`",
                    target_id=ctx.guild.id if ctx.guild else None,
                )
            else:
                embed = discord.Embed(
                    title=f"{getattr(E, 'RECHERCHE', '🔎')} Résultat GIF",
                    description=f"Mot-clé recherché : `{keyword}`",
                    color=0x5865F2,
                )

            embed.set_image(url=gif_url)
            await ctx.send(embed=embed)
        except Exception as e:
            print(f"[gif.py] Erreur inattendue : {e}")
            await ctx.send(f"{getattr(E, 'ERREUR', '❌')} Une erreur est survenue.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Gif(bot))
