"""
COMMANDE LAYOUT - Éditeur de Layout V2 interactif
=================================================
Permet de concevoir et publier des Layouts V2 personnalisés sur le serveur.
"""

from __future__ import annotations

import asyncio
import traceback
from typing import Any

import discord
from discord import ui
from discord.ext import commands

from utils.config_emoji import Emoji as E

# ==============================================================================
# CONFIGURATION DES LOGS ET EMOJIS GLOBAUX
# ==============================================================================
DEBUG_MODE = True
ERROR_LOG_ONLY = False

# Centralisation des emojis du bot via utils.config_emoji

# ==============================================================================
# GESTION DES IMPORTS ET DU CONFIG_MANAGER
# ==============================================================================
from utils.config_data import DataManager
from utils.config_theme import config_manager
from utils.config_perm import ensure_command_permission, perm_command
from utils.config_prefix import prefix_config_manager

# ==============================================================================
# FONCTIONS UTILITAIRES (RECHERCHE INTELLIGENTE)
# ==============================================================================

async def find_message_in_guild(guild: discord.Guild, message_id: int) -> discord.Message | None:
    """Cherche un message par son ID dans tous les salons textuels du serveur."""
    if DEBUG_MODE and not ERROR_LOG_ONLY:
        print(f"\033[36m[DEBUG] Recherche du message ID {message_id} sur le serveur {guild.name}\033[0m")
        
    for channel in guild.text_channels:
        if not channel.permissions_for(guild.me).read_message_history:
            continue
        try:
            return await channel.fetch_message(message_id)
        except Exception:
            continue
    return None


# ==============================================================================
# MODALS (FORMULAIRES)
# ==============================================================================

class CopyLayoutModal(ui.Modal, title="Copier un layout existant"):
    def __init__(self, parent_view: LayoutConfigView):
        super().__init__()
        self.parent_view = parent_view
        self.message_id = ui.TextInput(label="ID du Message", placeholder="Collez juste l'ID du message...", required=True)
        self.add_item(self.message_id)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        try:
            msg = await find_message_in_guild(interaction.guild, int(self.message_id.value))
            if not msg:
                if DEBUG_MODE:
                    print(f"\033[31m[ERREUR] Message ID {self.message_id.value} introuvable.\033[0m")
                await interaction.followup.send(f"{E.ERROR} Message introuvable.")
                return
            
            extracted_text = msg.content if msg.content else "Contenu importé depuis un message distant."
            self.parent_view.layout_content = extracted_text
            
            if self.parent_view.preview_msg:
                await self.parent_view.preview_msg.edit(view=self.parent_view.build_preview_layout())
            await self.parent_view.show_step_2(interaction)
        except Exception as e:
            if DEBUG_MODE:
                print(f"\033[31m[ERREUR] CopyLayoutModal: {e}\033[0m")
                traceback.print_exc()
            await interaction.followup.send(f"{E.ERROR} Erreur lors de l'importation.")


class TitleEditModal(ui.Modal, title="Modifier ou définir le titre"):
    def __init__(self, parent_view: LayoutConfigView):
        super().__init__()
        self.parent_view = parent_view
        
        current_title = ""
        lines = self.parent_view.layout_content.splitlines()
        if lines and lines[0].startswith("# "):
            current_title = lines[0][2:].strip()
        elif lines and lines[0].startswith("#"):
            current_title = lines[0].lstrip("#").strip()

        self.title_input = ui.TextInput(
            label="Titre du Layout (Laissez vide pour aucun)",
            placeholder="Ex: Annonce Importante...",
            default=current_title,
            required=False,
            max_length=256
        )
        self.add_item(self.title_input)

    async def on_submit(self, interaction: discord.Interaction):
        new_title = self.title_input.value.strip()
        lines = self.parent_view.layout_content.splitlines()
        
        has_old_title = lines and (lines[0].startswith("#") or lines[0].startswith("Titre de l'Annonce"))
        
        if new_title:
            formatted_title = f"# {new_title}"
            if has_old_title:
                lines[0] = formatted_title
            else:
                lines.insert(0, formatted_title)
        else:
            if has_old_title:
                lines.pop(0)

        self.parent_view.layout_content = "\n".join(lines)
        if self.parent_view.preview_msg:
            await self.parent_view.preview_msg.edit(view=self.parent_view.build_preview_layout())
        
        if DEBUG_MODE and not ERROR_LOG_ONLY:
            print(f"\033[32m[SUCCÈS] Titre mis à jour par {interaction.user}\033[0m")
        
        await interaction.response.defer()
        await self.parent_view.show_step_2(interaction)


