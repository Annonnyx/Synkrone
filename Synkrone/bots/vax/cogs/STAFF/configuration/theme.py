from __future__ import annotations

import asyncio
import time
import re
import aiohttp

import discord
from discord import ui
from discord.ext import commands
from discord.utils import _bytes_to_base64_data

from utils.config_emoji import Emoji as E
from utils.config_prefix import get_global_prefix, prefix_config_manager
from utils.config_theme import BaliseCatalogLayoutView, config_manager
from utils.config_perm import FALLBACK_DENY_MESSAGE, ensure_command_permission, perm_command, perm_config_manager

UPLOAD_TIMEOUT = 300
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif")

class NicknameModal(ui.Modal):
    def __init__(self, cog: "Theme", guild: discord.Guild, owner_id: int, source_message: discord.Message | None):
        super().__init__(title="Nom du bot pour ce serveur")
        self.cog = cog
        self.guild = guild
        self.owner_id = owner_id
        self.source_message = source_message
        current_member = guild.me or guild.get_member(cog.bot.user.id)

        self.nickname = ui.TextInput(
            label="Surnom du bot",
            placeholder="Laisse vide pour revenir au nom global",
            default=current_member.nick if current_member and current_member.nick else "",
            required=False,
            max_length=32,
        )
        self.add_item(self.nickname)

    async def on_submit(self, interaction: discord.Interaction):
        value = self.nickname.value.strip() or None
        if not interaction.response.is_done():
            await interaction.response.defer()
            
        success = await self.cog.apply_profile_update(
            interaction,
            success_title="Nom mis à jour",
            success_body="Le nom du bot pour ce serveur vient d'être modifié.",
            nick=value,
        )
        if not success:
            return

        member = await self.cog.fetch_me(self.guild)
        if self.source_message is not None:
            await self.source_message.edit(
                view=ThemeLayoutView(self.cog, self.guild, interaction.user, default_section="profil", member=member)
            )


class EditNicknameButton(ui.Button):
    def __init__(self, cog: "Theme", guild: discord.Guild, owner_id: int):
        super().__init__(label="Nom", style=discord.ButtonStyle.primary, emoji=getattr(E, "MODIFIER", "✏️"))
        self.cog = cog
        self.guild = guild
        self.owner_id = owner_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(f"{getattr(E, 'ERREUR', '❌')} Ce menu ne vous appartient pas.", ephemeral=True)
            return
        await interaction.response.send_modal(NicknameModal(self.cog, self.guild, self.owner_id, interaction.message))


class UploadImageButton(ui.Button):
    def __init__(self, cog: "Theme", guild: discord.Guild, owner_id: int, asset_key: str, label: str):
        super().__init__(label=label, style=discord.ButtonStyle.secondary, emoji=getattr(E, "IMAGE", "🖼️"))
        self.cog = cog
        self.guild = guild
        self.owner_id = owner_id
        self.asset_key = asset_key

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(f"{getattr(E, 'ERREUR', '❌')} Ce menu ne vous appartient pas.", ephemeral=True)
            return
        await self.cog._start_image_upload(interaction, self.asset_key)


