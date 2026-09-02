"""
MODULE CONFESSIONS V3 - Système de confessions anonymes et interactives
=====================================================================
Refonte complète aux standards Vax v3 : LayoutV2, gestion dynamique par salon,
signalements centralisés uniques, persistance fichier par confession et robustesse des interactions.
"""

from __future__ import annotations

import os
import traceback
from typing import Any

import discord
from discord import ui
from discord.ext import commands

from utils.config_data import DataManager
from utils.config_perm import ensure_command_permission, perm_command
from utils.config_theme import config_manager
from utils.config_emoji import Emoji as E

# ==============================================================================
# ----------------------- CONFIGURATION & LOGS GLOBALES ------------------------
# ==============================================================================

DEBUG_LOGS = True
ERROR_LOGS_ONLY = False

# Centralisation globale des Emojis (Utilisation des customs Vax v3)
E_CONFESS = getattr(E, "COEUR", "💌")
E_SUCCESS = getattr(E, "VALIDER", "✅")
E_ERROR = getattr(E, "ERREUR", getattr(E, "REFUSER", "❌"))
E_GEAR = getattr(E, "MODIFIER", "⚙️")
E_CHAN = getattr(E, "LIEN", "📍")
E_ADD = getattr(E, "AJOUTER", getattr(E, "CREATE", "➕"))
E_PUB = getattr(E, "MONDE", "🗣️")
E_ANON = getattr(E, "ROLE", "🕵️")
E_REFRESH = getattr(E, "RAFRAICHIR", "🔄")
E_ID = getattr(E, "IDENTIFIANT", "🆔")
E_REPLY = getattr(E, "MEMO", getattr(E, "TEXT", "💬"))
E_REPORT = getattr(E, "ATTENTION", getattr(E, "WARNING", "🚨"))


def log_debug(msg: str, is_error: bool = False):
    """Système de log conditionné avec formatage couleur console (Vax v3)."""
    if not DEBUG_LOGS and not is_error:
        return
    if ERROR_LOGS_ONLY and not is_error:
        return

    color = "\033[91m" if is_error else "\033[94m"
    if "✅" in msg or E_SUCCESS in msg:
        color = "\033[92m"

    prefix = "[ERREUR]" if is_error else "[INFO]"
    reset = "\033[0m"
    print(f"{color}{prefix} Vax v3 (Confessions) - {msg}{reset}")


# Initialisation des gestionnaires de données du projet Vax
conf_db = DataManager("staff/configuration/data_confession/config")

SALON_NOM_CIBLE = "💌│𝑪𝒐𝒏𝒇𝒆𝒔𝒔𝒊𝒐𝒏𝒔"
TARGET_REPORT_GUILD_ID = 1368235294192570520
TARGET_REPORT_CHANNEL_ID = 1533468437765161123

# ==============================================================================
# ------------------------- GESTION DATA PAR CONFIG ----------------------------
# ==============================================================================


def get_confession_db(guild_id: int) -> DataManager:
    """Renvoie un DataManager ciblant le dossier requis data/staff/configuration/data_confession/<guild_id>."""
    return DataManager(f"staff/configuration/data_confession/{guild_id}")


# ==============================================================================
# ------------------------------ UI COMPONENTS ---------------------------------
# ==============================================================================


def build_confession_view(
    bot: commands.Bot, guild_id: int, count: int, reports_count: int = 0, is_active: bool = True
) -> ui.LayoutView:
    """Génère la vue LayoutV2 d'une confession principale avec le sélecteur d'actions et le bouton 'Se confesser'."""
    theme = config_manager.get_resolved_values(guild_id)
    accent_color = int(theme.get("color", 0x5865F2))

    view = ui.LayoutView(timeout=None)
    container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)

    db = get_confession_db(guild_id)
    conf_data = db.load(count) or {}
    confession_content = conf_data.get("content", "Contenu introuvable.")

    section_top = ui.Section(
        ui.TextDisplay(f"# {E_CONFESS} Confession #{count}"),
        ui.TextDisplay(confession_content),
        accessory=ui.Button(
            label=f"Signaler : {reports_count}",
            style=discord.ButtonStyle.danger,
            emoji=E_REPORT,
            custom_id=f"conf_report_btn_{count}",
        ),
    )
    container.add_item(section_top)
    container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

    action_select = ui.Select(
        placeholder="Choisir une action de réponse...",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(
                label="Réponse publique", value=f"conf_pub_{count}", emoji=E_PUB, description="Répondre de manière visible"
            ),
            discord.SelectOption(
                label="Réponse anonyme", value=f"conf_anon_{count}", emoji=E_ANON, description="Répondre de façon masquée"
            ),
        ],
        disabled=not is_active,
    )
    action_select.callback = _on_confession_action_select_static

    select_row = ui.ActionRow()
    select_row.add_item(action_select)
    container.add_item(select_row)

    confess_btn_row = ui.ActionRow()
    confess_btn = ui.Button(
        label="Se confesser",
        style=discord.ButtonStyle.primary,
        emoji=E_ADD,
        custom_id="trigger_confess_modal",
        disabled=not is_active,
    )
    confess_btn_row.add_item(confess_btn)
    container.add_item(confess_btn_row)

    footer_text = config_manager.format_footer_text(theme.get("footer", ""), None, None, bot, for_layout=True)
    if footer_text:
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
        container.add_item(ui.TextDisplay(footer_text))

    view.add_item(container)
    return view


