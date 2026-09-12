"""
COMMANDE UNLOCKALL - Réouverture complète de tous les salons du serveur
=====================================================================
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
    print(f"{colors.get(level, '\033[0m')}[UNLOCKALL-{level}] {msg}\033[0m")

EMOJI_UNLOCK = getattr(E, "UNLOCK", "ðŸ”“")
EMOJI_SUCCESS = getattr(E, "VALIDE", getattr(E, "VALIDER", "âœ…"))
EMOJI_ERROR = getattr(E, "REFUS", getattr(E, "REFUSER", "âŒ"))

db_lock = DataManager("staff/moderation/lock")


class UnlockAllCommand(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @perm_command(level=1)
    @commands.hybrid_command(name="unlockall", description="ðŸ”“ Réouverture complète du serveur.")
    async def unlockall(self, ctx: commands.Context):
        if not ctx.guild:
            return

        if not await ensure_command_permission(ctx, command_name="unlockall"):
            return
        
        db = db_lock.load(ctx.guild.id) or {}
        if not db:
            return await ctx.send(f"{EMOJI_ERROR} Aucune donnée de lockdown trouvée pour ce serveur.")
        
        total = len(db)
        count = 0
        target = ctx.guild.default_role
        
        funny_messages = [
            "ðŸ”‘ On retrouve les clés au fond des poches...",
            f"{getattr(E, 'UNLOCK', 'ðŸ”“')} Déblocage des verrous en cours...",
            "ðŸŽˆ C'est la fête, on rouvre tout !",
            "ðŸ§¹ On retire les rubans de sécurité...",
            f"{getattr(E, 'ECLAIR', 'âš¡')} Restauration de la parole pour tous...",
            f"{getattr(E, 'UNLOCK', 'ðŸ”“')} Les membres peuvent à nouveau s'exprimer !"
        ]

        progress_msg = await ctx.channel.send(f"{EMOJI_UNLOCK} **Lancement de la réouverture globale...**")

        theme = config_manager.get_layout_v2_theme(ctx.guild.id, ctx.guild, ctx.author, self.bot)
        accent_color = int(theme.get("color", 0x2ECC71))
        footer_text = theme.get("footer_text") or ""

        unlock_view = ui.LayoutView(timeout=180)
        container_unlock = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container_unlock.add_item(ui.TextDisplay(f"# {getattr(E, 'UNLOCK', 'ðŸ”“')} Fin de Maintenance"))
        container_unlock.add_item(ui.TextDisplay("Le serveur est de nouveau accessible. Merci de votre patience !"))
        if footer_text:
            container_unlock.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container_unlock.add_item(ui.TextDisplay(footer_text))
        unlock_view.add_item(container_unlock)

        for cid, perms in list(db.items()):
            channel = ctx.guild.get_channel(int(cid))
            if channel:
                try:
                    new_ov = discord.PermissionOverwrite(
                        send_messages=perms.get("send_messages"),
                        add_reactions=perms.get("add_reactions"),
                        connect=perms.get("connect"),
                        speak=perms.get("speak"),
                        view_channel=perms.get("view_channel")
                    )
                    await channel.set_permissions(target, overwrite=new_ov)
                    
                    if isinstance(channel, (discord.TextChannel, discord.ForumChannel)):
                        await channel.send(view=unlock_view)
                    
                    count += 1
                    if count % 2 == 0 or count == total:
                        status = random.choice(funny_messages)
                        percentage = int((count / total) * 10)
                        bar = "â–°" * percentage + "â–±" * (10 - percentage)
                        await progress_msg.edit(content=f"{status}\n`{bar}` **{count}/{total}**")
                    
                    await asyncio.sleep(0.4)
                except Exception:
                    pass
            del db[cid]

        db_lock.save(ctx.guild.id, db)
        _log(f"Réouverture globale exécutée sur {ctx.guild.id} ({count} salons)", "SUCCESS")

        final_view = ui.LayoutView(timeout=180)
        container_final = ui.Container(accent_color=discord.Color(0x3498DB), spoiler=False)
        container_final.add_item(ui.TextDisplay("# âœ¨ Serveur Restauré"))
        container_final.add_item(ui.TextDisplay(f"La réouverture est terminée.\n\nðŸ”¹ **{count}** salons restaurés.\nðŸ”¹ Les permissions d'origine sont de retour."))
        if footer_text:
            container_final.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container_final.add_item(ui.TextDisplay(footer_text))
        final_view.add_item(container_final)

        await progress_msg.edit(content=None, view=final_view)


async def setup(bot: commands.Bot):
    await bot.add_cog(UnlockAllCommand(bot))
