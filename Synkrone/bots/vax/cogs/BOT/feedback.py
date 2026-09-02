# ==============================================================================
# cogs/public/utilitaires/feedback.py - Vax v3 (Feedback Interactif LayoutV2)
# ==============================================================================

from __future__ import annotations

# 1) Variables globales de log (Architecture & Configuration Initiale)
DEBUG_MODE = False
ERROR_ONLY_MODE = True

import discord
from discord import app_commands, ui
from discord.ext import commands
from typing import Optional, Dict, Any
import logging
import json
import re
from pathlib import Path
import os
import traceback
from functools import wraps
import datetime
import asyncio
from dataclasses import dataclass

# --- IMPORTATIONS CENTRALISÉES DU PROJET VAX V3 ---
from utils.config_data import DataManager
from utils.config_theme import config_manager
from utils.config_prefix import prefix_config_manager, get_global_prefix
from utils.config_id import IdModal
from utils.config_emoji import Emoji as E

# ======================================================================
# --------------------------- CONFIGURATION & CHEMINS ------------------
# ======================================================================
EMBED_COLOR = 0x2b2d31
BASE_DIR = Path(__file__).parent.parent.parent
DB_DIR = BASE_DIR / "data" / "public" / "utilitaires" / "Feedback"

TEMP_DIR = DB_DIR / "temp_screenshots"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Cible centralisée (Serveur de Support du Bot)
TARGET_GUILD_ID = 1368235294192570520
TARGET_CHANNEL_ID = 1540836124824568020

# Emojis de vote (Réactions) forcés sur les variantes custom demandées
EMOJI_OUI = getattr(E, "VALIDER_CUSTOM", getattr(E, "VALIDER", "✅"))
EMOJI_NON = getattr(E, "REFUSER_CUSTOM", getattr(E, "REFUSER", "❌"))

# Emojis des Bots (Modernisation et style Vax v3)
BOT_EMOJIS = {
    "Vax": getattr(E, "VAX", "<:Vax:1472428869876191435>"),
    "Kayaba": getattr(E, "KAYABA", "<:kayaba:1505171139528233052>"),
    "Asuna": getattr(E, "ASUNA", "<:Asuna:1505137735877525564>"),
    "Yui": getattr(E, "YUI", "<:yui:1505166357623214110>"),
    "Autres": getattr(E, "MONDE", getattr(E, "SYNKRONE", "<:Synkrone:1502091722392469724>"))
}

# Code couleur ANSI pour le rendu Markdown
ANSI_COLORS = {
    "Ajouter une feature": "\u001b[2;32m",      # Vert
    "Améliorer une feature": "\u001b[2;34m",    # Bleu
    "Nerfer une feature": "\u001b[2;33m",       # Jaune
    "Supprimer une feature": "\u001b[2;35m",    # Magenta
    "Signaler un bug": "\u001b[2;31m",          # Rouge
}

def debug_print(message: str, level: str = "INFO"):
    """Gestion des prints de débogage conditionnés et colorés."""
    if not DEBUG_MODE:
        return
    if ERROR_ONLY_MODE and level.upper() != "ERROR":
        return
    
    colors = {
        "INFO": "\033[94m",     # Bleu
        "SUCCESS": "\033[92m",  # Vert
        "ERROR": "\033[91m",    # Rouge
        "WARNING": "\033[93m"   # Jaune
    }
    reset = "\033[0m"
    print(f"{colors.get(level.upper(), '\033[97m')}[DEBUG - Feedback] [{level.upper()}] {message}{reset}")

def handle_errors(func):
    """Décorateur pour capturer et logger les erreurs de manière robuste."""
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except Exception as e:
            debug_print(f"Erreur dans {func.__name__}: {e}\n{traceback.format_exc()}", "ERROR")
            return None
    return wrapper

# ======================================================================
# --------------------------- ETAT DU FEEDBACK -------------------------
# ======================================================================

@dataclass
class FeedbackState:
    cog: commands.Cog
    ctx: commands.Context
    feedback_type: str
    bot_target: str
    cmd_name: str = ""
    cmd_desc: str = ""
    screenshot_type: Optional[str] = None # "url" ou "local"
    screenshot_data: Optional[str] = None # Contient l'URL ou le chemin du fichier

