import discord
from discord import app_commands, ui
from discord.ext import commands, tasks
from typing import Optional, Dict, Any, List
import logging
import json
from pathlib import Path
import os
import traceback
from datetime import datetime
import pytz
import math

# ==============================================================================
# ------------------------- CONFIGURATION GLOBALE ------------------------------
# ==============================================================================


EMBED_COLOR = 0x2ecc71
BASE_DIR = Path(__file__).parent
USER_BDAY_DIR = Path(__file__).parents[3] / "data" / "staff" / "configuration" / "data_anniversaire"
# Répertoire pour la configuration des anniversaires par serveur
DB_DIR = BASE_DIR / "DB" / "anniversaire"

MOIS_FR = {
    1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril", 5: "Mai", 6: "Juin",
    7: "Juillet", 8: "Août", 9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"
}

# --- Importation dynamique du Config Manager ---
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# ==============================================================================
# ----------------------------- MODALS UTILISATEURS ----------------------------
# ==============================================================================

class UserBirthdayModal(ui.Modal, title='Configuration de votre Anniversaire'):
    jour = ui.TextInput(label='Jour', placeholder='Ex: 15', max_length=2, required=False)
    mois = ui.TextInput(label='Mois', placeholder='Ex: 8 (pour Août)', max_length=2, required=False)
    annee = ui.TextInput(label='Année (Optionnel)', placeholder='Ex: 1995', max_length=4, required=False)

    def __init__(self, cog, guild_id: int, user_id: int):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.user_id = user_id

        user_data = self.cog.load_user_birthday(self.user_id)
        if user_data:
            if 'day' in user_data: self.jour.default = str(user_data['day'])
            if 'month' in user_data: self.mois.default = str(user_data['month'])
            if 'year' in user_data: self.annee.default = str(user_data['year'])

    async def on_submit(self, interaction: discord.Interaction):
        try:
            j_val, m_val, a_val = self.jour.value.strip(), self.mois.value.strip(), self.annee.value.strip()


            if not j_val and not m_val and not a_val:
                self.cog.delete_user_birthday(self.user_id)
                return await interaction.response.send_message("🗑️ Vos informations d'anniversaire ont été supprimées.", ephemeral=True)

            if j_val or m_val:
                jour_int, mois_int = int(j_val), int(m_val)
                if not (1 <= jour_int <= 31) or not (1 <= mois_int <= 12):
                    raise ValueError("Date invalide.")
            else:
                return await interaction.response.send_message("❌ Renseignez au moins le jour et le mois.", ephemeral=True)

            annee_int = int(a_val) if a_val else None
            if annee_int and not (1900 <= annee_int <= datetime.now().year):
                raise ValueError("Année invalide.")

            data = {'day': jour_int, 'month': mois_int}
            if annee_int:
                data['year'] = annee_int
            self.cog.save_user_birthday(self.user_id, data)
            await interaction.response.send_message("✅ Votre anniversaire a été configuré avec succès !", ephemeral=True)

        except ValueError:
            await interaction.response.send_message("❌ **Erreur :** Valeurs numériques invalides.", ephemeral=True)
        except Exception as e:
            self.cog.logger.error(f"Erreur Modal Anniversaire: {e}")
            await interaction.response.send_message("❌ Une erreur inattendue s'est produite.", ephemeral=True)

class TimeModal(ui.Modal, title='Heure d\'annonce (Format 24h)'):
    heure = ui.TextInput(label='Heure', placeholder='Ex: 15:00', max_length=5, required=True)

    def __init__(self, cog, guild_id: int, admin_view):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.admin_view = admin_view
        config = self.cog.load_config_sync(self.guild_id)
        self.heure.default = config.get('time', '15:00')

    async def on_submit(self, interaction: discord.Interaction):
        val = self.heure.value.strip()
        try:
            datetime.strptime(val, "%H:%M")
            config = self.cog.load_config_sync(self.guild_id)
            config['time'] = val
            self.cog.save_config_sync(self.guild_id, config)
            # Mise à jour directe de l'embed Admin en arrière-plan
            await self.admin_view.update_message(interaction)
        except ValueError:
            await interaction.response.send_message("❌ Format invalide (`HH:MM`).", ephemeral=True)


