import discord
from discord import ui
from discord.ext import commands, tasks
import time
import asyncio
from datetime import datetime
import traceback
from typing import Optional

# ==============================================================================
# --- IMPORTS MÉTIER VAX ---
# Intégration stricte de l'écosystème pour garantir l'homogénéité.
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
E_TEXT = getattr(E, 'MEMO', "📝") if HAS_VAX_CORE else "📝"
E_TIME = getattr(E, 'TEMPS', "⏳") if HAS_VAX_CORE else "⏳"
E_STATS = getattr(E, 'GRAPHIQUE', "📊") if HAS_VAX_CORE else "📊"
E_USER = getattr(E, 'PROFIL', "👤") if HAS_VAX_CORE else "👤"
E_BOT = getattr(E, 'VAX', "🤖") if HAS_VAX_CORE else "🤖"
E_ONLINE = getattr(E, 'STATUS_ONLINE', "🟢") if HAS_VAX_CORE else "🟢"
E_BOOST = getattr(E, 'BOOST', "💎") if HAS_VAX_CORE else "💎"
E_MIC = getattr(E, 'MICRO', "🎤") if HAS_VAX_CORE else "🎤"
E_MSG = getattr(E, 'MESSAGE', "💬") if HAS_VAX_CORE else "💬"
E_RECORD = getattr(E, 'HAUSSE', "📈") if HAS_VAX_CORE else "📈"
E_TROPHY = getattr(E, 'CLASSEMENT', "🏆") if HAS_VAX_CORE else "🏆"
E_STAR = getattr(E, 'EXCELLENT', "🌟") if HAS_VAX_CORE else "🌟"
E_BACK = getattr(E, 'RETOUR', "↩️") if HAS_VAX_CORE else "↩️"
E_TRASH = getattr(E, 'SUPPRIMER', "🗑️") if HAS_VAX_CORE else "🗑️"
E_CHAN = getattr(E, 'LIEN', "📍") if HAS_VAX_CORE else "📍"
E_ADD = getattr(E, 'AJOUTER', "➕") if HAS_VAX_CORE else "➕"
E_ID = getattr(E, 'IDENTIFIANT', "🆔") if HAS_VAX_CORE else "🆔"

# Emojis complémentaires
E_STREAM = getattr(E, 'ECRAN', "🖥️") if HAS_VAX_CORE else "🖥️"
E_CAM = getattr(E, 'CAMERA', "📹") if HAS_VAX_CORE else "📹"
E_MUTE = getattr(E, 'MUTE', "🔇") if HAS_VAX_CORE else "🔇"
E_DEAF = getattr(E, 'CASQUE', "🔕") if HAS_VAX_CORE else "🔕"
E_FIRE = getattr(E, 'FEU', "🔥") if HAS_VAX_CORE else "🔥"
E_ROCKET = getattr(E, 'FUSEE', "🚀") if HAS_VAX_CORE else "🚀"

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
    COLOR_ERROR = "\033[91m"   # Rouge
    color = COLOR_ERROR if is_error else COLOR_INFO
    prefix = "[ERREUR AutoStats]" if is_error else "[INFO AutoStats]"
    print(f"{color}{prefix} [{action}] {message}{COLOR_RESET}")

# ==============================================================================
# --- GESTIONNAIRE DE DONNÉES (DataManager) ---
# ==============================================================================
class AutoStatsManager:
    """Interface de sauvegarde s'appuyant sur l'infrastructure standard."""
    def __init__(self):
        if HAS_VAX_CORE:
            self.data = DataManager("staff/configuration/data_autostats")
        else:
            log_sys("INIT", "DataManager introuvable.", is_error=True)

    def _migrate(self, config: dict) -> dict:
        if 'records' not in config:
            config['records'] = {
                "members": {"value": 0, "date": "N/A"},
                "online": {"value": 0, "date": "N/A"},
                "vocal": {"value": config.pop('vocal_record', 0), "date": "N/A"},
                "boosts": {"value": 0, "date": "N/A"},
                "msg_24h": {"value": 0, "date": "N/A"},
                "msg_week": {"value": 0, "date": "N/A"},
                "msg_month": {"value": 0, "date": "N/A"}
            }
        if 'msg_history' not in config:
            config['msg_history'] = {"daily": {}, "weekly": {}, "monthly": {}}
            
        if 'user_activity' not in config:
            now = datetime.now()
            config['user_activity'] = {
                "voice_all_time": {}, 
                "msg": {
                    "date_day": now.strftime("%Y-%m-%d"), "daily": {},
                    "date_week": now.strftime("%Y-W%W"), "weekly": {},
                    "date_month": now.strftime("%Y-%m"), "monthly": {}
                }
            }
        return config

    def load(self, guild_id: int) -> dict:
        default = {
            'ch_stats_text': None,
            'last_msg_id': None,
            'delay': 300,
            'fields': [
                "total", "humans", "bots", "online_total", "vocal_total", 
                "record_vocal", "msg_24h", "msg_week", "msg_month"
            ]
        }
        try:
            raw = self.data.load(guild_id) or {}
            config = {**default, **raw}
            return self._migrate(config)
        except Exception:
            return self._migrate(default)

    def save(self, guild_id: int, config: dict):
        self.data.save(guild_id, config)

