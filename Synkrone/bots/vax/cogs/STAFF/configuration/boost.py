import discord
from discord import ui, app_commands
from discord.ext import commands, tasks
import time
import io
import aiohttp
import asyncio
import re
from datetime import datetime
import traceback
from pathlib import Path
from typing import Optional, Dict, Any

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
E_BOOST = getattr(E, 'BOOST', "🚀") if HAS_VAX_CORE else "🚀"
E_IMAGE = getattr(E, 'IMAGE', "🖼️") if HAS_VAX_CORE else "🖼️"
E_TIME = getattr(E, 'TEMPS', "⏳") if HAS_VAX_CORE else "⏳"
E_TEXT = getattr(E, 'MEMO', "📝") if HAS_VAX_CORE else "📝"
E_STAR = getattr(E, 'EXCELLENT', "🌟") if HAS_VAX_CORE else "🌟"
E_HEART = getattr(E, 'COEUR', "❤️") if HAS_VAX_CORE else "❤️"
E_CHART = getattr(E, 'GRAPHIQUE', "📊") if HAS_VAX_CORE else "📊"
E_USER = getattr(E, 'PROFIL', "👤") if HAS_VAX_CORE else "👤"
E_DOC = getattr(E, 'DOCUMENT', "📄") if HAS_VAX_CORE else "📄"
E_ID = getattr(E, 'IDENTIFIANT', "🆔") if HAS_VAX_CORE else "🆔"
E_CHAN = getattr(E, 'LIEN', "📍") if HAS_VAX_CORE else "📍"
E_TRASH = getattr(E, 'SUPPRIMER', "🗑️") if HAS_VAX_CORE else "🗑️"
E_ADD = getattr(E, 'AJOUTER', "➕") if HAS_VAX_CORE else "➕"
E_ARROW_RIGHT = getattr(E, 'FLECHE_DROITE', "➡️") if HAS_VAX_CORE else "➡️"
E_BACK = getattr(E, 'RETOUR', "↩️") if HAS_VAX_CORE else "↩️"

# ==============================================================================
# --- UTILITAIRES DE LOGS & TEMPS ---
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
    prefix = "[ERREUR Boosters]" if is_error else "[INFO Boosters]"
    print(f"{color}{prefix} [{action}] {message}{COLOR_RESET}")

def parse_time_to_seconds(time_str: str) -> int:
    """Convertit une chaîne de temps (ex: 5m, 1h, 2j) en secondes."""
    time_str = time_str.strip().lower()
    if not time_str:
        return 600
    multipliers = {'s': 1, 'm': 60, 'h': 3600, 'j': 86400, 'd': 86400}
    try:
        if time_str[-1] in multipliers:
            val = int(time_str[:-1]) * multipliers[time_str[-1]]
        else:
            val = int(time_str) * 60
        return max(60, val) # Forcer un minimum de 60s
    except ValueError:
        return 600

def format_seconds(seconds: int) -> str:
    """Convertit des secondes en format lisible optimisé."""
    if seconds >= 86400: return f"{seconds // 86400} jour(s)"
    if seconds >= 3600: return f"{seconds // 3600} heure(s)"
    if seconds >= 60: return f"{seconds // 60} minute(s)"
    return f"{seconds} seconde(s)"

