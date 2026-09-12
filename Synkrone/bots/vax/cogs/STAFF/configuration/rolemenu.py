import discord
from discord import ui, app_commands
from discord.ext import commands
import traceback
from pathlib import Path

# ==============================================================================
# --- IMPORTS MÉTIER VAX ---
# Utilisation stricte de l'écosystème pour garantir l'homogénéité globale[cite: 1].
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
# Mappage dynamique depuis le module Emoji officiel avec fallbacks[cite: 1, 5].
# ==============================================================================
E_ON = getattr(E, 'VALIDER', "âœ…") if HAS_VAX_CORE else "âœ…"
E_OFF = getattr(E, 'REFUSER', "âŒ") if HAS_VAX_CORE else "âŒ"
E_WARN = getattr(E, 'ATTENTION', "âš ï¸") if HAS_VAX_CORE else "âš ï¸"
E_GEAR = getattr(E, 'MODIFIER', "âš™ï¸") if HAS_VAX_CORE else "âš™ï¸"
E_ROLE = getattr(E, 'ROLE', "ðŸŽ­") if HAS_VAX_CORE else "ðŸŽ­"
E_ADD = getattr(E, 'AJOUTER', "âž•") if HAS_VAX_CORE else "âž•"
E_TRASH = getattr(E, 'SUPPRIMER', "ðŸ—‘ï¸") if HAS_VAX_CORE else "ðŸ—‘ï¸"
E_BACK = getattr(E, 'RETOUR', "â†©ï¸") if HAS_VAX_CORE else "â†©ï¸"
E_EDIT = getattr(E, 'MODIFIER', "âœï¸") if HAS_VAX_CORE else "âœï¸"
E_LIST = getattr(E, 'LISTE', "ðŸ“‹") if HAS_VAX_CORE else "ðŸ“‹"
E_LOCK = getattr(E, 'LOCK', "ðŸ”’") if HAS_VAX_CORE else "ðŸ”’"
E_ROCKET = getattr(E, 'HAUSSE', "ðŸš€") if HAS_VAX_CORE else "ðŸš€"
E_FOLDER = getattr(E, 'DOCUMENT', "ðŸ“‚") if HAS_VAX_CORE else "ðŸ“‚"

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
    prefix = "[ERREUR RoleMenu]" if is_error else "[INFO RoleMenu]"
    print(f"{color}{prefix} [{action}] {message}{COLOR_RESET}")

# ==============================================================================
# --- GESTIONNAIRE DE DONNÉES (DataManager) ---
# ==============================================================================
class RoleMenuManager:
    """Interface de sauvegarde s'appuyant sur l'infrastructure standard[cite: 1, 2]."""
    def __init__(self):
        if HAS_VAX_CORE:
            self.data = DataManager("staff/configuration/data_rolemenus")
            # Sécurisation V3 : Forcer la création de l'arborescence physique pour éviter l'Errno 2
            try:
                Path("data/staff/configuration/data_rolemenus").mkdir(parents=True, exist_ok=True)
            except Exception as e:
                log_sys("MKDIR_ERR", f"Erreur de création du dossier de données: {e}", is_error=True)
        else:
            log_sys("INIT", "DataManager introuvable. Le système va échouer.", is_error=True)

    def load(self, guild_id: int) -> dict:
        try:
            raw = self.data.load(guild_id) or {}
            if "menus" not in raw:
                raw["menus"] = {}
            return raw
        except Exception as e:
            log_sys("DB_LOAD", f"Erreur de lecture DB pour {guild_id}: {e}", is_error=True)
            return {"menus": {}}

    def save(self, guild_id: int, config: dict):
        try:
            self.data.save(guild_id, config)
            log_sys("DB_SAVE", f"Configuration sauvegardée pour {guild_id}")
        except Exception as e:
            log_sys("DB_SAVE_ERR", f"Erreur d'écriture DB pour {guild_id}: {e}", is_error=True)

rolemenu_db = RoleMenuManager()

