from __future__ import annotations

import asyncio
import io
import re
from typing import Dict, Optional

import aiohttp
import discord
from discord import app_commands, ui
from discord.ext import commands, tasks

# ==============================================================================
# ------------------------------ DÉBOGAGE GLOBAL -------------------------------
# ==============================================================================
DEBUG_MODE = True


def log_debug(message: str, level: str = "info") -> None:
    """Affiche des logs formatés dans la console selon le niveau de sévérité."""
    if not DEBUG_MODE:
        return
    colors = {
        "info": "\033[94m[INFO]\033[0m",
        "success": "\033[92m[SUCCÈS]\033[0m",
        "error": "\033[91m[ERREUR]\033[0m",
        "warning": "\033[93m[ATTENTION]\033[0m",
        "emoji": "\033[35m[EMOJI]\033[0m",
    }
    prefix = colors.get(level, colors["info"])
    print(f"{prefix} [EmojiModule] {message}")


# ==============================================================================
# --------------------------- IMPORTATION UTILS --------------------------------
# ==============================================================================
try:
    from utils.config_theme import config_manager
    log_debug("Module config_manager importé avec succès.", "success")
except ImportError as e:
    log_debug(f"Erreur d'importation de config_manager : {e}", "error")
    config_manager = None

try:
    from utils.config_perm import _send_permission_denied, ensure_command_permission, perm_command
    log_debug("Module config_perm importé avec succès.", "success")
except ImportError as e:
    log_debug(f"Erreur d'importation de config_perm : {e}", "error")
    _send_permission_denied = None
    ensure_command_permission = None
    perm_command = None


