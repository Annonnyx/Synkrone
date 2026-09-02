import discord
from discord import ui, app_commands
from discord.ext import commands, tasks
from datetime import datetime, timezone
import re
import unicodedata
import traceback
import time
import asyncio
from typing import Optional

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
# Variables de contrôle d'exécution pour la console experte.
# ==============================================================================
DEBUG_LOGS = True
ERROR_LOGS_ONLY = False

# ==============================================================================
# --- CENTRALISATION DES EMOJIS ---
# Mappage dynamique depuis le module Emoji officiel avec fallbacks.
# ==============================================================================
E_ON = getattr(E, 'VALIDER', "🟢") if HAS_VAX_CORE else "🟢"
E_OFF = getattr(E, 'REFUSER', "🔴") if HAS_VAX_CORE else "🔴"
E_WARN = getattr(E, 'ATTENTION', "⚠️") if HAS_VAX_CORE else "⚠️"
E_GEAR = getattr(E, 'MODIFIER', "⚙️") if HAS_VAX_CORE else "⚙️"
E_ROBOT = getattr(E, 'VAX', "🤖") if HAS_VAX_CORE else "🤖"
E_USER = getattr(E, 'PROFIL', "👤") if HAS_VAX_CORE else "👤"
E_TIME = getattr(E, 'TEMPS', "⏳") if HAS_VAX_CORE else "⏳"
E_CAL = getattr(E, 'HISTOIRE', "📅") if HAS_VAX_CORE else "📅"
E_CROWN = getattr(E, 'OWNER', "👑") if HAS_VAX_CORE else "👑"
E_SHIELD = getattr(E, 'BOUCLIER', "🛡️") if HAS_VAX_CORE else "🛡️"
E_LINK = getattr(E, 'LIEN', "🔗") if HAS_VAX_CORE else "🔗"
E_WEB = getattr(E, 'MONDE', "🌐") if HAS_VAX_CORE else "🌐"
E_ADD = getattr(E, 'AJOUTER', "➕") if HAS_VAX_CORE else "➕"
E_EDIT = getattr(E, 'MODIFIER', "✏️") if HAS_VAX_CORE else "✏️"
E_RELOAD = getattr(E, 'RAFRAICHIR', "🔄") if HAS_VAX_CORE else "🔄"
E_BACK = getattr(E, 'RETOUR', "↩️") if HAS_VAX_CORE else "↩️"
E_ID = getattr(E, 'IDENTIFIANT', "🆔") if HAS_VAX_CORE else "🆔"
E_TOOLS = getattr(E, 'PARAMETRES', "🛠️") if HAS_VAX_CORE else "🛠️"
E_ROLE = getattr(E, 'ROLE', "🎭") if HAS_VAX_CORE else "🎭"
E_ARROW = getattr(E, 'FLECHE_DROITE', "➡️") if HAS_VAX_CORE else "➡️"
E_TARGET = getattr(E, 'CIBLE', "🎯") if HAS_VAX_CORE else "🎯"
E_EYE = getattr(E, 'RECHERCHE', "👁️") if HAS_VAX_CORE else "👁️"

# ==============================================================================
# --- UTILITAIRES DE LOGS ---
# ==============================================================================
def log_sys(action: str, message: str, is_error: bool = False):
    """Console experte avec colorisation ANSI obéissant aux filtres globaux."""
    if ERROR_LOGS_ONLY and not is_error:
        return
    if not DEBUG_LOGS and not is_error:
        return

    COLOR_RESET = "\033[0m"
    COLOR_INFO = "\033[96m"   # Cyan
    COLOR_SUCCESS = "\033[92m" # Vert
    COLOR_ERROR = "\033[91m"   # Rouge

    color = COLOR_ERROR if is_error else COLOR_INFO
    prefix = "[ERREUR AutoRole]" if is_error else "[INFO AutoRole]"
    print(f"{color}{prefix} [{action}] {message}{COLOR_RESET}")