# ======================================================================
# --------------------------- INTERFACE UTILISATEUR (UI) --------------
# ======================================================================

class FeedbackModal(ui.Modal):
    def __init__(self, state: FeedbackState, is_edit: bool = False, view_to_update: Optional[FeedbackPreviewView] = None):
        super().__init__(title="Détails du Feedback", timeout=300.0)
        self.state = state
        self.is_edit = is_edit
        self.view_to_update = view_to_update
        
        is_add_feature = (self.state.feedback_type == "Ajouter une feature")
        
        name_label = "Idée de nom de commande" if is_add_feature else "Nom de la commande / Feature"
        name_placeholder = "Ex: /profil" if is_add_feature else "Ex: /ping"
        
        self.cmd_name = ui.TextInput(
            label=name_label,
            placeholder=name_placeholder,
            style=discord.TextStyle.short,
            required=True,
            max_length=50,
            default=self.state.cmd_name if self.is_edit else ""
        )
        
        self.cmd_desc = ui.TextInput(
            label="Description détaillée",
            placeholder="Expliquez votre retour en détail...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000,
            default=self.state.cmd_desc if self.is_edit else ""
        )
        
        self.add_item(self.cmd_name)
        self.add_item(self.cmd_desc)

    async def on_submit(self, interaction: discord.Interaction):
        self.state.cmd_name = self.cmd_name.value
        self.state.cmd_desc = self.cmd_desc.value
        
        if self.is_edit and self.view_to_update:
            self.view_to_update._build()
            attachments = []
            if self.state.screenshot_type == "local" and self.state.screenshot_data and os.path.exists(self.state.screenshot_data):
                attachments.append(discord.File(self.state.screenshot_data))
            await interaction.response.edit_message(view=self.view_to_update, attachments=attachments)
        else:
            preview_view = FeedbackPreviewView(self.state)
            await interaction.response.edit_message(view=preview_view)