class ResetProfileSelect(ui.Select):
    def __init__(self, cog: "Theme", guild: discord.Guild, owner_id: int, member: discord.Member):
        options: list[discord.SelectOption] = []
        if member.nick:
            options.append(discord.SelectOption(label="Nom", value="nick", description="Réinitialiser le nom serveur", emoji=getattr(E, "SUPPRIMER", "🗑️")))

        guild_avatar = getattr(member, "guild_avatar", None)
        if guild_avatar:
            options.append(discord.SelectOption(label="Avatar", value="avatar", description="Réinitialiser l'avatar serveur", emoji=getattr(E, "SUPPRIMER", "🗑️")))

        guild_banner = getattr(member, "guild_banner", None)
        if guild_banner:
            options.append(discord.SelectOption(label="Bannière", value="banner", description="Réinitialiser la bannière serveur", emoji=getattr(E, "SUPPRIMER", "🗑️")))

        self.has_options = bool(options)
        if not options:
            options = [
                discord.SelectOption(
                    label="Aucune information personnalisée",
                    value="none",
                    description="Rien à réinitialiser pour le moment",
                    emoji=getattr(E, "INFO", "ℹ️"),
                )
            ]

        super().__init__(
            placeholder="Réinitialiser une information du profil..." if self.has_options else "Aucune information à réinitialiser",
            min_values=1,
            max_values=1,
            options=options,
            disabled=not self.has_options,
        )
        self.cog = cog
        self.guild = guild
        self.owner_id = owner_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(f"{getattr(E, 'ERREUR', '❌')} Ce menu ne vous appartient pas.", ephemeral=True)
            return

        if not self.has_options:
            await interaction.response.defer()
            return

        field_name = (interaction.data or {}).get("values", [None])[0]
        if field_name not in {"nick", "avatar", "banner"}:
            await interaction.response.send_message(f"{getattr(E, 'ERREUR', '❌')} Champ de réinitialisation invalide.", ephemeral=True)
            return

        await interaction.response.defer()
        success = await self.cog.apply_profile_update(
            interaction,
            success_title="Profil réinitialisé",
            success_body=f"Le champ `{field_name}` a été réinitialisé pour ce serveur.",
            **{field_name: None},
        )
        if not success:
            return

        member = await self.cog.fetch_me(self.guild)
        if interaction.message is not None:
            bot_profile_user = await self.cog.fetch_bot_profile_user()
            await interaction.message.edit(
                view=ThemeLayoutView(
                    self.cog,
                    self.guild,
                    interaction.user,
                    default_section="profil",
                    member=member,
                    bot_profile_user=bot_profile_user,
                )
            )


