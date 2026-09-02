import discord
from discord import ui
from discord.ext import commands, tasks
import json
import traceback
from datetime import datetime
import pytz
import math
from pathlib import Path

# ==============================================================================
# --- IMPORTS MÉTIER VAX ---
# Utilisation stricte de nos gestionnaires internes pour garantir l'intégrité.
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
E_GIFT = getattr(E, 'CADEAU', "🎁") if HAS_VAX_CORE else "🎁"
E_CALENDAR = getattr(E, 'HISTOIRE', "📅") if HAS_VAX_CORE else "📅"
E_GEAR = getattr(E, 'MODIFIER', "⚙️") if HAS_VAX_CORE else "⚙️"
E_USER = getattr(E, 'PROFIL', "👤") if HAS_VAX_CORE else "👤"
E_BACK = getattr(E, 'RETOUR', "↩️") if HAS_VAX_CORE else "↩️"
E_TRASH = getattr(E, 'SUPPRIMER', "🗑️") if HAS_VAX_CORE else "🗑️"
E_NAV_LEFT = getattr(E, 'FLECHE_GAUCHE', "◀️") if HAS_VAX_CORE else "◀️"
E_NAV_RIGHT = getattr(E, 'FLECHE_DROITE', "▶️") if HAS_VAX_CORE else "▶️"
E_TIME = getattr(E, 'HORLOGE', "🕒") if HAS_VAX_CORE else "🕒"

# Les nouveaux emojis personnalisables pour le gâteau et la fête
E_CAKE = getattr(E, 'CADEAU', "🎂") if HAS_VAX_CORE else "🎂"
E_PARTY = getattr(E, 'PROFIL', "🎉") if HAS_VAX_CORE else "🎉"

MOIS_FR = {
    1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril", 5: "Mai", 6: "Juin",
    7: "Juillet", 8: "Août", 9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"
}

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
    prefix = "[ERREUR Anniversaire]" if is_error else "[INFO Anniversaire]"
    print(f"{color}{prefix} [{action}] {message}{COLOR_RESET}")

# ==============================================================================
# --- GESTIONNAIRES DE DONNÉES (DataManager) ---
# ==============================================================================
class GuildBirthdayManager:
    def __init__(self):
        self.data = DataManager("staff/configuration/data_anniversaire/guilds")

    def load(self, guild_id: int) -> dict:
        raw = self.data.load(guild_id) or {}
        return {
            'channel_id': raw.get('channel_id', None),
            'role_id': raw.get('role_id', None),
            'time': raw.get('time', '15:00')
        }

    def save(self, guild_id: int, config: dict):
        self.data.save(guild_id, config)

class UserBirthdayManager:
    def __init__(self):
        self.data = DataManager("staff/configuration/data_anniversaire")
        # Chemin physique nécessaire pour le parcours global
        self.base_path = Path.cwd() / "data" / "staff" / "configuration" / "data_anniversaire"
        self.base_path.mkdir(parents=True, exist_ok=True)

    def load(self, user_id: int) -> dict:
        return self.data.load(user_id) or {}

    def save(self, user_id: int, config: dict):
        self.data.save(user_id, config)

    def delete(self, user_id: int):
        self.data.delete(user_id)

    def iter_all_users(self):
        for file in self.base_path.glob("*.json"):
            if not file.name.startswith("guild_"):
                try:
                    yield int(file.stem)
                except ValueError:
                    continue

guild_bday_db = GuildBirthdayManager()
user_bday_db = UserBirthdayManager()

