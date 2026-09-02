"""
COMMANDE WARNLIST - Registre global du serveur
================================================
Affiche le palmarès complet via une pagination dynamique.
"""

from __future__ import annotations

import traceback

import discord
from discord import app_commands, ui
from discord.ext import commands

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
    print(f"{colors.get(level, '\033[0m')}[MOD-WARNLIST - {level}] {msg}\033[0m")

EMOJI_LIST = getattr(E, "LISTE", "ðŸ“‹")
EMOJI_SUCCESS = getattr(E, "VALIDE", getattr(E, "VALIDER", "âœ…"))
EMOJI_ERROR = getattr(E, "REFUS", getattr(E, "REFUSER", "âŒ"))

db_warns = DataManager("staff/moderation/warns")

class WarnListLayoutView(ui.LayoutView):
    def __init__(self, guild: discord.Guild, user: discord.abc.User, bot: commands.Bot, pages_content: list[str]):
        super().__init__(timeout=180)
        self.guild = guild
        self.user = user
        self.bot = bot
        self.pages_content = pages_content
        self.current_page = 0
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(f"{EMOJI_ERROR} Ce menu ne vous appartient pas.", ephemeral=False)
            return False
        return True

    def _build(self):
        self.clear_items()
        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.bot)
        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text") or ""
        total_pages = len(self.pages_content)

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {EMOJI_LIST} Liste des Avertissements"))
        
        content = self.pages_content[self.current_page]
        content += f"\n-# Page {self.current_page + 1}/{total_pages} - `/warninfo @Utilisateur`"
        container.add_item(ui.TextDisplay(content))

        if total_pages > 1:
            nav_row = ui.ActionRow()
            btn_prev = ui.Button(label=getattr(E, "BACK", "â¬…ï¸"), style=discord.ButtonStyle.secondary, disabled=(self.current_page == 0))
            btn_prev.callback = self.prev_page
            nav_row.add_item(btn_prev)
            
            btn_next = ui.Button(label=getattr(E, "NEXT", "âž¡ï¸"), style=discord.ButtonStyle.secondary, disabled=(self.current_page >= total_pages - 1))
            btn_next.callback = self.next_page
            nav_row.add_item(btn_next)
            container.add_item(nav_row)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    async def prev_page(self, interaction: discord.Interaction):
        self.current_page -= 1
        self._build()
        await interaction.response.edit_message(view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page += 1
        self._build()
        await interaction.response.edit_message(view=self)


class WarnList(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @perm_command(level=3)
    @commands.command(name="warnlist", description="Affiche le registre et le classement des avertissements du serveur")
    async def warnlist(self, ctx: commands.Context):
        if not ctx.guild:
            return

        if not await ensure_command_permission(ctx, command_name="warnlist"):
            return

        data = db_warns.load(ctx.guild.id) or {}
        
        all_warns = []
        user_counts = []
        
        for user_id, warns in data.items():
            if warns:
                user_counts.append((user_id, len(warns)))
                for w in warns:
                    w['cible_id'] = user_id
                    all_warns.append(w)

        if not all_warns:
            msg = f"{EMOJI_SUCCESS} âœ¨ Aucun avertissement n'est enregistré sur ce serveur."
            if ctx.interaction:
                return await ctx.interaction.response.send_message(msg, ephemeral=False)
            return await ctx.send(msg)

        # Les 3 derniers warns
        recent_warns = sorted(all_warns, key=lambda x: x.get('timestamp', ''), reverse=True)[:3]
        recent_text = "### ðŸ•’ 3 Derniers Avertissements\n"
        for w in recent_warns:
            cible_mention = f"<@{w['cible_id']}>"
            staff_mention = f"<@{w['staff_id']}>"
            date_str = w.get('timestamp', 'Inconnue').replace(' à ', ' - ')
            raison = w.get('raison', 'Aucune')
            recent_text += f"â€¢ [{date_str}] {cible_mention} sanctionné par {staff_mention} - `{raison}`\n"

        # Classement et pagination
        user_counts.sort(key=lambda x: x[1], reverse=True)
        pages_content = []
        
        for i in range(0, len(user_counts), 25):
            chunk = user_counts[i:i + 25]
            page_text = recent_text + f"\n### {getattr(E, 'CLASSEMENT', 'ðŸ†')} Classement\n"
            
            for index, (u_id, count) in enumerate(chunk, i + 1):
                member = ctx.guild.get_member(int(u_id))
                mention = member.mention if member else f"Utilisateur inconnu (`{u_id}`)"
                medal = "ðŸ¥‡" if index == 1 else "ðŸ¥ˆ" if index == 2 else "ðŸ¥‰" if index == 3 else f"`#{index}`"
                page_text += f"{medal} {mention} : **{count}** warn(s)\n"
            
            pages_content.append(page_text)

        view = WarnListLayoutView(ctx.guild, ctx.author, self.bot, pages_content)
        
        if ctx.interaction:
            if not ctx.interaction.response.is_done():
                await ctx.interaction.response.send_message(view=view, ephemeral=False)
            else:
                await ctx.interaction.followup.send(view=view, ephemeral=False)
        else:
            await ctx.send(view=view)

    @warnlist.error
    async def warnlist_error(self, ctx: commands.Context, error):
        _log(f"Erreur inattendue : {error}", "ERROR")
        traceback.print_exc()

async def setup(bot: commands.Bot):
    await bot.add_cog(WarnList(bot))
