"""
COMMANDE ACCES - Contrôle global d'accès aux commandes
=======================================================
Configuration serveur des restrictions par salons, rôles et utilisateurs.
"""

from __future__ import annotations

from typing import Any

import discord
from discord import ui
from discord.ext import commands

from utils.config_data import DataManager
from utils.config_id import IdModal
from utils.config_perm import FALLBACK_DENY_MESSAGE, ensure_command_permission, perm_command
from utils.config_prefix import prefix_config_manager
from utils.config_theme import config_manager
from utils.config_emoji import Emoji as E


MAX_ITEMS_PER_KIND = 200
VISIBLE_LIMIT = 25


class AccessConfigManager:
    def __init__(self):
        self.data = DataManager("staff/configuration/acces")

    def _normalize_ids(self, values: list[Any] | None) -> list[int]:
        src = values or []
        out: list[int] = []
        for value in src:
            raw = str(value)
            if not raw.isdigit():
                continue
            number = int(raw)
            if number not in out:
                out.append(number)
            if len(out) >= MAX_ITEMS_PER_KIND:
                break
        return out

    def _normalize(self, raw: dict[str, Any] | None) -> dict[str, Any]:
        src = raw or {}

        channel_mode = str(src.get("channel_mode", "blacklist")).lower().strip()
        role_mode = str(src.get("role_mode", "blacklist")).lower().strip()
        user_mode = str(src.get("user_mode", "blacklist")).lower().strip()

        if channel_mode not in {"blacklist", "whitelist"}:
            channel_mode = "blacklist"
        if role_mode not in {"blacklist", "whitelist"}:
            role_mode = "blacklist"
        if user_mode not in {"blacklist", "whitelist"}:
            user_mode = "blacklist"

        return {
            "channel_mode": channel_mode,
            "channels": self._normalize_ids(src.get("channels", [])),
            "role_mode": role_mode,
            "roles": self._normalize_ids(src.get("roles", [])),
            "user_mode": user_mode,
            "users": self._normalize_ids(src.get("users", [])),
            "owner_bypass": bool(src.get("owner_bypass", True)),
            "admin_bypass": bool(src.get("admin_bypass", True)),
        }

    def load(self, guild_id: int) -> dict[str, Any]:
        return self._normalize(self.data.load(guild_id))

    def save(self, guild_id: int, config: dict[str, Any]) -> None:
        normalized = self._normalize(config)
        self.data.save(guild_id, normalized)


access_config_manager = AccessConfigManager()


