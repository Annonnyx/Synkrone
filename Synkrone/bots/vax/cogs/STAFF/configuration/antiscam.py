import asyncio
import re
import time
from datetime import datetime, timedelta
from typing import Any, Optional

import discord
from discord import ui
from discord.ext import commands, tasks

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
# --- CONFIGURATION GLOBALE & LOGS ---
# ==============================================================================
DEBUG_MODE = True
ERROR_ONLY_MODE = False

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
    now = datetime.now().strftime("%H:%M:%S")
    print(f"{color}[ANTISCAM] [{now}] [{level.upper()}] {message}{reset}")

# ==============================================================================
# --- CENTRALISATION DES EMOJIS ---
# ==============================================================================
E_ON = getattr(E, 'VALIDER', "🟢") if HAS_VAX_CORE else "🟢"
E_OFF = getattr(E, 'REFUSER', "🔴") if HAS_VAX_CORE else "🔴"
E_WARN = getattr(E, 'ATTENTION', "⚠️") if HAS_VAX_CORE else "⚠️"
E_GEAR = getattr(E, 'MODIFIER', "⚙️") if HAS_VAX_CORE else "⚙️"
E_SHIELD = getattr(E, 'BOUCLIER', "🛡️") if HAS_VAX_CORE else "🛡️"
E_DOC = getattr(E, 'DOCUMENT', "📄") if HAS_VAX_CORE else "📄"
E_UNLOCK = getattr(E, 'UNLOCK', "🔓") if HAS_VAX_CORE else "🔓"
E_REFRESH = getattr(E, 'RAFRAICHIR', "🔄") if HAS_VAX_CORE else "🔄"
E_RIGHT = getattr(E, 'FLECHE_DROITE', "➡️") if HAS_VAX_CORE else "➡️"
E_STAR = getattr(E, 'ETOILE', "⭐") if HAS_VAX_CORE else "⭐"
E_TRASH = getattr(E, 'SUPPRIMER', "🗑️") if HAS_VAX_CORE else "🗑️"
E_ID = getattr(E, 'IDENTIFIANT', "🆔") if HAS_VAX_CORE else "🆔"
E_ROLE = getattr(E, 'ROLE', "🎭") if HAS_VAX_CORE else "🎭"
E_USER = getattr(E, 'PROFIL', "👤") if HAS_VAX_CORE else "👤"
E_BACK = getattr(E, 'RETOUR', "↩️") if HAS_VAX_CORE else "↩️"

# Regex pour détecter les URLs et extensions d'images
URL_REGEX = re.compile(
    r"(https?://[^\s]+"
    r"|(?:www\.)?discord\.gg/[^\s]+"
    r"|(?:www\.)?(?:canary\.|ptb\.)?discord(?:app)?\.com/invite/[^\s]+)",
    re.IGNORECASE,
)
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")

# ==============================================================================
# --- GESTIONNAIRE DE DONNÉES (CRUD) ---
# ==============================================================================
class AntiScamManager:
    """Gestionnaire centralisé pour la configuration Anti-Scam via DataManager."""
    def __init__(self):
        if HAS_VAX_CORE:
            self.db = DataManager("staff/configuration/data_antiscam")
        else:
            custom_log("error", "DataManager introuvable. Échec système.")

    def _normalize(self, raw: dict[str, Any] | None) -> dict[str, Any]:
        src = raw or {}
        
        # Blindage du dictionnaire des prisonniers pour éviter les crashs UI
        prisonniers_raw = src.get("prisonniers", {})
        prisonniers_clean = {}
        if isinstance(prisonniers_raw, dict):
            for k, v in prisonniers_raw.items():
                if isinstance(v, dict):
                    prisonniers_clean[str(k)] = v

        return {
            "enabled": bool(src.get("enabled", True)),
            "threshold": int(src.get("threshold", 3)),
            "timeframe": int(src.get("timeframe", 60)),
            "whitelist_users": src.get("whitelist_users", []),
            "whitelist_roles": src.get("whitelist_roles", []),
            "prisonniers": prisonniers_clean
        }

    def load_guild(self, guild_id: int) -> dict[str, Any]:
        try:
            return self._normalize(self.db.load(guild_id))
        except Exception:
            return self._normalize({})

    def save_guild(self, guild_id: int, data: dict[str, Any]) -> None:
        self.db.save(guild_id, self._normalize(data))