class EditFeedbackSelect(ui.Select):
    def __init__(self, parent_view: FeedbackPreviewView):
        self.parent_view = parent_view
        
        screen_label = "Modifier le screenshot" if self.parent_view.state.screenshot_data else "Ajouter un screenshot"
        
        options = [
            discord.SelectOption(label="Modifier le texte", emoji=getattr(E, "MODIFIER", "✏️"), value="text"),
            discord.SelectOption(label=screen_label, emoji=getattr(E, "IMAGE", "🖼️"), value="screenshot"),
            discord.SelectOption(label="Envoyer", emoji=getattr(E, "SEND", getattr(E, "VALIDER", "📤")), value="send")
        ]
        super().__init__(placeholder="Gérer ou envoyer le feedback...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]
        if choice == "text":
            modal = FeedbackModal(state=self.parent_view.state, is_edit=True, view_to_update=self.parent_view)
            await interaction.response.send_modal(modal)
        elif choice == "screenshot":
            await self.parent_view.start_screenshot_wait(interaction)
        elif choice == "send":
            await self.parent_view.confirm_send_callback(interaction)


class FeedbackPreviewView(ui.LayoutView):
    def __init__(self, state: FeedbackState):
        super().__init__(timeout=900)
        self.state = state
        self.waiting_for_image = False
        self.wait_task: Optional[asyncio.Task] = None
        self._build()

    def _build(self):
        self.clear_items()
        
        cog = self.state.cog
        bot = cog.bot
        user = self.state.ctx.author
        source_guild = self.state.ctx.guild
        
        theme = config_manager.get_layout_v2_theme(source_guild.id if source_guild else 0, source_guild, user, bot)
        accent_color = int(theme.get("color", EMBED_COLOR))
        footer_text = theme.get("footer_text", "")

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        
        if self.waiting_for_image:
            container.add_item(ui.TextDisplay(f"# {getattr(E, 'TEMPS', '⏳')} En attente d'un screenshot..."))
            container.add_item(ui.TextDisplay(
                "Veuillez envoyer une **image** ou un **lien d'image (URL)** directement dans ce salon.\n\n"
                "-# Vous avez 5 minutes. Le message sera automatiquement intercepté et supprimé."
            ))
            
            wait_row = ui.ActionRow()
            btn_cancel = ui.Button(label="Annuler", style=discord.ButtonStyle.secondary, emoji=getattr(E, "RETOUR", "↩️"))
            btn_cancel.callback = self.cancel_wait_callback
            wait_row.add_item(btn_cancel)
            
            if self.state.screenshot_data:
                btn_delete = ui.Button(label="Supprimer le screenshot actuel", style=discord.ButtonStyle.danger, emoji=getattr(E, "SUPPRIMER", "🗑️"))
                btn_delete.callback = self.delete_screenshot_callback
                wait_row.add_item(btn_delete)
                
            container.add_item(wait_row)
            self.add_item(container)
            return

        container.add_item(ui.TextDisplay(f"# {getattr(E, 'DOCUMENT', '📄')} Prévisualisation du Feedback"))
        
        raw_cmd = self.state.cmd_name.strip()
        formatted_cmd = raw_cmd if raw_cmd.startswith('/') else f"/{re.sub(r'^[^\w\s]+', '', raw_cmd).strip()}"
        
        ansi_color = ANSI_COLORS.get(self.state.feedback_type, "\u001b[0m")
        preview_content = (
            f"**Cible :** `{formatted_cmd}`\n\n"
            f"**Type de retour :**\n```ansi\n{ansi_color}{self.state.feedback_type}\u001b[0m\n```\n"
            f"**Description :**\n```ansi\n{ansi_color}{self.state.cmd_desc}\u001b[0m\n```"
        )
        
        # On ajoute le texte du lien uniquement si c'est une URL externe
        if self.state.screenshot_type == "url" and self.state.screenshot_data:
            preview_content += f"\n{getattr(E, 'IMAGE', '🖼️')} **Screenshot :** [Ouvrir l'image]({self.state.screenshot_data})"
            
        container.add_item(ui.TextDisplay(preview_content))

        if self.state.screenshot_data:
            try:
                gallery = ui.MediaGallery()
                if self.state.screenshot_type == "url":
                    gallery.add_item(media=self.state.screenshot_data, description="Screenshot attaché")
                elif self.state.screenshot_type == "local":
                    filename = os.path.basename(self.state.screenshot_data)
                    gallery.add_item(media=f"attachment://{filename}", description="Screenshot attaché")
                container.add_item(gallery)
            except Exception as e:
                debug_print(f"Impossible de rendre la MediaGallery: {e}", "WARNING")

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

        select_row = ui.ActionRow()
        select_row.add_item(EditFeedbackSelect(self))
        container.add_item(select_row)
        
        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    async def cancel_wait_callback(self, interaction: discord.Interaction):
        if self.wait_task:
            self.wait_task.cancel()
        self.waiting_for_image = False
        self._build()
        attachments = []
        if self.state.screenshot_type == "local" and self.state.screenshot_data and os.path.exists(self.state.screenshot_data):
            attachments.append(discord.File(self.state.screenshot_data))
        await interaction.response.edit_message(view=self, attachments=attachments)

    async def delete_screenshot_callback(self, interaction: discord.Interaction):
        if self.wait_task:
            self.wait_task.cancel()
            
        # Suppression du fichier local si applicable
        if self.state.screenshot_type == "local" and self.state.screenshot_data and os.path.exists(self.state.screenshot_data):
            try:
                os.remove(self.state.screenshot_data)
            except Exception as e:
                debug_print(f"Impossible de supprimer le fichier temporaire : {e}", "WARNING")
                
        self.state.screenshot_type = None
        self.state.screenshot_data = None
        self.waiting_for_image = False
        self._build()
        
        # Enlever les attachments du message lors de l'edit
        await interaction.response.edit_message(view=self, attachments=[])

    async def start_screenshot_wait(self, interaction: discord.Interaction):
        self.waiting_for_image = True
        self._build()
        await interaction.response.edit_message(view=self, attachments=[])
        self.wait_task = asyncio.create_task(self.wait_for_image_task(interaction))

    async def wait_for_image_task(self, interaction: discord.Interaction):
        def check(m):
            return m.author.id == self.state.ctx.author.id and m.channel.id == interaction.channel.id
            
        try:
            msg = await self.state.cog.bot.wait_for("message", check=check, timeout=300.0)
            
            url = None
            local_path = None
            
            if msg.attachments:
                att = msg.attachments[0]
                for a in msg.attachments:
                    if a.content_type and a.content_type.startswith('image/'):
                        att = a
                        break
                
                filename = f"{self.state.ctx.author.id}_{int(datetime.datetime.now().timestamp())}_{att.filename}"
                filepath = TEMP_DIR / filename
                await att.save(filepath)
                local_path = str(filepath)
            else:
                match = re.search(r'(https?://\S+\.(?:png|jpe?g|webp|gif)(?:\?\S*)?)', msg.content, re.IGNORECASE)
                if match:
                    url = match.group(1)
                else:
                    match = re.search(r'(https?://\S+)', msg.content)
                    if match:
                        url = match.group(1)
            
            try:
                await msg.delete()
            except (discord.Forbidden, discord.NotFound):
                pass
                
            if local_path:
                self.state.screenshot_type = "local"
                self.state.screenshot_data = local_path
            elif url:
                self.state.screenshot_type = "url"
                self.state.screenshot_data = url
                
        except asyncio.TimeoutError:
            pass
        except asyncio.CancelledError:
            return
            
        self.waiting_for_image = False
        self._build()
        
        attachments = []
        if self.state.screenshot_type == "local" and self.state.screenshot_data and os.path.exists(self.state.screenshot_data):
            attachments.append(discord.File(self.state.screenshot_data))
            
        try:
            await interaction.edit_original_response(view=self, attachments=attachments)
        except Exception as e:
            debug_print(f"Erreur lors de l'update de l'UI Screenshot: {e}", "ERROR")

    async def confirm_send_callback(self, interaction: discord.Interaction):
        self.clear_items()
        
        guild = self.state.ctx.guild
        theme = config_manager.get_layout_v2_theme(guild.id if guild else 0, guild, self.state.ctx.author, self.state.cog.bot)
        accent_color = int(theme.get("color", EMBED_COLOR))
        
        container = ui.Container(accent_color=discord.Color(accent_color))
        container.add_item(ui.TextDisplay(f"# {getattr(E, 'QUESTION', '❓')} Confirmation d'envoi"))
        container.add_item(ui.TextDisplay("Êtes-vous sûr de vouloir envoyer ce feedback à l'équipe de développement ?"))
        
        row = ui.ActionRow()
        btn_oui = ui.Button(label="Confirmer", style=discord.ButtonStyle.success, emoji=getattr(E, "VALIDER", "✅"))
        btn_oui.callback = self.execute_send_callback
        
        btn_non = ui.Button(label="Annuler", style=discord.ButtonStyle.secondary, emoji=getattr(E, "RETOUR", "↩️"))
        btn_non.callback = self.cancel_confirm_callback
        
        row.add_item(btn_oui)
        row.add_item(btn_non)
        container.add_item(row)
        self.add_item(container)
        
        attachments = []
        if self.state.screenshot_type == "local" and self.state.screenshot_data and os.path.exists(self.state.screenshot_data):
            attachments.append(discord.File(self.state.screenshot_data))
            
        await interaction.response.edit_message(view=self, attachments=attachments)

    async def cancel_confirm_callback(self, interaction: discord.Interaction):
        self._build()
        attachments = []
        if self.state.screenshot_type == "local" and self.state.screenshot_data and os.path.exists(self.state.screenshot_data):
            attachments.append(discord.File(self.state.screenshot_data))
        await interaction.response.edit_message(view=self, attachments=attachments)

    async def execute_send_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        cog = self.state.cog
        bot = cog.bot
        user = self.state.ctx.author
        source_guild = self.state.ctx.guild
        
        raw_cmd = self.state.cmd_name.strip()
        formatted_cmd = raw_cmd if raw_cmd.startswith('/') else f"/{re.sub(r'^[^\w\s]+', '', raw_cmd).strip()}"

        emoji_bot = BOT_EMOJIS.get("Vax", "🤖")
        embed_title = f"{emoji_bot} | Vax - {self.state.feedback_type}"
        
        guild_name = source_guild.name if source_guild else 'Message Privé'
        guild_id = source_guild.id if source_guild else 'N/A'
        
        ansi_color = ANSI_COLORS.get(self.state.feedback_type, "\u001b[0m")
        embed_desc = (
            f"# `{formatted_cmd}`\n\n"
            f"**Type :**\n```ansi\n{ansi_color}{self.state.feedback_type}\u001b[0m\n```\n"
            f"**Description :**\n```ansi\n{ansi_color}{self.state.cmd_desc}\u001b[0m\n```\n\n"
            f"-# Serveur : {guild_name} - `{guild_id}`\n"
            f"-# ID Utilisateur : `{user.id}`"
        )
        
        if self.state.screenshot_type == "url" and self.state.screenshot_data:
            embed_desc += f"\n\n**Screenshot :** [Lien vers l'image]({self.state.screenshot_data})"
        
        invite_url = None
        try:
            target_channel = bot.get_channel(TARGET_CHANNEL_ID)
            if not target_channel:
                target_channel = await bot.fetch_channel(TARGET_CHANNEL_ID)

            try:
                invite = await target_channel.create_invite(
                    max_age=604800, 
                    max_uses=0, 
                    reason=f"Invitation Feedback générée pour {user.name}"
                )
                invite_url = invite.url
            except Exception as e:
                debug_print(f"Impossible de générer l'invitation : {e}", "WARNING")

            log_embed = cog.create_custom_embed(source_guild, user, embed_title, embed_desc)
            log_embed.set_author(name=f"Feedback de {user.display_name}", icon_url=user.display_avatar.url)
            log_embed.timestamp = datetime.datetime.now()
            
            # Gestion de l'image pour le salon cible
            log_file = None
            if self.state.screenshot_type == "url" and self.state.screenshot_data:
                log_embed.set_image(url=self.state.screenshot_data)
            elif self.state.screenshot_type == "local" and self.state.screenshot_data and os.path.exists(self.state.screenshot_data):
                filename = os.path.basename(self.state.screenshot_data)
                log_file = discord.File(self.state.screenshot_data, filename=filename)
                log_embed.set_image(url=f"attachment://{filename}")
            
            if log_file:
                log_msg = await target_channel.send(embed=log_embed, file=log_file)
            else:
                log_msg = await target_channel.send(embed=log_embed)
                
            await log_msg.add_reaction(discord.PartialEmoji.from_str(EMOJI_OUI))
            await log_msg.add_reaction(discord.PartialEmoji.from_str(EMOJI_NON))

        except discord.Forbidden:
            debug_print("Erreur: Le bot n'a pas accès au salon centralisé ou manque de permissions.", "ERROR")
        except Exception as e:
            debug_print(f"Impossible d'envoyer le log centralisé: {e}", "ERROR")
        
        theme = config_manager.get_layout_v2_theme(source_guild.id if source_guild else 0, source_guild, user, bot)
        accent_color = int(theme.get("color", EMBED_COLOR))
        footer_text = theme.get("footer_text", "")

        layout_view = ui.LayoutView(timeout=180)
        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        
        container.add_item(ui.TextDisplay(f"# {getattr(E, 'VALIDER', '✅')} Feedback Transmis !"))
        
        success_content = (
            f"> **Merci pour votre contribution.** Votre retour a bien été transmis à l'équipe de développement !\n\n"
            f"**Cible / Commande :** `{formatted_cmd}`\n\n"
            f"**Type de retour :**\n```ansi\n{ansi_color}{self.state.feedback_type}\u001b[0m\n```\n"
            f"**Description :**\n```ansi\n{ansi_color}{self.state.cmd_desc}\u001b[0m\n```"
        )
        container.add_item(ui.TextDisplay(success_content))

        if self.state.screenshot_type == "url" and self.state.screenshot_data:
            container.add_item(ui.TextDisplay(f"{getattr(E, 'IMAGE', '🖼️')} **Screenshot attaché :** [Lien vers l'image]({self.state.screenshot_data})"))

        if self.state.screenshot_data:
            try:
                gallery = ui.MediaGallery()
                if self.state.screenshot_type == "url":
                    gallery.add_item(media=self.state.screenshot_data, description="Screenshot attaché")
                elif self.state.screenshot_type == "local":
                    filename = os.path.basename(self.state.screenshot_data)
                    gallery.add_item(media=f"attachment://{filename}", description="Screenshot attaché")
                container.add_item(gallery)
            except Exception as e:
                debug_print(f"Impossible de rendre la MediaGallery de succès: {e}", "WARNING")

        if invite_url:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
            container.add_item(ui.TextDisplay(f"🔗 [Voir votre feedback dans le salon dédié]({invite_url})"))

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        layout_view.add_item(container)

        attachments = []
        if self.state.screenshot_type == "local" and self.state.screenshot_data and os.path.exists(self.state.screenshot_data):
            attachments.append(discord.File(self.state.screenshot_data))

        try:
            await interaction.edit_original_response(view=layout_view, attachments=attachments)
        except discord.HTTPException:
            await interaction.followup.send(view=layout_view, files=attachments)


class Step1Select(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Ajouter une feature", emoji=getattr(E, "CREATE", "✨"), description="Proposer une nouveauté"),
            discord.SelectOption(label="Améliorer une feature", emoji=getattr(E, "HAUSSE", "📈"), description="Suggérer une amélioration"),
            discord.SelectOption(label="Nerfer une feature", emoji=getattr(E, "BOUCLIER", "⚖️"), description="Équilibrer une fonction"),
            discord.SelectOption(label="Supprimer une feature", emoji=getattr(E, "SUPPRIMER", "🗑️"), description="Retirer une fonction obsolète"),
            discord.SelectOption(label="Signaler un bug", emoji=getattr(E, "INSECTE", getattr(E, "ATTENTION", "🐛")), description="Rapporter un dysfonctionnement")
        ]
        super().__init__(placeholder="Choisissez le type de feedback...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        feedback_type = self.values[0]
        state = FeedbackState(
            cog=self.view.cog, 
            ctx=self.view.ctx, 
            feedback_type=feedback_type, 
            bot_target=self.view.bot_target
        )
        modal = FeedbackModal(state=state, is_edit=False)
        await interaction.response.send_modal(modal)


class FeedbackView(ui.LayoutView):
    """Vue interactive initiale"""
    def __init__(self, cog, ctx: commands.Context):
        super().__init__(timeout=900)
        self.cog = cog
        self.ctx = ctx
        self.author = ctx.author
        self.bot_target = "Vax"
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(f"{getattr(E, 'REFUSER', '❌')} Ce menu interactif ne vous appartient pas.", ephemeral=True)
            return False
        return True

    def _build(self):
        self.clear_items()
        
        guild = self.ctx.guild
        theme = config_manager.get_layout_v2_theme(guild.id if guild else 0, guild, self.author, self.cog.bot)
        accent_color = int(theme.get("color", EMBED_COLOR))
        footer_text = theme.get("footer_text", "")

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {getattr(E, 'MEMO', '📝')} Centre de Feedback - Vax v3"))
        container.add_item(
            ui.TextDisplay(
                "Bienvenue dans l'interface interactive de suggestion et de suivi.\n"
                "Utilisez le menu déroulant ci-dessous pour sélectionner **le type de retour** que vous souhaitez effectuer."
            )
        )
        
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
        
        select_row = ui.ActionRow()
        select_row.add_item(Step1Select())
        container.add_item(select_row)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    async def on_timeout(self):
        debug_print("La vue interactive du feedback a expiré.", "INFO")


# ======================================================================
# --------------------------------- COG MAIN ---------------------------
# ======================================================================

class FeedbackCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        debug_print("Cog Feedback initialisé avec succès.", "SUCCESS")

    def create_custom_embed(self, guild, user, title, description):
        """Intégration transparente avec EmbedConfigManager."""
        if config_manager:
            return config_manager.get_formatted_embed(
                guild=guild, 
                user=user, 
                bot=self.bot, 
                title=title, 
                description=description,
                target_id=guild.id if guild else None
            )
        return discord.Embed(title=title, description=description, color=EMBED_COLOR)

    @commands.hybrid_command(name="feedback", aliases=["fb"], description="Soumettre une idée, une amélioration ou signaler un bug à l'équipe de développement.")
    @handle_errors
    async def feedback(self, ctx: commands.Context):
        debug_print(f"Commande /feedback exécutée par {ctx.author} sur {ctx.guild.name if ctx.guild else 'DM'}.", "INFO")
        
        view = FeedbackView(self, ctx)
        if ctx.interaction:
            if not ctx.interaction.response.is_done():
                await ctx.interaction.response.send_message(view=view, ephemeral=False)
            else:
                await ctx.interaction.followup.send(view=view, ephemeral=False)
        else:
            await ctx.send(view=view, reference=ctx.message, mention_author=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(FeedbackCog(bot))