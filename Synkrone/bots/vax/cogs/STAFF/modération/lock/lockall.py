"""
COMMANDE LOCKALL - Verrouillage global de tous les salons du serveur
===================================================================
"""

from __future__ import annotations

import asyncio
import random
import traceback
import discord
from discord import ui
from discord.ext import commands

from utils.config_data import DataManager
from utils.config_emoji import Emoji as E
from utils.config_perm import ensure_command_permission, perm_command
from utils.config_theme import config_manager

DEBUG_LOGS = True
ERROR_LOGS = True

def _log(msg: str, level: str = "INFO"):
    if level == "DEBUG" and not DEBUG_LOGS:
        return
    if level == "ERROR" and not ERROR_LOGS:
        return
    colors = {"INFO": "\033[94m", "SUCCESS": "\033[92m", "ERROR": "\033[91m", "WARN": "\033[93m"}
    print(f"{colors.get(level, '\033[0m')}[LOCKALL-{level}] {msg}\033[0m")

EMOJI_ALERT = getattr(E, "ATTENTION", "ðŸš¨")
EMOJI_SUCCESS = getattr(E, "VALIDE", getattr(E, "VALIDER", "âœ…"))
EMOJI_ERROR = getattr(E, "REFUS", getattr(E, "REFUSER", "âŒ"))

db_lock = DataManager("staff/moderation/lock")


class LockAllCommand(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @perm_command(level=1)
    @commands.command(name="lockall", description="ðŸš¨ Verrouillage global du serveur.")
    async def lockall(self, ctx: commands.Context):
        if not ctx.guild:
            return

        if not await ensure_command_permission(ctx, command_name="lockall"):
            return

        db = db_lock.load(ctx.guild.id) or {}
        target = ctx.guild.default_role
        
        channels = [c for c in ctx.guild.channels if isinstance(c, (discord.TextChannel, discord.VoiceChannel, discord.ForumChannel))]
        total = len(channels)
        count = 0

        funny_messages = [
            f"{getattr(E, 'LOCK', 'ðŸ”’')} Fermeture des portes à double tour...",
            "ðŸ§± On empile les briques devant les salons...",
            "ðŸ¤« Chut ! Tout le monde doit dormir maintenant...",
            "â›“ï¸ On sort les chaînes et les cadenas...",
            f"{getattr(E, 'AUTORITE', 'ðŸ‘®')} Patrouille de sécurité en cours...",
            "ðŸ› ï¸ Installation des barreaux aux fenêtres..."
        ]

        progress_msg = await ctx.channel.send(f"{EMOJI_ALERT} **Initialisation du Lockdown global...**")

        theme = config_manager.get_layout_v2_theme(ctx.guild.id, ctx.guild, ctx.author, self.bot)
        accent_color = int(theme.get("color", 0xE74C3C))
        footer_text = theme.get("footer_text") or ""

        # Embed / Layout d'annonce de maintenance dans les salons
        lock_view = ui.LayoutView(timeout=180)
        container_lock = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container_lock.add_item(ui.TextDisplay(f"# {getattr(E, 'ATTENTION', 'ðŸš¨')} Maintenance du Serveur"))
        container_lock.add_item(ui.TextDisplay("Le serveur est temporairement verrouillé. L'écriture est désactivée."))
        if footer_text:
            container_lock.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container_lock.add_item(ui.TextDisplay(footer_text))
        lock_view.add_item(container_lock)

        for channel in channels:
            cid = str(channel.id)
            if cid in db:
                continue
            
            try:
                ov = channel.overwrites_for(target)
                db[cid] = {
                    "send_messages": ov.send_messages,
                    "add_reactions": ov.add_reactions,
                    "connect": ov.connect,
                    "speak": ov.speak,
                    "view_channel": ov.view_channel
                }

                if isinstance(channel, (discord.TextChannel, discord.ForumChannel)):
                    await channel.set_permissions(target, send_messages=False, add_reactions=False, view_channel=ov.view_channel)
                    await channel.send(view=lock_view)
                elif isinstance(channel, discord.VoiceChannel):
                    await channel.set_permissions(target, connect=False, view_channel=ov.view_channel)
                
                count += 1
                
                if count % 2 == 0 or count == total:
                    status = random.choice(funny_messages)
                    percentage = int((count / total) * 10)
                    bar = "â–°" * percentage + "â–±" * (10 - percentage)
                    await progress_msg.edit(content=f"{status}\n`{bar}` **{count}/{total}**")
                
                await asyncio.sleep(0.4)
            except Exception:
                continue

        db_lock.save(ctx.guild.id, db)
        _log(f"Lockdown global exécuté sur {ctx.guild.id} ({count} salons)", "SUCCESS")

        # Message de fin persistant en LayoutV2
        final_view = ui.LayoutView(timeout=180)
        container_final = ui.Container(accent_color=discord.Color(0x2ECC71), spoiler=False)
        container_final.add_item(ui.TextDisplay(f"# {getattr(E, 'VALIDE', 'âœ…')} Opération Terminée"))
        container_final.add_item(ui.TextDisplay(f"Le serveur est désormais sécurisé.\n\nðŸ”¹ **{count}** salons verrouillés.\nðŸ”¹ Visibilité d'origine préservée."))
        if footer_text:
            container_final.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container_final.add_item(ui.TextDisplay(footer_text))
        final_view.add_item(container_final)

        await progress_msg.edit(content=None, view=final_view)


async def setup(bot: commands.Bot):
    await bot.add_cog(LockAllCommand(bot))
