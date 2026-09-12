import discord
from discord import ui, app_commands
from discord.ext import commands, tasks
import asyncio
import time
import traceback
from pathlib import Path

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
E_BACK = getattr(E, 'RETOUR', "↩️") if HAS_VAX_CORE else "↩️"
E_FOLDER = getattr(E, 'DOCUMENT', "📁") if HAS_VAX_CORE else "📁"
E_TEXT = getattr(E, 'MEMO', "📝") if HAS_VAX_CORE else "📝"
E_MIC = getattr(E, 'MICRO', "🎤") if HAS_VAX_CORE else "🎤"
E_MSG = getattr(E, 'MESSAGE', "💬") if HAS_VAX_CORE else "💬"
E_HAMMER = getattr(E, 'MARTEAU', "🔨") if HAS_VAX_CORE else "🔨"
E_SERVER = getattr(E, 'SERVEUR', "⚙️") if HAS_VAX_CORE else "⚙️"
E_USER = getattr(E, 'PROFIL', "👤") if HAS_VAX_CORE else "👤"
E_SOUND = getattr(E, 'VOCAL', "🔊") if HAS_VAX_CORE else "🔊"
E_DOOR = getattr(E, 'PORTE', "🚪") if HAS_VAX_CORE else "🚪"
E_ARROW_LR = getattr(E, 'FLECHE_DOUBLE', "↔️") if HAS_VAX_CORE else "↔️"
E_ARROW_L = getattr(E, 'FLECHE_GAUCHE', "⬅️") if HAS_VAX_CORE else "⬅️"
E_ARROW_R = getattr(E, 'FLECHE_DROITE', "➡️") if HAS_VAX_CORE else "➡️"
E_MUTE = getattr(E, 'MUTE', "🔇") if HAS_VAX_CORE else "🔇"
E_DEAF = getattr(E, 'CASQUE', "🔕") if HAS_VAX_CORE else "🔕"
E_CAM = getattr(E, 'CAMERA', "📹") if HAS_VAX_CORE else "📹"
E_STREAM = getattr(E, 'ECRAN', "🖥️") if HAS_VAX_CORE else "🖥️"
E_LINK = getattr(E, 'LIEN', "🔗") if HAS_VAX_CORE else "🔗"
E_REFRESH = getattr(E, 'RAFRAICHIR', "🔄") if HAS_VAX_CORE else "🔄"
E_BAN = getattr(E, 'BAN', "🚫") if HAS_VAX_CORE else "🚫"
E_POLICE = getattr(E, 'AUTORITE', "👮") if HAS_VAX_CORE else "👮"
E_KICK = getattr(E, 'KICK', "👢") if HAS_VAX_CORE else "👢"
E_HOURGLASS = getattr(E, 'TEMPS', "⏳") if HAS_VAX_CORE else "⏳"
E_MAGIC = getattr(E, 'ETOILE', "✨") if HAS_VAX_CORE else "✨"
E_TRASH = getattr(E, 'SUPPRIMER', "🗑️") if HAS_VAX_CORE else "🗑️"
E_CHAN = getattr(E, 'LIEN', "📍") if HAS_VAX_CORE else "📍"
E_ID = getattr(E, 'IDENTIFIANT', "🆔") if HAS_VAX_CORE else "🆔"
E_ROLE = getattr(E, 'ROLE', "🎭") if HAS_VAX_CORE else "🎭"
E_ADD = getattr(E, 'AJOUTER', "➕") if HAS_VAX_CORE else "➕"

# Mapping des catégories de logs pour l'UI
LOG_CATEGORIES = {
    "vocal": {"label": "Logs Vocaux", "emoji": E_MIC, "desc": "Connexions, déplacements, sourdines, caméras."},
    "messages": {"label": "Logs Messages", "emoji": E_MSG, "desc": "Messages supprimés et historique des modifications."},
    "moderation": {"label": "Logs Modération", "emoji": E_HAMMER, "desc": "Bannissements, exclusions, kicks manuels."},
    "server": {"label": "Logs Serveur", "emoji": E_SERVER, "desc": "Modifications des salons, rôles et paramètres du serveur."}
}

