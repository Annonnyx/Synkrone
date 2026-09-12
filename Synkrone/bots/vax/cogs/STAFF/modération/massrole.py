import discord
from discord import ui
from discord.ext import commands, tasks
import asyncio
import time
import re
import os
import json
import traceback
from typing import Optional

# ==========================================
# GESTION DES CONFIGURATIONS VAX V3
# ==========================================
from utils.config_data import DataManager
from utils.config_theme import config_manager
from utils.config_perm import ensure_command_permission, perm_command
from utils.config_id import IdModal
from utils.config_emoji import Emoji as E

# ==========================================
# CONFIGURATION GLOBALE & DÉBOGAGE
# ==========================================
DEBUG_LOGS = True
ERROR_LOGS = True

# ==========================================
# CENTRALISATION DES EMOJIS UI
# ==========================================
EMOJI_ADD = getattr(E, "AJOUTER", "ðŸ“¥")
EMOJI_REMOVE = getattr(E, "SUPPRIMER", "ðŸ“¤")
EMOJI_EVERYONE = getattr(E, "MONDE", "ðŸŒ")
EMOJI_SPECIFIC = getattr(E, "CIBLE", "ðŸŽ¯")
EMOJI_ACTION_ROLE = getattr(E, "MODIFIER", "âš™ï¸")
EMOJI_ROLE = getattr(E, "ROLE", "ðŸŽ­")
EMOJI_USER = getattr(E, "PROFIL", "ðŸ‘¤")
EMOJI_TIME = getattr(E, "TEMPS", "â³")
EMOJI_LAUNCH = getattr(E, "SEND", "ðŸš€")
EMOJI_SUCCESS = getattr(E, "VALIDE", "âœ…")
EMOJI_ERROR = getattr(E, "ERREUR", "âŒ")
EMOJI_WARN = getattr(E, "ATTENTION", "âš ï¸")
EMOJI_BULLET = "ðŸ”¹"
EMOJI_ID = getattr(E, "IDENTIFIANT", "ðŸ†”")
EMOJI_TRASH = getattr(E, "SUPPRIMER", "ðŸ—‘ï¸")

# ==========================================
# UTILITAIRES DE LOGS (COLORIMÉTRIE)
# ==========================================
def log_info(message: str):
    if DEBUG_LOGS:
        print(f"\033[94m[INFO]\033[0m {message}")

def log_success(message: str):
    if DEBUG_LOGS:
        print(f"\033[92m[SUCCESS]\033[0m {message}")

def log_error(message: str):
    if ERROR_LOGS:
        print(f"\033[91m[ERROR]\033[0m {message}")

# ==========================================
# GESTION PERSISTANCE (VAX ARCHITECTURE)
# ==========================================
class MassRoleManager:
    """Gestionnaire de persistance pour les rôles temporaires via DataManager[cite: 6, 7]."""
    def __init__(self):
        self.db = DataManager("staff/moderation/massrole")
        self.legacy_dir = os.path.join(self.db.project_root, "data", "addons", "massrole")
        self._migrate_legacy_data()
        log_info("Base de données MassRole initialisée.")

    def _migrate_legacy_data(self):
        """Migre les fichiers legacy de l'ancien dossier de données vers staff/moderation/massrole."""
        if not os.path.exists(self.legacy_dir):
            return

        for filename in os.listdir(self.legacy_dir):
            if not filename.endswith(".json"):
                continue
            gid = filename.rsplit(".", 1)[0]
            if not gid.isdigit():
                continue

            src = os.path.join(self.legacy_dir, filename)
            try:
                with open(src, "r", encoding="utf-8") as f:
                    legacy = json.load(f)
            except Exception:
                legacy = []

            try:
                current = self.db.load(gid)
                merged = []
                if isinstance(current, list):
                    merged.extend(current)
                if isinstance(legacy, list):
                    merged.extend(legacy)

                if merged:
                    self.db.save(gid, merged)
            except Exception:
                pass

            try:
                os.remove(src)
            except Exception:
                pass

        # Supprime le dossier legacy s'il est vide.
        try:
            if os.path.exists(self.legacy_dir) and not os.listdir(self.legacy_dir):
                os.rmdir(self.legacy_dir)
        except Exception:
            pass

    def load_data(self, guild_id: int) -> list[dict]:
        return self.db.load(guild_id) or []

    def save_temp_role(self, guild_id: int, member_id: int, role_id: int, end_time: float):
        data = self.load_data(guild_id)
        data.append({"member_id": member_id, "role_id": role_id, "end_time": end_time})
        self.db.save(guild_id, data)

    def remove_entry(self, guild_id: int, entry: dict):
        data = self.load_data(guild_id)
        data = [d for d in data if not (d['member_id'] == entry['member_id'] and d['role_id'] == entry['role_id'])]
        self.db.save(guild_id, data)

    def get_all_guilds(self) -> list[int]:
        guilds = []
        if os.path.exists(self.db.path):
            for gid in self.db.get_all_files():
                if str(gid).isdigit():
                    guilds.append(int(gid))
        return guilds

