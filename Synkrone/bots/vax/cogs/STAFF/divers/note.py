# -*- coding: utf-8 -*-
"""
COG NOTES - Gestionnaire de notes Vax v3
=========================================
Système avancé de notes avec support LayoutV2, permissions hiérarchiques, 
et stockage optimisé via DataManager.
"""

from __future__ import annotations

import math
from datetime import datetime

import discord
from discord import ui
from discord.ext import commands
from discord import app_commands

from utils.config_data import DataManager
from utils.config_theme import config_manager
from utils.config_perm import ensure_command_permission, perm_command
from utils.config_prefix import prefix_config_manager
from utils.config_emoji import Emoji as E

# ==========================================
# CONFIGURATION GLOBALE & VARIABLES
# ==========================================
DEBUG_MODE = True
ERROR_ONLY_MODE = False

# Fallbacks emojis globaux
EMOJI_MEMO = getattr(E, "MEMO", "ðŸ“")
EMOJI_MODIFIER = getattr(E, "MODIFIER", "âœï¸")
EMOJI_SUPPRIMER = getattr(E, "SUPPRIMER", "ðŸ—‘ï¸")
EMOJI_RETOUR = getattr(E, "RETOUR", "â—€ï¸")
EMOJI_VALIDER = getattr(E, "VALIDER", "âœ…")
EMOJI_REFUSER = getattr(E, "REFUSER", "âŒ")
EMOJI_ROLE = getattr(E, "ROLE", "ðŸŽ­")
EMOJI_USER = getattr(E, "PROFIL", "ðŸ‘¤")
EMOJI_LIEN = getattr(E, "LIEN", "ðŸ”—")
EMOJI_ATTENTION = getattr(E, "ATTENTION", "âš ï¸")

NOTES_PER_PAGE = 10

# ==========================================
# SYSTÈME DE LOGS VAX V3
# ==========================================
def custom_log(level: str, message: str):
    """Système de logs colorés respectant les variables globales de debug."""
    is_error = level.lower() == "error"
    if ERROR_ONLY_MODE and not is_error:
        return
    if not DEBUG_MODE and not is_error:
        return

    colors = {
        "info": "\033[94m",    # Bleu
        "success": "\033[92m", # Vert
        "warning": "\033[93m", # Jaune
        "error": "\033[91m"    # Rouge
    }
    color = colors.get(level.lower(), "\033[0m")
    reset = "\033[0m"
    print(f"{color}[NOTE] [{level.upper()}] {message}{reset}")

# ==========================================
# GESTIONNAIRE DE DONNÉES (CRUD VIA DATAMANAGER)
# ==========================================
class NoteManager:
    """Gestionnaire des notes basé sur le DataManager standard."""
    
    def __init__(self):
        self.db = DataManager("staff/divers/notes")

    def get_all_notes(self, guild_id: int) -> dict:
        data = self.db.load(guild_id)
        return data.get("notes", {})

    def get_note(self, guild_id: int, name: str) -> dict | None:
        notes = self.get_all_notes(guild_id)
        return notes.get(name.lower())

    def create_note(self, guild_id: int, name: str, title: str, short_description: str, content: str, author_id: int) -> bool:
        data = self.db.load(guild_id)
        notes = data.setdefault("notes", {})
        
        if name in notes:
            return False
            
        now = datetime.now().isoformat()
        notes[name] = {
            "content": content[:2000],
            "title": title,
            "author_id": author_id,
            "created_at": now,
            "updated_at": now,
            "is_public": True,
            "short_description": short_description[:100],
            "markdown_enabled": False
        }
        self.db.save(guild_id, data)
        custom_log("success", f"Note '{name}' créée pour la guilde {guild_id}")
        return True

    def update_note(self, guild_id: int, name: str, data_updates: dict) -> bool:
        data = self.db.load(guild_id)
        notes = data.get("notes", {})
        
        if name not in notes:
            return False
            
        notes[name].update(data_updates)
        notes[name]["updated_at"] = datetime.now().isoformat()
        self.db.save(guild_id, data)
        custom_log("info", f"Note '{name}' mise à  jour pour la guilde {guild_id}")
        return True

    def delete_note(self, guild_id: int, name: str) -> bool:
        data = self.db.load(guild_id)
        notes = data.get("notes", {})
        
        if name in notes:
            del notes[name]
            self.db.save(guild_id, data)
            custom_log("warning", f"Note '{name}' supprimée pour la guilde {guild_id}")
            return True
        return False

