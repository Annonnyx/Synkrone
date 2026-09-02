import discord
from discord import ui, app_commands
from discord.ext import commands
import traceback
import re

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
E_SHIELD = getattr(E, 'BOUCLIER', "🛡️") if HAS_VAX_CORE else "🛡️"
E_STAR = getattr(E, 'ETOILE', "⭐") if HAS_VAX_CORE else "⭐"
E_HOME = getattr(E, 'ACCUEIL', "🏠") if HAS_VAX_CORE else "🏠"
E_TIME = getattr(E, 'TEMPS', "⏳") if HAS_VAX_CORE else "⏳"
E_TRASH = getattr(E, 'SUPPRIMER', "🗑️") if HAS_VAX_CORE else "🗑️"
E_ID = getattr(E, 'IDENTIFIANT', "🆔") if HAS_VAX_CORE else "🆔"

# Emojis Custom Spécifiques
E_ROLE = getattr(E, 'ROLE', "🎭") if HAS_VAX_CORE else "🎭"
E_USER = getattr(E, 'PROFIL', "👤") if HAS_VAX_CORE else "👤"
E_BOT = getattr(E, 'VAX', "🤖") if HAS_VAX_CORE else "🤖"

E_HAMMER = getattr(E, 'MARTEAU', "🔨") if HAS_VAX_CORE else "🔨"
E_DOOR = getattr(E, 'PORTE', "🚪") if HAS_VAX_CORE else "🚪"
E_DOCUMENT = getattr(E, 'DOCUMENT', "📄") if HAS_VAX_CORE else "📄"
E_ANNOUNCE = getattr(E, 'ANNONCE', "📢") if HAS_VAX_CORE else "📢"
E_LINK = getattr(E, 'LIEN', "🔗") if HAS_VAX_CORE else "🔗"
E_MEMO = getattr(E, 'MEMO', "🏷️") if HAS_VAX_CORE else "🏷️"
E_EDIT = getattr(E, 'MODIFIER', "✏️") if HAS_VAX_CORE else "✏️"

E_N1 = getattr(E, 'N1', "1️⃣") if HAS_VAX_CORE else "1️⃣"
E_N2 = getattr(E, 'N2', "2️⃣") if HAS_VAX_CORE else "2️⃣"
E_N3 = getattr(E, 'N3', "3️⃣") if HAS_VAX_CORE else "3️⃣"

# ==============================================================================
# --- UTILITAIRES DE LOGS ---
# ==============================================================================
def log_sys(action: str, message: str, is_error: bool = False):
    if ERROR_LOGS_ONLY and not is_error: return
    if not DEBUG_LOGS and not is_error: return

    COLOR_RESET = "\033[0m"
    COLOR_INFO = "\033[96m"   # Cyan
    COLOR_ERROR = "\033[91m"   # Rouge
    color = COLOR_ERROR if is_error else COLOR_INFO
    prefix = "[ERREUR Securite]" if is_error else "[INFO Securite]"
    print(f"{color}{prefix} [{action}] {message}{COLOR_RESET}")

