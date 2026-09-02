import discord
from discord import ui, app_commands
from discord.ext import commands
import math
import traceback

# ==============================================================================
# --- IMPORTS MÉTIER VAX ---
# Utilisation stricte de nos gestionnaires internes pour garantir l'intégrité.
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
# ==============================================================================
E_ON = getattr(E, 'VALIDER', "✅")
E_OFF = getattr(E, 'REFUSER', "❌")
E_WARN = getattr(E, 'ATTENTION', "⚠️")
E_ADD = getattr(E, 'AJOUTER', "➕")
E_LIST = getattr(E, 'LISTE', "📋")
E_TRASH = getattr(E, 'SUPPRIMER', "🗑️")
E_BACK = getattr(E, 'RETOUR', "↩️")
E_PING = getattr(E, 'CLOCHE', "🔔")
E_NAV_LEFT = getattr(E, 'FLECHE_GAUCHE', "⬅️")
E_NAV_RIGHT = getattr(E, 'FLECHE_DROITE', "➡️")

# ==============================================================================
# --- UTILITAIRES DE LOGS ---
# ==============================================================================
def log_sys(action: str, message: str, is_error: bool = False):
    """Système de logs dynamiques respectant les variables globales de débogage."""
    if ERROR_LOGS_ONLY and not is_error:
        return
    if not DEBUG_LOGS and not is_error:
        return

    COLOR_RESET = "\033[0m"
    COLOR_INFO = "\033[96m"   # Cyan
    COLOR_ERROR = "\033[91m"   # Rouge
    color = COLOR_ERROR if is_error else COLOR_INFO
    prefix = "[ERREUR AutoPing]" if is_error else "[INFO AutoPing]"
    print(f"{color}{prefix} [{action}] {message}{COLOR_RESET}")

# ==============================================================================
# --- GESTIONNAIRE DE DONNÉES (DataManager) ---
# ==============================================================================
class AutoPingManager:
    def __init__(self):
        self.data = DataManager("staff/configuration/data_autoping")

    def load(self, guild_id: int) -> dict:
        # Structure attendue: { "channel_id": "role_id" }
        return self.data.load(guild_id) or {}

    def save(self, guild_id: int, config: dict):
        self.data.save(guild_id, config)

autoping_db = AutoPingManager()

