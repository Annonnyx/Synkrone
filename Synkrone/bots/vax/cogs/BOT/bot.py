# -*- coding: utf-8 -*-
"""
Cog Bot - Affichage du profil interactif Vax v3
==========================================================
"""

from __future__ import annotations

from datetime import datetime, timezone
import discord
from discord.ext import commands
from colorama import Fore, Style, init

from utils.config_profilbot import EmbedManager
from utils.config_emoji import Emoji as E

# --- Configuration & Logs ---
DEBUG_MODE = True
ERROR_ONLY_MODE = False

init(autoreset=True)

INVITE_VAX = "https://discord.com/oauth2/authorize?client_id=1367891720871874560&permissions=8&integration_type=0&scope=bot+applications.commands"
VOTE_LINK = "https://top.gg/fr/bot/1367891720871874560"
SUPPORT_LINK = "https://discord.gg/p768u2Pgp3"

try:
    from zoneinfo import ZoneInfo
    FRENCH_TIMEZONE = ZoneInfo('Europe/Berlin')
except ImportError:
    FRENCH_TIMEZONE = timezone.utc
except Exception:
    FRENCH_TIMEZONE = timezone.utc


class Bot(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if not hasattr(self.bot, 'start_time'):
            self.bot.start_time = datetime.now(FRENCH_TIMEZONE)
        self.embed_manager = None
        
    async def cog_load(self):
        self.embed_manager = await EmbedManager.create(self.bot)
        if DEBUG_MODE and not ERROR_ONLY_MODE:
            print(f"{Fore.CYAN}[BOT COG] Cog Bot initialisé avec succès.{Style.RESET_ALL}")

    @commands.hybrid_command(name="bot", description="Affiche le profil et les statistiques du bot.")
    async def botprofil(self, ctx: commands.Context):
        """Affiche les statistiques du bot sous forme de Container LayoutV2"""
        try:
            if not self.embed_manager:
                self.embed_manager = await EmbedManager.create(self.bot)

            async with ctx.typing():
                view, file = await self.embed_manager.get_profile_layout(ctx.guild)
                if file:
                    await ctx.send(view=view, file=file)
                else:
                    await ctx.send(view=view)
                if DEBUG_MODE and not ERROR_ONLY_MODE:
                    print(f"{Fore.GREEN}[BOT COMMAND] Commande /bot exécutée par {ctx.author}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[BOT COMMAND ERROR] Echec commande bot: {e}{Style.RESET_ALL}")
            await ctx.send("⚠️ Impossible d'afficher le profil du bot pour le moment.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not self.bot.user:
            return
        
        if message.content in (f"<@{self.bot.user.id}>", f"<@!{self.bot.user.id}>"):
            ctx = await self.bot.get_context(message)
            try:
                await self.botprofil(ctx)
            except Exception as e:
                print(f"{Fore.RED}[BOT MENTION ERROR] Echec reponse mention: {e}{Style.RESET_ALL}")


async def setup(bot):
    await bot.add_cog(Bot(bot))