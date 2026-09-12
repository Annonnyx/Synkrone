# -*- coding: utf-8-sig -*-
import discord
from discord import ui, app_commands
from discord.ext import commands, tasks
import asyncio
import os
import re
from pathlib import Path
import traceback

# ==============================================================================
# --- IMPORTS MÉTIER VAX ---
# Utilisation stricte de l'écosystème pour garantir l'homogénéité globale.
# ==============================================================================
try:
    from utils.config_data import DataManager
    from utils.config_theme import config_manager
    from utils.config_perm import ensure_command_permission, perm_command
    from utils.config_emoji import Emoji as E
    HAS_VAX_CORE = True
except ImportError as e:
    HAS_VAX_CORE = False
    print(f"\033[91m[ERREUR CRITIQUE] Impossible d'importer le noyau Vax : {e}\033[0m")

# ==============================================================================
# --- CONFIGURATION GLOBALE & DÉBOGAGE ---
# ==============================================================================
DEBUG_LOGS = True
ERROR_LOGS_ONLY = False

# ==============================================================================
# --- CENTRALISATION DES EMOJIS ---
# ==============================================================================
E_ON = getattr(E, 'VALIDER', "🟢") if HAS_VAX_CORE else "🟢"
E_OFF = getattr(E, 'REFUSER', "🔴") if HAS_VAX_CORE else "🔴"
E_WARN = getattr(E, 'ATTENTION', "⚠️") if HAS_VAX_CORE else "⚠️"
E_GEAR = getattr(E, 'MODIFIER', "⚙️") if HAS_VAX_CORE else "⚙️"
E_ADD = getattr(E, 'AJOUTER', "➕") if HAS_VAX_CORE else "➕"
E_EDIT = getattr(E, 'MODIFIER', "✏️") if HAS_VAX_CORE else "✏️"
E_TRASH = getattr(E, 'SUPPRIMER', "🗑️") if HAS_VAX_CORE else "🗑️"
E_IMAGE = getattr(E, 'IMAGE', "🖼️") if HAS_VAX_CORE else "🖼️"
E_TEXT = getattr(E, 'MEMO', "📝") if HAS_VAX_CORE else "📝"
E_TICKET = getattr(E, 'DOCUMENT', "🎫") if HAS_VAX_CORE else "🎫"
E_SUPPORT = getattr(E, 'BOUCLIER', "🛡️") if HAS_VAX_CORE else "🛡️"
E_FOLDER = getattr(E, 'LISTE', "📂") if HAS_VAX_CORE else "📂"
E_ARCHIVE = getattr(E, 'HISTOIRE', "🗄️") if HAS_VAX_CORE else "🗄️"
E_LOCK = getattr(E, 'LOCK', "🔒") if HAS_VAX_CORE else "🔒"
E_UNLOCK = getattr(E, 'UNLOCK', "🔓") if HAS_VAX_CORE else "🔓"
E_BULLET = getattr(E, 'FLECHE_DROITE', "🔸") if HAS_VAX_CORE else "🔸"
E_LIGHT = getattr(E, 'LAMPE', "💡") if HAS_VAX_CORE else "💡"
E_ID = getattr(E, 'IDENTIFIANT', "🆔") if HAS_VAX_CORE else "🆔"
E_SYNC = getattr(E, 'RAFRAICHIR', "🔄") if HAS_VAX_CORE else "🔄"
E_BACK = getattr(E, 'RETOUR', "↩️") if HAS_VAX_CORE else "↩️"
E_LINK = getattr(E, 'LIEN', "🔗") if HAS_VAX_CORE else "🔗"

GEN_NAME = f"{E_GEAR} Général"
EXEMPLE_DATA = [
    {"name": "🤝 Partenariat", "desc": "Proposez une collaboration ou un échange."},
    {"name": "📝 Recrutement", "desc": "Postulez pour rejoindre nos rangs."},
    {"name": "🎉 Animation", "desc": "Suggestions ou problèmes liés aux events."},
    {"name": "🛡️ Report", "desc": "Signaler un joueur ou un abus."},
    {"name": "💎 Boutique", "desc": "Problème avec un achat ou un grade."},
    {"name": "💡 Suggestion", "desc": "Partagez vos idées pour le serveur."},
    {"name": "🛠️ Bug", "desc": "Signaler un dysfonctionnement technique."},
    {"name": "❓ Question", "desc": "Besoin d'une information générale."}
]

def log_sys(action: str, message: str, is_error: bool = False):
    if ERROR_LOGS_ONLY and not is_error: return
    if not DEBUG_LOGS and not is_error: return
    color = "\033[91m" if is_error else "\033[96m"
    prefix = "[ERREUR Tickets]" if is_error else "[INFO Tickets]"
    print(f"{color}{prefix} [{action}] {message}\033[0m")

# ==============================================================================
# --- GESTIONNAIRE DE DONNÉES (DataManager) ---
# ==============================================================================
class TicketManager:
    def __init__(self):
        if HAS_VAX_CORE:
            self.data = DataManager("staff/configuration/data_tickets")
            self.assets_dir = Path("data/staff/configuration/data_tickets/assets")
            try:
                self.assets_dir.mkdir(parents=True, exist_ok=True)
            except Exception: pass

    def get_bg_path(self, guild_id: int) -> Path:
        return self.assets_dir / f"{guild_id}_banner.png"

    def get_default_config(self):
        return {
            "channel_id": None,
            "category_id": None,
            "archive_id": None,
            "support_role_id": None,
            "msg_id": None,
            "custom_title": None,
            "custom_description": None,
            "custom_banner_url": None,
            "categories": [{"name": GEN_NAME, "desc": "Support classique.", "category_id": None}],
            "ticket_count": 0,
            "stats": {"total_wait_time": 0, "total_answered": 0}
        }

    def load(self, guild_id: int) -> dict:
        try:
            raw = self.data.load(guild_id) or {}
            return {**self.get_default_config(), **raw}
        except Exception:
            return self.get_default_config()

    def save(self, guild_id: int, config: dict):
        self.data.save(guild_id, config)

ticket_db = TicketManager()