# ==============================================================================
# --- MODALS D'ADMINISTRATION ---
# ==============================================================================
class MenuCreateModal(ui.Modal, title="Création de Menu"):
    name_input = ui.TextInput(label="Nom du menu (Interne)", placeholder="Ex: Ping Jeux", required=True, max_length=50)
    title_input = ui.TextInput(label="Titre d'affichage public", placeholder="Ex: Choisissez vos jeux", required=True, max_length=100)

    def __init__(self, view: "AdminRoleMenuLayoutView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        log_sys("MODAL_CREATE", f"Soumission de création par {interaction.user.name}")
        m_id = self.name_input.value.strip().replace(" ", "_").lower()
        m_title = self.title_input.value.strip()
        
        config = rolemenu_db.load(self.view.guild.id)
        if m_id in config["menus"]:
            self.view.status_message = f"{E_WARN} Un menu avec cet identifiant existe déjà."
        else:
            config["menus"][m_id] = {
                "title": m_title,
                "display_type": "select",
                "selection_mode": "multiple",
                "required_role": None,
                "forbidden_role": None,
                "deploy_chan": None,
                "deploy_msg": None,
                "roles": {}
            }
            rolemenu_db.save(self.view.guild.id, config)
            self.view.selected_menu = m_id
            self.view.state = "detail"
            self.view.status_message = f"{E_ON} Le menu `{m_title}` a été forgé avec succès."
        
        await self.view._refresh(interaction)

class RoleEditModal(ui.Modal, title="Édition d'un Rôle"):
    label_input = ui.TextInput(label="Nom d'affichage", placeholder="Ex: Joueur de Valorant", required=True, max_length=50)
    desc_input = ui.TextInput(label="Description (pour Menu Déroulant)", placeholder="Ex: Reçoit des notifications...", required=False, max_length=100)
    emoji_input = ui.TextInput(label="Emoji (Unicode ou <a:nom:id>)", placeholder="Ex: ðŸŽ®", required=False)

    def __init__(self, view: "AdminRoleMenuLayoutView", role_id: str):
        super().__init__()
        self.view = view
        self.role_id = role_id
        
        config = rolemenu_db.load(self.view.guild.id)
        r_data = config["menus"][self.view.selected_menu]["roles"][role_id]
        
        self.label_input.default = r_data.get("label", "")
        self.desc_input.default = r_data.get("description", "")
        self.emoji_input.default = r_data.get("emoji", "")

    async def on_submit(self, interaction: discord.Interaction):
        log_sys("MODAL_EDIT", f"Édition du rôle {self.role_id} par {interaction.user.name}")
        config = rolemenu_db.load(self.view.guild.id)
        r_data = config["menus"][self.view.selected_menu]["roles"][self.role_id]
        
        r_data["label"] = self.label_input.value.strip()
        r_data["description"] = self.desc_input.value.strip()
        r_data["emoji"] = self.emoji_input.value.strip() or "ðŸ”¹"
        
        rolemenu_db.save(self.view.guild.id, config)
        self.view.status_message = f"{E_ON} Esthétique du rôle mise à  jour."
        
        await self.view.cog.refresh_deployed_menu(self.view.guild, self.view.selected_menu)
        await self.view._refresh(interaction)

# ==============================================================================
# --- VUE PUBLIQUE (RoleMenu Deployed) ---
# ==============================================================================
class PublicRoleMenuView(ui.LayoutView):
    """Générateur de rendu V2 pour le menu public des utilisateurs[cite: 1, 4]."""
    def __init__(self, cog: "RoleMenuCog", guild: discord.Guild, menu_id: str):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild = guild
        self.menu_id = menu_id
        self._build()

    def _build(self):
        self.clear_items()
        config = rolemenu_db.load(self.guild.id)
        m_data = config["menus"].get(self.menu_id)
        if not m_data: return

        # Sécurité de chargement du thème global
        accent_color = 0x2b2d31
        try:
            theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.cog.bot.user, self.cog.bot)
            accent_color = int(theme.get("color", 0x2b2d31))
        except Exception as e:
            log_sys("THEME_ERR", f"Erreur de thème public: {e}", is_error=True)

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {E_ROLE} {m_data.get('title', 'Menu des rôles')}"))
        
        desc = "Utilisez les composants ci-dessous pour obtenir ou retirer vos rôles."
        if m_data.get('required_role'):
            desc += f"\n{E_LOCK} *Requiert le rôle <@&{m_data['required_role']}>.*"

        roles_dict = m_data.get("roles", {})
        if roles_dict:
            public_lines = []
            for r_id_str, r_info in list(roles_dict.items())[:25]:
                role_emoji = r_info.get("emoji") or "ðŸ”¹"
                role_label = r_info.get("label", "Rôle")
                public_lines.append(f"- {role_emoji} **{role_label}** (<@&{r_id_str}>)")
            desc += "\n\n### Rôles disponibles\n" + "\n".join(public_lines)

        container.add_item(ui.TextDisplay(desc))

        if not roles_dict:
            container.add_item(ui.TextDisplay("> *Ce menu est en cours de configuration.*"))
            self.add_item(container)
            return

        if m_data.get("display_type") == "buttons":
            row = ui.ActionRow()
            count = 0
            for r_id_str, r_info in list(roles_dict.items())[:25]:
                if count > 0 and count % 5 == 0:
                    container.add_item(row)
                    row = ui.ActionRow()
                
                btn = ui.Button(
                    label=r_info.get("label", "Rôle")[:80],
                    emoji=r_info.get("emoji") if r_info.get("emoji") else None,
                    style=discord.ButtonStyle.secondary,
                    custom_id=f"rm_{self.guild.id}_{self.menu_id}_{r_id_str}"
                )
                btn.callback = self._create_toggle_callback(r_id_str)
                row.add_item(btn)
                count += 1
            container.add_item(row)
            
        else:
            options = []
            for r_id_str, r_info in list(roles_dict.items())[:25]:
                options.append(discord.SelectOption(
                    label=r_info.get("label", "Rôle")[:100],
                    value=r_id_str,
                    description=r_info.get("description")[:100] if r_info.get("description") else None,
                    emoji=r_info.get("emoji") if r_info.get("emoji") else None
                ))
            
            sel_row = ui.ActionRow()
            max_val = len(options) if m_data.get("selection_mode") == "multiple" else 1
            select = ui.Select(
                placeholder="Sélectionnez vos rôles...",
                min_values=0, max_values=max_val,
                options=options,
                custom_id=f"rm_sel_{self.guild.id}_{self.menu_id}"
            )
            select.callback = self._select_callback
            sel_row.add_item(select)
            container.add_item(sel_row)

        self.add_item(container)

    def _create_toggle_callback(self, role_id_str: str):
        async def callback(interaction: discord.Interaction):
            await self._process_roles(interaction, [role_id_str])
        return callback

    async def _select_callback(self, interaction: discord.Interaction):
        await self._process_roles(interaction, interaction.data.get('values', []))

    async def _process_roles(self, interaction: discord.Interaction, target_ids: list):
        """Traitement métier avec technique Defer pour annuler l'éphémère sans freeze."""
        log_sys("ROLE_PROCESS", f"Interaction déclenchée par {interaction.user.name}")
        
        if not interaction.response.is_done():
            await interaction.response.defer()
        
        config = rolemenu_db.load(self.guild.id)
        m_data = config["menus"].get(self.menu_id)
        if not m_data: return

        member = interaction.user
        guild = interaction.guild

        req_role = m_data.get("required_role")
        if req_role and str(req_role).isdigit() and not member.get_role(int(req_role)):
            return await interaction.channel.send(f"{E_OFF} {member.mention}, vous n'avez pas l'accréditation requise pour utiliser ce menu.", delete_after=6)

        forb_role = m_data.get("forbidden_role")
        if forb_role and str(forb_role).isdigit() and member.get_role(int(forb_role)):
            return await interaction.channel.send(f"{E_OFF} {member.mention}, un de vos rôles vous interdit l'accès à ce menu.", delete_after=6)

        added, removed = [], []
        target_role_ids = [int(r) for r in target_ids]

        if m_data.get("selection_mode") == "unique":
            menu_role_ids = [int(k) for k in m_data["roles"].keys()]
            clean_remove = [guild.get_role(r) for r in menu_role_ids if r not in target_role_ids and member.get_role(r)]
            clean_remove = [r for r in clean_remove if r]

            if target_role_ids:
                target_role = guild.get_role(target_role_ids[0])
                if target_role:
                    if target_role in member.roles:
                        clean_remove.append(target_role)
                        removed.append(target_role.name)
                    else:
                        try:
                            await member.add_roles(target_role, reason="AutoRoleMenu: Select Unique")
                            added.append(target_role.name)
                        except discord.Forbidden:
                            return await interaction.channel.send(f"{E_OFF} {member.mention}, le bot manque de permissions hiérarchiques.", delete_after=6)

            if clean_remove:
                try:
                    await member.remove_roles(*clean_remove, reason="AutoRoleMenu: Clean Unique")
                    removed.extend([r.name for r in clean_remove if r.name not in removed])
                except discord.Forbidden:
                    pass

        else: 
            for rid in target_role_ids:
                role = guild.get_role(rid)
                if not role: continue
                try:
                    if role in member.roles:
                        await member.remove_roles(role, reason="AutoRoleMenu: Toggle Off")
                        removed.append(role.name)
                    else:
                        await member.add_roles(role, reason="AutoRoleMenu: Toggle On")
                        added.append(role.name)
                except discord.Forbidden:
                    log_sys("PERM_ERROR", f"Impossible d'assigner {role.name} à {member.name}", is_error=True)
                    return await interaction.channel.send(f"{E_OFF} {member.mention}, hiérarchie insuffisante pour assigner `{role.name}`.", delete_after=6)

        msg_lines = []
        if added: msg_lines.append(f"{E_ON} **Ajoutés :** {', '.join(added)}")
        if removed: msg_lines.append(f"{E_OFF} **Retirés :** {', '.join(removed)}")
        
        final_msg = "\n".join(msg_lines) if msg_lines else "Aucun changement appliqué."
        await interaction.channel.send(f"{member.mention} âžœ {final_msg}", delete_after=6)


