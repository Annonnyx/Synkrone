import discord
from discord import ui, app_commands
from discord.ext import commands
import uuid
import traceback
from datetime import datetime
from typing import Optional

# ==============================================================================
# --- IMPORTS MÉTIER VAX ---
# Utilisation de nos gestionnaires internes pour la configuration et le rendu.
from utils.config_data import DataManager
from utils.config_theme import config_manager
from utils.config_perm import ensure_command_permission, perm_command
from utils.config_emoji import Emoji as E

# ==============================================================================
# --- CONFIGURATION GLOBALE & DÉBOGAGE ---
# ==============================================================================
DEBUG_LOGS = True
ERROR_LOGS_ONLY = False

# ==============================================================================
# --- CENTRALISATION DES EMOJIS ---
# Variables dédiées au sommet du fichier pour modification rapide et globale.
# ==============================================================================
EMOJI_SUCCESS = getattr(E, 'VALIDER', "✅")
EMOJI_ERROR = getattr(E, 'REFUSER', "❌")
EMOJI_ADD = getattr(E, 'AJOUTER', "➕")
EMOJI_EDIT = getattr(E, 'MODIFIER', "✏️")
EMOJI_DELETE = getattr(E, 'SUPPRIMER', "🗑️")
EMOJI_BACK = getattr(E, 'RETOUR', "↩️")
EMOJI_PROFILE = getattr(E, 'PROFIL', "👤")
EMOJI_TROPHY = getattr(E, 'CLASSEMENT', "🏆")
EMOJI_GEAR = getattr(E, 'MODIFIER', "⚙️")
EMOJI_CALENDAR = getattr(E, 'HISTOIRE', "📅")
EMOJI_ROLE = getattr(E, 'ROLE', "🎭")

# ==============================================================================
# --- UTILITAIRES DE LOGS ---
# ==============================================================================
def log_system(action: str, message: str, is_error: bool = False):
    """Système de logs colorés respectant les variables globales de débogage."""
    if ERROR_LOGS_ONLY and not is_error:
        return
    if not DEBUG_LOGS and not is_error:
        return

    COLOR_RESET = "\033[0m"
    COLOR_INFO = "\033[96m"   # Cyan
    COLOR_SUCCESS = "\033[92m" # Vert
    COLOR_ERROR = "\033[91m"   # Rouge

    color = COLOR_ERROR if is_error else COLOR_INFO
    prefix = "[ERROR Reward]" if is_error else "[INFO Reward]"
    
    print(f"{color}{prefix} [{action}] {message}{COLOR_RESET}")

# ==============================================================================
# --- GESTION DES DONNÉES (DataManager) ---
# ==============================================================================
class RewardConfigManager:
    def __init__(self):
        # Utilisation de DataManager pour stocker dans data/staff/configuration/data_reward/<id>.json
        self.data = DataManager("staff/configuration/data_reward")

    def load(self, guild_id: int) -> dict:
        raw = self.data.load(guild_id) or {}
        return {
            "rewards": raw.get("rewards", {}),
            "users": raw.get("users", {})
        }

    def save(self, guild_id: int, config: dict):
        self.data.save(guild_id, config)

reward_manager = RewardConfigManager()