stats_db = AutoStatsManager()

# ==============================================================================
# --- DÉFINITIONS DES MÉTRIQUES ---
# ==============================================================================
DEMO_OPTIONS = [
    ("total", "Membres Total", "Membres du serveur", E_USER),
    ("humans", "Membres Humains", "Utilisateurs standards", E_USER),
    ("bots", "Membres Bots", "Applications", E_BOT),
    ("online_total", "En ligne Tous", "Membres connectés", E_ONLINE),
    ("online_humans", "En ligne Humains", "Utilisateurs connectés", E_ONLINE),
    ("online_bots", "En ligne Bots", "Bots en service", E_ONLINE),
    ("boosts", "Boosts", "Niveau et nombre de boosts", E_BOOST),
]

VOCAL_OPTIONS = [
    ("vocal_total", "En Vocal", "Dans les salons vocaux", E_MIC),
    ("vocal_stream", "Stream", "Partages d'écran actifs", E_STREAM),
    ("vocal_cam", "Caméra", "Webcams allumées", E_CAM),
    ("vocal_muted", "Muet", "Microphones coupés", E_MUTE),
    ("vocal_deaf", "Sourdine", "Casques coupés", E_DEAF),
    ("top_vocal", "Top Membre Vocal", "Membre avec le plus d'heures", E_STAR),
]

MSG_OPTIONS = [
    ("msg_24h", "Messages Aujourd'hui", "Aujourd'hui", E_MSG),
    ("msg_week", "Messages Semaine", "Cette semaine", E_MSG),
    ("msg_month", "Messages Mois", "Ce mois-ci", E_MSG),
    ("top_msg", "Top Membre Messages", "Membres les plus actifs", E_TROPHY),
]

RECORD_OPTIONS = [
    ("record_members", "Record Membres", "Pic historique de membres", E_RECORD),
    ("record_online", "Record En ligne", "Pic historique connectés", E_FIRE),
    ("record_vocal", "Record Vocal", "Pic historique en vocal", E_RECORD),
    ("record_boosts", "Record Boosts", "Pic historique de boosts", E_ROCKET),
    ("record_msg_24h", "Record Msg/Jour", "Meilleure journée", E_TROPHY),
    ("record_msg_week", "Record Msg/Semaine", "Meilleure semaine", E_TROPHY),
    ("record_msg_month", "Record Msg/Mois", "Meilleur mois", E_TROPHY),
]

# ==============================================================================
# --- MODALS UTILISATEUR ---
# ==============================================================================
class DelayModal(ui.Modal, title="Fréquence d'actualisation"):
    delay_input = ui.TextInput(label="Délai (ex: 30s, 5m, 2h)", placeholder="Ex: 5m", required=True)

    def __init__(self, view: "StatsConfigLayoutView"):
        super().__init__()
        self.view = view
        current_delay = self.view.config.get('delay', 300)
        self.delay_input.default = self.view.format_delay(current_delay)

    def parse_delay(self, val: str) -> int:
        val = val.strip().lower()
        if val.endswith("j"): return int(val[:-1]) * 86400
        if val.endswith("h"): return int(val[:-1]) * 3600
        if val.endswith("m"): return int(val[:-1]) * 60
        if val.endswith("s"): return int(val[:-1])
        return int(val)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            value = self.parse_delay(self.delay_input.value)
            if value < 30:
                self.view.status_message = f"{E_OFF} Le délai minimum est de 30 secondes (sécurité anti rate-limit)."
            else:
                self.view.config['delay'] = value
                stats_db.save(self.view.guild.id, self.view.config)
                self.view.status_message = f"{E_ON} La fréquence d'actualisation a été définie à **{self.delay_input.value}**."
        except ValueError:
            self.view.status_message = f"{E_OFF} Format invalide. Utilisez 's' pour secondes, 'm' pour minutes, 'h' pour heures."
        
        await self.view._refresh(interaction)