def build_reply_public_view(
    bot: commands.Bot, guild_id: int, count: int, reports_count: int = 0, is_active: bool = True
) -> ui.LayoutView:
    """Génère la vue LayoutV2 distincte pour les réponses publiques (avec sélecteur de réponse, sans signalement en haut)."""
    theme = config_manager.get_resolved_values(guild_id)
    accent_color = int(theme.get("color", 0x5865F2))

    view = ui.LayoutView(timeout=None)
    container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)

    container.add_item(ui.TextDisplay(f"# {E_REPLY} Réponse publique"))
    container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

    action_select = ui.Select(
        placeholder="Choisir une action de réponse...",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(
                label="Réponse publique", value=f"conf_pub_{count}", emoji=E_PUB, description="Répondre de manière visible"
            ),
            discord.SelectOption(
                label="Réponse anonyme", value=f"conf_anon_{count}", emoji=E_ANON, description="Répondre de façon masquée"
            ),
        ],
        disabled=not is_active,
    )
    action_select.callback = _on_confession_action_select_static

    select_row = ui.ActionRow()
    select_row.add_item(action_select)
    container.add_item(select_row)

    footer_text = config_manager.format_footer_text(theme.get("footer", ""), None, None, bot, for_layout=True)
    if footer_text:
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
        container.add_item(ui.TextDisplay(footer_text))

    view.add_item(container)
    return view


def build_reply_anonymous_view(
    bot: commands.Bot, guild_id: int, count: int, reply_index: int, reports_count: int = 0, is_active: bool = True
) -> ui.LayoutView:
    """Génère la vue LayoutV2 distincte pour les réponses anonymes, avec un bouton de signalement unique en haut à droite."""
    theme = config_manager.get_resolved_values(guild_id)
    accent_color = int(theme.get("color", 0x5865F2))

    view = ui.LayoutView(timeout=None)
    container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)

    section_top = ui.Section(
        ui.TextDisplay(f"# {E_REPLY} Réponse anonyme"),
        ui.TextDisplay("Réagissez à ce message ci-dessous."),
        accessory=ui.Button(
            label=f"Signaler : {reports_count}",
            style=discord.ButtonStyle.danger,
            emoji=E_REPORT,
            custom_id=f"conf_report_reply_btn_{count}_{reply_index}",
        ),
    )
    container.add_item(section_top)
    container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

    action_select = ui.Select(
        placeholder="Choisir une action de réponse...",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(
                label="Réponse publique", value=f"conf_pub_{count}", emoji=E_PUB, description="Répondre de manière visible"
            ),
            discord.SelectOption(
                label="Réponse anonyme", value=f"conf_anon_{count}", emoji=E_ANON, description="Répondre de façon masquée"
            ),
        ],
        disabled=not is_active,
    )
    action_select.callback = _on_confession_action_select_static

    select_row = ui.ActionRow()
    select_row.add_item(action_select)
    container.add_item(select_row)

    footer_text = config_manager.format_footer_text(theme.get("footer", ""), None, None, bot, for_layout=True)
    if footer_text:
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
        container.add_item(ui.TextDisplay(footer_text))

    view.add_item(container)
    return view


async def _on_confession_action_select_static(interaction: discord.Interaction):
    """Callback global pour le sélecteur d'action de la confession."""
    try:
        values = interaction.data.get("values", [])
        if not values:
            return
        val = values[0]

        if val.startswith("conf_pub_") or val.startswith("conf_anon_"):
            is_anon = "conf_anon_" in val
            count = int(val.split("_")[-1])

            db = get_confession_db(interaction.guild.id)
            target_data = db.load(count)

            if not target_data:
                await interaction.response.send_message(f"{E_ERROR} Données introuvables.", ephemeral=True)
                return

            thread = interaction.guild.get_thread(target_data.get("thread_id"))
            if not thread:
                await interaction.response.send_message(f"{E_ERROR} Fil de discussion introuvable ou archivé.", ephemeral=True)
                return

            author_member = None
            if target_data and not is_anon:
                author_id = target_data.get("author_id")
                if author_id and str(author_id).isdigit():
                    author_member = interaction.guild.get_member(int(author_id))
                    if not author_member:
                        try:
                            author_member = await interaction.guild.fetch_member(int(author_id))
                        except Exception:
                            pass

            await interaction.response.send_modal(ReplyModal(interaction.client, thread, is_anon, count, author_member=author_member))
    except Exception as e:
        log_debug(f"Erreur dans _on_confession_action_select_static : {e}", is_error=True)
        if not interaction.response.is_done():
            await interaction.response.send_message(f"{E_ERROR} Une erreur est survenue.", ephemeral=True)