# ==========================================
# MODALS (CRÉATION ET ÉDITION)
# ==========================================
class NoteModal(ui.Modal):
    def __init__(self, view: ui.LayoutView, mode: str = "create", note_name: str = None):
        super().__init__(title="Créer une Note" if mode == "create" else f"Modifier: {note_name}"[:45])
        self.parent_view = view
        self.mode = mode
        self.note_name = note_name
        self.manager = view.cog.note_manager

        note_data = {}
        if mode == "edit" and note_name:
            note_data = self.manager.get_note(view.guild.id, note_name) or {}

        self.n_name = ui.TextInput(
            label="Clé d'appel de la note (sans espace)", 
            max_length=20, 
            required=True,
            default=note_name if mode == "edit" else ""
        )
        self.n_title = ui.TextInput(
            label="Titre affiché", 
            max_length=50, 
            required=True, 
            default=note_data.get("title", "")
        )
        self.n_short = ui.TextInput(
            label="Description courte", 
            max_length=100, 
            required=True, 
            default=note_data.get("short_description", "")
        )
        self.n_content = ui.TextInput(
            label="Contenu", 
            style=discord.TextStyle.paragraph, 
            max_length=2000, 
            required=True, 
            default=note_data.get("content", "")
        )
        
        self.add_item(self.n_name)
        self.add_item(self.n_title)
        self.add_item(self.n_short)
        self.add_item(self.n_content)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild_id = interaction.guild.id
        new_name = self.n_name.value.lower().replace(" ", "_")

        if self.mode == "create":
            success = self.manager.create_note(
                guild_id, new_name, self.n_title.value, self.n_short.value, self.n_content.value, interaction.user.id
            )
            if not success:
                await interaction.channel.send(f"{EMOJI_REFUSER} {interaction.user.mention}, une note avec cette clé existe déjà.")
                return
        else:
            if new_name != self.note_name:
                if self.manager.get_note(guild_id, new_name):
                    await interaction.channel.send(f"{EMOJI_REFUSER} {interaction.user.mention}, la clé '{new_name}' est déjà utilisée.")
                    return
                
                note_data = self.manager.get_note(guild_id, self.note_name)
                if note_data:
                    self.manager.create_note(guild_id, new_name, self.n_title.value, self.n_short.value, self.n_content.value, note_data['author_id'])
                    self.manager.update_note(guild_id, new_name, {
                        "is_public": note_data.get('is_public', True),
                        "markdown_enabled": note_data.get('markdown_enabled', False),
                        "created_at": note_data['created_at']
                    })
                    self.manager.delete_note(guild_id, self.note_name)
                    if hasattr(self.parent_view, 'note_name'):
                        self.parent_view.note_name = new_name
            else:
                self.manager.update_note(guild_id, self.note_name, {
                    "title": self.n_title.value,
                    "short_description": self.n_short.value,
                    "content": self.n_content.value
                })

        if hasattr(self.parent_view, '_build'):
            self.parent_view._build()
            await interaction.message.edit(view=self.parent_view)

        await interaction.channel.send(f"{EMOJI_VALIDER} {interaction.user.mention}, la note `{new_name}` a été sauvegardée avec succès.")