class StatsChannelModal(ui.Modal, title="Lier par ID de Salon"):
    id_input = ui.TextInput(label="ID du Salon", placeholder="Collez l'ID ici...", min_length=15, max_length=25)
    
    def __init__(self, view: "StatsConfigLayoutView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        raw_id = self.id_input.value.strip()
        if not raw_id.isdigit():
            return await interaction.response.send_message(f"{E_OFF} L'ID fourni n'est pas un nombre valide.", ephemeral=True)
            
        target = interaction.guild.get_channel(int(raw_id))
        if not target or target.type not in {discord.ChannelType.text, discord.ChannelType.news}:
            return await interaction.response.send_message(f"{E_OFF} Salon textuel introuvable.", ephemeral=True)

        self.view.config['ch_stats_text'] = target.id
        stats_db.save(self.view.guild.id, self.view.config)
        
        self.view.status_message = f"{E_ON} Salon d'affichage lié avec succès."
        self.view.active_sub_menu = None
        await self.view._refresh(interaction)


# ==============================================================================
# --- SELECTEURS D'OPTIONS ---
# ==============================================================================
class StatsOptionsSelect(ui.Select):
    def __init__(self, parent_view: "StatsConfigLayoutView"):
        self.parent_view = parent_view
        is_enabled = bool(self.parent_view.config.get('ch_stats_text'))
        
        options = [
            discord.SelectOption(label="Configurer le salon", value="channel", emoji=E_CHAN, description="Sélectionner, lier ou générer le salon d'affichage"),
            discord.SelectOption(label="Modifier la fréquence", value="delay", emoji=E_TIME, description="Changer le délai d'actualisation (ex: 5m)"),
            discord.SelectOption(label="Gérer l'affichage (Métriques)", value="manage_fields", emoji=E_GEAR, description="Choisir quelles statistiques afficher dans le salon"),
        ]
        if is_enabled:
            options.append(discord.SelectOption(label="Désactiver le module", value="reset", emoji=E_TRASH, description="Désactiver et retirer le salon"))
            
        super().__init__(placeholder="Options de configuration...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val == "channel":
            self.parent_view.active_sub_menu = "channel"
            await self.parent_view._refresh(interaction)
        elif val == "manage_fields":
            self.parent_view.active_sub_menu = "manage_fields"
            await self.parent_view._refresh(interaction)
        elif val == "delay":
            await self.parent_view._open_delay_modal(interaction)
        elif val == "reset":
            await self.parent_view._on_reset(interaction)


class StatsCategorySelect(ui.Select):
    """Sélecteur générique pour gérer les métriques par thème."""
    def __init__(self, parent_view: "StatsConfigLayoutView", placeholder: str, options_data: list, category_keys: list):
        self.parent_view = parent_view
        self.category_keys = category_keys
        current_fields = self.parent_view.config.get('fields', [])
        
        options = [
            discord.SelectOption(label=l, value=v, description=d, emoji=e, default=(v in current_fields))
            for v, l, d, e in options_data
        ]
        super().__init__(placeholder=placeholder, min_values=0, max_values=len(options), options=options)

    async def callback(self, interaction: discord.Interaction):
        current_set = set(self.parent_view.config.get('fields', []))
        
        # Nettoyage des anciennes valeurs de cette catégorie
        for k in self.category_keys:
            if k in current_set:
                current_set.remove(k)
                
        # Ajout des nouvelles
        for val in self.values:
            current_set.add(val)
            
        # Tri basique pour garder l'ordre d'origine
        all_keys = [x[0] for x in DEMO_OPTIONS + VOCAL_OPTIONS + MSG_OPTIONS + RECORD_OPTIONS]
        ordered_fields = [k for k in all_keys if k in current_set]
        
        self.parent_view.config['fields'] = ordered_fields
        stats_db.save(self.parent_view.guild.id, self.parent_view.config)
        
        self.parent_view.status_message = f"{E_ON} Métriques d'affichage mises à jour."
        await self.parent_view._refresh(interaction)


# ==============================================================================
# --- INTERFACE UTILISATEUR (Layout V2) ---
# ==============================================================================
class StatsConfigLayoutView(ui.LayoutView):
    def __init__(self, cog: "ServerStatsCog", guild: discord.Guild, config: dict, user: discord.Member):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild = guild
        self.config = config
        self.user = user
        self.status_message = ""
        self.active_sub_menu: str | None = None
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(f"{E_OFF} Action refusée : ce panneau appartient à {self.user.mention}.", ephemeral=True)
            return False
        return True

    def format_delay(self, delay: int) -> str:
        if delay % 86400 == 0: return f"{delay//86400}j"
        if delay % 3600 == 0: return f"{delay//3600}h"
        if delay % 60 == 0: return f"{delay//60}m"
        return f"{delay}s"

    def _build(self):
        self.clear_items()
        
        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.cog.bot)
        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text", "")

        is_enabled = bool(self.config.get('ch_stats_text')) and self.guild.get_channel(int(self.config['ch_stats_text'])) is not None
        state_text = f"{E_ON} `Activé`" if is_enabled else f"{E_OFF} `Désactivé`"
        chan_txt = f"<#{self.config['ch_stats_text']}>" if is_enabled else "`Désactivé`"
        delay_str = self.format_delay(self.config.get('delay', 300))

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {E_STATS} Configuration AutoStats"))
        
        if self.status_message:
            container.add_item(ui.TextDisplay(f"> {self.status_message}"))
            self.status_message = ""
        
        # --- APERÇU OU RÉSUMÉ ---
        if self.active_sub_menu == "manage_fields":
            container.add_item(ui.TextDisplay("## ── APERÇU EN DIRECT ──\n"))
            stats_data = self.cog.get_guild_stats(self.guild, self.config)
            layout_blocks = self.cog.build_stats_layout_blocks(stats_data, self.config.get('fields', []), guild=self.guild, use_mentions=False)
            
            if not layout_blocks:
                container.add_item(ui.TextDisplay("*Aucune donnée configurée pour l'affichage.*"))
            else:
                for block in layout_blocks:
                    container.add_item(ui.TextDisplay(block))
                    
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
        else:
            container.add_item(ui.TextDisplay(
                f"**État du système :** {state_text}\n"
                f"**Salon d'affichage :** {chan_txt}\n"
                f"**Fréquence d'actualisation :** `{delay_str}`\n\n"
                "Sélectionnez une option ci-dessous pour configurer l'infrastructure des statistiques."
            ))

        # --- ROUTAGE DES MENUS ---
        if self.active_sub_menu == "manage_fields":
            # 4 Sélecteurs par catégories
            r1 = ui.ActionRow()
            r1.add_item(StatsCategorySelect(self, f"👥 Démographie & Présence...", DEMO_OPTIONS, [x[0] for x in DEMO_OPTIONS]))
            container.add_item(r1)

            r2 = ui.ActionRow()
            r2.add_item(StatsCategorySelect(self, f"🎤 Activité Vocale...", VOCAL_OPTIONS, [x[0] for x in VOCAL_OPTIONS]))
            container.add_item(r2)

            r3 = ui.ActionRow()
            r3.add_item(StatsCategorySelect(self, f"💬 Échanges & Messages...", MSG_OPTIONS, [x[0] for x in MSG_OPTIONS]))
            container.add_item(r3)

            r4 = ui.ActionRow()
            r4.add_item(StatsCategorySelect(self, f"📈 Records Historiques...", RECORD_OPTIONS, [x[0] for x in RECORD_OPTIONS]))
            container.add_item(r4)

            # Bouton de retour
            r5 = ui.ActionRow()
            btn_back = ui.Button(label="Retour", style=discord.ButtonStyle.secondary, emoji=E_BACK)
            btn_back.callback = self._on_back_main
            r5.add_item(btn_back)
            container.add_item(r5)
            
        elif self.active_sub_menu == "channel":
            row_chan = ui.ActionRow()
            chan_select = ui.ChannelSelect(
                placeholder="Sélectionner le salon d'affichage...",
                min_values=1, max_values=1,
                channel_types=[discord.ChannelType.text, discord.ChannelType.news]
            )
            chan_select.callback = self._on_chan_selected
            row_chan.add_item(chan_select)
            container.add_item(row_chan)

            row_id = ui.ActionRow()
            btn_id = ui.Button(label="Lier par ID", style=discord.ButtonStyle.secondary, emoji=E_ID)
            btn_id.callback = self._on_chan_id_manual
            row_id.add_item(btn_id)
            
            btn_auto = ui.Button(label="Générer", style=discord.ButtonStyle.primary, emoji=E_ADD)
            btn_auto.callback = self._on_chan_auto_create
            row_id.add_item(btn_auto)

            btn_back = ui.Button(label="Retour", style=discord.ButtonStyle.secondary, emoji=E_BACK)
            btn_back.callback = self._on_back_main
            row_id.add_item(btn_back)
            
            container.add_item(row_id)
            
        else:
            # Sélecteur principal d'options
            action_row = ui.ActionRow()
            action_row.add_item(StatsOptionsSelect(self))
            container.add_item(action_row)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    async def _refresh(self, interaction: discord.Interaction):
        self._build()
        if interaction.response.is_done():
            await interaction.edit_original_response(view=self)
        else:
            await interaction.response.edit_message(view=self)

    async def _on_back_main(self, interaction: discord.Interaction):
        self.active_sub_menu = None
        await self._refresh(interaction)

    async def _open_delay_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(DelayModal(self))

    async def _on_chan_selected(self, interaction: discord.Interaction):
        chan_id = int(interaction.data['values'][0])
        self.config['ch_stats_text'] = chan_id
        stats_db.save(self.guild.id, self.config)
        self.status_message = f"{E_ON} Salon d'affichage sélectionné avec succès."
        self.active_sub_menu = None
        await self._refresh(interaction)

    async def _on_chan_id_manual(self, interaction: discord.Interaction):
        await interaction.response.send_modal(StatsChannelModal(self))

    async def _on_chan_auto_create(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer()
            
        overwrites = {
            self.guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=False),
            self.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, embed_links=True)
        }
        
        try:
            channel = await self.guild.create_text_channel(f"📊│𝐬𝐭𝐚𝐭𝐢𝐬𝐭𝐢𝐪𝐮𝐞𝐬", overwrites=overwrites)
            self.config['ch_stats_text'] = channel.id
            stats_db.save(self.guild.id, self.config)
            self.status_message = f"{E_ON} Salon généré automatiquement avec succès."
        except Exception as e:
            self.status_message = f"{E_OFF} Impossible de créer le salon : {e}"
            
        self.active_sub_menu = None
        await self._refresh(interaction)

    async def _on_reset(self, interaction: discord.Interaction):
        self.active_sub_menu = None
        self.config['ch_stats_text'] = None
        stats_db.save(self.guild.id, self.config)
        self.status_message = f"{E_TRASH} Module désactivé et salon retiré."
        await self._refresh(interaction)