class ReplyModal(ui.Modal, title="Répondre à la confession"):
    content = ui.TextInput(label="Votre message", style=discord.TextStyle.paragraph, min_length=1)

    def __init__(self, bot: commands.Bot, thread: discord.Thread, is_anonymous: bool, count: int, author_member: discord.Member | None = None):
        super().__init__()
        self.bot = bot
        self.thread = thread
        self.is_anonymous = is_anonymous
        self.count = count
        self.author_member = author_member

    async def on_submit(self, interaction: discord.Interaction):
        try:
            title = "Réponse Anonyme" if self.is_anonymous else interaction.user.display_name
            description = self.content.value

            theme = config_manager.get_resolved_values(interaction.guild.id)
            accent_color = int(theme.get("color", 0x5865F2))

            db = get_confession_db(interaction.guild.id)
            conf_data = db.load(self.count) or {}

            view = ui.LayoutView(timeout=None)
            container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)

            if not self.is_anonymous and self.author_member:
                avatar_url = self.author_member.display_avatar.url
                section = ui.Section(
                    ui.TextDisplay(f"### {E_REPLY} {title}"),
                    ui.TextDisplay(description),
                    accessory=ui.Thumbnail(avatar_url, description=f"Avatar de {self.author_member.display_name}"),
                )
                container.add_item(section)
            else:
                reply_index = len(conf_data.get("anonymous_replies", []))
                reports_map = conf_data.get("reply_reports_count", {})
                rep_count = reports_map.get(str(reply_index), 0)

                section = ui.Section(
                    ui.TextDisplay(f"### {E_REPLY} {title}"),
                    ui.TextDisplay(description),
                    accessory=ui.Button(
                        label=f"Signaler : {rep_count}",
                        style=discord.ButtonStyle.danger,
                        emoji=E_REPORT,
                        custom_id=f"conf_report_reply_btn_{self.count}_{reply_index}",
                    ),
                )
                container.add_item(section)

            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

            action_select = ui.Select(
                placeholder="Choisir une action de réponse...",
                min_values=1,
                max_values=1,
                options=[
                    discord.SelectOption(
                        label="Réponse publique", value=f"conf_pub_{self.count}", emoji=E_PUB, description="Répondre de manière visible"
                    ),
                    discord.SelectOption(
                        label="Réponse anonyme", value=f"conf_anon_{self.count}", emoji=E_ANON, description="Répondre de façon masquée"
                    ),
                ],
            )
            action_select.callback = _on_confession_action_select_static

            select_row = ui.ActionRow()
            select_row.add_item(action_select)
            container.add_item(select_row)

            footer_text = config_manager.format_footer_text(theme.get("footer", ""), interaction.guild, interaction.user, self.bot, for_layout=True)
            if footer_text:
                container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
                container.add_item(ui.TextDisplay(footer_text))

            view.add_item(container)

            # Désactivation des interactions sur les messages précédents du fil
            async for old_msg in self.thread.history(limit=50):
                if old_msg.author == self.bot.user and old_msg.components:
                    try:
                        old_view = discord.ui.View.from_message(old_msg)
                        for comp in old_view.children:
                            if isinstance(comp, (discord.ui.Button, discord.ui.Select)) and getattr(comp, "custom_id", None) and not comp.custom_id.startswith("conf_report_btn_") and not comp.custom_id.startswith("conf_report_reply_btn_"):
                                comp.disabled = True
                        await old_msg.edit(view=old_view)
                    except Exception:
                        pass

            await self.thread.send(view=view)

            if self.is_anonymous:
                conf_data.setdefault("anonymous_replies", []).append({
                    "user_id": interaction.user.id,
                    "content": description,
                })
                db.save(self.count, conf_data)

            log_debug(f"Réponse postée dans le fil {self.thread.id} sur {interaction.guild.name}.")
            await interaction.response.send_message("Votre réponse a été envoyée avec succès dans le fil !", ephemeral=True)
        except Exception as e:
            err_trace = traceback.format_exc()
            log_debug(f"Échec de l'envoi de la réponse : {e}\n{err_trace}", is_error=True)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"{E_ERROR} Une erreur est survenue lors de l'envoi de votre réponse.", ephemeral=True)
            except Exception:
                pass


