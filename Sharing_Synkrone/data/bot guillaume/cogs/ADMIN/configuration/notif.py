import discord
from discord.ext import commands, tasks
from discord import ui
import json
import os
import aiohttp
from pathlib import Path

# Chargement des variables d'environnement
from dotenv import load_dotenv
load_dotenv()

try:
    from cogs.config_manager.utils import config_manager
except ImportError:
    config_manager = None

DATA_FILE = Path("data/notifications_config.json")

# Récupération des clés API depuis le .env
TWITCH_CLIENT_ID = os.getenv("TWITCH_CLIENT_ID")
TWITCH_CLIENT_SECRET = os.getenv("TWITCH_CLIENT_SECRET")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

PLATFORM_ALIASES = {
    "twitch": "twitch",
    "youtube": "youtube video",
    "youtube video": "youtube video",
    "youtube live": "youtube live",
}


def normalize_platform(raw: str) -> str | None:
    return PLATFORM_ALIASES.get((raw or "").strip().lower())


def get_platform_label(platform: str) -> str:
    p = (platform or "").strip().lower()
    if p == "twitch":
        return "Twitch"
    if p == "youtube live":
        return "YouTube Live"
    return "YouTube Video"


def get_event_kind(conf: dict) -> str:
    p = str(conf.get("platform", "twitch")).strip().lower()
    if p == "youtube live":
        return "live"
    if p in {"youtube", "youtube video"}:
        return "video"
    return "live"


def get_notification_button_label(conf: dict, event_kind: str) -> str:
    platform = str(conf.get("platform", "twitch")).strip().lower()
    if platform == "twitch":
        return "Rejoindre le stream"
    if event_kind == "live":
        return "Rejoindre le live"
    return "Regarder la video"


def build_notification_link_view(conf: dict, link: str, event_kind: str) -> ui.View | None:
    effective_link = link or get_channel_fallback_link(conf)
    if not effective_link:
        return None

    view = ui.View(timeout=None)
    view.add_item(
        ui.Button(
            label=get_notification_button_label(conf, event_kind),
            style=discord.ButtonStyle.link,
            url=effective_link,
        )
    )
    return view

def load_data():
    if not DATA_FILE.parent.exists():
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def get_guild_notifs(guild_id: int):
    data = load_data()
    guild_id_str = str(guild_id)
    if guild_id_str not in data:
        data[guild_id_str] = {"notifications": {}}
        save_data(data)
    return data[guild_id_str]["notifications"]

def get_message_preview_text(message_template: str) -> str:
    return message_template if message_template else ""


def get_channel_fallback_link(conf: dict) -> str:
    platform = str(conf.get("platform", "twitch")).strip().lower()
    pseudo = str(conf.get("pseudo", "")).strip()
    if not pseudo:
        return ""
    if platform == "twitch":
        return f"https://www.twitch.tv/{pseudo}"
    return f"https://www.youtube.com/@{pseudo}"


