from __future__ import annotations

import asyncio
import aiohttp
import traceback
import discord
from discord import ui
from discord.ext import commands

from utils.config_data import DataManager
from utils.config_emoji import Emoji
from utils.config_theme import BaliseCatalogLayoutView, DEFAULT_COLOR, DEFAULT_FOOTER, config_manager

# ==============================================================================
# CONFIGURATION DES LOGS & CODES COULEUR CONSOLE
# ==============================================================================
DEBUG_LOGS = True
ERROR_LOGS = True


class LogColor:
    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def log_debug(message: str):
    if DEBUG_LOGS:
        print(f"{LogColor.OKCYAN}[DEBUG][PanelBot] {message}{LogColor.ENDC}")


def log_success(message: str):
    print(f"{LogColor.OKGREEN}[SUCCESS][PanelBot] {message}{LogColor.ENDC}")


def log_error(message: str):
    if ERROR_LOGS:
        print(f"{LogColor.FAIL}[ERROR][PanelBot] {message}{LogColor.ENDC}")


PANELBOT_DATA = DataManager("owner")
PANELBOT_DATA_KEY = "data_panelbot"


def _load_panelbot_data() -> dict:
    data = PANELBOT_DATA.load(PANELBOT_DATA_KEY)
    return data if isinstance(data, dict) else {}


def _save_panelbot_data(data: dict) -> None:
    PANELBOT_DATA.save(PANELBOT_DATA_KEY, data)


def _get_bot_settings() -> dict:
    raw = _load_panelbot_data().get("bot_settings", {})
    return raw if isinstance(raw, dict) else {}


def _update_bot_setting(key: str, value):
    data = _load_panelbot_data()
    bot_settings = data.get("bot_settings", {})
    if not isinstance(bot_settings, dict):
        bot_settings = {}
    bot_settings[key] = value
    data["bot_settings"] = bot_settings
    _save_panelbot_data(data)


def _get_presences() -> list[str]:
    settings = _get_bot_settings()
    raw = settings.get("presences", [])
    if not isinstance(raw, list):
        return []
    return [str(x).strip() for x in raw if str(x).strip()]


def _save_presences(presences: list[str]) -> None:
    clean = [str(x).strip() for x in presences if str(x).strip()]
    _update_bot_setting("presences", clean)


def _get_global_theme_defaults() -> dict:
    data = _load_panelbot_data()

    layout_cfg = data.get("layout_v2_config", {}) if isinstance(data.get("layout_v2_config", {}), dict) else {}
    embed_cfg = data.get("embed_config", {}) if isinstance(data.get("embed_config", {}), dict) else {}

    color = layout_cfg.get("color", layout_cfg.get("accent_color", embed_cfg.get("color", DEFAULT_COLOR)))
    footer = layout_cfg.get("footer", embed_cfg.get("footer", DEFAULT_FOOTER))

    try:
        if isinstance(color, str):
            color = color.strip()
            if color.startswith("#"):
                color = int(color[1:], 16)
            else:
                color = int(color)
        else:
            color = int(color)
    except Exception:
        color = DEFAULT_COLOR

    footer = str(footer if footer is not None else DEFAULT_FOOTER)
    return {"color": color, "footer": footer}


def _save_global_theme_defaults(color: int, footer: str) -> None:
    data = _load_panelbot_data()

    layout_cfg = data.get("layout_v2_config", {}) if isinstance(data.get("layout_v2_config", {}), dict) else {}
    embed_cfg = data.get("embed_config", {}) if isinstance(data.get("embed_config", {}), dict) else {}

    layout_cfg["color"] = int(color)
    layout_cfg["footer"] = str(footer)
    embed_cfg["color"] = int(color)
    embed_cfg["footer"] = str(footer)

    data["layout_v2_config"] = layout_cfg
    data["embed_config"] = embed_cfg
    _save_panelbot_data(data)


def _reset_global_theme_defaults() -> None:
    _save_global_theme_defaults(DEFAULT_COLOR, DEFAULT_FOOTER)


