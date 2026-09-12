"""
COMMANDE MUTELIST - Consultation et levée interactive des sanctions
=================================================================
"""

from __future__ import annotations

import math
import discord
from discord import ui
from discord.ext import commands, tasks

from utils.config_data import DataManager
from utils.config_emoji import Emoji as E
from utils.config_perm import ensure_command_permission, perm_command
from utils.config_theme import config_manager

DEBUG_LOGS = True
ERROR_LOGS = True


def _log(msg: str, level: str = "INFO"):
    if level == "DEBUG" and not DEBUG_LOGS:
        return
    if level == "ERROR" and not ERROR_LOGS:
        return
    colors = {"INFO": "\033[94m", "SUCCESS": "\033[92m", "ERROR": "\033[91m", "WARN": "\033[93m"}
    print(f"{colors.get(level, '\033[0m')}[MUTELIST-{level}] {msg}\033[0m")


EMOJI_LIST = getattr(E, "LISTE", getattr(E, "ATTENTION", "ðŸ“œ"))
EMOJI_SUCCESS = getattr(E, "VALIDE", getattr(E, "VALIDER", "âœ…"))
EMOJI_ERROR = getattr(E, "REFUS", getattr(E, "REFUSER", "âŒ"))
ALERT_EMOJI = getattr(E, "ATTENTION", "âš ï¸")

ITEMS_PER_PAGE = 25