# ==============================================================================
# --- INTERFACES UTILISATEUR (Layout V2 & Modals) ---
# ==============================================================================
class UserBirthdayModal(ui.Modal, title='Configuration Anniversaire'):
    jour = ui.TextInput(label='Jour', placeholder='Ex: 15', max_length=2, required=False)
    mois = ui.TextInput(label='Mois', placeholder='Ex: 8 (pour Août)', max_length=2, required=False)
    annee = ui.TextInput(label='Année (Optionnel)', placeholder='Ex: 1995', max_length=4, required=False)

    def __init__(self, view: "BirthdayLayoutView"):
        super().__init__()
        self.view = view
        user_data = user_bday_db.load(self.view.user.id)
        
        if user_data:
            if 'day' in user_data: self.jour.default = str(user_data['day'])
            if 'month' in user_data: self.mois.default = str(user_data['month'])
            if 'year' in user_data: self.annee.default = str(user_data['year'])

    async def on_submit(self, interaction: discord.Interaction):
        try:
            j_val, m_val, a_val = self.jour.value.strip(), self.mois.value.strip(), self.annee.value.strip()

            if not j_val and not m_val and not a_val:
                user_bday_db.delete(self.view.user.id)
                self.view.status_message = f"{E_TRASH} Vos informations d'anniversaire ont été supprimées."
                return await self.view._refresh(interaction)

            if j_val or m_val:
                jour_int, mois_int = int(j_val), int(m_val)
                if not (1 <= jour_int <= 31) or not (1 <= mois_int <= 12):
                    raise ValueError("Date invalide.")
            else:
                self.view.status_message = f"{E_OFF} Renseignez au moins le jour et le mois."
                return await self.view._refresh(interaction)

            annee_int = int(a_val) if a_val else None
            if annee_int and not (1900 <= annee_int <= datetime.now().year):
                raise ValueError("Année invalide.")

            data = {'day': jour_int, 'month': mois_int}
            if annee_int:
                data['year'] = annee_int
                
            user_bday_db.save(self.view.user.id, data)
            self.view.status_message = f"{E_ON} Votre anniversaire a été configuré avec succès !"
            await self.view._refresh(interaction)

        except ValueError:
            self.view.status_message = f"{E_OFF} Erreur de saisie : les valeurs doivent être numériques et valides."
            await self.view._refresh(interaction)

class TimeModal(ui.Modal, title="Heure d'annonce (Format 24h)"):
    heure = ui.TextInput(label='Heure', placeholder='Ex: 15:00', max_length=5, required=True)

    def __init__(self, view: "BirthdayLayoutView"):
        super().__init__()
        self.view = view
        config = guild_bday_db.load(self.view.guild.id)
        self.heure.default = config.get('time', '15:00')

    async def on_submit(self, interaction: discord.Interaction):
        val = self.heure.value.strip()
        try:
            datetime.strptime(val, "%H:%M")
            config = guild_bday_db.load(self.view.guild.id)
            config['time'] = val
            guild_bday_db.save(self.view.guild.id, config)
            
            self.view.status_message = f"{E_ON} L'heure d'annonce automatique a été fixée à **{val}**."
            await self.view._refresh(interaction)
        except ValueError:
            self.view.status_message = f"{E_OFF} Le format de l'heure est invalide (requis: `HH:MM`)."
            await self.view._refresh(interaction)