class ConfessModal(ui.Modal, title="Nouvelle confession"):
    content = ui.TextInput(label="Ta confession", style=discord.TextStyle.paragraph, min_length=5)

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        try:
            config = conf_db.load(interaction.guild.id) or {}
            channel_id = config.get("channel_id")
            channel = interaction.guild.get_channel(channel_id) if channel_id else None

            if not channel:
                log_debug(f"Salon introuvable ou système désactivé pour guild_id={interaction.guild.id}", is_error=True)
                await interaction.response.send_message(f"{E_ERROR} Salon introuvable ou système désactivé.", ephemeral=True)
                return

            config["counter"] = config.get("counter", 0) + 1
            count = config["counter"]
            conf_db.save(interaction.guild.id, config)

            description = self.content.value

            db = get_confession_db(interaction.guild.id)
            conf_payload = {
                "count": count,
                "author_id": interaction.user.id,
                "content": description,
                "anonymous_replies": [],
                "reports_count": 0,
                "reported_users": [],
                "reply_reported_users": {},
                "reply_reports_count": {},
            }
            db.save(count, conf_payload)

            view = build_confession_view(self.bot, interaction.guild.id, count, reports_count=0, is_active=True)

            msg = await channel.send(view=view)
            thread = await msg.create_thread(name=f"Discussion #{count}", auto_archive_duration=1440)

            conf_payload["thread_id"] = thread.id
            conf_payload["message_id"] = msg.id
            db.save(count, conf_payload)

            log_debug(f"Confession #{count} publiée sur {interaction.guild.name}.")

            try:
                await interaction.user.send(f"{E_SUCCESS} Votre confession a été postée avec succès dans {channel.mention} !")
            except Exception as dm_err:
                log_debug(f"Impossible d'envoyer le MP de confirmation : {dm_err}", is_error=True)

            await interaction.response.send_message("Votre confession a été publiée avec succès !", ephemeral=True)

        except Exception as e:
            err_trace = traceback.format_exc()
            log_debug(f"Erreur critique dans ConfessModal.on_submit : {e}\n{err_trace}", is_error=True)
            try:
                await interaction.user.send(f"{E_ERROR} Une erreur est survenue lors de la publication de votre confession.")
            except Exception:
                pass
            if not interaction.response.is_done():
                await interaction.response.send_message(f"{E_ERROR} Une erreur interne est survenue.", ephemeral=True)


# ==============================================================================
# --------------------------- LAYOUT V2 SETTINGS -------------------------------
# ==============================================================================

class ConfessChannelModal(ui.Modal, title="Associer un salon"):
    """Modal dédié à l'association de salon sans le '(ID Discord)'."""
    channel_id_input = ui.TextInput(
        label="Identifiant",
        placeholder="Ex: 123456789101112345",
        style=discord.TextStyle.short,
        required=True,
        max_length=25
    )

    def __init__(self, callback_coro):
        super().__init__()
        self.callback_coro = callback_coro

    async def on_submit(self, interaction: discord.Interaction):
        raw_id = self.channel_id_input.value.strip()
        if not raw_id.isdigit():
            return await interaction.response.send_message(f"{E_ERROR} L'ID fourni n'est pas un nombre valide.", ephemeral=True)
        
        target = interaction.guild.get_channel(int(raw_id))
        if not target:
            return await interaction.response.send_message(f"{E_ERROR} Salon introuvable sur ce serveur.", ephemeral=True)
            
        await interaction.response.defer()
        await self.callback_coro(interaction, target)