class MuteListView(ui.LayoutView):
    def __init__(self, ctx: commands.Context, entries: list[tuple[str, dict]], bot: commands.Bot):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.entries = entries
        self.bot = bot
        self.current_page = 0
        self.selected_key: str | None = None
        self.data_manager_global = DataManager("staff/moderation/mute_global")
        self.data_manager_local = DataManager("staff/moderation/mute_local")
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(f"{EMOJI_ERROR} Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        return True

    def _build(self):
        self.clear_items()

        theme = config_manager.get_layout_v2_theme(
            self.ctx.guild.id, self.ctx.guild, self.ctx.author, self.bot, force_global=(self.ctx.guild is None)
        )
        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text") or ""

        pages_count = max(1, math.ceil(len(self.entries) / ITEMS_PER_PAGE))
        if self.current_page >= pages_count:
            self.current_page = pages_count - 1

        start_idx = self.current_page * ITEMS_PER_PAGE
        end_idx = min(start_idx + ITEMS_PER_PAGE, len(self.entries))
        page_entries = self.entries[start_idx:end_idx]

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {EMOJI_LIST} Registre Unifie des Sanctions Mute"))

        if self.selected_key:
            target_data = next((data for key, data in self.entries if key == self.selected_key), {})
            user_id = int(target_data.get("user_id", 0) or 0)
            member = self.ctx.guild.get_member(user_id) if self.ctx.guild else None
            target_name = member.mention if member else target_data.get("display_name", f"ID: {user_id}")
            sanction_type = str(target_data.get("sanction_type", "LOCAL")).upper()

            container.add_item(
                ui.TextDisplay(
                    f"### {ALERT_EMOJI} Confirmation de levee\n"
                    f"Voulez-vous vraiment lever la sanction **{sanction_type}** de {target_name} ?"
                )
            )

            confirm_row = ui.ActionRow()
            yes_btn = ui.Button(label="Confirmer", style=discord.ButtonStyle.danger, emoji="âœ…")
            yes_btn.callback = self.confirm_unmute
            confirm_row.add_item(yes_btn)

            no_btn = ui.Button(label="Annuler", style=discord.ButtonStyle.secondary, emoji="â†©ï¸")
            no_btn.callback = self.cancel_unmute
            confirm_row.add_item(no_btn)
            container.add_item(confirm_row)
        else:
            if not self.entries:
                container.add_item(ui.TextDisplay("Aucune sanction mute active enregistree sur le serveur."))
            else:
                description = f"**Total sanctions actives :** `{len(self.entries)}` (Page {self.current_page + 1}/{pages_count})\n\n"
                for key, data in page_entries:
                    user_id = int(data.get("user_id", 0) or 0)
                    member = self.ctx.guild.get_member(user_id) if self.ctx.guild else None
                    name = member.display_name if member else data.get("display_name", f"ID: {user_id}")
                    sanction_type = str(data.get("sanction_type", "LOCAL")).upper()
                    reason = data.get("reason", "Système") or "Système"
                    description += f"â€¢ **{name}** (`{user_id}`) [{sanction_type}]\n  â”” ðŸ“ *{reason}*\n"

                container.add_item(ui.TextDisplay(description))

                select_options = [
                    discord.SelectOption(
                        label=f"{(self.ctx.guild.get_member(int(data.get('user_id', 0) or 0)).display_name if self.ctx.guild and self.ctx.guild.get_member(int(data.get('user_id', 0) or 0)) else data.get('display_name', f'ID: {data.get('user_id', 0)}'))}"[:100],
                        value=key,
                        description=f"ID: {data.get('user_id', 0)} | Type: {str(data.get('sanction_type', 'LOCAL')).upper()}"[:100],
                        emoji="ðŸ”Š",
                    )
                    for key, data in page_entries
                ]

                if select_options:
                    select = ui.Select(
                        placeholder="Selectionner un membre a unmute...",
                        min_values=1,
                        max_values=1,
                        options=select_options,
                    )
                    select.callback = self.select_sanction_callback
                    select_row = ui.ActionRow()
                    select_row.add_item(select)
                    container.add_item(select_row)

                if pages_count > 1:
                    nav_row = ui.ActionRow()
                    prev_btn = ui.Button(label="â—€ Precedent", style=discord.ButtonStyle.secondary, disabled=(self.current_page == 0))
                    prev_btn.callback = self.prev_page
                    nav_row.add_item(prev_btn)

                    page_indicator = ui.Button(
                        label=f"Page {self.current_page + 1}/{pages_count}",
                        style=discord.ButtonStyle.secondary,
                        disabled=True,
                    )
                    nav_row.add_item(page_indicator)

                    next_btn = ui.Button(
                        label="Suivant â–¶",
                        style=discord.ButtonStyle.secondary,
                        disabled=(self.current_page >= pages_count - 1),
                    )
                    next_btn.callback = self.next_page
                    nav_row.add_item(next_btn)
                    container.add_item(nav_row)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    async def prev_page(self, interaction: discord.Interaction):
        if self.current_page > 0:
            self.current_page -= 1
            self._build()
            await interaction.response.edit_message(view=self)

    async def next_page(self, interaction: discord.Interaction):
        pages_count = max(1, math.ceil(len(self.entries) / ITEMS_PER_PAGE))
        if self.current_page < pages_count - 1:
            self.current_page += 1
            self._build()
            await interaction.response.edit_message(view=self)

    async def select_sanction_callback(self, interaction: discord.Interaction):
        selected_key = interaction.data.get("values", [None])[0]
        if not selected_key:
            return
        self.selected_key = selected_key
        self._build()
        await interaction.response.edit_message(view=self)

    async def cancel_unmute(self, interaction: discord.Interaction):
        self.selected_key = None
        self._build()
        await interaction.response.edit_message(view=self)

    async def confirm_unmute(self, interaction: discord.Interaction):
        key = self.selected_key
        if not key:
            return

        try:
            dg = self.data_manager_global.load(self.ctx.guild.id) or {}
            dl = self.data_manager_local.load(self.ctx.guild.id) or {}
        except Exception as e:
            _log(f"Erreur lecture stockages mutelist: {e}", "ERROR")
            dg, dl = {}, {}

        feedback = ""
        info = None
        is_global = False

        if key in dg:
            info = dg.pop(key)
            is_global = True
            self.data_manager_global.save(self.ctx.guild.id, dg)
        elif key in dl:
            info = dl.pop(key)
            self.data_manager_local.save(self.ctx.guild.id, dl)

        if not info:
            feedback = f"{EMOJI_ERROR} Sanction introuvable: entree deja retiree de la base locale."
            self.selected_key = None
            self.entries = self.ctx.cog._build_combined_entries(self.ctx.guild.id)
            self._build()
            await interaction.response.edit_message(content=feedback, view=self)
            return

        user_id = int(info.get("user_id", 0) or 0)
        member = self.ctx.guild.get_member(user_id)

        try:
            if is_global:
                role = discord.utils.get(self.ctx.guild.roles, name="ðŸ¤«â”‚ð‘´ð’–ð’†ð’•")
                if member and role and role in member.roles:
                    await member.remove_roles(role, reason=f"Unmute via mutelist par {self.ctx.author}")
                feedback = f"{EMOJI_SUCCESS} Sanction globale levee pour l'utilisateur `{user_id}`."
            else:
                chan_id = info.get("channel_id")
                channel = self.ctx.guild.get_channel(int(chan_id)) if chan_id else None
                if member and channel:
                    await channel.set_permissions(member, overwrite=None, reason=f"Unmute local via mutelist par {self.ctx.author}")
                feedback = f"{EMOJI_SUCCESS} Sanction locale levee pour l'utilisateur `{user_id}`."
        except discord.Forbidden:
            feedback = f"{EMOJI_ERROR} Action refusee: permissions manquantes ou hierarchie insuffisante."
        except Exception as e:
            feedback = f"{EMOJI_ERROR} Erreur lors de la levee de sanction: {e}"

        self.entries = self.ctx.cog._build_combined_entries(self.ctx.guild.id)
        self.selected_key = None
        self._build()
        await interaction.response.edit_message(content=feedback, view=self)


class MuteList(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data_manager_global = DataManager("staff/moderation/mute_global")
        self.data_manager_local = DataManager("staff/moderation/mute_local")
        self.check_mutes.start()

    def cog_unload(self):
        self.check_mutes.cancel()

    def _build_combined_entries(self, guild_id: int) -> list[tuple[str, dict]]:
        try:
            dg = self.data_manager_global.load(guild_id) or {}
            dl = self.data_manager_local.load(guild_id) or {}
        except Exception:
            dg, dl = {}, {}

        entries: list[tuple[str, dict]] = []
        for key, value in dg.items():
            item = dict(value)
            item["sanction_type"] = "global"
            entries.append((str(key), item))

        for key, value in dl.items():
            item = dict(value)
            item["sanction_type"] = "local"
            entries.append((str(key), item))

        entries.sort(key=lambda entry: (str(entry[1].get("sanction_type", "")), str(entry[1].get("user_id", ""))))
        return entries

    async def _send_fallback(self, ctx: commands.Context, title: str, description: str, color: int = 0xED4245):
        guild = ctx.guild
        guild_id = guild.id if guild else None
        theme = config_manager.get_layout_v2_theme(guild_id, guild, ctx.author, self.bot, force_global=(guild is None))
        footer_text = theme.get("footer_text", "")
        view = ui.LayoutView(timeout=15)
        container = ui.Container(accent_color=discord.Color(color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {EMOJI_ERROR} {title}"))
        container.add_item(ui.TextDisplay(description))
        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))
        view.add_item(container)
        await ctx.send(view=view)

    @tasks.loop(seconds=30)
    async def check_mutes(self):
        now = discord.utils.utcnow().timestamp()
        for guild in self.bot.guilds:
            try:
                # Synchronisation & nettoyage global
                dg = self.data_manager_global.load(guild.id) or {}
                to_remove_g = []
                for k, v in dg.items():
                    exp = v.get("expires_at", 0)
                    if exp is None:
                        to_remove_g.append(k)
                        continue
                    if exp != 9999999999 and now >= exp:
                        to_remove_g.append(k)
                        member = guild.get_member(v.get("user_id"))
                        role = discord.utils.get(guild.roles, name="ðŸ¤«â”‚ð‘´ð’–ð’†ð’•")
                        if member and role:
                            try:
                                await member.remove_roles(role)
                            except Exception:
                                pass
                if to_remove_g:
                    for k in to_remove_g:
                        dg.pop(k)
                    self.data_manager_global.save(guild.id, dg)

                # Nettoyage local
                dl = self.data_manager_local.load(guild.id) or {}
                to_remove_l = []
                for k, v in dl.items():
                    exp = v.get("expires_at", 0)
                    if exp is None:
                        to_remove_l.append(k)
                        continue
                    if exp != 9999999999 and now >= exp:
                        to_remove_l.append(k)
                        member = guild.get_member(v.get("user_id"))
                        channel = guild.get_channel(v.get("channel_id"))
                        if member and channel:
                            try:
                                await channel.set_permissions(member, overwrite=None)
                            except Exception:
                                pass
                if to_remove_l:
                    for k in to_remove_l:
                        dl.pop(k)
                    self.data_manager_local.save(guild.id, dl)

            except Exception as e:
                if ERROR_LOGS:
                    _log(f"Erreur tâche d'arrière-plan Guild {guild.id}: {e}", "ERROR")

    @perm_command(level=2)
    @commands.hybrid_command(name="mutelist", description="ðŸ“œ Affiche la liste unifiee des sanctions mute actives.")
    async def mutelist(self, ctx: commands.Context):
        if not ctx.guild:
            return await self._send_fallback(ctx, "Action impossible", "Cette commande doit etre utilisee sur un serveur.")

        if not await ensure_command_permission(ctx, command_name="mutelist"):
            return

        entries = self._build_combined_entries(ctx.guild.id)
        if not entries:
            return await self._send_fallback(ctx, "Registre vide", "Aucune sanction mute active enregistree.", color=0x57F287)

        view = MuteListView(ctx, entries, self.bot)
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(MuteList(bot))