# ==============================================================================
# ------------------------- VUE LAYOUT V2 DES EMOJIS ---------------------------
# ==============================================================================
class EmojiLayoutView(ui.LayoutView):
    """Interface Layout V2 pour la gestion des emojis avec sélecteur d'action."""

    def __init__(self, cog: "StaffEmojiCommand", user_id: int, guild: discord.Guild, author: discord.Member):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id
        self.guild = guild
        self.author = author
        self.added_emojis = []
        self.message: Optional[discord.Message] = None
        self.instruction_message: Optional[discord.Message] = None
        self.last_interaction = asyncio.get_event_loop().time()
        self.info_text = ""
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("âŒ Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        self.last_interaction = asyncio.get_event_loop().time()
        return True

    async def delete_after_delay(self, message: discord.Message, delay: int):
        """Supprime un message après un délai donné."""
        try:
            await asyncio.sleep(delay)
            await message.delete()
        except (discord.NotFound, discord.HTTPException):
            pass

    def _build(self):
        self.clear_items()

        theme = (
            config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.author, self.cog.bot)
            if config_manager
            else {"color": 0x5865F2, "footer_text": ""}
        )
        accent_color = int(theme.get("color", 0x5865F2))
        footer_text = theme.get("footer_text", "")

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay("# ðŸ–¼ï¸ Gestion des Emojis"))
        container.add_item(ui.TextDisplay("Sélectionnez une action dans le menu ci-dessous pour gérer vos emojis."))

        if self.info_text:
            container.add_item(ui.TextDisplay(self.info_text))

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

        if self.added_emojis:
            emojis_text = "\n".join([f"{str(emoji)} `:{emoji.name}:`" for emoji in self.added_emojis[-10:]])
            container.add_item(ui.TextDisplay(f"### ðŸ“ Emojis ajoutés / traités récemment\n{emojis_text}"))
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

        # Sélecteur d'action remplaçant les boutons
        action_row = ui.ActionRow()
        select = ui.Select(
            placeholder="âš™ï¸ Choisir une action...",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label="Importer par image", value="import_image", emoji="ðŸ–¼ï¸", description="Envoyer des images locales pour créer des emojis"),
                discord.SelectOption(label="Ajouter par URL", value="import_url", emoji="ðŸ”—", description="Créer un emoji à partir d'un lien direct d'image"),
                discord.SelectOption(label="Copier emoji", value="copy_emoji", emoji="ðŸ“‹", description="Copier des emojis personnalisés d'un autre serveur"),
                discord.SelectOption(label="Afficher format image", value="show_format", emoji="ðŸ”", description="Recevoir les liens images d'une liste d'emojis"),
            ]
        )
        select.callback = self.action_select_callback
        action_row.add_item(select)
        container.add_item(action_row)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    async def _refresh(self, interaction: discord.Interaction):
        self._build()
        if not interaction.response.is_done():
            await interaction.response.edit_message(view=self)
        else:
            await interaction.edit_original_response(view=self)

    async def _refresh_silent(self):
        if self.message:
            self._build()
            await self.message.edit(view=self)

    async def action_select_callback(self, interaction: discord.Interaction):
        choice = interaction.data.get("values", [""])[0]
        if choice == "import_image":
            await self.handle_import_image(interaction)
        elif choice == "import_url":
            await self.handle_import_url(interaction)
        elif choice == "copy_emoji":
            await self.handle_copy_emoji(interaction)
        elif choice == "show_format":
            await self.handle_show_format(interaction)

    async def handle_import_image(self, interaction: discord.Interaction):
        await interaction.response.defer()
        desc = (
            "ðŸ“¤ **Envoyez une ou plusieurs images** dans ce salon pour les convertir en emojis.\n"
            "Vous pouvez envoyer plusieurs fichiers dans un seul message (Délai : 60 secondes)."
        )
        self.instruction_message = await interaction.followup.send(desc, wait=True)
        if self.instruction_message:
            asyncio.create_task(self.delete_after_delay(self.instruction_message, 15))

        def check(m: discord.Message) -> bool:
            return m.author.id == interaction.user.id and bool(m.attachments) and m.channel.id == interaction.channel_id

        try:
            msg = await self.cog.bot.wait_for("message", check=check, timeout=60.0)
            added_emojis = []
            errors = []

            for attachment in msg.attachments[:10]:
                try:
                    if not any(attachment.filename.lower().endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif"]):
                        errors.append(f"âŒ `{attachment.filename}` : Format invalide.")
                        continue
                    if attachment.size > 256 * 1024:
                        errors.append(f"âŒ `{attachment.filename}` : Fichier trop lourd (>256KB).")
                        continue

                    emoji_name = "".join(
                        c for c in attachment.filename.split(".")[0].lower().replace(" ", "_") if c.isalnum() or c == "_"
                    )
                    if not emoji_name:
                        emoji_name = f"emoji_{len(self.added_emojis) + 1}"

                    data = await attachment.read()
                    new_emoji = await interaction.guild.create_custom_emoji(
                        name=emoji_name[:32], image=data, reason=f"Ajouté par {interaction.user}"
                    )
                    self.added_emojis.append(new_emoji)
                    added_emojis.append(new_emoji)
                except Exception as e:
                    errors.append(f"âŒ `{attachment.filename}` : {str(e)}")

            try:
                await msg.delete()
            except Exception:
                pass

            report_parts = []
            if added_emojis:
                emoji_list = " ".join(str(e) for e in added_emojis)
                report_parts.append(f"âœ… {len(added_emojis)} emoji(s) ajouté(s) : {emoji_list}")
            if errors:
                report_parts.append("âš ï¸ Erreurs :\n" + "\n".join(errors[:5]))

            self.info_text = "\n".join(report_parts) if report_parts else ""
            await self._refresh_silent()
        except asyncio.TimeoutError:
            self.info_text = "âŒ Temps écoulé pour l'importation d'image."
            await self._refresh_silent()

    async def handle_import_url(self, interaction: discord.Interaction):
        await interaction.response.send_modal(EmojiUrlModal(self))

    async def handle_copy_emoji(self, interaction: discord.Interaction):
        await interaction.response.defer()
        desc = (
            "ðŸ“¤ **Envoyez un ou plusieurs emojis personnalisés** dans ce salon à copier.\n"
            "Vous pouvez envoyer plusieurs emojis dans un seul message (Délai : 60 secondes)."
        )
        self.instruction_message = await interaction.followup.send(desc, wait=True)
        if self.instruction_message:
            asyncio.create_task(self.delete_after_delay(self.instruction_message, 15))

        def check(m: discord.Message) -> bool:
            return (
                m.author.id == interaction.user.id
                and m.channel.id == interaction.channel_id
                and bool(re.search(r"<a?:\w+:\d+>", m.content))
            )

        try:
            msg = await self.cog.bot.wait_for("message", check=check, timeout=60.0)
            emoji_matches = re.finditer(r"<(?P<animated>a?):(?P<name>\w+):(?P<id>\d+)>", msg.content)
            emoji_data = [(m.group("id"), m.group("animated") == "a", m.group("name")) for m in emoji_matches]
            emoji_data = list(dict.fromkeys(emoji_data))[:10]

            if not emoji_data:
                try:
                    await msg.delete()
                except Exception:
                    pass
                self.info_text = "âŒ Aucun emoji valide trouvé dans le message."
                await self._refresh_silent()
                return

            added = []
            errors = []

            for emoji_id, is_animated, emoji_name in emoji_data:
                try:
                    url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{'gif' if is_animated else 'png'}"
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url) as response:
                            if response.status != 200:
                                errors.append(f"âŒ `{emoji_name}` : Impossible de télécharger.")
                                continue
                            data = await response.read()
                            new_emoji = await interaction.guild.create_custom_emoji(
                                name=emoji_name[:32], image=data, reason=f"Copié par {interaction.user}"
                            )
                            self.added_emojis.append(new_emoji)
                            added.append(new_emoji)
                except Exception:
                    errors.append(f"âŒ `{emoji_name}` : Erreur de traitement.")

            try:
                await msg.delete()
            except Exception:
                pass

            report_parts = []
            if added:
                emoji_list = " ".join(str(e) for e in added)
                report_parts.append(f"âœ… {len(added)} emoji(s) copié(s) : {emoji_list}")
            if errors:
                report_parts.append("âš ï¸ Erreurs :\n" + "\n".join(errors[:5]))

            self.info_text = "\n".join(report_parts) if report_parts else ""
            await self._refresh_silent()
        except asyncio.TimeoutError:
            self.info_text = "âŒ Temps écoulé pour la copie d'emoji."
            await self._refresh_silent()

    async def handle_show_format(self, interaction: discord.Interaction):
        await interaction.response.defer()
        desc = (
            "ðŸ” **Envoyez une liste d'emojis** dans ce salon pour obtenir leurs liens d'images directs.\n"
            "(Délai : 60 secondes)."
        )
        self.instruction_message = await interaction.followup.send(desc, wait=True)
        if self.instruction_message:
            asyncio.create_task(self.delete_after_delay(self.instruction_message, 15))

        def check(m: discord.Message) -> bool:
            return (
                m.author.id == interaction.user.id
                and m.channel.id == interaction.channel_id
                and bool(re.search(r"<a?:\w+:\d+>", m.content))
            )

        try:
            msg = await self.cog.bot.wait_for("message", check=check, timeout=60.0)
            emoji_matches = re.finditer(r"<(?P<animated>a?):(?P<name>\w+):(?P<id>\d+)>", msg.content)
            urls = []
            for m in emoji_matches:
                emoji_id = m.group("id")
                is_animated = m.group("animated") == "a"
                ext = "gif" if is_animated else "png"
                urls.append(f"- **{m.group('name')}** : https://cdn.discordapp.com/emojis/{emoji_id}.{ext}")

            try:
                await msg.delete()
            except Exception:
                pass

            if urls:
                self.info_text = "### ðŸ”— Formats d'images trouvés :\n" + "\n".join(urls[:10])
            else:
                self.info_text = "âŒ Aucun emoji personnalisé valide détecté."
            await self._refresh_silent()
        except asyncio.TimeoutError:
            self.info_text = "âŒ Temps écoulé pour l'affichage du format image."
            await self._refresh_silent()


