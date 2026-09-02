"""
COMMANDE TEMPMUTE - Mute global temporaire avec parsing d'unités
==============================================================
"""

from __future__ import annotations

import re
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
    print(f"{colors.get(level, '\033[0m')}[TEMPMUTE-{level}] {msg}\033[0m")


EMOJI_TIME = getattr(E, "TEMPS", getattr(E, "ATTENTION", "â³"))
EMOJI_SUCCESS = getattr(E, "VALIDE", getattr(E, "VALIDER", "âœ…"))
EMOJI_ERROR = getattr(E, "REFUS", getattr(E, "REFUSER", "âŒ"))


class TempMuteLayoutView(ui.LayoutView):
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
        accent_color = int(theme.get("color", discord.Color.orange().value))
        footer_text = theme.get("footer_text") or ""

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {EMOJI_TIME} {self.title}"))
        container.add_item(ui.TextDisplay(self.description))

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)


class TempMute(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.mute_role_cache: dict[int, discord.Role] = {}
        self.data_manager = DataManager("staff/moderation/mute_global")

    async def _send_fallback(self, ctx: commands.Context, title: str, description: str):
        view = TempMuteLayoutView(ctx.guild, ctx.author, self.bot, title, description)
        await ctx.send(view=view)

    async def get_mute_role(self, guild: discord.Guild) -> discord.Role:
        role = self.mute_role_cache.get(guild.id)
        if role and discord.utils.get(guild.roles, id=role.id):
            return role

        role = discord.utils.get(guild.roles, name="ðŸ¤«â”‚ð‘´ð’–ð’†ð’•")
        if not role:
            role = await guild.create_role(name="ðŸ¤«â”‚ð‘´ð’–ð’†ð’•", reason="Système TempMute Vax")
            for channel in guild.channels:
                try:
                    await channel.set_permissions(role, send_messages=False, speak=False)
                except Exception:
                    continue
        self.mute_role_cache[guild.id] = role
        return role

    def get_syntax_help(self) -> str:
        return (
            f"### {EMOJI_ERROR} Aide : TempMute\n"
            "Mute un membre temporairement sur l'ensemble du serveur.\n\n"
            "**Format :** `!tempmute <@membre/ID> <durée> [raison]`\n"
            "**Unités acceptées :** `s`, `m`, `h`, `d`."
        )

    @perm_command(level=2)
    @commands.command(name="tempmute", description="â³ Mute global temporaire.")
    async def tempmute(self, ctx: commands.Context, membre: discord.Member = None, durée: str = None, *, raison: str = None):
        if not ctx.guild:
            return await ctx.send(f"{EMOJI_ERROR} Cette commande nécessite un serveur.")

        if not await ensure_command_permission(ctx, command_name="tempmute"):
            return

        # Fallback tutoriel usage de commandes (Point 3)
        if membre is None or durée is None:
            return await self._send_fallback(ctx, "Guide TempMute", self.get_syntax_help())

        units = {"d": 86400, "h": 3600, "m": 60, "s": 1}
        seconds = 0
        for val, unit in re.findall(r"(\d+)([dhms])", durée.lower()):
            seconds += int(val) * units[unit]

        if seconds <= 0 or (not ctx.author.guild_permissions.administrator and not raison):
            return await self._send_fallback(ctx, "Aide TempMute", self.get_syntax_help())

        if membre.top_role >= ctx.guild.me.top_role:
            return await self._send_fallback(ctx, "Hiérarchie", f"{EMOJI_ERROR} Rôle supérieur ou égal au mien.")

        role = await self.get_mute_role(ctx.guild)

        try:
            await membre.add_roles(role, reason=f"TempMute par {ctx.author}: {raison or 'Admin'}")
            
            try:
                data = self.data_manager.load(ctx.guild.id) or {}
            except Exception:
                data = {}

            data[str(membre.id)] = {
                "user_id": membre.id,
                "reason": raison or "Administrateur",
                "expires_at": discord.utils.utcnow().timestamp() + seconds,
            }
            self.data_manager.save(ctx.guild.id, data)
            _log(f"TempMute global appliqué sur {membre.id} pour {durée}", "SUCCESS")

            desc = f"{membre.mention} est muet sur **tout le serveur**.\n**Durée :** {durée}\n**Raison :** {raison or 'Administrateur'}"
            view = TempMuteLayoutView(ctx.guild, ctx.author, self.bot, "Sanction Temporaire Appliquée", desc)
            await ctx.send(view=view)
        except Exception as e:
            if ERROR_LOGS:
                _log(f"Erreur TempMute: {e}", "ERROR")
            await self._send_fallback(ctx, "Erreur", f"{EMOJI_ERROR} Échec de l'application : {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(TempMute(bot))
