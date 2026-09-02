"""
COMMANDE LOCK - Verrouillage d'un salon en préservant la visibilité
==================================================================
"""

from __future__ import annotations

import traceback
import discord
from discord import ui
from discord.ext import commands

from utils.config_data import DataManager
from utils.config_emoji import Emoji as E
from utils.config_perm import ensure_command_permission, perm_command
from utils.config_theme import config_manager

# --- 1) CONFIGURATION DES LOGS ---
DEBUG_LOGS = True
ERROR_LOGS = True

def _log(msg: str, level: str = "INFO"):
    if level == "DEBUG" and not DEBUG_LOGS:
        return
    if level == "ERROR" and not ERROR_LOGS:
        return
    colors = {"INFO": "\033[94m", "SUCCESS": "\033[92m", "ERROR": "\033[91m", "WARN": "\033[93m"}
    print(f"{colors.get(level, '\033[0m')}[LOCK-{level}] {msg}\033[0m")

# --- 2) CENTRALISATION DES EMOJIS ---
EMOJI_LOCK = getattr(E, "LOCK", "ðŸ”’")
EMOJI_SUCCESS = getattr(E, "VALIDE", getattr(E, "VALIDER", "âœ…"))
EMOJI_ERROR = getattr(E, "REFUS", getattr(E, "REFUSER", "âŒ"))

# --- 3) GESTIONNAIRE DE DONNÉES ---
db_lock = DataManager("staff/moderation/lock")


class LockLayoutView(ui.LayoutView):
    def __init__(self, guild: discord.Guild, user: discord.abc.User, bot: commands.Bot, title: str, description: str, rank: str):
        super().__init__(timeout=180)
        self.guild = guild
        self.user = user
        self.bot = bot
        self.title = title
        self.description = description
        self.rank = rank
        self._build()

    def _build(self):
        self.clear_items()
        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.bot)
        accent_color = int(theme.get("color", 0xE74C3C))
        footer_text = theme.get("footer_text") or ""

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {self.title}"))
        container.add_item(ui.TextDisplay(self.description))
        container.add_item(ui.TextDisplay(f"{getattr(E, 'BOUCLIER', 'ðŸ›¡ï¸')} **Autorité :** `{self.rank}`"))

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)


class Lock(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @perm_command(level=3)
    @commands.command(name="lock", description="ðŸ”’ Verrouille l'écriture en préservant strictement la visibilité.")
    async def lock(self, ctx: commands.Context):
        if not ctx.guild:
            return

        if not await ensure_command_permission(ctx, command_name="lock"):
            return

        try:
            db = db_lock.load(ctx.guild.id) or {}
            cid = str(ctx.channel.id)
            target = ctx.guild.default_role
            
            ov = ctx.channel.overwrites_for(target)
            
            db[cid] = {
                "send_messages": ov.send_messages,
                "add_reactions": ov.add_reactions,
                "connect": ov.connect,
                "speak": ov.speak,
                "view_channel": ov.view_channel 
            }
            db_lock.save(ctx.guild.id, db)

            if isinstance(ctx.channel, (discord.TextChannel, discord.ForumChannel)):
                await ctx.channel.set_permissions(
                    target, 
                    send_messages=False, 
                    add_reactions=False,
                    view_channel=ov.view_channel
                )
            elif isinstance(ctx.channel, discord.VoiceChannel):
                await ctx.channel.set_permissions(
                    target, 
                    connect=False,
                    view_channel=ov.view_channel
                )

            _log(f"Salon {ctx.channel.id} verrouillé sur {ctx.guild.id}", "SUCCESS")

            rank = "Owner" if ctx.author.id == ctx.guild.owner_id else "Administrateur" if ctx.author.guild_permissions.administrator else "Modérateur"
            view = LockLayoutView(ctx.guild, ctx.author, self.bot, f"{getattr(E, 'LOCK', 'ðŸ”’')} Salon Verrouillé", f"Le salon {ctx.channel.mention} est fermé par {ctx.author.mention}.", rank)
            await ctx.channel.send(view=view)

        except Exception as e:
            if ERROR_LOGS:
                _log(f"Erreur critique lock : {e}", "ERROR")
            traceback.print_exc()
            await ctx.send(f"{EMOJI_ERROR} Erreur critique lors du verrouillage : {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Lock(bot))