class ConfessionsConfigLayout(ui.LayoutView):
    def __init__(self, bot: commands.Bot, guild: discord.Guild, user: discord.Member):
        super().__init__(timeout=600)
        self.bot = bot
        self.guild = guild
        self.user = user
        self.config = conf_db.load(self.guild.id) or {"channel_id": None, "counter": 0}
        self.message: discord.Message | None = None
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(f"{E_ERROR} Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        return True

    def _build(self):
        self.clear_items()

        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.bot)
        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text") or ""

        channel_id = self.config.get("channel_id")
        chan_obj = self.guild.get_channel(channel_id) if channel_id else None

        is_enabled = chan_obj is not None
        
        # Sortir les émojis des backticks pour qu'ils soient rendus correctement en Markdown !
        status_salon = chan_obj.mention if is_enabled else f"{E_ERROR} `Aucun / Introuvable`"
        counter = self.config.get("counter", 0)

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {E_GEAR} Système de Confessions"))
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

        container.add_item(ui.TextDisplay(f"**État du système :** {E_SUCCESS} `ACTIVÉ`" if is_enabled else f"**État du système :** {E_ERROR} `DÉSACTIVÉ`"))
        container.add_item(ui.TextDisplay(f"**Salon cible :** {status_salon}"))
        container.add_item(ui.TextDisplay(f"**Confessions publiées :** `{counter}`"))

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
        container.add_item(ui.TextDisplay(f"## {E_CHAN} Gestion du Salon"))

        if is_enabled:
            options = [
                discord.SelectOption(label="Envoyer le panneau de confession", value="spawn_panel", emoji=E_CONFESS, description="Publier l'interface utilisateur"),
                discord.SelectOption(label="Retirer le salon & désactiver", value="remove_salon", emoji=getattr(E, "SUPPRIMER", "🗑️"), description="Désactiver le module"),
            ]
            chan_select = ui.Select(
                placeholder="Sélectionner une action de gestion...",
                min_values=1,
                max_values=1,
                options=options,
            )
            chan_select.callback = self._on_channel_action_select

            row_sel = ui.ActionRow()
            row_sel.add_item(chan_select)
            container.add_item(row_sel)
        else:
            container.add_item(ui.TextDisplay("Sélectionne un salon textuel existant :"))
            channel_select = ui.ChannelSelect(
                placeholder="Sélectionne un salon textuel...",
                min_values=1,
                max_values=1,
                channel_types=[discord.ChannelType.text],
            )
            channel_select.callback = self._on_channel_select
            row_chan = ui.ActionRow()
            row_chan.add_item(channel_select)
            container.add_item(row_chan)

            options = [
                discord.SelectOption(label="Lier par ID", value="set_id", emoji=E_ID, description="Associer un salon via son ID"),
                discord.SelectOption(label="Générer automatiquement", value="auto_create", emoji=E_ADD, description="Créer le salon de confessions optimisé"),
            ]
            chan_select = ui.Select(
                placeholder="Autres options de configuration...",
                min_values=1,
                max_values=1,
                options=options,
            )
            chan_select.callback = self._on_channel_action_select

            row_sel = ui.ActionRow()
            row_sel.add_item(chan_select)
            container.add_item(row_sel)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    async def _refresh(self, interaction: discord.Interaction):
        conf_db.save(self.guild.id, self.config)
        self._build()
        await interaction.response.edit_message(view=self)

    async def _refresh_silent(self):
        if self.message is not None:
            conf_db.save(self.guild.id, self.config)
            self._build()
            await self.message.edit(view=self)

    async def _on_channel_select(self, interaction: discord.Interaction):
        try:
            values = interaction.data.get("values", [])
            if not values:
                return
            channel_id = int(values[0])
            channel = interaction.guild.get_channel(channel_id)
            if not channel:
                return

            self.config["channel_id"] = channel.id
            conf_db.save(self.guild.id, self.config)
            self._build()
            await interaction.response.edit_message(view=self)
        except Exception as e:
            log_debug(f"Erreur dans _on_channel_select : {e}", is_error=True)

    async def _on_channel_action_select(self, interaction: discord.Interaction):
        try:
            values = interaction.data.get("values", [])
            if not values:
                return
            action = values[0]

            if action == "set_id":
                await interaction.response.send_modal(ConfessChannelModal(self._on_channel_id_submit))
            elif action == "auto_create":
                await self._auto_create_channel(interaction)
            elif action == "spawn_panel":
                await self._spawn_confess_panel(interaction)
            elif action == "remove_salon":
                await self._remove_salon(interaction)
        except Exception as e:
            log_debug(f"Erreur dans _on_channel_action_select : {e}", is_error=True)

    async def _on_channel_id_submit(self, interaction: discord.Interaction, target):
        try:
            channel = target if isinstance(target, discord.abc.GuildChannel) else None
            if channel is None:
                return

            self.config["channel_id"] = channel.id
            conf_db.save(self.guild.id, self.config)
            await self._refresh_silent()
        except Exception as e:
            log_debug(f"Erreur dans _on_channel_id_submit : {e}", is_error=True)

    async def _auto_create_channel(self, interaction: discord.Interaction):
        await interaction.response.defer()
        overwrites = {
            self.guild.default_role: discord.PermissionOverwrite(send_messages=False, read_messages=True, send_messages_in_threads=False),
            self.guild.me: discord.PermissionOverwrite(send_messages=True, manage_messages=True, manage_threads=True, create_public_threads=True),
        }

        try:
            new_chan = await self.guild.create_text_channel(SALON_NOM_CIBLE, overwrites=overwrites)
            self.config["channel_id"] = new_chan.id
            log_debug(f"Salon auto-généré : {new_chan.name} ({new_chan.id}).")
            await self._refresh_silent()
        except Exception as e:
            log_debug(f"Erreur création salon : {e}", is_error=True)

    async def _spawn_confess_panel(self, interaction: discord.Interaction):
        try:
            channel = self.guild.get_channel(self.config.get("channel_id"))
            if not channel:
                return

            theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.bot)
            accent_color = int(theme.get("color", discord.Color.blurple().value))

            panel_view = ui.LayoutView(timeout=None)
            panel_container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)

            section = ui.Section(
                ui.TextDisplay(f"## {E_CONFESS} Rédiger une confession"),
                ui.TextDisplay("L'anonymat est absolu. Utilise le bouton ci-dessous pour commencer."),
                accessory=ui.Button(label="Se confesser", style=discord.ButtonStyle.primary, emoji=E_ADD, custom_id="trigger_confess_modal"),
            )
            panel_container.add_item(section)

            footer_text = config_manager.format_footer_text(theme.get("footer", ""), self.guild, self.user, self.bot, for_layout=True)
            if footer_text:
                panel_container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
                panel_container.add_item(ui.TextDisplay(footer_text))

            panel_view.add_item(panel_container)

            await channel.send(view=panel_view)
            await interaction.response.send_message(f"{E_SUCCESS} Panneau opérationnel dans {channel.mention}.", ephemeral=False)
        except Exception as e:
            err_trace = traceback.format_exc()
            log_debug(f"Erreur envoi panneau de confession : {e}\n{err_trace}", is_error=True)

    async def _remove_salon(self, interaction: discord.Interaction):
        self.config["channel_id"] = None
        db = get_confession_db(interaction.guild.id)
        db.delete_all() if hasattr(db, "delete_all") else None
        log_debug(f"Gestion du salon retirée et système désactivé pour {self.guild.name}.")
        await self._refresh(interaction)


