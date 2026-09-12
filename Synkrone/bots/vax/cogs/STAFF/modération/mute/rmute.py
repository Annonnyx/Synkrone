"""
COMMANDE RMUTE - Mute local permanent dans le salon actuel
=========================================================
"""

from __future__ import annotations

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
    print(f"{colors.get(level, '\033[0m')}[RMUTE-{level}] {msg}\033[0m")


EMOJI_MUTE = getattr(E, "MUTE", getattr(E, "ATTENTION", "ðŸ”‡"))
EMOJI_SUCCESS = getattr(E, "VALIDE", getattr(E, "VALIDER", "âœ…"))
EMOJI_ERROR = getattr(E, "REFUS", getattr(E, "REFUSER", "âŒ"))


class RMuteLayoutView(ui.LayoutView):
    def __init__(self, guild: discord.Guild | None, user: discord.abc.User, bot: commands.Bot, title: str, description: str):
        super().__init__(timeout=180)
        self.guild = guild
        self.user = user
        self.bot = bot
        self.title = title
        self.description = description
        self._build()

    def _build(self):
        self.clear_items()
        theme = config_manager.get_layout_v2_theme(
            self.guild.id if self.guild else None, self.guild, self.user, self.bot, force_global=(self.guild is None)
        )
        accent_color = int(theme.get("color", discord.Color.red().value))
        footer_text = theme.get("footer_text") or ""

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {EMOJI_MUTE} {self.title}"))
        container.add_item(ui.TextDisplay(self.description))

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)


class RMute(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data_manager = DataManager("staff/moderation/mute_local")

    async def _send_fallback(self, ctx: commands.Context, title: str, description: str):
        view = RMuteLayoutView(ctx.guild, ctx.author, self.bot, title, description)
        await ctx.send(view=view)

    def get_syntax_help(self) -> str:
        return (
            f"### {EMOJI_ERROR} Erreur de Syntaxe : RMute\n"
            "Restreint l'écriture d'un membre dans ce salon de façon permanente.\n\n"
            "**Format :** `!rmute <@membre/ID> [raison]`\n\n"
            "*Note : La raison est obligatoire pour les non-admins.*"
        )

    @perm_command(level=2)
    @commands.hybrid_command(name="rmute", description="ðŸ”‡ Mute local permanent (Salon actuel).")
    async def rmute(self, ctx: commands.Context, membre: discord.Member = None, *, raison: str = None):
        if not ctx.guild:
            return await ctx.send(f"{EMOJI_ERROR} Cette commande requiert un serveur.")

        if not await ensure_command_permission(ctx, command_name="rmute"):
            return

        # Fallback tutoriel usage de commandes (Point 3)
        if membre is None:
            return await self._send_fallback(ctx, "Aide RMute", self.get_syntax_help())

        if not ctx.author.guild_permissions.administrator and not raison:
            return await self._send_fallback(ctx, "Aide RMute - Raison Requise", self.get_syntax_help())

        try:
            data = self.data_manager.load(ctx.guild.id) or {}
        except Exception:
            data = {}

        key = f"{membre.id}_{ctx.channel.id}"
        if key in data:
            return await self._send_fallback(ctx, "Déjà restreint", f"{EMOJI_ERROR} {membre.mention} est déjà restreint dans ce salon.")

        if membre.top_role >= ctx.guild.me.top_role:
            return await self._send_fallback(ctx, "Erreur Hiérarchie", f"{EMOJI_ERROR} Impossible de restreindre ce membre.")

        try:
            await ctx.channel.set_permissions(membre, send_messages=False, reason=f"RMute: {raison or 'Admin'}")
            data[key] = {
                "user_id": membre.id,
                "channel_id": ctx.channel.id,
                "reason": raison or "Administrateur",
                "expires_at": 9999999999,
            }
            self.data_manager.save(ctx.guild.id, data)
            _log(f"RMute appliqué sur {membre.id} dans {ctx.channel.id}", "SUCCESS")

            desc = f"{membre.mention} est mute définitivement dans #{ctx.channel.name}.\n**Raison :** {raison or 'Administrateur'}"
            view = RMuteLayoutView(ctx.guild, ctx.author, self.bot, "Mute Salon Permanent", desc)
            await ctx.send(view=view)
        except Exception as e:
            if ERROR_LOGS:
                _log(f"Erreur RMute: {e}", "ERROR")
            await self._send_fallback(ctx, "Erreur", f"{EMOJI_ERROR} Erreur d'exécution : {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(RMute(bot))