# ==============================================================================
# --- UTILITAIRES DE LOGS ---
# ==============================================================================
def log_sys(action: str, message: str, is_error: bool = False):
    """Console experte avec colorisation ANSI obéissant aux filtres globaux."""
    if ERROR_LOGS_ONLY and not is_error: return
    if not DEBUG_LOGS and not is_error: return

    COLOR_RESET = "\033[0m"
    COLOR_INFO = "\033[96m"   # Cyan
    COLOR_SUCCESS = "\033[92m" # Vert
    COLOR_ERROR = "\033[91m"   # Rouge

    color = COLOR_ERROR if is_error else COLOR_INFO
    prefix = "[ERREUR LogsSys]" if is_error else "[INFO LogsSys]"
    print(f"{color}{prefix} [{action}] {message}{COLOR_RESET}")

# ==============================================================================
# --- GESTIONNAIRE DE DONNÉES (DataManager) ---
# ==============================================================================
class LogsManager:
    """Interface de sauvegarde s'appuyant sur l'infrastructure standard."""
    def __init__(self):
        if HAS_VAX_CORE:
            self.data = DataManager("staff/configuration/data_logs")
            try:
                Path("data/staff/configuration/data_logs").mkdir(parents=True, exist_ok=True)
            except Exception as e:
                log_sys("MKDIR_ERR", f"Erreur de création de l'arborescence: {e}", is_error=True)
        else:
            log_sys("INIT", "DataManager introuvable. Échec système.", is_error=True)

    def load(self, guild_id: int) -> dict:
        try:
            raw = self.data.load(guild_id) or {}
            if "categories" not in raw:
                raw["categories"] = {}
            for cat in LOG_CATEGORIES.keys():
                if cat not in raw["categories"]:
                    raw["categories"][cat] = {"active": False, "channel": None}
            return raw
        except Exception as e:
            log_sys("DB_LOAD", f"Erreur de lecture DB pour {guild_id}: {e}", is_error=True)
            return {"categories": {}}

    def save(self, guild_id: int, config: dict):
        try:
            self.data.save(guild_id, config)
        except Exception as e:
            log_sys("DB_SAVE_ERR", f"Erreur d'écriture DB pour {guild_id}: {e}", is_error=True)

logs_db = LogsManager()


# ==============================================================================
# --- MODALS UTILISATEUR ---
# ==============================================================================
class LogsChannelModal(ui.Modal, title="Lier par ID de Salon"):
    id_input = ui.TextInput(label="ID du Salon", placeholder="Collez l'ID ici...", min_length=15, max_length=25)
    
    def __init__(self, view: "LogsAdminLayoutView", category: str):
        super().__init__()
        self.view = view
        self.category = category

    async def on_submit(self, interaction: discord.Interaction):
        raw_id = self.id_input.value.strip()
        if not raw_id.isdigit():
            return await interaction.response.send_message(f"{E_OFF} L'ID fourni n'est pas un nombre valide.", ephemeral=True)
            
        target = interaction.guild.get_channel(int(raw_id))
        if not target or target.type not in {discord.ChannelType.text, discord.ChannelType.news}:
            return await interaction.response.send_message(f"{E_OFF} Salon textuel introuvable.", ephemeral=True)

        conf = logs_db.load(self.view.guild.id)
        
        if self.category == "all":
            for cat_key in LOG_CATEGORIES.keys():
                conf["categories"][cat_key]["channel"] = target.id
                conf["categories"][cat_key]["active"] = True
            self.view.status_message = f"{E_ON} Salon cible défini et activé pour **toutes les catégories**."
        else:
            conf["categories"][self.category]["channel"] = target.id
            conf["categories"][self.category]["active"] = True
            self.view.status_message = f"{E_ON} Salon cible mis à jour et catégorie activée."
            
        logs_db.save(self.view.guild.id, conf)
        
        self.view.state = "main"
        self.view.selected_category = None
        await self.view._refresh(interaction)