# ==============================================================================
# ------------------------------ COG PRINCIPAL ---------------------------------
# ==============================================================================


class Confessions(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log_debug("Module Confessions Vax v3 initialisé avec succès.")

    @perm_command(level=2)
    @commands.command(name="confess", aliases=["confes", "confession", "confessions"], description="Configurer et gérer le système de confessions anonymes")
    async def confess(self, ctx: commands.Context):
        if not ctx.guild:
            return await ctx.send(f"{E_ERROR} Cette commande doit être utilisée sur un serveur.")

        if not await ensure_command_permission(ctx, command_name="confess"):
            return

        log_debug(f"Interface Confessions ouverte par {ctx.author} sur {ctx.guild.name}.")
        view = ConfessionsConfigLayout(self.bot, ctx.guild, ctx.author)
        message = await ctx.send(view=view)
        view.message = message

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        try:
            if not interaction.data:
                return

            custom_id = interaction.data.get("custom_id")

            # Gestion du signalement de confession principale
            if custom_id and custom_id.startswith("conf_report_btn_"):
                await interaction.response.defer(ephemeral=True)

                count = int(custom_id.split("_")[-1])
                db = get_confession_db(interaction.guild.id)
                target_data = db.load(count)

                if not target_data:
                    return await interaction.followup.send(f"{E_ERROR} Données introuvables.", ephemeral=True)

                reported_users = target_data.setdefault("reported_users", [])
                if interaction.user.id in reported_users:
                    return await interaction.followup.send(f"{E_ERROR} Vous avez déjà signalé cette confession.", ephemeral=True)

                reported_users.append(interaction.user.id)

                author_id = target_data.get("author_id", "Inconnu")
                content = target_data.get("content", "Contenu non disponible")

                author_member = interaction.guild.get_member(int(author_id)) if str(author_id).isdigit() else None
                if not author_member and str(author_id).isdigit():
                    try:
                        author_member = await interaction.guild.fetch_member(int(author_id))
                    except Exception:
                        pass

                author_display = author_member.display_name if author_member else f"Utilisateur {author_id}"

                total_reports = target_data.get("reports_count", 0) + 1
                target_data["reports_count"] = total_reports
                db.save(count, target_data)

                try:
                    message = interaction.message
                    if message:
                        new_view = build_confession_view(self.bot, interaction.guild.id, count, total_reports, is_active=True)
                        await message.edit(view=new_view)
                except Exception as exc:
                    log_debug(f"Erreur mise à jour visuelle du bouton signaler : {exc}", is_error=True)

                target_guild = self.bot.get_guild(TARGET_REPORT_GUILD_ID)
                if not target_guild:
                    try:
                        target_guild = await self.bot.fetch_guild(TARGET_REPORT_GUILD_ID)
                    except Exception:
                        pass

                if target_guild:
                    report_channel = target_guild.get_channel(TARGET_REPORT_CHANNEL_ID)
                    if not report_channel:
                        try:
                            report_channel = await target_guild.fetch_channel(TARGET_REPORT_CHANNEL_ID)
                        except Exception:
                            pass

                    if report_channel:
                        theme = config_manager.get_resolved_values(interaction.guild.id)
                        accent_color = int(theme.get("color", 0x5865F2))

                        report_view = ui.LayoutView(timeout=None)
                        rep_container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
                        rep_container.add_item(ui.TextDisplay(f"# {E_REPORT} Confession"))
                        rep_container.add_item(
                            ui.TextDisplay(
                                f"- **Serveur de provenance :** `{interaction.guild.name}` (`{interaction.guild.id}`)\n"
                                f"- **Auteur du signalement :** `{interaction.user.display_name}` (`{interaction.user.id}`)\n"
                                f"- **Auteur de la confession :** `{author_display}` (`{author_id}`)\n"
                                f"- **Nombre total de signalements :** `{total_reports}`"
                            )
                        )
                        rep_container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
                        rep_container.add_item(ui.TextDisplay(f"**Contenu n°{count} signalé :**\n> {content}"))

                        footer_text = config_manager.format_footer_text(
                            theme.get("footer", ""), interaction.guild, interaction.user, self.bot, for_layout=True
                        )
                        if footer_text:
                            rep_container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
                            rep_container.add_item(ui.TextDisplay(footer_text))

                        report_view.add_item(rep_container)

                        try:
                            await report_channel.send(view=report_view)
                        except Exception as e:
                            log_debug(f"Erreur envoi rapport de signalement : {e}", is_error=True)

                try:
                    await interaction.user.send(
                        f"{E_SUCCESS} Votre signalement a bien été pris en compte.\n"
                        "Maintenant, seul un administrateur de votre serveur peut faire la demande auprès du serveur support "
                        "pour demander l'identité de l'éditeur du message pour pouvoir le signaler.\n"
                        "Attention : l'identité est dévoilée seulement si le motif est précisé dans le règlement du serveur."
                    )
                except Exception as dm_err:
                    log_debug(f"Impossible d'envoyer le MP de signalement : {dm_err}", is_error=True)

                return

            # Gestion du signalement de réponse anonyme
            if custom_id and custom_id.startswith("conf_report_reply_btn_"):
                await interaction.response.defer(ephemeral=True)

                parts = custom_id.split("_")
                count = int(parts[4])
                reply_index = int(parts[5])

                db = get_confession_db(interaction.guild.id)
                target_data = db.load(count)

                if not target_data:
                    return await interaction.followup.send(f"{E_ERROR} Données introuvables.", ephemeral=True)

                replies = target_data.get("anonymous_replies", [])
                if reply_index >= len(replies):
                    return await interaction.followup.send(f"{E_ERROR} Réponse introuvable.", ephemeral=True)

                reply_obj = replies[reply_index]
                reply_reported_users_map = target_data.setdefault("reply_reported_users", {})
                user_list_for_reply = reply_reported_users_map.setdefault(str(reply_index), [])

                if interaction.user.id in user_list_for_reply:
                    return await interaction.followup.send(f"{E_ERROR} Vous avez déjà signalé cette réponse anonyme.", ephemeral=True)

                user_list_for_reply.append(interaction.user.id)

                reply_author_id = reply_obj.get("user_id", "Inconnu")
                reply_content = reply_obj.get("content", "Contenu non disponible")

                reply_author_member = interaction.guild.get_member(int(reply_author_id)) if str(reply_author_id).isdigit() else None
                if not reply_author_member and str(reply_author_id).isdigit():
                    try:
                        reply_author_member = await interaction.guild.fetch_member(int(reply_author_id))
                    except Exception:
                        pass

                reply_author_display = reply_author_member.display_name if reply_author_member else f"Utilisateur {reply_author_id}"

                reply_reports_count_map = target_data.setdefault("reply_reports_count", {})
                total_reply_reports = reply_reports_count_map.get(str(reply_index), 0) + 1
                reply_reports_count_map[str(reply_index)] = total_reply_reports
                db.save(count, target_data)

                try:
                    message = interaction.message
                    if message:
                        theme = config_manager.get_resolved_values(interaction.guild.id)
                        accent_color = int(theme.get("color", 0x5865F2))

                        new_view = ui.LayoutView(timeout=None)
                        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)

                        section_top = ui.Section(
                            ui.TextDisplay(f"# {E_REPLY} Réponse anonyme"),
                            ui.TextDisplay(reply_content),
                            accessory=ui.Button(
                                label=f"Signaler : {total_reply_reports}",
                                style=discord.ButtonStyle.danger,
                                emoji=E_REPORT,
                                custom_id=f"conf_report_reply_btn_{count}_{reply_index}",
                            ),
                        )
                        container.add_item(section_top)
                        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

                        action_select = ui.Select(
                            placeholder="Choisir une action de réponse...",
                            min_values=1,
                            max_values=1,
                            options=[
                                discord.SelectOption(label="Réponse publique", value=f"conf_pub_{count}", emoji=E_PUB, description="Répondre de manière visible"),
                                discord.SelectOption(label="Réponse anonyme", value=f"conf_anon_{count}", emoji=E_ANON, description="Répondre de façon masquée"),
                            ],
                        )
                        action_select.callback = _on_confession_action_select_static
                        select_row = ui.ActionRow()
                        select_row.add_item(action_select)
                        container.add_item(select_row)

                        footer_text = config_manager.format_footer_text(theme.get("footer", ""), interaction.guild, interaction.user, self.bot, for_layout=True)
                        if footer_text:
                            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
                            container.add_item(ui.TextDisplay(footer_text))

                        new_view.add_item(container)
                        await message.edit(view=new_view)
                except Exception as exc:
                    log_debug(f"Erreur mise à jour visuelle du bouton signaler réponse : {exc}", is_error=True)

                target_guild = self.bot.get_guild(TARGET_REPORT_GUILD_ID)
                if not target_guild:
                    try:
                        target_guild = await self.bot.fetch_guild(TARGET_REPORT_GUILD_ID)
                    except Exception:
                        pass

                if target_guild:
                    report_channel = target_guild.get_channel(TARGET_REPORT_CHANNEL_ID)
                    if not report_channel:
                        try:
                            report_channel = await target_guild.fetch_channel(TARGET_REPORT_CHANNEL_ID)
                        except Exception:
                            pass

                    if report_channel:
                        theme = config_manager.get_resolved_values(interaction.guild.id)
                        accent_color = int(theme.get("color", 0x5865F2))

                        report_view = ui.LayoutView(timeout=None)
                        rep_container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
                        rep_container.add_item(ui.TextDisplay(f"# {E_REPORT} Réponse anonyme"))
                        rep_container.add_item(
                            ui.TextDisplay(
                                f"- **Serveur de provenance :** `{interaction.guild.name}` (`{interaction.guild.id}`)\n"
                                f"- **Auteur du signalement :** `{interaction.user.display_name}` (`{interaction.user.id}`)\n"
                                f"- **Auteur de la réponse :** `{reply_author_display}` (`{reply_author_id}`)\n"
                                f"- **Nombre total de signalements :** `{total_reply_reports}`"
                            )
                        )
                        rep_container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
                        rep_container.add_item(ui.TextDisplay(f"**Contenu de la réponse anonyme (Confession n°{count}) :**\n> {reply_content}"))

                        footer_text = config_manager.format_footer_text(
                            theme.get("footer", ""), interaction.guild, interaction.user, self.bot, for_layout=True
                        )
                        if footer_text:
                            rep_container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
                            rep_container.add_item(ui.TextDisplay(footer_text))

                        report_view.add_item(rep_container)

                        try:
                            await report_channel.send(view=report_view)
                        except Exception as e:
                            log_debug(f"Erreur envoi rapport de signalement de réponse : {e}", is_error=True)

                try:
                    await interaction.user.send(
                        f"{E_SUCCESS} Votre signalement de la réponse anonyme a bien été pris en compte.\n"
                        "Maintenant, seul un administrateur de votre serveur peut faire la demande auprès du serveur support "
                        "pour demander l'identité de l'éditeur du message pour pouvoir le signaler.\n"
                        "Attention : l'identité est dévoilée seulement si le motif est précisé dans le règlement du serveur."
                    )
                except Exception as dm_err:
                    log_debug(f"Impossible d'envoyer le MP de signalement de réponse : {dm_err}", is_error=True)

                return

            # Déclenchement du modal de nouvelle confession depuis le panneau d'administration ou un bouton "Se confesser"
            if custom_id == "trigger_confess_modal":
                guild = interaction.guild
                if not guild:
                    return
                config = conf_db.load(guild.id) or {}
                channel_id = config.get("channel_id")
                if not channel_id or not guild.get_channel(channel_id):
                    await interaction.response.send_message(f"{E_ERROR} Le système est actuellement inactif (salon invalide).", ephemeral=True)
                    return

                await interaction.response.send_modal(ConfessModal(self.bot))
                return

        except Exception as e:
            err_trace = traceback.format_exc()
            log_debug(f"Erreur critique dans on_interaction listener : {e}\n{err_trace}", is_error=True)
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"{E_ERROR} Une erreur est survenue lors de l'interaction.", ephemeral=True)
            except Exception:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Confessions(bot))