# ==============================================================================
# --- INTERFACE D'ADMINISTRATION (Layout V2) ---
# ==============================================================================
class AdminRoleMenuLayoutView(ui.LayoutView):
    """Tableau de bord V2 d'administration de l'infrastructure RoleMenu[cite: 1, 4]."""
    def __init__(self, cog: "RoleMenuCog", guild: discord.Guild, user: discord.Member):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild = guild
        self.user = user
        self.state = "main" 
        self.selected_menu = None
        self.selected_role = None
        self.deploy_channel_id = None
        self.status_message = ""
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            try:
                await interaction.response.send_message(f"{E_OFF} {interaction.user.mention}, cette console est protégée par {self.user.mention}.", ephemeral=False, delete_after=5)
            except Exception:
                if not interaction.response.is_done():
                    await interaction.response.defer()
            return False
        return True

    def _build(self):
        log_sys("BUILD", f"Construction de la vue Admin (État: {self.state})")
        self.clear_items()
        config = rolemenu_db.load(self.guild.id)
        
        accent_color = 0x2b2d31
        footer_text = ""
        if HAS_VAX_CORE and config_manager:
            try:
                theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.cog.bot)
                accent_color = int(theme.get("color", 0x2b2d31))
                footer_text = theme.get("footer_text", "")
            except Exception as e:
                log_sys("THEME_ERR", f"Erreur de chargement du thème: {e}", is_error=True)

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        
        if self.status_message:
            container.add_item(ui.TextDisplay(f"> {self.status_message}"))
            self.status_message = ""

        if self.state == "main":
            self._build_main(container, config)
        elif self.state == "detail":
            self._build_detail(container, config)
        elif self.state == "edit_role":
            self._build_role_edit(container, config)

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
            log_sys("REFRESH", "Interface rafraîchie avec succès.")
        except Exception as e:
            log_sys("REFRESH_ERR", f"Échec du rafraîchissement UI: {e}", is_error=True)

    # --- SOUS-SECTIONS ---
    def _build_main(self, container: ui.Container, config: dict):
        menus = config.get("menus", {})
        container.add_item(ui.TextDisplay(f"# {E_GEAR} Ingénierie des RoleMenus"))
        container.add_item(ui.TextDisplay(
            "Concevez des interfaces d'attribution de rôles interactives pour vos membres.\n"
            f"**Systèmes actifs :** `{len(menus)}`"
        ))

        # Séparation du menu déroulant et du bouton pour respecter la hiérarchie ActionRow[cite: 1]
        if menus:
            select_row = ui.ActionRow()
            options = [discord.SelectOption(label=m_data["title"][:100], value=m_id, emoji=E_FOLDER) for m_id, m_data in list(menus.items())[:25]]
            sel = ui.Select(placeholder="Ouvrir un menu existant...", options=options)
            sel.callback = self._on_menu_select
            select_row.add_item(sel)
            container.add_item(select_row)

        action_row = ui.ActionRow()
        btn_add = ui.Button(label="Nouvelle Interface", style=discord.ButtonStyle.success, emoji=E_ADD)
        btn_add.callback = self._open_create_modal
        action_row.add_item(btn_add)
        
        container.add_item(action_row)

    def _build_detail(self, container: ui.Container, config: dict):
        m_data = config["menus"][self.selected_menu]

        if self.deploy_channel_id is None and m_data.get("deploy_chan"):
            self.deploy_channel_id = int(m_data["deploy_chan"])
        
        roles_txt = "Aucun"
        if m_data["roles"]:
            roles_txt = "\n".join([f"- {r['emoji']} **{r['label']}** (<@&{r_id}>)" for r_id, r in m_data["roles"].items()])

        mode_txt = "Unique (1 seul rôle possible)" if m_data["selection_mode"] == "unique" else "Multiple (Choix libres)"
        type_txt = "Boutons interactifs" if m_data["display_type"] == "buttons" else "Menu Déroulant"
        req_txt = f"<@&{m_data['required_role']}>" if m_data["required_role"] else "`Aucun`"
        dep_txt = f"<#{m_data['deploy_chan']}>" if m_data["deploy_chan"] else "`Non déployé`"
        selected_chan_txt = f"<#{self.deploy_channel_id}>" if self.deploy_channel_id else "`Aucun salon sélectionné`"

        container.add_item(ui.TextDisplay(f"# {E_FOLDER} Menu : {m_data['title']}"))
        container.add_item(ui.TextDisplay(
            f"**Architecture :** {type_txt} | **Mode :** {mode_txt}\n"
            f"**Prérequis :** {req_txt} | **Ancrage :** {dep_txt}\n"
            f"**Salon ciblé (pré-déploiement) :** {selected_chan_txt}\n\n"
            f"### {E_ROLE} Configuration des Rôles ({len(m_data['roles'])})\n{roles_txt}"
        ))

        act_row = ui.ActionRow()
        act_sel = ui.Select(placeholder="âš™ï¸ Configurer l'infrastructure...", options=[
            discord.SelectOption(label="Basculer Mode (Unique/Multiple)", value="mode", emoji="ðŸ”„"),
            discord.SelectOption(label="Basculer Affichage (Boutons/Sélecteur)", value="type", emoji="ðŸŽ¨"),
            discord.SelectOption(label="Détruire le menu", value="delete", emoji=E_TRASH)
        ])
        act_sel.callback = self._on_action_select
        act_row.add_item(act_sel)
        container.add_item(act_row)

        add_row = ui.ActionRow()
        role_sel = ui.RoleSelect(placeholder="Ajouter des rôles au menu...", min_values=1, max_values=25)
        role_sel.callback = self._on_add_roles
        add_row.add_item(role_sel)
        container.add_item(add_row)

        if m_data["roles"]:
            edit_row = ui.ActionRow()
            e_opts = [discord.SelectOption(label=r['label'][:100], value=r_id, emoji=E_EDIT) for r_id, r in m_data["roles"].items()]
            edit_sel = ui.Select(placeholder="Éditer un rôle de la liste...", options=e_opts[:25])
            edit_sel.callback = self._on_edit_role_select
            edit_row.add_item(edit_sel)
            container.add_item(edit_row)

        deploy_sel_row = ui.ActionRow()
        chan_sel = ui.ChannelSelect(
            placeholder="Choisir le salon cible du déploiement...",
            min_values=1,
            max_values=1,
            channel_types=[discord.ChannelType.text]
        )
        chan_sel.callback = self._on_deploy_channel_select
        deploy_sel_row.add_item(chan_sel)
        container.add_item(deploy_sel_row)

        nav_row = ui.ActionRow()
        btn_deploy = ui.Button(label="Déployer dans le salon", style=discord.ButtonStyle.primary, emoji=E_ROCKET)
        btn_deploy.callback = self._deploy_to_selected_channel
        nav_row.add_item(btn_deploy)

        btn_detach = ui.Button(label="Détacher", style=discord.ButtonStyle.danger, emoji=E_TRASH)
        btn_detach.callback = self._detach_deploy
        nav_row.add_item(btn_detach)

        btn_back = ui.Button(label="Retour", style=discord.ButtonStyle.secondary, emoji=E_BACK)
        btn_back.callback = lambda i: self._change_state(i, "main")
        nav_row.add_item(btn_back)
        container.add_item(nav_row)

    def _build_role_edit(self, container: ui.Container, config: dict):
        r_data = config["menus"][self.selected_menu]["roles"][self.selected_role]
        
        container.add_item(ui.TextDisplay(f"# {E_EDIT} Édition du rôle"))
        container.add_item(ui.TextDisplay(
            f"**Cible :** <@&{self.selected_role}>\n"
            f"**Label :** `{r_data['label']}`\n"
            f"**Description :** `{r_data.get('description', 'Aucune')}`\n"
            f"**Emoji :** {r_data.get('emoji', 'Aucun')}"
        ))

        act_row = ui.ActionRow()
        btn_edit = ui.Button(label="Modifier (Nom/Emoji)", style=discord.ButtonStyle.primary, emoji=E_EDIT)
        btn_edit.callback = self._open_role_edit_modal
        act_row.add_item(btn_edit)

        btn_del = ui.Button(label="Exclure du Menu", style=discord.ButtonStyle.danger, emoji=E_TRASH)
        btn_del.callback = self._remove_role
        act_row.add_item(btn_del)

        btn_back = ui.Button(label="Retour", style=discord.ButtonStyle.secondary, emoji=E_BACK)
        btn_back.callback = lambda i: self._change_state(i, "detail")
        act_row.add_item(btn_back)

        container.add_item(act_row)

    # --- CALLBACKS ---
    async def _change_state(self, interaction: discord.Interaction, new_state: str):
        self.state = new_state
        self.status_message = ""
        await self._refresh(interaction)

    async def _on_menu_select(self, interaction: discord.Interaction):
        self.selected_menu = interaction.data["values"][0]
        await self._change_state(interaction, "detail")

    async def _open_create_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(MenuCreateModal(self))

    async def _on_action_select(self, interaction: discord.Interaction):
        action = interaction.data["values"][0]
        config = rolemenu_db.load(self.guild.id)
        m_data = config["menus"][self.selected_menu]

        if action == "mode":
            m_data["selection_mode"] = "unique" if m_data["selection_mode"] == "multiple" else "multiple"
            self.status_message = f"{E_ON} Mode de sélection mis à jour."
        elif action == "type":
            m_data["display_type"] = "buttons" if m_data["display_type"] == "select" else "select"
            self.status_message = f"{E_ON} Rendu visuel mis à jour."
        elif action == "delete":
            del config["menus"][self.selected_menu]
            self.selected_menu = None
            self.state = "main"
            self.status_message = f"{E_TRASH} Menu détruit de la base de données."
        
        rolemenu_db.save(self.guild.id, config)
        if action in ["mode", "type"]:
            await self.cog.refresh_deployed_menu(self.guild, self.selected_menu)
            
        await self._refresh(interaction)

    async def _on_add_roles(self, interaction: discord.Interaction):
        log_sys("ROLE_ADD", f"Ajout de rôles demandé par {interaction.user.name}")
        role_ids = interaction.data.get("values", [])
        config = rolemenu_db.load(self.guild.id)
        r_dict = config["menus"][self.selected_menu]["roles"]
        
        count = 0
        for r_id_str in role_ids:
            if r_id_str not in r_dict:
                role_obj = self.guild.get_role(int(r_id_str))
                if role_obj:
                    r_dict[r_id_str] = {
                        "label": role_obj.name[:50],
                        "description": "Cliquez pour obtenir ce rôle",
                        "emoji": "ðŸ”¹"
                    }
                    count += 1

        rolemenu_db.save(self.guild.id, config)
        self.status_message = f"{E_ON} {count} rôle(s) ajouté(s) à l'interface."
        
        await self.cog.refresh_deployed_menu(self.guild, self.selected_menu)
        await self._refresh(interaction)

    async def _on_edit_role_select(self, interaction: discord.Interaction):
        self.selected_role = interaction.data["values"][0]
        await self._change_state(interaction, "edit_role")

    async def _on_deploy_channel_select(self, interaction: discord.Interaction):
        values = interaction.data.get("values", [])
        if values:
            self.deploy_channel_id = int(values[0])
            self.status_message = f"{E_ON} Salon de déploiement ciblé: <#{self.deploy_channel_id}>."
        else:
            self.status_message = f"{E_WARN} Aucun salon sélectionné."
        await self._refresh(interaction)

    async def _open_role_edit_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(RoleEditModal(self, self.selected_role))

    async def _remove_role(self, interaction: discord.Interaction):
        config = rolemenu_db.load(self.guild.id)
        del config["menus"][self.selected_menu]["roles"][self.selected_role]
        rolemenu_db.save(self.guild.id, config)
        
        self.status_message = f"{E_TRASH} Rôle retiré du menu."
        self.selected_role = None
        self.state = "detail"
        
        await self.cog.refresh_deployed_menu(self.guild, self.selected_menu)
        await self._refresh(interaction)

    async def _deploy_to_selected_channel(self, interaction: discord.Interaction):
        log_sys("MODAL_DEPLOY", f"Déploiement automatique demandé par {interaction.user.name}")
        config = rolemenu_db.load(self.guild.id)
        m_data = config["menus"].get(self.selected_menu)
        if not m_data:
            return await self._refresh(interaction)

        chan_id = self.deploy_channel_id or m_data.get("deploy_chan")
        if not chan_id:
            self.status_message = f"{E_WARN} Sélectionnez d'abord un salon via le sélecteur."
            return await self._refresh(interaction)

        target_chan = interaction.guild.get_channel(int(chan_id))
        if not target_chan:
            self.status_message = f"{E_OFF} Le salon sélectionné est introuvable."
            return await self._refresh(interaction)

        if not isinstance(target_chan, discord.TextChannel):
            self.status_message = f"{E_OFF} Le déploiement exige un salon textuel."
            return await self._refresh(interaction)

        try:
            view = PublicRoleMenuView(self.cog, self.guild, self.selected_menu)
            deployed_msg = None

            old_chan_id = m_data.get("deploy_chan")
            old_msg_id = m_data.get("deploy_msg")
            if old_chan_id and old_msg_id and int(old_chan_id) == target_chan.id:
                try:
                    old_msg = await target_chan.fetch_message(int(old_msg_id))
                    try:
                        await old_msg.edit(view=view)
                    except discord.HTTPException as e:
                        if e.code == 50035 and "IS_COMPONENTS_V2" in str(e):
                            await old_msg.edit(content=None, embeds=[], attachments=[], view=None)
                            await old_msg.edit(view=view)
                        else:
                            raise
                    deployed_msg = old_msg
                except discord.NotFound:
                    deployed_msg = None

            if deployed_msg is None:
                deployed_msg = await target_chan.send(view=view)

            m_data["deploy_chan"] = target_chan.id
            m_data["deploy_msg"] = deployed_msg.id
            rolemenu_db.save(self.guild.id, config)
            self.status_message = f"{E_ROCKET} Menu déployé automatiquement dans {target_chan.mention}."
        except discord.Forbidden:
            self.status_message = f"{E_OFF} Permissions insuffisantes pour écrire dans {target_chan.mention}."
        except Exception as e:
            self.status_message = f"{E_OFF} Échec du déploiement automatique."
            log_sys("DEPLOY_ERR", f"Déploiement auto impossible: {e}", is_error=True)

        await self._refresh(interaction)

    async def _detach_deploy(self, interaction: discord.Interaction):
        config = rolemenu_db.load(self.guild.id)
        m_data = config["menus"].get(self.selected_menu)
        if not m_data:
            return await self._refresh(interaction)

        m_data["deploy_chan"] = None
        m_data["deploy_msg"] = None
        rolemenu_db.save(self.guild.id, config)
        self.status_message = f"{E_TRASH} Le menu a été détaché du bot."
        await self._refresh(interaction)