# ==============================================================================
# MODALE D'IMPORTATION PAR URL
# ==============================================================================
class EmojiUrlModal(ui.Modal, title="Ajouter un emoji par URL"):
    def __init__(self, view: EmojiLayoutView):
        super().__init__()
        self.view = view

        self.url_input = ui.TextInput(
            label="URL directe de l'image",
            placeholder="https://exemple.com/image.png",
            required=True,
            style=discord.TextStyle.short
        )
        self.name_input = ui.TextInput(
            label="Nom de l'emoji",
            placeholder="mon_super_emoji",
            required=True,
            max_length=32
        )
        self.add_item(self.url_input)
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        url = self.url_input.value.strip()
        emoji_name = "".join(c for c in self.name_input.value.strip().lower().replace(" ", "_") if c.isalnum() or c == "_")
        if not emoji_name:
            emoji_name = "emoji_personnalise"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        self.view.info_text = "âŒ Impossible de télécharger l'image depuis l'URL fournie."
                        await self.view._refresh_silent()
                        return await interaction.followup.send("âŒ Erreur de téléchargement.", ephemeral=True)
                    data = await resp.read()

            new_emoji = await interaction.guild.create_custom_emoji(
                name=emoji_name[:32], image=data, reason=f"Ajouté par URL par {interaction.user}"
            )
            self.view.added_emojis.append(new_emoji)
            self.view.info_text = f"âœ… Emoji créé avec succès : {str(new_emoji)} `:{new_emoji.name}:`"
            await self.view._refresh_silent()
            await interaction.followup.send(f"âœ… Emoji créé avec succès : {str(new_emoji)}", ephemeral=True)
        except Exception as e:
            log_debug(f"Erreur création emoji URL : {e}", "error")
            await interaction.followup.send(f"âŒ Erreur lors de la création : {e}", ephemeral=True)