# ==========================================
# INTERFACES INTERACTIVES (LAYOUT V2)
# ==========================================
class DurationModal(ui.Modal, title="Définir la durée"):
    """Modal pour saisir la durée d'attribution d'un rôle temporaire."""
    duration = ui.TextInput(label="Durée", placeholder="Ex: 10s, 5m, 2h, 1d", min_length=2, required=True)
    
    def __init__(self, view: "MassRoleLayoutView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        seconds = self.view.cog.parse_duration(self.duration.value)
        if not seconds:
            self.view.error_msg = "Format de durée invalide. Utilisez s, m, h ou d."
            await self.view._refresh(interaction)
            return
            
        self.view.duration_str = self.duration.value
        self.view.duration_seconds = seconds
        self.view.error_msg = ""
        await self.view._refresh(interaction)


class MassRoleLayoutView(ui.LayoutView):
    """Vue interactive globale pour la programmation du MassRole via LayoutV2[cite: 6, 8]."""
    def __init__(self, ctx: commands.Context, cog: "MassRole"):
        super().__init__(timeout=600)
        self.ctx = ctx
        self.cog = cog
        self.guild = ctx.guild
        
        # États de la vue
        self.action = "Ajouter"
        self.target_mode = "Everyone"
        self.selected_role: Optional[discord.Role] = None
        
        # Cibles spécifiques (IDs)
        self.target_users: list[int] = []
        self.target_roles: list[int] = []
        
        self.duration_str = "Permanent"
        self.duration_seconds: Optional[int] = None
        self.error_msg = ""
        self.success_msg = ""
        
        self.message: Optional[discord.Message] = None
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Sécurisation de l'interaction (Pattern Vax strict)[cite: 6, 7]."""
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(f"{EMOJI_ERROR} Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        return True

    def _selected_ids(self, interaction: discord.Interaction) -> set[int]:
        """Extrait les IDs depuis un menu déroulant natif[cite: 7]."""
        raw_values = interaction.data.get("values", []) if interaction.data else []
        return {int(v) for v in raw_values if str(v).isdigit()}

    def _build(self):
        """Construction intégrale du conteneur selon les paramètres en cours[cite: 6, 8]."""
        self.clear_items()
        theme = config_manager.get_layout_v2_theme(self.ctx.guild.id, self.ctx.guild, self.ctx.author, self.cog.bot)
        color = int(theme.get("color", 0x5865F2))
        footer = theme.get("footer_text", "")

        container = ui.Container(accent_color=discord.Color(color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {EMOJI_ACTION_ROLE} Programmation MassRole"))
        
        # --- Évaluation de la validité pour afficher le bouton Lancer ---
        is_ready = self.selected_role is not None
        if self.target_mode == "Spécifique" and not self.target_users and not self.target_roles:
            is_ready = False

        # --- Formatage des informations ---
        role_display = f"`@{self.selected_role.name}`" if self.selected_role else f"{EMOJI_ERROR} *Non défini*"
        
        if self.success_msg:
            desc = f"**{EMOJI_SUCCESS} OPÉRATION TERMINÉE**\n{self.success_msg}"
        else:
            desc = "Sélectionnez l'action, la cible, et configurez le rôle à appliquer.\n\n"
            desc += f"{EMOJI_BULLET} **Action :** {self.action}\n"
            desc += f"{EMOJI_BULLET} **Mode Cible :** {self.target_mode}\n"
            desc += f"{EMOJI_BULLET} **Rôle à appliquer :** {role_display}\n"
            
            if self.target_mode == "Spécifique":
                # Formatage précis des cibles avec mentions backticks
                users_display = []
                for uid in self.target_users:
                    m = self.guild.get_member(uid)
                    users_display.append(f"`@{m.name}`" if m else f"`ID:{uid}`")
                
                roles_display = []
                for rid in self.target_roles:
                    r = self.guild.get_role(rid)
                    roles_display.append(f"`@{r.name}`" if r else f"`ID:{rid}`")

                desc += f"{EMOJI_BULLET} **Cibles (Utilisateurs) :** {', '.join(users_display) if users_display else 'Aucun'}\n"
                desc += f"{EMOJI_BULLET} **Cibles (Rôles) :** {', '.join(roles_display) if roles_display else 'Aucun'}\n"
            
            if self.action == "Ajouter":
                desc += f"{EMOJI_BULLET} **Durée :** {self.duration_str}\n"

            if self.error_msg:
                desc += f"\n{EMOJI_WARN} **Erreur :** {self.error_msg}"

        container.add_item(ui.TextDisplay(desc))

        # --- Si l'opération est terminée, on ne recrée pas les menus ---
        if not self.success_msg:
            
            # 1. Sélection de l'Action (1 Select par ActionRow)
            row_action = ui.ActionRow()
            action_select = ui.Select(
                placeholder="ðŸ”§ Choisir l'action...",
                options=[
                    discord.SelectOption(label="Ajouter le rôle", value="Ajouter", emoji=EMOJI_ADD, default=(self.action=="Ajouter")),
                    discord.SelectOption(label="Retirer le rôle", value="Retirer", emoji=EMOJI_REMOVE, default=(self.action=="Retirer"))
                ],
                custom_id="select_action"
            )
            action_select.callback = self.select_action
            row_action.add_item(action_select)
            container.add_item(row_action)

            # 2. Sélection du Mode Cible (1 Select par ActionRow)
            row_target = ui.ActionRow()
            target_select = ui.Select(
                placeholder="ðŸ‘¥ Choisir la cible...",
                options=[
                    discord.SelectOption(label="Tout le monde", value="Everyone", emoji=EMOJI_EVERYONE, default=(self.target_mode=="Everyone")),
                    discord.SelectOption(label="Cibles spécifiques", value="Spécifique", emoji=EMOJI_SPECIFIC, default=(self.target_mode=="Spécifique"))
                ],
                custom_id="select_target"
            )
            target_select.callback = self.select_target
            row_target.add_item(target_select)
            container.add_item(row_target)

            # 3. Section Cibles spécifiques (Uniquement boutons ID & Select de retrait)
            if self.target_mode == "Spécifique":
                container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
                container.add_item(ui.TextDisplay("### ðŸŽ¯ Ajouter des Cibles"))
                
                # Boutons manuels ID
                row_id_modals = ui.ActionRow()
                btn_id_user = ui.Button(label="ID Utilisateur", style=discord.ButtonStyle.secondary, emoji=EMOJI_ID)
                btn_id_user.callback = self.open_target_user_modal
                row_id_modals.add_item(btn_id_user)
                
                btn_id_role = ui.Button(label="ID Rôle", style=discord.ButtonStyle.secondary, emoji=EMOJI_ID)
                btn_id_role.callback = self.open_target_role_modal
                row_id_modals.add_item(btn_id_role)
                
                # Affichage conditionnel du bouton Vider
                if self.target_users or self.target_roles:
                    btn_clear = ui.Button(label="Vider", style=discord.ButtonStyle.danger, emoji=EMOJI_TRASH)
                    btn_clear.callback = self.clear_targets
                    row_id_modals.add_item(btn_clear)
                
                container.add_item(row_id_modals)

                # Sélecteur de suppression de cible (Affichage conditionnel)
                if self.target_users or self.target_roles:
                    remove_options = []
                    for uid in self.target_users:
                        m = self.guild.get_member(uid)
                        remove_options.append(discord.SelectOption(label=f"Utilisateur: {m.name if m else uid}", value=f"user_{uid}", emoji=EMOJI_USER))
                    for rid in self.target_roles:
                        r = self.guild.get_role(rid)
                        remove_options.append(discord.SelectOption(label=f"Rôle: {r.name if r else rid}", value=f"role_{rid}", emoji=EMOJI_ROLE))

                    if remove_options:
                        row_remove_target = ui.ActionRow()
                        remove_target_select = ui.Select(
                            placeholder="Sélectionnez une cible pour la retirer...",
                            options=remove_options[:25],
                            custom_id="remove_target"
                        )
                        remove_target_select.callback = self.on_remove_target_select
                        row_remove_target.add_item(remove_target_select)
                        container.add_item(row_remove_target)

            # 4. Paramétrage de l'Action (Rôle à appliquer via Native Select + Button ID)
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
            container.add_item(ui.TextDisplay("### âš™ï¸ Configuration de l'Action"))
            
            # Select natif pour le rôle d'action
            row_action_role_select = ui.ActionRow()
            action_role_select = ui.RoleSelect(placeholder="Choisir le rôle à appliquer...", min_values=1, max_values=1)
            action_role_select.callback = self.on_action_role_select
            row_action_role_select.add_item(action_role_select)
            container.add_item(row_action_role_select)

            # Boutons de configuration supplémentaires
            row_config_btns = ui.ActionRow()
            btn_action_role = ui.Button(label="ID Rôle", style=discord.ButtonStyle.primary, emoji=EMOJI_ACTION_ROLE)
            btn_action_role.callback = self.open_action_role_modal
            row_config_btns.add_item(btn_action_role)

            # Affichage conditionnel du bouton Temporaire
            if self.action == "Ajouter":
                btn_time = ui.Button(label="Temporaire", style=discord.ButtonStyle.secondary, emoji=EMOJI_TIME)
                btn_time.callback = self.open_duration_modal
                row_config_btns.add_item(btn_time)
                
            container.add_item(row_config_btns)

            # 5. Bouton de Lancement (Conditionnel Poka-Yoke)
            if is_ready:
                row_exec = ui.ActionRow()
                btn_exec = ui.Button(label="ðŸš€ LANCER L'ACTION", style=discord.ButtonStyle.success)
                btn_exec.callback = self.execute_massrole
                row_exec.add_item(btn_exec)
                container.add_item(row_exec)

        if footer:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer))

        self.add_item(container)

    async def _refresh(self, interaction: discord.Interaction):
        """Rafraîchit la vue interactive en place[cite: 6, 8]."""
        self._build()
        await interaction.response.edit_message(view=self)
        
    async def _refresh_silent(self):
        """Rafraîchit la vue sans nouvelle interaction."""
        if self.message:
            self._build()
            await self.message.edit(view=self)

    # --- CALLBACKS DE MODE ---
    async def select_action(self, interaction: discord.Interaction):
        self.action = interaction.data.get("values", ["Ajouter"])[0]
        if self.action == "Retirer":
            self.duration_str = "Permanent"
            self.duration_seconds = None
        await self._refresh(interaction)

    async def select_target(self, interaction: discord.Interaction):
        self.target_mode = interaction.data.get("values", ["Everyone"])[0]
        await self._refresh(interaction)

    # --- CALLBACKS CIBLES (BOUTONS ID & SUPPRESSION) ---
    async def clear_targets(self, interaction: discord.Interaction):
        self.target_users = []
        self.target_roles = []
        await self._refresh(interaction)

    async def open_target_user_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(IdModal("user", self._on_target_user_submit))

    async def _on_target_user_submit(self, interaction: discord.Interaction, target: discord.abc.Snowflake):
        if isinstance(target, discord.Member) or getattr(target, 'id', None):
            uid = target.id
            if uid not in self.target_users:
                self.target_users.append(uid)
            self.error_msg = ""
        else:
            self.error_msg = "Utilisateur introuvable."
        await self._refresh(interaction)

    async def open_target_role_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(IdModal("role", self._on_target_role_submit))

    async def _on_target_role_submit(self, interaction: discord.Interaction, target: discord.abc.Snowflake):
        if isinstance(target, discord.Role):
            if target.id not in self.target_roles:
                self.target_roles.append(target.id)
            self.error_msg = ""
        else:
            self.error_msg = "Le rôle cible n'a pas pu être identifié."
        await self._refresh(interaction)

    async def on_remove_target_select(self, interaction: discord.Interaction):
        """Supprime spécifiquement une cible sélectionnée via le menu déroulant."""
        val = interaction.data.get("values", [""])[0]
        if val.startswith("user_"):
            uid = int(val.split("_")[1])
            if uid in self.target_users:
                self.target_users.remove(uid)
        elif val.startswith("role_"):
            rid = int(val.split("_")[1])
            if rid in self.target_roles:
                self.target_roles.remove(rid)
        await self._refresh(interaction)

    # --- CONFIGURATION ACTION ---
    async def on_action_role_select(self, interaction: discord.Interaction):
        """Récupère le rôle d'action via le sélecteur natif Discord."""
        values = self._selected_ids(interaction)
        if values:
            role_id = list(values)[0]
            role = self.ctx.guild.get_role(role_id)
            if role:
                self.selected_role = role
                self.error_msg = ""
            else:
                self.error_msg = "Le rôle sélectionné n'a pas pu être résolu."
        await self._refresh(interaction)

    async def open_action_role_modal(self, interaction: discord.Interaction):
        """Utilisation de l'IdModal standard Vax v3 pour le rôle à appliquer[cite: 6, 7]."""
        await interaction.response.send_modal(IdModal("role", self._on_action_role_submit))

    async def _on_action_role_submit(self, interaction: discord.Interaction, target: discord.abc.Snowflake):
        if isinstance(target, discord.Role):
            self.selected_role = target
            self.error_msg = ""
        else:
            self.error_msg = "Le rôle d'action n'a pas pu être identifié."
        await self._refresh(interaction)

    async def open_duration_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(DurationModal(self))

    # --- EXECUTION ---
    async def execute_massrole(self, interaction: discord.Interaction):
        """Moteur principal d'exécution d'attribution ou de retrait."""
        if not self.selected_role:
            return # Sécurité supplémentaire (Poka-Yoke)

        # Compilation des cibles uniques
        targets = set()
        if self.target_mode == "Everyone":
            targets = {m for m in self.ctx.guild.members if not m.bot}
        else:
            for uid in self.target_users:
                member = self.ctx.guild.get_member(uid)
                if member and not member.bot:
                    targets.add(member)
            
            for rid in self.target_roles:
                role = self.ctx.guild.get_role(rid)
                if role:
                    for member in role.members:
                        if not member.bot:
                            targets.add(member)

        if not targets:
            self.error_msg = "La liste des cibles est vide ou ne contient que des bots."
            await self._refresh(interaction)
            return

        # Suspension absolue de l'interaction pendant le traitement lourd (pas d'éphémère)
        await interaction.response.defer()
        
        self.error_msg = "Traitement en cours... Veuillez patienter."
        await self._refresh_silent()

        success = 0
        fail = 0

        for m in targets:
            try:
                if self.action == "Ajouter":
                    await m.add_roles(self.selected_role, reason=f"MassRole par {self.ctx.author}")
                    if self.duration_seconds:
                        self.cog.db.save_temp_role(self.ctx.guild.id, m.id, self.selected_role.id, time.time() + self.duration_seconds)
                else:
                    await m.remove_roles(self.selected_role, reason=f"MassRole par {self.ctx.author}")
                success += 1
            except (discord.Forbidden, discord.HTTPException):
                fail += 1

        action_word = "attribué à" if self.action == "Ajouter" else "retiré de"
        self.success_msg = f"Le rôle a été {action_word} **{success}** membre(s).\nÉchecs (hiérarchie/permissions) : **{fail}**"
        self.error_msg = ""
        
        log_success(f"MassRole terminé : {success} succès, {fail} échecs sur {self.ctx.guild.name}.")
        await self._refresh_silent()
        self.stop()

# ==========================================
# COG PRINCIPAL : MASSROLE
# ==========================================
class MassRole(commands.Cog):
    """
    Système avancé d'attribution et révocation de rôles en masse (LayoutV2, Permissions).
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = MassRoleManager()
        self.check_temp_roles.start()
        log_info("Module 'MassRole' initialisé.")

    def parse_duration(self, s: str) -> Optional[int]:
        """Convertit une string formatée (ex: 5m, 1h) en secondes."""
        m = re.fullmatch(r"(\d+)([smhd])", s.lower())
        if not m:
            return None
        multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
        return int(m[1]) * multipliers[m[2]]

    @tasks.loop(minutes=30)
    async def check_temp_roles(self):
        """Tâche de fond vérifiant l'expiration des rôles temporaires."""
        now = time.time()
        guilds = self.db.get_all_guilds()
        
        for gid in guilds:
            guild = self.bot.get_guild(gid)
            if not guild:
                continue
                
            entries = self.db.load_data(gid)
            for entry in entries:
                if now >= entry['end_time']:
                    member = guild.get_member(entry['member_id'])
                    role = guild.get_role(entry['role_id'])
                    if member and role:
                        try:
                            await member.remove_roles(role, reason="Expiration durée MassRole")
                            log_info(f"Rôle temp expiré : {role.name} retiré de {member.name}.")
                        except (discord.Forbidden, discord.HTTPException):
                            log_error(f"Impossible de retirer le rôle {role.name} à {member.name} (Forbidden/HTTPException).")
                    self.db.remove_entry(gid, entry)

    @check_temp_roles.before_loop
    async def before_check_temp_roles(self):
        await self.bot.wait_until_ready()

    @perm_command(level=3)
    @commands.hybrid_command(name="massrole", description="Interface Vax avancée pour la gestion de rôles en masse.")
    async def massrole(self, ctx: commands.Context):
        """Point d'entrée du système MassRole sécurisé[cite: 6, 8]."""
        log_info(f"Exécution de massrole par {ctx.author} sur {ctx.guild.name}")
        
        # Vérification stricte via l'écosystème de permissions[cite: 6, 8]
        if not await ensure_command_permission(ctx, command_name="massrole"):
            return

        # Refus formel de l'éphémère pour les commandes métier Vax
        await ctx.defer(ephemeral=False)
        
        try:
            view = MassRoleLayoutView(ctx, self)
            message = await ctx.send(view=view)
            view.message = message
        except Exception as e:
            log_error(f"Erreur d'initialisation de la vue MassRole : {e}")
            traceback.print_exc()

async def setup(bot: commands.Bot):
    await bot.add_cog(MassRole(bot))
    log_success("Cog 'MassRole' compilé et déployé avec succès (Ergonomie avancée).")