# ==============================================================================
# --- INTERFACES UTILISATEUR (Layout V2 & Modals) ---
# ==============================================================================
class RewardModal(ui.Modal):
    """Modal dynamique pour l'ajout ou la modification d'un reward."""
    name = ui.TextInput(label="Nom de l'événement", placeholder="Ex: Noël 2026", style=discord.TextStyle.short, required=True, max_length=50)
    date_str = ui.TextInput(label="Date requise (JJ/MM/AAAA)", placeholder="Ex: 25/12/2026", style=discord.TextStyle.short, required=True, min_length=10, max_length=10)
    title_str = ui.TextInput(label="Titre à obtenir (Optionnel)", placeholder="Ex: Lutin de Noël", style=discord.TextStyle.short, required=False, max_length=100)
    role_id = ui.TextInput(label="ID du rôle (Optionnel)", placeholder="Ex: 123456789101112131", style=discord.TextStyle.short, required=False, max_length=20)

    def __init__(self, view: "RewardLayoutView", action: str = "add", reward_id: str = None, default_data: dict = None):
        # Les émojis personnalisés ne sont pas supportés par l'API Discord dans les titres de modales.
        super().__init__(title="Créer un Reward" if action == "add" else "Modifier le Reward")
        self.view = view
        self.action = action
        self.reward_id = reward_id or str(uuid.uuid4())[:8]

        if default_data:
            self.name.default = default_data.get("name", "")
            self.date_str.default = datetime.fromtimestamp(default_data.get("date_timestamp")).strftime("%d/%m/%Y")
            self.title_str.default = default_data.get("title", "")
            self.role_id.default = str(default_data.get("role_id", "")) if default_data.get("role_id") else ""

    async def on_submit(self, interaction: discord.Interaction):
        try:
            req_date = datetime.strptime(self.date_str.value.strip(), "%d/%m/%Y")
        except ValueError:
            await interaction.response.send_message(f"{EMOJI_ERROR} Le format de la date doit être exactement `JJ/MM/AAAA`.", ephemeral=True)
            return

        if not self.title_str.value.strip() and not self.role_id.value.strip():
            await interaction.response.send_message(f"{EMOJI_ERROR} Vous devez définir au moins un Titre ou un ID de Rôle.", ephemeral=True)
            return

        r_id = None
        if self.role_id.value.strip():
            if not self.role_id.value.isdigit():
                await interaction.response.send_message(f"{EMOJI_ERROR} L'ID du rôle doit être uniquement numérique.", ephemeral=True)
                return
            r_id = int(self.role_id.value.strip())
            if not self.view.guild.get_role(r_id):
                await interaction.response.send_message(f"{EMOJI_ERROR} Impossible de trouver le rôle `{r_id}` sur ce serveur.", ephemeral=True)
                return

        config = reward_manager.load(self.view.guild.id)
        config["rewards"][self.reward_id] = {
            "name": self.name.value.strip(),
            "date_timestamp": req_date.timestamp(),
            "title": self.title_str.value.strip() if self.title_str.value.strip() else None,
            "role_id": r_id
        }
        reward_manager.save(self.view.guild.id, config)
        log_system("DB_SAVE", f"Reward {self.action} : {self.reward_id} sur {self.view.guild.id}")

        self.view.state = "main"
        self.view.status_message = f"{EMOJI_SUCCESS} Le reward **{self.name.value}** a été {'créé' if self.action == 'add' else 'modifié'} avec succès."
        await self.view._refresh(interaction)