# ==============================================================================
# --- GESTIONNAIRE DE DONNÉES (DataManager) ---
# ==============================================================================
class AutoRoleManager:
    """Interface de sauvegarde s'appuyant sur l'infrastructure standard."""
    def __init__(self):
        if HAS_VAX_CORE:
            self.data = DataManager("staff/configuration/data_autorole")
        else:
            log_sys("INIT", "DataManager introuvable. Échec système.", is_error=True)

    def load(self, guild_id: int) -> dict:
        try:
            raw = self.data.load(guild_id) or {}
            if "enabled_features" not in raw: raw["enabled_features"] = []
            if "roles" not in raw: raw["roles"] = {}
            if "settings" not in raw: raw["settings"] = {"discord_url": "", "site_url": "", "forced_tag": ""}
            return raw
        except Exception as e:
            log_sys("DB_LOAD", f"Erreur de lecture DB pour {guild_id}: {e}", is_error=True)
            return {"enabled_features": [], "roles": {}, "settings": {"discord_url": "", "site_url": "", "forced_tag": ""}}

    def save(self, guild_id: int, config: dict):
        try:
            self.data.save(guild_id, config)
        except Exception as e:
            log_sys("DB_SAVE", f"Erreur d'écriture DB pour {guild_id}: {e}", is_error=True)

autorole_db = AutoRoleManager()

FEATURES_DEF = {
    "bot": {"label": "Bots", "emoji": E_ROBOT, "cat": "base", "color": 0x7289da, "admin": True, "default_name": "Bots"},
    "membre": {"label": "Membres", "emoji": E_USER, "cat": "base", "color": 0x95a5a6, "admin": False, "default_name": "Membres"},
    "1_mois": {"label": "1 Mois", "emoji": E_TIME, "cat": "time", "color": 0x3498db, "days": 30, "default_name": "Ancien : 1 Mois"},
    "3_mois": {"label": "3 Mois", "emoji": E_TIME, "cat": "time", "color": 0x2ecc71, "days": 90, "default_name": "Ancien : 3 Mois"},
    "6_mois": {"label": "6 Mois", "emoji": E_TIME, "cat": "time", "color": 0x1abc9c, "days": 180, "default_name": "Ancien : 6 Mois"},
    "9_mois": {"label": "9 Mois", "emoji": E_TIME, "cat": "time", "color": 0x9b59b6, "days": 270, "default_name": "Ancien : 9 Mois"},
    "1_an": {"label": "1 An", "emoji": E_CAL, "cat": "time", "color": 0xf1c40f, "days": 365, "default_name": "Vétéran : 1 An"},
    "2_ans": {"label": "2 Ans", "emoji": E_CAL, "cat": "time", "color": 0xe67e22, "days": 730, "default_name": "Vétéran : 2 Ans"},
    "3_ans": {"label": "3 Ans", "emoji": E_CAL, "cat": "time", "color": 0xe74c3c, "days": 1095, "default_name": "Légende : 3 Ans"},
    "5_ans": {"label": "5 Ans et +", "emoji": E_CROWN, "cat": "time", "color": 0xad1457, "days": 1825, "default_name": "Immortel : 5 Ans +"},
    "guild_tag": {"label": "Tag de Guilde/Clan", "emoji": E_SHIELD, "cat": "presence", "color": 0x1abc9c, "default_name": "Membre du Clan"},
    "discord_url": {"label": "Soutien Discord", "emoji": E_LINK, "cat": "presence", "color": 0x5865F2, "default_name": "Supporteur Discord"},
    "site_url": {"label": "Soutien Web", "emoji": E_WEB, "cat": "presence", "color": 0x2ecc71, "default_name": "Supporteur Web"}
}

