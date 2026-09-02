"""
COMMANDE WARN - Système d'avertissement formel
================================================
Intègre le LayoutV2, la gestion de permissions centralisée et le modal interactif.
"""

from __future__ import annotations

import datetime
import os
import traceback

import discord
from discord import app_commands, ui
from discord.ext import commands

from utils.config_data import DataManager
from utils.config_emoji import Emoji as E
from utils.config_perm import ensure_command_permission, perm_command
from utils.config_theme import config_manager

# --- 1) VARIABLES GLOBALES DE DEBUG ---
DEBUG_LOGS = True
ERROR_LOGS = True

def _log(msg: str, level: str = "INFO"):
    if level == "DEBUG" and not DEBUG_LOGS:
        return
    if level == "ERROR" and not ERROR_LOGS:
        return
    colors = {"INFO": "\033[94m", "SUCCESS": "\033[92m", "ERROR": "\033[91m", "WARN": "\033[93m"}
    print(f"{colors.get(level, '\033[0m')}[MOD-WARN - {level}] {msg}\033[0m")

# --- 2) CENTRALISATION DES EMOJIS ---
EMOJI_WARN = getattr(E, "ATTENTION", "âš ï¸")
EMOJI_SUCCESS = getattr(E, "VALIDE", getattr(E, "VALIDER", "âœ…"))
EMOJI_ERROR = getattr(E, "REFUS", getattr(E, "REFUSER", "âŒ"))

# --- 3) GESTIONNAIRE DE DONNÉES ---
db_warns = DataManager("staff/moderation/warns")

class WarnModal(ui.Modal, title="Sanctionner un utilisateur"):
    raison = ui.TextInput(
        label="Raison de l'avertissement", 
        style=discord.TextStyle.paragraph, 
        placeholder="Indiquez la raison précise de la sanction...", 
        required=True, 
        min_length=4
    )

    def __init__(self, bot: commands.Bot, cible_user: discord.Member, cog_instance: "ModerationWarn"):
        super().__init__()
        self.bot = bot
        self.cible_user = cible_user
        self.cog = cog_instance

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.save_and_send_warn(interaction, self.cible_user, self.raison.value)


class WarnLayoutView(ui.LayoutView):
    def __init__(self, guild: discord.Guild, user: discord.abc.User, bot: commands.Bot, title: str, description: str, color_override: discord.Color = None):
        super().__init__(timeout=180)
        self.guild = guild
        self.user = user
        self.bot = bot
        self.title = title
        self.description = description
        self.color_override = color_override
        self._build()

    def _build(self):
        self.clear_items()
        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.bot)
        accent_color = self.color_override.value if self.color_override else int(theme.get("color", discord.Color.orange().value))
        footer_text = theme.get("footer_text") or ""

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {self.title}"))
        container.add_item(ui.TextDisplay(self.description))

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)


