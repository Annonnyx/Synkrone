from __future__ import annotations

import traceback
import discord
from discord import ui
from discord.ext import commands

from utils.config_emoji import Emoji
from utils.config_theme import config_manager


DEBUG_LOGS = True
ERROR_LOGS = True


class LogColor:
    OKCYAN = "\033[96m"
    OKGREEN = "\033[92m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"


def log_debug(message: str):
    if DEBUG_LOGS:
        print(f"{LogColor.OKCYAN}[DEBUG][Check] {message}{LogColor.ENDC}")


def log_success(message: str):
    print(f"{LogColor.OKGREEN}[SUCCESS][Check] {message}{LogColor.ENDC}")


def log_error(message: str):
    if ERROR_LOGS:
        print(f"{LogColor.FAIL}[ERROR][Check] {message}{LogColor.ENDC}")


def _status_to_emoji(status: discord.Status) -> str:
    if status == discord.Status.online:
        return "🟢"
    if status == discord.Status.idle:
        return "🌙"
    if status == discord.Status.dnd:
        return "🔴"
    return "⚫"


def _member_tier(member: discord.Member) -> tuple[int, str]:
    if member.guild.owner_id == member.id:
        return 1, "👑"
    if member.guild_permissions.administrator:
        return 2, "🛠️"
    if member.guild_permissions.manage_guild or member.guild_permissions.manage_messages:
        return 3, "🛡️"
    return 4, "👤"


def _tier_to_permission_label(tier: int) -> str:
    if tier == 1:
        return "Owner"
    if tier == 2:
        return "Admin"
    return "Membre"


def _tier_to_access_code(tier: int) -> str:
    if tier == 1:
        return "OWN"
    if tier == 2:
        return "ADM"
    if tier == 3:
        return "MOD"
    return "MBR"