antiscam_config_manager = AntiScamManager()

# ==============================================================================
# --- INTERFACES UTILISATEUR (LayoutV2 & Modals) ---
# ==============================================================================
class ConfigModal(ui.Modal, title="Configuration Anti-Scam"):
    def __init__(self, view: "AntiScamLayoutView"):
        super().__init__()
        self.view = view
        config = self.view.config
        
        self.threshold = ui.TextInput(
            label="Seuil de salons (ex: 3)",
            default=str(config.get("threshold", 3)),
            max_length=2,
            required=True
        )
        self.timeframe = ui.TextInput(
            label="Fenêtre de temps (secondes)",
            default=str(config.get("timeframe", 60)),
            max_length=4,
            required=True
        )
        self.add_item(self.threshold)
        self.add_item(self.timeframe)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            threshold_val = int(self.threshold.value)
            timeframe_val = int(self.timeframe.value)
            
            if threshold_val < 2 or timeframe_val < 10:
                raise ValueError("Valeurs hors limites.")
                
            # Sauvegarde chirurgicale sur les données fraîches
            fresh_config = antiscam_config_manager.load_guild(self.view.guild.id)
            fresh_config["threshold"] = threshold_val
            fresh_config["timeframe"] = timeframe_val
            antiscam_config_manager.save_guild(self.view.guild.id, fresh_config)
            
            self.view.config = fresh_config
            self.view.status_message = f"{E_ON} Seuils Anti-Scam mis à jour."
            await self.view._refresh(interaction)
        except ValueError:
            if not interaction.response.is_done():
                await interaction.response.defer()
            await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, Valeurs invalides. Entrez des nombres corrects.", delete_after=7)


