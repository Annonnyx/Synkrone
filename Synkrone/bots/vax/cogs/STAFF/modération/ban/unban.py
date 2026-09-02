"""
COGNITIVE MODULE - Unban (Débannissement)
========================================
Module de levée de sanction avec retour Layout V2 persistant et visible dans le salon textuel.
"""

from __future__ import annotations

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


class Unban(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = DataManager("staff/moderation/banlist_serveur")

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

    async def _send_dm_unban(self, user: discord.User, guild_name: str, color: int):
        try:
            dm_view = ui.LayoutView(timeout=20)
            dm_container = ui.Container(accent_color=discord.Color(color), spoiler=False)
            dm_container.add_item(ui.TextDisplay("# â™»ï¸ Notification de debannissement"))
            dm_container.add_item(ui.TextDisplay(f"Vous avez ete debanni du serveur **{guild_name}**."))
            dm_view.add_item(dm_container)
            await user.send(view=dm_view)
        except Exception:
            pass

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

    @perm_command(level=2)
    @commands.command(name="unban", description="Débannir un utilisateur par son ID Discord.")
    @app_commands.describe(user_id="L'ID Discord exact de l'utilisateur à débannir")
    async def unban(self, ctx: commands.Context, user_id: str | None = None):
        if not ctx.guild:
            return await self._send_fallback(ctx, "Action impossible", "Cette commande doit être utilisée sur un serveur.")

        if not await ensure_command_permission(ctx, command_name="unban"):
            return

        if not user_id:
            return await self._send_ban_module_tutorial(ctx)

        clean_id_str = "".join(filter(str.isdigit, user_id))
        if not clean_id_str:
            return await self._send_fallback(ctx, "Erreur de syntaxe", "Identifiant utilisateur invalide.")

        bans = self.db.load(ctx.guild.id) or {}
        uid_int = int(clean_id_str)

        try:
            target_user = await self.bot.fetch_user(uid_int)

            # Verifie d'abord l'etat reel sur Discord pour un message explicite.
            try:
                await ctx.guild.fetch_ban(discord.Object(id=uid_int))
            except discord.NotFound:
                if clean_id_str in bans:
                    bans.pop(clean_id_str, None)
                    self.db.save(ctx.guild.id, bans)
                return await self._send_fallback(
                    ctx,
                    "Utilisateur non banni",
                    f"{ALERT_EMOJI} Cet utilisateur n'est pas banni sur ce serveur.",
                    color=0xFAA61A,
                )
            
            # Exécution de l'unban sur l'API Discord
            await ctx.guild.unban(target_user, reason=f"Débannissement par {ctx.author}")

            # Nettoyage de la base de données locale
            bans.pop(clean_id_str, None)
            self.db.save(ctx.guild.id, bans)

            theme = config_manager.get_layout_v2_theme(ctx.guild.id, ctx.guild, ctx.author, self.bot)
            color = int(theme.get("color", 0x57F287))
            footer_text = theme.get("footer_text", "")

            # LayoutV2 persistant et visible dans le salon (garanti sans mode éphémère)
            view = ui.LayoutView(timeout=30)
            container = ui.Container(accent_color=discord.Color(color), spoiler=False)
            container.add_item(ui.TextDisplay(f"# {EMOJI_SUCCESS} Debannissement reussi"))
            container.add_item(ui.TextDisplay(f"â™»ï¸ L'utilisateur **{target_user}** (`{clean_id_str}`) a été débanni avec succès par {ctx.author.mention}."))
            if footer_text:
                container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
                container.add_item(ui.TextDisplay(footer_text))
            view.add_item(container)

            await ctx.send(view=view)
            await self._send_dm_unban(target_user, ctx.guild.name, color)

            if DEBUG_MODE and not ERROR_LOGS_ONLY:
                print(f"\033[32m[SUCCÈS UNBAN] {target_user} ({clean_id_str}) débanni sur {ctx.guild.name} par {ctx.author}\033[0m")

        except discord.NotFound:
            if clean_id_str in bans:
                bans.pop(clean_id_str, None)
                self.db.save(ctx.guild.id, bans)
            await self._send_fallback(
                ctx,
                "Utilisateur non banni",
                f"{ALERT_EMOJI} Cet utilisateur n'est pas banni sur ce serveur (ou l'ID est incorrect).",
                color=0xFAA61A,
            )
        except discord.Forbidden:
            await self._send_fallback(
                ctx,
                "Permissions insuffisantes",
                "Je ne peux pas debannir cet utilisateur (permissions manquantes ou role superieur).",
            )
        except Exception as e:
            if DEBUG_MODE:
                print(f"\033[31m[ERREUR CRITIQUE UNBAN] {e}\033[0m")
            await self._send_fallback(ctx, "Erreur d'exécution", f"Une erreur est survenue : `{e}`")


async def setup(bot: commands.Bot):
    await bot.add_cog(Unban(bot))