class CheckIdModal(ui.Modal):
    def __init__(self, parent_view: "CheckLayoutView"):
        super().__init__(title="Rechercher un ID")
        self.parent_view = parent_view
        self.id_input = ui.TextInput(
            label="ID utilisateur ou serveur",
            placeholder="Ex: 123456789101112345",
            max_length=25,
            required=True,
        )
        self.add_item(self.id_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw_id = self.id_input.value.strip()
        if not raw_id.isdigit():
            return await interaction.response.send_message(f"{Emoji.REFUSER} ID invalide.", ephemeral=True)

        await interaction.response.defer()
        await self.parent_view.search_by_id(interaction, int(raw_id))


class CheckLayoutView(ui.LayoutView):
    def __init__(
        self,
        bot: commands.Bot,
        guild_context: discord.Guild,
        author: discord.Member,
        *,
        target_user: discord.User | None = None,
        target_guild: discord.Guild | None = None,
    ):
        super().__init__(timeout=600)
        self.bot = bot
        self.guild_context = guild_context
        self.author = author
        self.message: discord.Message | None = None

        self.target_user = target_user
        self.target_guild = target_guild

        self.mode = "guild" if target_guild else "user"
        self.page = 0
        self.per_page = 10
        self.show_ids = False

        self.shared_guilds: list[dict] = []
        self.highest_status = discord.Status.offline
        self.voice_str = ""
        self.generated_invites: dict[int, str] = {}

        if self.target_user:
            self._collect_shared_guilds()

        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(f"{Emoji.REFUSER} Ce menu interactif ne vous appartient pas.", ephemeral=True)
            return False
        return True

    def _collect_shared_guilds(self) -> None:
        if not self.target_user:
            self.shared_guilds = []
            return

        rows = []
        highest_status = discord.Status.offline
        voice_line = ""

        for guild in self.bot.guilds:
            member = guild.get_member(self.target_user.id)
            if not member:
                continue

            tier, emoji = _member_tier(member)
            rows.append({
                "tier": tier,
                "emoji": emoji,
                "permission": _tier_to_permission_label(tier),
                "access_code": _tier_to_access_code(tier),
                "count": guild.member_count,
                "name": guild.name,
                "display_name": discord.utils.escape_markdown(guild.name),
                "id": guild.id,
                "guild": guild,
            })

            if member.status == discord.Status.online:
                highest_status = discord.Status.online
            elif highest_status != discord.Status.online and member.status != discord.Status.offline:
                highest_status = member.status

            if member.voice and member.voice.channel:
                voice_line = f"🎙️ **{guild.name}**\n-> `{member.voice.channel.id}`"

        rows.sort(key=lambda x: (-x["count"], x["tier"], str(x["name"]).lower()))
        self.shared_guilds = rows
        self.highest_status = highest_status
        self.voice_str = voice_line

    async def refresh_message(self) -> None:
        self._build()
        if self.message:
            await self.message.edit(view=self)

    def _current_page_slice(self) -> list[dict]:
        start = self.page * self.per_page
        end = start + self.per_page
        return self.shared_guilds[start:end]

    def _max_pages(self) -> int:
        return max(1, (len(self.shared_guilds) + self.per_page - 1) // self.per_page)

    def _header_title_and_subtitle(self) -> tuple[str, str]:
        if self.mode == "guild" and self.target_guild:
            return self.target_guild.name, f"`{self.target_guild.id}`"
        if self.target_user:
            return self.target_user.display_name, f"`{self.target_user.id}`"
        return "Diagnostic ID", "Aucune cible active"

    def _build(self) -> None:
        self.clear_items()

        theme = config_manager.get_layout_v2_theme(self.guild_context.id, self.guild_context, self.author, self.bot)
        color = int(theme.get("color", config_manager.get_color(self.guild_context.id)))
        footer_text = str(theme.get("footer_text", "") or "").strip()

        title, subtitle = self._header_title_and_subtitle()
        id_btn = ui.Button(label="ID", style=discord.ButtonStyle.secondary, emoji=Emoji.IDENTIFIANT)
        id_btn.callback = self._action_open_id_modal

        container = ui.Container(accent_color=discord.Color(color), spoiler=False)
        container.add_item(
            ui.Section(
                ui.TextDisplay(f"# {Emoji.RECHERCHE} {title}"),
                ui.TextDisplay(subtitle),
                accessory=id_btn,
            )
        )
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

        if self.mode == "guild" and self.target_guild:
            self._render_guild(container)
        elif self.target_user:
            self._render_user(container)
        else:
            container.add_item(ui.TextDisplay("Aucune donnée disponible. Utilise le bouton ID en haut à droite pour rechercher un serveur ou un utilisateur."))

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    def _render_guild(self, container: ui.Container) -> None:
        guild = self.target_guild
        if not guild:
            container.add_item(ui.TextDisplay("Serveur introuvable."))
            return

        humans = [m for m in guild.members if not m.bot]
        bots = [m for m in guild.members if m.bot]
        humans_online = [m for m in humans if m.status != discord.Status.offline]
        bots_online = [m for m in bots if m.status != discord.Status.offline]
        total_online = len(humans_online) + len(bots_online)
        owner_member = guild.get_member(guild.owner_id) if guild.owner_id else None
        owner_mention = owner_member.mention if owner_member else (f"<@{guild.owner_id}>" if guild.owner_id else "Inconnu")
        owner_name = owner_member.display_name if owner_member else (guild.owner.display_name if guild.owner else "utilisateur-inconnu")

        joined_days = (discord.utils.utcnow() - guild.me.joined_at).days if (guild.me and guild.me.joined_at) else 0
        joined_date_str = guild.me.joined_at.strftime("%d/%m/%y") if (guild.me and guild.me.joined_at) else "Inconnue"

        if guild.icon:
            container.add_item(
                ui.Section(
                    ui.TextDisplay(f"## 🏰 {guild.name}"),
                    ui.TextDisplay("Profil serveur"),
                    accessory=ui.Thumbnail(guild.icon.url, description=f"Icone de {guild.name}"),
                )
            )
        else:
            container.add_item(ui.TextDisplay(f"## 🏰 {guild.name}\nProfil serveur"))

        if guild.banner:
            try:
                gallery = ui.MediaGallery()
                gallery.add_item(media=guild.banner.url, description=f"Banniere du serveur {guild.name}")
                container.add_item(gallery)
            except Exception:
                pass

        invite_url = self.generated_invites.get(guild.id)
        if invite_url:
            stats_button = ui.Button(label="Rejoindre", style=discord.ButtonStyle.link, emoji=Emoji.LIEN, url=invite_url)
        else:
            stats_button = ui.Button(label="Créer", style=discord.ButtonStyle.success, emoji=Emoji.LIEN)
            stats_button.callback = self._action_generate_invite

        container.add_item(
            ui.Section(
                ui.TextDisplay("## Statistiques"),
                ui.TextDisplay(
                    f"• 👑 Propriétaire: {owner_mention}\n"
                    f"• Pseudo owner: `{owner_name}`\n"
                    f"• ID owner: `{guild.owner_id}`\n"
                    f"• Membres total: `{guild.member_count}`\n"
                    f"• Humains: `{len(humans)}`\n"
                    f"• Bots: `{len(bots)}`\n"
                    f"• Membres connectés: `{total_online}`\n"
                    f"• Humains connectés: `{len(humans_online)}`\n"
                    f"• Bots connectés: `{len(bots_online)}`\n"
                    f"• Rejoint le: `{joined_date_str}`\n"
                    f"• Présence bot: `{joined_days}` jour(s)"
                ),
                accessory=stats_button,
            )
        )

        if self.target_user:
            row = ui.ActionRow()
            back_btn = ui.Button(label="Retour utilisateur", style=discord.ButtonStyle.secondary)
            back_btn.callback = self._action_back_to_user
            row.add_item(back_btn)
            container.add_item(row)

    def _render_user(self, container: ui.Container) -> None:
        user = self.target_user
        if not user:
            container.add_item(ui.TextDisplay("Utilisateur introuvable."))
            return

        status_str = _status_to_emoji(self.highest_status)
        if user.avatar:
            container.add_item(
                ui.Section(
                    ui.TextDisplay(f"## {status_str} {user.display_name}"),
                    ui.TextDisplay("Profil utilisateur"),
                    accessory=ui.Thumbnail(user.avatar.url, description=f"Avatar de {user.display_name}"),
                )
            )
        else:
            container.add_item(ui.TextDisplay(f"## {status_str} {user.display_name}"))

        if user.banner:
            try:
                gallery = ui.MediaGallery()
                gallery.add_item(media=user.banner.url, description=f"Banniere de {user.display_name}")
                container.add_item(gallery)
            except Exception:
                pass

        if self.voice_str:
            container.add_item(ui.TextDisplay(f"**Vocal** : {self.voice_str}"))

        max_pages = self._max_pages()
        self.page = max(0, min(self.page, max_pages - 1))
        page_items = self._current_page_slice()

        start_index = self.page * self.per_page
        list_text = "\n".join(
            [
                f"{start_index + idx + 1}. {g['emoji']} {g['display_name']} `{g['id']}`" if self.show_ids
                else f"{start_index + idx + 1}. {g['emoji']} {g['display_name']}"
                for idx, g in enumerate(page_items)
            ]
        ) if page_items else "*Aucun serveur en commun.*"
        container.add_item(ui.TextDisplay(
            f"{Emoji.MONDE} Serveurs en commun: `{len(self.shared_guilds)}`\n"
            f"{list_text}"
        ))

        if page_items:
            select_row = ui.ActionRow()
            options = [
                discord.SelectOption(
                    label=((f"{start_index + idx + 1}. {g['name']}")[:100]),
                    value=str(g["id"]),
                    description=f"M: {g['count']} | {g['emoji']} {g['access_code']}",
                    emoji=g["emoji"],
                )
                for idx, g in enumerate(page_items)
            ]
            guild_select = ui.Select(
                placeholder="Choisir un serveur pour afficher son profil...",
                min_values=1,
                max_values=1,
                options=options,
                custom_id="check_guild_select",
            )
            guild_select.callback = self._on_shared_guild_selected
            select_row.add_item(guild_select)
            container.add_item(select_row)

        if max_pages > 1:
            nav_row = ui.ActionRow()
            prev_btn = ui.Button(label="◀", style=discord.ButtonStyle.secondary, disabled=(self.page == 0))
            prev_btn.callback = self._action_prev_page
            nav_row.add_item(prev_btn)

            counter_btn = ui.Button(label=f"Page {self.page + 1}/{max_pages}", style=discord.ButtonStyle.secondary, disabled=True)
            nav_row.add_item(counter_btn)

            next_btn = ui.Button(label="▶", style=discord.ButtonStyle.secondary, disabled=(self.page >= max_pages - 1))
            next_btn.callback = self._action_next_page
            nav_row.add_item(next_btn)

            toggle_label = "Masquer ID" if self.show_ids else "Afficher ID"
            toggle_btn = ui.Button(label=toggle_label, style=discord.ButtonStyle.secondary, emoji=Emoji.IDENTIFIANT)
            toggle_btn.callback = self._action_toggle_ids
            nav_row.add_item(toggle_btn)

            container.add_item(nav_row)
        else:
            toggle_row = ui.ActionRow()
            toggle_label = "Masquer ID" if self.show_ids else "Afficher ID"
            toggle_btn = ui.Button(label=toggle_label, style=discord.ButtonStyle.secondary, emoji=Emoji.IDENTIFIANT)
            toggle_btn.callback = self._action_toggle_ids
            toggle_row.add_item(toggle_btn)
            container.add_item(toggle_row)

    async def _on_shared_guild_selected(self, interaction: discord.Interaction):
        values = interaction.values if hasattr(interaction, "values") else interaction.data.get("values", [])
        if not values:
            return await interaction.response.defer()

        try:
            guild_id = int(values[0])
        except ValueError:
            return await interaction.response.send_message(f"{Emoji.REFUSER} Sélection invalide.", ephemeral=True)

        selected = None
        for row in self.shared_guilds:
            if row["id"] == guild_id:
                selected = row["guild"]
                break

        if not selected:
            return await interaction.response.send_message(f"{Emoji.REFUSER} Serveur introuvable.", ephemeral=True)

        self.target_guild = selected
        self.mode = "guild"
        self._build()
        await interaction.response.edit_message(view=self)

    async def _action_prev_page(self, interaction: discord.Interaction):
        self.page -= 1
        self._build()
        await interaction.response.edit_message(view=self)

    async def _action_next_page(self, interaction: discord.Interaction):
        self.page += 1
        self._build()
        await interaction.response.edit_message(view=self)

    async def _action_back_to_user(self, interaction: discord.Interaction):
        self.mode = "user"
        self._build()
        await interaction.response.edit_message(view=self)

    async def _action_open_id_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CheckIdModal(self))

    async def _action_toggle_ids(self, interaction: discord.Interaction):
        self.show_ids = not self.show_ids
        self._build()
        await interaction.response.edit_message(view=self)

    async def search_by_id(self, interaction: discord.Interaction, obj_id: int):
        guild = self.bot.get_guild(obj_id)

        if guild:
            self.target_guild = guild
            self.mode = "guild"
            self.page = 0
            self._build()
            if self.message:
                await self.message.edit(view=self)
            return

        try:
            user = await self.bot.fetch_user(obj_id)
        except Exception:
            user = None

        if user:
            self.target_user = user
            self.target_guild = None
            self.mode = "user"
            self.page = 0
            self._collect_shared_guilds()
            self._build()
            if self.message:
                await self.message.edit(view=self)
            return

        await interaction.followup.send(f"{Emoji.REFUSER} Aucune correspondance trouvée pour `{obj_id}`.", ephemeral=True)

    async def _action_generate_invite(self, interaction: discord.Interaction):
        guild = self.target_guild
        if not guild:
            return await interaction.response.send_message(f"{Emoji.REFUSER} Aucun serveur actif.", ephemeral=True)

        bot_member = guild.me or (guild.get_member(self.bot.user.id) if self.bot.user else None)
        invite_info = None

        try:
            invites = await guild.invites()
            for inv in invites:
                if inv.max_age == 0 or inv.max_age > 600:
                    invite_info = f"✅ **Lien existant trouvé :**\\n{inv.url}"
                    self.generated_invites[guild.id] = inv.url
                    break

            if not invite_info:
                for channel in guild.text_channels:
                    if bot_member and channel.permissions_for(bot_member).create_instant_invite:
                        new_invite = await channel.create_invite(max_age=600, max_uses=1, reason="Owner check")
                        invite_info = f"✨ **Nouveau lien généré** *(Usage unique, expire dans 10m)* :\\n{new_invite.url}"
                        self.generated_invites[guild.id] = new_invite.url
                        break
        except discord.Forbidden:
            invite_info = "❌ Permissions insuffisantes pour voir ou créer une invitation sur ce serveur."
        except Exception as e:
            invite_info = f"❌ Erreur : {e}"

        if not invite_info:
            invite_info = "❌ Aucun salon textuel disponible."
            return await interaction.response.send_message(invite_info, ephemeral=True)

        self._build()
        await interaction.response.edit_message(view=self)

class OwnerCheck(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log_success("Cog Check initialisé.")

    @commands.command(name="check", description="Diagnostic rapide sur un ID")
    async def check(self, ctx: commands.Context, target_id: str | None = None):
        if not ctx.guild:
            return await ctx.send(f"{Emoji.REFUSER} Cette commande doit être exécutée sur un serveur.")

        member = ctx.author if isinstance(ctx.author, discord.Member) else ctx.guild.get_member(ctx.author.id)
        if not member:
            return await ctx.send(f"{Emoji.REFUSER} Impossible de valider vos permissions.")

        if not target_id:
            view = CheckLayoutView(self.bot, ctx.guild, member)
            message = await ctx.send(view=view)
            view.message = message
            return

        if not target_id.isdigit():
            return await ctx.send(f"{Emoji.ATTENTION} Veuillez spécifier un ID valide. Exemple : `²check 123456789012345678`")

        obj_id = int(target_id)
        guild = self.bot.get_guild(obj_id)

        if guild:
            log_success(f"Check Serveur exécuté pour {guild.name} ({guild.id}).")
            view = CheckLayoutView(self.bot, ctx.guild, member, target_guild=guild)
            message = await ctx.send(view=view)
            view.message = message
            return

        try:
            user = await self.bot.fetch_user(obj_id)
        except Exception:
            user = None

        if user:
            log_success(f"Check Utilisateur exécuté pour {user} ({user.id}).")
            view = CheckLayoutView(self.bot, ctx.guild, member, target_user=user)
            message = await ctx.send(view=view)
            view.message = message
            return

        await ctx.send(f"{Emoji.REFUSER} Aucune correspondance trouvée pour cet ID `{obj_id}`.")

    async def cog_command_error(self, ctx: commands.Context, error: Exception):
        if ctx.command and ctx.command.name == "check":
            log_error(f"Erreur commande {ctx.command.name}: {error}")
            log_error(traceback.format_exc())
            try:
                await ctx.send(f"{Emoji.REFUSER} Erreur sur la commande `{ctx.command.name}`: `{error}`")
            except Exception:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(OwnerCheck(bot))
