import os
import aiohttp
import discord
from discord.ext import commands
from discord import app_commands
import random
from utils.config_theme import config_manager
from utils.config_emoji import Emoji as E

class Punch(commands.Cog):
    """Commande /punch — Donne un coup de poing à un membre."""

    FALLBACK_URLS = [
        "https://media.giphy.com/media/arbHBoiUWUgmc/giphy.gif",
        "https://media.giphy.com/media/xT0GqgeTVbhRh9O4qA/giphy.gif",
        "https://media.giphy.com/media/11HeubLHnQJSAU/giphy.gif",
        "https://media.giphy.com/media/AlsIdbTgxXOUU/giphy.gif"
    ]

    def __init__(self, bot):
        self.bot = bot

    async def _resolve_gif_url(self) -> str:
        api_key = os.getenv("GIPHY_API_KEY") or os.getenv("GIPHY_KEY")
        if api_key:
            url = f"https://api.giphy.com/v1/gifs/search?api_key={api_key}&q=anime+punch+hit&limit=25&rating=pg-13"
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

    @commands.hybrid_command(name="punch", description="Donne un coup de poing à un membre.")
    @app_commands.describe(membre="Le membre à frapper")
    async def punch(self, ctx: commands.Context, membre: discord.Member):
        await ctx.defer()
        try:
            gif_url = await self._resolve_gif_url()

            if config_manager:
                embed = config_manager.get_formatted_embed(
                    guild=ctx.guild, user=ctx.author, bot=self.bot,
                    title=f"{getattr(E, 'AUTORITE', '👮')} Prends ça !",
                    description=f"{ctx.author.mention} donne un puissant coup de poing à {membre.mention} {getattr(E, 'ECLAIR', '⚡')}",
                    target_id=ctx.guild.id if ctx.guild else None
                )
            else:
                embed = discord.Embed(
                    title=f"{getattr(E, 'AUTORITE', '👮')} Prends ça !",
                    description=f"{ctx.author.mention} donne un puissant coup de poing à {membre.mention} {getattr(E, 'ECLAIR', '⚡')}",
                    color=0x95a5a6
                )
            embed.set_image(url=gif_url)
            await ctx.send(content=membre.mention, embed=embed)
        except Exception as e:
            print(f"[punch.py] Erreur inattendue : {e}")
            await ctx.send(f"{getattr(E, 'ERREUR', '❌')} Une erreur est survenue.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Punch(bot))