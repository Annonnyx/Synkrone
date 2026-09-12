"""
COMMANDE UNLOCK - Déverrouillage d'un salon verrouillé par le bot
===============================================================
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

DEBUG_LOGS = True
ERROR_LOGS = True

def _log(msg: str, level: str = "INFO"):
    if level == "DEBUG" and not DEBUG_LOGS:
        return
    if level == "ERROR" and not ERROR_LOGS:
        return
    colors = {"INFO": "\033[94m", "SUCCESS": "\033[92m", "ERROR": "\033[91m", "WARN": "\033[93m"}
    print(f"{colors.get(level, '\033[0m')}[UNLOCK-{level}] {msg}\033[0m")

EMOJI_UNLOCK = getattr(E, "UNLOCK", "ðŸ”“")
EMOJI_SUCCESS = getattr(E, "VALIDE", getattr(E, "VALIDER", "âœ…"))
EMOJI_ERROR = getattr(E, "REFUS", getattr(E, "REFUSER", "âŒ"))

db_lock = DataManager("staff/moderation/lock")


class UnlockLayoutView(ui.LayoutView):
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
        accent_color = int(theme.get("color", 0x2ECC71))
        footer_text = theme.get("footer_text") or ""

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {self.title}"))
        container.add_item(ui.TextDisplay(self.description))
        container.add_item(ui.TextDisplay(f"{getattr(E, 'BOUCLIER', 'ðŸ›¡ï¸')} **Autorité :** `{self.rank}`"))

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)


class Unlock(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @perm_command(level=3)
    @commands.hybrid_command(name="unlock", description="ðŸ”“ Déverrouille le salon actuel (si verrouillé par le bot).")
    async def unlock(self, ctx: commands.Context):
        if not ctx.guild:
            return

        if not await ensure_command_permission(ctx, command_name="unlock"):
            return
        
        db = db_lock.load(ctx.guild.id) or {}
        cid = str(ctx.channel.id)

        if not db or cid not in db:
            return await ctx.send(
                f"{EMOJI_ERROR} **Action annulée** : Ce salon n'a pas été verrouillé par le bot.\n"
                "Ceci évite de modifier accidentellement vos salons staff ou privés."
            )

        perms = db[cid]
        target = ctx.guild.default_role
        
        new_ov = discord.PermissionOverwrite(
            send_messages=perms.get("send_messages"),
            add_reactions=perms.get("add_reactions"),
            connect=perms.get("connect"),
            speak=perms.get("speak"),
            view_channel=perms.get("view_channel")
        )

        await ctx.channel.set_permissions(target, overwrite=new_ov)

        del db[cid]
        db_lock.save(ctx.guild.id, db)
        _log(f"Salon {cid} déverrouillé sur {ctx.guild.id}", "SUCCESS")

        rank = "Owner" if ctx.author.id == ctx.guild.owner_id else "Administrateur" if ctx.author.guild_permissions.administrator else "Modérateur"
        view = UnlockLayoutView(ctx.guild, ctx.author, self.bot, f"{getattr(E, 'UNLOCK', 'ðŸ”“')} Salon Déverrouillé", f"Le salon {ctx.channel.mention} a été restauré avec succès par {ctx.author.mention}.", rank)
        await ctx.channel.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Unlock(bot))