class BirthdayLayoutView(ui.LayoutView):
    """Vue V2 centralisée gérant la navigation persistante entre l'accueil, la liste et l'administration."""
    def __init__(self, bot: commands.Bot, guild: discord.Guild, user: discord.Member, is_admin: bool):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild = guild
        self.user = user
        self.is_admin = is_admin
        self.state = "main" # États: 'main', 'list', 'admin'
        self.status_message = ""
        
        # Variables de pagination pour la liste
        self.current_month = datetime.now(pytz.timezone("Europe/Paris")).month
        self.current_page = 0
        self.items_per_page = 10
        
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            # Rejet ferme non-éphémère via l'intercepteur de la View
            await interaction.response.send_message(f"{E_OFF} Action refusée : lancez la commande pour ouvrir votre menu.", ephemeral=True)
            return False
        return True

    def _build(self):
        self.clear_items()
        
        # Résolution esthétique du serveur
        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.bot)
        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text", "")

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        
        if self.status_message:
            container.add_item(ui.TextDisplay(f"> {self.status_message}"))
            self.status_message = ""

        if self.state == "list":
            self._build_list(container)
        elif self.state == "admin" and self.is_admin:
            self._build_admin(container)
        else:
            self._build_main(container)

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
        container.add_item(ui.TextDisplay(f"# {E_CAKE} Centre d'Anniversaires !"))
        container.add_item(ui.TextDisplay(
            "Bienvenue dans le menu interactif. Utilisez les boutons ci-dessous pour renseigner "
            "votre date de naissance, consulter le calendrier du serveur, ou paramétrer le module."
        ))

        action_row = ui.ActionRow()
        
        btn_user = ui.Button(label="Mon anniversaire", style=discord.ButtonStyle.success, emoji=E_PARTY)
        btn_user.callback = self.open_user_modal
        action_row.add_item(btn_user)

        btn_list = ui.Button(label="Calendrier", style=discord.ButtonStyle.primary, emoji=E_CALENDAR)
        btn_list.callback = lambda i: self._change_state(i, "list")
        action_row.add_item(btn_list)

        if self.is_admin:
            btn_admin = ui.Button(label="Configuration", style=discord.ButtonStyle.secondary, emoji=E_GEAR)
            btn_admin.callback = lambda i: self._change_state(i, "admin")
            action_row.add_item(btn_admin)

        container.add_item(action_row)

    def _build_list(self, container: ui.Container):
        data = self._get_data_for_month()
        mois_nom = MOIS_FR.get(self.current_month, "Inconnu")
        max_pages = max(1, math.ceil(len(data) / self.items_per_page))
        
        container.add_item(ui.TextDisplay(f"# {E_CALENDAR} Anniversaires de {mois_nom}"))

        if not data:
            container.add_item(ui.TextDisplay(f"Aucun anniversaire enregistré en **{mois_nom}**."))
        else:
            start_idx = self.current_page * self.items_per_page
            page_data = data[start_idx:start_idx + self.items_per_page]
            current_year = datetime.now(pytz.timezone("Europe/Paris")).year
            
            lines = []
            for item in page_data:
                age_str = f" *(aura {current_year - item['year']} ans)*" if item['year'] else ""
                lines.append(f"- **{item['day']} {mois_nom}** : <@{item['user_id']}>{age_str}")
            
            container.add_item(ui.TextDisplay("\n".join(lines) + f"\n\n*Page {self.current_page + 1}/{max_pages}*"))

        # Contrôles de Mois et Pagination
        select_row = ui.ActionRow()
        month_select = ui.Select(
            placeholder="Changer de mois...",
            min_values=1, max_values=1,
            options=[discord.SelectOption(label=nom, value=str(num), default=(num == self.current_month)) for num, nom in MOIS_FR.items()]
        )
        month_select.callback = self._on_month_select
        select_row.add_item(month_select)
        container.add_item(select_row)

        nav_row = ui.ActionRow()
        btn_prev = ui.Button(label="Précédent", style=discord.ButtonStyle.secondary, emoji=E_NAV_LEFT, disabled=(self.current_page == 0))
        btn_prev.callback = self._prev_page
        nav_row.add_item(btn_prev)

        btn_next = ui.Button(label="Suivant", style=discord.ButtonStyle.secondary, emoji=E_NAV_RIGHT, disabled=(self.current_page >= max_pages - 1))
        btn_next.callback = self._next_page
        nav_row.add_item(btn_next)

        btn_back = ui.Button(label="Retour Menu", style=discord.ButtonStyle.secondary, emoji=E_BACK)
        btn_back.callback = lambda i: self._change_state(i, "main")
        nav_row.add_item(btn_back)
        
        container.add_item(nav_row)

    def _build_admin(self, container: ui.Container):
        config = guild_bday_db.load(self.guild.id)
        chan_mention = f"<#{config['channel_id']}>" if config.get('channel_id') else "`Non configuré`"
        role_mention = f"<@&{config['role_id']}>" if config.get('role_id') else "`Non configuré`"
        heure = f"**{config.get('time', '15:00')}**"

        container.add_item(ui.TextDisplay(f"# {E_GEAR} Administration du module"))
        container.add_item(ui.TextDisplay(
            f"- **Salon d'annonce :** {chan_mention}\n"
            f"- **Rôle notifié :** {role_mention}\n"
            f"- **Heure de tir automatique :** {heure}\n\n"
            "Utilisez les sélecteurs pour configurer ou désactiver les annonces."
        ))

        chan_row = ui.ActionRow()
        select_channel = ui.ChannelSelect(channel_types=[discord.ChannelType.text], placeholder="Salon d'annonce...")
        select_channel.callback = self.on_select_channel
        chan_row.add_item(select_channel)
        container.add_item(chan_row)

        role_row = ui.ActionRow()
        select_role = ui.RoleSelect(placeholder="Rôle à mentionner...")
        select_role.callback = self.on_select_role
        role_row.add_item(select_role)
        container.add_item(role_row)

        action_row = ui.ActionRow()
        btn_time = ui.Button(label="Heure", style=discord.ButtonStyle.primary, emoji=E_TIME)
        btn_time.callback = self.open_time_modal
        action_row.add_item(btn_time)

        if config.get('channel_id'):
            btn_disable = ui.Button(label="Désactiver", style=discord.ButtonStyle.danger, emoji=E_TRASH)
            btn_disable.callback = self.on_disable_module
            action_row.add_item(btn_disable)

        btn_back = ui.Button(label="Retour Menu", style=discord.ButtonStyle.secondary, emoji=E_BACK)
        btn_back.callback = lambda i: self._change_state(i, "main")
        action_row.add_item(btn_back)
        
        container.add_item(action_row)

    # --- CALLBACKS ET UTILITAIRES ---

    def _get_data_for_month(self):
        month_data = []
        for user_id in user_bday_db.iter_all_users():
            data = user_bday_db.load(user_id)
            if data.get('month') == self.current_month:
                month_data.append({'user_id': user_id, 'day': data.get('day'), 'year': data.get('year')})
        return sorted(month_data, key=lambda x: x['day'])

    async def _change_state(self, interaction: discord.Interaction, new_state: str):
        self.state = new_state
        self.status_message = ""
        await self._refresh(interaction)

    async def _on_month_select(self, interaction: discord.Interaction):
        self.current_month = int(interaction.data['values'][0])
        self.current_page = 0
        await self._refresh(interaction)

    async def _prev_page(self, interaction: discord.Interaction):
        self.current_page -= 1
        await self._refresh(interaction)

    async def _next_page(self, interaction: discord.Interaction):
        self.current_page += 1
        await self._refresh(interaction)

    async def open_user_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(UserBirthdayModal(self))

    async def on_select_channel(self, interaction: discord.Interaction):
        config = guild_bday_db.load(self.guild.id)
        config['channel_id'] = interaction.data['values'][0]
        guild_bday_db.save(self.guild.id, config)
        self.status_message = f"{E_ON} Salon d'annonce enregistré."
        await self._refresh(interaction)

    async def on_select_role(self, interaction: discord.Interaction):
        config = guild_bday_db.load(self.guild.id)
        config['role_id'] = interaction.data['values'][0]
        guild_bday_db.save(self.guild.id, config)
        self.status_message = f"{E_ON} Rôle à mentionner enregistré."
        await self._refresh(interaction)

    async def open_time_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TimeModal(self))

    async def on_disable_module(self, interaction: discord.Interaction):
        config = guild_bday_db.load(self.guild.id)
        config['channel_id'] = None
        config['role_id'] = None
        guild_bday_db.save(self.guild.id, config)
        self.status_message = f"{E_TRASH} Le système d'annonce automatique a été désactivé."
        await self._refresh(interaction)