# ==============================================================================
# --- INTERFACE D'ADMINISTRATION (Layout V2) ---
# ==============================================================================
class LogsAdminLayoutView(ui.LayoutView):
    """Panneau de contrôle V2 pour la gestion dynamique des canaux de logs."""
    def __init__(self, cog: "LogsCog", guild: discord.Guild, user: discord.Member):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild = guild
        self.user = user
        self.state = "main" # 'main' ou 'edit_category'
        self.selected_category = None
        self.status_message = ""
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            if not interaction.response.is_done(): await interaction.response.defer()
            await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, cette console est protégée.", delete_after=6)
            return False
        return True

    def _build(self):
        self.clear_items()
        config = logs_db.load(self.guild.id)
        
        accent_color = 0x2b2d31
        footer_text = ""
        if HAS_VAX_CORE and config_manager:
            try:
                theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.cog.bot)
                accent_color = int(theme.get("color", 0x2b2d31))
                footer_text = theme.get("footer_text", "")
            except Exception as e:
                log_sys("THEME_ERR", f"Erreur chargement thème: {e}", is_error=True)

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        
        if self.status_message:
            container.add_item(ui.TextDisplay(f"> {self.status_message}"))
            self.status_message = ""

        if self.state == "main":
            self._build_main(container, config)
        elif self.state == "edit_category":
            self._build_edit_category(container, config)

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

    def _build_main(self, container: ui.Container, config: dict):
        container.add_item(ui.TextDisplay(f"# {E_GEAR} Centre de Contrôle des Logs"))
        container.add_item(ui.TextDisplay(
            "Sélectionnez une catégorie de logs ci-dessous pour l'activer et lui assigner un salon.\n"
            "Vous pouvez assigner plusieurs catégories au même salon pour les regrouper."
        ))

        # Affichage de l'état actuel des catégories
        status_lines = []
        for cat_key, info in LOG_CATEGORIES.items():
            cat_cfg = config["categories"][cat_key]
            is_active = bool(cat_cfg.get("channel"))
            state = E_ON if is_active else E_OFF
            chan_txt = f"<#{cat_cfg['channel']}>" if is_active else "`Désactivé`"
            status_lines.append(f"{state} **{info['label']}** : {chan_txt}")
        
        container.add_item(ui.TextDisplay(f"### État du Système\n" + "\n".join(status_lines)))

        # Sélecteur de navigation
        nav_row = ui.ActionRow()
        
        # Option Globale (Toutes les catégories)
        options = [discord.SelectOption(label="Toutes les catégories (Global)", value="all", emoji=E_FOLDER, description="Définir un salon unique pour tous les logs")]
        
        # Options individuelles
        for cat_key, info in LOG_CATEGORIES.items():
            options.append(discord.SelectOption(label=info["label"], value=cat_key, emoji=info["emoji"], description=info["desc"][:100]))
        
        sel = ui.Select(placeholder="Configurer les logs...", options=options)
        sel.callback = self._on_category_select
        nav_row.add_item(sel)
        container.add_item(nav_row)

    def _build_edit_category(self, container: ui.Container, config: dict):
        cat = self.selected_category
        is_global = (cat == "all")

        if is_global:
            container.add_item(ui.TextDisplay(f"# {E_SERVER} Configuration Globale"))
            container.add_item(ui.TextDisplay("Définissez un salon unique pour **toutes les catégories** de logs. Cela activera automatiquement toutes les catégories vers ce salon."))
        else:
            cat_info = LOG_CATEGORIES[cat]
            cat_cfg = config["categories"][cat]
            
            container.add_item(ui.TextDisplay(f"# {cat_info['emoji']} Configuration : {cat_info['label']}"))
            
            is_active = bool(cat_cfg.get("channel"))
            state_txt = f"{E_ON} `Activé`" if is_active else f"{E_OFF} `Désactivé`"
            chan_txt = f"<#{cat_cfg['channel']}>" if is_active else "`Désactivé`"
            
            container.add_item(ui.TextDisplay(
                f"**Description :** {cat_info['desc']}\n"
                f"**État :** {state_txt}\n"
                f"**Salon d'ancrage :** {chan_txt}\n\n"
                "Sélectionnez ou générez un salon ci-dessous pour activer la catégorie."
            ))

        # Sélecteur de salon
        chan_row = ui.ActionRow()
        chan_sel = ui.ChannelSelect(
            placeholder="Sélectionnez le salon cible...", 
            channel_types=[discord.ChannelType.text, discord.ChannelType.news],
            min_values=1, max_values=1
        )
        chan_sel.callback = self._on_channel_select
        chan_row.add_item(chan_sel)
        container.add_item(chan_row)

        # Boutons d'action
        act_row = ui.ActionRow()
        
        btn_id = ui.Button(label="Lier par ID", style=discord.ButtonStyle.secondary, emoji=E_ID)
        btn_id.callback = self._on_chan_id_manual
        act_row.add_item(btn_id)
        
        btn_auto = ui.Button(label="Générer", style=discord.ButtonStyle.primary, emoji=E_ADD)
        btn_auto.callback = self._on_chan_auto_create
        act_row.add_item(btn_auto)

        if is_global:
            btn_disable_all = ui.Button(label="Tout Désactiver", style=discord.ButtonStyle.danger, emoji=E_TRASH)
            btn_disable_all.callback = self._on_disable_all
            act_row.add_item(btn_disable_all)
        else:
            cat_cfg = config["categories"][cat]
            if cat_cfg.get("channel"):
                btn_remove = ui.Button(
                    label="Désactiver",
                    style=discord.ButtonStyle.danger,
                    emoji=E_TRASH
                )
                btn_remove.callback = self._on_remove_channel
                act_row.add_item(btn_remove)

        btn_back = ui.Button(label="Retour", style=discord.ButtonStyle.secondary, emoji=E_BACK)
        btn_back.callback = lambda i: self._change_state(i, "main")
        act_row.add_item(btn_back)
        
        container.add_item(act_row)

    async def _change_state(self, interaction: discord.Interaction, new_state: str):
        self.state = new_state
        self.status_message = ""
        await self._refresh(interaction)

    async def _on_category_select(self, interaction: discord.Interaction):
        self.selected_category = interaction.data["values"][0]
        await self._change_state(interaction, "edit_category")

    async def _on_channel_select(self, interaction: discord.Interaction):
        chan_id = interaction.data["values"][0]
        config = logs_db.load(self.guild.id)
        
        if self.selected_category == "all":
            for cat_key in LOG_CATEGORIES.keys():
                config["categories"][cat_key]["channel"] = int(chan_id)
                config["categories"][cat_key]["active"] = True
            self.status_message = f"{E_ON} Salon cible défini et activé pour **toutes les catégories**."
        else:
            config["categories"][self.selected_category]["channel"] = int(chan_id)
            config["categories"][self.selected_category]["active"] = True
            self.status_message = f"{E_ON} Salon cible défini et catégorie activée."
            
        logs_db.save(self.guild.id, config)
        self.state = "main"
        self.selected_category = None
        await self._refresh(interaction)

    async def _on_chan_id_manual(self, interaction: discord.Interaction):
        await interaction.response.send_modal(LogsChannelModal(self, self.selected_category))

    async def _on_chan_auto_create(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer()
            
        overwrites = {
            self.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            self.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, embed_links=True)
        }
        
        cat = self.selected_category
        name_map = {
            "all": f"📁│𝐥𝐨𝐠𝐬-𝐠𝐥𝐨𝐛𝐚𝐥",
            "vocal": f"🎤│𝐥𝐨𝐠𝐬-𝐯𝐨𝐜𝐚𝐮𝐱",
            "messages": f"💬│𝐥𝐨𝐠𝐬-𝐦𝐞𝐬𝐬𝐚𝐠𝐞𝐬",
            "moderation": f"🔨│𝐥𝐨𝐠𝐬-𝐦𝐨𝐝𝐞𝐫𝐚𝐭𝐢𝐨𝐧",
            "server": f"⚙️│𝐥𝐨𝐠𝐬-𝐬𝐞𝐫𝐯𝐞𝐮𝐫"
        }
        
        try:
            channel = await self.guild.create_text_channel(name_map[cat], overwrites=overwrites)
            conf = logs_db.load(self.guild.id)
            
            if cat == "all":
                for c in LOG_CATEGORIES:
                    conf["categories"][c]["channel"] = channel.id
                    conf["categories"][c]["active"] = True
            else:
                conf["categories"][cat]["channel"] = channel.id
                conf["categories"][cat]["active"] = True
            
            logs_db.save(self.guild.id, conf)
            self.status_message = f"{E_ON} Salon généré avec succès."
        except Exception as e:
            self.status_message = f"{E_OFF} Impossible de créer le salon : {e}"
            
        self.state = "main"
        self.selected_category = None
        await self._refresh(interaction)

    async def _on_remove_channel(self, interaction: discord.Interaction):
        config = logs_db.load(self.guild.id)
        cat_cfg = config["categories"][self.selected_category]
        cat_cfg["channel"] = None
        cat_cfg["active"] = False
        logs_db.save(self.guild.id, config)
        self.status_message = f"{E_TRASH} Le salon a été retiré et la catégorie désactivée."
        self.state = "main"
        self.selected_category = None
        await self._refresh(interaction)

    async def _on_disable_all(self, interaction: discord.Interaction):
        config = logs_db.load(self.guild.id)
        for cat_key in LOG_CATEGORIES.keys():
            config["categories"][cat_key]["active"] = False
            config["categories"][cat_key]["channel"] = None
        logs_db.save(self.guild.id, config)
        self.status_message = f"{E_TRASH} Toutes les catégories ont été désactivées et détachées de leurs salons."
        self.state = "main"
        self.selected_category = None
        await self._refresh(interaction)