# ==============================================================================
# --- INTERFACE UTILISATEUR (Layout V2) ---
# ==============================================================================
class AutoPingLayoutView(ui.LayoutView):
    """Vue V2 centralisée gérant la navigation via une machine à états."""
    def __init__(self, cog: "AutoPingCog", guild: discord.Guild, user: discord.Member):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.user = user
        self.state = "main" # États: 'main', 'add_chan', 'add_role', 'list'
        self.status_message = ""
        
        # Variables de session
        self.selected_channel_id = None
        self.current_page = 0
        self.items_per_page = 5
        
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            # Rejet ferme et persistant, sans utiliser d'éphémère.
            await interaction.response.send_message(f"{E_OFF} {interaction.user.mention}, ce menu est verrouillé par l'auteur de la commande.", ephemeral=False)
            return False
        return True

    def _build(self):
        self.clear_items()
        
        # Résolution esthétique du serveur
        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.cog.bot)
        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text", "")

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        
        if self.status_message:
            container.add_item(ui.TextDisplay(f"> {self.status_message}"))
            self.status_message = ""

        # Aiguillage selon l'état de la vue
        if self.state == "main":
            self._build_main(container)
        elif self.state == "add_chan":
            self._build_add_chan(container)
        elif self.state == "add_role":
            self._build_add_role(container)
        elif self.state == "list":
            self._build_list(container)

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

    def _build_main(self, container: ui.Container):
        container.add_item(ui.TextDisplay(f"# {E_PING} Interface Auto-Ping"))
        container.add_item(ui.TextDisplay(
            "Bienvenue dans le panneau de gestion des pings automatiques.\n\n"
            "Ce module automatise l'envoi d'une mention à un rôle spécifique dès qu'un message "
            "est publié dans un salon cible (idéal pour les annonces ou flux inter-serveurs)."
        ))

        action_row = ui.ActionRow()
        
        btn_add = ui.Button(label="Ajouter / Modifier", style=discord.ButtonStyle.success, emoji=E_ADD)
        btn_add.callback = lambda i: self._change_state(i, "add_chan")
        action_row.add_item(btn_add)

        btn_list = ui.Button(label="Gérer les pings", style=discord.ButtonStyle.primary, emoji=E_LIST)
        btn_list.callback = lambda i: self._change_state(i, "list")
        action_row.add_item(btn_list)

        container.add_item(action_row)

    def _build_add_chan(self, container: ui.Container):
        container.add_item(ui.TextDisplay(f"# {E_ADD} Étape 1 : Le Salon"))
        container.add_item(ui.TextDisplay("Sélectionnez le salon textuel ou d'annonce à placer sous surveillance."))

        select_row = ui.ActionRow()
        chan_select = ui.ChannelSelect(
            channel_types=[discord.ChannelType.text, discord.ChannelType.news],
            placeholder="Sélectionnez le salon cible...",
            min_values=1, max_values=1
        )
        chan_select.callback = self._on_chan_selected
        select_row.add_item(chan_select)
        container.add_item(select_row)

        self._add_return_button(container)

    def _build_add_role(self, container: ui.Container):
        container.add_item(ui.TextDisplay(f"# {E_ADD} Étape 2 : Le Rôle"))
        container.add_item(ui.TextDisplay(
            f"{E_ON} **Salon sélectionné :** <#{self.selected_channel_id}>\n\n"
            "Sélectionnez maintenant le rôle qui sera mentionné à chaque nouveau message."
        ))

        select_row = ui.ActionRow()
        role_select = ui.RoleSelect(
            placeholder="Sélectionnez le rôle à ping...",
            min_values=1, max_values=1
        )
        role_select.callback = self._on_role_selected
        select_row.add_item(role_select)
        container.add_item(select_row)

        self._add_return_button(container)

    def _build_list(self, container: ui.Container):
        config = autoping_db.load(self.guild.id)
        
        container.add_item(ui.TextDisplay(f"# {E_LIST} Liste des configurations"))

        if not config:
            container.add_item(ui.TextDisplay("*Aucun ping automatique n'est configuré sur ce serveur actuellement.*"))
            self._add_return_button(container)
            return

        items = list(config.items())
        max_pages = max(1, math.ceil(len(items) / self.items_per_page))
        
        # Sécurité pour pagination
        if self.current_page >= max_pages:
            self.current_page = max_pages - 1

        start_idx = self.current_page * self.items_per_page
        page_items = items[start_idx : start_idx + self.items_per_page]

        lines = []
        options = []
        for i, (chan_id_str, role_id_str) in enumerate(page_items, start=start_idx + 1):
            lines.append(f"`{i}.` ➡️ **Salon :** <#{chan_id_str}> | **Ping :** <@&{role_id_str}>")
            
            # Préparation des options pour la suppression
            chan = self.guild.get_channel(int(chan_id_str))
            chan_name = chan.name if chan else "Salon introuvable"
            options.append(discord.SelectOption(
                label=f"Supprimer la config n°{i}",
                description=f"Salon: {chan_name}"[:100],
                value=chan_id_str,
                emoji=E_TRASH
            ))

        container.add_item(ui.TextDisplay("\n".join(lines) + f"\n\n*Page {self.current_page + 1}/{max_pages}*"))

        # Sélecteur de suppression
        del_row = ui.ActionRow()
        del_select = ui.Select(placeholder="Choisissez une configuration à supprimer...", options=options)
        del_select.callback = self._on_delete
        del_row.add_item(del_select)
        container.add_item(del_row)

        # Pagination et Retour
        nav_row = ui.ActionRow()
        if max_pages > 1:
            btn_prev = ui.Button(label="Précédent", style=discord.ButtonStyle.secondary, emoji=E_NAV_LEFT, disabled=(self.current_page == 0))
            btn_prev.callback = self._prev_page
            nav_row.add_item(btn_prev)

            btn_next = ui.Button(label="Suivant", style=discord.ButtonStyle.secondary, emoji=E_NAV_RIGHT, disabled=(self.current_page >= max_pages - 1))
            btn_next.callback = self._next_page
            nav_row.add_item(btn_next)

        btn_back = ui.Button(label="Retour", style=discord.ButtonStyle.secondary, emoji=E_BACK)
        btn_back.callback = lambda i: self._change_state(i, "main")
        nav_row.add_item(btn_back)
        
        container.add_item(nav_row)

    def _add_return_button(self, container: ui.Container):
        nav_row = ui.ActionRow()
        btn_back = ui.Button(label="Retour", style=discord.ButtonStyle.secondary, emoji=E_BACK)
        btn_back.callback = lambda i: self._change_state(i, "main")
        nav_row.add_item(btn_back)
        container.add_item(nav_row)

    # --- CALLBACKS ---

    async def _change_state(self, interaction: discord.Interaction, new_state: str):
        self.state = new_state
        self.status_message = ""
        await self._refresh(interaction)

    async def _on_chan_selected(self, interaction: discord.Interaction):
        self.selected_channel_id = str(interaction.data['values'][0])
        self.state = "add_role"
        await self._refresh(interaction)

    async def _on_role_selected(self, interaction: discord.Interaction):
        role_id = str(interaction.data['values'][0])
        
        # Persistance des données
        config = autoping_db.load(self.guild.id)
        config[self.selected_channel_id] = role_id
        autoping_db.save(self.guild.id, config)
        log_sys("CONFIG", f"AutoPing configuré sur le serveur {self.guild.id} (Salon: {self.selected_channel_id}, Role: {role_id})")

        self.state = "main"
        self.status_message = f"{E_ON} Configuration mémorisée avec succès pour le salon <#{self.selected_channel_id}>."
        self.selected_channel_id = None
        await self._refresh(interaction)

    async def _on_delete(self, interaction: discord.Interaction):
        chan_id_str = interaction.data['values'][0]
        
        config = autoping_db.load(self.guild.id)
        if chan_id_str in config:
            del config[chan_id_str]
            autoping_db.save(self.guild.id, config)
            log_sys("DELETE", f"AutoPing supprimé sur le serveur {self.guild.id} pour le salon {chan_id_str}")
            self.status_message = f"{E_ON} La configuration pour le salon <#{chan_id_str}> a été détruite."
        
        await self._refresh(interaction)

    async def _prev_page(self, interaction: discord.Interaction):
        self.current_page -= 1
        await self._refresh(interaction)

    async def _next_page(self, interaction: discord.Interaction):
        self.current_page += 1
        await self._refresh(interaction)