class ThemeConfigModal(ui.Modal):
    def __init__(self, view: "ThemeLayoutView", source_message: discord.Message | None):
        super().__init__(title="Édition du thème serveur")
        self.view = view
        self.source_message = source_message

        current_vals = config_manager.get_server_theme_values(self.view.guild.id)
        self.color_input = ui.TextInput(
            label="Code couleur (Hex)",
            default=f"#{int(current_vals.get('color', config_manager.DEFAULT_COLOR)):06x}",
            required=False,
            min_length=6,
            max_length=7,
        )
        self.footer_input = ui.TextInput(
            label="Texte footer",
            default=current_vals.get("footer", config_manager.DEFAULT_FOOTER),
            required=False,
            style=discord.TextStyle.long,
            max_length=80,
        )
        self.add_item(self.color_input)
        self.add_item(self.footer_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw_color = self.color_input.value.strip().lstrip("#")
        try:
            new_color = int(raw_color, 16) if raw_color else config_manager.DEFAULT_COLOR
        except ValueError:
            await interaction.response.send_message(f"{getattr(E, 'ERREUR', '❌')} Code couleur invalide.", ephemeral=True)
            return

        footer_text = (self.footer_input.value or "").strip()
        if len(footer_text) > 80:
            await interaction.response.send_message(
                f"{getattr(E, 'ERREUR', '❌')} Le footer ne doit pas dépasser 80 caractères (actuel : {len(footer_text)}).",
                ephemeral=True,
            )
            return

        config_manager.save_config(
            {
                "color": new_color,
                "footer": footer_text or config_manager.DEFAULT_FOOTER,
            },
            self.view.guild.id,
        )

        refreshed = ThemeLayoutView(
            self.view.cog,
            self.view.guild,
            self.view.user,
            default_section="theme",
            member=self.view.member,
        )

        if self.source_message is not None:
            await self.source_message.edit(view=refreshed)
            await interaction.response.send_message(f"{getattr(E, 'VALIDER', '✅')} Thème mis à jour.", ephemeral=True)
            return

        await interaction.response.edit_message(view=refreshed)


class ThemePrefixConfigModal(ui.Modal):
    def __init__(self, view: "ThemeLayoutView", source_message: discord.Message | None):
        super().__init__(title="Configuration des préfixes")
        self.view = view
        self.source_message = source_message

        cfg = prefix_config_manager.get_server_config(view.guild.id)
        values = cfg.get("prefixes", [])

        self.prefix_1 = ui.TextInput(label="Préfixe 1", required=False, max_length=5, default=values[0] if len(values) > 0 else "")
        self.prefix_2 = ui.TextInput(label="Préfixe 2", required=False, max_length=5, default=values[1] if len(values) > 1 else "")
        self.prefix_3 = ui.TextInput(label="Préfixe 3", required=False, max_length=5, default=values[2] if len(values) > 2 else "")
        self.prefix_4 = ui.TextInput(label="Préfixe 4", required=False, max_length=5, default=values[3] if len(values) > 3 else "")
        self.prefix_5 = ui.TextInput(label="Préfixe 5", required=False, max_length=5, default=values[4] if len(values) > 4 else "")

        self.add_item(self.prefix_1)
        self.add_item(self.prefix_2)
        self.add_item(self.prefix_3)
        self.add_item(self.prefix_4)
        self.add_item(self.prefix_5)

    async def on_submit(self, interaction: discord.Interaction):
        new_prefixes: list[str] = []
        for field in [self.prefix_1, self.prefix_2, self.prefix_3, self.prefix_4, self.prefix_5]:
            value = (field.value or "").strip()
            if value and value not in new_prefixes:
                new_prefixes.append(value)

        current = prefix_config_manager.get_server_config(self.view.guild.id)
        prefix_config_manager.save_server_config(
            self.view.guild.id,
            {
                "prefixes": new_prefixes,
                "disable_global": bool(current.get("disable_global", False)),
            },
        )

        refreshed = ThemeLayoutView(
            self.view.cog,
            self.view.guild,
            self.view.user,
            default_section="prefix",
            member=self.view.member,
        )

        if self.source_message is not None:
            await interaction.response.defer()
            await self.source_message.edit(view=refreshed)
            return

        await interaction.response.edit_message(view=refreshed)


class ThemeLayoutView(ui.LayoutView):
    COLOR_OPTIONS = [
        ("red", getattr(E, "STATUS_DND", "🔴"), 0xED4245, "Rouge"),
        ("white", getattr(E, "N1", "⚪"), 0xFFFFFF, "Blanc"),
        ("orange", getattr(E, "N2", "🟠"), 0xFAA61A, "Orange"),
        ("yellow", getattr(E, "N3", "🟡"), 0xFEE75C, "Jaune"),
        ("green", getattr(E, "STATUS_ONLINE", "🟢"), 0x57F287, "Vert"),
        ("blue", getattr(E, "N4", "🔵"), 0x5865F2, "Bleu"),
        ("purple", getattr(E, "N5", "🟣"), 0x9B59B6, "Violet"),
        ("brown", getattr(E, "N6", "🟤"), 0x8D6E63, "Marron"),
        ("black", getattr(E, "STATUS_INVISIBLE", "⚫"), 0x23272A, "Noir"),
    ]

    def __init__(
        self,
        cog: "Theme",
        guild: discord.Guild,
        user: discord.Member,
        *,
        default_section: str = "profil",
        member: discord.Member | None = None,
        bot_profile_user: discord.User | None = None,
    ):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.user = user
        self.current_section = default_section
        self.member = member
        self.bot_profile_user = bot_profile_user
        self.confirm_reset = False
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(f"{getattr(E, 'ERREUR', '❌')} Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        return True

    @staticmethod
    def _add_banner_gallery(container: ui.Container, image_url: str, description: str) -> None:
        try:
            gallery = ui.MediaGallery()
            gallery.add_item(media=image_url, description=description)
            container.add_item(gallery)
        except Exception:
            container.add_item(ui.TextDisplay(f"{getattr(E, 'ATTENTION', '⚠️')} Image indisponible: {description}"))

    @staticmethod
    def _add_thumbnail_section(container: ui.Container, text: str, image_url: str, description: str) -> None:
        try:
            container.add_item(
                ui.Section(
                    text,
                    accessory=ui.Thumbnail(image_url, description=description),
                )
            )
        except Exception:
            container.add_item(ui.TextDisplay(text))

    def _build(self):
        self.clear_items()

        theme_values = config_manager.get_resolved_values(self.guild.id)
        accent_color = int(theme_values.get("color", config_manager.DEFAULT_COLOR))
        footer_template = str(theme_values.get("footer", config_manager.DEFAULT_FOOTER))
        footer_resolved = config_manager.format_footer_text(footer_template, self.guild, self.user, self.cog.bot, for_layout=True)

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {getattr(E, 'MODIFIER', '⚙️')} Configuration serveur"))

        nav_row = ui.ActionRow()
        section_select = ui.Select(
            placeholder="Sélectionne une section...",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label="Profil", value="profil", description="Profil serveur du bot", emoji=getattr(E, "PROFIL", "👤"), default=self.current_section == "profil"),
                discord.SelectOption(label="Préfixe", value="prefix", description="Préfixes de commande", emoji=getattr(E, "TEXT", "⌨️"), default=self.current_section == "prefix"),
                discord.SelectOption(label="Thème", value="theme", description="Couleur et footer", emoji=getattr(E, "IMAGE", "🎨"), default=self.current_section == "theme"),
            ],
        )
        section_select.callback = self._on_section_select
        nav_row.add_item(section_select)
        container.add_item(nav_row)
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

        if self.current_section == "profil":
            self._render_profile_section(container)
        elif self.current_section == "prefix":
            self._render_prefix_section(container)
        else:
            self._render_theme_section(container)

        if footer_resolved:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_resolved))

        self.add_item(container)

    def _resolve_profile_banner_asset(self, member: discord.Member) -> discord.Asset | None:
        guild_banner = getattr(member, "guild_banner", None)
        if guild_banner:
            return guild_banner

        bot_user = self.cog.bot.user
        if self.bot_profile_user and self.bot_profile_user.banner:
            return self.bot_profile_user.banner
        if bot_user and getattr(bot_user, "banner", None):
            return bot_user.banner
        return None

    def _render_profile_section(self, container: ui.Container):
        member = self.member or self.guild.me or self.guild.get_member(self.cog.bot.user.id)
        if member is None:
            container.add_item(ui.TextDisplay(f"{getattr(E, 'ATTENTION', '⚠️')} Impossible de récupérer le membre du bot sur ce serveur."))
            return

        guild_avatar = getattr(member, "guild_avatar", None)
        bot_user = self.cog.bot.user
        avatar_asset = guild_avatar or member.display_avatar
        banner_asset = self._resolve_profile_banner_asset(member)

        container.add_item(ui.TextDisplay(f"## {getattr(E, 'PROFIL', '👤')} Profil du bot"))

        profile_name = member.display_name
        profile_id = bot_user.id if bot_user else member.id
        profile_text = (
            f"- **Nom du serveur** : `{profile_name}`\n"
            f"- **Identifiant** : `{profile_id}`"
        )

        self._add_thumbnail_section(
            container,
            profile_text,
            avatar_asset.url,
            f"Avatar de {member.display_name}",
        )

        if banner_asset:
            self._add_banner_gallery(container, banner_asset.url, f"Bannière de {member.display_name}")

        reset_row = ui.ActionRow()
        reset_row.add_item(ResetProfileSelect(self.cog, self.guild, self.user.id, member))
        container.add_item(reset_row)

        row_actions = ui.ActionRow(
            EditNicknameButton(self.cog, self.guild, self.user.id),
            UploadImageButton(self.cog, self.guild, self.user.id, "avatar", "Avatar"),
            UploadImageButton(self.cog, self.guild, self.user.id, "banner", "Bannière"),
        )
        container.add_item(row_actions)

    def _render_prefix_section(self, container: ui.Container):
        cfg = prefix_config_manager.get_server_config(self.guild.id)
        server_prefixes = cfg.get("prefixes", [])
        disable_global = bool(cfg.get("disable_global", False))

        if not server_prefixes and disable_global:
            disable_global = False
            prefix_config_manager.save_server_config(self.guild.id, {"prefixes": [], "disable_global": False})

        global_prefix = get_global_prefix(self.cog.bot, fallback="!")
        global_state = "Désactivé" if disable_global else "Activé"
        global_emoji = getattr(E, "STATUS_DND", "🔴") if disable_global else getattr(E, "STATUS_ONLINE", "🟢")
        custom_prefixes_text = " ".join(f"`{p}`" for p in server_prefixes) if server_prefixes else "Aucun"

        container.add_item(ui.TextDisplay(f"## {getattr(E, 'TEXT', '⌨️')} Configuration des préfixes"))
        container.add_item(
            ui.TextDisplay(
                f"- Préfixe global {global_emoji} `[{global_prefix}]` : {global_state}\n"
                f"- Préfixes custom : {custom_prefixes_text}"
            )
        )

        if server_prefixes:
            remove_select_row = ui.ActionRow()
            remove_select = ui.Select(
                placeholder="Sélectionner les préfixes à supprimer...",
                min_values=1,
                max_values=len(server_prefixes),
                options=[discord.SelectOption(label=f"Préfixe : {prefix}", value=str(idx), emoji=getattr(E, "SUPPRIMER", "🗑️")) for idx, prefix in enumerate(server_prefixes)],
            )
            remove_select.callback = self.remove_prefixes
            remove_select_row.add_item(remove_select)
            container.add_item(remove_select_row)

        actions_row = ui.ActionRow()
        configure_btn = ui.Button(label="Configurer", style=discord.ButtonStyle.primary, emoji=getattr(E, "MODIFIER", "⚙️"))
        configure_btn.callback = self.open_prefix_modal
        actions_row.add_item(configure_btn)

        if server_prefixes:
            toggle_label = "Activer préfixe global" if disable_global else "Désactiver préfixe global"
            toggle_style = discord.ButtonStyle.success if disable_global else discord.ButtonStyle.secondary
            toggle_btn = ui.Button(label=toggle_label, style=toggle_style, emoji=getattr(E, "MODIFIER", "🔧"))
            toggle_btn.callback = self.toggle_prefix_global
            actions_row.add_item(toggle_btn)

        container.add_item(actions_row)

    def _render_theme_section(self, container: ui.Container):
        has_modified_theme = config_manager.is_server_theme_modified(self.guild.id)
        if not has_modified_theme:
            self.confirm_reset = False

        current_vals = config_manager.get_server_theme_values(self.guild.id)
        current_color = int(current_vals.get("color", config_manager.DEFAULT_COLOR))
        color_hex = f"0x{current_color:06x}"
        footer_brut = current_vals.get("footer", config_manager.DEFAULT_FOOTER)
        footer_resolu = config_manager.format_footer_text(footer_brut, self.guild, self.user, self.cog.bot) or "-"

        container.add_item(ui.TextDisplay(f"## {getattr(E, 'IMAGE', '🎨')} Configuration du thème"))
        container.add_item(ui.TextDisplay(f"{getattr(E, 'IMAGE', '🎨')} Code hex couleur : [Clique-ici](https://htmlcolorcodes.com/fr/)"))
        container.add_item(
            ui.TextDisplay(
                f"- Couleur active : `{color_hex}`\n"
                f"- Footer brut : `{footer_brut}`\n"
                f"- Footer résolu : `{footer_resolu}`"
            )
        )

        select_row = ui.ActionRow()
        options = [discord.SelectOption(label=label, value=key, emoji=emoji) for key, emoji, _hex, label in self.COLOR_OPTIONS]
        color_select = ui.Select(
            placeholder="Choisis une couleur rapide...",
            min_values=1,
            max_values=1,
            options=options,
        )
        color_select.callback = self.color_select_callback
        select_row.add_item(color_select)
        container.add_item(select_row)

        actions_row = ui.ActionRow()
        edit_btn = ui.Button(label="Modifier", style=discord.ButtonStyle.primary, emoji=getattr(E, "MODIFIER", "✏️"))
        edit_btn.callback = self.open_config_modal
        actions_row.add_item(edit_btn)

        balises_btn = ui.Button(label="Balises", style=discord.ButtonStyle.secondary, emoji=getattr(E, "LISTE", "📚"))
        balises_btn.callback = self.show_balises
        actions_row.add_item(balises_btn)

        if has_modified_theme:
            if self.confirm_reset:
                confirm_btn = ui.Button(label="Sûr ?", style=discord.ButtonStyle.danger, emoji=getattr(E, "VALIDER", "✅"))
                confirm_btn.callback = self.confirm_reset_theme
                actions_row.add_item(confirm_btn)

                cancel_btn = ui.Button(label="Annuler", style=discord.ButtonStyle.secondary, emoji=getattr(E, "RETOUR", "↩️"))
                cancel_btn.callback = self.cancel_reset_theme
                actions_row.add_item(cancel_btn)
            else:
                reset_btn = ui.Button(label="Défaut", style=discord.ButtonStyle.danger, emoji=getattr(E, "SUPPRIMER", "🗑️"))
                reset_btn.callback = self.ask_reset_theme
                actions_row.add_item(reset_btn)

        container.add_item(actions_row)

    async def _on_section_select(self, interaction: discord.Interaction):
        selected = interaction.data.get("values", ["profil"])[0]
        self.current_section = selected if selected in {"profil", "prefix", "theme"} else "profil"

        member = self.member
        if self.current_section == "profil":
            member = await self.cog.fetch_me(self.guild)

        await interaction.response.edit_message(
            view=ThemeLayoutView(
                self.cog,
                self.guild,
                self.user,
                default_section=self.current_section,
                member=member,
                bot_profile_user=await self.cog.fetch_bot_profile_user(),
            )
        )

    async def color_select_callback(self, interaction: discord.Interaction):
        choice = interaction.data.get("values", [None])[0]
        color_map = {key: hex_color for key, _emoji, hex_color, _label in self.COLOR_OPTIONS}

        if choice not in color_map:
            await interaction.response.send_message(f"{getattr(E, 'ERREUR', '❌')} Couleur invalide.", ephemeral=True)
            return

        gid = self.guild.id
        current_vals = config_manager.get_server_theme_values(gid)
        config_manager.save_config(
            {
                "color": color_map[choice],
                "footer": current_vals.get("footer", config_manager.DEFAULT_FOOTER),
            },
            gid,
        )

        await interaction.response.edit_message(
            view=ThemeLayoutView(
                self.cog,
                self.guild,
                self.user,
                default_section="theme",
                member=self.member,
                bot_profile_user=self.bot_profile_user,
            )
        )

    async def open_config_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ThemeConfigModal(self, interaction.message))

    async def show_balises(self, interaction: discord.Interaction):
        view = BaliseCatalogLayoutView(self.guild, interaction.user, self.cog.bot)
        await interaction.response.send_message(
            content=f"✨ **Balises Globales du Bot**\n*(Ces variables s'adaptent dynamiquement au serveur et à l'utilisateur)*", 
            view=view, 
            ephemeral=True
        )

    async def open_prefix_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ThemePrefixConfigModal(self, interaction.message))

    async def toggle_prefix_global(self, interaction: discord.Interaction):
        cfg = prefix_config_manager.get_server_config(self.guild.id)
        current_prefixes = cfg.get("prefixes", [])

        if not current_prefixes:
            prefix_config_manager.save_server_config(self.guild.id, {"prefixes": [], "disable_global": False})
            await interaction.response.edit_message(
                view=ThemeLayoutView(
                    self.cog,
                    self.guild,
                    self.user,
                    default_section="prefix",
                    member=self.member,
                    bot_profile_user=self.bot_profile_user,
                )
            )
            return

        prefix_config_manager.save_server_config(
            self.guild.id,
            {
                "prefixes": current_prefixes,
                "disable_global": not bool(cfg.get("disable_global", False)),
            },
        )
        await interaction.response.edit_message(
            view=ThemeLayoutView(
                self.cog,
                self.guild,
                self.user,
                default_section="prefix",
                member=self.member,
                bot_profile_user=self.bot_profile_user,
            )
        )

    async def remove_prefixes(self, interaction: discord.Interaction):
        raw_values = interaction.data.get("values", []) if interaction.data else []
        selected_indexes = {int(v) for v in raw_values if str(v).isdigit()}

        cfg = prefix_config_manager.get_server_config(self.guild.id)
        updated_prefixes = [p for idx, p in enumerate(cfg.get("prefixes", [])) if idx not in selected_indexes]
        next_disable_global = bool(cfg.get("disable_global", False)) and bool(updated_prefixes)

        prefix_config_manager.save_server_config(
            self.guild.id,
            {
                "prefixes": updated_prefixes,
                "disable_global": next_disable_global,
            },
        )

        await interaction.response.edit_message(
            view=ThemeLayoutView(
                self.cog,
                self.guild,
                self.user,
                default_section="prefix",
                member=self.member,
                bot_profile_user=self.bot_profile_user,
            )
        )

    async def ask_reset_theme(self, interaction: discord.Interaction):
        self.confirm_reset = True
        self._build()
        await interaction.response.edit_message(view=self)

    async def cancel_reset_theme(self, interaction: discord.Interaction):
        self.confirm_reset = False
        self._build()
        await interaction.response.edit_message(view=self)

    async def confirm_reset_theme(self, interaction: discord.Interaction):
        config_manager.reset_server_theme_to_default(self.guild.id)
        await interaction.response.edit_message(
            view=ThemeLayoutView(
                self.cog,
                self.guild,
                self.user,
                default_section="theme",
                member=self.member,
                bot_profile_user=self.bot_profile_user,
            )
        )