# ==========================================
# INTERFACES UTILISATEUR (VIEWS LAYOUT V2)
# ==========================================
class EditNoteLayoutView(ui.LayoutView):
    def __init__(self, cog, guild, user, note_name, parent_panel):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.user = user
        self.note_name = note_name
        self.parent_panel = parent_panel
        self.confirm_delete = False
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(f"{EMOJI_REFUSER} {interaction.user.mention}, vous n'avez pas la permission d'utiliser ce menu.")
            return False
        return True

    def _build(self):
        self.clear_items()
        note_data = self.cog.note_manager.get_note(self.guild.id, self.note_name)
        
        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.cog.bot)
        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text", "")

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        
        if not note_data:
            container.add_item(ui.TextDisplay(f"# {EMOJI_ATTENTION} Erreur"))
            container.add_item(ui.TextDisplay("Cette note est introuvable ou a été supprimée."))
            
            back_row = ui.ActionRow()
            # Sécurisation Unicode stricte pour éviter l'erreur 50035
            back_btn = ui.Button(label="Retour", style=discord.ButtonStyle.secondary, emoji="â—€ï¸")
            back_btn.callback = self.on_back
            back_row.add_item(back_btn)
            container.add_item(back_row)
            self.add_item(container)
            return

        content_display = f"```md\n{note_data['content']}\n```" if note_data.get('markdown_enabled') else note_data['content']
        visibility = "ðŸŒ Publique" if note_data.get('is_public', True) else "ðŸ”’ Privée (Admin uniquement)"

        author_id = note_data.get('author_id')
        author_member = self.guild.get_member(author_id)
        author_name = author_member.display_name if author_member else f"ID: {author_id}"

        # Titre et détails formatés en TextDisplay (sans le paramètre accessory pour éviter les crashs)
        container.add_item(ui.TextDisplay(f"# âœï¸ Édition : {note_data.get('title', self.note_name)}"))
        
        container.add_item(ui.TextDisplay("## Détails de la note"))
        container.add_item(
            ui.TextDisplay(
                f"- **Clé d'appel:** `/note {self.note_name}`\n"
                f"- **Visibilité:** {visibility}\n"
                f"- **Auteur:** {author_name}\n"
                f"- **Description:** {note_data.get('short_description', 'N/A')}\n"
            )
        )
        
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
        container.add_item(ui.TextDisplay("## Aperçu du contenu"))
        container.add_item(ui.TextDisplay(content_display))

        # Sélecteur d'actions restauré, avec emojis Unicode 100% natifs et infaillibles
        action_row = ui.ActionRow()
        action_options = [
            discord.SelectOption(label="Modifier", value="edit", emoji="âœï¸", description="Modifier le contenu de la note"),
            discord.SelectOption(label="Visibilité", value="visibility", emoji="ðŸ”„", description="Alterner entre publique et privée"),
            discord.SelectOption(label="Markdown", value="markdown", emoji="ðŸ“„", description="Activer ou désactiver le rendu Markdown"),
            discord.SelectOption(label="Supprimer", value="delete", emoji="ðŸ—‘ï¸", description="Supprimer définitivement cette note")
        ]
        action_select = ui.Select(placeholder="Choisissez une action...", min_values=1, max_values=1, options=action_options)
        action_select.callback = self.on_action_select
        action_row.add_item(action_select)
        container.add_item(action_row)

        # Ligne d'actions dédiées au danger (Retour et Confirmation) avec emojis robustes
        danger_row = ui.ActionRow()
        back_btn = ui.Button(label="Retour", style=discord.ButtonStyle.success, emoji="â—€ï¸")
        back_btn.callback = self.on_back
        danger_row.add_item(back_btn)

        if self.confirm_delete:
            confirm_btn = ui.Button(label="Confirmer Suppression", style=discord.ButtonStyle.danger, emoji="âœ…")
            confirm_btn.callback = self.on_confirm_delete
            danger_row.add_item(confirm_btn)
            
            cancel_btn = ui.Button(label="Annuler", style=discord.ButtonStyle.secondary, emoji="âŒ")
            cancel_btn.callback = self.on_cancel_delete
            danger_row.add_item(cancel_btn)

        container.add_item(danger_row)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    async def on_action_select(self, interaction: discord.Interaction):
        try:
            if not interaction.data or "values" not in interaction.data:
                if not interaction.response.is_done():
                    await interaction.response.defer()
                return
                
            choice = interaction.data.get("values")[0]
            note_data = self.cog.note_manager.get_note(self.guild.id, self.note_name)
            
            if choice == "edit":
                await interaction.response.send_modal(NoteModal(self, mode="edit", note_name=self.note_name))
                
            elif choice == "visibility":
                self.cog.note_manager.update_note(self.guild.id, self.note_name, {"is_public": not note_data.get("is_public", True)})
                self._build()
                await interaction.response.edit_message(view=self)
                
            elif choice == "markdown":
                self.cog.note_manager.update_note(self.guild.id, self.note_name, {"markdown_enabled": not note_data.get("markdown_enabled", False)})
                self._build()
                await interaction.response.edit_message(view=self)
                
            elif choice == "delete":
                self.confirm_delete = True
                self._build()
                await interaction.response.edit_message(view=self)
                
        except Exception as e:
            custom_log("error", f"Erreur lors de la sélection d'action : {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"{EMOJI_ATTENTION} Une erreur est survenue : {e}")

    async def on_cancel_delete(self, interaction: discord.Interaction):
        self.confirm_delete = False
        self._build()
        await interaction.response.edit_message(view=self)

    async def on_confirm_delete(self, interaction: discord.Interaction):
        self.cog.note_manager.delete_note(self.guild.id, self.note_name)
        await interaction.response.send_message(f"{EMOJI_VALIDER} {interaction.user.mention}, la note `{self.note_name}` a été supprimée.")
        self.parent_panel._build()
        await interaction.message.edit(view=self.parent_panel)

    async def on_back(self, interaction: discord.Interaction):
        self.parent_panel._build()
        await interaction.response.edit_message(view=self.parent_panel)


class NotePanelLayoutView(ui.LayoutView):
    def __init__(self, cog, guild, user, page=0):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.user = user
        self.page = page
        self.max_pages = 1
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(f"{EMOJI_REFUSER} {interaction.user.mention}, ce menu ne vous appartient pas.")
            return False
        return True

    def _build(self):
        self.clear_items()
        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.cog.bot)
        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text", "")

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        
        title_section = ui.Section(
            ui.TextDisplay(f"# {EMOJI_MEMO} Gestionnaire de Notes"),
            accessory=ui.Button(
                label="Ajouter",
                style=discord.ButtonStyle.success,
                emoji="âž•"
            )
        )
        title_section.accessory.callback = self.on_add
        container.add_item(title_section)
        
        all_notes = self.cog.note_manager.get_all_notes(self.guild.id)
        sorted_keys = sorted(all_notes.keys())
        
        self.max_pages = math.ceil(len(sorted_keys) / NOTES_PER_PAGE) or 1
        self.page = max(0, min(self.page, self.max_pages - 1))
        
        start = self.page * NOTES_PER_PAGE
        page_keys = sorted_keys[start:start + NOTES_PER_PAGE]

        effective_prefixes = prefix_config_manager.get_effective_prefixes(self.cog.bot, self.guild.id, default_prefix="!")
        pfx = effective_prefixes[0] if effective_prefixes else "!"

        desc = (
            "Gérez vos blocs de texte configurables dynamiquement pour une utilisation simplifiée sur votre serveur.\n\n"
            "**Exemples d'utilisation :**\n"
            f"â€¢ `{pfx}note recrutement`\n"
            f"â€¢ `{pfx}note reglement`\n\n"
            "**ðŸ“š Notes disponibles :**\n"
        )

        if not sorted_keys:
            desc += "*Aucune note n'a été créée pour le moment.*"
        else:
            for i, k in enumerate(page_keys, start=start + 1):
                note = all_notes[k]
                icon = "ðŸŒ" if note.get("is_public", True) else "ðŸ”’"
                desc += f"`{i}.` {icon} **{k}** - {note.get('short_description', 'N/A')}\n"

        container.add_item(ui.TextDisplay(desc))

        if page_keys:
            select_row = ui.ActionRow()
            options = [
                discord.SelectOption(
                    label=f"{i+1}. {k}", 
                    description=all_notes[k].get('short_description', '')[:95],
                    emoji="ðŸ“„",
                    value=k
                ) for i, k in enumerate(page_keys, start=start + 1)
            ]
            select = ui.Select(placeholder="Sélectionnez une note pour la configurer...", options=options)
            select.callback = self.on_select_note
            select_row.add_item(select)
            container.add_item(select_row)

        nav_row = ui.ActionRow()
        # Sécurisation des emojis directionnels avec Unicode pur
        btn_prev = ui.Button(emoji="â—€ï¸", style=discord.ButtonStyle.secondary, disabled=(self.page == 0))
        btn_prev.callback = self.on_prev
        
        btn_page = ui.Button(label=f"Page {self.page + 1}/{self.max_pages}", style=discord.ButtonStyle.secondary, disabled=True)
        
        btn_next = ui.Button(emoji="â–¶ï¸", style=discord.ButtonStyle.secondary, disabled=(self.page >= self.max_pages - 1))
        btn_next.callback = self.on_next
        
        nav_row.add_item(btn_prev)
        nav_row.add_item(btn_page)
        nav_row.add_item(btn_next)
        
        container.add_item(nav_row)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    async def on_select_note(self, interaction: discord.Interaction):
        try:
            if not interaction.data or "values" not in interaction.data:
                if not interaction.response.is_done():
                    await interaction.response.defer()
                return
                
            selected_key = interaction.data.get("values")[0]
            edit_view = EditNoteLayoutView(self.cog, self.guild, self.user, selected_key, self)
            await interaction.response.edit_message(view=edit_view)
        except Exception as e:
            custom_log("error", f"Erreur lors de la sélection de la note : {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"{EMOJI_ATTENTION} Une erreur est survenue : {e}")

    async def on_prev(self, interaction: discord.Interaction):
        self.page -= 1
        self._build()
        await interaction.response.edit_message(view=self)

    async def on_next(self, interaction: discord.Interaction):
        self.page += 1
        self._build()
        await interaction.response.edit_message(view=self)

    async def on_add(self, interaction: discord.Interaction):
        await interaction.response.send_modal(NoteModal(self, mode="create"))


class DisplayNoteLayoutView(ui.LayoutView):
    """LayoutV2 léger pour l'affichage frontal d'une note aux utilisateurs"""
    def __init__(self, bot, guild, user, note_data):
        super().__init__(timeout=180)
        self.bot = bot
        self.guild = guild
        self.user = user
        self.note_data = note_data
        self._build()

    def _build(self):
        self.clear_items()
        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.bot)
        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text", "")

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {self.note_data.get('title', 'Note')}"))
        
        content = self.note_data.get("content", "")
        if self.note_data.get("markdown_enabled", False):
            content = f"```md\n{content}\n```"

        container.add_item(ui.TextDisplay(content))

        try:
            created_ts = int(datetime.fromisoformat(self.note_data["created_at"]).timestamp())
            
            author_id = self.note_data.get('author_id')
            author_member = self.guild.get_member(author_id)
            author_name = author_member.display_name if author_member else f"ID: {author_id}"
            
            metadata = f"- **Auteur:** {author_name}\n- **Créée le:** <t:{created_ts}:F>"
            
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
            container.add_item(ui.TextDisplay(metadata))
        except Exception as e:
            custom_log("warning", f"Affichage des métadonnées échoué : {e}")

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