class AccessLayoutView(ui.LayoutView):
    def __init__(self, cog: "Access", guild: discord.Guild, user: discord.Member):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild = guild
        self.user = user
        self.message: discord.Message | None = None
        self.config = self.cog.get_config(self.guild.id)
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(f"{getattr(E, 'ERREUR', '❌')} Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        return True

    def _mode_chip(self, mode: str) -> str:
        if mode == "whitelist":
            return f"{getattr(E, 'STATUS_ONLINE', '🟢')} Whitelist"
        return f"{getattr(E, 'STATUS_DND', '🔴')} Blacklist"

    def _render_mentions(self, values: list[int], pattern: str) -> str:
        if not values:
            return "Aucun"
        txt = " ".join(pattern.format(v) for v in values)
        if len(txt) > 900:
            return txt[:890] + "... *(et d'autres)*"
        return txt

    def _sync_owner_blacklist_rule(self) -> None:
        """Le propriétaire serveur ne peut pas être blacklisté directement en utilisateur."""
        users = self.config.get("users", [])
        if self.config.get("user_mode", "blacklist") == "blacklist" and self.guild.owner_id in users:
            self.config["users"] = [uid for uid in users if uid != self.guild.owner_id]

    def _build(self):
        self.clear_items()
        self._sync_owner_blacklist_rule()

        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.cog.bot)
        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text") or ""

        channel_mode = self.config.get("channel_mode", "blacklist")
        role_mode = self.config.get("role_mode", "blacklist")
        user_mode = self.config.get("user_mode", "blacklist")

        owner_bypass = bool(self.config.get("owner_bypass", True))
        admin_bypass = bool(self.config.get("admin_bypass", True))

        channels = list(self.config.get("channels", []))
        roles = list(self.config.get("roles", []))
        users = list(self.config.get("users", []))

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {getattr(E, 'BOUCLIER', '🛡️')} Configuration d'accès"))
        container.add_item(
            ui.TextDisplay(
                "Configurez les restrictions d'utilisation des commandes du bot.\n"
                "Le propriétaire serveur ne peut pas être blacklisté en utilisateur."
            )
        )

        bypass_row = ui.ActionRow()
        owner_btn = ui.Button(
            label=f"Owner bypass: {'Activé' if owner_bypass else 'Désactivé'}",
            style=discord.ButtonStyle.success if owner_bypass else discord.ButtonStyle.secondary,
            emoji=getattr(E, "OWNER", "👑"),
        )
        owner_btn.callback = self.toggle_owner_bypass
        bypass_row.add_item(owner_btn)

        admin_btn = ui.Button(
            label=f"Admin bypass: {'Activé' if admin_bypass else 'Désactivé'}",
            style=discord.ButtonStyle.success if admin_bypass else discord.ButtonStyle.secondary,
            emoji=getattr(E, "BOUCLIER", "🛡️"),
        )
        admin_btn.callback = self.toggle_admin_bypass
        bypass_row.add_item(admin_btn)
        container.add_item(bypass_row)

        # Section Salons
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
        container.add_item(ui.TextDisplay(f"## {getattr(E, 'CIBLE', '📍')} Catégorie Salons"))
        container.add_item(
            ui.TextDisplay(
                f"- Mode : {self._mode_chip(channel_mode)}\n"
                f"- Salons configurés ({len(channels)}) : {self._render_mentions(channels, '<#{}>')}"
            )
        )

        channel_row = ui.ActionRow()
        toggle_chan_btn = ui.Button(
            label="Basculer mode salons",
            style=discord.ButtonStyle.secondary,
            emoji=getattr(E, "RAFRAICHIR", "🔄"),
        )
        toggle_chan_btn.callback = self.toggle_channel_mode
        channel_row.add_item(toggle_chan_btn)

        add_chan_id_btn = ui.Button(label="Ajouter ID salon", style=discord.ButtonStyle.primary, emoji=getattr(E, "IDENTIFIANT", "🆔"))
        add_chan_id_btn.callback = self.open_channel_id_modal
        channel_row.add_item(add_chan_id_btn)
        container.add_item(channel_row)

        channel_select = ui.ChannelSelect(
            placeholder="Ajouter/Retirer des salons...",
            min_values=0,
            max_values=min(VISIBLE_LIMIT, max(1, len(channels[:VISIBLE_LIMIT]))),
            channel_types=[discord.ChannelType.text, discord.ChannelType.voice, discord.ChannelType.news],
        )
        channel_select.default_values = [discord.Object(id=cid) for cid in channels[:VISIBLE_LIMIT]]
        channel_select.callback = self.on_channel_select
        channel_select_row = ui.ActionRow()
        channel_select_row.add_item(channel_select)
        container.add_item(channel_select_row)

        # Section Rôles
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
        container.add_item(ui.TextDisplay(f"## {getattr(E, 'ROLE', '🎭')} Catégorie Rôles"))
        container.add_item(
            ui.TextDisplay(
                f"- Mode : {self._mode_chip(role_mode)}\n"
                f"- Rôles configurés ({len(roles)}) : {self._render_mentions(roles, '<@&{}>')}"
            )
        )

        role_row = ui.ActionRow()
        toggle_role_btn = ui.Button(
            label="Basculer mode rôles",
            style=discord.ButtonStyle.secondary,
            emoji=getattr(E, "RAFRAICHIR", "🔄"),
        )
        toggle_role_btn.callback = self.toggle_role_mode
        role_row.add_item(toggle_role_btn)

        add_role_id_btn = ui.Button(label="Ajouter ID rôle", style=discord.ButtonStyle.primary, emoji=getattr(E, "IDENTIFIANT", "🆔"))
        add_role_id_btn.callback = self.open_role_id_modal
        role_row.add_item(add_role_id_btn)
        container.add_item(role_row)

        role_select = ui.RoleSelect(
            placeholder="Ajouter/Retirer des rôles...",
            min_values=0,
            max_values=min(VISIBLE_LIMIT, max(1, len(roles[:VISIBLE_LIMIT]))),
        )
        role_select.default_values = [discord.Object(id=rid) for rid in roles[:VISIBLE_LIMIT]]
        role_select.callback = self.on_role_select
        role_select_row = ui.ActionRow()
        role_select_row.add_item(role_select)
        container.add_item(role_select_row)

        # Section Utilisateurs
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
        container.add_item(ui.TextDisplay(f"## {getattr(E, 'PROFIL', '👤')} Catégorie Utilisateurs"))
        container.add_item(
            ui.TextDisplay(
                f"- Mode : {self._mode_chip(user_mode)}\n"
                f"- Utilisateurs configurés ({len(users)}) : {self._render_mentions(users, '<@{}>')}"
            )
        )

        user_row = ui.ActionRow()
        toggle_user_btn = ui.Button(
            label="Basculer mode utilisateurs",
            style=discord.ButtonStyle.secondary,
            emoji=getattr(E, "RAFRAICHIR", "🔄"),
        )
        toggle_user_btn.callback = self.toggle_user_mode
        user_row.add_item(toggle_user_btn)

        add_user_id_btn = ui.Button(label="Ajouter ID utilisateur", style=discord.ButtonStyle.primary, emoji=getattr(E, "IDENTIFIANT", "🆔"))
        add_user_id_btn.callback = self.open_user_id_modal
        user_row.add_item(add_user_id_btn)
        container.add_item(user_row)

        user_select = ui.UserSelect(
            placeholder="Ajouter/Retirer des utilisateurs...",
            min_values=0,
            max_values=min(VISIBLE_LIMIT, max(1, len(users[:VISIBLE_LIMIT]))),
        )
        user_select.default_values = [discord.Object(id=uid) for uid in users[:VISIBLE_LIMIT]]
        user_select.callback = self.on_user_select
        user_select_row = ui.ActionRow()
        user_select_row.add_item(user_select)
        container.add_item(user_select_row)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    def _save(self):
        self._sync_owner_blacklist_rule()
        self.cog.save_config(self.guild.id, self.config)

    async def _refresh(self, interaction: discord.Interaction):
        self._save()
        self._build()
        await interaction.response.edit_message(view=self)

    async def _refresh_silent(self):
        if self.message is not None:
            self._save()
            self._build()
            await self.message.edit(view=self)

    def _selected_ids(self, interaction: discord.Interaction) -> set[int]:
        values = getattr(interaction, "values", None)
        if values:
            result: set[int] = set()
            for item in values:
                item_id = getattr(item, "id", None)
                if isinstance(item_id, int):
                    result.add(item_id)
                else:
                    raw = str(item)
                    if raw.isdigit():
                        result.add(int(raw))
            return result

        raw_values = interaction.data.get("values", []) if interaction.data else []
        return {int(v) for v in raw_values if str(v).isdigit()}

    async def toggle_owner_bypass(self, interaction: discord.Interaction):
        self.config["owner_bypass"] = not bool(self.config.get("owner_bypass", True))
        await self._refresh(interaction)

    async def toggle_admin_bypass(self, interaction: discord.Interaction):
        self.config["admin_bypass"] = not bool(self.config.get("admin_bypass", True))
        await self._refresh(interaction)

    async def toggle_channel_mode(self, interaction: discord.Interaction):
        cur = self.config.get("channel_mode", "blacklist")
        self.config["channel_mode"] = "whitelist" if cur == "blacklist" else "blacklist"
        await self._refresh(interaction)

    async def toggle_role_mode(self, interaction: discord.Interaction):
        cur = self.config.get("role_mode", "blacklist")
        self.config["role_mode"] = "whitelist" if cur == "blacklist" else "blacklist"
        await self._refresh(interaction)

    async def toggle_user_mode(self, interaction: discord.Interaction):
        cur = self.config.get("user_mode", "blacklist")
        self.config["user_mode"] = "whitelist" if cur == "blacklist" else "blacklist"
        await self._refresh(interaction)

    async def on_channel_select(self, interaction: discord.Interaction):
        current = set(self.config.get("channels", []))
        shown = set(self.config.get("channels", [])[:VISIBLE_LIMIT])
        selected = self._selected_ids(interaction)
        self.config["channels"] = list((current - shown).union(selected))
        await self._refresh(interaction)

    async def on_role_select(self, interaction: discord.Interaction):
        current = set(self.config.get("roles", []))
        shown = set(self.config.get("roles", [])[:VISIBLE_LIMIT])
        selected = self._selected_ids(interaction)
        self.config["roles"] = list((current - shown).union(selected))
        await self._refresh(interaction)

    async def on_user_select(self, interaction: discord.Interaction):
        current = set(self.config.get("users", []))
        shown = set(self.config.get("users", [])[:VISIBLE_LIMIT])
        selected = self._selected_ids(interaction)

        # Le propriétaire serveur n'est jamais blacklistable en utilisateur.
        if self.config.get("user_mode", "blacklist") == "blacklist":
            selected.discard(self.guild.owner_id)

        self.config["users"] = list((current - shown).union(selected))
        await self._refresh(interaction)

    async def open_channel_id_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(IdModal("channel", self._on_channel_id_submit))

    async def open_role_id_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(IdModal("role", self._on_role_id_submit))

    async def open_user_id_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(IdModal("user", self._on_user_id_submit))

    async def _on_channel_id_submit(self, interaction: discord.Interaction, target):
        channel = target if isinstance(target, discord.abc.GuildChannel) else None
        if channel is None:
            return
        channels = self.config.get("channels", [])
        if channel.id not in channels:
            channels.append(channel.id)
        self.config["channels"] = channels
        await self._refresh_silent()

    async def _on_role_id_submit(self, interaction: discord.Interaction, target):
        role = target if isinstance(target, discord.Role) else None
        if role is None:
            return
        roles = self.config.get("roles", [])
        if role.id not in roles:
            roles.append(role.id)
        self.config["roles"] = roles
        await self._refresh_silent()

    async def _on_user_id_submit(self, interaction: discord.Interaction, target):
        member = target if isinstance(target, discord.Member) else None
        if member is None:
            return

        if self.config.get("user_mode", "blacklist") == "blacklist" and member.id == self.guild.owner_id:
            await interaction.followup.send(
                f"{getattr(E, 'ERREUR', '❌')} Impossible de blacklister le propriétaire serveur dans la catégorie utilisateurs.",
                ephemeral=True,
            )
            await self._refresh_silent()
            return

        users = self.config.get("users", [])
        if member.id not in users:
            users.append(member.id)
        self.config["users"] = users
        await self._refresh_silent()