# ==============================================================================
# --- DONNÉES DES MODULES ---
# ==============================================================================
MODULES_DATA = {
    "ban": {"emoji": E_HAMMER, "desc": "Contrôle des bannissements et débannissements massifs.", "def": {"actif": False, "seuil": 5, "temps": 60, "action": "Dérank"}},
    "bot": {"emoji": E_BOT, "desc": "Blocage des bots non-autorisés (Anti-Token).", "def": {"actif": False, "action_bot": "Kick", "action_user": "Dérank"}},
    "channel": {"emoji": E_DOCUMENT, "desc": "Protection contre la création/suppression de salons.", "def": {"actif": False, "seuil": 3, "temps": 10, "action": "Dérank"}},
    "deco": {"emoji": E_DOOR, "desc": "Alerte en cas de départs massifs (Anti-Leaver).", "def": {"actif": False, "seuil": 5, "temps": 60, "action": "Alerte"}},
    "everyone": {"emoji": E_ANNOUNCE, "desc": "Limitation des mentions everyone et here.", "def": {"actif": False, "seuil": 2, "temps": 60, "action": "Dérank"}},
    "link": {"emoji": E_LINK, "desc": "Suppression automatique des liens publicitaires.", "def": {"actif": False, "seuil": 3, "temps": 10, "action": "Mute"}},
    "massmention": {"emoji": E_ROLE, "desc": "Contrôle du nombre de mentions par message.", "def": {"actif": False, "seuil": 5, "action": "Supprimer"}},
    "anti_mention": {"emoji": E_MEMO, "desc": "Protection contre le spam de tags rôles/users.", "def": {"actif": False, "seuil": 4, "temps": 5, "action": "Mute"}},
    "role": {"emoji": E_ROLE, "desc": "Surveillance des modifications de rôles.", "def": {"actif": False, "seuil": 3, "temps": 10, "action": "Dérank"}},
    "update": {"emoji": E_EDIT, "desc": "Protection des paramètres du serveur.", "def": {"actif": False, "action": "Dérank"}},
    "webhook": {"emoji": E_LINK, "desc": "Interdiction de création de webhooks.", "def": {"actif": False, "action": "Dérank"}}
}

PAGES_ORDER = ["main"] + list(MODULES_DATA.keys()) + ["whitelist"]

# ==============================================================================
# --- GESTIONNAIRE DE DONNÉES (DataManager) ---
# ==============================================================================
class SecurManager:
    """Interface de sauvegarde s'appuyant sur l'infrastructure standard."""
    def __init__(self):
        if HAS_VAX_CORE:
            self.data = DataManager("staff/configuration/securite")
        else:
            log_sys("INIT", "DataManager introuvable. Échec système.", is_error=True)

    def load(self, guild_id: int) -> dict:
        raw = self.data.load(guild_id) or {}
        if "config" not in raw: raw["config"] = {}
        if "whitelist" not in raw: raw["whitelist"] = []
        
        # Injection des configurations par défaut pour éviter les KeyErrors
        for m_key, m_info in MODULES_DATA.items():
            if m_key not in raw["config"]:
                raw["config"][m_key] = m_info["def"].copy()
                
        return raw

    def save(self, guild_id: int, config: dict):
        self.data.save(guild_id, config)

secur_db = SecurManager()

