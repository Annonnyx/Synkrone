from __future__ import annotations

import re
from typing import Optional

import discord
from discord import app_commands, ui
from discord.ext import commands

from utils.config_id import IdModal
from utils.config_theme import config_manager


class InfoLayoutView(ui.LayoutView):
    def __init__(self, cog: "Info", guild: discord.Guild, author: discord.Member):
        super().__init__(timeout=900)
        self.cog = cog
        self.guild = guild
        self.author = author
        self.message: Optional[discord.Message] = None
        self.target_kind: str = "guild"
        self.target_obj: object = guild
        self.target_banner_url: Optional[str] = guild.banner.url if guild.banner else None
        self.search_mode: str = "guild"
        self.info_text = ""
        self._build()

    @staticmethod
    def _mode_display(mode: str) -> str:
        mapping = {
            "guild": "serveur",
            "channel": "salon",
            "role": "rôle",
            "member": "utilisateur",
            "auto": "auto",
            "serveur": "serveur",
            "salon": "salon",
            "utilisateur": "utilisateur",
        }
        return mapping.get(mode, mode)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Ce panneau ne vous appartient pas.", ephemeral=True)
            return False
        return True

    def set_target(self, kind: str, obj: object) -> None:
        self.target_kind = kind
        self.target_obj = obj

        if kind == "guild" and isinstance(obj, discord.Guild):
            self.target_banner_url = obj.banner.url if obj.banner else None
            return

        if kind == "member" and isinstance(obj, (discord.Member, discord.User)):
            banner = getattr(obj, "banner", None)
            self.target_banner_url = banner.url if banner else None
            return

        self.target_banner_url = None

    async def prepare_target_media(self) -> None:
        if self.target_kind != "member" or not isinstance(self.target_obj, (discord.Member, discord.User)):
            return

        member_id = self.target_obj.id
        try:
            full_user = await self.cog.bot.fetch_user(member_id)
        except Exception:
            return

        if full_user.banner:
            self.target_banner_url = full_user.banner.url

    @staticmethod
    def _first_selected(interaction: discord.Interaction):
        values = getattr(interaction, "values", None)
        if values:
            return values[0]

        if interaction.data:
            raw_values = interaction.data.get("values", [])
            if raw_values:
                return raw_values[0]
        return None

    @staticmethod
    def _extract_selected_id(interaction: discord.Interaction) -> Optional[int]:
        target = InfoLayoutView._first_selected(interaction)
        if target is None:
            return None

        target_id = getattr(target, "id", None)
        if isinstance(target_id, int):
            return target_id

        raw = str(target)
        return int(raw) if raw.isdigit() else None

    async def resolve_query(self, query: str, preferred_mode: str = "auto") -> Optional[tuple[str, object]]:
        raw = (query or "").strip()
        if not raw:
            return None

        lowered = raw.lower()
        if lowered in {"serveur", "server", "guild", "this", "ici"}:
            return "guild", self.guild

        mention_channel = re.fullmatch(r"<#(\d+)>", raw)
        mention_role = re.fullmatch(r"<@&(\d+)>", raw)
        mention_user = re.fullmatch(r"<@!?(\d+)>", raw)

        if mention_channel:
            channel = self.guild.get_channel(int(mention_channel.group(1)))
            return ("channel", channel) if channel else None
        if mention_role:
            role = self.guild.get_role(int(mention_role.group(1)))
            return ("role", role) if role else None
        if mention_user:
            uid = int(mention_user.group(1))
            member = self.guild.get_member(uid)
            if member is None:
                try:
                    member = await self.guild.fetch_member(uid)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    member = None
            return ("member", member) if member else None

        if raw.isdigit():
            sid = int(raw)
            if sid == self.guild.id:
                return "guild", self.guild

            if preferred_mode == "channel":
                channel = self.guild.get_channel(sid)
                return ("channel", channel) if channel else None
            if preferred_mode == "role":
                role = self.guild.get_role(sid)
                return ("role", role) if role else None
            if preferred_mode == "member":
                member = self.guild.get_member(sid)
                if member is None:
                    try:
                        member = await self.guild.fetch_member(sid)
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        member = None
                return ("member", member) if member else None

            channel = self.guild.get_channel(sid)
            if channel:
                return "channel", channel

            role = self.guild.get_role(sid)
            if role:
                return "role", role

            member = self.guild.get_member(sid)
            if member is None:
                try:
                    member = await self.guild.fetch_member(sid)
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    member = None
            if member:
                return "member", member

            return None

        # Recherche par nom (ergonomique)
        if preferred_mode in {"channel", "auto", "guild"}:
            by_name = discord.utils.find(lambda c: c.name.lower() == lowered, self.guild.channels)
            if by_name:
                return "channel", by_name
            contains = discord.utils.find(lambda c: lowered in c.name.lower(), self.guild.channels)
            if contains:
                return "channel", contains

        if preferred_mode in {"role", "auto", "guild"}:
            by_name = discord.utils.find(lambda r: r.name.lower() == lowered, self.guild.roles)
            if by_name:
                return "role", by_name
            contains = discord.utils.find(lambda r: lowered in r.name.lower(), self.guild.roles)
            if contains:
                return "role", contains

        if preferred_mode in {"member", "auto", "guild"}:
            member_exact = discord.utils.find(
                lambda m: lowered in {m.name.lower(), m.display_name.lower()},
                self.guild.members,
            )
            if member_exact:
                return "member", member_exact
            member_contains = discord.utils.find(
                lambda m: lowered in m.display_name.lower() or lowered in m.name.lower(),
                self.guild.members,
            )
            if member_contains:
                return "member", member_contains

        return None

    def _kind_label(self) -> str:
        mapping = {
            "guild": "Serveur",
            "channel": "Salon",
            "role": "Rôle",
            "member": "Utilisateur",
        }
        return mapping.get(self.target_kind, "Inconnu")

    def _render_guild(self, guild: discord.Guild) -> str:
        owner_member = guild.get_member(guild.owner_id) if guild.owner_id else None
        owner = owner_member.mention if owner_member else (f"<@{guild.owner_id}>" if guild.owner_id else "Inconnu")
        created = int(guild.created_at.timestamp())
        members = list(guild.members)
        total_members = guild.member_count or len(members)
        human_members = sum(1 for member in members if not member.bot)
        bot_members = sum(1 for member in members if member.bot)

        connected_members = [member for member in members if getattr(member, "status", discord.Status.offline) != discord.Status.offline]
        connected_total = len(connected_members)
        connected_humans = sum(1 for member in connected_members if not member.bot)
        connected_bots = sum(1 for member in connected_members if member.bot)

        return (
            f"### 🏠 {guild.name}\n"
            f"👑 Propriétaire : {owner}\n"
            f"🆔 ID serveur : `{guild.id}`\n"
            f"📅 Création : <t:{created}:D> (<t:{created}:R>)\n"
            f"\n"
            f"👥 Membres Total : `{total_members}`\n"
            f"› 👤 Humains : `{human_members}`\n"
            f"› 🤖 Bots : `{bot_members}`\n"
            f"\n"
            f"🟢 Membres Connectés : `{connected_total}`\n"
            f"› 👤 Humains : `{connected_humans}`\n"
            f"› 🤖 Bots : `{connected_bots}`\n"
            f"🎭 Rôles : `{len(guild.roles)}`\n"
            f"💬 Salons : `{len(guild.channels)}` (`{len(guild.text_channels)}` texte / `{len(guild.voice_channels)}` vocal)\n"
            f"✨ Boosts : niveau `{guild.premium_tier}` / `{guild.premium_subscription_count}` boost(s)"
        )

    def _render_channel(self, channel: discord.abc.GuildChannel) -> str:
        created = int(channel.created_at.timestamp())
        ctype = type(channel).__name__.replace("Channel", "")
        category = channel.category.mention if getattr(channel, "category", None) else "Aucune"
        base = (
            f"### 📍 {channel.mention}\n"
            f"🆔 ID : `{channel.id}`\n"
            f"🏷️ Type : `{ctype}`\n"
            f"📁 Catégorie : {category}\n"
            f"📅 Création : <t:{created}:D> (<t:{created}:R>)"
        )

        if isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
            connected = list(channel.members)
            count = len(connected)
            if connected:
                members_list = "\n".join(f"• {m.display_name} (`{m.id}`)" for m in connected[:25])
                if count > 25:
                    members_list += f"\n… et {count - 25} autre(s)."
            else:
                members_list = "Aucun membre connecté."

            extra = ""
            if isinstance(channel, discord.VoiceChannel):
                limit = channel.user_limit if channel.user_limit > 0 else "illimitée"
                extra = f"\n🔊 Bitrate : `{channel.bitrate // 1000} kbps`\n👥 Limite : `{limit}`"

            return (
                f"{base}{extra}\n"
                f"👤 Connectés : `{count}`\n"
                f"\n"
                f"### Membres présents\n"
                f"{members_list}"
            )

        return base

    def _render_role(self, role: discord.Role) -> str:
        created = int(role.created_at.timestamp())
        members = role.members
        total = self.guild.member_count or 0
        percent = (len(members) / total * 100) if total else 0
        preview = " ".join(m.mention for m in members[:12]) if members else "Aucun"
        return (
            f"### 🎭 {role.mention}\n"
            f"🆔 ID : `{role.id}`\n"
            f"📅 Création : <t:{created}:D> (<t:{created}:R>)\n"
            f"🌈 Couleur : `{str(role.color).upper()}`\n"
            f"👥 Membres : `{len(members)}` ({percent:.1f}% du serveur)\n"
            f"\n"
            f"Aperçu membres : {preview}"
        )

    def _render_member(self, member: discord.Member | discord.User) -> str:
        created = int(member.created_at.timestamp())
        joined = int(member.joined_at.timestamp()) if isinstance(member, discord.Member) and member.joined_at else None
        roles = []
        if isinstance(member, discord.Member):
            roles = [r.mention for r in reversed(member.roles) if r.name != "@everyone"]
        roles_preview = " ".join(roles[:12]) if roles else "Aucun"

        display_name = member.display_name if isinstance(member, discord.Member) else member.name
        mention = member.mention

        lines = [
            f"### 👤 {mention}",
            f"🆔 ID : `{member.id}`",
            f"🎂 Compte créé : <t:{created}:D> (<t:{created}:R>)",
        ]
        if joined:
            lines.append(f"🚪 Arrivé : <t:{joined}:D> (<t:{joined}:R>)")
        lines.append(f"🏷️ Nom : `{display_name}`")
        lines.append(f"🎭 Rôles ({len(roles)}) : {roles_preview}")
        return "\n".join(lines)

    def _details_text(self) -> str:
        if self.target_kind == "guild" and isinstance(self.target_obj, discord.Guild):
            return self._render_guild(self.target_obj)
        if self.target_kind == "channel" and isinstance(self.target_obj, discord.abc.GuildChannel):
            return self._render_channel(self.target_obj)
        if self.target_kind == "role" and isinstance(self.target_obj, discord.Role):
            return self._render_role(self.target_obj)
        if self.target_kind == "member" and isinstance(self.target_obj, (discord.Member, discord.User)):
            return self._render_member(self.target_obj)
        return "❌ Aucune donnée à afficher."

    def _thumbnail_url(self) -> Optional[str]:
        if self.target_kind == "guild" and isinstance(self.target_obj, discord.Guild):
            if self.target_obj.icon:
                return self.target_obj.icon.url
            return None

        if self.target_kind == "member" and isinstance(self.target_obj, (discord.Member, discord.User)):
            return self.target_obj.display_avatar.url

        return None

    def _banner_url(self) -> Optional[str]:
        if self.target_banner_url:
            return self.target_banner_url

        if self.target_kind == "guild" and isinstance(self.target_obj, discord.Guild):
            if self.target_obj.banner:
                return self.target_obj.banner.url
            return None

        if self.target_kind == "member" and isinstance(self.target_obj, (discord.Member, discord.User)):
            banner = getattr(self.target_obj, "banner", None)
            if banner:
                return banner.url
            return None

        return None

    def _build(self) -> None:
        self.clear_items()

        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.author, self.cog.bot)
        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text") or ""

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay("# 🔎 Info Explorer"))
        container.add_item(ui.TextDisplay("Trouvez des infos sur serveur, salon, rôle ou utilisateur."))
        if self.info_text:
            container.add_item(ui.TextDisplay(self.info_text))

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
        container.add_item(ui.TextDisplay(f"## 🎯 Cible actuelle : {self._kind_label()}"))
        details = self._details_text()
        thumb_url = self._thumbnail_url()
        if thumb_url:
            container.add_item(
                ui.Section(
                    details,
                    accessory=ui.Thumbnail(thumb_url, description=f"Avatar de {self._kind_label()}")
                )
            )
        else:
            container.add_item(ui.TextDisplay(details))

        if self.target_kind == "guild" and isinstance(self.target_obj, discord.Guild):
            emoji_total = len(self.target_obj.emojis)
            emoji_preview = " ".join(str(e) for e in self.target_obj.emojis[:18]) if self.target_obj.emojis else "Aucun"
            if emoji_total > 18:
                emoji_preview += f" ... (+{emoji_total - 18})"

            emoji_btn = ui.Button(label="Tout visionner", style=discord.ButtonStyle.secondary)
            emoji_btn.callback = self._action_view_all_emojis
            container.add_item(
                ui.Section(
                    ui.TextDisplay(f"## 😀 Emojis ({emoji_total})"),
                    ui.TextDisplay(emoji_preview),
                    accessory=emoji_btn,
                )
            )

        banner_url = self._banner_url()
        if banner_url:
            try:
                gallery = ui.MediaGallery()
                gallery.add_item(media=banner_url, description=f"Banniere {self._kind_label()}")
                container.add_item(gallery)
            except Exception:
                pass

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
        container.add_item(ui.TextDisplay("## ⚙️ Rechercher"))

        mode_row = ui.ActionRow()
        mode_select = ui.Select(
            placeholder="Choisir un type de recherche...",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label="Serveur", value="guild", default=self.search_mode == "guild", emoji="🏠"),
                discord.SelectOption(label="Salon", value="channel", default=self.search_mode == "channel", emoji="📍"),
                discord.SelectOption(label="Rôle", value="role", default=self.search_mode == "role", emoji="🎭"),
                discord.SelectOption(label="Utilisateur", value="member", default=self.search_mode == "member", emoji="👤"),
            ],
        )

        async def mode_callback(interaction: discord.Interaction):
            picked = mode_select.values[0] if mode_select.values else "guild"
            self.search_mode = picked
            if picked == "guild":
                self.set_target("guild", self.guild)
            self.info_text = f"Mode de recherche : `{self._mode_display(picked)}`"
            await self.refresh_from_interaction(interaction)

        mode_select.callback = mode_callback
        mode_row.add_item(mode_select)
        container.add_item(mode_row)

        # Sélecteur ergonomique selon le mode.
        if self.search_mode == "channel":
            picker_row = ui.ActionRow()
            picker = ui.ChannelSelect(
                placeholder="Choisir un salon (texte, annonce, forum, vocal)...",
                min_values=1,
                max_values=1,
                channel_types=[
                    discord.ChannelType.text,
                    discord.ChannelType.news,
                    discord.ChannelType.forum,
                    discord.ChannelType.voice,
                    discord.ChannelType.stage_voice,
                ],
            )

            async def pick_channel(interaction: discord.Interaction):
                target = self._first_selected(interaction)
                if not isinstance(target, discord.abc.GuildChannel):
                    target_id = self._extract_selected_id(interaction)
                    target = self.guild.get_channel(target_id) if target_id else None
                if target is None:
                    return await interaction.response.send_message("❌ Aucun salon sélectionné.", ephemeral=True)
                self.set_target("channel", target)
                self.info_text = "Salon sélectionné."
                await self.refresh_from_interaction(interaction)

            picker.callback = pick_channel
            picker_row.add_item(picker)
            container.add_item(picker_row)

        elif self.search_mode == "role":
            picker_row = ui.ActionRow()
            picker = ui.RoleSelect(placeholder="Choisir un rôle...", min_values=1, max_values=1)

            async def pick_role(interaction: discord.Interaction):
                target = self._first_selected(interaction)
                if not isinstance(target, discord.Role):
                    target_id = self._extract_selected_id(interaction)
                    target = self.guild.get_role(target_id) if target_id else None
                if target is None:
                    return await interaction.response.send_message("❌ Aucun rôle sélectionné.", ephemeral=True)
                self.set_target("role", target)
                self.info_text = "Rôle sélectionné."
                await self.refresh_from_interaction(interaction)

            picker.callback = pick_role
            picker_row.add_item(picker)
            container.add_item(picker_row)

        elif self.search_mode == "member":
            picker_row = ui.ActionRow()
            picker = ui.UserSelect(placeholder="Choisir un utilisateur...", min_values=1, max_values=1)

            async def pick_user(interaction: discord.Interaction):
                target = self._first_selected(interaction)
                if not isinstance(target, discord.Member):
                    uid = getattr(target, "id", None)
                    if not isinstance(uid, int):
                        uid = self._extract_selected_id(interaction)
                    target = self.guild.get_member(uid) if uid else None
                    if target is None and uid:
                        try:
                            target = await self.guild.fetch_member(uid)
                        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                            target = None
                if target is None:
                    return await interaction.response.send_message("❌ Aucun utilisateur sélectionné.", ephemeral=True)
                self.set_target("member", target)
                await self.prepare_target_media()
                self.info_text = "Utilisateur sélectionné."
                await self.refresh_from_interaction(interaction)

            picker.callback = pick_user
            picker_row.add_item(picker)
            container.add_item(picker_row)

        if self.search_mode in {"channel", "role", "member"}:
            actions_row = ui.ActionRow()
            id_btn = ui.Button(label="Insérer un ID", style=discord.ButtonStyle.primary, emoji="🆔")

            async def id_callback(interaction: discord.Interaction):
                modal_mode = "user" if self.search_mode == "member" else self.search_mode
                await interaction.response.send_modal(IdModal(modal_mode, self._on_id_submit))

            id_btn.callback = id_callback
            actions_row.add_item(id_btn)
            container.add_item(actions_row)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    async def _on_id_submit(self, interaction: discord.Interaction, target) -> None:
        if isinstance(target, discord.abc.GuildChannel):
            self.set_target("channel", target)
            self.info_text = "Salon trouvé via ID."
        elif isinstance(target, discord.Role):
            self.set_target("role", target)
            self.info_text = "Rôle trouvé via ID."
        elif isinstance(target, discord.Member):
            self.set_target("member", target)
            await self.prepare_target_media()
            self.info_text = "Utilisateur trouvé via ID."
        else:
            await interaction.followup.send("❌ Type d'objet non supporté.", ephemeral=True)
            return

        await self.refresh_silent()
        await interaction.followup.send("✅ Résultat affiché.", ephemeral=True)

    async def refresh_silent(self) -> None:
        if self.message is None:
            return
        self._build()
        await self.message.edit(view=self, allowed_mentions=discord.AllowedMentions.none())

    async def refresh_from_interaction(self, interaction: discord.Interaction) -> None:
        self._build()
        await interaction.response.edit_message(view=self, allowed_mentions=discord.AllowedMentions.none())

    async def _action_view_all_emojis(self, interaction: discord.Interaction):
        if self.target_kind != "guild" or not isinstance(self.target_obj, discord.Guild):
            return await interaction.response.send_message("❌ Cette action est disponible uniquement sur une page serveur.", ephemeral=True)

        guild = self.target_obj
        if not guild.emojis:
            return await interaction.response.send_message("Aucun emoji sur ce serveur.", ephemeral=True)

        lines = [f"{idx + 1}. {str(emoji)} - `{emoji.name}` (`{emoji.id}`)" for idx, emoji in enumerate(guild.emojis)]
        header = f"😀 Emojis de **{guild.name}** ({len(guild.emojis)})\n"

        chunks: list[str] = []
        current = header
        for line in lines:
            candidate = f"{current}\n{line}" if current else line
            if len(candidate) > 1800:
                chunks.append(current)
                current = line
            else:
                current = candidate
        if current:
            chunks.append(current)

        await interaction.response.send_message(chunks[0], ephemeral=True)
        for extra in chunks[1:]:
            await interaction.followup.send(extra, ephemeral=True)