# ==========================================
# COG PRINCIPAL
# ==========================================
class NoteCog(commands.Cog, name="Notes"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.note_manager = NoteManager()

    @perm_command(level=3)
    @commands.hybrid_command(name="note", aliases=["notes"], description="Affiche le panel de gestion des notes ou le contenu d'une note.")
    @app_commands.describe(name="La clé de la note à afficher (laisser vide pour le panel de gestion)")
    async def note_cmd(self, ctx: commands.Context, name: str = None):
        """Point d'entrée du module Note respectant les autorisations."""
        if not ctx.guild:
            await ctx.send(f"{EMOJI_REFUSER} {ctx.author.mention}, cette commande doit être exécutée sur un serveur.")
            return

        if not await ensure_command_permission(ctx, command_name="note"):
            return

        # MODE PANEL DE GESTION
        if name is None:
            view = NotePanelLayoutView(self, ctx.guild, ctx.author)
            await ctx.send(view=view)
            return

        # MODE AFFICHAGE DE NOTE UTILISATEUR
        note_data = self.note_manager.get_note(ctx.guild.id, name)
        if not note_data:
            await ctx.send(f"{EMOJI_REFUSER} La note `{name}` n'existe pas sur ce serveur.")
            return

        if not note_data.get("is_public", True) and not ctx.author.guild_permissions.administrator:
            await ctx.send(f"{EMOJI_ATTENTION} Cette note est restreinte au personnel administratif.")
            return

        view = DisplayNoteLayoutView(self.bot, ctx.guild, ctx.author, note_data)
        await ctx.send(view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(NoteCog(bot))
    custom_log("success", "Module Notes (LayoutV2) chargé avec succès.")
