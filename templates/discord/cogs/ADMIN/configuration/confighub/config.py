import base64
import hashlib
import hmac
import json
import os
import time

import discord
from discord import app_commands, ui
from discord.ext import commands

try:
    from cogs.config_manager.utils import EmbedCustomizerView, config_manager
except ImportError:
    EmbedCustomizerView = None
    config_manager = None

try:
    from synkrone_slash import runtime_prefix
except ImportError:
    def runtime_prefix(bot=None, default="*"):
        return default


HUB_MODULES = [
    ("bienvenue", "Bienvenue", "Message et salon d'arrivée"),
    ("aurevoir", "Au revoir", "Message et salon de départ"),
    ("servembed", "Embeds serveur", "Couleur, footer, images"),
    ("ticket", "Tickets", "Panneau de tickets"),
    ("log", "Logs", "Salons de journaux"),
    ("voice", "Vocaux", "Salons vocaux temporaires"),
    ("antiscam", "Anti-scam", "Filtre des liens"),
    ("bonjour", "Bonjour", "Message du matin"),
    ("notif", "Notifications", "Lives et vidéos"),
    ("custom", "Mots-clés", "Réponses custom"),
    ("statsserver", "Stats serveur", "Salons vocaux de stats"),
]


def _normalize_origin(raw: str) -> str:
    origin = str(raw or "").strip().rstrip("/")
    if origin.endswith("/hebergement"):
        origin = origin[: -len("/hebergement")]
    return origin


def _site_origin() -> str:
    origin = _normalize_origin(
        os.getenv("PUBLIC_SITE_ORIGIN")
        or os.getenv("PUBLIC_ORIGIN")
        or os.getenv("ORBITAL_PUBLIC_ORIGIN")
        or os.getenv("SYNKRONE_PANEL_ORIGIN")
        or ""
    )
    if origin:
        return origin
    try:
        with open("config/bot.json", encoding="utf-8") as fh:
            data = json.load(fh)
        return _normalize_origin(str(data.get("siteOrigin") or ""))
    except Exception:
        return ""


def _config_secret() -> str:
    return str(
        os.getenv("BOT_CONFIG_SECRET")
        or os.getenv("SESSION_SECRET")
        or os.getenv("PLATFORM_SECRET_KEY")
        or ""
    ).strip()


def sign_site_token(guild_id: int, user_id: int, application_id: str) -> str | None:
    secret = _config_secret()
    if not secret or not application_id:
        return None
    payload = {
        "a": str(application_id),
        "exp": int(time.time()) + 15 * 60,
        "g": str(guild_id),
        "u": str(user_id),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    b64 = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    sig = hmac.new(secret.encode("utf-8"), b64.encode("ascii"), hashlib.sha256).hexdigest()[:32]
    return f"{b64}.{sig}"


def site_config_url(guild_id: int, user_id: int, application_id: str) -> str | None:
    origin = _site_origin()
    token = sign_site_token(guild_id, user_id, application_id)
    if not origin or not token:
        return None
    return f"{origin}/serveur?t={token}"


class ConfigHubView(ui.View):
    def __init__(self, cog: "ServerConfig", ctx: commands.Context, is_owner: bool):
        super().__init__(timeout=300)
        self.cog = cog
        self.ctx = ctx
        self.is_owner = is_owner
        self._add_items()

    def _add_items(self):
        self.clear_items()
        loaded = []
        for name, label, hint in HUB_MODULES:
            cmd = self.cog.bot.get_command(name)
            if cmd:
                loaded.append(discord.SelectOption(label=label, description=hint[:100], value=name))
        if loaded:
            select = ui.Select(
                placeholder="Ouvrir un module de configuration…",
                options=loaded[:25],
                min_values=1,
                max_values=1,
                row=0,
            )
            select.callback = self.open_module
            self.add_item(select)

        url = self.cog.site_url(self.ctx)
        if url:
            self.add_item(ui.Button(label="Configurer sur le site", style=discord.ButtonStyle.link, url=url, row=1))
        else:
            site = ui.Button(label="Configurer sur le site", style=discord.ButtonStyle.secondary, row=1)
            site.callback = self.site_missing
            self.add_item(site)

        if self.is_owner:
            ident = ui.Button(label="Identité du bot", style=discord.ButtonStyle.primary, row=2)
            ident.callback = self.open_identity
            self.add_item(ident)
            avatar = ui.Button(label="Avatar", style=discord.ButtonStyle.secondary, row=2)
            avatar.callback = self.ask_avatar
            self.add_item(avatar)
            embed_global = ui.Button(label="Embed global", style=discord.ButtonStyle.secondary, row=2)
            embed_global.callback = self.open_devembed
            self.add_item(embed_global)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        return True

    async def open_module(self, interaction: discord.Interaction):
        name = interaction.data.get("values", [None])[0]
        cmd = self.cog.bot.get_command(name) if name else None
        if not cmd:
            await interaction.response.send_message("Ce module n'est pas chargé.", ephemeral=True)
            return
        ctx = await commands.Context.from_interaction(interaction)
        try:
            await ctx.invoke(cmd)
        except commands.MissingPermissions:
            msg = "Permission insuffisante pour ce module."
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception as err:
            msg = f"Impossible d'ouvrir le module : {err}"
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)

    async def site_missing(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "Le lien site n'est pas configuré (PUBLIC_SITE_ORIGIN / secret manquant).",
            ephemeral=True,
        )

    async def open_identity(self, interaction: discord.Interaction):
        cmd = self.cog.bot.get_command("panelbot")
        if not cmd:
            await interaction.response.send_message("panelbot n'est pas chargé.", ephemeral=True)
            return
        ctx = await commands.Context.from_interaction(interaction)
        await ctx.invoke(cmd)

    async def open_devembed(self, interaction: discord.Interaction):
        if EmbedCustomizerView is None:
            cmd = self.cog.bot.get_command("devembed")
            if not cmd:
                await interaction.response.send_message("devembed n'est pas chargé.", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True)
            ctx = await commands.Context.from_interaction(interaction)
            await cmd.invoke(ctx)
            return
        view = EmbedCustomizerView(False, None, self.cog.bot, interaction.user.id)
        await interaction.response.send_message(
            embed=view.generate_preview_embed(interaction.user, interaction.guild),
            view=view,
            ephemeral=True,
        )

    async def ask_avatar(self, interaction: discord.Interaction):
        admin = self.cog.bot.cogs.get("BotAdmin")
        if admin is not None and hasattr(admin, "avatar_waiting_list"):
            admin.avatar_waiting_list[interaction.user.id] = time.time() + 120
        else:
            self.cog.avatar_waiting[interaction.user.id] = time.time() + 120
        await interaction.response.send_message(
            "Envoie une image PNG ou JPEG (max. 8 Mo) dans les deux minutes pour changer l'avatar du bot.",
            ephemeral=True,
        )


