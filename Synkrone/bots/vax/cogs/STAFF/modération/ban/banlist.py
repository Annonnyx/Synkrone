"""
COGNITIVE MODULE - Banlist (Registre des bannissements)
======================================================
Registre unifié interactif (25 par page) avec sélecteur et boutons de confirmation intégrés au Layout V2.
"""

from __future__ import annotations

import math

import discord
from discord import ui
from discord.ext import commands

from utils.config_data import DataManager
from utils.config_emoji import Emoji as E
from utils.config_perm import ensure_command_permission, perm_command
from utils.config_theme import config_manager

# --- CONFIGURATION DES LOGS ---
DEBUG_MODE = True
ERROR_LOGS_ONLY = False
ALERT_EMOJI = getattr(E, "ATTENTION", "âš ï¸")
EMOJI_ERROR = getattr(E, "REFUS", getattr(E, "REFUSER", "âŒ"))
EMOJI_SUCCESS = getattr(E, "VALIDE", getattr(E, "VALIDER", "âœ…"))

ITEMS_PER_PAGE = 25


class BanManagerView(ui.LayoutView):
    def __init__(self, ctx: commands.Context, entries: list[tuple[str, dict]]):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.entries = entries
        self.current_page = 0
        self.selected_uid: str | None = None
        self.db = DataManager("staff/moderation/banlist_serveur")
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(f"{EMOJI_ERROR} Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        return True

    def _build(self):
        self.clear_items()
        theme = config_manager.get_layout_v2_theme(self.ctx.guild.id, self.ctx.guild, self.ctx.user if hasattr(self.ctx, 'user') else self.ctx.author, self.ctx.bot)
        color = int(theme.get("color", 0x5865F2))
        footer_text = theme.get("footer_text", "")

        pages_count = max(1, math.ceil(len(self.entries) / ITEMS_PER_PAGE))
        if self.current_page >= pages_count:
            self.current_page = pages_count - 1

        start_idx = self.current_page * ITEMS_PER_PAGE
        end_idx = min(start_idx + ITEMS_PER_PAGE, len(self.entries))
        page_entries = self.entries[start_idx:end_idx]

        container = ui.Container(accent_color=discord.Color(color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {getattr(E, 'PROFIL', 'ðŸ‘¤')} Registre Unifie des Bannissements"))

        if self.selected_uid:
            target_data = next((data for uid, data in self.entries if uid == self.selected_uid), {})
            target_name = target_data.get("Nom complet", self.selected_uid)
            
            container.add_item(ui.TextDisplay(f"### {ALERT_EMOJI} Confirmation de Debannissement\nVoulez-vous vraiment debannir **{target_name}** (`{self.selected_uid}`) du serveur ?"))

            confirm_row = ui.ActionRow()
            yes_btn = ui.Button(label="Confirmer", style=discord.ButtonStyle.danger, emoji="âœ…")
            yes_btn.callback = self.confirm_unban
            confirm_row.add_item(yes_btn)

            no_btn = ui.Button(label="Annuler", style=discord.ButtonStyle.secondary, emoji="â†©ï¸")
            no_btn.callback = self.cancel_unban
            confirm_row.add_item(no_btn)
            container.add_item(confirm_row)
        else:
            description = f"**Total banni(s) :** `{len(self.entries)}` (Page {self.current_page + 1}/{pages_count})\n\n"
            for uid, data in page_entries:
                b_type = data.get("Type", "BAN").upper()
                name = data.get("Nom complet", "Inconnu")
                mod = data.get("Modérateur", "Système") or "Système"
                reason = data.get("Raison", "Système") or "Système"
                description += f"â€¢ **{name}** (`{uid}`) [{b_type}]\n  â”” {getattr(E, 'AUTORITE', 'ðŸ‘®')} `{mod}` | {getattr(E, 'MEMO', 'ðŸ“')} *{reason}*\n"

            container.add_item(ui.TextDisplay(description))

            if page_entries:
                select_options = [
                    discord.SelectOption(
                        label=f"{data.get('Nom complet', uid)}"[:100],
                        value=uid,
                        description=f"ID: {uid} | Type: {data.get('Type', 'BAN')}"[:100],
                        emoji=getattr(E, 'RAZ', 'â™»ï¸')
                    )
                    for uid, data in page_entries
                ]
                select = ui.Select(placeholder=f"{getattr(E, 'RECHERCHE', 'ðŸ”')} Sélectionner un membre à débannir...", min_values=1, max_values=1, options=select_options)
                select.callback = self.select_member_callback
                select_row = ui.ActionRow()
                select_row.add_item(select)
                container.add_item(select_row)

            if pages_count > 1:
                nav_row = ui.ActionRow()
                prev_btn = ui.Button(label="â—€ Précédent", style=discord.ButtonStyle.secondary, disabled=(self.current_page == 0))
                prev_btn.callback = self.prev_page
                nav_row.add_item(prev_btn)

                page_indicator = ui.Button(label=f"Page {self.current_page + 1}/{pages_count}", style=discord.ButtonStyle.secondary, disabled=True)
                nav_row.add_item(page_indicator)

                next_btn = ui.Button(label="Suivant â–¶", style=discord.ButtonStyle.secondary, disabled=(self.current_page >= pages_count - 1))
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
        pages_count = math.ceil(len(self.entries) / ITEMS_PER_PAGE)
        if self.current_page < pages_count - 1:
            self.current_page += 1
            self._build()
            await interaction.response.edit_message(view=self)

    async def select_member_callback(self, interaction: discord.Interaction):
        selected_uid = interaction.data.get("values", [None])[0]
        if not selected_uid:
            return
        self.selected_uid = selected_uid
        self._build()
        await interaction.response.edit_message(view=self)

    async def cancel_unban(self, interaction: discord.Interaction):
        self.selected_uid = None
        self._build()
        await interaction.response.edit_message(view=self)

    async def confirm_unban(self, interaction: discord.Interaction):
        uid_to_unban = self.selected_uid
        if not uid_to_unban:
            return

        bans = self.db.load(self.ctx.guild.id) or {}
        feedback = ""
        try:
            user = await self.ctx.bot.fetch_user(int(uid_to_unban))
            try:
                await self.ctx.guild.fetch_ban(discord.Object(id=int(uid_to_unban)))
            except discord.NotFound:
                bans.pop(uid_to_unban, None)
                self.db.save(self.ctx.guild.id, bans)
                self.entries = list(bans.items())
                self.selected_uid = None
                self._build()
                feedback = f"{ALERT_EMOJI} Utilisateur non banni: entree retiree du registre local."
                await interaction.response.edit_message(content=feedback, view=self)
                return

            await self.ctx.guild.unban(user, reason=f"Débannissement via banlist par {self.ctx.author}")
            feedback = f"{EMOJI_SUCCESS} {user} a ete debanni avec succes."
        except discord.Forbidden:
            feedback = f"{EMOJI_ERROR} Debannissement refuse: permissions manquantes ou role superieur."
            await interaction.response.edit_message(content=feedback, view=self)
            return
        except Exception as e:
            feedback = f"{EMOJI_ERROR} Erreur de debannissement: {e}"
            await interaction.response.edit_message(content=feedback, view=self)
            return

        bans.pop(uid_to_unban, None)
        self.db.save(self.ctx.guild.id, bans)

        if DEBUG_MODE and not ERROR_LOGS_ONLY:
            print(f"\033[32m[SUCCÈS UNBAN BANLIST] {uid_to_unban} débanni par {self.ctx.author}\033[0m")

        self.entries = list(bans.items())
        self.selected_uid = None
        self._build()
        await interaction.response.edit_message(content=feedback, view=self)


class Banlist(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = DataManager("staff/moderation/banlist_serveur")

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

    @perm_command(level=2)
    @commands.command(name="banlist", description="Affiche le registre unifié (25/page) de tous les bannis du serveur.")
    async def banlist(self, ctx: commands.Context):
        if not ctx.guild:
            return await self._send_fallback(ctx, "Action impossible", "Cette commande doit être utilisée sur un serveur.")

        if not await ensure_command_permission(ctx, command_name="banlist"):
            return

        bans_dict = self.db.load(ctx.guild.id) or {}

        try:
            async for ban_entry in ctx.guild.bans():
                uid_str = str(ban_entry.user.id)
                if uid_str not in bans_dict:
                    bans_dict[uid_str] = {
                        "Nom complet": str(ban_entry.user),
                        "Raison": ban_entry.reason or "Système",
                        "Date": "Inconnue",
                        "Heure": "--:--",
                        "Modérateur": "Système",
                        "Type": "BANNISSEMENT GLOBAL"
                    }
                else:
                    if not bans_dict[uid_str].get("Raison"):
                        bans_dict[uid_str]["Raison"] = "Système"
                    if not bans_dict[uid_str].get("Modérateur"):
                        bans_dict[uid_str]["Modérateur"] = "Système"
            self.db.save(ctx.guild.id, bans_dict)
        except Exception as e:
            if DEBUG_MODE:
                print(f"\033[33m[AVERTISSEMENT BANLIST] Sync API impossible: {e}\033[0m")

        if not bans_dict:
            return await self._send_fallback(ctx, "Registre vide", "Aucun banni enregistré dans le registre.", color=0x57F287)

        entries = list(bans_dict.items())
        view = BanManagerView(ctx, entries)
        await ctx.send(view=view)

        if DEBUG_MODE and not ERROR_LOGS_ONLY:
            print(f"\033[34m[INFO BANLIST] Affichage de la banlist unifiée pour {ctx.guild.name}\033[0m")


async def setup(bot: commands.Bot):
    await bot.add_cog(Banlist(bot))