# ==============================================================================
# --- MODALS UTILISATEUR ---
# ==============================================================================
class KeywordConfigModal(ui.Modal, title="Filtres Textuels"):
    def __init__(self, view: "AutoRoleLayoutView"):
        super().__init__()
        self.view = view
        settings = autorole_db.load(self.view.guild.id).get("settings", {})

        self.tag_input = ui.TextInput(
            label="Tag de Guilde (Option Alternative)", default=settings.get("forced_tag", ""), 
            placeholder="Ex: Synk", required=False
        )
        self.discord_input = ui.TextInput(
            label="Lien Discord (Soutien)", default=settings.get("discord_url", ""), 
            placeholder="Ex: .gg/synk", required=False
        )
        self.site_input = ui.TextInput(
            label="Lien Site Web (Soutien)", default=settings.get("site_url", ""), 
            placeholder="Ex: synk.fr", required=False
        )

        self.add_item(self.tag_input)
        self.add_item(self.discord_input)
        self.add_item(self.site_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        gid = self.view.guild.id
        config = autorole_db.load(gid)
        config["settings"]["forced_tag"] = self.tag_input.value.strip()
        config["settings"]["discord_url"] = self.discord_input.value.strip()
        config["settings"]["site_url"] = self.site_input.value.strip()
        autorole_db.save(gid, config)
        
        self.view.state = "syncing"
        self.view.sync_text = "Calcul des modifications..."
        await self.view._refresh(interaction)

        await self.view.cog.sync_with_progress(self.view.guild, self.view)
        
        self.view.status_message = f"{E_ON} Les tags et liens de soutien ont été mis à jour."
        self.view.state = "main"
        self.view.active_sub_menu = None
        await self.view._refresh()

# ==============================================================================
# --- SELECTEURS D'OPTIONS (Layout V2) ---
# ==============================================================================
class AutoRoleOptionsSelect(ui.Select):
    def __init__(self, parent_view: "AutoRoleLayoutView"):
        self.parent_view = parent_view
        options = []
        
        if not self.parent_view.show_roles:
            options.append(discord.SelectOption(label="Afficher les rôles", value="show_roles", emoji=E_EYE, description="Rendre visible les mentions de rôles"))
            
        options.extend([
            discord.SelectOption(label="Gérer les modules", value="modules", emoji=E_GEAR, description="Activer ou désactiver des rôles automatiques"),
            discord.SelectOption(label="Lier un rôle manuel", value="bind_feature", emoji=E_ROLE, description="Associer un rôle existant du serveur"),
            discord.SelectOption(label="Filtres & Tags", value="filters", emoji=E_EDIT, description="Configurer le tag de clan et les liens de soutien"),
            discord.SelectOption(label="Créer/Initialiser", value="init", emoji=E_TOOLS, description="Créer automatiquement les rôles manquants"),
            discord.SelectOption(label="Forcer le Scan", value="scan", emoji=E_RELOAD, description="Actualiser tous les membres immédiatement"),
        ])
        super().__init__(placeholder="Options de configuration...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val == "show_roles":
            self.parent_view.show_roles = True
            await self.parent_view._refresh(interaction)
        elif val == "modules":
            self.parent_view.active_sub_menu = "modules"
            await self.parent_view._refresh(interaction)
        elif val == "bind_feature":
            self.parent_view.active_sub_menu = "bind_feature"
            await self.parent_view._refresh(interaction)
        elif val == "filters":
            await self.parent_view._open_filters_modal(interaction)
        elif val == "init":
            await self.parent_view._initialize_roles(interaction)
        elif val == "scan":
            await self.parent_view._force_scan(interaction)


# ==============================================================================
# --- INTERFACE UTILISATEUR (Layout V2) ---
# ==============================================================================
class AutoRoleLayoutView(ui.LayoutView):
    """Machine à états UI V2 pour la configuration des Rôles Automatiques."""
    def __init__(self, cog: "AutoRoleCog", guild: discord.Guild, user: discord.Member):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild = guild
        self.user = user
        
        self.message = None
        self.show_roles = False
        self.status_message = ""
        self.active_sub_menu: str | None = None
        self.bind_target_feature: str | None = None
        
        # Variables de Progression (Mode Syncing)
        self.state = "main" # 'main', 'bind_role', 'syncing'
        self.sync_total = 0
        self.sync_progress = 0
        self.sync_text = ""
        
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            if not interaction.response.is_done(): await interaction.response.defer()
            await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, cette interface est verrouillée.", delete_after=6)
            return False
        return True

    def _build(self):
        """Reconstruction architecturale complète du composant V2."""
        self.clear_items()
        
        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.cog.bot)
        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text", "")

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        
        if self.status_message:
            container.add_item(ui.TextDisplay(f"> {self.status_message}"))
            self.status_message = ""

        if self.state == "syncing":
            self._build_syncing(container)
        elif self.state == "bind_role":
            self._build_role_bind(container)
        else:
            self._build_main(container)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    async def _refresh(self, interaction: discord.Interaction = None):
        """Rafraîchissement centralisé supportant la boucle de progression asynchrone."""
        self._build()
        try:
            if interaction:
                if interaction.response.is_done():
                    await interaction.edit_original_response(view=self)
                else:
                    await interaction.response.edit_message(view=self)
            elif self.message:
                await self.message.edit(view=self)
        except Exception:
            pass

    def _build_syncing(self, container: ui.Container):
        container.add_item(ui.TextDisplay(f"# {E_RELOAD} Déploiement en cours..."))
        
        pct = 100
        if self.sync_total > 0:
            pct = int((self.sync_progress / self.sync_total) * 100)
            
        bar_len = 20
        filled = int((pct / 100) * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)
        
        container.add_item(ui.TextDisplay(
            f"**Progression globale :** {pct}% `[{bar}]` ({self.sync_progress}/{self.sync_total})\n\n"
            f"> {self.sync_text}"
        ))

    def _build_main(self, container: ui.Container):
        config = autorole_db.load(self.guild.id)
        counts = self.cog.calculate_eligible_counts(self.guild, config)

        container.add_item(ui.TextDisplay(f"# {E_GEAR} Configuration AutoRole"))
        container.add_item(ui.TextDisplay(f"Gestion globale en temps réel.\n"))

        categories = {
            "base": f"{E_USER} Structure de Base", 
            "time": f"{E_TIME} Récompenses d'Ancienneté", 
            "presence": f"{E_TARGET} Soutien"
        }

        # Construction de l'affichage par blocs
        for cat_key, cat_name in categories.items():
            lines = []
            for f_key, f_info in FEATURES_DEF.items():
                if f_info["cat"] == cat_key:
                    is_active = f_key in config["enabled_features"]
                    role_id = config["roles"].get(f_key)
                    role_obj = self.guild.get_role(int(role_id)) if role_id and str(role_id).isdigit() else None
                    
                    # Logique de visibilité pour éviter les pings
                    if self.show_roles:
                        r_mention = f" : {role_obj.mention}" if role_obj else " : *Aucun rôle lié*"
                    else:
                        r_mention = ""
                    
                    extra = ""
                    if cat_key == "presence":
                        if f_key == "guild_tag":
                            kw = config["settings"].get("forced_tag", "")
                        else:
                            kw = config["settings"].get(f_key, "")
                        extra = f" {E_ARROW} `{kw}`" if kw else f" {E_ARROW} {E_WARN} *Non configuré*"

                    status = E_ON if is_active else E_OFF
                    lines.append(f"{status} **[{counts.get(f_key, 0)}]** {f_info['emoji']} **{f_info['label']}**{r_mention}{extra}")
            
            if lines:
                container.add_item(ui.TextDisplay(f"### {cat_name}\n" + "\n".join(lines)))

        # Ligne Principale : Sélecteur d'options
        row_main = ui.ActionRow()
        row_main.add_item(AutoRoleOptionsSelect(self))
        container.add_item(row_main)

        # Sous-menus dynamiques
        if self.active_sub_menu == "modules":
            active = config.get("enabled_features", [])
            toggle_opts = [discord.SelectOption(label=fi["label"], value=fk, default=(fk in active), emoji=fi["emoji"]) for fk, fi in FEATURES_DEF.items()]
            
            toggle_row = ui.ActionRow()
            toggle_select = ui.Select(placeholder="Activer / Désactiver les modules", min_values=0, max_values=len(toggle_opts), options=toggle_opts[:25])
            toggle_select.callback = self._on_module_toggle
            toggle_row.add_item(toggle_select)
            container.add_item(toggle_row)
            
        elif self.active_sub_menu == "bind_feature":
            bind_opts = [discord.SelectOption(label=f"Lier : {fi['label']}", value=fk, emoji=fi["emoji"]) for fk, fi in FEATURES_DEF.items()]
            
            bind_row = ui.ActionRow()
            bind_select = ui.Select(placeholder="Choisir la catégorie à lier...", options=bind_opts[:25])
            bind_select.callback = self._on_bind_select
            bind_row.add_item(bind_select)
            container.add_item(bind_row)

    def _build_role_bind(self, container: ui.Container):
        f_info = FEATURES_DEF[self.bind_target_feature]
        container.add_item(ui.TextDisplay(f"# {E_ROLE} Liaison : {f_info['label']}"))
        container.add_item(ui.TextDisplay(f"Choisissez le rôle du serveur à associer pour le module **{f_info['label']}**."))

        role_row = ui.ActionRow()
        role_select = ui.RoleSelect(placeholder="Choisissez le rôle dans la liste...", min_values=1, max_values=1)
        role_select.callback = self._on_role_selected
        role_row.add_item(role_select)
        container.add_item(role_row)

        nav_row = ui.ActionRow()
        btn_back = ui.Button(label="Retour", style=discord.ButtonStyle.secondary, emoji=E_BACK)
        btn_back.callback = self._on_back_main
        nav_row.add_item(btn_back)
        container.add_item(nav_row)

    # --- CALLBACKS UI ---
    async def _on_back_main(self, interaction: discord.Interaction):
        self.active_sub_menu = None
        self.bind_target_feature = None
        await self._refresh(interaction)

    async def _on_module_toggle(self, interaction: discord.Interaction):
        await interaction.response.defer()
        config = autorole_db.load(self.guild.id)
        config["enabled_features"] = interaction.data.get('values', [])
        autorole_db.save(self.guild.id, config)
        
        self.state = "syncing"
        self.sync_text = "Calcul des modifications..."
        await self._refresh(interaction)

        await self.cog.sync_with_progress(self.guild, self)

        self.status_message = f"{E_ON} Les modules actifs ont été mis à jour."
        self.active_sub_menu = None
        self.state = "main"
        await self._refresh()

    async def _on_bind_select(self, interaction: discord.Interaction):
        self.bind_target_feature = interaction.data.get('values', [None])[0]
        self.active_sub_menu = "bind_role"
        self.state = "bind_role"
        await self._refresh(interaction)

    async def _on_role_selected(self, interaction: discord.Interaction):
        role_id = interaction.data.get('values', [None])[0]
        role = self.guild.get_role(int(role_id))
        
        bot_member = self.guild.get_member(self.cog.bot.user.id)
        if bot_member and role and role.position >= bot_member.top_role.position:
            self.status_message = f"{E_OFF} Erreur : La position hiérarchique de ce rôle est supérieure à celle du bot."
            self.state = "main"
            await self._refresh(interaction)
            return

        config = autorole_db.load(self.guild.id)
        config["roles"][self.bind_target_feature] = str(role_id)
        autorole_db.save(self.guild.id, config)
        
        await interaction.response.defer()
        self.state = "syncing"
        self.sync_text = "Calcul des tâches..."
        await self._refresh(interaction)

        await self.cog.sync_with_progress(self.guild, self)

        self.status_message = f"{E_ON} Le rôle a bien été lié à la fonctionnalité."
        self.state = "main"
        self.active_sub_menu = None
        self.bind_target_feature = None
        await self._refresh()

    async def _open_filters_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(KeywordConfigModal(self))

    async def _initialize_roles(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.state = "syncing"
        self.sync_text = "Création des rôles manquants..."
        await self._refresh(interaction)
            
        config = autorole_db.load(self.guild.id)
        creations = 0
        for f_key in FEATURES_DEF.keys():
            r_id = config["roles"].get(f_key)
            role_obj = self.guild.get_role(int(r_id)) if r_id and str(r_id).isdigit() else None
            
            if not role_obj:
                await self.cog.ensure_role_exists(self.guild, f_key)
                creations += 1
                
        self.sync_text = "Calcul des affectations..."
        await self._refresh()
        await self.cog.sync_with_progress(self.guild, self)
        
        self.status_message = f"{E_ON} Infrastructure mise à jour : **{creations}** rôles générés et configurés."
        self.active_sub_menu = None
        self.state = "main"
        await self._refresh()

    async def _force_scan(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.state = "syncing"
        self.sync_text = "Calcul des tâches requises..."
        await self._refresh(interaction)
            
        await self.cog.sync_with_progress(self.guild, self)
        
        self.status_message = f"{E_ON} Le scan complet des membres a été effectué."
        self.active_sub_menu = None
        self.state = "main"
        await self._refresh()


# ==============================================================================
# --- COG PRINCIPAL ---
# ==============================================================================
class AutoRoleCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log_sys("INIT", "Module AutoRole déployé.")

    async def cog_load(self):
        self.check_all_roles.start()

    async def cog_unload(self):
        self.check_all_roles.cancel()

    def normalize_text(self, text: str) -> str:
        if not text: return ""
        return unicodedata.normalize('NFKC', text).lower().strip()

    def resolve_expected_tag(self, guild: discord.Guild, data: dict) -> str:
        settings = data.get("settings", {})
        if settings.get("forced_tag"):
            return self.normalize_text(settings["forced_tag"])

        if hasattr(guild, 'clan') and guild.clan and getattr(guild.clan, 'tag', None):
            return self.normalize_text(guild.clan.tag)

        match = re.search(r'[\[\(\{](.*?)[\]\)\}]|^(\w+)\s*[\|\]\-]', guild.name)
        if match:
            return self.normalize_text(match.group(1) or match.group(2))

        return self.normalize_text(guild.name[:4])

    def check_member_tag(self, member: discord.Member, target_tag: str) -> bool:
        if not target_tag: return False

        if hasattr(member, 'clan') and member.clan and getattr(member.clan, 'tag', None):
            if self.normalize_text(member.clan.tag) == target_tag:
                return True

        display_name = self.normalize_text(member.display_name)
        username = self.normalize_text(member.name)
        
        patterns = [
            rf"\b{re.escape(target_tag)}\b",
            rf"\[{re.escape(target_tag)}\]",
            rf"\({re.escape(target_tag)}\)",
            rf"\{{{re.escape(target_tag)}\}}",
            rf"^{re.escape(target_tag)}\s*[\|•\-]",
        ]
        
        for pattern in patterns:
            if re.search(pattern, display_name) or re.search(pattern, username):
                return True
                
        return target_tag in display_name or target_tag in username

    def check_support_status(self, member: discord.Member, keyword: str) -> bool:
        if not keyword: return False
        kw = keyword.lower().strip()

        for activity in member.activities:
            if isinstance(activity, discord.CustomActivity):
                state = self.normalize_text(getattr(activity, 'state', ''))
                name = self.normalize_text(getattr(activity, 'name', ''))
                if kw in state or kw in name:
                    return True
        return False

    async def ensure_role_exists(self, guild: discord.Guild, f_key: str) -> discord.Role:
        data = autorole_db.load(guild.id)
        current_id = data["roles"].get(f_key)
        
        role = guild.get_role(int(current_id)) if current_id and str(current_id).isdigit() else None
        
        if not role:
            f_info = FEATURES_DEF[f_key]
            perms = discord.Permissions(administrator=True) if f_info.get("admin") else discord.Permissions.none()
            
            role_name = f"{f_info['default_name']}"
            if f_key == "guild_tag" and data["settings"].get("forced_tag"):
                role_name = f"🛡️ Clan [{data['settings']['forced_tag'].upper()}]"

            try:
                role = await guild.create_role(
                    name=role_name,
                    color=discord.Color(f_info["color"]),
                    hoist=True,
                    permissions=perms,
                    reason="AutoRole : Initialisation de l'infrastructure"
                )
                data["roles"][f_key] = str(role.id)
                autorole_db.save(guild.id, data)
                log_sys("ROLE_CREATED", f"Rôle {f_key} généré sur le serveur {guild.id}.")
            except discord.Forbidden:
                log_sys("PERM_ERROR", f"Permissions insuffisantes pour créer le rôle {f_key} sur {guild.name}", is_error=True)
                return None
        return role

    async def sync_with_progress(self, guild: discord.Guild, view: AutoRoleLayoutView):
        """Méthode dédiée à la mise à jour visuelle des rôles de l'entièreté de la guilde."""
        data = autorole_db.load(guild.id)
        target_tag = self.resolve_expected_tag(guild, data)

        now = datetime.now(timezone.utc)
        feats = data.get("enabled_features", [])
        settings = data.get("settings", {})
        
        bot_member = guild.get_member(self.bot.user.id)
        top_pos = bot_member.top_role.position if bot_member else 0

        tasks_list = []
        for member in guild.members:
            added_roles = set()
            removed_roles = set()
            for f_key, f_info in FEATURES_DEF.items():
                r_id = data["roles"].get(f_key)
                role = guild.get_role(int(r_id)) if r_id and str(r_id).isdigit() else None
                if not role: continue

                should_have_role = False
                if f_key in feats:
                    if f_info["cat"] == "base":
                        if (f_key == "bot" and member.bot) or (f_key == "membre" and not member.bot):
                            should_have_role = True
                    elif f_info["cat"] == "time" and not member.bot:
                        days = (now - member.joined_at).days if member.joined_at else 0
                        if days >= f_info["days"]:
                            should_have_role = True
                    elif f_info["cat"] == "presence" and not member.bot:
                        if f_key == "guild_tag":
                            if self.check_member_tag(member, target_tag):
                                should_have_role = True
                        else:
                            kw = settings.get(f_key, "")
                            if kw and self.check_support_status(member, kw):
                                should_have_role = True

                if should_have_role and role not in member.roles and role.position < top_pos:
                    added_roles.add(role)
                elif not should_have_role and role in member.roles and role.position < top_pos:
                    removed_roles.add(role)

            if added_roles:
                tasks_list.append(("add", member, list(added_roles)))
            if removed_roles:
                tasks_list.append(("remove", member, list(removed_roles)))

        view.sync_total = len(tasks_list)
        view.sync_progress = 0
        if view.sync_total == 0:
            view.sync_text = "Aucune modification nécessaire."
            await view._refresh()
            await asyncio.sleep(1)
            return

        last_update = time.time()
        for i, (action, member, roles) in enumerate(tasks_list):
            try:
                role_mentions = ", ".join([r.mention for r in roles])
                if action == "add":
                    await member.add_roles(*roles, reason="AutoRole : Sync")
                    view.sync_text = f"Rôle {role_mentions} donné à l'utilisateur {member.mention}"
                else:
                    await member.remove_roles(*roles, reason="AutoRole : Sync")
                    view.sync_text = f"Rôle {role_mentions} retiré à l'utilisateur {member.mention}"
            except discord.Forbidden:
                view.sync_text = f"Permission refusée pour {member.mention}"
            except Exception:
                pass

            view.sync_progress = i + 1
            
            # Anti-Spam: Rafraîchissement de l'interface toutes les 1.5 secondes seulement
            if time.time() - last_update > 1.5:
                await view._refresh()
                last_update = time.time()
                
        view.sync_text = "Synchronisation terminée avec succès !"
        await view._refresh()
        await asyncio.sleep(1)

    async def process_member_roles(self, member: discord.Member, data: dict, target_tag: str):
        """Évaluation métier silencieuse pour la tâche de fond (check_all_roles)."""
        added_roles, removed_roles = set(), set()
        now = datetime.now(timezone.utc)
        feats = data.get("enabled_features", [])
        settings = data.get("settings", {})

        for f_key, f_info in FEATURES_DEF.items():
            r_id = data["roles"].get(f_key)
            role = member.guild.get_role(int(r_id)) if r_id and str(r_id).isdigit() else None
            
            if not role: continue

            should_have_role = False

            if f_key in feats:
                if f_info["cat"] == "base":
                    if (f_key == "bot" and member.bot) or (f_key == "membre" and not member.bot):
                        should_have_role = True
                elif f_info["cat"] == "time" and not member.bot:
                    days = (now - member.joined_at).days if member.joined_at else 0
                    if days >= f_info["days"]:
                        should_have_role = True
                elif f_info["cat"] == "presence" and not member.bot:
                    if f_key == "guild_tag":
                        if self.check_member_tag(member, target_tag):
                            should_have_role = True
                    else:
                        kw = settings.get(f_key, "")
                        if kw and self.check_support_status(member, kw):
                            should_have_role = True

            if should_have_role and role not in member.roles:
                added_roles.add(role)
            elif not should_have_role and role in member.roles:
                removed_roles.add(role)

        try:
            bot_member = member.guild.get_member(self.bot.user.id)
            if bot_member:
                top_pos = bot_member.top_role.position
                clean_add = [r for r in added_roles if r.position < top_pos]
                clean_remove = [r for r in removed_roles if r.position < top_pos]

                if clean_add:
                    await member.add_roles(*clean_add, reason="AutoRole : Background Sync")
                if clean_remove:
                    await member.remove_roles(*clean_remove, reason="AutoRole : Background Sync")
        except discord.Forbidden:
            pass

    async def apply_roles_to_all(self, guild: discord.Guild):
        """Scanne la guilde de manière globale et silencieuse."""
        data = autorole_db.load(guild.id)
        target_tag = self.resolve_expected_tag(guild, data)

        for f_key in data.get("enabled_features", []):
            await self.ensure_role_exists(guild, f_key)

        for member in guild.members:
            await self.process_member_roles(member, data, target_tag)

    def calculate_eligible_counts(self, guild: discord.Guild, data: dict) -> dict:
        """Décompte de prédiction d'éligibilité pour les statistiques."""
        counts = {k: 0 for k in FEATURES_DEF}
        now = datetime.now(timezone.utc)
        settings = data.get("settings", {})
        target_tag = self.resolve_expected_tag(guild, data)

        for member in guild.members:
            if member.bot:
                counts["bot"] += 1
            else:
                counts["membre"] += 1
                days = (now - member.joined_at).days if member.joined_at else 0
                for f_key, f_info in FEATURES_DEF.items():
                    if f_info["cat"] == "time" and days >= f_info["days"]:
                        counts[f_key] += 1
                
                if self.check_member_tag(member, target_tag):
                    counts["guild_tag"] += 1

                for p_key in ["discord_url", "site_url"]:
                    kw = settings.get(p_key, "")
                    if kw and self.check_support_status(member, kw):
                        counts[p_key] += 1
        return counts

    @tasks.loop(minutes=15)
    async def check_all_roles(self):
        for guild in self.bot.guilds:
            try:
                if not guild.chunked:
                    await guild.chunk()
                data = autorole_db.load(guild.id)
                target_tag = self.resolve_expected_tag(guild, data)
                for member in guild.members:
                    await self.process_member_roles(member, data, target_tag)
            except Exception as e:
                log_sys("LOOP_ERROR", f"Échec de l'AutoRole sur le serveur {guild.id}: {e}", is_error=True)

    @check_all_roles.before_loop
    async def before_check(self):
        await self.bot.wait_until_ready()

    @perm_command(level=2)
    @commands.command(name="autorole", description="Ouvre l'interface de gestion de l'attribution automatique des rôles.")
    async def autorole_cmd(self, ctx: commands.Context):
        if not ctx.guild:
            await ctx.send(f"{E_OFF} Cette commande exige un contexte de serveur Discord.")
            return

        if not await ensure_command_permission(ctx, command_name="autorole"):
            return

        if not ctx.guild.chunked:
            await ctx.guild.chunk()
            
        log_sys("COMMAND", f"Lancement de /autorole par {ctx.author.name}")
        view = AutoRoleLayoutView(self, ctx.guild, ctx.author)
        msg = await ctx.send(view=view)
        view.message = msg


async def setup(bot: commands.Bot):
    if bot.get_command("autorole"):
        bot.remove_command("autorole")
    await bot.add_cog(AutoRoleCog(bot))