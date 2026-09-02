import discord
from discord.ext import commands, tasks
from discord import app_commands, ui
import json
import os
import re
import time
import asyncio
import traceback
from datetime import datetime, timedelta
from pathlib import Path

# ==============================================================================
# ------------------------- CONFIGURATION & CHEMINS ----------------------------
# ==============================================================================
# Sauvegarde dans le dossier 'data' à la racine (au même niveau que main.py)
BASE_DIR = Path.cwd()
DATA_DIR = BASE_DIR / "data" / "staff" / "configuration" / "data_antiscam"

try:
    from cogs.config_manager.utils import config_manager
except ImportError:
    config_manager = None

# Regex pour détecter les URLs (dont invitations Discord) en http(s) ou format court.
URL_REGEX = re.compile(
    r"(https?://[^\s]+"
    r"|(?:www\.)?discord\.gg/[^\s]+"
    r"|(?:www\.)?(?:canary\.|ptb\.)?discord(?:app)?\.com/invite/[^\s]+)",
    re.IGNORECASE,
)

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")


def parse_ids(raw_value: str) -> list[str]:
    """Extrait les IDs Discord depuis une chaîne (CSV, espaces, mentions)."""
    if not raw_value:
        return []
    found = re.findall(r"\d{17,20}", raw_value)
    unique = []
    for item in found:
        if item not in unique:
            unique.append(item)
    return unique

# ==============================================================================
# --------------------------- INTERFACES UTILISATEUR ---------------------------
# ==============================================================================