# ==============================================================================
# --- MODALS ---
# ==============================================================================
class ManualIDModal(ui.Modal, title="Gestion Manuelle par ID"):
    """Modal natif pour cibler n'importe quel identifiant dans la Whitelist."""
    target_id = ui.TextInput(
        label="ID de l'entité (Membre, Rôle, Bot)",
        placeholder="Ex: 123456789012345678",
        min_length=17,
        max_length=20,
        required=True
    )

    def __init__(self, view: "SecurLayoutView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            id_to_manage = int(self.target_id.value)
        except ValueError:
            if not interaction.response.is_done(): await interaction.response.defer()
            return await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, l'ID doit être composé uniquement de nombres.", delete_after=6)

        existing_ids = [x['id'] for x in self.view.db["whitelist"]]

        if id_to_manage in existing_ids:
            self.view.db["whitelist"] = [x for x in self.view.db["whitelist"] if x['id'] != id_to_manage]
            action = "retirée de"
        else:
            t_type = "ID Manuel"
            if self.view.guild.get_role(id_to_manage): t_type = "Rôle"
            elif self.view.guild.get_member(id_to_manage): t_type = "Membre/Bot"
            
            self.view.db["whitelist"].append({"id": id_to_manage, "type": t_type})
            action = "ajoutée à"

        secur_db.save(self.view.guild.id, self.view.db)
        self.view.status_message = f"{E_ON} Entité `{id_to_manage}` {action} la Whitelist."
        await self.view._refresh(interaction)

class SeuilModal(ui.Modal, title="Réglages de Détection"):
    def __init__(self, view: "SecurLayoutView", module_name: str):
        super().__init__()
        self.view = view
        self.module_name = module_name
        
        conf = self.view.db["config"][module_name]
        
        self.s = ui.TextInput(label="Nombre d'actions maximum", default=str(conf.get("seuil", 5)), required=True)
        self.add_item(self.s)
        
        if "temps" in MODULES_DATA[module_name]["def"]:
            self.t = ui.TextInput(label="Dans un intervalle de (secondes)", default=str(conf.get("temps", 60)), required=True)
            self.add_item(self.t)
        else:
            self.t = None

    async def on_submit(self, interaction: discord.Interaction):
        try:
            self.view.db["config"][self.module_name]["seuil"] = int(self.s.value)
            if self.t:
                self.view.db["config"][self.module_name]["temps"] = int(self.t.value)
            
            secur_db.save(self.view.guild.id, self.view.db)
            self.view.status_message = f"{E_ON} Seuils de détection mis à jour avec succès."
            await self.view._refresh(interaction)
        except ValueError:
            if not interaction.response.is_done(): await interaction.response.defer()
            await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, les valeurs doivent être des nombres entiers.", delete_after=6)


# ==============================================================================
# --- INTERFACE UTILISATEUR (Layout V2) ---
# ==============================================================================
class SecurLayoutView(ui.LayoutView):
    """Panneau V2 gérant la sécurité avec navigation au sommet."""
    def __init__(self, cog: "ConfigSecurCog", guild: discord.Guild, user: discord.Member):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild = guild
        self.user = user
        self.db = secur_db.load(guild.id)
        self.current_page = "main"
        self.status_message = ""
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            if not interaction.response.is_done(): await interaction.response.defer()
            await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, cette console est protégée par {self.user.mention}.", delete_after=6)
            return False
        return True

    def _build(self):
        log_sys("BUILD", f"Construction de la vue (Page: {self.current_page})")
        self.clear_items()
        
        accent_color = 0x2b2d31
        footer_text = ""
        if HAS_VAX_CORE and config_manager:
            try:
                theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.cog.bot)
                accent_color = int(theme.get("color", 0x2b2d31))
                footer_text = theme.get("footer_text", "")
            except Exception as e:
                log_sys("THEME_ERR", f"Erreur thème: {e}", is_error=True)

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)

        # 1. NOTIFICATIONS
        container.add_item(ui.TextDisplay(f"# {E_SHIELD} Panel de Sécurité Intégrale"))
        if self.status_message:
            container.add_item(ui.TextDisplay(f"> {self.status_message}"))
            self.status_message = ""

        # 2. SÉLECTEUR DE NAVIGATION (TOUT EN HAUT)
        nav_options = []
        for p in PAGES_ORDER:
            if p == "main":
                nav_options.append(discord.SelectOption(label="Sommaire Global", value="main", emoji=E_HOME, default=(self.current_page == "main")))
            elif p == "whitelist":
                nav_options.append(discord.SelectOption(label="Whitelist (Immunisés)", value="whitelist", emoji=E_STAR, default=(self.current_page == "whitelist")))
            else:
                is_on = self.db["config"].get(p, {}).get("actif", False)
                emo = E_ON if is_on else E_OFF
                nav_options.append(discord.SelectOption(
                    label=p.capitalize(), 
                    value=p, 
                    emoji=emo, 
                    description=MODULES_DATA[p]["desc"][:100],
                    default=(self.current_page == p)
                ))

        nav_row = ui.ActionRow()
        nav_select = ui.Select(placeholder="Naviguer vers un module de sécurité...", min_values=1, max_values=1, options=nav_options)
        nav_select.callback = self._on_nav_select
        nav_row.add_item(nav_select)
        container.add_item(nav_row)
        
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

        # 3. ROUTAGE DU CONTENU
        if self.current_page == "main":
            self._build_main(container)
        elif self.current_page == "whitelist":
            self._build_whitelist(container)
        else:
            self._build_module(container)

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

    # --- SOUS-PAGES ---

    def _build_main(self, container: ui.Container):
        desc = (
            "Ce système de pointe protège votre serveur contre les raids, les spams et les abus administratifs.\n\n"
            "**Comment configurer :**\n"
            f"{E_N1} Utilisez le menu déroulant ci-dessus pour parcourir les modules.\n"
            f"{E_N2} Activez le module souhaité.\n"
            f"{E_N3} Réglez le seuil (ex: 5 bans en 60s) et la sentence.\n\n"
            "**État global des modules :**\n"
        )
        
        for m, info in MODULES_DATA.items():
            state = E_ON if self.db["config"].get(m, {}).get("actif") else E_OFF
            desc += f"{state} `{m.upper()}` : {info['desc']}\n"
            
        container.add_item(ui.TextDisplay(desc))

    def _build_whitelist(self, container: ui.Container):
        desc = f"### {E_STAR} Entités immunisées\nLes utilisateurs, rôles ou bots ci-dessous ignorent les protections du système.\n\n"
        
        roles_list, users_list, bots_list = [], [], []
        
        for item in self.db.get("whitelist", []):
            t_id = item['id']
            t_type = item['type']
            
            if t_type == "Rôle": roles_list.append(f"- <@&{t_id}> | ID : `{t_id}`")
            elif t_type == "Bot": bots_list.append(f"- <@{t_id}> | ID : `{t_id}`")
            else: users_list.append(f"- <@{t_id}> | ID : `{t_id}`")

        desc += f"**{E_ROLE} Rôles Whitelist**\n" + ("\n".join(roles_list) if roles_list else "*Aucun rôle*\n")
        desc += f"\n**{E_USER} Utilisateurs Whitelist**\n" + ("\n".join(users_list) if users_list else "*Aucun utilisateur*\n")
        desc += f"\n**{E_BOT} Bots Whitelist**\n" + ("\n".join(bots_list) if bots_list else "*Aucun bot*\n")

        container.add_item(ui.TextDisplay(desc))

        # Outils Whitelist (Un select par ligne pour respecter l'UI V2)
        user_row = ui.ActionRow()
        user_sel = ui.UserSelect(placeholder="Ajouter/Retirer Utilisateur ou Bot...")
        user_sel.callback = self._on_user_select
        user_row.add_item(user_sel)
        container.add_item(user_row)

        role_row = ui.ActionRow()
        role_sel = ui.RoleSelect(placeholder="Ajouter/Retirer Rôle...")
        role_sel.callback = self._on_role_select
        role_row.add_item(role_sel)
        container.add_item(role_row)

        action_row = ui.ActionRow()
        btn_id = ui.Button(label="Saisie ID Manuelle", style=discord.ButtonStyle.primary, emoji=E_ID)
        btn_id.callback = self._on_manual_id
        action_row.add_item(btn_id)

        btn_clear = ui.Button(label="Vider la liste", style=discord.ButtonStyle.danger, emoji=E_TRASH)
        btn_clear.callback = self._on_clear_whitelist
        action_row.add_item(btn_clear)
        container.add_item(action_row)

    def _build_module(self, container: ui.Container):
        m_name = self.current_page
        m_info = MODULES_DATA[m_name]
        conf = self.db["config"][m_name]
        
        is_active = conf["actif"]
        status_txt = f"{E_ON} **Activé**" if is_active else f"{E_OFF} **Désactivé**"

        desc = f"**Mission :** {m_info['desc']}\n**État :** {status_txt}\n\n"
        
        if m_name == "bot":
            desc += f"- **Action sur le Bot :** `{conf.get('action_bot', 'Kick')}`\n"
            desc += f"- **Action sur l'inviteur :** `{conf.get('action_user', 'Dérank')}`"
        else:
            desc += f"- **Punition :** `{conf.get('action', 'Dérank')}`\n"
            if "seuil" in conf:
                desc += f"- **Détection :** {conf['seuil']} actions en {conf.get('temps', '∞')} secondes."
                
        container.add_item(ui.TextDisplay(f"### {m_info['emoji']} Module : {m_name.upper()}\n{desc}"))

        # Contrôles du module
        ctrl_row = ui.ActionRow()
        
        btn_toggle = ui.Button(
            label="Désactiver" if is_active else "Activer", 
            style=discord.ButtonStyle.danger if is_active else discord.ButtonStyle.success,
            emoji=E_OFF if is_active else E_ON
        )
        btn_toggle.callback = self._on_toggle_module
        ctrl_row.add_item(btn_toggle)

        if "seuil" in conf:
            btn_seuil = ui.Button(label="Paramétrer Seuils", style=discord.ButtonStyle.primary, emoji=E_TIME)
            btn_seuil.callback = self._on_seuil_config
            ctrl_row.add_item(btn_seuil)
            
        container.add_item(ctrl_row)

        # Sélecteurs d'actions (un Select par ActionRow)
        if m_name == "bot":
            r1 = ui.ActionRow()
            s_b = ui.Select(placeholder=f"Punition Bot : {conf.get('action_bot', 'Kick')}", options=[
                discord.SelectOption(label="Kick", value="bot_Kick"), discord.SelectOption(label="Ban", value="bot_Ban")
            ])
            s_b.callback = self._on_bot_punish_select
            r1.add_item(s_b)
            container.add_item(r1)

            r2 = ui.ActionRow()
            s_u = ui.Select(placeholder=f"Punition User : {conf.get('action_user', 'Dérank')}", options=[
                discord.SelectOption(label="Dérank", value="user_Dérank"), discord.SelectOption(label="Kick", value="user_Kick"), discord.SelectOption(label="Ban", value="user_Ban")
            ])
            s_u.callback = self._on_bot_punish_select
            r2.add_item(s_u)
            container.add_item(r2)
            
        else:
            choices = ["Dérank", "Kick", "Ban"]
            if m_name in ["link", "anti_mention"]: choices.append("Mute")
            if m_name == "deco": choices.append("Alerte")
            
            act_row = ui.ActionRow()
            sel = ui.Select(placeholder=f"Action : {conf.get('action', 'Dérank')}", options=[discord.SelectOption(label=c, value=c) for c in choices])
            sel.callback = self._on_action_select
            act_row.add_item(sel)
            container.add_item(act_row)

    # --- CALLBACKS DE NAVIGATION & CONFIG ---

    async def _on_nav_select(self, interaction: discord.Interaction):
        self.current_page = interaction.data["values"][0]
        self.status_message = ""
        await self._refresh(interaction)

    async def _on_toggle_module(self, interaction: discord.Interaction):
        if interaction.user.id != self.guild.owner_id:
            if not interaction.response.is_done(): await interaction.response.defer()
            return await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, seul le propriétaire du serveur peut activer/désactiver les modules.", delete_after=6)
            
        self.db["config"][self.current_page]["actif"] = not self.db["config"][self.current_page]["actif"]
        secur_db.save(self.guild.id, self.db)
        state = "activé" if self.db["config"][self.current_page]["actif"] else "désactivé"
        self.status_message = f"{E_ON} Module `{self.current_page.upper()}` {state}."
        await self._refresh(interaction)

    async def _on_seuil_config(self, interaction: discord.Interaction):
        if interaction.user.id != self.guild.owner_id:
            if not interaction.response.is_done(): await interaction.response.defer()
            return await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, seul le propriétaire du serveur peut modifier les seuils.", delete_after=6)
            
        await interaction.response.send_modal(SeuilModal(self, self.current_page))

    async def _on_action_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.guild.owner_id:
            if not interaction.response.is_done(): await interaction.response.defer()
            return await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, seul le propriétaire du serveur peut modifier les sanctions.", delete_after=6)

        self.db["config"][self.current_page]["action"] = interaction.data['values'][0]
        secur_db.save(self.guild.id, self.db)
        self.status_message = f"{E_ON} Sanction mise à jour avec succès."
        await self._refresh(interaction)

    async def _on_bot_punish_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.guild.owner_id:
            if not interaction.response.is_done(): await interaction.response.defer()
            return await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, seul le propriétaire peut modifier les sanctions.", delete_after=6)

        val = interaction.data['values'][0]
        if val.startswith("bot_"):
            self.db["config"]["bot"]["action_bot"] = val.replace("bot_", "")
        else:
            self.db["config"]["bot"]["action_user"] = val.replace("user_", "")
            
        secur_db.save(self.guild.id, self.db)
        self.status_message = f"{E_ON} Punition Anti-Bot mise à jour."
        await self._refresh(interaction)

    # --- CALLBACKS WHITELIST ---

    def _toggle_whitelist_id(self, target_id: int, t_type: str) -> str:
        existing = [x['id'] for x in self.db["whitelist"]]
        if target_id in existing:
            self.db["whitelist"] = [x for x in self.db["whitelist"] if x['id'] != target_id]
            return "retiré(e) de"
        else:
            self.db["whitelist"].append({"id": target_id, "type": t_type})
            return "ajouté(e) à"

    async def _on_user_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.guild.owner_id:
            if not interaction.response.is_done(): await interaction.response.defer()
            return await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, seul le propriétaire gère la Whitelist.", delete_after=6)

        t_id = int(interaction.data['values'][0])
        user = self.guild.get_member(t_id)
        if not user:
            try: user = await self.cog.bot.fetch_user(t_id)
            except: pass
            
        t_type = "Bot" if user and user.bot else "Membre"
        action = self._toggle_whitelist_id(t_id, t_type)
        secur_db.save(self.guild.id, self.db)
        self.status_message = f"{E_ON} Utilisateur/Bot `{t_id}` {action} la Whitelist."
        await self._refresh(interaction)

    async def _on_role_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.guild.owner_id:
            if not interaction.response.is_done(): await interaction.response.defer()
            return await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, seul le propriétaire gère la Whitelist.", delete_after=6)

        t_id = int(interaction.data['values'][0])
        action = self._toggle_whitelist_id(t_id, "Rôle")
        secur_db.save(self.guild.id, self.db)
        self.status_message = f"{E_ON} Rôle `{t_id}` {action} la Whitelist."
        await self._refresh(interaction)

    async def _on_manual_id(self, interaction: discord.Interaction):
        if interaction.user.id != self.guild.owner_id:
            if not interaction.response.is_done(): await interaction.response.defer()
            return await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, seul le propriétaire gère la Whitelist.", delete_after=6)

        await interaction.response.send_modal(ManualIDModal(self))

    async def _on_clear_whitelist(self, interaction: discord.Interaction):
        if interaction.user.id != self.guild.owner_id:
            if not interaction.response.is_done(): await interaction.response.defer()
            return await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, seul le propriétaire gère la Whitelist.", delete_after=6)

        self.db["whitelist"] = []
        secur_db.save(self.guild.id, self.db)
        self.status_message = f"{E_ON} La Whitelist a été entièrement purgée."
        await self._refresh(interaction)