class ServerConfig(commands.Cog, name="ServerConfig"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.avatar_waiting = {}

    def site_url(self, ctx: commands.Context) -> str | None:
        if not ctx.guild:
            return None
        app_id = str(getattr(self.bot.user, "id", "") or "")
        return site_config_url(ctx.guild.id, ctx.author.id, app_id)

    def get_embed(self, ctx: commands.Context, title: str, description: str):
        if config_manager:
            return config_manager.get_formatted_embed(
                ctx.guild, ctx.author, self.bot, title, description,
                ctx.guild.id if ctx.guild else None,
            )
        return discord.Embed(title=title, description=description, color=0x2b2d31)

    @commands.hybrid_command(name="config", description="Hub de configuration du serveur.")
    @commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    @commands.has_permissions(manage_guild=True)
    async def config_cmd(self, ctx: commands.Context):
        is_owner = await self.bot.is_owner(ctx.author)
        loaded = [label for name, label, _ in HUB_MODULES if self.bot.get_command(name)]
        prefix = runtime_prefix(self.bot)
        site = self.site_url(ctx)
        desc = (
            f"Préfixe actuel : `{prefix}`\n"
            f"Modules détectés : {', '.join(loaded) if loaded else 'aucun'}\n\n"
            "Choisis un module pour ouvrir sa configuration, sans dupliquer les menus existants."
        )
        if site:
            desc += "\n\nTu peux aussi configurer le serveur sur le site (lien valable 15 min)."
        view = ConfigHubView(self, ctx, is_owner)
        await ctx.send(embed=self.get_embed(ctx, "Configuration", desc), view=view, ephemeral=True)

    @config_cmd.error
    async def config_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, (commands.MissingPermissions, app_commands.MissingPermissions)):
            msg = "Il faut la permission Gérer le serveur."
            if ctx.interaction:
                if ctx.interaction.response.is_done():
                    return await ctx.interaction.followup.send(msg, ephemeral=True)
                return await ctx.interaction.response.send_message(msg, ephemeral=True)
            return await ctx.send(msg)
        raise error

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        pending = self.avatar_waiting.get(message.author.id)
        if not pending:
            return
        if pending < time.time():
            self.avatar_waiting.pop(message.author.id, None)
            return
        if not await self.bot.is_owner(message.author):
            return
        if not message.attachments:
            return
        att = message.attachments[0]
        ctype = (att.content_type or "").lower()
        if att.size > 8 * 1024 * 1024 or not (ctype.startswith("image/png") or ctype.startswith("image/jpeg") or att.filename.lower().endswith((".png", ".jpg", ".jpeg"))):
            await message.channel.send("Image refusée : PNG ou JPEG, 8 Mo maximum.", delete_after=20)
            return
        try:
            data = await att.read()
            await self.bot.user.edit(avatar=data)
            self.avatar_waiting.pop(message.author.id, None)
            await message.channel.send("Avatar du bot mis à jour.", delete_after=20)
        except Exception as err:
            await message.channel.send(f"Impossible de changer l'avatar : {err}", delete_after=20)


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerConfig(bot))