class TextEditLayoutModal(ui.Modal, title="Modifier le contenu du Layout"):
    def __init__(self, parent_view: LayoutConfigView):
        super().__init__()
        self.parent_view = parent_view
        
        lines = self.parent_view.layout_content.splitlines()
        body_content = self.parent_view.layout_content
        if lines and lines[0].startswith("#"):
            body_content = "\n".join(lines[1:])

        self.content_input = ui.TextInput(
            label="Contenu textuel / Markdown (Corps)", 
            style=discord.TextStyle.paragraph, 
            default=body_content, 
            required=True, 
            max_length=4000
        )
        self.add_item(self.content_input)

    async def on_submit(self, interaction: discord.Interaction):
        if DEBUG_MODE and not ERROR_LOG_ONLY:
            print(f"\033[32m[SUCCÈS] Mise à jour du texte du layout par {interaction.user}\033[0m")
        
        body = self.content_input.value
        lines = self.parent_view.layout_content.splitlines()
        
        if lines and lines[0].startswith("#"):
            title_line = lines[0]
            self.parent_view.layout_content = f"{title_line}\n{body}"
        else:
            self.parent_view.layout_content = body

        if self.parent_view.preview_msg:
            await self.parent_view.preview_msg.edit(view=self.parent_view.build_preview_layout())
        
        await interaction.response.defer()
        await self.parent_view.show_step_2(interaction)


class ImageLinkModal(ui.Modal):
    def __init__(self, parent_view: LayoutConfigView, image_type: str):
        super().__init__(title=f"Lien URL pour {image_type}")
        self.parent_view = parent_view
        self.image_type = image_type
        self.url_input = ui.TextInput(label="Lien URL (http...)", placeholder="https://i.imgur.com/...", required=True)
        self.add_item(self.url_input)

    async def on_submit(self, interaction: discord.Interaction):
        url = self.url_input.value.strip()
        if self.image_type == "thumbnail":
            self.parent_view.thumbnail_url = url
        elif self.image_type == "banner":
            self.parent_view.banner_url = url

        if self.parent_view.preview_msg:
            await self.parent_view.preview_msg.edit(view=self.parent_view.build_preview_layout())
        
        if DEBUG_MODE and not ERROR_LOG_ONLY:
            print(f"\033[32m[SUCCÈS] Visuel {self.image_type} mis à jour via URL\033[0m")

        await interaction.response.defer()
        await self.parent_view.show_step_2(interaction)


class SendChannelLayoutModal(ui.Modal, title="Envoyer le Layout dans un salon"):
    def __init__(self, parent_view: LayoutConfigView):
        super().__init__()
        self.parent_view = parent_view
        self.channel_id = ui.TextInput(label="ID du Salon", placeholder="Ex: 123456789...", required=True)
        self.add_item(self.channel_id)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            channel = interaction.guild.get_channel(int(self.channel_id.value))
            if not channel:
                await interaction.response.send_message(f"{E.ERROR} Salon introuvable.")
                return
            
            await channel.send(view=self.parent_view.build_preview_layout())
            if DEBUG_MODE and not ERROR_LOG_ONLY:
                print(f"\033[32m[SUCCÈS] Layout publié dans le salon {channel.id}\033[0m")
            await interaction.response.send_message(f"{E.SUCCESS} Layout publié dans {channel.mention} !")
        except Exception as e:
            if DEBUG_MODE:
                print(f"\033[31m[ERREUR] SendChannelLayoutModal: {e}\033[0m")
            await interaction.response.send_message(f"{E.ERROR} ID invalide ou permissions manquantes.")