class RewardLayoutView(ui.LayoutView):
    """LayoutV2 gérant l'intégralité du système Reward via une machine à états."""
    def __init__(self, cog: "RewardsCog", guild: discord.Guild, user: discord.Member, target_user: discord.Member = None, initial_state: str = "main"):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.user = user
        self.target_user = target_user or user
        self.state = initial_state # États: "main", "profile", "edit_select", "delete_select"
        self.status_message = ""
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            # Rejet ferme sans message éphémère.
            await interaction.response.send_message(f"{EMOJI_ERROR} Action refusée : ce menu est verrouillé par {self.user.mention}.")
            return False
        return True

    def _build(self):
        self.clear_items()
        
        # Récupération de l'esthétique du serveur.
        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.cog.bot)
        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text", "")

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        
        # Affichage d'un statut temporaire si existant
        if self.status_message:
            container.add_item(ui.TextDisplay(f"> {self.status_message}"))
            self.status_message = ""

        if self.state == "profile":
            self._build_profile(container)
        elif self.state == "edit_select":
            self._build_select_menu(container, "edit")
        elif self.state == "delete_select":
            self._build_select_menu(container, "delete")
        else:
            self._build_main_menu(container)

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

    # --- SOUS-MENUS ---

    def _build_main_menu(self, container: ui.Container):
        container.add_item(ui.TextDisplay(f"# {EMOJI_GEAR} Gestion des Rewards"))
        container.add_item(ui.TextDisplay("Sélectionnez une action d'administration ou consultez un profil."))

        action_row = ui.ActionRow()
        
        btn_add = ui.Button(label="Ajouter", style=discord.ButtonStyle.success, emoji=EMOJI_ADD)
        btn_add.callback = self._on_add_click
        action_row.add_item(btn_add)

        btn_edit = ui.Button(label="Modifier", style=discord.ButtonStyle.primary, emoji=EMOJI_EDIT)
        btn_edit.callback = lambda i: self._change_state(i, "edit_select")
        action_row.add_item(btn_edit)

        btn_delete = ui.Button(label="Supprimer", style=discord.ButtonStyle.danger, emoji=EMOJI_DELETE)
        btn_delete.callback = lambda i: self._change_state(i, "delete_select")
        action_row.add_item(btn_delete)

        btn_profile = ui.Button(label="Mon Profil", style=discord.ButtonStyle.secondary, emoji=EMOJI_PROFILE)
        btn_profile.callback = lambda i: self._change_state(i, "profile")
        action_row.add_item(btn_profile)

        container.add_item(action_row)

    def _build_select_menu(self, container: ui.Container, action: str):
        config = reward_manager.load(self.guild.id)
        rewards = config.get("rewards", {})
        
        title = f"# {EMOJI_EDIT} Modifier un Reward" if action == "edit" else f"# {EMOJI_DELETE} Supprimer un Reward"
        container.add_item(ui.TextDisplay(title))

        options = []
        for r_id, r_data in list(rewards.items())[:25]:
            date_str = datetime.fromtimestamp(r_data["date_timestamp"]).strftime("%d/%m/%Y")
            options.append(discord.SelectOption(
                label=r_data["name"][:100], 
                description=f"Date: {date_str}", 
                value=r_id,
                emoji=EMOJI_EDIT if action == "edit" else EMOJI_DELETE
            ))

        select_row = ui.ActionRow()
        if options:
            select = ui.Select(placeholder=f"Sélectionnez un reward...", min_values=1, max_values=1, options=options)
            select.callback = self._on_edit_select if action == "edit" else self._on_delete_select
            select_row.add_item(select)
        else:
            container.add_item(ui.TextDisplay("*Aucun reward configuré sur ce serveur.*"))
        
        if len(select_row.children) > 0:
            container.add_item(select_row)

        back_row = ui.ActionRow()
        btn_back = ui.Button(label="Retour", style=discord.ButtonStyle.secondary, emoji=EMOJI_BACK)
        btn_back.callback = lambda i: self._change_state(i, "main")
        back_row.add_item(btn_back)
        container.add_item(back_row)

    def _build_profile(self, container: ui.Container):
        self.cog.sync_user_rewards(self.guild, self.target_user)
        config = reward_manager.load(self.guild.id)
        user_data = config["users"].get(str(self.target_user.id), {}).get("obtained_rewards", {})

        container.add_item(ui.TextDisplay(f"# {EMOJI_PROFILE} Profil Rewards : {self.target_user.display_name}"))

        titres_list = []
        roles_list = []

        for r_id, obt_ts in user_data.items():
            if r_id in config["rewards"]:
                r_data = config["rewards"][r_id]
                date_str = datetime.fromtimestamp(obt_ts).strftime('%d/%m/%Y')
                
                if r_data.get("title"):
                    titres_list.append(f"- **{r_data['title']}** *(Obtenu le {date_str})*")
                if r_data.get("role_id"):
                    role = self.guild.get_role(r_data["role_id"])
                    if role: roles_list.append(role.mention)

        if not titres_list and not roles_list:
            container.add_item(ui.TextDisplay("Cet utilisateur n'a débloqué aucune récompense d'ancienneté pour le moment."))
        else:
            if titres_list:
                container.add_item(ui.TextDisplay(f"### {EMOJI_TROPHY} Titres obtenus\n" + "\n".join(titres_list)))
            if roles_list:
                container.add_item(ui.TextDisplay(f"### {EMOJI_ROLE} Rôles obtenus\n" + " ".join(roles_list)))

        # Intégration ergonomique de l'avatar utilisateur via UI Thumbnail
        container.add_item(ui.Section(
            "Identité Discord", 
            accessory=ui.Thumbnail(self.target_user.display_avatar.url, description=f"Avatar de {self.target_user.display_name}")
        ))

        if self.user.guild_permissions.administrator or self.user.id == self.guild.owner_id:
            back_row = ui.ActionRow()
            btn_back = ui.Button(label="Menu Principal", style=discord.ButtonStyle.secondary, emoji=EMOJI_BACK)
            btn_back.callback = lambda i: self._change_state(i, "main")
            back_row.add_item(btn_back)
            container.add_item(back_row)

    # --- CALLBACKS & ACTIONS ---

    async def _change_state(self, interaction: discord.Interaction, new_state: str):
        self.state = new_state
        await self._refresh(interaction)

    async def _on_add_click(self, interaction: discord.Interaction):
        await interaction.response.send_modal(RewardModal(self, action="add"))

    async def _on_edit_select(self, interaction: discord.Interaction):
        reward_id = interaction.data.get("values", [None])[0]
        if not reward_id: return
        
        config = reward_manager.load(self.guild.id)
        reward_data = config["rewards"].get(reward_id)
        await interaction.response.send_modal(RewardModal(self, action="edit", reward_id=reward_id, default_data=reward_data))

    async def _on_delete_select(self, interaction: discord.Interaction):
        reward_id = interaction.data.get("values", [None])[0]
        if not reward_id: return
        
        config = reward_manager.load(self.guild.id)
        reward_data = config["rewards"].pop(reward_id, None)
        if reward_data:
            reward_manager.save(self.guild.id, config)
            log_system("DB_DELETE", f"Reward supprimé : {reward_id} sur {self.guild.id}")
            self.status_message = f"{EMOJI_SUCCESS} Le reward **{reward_data['name']}** a été supprimé définitivement."
        
        self.state = "main"
        await self._refresh(interaction)