# ==============================================================================
# --- COG PRINCIPAL ---
# ==============================================================================
class ServerStatsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.message_buffer = {} 
        self.user_msg_buffer = {} 
        log_sys("INIT", "Module AutoStats déployé sur l'architecture V3.")

    async def cog_load(self):
        self.update_stats_loop.start()

    async def cog_unload(self):
        self.update_stats_loop.cancel()

    def get_time_keys(self):
        now = datetime.now()
        return {
            "daily": now.strftime("%Y-%m-%d"),
            "weekly": now.strftime("%Y-W%W"),
            "monthly": now.strftime("%Y-%m"),
            "display_date": now.strftime("%d/%m/%Y")
        }

    def format_duration(self, seconds: int) -> str:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if hours > 0: 
            return f"{hours}h {minutes}min" if minutes > 0 else f"{hours}h"
        return f"{minutes}min"

    def format_msg_count(self, count: int) -> str:
        return f"{count} message{'s' if count > 1 else ''}"

    def get_top_user(self, data_dict: dict) -> tuple:
        if not data_dict: return (None, 0)
        best_uid = max(data_dict, key=data_dict.get)
        return (best_uid, data_dict[best_uid])

    def get_guild_stats(self, guild: discord.Guild, config: dict) -> dict:
        humans = sum(1 for m in guild.members if not m.bot)
        bots = guild.member_count - humans
        
        online_members = [m for m in guild.members if m.status != discord.Status.offline]
        online_total = len(online_members)
        online_humans = sum(1 for m in online_members if not m.bot)
        online_bots = online_total - online_humans

        v_tot, v_str, v_cam, v_mut, v_deaf = 0, 0, 0, 0, 0
        for vc in guild.voice_channels:
            v_tot += len(vc.members)
            for m in vc.members:
                if not m.voice: continue
                if m.voice.self_stream: v_str += 1
                if m.voice.self_video: v_cam += 1
                if m.voice.self_mute or m.voice.mute: v_mut += 1
                if m.voice.self_deaf or m.voice.deaf: v_deaf += 1

        tk = self.get_time_keys()
        hist = config.get('msg_history', {})
        msg_day = hist.get("daily", {}).get(tk["daily"], 0)
        msg_week = hist.get("weekly", {}).get(tk["weekly"], 0)
        msg_month = hist.get("monthly", {}).get(tk["monthly"], 0)

        user_act = config.get('user_activity', {})
        top_voice_id, top_voice_val = self.get_top_user(user_act.get("voice_all_time", {}))
        top_msg_day_id, top_msg_day_val = self.get_top_user(user_act.get("msg", {}).get("daily", {}))
        top_msg_week_id, top_msg_week_val = self.get_top_user(user_act.get("msg", {}).get("weekly", {}))
        top_msg_month_id, top_msg_month_val = self.get_top_user(user_act.get("msg", {}).get("monthly", {}))

        return {
            "total": guild.member_count, "humans": humans, "bots": bots,
            "boosts": guild.premium_subscription_count,
            "online_total": online_total, "online_humans": online_humans, "online_bots": online_bots,
            "vocal_total": v_tot, "vocal_stream": v_str, "vocal_cam": v_cam, 
            "vocal_muted": v_mut, "vocal_deaf": v_deaf,
            "msg_24h": msg_day, "msg_week": msg_week, "msg_month": msg_month,
            "top_vocal_id": top_voice_id, "top_vocal_val": top_voice_val,
            "top_msg_day_id": top_msg_day_id, "top_msg_day_val": top_msg_day_val,
            "top_msg_week_id": top_msg_week_id, "top_msg_week_val": top_msg_week_val,
            "top_msg_month_id": top_msg_month_id, "top_msg_month_val": top_msg_month_val,
            "records": config.get('records', {})
        }

    def build_stats_layout_blocks(self, stats: dict, active_fields: list, guild: discord.Guild, use_mentions: bool = True) -> list:
        """Génère des blocs de texte propres pour l'affichage LayoutV2."""
        sections = {
            f"{E_USER} Démographie & Présence": [],
            f"{E_MIC} Activité Vocale": [],
            f"{E_MSG} Échanges & Messages": [],
            f"{E_TROPHY} Classements & Top Membres": [],
            f"{E_RECORD} Records Historiques": []
        }

        mapping_standard = {
            "total": (f"{E_USER} Démographie & Présence", "Membres Total", E_USER),
            "humans": (f"{E_USER} Démographie & Présence", "Membres Humains", E_USER),
            "bots": (f"{E_USER} Démographie & Présence", "Membres Bots", E_BOT),
            "online_total": (f"{E_USER} Démographie & Présence", "En ligne Tous", E_ONLINE),
            "online_humans": (f"{E_USER} Démographie & Présence", "En ligne Humains", E_ONLINE),
            "online_bots": (f"{E_USER} Démographie & Présence", "En ligne Bots", E_ONLINE),
            "boosts": (f"{E_USER} Démographie & Présence", "Boosts", E_BOOST),
            "vocal_total": (f"{E_MIC} Activité Vocale", "En Vocal", E_MIC),
            "vocal_stream": (f"{E_MIC} Activité Vocale", "Stream", E_STREAM),
            "vocal_cam": (f"{E_MIC} Activité Vocale", "Caméra", E_CAM),
            "vocal_muted": (f"{E_MIC} Activité Vocale", "Muet", E_MUTE),
            "vocal_deaf": (f"{E_MIC} Activité Vocale", "Sourdine", E_DEAF),
            "msg_24h": (f"{E_MSG} Échanges & Messages", "Messages Aujourd'hui", E_MSG),
            "msg_week": (f"{E_MSG} Échanges & Messages", "Messages Semaine", E_MSG),
            "msg_month": (f"{E_MSG} Échanges & Messages", "Messages Mois", E_MSG)
        }

        mapping_records = {
            "record_members": (f"{E_RECORD} Records Historiques", "Record Membres", E_RECORD, "members"),
            "record_online": (f"{E_RECORD} Records Historiques", "Record En ligne", E_FIRE, "online"),
            "record_vocal": (f"{E_RECORD} Records Historiques", "Record Vocal", E_RECORD, "vocal"),
            "record_boosts": (f"{E_RECORD} Records Historiques", "Record Boosts", E_ROCKET, "boosts"),
            "record_msg_24h": (f"{E_RECORD} Records Historiques", "Record Msg Aujourd'hui", E_TROPHY, "msg_24h"),
            "record_msg_week": (f"{E_RECORD} Records Historiques", "Record Msg Semaine", E_TROPHY, "msg_week"),
            "record_msg_month": (f"{E_RECORD} Records Historiques", "Record Msg Mois", E_TROPHY, "msg_month"),
        }

        def format_user(uid):
            if not uid: return "N/A"
            if use_mentions: return f"<@{uid}>"
            m = guild.get_member(int(uid))
            return f"@{m.display_name}" if m else f"@{uid}"

        for field in active_fields:
            if field in mapping_standard:
                sec, label, emo = mapping_standard[field]
                sections[sec].append(f"- {emo} **{label}** : {stats.get(field, 0)}")
            elif field in mapping_records:
                sec, label, emo, rec_key = mapping_records[field]
                rec_data = stats.get("records", {}).get(rec_key, {"value": 0, "date": "N/A"})
                sections[sec].append(f"- {emo} **{label}** : {rec_data.get('value', 0)} `{rec_data.get('date', 'N/A')}`")

        if "top_vocal" in active_fields:
            uid = stats.get("top_vocal_id")
            val = stats.get("top_vocal_val", 0)
            mention = format_user(uid) if uid else "Aucun"
            sections[f"{E_TROPHY} Classements & Top Membres"].append(f"- {E_STAR} **Top Vocal** : {mention} *({self.format_duration(val)})*")

        if "top_msg" in active_fields:
            sections[f"{E_TROPHY} Classements & Top Membres"].append(f"- {E_TROPHY} **Membres les plus Actifs :**")
            d_id, d_val = stats.get("top_msg_day_id"), stats.get("top_msg_day_val", 0)
            w_id, w_val = stats.get("top_msg_week_id"), stats.get("top_msg_week_val", 0)
            m_id, m_val = stats.get("top_msg_month_id"), stats.get("top_msg_month_val", 0)
            sections[f"{E_TROPHY} Classements & Top Membres"].append(f"  ├ *Jour* : {format_user(d_id)} - *{self.format_msg_count(d_val)}*")
            sections[f"{E_TROPHY} Classements & Top Membres"].append(f"  ├ *Semaine* : {format_user(w_id)} - *{self.format_msg_count(w_val)}*")
            sections[f"{E_TROPHY} Classements & Top Membres"].append(f"  └ *Mois* : {format_user(m_id)} - *{self.format_msg_count(m_val)}*")

        blocks = []
        for section_title, lines in sections.items():
            if lines:
                blocks.append(f"### {section_title}\n" + "\n".join(lines))
        return blocks

    # --- Événements & Tâches ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Mise en cache haute performance des compteurs."""
        if message.author.bot or not message.guild: return
        
        gid = message.guild.id
        uid = str(message.author.id)
        
        if gid not in self.user_msg_buffer:
            self.user_msg_buffer[gid] = {}
            
        self.message_buffer[gid] = self.message_buffer.get(gid, 0) + 1
        self.user_msg_buffer[gid][uid] = self.user_msg_buffer[gid].get(uid, 0) + 1

    @tasks.loop(seconds=30)
    async def update_stats_loop(self):
        try:
            tk = self.get_time_keys()
            
            for guild in self.bot.guilds:
                config = stats_db.load(guild.id)
                ch_id = config.get('ch_stats_text')
                
                # Le module est considéré inactif s'il n'y a pas de salon configuré
                if not ch_id: 
                    continue

                data_changed = False
                
                # 1. Mise à jour du temps de VOCAL
                for vc in guild.voice_channels:
                    for member in vc.members:
                        if not member.bot:
                            uid = str(member.id)
                            config['user_activity']['voice_all_time'][uid] = config['user_activity']['voice_all_time'].get(uid, 0) + 30
                            data_changed = True

                # 2. Gestion des resets temporels
                msg_act = config['user_activity']['msg']
                if msg_act['date_day'] != tk['daily']:
                    msg_act['daily'] = {}; msg_act['date_day'] = tk['daily']; data_changed = True
                if msg_act['date_week'] != tk['weekly']:
                    msg_act['weekly'] = {}; msg_act['date_week'] = tk['weekly']; data_changed = True
                if msg_act['date_month'] != tk['monthly']:
                    msg_act['monthly'] = {}; msg_act['date_month'] = tk['monthly']; data_changed = True

                # 3. Dépôt des Buffers
                buffered_server_msgs = self.message_buffer.pop(guild.id, 0)
                if buffered_server_msgs > 0:
                    hist = config['msg_history']
                    hist['daily'][tk['daily']] = hist['daily'].get(tk['daily'], 0) + buffered_server_msgs
                    hist['weekly'][tk['weekly']] = hist['weekly'].get(tk['weekly'], 0) + buffered_server_msgs
                    hist['monthly'][tk['monthly']] = hist['monthly'].get(tk['monthly'], 0) + buffered_server_msgs
                    data_changed = True

                buffered_user_msgs = self.user_msg_buffer.pop(guild.id, {})
                for uid, count in buffered_user_msgs.items():
                    msg_act['daily'][uid] = msg_act['daily'].get(uid, 0) + count
                    msg_act['weekly'][uid] = msg_act['weekly'].get(uid, 0) + count
                    msg_act['monthly'][uid] = msg_act['monthly'].get(uid, 0) + count
                    data_changed = True

                # 4. Vérification des Records
                stats = self.get_guild_stats(guild, config)
                recs = config['records']
                
                checks = [
                    ("members", stats['total']), ("online", stats['online_total']),
                    ("vocal", stats['vocal_total']), ("boosts", stats['boosts']),
                    ("msg_24h", stats['msg_24h']), ("msg_week", stats['msg_week']),
                    ("msg_month", stats['msg_month'])
                ]
                
                for r_key, current_val in checks:
                    if current_val > recs.get(r_key, {}).get('value', 0):
                        recs[r_key] = {"value": current_val, "date": tk['display_date']}
                        data_changed = True

                # 5. Publication de l'annonce via LayoutV2
                delay = max(30, int(config.get('delay', 300)))
                now = time.time()
                if not hasattr(self, '_last_sent'): self._last_sent = {}
                
                # Si le délai exact est écoulé, le bot supprime l'ancien log et envoie le nouveau
                if now - self._last_sent.get(guild.id, 0) >= delay:
                    channel = guild.get_channel(int(ch_id))
                    if channel:
                        # Suppression de l'ancien message de stats pour garder le channel propre
                        last_msg_id = config.get("last_msg_id")
                        if last_msg_id:
                            try:
                                old_msg = await channel.fetch_message(last_msg_id)
                                await old_msg.delete()
                            except discord.NotFound:
                                pass
                            except discord.Forbidden:
                                log_sys("PERM_ERROR", f"Permissions de suppression manquantes {guild.name}")

                        # --- PHASE 1 : Envoi sans Pings (Nom brut) ---
                        view_no_mentions = ui.LayoutView(timeout=1)
                        theme = config_manager.get_layout_v2_theme(guild.id, guild, self.bot.user, self.bot)
                        accent_color = int(theme.get("color", discord.Color.blurple().value))
                        footer_text = theme.get("footer_text", "")
                        
                        container_no_mentions = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
                        container_no_mentions.add_item(ui.TextDisplay(f"# {E_STATS} Évolution des Statistiques"))
                        
                        blocks_no_mentions = self.build_stats_layout_blocks(stats, config.get('fields', []), guild=guild, use_mentions=False)
                        for block in blocks_no_mentions:
                            container_no_mentions.add_item(ui.TextDisplay(block))
                            
                        if footer_text:
                            container_no_mentions.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
                            container_no_mentions.add_item(ui.TextDisplay(footer_text))
                            
                        view_no_mentions.add_item(container_no_mentions)
                        
                        try:
                            msg = await channel.send(view=view_no_mentions)
                            self._last_sent[guild.id] = now
                            config['last_msg_id'] = msg.id
                            data_changed = True
                            
                            # --- PHASE 2 : Édition avec Mentions silencieuses (Après 2 secondes) ---
                            await asyncio.sleep(2)
                            
                            view_mentions = ui.LayoutView(timeout=1)
                            container_mentions = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
                            container_mentions.add_item(ui.TextDisplay(f"# {E_STATS} Évolution des Statistiques"))
                            
                            blocks_mentions = self.build_stats_layout_blocks(stats, config.get('fields', []), guild=guild, use_mentions=True)
                            for block in blocks_mentions:
                                container_mentions.add_item(ui.TextDisplay(block))
                                
                            if footer_text:
                                container_mentions.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
                                container_mentions.add_item(ui.TextDisplay(footer_text))
                                
                            view_mentions.add_item(container_mentions)
                            
                            await msg.edit(view=view_mentions)
                            
                        except discord.Forbidden:
                            log_sys("PERM_ERROR", f"Permissions d'envoi manquantes dans le salon {ch_id} du serveur {guild.name}", is_error=True)
                        except Exception as e:
                            log_sys("EDIT_ERROR", f"Erreur lors de l'édition Anti-Ping : {e}", is_error=True)
                        
                if data_changed:
                    stats_db.save(guild.id, config)

        except Exception as e:
            log_sys("CRITICAL_LOOP", f"Erreur critique dans la boucle: {e}\n{traceback.format_exc()}", is_error=True)

    @update_stats_loop.before_loop
    async def before_update_stats_loop(self):
        await self.bot.wait_until_ready()

    # --- Commandes ---

    @perm_command(level=2)
    @commands.hybrid_command(name="autostats", description="Déploie le panneau de configuration dynamique des statistiques.")
    async def autostats_cmd(self, ctx: commands.Context):
        if not ctx.guild:
            await ctx.send(f"{E_OFF} Cette commande exige un contexte de serveur.")
            return

        if HAS_VAX_CORE and not await ensure_command_permission(ctx, command_name="autostats"):
            return

        log_sys("COMMAND", f"Lancement de /autostats par {ctx.author.name}")
        config = stats_db.load(ctx.guild.id)
        view = StatsConfigLayoutView(self, ctx.guild, config, ctx.author)
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    if bot.get_command("autostats"):
        bot.remove_command("autostats")
    await bot.add_cog(ServerStatsCog(bot))