# ==============================================================================
# --- MODALS D'ADMINISTRATION ET UTILISATEUR ---
# ==============================================================================
class TicketChanIdModal(ui.Modal, title="ID Salon Accueil"):
    def __init__(self, view: "TicketAdminLayoutView"):
        super().__init__()
        self.view = view
        conf = ticket_db.load(view.guild.id)
        self.c = ui.TextInput(label="ID du Salon", default=str(conf.get("channel_id") or ""), required=False)
        self.add_item(self.c)

    async def on_submit(self, interaction: discord.Interaction):
        conf = ticket_db.load(self.view.guild.id)
        try:
            conf["channel_id"] = int(self.c.value) if self.c.value.strip() else None
            ticket_db.save(self.view.guild.id, conf)
            self.view.status_message = f"{E_ON} Salon d'accueil mis à jour."
            await self.view._refresh(interaction)
            await self.view.cog.sync_launcher_message(self.view.guild, conf)
        except ValueError:
            if not interaction.response.is_done(): await interaction.response.defer(ephemeral=True)
            await interaction.followup.send(f"{E_OFF} {interaction.user.mention}, ID invalide.", ephemeral=True)

class TicketRoleIdModal(ui.Modal, title="ID Rôle Support"):
    def __init__(self, view: "TicketAdminLayoutView"):
        super().__init__()
        self.view = view
        conf = ticket_db.load(view.guild.id)
        self.r = ui.TextInput(label="ID du Rôle", default=str(conf.get("support_role_id") or ""), required=False)
        self.add_item(self.r)

    async def on_submit(self, interaction: discord.Interaction):
        conf = ticket_db.load(self.view.guild.id)
        try:
            conf["support_role_id"] = int(self.r.value) if self.r.value.strip() else None
            ticket_db.save(self.view.guild.id, conf)
            self.view.status_message = f"{E_ON} Rôle support mis à jour."
            await self.view._refresh(interaction)
        except ValueError:
            if not interaction.response.is_done(): await interaction.response.defer(ephemeral=True)
            await interaction.followup.send(f"{E_OFF} {interaction.user.mention}, ID invalide.", ephemeral=True)

class TicketCatsIdModal(ui.Modal, title="IDs Catégories (Ouverts & Archives)"):
    def __init__(self, view: "TicketAdminLayoutView"):
        super().__init__()
        self.view = view
        conf = ticket_db.load(view.guild.id)
        self.o = ui.TextInput(label="ID Catégorie Ouverts", default=str(conf.get("category_id") or ""), required=False)
        self.a = ui.TextInput(label="ID Catégorie Archives", default=str(conf.get("archive_id") or ""), required=False)
        self.add_item(self.o)
        self.add_item(self.a)

    async def on_submit(self, interaction: discord.Interaction):
        conf = ticket_db.load(self.view.guild.id)
        try:
            conf["category_id"] = int(self.o.value) if self.o.value.strip() else None
            conf["archive_id"] = int(self.a.value) if self.a.value.strip() else None
            ticket_db.save(self.view.guild.id, conf)
            self.view.status_message = f"{E_ON} Catégories mises à jour."
            await self.view._refresh(interaction)
        except ValueError:
            if not interaction.response.is_done(): await interaction.response.defer(ephemeral=True)
            await interaction.followup.send(f"{E_OFF} {interaction.user.mention}, un ou plusieurs IDs sont invalides.", ephemeral=True)