class Theme(commands.Cog):
    """Cog pour la personnalisation du serveur"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def fetch_me(self, guild: discord.Guild) -> discord.Member:
        try:
            return await guild.fetch_member(self.bot.user.id)
        except discord.HTTPException:
            member = guild.me or guild.get_member(self.bot.user.id)
            if member is None:
                raise
            return member

    async def fetch_bot_profile_user(self) -> discord.User | None:
        if not self.bot.user:
            return None
        try:
            return await self.bot.fetch_user(self.bot.user.id)
        except discord.HTTPException:
            return self.bot.user

    async def apply_profile_update(
        self,
        interaction: discord.Interaction,
        *,
        success_title: str,
        success_body: str,
        **fields,
    ) -> bool:
        payload = {}
        for key, value in fields.items():
            if key in {"avatar", "banner"} and isinstance(value, (bytes, bytearray)):
                payload[key] = _bytes_to_base64_data(bytes(value))
            else:
                payload[key] = value

        try:
            await self.bot.http.edit_my_member(
                interaction.guild.id,
                reason=f"Profile serveur modifie par {interaction.user} ({interaction.user.id})",
                **payload,
            )
        except discord.Forbidden:
            if interaction.response.is_done():
                await interaction.followup.send(
                    f"{getattr(E, 'ERREUR', '❌')} Discord a refusé la mise à jour. Vérifiez les permissions du bot.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    f"{getattr(E, 'ERREUR', '❌')} Discord a refusé la mise à jour. Vérifiez les permissions du bot.",
                    ephemeral=True,
                )
            return False
        except discord.HTTPException as exc:
            if interaction.response.is_done():
                await interaction.followup.send(
                    f"{getattr(E, 'ERREUR', '❌')} Discord n'a pas accepté la modification.\n\n`{exc}`",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    f"{getattr(E, 'ERREUR', '❌')} Discord n'a pas accepté la modification.\n\n`{exc}`",
                    ephemeral=True,
                )
            return False

        return True

    async def _start_image_upload(self, interaction: discord.Interaction, asset_key: str):
        if not interaction.response.is_done():
            await interaction.response.defer()
            
        target_label = "l'avatar" if asset_key == "avatar" else "la bannière"
        prompt = await interaction.channel.send(
            f"{getattr(E, 'RECHERCHE', '📥')} {interaction.user.mention}, envoyez l'image (fichier joint) ou l'URL directe (PNG/JPG/WEBP/GIF) pour {target_label} dans ce salon.\n"
            f"*Vous avez 5 minutes. Le message sera automatiquement intercepté et supprimé.*", 
            delete_after=300
        )
        
        def check(m): return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id

        try:
            msg = await self.bot.wait_for('message', check=check, timeout=300)
            
            url = None
            if msg.attachments:
                for att in msg.attachments:
                    if att.content_type and att.content_type.startswith('image/'):
                        url = att.url
                        break
                if not url: url = msg.attachments[0].url
            else:
                match = re.search(r'(https?://\S+\.(?:png|jpe?g|webp|gif)(?:\?\S*)?)', msg.content, re.IGNORECASE)
                if match:
                    url = match.group(1)
                else:
                    match = re.search(r'(https?://\S+)', msg.content)
                    if match: url = match.group(1)

            if url:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            image_bytes = await resp.read()
                            
                            success = await self.apply_profile_update(
                                interaction,
                                success_title="Image mise à jour",
                                success_body=f"La {asset_key} du bot pour ce serveur a bien été mise à jour.",
                                **{asset_key: image_bytes}
                            )
                            
                            if success:
                                member = await self.fetch_me(interaction.guild)
                                bot_profile_user = await self.fetch_bot_profile_user()
                                try:
                                    await interaction.edit_original_response(
                                        view=ThemeLayoutView(
                                            self,
                                            interaction.guild,
                                            interaction.user,
                                            default_section="profil",
                                            member=member,
                                            bot_profile_user=bot_profile_user,
                                        )
                                    )
                                except discord.HTTPException:
                                    pass
                        else:
                            await interaction.channel.send(f"{getattr(E, 'ERREUR', '❌')} Erreur de téléchargement depuis l'URL.", delete_after=6)
            else:
                await interaction.channel.send(f"{getattr(E, 'ERREUR', '❌')} Aucune image ou URL valide n'a été trouvée dans votre message.", delete_after=6)

            try: await msg.delete()
            except: pass
            try: await prompt.delete()
            except: pass

        except asyncio.TimeoutError:
            await interaction.channel.send(f"{getattr(E, 'TEMPS', '⏳')} {interaction.user.mention}, délai écoulé pour l'image. Relancez l'action.", delete_after=6)

    @perm_command(level=1)
    @commands.command(name="theme", description="Personnaliser l'apparence du serveur")
    async def theme(self, ctx: commands.Context):
        if not ctx.guild:
            await ctx.send(f"{getattr(E, 'ERREUR', '❌')} Cette commande doit etre utilisee sur un serveur.")
            return

        command_levels = perm_config_manager.get_command_level_map(ctx.guild.id)
        if "theme" not in command_levels and "prefix" in command_levels:
            perm_config_manager.set_command_level(ctx.guild.id, "theme", int(command_levels["prefix"]))
            perm_config_manager.remove_command_level(ctx.guild.id, "prefix")
            command_levels = perm_config_manager.get_command_level_map(ctx.guild.id)
        cfg = perm_config_manager.load_guild_config(ctx.guild.id)

        member: discord.Member | None
        if isinstance(ctx.author, discord.Member):
            member = ctx.author
        else:
            member = ctx.guild.get_member(ctx.author.id)
            if member is None:
                try:
                    member = await ctx.guild.fetch_member(ctx.author.id)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    member = None

        is_admin_bypass = (
            member is not None
            and bool(cfg.get("admins_enabled", True))
            and member.guild_permissions.administrator
        )
        if "theme" not in command_levels and not await ctx.bot.is_owner(ctx.author) and not is_admin_bypass:
            await ctx.send(FALLBACK_DENY_MESSAGE)
            return

        if not await ensure_command_permission(ctx, command_name="theme"):
            return

        bot_member = await self.fetch_me(ctx.guild)
        bot_profile_user = await self.fetch_bot_profile_user()
        await ctx.send(
            view=ThemeLayoutView(
                self,
                ctx.guild,
                ctx.author,
                default_section="profil",
                member=bot_member,
                bot_profile_user=bot_profile_user,
            )
        )


async def setup(bot):
    await bot.add_cog(Theme(bot))