# ==============================================================================
# --- COG PRINCIPAL ---
# ==============================================================================
class AnniversaireCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.timezone = pytz.timezone("Europe/Paris")
        self.last_checked_time = ""
        log_sys("INIT", "Module Anniversaires prêt et fonctionnel.")

    async def cog_load(self):
        self.birthday_loop.start()

    async def cog_unload(self):
        self.birthday_loop.cancel()

    def user_has_guilds(self, user_id: int) -> bool:
        """Vérifie si l'utilisateur partage au moins un serveur avec le bot pour purger les orphelins."""
        for guild in self.bot.guilds:
            if guild.get_member(user_id):
                return True
        return False

    @commands.command(name="anniversaire", description="Gérez et configurez les anniversaires du serveur.")
    async def cmd_anniversaire(self, ctx: commands.Context):
        if not ctx.guild:
            await ctx.send(f"{E_OFF} Cette commande exige un contexte serveur.")
            return
            
        try:
            is_admin = ctx.author.guild_permissions.administrator
            view = BirthdayLayoutView(self.bot, ctx.guild, ctx.author, is_admin)
            log_sys("CMD", f"Menu d'anniversaire déployé pour {ctx.author}")
            await ctx.send(view=view)
        except Exception as e:
            log_sys("CMD_ERR", f"Crash lors du lancement : {e}\n{traceback.format_exc()}", is_error=True)

    @tasks.loop(minutes=1)
    async def birthday_loop(self):
        now = datetime.now(self.timezone)
        current_time_str = now.strftime("%H:%M")
        
        if current_time_str == self.last_checked_time:
            return
        self.last_checked_time = current_time_str

        # Boucle d'envoi sur tous les serveurs
        for guild in self.bot.guilds:
            config = guild_bday_db.load(guild.id)
            if config.get('time') != current_time_str or not config.get('channel_id'):
                continue
                
            channel = guild.get_channel(int(config['channel_id']))
            if not channel:
                continue

            # Compilation des utilisateurs à fêter
            bday_members = []
            for user_id in user_bday_db.iter_all_users():
                try:
                    data = user_bday_db.load(user_id)
                    if data.get('day') == now.day and data.get('month') == now.month:
                        member = guild.get_member(user_id)
                        if member:
                            age = now.year - data['year'] if 'year' in data else None
                            bday_members.append({'member': member, 'age': age})
                except Exception:
                    continue

            if not bday_members:
                continue

            mentions = []
            if config.get('role_id'):
                role = guild.get_role(int(config['role_id']))
                if role: mentions.append(role.mention)
            mentions.extend([b['member'].mention for b in bday_members])

            desc_lines = [f"{E_GIFT} {b['member'].mention}" + (f" (**{b['age']} ans**)" if b['age'] else "") for b in bday_members]

            # Rendu V2 sans le champ `content` pour respecter l'API Discord sur les composants
            view = ui.LayoutView(timeout=1) # Vue technique pour transporter le Container
            theme = config_manager.get_layout_v2_theme(guild.id, guild, self.bot.user, self.bot)
            accent_color = int(theme.get("color", discord.Color.blurple().value))
            
            container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
            
            # Intégration astucieuse des mentions brutes directement dans le bloc TextDisplay
            mentions_str = " ".join(mentions)
            container.add_item(ui.TextDisplay(
                f"{mentions_str}\n# {E_CAKE} C'est l'heure des Anniversaires !\n\n"
                "Aujourd'hui, nous fêtons l'anniversaire de :\n\n" + "\n".join(desc_lines)
            ))
            view.add_item(container)

            try:
                msg = await channel.send(view=view)
                
                # Réactions supplémentaires optionnelles
                react_emoji_joie = getattr(E, 'JOIE', "🥳")
                for emoji in [E_PARTY, E_CAKE, react_emoji_joie, E_GIFT]:
                    try:
                        await msg.add_reaction(emoji)
                    except discord.HTTPException:
                        pass
            except discord.HTTPException as e:
                log_sys("LOOP_ERR", f"Impossible de poster sur le serveur {guild.name}: {e}", is_error=True)

        # Purge asynchrone des utilisateurs fantômes
        for user_id in list(user_bday_db.iter_all_users()):
            try:
                if not self.user_has_guilds(user_id):
                    user_bday_db.delete(user_id)
                    log_sys("CLEANUP", f"Données purgées pour l'utilisateur orphelin {user_id}")
            except Exception:
                continue

    @birthday_loop.before_loop
    async def before_birthday_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    if bot.get_command("anniversaire"):
        bot.remove_command("anniversaire")
    await bot.add_cog(AnniversaireCog(bot))