class Access(commands.Cog):
    """Configuration des accès globaux du bot par serveur."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def get_config(self, guild_id: int) -> dict[str, Any]:
        return access_config_manager.load(guild_id)

    def save_config(self, guild_id: int, config: dict[str, Any]) -> None:
        access_config_manager.save(guild_id, config)

    def _get_access_prefix(self, ctx: commands.Context) -> str:
        prefix = getattr(ctx, "prefix", None)
        if isinstance(prefix, str) and prefix.strip():
            return prefix.strip()

        if ctx.guild:
            try:
                effective = prefix_config_manager.get_effective_prefixes(self.bot, ctx.guild.id, default_prefix="!")
                for value in effective:
                    if value and value != "\x00":
                        return value
            except Exception:
                pass

        return "!"

    def _access_hint(self, ctx: commands.Context) -> str:
        return f"Les accès se gèrent via la commande `{self._get_access_prefix(ctx)}acces`."

    @perm_command(level=1)
    @commands.hybrid_command(name="acces", description="Configurer les accès globaux du bot")
    async def acces(self, ctx: commands.Context):
        if not ctx.guild:
            return await ctx.send(f"{getattr(E, 'ERREUR', '❌')} Cette commande doit être utilisée sur un serveur.")

        if not await ensure_command_permission(ctx, command_name="acces"):
            return

        if not isinstance(ctx.author, discord.Member):
            author = ctx.guild.get_member(ctx.author.id)
            if author is None:
                return await ctx.send(f"{FALLBACK_DENY_MESSAGE}\n{self._access_hint(ctx)}")
        else:
            author = ctx.author

        view = AccessLayoutView(self, ctx.guild, author)
        message = await ctx.send(view=view)
        view.message = message

    def bot_check(self, ctx: commands.Context) -> bool:
        if not ctx.guild or ctx.author.bot:
            return True

        # Évite de bloquer la commande de gestion elle-même.
        if ctx.command and ctx.command.name == "acces":
            return True

        config = self.get_config(ctx.guild.id)

        channel_mode = config.get("channel_mode", "blacklist")
        channels = config.get("channels", [])

        role_mode = config.get("role_mode", "blacklist")
        roles = set(config.get("roles", []))
        author_roles = {role.id for role in getattr(ctx.author, "roles", [])}
        role_match = any(rid in roles for rid in author_roles)

        user_mode = config.get("user_mode", "blacklist")
        users = set(config.get("users", []))
        user_match = ctx.author.id in users

        is_owner = ctx.author.id == ctx.guild.owner_id

        # Priorité stricte: blacklist utilisateur/rôle > whitelist et bypass.
        if role_mode == "blacklist" and role_match:
            self.bot.loop.create_task(self._send_rejection(ctx, f"{getattr(E, 'REFUSER', '🚫')} Un de vos rôles est bloqué."))
            return False
        if user_mode == "blacklist" and user_match:
            self.bot.loop.create_task(self._send_rejection(ctx, f"{getattr(E, 'REFUSER', '🚫')} Votre utilisateur est bloqué."))
            return False

        if bool(config.get("owner_bypass", True)) and is_owner:
            return True

        # Si owner bypass est désactivé, le propriétaire n'est autorisé
        # que via une whitelist salon OU rôle.
        if is_owner and not bool(config.get("owner_bypass", True)):
            owner_allowed_by_channel_whitelist = channel_mode == "whitelist" and ctx.channel.id in channels
            owner_allowed_by_role_whitelist = role_mode == "whitelist" and role_match
            if not (owner_allowed_by_channel_whitelist or owner_allowed_by_role_whitelist):
                self.bot.loop.create_task(
                    self._send_rejection(
                        ctx,
                        f"{getattr(E, 'LOCK', '🔒')} Owner bypass désactivé : propriétaire autorisé uniquement via whitelist salon ou rôle.",
                    )
                )
                return False
            return True

        if bool(config.get("admin_bypass", True)) and ctx.author.guild_permissions.administrator and not is_owner:
            return True

        # Filtre salons
        if channel_mode == "blacklist" and ctx.channel.id in channels:
            self.bot.loop.create_task(self._send_rejection(ctx, f"{getattr(E, 'ATTENTION', '🔕')} Les commandes sont interdites dans ce salon."))
            return False
        if channel_mode == "whitelist" and ctx.channel.id not in channels:
            if not channels:
                self.bot.loop.create_task(
                    self._send_rejection(ctx, f"{getattr(E, 'LOCK', '🔒')} Mode whitelist salons actif, mais aucun salon n'est configuré.")
                )
                return False
            allowed = " ".join(f"<#{cid}>" for cid in channels[:10])
            self.bot.loop.create_task(self._send_rejection(ctx, f"{getattr(E, 'TEXT', '💬')} Le bot est autorisé uniquement dans :\n{allowed}"))
            return False

        # Filtre rôles
        if role_mode == "whitelist" and roles and not role_match:
            self.bot.loop.create_task(self._send_rejection(ctx, f"{getattr(E, 'LOCK', '🔒')} Vos rôles ne sont pas autorisés (whitelist)."))
            return False

        # Filtre utilisateurs
        if user_mode == "whitelist" and users and not user_match:
            self.bot.loop.create_task(self._send_rejection(ctx, f"{getattr(E, 'LOCK', '🔒')} Votre utilisateur n'est pas autorisé (whitelist)."))
            return False

        return True

    async def _send_rejection(self, ctx: commands.Context, message: str):
        try:
            hint = self._access_hint(ctx)
            full_message = message if "Les accès se gèrent via la commande" in message else f"{message}\n{hint}"
            if ctx.interaction:
                if not ctx.interaction.response.is_done():
                    await ctx.interaction.response.send_message(full_message, ephemeral=True)
                else:
                    await ctx.interaction.followup.send(full_message, ephemeral=True)
            else:
                await ctx.send(full_message, delete_after=7)
        except Exception:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Access(bot))