class TicketMotifAddModal(ui.Modal, title="Ajouter un Motif"):
    n = ui.TextInput(label="Nom du motif", max_length=50, required=True)
    d = ui.TextInput(label="Description", style=discord.TextStyle.paragraph, max_length=100, required=False)
    
    def __init__(self, view: "TicketAdminLayoutView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        conf = ticket_db.load(self.view.guild.id)
        if len(conf["categories"]) >= 25:
            if not interaction.response.is_done(): await interaction.response.defer(ephemeral=True)
            return await interaction.followup.send(f"{E_WARN} Limite de 25 motifs atteinte.", ephemeral=True)
            
        conf["categories"].append({"name": self.n.value.strip(), "desc": self.d.value.strip(), "category_id": None})
        ticket_db.save(self.view.guild.id, conf)
        
        self.view.status_message = f"{E_ON} Le motif `{self.n.value}` a été ajouté."
        await self.view.cog.sync_launcher_message(self.view.guild, conf)
        await self.view._refresh(interaction)

class TicketMotifEditModal(ui.Modal, title="Modifier un Motif"):
    n = ui.TextInput(label="Nouveau Nom", max_length=50, required=True)
    d = ui.TextInput(label="Nouvelle Description", style=discord.TextStyle.paragraph, max_length=100, required=False)
    
    def __init__(self, view: "TicketAdminLayoutView", idx: int):
        super().__init__()
        self.view = view
        self.idx = idx
        conf = ticket_db.load(view.guild.id)
        cat = conf["categories"][idx]
        self.n.default = cat["name"]
        self.d.default = cat.get("desc", "")

    async def on_submit(self, interaction: discord.Interaction):
        conf = ticket_db.load(self.view.guild.id)
        conf["categories"][self.idx]["name"] = self.n.value.strip()
        conf["categories"][self.idx]["desc"] = self.d.value.strip()
        ticket_db.save(self.view.guild.id, conf)
        
        self.view.status_message = f"{E_ON} Textes du motif mis à jour."
        await self.view.cog.sync_launcher_message(self.view.guild, conf)
        await self.view._refresh(interaction)

class TicketTitleModal(ui.Modal, title="Titre du Launcher"):
    t = ui.TextInput(label="Titre personnalisé", required=False, max_length=100)
    def __init__(self, view: "TicketAdminLayoutView"):
        super().__init__()
        self.view = view
        conf = ticket_db.load(self.view.guild.id)
        self.t.default = conf.get("custom_title", "")

    async def on_submit(self, interaction: discord.Interaction):
        conf = ticket_db.load(self.view.guild.id)
        conf["custom_title"] = self.t.value.strip() or None
        ticket_db.save(self.view.guild.id, conf)
        self.view.status_message = f"{E_ON} Titre du Launcher mis à jour."
        await self.view.cog.sync_launcher_message(self.view.guild, conf)
        await self.view._refresh(interaction)

class TicketTextModal(ui.Modal, title="Texte d'Accueil Launcher"):
    t = ui.TextInput(label="Description personnalisée", style=discord.TextStyle.paragraph, required=False, max_length=1500)
    def __init__(self, view: "TicketAdminLayoutView"):
        super().__init__()
        self.view = view
        conf = ticket_db.load(self.view.guild.id)
        self.t.default = conf.get("custom_description", "")

    async def on_submit(self, interaction: discord.Interaction):
        conf = ticket_db.load(self.view.guild.id)
        conf["custom_description"] = self.t.value.strip() or None
        ticket_db.save(self.view.guild.id, conf)
        self.view.status_message = f"{E_ON} Texte du Launcher mis à jour."
        await self.view.cog.sync_launcher_message(self.view.guild, conf)
        await self.view._refresh(interaction)

# --- MODALS UTILISATEUR PUBLIC ---
class TicketCreationModal(ui.Modal):
    """Saisie des détails pour l'ouverture du ticket sans sujet manuel."""
    description = ui.TextInput(label="Description détaillée", placeholder="Expliquez votre problème ici...", style=discord.TextStyle.paragraph, min_length=10, max_length=1000, required=True)
    
    def __init__(self, cog: "TicketCog", category_name: str):
        super().__init__(title=f"Ouverture : {category_name[:20]}")
        self.cog = cog
        self.category_name = category_name

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        
        channel = await self.cog.create_ticket_process(interaction, self.category_name, self.description.value)
        if channel:
            await interaction.followup.send(f"{E_ON} Votre ticket a été ouvert avec succès : {channel.mention}", ephemeral=True)
        else:
            await interaction.followup.send(f"{E_OFF} Impossible de créer le ticket (L'infrastructure est manquante ou le bot manque de permissions).", ephemeral=True)

class TicketReopenModal(ui.Modal, title="Motif de Réouverture"):
    reason = ui.TextInput(label="Pourquoi réouvrez-vous ce ticket ?", style=discord.TextStyle.paragraph, required=True, max_length=500)
    def __init__(self, cog: "TicketCog", owner_id: int):
        super().__init__()
        self.cog = cog
        self.owner_id = owner_id

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.response.is_done(): await interaction.response.defer()
        await self.cog.reopen_ticket_process(interaction, self.owner_id, self.reason.value)


# ==============================================================================
# --- SÉLECTEURS DE NAVIGATION & CONFIGURATION ---
# ==============================================================================
class MainNavSelect(ui.Select):
    def __init__(self, view: "TicketAdminLayoutView"):
        self.parent_view = view
        options = [
            discord.SelectOption(label="Résumé", value="resume", emoji=E_FOLDER, description="Vue d'ensemble du système", default=(view.current_page == "resume")),
            discord.SelectOption(label="Emplacement & Accès", value="emplacement", emoji=E_GEAR, description="Salons, Catégories et Rôle Support", default=(view.current_page == "emplacement")),
            discord.SelectOption(label="Visuel", value="visuel", emoji=E_IMAGE, description="Textes, Bannière et Titre", default=(view.current_page == "visuel")),
            discord.SelectOption(label="Motifs de contact", value="motifs", emoji=E_TICKET, description="Configurer les choix d'ouverture", default=(view.current_page == "motifs")),
        ]
        super().__init__(placeholder="Menu de configuration...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.parent_view.current_page = self.values[0]
        await self.parent_view._refresh(interaction)

class VisualActionSelect(ui.Select):
    def __init__(self, view: "TicketAdminLayoutView"):
        self.parent_view = view
        options = [
            discord.SelectOption(label="Modifier Titre", value="title", emoji=E_EDIT),
            discord.SelectOption(label="Modifier Texte", value="text", emoji=E_TEXT),
            discord.SelectOption(label="Modifier Bannière", value="banner", emoji=E_IMAGE),
            discord.SelectOption(label="Forcer MàJ Launcher", value="sync", emoji=E_SYNC)
        ]
        super().__init__(placeholder="Actions visuelles...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val == "title": await interaction.response.send_modal(TicketTitleModal(self.parent_view))
        elif val == "text": await interaction.response.send_modal(TicketTextModal(self.parent_view))
        elif val == "banner": await self.parent_view._on_banner_upload(interaction)
        elif val == "sync": await self.parent_view._force_sync(interaction)

class MotifSelect(ui.Select):
    def __init__(self, view: "TicketAdminLayoutView"):
        self.parent_view = view
        conf = ticket_db.load(view.guild.id)
        options = []
        for i, c in enumerate(conf.get('categories', [])):
            options.append(discord.SelectOption(label=c['name'][:90], value=str(i), emoji=E_EDIT))
            
        super().__init__(placeholder="Sélectionnez un motif pour le configurer...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.parent_view.current_motif_idx = int(self.values[0])
        self.parent_view.current_page = "motif_edit"
        await self.parent_view._refresh(interaction)

class MotifActionSelect(ui.Select):
    def __init__(self, view: "TicketAdminLayoutView"):
        self.parent_view = view
        options = [
            discord.SelectOption(label="Éditer Nom & Description", value="text", emoji=E_EDIT),
            discord.SelectOption(label="Éditer Catégorie Spécifique", value="cat", emoji=E_FOLDER),
        ]
        super().__init__(placeholder="Que souhaitez-vous modifier ?", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        val = self.values[0]
        if val == "text":
            await interaction.response.send_modal(TicketMotifEditModal(self.parent_view, self.parent_view.current_motif_idx))
        elif val == "cat":
            self.parent_view.current_page = "motif_edit_cat"
            await self.parent_view._refresh(interaction)

# Sélecteurs natifs pour Emplacement
class GenericChannelSelect(ui.ChannelSelect):
    def __init__(self, view: "TicketAdminLayoutView", key: str, placeholder: str, c_type: discord.ChannelType):
        self.parent_view = view
        self.key = key
        super().__init__(placeholder=placeholder, channel_types=[c_type], min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        conf = ticket_db.load(interaction.guild.id)
        conf[self.key] = self.values[0].id
        ticket_db.save(interaction.guild.id, conf)
        
        if self.key == "channel_id":
            await self.parent_view.cog.sync_launcher_message(interaction.guild, conf)
            
        self.parent_view.status_message = f"{E_ON} Modification enregistrée."
        await self.parent_view._refresh(interaction)

class SupportRoleSelect(ui.RoleSelect):
    def __init__(self, view: "TicketAdminLayoutView"):
        self.parent_view = view
        super().__init__(placeholder="Sélectionnez le rôle du support...", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        conf = ticket_db.load(interaction.guild.id)
        conf["support_role_id"] = self.values[0].id
        ticket_db.save(interaction.guild.id, conf)
        self.parent_view.status_message = f"{E_ON} Rôle support défini."
        await self.parent_view._refresh(interaction)

class MotifCategorySelect(ui.ChannelSelect):
    def __init__(self, view: "TicketAdminLayoutView"):
        self.parent_view = view
        super().__init__(placeholder="Lier une catégorie existante...", channel_types=[discord.ChannelType.category], min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cat = self.values[0]
        conf = ticket_db.load(interaction.guild.id)
        conf["categories"][self.parent_view.current_motif_idx]["category_id"] = cat.id
        ticket_db.save(interaction.guild.id, conf)
        
        self.parent_view.status_message = f"{E_ON} Catégorie affectée à ce motif."
        self.parent_view.current_page = "motif_edit"
        await self.parent_view._refresh(interaction)


# ==============================================================================
# --- VUES (Layout V2) ---
# ==============================================================================
class TicketAdminLayoutView(ui.LayoutView):
    def __init__(self, cog: "TicketCog", guild: discord.Guild, user: discord.Member):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild = guild
        self.user = user
        self.status_message = ""
        self.current_page = "resume"
        self.current_motif_idx = 0
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            if not interaction.response.is_done(): await interaction.response.defer(ephemeral=True)
            await interaction.followup.send(f"{E_OFF} {interaction.user.mention}, ce menu est verrouillé.", ephemeral=True)
            return False
        return True

    def _build(self):
        self.clear_items()
        conf = ticket_db.load(self.guild.id)
        
        accent_color = 0x3498db
        footer_text = ""
        if HAS_VAX_CORE and config_manager:
            try:
                theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.cog.bot)
                accent_color = int(theme.get("color", 0x3498db))
                footer_text = theme.get("footer_text", "")
            except Exception: pass

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {E_SUPPORT} Ingénierie des Tickets"))
        
        if self.current_page not in ["motif_edit", "motif_edit_cat"]:
            nav_row = ui.ActionRow()
            nav_row.add_item(MainNavSelect(self))
            container.add_item(nav_row)

        if self.status_message:
            container.add_item(ui.TextDisplay(f"> {self.status_message}"))
            self.status_message = ""

        # ================= PAGE : RESUME =================
        if self.current_page == "resume":
            role = self.guild.get_role(conf.get('support_role_id'))
            chan = self.guild.get_channel(conf.get('channel_id'))
            cat_op = self.guild.get_channel(conf.get('category_id'))
            cat_ar = self.guild.get_channel(conf.get('archive_id'))

            r_str = f"`@{role.name}`" if role else "`Non défini`"
            c_str = f"`#{chan.name}`" if chan else "`Non défini`"
            o_str = f"`{cat_op.name}`" if cat_op else "`Non défini`"
            a_str = f"`{cat_ar.name}`" if cat_ar else "`Non défini`"

            desc = (
                f"**Salon d'accueil :** {c_str}\n"
                f"**Support :** {r_str}\n\n"
                f"**Catégories :**\n"
                f"- Ouverts : {o_str}\n"
                f"- Archives : {a_str}\n\n"
                f"### {E_FOLDER} Motifs de contact ({len(conf['categories'])}/25)\n"
            )

            lines = [f"{E_BULLET} **{c['name']}** : {c.get('desc', 'Aucune description')}" for c in conf.get('categories', [])]
            desc += "\n".join(lines) if lines else "*Aucun motif configuré.*"
            container.add_item(ui.TextDisplay(desc))

        # ================= PAGE : EMPLACEMENT =================
        elif self.current_page == "emplacement":
            role = self.guild.get_role(conf.get('support_role_id'))
            chan = self.guild.get_channel(conf.get('channel_id'))
            cat_op = self.guild.get_channel(conf.get('category_id'))
            cat_ar = self.guild.get_channel(conf.get('archive_id'))
            
            r_str = f"`@{role.name}`" if role else "`Non défini`"
            c_str = f"`#{chan.name}`" if chan else "`Non défini`"
            o_str = f"`{cat_op.name}`" if cat_op else "`Non défini`"
            a_str = f"`{cat_ar.name}`" if cat_ar else "`Non défini`"
            
            # Bouton de génération Auto & IDs tout en haut (ActionRow 2)
            row2 = ui.ActionRow()
            btn_auto = ui.Button(label="Générer Infrastructure Auto", style=discord.ButtonStyle.success, emoji=E_ON)
            btn_auto.callback = self._on_auto_setup
            row2.add_item(btn_auto)

            btn_c_id = ui.Button(label="ID Accueil", style=discord.ButtonStyle.secondary, emoji=E_ID)
            btn_c_id.callback = self._open_id_chan
            row2.add_item(btn_c_id)

            btn_r_id = ui.Button(label="ID Rôle", style=discord.ButtonStyle.secondary, emoji=E_ID)
            btn_r_id.callback = self._open_id_role
            row2.add_item(btn_r_id)

            btn_cat_id = ui.Button(label="IDs Catégories", style=discord.ButtonStyle.secondary, emoji=E_ID)
            btn_cat_id.callback = self._open_id_cats
            row2.add_item(btn_cat_id)
            container.add_item(row2)

            container.add_item(ui.TextDisplay(
                f"### {E_GEAR} Résumé de la configuration\n"
                f"**Accueil :** {c_str} | **Support :** {r_str}\n"
                f"**Ouverts :** {o_str} | **Archives :** {a_str}"
            ))

            row3 = ui.ActionRow()
            row3.add_item(GenericChannelSelect(self, "channel_id", "1️⃣ Salon d'accueil...", discord.ChannelType.text))
            container.add_item(row3)

            row4 = ui.ActionRow()
            row4.add_item(SupportRoleSelect(self))
            container.add_item(row4)

            row5 = ui.ActionRow()
            row5.add_item(GenericChannelSelect(self, "category_id", "3️⃣ Catégorie (Ouverts)...", discord.ChannelType.category))
            container.add_item(row5)

        # ================= PAGE : VISUEL =================
        elif self.current_page == "visuel":
            chan = self.guild.get_channel(conf.get('channel_id'))
            c_str = chan.mention if chan else "`Non défini`"
            container.add_item(ui.TextDisplay(f"### {E_IMAGE} Visuel\nSalon d'accueil configuré : {c_str}\n\n*Personnalisez l'apparence de l'Embed d'accueil avec les options ci-dessous.*"))

            row1 = ui.ActionRow()
            row1.add_item(VisualActionSelect(self))
            container.add_item(row1)

        # ================= PAGE : MOTIFS =================
        elif self.current_page == "motifs":
            lines = [f"{E_BULLET} **{c['name']}** : {c.get('desc', 'Aucune description')}" for c in conf.get('categories', [])]
            desc_motifs = "\n".join(lines) if lines else "*Aucun motif configuré.*"
            
            container.add_item(ui.TextDisplay(f"### {E_TICKET} Motifs de contact existants\n{desc_motifs}"))

            row1 = ui.ActionRow()
            row1.add_item(MotifSelect(self))
            container.add_item(row1)

            row2 = ui.ActionRow()
            btn_add = ui.Button(label="Ajouter un motif", style=discord.ButtonStyle.success, emoji=E_ADD)
            btn_add.callback = self._open_add_motif_modal
            row2.add_item(btn_add)

            ex_names = [e["name"] for e in EXEMPLE_DATA]
            has_examples = any(c["name"] in ex_names for c in conf.get("categories", []))
            btn_ex = ui.Button(label="Exemples", style=discord.ButtonStyle.danger if has_examples else discord.ButtonStyle.primary, emoji=E_LIGHT)
            btn_ex.callback = self._on_toggle_examples
            row2.add_item(btn_ex)
            container.add_item(row2)

        # ================= PAGE : ÉDITION D'UN MOTIF =================
        elif self.current_page == "motif_edit":
            try: motif = conf["categories"][self.current_motif_idx]
            except IndexError:
                self.current_page = "motifs"
                return self._build()
                
            cat_id = motif.get("category_id")
            cat_obj = self.guild.get_channel(cat_id) if cat_id else None
            
            container.add_item(ui.TextDisplay(
                f"### {E_EDIT} Édition du motif\n"
                f"**Nom :** {motif['name']}\n"
                f"**Description :** {motif.get('desc', 'Aucune')}\n"
                f"**Catégorie spécifique :** {cat_obj.mention if cat_obj else '`Globale par défaut`'}"
            ))

            row1 = ui.ActionRow()
            row1.add_item(MotifActionSelect(self))
            container.add_item(row1)

            row2 = ui.ActionRow()
            btn_del = ui.Button(label="Supprimer ce motif", style=discord.ButtonStyle.danger, emoji=E_TRASH)
            btn_del.callback = self._on_delete_current_motif
            row2.add_item(btn_del)
            
            btn_back = ui.Button(label="Retour", style=discord.ButtonStyle.secondary, emoji=E_BACK)
            btn_back.callback = self._on_back_to_motifs
            row2.add_item(btn_back)
            container.add_item(row2)
            
        # ================= PAGE : ÉDITION CATÉGORIE MOTIF =================
        elif self.current_page == "motif_edit_cat":
            motif = conf["categories"][self.current_motif_idx]
            container.add_item(ui.TextDisplay(f"### {E_FOLDER} Catégorie pour le motif : {motif['name']}"))
            
            row1 = ui.ActionRow()
            row1.add_item(MotifCategorySelect(self))
            container.add_item(row1)
            
            row2 = ui.ActionRow()
            btn_id_cat = ui.Button(label="Saisir ID", style=discord.ButtonStyle.secondary, emoji=E_ID)
            btn_id_cat.callback = self._open_motif_cat_id_modal
            row2.add_item(btn_id_cat)
            
            btn_disable_cat = ui.Button(label="Désactiver", style=discord.ButtonStyle.danger, emoji=E_OFF)
            btn_disable_cat.callback = self._disable_motif_cat
            row2.add_item(btn_disable_cat)
            
            btn_back = ui.Button(label="Retour", style=discord.ButtonStyle.secondary, emoji=E_BACK)
            btn_back.callback = self._on_back_to_motif_edit
            row2.add_item(btn_back)
            container.add_item(row2)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    async def _refresh(self, interaction: discord.Interaction):
        self._build()
        try:
            if interaction.response.is_done():
                await interaction.edit_original_response(view=self)
            else:
                await interaction.response.edit_message(view=self)
        except Exception as e:
            log_sys("REFRESH_ERR", f"Échec actualisation UI: {e}", is_error=True)

    async def _on_auto_setup(self, interaction: discord.Interaction):
        await interaction.response.defer()
        conf = ticket_db.load(self.guild.id)
        updates = False
        
        try:
            if not conf.get("category_id") or not self.guild.get_channel(conf["category_id"]):
                cat_op = await self.guild.create_category("📁│TICKETS EN COURS")
                conf["category_id"] = cat_op.id
                updates = True
            if not conf.get("archive_id") or not self.guild.get_channel(conf["archive_id"]):
                cat_ar = await self.guild.create_category("🗄️│TICKETS ARCHIVÉS")
                conf["archive_id"] = cat_ar.id
                updates = True
            if not conf.get("support_role_id") or not self.guild.get_role(conf["support_role_id"]):
                role = await self.guild.create_role(name="🛡️│Support", color=discord.Color.red(), hoist=True)
                conf["support_role_id"] = role.id
                updates = True
            if not conf.get("channel_id") or not self.guild.get_channel(conf["channel_id"]):
                chan = await self.guild.create_text_channel("🎫│Tickets", category=None)
                conf["channel_id"] = chan.id
                updates = True
                
            if updates:
                self.status_message = f"{E_ON} Infrastructure manquante générée avec succès."
                ticket_db.save(self.guild.id, conf)
                await self.cog.sync_launcher_message(self.guild, conf)
            else:
                self.status_message = f"{E_ON} L'infrastructure est déjà complète."
        except Exception as e:
            self.status_message = f"{E_OFF} Erreur création infrastructure: {e}"

        await self._refresh(interaction)

    async def _open_id_chan(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TicketChanIdModal(self))
    async def _open_id_role(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TicketRoleIdModal(self))
    async def _open_id_cats(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TicketCatsIdModal(self))

    async def _open_add_motif_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TicketMotifAddModal(self))

    async def _on_delete_current_motif(self, interaction: discord.Interaction):
        await interaction.response.defer()
        conf = ticket_db.load(self.guild.id)
        del conf["categories"][self.current_motif_idx]
        ticket_db.save(self.guild.id, conf)
        
        self.status_message = f"{E_TRASH} Motif supprimé."
        self.current_page = "motifs"
        await self.cog.sync_launcher_message(self.guild, conf)
        await self._refresh(interaction)
        
    async def _on_back_to_motifs(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.current_page = "motifs"
        await self._refresh(interaction)
        
    async def _on_back_to_motif_edit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.current_page = "motif_edit"
        await self._refresh(interaction)

    async def _disable_motif_cat(self, interaction: discord.Interaction):
        await interaction.response.defer()
        conf = ticket_db.load(self.guild.id)
        conf["categories"][self.current_motif_idx]["category_id"] = None
        ticket_db.save(self.guild.id, conf)
        self.status_message = f"{E_ON} Catégorie personnalisée désactivée (Retour par défaut)."
        self.current_page = "motif_edit"
        await self._refresh(interaction)
        
    async def _open_motif_cat_id_modal(self, interaction: discord.Interaction):
        async def callback(inter, target):
            await inter.response.defer(ephemeral=True)
            if isinstance(target, discord.CategoryChannel):
                conf = ticket_db.load(self.guild.id)
                conf["categories"][self.current_motif_idx]["category_id"] = target.id
                ticket_db.save(self.guild.id, conf)
                self.status_message = f"{E_ON} Catégorie liée avec succès."
                self.current_page = "motif_edit"
                await self._refresh(inter)
            else:
                await inter.followup.send(f"{E_OFF} ID invalide (ce n'est pas une catégorie).", ephemeral=True)
        await interaction.response.send_modal(IdModal("category", callback))

    async def _on_toggle_examples(self, interaction: discord.Interaction):
        if not interaction.response.is_done(): await interaction.response.defer()
        conf = ticket_db.load(self.guild.id)
        ex_names = [e["name"] for e in EXEMPLE_DATA]
        
        if any(c["name"] in ex_names for c in conf["categories"]):
            conf["categories"] = [c for c in conf["categories"] if c["name"] not in ex_names]
            self.status_message = f"{E_TRASH} Exemples retirés."
        else:
            for e in EXEMPLE_DATA:
                if not any(c['name'] == e['name'] for c in conf["categories"]):
                    e_copy = e.copy()
                    e_copy["category_id"] = None
                    conf["categories"].append(e_copy)
            self.status_message = f"{E_ON} Exemples ajoutés."
            
        ticket_db.save(self.guild.id, conf)
        await self.cog.sync_launcher_message(self.guild, conf)
        await self._refresh(interaction)

    async def _on_banner_upload(self, interaction: discord.Interaction):
        if not interaction.response.is_done(): await interaction.response.defer()
        
        prompt = await interaction.channel.send(f"📥 {interaction.user.mention}, envoyez l'image (fichier) OU le lien URL (https://) dans ce salon. (Expirera dans 60s)", delete_after=60)
        def check(m): return m.author.id == interaction.user.id
        try:
            msg = await self.cog.bot.wait_for('message', check=check, timeout=60)
            conf = ticket_db.load(self.guild.id)
            
            if msg.attachments:
                conf["custom_banner_url"] = None
                path = ticket_db.get_bg_path(self.guild.id)
                await msg.attachments[0].save(path)
                self.status_message = f"{E_ON} Bannière locale mise à jour."
            elif msg.content.startswith("http"):
                conf["custom_banner_url"] = msg.content.strip()
                bg_path = ticket_db.get_bg_path(self.guild.id)
                if bg_path.exists():
                    try: bg_path.unlink()
                    except: pass
                self.status_message = f"{E_ON} Bannière URL définie."
            else:
                self.status_message = f"{E_OFF} Format invalide (fichier ou URL attendu)."
                
            ticket_db.save(self.guild.id, conf)
            try: await msg.delete()
            except: pass
            try: await prompt.delete()
            except: pass
            
            await self.cog.sync_launcher_message(self.guild, conf)
            await self._refresh(interaction)
        except asyncio.TimeoutError:
            await interaction.channel.send(f"{E_WARN} {interaction.user.mention}, délai écoulé.", delete_after=6)

    async def _force_sync(self, interaction: discord.Interaction):
        if not interaction.response.is_done(): await interaction.response.defer()
        conf = ticket_db.load(self.guild.id)
        await self.cog.sync_launcher_message(self.guild, conf)
        self.status_message = f"{E_ON} Synchronisation forcée du Launcher."
        await self._refresh(interaction)


# ==============================================================================
# --- BUILDERS (Launcher & Ticket Privé) ---
# ==============================================================================
class TicketLauncherBuilder:
    """Builder statique pour générer le LayoutV2 du Launcher public."""
    @staticmethod
    def build(guild: discord.Guild, config: dict, bot: commands.Bot) -> ui.LayoutView:
        view = ui.LayoutView(timeout=None)
        
        accent_color = 0x3498db
        if HAS_VAX_CORE and config_manager:
            try:
                theme = config_manager.get_layout_v2_theme(guild.id, guild, bot.user, bot)
                accent_color = int(theme.get("color", 0x3498db))
            except: pass

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        
        cats = config.get("categories", [])
        title = config.get("custom_title") or f"{E_TICKET} Support - Ouverture de Ticket"
        desc = config.get("custom_description")
        
        if not desc:
            if len(cats) <= 1:
                desc = "Appuyez sur le bouton ci-dessous pour ouvrir un ticket et contacter notre équipe."
            else:
                desc = "Veuillez choisir le motif de votre demande dans le menu ci-dessous pour ouvrir un ticket."
                
        container.add_item(ui.TextDisplay(f"# {title}\n{desc}"))

        # Gestion de l'image (Priorité URL > Local)
        banner_url = config.get("custom_banner_url")
        bg_path = ticket_db.get_bg_path(guild.id)
        
        if banner_url:
            try:
                gallery = ui.MediaGallery()
                gallery.add_item(media=banner_url, description="Bannière Support")
                container.add_item(gallery)
            except Exception: pass
        elif bg_path.exists():
            try:
                gallery = ui.MediaGallery()
                gallery.add_item(media=f"attachment://{bg_path.name}", description="Bannière Support")
                container.add_item(gallery)
            except Exception as e:
                log_sys("GALLERY_ERR", f"Erreur gallery: {e}", is_error=True)

        if len(cats) <= 1:
            row = ui.ActionRow()
            btn = ui.Button(label="Ouvrir un ticket", style=discord.ButtonStyle.primary, emoji=E_TICKET, custom_id="tkt_launch_btn_open")
            row.add_item(btn)
            container.add_item(row)
        else:
            row = ui.ActionRow()
            options = []
            for c in cats[:25]:
                opt = discord.SelectOption(
                    label=c['name'][:90],
                    description=c.get("desc", "Cliquez pour ouvrir ce ticket")[:100],
                    value=c["name"]
                )
                options.append(opt)
                
            select = ui.Select(placeholder="Choisissez le motif de votre demande...", options=options, custom_id="tkt_launch_sel_open")
            row.add_item(select)
            container.add_item(row)

        view.add_item(container)
        return view

class TicketPrivateBuilder:
    """Builder statique pour générer le LayoutV2 à l'intérieur d'un ticket."""
    @staticmethod
    def build(guild: discord.Guild, bot: commands.Bot, owner: discord.Member, category: str, description: str, ticket_num: int, is_closed: bool = False) -> ui.LayoutView:
        view = ui.LayoutView(timeout=None)
        
        accent_color = 0x95a5a6 if is_closed else 0x2ecc71
        if HAS_VAX_CORE and config_manager and not is_closed:
            try:
                theme = config_manager.get_layout_v2_theme(guild.id, guild, bot.user, bot)
                accent_color = int(theme.get("color", 0x2ecc71))
            except: pass

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        status_txt = f"{E_LOCK} **FERMÉ**" if is_closed else f"{E_SUPPORT} **EN COURS**"
        
        main_text = (
            f"# {E_TICKET} Ticket n°{ticket_num}\n"
            f"{status_txt}\n\n"
            f"**Propriétaire :** {owner.mention if owner else '`Introuvable`'}\n"
            f"**Sujet :** `{category}`\n\n"
            f"**Description :**\n```\n{description}\n```"
        )
        
        if owner and hasattr(owner, 'display_avatar'):
            try:
                container.add_item(ui.Section(main_text, accessory=ui.Thumbnail(owner.display_avatar.url, description="Avatar")))
            except:
                container.add_item(ui.TextDisplay(main_text))
        else:
            container.add_item(ui.TextDisplay(main_text))

        row = ui.ActionRow()
        if is_closed:
            btn_reopen = ui.Button(label="Réouvrir", style=discord.ButtonStyle.success, emoji=E_UNLOCK, custom_id="tkt_priv_btn_reopen")
            row.add_item(btn_reopen)
            btn_delete = ui.Button(label="Supprimer Définitivement", style=discord.ButtonStyle.danger, emoji=E_TRASH, custom_id="tkt_priv_btn_delete")
            row.add_item(btn_delete)
        else:
            btn_close = ui.Button(label="Clôturer", style=discord.ButtonStyle.danger, emoji=E_LOCK, custom_id="tkt_priv_btn_close")
            row.add_item(btn_close)

        container.add_item(row)
        view.add_item(container)
        return view


# ==============================================================================
# --- COG PRINCIPAL (Intercepteur, Tâches et Logique) ---
# ==============================================================================
class TicketCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log_sys("INIT", "Module Tickets V3 déployé.")

    # --- SYNCHRONISATION DU LAUNCHER ---
    async def sync_launcher_message(self, guild: discord.Guild, config: dict):
        chan = guild.get_channel(config.get("channel_id"))
        if not chan: return

        view = TicketLauncherBuilder.build(guild, config, self.bot)
        
        files = []
        if not config.get("custom_banner_url"):
            bg_path = ticket_db.get_bg_path(guild.id)
            if bg_path.exists():
                files.append(discord.File(bg_path, filename=bg_path.name))

        old_msg_id = config.get("msg_id")
        if old_msg_id:
            try:
                msg = await chan.fetch_message(old_msg_id)
                await msg.edit(view=view, attachments=files)
                return
            except discord.NotFound: pass
            except Exception as e: log_sys("SYNC_ERR", f"Erreur fetch message: {e}", is_error=True)

        try:
            new_msg = await chan.send(files=files, view=view)
            config["msg_id"] = new_msg.id
            ticket_db.save(guild.id, config)
        except discord.Forbidden:
            log_sys("PERM_ERR", f"Impossible d'envoyer le launcher dans le salon {chan.id}")

    # --- PROCESSUS MÉTIER TICKET ---
    async def create_ticket_process(self, interaction: discord.Interaction, category_name: str, description: str):
        guild = interaction.guild
        user = interaction.user
        config = ticket_db.load(guild.id)
        
        ticket_count = config.get("ticket_count", 0) + 1
        config["ticket_count"] = ticket_count 
        ticket_db.save(guild.id, config)
        
        safe_name = re.sub(r'[^a-zA-Z0-9]', '-', user.name.lower())
        channel_name = f"tkt-{ticket_count:04d}-{safe_name}"
        
        support_role = guild.get_role(config.get("support_role_id"))
        
        cat_custom_id = next((c.get("category_id") for c in config.get("categories", []) if c["name"] == category_name), None)
        category_discord = guild.get_channel(cat_custom_id) if cat_custom_id else guild.get_channel(config.get("category_id"))

        # Sécurisation : On force la création même sans catégorie, avec des perms blindées
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True, manage_permissions=True, manage_messages=True)
        }
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True)

        try:
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category_discord,
                overwrites=overwrites,
                topic=f"OwnerID:{user.id} | Status:Open | Cat:{category_name} | Num:{ticket_count} | Desc:-"
            )

            notification_msg = f"{user.mention}"
            if support_role: notification_msg += f" | {support_role.mention}"

            view = TicketPrivateBuilder.build(guild, self.bot, user, category_name, description, ticket_count, is_closed=False)
            await channel.send(content=notification_msg, view=view)
            return channel
        except Exception as e:
            log_sys("CREATE_ERR", f"Erreur de génération du salon ticket: {e}", is_error=True)
            return None

    def _parse_ticket_topic(self, topic: str):
        data = {"owner_id": None, "status": "Open", "cat": "Général", "num": 0}
        if not topic: return data
        parts = topic.split(" | ")
        for p in parts:
            if ":" not in p: continue
            k, v = p.split(":", 1)
            k, v = k.strip(), v.strip()
            if k == "OwnerID" and v.isdigit(): data["owner_id"] = int(v)
            elif k == "Status": data["status"] = v
            elif k == "Cat": data["cat"] = v
            elif k == "Num" and v.isdigit(): data["num"] = int(v)
        return data

    async def close_ticket_process(self, interaction: discord.Interaction):
        config = ticket_db.load(interaction.guild.id)
        topic_data = self._parse_ticket_topic(interaction.channel.topic)
        
        owner_id = topic_data.get("owner_id")
        if not owner_id:
            return await interaction.channel.send(f"{E_OFF} Méta-données introuvables.", delete_after=6)

        owner = interaction.guild.get_member(owner_id)
        overwrites = interaction.channel.overwrites
        if owner in overwrites:
            del overwrites[owner]
        
        cat_archive = interaction.guild.get_channel(config.get("archive_id"))
        if not cat_archive:
            return await interaction.channel.send(f"{E_OFF} Catégorie d'archives introuvable.", delete_after=6)

        try:
            new_topic = interaction.channel.topic.replace("Status:Open", "Status:Closed")
            await interaction.channel.edit(category=cat_archive, overwrites=overwrites, topic=new_topic)
            
            desc = "*(Description archivée)*"
            if interaction.message.embeds:
                desc = interaction.message.embeds[0].description.split("```")[1] if "```" in interaction.message.embeds[0].description else desc

            view = TicketPrivateBuilder.build(interaction.guild, self.bot, owner, topic_data["cat"], desc, topic_data["num"], is_closed=True)
            await interaction.message.edit(view=view)
            
            await interaction.channel.send(f"{E_LOCK} Ticket clôturé et archivé par {interaction.user.mention}.")
        except Exception as e:
            log_sys("CLOSE_ERR", f"Erreur de clôture: {e}", is_error=True)

    async def reopen_ticket_process(self, interaction: discord.Interaction, owner_id: int, reason: str):
        config = ticket_db.load(interaction.guild.id)
        topic_data = self._parse_ticket_topic(interaction.channel.topic)
        owner = interaction.guild.get_member(owner_id)
        
        if not owner:
            return await interaction.channel.send(f"{E_OFF} L'utilisateur a quitté le serveur.", delete_after=6)

        overwrites = interaction.channel.overwrites
        overwrites[owner] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True, embed_links=True)
        
        cat_custom_id = next((c.get("category_id") for c in config.get("categories", []) if c["name"] == topic_data["cat"]), None)
        cat_open = interaction.guild.get_channel(cat_custom_id) if cat_custom_id else interaction.guild.get_channel(config.get("category_id"))
        
        try:
            new_topic = interaction.channel.topic.replace("Status:Closed", "Status:Open")
            await interaction.channel.edit(category=cat_open, overwrites=overwrites, topic=new_topic)
            
            desc = "*(Description archivée)*"
            if interaction.message.embeds and "```" in interaction.message.embeds[0].description:
                desc = interaction.message.embeds[0].description.split("```")[1]

            view = TicketPrivateBuilder.build(interaction.guild, self.bot, owner, topic_data["cat"], desc, topic_data["num"], is_closed=False)
            await interaction.message.edit(view=view)
            
            await interaction.channel.send(f"{E_UNLOCK} **Ticket réouvert** par {interaction.user.mention}\n**Motif :** `{reason}`\n{owner.mention} le support est de retour.")
        except Exception as e:
            log_sys("REOPEN_ERR", f"Erreur de réouverture: {e}", is_error=True)

    # --- INTERCEPTEUR GLOBAL PERSISTANT (REBOOT-PROOF) ---
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component: return
        custom_id = interaction.data.get("custom_id", "")
        
        if custom_id.startswith("tkt_launch_"):
            if custom_id == "tkt_launch_btn_open":
                conf = ticket_db.load(interaction.guild.id)
                cat_name = conf["categories"][0]["name"] if conf.get("categories") else GEN_NAME
                await interaction.response.send_modal(TicketCreationModal(self, cat_name))
            elif custom_id == "tkt_launch_sel_open":
                cat_name = interaction.data.get("values", [GEN_NAME])[0]
                await interaction.response.send_modal(TicketCreationModal(self, cat_name))

        elif custom_id.startswith("tkt_priv_"):
            if custom_id == "tkt_priv_btn_close":
                if not interaction.response.is_done(): await interaction.response.defer()
                await self.close_ticket_process(interaction)
            elif custom_id == "tkt_priv_btn_reopen":
                topic_data = self._parse_ticket_topic(interaction.channel.topic)
                if topic_data["owner_id"]:
                    await interaction.response.send_modal(TicketReopenModal(self, topic_data["owner_id"]))
                else:
                    if not interaction.response.is_done(): await interaction.response.defer(ephemeral=True)
                    await interaction.followup.send(f"{E_OFF} Méta-données corrompues.", ephemeral=True)
            elif custom_id == "tkt_priv_btn_delete":
                if not interaction.response.is_done(): await interaction.response.defer()
                await interaction.channel.send(f"{E_TRASH} Autodestruction initiée par {interaction.user.mention}...")
                await asyncio.sleep(3)
                try: await interaction.channel.delete()
                except: pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild: return
        if not message.channel.name or not message.channel.name.startswith("tkt-"): return

        topic = message.channel.topic or ""
        if "OwnerID:" not in topic: return 

        cfg = ticket_db.load(message.guild.id)
        support_role_id = cfg.get("support_role_id")
        
        if support_role_id and any(role.id == support_role_id for role in message.author.roles):
            if " | Répondu" not in topic:
                wait_time = (message.created_at.timestamp() - message.channel.created_at.timestamp()) / 60
                stats = cfg.setdefault("stats", {"total_wait_time": 0, "total_answered": 0})
                stats["total_wait_time"] += wait_time
                stats["total_answered"] += 1
                ticket_db.save(message.guild.id, cfg)
                try: await message.channel.edit(topic=f"{topic} | Répondu")
                except: pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        cfg = ticket_db.load(member.guild.id)
        cat_ids = [cfg.get("category_id")] + [c.get("category_id") for c in cfg.get("categories", [])]
        for cat_id in set(filter(None, cat_ids)):
            cat_op = member.guild.get_channel(cat_id)
            if cat_op:
                safe_name = re.sub(r'[^a-zA-Z0-9]', '-', member.name.lower())
                suffix = f"-{safe_name}"
                for chan in cat_op.text_channels:
                    if chan.name.endswith(suffix):
                        try: await chan.delete(reason="L'utilisateur a quitté le serveur.")
                        except: pass

    @perm_command(level=2)
    @commands.hybrid_command(name="ticket", description="Ouvre le panneau de configuration des tickets.")
    async def ticket_cmd(self, ctx: commands.Context):
        if not ctx.guild: return await ctx.send(f"{E_OFF} Commande de serveur.")
        if HAS_VAX_CORE:
            if not await ensure_command_permission(ctx, command_name="ticket"): return
        else:
            if not ctx.author.guild_permissions.administrator: return await ctx.send(f"{E_OFF} Permissions insuffisantes.")
            
        log_sys("CMD_INVOKE", f"Console /ticket invoquée par {ctx.author.name}")
        view = TicketAdminLayoutView(self, ctx.guild, ctx.author)
        await ctx.send(view=view)

async def setup(bot: commands.Bot):
    if bot.get_command("ticket"): bot.remove_command("ticket")
    await bot.add_cog(TicketCog(bot))