# ==============================================================================
# --- COG PRINCIPAL (Moteur des Logs) ---
# ==============================================================================
class LogsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.vocal_tracking = {} # Cache pour le temps en vocal
        self.msg_threads = {} # Cache pour les threads d'édition de messages
        log_sys("INIT", "Module Logs Unifié V3 déployé.")

    # --- MÉTHODE DE DISTRIBUTION DES LOGS (FULL LAYOUT V2) ---
    async def dispatch_log(self, guild: discord.Guild, category: str, title: str, description: str, color_hex: int, user: discord.User = None):
        """Dispatche le log en tant que LayoutV2 dans le canal assigné si actif."""
        config = logs_db.load(guild.id)
        cat_cfg = config.get("categories", {}).get(category)
        
        if not cat_cfg or not cat_cfg.get("channel"):
            return None
            
        channel = guild.get_channel(cat_cfg["channel"])
        if not channel:
            return None

        # Rendu natif V2 pour les logs (sans Embed)
        view = ui.LayoutView(timeout=1)
        container = ui.Container(accent_color=discord.Color(color_hex), spoiler=False)
        
        if user and hasattr(user, 'display_avatar'):
            try:
                container.add_item(ui.Section(
                    f"### {title}\n{description}", 
                    accessory=ui.Thumbnail(user.display_avatar.url, description=f"Avatar de {user.name}")
                ))
            except Exception:
                container.add_item(ui.TextDisplay(f"### {title}\n{description}"))
        else:
            container.add_item(ui.TextDisplay(f"### {title}\n{description}"))
            
        view.add_item(container)
        
        try:
            return await channel.send(view=view)
        except discord.Forbidden:
            log_sys("PERM_ERROR", f"Impossible d'envoyer le log dans le salon {channel.id}", is_error=True)
            return None
        except Exception as e:
            log_sys("SEND_ERR", f"Erreur de transmission: {e}", is_error=True)
            return None

    # ==============================================================================
    # 1. LOGS VOCAUX
    # ==============================================================================
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        guild = member.guild
        self.vocal_tracking.setdefault(member.id, {})
        now = time.time()

        # Join / Leave / Move
        if before.channel != after.channel:
            if before.channel is None:
                self.vocal_tracking[member.id]["join"] = now
                await self.dispatch_log(guild, "vocal", f"{E_SOUND} Connexion Vocal", f"**{member.mention}** a rejoint {after.channel.mention}", 0x43b581, member)
            elif after.channel is None:
                start = self.vocal_tracking[member.id].pop("join", now)
                dur = self._format_duration(now - start)
                await self.dispatch_log(guild, "vocal", f"{E_DOOR} Déconnexion Vocal", f"**{member.mention}** a quitté {before.channel.mention}\n> {E_HOURGLASS} Temps : `{dur}`", 0x95a5a6, member)
            else:
                await self.dispatch_log(guild, "vocal", f"{E_ARROW_LR} Déplacement Vocal", f"**{member.mention}** s'est déplacé.\n> {E_ARROW_L} De : {before.channel.mention}\n> {E_ARROW_R} Vers : {after.channel.mention}", 0x3498db, member)

        # Mute / Deafen Serveur
        if before.mute != after.mute:
            act = 'coupé' if after.mute else 'rétabli'
            await self.dispatch_log(guild, "vocal", f"{E_MUTE} Mute Serveur", f"Le micro de **{member.mention}** a été {act}.", 0xe67e22, member)
        elif before.deaf != after.deaf:
            act = 'activée' if after.deaf else 'retirée'
            await self.dispatch_log(guild, "vocal", f"{E_DEAF} Sourdine Serveur", f"La sourdine de **{member.mention}** a été {act}.", 0xe67e22, member)
            
        # Camera / Stream
        if before.self_video != after.self_video:
            act = 'allumé' if after.self_video else 'éteint'
            await self.dispatch_log(guild, "vocal", f"{E_CAM} Caméra", f"**{member.mention}** a {act} sa caméra.", 0x9b59b6, member)
        if before.self_stream != after.self_stream:
            act = 'lancé' if after.self_stream else 'arrêté'
            await self.dispatch_log(guild, "vocal", f"{E_STREAM} Stream", f"**{member.mention}** a {act} son partage d'écran.", 0x34495e, member)

    def _format_duration(self, delta: float) -> str:
        h, r = divmod(int(delta), 3600)
        m, s = divmod(r, 60)
        return f"{h}h {m}m {s}s" if h > 0 else f"{m}m {s}s"

    # ==============================================================================
    # 2. LOGS MESSAGES
    # ==============================================================================
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot: return
        
        # Identification par Audit Log si possible (Modération)
        performer = None
        await asyncio.sleep(0.8)
        try:
            async for entry in message.guild.audit_logs(limit=3, action=discord.AuditLogAction.message_delete):
                if entry.target.id == message.author.id and entry.extra.channel.id == message.channel.id:
                    performer = entry.user
                    break
        except Exception: pass

        content = message.content[:1500] if message.content else "*Fichier/Embed supprimé*"
        title = f"{E_HAMMER} Message Supprimé (Modération)" if performer else f"{E_TRASH} Message Supprimé"
        desc = f"{E_USER} **Auteur :** {message.author.mention}\n{E_CHAN} **Salon :** {message.channel.mention}"
        if performer: desc += f"\n{E_POLICE} **Supprimé par :** {performer.mention}"
        desc += f"\n\n**Contenu :**\n```\n{content}\n```"

        await self.dispatch_log(message.guild, "messages", title, desc, 0xff4757 if performer else 0x95a5a6, message.author)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or before.content == after.content: return

        if before.id not in self.msg_threads:
            desc = f"{E_USER} **Auteur :** {before.author.mention}\n{E_CHAN} **Salon :** {before.channel.mention}\n{E_LINK} [Aller au message]({after.jump_url})\n\n"
            desc += f"**Message original :**\n```\n{before.content[:1000] or 'Vide'}\n```\n*Le suivi des modifications continues est disponible dans le fil associé.*"
            
            log_msg = await self.dispatch_log(before.guild, "messages", f"{E_TEXT} Message Modifié", desc, 0xeaa14e, before.author)
            
            if log_msg:
                try:
                    thread = await log_msg.create_thread(name=f"Modifs - {before.author.name}", auto_archive_duration=60)
                    self.msg_threads[before.id] = thread
                    await thread.send(f"{E_REFRESH} **Nouvelle version :**\n```\n{after.content[:1900]}\n```")
                    self.bot.loop.create_task(self._cleanup_thread(before.id))
                except Exception: pass
        else:
            thread = self.msg_threads[before.id]
            try:
                await thread.send(f"{E_REFRESH} **Nouvelle modification :**\n```\n{after.content[:1900]}\n```")
            except discord.NotFound:
                self.msg_threads.pop(before.id, None)

    async def _cleanup_thread(self, msg_id: int):
        await asyncio.sleep(3600)
        self.msg_threads.pop(msg_id, None)

    # ==============================================================================
    # 3. LOGS MODÉRATION
    # ==============================================================================
    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        await asyncio.sleep(1)
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
            if entry.target.id == user.id and entry.user.id != self.bot.user.id:
                desc = f"{E_USER} **Cible :** {user.mention}\n{E_POLICE} **Modérateur :** {entry.user.mention}\n{E_TEXT} **Raison :** {entry.reason or 'Non spécifiée'}"
                await self.dispatch_log(guild, "moderation", f"{E_BAN} Ban Manuel", desc, 0xff4757, user)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await asyncio.sleep(1)
        async for entry in member.guild.audit_logs(limit=2, action=discord.AuditLogAction.member_kick):
            if entry.target.id == member.id and (discord.utils.utcnow() - entry.created_at).total_seconds() < 10:
                if entry.user.id == self.bot.user.id: return
                desc = f"{E_USER} **Cible :** {member.mention}\n{E_POLICE} **Modérateur :** {entry.user.mention}\n{E_TEXT} **Raison :** {entry.reason or 'Non spécifiée'}"
                await self.dispatch_log(member.guild, "moderation", f"{E_KICK} Kick Manuel", desc, 0xff9f43, member)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.timed_out_until != after.timed_out_until and after.timed_out_until:
            await asyncio.sleep(1)
            async for entry in after.guild.audit_logs(limit=2, action=discord.AuditLogAction.member_update):
                if entry.target.id == after.id and entry.user.id != self.bot.user.id:
                    desc = f"{E_USER} **Cible :** {after.mention}\n{E_POLICE} **Modérateur :** {entry.user.mention}\n{E_TEXT} **Raison :** {entry.reason or 'Non spécifiée'}"
                    await self.dispatch_log(after.guild, "moderation", f"{E_HOURGLASS} Exclusion Manuelle", desc, 0xe84118, after)

    # ==============================================================================
    # 4. LOGS SERVEUR
    # ==============================================================================
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        cat = channel.category.name if channel.category else "Aucune"
        desc = f"{E_CHAN} **Salon :** {channel.mention}\n{E_FOLDER} **Catégorie :** `{cat}`\n{E_ID} **ID :** `{channel.id}`"
        await self.dispatch_log(channel.guild, "server", f"{E_CHAN} Salon Créé", desc, 0x2ecc71)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        cat = channel.category.name if channel.category else "Aucune"
        desc = f"{E_TRASH} **Nom :** `#{channel.name}`\n{E_FOLDER} **Catégorie :** `{cat}`"
        await self.dispatch_log(channel.guild, "server", f"{E_TRASH} Salon Supprimé", desc, 0xe74c3c)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        desc = f"{E_MAGIC} **Rôle :** {role.mention}\n{E_ID} **ID :** `{role.id}`"
        await self.dispatch_log(role.guild, "server", f"{E_ROLE} Rôle Créé", desc, 0x2ecc71)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        desc = f"{E_TRASH} **Nom :** `{role.name}`"
        await self.dispatch_log(role.guild, "server", f"{E_ROLE} Rôle Supprimé", desc, 0xe74c3c)

    # ==============================================================================
    # --- COMMANDE D'ADMINISTRATION ---
    # ==============================================================================
    @perm_command(level=2) # Protection métier Vax V3
    @commands.hybrid_command(name="logs", description="Ouvrir le panneau de configuration des Logs.")
    async def logs_cmd(self, ctx: commands.Context):
        if not ctx.guild:
            await ctx.send(f"{E_OFF} Cette commande exige un contexte de serveur.")
            return

        if not await ensure_command_permission(ctx, command_name="logs"):
            return
            
        log_sys("CMD_INVOKE", f"Console /logs invoquée par {ctx.author.name}")
        view = LogsAdminLayoutView(self, ctx.guild, ctx.author)
        await ctx.send(view=view)

async def setup(bot: commands.Bot):
    if bot.get_command("logs"):
        bot.remove_command("logs")
    await bot.add_cog(LogsCog(bot))