# ==============================================================================
# --- GESTIONNAIRE DE DONNÉES (DataManager) ---
# ==============================================================================
class BoosterManager:
    """Interface de sauvegarde s'appuyant sur l'infrastructure standard."""
    def __init__(self):
        if HAS_VAX_CORE:
            self.data = DataManager("staff/configuration/data_boosters")
            self.assets_dir = Path("data/staff/configuration/data_boosters/assets")
            try:
                self.assets_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                log_sys("MKDIR_ERR", f"Erreur de création du dossier assets: {e}", is_error=True)
        else:
            log_sys("INIT", "DataManager introuvable. Échec système.", is_error=True)

    def get_thumb_path(self, guild_id: int) -> Path:
        return self.assets_dir / f"{guild_id}_thumb.png"

    def get_banner_path(self, guild_id: int) -> Path:
        return self.assets_dir / f"{guild_id}_banner.png"

    def get_default_config(self):
        return {
            "enabled": False,
            "cooldown": 600, # 10 minutes par défaut
            "channel_id": None,
            "message_id": None,
            "last_update": 0,
            "thumb_type": None,  # "url" or "local"
            "thumb_data": None,
            "banner_type": None, # "url" or "local"
            "banner_data": None
        }

    def load(self, guild_id: int) -> dict:
        try:
            raw = self.data.load(guild_id) or {}
            
            # Rétrocompatibilité avec les anciens paramètres
            if "thumbnail_url" in raw and raw["thumbnail_url"]:
                raw["thumb_type"] = "url"
                raw["thumb_data"] = raw.pop("thumbnail_url")
            if "image_url" in raw and raw["image_url"]:
                raw["banner_type"] = "url"
                raw["banner_data"] = raw.pop("image_url")
                
            return {**self.get_default_config(), **raw}
        except Exception as e:
            log_sys("DB_LOAD", f"Erreur de lecture DB pour {guild_id}: {e}", is_error=True)
            return self.get_default_config()

    def save(self, guild_id: int, config: dict):
        try:
            self.data.save(guild_id, config)
        except Exception as e:
            log_sys("DB_SAVE", f"Erreur d'écriture DB pour {guild_id}: {e}", is_error=True)

booster_db = BoosterManager()