class ModerationWarn(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _send_persistent_response(self, context, title: str, description: str, color: discord.Color = None):
        """Retours persistants et publics  (zéro message éphémère)."""
        guild = context.guild
        author = context.user if isinstance(context, discord.Interaction) else context.author
        view = WarnLayoutView(guild, author, self.bot, title, description, color_override=color)
        
        if isinstance(context, discord.Interaction):
            if context.response.is_done():
                await context.followup.send(view=view, ephemeral=False)
            else:
                await context.response.send_message(view=view, ephemeral=False)
        else:
            await context.send(view=view)

    def get_staff_rank(self, member: discord.Member) -> str:
        if member.guild.owner_id == member.id:
            return "Propriétaire"
        elif member.guild_permissions.administrator:
            return "Administrateur"
        return "Modérateur"

    async def save_and_send_warn(self, context, cible_user: discord.Member, raison: str):
        guild = context.guild
        author = context.user if isinstance(context, discord.Interaction) else context.author
        
        warn_id = os.urandom(4).hex()
        staff_rank = self.get_staff_rank(author)
        timestamp = datetime.datetime.now().strftime("%d/%m/%Y à %H:%M")
        
        warn_data = {
            "id": warn_id,
            "staff_id": author.id,
            "staff_name": author.display_name,
            "staff_rank": staff_rank,
            "raison": raison,
            "timestamp": timestamp
        }

        try:
            data = db_warns.load(guild.id) or {}
            user_key = str(cible_user.id)
            if user_key not in data:
                data[user_key] = []
            
            data[user_key].append(warn_data)
            db_warns.save(guild.id, data)
            _log(f"Avertissement [{warn_id}] appliqué à {cible_user.id} par {author.id}", "SUCCESS")
        except Exception as e:
            _log(f"Échec de la sauvegarde de l'avertissement : {e}", "ERROR")

        desc = (
            f"{getattr(E, 'PROFIL', 'ðŸ‘¤')} **Cible :** {cible_user.mention} (`{cible_user.id}`)\n"
            f"{getattr(E, 'BOUCLIER', 'ðŸ›¡ï¸')} **Staff :** {author.mention} ({staff_rank})\n\n"
            f"{getattr(E, 'MEMO', 'ðŸ“')} **Raison :**\n```\n{raison}\n```"
        )
        await self._send_persistent_response(context, f"{EMOJI_WARN} Avertissement Appliqué", desc)

        try:
            mp_view = WarnLayoutView(guild, author, self.bot, f"{EMOJI_WARN} Sanction - {guild.name}", desc)
            await cible_user.send(view=mp_view)
        except discord.Forbidden:
            _log(f"Impossible d'envoyer le MP à {cible_user.id} (DMs fermés)", "DEBUG")

    @perm_command(level=3)
    @commands.command(name="warn", description="Avertir formellement un membre du serveur.")
    @app_commands.describe(utilisateur="Le membre à avertir", raison="Raison (optionnel en slash, ouvre un formulaire)")
    async def warn(self, ctx: commands.Context, utilisateur: discord.Member = None, *, raison: str = None):
        if not ctx.guild:
            return

        if not await ensure_command_permission(ctx, command_name="warn"):
            return

        # Fallback tutoriel usage / arguments manquants
        if utilisateur is None:
            help_desc = (
                f"### {getattr(E, 'ERREUR', 'âŒ')} Guide d'utilisation : Warn\n"
                "Permet d'enregistrer un avertissement formel dans le casier d'un membre.\n\n"
                "**Format :** `!warn <@membre/ID> [raison]`\n"
                "*(Si aucune raison n'est fournie en slash, un formulaire interactif s'ouvrira.)*"
            )
            return await self._send_persistent_response(ctx, "Guide d'Utilisation", help_desc, discord.Color.orange())

        if utilisateur.id == ctx.author.id:
            return await self._send_persistent_response(ctx, f"{EMOJI_ERROR} Action Interdite", "Vous ne pouvez pas vous avertir vous-même.", discord.Color.red())
        if utilisateur.bot:
            return await self._send_persistent_response(ctx, f"{EMOJI_ERROR} Action Interdite", "Les bots ne peuvent pas recevoir d'avertissements.", discord.Color.red())
        if utilisateur.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            return await self._send_persistent_response(ctx, f"{EMOJI_ERROR} Erreur de Hiérarchie", "Vous ne pouvez pas avertir un membre dont le rôle est supérieur ou égal au vôtre.", discord.Color.red())

        if ctx.interaction and not raison:
            return await ctx.interaction.response.send_modal(WarnModal(self.bot, utilisateur, self))

        if not raison:
            return await self._send_persistent_response(ctx, f"{EMOJI_ERROR} Syntaxe Invalide", f"Vous devez obligatoirement fournir une raison.\nUsage: `{ctx.prefix}warn {utilisateur.mention} <raison>`", discord.Color.red())

        await self.save_and_send_warn(ctx, utilisateur, raison)

    @warn.error
    async def warn_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await self._send_persistent_response(ctx, f"{EMOJI_ERROR} Paramètre Manquant", f"Usage incorrect.\nFormat : `{ctx.prefix}warn <@membre> <raison>`", discord.Color.red())
        else:
            _log(f"Erreur inattendue : {error}", "ERROR")
            traceback.print_exc()

async def setup(bot: commands.Bot):
    await bot.add_cog(ModerationWarn(bot))