# ==============================================================================
# --------------------------- COG PRINCIPAL ------------------------------------
# ==============================================================================
class StaffEmojiCommand(commands.Cog):
    """Gestion des emojis du serveur avec une interface interactive Layout V2 et sélecteur."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_views: Dict[int, EmojiLayoutView] = {}
        self.cleanup_task = self.cleanup_old_views.start()
        log_debug("Cog StaffEmojiCommand initialisé.", "success")

    def cog_unload(self):
        if self.cleanup_task:
            self.cleanup_task.cancel()
        log_debug("Cog StaffEmojiCommand déchargé.", "warning")

    @tasks.loop(minutes=5)
    async def cleanup_old_views(self):
        current_time = asyncio.get_event_loop().time()
        to_remove = []

        for user_id, view in self.active_views.items():
            if current_time - view.last_interaction > 1800:
                to_remove.append(user_id)
                if view.message:
                    try:
                        await view.message.delete()
                    except Exception:
                        pass

        for user_id in to_remove:
            self.active_views.pop(user_id, None)

    @perm_command(level=1)
    @commands.command(name="emoji", description="ðŸ–¼ï¸ Ouvre le menu de gestion des emojis ou affiche un emoji en grand")
    @app_commands.describe(emoji="L'emoji personnalisé à afficher en grand (optionnel)")
    @commands.has_permissions(manage_emojis=True)
    @discord.app_commands.guild_only()
    async def emoji_command(self, ctx: commands.Context, *, emoji: str = None):
        if ctx.guild and ensure_command_permission:
            if not await ensure_command_permission(ctx, command_name="emoji"):
                return

        if emoji is not None and emoji.strip():
            match = re.search(r"<(a?):(\w+):(\d+)>", emoji.strip())
            if match:
                emoji_id = match.group(3)
                is_animated = match.group(1) == "a"
                ext = "gif" if is_animated else "png"
                url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            return await ctx.send("âŒ Impossible de récupérer l'emoji.")
                        data = await resp.read()
                        file = discord.File(fp=io.BytesIO(data), filename=f"emoji.{ext}")
                        log_debug(f"Affichage en grand de l'emoji ID {emoji_id}", "emoji")
                        return await ctx.send(file=file)
            return await ctx.send("âŒ Veuillez fournir un emoji personnalisé valide sous la forme `<:nom:id>` ou `<a:nom:id>`.")

        if not ctx.guild.me.guild_permissions.manage_emojis:
            return await ctx.send("âŒ Je n'ai pas la permission `Gérer les emojis`.")

        if ctx.author.id in self.active_views:
            old_view = self.active_views[ctx.author.id]
            if old_view.message:
                try:
                    await old_view.message.delete()
                except Exception:
                    pass

        view = EmojiLayoutView(self, ctx.author.id, ctx.guild, ctx.author)
        log_debug(f"Ouverture du panneau Layout V2 Emojis pour {ctx.author} ({ctx.author.id})", "info")

        message = await ctx.send(view=view)
        if isinstance(message, discord.Interaction):
            view.message = await message.original_response()
        else:
            view.message = message

        self.active_views[ctx.author.id] = view

    @emoji_command.error
    async def emoji_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            if _send_permission_denied is not None:
                await _send_permission_denied(ctx)
                return
            await ctx.send("âŒ Vous n'avez pas la permission requise pour utiliser cette commande.")
        if isinstance(error, commands.BadArgument):
            await ctx.send("âŒ Argument invalide.")


async def setup(bot: commands.Bot):
    await bot.add_cog(StaffEmojiCommand(bot))
    log_debug("Cog StaffEmojiCommand enregistré et chargé.", "success")