# ==============================================================================
# --- MODALS UTILISATEUR ---
# ==============================================================================
class BoosterChannelModal(ui.Modal, title="Lier par ID de Salon"):
    id_input = ui.TextInput(label="ID du Salon", placeholder="Collez l'ID ici...", min_length=15, max_length=25)
    
    def __init__(self, view: "BoosterControlLayoutView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        raw_id = self.id_input.value.strip()
        if not raw_id.isdigit():
            return await interaction.response.send_message(f"{E_OFF} L'ID fourni n'est pas un nombre valide.", ephemeral=True)
            
        target = interaction.guild.get_channel(int(raw_id))
        if not target or target.type not in {discord.ChannelType.text, discord.ChannelType.news}:
            return await interaction.response.send_message(f"{E_OFF} Salon textuel introuvable.", ephemeral=True)

        conf = booster_db.load(self.view.guild.id)
        conf['channel_id'] = target.id
        conf['enabled'] = True
        conf['last_update'] = 0
        booster_db.save(self.view.guild.id, conf)
        self.view.status_message = f"{E_ON} Salon cible mis à jour avec succès."
        self.view.active_sub_menu = None
        await self.view._refresh(interaction)

class BoosterCooldownModal(ui.Modal, title="Fréquence de Mise à Jour"):
    cooldown_input = ui.TextInput(label="Délai (ex: 10m, 1h, 1j)", placeholder="Ex: 10m", required=True, max_length=10)

    def __init__(self, view: "BoosterControlLayoutView"):
        super().__init__()
        self.view = view
        config = booster_db.load(self.view.guild.id)
        self.cooldown_input.default = format_seconds(config.get('cooldown', 600)).replace(' minute(s)', 'm').replace(' heure(s)', 'h')

    async def on_submit(self, interaction: discord.Interaction):
        config = booster_db.load(self.view.guild.id)
        seconds = parse_time_to_seconds(self.cooldown_input.value)
        config['cooldown'] = seconds
        config['last_update'] = 0
        booster_db.save(self.view.guild.id, config)
        
        self.view.status_message = f"{E_ON} Fréquence de mise à jour modifiée : {format_seconds(seconds)}."
        self.view.active_sub_menu = None
        await self.view._refresh(interaction)


# ==============================================================================
# --- SELECTEURS D'OPTIONS (Layout V2) ---
# ==============================================================================
class BoosterOptionsSelect(ui.Select):
    def __init__(self, parent_view: "BoosterControlLayoutView", is_default: bool):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(label="Configurer le salon", value="channel", emoji=E_CHAN, description="Sélectionner, lier ou auto-générer le salon"),
            discord.SelectOption(label="Fréquence de MAJ", value="cooldown", emoji=E_TIME, description="Modifier l'intervalle de rafraîchissement"),
            discord.SelectOption(label="Apparence visuelle", value="images", emoji=E_IMAGE, description="Modifier la miniature et la bannière"),
        ]
        if not is_default:
            options.append(discord.SelectOption(label="Réinitialiser", value="reset", emoji=E_TRASH, description="Désactiver et remettre à zéro le module"))
            
        super().__init__(placeholder="Options de configuration...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val == "channel":
            self.parent_view.active_sub_menu = "channel"
            await self.parent_view._refresh(interaction)
        elif val == "images":
            self.parent_view.active_sub_menu = "images"
            await self.parent_view._refresh(interaction)
        elif val == "cooldown":
            await self.parent_view._on_cooldown_config(interaction)
        elif val == "reset":
            await self.parent_view._on_reset(interaction)

# ==============================================================================
# --- INTERFACE D'ADMINISTRATION (Layout V2) ---
# ==============================================================================
class BoosterControlLayoutView(ui.LayoutView):
    """Panneau de contrôle de l'administration du module Boosters."""
    def __init__(self, cog: "BoostersCog", guild: discord.Guild, user: discord.Member):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild = guild
        self.user = user
        self.status_message = ""
        self.active_sub_menu: str | None = None
        self.wait_task: Optional[asyncio.Task] = None
        self.waiting_for_image = False
        self.image_target: str | None = None
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Sécurisation du menu."""
        if interaction.user.id != self.user.id:
            if not interaction.response.is_done(): await interaction.response.defer()
            await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, cette interface est verrouillée.", delete_after=6)
            return False
        return True

    def _build(self):
        """Construction de l'interface V2 dynamique."""
        self.clear_items()
        config = booster_db.load(self.guild.id)
        
        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.cog.bot)
        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text", "")

        is_enabled = bool(config.get('channel_id')) and self.guild.get_channel(config['channel_id']) is not None
        statut_txt = f"{E_ON} `Activé`" if is_enabled else f"{E_OFF} `Désactivé`"
        salon_txt = f"<#{config['channel_id']}>" if config.get('channel_id') else "`Non configuré`"
        freq_txt = format_seconds(config.get('cooldown', 600))
        
        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        
        # Gestion du mode attente d'image
        if self.waiting_for_image:
            container.add_item(ui.TextDisplay(f"# {E_TIME} En attente d'un média..."))
            target_name = "la miniature (thumbnail)" if self.image_target == "thumb" else "la bannière"
            container.add_item(ui.TextDisplay(
                f"Veuillez envoyer une **image** (fichier joint) ou un **lien (URL)** pour {target_name} directement dans ce salon.\n\n"
                "-# Vous avez 5 minutes. Le message sera automatiquement intercepté et supprimé."
            ))
            
            wait_row = ui.ActionRow()
            btn_cancel = ui.Button(label="Annuler", style=discord.ButtonStyle.secondary, emoji=E_BACK)
            btn_cancel.callback = self.cancel_wait_callback
            wait_row.add_item(btn_cancel)
            container.add_item(wait_row)
            self.add_item(container)
            return

        container.add_item(ui.TextDisplay(f"# {E_DOC} Configuration des Boosters"))
        
        if self.status_message:
            container.add_item(ui.TextDisplay(f"> {self.status_message}"))
            self.status_message = ""

        container.add_item(ui.TextDisplay(
            f"**État du système :** {statut_txt}\n"
            f"**Salon cible :** {salon_txt}\n"
            f"**Mise à jour :** Chaque {freq_txt}\n\n"
            f"### {E_IMAGE} Apparence Visuelle\n"
            f"- **Miniature :** {'`Définie`' if config.get('thumb_data') else '`Aucune`'}\n"
            f"- **Bannière :** {'`Définie`' if config.get('banner_data') else '`Aucune`'}"
        ))

        # Sélecteur principal
        row_main = ui.ActionRow()
        is_default = not config.get('channel_id') and not config.get('thumb_data') and not config.get('banner_data') and config.get('cooldown') == 600
        opt_select = BoosterOptionsSelect(self, is_default)
        row_main.add_item(opt_select)
        container.add_item(row_main)

        # Sous-menus dynamiques
        if self.active_sub_menu == "channel":
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
            
            btn_auto = ui.Button(label="Générer automatiquement", style=discord.ButtonStyle.primary, emoji=E_ADD)
            btn_auto.callback = self._on_chan_auto_create
            row_id.add_item(btn_auto)
            
            container.add_item(row_id)
            
        elif self.active_sub_menu == "images":
            row_img = ui.ActionRow()
            img_select = ui.Select(
                placeholder="Gérer les images du tableau...",
                options=[
                    discord.SelectOption(label="Modifier la Miniature", value="set_thumb", emoji=E_IMAGE, description="Ajouter ou remplacer le logo"),
                    discord.SelectOption(label="Supprimer la Miniature", value="del_thumb", emoji=E_TRASH, description="Retirer le logo actuel"),
                    discord.SelectOption(label="Modifier la Bannière", value="set_banner", emoji=E_IMAGE, description="Ajouter ou remplacer l'image large"),
                    discord.SelectOption(label="Supprimer la Bannière", value="del_banner", emoji=E_TRASH, description="Retirer la bannière actuelle")
                ]
            )
            img_select.callback = self._on_img_select
            row_img.add_item(img_select)
            container.add_item(row_img)

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

    # --- CALLBACKS SOUS-MENUS ---
    async def _on_chan_selected(self, interaction: discord.Interaction):
        chan_id = int(interaction.data['values'][0])
        conf = booster_db.load(self.guild.id)
        conf['channel_id'] = chan_id
        conf['enabled'] = True
        conf['last_update'] = 0
        booster_db.save(self.guild.id, conf)
        self.status_message = f"{E_ON} Salon des boosters sélectionné et module activé."
        self.active_sub_menu = None
        await self._refresh(interaction)

    async def _on_chan_id_manual(self, interaction: discord.Interaction):
        self.active_sub_menu = None
        await interaction.response.send_modal(BoosterChannelModal(self))

    async def _on_chan_auto_create(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer()
        overwrites = {
            self.guild.default_role: discord.PermissionOverwrite(send_messages=False),
            self.guild.me: discord.PermissionOverwrite(send_messages=True, embed_links=True, attach_files=True, read_message_history=True)
        }
        try:
            channel = await self.guild.create_text_channel(f"🚀│𝐁𝐨𝐨𝐬𝐭𝐞𝐫𝐬", overwrites=overwrites)
            conf = booster_db.load(self.guild.id)
            conf['channel_id'] = channel.id
            conf['enabled'] = True
            conf['last_update'] = 0
            booster_db.save(self.guild.id, conf)
            self.status_message = f"{E_ON} Salon généré automatiquement avec succès."
        except Exception as e:
            self.status_message = f"{E_OFF} Impossible de créer le salon : {e}"
            
        self.active_sub_menu = None
        await self._refresh(interaction)

    async def _on_cooldown_config(self, interaction: discord.Interaction):
        self.active_sub_menu = None
        await interaction.response.send_modal(BoosterCooldownModal(self))

    async def _on_img_select(self, interaction: discord.Interaction):
        val = interaction.data['values'][0]
        self.active_sub_menu = None
        
        if val in ("set_thumb", "set_banner"):
            self.image_target = "thumb" if val == "set_thumb" else "banner"
            await self._start_image_upload(interaction)
        elif val in ("del_thumb", "del_banner"):
            conf = booster_db.load(self.guild.id)
            target = "thumb" if val == "del_thumb" else "banner"
            
            # Suppression du fichier local si nécessaire
            if conf.get(f"{target}_type") == "local":
                path = booster_db.get_thumb_path(self.guild.id) if target == "thumb" else booster_db.get_banner_path(self.guild.id)
                if path.exists():
                    try: path.unlink()
                    except: pass
                    
            conf[f"{target}_type"] = None
            conf[f"{target}_data"] = None
            conf['last_update'] = 0
            booster_db.save(self.guild.id, conf)
            self.status_message = f"{E_TRASH} {target.capitalize()} supprimée avec succès."
            await self._refresh(interaction)

    # --- UPLOAD D'IMAGE DYNAMIQUE ---
    async def cancel_wait_callback(self, interaction: discord.Interaction):
        if self.wait_task:
            self.wait_task.cancel()
        self.waiting_for_image = False
        self.active_sub_menu = None
        await self._refresh(interaction)

    async def _start_image_upload(self, interaction: discord.Interaction):
        self.waiting_for_image = True
        self._build()
        await interaction.response.edit_message(view=self)
        self.wait_task = asyncio.create_task(self.wait_for_image_task(interaction))

    async def wait_for_image_task(self, interaction: discord.Interaction):
        def check(m):
            return m.author.id == self.user.id and m.channel.id == interaction.channel.id
            
        try:
            msg = await self.cog.bot.wait_for('message', check=check, timeout=300.0)
            
            url = None
            local_path = None
            target_path = booster_db.get_thumb_path(self.guild.id) if self.image_target == "thumb" else booster_db.get_banner_path(self.guild.id)
            
            if msg.attachments:
                att = msg.attachments[0]
                for a in msg.attachments:
                    if a.content_type and a.content_type.startswith('image/'):
                        att = a
                        break
                
                await att.save(target_path)
                local_path = str(target_path)
            else:
                match = re.search(r'(https?://\S+\.(?:png|jpe?g|webp|gif)(?:\?\S*)?)', msg.content, re.IGNORECASE)
                if match:
                    url = match.group(1)
                else:
                    match = re.search(r'(https?://\S+)', msg.content)
                    if match:
                        url = match.group(1)
                        
                if url:
                    # On télécharge l'URL pour assurer la pérennité de l'image
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url) as resp:
                            if resp.status == 200:
                                data = await resp.read()
                                with open(target_path, "wb") as f:
                                    f.write(data)
                                local_path = str(target_path)
                                url = None # On privilégie le local
            
            try:
                await msg.delete()
            except (discord.Forbidden, discord.NotFound):
                pass
                
            if local_path or url:
                conf = booster_db.load(self.guild.id)
                if local_path:
                    conf[f"{self.image_target}_type"] = "local"
                    conf[f"{self.image_target}_data"] = local_path
                else:
                    conf[f"{self.image_target}_type"] = "url"
                    conf[f"{self.image_target}_data"] = url
                    
                conf['last_update'] = 0
                booster_db.save(self.guild.id, conf)
                self.status_message = f"{E_ON} L'image a été configurée avec succès."
            else:
                self.status_message = f"{E_OFF} Aucune image ou URL valide n'a été détectée."
                
        except asyncio.TimeoutError:
            self.status_message = f"{E_WARN} Délai d'attente expiré (5 minutes)."
        except asyncio.CancelledError:
            return  # Annulé par le bouton
            
        self.waiting_for_image = False
        self.image_target = None
        
        try:
            self._build()
            await interaction.edit_original_response(view=self)
        except Exception as e:
            log_sys("UI_ERR", f"Erreur update UI upload: {e}", is_error=True)

    async def _on_reset(self, interaction: discord.Interaction):
        self.active_sub_menu = None
        
        # Nettoyage des fichiers locaux
        try:
            thumb_path = booster_db.get_thumb_path(self.guild.id)
            banner_path = booster_db.get_banner_path(self.guild.id)
            if thumb_path.exists(): thumb_path.unlink()
            if banner_path.exists(): banner_path.unlink()
        except: pass
        
        booster_db.save(self.guild.id, booster_db.get_default_config())
        self.status_message = f"{E_TRASH} Configuration réinitialisée et module désactivé."
        await self._refresh(interaction)