class Info(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="info", description="Affiche des informations (serveur/salon/rôle/utilisateur).")
    @app_commands.describe(query="ID, mention ou nom de serveur/salon/rôle/utilisateur")
    async def info(self, ctx: commands.Context, *, query: Optional[str] = None):
        if not ctx.guild or not isinstance(ctx.author, discord.Member):
            return await ctx.send("❌ Cette commande doit être utilisée sur un serveur.")

        view = InfoLayoutView(self, ctx.guild, ctx.author)

        if query:
            resolved = await view.resolve_query(query, preferred_mode="auto")
            if resolved is None:
                view.info_text = "❌ Aucun résultat trouvé. Utilisez le mode de recherche puis un sélecteur/ID."
            else:
                kind, obj = resolved
                view.set_target(kind, obj)
                await view.prepare_target_media()
                view.info_text = f"Résultat pour `{query}`"

            view._build()

        mention_query = bool(query and (re.search(r"<@!?\d+>", query) or re.search(r"<@&\d+>", query)))
        if ctx.interaction and mention_query:
            if not ctx.interaction.response.is_done():
                await ctx.interaction.response.send_message(view=view, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
                sent = await ctx.interaction.original_response()
            else:
                sent = await ctx.interaction.followup.send(view=view, ephemeral=True, wait=True, allowed_mentions=discord.AllowedMentions.none())
        else:
            sent = await ctx.send(view=view, allowed_mentions=discord.AllowedMentions.none())
        view.message = sent


async def setup(bot: commands.Bot):
    if bot.get_command("info"):
        bot.remove_command("info")
    await bot.add_cog(Info(bot))