# ==============================================================================
# --- COG PRINCIPAL ---
# ==============================================================================
class ConfigSecurCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log_sys("INIT", "Module Sécurité V3 déployé.")

    @perm_command(level=2) # Verrouillage métier via la config_perm
    @commands.command(name="secur", description="Ouvrir le panel de sécurité intégrale.")
    async def secur_cmd(self, ctx: commands.Context):
        log_sys("CMD_CALL", f"Commande /secur déclenchée par {ctx.author.name}")
        
        if not ctx.guild:
            await ctx.send(f"{E_OFF} Cette commande exige un contexte de serveur.")
            return

        # Autorisation d'accès contrôlée si HAS_VAX_CORE, sinon accès basique admin
        if HAS_VAX_CORE:
            if not await ensure_command_permission(ctx, command_name="secur"):
                log_sys("CMD_DENY", f"Accès refusé par ensure_command_permission pour {ctx.author.name}")
                return
        else:
            if not ctx.author.guild_permissions.administrator:
                await ctx.send(f"{E_OFF} Permissions administrateur requises.")
                return
            
        log_sys("CMD_APPROVE", f"Interface /secur déployée pour {ctx.author.name}")
        view = SecurLayoutView(self, ctx.guild, ctx.author)
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    if bot.get_command("secur"):
        bot.remove_command("secur")
    await bot.add_cog(ConfigSecurCog(bot))