def _strip_layout_emoji_prefix(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    prefix = f"{Emoji.VAX} "
    if raw.startswith(prefix):
        return raw[len(prefix):]
    if raw.startswith(Emoji.VAX):
        return raw[len(Emoji.VAX):].lstrip()
    return raw


# ==============================================================================
# VUE PRINCIPALE DU PANELBOT (LAYOUT V2)
# ==============================================================================
class PanelBotLayoutView(ui.LayoutView):
    def __init__(
        self,
        bot: commands.Bot,
        guild: discord.Guild,
        user: discord.Member,
        default_section: str = "profil",
        bot_profile_user: discord.User | None = None,
    ):
        super().__init__(timeout=600)
        self.bot = bot
        self.guild = guild
        self.user = user
        self.current_section = default_section
        self.message: discord.Message | None = None
        self.bot_profile_user: discord.User | None = bot_profile_user

        self.selected_presence_index: int | None = None

        self._build()

    async def refresh_view_message(self) -> None:
        self._build()
        if self.message:
            await self.message.edit(view=self)

    async def refresh_bot_profile_user(self) -> None:
        bot_user = self.bot.user
        if not bot_user:
            return
        try:
            self.bot_profile_user = await self.bot.fetch_user(bot_user.id)
        except Exception:
            self.bot_profile_user = bot_user

    @staticmethod
    def _add_banner_gallery(container: ui.Container, image_url: str, description: str) -> None:
        try:
            gallery = ui.MediaGallery()
            gallery.add_item(media=image_url, description=description)
            container.add_item(gallery)
        except Exception:
            container.add_item(ui.TextDisplay(f"{Emoji.ATTENTION} Image indisponible: {description}"))

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

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                f"{Emoji.REFUSER} Ce menu interactif ne vous appartient pas.",
                ephemeral=True,
            )
            return False
        return True

    def _build(self):
        self.clear_items()

        if self.current_section == "theme":
            # La vue Theme manipule explicitement les valeurs globales panelbot.
            theme_defaults = _get_global_theme_defaults()
            accent_color = int(theme_defaults.get("color", config_manager.DEFAULT_COLOR))
            footer_template = str(theme_defaults.get("footer", config_manager.DEFAULT_FOOTER))
            footer_resolved = config_manager.format_footer_text(
                footer_template,
                self.guild,
                self.user,
                self.bot,
                for_layout=True,
            )
        else:
            # Profil et Presence suivent le theme resolu du serveur (avec fallback interne).
            server_theme = config_manager.get_layout_v2_theme(
                self.guild.id,
                self.guild,
                self.user,
                self.bot,
                force_global=False,
            )
            accent_color = int(server_theme.get("color", config_manager.DEFAULT_COLOR))
            footer_resolved = str(server_theme.get("footer_text", "") or "")

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)

        container.add_item(ui.TextDisplay("# ⚙️ Panneau de configuration"))
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

        top_row = ui.ActionRow()

        sync_btn = ui.Button(label="Synchroniser", style=discord.ButtonStyle.success, emoji=Emoji.VALIDER)
        sync_btn.callback = self._action_sync_commands
        top_row.add_item(sync_btn)

        btn_prefix = ui.Button(label="Prefix", style=discord.ButtonStyle.primary, emoji=Emoji.MODIFIER)
        btn_prefix.callback = lambda i: i.response.send_modal(BotAvanceSingleEditModal(self, "prefix"))
        top_row.add_item(btn_prefix)

        btn_version = ui.Button(label="Version", style=discord.ButtonStyle.primary, emoji=Emoji.MODIFIER)
        btn_version.callback = lambda i: i.response.send_modal(BotAvanceSingleEditModal(self, "version"))
        top_row.add_item(btn_version)

        container.add_item(top_row)
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

        select_row = ui.ActionRow()
        nav_select = ui.Select(
            placeholder=f"{Emoji.RECHERCHE} Sélectionnez une section...",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label="Profil",
                    value="profil",
                    description="Identité du bot",
                    emoji=Emoji.PROFIL,
                    default=(self.current_section == "profil"),
                ),
                discord.SelectOption(
                    label="Présence",
                    value="presence",
                    description="Statuts et textes d'activité",
                    emoji="📝",
                    default=(self.current_section == "presence"),
                ),
                discord.SelectOption(
                    label="Thème",
                    value="theme",
                    description="Couleur et footer",
                    emoji="🎨",
                    default=(self.current_section == "theme"),
                ),
            ],
            custom_id="panelbot_nav_select",
        )
        nav_select.callback = self._on_section_select
        select_row.add_item(nav_select)
        container.add_item(select_row)
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

        if self.current_section == "profil":
            self._render_profil_section(container)
        elif self.current_section == "presence":
            self._render_presence_section(container)
        elif self.current_section == "theme":
            self._render_theme_section(container, footer_resolved)

        if footer_resolved:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_resolved))

        self.add_item(container)

    # --------------------------------------------------------------------------
    # SECTIONS DU PANEL
    # --------------------------------------------------------------------------
    def _render_profil_section(self, container: ui.Container):
        bot_user = self.bot.user
        bot_name = bot_user.name if bot_user else "Inconnu"
        avatar_url = bot_user.display_avatar.url if bot_user else ""

        banner_url = None
        if self.bot_profile_user and self.bot_profile_user.banner:
            banner_url = self.bot_profile_user.banner.url
        elif bot_user and bot_user.banner:
            banner_url = bot_user.banner.url

        container.add_item(ui.TextDisplay(f"## {Emoji.PROFIL} Profil {bot_name}"))
        profil_text = (
            f"- **Nom du Bot** : `{bot_name}`\n"
            f"- **Identifiant** : `{bot_user.id if bot_user else 'Inconnu'}`"
        )
        if avatar_url:
            self._add_thumbnail_section(container, profil_text, avatar_url, f"Avatar de {bot_name}")
        else:
            container.add_item(ui.TextDisplay(profil_text))

        if banner_url:
            self._add_banner_gallery(container, banner_url, f"Bannière de {bot_name}")

        status = _get_bot_settings().get("status", "online")
        status_row = ui.ActionRow()
        status_select = ui.Select(
            placeholder="Sélectionner le statut visuel du bot...",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label="En ligne", value="online", emoji="🟢", default=(status == "online")),
                discord.SelectOption(label="Absent", value="idle", emoji="🌙", default=(status == "idle")),
                discord.SelectOption(label="Ne pas déranger", value="dnd", emoji="🔴", default=(status == "dnd")),
                discord.SelectOption(label="Invisible", value="invisible", emoji="⚫", default=(status == "invisible")),
            ],
            custom_id="panelbot_status_select",
        )
        status_select.callback = self._on_status_select
        status_row.add_item(status_select)
        container.add_item(status_row)

        row = ui.ActionRow()
        btn_name = ui.Button(label="Nom", style=discord.ButtonStyle.primary, emoji=Emoji.MODIFIER)
        btn_name.callback = lambda i: i.response.send_modal(BotProfileSingleEditModal(self, "username"))
        row.add_item(btn_name)

        btn_avatar = ui.Button(label="Avatar", style=discord.ButtonStyle.primary, emoji=Emoji.IMAGE)
        btn_avatar.callback = lambda i: i.response.send_message(view=ImageChoiceView(self, "avatar"), ephemeral=True)
        row.add_item(btn_avatar)

        btn_banner = ui.Button(label="Bannière", style=discord.ButtonStyle.primary, emoji=Emoji.IMAGE)
        btn_banner.callback = lambda i: i.response.send_message(view=ImageChoiceView(self, "banner"), ephemeral=True)
        row.add_item(btn_banner)

        container.add_item(row)

    def _render_presence_section(self, container: ui.Container):
        presences = _get_presences()

        container.add_item(ui.TextDisplay("## 📝 Configuration des Présences"))
        top_action_row = ui.ActionRow()

        add_btn = ui.Button(label="Ajouter", style=discord.ButtonStyle.success, emoji=Emoji.AJOUTER)
        add_btn.callback = self._action_presence_add
        top_action_row.add_item(add_btn)

        balise_btn = ui.Button(label="Balises", style=discord.ButtonStyle.secondary, emoji=Emoji.LAMPE)
        balise_btn.callback = self._action_open_balises_ephemeral
        top_action_row.add_item(balise_btn)

        container.add_item(top_action_row)
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

        if not presences:
            container.add_item(ui.TextDisplay("Aucune présence configurée."))
            return

        container.add_item(ui.TextDisplay("### Liste des présences"))
        for idx, pres in enumerate(presences, start=1):
            container.add_item(ui.TextDisplay(f"`{idx}.` {pres}"))

        self.selected_presence_index = self._clamp_presence_index(self.selected_presence_index, len(presences))

        options = []
        for idx, pres in enumerate(presences[:25]):
            short = pres if len(pres) <= 95 else f"{pres[:92]}..."
            options.append(
                discord.SelectOption(
                    label=f"Configuration {idx + 1}",
                    value=str(idx),
                    description=short,
                    default=(self.selected_presence_index == idx),
                )
            )

        select_row = ui.ActionRow()
        presence_select = ui.Select(
            placeholder="Choisir une configuration de présence...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="panelbot_presence_select",
        )
        presence_select.callback = self._on_presence_select
        select_row.add_item(presence_select)
        container.add_item(select_row)

        if self.selected_presence_index is not None:
            selected_text = presences[self.selected_presence_index]
            container.add_item(ui.TextDisplay(f"### Configuration sélectionnée\n{selected_text}"))

            action_row = ui.ActionRow()

            edit_btn = ui.Button(label="Modifier", style=discord.ButtonStyle.primary, emoji=Emoji.MODIFIER)
            edit_btn.callback = self._action_presence_edit
            action_row.add_item(edit_btn)

            delete_btn = ui.Button(label="Supprimer", style=discord.ButtonStyle.danger, emoji=Emoji.SUPPRIMER)
            delete_btn.callback = self._action_presence_delete
            action_row.add_item(delete_btn)

            cancel_btn = ui.Button(label="Annuler", style=discord.ButtonStyle.secondary)
            cancel_btn.callback = self._action_presence_cancel
            action_row.add_item(cancel_btn)

            container.add_item(action_row)

    def _render_theme_section(self, container: ui.Container, footer_resolved: str):
        default_vals = _get_global_theme_defaults()
        color_hex = f"0x{int(default_vals.get('color', DEFAULT_COLOR)):06x}"
        footer_brut = default_vals.get("footer", DEFAULT_FOOTER)

        container.add_item(ui.TextDisplay(f"## {Emoji.IMAGE} Configuration du Thème Global"))
        container.add_item(ui.TextDisplay(f"{Emoji.LIEN} Code hex couleur : [Clique-ici](https://htmlcolorcodes.com/fr/)"))
        container.add_item(ui.TextDisplay(
            f"- **Couleur d'accentuation globale** : `{color_hex}`\n"
            f"- **Footer brut par défaut** : `{footer_brut}`\n"
            f"- **Footer résolu** : `{_strip_layout_emoji_prefix(footer_resolved)}`"
        ))

        row = ui.ActionRow()
        edit_theme_btn = ui.Button(label="Éditer thème", style=discord.ButtonStyle.primary, emoji=Emoji.MODIFIER)
        edit_theme_btn.callback = self._action_edit_theme_modal
        row.add_item(edit_theme_btn)

        reset_theme_btn = ui.Button(label="Défaut", style=discord.ButtonStyle.danger, emoji=Emoji.SUPPRIMER)
        reset_theme_btn.callback = self._action_reset_theme
        row.add_item(reset_theme_btn)

        balise_btn = ui.Button(label="Balises", style=discord.ButtonStyle.secondary, emoji=Emoji.LAMPE)
        balise_btn.callback = self._action_open_balises_ephemeral
        row.add_item(balise_btn)

        container.add_item(row)

    @staticmethod
    def _clamp_presence_index(index: int | None, size: int) -> int | None:
        if size <= 0 or index is None:
            return None
        if index < 0:
            return 0
        if index >= size:
            return size - 1
        return index

    # --------------------------------------------------------------------------
    # CALLBACKS ET INTERACTIONS NAVIGATION
    # --------------------------------------------------------------------------
    async def _on_section_select(self, interaction: discord.Interaction):
        values = interaction.values if hasattr(interaction, "values") else interaction.data.get("values", [])
        if values:
            self.current_section = values[0]
            if self.current_section != "presence":
                self.selected_presence_index = None
            log_debug(f"Navigation panelbot vers : {self.current_section}")

            self._build()
            await interaction.response.edit_message(view=self)

    async def _on_status_select(self, interaction: discord.Interaction):
        values = interaction.values if hasattr(interaction, "values") else interaction.data.get("values", [])
        if values:
            new_status = values[0]
            _update_bot_setting("status", new_status)
            try:
                status_map = {
                    "online": discord.Status.online,
                    "idle": discord.Status.idle,
                    "dnd": discord.Status.dnd,
                    "invisible": discord.Status.invisible,
                }
                await interaction.client.change_presence(status=status_map.get(new_status, discord.Status.online))
            except Exception:
                pass
            log_success(f"Statut visuel mis à jour via sélecteur : {new_status}")
        self._build()
        await interaction.response.edit_message(view=self)

    async def _on_presence_select(self, interaction: discord.Interaction):
        values = interaction.values if hasattr(interaction, "values") else interaction.data.get("values", [])
        if values:
            try:
                self.selected_presence_index = int(values[0])
            except Exception:
                self.selected_presence_index = None
        self._build()
        await interaction.response.edit_message(view=self)

    async def _action_sync_commands(self, interaction: discord.Interaction):
        try:
            synced = await interaction.client.tree.sync()
            log_success(f"Synchronisation réussie ({len(synced)} commandes).")
            if not interaction.response.is_done():
                await interaction.response.defer()
        except Exception as e:
            log_error(f"Erreur de synchronisation : {e}")
            if interaction.response.is_done():
                await interaction.followup.send(f"{Emoji.REFUSER} Erreur de synchronisation : {e}", ephemeral=True)
            else:
                await interaction.response.send_message(f"{Emoji.REFUSER} Erreur de synchronisation : {e}", ephemeral=True)

    async def _action_edit_theme_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ThemeDefaultEditModal(self))

    async def _action_reset_theme(self, interaction: discord.Interaction):
        _reset_global_theme_defaults()
        log_success("Réinitialisation du thème global par défaut.")
        self._build()
        await interaction.response.edit_message(view=self)

    async def _action_open_balises_ephemeral(self, interaction: discord.Interaction):
        view = BaliseCatalogLayoutView(self.guild, self.user, self.bot)
        await interaction.response.send_message(view=view, ephemeral=True)

    async def _action_presence_add(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PresenceItemModal(self, mode="add"))

    async def _action_presence_edit(self, interaction: discord.Interaction):
        presences = _get_presences()
        idx = self._clamp_presence_index(self.selected_presence_index, len(presences))
        if idx is None:
            return await interaction.response.send_message(f"{Emoji.ATTENTION} Aucune présence sélectionnée.", ephemeral=True)
        await interaction.response.send_modal(PresenceItemModal(self, mode="edit", index=idx, initial_value=presences[idx]))

    async def _action_presence_delete(self, interaction: discord.Interaction):
        presences = _get_presences()
        idx = self._clamp_presence_index(self.selected_presence_index, len(presences))
        if idx is None:
            return await interaction.response.send_message(f"{Emoji.ATTENTION} Aucune présence sélectionnée.", ephemeral=True)

        del presences[idx]
        _save_presences(presences)
        self.selected_presence_index = self._clamp_presence_index(idx, len(presences))
        self._build()
        await interaction.response.edit_message(view=self)

    async def _action_presence_cancel(self, interaction: discord.Interaction):
        self.selected_presence_index = None
        self._build()
        await interaction.response.edit_message(view=self)