class ManualIDModal(ui.Modal, title="Gestion Manuelle par ID"):
    """Modal natif pour cibler n'importe quel identifiant dans la Whitelist."""
    target_id = ui.TextInput(
        label="ID de l'entité (Membre, Rôle, Bot)",
        placeholder="Ex: 123456789012345678",
        min_length=15,
        max_length=20,
        required=True
    )

    def __init__(self, view: "AntiScamLayoutView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            id_to_manage = int(self.target_id.value)
        except ValueError:
            if not interaction.response.is_done(): await interaction.response.defer()
            return await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, l'ID doit être composé uniquement de nombres.", delete_after=6)

        fresh_config = antiscam_config_manager.load_guild(self.view.guild.id)
        
        if id_to_manage in fresh_config["whitelist_users"]:
            fresh_config["whitelist_users"].remove(id_to_manage)
            action = "retirée de"
        elif id_to_manage in fresh_config["whitelist_roles"]:
            fresh_config["whitelist_roles"].remove(id_to_manage)
            action = "retirée de"
        else:
            if self.view.guild.get_role(id_to_manage):
                fresh_config["whitelist_roles"].append(id_to_manage)
            else:
                fresh_config["whitelist_users"].append(id_to_manage)
            action = "ajoutée à"

        antiscam_config_manager.save_guild(self.view.guild.id, fresh_config)
        self.view.config = fresh_config
        self.view.status_message = f"{E_ON} Entité `{id_to_manage}` {action} la Whitelist."
        await self.view._refresh(interaction)


class PrisonerSelect(ui.Select):
    def __init__(self, view: "AntiScamLayoutView"):
        self.parent_view = view
        
        # On lit directement les données fraîches pour le Select
        fresh_config = antiscam_config_manager.load_guild(view.guild.id)
        prisonniers = fresh_config.get("prisonniers", {})
        self.has_prisoners = bool(prisonniers)
        
        options = []
        for uid, data in list(prisonniers.items())[:25]:
            nom = data.get("name", f"Utilisateur {uid}")[:50]
            date_isolement = data.get("timestamp", "Inconnu")
            raison = data.get("flagged", "")[:40]
            
            desc = f"Isolé le {date_isolement}"
            if raison:
                desc += f" | Raison: {raison}..."
                
            options.append(discord.SelectOption(
                label=nom,
                description=desc[:100],
                value=str(uid),
                emoji=E_UNLOCK
            ))
            
        if not options:
            options.append(discord.SelectOption(
                label="Aucun prisonnier", 
                value="none", 
                description="Personne n'est en quarantaine actuellement.",
                emoji=E_ON
            ))
            
        super().__init__(
            placeholder="Sélectionner un membre à gracier..." if self.has_prisoners else "Aucun membre en quarantaine",
            min_values=1,
            max_values=1,
            options=options,
            disabled=not self.has_prisoners
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.defer()
            return
            
        user_id = self.values[0]
        member = interaction.guild.get_member(int(user_id))
        
        if member:
            try:
                await member.timeout(None, reason=f"Pardon Anti-Scam par {interaction.user}")
                custom_log("success", f"Quarantaine levée pour {user_id}")
            except discord.Forbidden:
                custom_log("warning", f"Impossible de lever le timeout pour {user_id} (Permissions).")
                
        fresh_config = antiscam_config_manager.load_guild(self.parent_view.guild.id)
        if user_id in fresh_config.get("prisonniers", {}):
            del fresh_config["prisonniers"][user_id]
            antiscam_config_manager.save_guild(self.parent_view.guild.id, fresh_config)
            
        self.parent_view.config = fresh_config
        self.parent_view.status_message = f"{E_ON} L'utilisateur a été libéré et retiré de la base de données."
        await self.parent_view._refresh(interaction)


# ==============================================================================
# --- SELECTEURS D'OPTIONS (Layout V2) ---
# ==============================================================================
class AntiScamOptionsSelect(ui.Select):
    def __init__(self, parent_view: "AntiScamLayoutView"):
        self.parent_view = parent_view
        is_enabled = parent_view.config.get("enabled", False)
        
        options = [
            discord.SelectOption(
                label="Désactiver le système" if is_enabled else "Activer le système", 
                value="toggle", 
                emoji=E_OFF if is_enabled else E_ON, 
                description="Allumer ou éteindre la protection"
            ),
            discord.SelectOption(label="Paramètres de détection", value="config", emoji=E_GEAR, description="Régler le seuil et le temps d'analyse"),
            discord.SelectOption(label="Gérer la Whitelist", value="whitelist", emoji=E_DOC, description="Immuniser des rôles ou utilisateurs"),
            discord.SelectOption(label="Actualiser les données", value="refresh", emoji=E_REFRESH, description="Rafraîchir l'interface"),
        ]
        super().__init__(placeholder="Options de configuration...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val == "toggle":
            await self.parent_view.on_toggle(interaction)
        elif val == "config":
            await self.parent_view.on_config(interaction)
        elif val == "whitelist":
            await self.parent_view._change_state(interaction, "whitelist")
        elif val == "refresh":
            await self.parent_view.on_refresh_data(interaction)


class AntiScamLayoutView(ui.LayoutView):
    def __init__(self, cog: "AntiScamCog", guild: discord.Guild, author: discord.Member):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild = guild
        self.author = author
        self.message: Optional[discord.Message] = None
        self.state = "main" # 'main' ou 'whitelist'
        self.status_message = ""
        self.config = antiscam_config_manager.load_guild(self.guild.id)
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            if not interaction.response.is_done(): await interaction.response.defer()
            await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, Ce menu ne vous appartient pas.", delete_after=7)
            return False
        return True

    async def _change_state(self, interaction: discord.Interaction, new_state: str):
        self.state = new_state
        self.status_message = ""
        await self._refresh(interaction)

    async def _refresh(self, interaction: discord.Interaction = None):
        self._build()
        if interaction:
            if not interaction.response.is_done():
                await interaction.response.edit_message(view=self)
            else:
                await interaction.edit_original_response(view=self)
        elif self.message:
            await self.message.edit(view=self)

    def _build(self):
        self.clear_items()
        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.author, self.cog.bot)
        accent_color = int(theme.get("color", discord.Color.red().value))
        footer_text = theme.get("footer_text", "")

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {E_SHIELD} Contrôle Anti-Scam"))

        if self.status_message:
            container.add_item(ui.TextDisplay(f"> {self.status_message}"))
            self.status_message = ""

        if self.state == "main":
            self._build_main(container)
        elif self.state == "whitelist":
            self._build_whitelist(container)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    def _build_main(self, container: ui.Container):
        is_enabled = self.config.get("enabled", False)
        prisonniers_count = len(self.config.get("prisonniers", {}))
        whitelist_users_count = len(self.config.get("whitelist_users", []))
        whitelist_roles_count = len(self.config.get("whitelist_roles", []))

        status_emoji = E_ON if is_enabled else E_OFF
        desc = (
            f"**Statut :** {status_emoji} {'Actif' if is_enabled else 'Inactif'}\n"
            f"**Seuil :** `{self.config.get('threshold', 3)}` salons\n"
            f"**Fenêtre :** `{self.config.get('timeframe', 60)}` secondes\n"
            f"**Quarantaine :** `{prisonniers_count}` membre(s)\n\n"
            f"**Whitelist :** `{whitelist_users_count}` utilisateurs | `{whitelist_roles_count}` rôles\n\n"
            "*Règle : Seuls les messages contenant un lien ou une image sont traqués.*"
        )
        container.add_item(ui.TextDisplay(desc))

        # Row 1: Sélecteur d'options
        opt_row = ui.ActionRow()
        opt_row.add_item(AntiScamOptionsSelect(self))
        container.add_item(opt_row)

        # Row 2: Select des prisonniers
        prison_row = ui.ActionRow()
        prison_row.add_item(PrisonerSelect(self))
        container.add_item(prison_row)

    def _build_whitelist(self, container: ui.Container):
        users = self.config.get("whitelist_users", [])
        roles = self.config.get("whitelist_roles", [])
        
        desc = f"### {E_STAR} Entités immunisées\nCes utilisateurs et rôles ignorent la protection Anti-Scam.\n\n"
        desc += f"**{E_ROLE} Rôles Whitelist**\n" + ("\n".join([f"- <@&{r}> | ID: `{r}`" for r in roles]) if roles else "*Aucun rôle*\n")
        desc += f"\n**{E_USER} Utilisateurs Whitelist**\n" + ("\n".join([f"- <@{u}> | ID: `{u}`" for u in users]) if users else "*Aucun utilisateur*\n")

        container.add_item(ui.TextDisplay(desc))

        user_row = ui.ActionRow()
        user_sel = ui.UserSelect(placeholder="Ajouter ou retirer un Utilisateur...")
        user_sel.callback = self._on_user_select
        user_row.add_item(user_sel)
        container.add_item(user_row)

        role_row = ui.ActionRow()
        role_sel = ui.RoleSelect(placeholder="Ajouter ou retirer un Rôle...")
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

        btn_back = ui.Button(label="Retour", style=discord.ButtonStyle.secondary, emoji=E_BACK)
        btn_back.callback = lambda i: self._change_state(i, "main")
        action_row.add_item(btn_back)

        container.add_item(action_row)

    # --- CALLBACKS CONFIG / WHITELIST ---
    async def on_toggle(self, interaction: discord.Interaction):
        fresh_config = antiscam_config_manager.load_guild(self.guild.id)
        fresh_config["enabled"] = not fresh_config.get("enabled", False)
        antiscam_config_manager.save_guild(self.guild.id, fresh_config)
        
        self.config = fresh_config
        etat = "activé" if fresh_config["enabled"] else "désactivé"
        self.status_message = f"{E_ON} Le système Anti-Scam a été {etat}."
        await self._refresh(interaction)

    async def on_config(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ConfigModal(self))
        
    async def on_refresh_data(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.config = antiscam_config_manager.load_guild(self.guild.id)
        self.status_message = f"{E_REFRESH} Données synchronisées avec succès."
        await self._refresh(interaction)

    async def _on_user_select(self, interaction: discord.Interaction):
        t_id = int(interaction.data['values'][0])
        fresh = antiscam_config_manager.load_guild(self.guild.id)
        if t_id in fresh["whitelist_users"]:
            fresh["whitelist_users"].remove(t_id)
            act = "retiré de"
        else:
            fresh["whitelist_users"].append(t_id)
            act = "ajouté à"
            
        antiscam_config_manager.save_guild(self.guild.id, fresh)
        self.config = fresh
        self.status_message = f"{E_ON} L'utilisateur `{t_id}` a été {act} la Whitelist."
        await self._refresh(interaction)

    async def _on_role_select(self, interaction: discord.Interaction):
        t_id = int(interaction.data['values'][0])
        fresh = antiscam_config_manager.load_guild(self.guild.id)
        if t_id in fresh["whitelist_roles"]:
            fresh["whitelist_roles"].remove(t_id)
            act = "retiré de"
        else:
            fresh["whitelist_roles"].append(t_id)
            act = "ajouté à"
            
        antiscam_config_manager.save_guild(self.guild.id, fresh)
        self.config = fresh
        self.status_message = f"{E_ON} Le rôle `{t_id}` a été {act} la Whitelist."
        await self._refresh(interaction)

    async def _on_manual_id(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ManualIDModal(self))

    async def _on_clear_whitelist(self, interaction: discord.Interaction):
        fresh = antiscam_config_manager.load_guild(self.guild.id)
        fresh["whitelist_users"] = []
        fresh["whitelist_roles"] = []
        antiscam_config_manager.save_guild(self.guild.id, fresh)
        self.config = fresh
        self.status_message = f"{E_ON} La Whitelist a été entièrement purgée."
        await self._refresh(interaction)

# ==============================================================================
# --- COG PRINCIPAL ---
# ==============================================================================
class AntiScamCog(commands.Cog, name="AntiScam"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.message_tracker = {}
        self.tracker_cleanup.start()

    def cog_unload(self):
        self.tracker_cleanup.cancel()

    def get_first_channel_link(self, guild: discord.Guild) -> str | None:
        if not guild.text_channels:
            return None
        return f"https://discord.com/channels/{guild.id}/{guild.text_channels[0].id}"

    def message_has_image(self, message: discord.Message) -> bool:
        for attachment in message.attachments:
            if (attachment.content_type or "").lower().startswith("image/") or (attachment.filename or "").lower().endswith(IMAGE_EXTENSIONS):
                return True
        return False

    @tasks.loop(minutes=2)
    async def tracker_cleanup(self):
        """Nettoyage intelligent de la mémoire tampon."""
        current_time = time.time()
        for guild_id in list(self.message_tracker.keys()):
            for user_id in list(self.message_tracker[guild_id].keys()):
                self.message_tracker[guild_id][user_id] = [
                    msg for msg in self.message_tracker[guild_id][user_id]
                    if current_time - msg['time'] < 180
                ]
                if not self.message_tracker[guild_id][user_id]:
                    del self.message_tracker[guild_id][user_id]

    @tracker_cleanup.before_loop
    async def before_tracker_cleanup(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        config = antiscam_config_manager.load_guild(message.guild.id)
        if not config.get("enabled", False):
            return

        guild_id = message.guild.id
        user_id = message.author.id
        current_time = time.time()

        # Vérification Whitelist
        if user_id in config.get("whitelist_users", []):
            return
            
        member_role_ids = {role.id for role in message.author.roles}
        if member_role_ids.intersection(config.get("whitelist_roles", [])):
            return

        has_link = bool(URL_REGEX.search(message.content or ""))
        has_image = self.message_has_image(message)

        if not has_link and not has_image:
            return

        if guild_id not in self.message_tracker:
            self.message_tracker[guild_id] = {}
        if user_id not in self.message_tracker[guild_id]:
            self.message_tracker[guild_id][user_id] = []

        timeframe = config.get("timeframe", 60)
        tracker = [m for m in self.message_tracker[guild_id][user_id] if current_time - m['time'] <= timeframe]
        
        tracker.append({
            'message': message,
            'content': message.content,
            'channel_id': message.channel.id,
            'time': current_time
        })
        self.message_tracker[guild_id][user_id] = tracker

        threshold = config.get("threshold", 3)
        unique_channels = {m['channel_id'] for m in tracker}

        if len(unique_channels) >= threshold:
            custom_log("warning", f"Seuil atteint pour {user_id} sur {guild_id}. Quarantaine engagée.")
            await self.trigger_quarantine(message.guild, message.author, tracker, config)
            del self.message_tracker[guild_id][user_id]

    async def trigger_quarantine(self, guild: discord.Guild, member: discord.Member, messages: list, config_dict: dict):
        # 1. Timeout maximum
        try:
            await member.timeout(discord.utils.utcnow() + timedelta(days=28), reason="Anti-Scam: Propagation de liens malveillants")
        except discord.Forbidden:
            custom_log("error", f"Timeout refusé pour {member.id} (Permissions manquantes).")
        except Exception as e:
            custom_log("error", f"Erreur inattendue Timeout pour {member.id} : {e}")

        # 2. Envoi du DM
        try:
            link = self.get_first_channel_link(guild)
            redirect = f"\n{E_RIGHT} Reviens sur le serveur : {link}\n" if link else "\n"
            dm_msg = f"{E_SHIELD} **Alerte de sécurité**\nVous avez été placé en quarantaine sur **{guild.name}** par notre système Anti-Scam.{redirect}Contactez le staff si votre compte est de nouveau sécurisé."
            await member.send(dm_msg)
        except discord.HTTPException:
            pass

        # 3. Suppression des messages incriminés
        for msg_data in messages:
            try:
                await msg_data['message'].delete()
            except Exception:
                pass

        # 4. Enregistrement en base (Rechargement pour éviter les conflits)
        try:
            fresh_config = antiscam_config_manager.load_guild(guild.id)
            if "prisonniers" not in fresh_config:
                fresh_config["prisonniers"] = {}
                
            fresh_config["prisonniers"][str(member.id)] = {
                "name": str(member),
                "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "flagged": (messages[0].get('content') or "[Médias]")[:50]
            }
            antiscam_config_manager.save_guild(guild.id, fresh_config)
            custom_log("success", f"Quarantaine de {member.id} sauvegardée avec succès.")
        except Exception as e:
            custom_log("error", f"Échec de l'écriture de la quarantaine pour {member.id} : {e}")

    @perm_command(level=3)
    @commands.hybrid_command(name="antiscam", description="Ouvrir le panneau de contrôle de l'Anti-Scam")
    async def antiscam_menu(self, ctx: commands.Context):
        """Interface d'administration Anti-Scam."""
        if not ctx.guild:
            await ctx.send(f"{E_OFF} Les configurations s'effectuent sur serveur.")
            return

        if HAS_VAX_CORE and not await ensure_command_permission(ctx, command_name="antiscam"):
            return

        custom_log("info", f"Panel Anti-Scam généré pour {ctx.author.name}")
        view = AntiScamLayoutView(self, ctx.guild, ctx.author)
        msg = await ctx.send(view=view)
        view.message = msg

async def setup(bot: commands.Bot):
    if bot.get_command("antiscam"):
        bot.remove_command("antiscam")
    await bot.add_cog(AntiScamCog(bot))