class EditMessageLayoutModal(ui.Modal, title="Modifier un message existant"):
    def __init__(self, parent_view: LayoutConfigView):
        super().__init__()
        self.parent_view = parent_view
        self.message_id = ui.TextInput(label="ID du Message", placeholder="Le message doit m'appartenir...", required=True)
        self.add_item(self.message_id)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        msg = await find_message_in_guild(interaction.guild, int(self.message_id.value))
        
        if not msg:
            await interaction.followup.send(f"{E.ERROR} Message introuvable sur ce serveur.")
            return
        if msg.author.id != self.parent_view.bot.user.id:
            await interaction.followup.send(f"{E.ERROR} Je ne peux modifier que mes propres messages.")
            return
        
        await msg.edit(view=self.parent_view.build_preview_layout())
        if DEBUG_MODE and not ERROR_LOG_ONLY:
            print(f"\033[32m[SUCCÈS] Message existant {msg.id} mis à jour.\033[0m")
        await interaction.followup.send(f"{E.SUCCESS} Message mis à jour avec succès !")


# ==============================================================================
# VUE PRINCIPALE DU CONTRÔLEUR DE LAYOUT (LayoutV2)
# ==============================================================================

class LayoutConfigView(ui.LayoutView):
    def __init__(self, bot: commands.Bot, guild: discord.Guild, author: discord.Member):
        super().__init__(timeout=600)
        self.bot = bot
        self.guild = guild
        self.author = author
        self.config_msg: discord.Message | None = None
        self.preview_msg: discord.Message | None = None
        
        self.layout_content = (
            "# Titre de l'Annonce (Aperçu)\n"
            "Ceci est un texte de remplacement pour visualiser la mise en page.\n"
            "Modifiez ce contenu à l'**Étape 2**.\n\n"
            "• Design moderne et épuré\n"
            "• Intégration native Layout V2"
        )
        self.thumbnail_url: str | None = None
        self.banner_url: str | None = None
        self.config_step = 1
        self._build_step_1()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(f"{E.ERROR} Ce menu ne vous appartient pas.")
            return False
        return True

    def build_config_container(self, title: str, description: str) -> ui.Container:
        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.author, self.bot) if config_manager else {}
        color = int(theme.get("color", 0x5865F2))
        footer_text = theme.get("footer_text", "")

        container = ui.Container(accent_color=discord.Color(color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {title}"))
        container.add_item(ui.TextDisplay(description))
        
        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
            container.add_item(ui.TextDisplay(footer_text))
            
        return container

    def build_preview_layout(self) -> ui.LayoutView:
        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.author, self.bot) if config_manager else {}
        color = int(theme.get("color", 0x2ecc71))
        footer_text = theme.get("footer_text", "")
        
        preview_view = ui.LayoutView(timeout=None)
        container = ui.Container(accent_color=discord.Color(color), spoiler=False)

        lines = self.layout_content.splitlines()
        has_title = lines and lines[0].startswith("#")

        if has_title:
            title_part = lines[0]
            rest_part = "\n".join(lines[1:])
            
            if title_part.strip():
                container.add_item(ui.TextDisplay(title_part))
                container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
            
            if self.thumbnail_url and rest_part.strip():
                try:
                    container.add_item(ui.Section(rest_part, accessory=ui.Thumbnail(self.thumbnail_url)))
                except Exception:
                    container.add_item(ui.TextDisplay(rest_part))
            elif rest_part.strip():
                container.add_item(ui.TextDisplay(rest_part))
        else:
            rest_part = self.layout_content
            if self.thumbnail_url and rest_part.strip():
                try:
                    container.add_item(ui.Section(rest_part, accessory=ui.Thumbnail(self.thumbnail_url)))
                except Exception:
                    container.add_item(ui.TextDisplay(rest_part))
            elif rest_part.strip():
                container.add_item(ui.TextDisplay(rest_part))

        if self.banner_url:
            try:
                gallery = ui.MediaGallery()
                gallery.add_item(media=self.banner_url, description="Bannière du layout")
                container.add_item(gallery)
            except Exception:
                pass

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        preview_view.add_item(container)
        return preview_view

    # ==========================================================================
    # ÉTAPE 1 : CHOIX DE DÉPART
    # ==========================================================================
    def _build_step_1(self):
        self.clear_items()
        
        container = self.build_config_container(
            "Étape 1 : Configuration", 
            "Bienvenue dans l'éditeur de Layout V2.\nSélectionnez une option ci-dessous pour commencer."
        )
        
        select_row = ui.ActionRow()
        select = ui.Select(
            placeholder="Étape 1 : Comment voulez-vous commencer ?", 
            options=[
                discord.SelectOption(label="Nouveau layout vierge", emoji=E.CREATE, value="new", description="Partir de zéro"),
                discord.SelectOption(label="Copier un layout existant", emoji=E.COPY, value="copy", description="Importer depuis un ID")
            ]
        )
        
        async def callback(i: discord.Interaction):
            if select.values[0] == "new":
                self.layout_content = "Nouveau Layout\nÉditez ce texte pour commencer."
                if self.preview_msg:
                    await self.preview_msg.edit(view=self.build_preview_layout())
                await self.show_step_2(i)
            else:
                await i.response.send_modal(CopyLayoutModal(self))
        
        select.callback = callback
        select_row.add_item(select)
        container.add_item(select_row)
        self.add_item(container)

    # ==========================================================================
    # ÉTAPE 2 : PERSONNALISATION ET VISUELS (Sélecteur privilégié)
    # ==========================================================================
    async def show_step_2(self, interaction: discord.Interaction):
        self.config_step = 2
        self.clear_items()
        
        container = self.build_config_container(
            "Étape 2 : Personnalisation", 
            "Modifiez le titre, le texte ou configurez les visuels via le menu déroulant ci-dessous."
        )

        select_row = ui.ActionRow()
        select = ui.Select(
            placeholder="Choisir une action de personnalisation...",
            options=[
                discord.SelectOption(label="Modifier le titre", emoji="📌", value="title", description="Définir ou modifier le titre principal"),
                discord.SelectOption(label="Modifier le texte", emoji=E.TEXT, value="text", description="Éditer le contenu du corps du layout"),
                discord.SelectOption(label="Gérer le Thumbnail", emoji=E.THUMBNAIL, value="thumb", description="Ajouter ou modifier le thumbnail"),
                discord.SelectOption(label="Gérer la Bannière", emoji=E.BANNER, value="banner", description="Ajouter ou modifier la bannière"),
                discord.SelectOption(label="Continuer vers la publication", emoji=E.NEXT, value="next", description="Passer à l'étape finale"),
                discord.SelectOption(label="Retour au début", emoji=E.BACK, value="back", description="Recommencer la configuration")
            ]
        )

        async def step2_callback(i: discord.Interaction):
            val = select.values[0]
            if val == "title":
                await i.response.send_modal(TitleEditModal(self))
            elif val == "text":
                await i.response.send_modal(TextEditLayoutModal(self))
            elif val == "thumb":
                await self.show_thumbnail_menu(i)
            elif val == "banner":
                await self.show_banner_menu(i)
            elif val == "next":
                await self.show_step_3(i)
            elif val == "back":
                await self.back_confirm_logic(i)

        select.callback = step2_callback
        select_row.add_item(select)
        container.add_item(select_row)
        
        self.add_item(container)

        if interaction.response.is_done():
            await interaction.edit_original_response(view=self)
        else:
            await interaction.response.edit_message(view=self)

    # ==========================================================================
    # SOUS-MENUS VISUELS (THUMBNAIL & BANNER) AVEC RETOUR ÉTAPE 2
    # ==========================================================================
    async def show_thumbnail_menu(self, interaction: discord.Interaction):
        container = self.build_config_container(
            "Gestion du Thumbnail", 
            "Choisissez la source de votre thumbnail (via URL)."
        )

        select_row = ui.ActionRow()
        options = [
            discord.SelectOption(label="Image du serveur", emoji="🏠", value="server", description="Utiliser l'icône du serveur"),
            discord.SelectOption(label="Image du bot", emoji="🤖", value="bot", description="Utiliser l'avatar du bot"),
            discord.SelectOption(label="URL Custom", emoji=E.LINK, value="custom", description="Entrer un lien URL personnalisé"),
            discord.SelectOption(label="Retour", emoji=E.BACK, value="back", description="Retourner au menu de personnalisation")
        ]
        if self.thumbnail_url:
            options.insert(3, discord.SelectOption(label="Retirer Thumbnail", emoji=E.DELETE, value="remove", description="Supprimer le thumbnail actuel"))

        select = ui.Select(placeholder="Options du thumbnail...", options=options)

        async def thumb_callback(i: discord.Interaction):
            val = select.values[0]
            if val == "server":
                self.thumbnail_url = interaction.guild.icon.url if interaction.guild.icon else None
                if self.preview_msg:
                    await self.preview_msg.edit(view=self.build_preview_layout())
                await self.show_step_2(i)
            elif val == "bot":
                self.thumbnail_url = self.bot.user.display_avatar.url if self.bot.user else None
                if self.preview_msg:
                    await self.preview_msg.edit(view=self.build_preview_layout())
                await self.show_step_2(i)
            elif val == "custom":
                await i.response.send_modal(ImageLinkModal(self, "thumbnail"))
            elif val == "remove":
                self.thumbnail_url = None
                if self.preview_msg:
                    await self.preview_msg.edit(view=self.build_preview_layout())
                await self.show_step_2(i)
            elif val == "back":
                await self.show_step_2(i)

        select.callback = thumb_callback
        select_row.add_item(select)
        container.add_item(select_row)

        self.clear_items()
        self.add_item(container)
        await interaction.response.edit_message(view=self)

    async def show_banner_menu(self, interaction: discord.Interaction):
        container = self.build_config_container(
            "Gestion de la Bannière", 
            "Choisissez la source de votre bannière (via URL)."
        )

        select_row = ui.ActionRow()
        options = [
            discord.SelectOption(label="Bannière serveur", emoji="🏠", value="server", description="Utiliser la bannière du serveur"),
            discord.SelectOption(label="Bannière bot", emoji="🤖", value="bot", description="Utiliser la bannière du bot"),
            discord.SelectOption(label="URL Custom", emoji=E.LINK, value="custom", description="Entrer un lien URL personnalisé"),
            discord.SelectOption(label="Retour", emoji=E.BACK, value="back", description="Retourner au menu de personnalisation")
        ]
        if self.banner_url:
            options.insert(3, discord.SelectOption(label="Retirer Bannière", emoji=E.DELETE, value="remove", description="Supprimer la bannière actuelle"))

        select = ui.Select(placeholder="Options de la bannière...", options=options)

        async def banner_callback(i: discord.Interaction):
            val = select.values[0]
            if val == "server":
                self.banner_url = interaction.guild.banner.url if interaction.guild.banner else None
                if self.preview_msg:
                    await self.preview_msg.edit(view=self.build_preview_layout())
                await self.show_step_2(i)
            elif val == "bot":
                bot_user = await self.bot.fetch_user(self.bot.user.id) if self.bot.user else None
                self.banner_url = bot_user.banner.url if bot_user and bot_user.banner else None
                if self.preview_msg:
                    await self.preview_msg.edit(view=self.build_preview_layout())
                await self.show_step_2(i)
            elif val == "custom":
                await i.response.send_modal(ImageLinkModal(self, "banner"))
            elif val == "remove":
                self.banner_url = None
                if self.preview_msg:
                    await self.preview_msg.edit(view=self.build_preview_layout())
                await self.show_step_2(i)
            elif val == "back":
                await self.show_step_2(i)

        select.callback = banner_callback
        select_row.add_item(select)
        container.add_item(select_row)

        self.clear_items()
        self.add_item(container)
        await interaction.response.edit_message(view=self)

    # ==========================================================================
    # ÉTAPE 3 : PUBLICATION (Sélecteur incluant "Retour")
    # ==========================================================================
    async def show_step_3(self, interaction: discord.Interaction):
        self.config_step = 3
        self.clear_items()
        
        container = self.build_config_container(
            "Étape 3 : Publication", 
            "Votre layout est prêt. Choisissez comment le diffuser sur le serveur."
        )

        select_row = ui.ActionRow()
        select_pub = ui.Select(placeholder="Choisir le mode d'envoi...", options=[
            discord.SelectOption(label="Envoyer ici", emoji="📍", value="here", description="Le layout créé reste ici, supprime ce menu de configuration"),
            discord.SelectOption(label="Envoyer dans un salon", emoji=E.SEND, value="send", description="Publier dans un autre salon via son ID"),
            discord.SelectOption(label="Modifier un message existant", emoji=E.EDIT, value="edit", description="Remplacer un message existant par ce layout"),
            discord.SelectOption(label="Retour", emoji=E.BACK, value="back", description="Retourner à l'étape précédente")
        ])

        async def pub_cb(i: discord.Interaction):
            val = select_pub.values[0]
            if val == "here":
                await i.response.defer()
                if self.config_msg:
                    try:
                        await self.config_msg.delete()
                    except Exception:
                        pass
            elif val == "send":
                await i.response.send_modal(SendChannelLayoutModal(self))
            elif val == "edit":
                await i.response.send_modal(EditMessageLayoutModal(self))
            elif val == "back":
                await self.show_step_2(i)
        
        select_pub.callback = pub_cb
        select_row.add_item(select_pub)
        container.add_item(select_row)

        self.add_item(container)
        await interaction.response.edit_message(view=self)

    # ==========================================================================
    # LOGIQUE DE RETOUR ET CONFIRMATION (Sélecteur privilégié)
    # ==========================================================================
    async def back_confirm_logic(self, i: discord.Interaction):
        container = self.build_config_container(
            "⚠️ Confirmation requise", 
            "Voulez-vous vraiment recommencer ?\nToute modification non enregistrée sera perdue."
        )

        select_row = ui.ActionRow()
        select = ui.Select(
            placeholder="Confirmer le retour au début ?",
            options=[
                discord.SelectOption(label="Oui, recommencer", emoji=E.SUCCESS, value="yes", description="Réinitialiser le layout et repartir de zéro"),
                discord.SelectOption(label="Non, annuler", emoji=E.BACK, value="no", description="Revenir au menu de personnalisation")
            ]
        )

        async def confirm_cb(interaction: discord.Interaction):
            if select.values[0] == "yes":
                self.thumbnail_url = None
                self.banner_url = None
                self._build_step_1()
                await interaction.response.edit_message(view=self)
            else:
                await self.show_step_2(interaction)

        select.callback = confirm_cb
        select_row.add_item(select)
        container.add_item(select_row)

        self.clear_items()
        self.add_item(container)
        await interaction.response.edit_message(view=self)


# ==============================================================================
# COG PRINCIPAL DE LA COMMANDE LAYOUT
# ==============================================================================

class LayoutCog(commands.Cog):
    """Cog de gestion et de création de Layouts V2 interactifs."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @perm_command(level=1)
    @commands.command(name="layout", description="Lance l'éditeur de Layouts V2 complet.")
    async def layout_command(self, ctx: commands.Context):
        if not ctx.guild:
            if DEBUG_MODE:
                print(f"\033[33m[AVERTISSEMENT] Tentative d'utilisation de 'layout' en DM par {ctx.author}\033[0m")
            await ctx.send(f"{E.ERROR} Cette commande doit être exécutée sur un serveur.")
            return

        if not await ensure_command_permission(ctx, command_name="layout"):
            if DEBUG_MODE:
                print(f"\033[31m[ERREUR] Permission refusée pour {ctx.author} sur la commande 'layout'.\033[0m")
            return

        try:
            await ctx.message.delete()
        except Exception:
            pass

        if DEBUG_MODE and not ERROR_LOG_ONLY:
            print(f"\033[32m[SUCCÈS] Lancement de l'éditeur de layout par {ctx.author} sur {ctx.guild.name}\033[0m")

        view = LayoutConfigView(self.bot, ctx.guild, ctx.author)
        
        preview_view = view.build_preview_layout()
        view.config_msg = await ctx.send(view=view)
        view.preview_msg = await ctx.send(view=preview_view)


async def setup(bot: commands.Bot):
    if DEBUG_MODE and not ERROR_LOG_ONLY:
        print(f"\033[35m[SYSTÈME] Chargement du cog Layout en cours...\033[0m")
    await bot.add_cog(LayoutCog(bot))