# ==============================================================================
# VUE DE CHOIX DE TYPE D'IMAGE (URL vs UPLOAD)
# ==============================================================================
class ImageChoiceView(ui.View):
    def __init__(self, view: PanelBotLayoutView, field_type: str):
        super().__init__(timeout=180)
        self.parent_view = view
        self.field_type = field_type

    @ui.button(label="Via URL", style=discord.ButtonStyle.primary, emoji=Emoji.LIEN)
    async def via_url(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(BotProfileImageModal(self.parent_view, self.field_type))

    @ui.button(label="Via Image", style=discord.ButtonStyle.secondary, emoji=Emoji.IMAGE)
    async def via_image(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message(
            f"{Emoji.ATTENTION} **Configuration par image** : L'image que vous enverrez dans ce salon au cours des "
            f"**10 prochaines minutes** sera enregistrée comme nouvel/nouvelle {self.field_type} du bot.",
            ephemeral=True,
        )

        def check(m: discord.Message):
            return m.author.id == self.parent_view.user.id and m.channel.id == interaction.channel.id and len(m.attachments) > 0

        try:
            msg = await self.parent_view.bot.wait_for("message", check=check, timeout=600.0)
            attachment = msg.attachments[0]
            img_bytes = await attachment.read()

            await interaction.client.user.edit(**{self.field_type: img_bytes})
            await self.parent_view.refresh_bot_profile_user()
            log_success(f"Profil mis à jour via upload conversation ({self.field_type}).")
            try:
                await self.parent_view.refresh_view_message()
            except Exception as refresh_error:
                log_error(f"Impossible de rafraîchir le panel après upload image: {refresh_error}")
            try:
                await msg.delete()
            except Exception:
                pass
        except asyncio.TimeoutError:
            await interaction.followup.send(f"{Emoji.REFUSER} Délai d'attente dépassé (10 minutes). Aucune image n'a été reçue.", ephemeral=True)
        except Exception as e:
            log_error(f"Erreur import image profil : {e}")
            await interaction.followup.send(f"{Emoji.REFUSER} Erreur lors de l'application de l'image : {e}", ephemeral=True)


# ==============================================================================
# MODALES DE CONFIGURATION
# ==============================================================================
class BotProfileSingleEditModal(ui.Modal):
    def __init__(self, view: PanelBotLayoutView, field_type: str):
        super().__init__(title="Modifier le Nom du Bot")
        self.view = view
        self.field_type = field_type
        bot_user = view.bot.user

        self.input_field = ui.TextInput(
            label="Nom du Bot",
            default=bot_user.name if bot_user else "𝑉𝑎𝑥",
            max_length=32,
            required=True,
        )
        self.add_item(self.input_field)

    async def on_submit(self, interaction: discord.Interaction):
        val = self.input_field.value.strip()
        try:
            await interaction.client.user.edit(username=val)
            await self.view.refresh_bot_profile_user()
            log_success("Nom du bot mis à jour avec succès.")
            await interaction.response.defer()
            await self.view.refresh_view_message()
        except Exception as e:
            log_error(f"Erreur modification nom : {e}")
            err = str(e).lower()
            if "application is verified" in err or "verified" in err:
                await interaction.response.send_message(
                    f"{Emoji.REFUSER} Le bot étant vérifié, vous ne pouvez pas le renommer.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(f"{Emoji.REFUSER} Impossible de renommer le bot.", ephemeral=True)


class BotProfileImageModal(ui.Modal):
    def __init__(self, view: PanelBotLayoutView, field_type: str):
        super().__init__(title=f"Modifier {'l\'Avatar' if field_type == 'avatar' else 'la Bannière'} (URL)")
        self.view = view
        self.field_type = field_type

        self.url_input = ui.TextInput(
            label="URL directe de l'image",
            placeholder="https://...",
            required=True,
        )
        self.add_item(self.url_input)

    async def on_submit(self, interaction: discord.Interaction):
        url_val = self.url_input.value.strip()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url_val) as resp:
                    if resp.status == 200:
                        img_bytes = await resp.read()
                        kwargs = {self.field_type: img_bytes}
                        await interaction.client.user.edit(**kwargs)
                        await self.view.refresh_bot_profile_user()
                        log_success(f"Profil mis à jour via URL ({self.field_type}).")
                        await interaction.response.defer()
                        await self.view.refresh_view_message()
                    else:
                        await interaction.response.send_message(f"{Emoji.REFUSER} Impossible de récupérer l'image (Code HTTP {resp.status}).", ephemeral=True)
        except Exception as e:
            log_error(f"Erreur téléchargement image URL : {e}")
            await interaction.response.send_message(f"{Emoji.REFUSER} Erreur lors du téléchargement : {e}", ephemeral=True)


class BotAvanceSingleEditModal(ui.Modal):
    def __init__(self, view: PanelBotLayoutView, target_field: str):
        super().__init__(title=f"Modifier {target_field.capitalize()}")
        self.view = view
        self.target_field = target_field
        settings = _get_bot_settings()

        current_val = settings.get(target_field, "²" if target_field == "prefix" else "v1.0")
        self.input_field = ui.TextInput(
            label=f"Valeur {target_field}",
            default=current_val,
            max_length=15,
            required=True,
        )
        self.add_item(self.input_field)

    async def on_submit(self, interaction: discord.Interaction):
        val = self.input_field.value.strip()
        _update_bot_setting(self.target_field, val)

        log_success(f"Paramètre avancé mis à jour ({self.target_field}) : {val}")
        await interaction.response.defer()
        await self.view.refresh_view_message()


class PresenceItemModal(ui.Modal):
    def __init__(self, view: PanelBotLayoutView, mode: str, index: int | None = None, initial_value: str = ""):
        self.view = view
        self.mode = mode
        self.index = index

        title = "Ajouter une présence" if mode == "add" else "Modifier la présence"
        super().__init__(title=title)

        self.presence_input = ui.TextInput(
            label="Texte de présence",
            default=initial_value,
            style=discord.TextStyle.long,
            max_length=200,
            required=True,
            placeholder="Ex: ⚡{name} {version} - {ping} ms",
        )
        self.add_item(self.presence_input)

    async def on_submit(self, interaction: discord.Interaction):
        value = self.presence_input.value.strip()
        presences = _get_presences()

        if self.mode == "add":
            presences.append(value)
            self.view.selected_presence_index = len(presences) - 1
        elif self.mode == "edit":
            if self.index is None or self.index < 0 or self.index >= len(presences):
                return await interaction.response.send_message(f"{Emoji.REFUSER} Présence introuvable.", ephemeral=True)
            presences[self.index] = value
            self.view.selected_presence_index = self.index

        _save_presences(presences)
        await interaction.response.defer()
        await self.view.refresh_view_message()


class ThemeDefaultEditModal(ui.Modal):
    def __init__(self, view: PanelBotLayoutView):
        super().__init__(title="Édition du Thème Global")
        self.view = view
        current_vals = _get_global_theme_defaults()

        self.color_input = ui.TextInput(
            label="Code Couleur (Hex)",
            default=f"#{int(current_vals.get('color', DEFAULT_COLOR)):06x}",
            min_length=6,
            max_length=7,
            required=False,
        )
        self.footer_input = ui.TextInput(
            label="Texte du Footer global",
            default=current_vals.get("footer", DEFAULT_FOOTER),
            style=discord.TextStyle.long,
            max_length=80,
            required=False,
        )
        self.add_item(self.color_input)
        self.add_item(self.footer_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw_color = self.color_input.value.strip().lstrip("#")
        try:
            new_color = int(raw_color, 16) if raw_color else DEFAULT_COLOR
        except ValueError:
            return await interaction.response.send_message(f"{Emoji.REFUSER} Code couleur hexadécimal invalide.", ephemeral=True)

        footer_text = self.footer_input.value.strip()
        _save_global_theme_defaults(new_color, footer_text or DEFAULT_FOOTER)

        log_success("Thème global mis à jour.")
        await interaction.response.defer()
        await self.view.refresh_view_message()


# ==============================================================================
# COG PRINCIPAL PANELBOT
# ==============================================================================
class PanelBot(commands.Cog):
    """Cog principal intégrant le centre de contrôle layout du bot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log_success("Cog PanelBot initialisé avec succès.")

    @commands.command(name="panelbot", description="Ouvre le centre de contrôle global du bot")
    async def panelbot(self, ctx: commands.Context):
        if not ctx.guild:
            return await ctx.send(f"{Emoji.REFUSER} Cette commande doit être exécutée sur un serveur.")

        member = ctx.author if isinstance(ctx.author, discord.Member) else ctx.guild.get_member(ctx.author.id)
        if not member:
            return await ctx.send(f"{Emoji.REFUSER} Impossible de valider vos permissions.")

        log_debug(f"Ouverture du panneau de contrôle par {ctx.author} sur {ctx.guild.name}")
        try:
            bot_profile_user = None
            if self.bot.user:
                try:
                    bot_profile_user = await self.bot.fetch_user(self.bot.user.id)
                except Exception:
                    bot_profile_user = self.bot.user

            view = PanelBotLayoutView(self.bot, ctx.guild, member, default_section="profil", bot_profile_user=bot_profile_user)
            message = await ctx.send(view=view)
            view.message = message
        except Exception as e:
            log_error(f"Echec affichage panelbot: {e}")
            log_error(traceback.format_exc())
            await ctx.send(f"{Emoji.REFUSER} Impossible d'afficher le panel pour le moment: `{e}`")

    async def cog_command_error(self, ctx: commands.Context, error: Exception):
        if ctx.command and ctx.command.name == "panelbot":
            log_error(f"Erreur commande {ctx.command.name}: {error}")
            log_error(traceback.format_exc())
            try:
                await ctx.send(f"{Emoji.REFUSER} Erreur sur la commande `{ctx.command.name}`: `{error}`")
            except Exception:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(PanelBot(bot))