async def fetch_twitch_thumbnail(login: str) -> str | None:
    if not TWITCH_CLIENT_ID or not TWITCH_CLIENT_SECRET or not login:
        return None

    try:
        async with aiohttp.ClientSession() as session:
            auth_url = "https://id.twitch.tv/oauth2/token"
            auth_payload = {
                "client_id": TWITCH_CLIENT_ID,
                "client_secret": TWITCH_CLIENT_SECRET,
                "grant_type": "client_credentials",
            }
            async with session.post(auth_url, data=auth_payload, timeout=aiohttp.ClientTimeout(total=10)) as auth_response:
                if auth_response.status != 200:
                    return None
                auth_data = await auth_response.json()
                access_token = auth_data.get("access_token")
                if not access_token:
                    return None

            headers = {
                "Client-Id": TWITCH_CLIENT_ID,
                "Authorization": f"Bearer {access_token}",
            }
            users_url = f"https://api.twitch.tv/helix/users?login={login}"
            async with session.get(users_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as users_response:
                if users_response.status != 200:
                    return None
                users_data = await users_response.json()
                users = users_data.get("data", [])
                if not users:
                    return None
                return users[0].get("profile_image_url")
    except Exception:
        return None


async def fetch_youtube_thumbnail(channel_name: str) -> str | None:
    if not YOUTUBE_API_KEY or not channel_name:
        return None

    try:
        async with aiohttp.ClientSession() as session:
            search_url = "https://www.googleapis.com/youtube/v3/search"
            params = {
                "part": "snippet",
                "type": "channel",
                "q": channel_name,
                "maxResults": 1,
                "key": YOUTUBE_API_KEY,
            }
            async with session.get(search_url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status != 200:
                    return None
                data = await response.json()
                items = data.get("items", [])
                if not items:
                    return None
                thumbnails = items[0].get("snippet", {}).get("thumbnails", {})
                for size in ("high", "medium", "default"):
                    if size in thumbnails and thumbnails[size].get("url"):
                        return thumbnails[size]["url"]
    except Exception:
        return None

    return None


async def resolve_thumbnail_url(bot: commands.Bot, guild: discord.Guild, conf: dict) -> str | None:
    user_id = conf.get("user_id")
    discord_avatar = None
    if user_id:
        member = guild.get_member(int(user_id)) if str(user_id).isdigit() else None
        if member:
            discord_avatar = member.display_avatar.url

    platform = str(conf.get("platform", "twitch")).strip().lower()
    pseudo = conf.get("pseudo", "").strip()

    if platform == "twitch":
        thumb = await fetch_twitch_thumbnail(pseudo)
    else:
        thumb = await fetch_youtube_thumbnail(pseudo)

    return thumb or discord_avatar


def build_notification_message(conf: dict, link: str, event_kind: str = "live") -> str:
    role_mention = ""
    role_val = str(conf.get("role_id", "")).lower()
    if role_val in ["everyone", "@everyone"]:
        role_mention = "@everyone"
    elif role_val in ["here", "@here"]:
        role_mention = "@here"
    elif role_val.isdigit():
        role_mention = f"<@&{role_val}>"

    pseudo = str(conf.get("pseudo", "Créateur")).strip() or "Créateur"

    if event_kind == "video":
        msg_content = f"{role_mention} 🎬 Nouvelle video de **{pseudo}**."
    else:
        msg_content = f"{role_mention} 🔴 **{pseudo}** est en direct."

    return " ".join(msg_content.split())


def build_notification_embed(bot: commands.Bot, guild: discord.Guild, user: discord.Member | discord.User, conf: dict, link: str, thumbnail_url: str | None = None, event_kind: str = "live") -> discord.Embed:
    platform = conf.get("platform", "twitch")
    color = 0x9146FF if platform == "twitch" else 0xFF0000
    pseudo = conf.get("pseudo", "Créateur")

    if event_kind == "video":
        author_name = f"🎬 Nouvelle vidéo de {pseudo}"
    else:
        author_name = f"🔴 {pseudo} est en direct"

    author_icon = thumbnail_url or ""
    embed = discord.Embed(color=color)
    if author_icon:
        embed.set_author(name=author_name, icon_url=author_icon)
    else:
        embed.set_author(name=author_name)

    if thumbnail_url:
        embed.set_image(url=thumbnail_url)

    if config_manager:
        formatted = config_manager.get_formatted_embed(
            guild=guild,
            user=user,
            bot=bot,
            title=embed.title,
            description=embed.description,
            target_id=guild.id,
        )
        formatted.color = embed.color
        if author_icon:
            formatted.set_author(name=author_name, icon_url=author_icon)
        else:
            formatted.set_author(name=author_name)
        if thumbnail_url:
            formatted.set_image(url=thumbnail_url)
        return formatted

    return embed

# ==============================================================================
# --------------------------- MODALS -------------------------------------------
# ==============================================================================
class ProfileModal(ui.Modal):
    def __init__(self, parent_view, notif_id: str = None, config: dict = None):
        is_edit = notif_id is not None
        title = "✏️ Profil Notification" if is_edit else "➕ Nouvelle notification"
        super().__init__(title=title)
        
        self.parent_view = parent_view
        self.is_edit = is_edit
        self.old_notif_id = notif_id
        self.config = config or {}

        self.pseudo_input = ui.TextInput(
            label="Pseudo Twitch ou YouTube",
            placeholder="Ex: Squeezie",
            default=self.config.get("pseudo", ""),
            max_length=100,
            required=True
        )
        self.platform_input = ui.TextInput(
            label="Plateforme",
            placeholder="twitch, youtube video, youtube live",
            default=self.config.get("platform", "twitch"),
            max_length=20,
            required=True
        )
        self.user_id_input = ui.TextInput(
            label="ID Utilisateur Discord (Facultatif)",
            placeholder="Ex: 123456789101112 (pour le @tag)",
            default=self.config.get("user_id", ""),
            max_length=25,
            required=False
        )
        
        self.add_item(self.pseudo_input)
        self.add_item(self.platform_input)
        self.add_item(self.user_id_input)

    async def on_submit(self, interaction: discord.Interaction):
        platform = normalize_platform(self.platform_input.value)
        if platform is None:
            return await interaction.response.send_message("❌ Plateforme invalide. Utilisez: twitch, youtube video, youtube live.", ephemeral=True)

        pseudo = self.pseudo_input.value.strip()
        new_notif_id = f"{platform.replace(' ', '_')}_{pseudo.lower()}"

        data = load_data()
        guild_id_str = str(interaction.guild.id)
        if guild_id_str not in data:
            data[guild_id_str] = {"notifications": {}}

        notifs = data[guild_id_str]["notifications"]

        channel_id = self.config.get("channel_id", "")
        role_id = self.config.get("role_id", "")
        if self.is_edit and self.old_notif_id != new_notif_id:
            if self.old_notif_id in notifs:
                del notifs[self.old_notif_id]

        notifs[new_notif_id] = {
            "pseudo": pseudo,
            "platform": platform,
            "user_id": self.user_id_input.value.strip(),
            "channel_id": channel_id,
            "role_id": role_id
        }
        
        save_data(data)

        self.parent_view.notifications = notifs
        self.parent_view.selected_notif = new_notif_id
        await self.parent_view.open_profile(interaction, new_notif_id)


class NotificationSettingsModal(ui.Modal):
    def __init__(self, parent_view, notif_id: str, config: dict):
        super().__init__(title="⚙️ Configuration de la notification")
        self.parent_view = parent_view
        self.notif_id = notif_id
        self.config = config

        self.channel_input = ui.TextInput(
            label="Salon d'envoi",
            placeholder="ID du salon",
            default=str(config.get("channel_id", "")),
            max_length=25,
            required=False,
        )
        self.user_input = ui.TextInput(
            label="ID utilisateur",
            placeholder="Facultatif",
            default=str(config.get("user_id", "")),
            max_length=25,
            required=False,
        )
        self.role_input = ui.TextInput(
            label="Notification ou rôle",
            placeholder="everyone, here ou ID de rôle",
            default=str(config.get("role_id", "")),
            max_length=50,
            required=False,
        )
        self.message_input = ui.TextInput(
            label="Message personnalisé",
            style=discord.TextStyle.paragraph,
            placeholder="Laissez vide pour aucun message",
            default=str(config.get("message", "")),
            max_length=2000,
            required=False,
        )
        self.author_input = ui.TextInput(
            label="Auteur personnalisé",
            placeholder="Ex: 🟢 En direct",
            default=str(config.get("author_name", "")),
            max_length=256,
            required=False,
        )
        self.description_input = ui.TextInput(
            label="Description personnalisée",
            style=discord.TextStyle.paragraph,
            placeholder="Description de l'embed",
            default=str(config.get("description", "")),
            max_length=4000,
            required=False,
        )

        for item in [
            self.channel_input,
            self.user_input,
            self.role_input,
            self.message_input,
            self.author_input,
            self.description_input,
        ]:
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        data = load_data()
        guild_id_str = str(interaction.guild.id)
        notifs = data.setdefault(guild_id_str, {"notifications": {}})["notifications"]

        if self.notif_id not in notifs:
            return await interaction.response.send_message("❌ Notification introuvable.", ephemeral=True)

        notifs[self.notif_id]["channel_id"] = self.channel_input.value.strip()
        notifs[self.notif_id]["user_id"] = self.user_input.value.strip()
        notifs[self.notif_id]["role_id"] = self.role_input.value.strip()
        notifs[self.notif_id]["message"] = self.message_input.value
        notifs[self.notif_id]["author_name"] = self.author_input.value.strip()
        notifs[self.notif_id]["author_icon"] = self.config.get("author_icon", "")
        notifs[self.notif_id]["description"] = self.description_input.value
        save_data(data)

        self.parent_view.notifications = notifs
        await self.parent_view.open_profile(interaction, self.notif_id)

class SendModal(ui.Modal, title="📡 Configuration d'envoi"):
    def __init__(self, parent_view, notif_id: str, config: dict):
        super().__init__()
        self.parent_view = parent_view
        self.notif_id = notif_id
        self.config = config

        self.channel_input = ui.TextInput(
            label="ID du salon d'envoi",
            placeholder="Ex: 123456789101112",
            default=config.get("channel_id", ""),
            max_length=25,
            required=True
        )
        self.role_input = ui.TextInput(
            label="ID du rôle (ou everyone/here)",
            placeholder="Laissez vide pour aucune mention",
            default=config.get("role_id", ""),
            max_length=25,
            required=False
        )
        self.message_input = ui.TextInput(
            label="Message personnalisé",
            style=discord.TextStyle.paragraph,
            placeholder="Variables dispo : {role}, {tag}, {pseudo}, {plateforme}, {lien}",
            default=config.get("message", "{role} {tag} **{pseudo}** est en live ! {lien}"),
            max_length=1000,
            required=True
        )
        
        self.add_item(self.channel_input)
        self.add_item(self.role_input)
        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction):
        data = load_data()
        guild_id_str = str(interaction.guild.id)
        
        notifs = data[guild_id_str]["notifications"]
        if self.notif_id in notifs:
            notifs[self.notif_id]["channel_id"] = self.channel_input.value.strip()
            notifs[self.notif_id]["role_id"] = self.role_input.value.strip()
            notifs[self.notif_id]["message"] = self.message_input.value.strip()
            save_data(data)

            self.parent_view.notifications = notifs
            await self.parent_view.update_ui(interaction)

# ==============================================================================
# --------------------------- VUES & SELECTEURS --------------------------------
# ==============================================================================
class NotificationSelect(ui.Select):
    def __init__(self, notifs_dict: dict, page: int):
        self.notifs_dict = notifs_dict
        self.page = page
        
        items = list(notifs_dict.items())
        start_idx = page * 25
        end_idx = start_idx + 25
        current_page_items = items[start_idx:end_idx]

        options = []
        for idx, (n_id, conf) in enumerate(current_page_items, start=start_idx + 1):
            plat = get_platform_label(conf.get('platform', ''))
            desc = f"{plat} | Salon: {conf.get('channel_id', '❌') or '❌'}"
            options.append(discord.SelectOption(label=f"{idx}. {conf['pseudo']}", description=desc, value=n_id))

        if not options:
            options.append(discord.SelectOption(label="Aucune configuration", value="none", description="Utilisez le bouton Ajouter"))

        super().__init__(placeholder="🔍 Sélectionner une notification...", options=options, row=0, disabled=not notifs_dict)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            return
        self.view.selected_notif = self.values[0]
        await self.view.open_profile(interaction, self.values[0])


class NotificationProfileSelect(ui.Select):
    def __init__(self, notif_id: str, config: dict):
        options = [
            discord.SelectOption(label="📨 Salon d'envoi", value="channel"),
            discord.SelectOption(label="👤 ID utilisateur", value="user"),
            discord.SelectOption(label="🎭 Notification ou rôle", value="role"),
        ]
        super().__init__(placeholder="⚙️ Choisir un réglage", options=options, row=0)
        self.notif_id = notif_id
        self.config = config

    async def callback(self, interaction: discord.Interaction):
        await self.view.handle_profile_action(interaction, self.values[0])


class NotificationChannelSelectView(ui.View):
    def __init__(self, parent_view, notif_id: str):
        super().__init__(timeout=300)
        self.parent_view = parent_view
        self.notif_id = notif_id

        select = discord.ui.ChannelSelect(
            placeholder="📨 Choisir le salon d'envoi",
            channel_types=[discord.ChannelType.text],
            row=0,
        )
        select.callback = self.channel_selected
        self.add_item(select)

        back_btn = ui.Button(label="Retour", style=discord.ButtonStyle.secondary, emoji="⬅️", row=1)
        back_btn.callback = self.back_callback
        self.add_item(back_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ Vous n'avez pas la permission de gérer les notifications.", ephemeral=True)
            return False
        return True

    async def channel_selected(self, interaction: discord.Interaction):
        channel_id = interaction.data.get("values", [None])[0]
        if not channel_id:
            return await interaction.response.send_message("❌ Aucun salon sélectionné.", ephemeral=True)

        channel = interaction.guild.get_channel(int(channel_id))
        if not channel:
            return await interaction.response.send_message("❌ Salon introuvable.", ephemeral=True)

        data = load_data()
        guild_id_str = str(interaction.guild.id)
        notifs = data.setdefault(guild_id_str, {"notifications": {}})["notifications"]
        if self.notif_id not in notifs:
            return await interaction.response.send_message("❌ Notification introuvable.", ephemeral=True)

        notifs[self.notif_id]["channel_id"] = str(channel.id)
        save_data(data)
        self.parent_view.notifications = notifs
        await interaction.response.defer()
        await self.parent_view.open_profile(interaction, self.notif_id)

    async def back_callback(self, interaction: discord.Interaction):
        await self.parent_view.open_profile(interaction, self.notif_id)


class NotificationUserSelectView(ui.View):
    def __init__(self, parent_view, notif_id: str):
        super().__init__(timeout=300)
        self.parent_view = parent_view
        self.notif_id = notif_id

        user_select = discord.ui.UserSelect(
            placeholder="👤 Choisir l'utilisateur",
            row=0,
        )
        user_select.callback = self.user_selected
        self.add_item(user_select)

        back_btn = ui.Button(label="Retour", style=discord.ButtonStyle.secondary, emoji="⬅️", row=1)
        back_btn.callback = self.back_callback
        self.add_item(back_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ Vous n'avez pas la permission de gérer les notifications.", ephemeral=True)
            return False
        return True

    async def user_selected(self, interaction: discord.Interaction):
        selected_user_id = interaction.data.get("values", [None])[0]
        if not selected_user_id:
            return await interaction.response.send_message("❌ Aucun utilisateur sélectionné.", ephemeral=True)

        selected_user = interaction.guild.get_member(int(selected_user_id))
        if not selected_user:
            return await interaction.response.send_message("❌ Utilisateur introuvable sur ce serveur.", ephemeral=True)

        data = load_data()
        guild_id_str = str(interaction.guild.id)
        notifs = data.setdefault(guild_id_str, {"notifications": {}})["notifications"]
        if self.notif_id not in notifs:
            return await interaction.response.send_message("❌ Notification introuvable.", ephemeral=True)

        notifs[self.notif_id]["user_id"] = str(selected_user.id)
        save_data(data)
        self.parent_view.notifications = notifs
        await interaction.response.defer()
        await self.parent_view.open_profile(interaction, self.notif_id)

    async def back_callback(self, interaction: discord.Interaction):
        await self.parent_view.open_profile(interaction, self.notif_id)


class NotificationRoleSelectView(ui.View):
    def __init__(self, parent_view, notif_id: str):
        super().__init__(timeout=300)
        self.parent_view = parent_view
        self.notif_id = notif_id

        role_select = discord.ui.RoleSelect(
            placeholder="🎭 Choisir le rôle",
            row=0,
        )
        role_select.callback = self.role_selected
        self.add_item(role_select)

        mention_select = ui.Select(
            placeholder="📣 Ou choisir @everyone/@here",
            options=[
                discord.SelectOption(label="Aucun", value="none"),
                discord.SelectOption(label="@everyone", value="everyone"),
                discord.SelectOption(label="@here", value="here"),
            ],
            row=1,
        )
        mention_select.callback = self.mention_selected
        self.add_item(mention_select)

        back_btn = ui.Button(label="Retour", style=discord.ButtonStyle.secondary, emoji="⬅️", row=2)
        back_btn.callback = self.back_callback
        self.add_item(back_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ Vous n'avez pas la permission de gérer les notifications.", ephemeral=True)
            return False
        return True

    async def role_selected(self, interaction: discord.Interaction):
        role_id = interaction.data.get("values", [None])[0]
        if not role_id:
            return await interaction.response.send_message("❌ Aucun rôle sélectionné.", ephemeral=True)

        data = load_data()
        guild_id_str = str(interaction.guild.id)
        notifs = data.setdefault(guild_id_str, {"notifications": {}})["notifications"]
        if self.notif_id not in notifs:
            return await interaction.response.send_message("❌ Notification introuvable.", ephemeral=True)

        notifs[self.notif_id]["role_id"] = str(role_id)
        save_data(data)
        self.parent_view.notifications = notifs
        await interaction.response.defer()
        await self.parent_view.open_profile(interaction, self.notif_id)

    async def mention_selected(self, interaction: discord.Interaction):
        choice = interaction.data.get("values", ["none"])[0]

        data = load_data()
        guild_id_str = str(interaction.guild.id)
        notifs = data.setdefault(guild_id_str, {"notifications": {}})["notifications"]
        if self.notif_id not in notifs:
            return await interaction.response.send_message("❌ Notification introuvable.", ephemeral=True)

        notifs[self.notif_id]["role_id"] = "" if choice == "none" else choice
        save_data(data)
        self.parent_view.notifications = notifs
        await interaction.response.defer()
        await self.parent_view.open_profile(interaction, self.notif_id)

    async def back_callback(self, interaction: discord.Interaction):
        await self.parent_view.open_profile(interaction, self.notif_id)


class NotificationProfileView(ui.View):
    def __init__(self, parent_view, notif_id: str):
        super().__init__(timeout=600)
        self.parent_view = parent_view
        self.notif_id = notif_id
        self.config = parent_view.notifications.get(notif_id, {})
        self.add_item(NotificationProfileSelect(notif_id, self.config))

        preview_btn = ui.Button(label="Aperçu", style=discord.ButtonStyle.success, emoji="👁️", row=1)
        preview_btn.callback = self.preview_callback
        self.add_item(preview_btn)

        back_btn = ui.Button(label="Retour", style=discord.ButtonStyle.secondary, emoji="⬅️", row=1)
        back_btn.callback = self.back_callback
        self.add_item(back_btn)

        help_btn = ui.Button(label="Aide", style=discord.ButtonStyle.secondary, emoji="❓", row=1)
        help_btn.callback = self.help_callback
        self.add_item(help_btn)

        delete_btn = ui.Button(label="Supprimer", style=discord.ButtonStyle.danger, emoji="🗑️", row=1)
        delete_btn.callback = self.delete_callback
        self.add_item(delete_btn)

    def create_custom_embed(self, title: str, description: str) -> discord.Embed:
        return self.parent_view.create_custom_embed(title, description)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ Vous n'avez pas la permission de gérer les notifications.", ephemeral=True)
            return False
        return True

    async def back_callback(self, interaction: discord.Interaction):
        await self.parent_view.show_main(interaction)

    async def help_callback(self, interaction: discord.Interaction):
        await self.parent_view.send_help(interaction)

    async def preview_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        config = self.parent_view.notifications.get(self.notif_id, {})
        link = get_channel_fallback_link(config)
        event_kind = get_event_kind(config)
        msg_content = build_notification_message(config, link, event_kind=event_kind)
        thumbnail_url = await resolve_thumbnail_url(self.parent_view.bot, interaction.guild, config)
        embed = build_notification_embed(self.parent_view.bot, interaction.guild, interaction.user, config, link, thumbnail_url=thumbnail_url, event_kind=event_kind)
        view = build_notification_link_view(config, link, event_kind)
        await interaction.followup.send(content=msg_content, embed=embed, view=view, ephemeral=True)

    async def delete_callback(self, interaction: discord.Interaction):
        data = load_data()
        guild_id_str = str(interaction.guild.id)
        if guild_id_str in data and self.notif_id in data[guild_id_str]["notifications"]:
            del data[guild_id_str]["notifications"][self.notif_id]
            save_data(data)

        self.parent_view.notifications = get_guild_notifs(interaction.guild.id)
        self.parent_view.selected_notif = None
        await self.parent_view.show_main(interaction)

    async def handle_profile_action(self, interaction: discord.Interaction, action: str):
        if action == "channel":
            await interaction.response.edit_message(view=NotificationChannelSelectView(self.parent_view, self.notif_id))
            return
        if action == "user":
            await interaction.response.edit_message(view=NotificationUserSelectView(self.parent_view, self.notif_id))
            return
        if action == "role":
            await interaction.response.edit_message(view=NotificationRoleSelectView(self.parent_view, self.notif_id))
            return


class NotificationMainView(ui.View):
    def __init__(self, ctx, bot, is_admin: bool):
        super().__init__(timeout=600)
        self.ctx = ctx
        self.bot = bot
        self.is_admin = is_admin
        self.message = None
        self.notifications = get_guild_notifs(ctx.guild.id)
        self.selected_notif = None
        self.page = 0
        self.max_pages = max(0, (len(self.notifications) - 1) // 25)

        self.setup_components()

class NotificationsView(ui.View):
    def __init__(self, ctx, bot, is_admin: bool):
        super().__init__(timeout=600)
        self.ctx = ctx
        self.bot = bot
        self.is_admin = is_admin
        self.message = None
        self.notifications = get_guild_notifs(ctx.guild.id)
        self.selected_notif = None
        self.page = 0
        self.max_pages = max(0, (len(self.notifications) - 1) // 25)

        self.setup_components()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ Vous n'avez pas la permission de gérer les notifications.", ephemeral=True)
            return False
        return True

    def create_custom_embed(self, title: str, description: str) -> discord.Embed:
        if config_manager:
            return config_manager.get_formatted_embed(
                guild=self.ctx.guild,
                user=self.ctx.author,
                bot=self.bot,
                title=title,
                description=description,
                target_id=self.ctx.guild.id,
            )
        return discord.Embed(title=title, description=description, color=0x2b2d31)

    def setup_components(self):
        self.clear_items()

        if self.is_admin:
            self.add_item(NotificationSelect(self.notifications, self.page))

            add_btn = ui.Button(label="Ajouter", style=discord.ButtonStyle.success, emoji="➕", row=1)
            add_btn.callback = self.add_callback
            self.add_item(add_btn)

            help_btn = ui.Button(label="Aide", style=discord.ButtonStyle.secondary, emoji="❓", row=1)
            help_btn.callback = self.help_callback
            self.add_item(help_btn)

        if self.max_pages > 0:
            prev_btn = ui.Button(label="◀️ Précédent", style=discord.ButtonStyle.secondary, disabled=self.page == 0, row=3)
            prev_btn.callback = self.prev_callback
            self.add_item(prev_btn)

            next_btn = ui.Button(label="Suivant ▶️", style=discord.ButtonStyle.secondary, disabled=self.page >= self.max_pages, row=3)
            next_btn.callback = self.next_callback
            self.add_item(next_btn)

    async def add_callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ProfileModal(self))

    async def open_profile(self, interaction: discord.Interaction, notif_id: str):
        self.selected_notif = notif_id
        self.setup_components()

        config = self.notifications.get(notif_id, {})
        embed = self.create_custom_embed(
            "Gestion des notifications auto",
            self.build_profile_description(notif_id, config),
        )

        view = NotificationProfileView(self, notif_id)
        if self.message:
            if not interaction.response.is_done():
                await interaction.response.defer()
            await self.message.edit(embed=embed, view=view)
        else:
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed, view=view)
            else:
                await interaction.response.edit_message(embed=embed, view=view)

    def build_profile_description(self, notif_id: str, config: dict) -> str:
        pseudo = config.get("pseudo", "Inconnu")
        platform = get_platform_label(config.get("platform", "twitch"))
        channel = f"<#{config.get('channel_id')}>" if config.get("channel_id") else "❌"
        user_id = f"<@{config.get('user_id')}>" if config.get("user_id") else "❌"
        role_raw = config.get("role_id")
        if role_raw in ["everyone", "@everyone"]:
            role_id = "@everyone"
        elif role_raw in ["here", "@here"]:
            role_id = "@here"
        elif role_raw:
            role_id = f"<@&{role_raw}>"
        else:
            role_id = "❌"
        author_name = f"🔴 {pseudo} est en direct" if get_event_kind(config) == "live" else f"🎬 Nouvelle vidéo de {pseudo}"

        return (
            f"**1. {pseudo} - {platform}**\n\n"
            f"📨 Salon d'envoi : {channel}\n"
            f"👤 Id utilisateur : {user_id}\n"
            f"🎭 Notification ou rôle : {role_id}\n"
            f"🎨 Auteur fixe : {author_name}"
        )

    async def show_main(self, interaction: discord.Interaction):
        self.notifications = get_guild_notifs(self.ctx.guild.id)
        self.max_pages = max(0, (len(self.notifications) - 1) // 25)
        if self.page > self.max_pages:
            self.page = max(0, self.max_pages)
        self.selected_notif = None
        self.setup_components()

        embed = self.get_embed()
        if not interaction.response.is_done():
            await interaction.response.defer()
        if self.message:
            await self.message.edit(embed=embed, view=self)
        else:
            await interaction.edit_original_response(embed=embed, view=self)

    async def send_help(self, interaction: discord.Interaction):
        desc = (
            "## Guide complet\n"
            "Configure des annonces automatiques Twitch et YouTube en quelques clics.\n\n"
            "**1. Créer un profil**\n"
            "Clique sur Ajouter puis renseigne:\n"
            "- Pseudo\n"
            "- Plateforme: twitch, youtube video, youtube live\n"
            "- ID utilisateur Discord optionnel\n\n"
            "**2. Configurer le profil**\n"
            "Dans le profil sélectionné:\n"
            "- Salon d'envoi\n"
            "- ID utilisateur à associer\n"
            "- Mention: rôle, @everyone, @here, ou aucun\n\n"
            "**3. Message automatique**\n"
            "Le bot génère automatiquement un message propre selon la plateforme:\n"
            "- Twitch et YouTube Live: style direct\n"
            "- YouTube Video: style nouvelle vidéo\n"
            "Le lien est ajouté avec un bouton d'action contextuel.\n\n"
            "**4. Aperçu avant envoi**\n"
            "Le bouton Aperçu montre le rendu final:\n"
            "- Mention\n"
            "- Texte généré\n"
            "- Auteur et image\n"
            "- Couleur de plateforme\n\n"
            "**5. Images et auteur**\n"
            "Le bot tente de récupérer l'image de profil de la plateforme,\n"
            "puis utilise l'avatar Discord associé si disponible.\n\n"
            "**6. Conseils**\n"
            "- Utilise exactement les valeurs de plateforme ci-dessus\n"
            "- Vérifie les permissions du bot dans le salon cible\n"
            "- Utilise Aperçu après chaque modification"
        )
        embed = self.create_custom_embed("❓ Aide - Notifications Auto", desc)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def edit_profile_callback(self, interaction: discord.Interaction):
        config = self.notifications.get(self.selected_notif, {})
        await interaction.response.send_modal(NotificationSettingsModal(self, self.selected_notif, config))

    async def edit_send_callback(self, interaction: discord.Interaction):
        config = self.notifications.get(self.selected_notif, {})
        await interaction.response.send_modal(NotificationSettingsModal(self, self.selected_notif, config))

    async def delete_callback(self, interaction: discord.Interaction):
        data = load_data()
        guild_id_str = str(interaction.guild.id)
        if guild_id_str in data and self.selected_notif in data[guild_id_str]["notifications"]:
            del data[guild_id_str]["notifications"][self.selected_notif]
            save_data(data)

        self.notifications = get_guild_notifs(interaction.guild.id)
        self.selected_notif = None
        await self.show_main(interaction)

    async def preview_callback(self, interaction: discord.Interaction):
        config = self.notifications.get(self.selected_notif)
        if not config:
            return
        await interaction.response.defer(ephemeral=True)
        link = get_channel_fallback_link(config)
        event_kind = get_event_kind(config)
        msg_content = build_notification_message(config, link, event_kind=event_kind)
        thumbnail_url = await resolve_thumbnail_url(self.bot, interaction.guild, config)
        embed = build_notification_embed(self.bot, interaction.guild, interaction.user, config, link, thumbnail_url=thumbnail_url, event_kind=event_kind)
        view = build_notification_link_view(config, link, event_kind)
        await interaction.followup.send(content=msg_content, embed=embed, view=view, ephemeral=True)

    async def help_callback(self, interaction: discord.Interaction):
        await self.send_help(interaction)

    async def prev_callback(self, interaction: discord.Interaction):
        if self.page > 0:
            self.page -= 1
            await self.update_ui(interaction)

    async def next_callback(self, interaction: discord.Interaction):
        if self.page < self.max_pages:
            self.page += 1
            await self.update_ui(interaction)

    def get_embed(self) -> discord.Embed:
        items = list(self.notifications.items())
        start_idx = self.page * 25
        end_idx = start_idx + 25
        current_page_items = items[start_idx:end_idx]

        desc_list = ""
        if not current_page_items:
            desc_list = "*Aucune notification configurée pour ce serveur.*"
        else:
            for idx, (n_id, conf) in enumerate(current_page_items, start=start_idx + 1):
                pseudo = conf.get('pseudo', 'Inconnu')
                plat = get_platform_label(conf.get('platform', 'Inconnu'))
                
                desc_list += f"**{idx}.** {pseudo} - {plat}\n"

        title = "Gestion des notifications auto"
        desc = (
            f"> Page **{self.page + 1}** / **{max(1, self.max_pages + 1)}**\n\n"
            f"{desc_list}"
        )

        return self.create_custom_embed(title, desc)

    async def update_ui(self, interaction: discord.Interaction):
        self.max_pages = max(0, (len(self.notifications) - 1) // 25)
        if self.page > self.max_pages:
            self.page = max(0, self.max_pages)
        self.setup_components()
        
        embed = self.get_embed()
        if not interaction.response.is_done():
            await interaction.response.defer()
        if self.message:
            await self.message.edit(embed=embed, view=self)
        else:
            await interaction.edit_original_response(embed=embed, view=self)

# ==============================================================================
# --------------------------- COG PRINCIPAL ------------------------------------
# ==============================================================================
class NotificationsCog(commands.Cog):
    """📡 Module de notifications YouTube & Twitch."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # self.check_apis.start() # Décommente ceci quand tes requêtes API (plus bas) seront écrites

    def cog_unload(self):
        # self.check_apis.cancel()
        pass

    @commands.hybrid_command(
        name="notif",
        description="Configure les annonces automatiques Twitch et YouTube."
    )
    @discord.app_commands.default_permissions(manage_guild=True)
    @commands.has_permissions(manage_guild=True)
    async def notif(self, ctx: commands.Context):
        if not ctx.author.guild_permissions.manage_guild:
            return await ctx.send("❌ Vous n'avez pas la permission de gérer les notifications.", ephemeral=True)

        view = NotificationsView(ctx, self.bot, is_admin=True)
        embed = view.get_embed()
        if ctx.interaction:
            msg = await ctx.send(embed=embed, view=view, ephemeral=True)
        else:
            msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    # ==============================================================================
    # --------------------------- BOUCLE DE VERIFICATION ---------------------------
    # ==============================================================================
    @tasks.loop(minutes=5.0)
    async def check_apis(self):
        """Vérifie régulièrement les APIs Twitch et YouTube pour les nouvelles vidéos/lives."""
        data = load_data()
        
        for guild_id_str, guild_data in data.items():
            notifs = guild_data.get("notifications", {})
            guild = self.bot.get_guild(int(guild_id_str))
            
            if not guild:
                continue

            for notif_id, conf in notifs.items():
                platform = str(conf.get("platform", "")).strip().lower()
                channel_id = conf.get("channel_id")
                
                if not channel_id:
                    continue
                
                send_channel = guild.get_channel(int(channel_id))
                if not send_channel:
                    continue

                if platform == "twitch":
                    await self.check_twitch(conf, send_channel)
                elif platform in {"youtube", "youtube video", "youtube live"}:
                    await self.check_youtube(conf, send_channel)

    @check_apis.before_loop
    async def before_check_apis(self):
        await self.bot.wait_until_ready()
        self.announced_streams = getattr(self, "announced_streams", {})

    async def check_twitch(self, conf: dict, channel: discord.TextChannel):
        """Fonction de vérification pour Twitch."""
        pseudo = conf["pseudo"].lower()
        notif_id = f"twitch_{pseudo}"
        
        # TODO: Faire la requête API Twitch ici (avec aiohttp).
        is_live = False 
        stream_url = f"https://twitch.tv/{pseudo}"
        
        # Variables à récupérer depuis l'API Twitch
        profile_url = "https://via.placeholder.com/150.png?text=Profil"
        stream_thumbnail = "https://via.placeholder.com/800x450.png?text=Live"
        
        if is_live:
            if not self.announced_streams.get(notif_id):
                self.announced_streams[notif_id] = True
                await self.send_notification(conf, channel, stream_url, profile_url, stream_thumbnail)
        else:
            if self.announced_streams.get(notif_id):
                self.announced_streams[notif_id] = False

    async def check_youtube(self, conf: dict, channel: discord.TextChannel):
        """Fonction de vérification pour YouTube."""
        pseudo = conf["pseudo"]
        notif_id = f"youtube_{pseudo.lower()}"
        
        # TODO: Faire la requête API YouTube ici.
        is_live_or_new_video = False 
        video_id = "12345" 
        video_url = f"https://youtube.com/watch?v={video_id}"
        
        # Variables à récupérer depuis l'API YouTube
        profile_url = "https://via.placeholder.com/150.png?text=Profil"
        video_thumbnail = f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
        
        if is_live_or_new_video and self.announced_streams.get(notif_id) != video_id:
            self.announced_streams[notif_id] = video_id
            await self.send_notification(conf, channel, video_url, profile_url, video_thumbnail)

    async def send_notification(self, conf: dict, channel: discord.TextChannel, link: str, profile_url: str, thumbnail_url: str):
        """Construit et envoie l'embed final de notification."""
        effective_link = link or get_channel_fallback_link(conf)
        event_kind = get_event_kind(conf)
        msg_content = build_notification_message(conf, effective_link, event_kind=event_kind)
        image_url = thumbnail_url or profile_url
        embed = build_notification_embed(
            self.bot,
            channel.guild,
            channel.guild.me,
            conf,
            effective_link,
            thumbnail_url=image_url,
            event_kind=event_kind,
        )
        view = build_notification_link_view(conf, effective_link, event_kind)
        
        try:
            # Envoi du message avec le texte (ping etc.) ET l'embed
            await channel.send(content=msg_content, embed=embed, view=view)
        except discord.Forbidden:
            print(f"Permissions manquantes pour envoyer un message dans {channel.id}")

async def setup(bot: commands.Bot):
    await bot.add_cog(NotificationsCog(bot))