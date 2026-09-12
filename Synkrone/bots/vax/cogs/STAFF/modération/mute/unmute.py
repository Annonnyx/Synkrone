"""
COMMANDE UNMUTE - Suppression immédiate de toute sanction de mute
================================================================
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
    print(f"{colors.get(level, '\033[0m')}[UNMUTE-{level}] {msg}\033[0m")


EMOJI_SOUND = getattr(E, "SON", getattr(E, "ATTENTION", "🔊"))
EMOJI_SUCCESS = getattr(E, "VALIDE", getattr(E, "VALIDER", "✅"))
EMOJI_ERROR = getattr(E, "REFUS", getattr(E, "REFUSER", "❌"))


class UnmuteLayoutView(ui.LayoutView):
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
        accent_color = int(theme.get("color", discord.Color.green().value))
        footer_text = theme.get("footer_text") or ""

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {EMOJI_SOUND} {self.title}"))
        container.add_item(ui.TextDisplay(self.description))

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)


class Unmute(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data_manager_global = DataManager("staff/moderation/mute_global")
        self.data_manager_local = DataManager("staff/moderation/mute_local")

    async def _send_fallback(self, ctx: commands.Context, title: str, description: str):
        view = UnmuteLayoutView(ctx.guild, ctx.author, self.bot, title, description)
        await ctx.send(view=view)

    def get_syntax_help(self) -> str:
        return (
            f"### {EMOJI_ERROR} Aide : Unmute\n"
            "Retire les sanctions d'un membre.\n\n"
            "**Format :** `!unmute <@membre/ID> [raison]`"
        )

    @perm_command(level=2)
    @commands.hybrid_command(name="unmute", description="🔊 Démute immédiatement un utilisateur.")
    @commands.has_permissions(moderate_members=True)
    async def unmute(self, ctx: commands.Context, member: discord.Member = None, *, reason: str = None):
        if not ctx.guild:
            return await ctx.send(f"{EMOJI_ERROR} Cette commande requiert un serveur.")

        if not await ensure_command_permission(ctx, command_name="unmute"):
            return

        # Fallback tutoriel usage de commandes (Point 3)
        if member is None:
            return await self._send_fallback(ctx, "Guide Unmute", self.get_syntax_help())

        try:
            dg = self.data_manager_global.load(ctx.guild.id) or {}
            dl = self.data_manager_local.load(ctx.guild.id) or {}
        except Exception:
            dg, dl = {}, {}

        found = False

        if str(member.id) in dg:
            dg.pop(str(member.id))
            self.data_manager_global.save(ctx.guild.id, dg)
            found = True

        local_keys_to_remove = [k for k in dl.keys() if k.startswith(f"{member.id}_")]
        if local_keys_to_remove:
            for k in local_keys_to_remove:
                dl.pop(k)
                chan_id = k.split("_")[1]
                chan = ctx.guild.get_channel(int(chan_id))
                if chan:
                    try:
                        await chan.set_permissions(member, overwrite=None)
                    except Exception:
                        pass
            self.data_manager_local.save(ctx.guild.id, dl)
            found = True

        mute_role = discord.utils.get(ctx.guild.roles, name="🤫│𝑴𝒖𝒆𝒕")
        if mute_role and mute_role in member.roles:
            try:
                await member.remove_roles(mute_role, reason=reason or "Unmute par commande")
                found = True
            except Exception:
                pass

        if found:
            _log(f"Utilisateur {member.id} démute sur {ctx.guild.id}", "SUCCESS")
            view = UnmuteLayoutView(ctx.guild, ctx.author, self.bot, "Sanction Levée", f"🔊 {member.mention} a été démute et retiré des registres.")
            await ctx.send(view=view)
        else:
            await self._send_fallback(ctx, "Introuvable", f"{EMOJI_ERROR} {member.mention} n'a aucune sanction active enregistrée dans les données locales.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Unmute(bot))