# ==============================================================================
# --- COG PRINCIPAL ---
# ==============================================================================
class AutoPingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log_sys("INIT", "Module AutoPing déployé avec succès.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.id == self.bot.user.id or not message.guild:
            return

        config = autoping_db.load(message.guild.id)
        chan_id_str = str(message.channel.id)

        if chan_id_str in config:
            role_id_str = config[chan_id_str]
            role = message.guild.get_role(int(role_id_str))
            
            if role:
                try:
                    await message.channel.send(f"{E_PING} {role.mention}")
                except discord.Forbidden:
                    log_sys("PERM_ERROR", f"Permissions insuffisantes pour envoyer le ping dans {message.channel.name}", is_error=True)
                except discord.HTTPException as e:
                    log_sys("API_ERROR", f"Erreur HTTP lors du ping dans {message.channel.name}: {e}", is_error=True)

    @perm_command(level=2) # Niveau administratif requis
    @commands.command(name="autoping", description="Ouvre le panneau de configuration des pings automatiques")
    async def autoping_cmd(self, ctx: commands.Context):
        if not ctx.guild:
            await ctx.send(f"{E_OFF} Cette commande exige un contexte serveur.")
            return

        # Validation de l'habilitation stricte via config_perm
        if not await ensure_command_permission(ctx, command_name="autoping"):
            return
            
        log_sys("COMMAND", f"Déploiement de l'interface AutoPing par {ctx.author}")
        view = AutoPingLayoutView(self, ctx.guild, ctx.author)
        await ctx.send(view=view)

async def setup(bot: commands.Bot):
    if bot.get_command("autoping"):
        bot.remove_command("autoping")
    await bot.add_cog(AutoPingCog(bot))