# ==============================================================================
# ------------------------------ VUES INTERACTIVES -----------------------------
# ==============================================================================

class MonthSelect(ui.Select):
    def __init__(self, current_month: int):
        options = [
            discord.SelectOption(label=nom, value=str(num), default=(num == current_month))
            for num, nom in MOIS_FR.items()
        ]
        super().__init__(placeholder="Choisissez un mois...", min_values=1, max_values=1, options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        view: BirthdayListView = self.view
        view.current_month = int(self.values[0])
        view.current_page = 0 
        await view.update_view(interaction)


class BirthdayListView(ui.View):
    def __init__(self, cog, guild: discord.Guild, user: discord.Member, main_view, main_embed):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.user = user
        self.main_view = main_view
        self.main_embed = main_embed
        
        self.current_month = datetime.now(pytz.timezone("Europe/Paris")).month
        self.current_page = 0
        self.items_per_page = 10

        self.btn_prev = ui.Button(label="◀", style=discord.ButtonStyle.blurple, custom_id="prev_page", row=1)
        self.btn_prev.callback = self.prev_page
        self.btn_next = ui.Button(label="▶", style=discord.ButtonStyle.blurple, custom_id="next_page", row=1)
        self.btn_next.callback = self.next_page
        self.btn_back = ui.Button(label="🔙 Retour au Menu", style=discord.ButtonStyle.secondary, custom_id="back_menu", row=1)
        self.btn_back.callback = self.go_back

        self.update_components()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        return True

    def get_data_for_month(self) -> List[dict]:
        month_data = []
        for file in USER_BDAY_DIR.glob("*.json"):
            if file.name.startswith("guild_"):
                continue
            try:
                user_id = int(file.stem)
                data = self.cog.load_user_birthday(user_id)
                if data.get('month') == self.current_month:
                    month_data.append({'user_id': user_id, 'day': data.get('day'), 'year': data.get('year')})
            except Exception:
                continue
        return sorted(month_data, key=lambda x: x['day'])

    def update_components(self):
        self.clear_items()
        self.add_item(MonthSelect(self.current_month))
        
        data = self.get_data_for_month()
        max_pages = max(1, math.ceil(len(data) / self.items_per_page))

        self.btn_prev.disabled = (self.current_page == 0)
        self.btn_next.disabled = (self.current_page >= max_pages - 1)
        
        self.add_item(self.btn_prev)
        self.add_item(self.btn_next)
        self.add_item(self.btn_back)

    async def update_view(self, interaction: discord.Interaction):
        self.update_components()
        data = self.get_data_for_month()
        mois_nom = MOIS_FR.get(self.current_month, "Inconnu")
        title = f"📅 Anniversaires - {mois_nom}"
        
        if not data:
            description = f"Aucun anniversaire enregistré en **{mois_nom}**."
        else:
            start_idx = self.current_page * self.items_per_page
            page_data = data[start_idx:start_idx + self.items_per_page]
            current_year = datetime.now(pytz.timezone("Europe/Paris")).year
            
            lines = []
            for item in page_data:
                age_str = f" *(aura {current_year - item['year']} ans)*" if item['year'] else ""
                lines.append(f"**{item['day']} {mois_nom}** : <@{item['user_id']}>{age_str}")
                
            max_pages = max(1, math.ceil(len(data) / self.items_per_page))
            description = "\n".join(lines) + f"\n\n*Page {self.current_page + 1}/{max_pages}*"

        embed = self.cog.create_custom_embed(self.guild, self.user, title, description)
        
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    async def prev_page(self, interaction: discord.Interaction):
        self.current_page -= 1
        await self.update_view(interaction)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page += 1
        await self.update_view(interaction)

    async def go_back(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=self.main_embed, view=self.main_view)


class BirthdayAdminView(ui.View):
    def __init__(self, cog, guild: discord.Guild, user: discord.Member, main_view, main_embed):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.user = user
        self.main_view = main_view
        self.main_embed = main_embed
        self.update_components()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Permission refusée.", ephemeral=True)
            return False
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        return True

    def get_admin_embed(self):
        config = self.cog.load_config_sync(self.guild.id)
        chan_mention = f"<#{config['channel_id']}>" if config.get('channel_id') else "`Non configuré`"
        role_mention = f"<@&{config['role_id']}>" if config.get('role_id') else "`Non configuré`"
        heure = f"**{config.get('time', '15:00')}**"

        desc = (
            "**État actuel du module :**\n"
            f"› **Salon d'annonce :** {chan_mention}\n"
            f"› **Rôle mentionné :** {role_mention}\n"
            f"› **Heure automatique :** {heure}\n\n"
            "Utilisez les sélecteurs ci-dessous pour modifier la configuration de votre serveur."
        )
        return self.cog.create_custom_embed(self.guild, self.user, "⚙️ Configuration Anniversaire", desc)

    def update_components(self):
        self.clear_items()
        config = self.cog.load_config_sync(self.guild.id)

        # Sélecteur Salon
        select_channel = ui.ChannelSelect(channel_types=[discord.ChannelType.text], placeholder="Choisir le salon d'annonce...", row=0)
        select_channel.callback = self.on_select_channel
        self.add_item(select_channel)

        # Sélecteur Rôle
        select_role = ui.RoleSelect(placeholder="Choisir le rôle à notifier...", row=1)
        select_role.callback = self.on_select_role
        self.add_item(select_role)

        # Boutons d'action
        btn_time = ui.Button(label="🕒 Modifier l'heure", style=discord.ButtonStyle.primary, row=2)
        btn_time.callback = self.on_time_button
        self.add_item(btn_time)

        # Apparition conditionnelle du bouton Désactiver
        if config.get('channel_id'):
            btn_disable = ui.Button(label="🗑️ Désactiver", style=discord.ButtonStyle.danger, row=2)
            btn_disable.callback = self.on_disable_button
            self.add_item(btn_disable)

        btn_back = ui.Button(label="🔙 Retour", style=discord.ButtonStyle.secondary, row=2)
        btn_back.callback = self.on_back_button
        self.add_item(btn_back)

    async def update_message(self, interaction: discord.Interaction):
        self.update_components()
        embed = self.get_admin_embed()
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    async def on_select_channel(self, interaction: discord.Interaction):
        config = self.cog.load_config_sync(self.guild.id)
        # Accès direct à self.children pour contourner un bug UI courant si besoin, mais `interaction.data` est plus sûr.
        config['channel_id'] = interaction.data['values'][0]
        self.cog.save_config_sync(self.guild.id, config)
        await self.update_message(interaction)

    async def on_select_role(self, interaction: discord.Interaction):
        config = self.cog.load_config_sync(self.guild.id)
        config['role_id'] = interaction.data['values'][0]
        self.cog.save_config_sync(self.guild.id, config)
        await self.update_message(interaction)

    async def on_time_button(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TimeModal(self.cog, self.guild.id, self))

    async def on_disable_button(self, interaction: discord.Interaction):
        config = self.cog.load_config_sync(self.guild.id)
        config['channel_id'] = None
        config['role_id'] = None
        self.cog.save_config_sync(self.guild.id, config)
        await self.update_message(interaction)

    async def on_back_button(self, interaction: discord.Interaction):
        await interaction.response.edit_message(embed=self.main_embed, view=self.main_view)


class BirthdayMainView(ui.View):
    def __init__(self, cog, guild: discord.Guild, user: discord.Member, is_admin: bool):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.user = user
        self.embed_main = None # Renseigné via la commande

        btn_user = ui.Button(label="🎉 Mon anniversaire", style=discord.ButtonStyle.success)
        btn_user.callback = self.open_user_modal
        self.add_item(btn_user)

        btn_list = ui.Button(label="📅 Liste des anniversaires", style=discord.ButtonStyle.primary)
        btn_list.callback = self.open_list_view
        self.add_item(btn_list)

        if is_admin:
            btn_admin = ui.Button(label="⚙️ Configuration Module", style=discord.ButtonStyle.secondary, row=1)
            btn_admin.callback = self.open_admin_menu
            self.add_item(btn_admin)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            # Ne restreint que pour éviter que d'autres perturbent la navigation de l'auteur
            await interaction.response.send_message("❌ Ce menu appartient à l'auteur de la commande. Lancez `/anniversaire` pour le vôtre.", ephemeral=True)
            return False
        return True

    async def open_user_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(UserBirthdayModal(self.cog, self.guild.id, interaction.user.id))

    async def open_list_view(self, interaction: discord.Interaction):
        view = BirthdayListView(self.cog, self.guild, self.user, self, self.embed_main)
        await view.update_view(interaction)

    async def open_admin_menu(self, interaction: discord.Interaction):
        view = BirthdayAdminView(self.cog, self.guild, self.user, self, self.embed_main)
        await view.update_message(interaction)


# ==============================================================================
# ------------------------------ COG PRINCIPAL ---------------------------------
# ==============================================================================

class Anniversaire(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.logger = logging.getLogger('bot')
        self.configs: Dict[int, Dict[str, Any]] = {}
        self.timezone = pytz.timezone("Europe/Paris")
        self.last_checked_time = ""
        USER_BDAY_DIR.mkdir(parents=True, exist_ok=True)

    def load_user_birthday(self, user_id: int) -> dict:
        path = USER_BDAY_DIR / f"{user_id}.json"
        if not path.exists():
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Erreur lecture JSON anniversaire utilisateur {user_id}: {e}")
            return {}

    def save_user_birthday(self, user_id: int, data: dict):
        path = USER_BDAY_DIR / f"{user_id}.json"
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            self.logger.error(f"Erreur sauvegarde JSON anniversaire utilisateur {user_id}: {e}")

    def delete_user_birthday(self, user_id: int):
        path = USER_BDAY_DIR / f"{user_id}.json"
        try:
            if path.exists():
                os.remove(path)
        except Exception as e:
            self.logger.error(f"Erreur suppression JSON anniversaire utilisateur {user_id}: {e}")

    def user_has_guilds(self, user_id: int) -> bool:
        for guild in self.bot.guilds:
            if guild.get_member(user_id):
                return True
        return False

    async def cog_load(self):
        DB_DIR.mkdir(parents=True, exist_ok=True)
        self._load_all_configs()
        self.birthday_loop.start()

    async def cog_unload(self):
        self.birthday_loop.cancel()

    def _load_all_configs(self):
        if not DB_DIR.exists(): return
        for file in os.listdir(DB_DIR):
            if file.endswith('.json'):
                try:
                    self.load_config_sync(int(file.replace('.json', '')))
                except Exception as e: 
                    self.logger.error(f"Erreur chargement {file}: {e}")

    def load_config_sync(self, guild_id: int) -> dict:
        if guild_id in self.configs: return self.configs[guild_id]
        path = DB_DIR / f"{guild_id}.json"
        default = {'channel_id': None, 'role_id': None, 'time': '15:00', 'users': {}}

        if not path.exists():
            self.configs[guild_id] = default
            self.save_config_sync(guild_id, default)
            return default

        try:
            with open(path, 'r', encoding='utf-8') as f:
                self.configs[guild_id] = {**default, **json.load(f)}
                return self.configs[guild_id]
        except Exception as e:
            self.logger.error(f"Erreur lecture JSON {guild_id}: {e}")
            return default

    def save_config_sync(self, guild_id: int, config: dict):
        self.configs[guild_id] = config
        path = DB_DIR / f"{guild_id}.json"
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            self.logger.error(f"Erreur sauvegarde JSON {guild_id}: {e}")

    def create_custom_embed(self, guild, user, title, description):
        if config_manager:
            return config_manager.get_formatted_embed(guild=guild, user=user, bot=self.bot, title=title, description=description)
        embed = discord.Embed(title=title, description=description, color=EMBED_COLOR)
        if self.bot.user.avatar: embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        return embed

    @commands.hybrid_command(name="anniversaire", description="Gérez et configurez les anniversaires du serveur.")
    async def cmd_anniversaire(self, ctx: commands.Context):
        try:
            is_admin = ctx.author.guild_permissions.administrator
            view = BirthdayMainView(self, ctx.guild, ctx.author, is_admin)
            
            desc = (
                "🎂 **Centre d'Anniversaires !**\n\n"
                "Bienvenue dans le menu interactif. Utilisez les boutons ci-dessous pour renseigner "
                "votre date de naissance, consulter le calendrier du serveur, ou paramétrer le module."
            )
            embed = self.create_custom_embed(ctx.guild, ctx.author, "🎉 Menu Anniversaire", desc)
            view.embed_main = embed # Sauvegarde pour le système de retour en arrière
            
            if ctx.interaction:
                await ctx.interaction.response.send_message(embed=embed, view=view)
            else:
                await ctx.send(embed=embed, view=view, reference=ctx.message)
        except Exception as e:
            self.logger.error(f"Erreur cmd_anniversaire : {e}\n{traceback.format_exc()}")

    @tasks.loop(minutes=1)
    async def birthday_loop(self):
        now = datetime.now(self.timezone)
        current_time_str = now.strftime("%H:%M")
        if current_time_str == self.last_checked_time:
            return
        self.last_checked_time = current_time_str

        # Pour chaque serveur, on regarde la config
        for guild in self.bot.guilds:
            config = self.load_config_sync(guild.id)
            if config.get('time') != current_time_str or not config.get('channel_id'):
                continue
            channel = guild.get_channel(int(config['channel_id'])) if guild else None
            if not channel:
                continue

            # Cherche tous les utilisateurs ayant leur anniversaire aujourd'hui
            bday_members = []
            for file in USER_BDAY_DIR.glob("*.json"):
                if file.name.startswith("guild_"):
                    continue
                try:
                    user_id = int(file.stem)
                    data = self.load_user_birthday(user_id)
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
                if role:
                    mentions.append(role.mention)
            mentions.extend([b['member'].mention for b in bday_members])

            desc_lines = [f"🎁 {b['member'].mention}" + (f" (**{b['age']} ans**)" if b['age'] else "") for b in bday_members]
            embed = self.create_custom_embed(
                guild, self.bot.user, "🎂 C'est l'heure des Anniversaires !",
                "Aujourd'hui, nous fêtons l'anniversaire de :\n\n" + "\n".join(desc_lines)
            )

            msg = await channel.send(content=f"🎉 {' '.join(mentions)}", embed=embed)
            for emoji in ["🎉", "🎂", "🥳", "🎁"]:
                try:
                    await msg.add_reaction(emoji)
                except discord.HTTPException:
                    pass

        # Suppression des fichiers utilisateurs sans serveur en commun
        for file in USER_BDAY_DIR.glob("*.json"):
            if file.name.startswith("guild_"):
                continue
            try:
                user_id = int(file.stem)
                if not self.user_has_guilds(user_id):
                    self.delete_user_birthday(user_id)
            except Exception:
                continue

    @birthday_loop.before_loop
    async def before_birthday_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(Anniversaire(bot))