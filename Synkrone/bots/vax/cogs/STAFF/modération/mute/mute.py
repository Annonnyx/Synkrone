"""
COMMANDE MUTE - Mute global permanent sur l'ensemble du serveur
===============================================================
"""

from __future__ import annotations

import json
from pathlib import Path

import discord
from discord import ui
from discord.ext import commands

from utils.config_data import DataManager
from utils.config_emoji import Emoji as E
from utils.config_perm import ensure_command_permission, perm_command
from utils.config_theme import config_manager

# --- ARCHITECTURE DES LOGS ---
DEBUG_LOGS = True
ERROR_LOGS = True


def _log(msg: str, level: str = "INFO"):
    if level == "DEBUG" and not DEBUG_LOGS:
        return
    if level == "ERROR" and not ERROR_LOGS:
        return
    colors = {"INFO": "\033[94m", "SUCCESS": "\033[92m", "ERROR": "\033[91m", "WARN": "\033[93m"}
    print(f"{colors.get(level, '\033[0m')}[MUTE-{level}] {msg}\033[0m")


# --- CENTRALISATION DES EMOJIS & FALLBACKS (Point 1) ---
EMOJI_MUTE = getattr(E, "MUTE", getattr(E, "ATTENTION", "ðŸ”‡"))
EMOJI_SUCCESS = getattr(E, "VALIDE", getattr(E, "VALIDER", "âœ…"))
EMOJI_ERROR = getattr(E, "REFUS", getattr(E, "REFUSER", "âŒ"))
EMOJI_WARN = getattr(E, "ATTENTION", "âš ï¸")


class MuteLayoutView(ui.LayoutView):
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
        guild_id = self.guild.id if self.guild else None
        
        # Fallback theme global (Point 2)
        theme = config_manager.get_layout_v2_theme(
            guild_id, self.guild, self.user, self.bot, force_global=(self.guild is None)
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


class Mute(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.mute_role_cache: dict[int, discord.Role] = {}
        self.data_manager = DataManager("staff/moderation/mute_global")

    async def _send_fallback(self, ctx: commands.Context, title: str, description: str):
        view = MuteLayoutView(ctx.guild, ctx.author, self.bot, title, description)
        await ctx.send(view=view)

    async def get_mute_role(self, guild: discord.Guild) -> discord.Role:
        role = self.mute_role_cache.get(guild.id)
        if role and discord.utils.get(guild.roles, id=role.id):
            return role

        role = discord.utils.get(guild.roles, name="ðŸ¤«â”‚ð‘´ð’–ð’†ð’•")
        if not role:
            role = await guild.create_role(name="ðŸ¤«â”‚ð‘´ð’–ð’†ð’•", reason="Système de Mute Global Vax")
            for channel in guild.channels:
                try:
                    await channel.set_permissions(role, send_messages=False, speak=False, add_reactions=False)
                except Exception:
                    continue

        self.mute_role_cache[guild.id] = role
        return role

    def get_syntax_help(self) -> str:
        return (
            f"### {EMOJI_ERROR} Aide & Syntaxe : Mute\n"
            "Mute un membre de façon **permanente** sur tout le serveur.\n\n"
            "**Format :** `!mute <@membre/ID> [raison]`\n\n"
            "**Exemples :**\n"
            "â€¢ `!mute @Vexa Spam publicitaire`\n"
            "â€¢ `!mute 136678283737373737 Infraction`\n\n"
            "*Note : La raison est obligatoire si vous n'êtes pas Administrateur.*"
        )

    @perm_command(level=2)
    @commands.hybrid_command(name="mute", description="ðŸ”‡ Mute global permanent (Tout le serveur).")
    async def mute(self, ctx: commands.Context, membre: discord.Member = None, *, raison: str = None):
        if not ctx.guild:
            return await ctx.send(f"{EMOJI_ERROR} Cette commande doit être exécutée sur un serveur.")

        if not await ensure_command_permission(ctx, command_name="mute"):
            return

        # Fallback tutoriel usage de commandes (Point 3)
        if membre is None:
            _log(f"Utilisation sans argument par {ctx.author}", "WARN")
            return await self._send_fallback(ctx, "Guide d'Utilisation : Mute", self.get_syntax_help())

        if not ctx.author.guild_permissions.administrator and not raison:
            return await self._send_fallback(ctx, "Aide Mute - Raison Requise", self.get_syntax_help())

        # Fallback permissions et hiérarchie (Point 7)
        if membre.top_role >= ctx.guild.me.top_role:
            return await self._send_fallback(
                ctx, 
                "Erreur de Hiérarchie", 
                f"{EMOJI_ERROR} Impossible de sanctionner {membre.mention} : son rôle est supérieur ou égal au mien."
            )

        role = await self.get_mute_role(ctx.guild)

        try:
            # Fallback état utilisateur déjà banni/mute (Adapté pour le rôle mute)
            if role in membre.roles:
                await self._send_fallback(
                    ctx, 
                    "Avertissement", 
                    f"{EMOJI_WARN} {membre.mention} possède déjà le rôle muet, mise à  jour des métadonnées."
                )

            await membre.add_roles(role, reason=f"Mute Permanent par {ctx.author}: {raison or 'Admin'}")

            # Fallback persistance locale (Point 9)
            try:
                data = self.data_manager.load(ctx.guild.id) or {}
            except Exception as e:
                _log(f"Erreur de lecture DB locale: {e}", "ERROR")
                data = {}

            data[str(membre.id)] = {
                "user_id": membre.id,
                "reason": raison or "Administrateur",
                "expires_at": 9999999999,
            }
            self.data_manager.save(ctx.guild.id, data)
            _log(f"Membre {membre.id} mute globalement sur {ctx.guild.id}", "SUCCESS")

            desc = f"{membre.mention} a été mute **définitivement** sur tout le serveur.\n**Raison :** {raison or 'Administrateur'}"
            view = MuteLayoutView(ctx.guild, ctx.author, self.bot, "Mute Global Définitif", desc)
            await ctx.send(view=view)

            # Fallback MP non bloquant (Point 4 & 8)
            try:
                mp_view = MuteLayoutView(
                    ctx.guild, ctx.author, self.bot, 
                    "Sanction Permanente", 
                    f"Vous avez été mute de façon **définitive** sur **{ctx.guild.name}**.\n**Raison :** {raison or 'Non spécifiée'}"
                )
                await membre.send(view=mp_view)
            except Exception:
                _log(f"Impossible d'envoyer un MP à {membre.id} (DMs fermés)", "DEBUG")

        except discord.Forbidden:
            return await self._send_fallback(ctx, "Permission Refusée", f"{EMOJI_ERROR} Je n'ai pas les permissions requises (Manage Roles).")
        except Exception as e:
            if ERROR_LOGS:
                _log(f"Erreur critique application mute: {e}", "ERROR")
            await self._send_fallback(ctx, "Erreur Exécution", f"{EMOJI_ERROR} Une erreur est survenue : {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Mute(bot))