# ==============================================================================
# --- COG PRINCIPAL ---
# ==============================================================================
class RewardsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log_system("INIT", "Module Rewards V3 initialisé.")

    def sync_user_rewards(self, guild: discord.Guild, target: discord.Member):
        """Synchronise l'éligibilité de l'utilisateur avec la base de données."""
        config = reward_manager.load(guild.id)
        user_str_id = str(target.id)
        current_ts = datetime.now().timestamp()
        
        if user_str_id not in config["users"]:
            config["users"][user_str_id] = {"obtained_rewards": {}}

        user_data = config["users"][user_str_id]["obtained_rewards"]
        updated = False
        roles_to_add = []

        for r_id, r_data in config["rewards"].items():
            if r_id not in user_data:
                if current_ts >= r_data["date_timestamp"]:
                    if target.joined_at and target.joined_at.timestamp() <= r_data["date_timestamp"]:
                        user_data[r_id] = r_data["date_timestamp"] 
                        updated = True
                        
                        if r_data.get("role_id"):
                            role = guild.get_role(r_data["role_id"])
                            if role and role not in target.roles:
                                roles_to_add.append(role)

        if updated:
            reward_manager.save(guild.id, config)
            if roles_to_add and guild.me.guild_permissions.manage_roles:
                # Ajout asynchrone non-bloquant
                self.bot.loop.create_task(self._safe_add_roles(target, roles_to_add))

    async def _safe_add_roles(self, member: discord.Member, roles: list):
        try:
            await member.add_roles(*roles, reason="Auto-claim Rewards")
        except Exception as e:
            log_system("ROLES_ERR", f"Échec d'attribution des rôles pour {member.id} : {e}", is_error=True)

    @perm_command(level=2) # Niveau administratif
    @commands.hybrid_command(name="reward", description="Affiche le profil Reward ou gère le système.")
    @app_commands.describe(cible="L'utilisateur dont vous souhaitez voir le profil (Optionnel)")
    async def reward_cmd(self, ctx: commands.Context, cible: Optional[discord.Member] = None):
        if not ctx.guild:
            await ctx.send(f"{EMOJI_ERROR} Cette commande nécessite un contexte serveur valide.")
            return

        # Vérification d'habilitation stricte via config_perm
        if not await ensure_command_permission(ctx, command_name="reward"):
            return

        is_admin = ctx.author.guild_permissions.administrator or ctx.author.id == ctx.guild.owner_id
        
        if cible is not None or not is_admin:
            target_user = cible if cible else ctx.author
            view = RewardLayoutView(self, ctx.guild, ctx.author, target_user=target_user, initial_state="profile")
            await ctx.send(view=view)
            return

        # Interface Admin principale persistante
        log_system("COMMAND", f"Déploiement du Layout d'administration /reward par {ctx.author}")
        view = RewardLayoutView(self, ctx.guild, ctx.author, initial_state="main")
        await ctx.send(view=view)

async def setup(bot: commands.Bot):
    if bot.get_command("reward"):
        bot.remove_command("reward")
    await bot.add_cog(RewardsCog(bot))