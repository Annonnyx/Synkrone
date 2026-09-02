"""
COGNITIVE MODULE - Ban (Bannissement permanent)
=============================================
Gestion centralisée des bannissements avec animation, notification MP, fallback UI et persistance.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import os

import discord
from discord import app_commands, ui
from discord.ext import commands

from utils.config_data import DataManager
from utils.config_emoji import Emoji as E
from utils.config_perm import ensure_command_permission, perm_command
from utils.config_theme import config_manager

# --- CONFIGURATION DES LOGS ---
DEBUG_MODE = True
ERROR_LOGS_ONLY = False
ALERT_EMOJI = getattr(E, "ATTENTION", "âš ï¸")
EMOJI_ERROR = getattr(E, "REFUS", getattr(E, "REFUSER", "âŒ"))
EMOJI_SUCCESS = getattr(E, "VALIDE", getattr(E, "VALIDER", "âœ…"))


class Ban(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = DataManager("staff/moderation/banlist_serveur")
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.tintin_path = os.path.join(self.base_dir, "tintin.png")

    def _load_bans(self, guild_id: int) -> dict:
        try:
            return self.db.load(guild_id) or {}
        except Exception as e:
            if DEBUG_MODE:
                print(f"\033[31m[ERREUR BAN] Chargement impossible pour {guild_id}: {e}\033[0m")
            return {}

    def _save_bans(self, guild_id: int, data: dict) -> None:
        try:
            self.db.save(guild_id, data)
        except Exception as e:
            if DEBUG_MODE:
                print(f"\033[31m[ERREUR BAN] Sauvegarde impossible pour {guild_id}: {e}\033[0m")

    async def _send_fallback(self, ctx: commands.Context, title: str, description: str, color: int = 0xED4245):
        guild = ctx.guild
        guild_id = guild.id if guild else None
        theme = config_manager.get_layout_v2_theme(guild_id, guild, ctx.author, self.bot, force_global=(guild is None))
        footer_text = theme.get("footer_text", "")
        view = ui.LayoutView(timeout=15)
        container = ui.Container(accent_color=discord.Color(color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {EMOJI_ERROR} {title}"))
        container.add_item(ui.TextDisplay(description))
        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))
        view.add_item(container)
        await ctx.send(view=view)

    async def _send_ban_module_tutorial(self, ctx: commands.Context):
        theme = config_manager.get_layout_v2_theme(ctx.guild.id, ctx.guild, ctx.author, self.bot)
        color = int(theme.get("color", 0x5865F2))
        footer_text = theme.get("footer_text", "")

        view = ui.LayoutView(timeout=60)
        container = ui.Container(accent_color=discord.Color(color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {ALERT_EMOJI} Tutoriel Module Bannissement"))
        container.add_item(
            ui.TextDisplay(
                "Voici les commandes disponibles :\n\n"
                "- **Â²ban <@membre|id> [raison]**\n"
                "  Exemple : `Â²ban @Pseudo Spam massif`\n"
                "- **Â²unban <id>**\n"
                "  Exemple : `Â²unban 123456789012345678`\n"
                "- **Â²tempban <@membre|id> <duree> [raison]**\n"
                "  Exemple : `Â²tempban @Pseudo 24h Flood`\n"
                "- **Â²banlist**\n"
                "  Affiche le registre des bannis et permet le deban via menu.\n\n"
                "Durees tempban supportees : `s` (secondes), `m` (minutes), `h` (heures), `j` (jours), `S` (semaines), `M` (mois), `a` (annees)."
            )
        )
        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))
        view.add_item(container)
        await ctx.send(view=view)

    async def _send_dm_notice(self, user: discord.abc.User, title: str, description: str, color: int, guild_name: str = ""):
        try:
            dm_view = ui.LayoutView(timeout=30)
            dm_container = ui.Container(accent_color=discord.Color(color), spoiler=False)
            dm_container.add_item(ui.TextDisplay(f"# {ALERT_EMOJI} {title}"))
            if guild_name:
                dm_container.add_item(ui.TextDisplay(f"Serveur : **{guild_name}**\n{description}"))
            else:
                dm_container.add_item(ui.TextDisplay(description))
            dm_view.add_item(dm_container)

            dm_file = discord.File(self.tintin_path, filename="tintin.png") if os.path.exists(self.tintin_path) else discord.utils.MISSING
            await user.send(view=dm_view, file=dm_file)
        except Exception:
            pass

    @perm_command(level=2)
    @commands.command(name="ban", description="Bannir un membre ou un utilisateur par ID avec animation et notification MP.")
    @app_commands.describe(target="ID ou mention de l'utilisateur à bannir", reason="Raison du bannissement")
    async def ban(self, ctx: commands.Context, target: str | None = None, *, reason: str = "Aucune raison fournie"):
        if not ctx.guild:
            return await self._send_fallback(ctx, "Action impossible", "Cette commande doit être utilisée sur un serveur.")

        if not await ensure_command_permission(ctx, command_name="ban"):
            return

        if not target:
            return await self._send_ban_module_tutorial(ctx)

        clean_id_str = "".join(filter(str.isdigit, target))
        if not clean_id_str:
            return await self._send_fallback(ctx, "Erreur de syntaxe", "Identifiant ou utilisateur cible invalide.")

        user_id = int(clean_id_str)
        target_user = self.bot.get_user(user_id)
        if not target_user:
            try:
                target_user = await self.bot.fetch_user(user_id)
            except Exception:
                return await self._send_fallback(ctx, "Utilisateur introuvable", f"Impossible de trouver un utilisateur Discord avec l'ID `{user_id}`.")

        theme = config_manager.get_layout_v2_theme(ctx.guild.id, ctx.guild, ctx.author, self.bot)
        color = int(theme.get("color", 0xED4245))
        footer_text = theme.get("footer_text", "")

        try:
            ban_entry = await ctx.guild.fetch_ban(target_user)
            if ban_entry:
                await self._send_dm_notice(
                    target_user,
                    "Statut du compte",
                    "Vous etes deja banni de ce serveur.",
                    color,
                    guild_name=ctx.guild.name,
                )
                return await self._send_fallback(
                    ctx,
                    "Utilisateur deja banni",
                    f"{ALERT_EMOJI} **{target_user}** est deja banni sur ce serveur. Un message prive lui a ete envoye.",
                )
        except discord.NotFound:
            pass

        member = ctx.guild.get_member(user_id)
        if member:
            if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
                return await self._send_fallback(ctx, "Erreur de hiérarchie", "Vous ne pouvez pas bannir ce membre (rôle supérieur ou égal au vôtre).")
            me_member = ctx.guild.me
            if me_member and member.top_role >= me_member.top_role:
                return await self._send_fallback(
                    ctx,
                    "Action refusee",
                    "Je ne peux pas executer cette action: ce membre a un role superieur ou egal au mien.",
                )

        bans = self._load_bans(ctx.guild.id)

        view = ui.LayoutView(timeout=30)
        container = ui.Container(accent_color=discord.Color(color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {ALERT_EMOJI} Sequence de bannissement"))
        container.add_item(ui.TextDisplay(f"{ALERT_EMOJI} **{target_user}** va etre banni dans **5** secondes."))
        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))
        view.add_item(container)

        file = discord.File(self.tintin_path, filename="tintin.png") if os.path.exists(self.tintin_path) else None
        msg = await ctx.send(view=view, file=file if file else discord.utils.MISSING)

        for i in range(4, 0, -1):
            await asyncio.sleep(1)
            container.children[1] = ui.TextDisplay(f"{ALERT_EMOJI} **{target_user}** va etre banni dans **{i}** secondes.")
            await msg.edit(view=view)

        await asyncio.sleep(1)

        try:
            await self._send_dm_notice(
                target_user,
                "Notification de bannissement",
                f"Vous avez ete banni.\nRaison : {reason}",
                color,
                guild_name=ctx.guild.name,
            )

            await ctx.guild.ban(target_user, reason=f"Par {ctx.author}: {reason}", delete_message_seconds=604800)

            now = datetime.now()
            bans[str(target_user.id)] = {
                "Nom complet": str(target_user),
                "Raison": reason,
                "Date": now.strftime("%d/%m/%Y"),
                "Heure": now.strftime("%H:%M"),
                "Modérateur": str(ctx.author),
                "Type": "BAN"
            }
            self._save_bans(ctx.guild.id, bans)

            success_container = ui.Container(accent_color=discord.Color(color), spoiler=False)
            success_container.add_item(ui.TextDisplay(f"# {EMOJI_SUCCESS} Bannissement effectue"))
            success_container.add_item(ui.TextDisplay(f"{getattr(E, 'SUPPRIMER', 'ðŸ—‘ï¸')} **{target_user}** (`{target_user.id}`) a été banni avec succès.\n**Raison :** {reason}"))
            if footer_text:
                success_container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
                success_container.add_item(ui.TextDisplay(footer_text))
            
            final_view = ui.LayoutView(timeout=10)
            final_view.add_item(success_container)
            await msg.edit(view=final_view)

            if DEBUG_MODE and not ERROR_LOGS_ONLY:
                print(f"\033[32m[SUCCÈS BAN] {target_user} banni sur {ctx.guild.name} par {ctx.author}\033[0m")

        except Exception as e:
            if isinstance(e, discord.Forbidden):
                return await self._send_fallback(
                    ctx,
                    "Permissions insuffisantes",
                    "Je ne peux pas bannir cet utilisateur (permissions manquantes ou role superieur).",
                )
            if DEBUG_MODE:
                print(f"\033[31m[ERREUR CRITIQUE BAN] {e}\033[0m")
            await self._send_fallback(ctx, "Erreur d'exécution", f"Impossible d'exécuter le bannissement : `{e}`")


async def setup(bot: commands.Bot):
    await bot.add_cog(Ban(bot))