# ==============================================================================
# --- COG PRINCIPAL ---
# ==============================================================================
class RoleMenuCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log_sys("INIT", "Module RoleMenu V3 déployé.")

    async def cog_load(self):
        """Réactivation des vues de manière asynchrone non-bloquante."""
        self.bot.loop.create_task(self._restore_views())

    async def _restore_views(self):
        """Fonction détachée du setup_hook pour ne jamais freezer le bot au démarrage."""
        await self.bot.wait_until_ready()
        count = 0
        for guild in self.bot.guilds:
            config = rolemenu_db.load(guild.id)
            for m_id, m_data in config.get("menus", {}).items():
                if m_data.get("deploy_msg") and m_data.get("deploy_chan"):
                    try:
                        view = PublicRoleMenuView(self, guild, m_id)
                        self.bot.add_view(view)
                        count += 1
                    except Exception as e:
                        log_sys("RESTORE_ERR", f"Impossible de restaurer la vue {m_id}: {e}", is_error=True)
        log_sys("RELOAD", f"{count} interfaces publiques ré-arrimées en mémoire avec succès.")

    async def refresh_deployed_menu(self, guild: discord.Guild, menu_id: str):
        """Met à jour physiquement le message public si la config change."""
        config = rolemenu_db.load(guild.id)
        m_data = config["menus"].get(menu_id)
        if not m_data or not m_data.get("deploy_msg"): return

        try:
            chan = guild.get_channel(m_data["deploy_chan"])
            if not chan: return
            msg = await chan.fetch_message(m_data["deploy_msg"])
            
            view = PublicRoleMenuView(self, guild, menu_id)
            try:
                await msg.edit(view=view)
            except discord.HTTPException as e:
                if e.code == 50035 and "IS_COMPONENTS_V2" in str(e):
                    # Migration d'un ancien message (avec contenu/embed) vers un message V2.
                    await msg.edit(content=None, embeds=[], attachments=[], view=None)
                    await msg.edit(view=view)
                else:
                    raise
            log_sys("UPDATE", f"Menu {menu_id} rafraîchi sur le message {msg.id}")
        except discord.NotFound:
            log_sys("CLEANUP", f"Message du menu {menu_id} introuvable, désancrage en base de données.")
            m_data["deploy_chan"] = None
            m_data["deploy_msg"] = None
            rolemenu_db.save(guild.id, config)
        except Exception as e:
            log_sys("UPDATE_ERR", f"Échec de mise à  jour du message {m_data['deploy_msg']}: {e}", is_error=True)

    @perm_command(level=2) # Verrouillage métier via la config_perm[cite: 1, 3]
    @commands.hybrid_command(name="rolemenu", description="Tableau de bord de gestion des rôles interactifs.")
    async def rolemenu_cmd(self, ctx: commands.Context):
        log_sys("CMD_CALL", f"Commande /rolemenu déclenchée par {ctx.author.name}")
        if not ctx.guild:
            await ctx.send(f"{E_OFF} Cette commande exige un contexte de serveur.")
            return

        # Autorisation d'accès contrôlée si HAS_VAX_CORE, sinon accès basique admin
        if HAS_VAX_CORE:
            if not await ensure_command_permission(ctx, command_name="rolemenu"):
                log_sys("CMD_DENY", f"Accès refusé par ensure_command_permission pour {ctx.author.name}")
                return
        else:
            if not ctx.author.guild_permissions.administrator:
                await ctx.send(f"{E_OFF} Permissions administrateur requises.")
                return
            
        log_sys("CMD_APPROVE", f"Interface /rolemenu déployée pour {ctx.author.name}")
        view = AdminRoleMenuLayoutView(self, ctx.guild, ctx.author)
        await ctx.send(view=view)

async def setup(bot: commands.Bot):
    if bot.get_command("rolemenu"):
        bot.remove_command("rolemenu")
    await bot.add_cog(RoleMenuCog(bot))