# ==============================================================================
# --- COG PRINCIPAL ---
# ==============================================================================
class BoostersCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log_sys("INIT", "Module Boosters V3 déployé.")

    async def cog_load(self):
        if not self.update_task_loop.is_running():
            self.update_task_loop.start()

    async def cog_unload(self):
        self.update_task_loop.cancel()

    def get_board_content(self, guild: discord.Guild, config: dict):
        """Prépare la vue LayoutV2 et les fichiers joints nécessaires."""
        boosters = guild.premium_subscribers
        boosters.sort(key=lambda x: x.premium_since)

        now_ts = int(time.time())
        theme = config_manager.get_layout_v2_theme(guild.id, guild, self.bot.user, self.bot)
        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text", "")
        
        view = ui.LayoutView(timeout=1) # Timeout 1s car vue statique
        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        files = []
        
        # --- RÉSOLUTION DES IMAGES ---
        thumb_url = None
        if config.get("thumb_type") == "url":
            thumb_url = config.get("thumb_data")
        elif config.get("thumb_type") == "local" and booster_db.get_thumb_path(guild.id).exists():
            thumb_filename = f"thumb_{guild.id}.png"
            files.append(discord.File(booster_db.get_thumb_path(guild.id), filename=thumb_filename))
            thumb_url = f"attachment://{thumb_filename}"

        banner_url = None
        if config.get("banner_type") == "url":
            banner_url = config.get("banner_data")
        elif config.get("banner_type") == "local" and booster_db.get_banner_path(guild.id).exists():
            banner_filename = f"banner_{guild.id}.png"
            files.append(discord.File(booster_db.get_banner_path(guild.id), filename=banner_filename))
            banner_url = f"attachment://{banner_filename}"
        
        # En-tête avec Section si un thumbnail est présent
        title_text = f"# {E_BOOST} Tableau d'Honneur des Boosters"
        desc_text = (
            f"Dernière mise à jour : <t:{now_ts}:R>\n\n"
            f"Un immense merci à nos précieux contributeurs qui font vivre le serveur ! {E_HEART}\n"
            "Votre soutien permet de débloquer des fonctionnalités exclusives."
        )

        if thumb_url:
            try:
                container.add_item(ui.Section(
                    title_text + "\n" + desc_text, 
                    accessory=ui.Thumbnail(thumb_url, description="Logo Boost")
                ))
            except Exception:
                container.add_item(ui.TextDisplay(title_text + "\n" + desc_text))
        else:
            container.add_item(ui.TextDisplay(title_text + "\n" + desc_text))

        # Liste des contributeurs avec la flèche custom
        list_text = "".join([f"- {m.mention} {E_ARROW_RIGHT} <t:{int(m.premium_since.timestamp())}:d>\n" for m in boosters[:30]])
        container.add_item(ui.TextDisplay(
            f"### {E_USER} Liste des contributeurs ({len(boosters)})\n" +
            (list_text if list_text else "> *Aucun boost actif actuellement.*")
        ))

        # Statistiques
        stats_text = (
            f"- Boosts actifs : **{guild.premium_subscription_count}**\n"
            f"- Niveau du serveur : **Niveau {guild.premium_tier}**"
        )
        container.add_item(ui.TextDisplay(f"### {E_CHART} Statistiques\n{stats_text}"))

        # Bannière avec MediaGallery
        if banner_url:
            try:
                gallery = ui.MediaGallery()
                gallery.add_item(media=banner_url, description="Bannière Boosters")
                container.add_item(gallery)
            except Exception:
                pass

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        view.add_item(container)
        return view, files

    async def update_boosters_panel(self, guild: discord.Guild, channel: discord.TextChannel, config: dict):
        """Met à jour ou remplace le tableau des boosters."""
        try:
            view_board, files = self.get_board_content(guild, config)

            last_message = None
            async for msg in channel.history(limit=1):
                last_message = msg

            old_msg_id = config.get('message_id')
            
            # Logique de conservation : On édite si on est toujours le dernier message
            if last_message and last_message.id == old_msg_id:
                try:
                    await last_message.edit(view=view_board, attachments=files)
                except discord.HTTPException:
                    pass
            else:
                if old_msg_id:
                    try:
                        old_msg = await channel.fetch_message(old_msg_id)
                        await old_msg.delete()
                    except discord.NotFound:
                        pass
                
                try:
                    new_msg = await channel.send(view=view_board, files=files)
                    config['message_id'] = new_msg.id
                except discord.Forbidden:
                    log_sys("PERM_ERROR", f"Impossible d'envoyer le tableau dans {channel.id}", is_error=True)

            config['last_update'] = int(time.time())
            booster_db.save(guild.id, config)

        except Exception as e:
            log_sys("UPDATE_ERR", f"Erreur critique update_boosters_panel [{guild.id}]: {e}\n{traceback.format_exc()}", is_error=True)

    # --- TACHES RÉCURRENTE
    @tasks.loop(minutes=1)
    async def update_task_loop(self):
        await self.bot.wait_until_ready()
        current_time = int(time.time())

        for guild in self.bot.guilds:
            config = booster_db.load(guild.id)
            if not config.get('channel_id'): # Vérification basée sur l'existence du salon
                continue
            
            last_update = config.get('last_update', 0)
            cooldown = config.get('cooldown', 600)

            if current_time - last_update >= cooldown:
                channel = guild.get_channel(config.get('channel_id'))
                if channel and isinstance(channel, discord.TextChannel):
                    await self.update_boosters_panel(guild, channel, config)

    # --- ÉVÉNEMENTS ---
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Détecte l'arrivée d'un nouveau booster pour l'annonce de célébration."""
        if before.premium_since is None and after.premium_since is not None:
            config = booster_db.load(after.guild.id)
            if not config.get('channel_id'):
                return

            channel = after.guild.get_channel(config['channel_id'])
            if not channel: return

            # Rendu de célébration LayoutV2
            view = ui.LayoutView(timeout=1)
            theme = config_manager.get_layout_v2_theme(after.guild.id, after.guild, self.bot.user, self.bot)
            accent_color = int(theme.get("color", discord.Color.blurple().value))
            footer_text = theme.get("footer_text", "")
            
            container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
            
            thumb_asset = after.display_avatar.url
            celeb_text = (
                f"# {E_BOOST} NOUVEAU BOOSTER !\n"
                f"Un immense merci à {after.mention} qui vient de soutenir le serveur !\n"
                f"Nous sommes maintenant à **{after.guild.premium_subscription_count}** boosts. {E_STAR}"
            )
            
            try:
                container.add_item(ui.Section(celeb_text, accessory=ui.Thumbnail(thumb_asset, description=f"Avatar de {after.display_name}")))
            except Exception:
                container.add_item(ui.TextDisplay(celeb_text))
            
            if footer_text:
                container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
                container.add_item(ui.TextDisplay(footer_text))
                
            view.add_item(container)
            
            try:
                await channel.send(content=after.mention, view=view)
                config['last_update'] = 0 # Force la MAJ du tableau au prochain cycle
                booster_db.save(after.guild.id, config)
            except discord.HTTPException:
                pass

    # --- COMMANDE D'ADMINISTRATION ---
    @perm_command(level=2) # Verrouillage métier via le gestionnaire global de permissions
    @commands.hybrid_command(name="boost", description="Configuration de l'interface et du système de boosters.")
    async def boost_cmd(self, ctx: commands.Context):
        if not ctx.guild:
            await ctx.send(f"{E_OFF} Cette commande exige un contexte de serveur.")
            return

        if not await ensure_command_permission(ctx, command_name="boost"):
            return

        log_sys("CMD_INVOKE", f"Interface /boost déployée par {ctx.author.name}")
        view = BoosterControlLayoutView(self, ctx.guild, ctx.author)
        await ctx.send(view=view)

async def setup(bot: commands.Bot):
    if bot.get_command("boost"):
        bot.remove_command("boost")
    await bot.add_cog(BoostersCog(bot))