class ConfigModal(ui.Modal, title="Configuration Anti-Scam"):
    def __init__(self, view: "AntiScamMenu"):
        super().__init__()
        self.parent_view = view
        config = view.config
        
        self.threshold = ui.TextInput(
            label="Seuil de salons (ex: 3)",
            default=str(config.get("threshold", 3)),
            max_length=2,
            required=True
        )
        self.timeframe = ui.TextInput(
            label="Fenêtre de temps en secondes (ex: 60)",
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
                
            self.parent_view.config["threshold"] = threshold_val
            self.parent_view.config["timeframe"] = timeframe_val
            self.parent_view.cog.save_config(interaction.guild.id, self.parent_view.config)
            
            await self.parent_view.update_menu(interaction)
        except ValueError:
            await interaction.response.send_message("❌ Valeurs invalides. Assurez-vous d'utiliser des nombres corrects.", ephemeral=True)

class PrisonerSelect(ui.Select):
    def __init__(self, view: "AntiScamMenu"):
        self.parent_view = view
        options = []
        prisonniers = view.config.get("prisonniers", {})
        self.has_prisoners = bool(prisonniers)
        
        for uid, data in list(prisonniers.items())[:25]:  # Discord limite à 25 options
            options.append(discord.SelectOption(
                label=data.get("name", f"Utilisateur {uid}")[:50],
                description=f"Isolé le {data['timestamp']}",
                value=str(uid),
                emoji="🔓"
            ))
            
        if not options:
            options.append(discord.SelectOption(label="Aucun prisonnier", value="none"))
            
        super().__init__(
            placeholder="Sélectionnez un membre à gracier..." if self.has_prisoners else "Aucun membre en prison actuellement",
            min_values=1,
            max_values=1,
            options=options,
            disabled=not self.has_prisoners,
            row=2
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            return await interaction.response.send_message("ℹ️ Aucun membre en prison pour le moment.", ephemeral=True)
            
        user_id = self.values[0]
        member = interaction.guild.get_member(int(user_id))
        
        # Retrait de la prison
        if member:
            try:
                await member.timeout(None, reason=f"Pardon Anti-Scam accordé par {interaction.user}")
            except discord.Forbidden:
                pass
                
        if user_id in self.parent_view.config.get("prisonniers", {}):
            del self.parent_view.config["prisonniers"][user_id]
        self.parent_view.cog.save_config(interaction.guild.id, self.parent_view.config)

        await self.parent_view.update_menu(interaction)
        await interaction.followup.send("✅ L'utilisateur a été libéré et ses accès restaurés.", ephemeral=True)


class WhitelistModal(ui.Modal, title="Whitelist Anti-Scam"):
    def __init__(self, view: "AntiScamMenu"):
        super().__init__()
        self.parent_view = view
        config = view.config

        self.users_input = ui.TextInput(
            label="Utilisateurs whitelist",
            default=", ".join(config.get("whitelist_users", []))[:4000],
            placeholder="IDs ou mentions: 123..., @user",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=4000,
        )
        self.roles_input = ui.TextInput(
            label="Rôles whitelist",
            default=", ".join(config.get("whitelist_roles", []))[:4000],
            placeholder="IDs ou mentions: 123..., @role",
            style=discord.TextStyle.paragraph,
            required=False,
            max_length=4000,
        )
        self.add_item(self.users_input)
        self.add_item(self.roles_input)

    async def on_submit(self, interaction: discord.Interaction):
        users = parse_ids(self.users_input.value)
        roles = parse_ids(self.roles_input.value)
        self.parent_view.config["whitelist_users"] = users
        self.parent_view.config["whitelist_roles"] = roles
        self.parent_view.cog.save_config(interaction.guild.id, self.parent_view.config)
        await self.parent_view.update_menu(interaction)

class AntiScamMenu(ui.View):
    def __init__(self, cog, guild: discord.Guild, author: discord.Member, config: dict):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.author = author
        self.config = config
        self.refresh_buttons()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        return True

    def refresh_buttons(self):
        self.clear_items()
        
        # Bouton d'activation
        is_enabled = self.config.get("enabled", False)
        btn_toggle = ui.Button(
            label="Désactiver" if is_enabled else "Activer",
            style=discord.ButtonStyle.danger if is_enabled else discord.ButtonStyle.success,
            emoji="🛑" if is_enabled else "✅",
            row=0
        )
        btn_toggle.callback = self.toggle_module
        self.add_item(btn_toggle)
        
        # Bouton de configuration
        btn_config = ui.Button(
            label="Paramètres",
            style=discord.ButtonStyle.primary,
            emoji="⚙️",
            row=0
        )
        btn_config.callback = self.open_config
        self.add_item(btn_config)

        # Bouton de whitelist
        btn_whitelist = ui.Button(
            label="Whitelist",
            style=discord.ButtonStyle.secondary,
            emoji="📝",
            row=0
        )
        btn_whitelist.callback = self.open_whitelist
        self.add_item(btn_whitelist)
        
        # Menu déroulant des prisonniers (toujours visible)
        self.add_item(PrisonerSelect(self))

    def generate_embed(self):
        is_enabled = self.config.get("enabled", False)
        prisonniers_count = len(self.config.get("prisonniers", {}))
        whitelist_users_count = len(self.config.get("whitelist_users", []))
        whitelist_roles_count = len(self.config.get("whitelist_roles", []))
        
        desc = (
            f"**État du module :** {'✅ Actif' if is_enabled else '❌ Inactif'}\n"
            f"**Seuil de détection :** `{self.config.get('threshold', 3)}` salons\n"
            f"**Fenêtre de temps :** `{self.config.get('timeframe', 60)}` secondes\n"
            f"**Membres en prison :** `{prisonniers_count}`\n\n"
            f"**Whitelist utilisateurs :** `{whitelist_users_count}`\n"
            f"**Whitelist rôles :** `{whitelist_roles_count}`\n\n"
            "**Règle active :**\n"
            "Seuls les messages contenant un lien ou une image sont pris en compte.\n"
            "Si un utilisateur en envoie dans plusieurs salons pendant la fenêtre définie, il est mis en quarantaine.\n\n"
            "Utilisez les boutons et la liste ci-dessous pour gérer le système de protection."
        )
        
        return self.cog.create_custom_embed(
            self.guild, self.author, 
            "🛡️ Centre de Contrôle Anti-Scam", 
            desc
        )

    async def update_menu(self, interaction: discord.Interaction):
        self.refresh_buttons()
        embed = self.generate_embed()
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    async def toggle_module(self, interaction: discord.Interaction):
        self.config["enabled"] = not self.config.get("enabled", False)
        self.cog.save_config(self.guild.id, self.config)
        await self.update_menu(interaction)

    async def open_config(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ConfigModal(self))

    async def open_whitelist(self, interaction: discord.Interaction):
        await interaction.response.send_modal(WhitelistModal(self))

# ==============================================================================
# ------------------------------- COG PRINCIPAL --------------------------------
# ==============================================================================

class AntiScam(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.configs = {}
        self.message_tracker = {}
        
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.tracker_cleanup.start()

    def cog_unload(self):
        self.tracker_cleanup.cancel()

    def load_config(self, guild_id: int) -> dict:
        if guild_id in self.configs:
            return self.configs[guild_id]
            
        file_path = DATA_DIR / f"{guild_id}.json"
        default = {
            "enabled": True,
            "threshold": 3,
            "timeframe": 60,
            "debug": True,
            "whitelist_users": [],
            "whitelist_roles": [],
            "prisonniers": {}
        }
        
        if not file_path.exists():
            self.configs[guild_id] = default
            self.save_config(guild_id, default)
            return default
            
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                final_config = {**default, **data}
                self.configs[guild_id] = final_config
                return final_config
        except Exception as e:
            print(f"[ANTISCAM] Erreur lecture: {e}")
            return default

    def save_config(self, guild_id: int, config: dict):
        self.configs[guild_id] = config
        file_path = DATA_DIR / f"{guild_id}.json"
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[ANTISCAM] Erreur sauvegarde: {e}")

    def create_custom_embed(self, guild, user, title, description, color=0xe74c3c):
        if config_manager:
            return config_manager.get_formatted_embed(
                guild=guild, user=user, bot=self.bot, 
                title=title, description=description, target_id=guild.id
            )
        embed = discord.Embed(title=title, description=description, color=color)
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        return embed

    def debug_log(self, guild_id: int, config: dict, message: str):
        if not config.get("debug", False):
            return
        now = datetime.now().strftime("%H:%M:%S")
        print(f"[ANTISCAM][DEBUG][{now}][G:{guild_id}] {message}")

    def get_first_channel_link(self, guild: discord.Guild) -> str | None:
        """Retourne un lien direct vers le premier salon textuel du serveur."""
        if not guild.text_channels:
            return None
        first_channel = guild.text_channels[0]
        return f"https://discord.com/channels/{guild.id}/{first_channel.id}"

    def message_has_image(self, message: discord.Message) -> bool:
        """Détecte une image via content_type ou extension du fichier joint."""
        for attachment in message.attachments:
            content_type = (attachment.content_type or "").lower()
            filename = (attachment.filename or "").lower()
            if content_type.startswith("image/") or filename.endswith(IMAGE_EXTENSIONS):
                return True
        return False

    async def notify_guild_owner(self, guild: discord.Guild, member: discord.Member):
        """Prévient le propriétaire du serveur lorsqu'un membre est mis en quarantaine."""
        owner = guild.owner
        if owner is None:
            try:
                owner = await self.bot.fetch_user(guild.owner_id)
            except discord.HTTPException:
                owner = None

        if owner is None:
            return

        owner_msg = (
            f"[Commande `!antiscam`] ⚠️ L'utilisateur `{member}` (ID: {member.id}) a été mis en quarantaine "
            f"sur le serveur `{guild.name}` (ID: {guild.id})."
        )
        try:
            await owner.send(owner_msg)
        except discord.HTTPException:
            pass

    @tasks.loop(minutes=2)
    async def tracker_cleanup(self):
        """Nettoie le tracker pour éviter les fuites de mémoire."""
        current_time = time.time()
        for guild_id in list(self.message_tracker.keys()):
            for user_id in list(self.message_tracker[guild_id].keys()):
                # On nettoie tout ce qui a plus de 3 minutes
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

        config = self.load_config(message.guild.id)
        if not config.get("enabled"):
            return

        guild_id = message.guild.id
        user_id = message.author.id
        current_time = time.time()

        whitelist_users = set(config.get("whitelist_users", []))
        whitelist_roles = set(config.get("whitelist_roles", []))
        member_role_ids = {str(role.id) for role in message.author.roles}
        if str(user_id) in whitelist_users or member_role_ids.intersection(whitelist_roles):
            self.debug_log(guild_id, config, f"Message ignoré (whitelist): U:{user_id} C:{message.channel.id} M:{message.id}")
            return

        has_link = bool(URL_REGEX.search(message.content or ""))
        has_image = self.message_has_image(message)

        if not has_link and not has_image:
            self.debug_log(guild_id, config, f"Message ignoré (ni lien ni image): U:{user_id} C:{message.channel.id} M:{message.id}")
            return

        self.debug_log(guild_id, config, f"Message détecté: U:{user_id} C:{message.channel.id} M:{message.id} has_link={has_link} has_image={has_image}")

        if guild_id not in self.message_tracker:
            self.message_tracker[guild_id] = {}
        if user_id not in self.message_tracker[guild_id]:
            self.message_tracker[guild_id][user_id] = []

        # Nettoyage dynamique à l'insertion basé sur le timeframe
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
        self.debug_log(
            guild_id,
            config,
            f"Tracker utilisateur: U:{user_id} messages_window={len(tracker)} timeframe={timeframe}s threshold={threshold}"
        )

        # Vérification du nombre de salons distincts sur tous les messages (quel que soit le contenu)
        unique_channels = set(m['channel_id'] for m in tracker)
        self.debug_log(
            guild_id,
            config,
            f"Salons distincts: U:{user_id} distinct={len(unique_channels)}/{threshold} -> {sorted(unique_channels)}"
        )

        if len(unique_channels) >= threshold:
            self.debug_log(guild_id, config, f"SEUIL ATTEINT: U:{user_id} lancement quarantaine")
            await self.trigger_quarantine(message.guild, message.author, tracker, config)
            del self.message_tracker[guild_id][user_id]
        else:
            self.debug_log(guild_id, config, f"Seuil non atteint: U:{user_id} requis={threshold}")

    async def trigger_quarantine(self, guild: discord.Guild, member: discord.Member, messages: list, config: dict):
        """Procédure d'isolement : Timeout, suppression, notification et enregistrement."""
        self.debug_log(guild.id, config, f"Quarantaine start: U:{member.id} messages={len(messages)}")

        # 1. Timeout maximum (28 jours)
        try:
            timeout_duration = timedelta(days=28)
            await member.timeout(discord.utils.utcnow() + timeout_duration, reason="Anti-Scam : Propagation de liens malveillants")
            self.debug_log(guild.id, config, f"Timeout appliqué: U:{member.id}")
        except discord.Forbidden:
            self.debug_log(guild.id, config, f"Timeout refusé (permissions): U:{member.id}")

        # 2. Envoi du DM
        try:
            first_channel_link = self.get_first_channel_link(guild)
            redirect_line = (
                f"👉 Reviens sur le serveur via ce lien direct : {first_channel_link}\n\n"
                if first_channel_link
                else ""
            )
            dm_desc = (
                "Vous venez certainement de vous faire scam. "
                f"Vous avez sur le serveur **{guild.name}** été mis en prison par la sécurité automatique.\n\n"
                f"{redirect_line}"
                "Dès que vous avez restitué votre compte, pensez à redemander l'accès au staff!"
            )
            embed = self.create_custom_embed(guild, member, "🛡️ Mise en quarantaine", dm_desc)
            await member.send(embed=embed)
            self.debug_log(guild.id, config, f"DM envoyé: U:{member.id}")
        except discord.HTTPException:
            self.debug_log(guild.id, config, f"DM non envoyé: U:{member.id}")

        # 3. Suppression des messages
        deleted_count = 0
        for msg_data in messages:
            try:
                await msg_data['message'].delete()
                deleted_count += 1
            except (discord.NotFound, discord.Forbidden):
                pass
        self.debug_log(guild.id, config, f"Messages supprimés: {deleted_count}/{len(messages)}")

        # 4. Sauvegarde dans les données
        config["prisonniers"][str(member.id)] = {
            "name": str(member),
            "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "flagged": (messages[0].get('content') or "[message sans texte]")[:50]
        }
        self.save_config(guild.id, config)
        self.debug_log(guild.id, config, f"Quarantaine enregistrée: U:{member.id}")
        await self.notify_guild_owner(guild, member)

    @commands.hybrid_command(name="antiscam", description="Ouvre le panneau de contrôle de l'Anti-Scam")
    @discord.app_commands.default_permissions(administrator=True)
    @commands.has_permissions(administrator=True)
    async def antiscam_menu(self, ctx: commands.Context):
        if ctx.guild is None:
            return await ctx.send("❌ Cette commande doit être utilisée dans un serveur.")

        config = self.load_config(ctx.guild.id)
        view = AntiScamMenu(self, ctx.guild, ctx.author, config)
        embed = view.generate_embed()

        # `ephemeral` n'est pas valide pour un envoi préfixe classique.
        await ctx.send(embed=embed, view=view)

    @antiscam_menu.error
    async def antiscam_menu_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            return await ctx.send("❌ Tu dois être administrateur pour utiliser cette commande.")
        if isinstance(error, commands.CheckFailure):
            return await ctx.send("❌ Tu n'as pas les permissions requises pour cette commande.")

async def setup(bot: commands.Bot):
    await bot.add_cog(AntiScam(bot))