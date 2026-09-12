"""
COMMANDE WARNINFO - Consultation et gestion des avertissements
==============================================================
Intègre une pagination et un système de suppression natifs avec LayoutV2.
"""

from __future__ import annotations

import math
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
    print(f"{colors.get(level, '\033[0m')}[MOD-WARNINFO - {level}] {msg}\033[0m")

EMOJI_INFO = getattr(E, "LISTE", "ðŸ“‹")
EMOJI_SUCCESS = getattr(E, "VALIDE", getattr(E, "VALIDER", "âœ…"))
EMOJI_ERROR = getattr(E, "REFUS", getattr(E, "REFUSER", "âŒ"))
EMOJI_WARN = getattr(E, "ATTENTION", "âš ï¸")

db_warns = DataManager("staff/moderation/warns")

class WarnConfirmView(ui.LayoutView):
    def __init__(self, bot: commands.Bot, parent_view: "WarnInfoLayoutView", target_user: discord.abc.User, index: int):
        super().__init__(timeout=60)
        self.bot = bot
        self.parent_view = parent_view
        self.target_user = target_user
        self.index = index
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.parent_view.user.id:
            await interaction.response.send_message(f"{EMOJI_ERROR} Ce menu ne vous appartient pas.", ephemeral=False)
            return False
        return True

    def _build(self):
        self.clear_items()
        container = ui.Container(accent_color=discord.Color.red(), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {EMOJI_WARN} Confirmation Requise"))
        container.add_item(ui.TextDisplay(f"Es-tu sûr de vouloir supprimer définitivement l'avertissement **#{self.index + 1}** de {self.target_user.mention} ?"))
        
        row = ui.ActionRow()
        btn_confirm = ui.Button(label="Confirmer", style=discord.ButtonStyle.danger, emoji=getattr(E, "SUPPRIMER", "ðŸ—‘ï¸"))
        btn_confirm.callback = self.confirm_action
        row.add_item(btn_confirm)
        
        btn_cancel = ui.Button(label="Annuler", style=discord.ButtonStyle.secondary, emoji=getattr(E, "RETOUR", "â†©ï¸"))
        btn_cancel.callback = self.cancel_action
        row.add_item(btn_cancel)
        
        container.add_item(row)
        self.add_item(container)

    async def confirm_action(self, interaction: discord.Interaction):
        guild_id = self.parent_view.guild.id
        user_key = str(self.target_user.id)
        
        data = db_warns.load(guild_id) or {}
        user_warns = data.get(user_key, [])
        
        if len(user_warns) > self.index:
            user_warns.pop(self.index)
            if not user_warns:
                del data[user_key]
            else:
                data[user_key] = user_warns
            db_warns.save(guild_id, data)
            _log(f"Avertissement index {self.index} supprimé pour {user_key}.", "SUCCESS")
        
        self.parent_view.data_warns = user_warns
        self.parent_view._build()
        await interaction.response.edit_message(view=self.parent_view)

    async def cancel_action(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=self.parent_view)


class WarnInfoLayoutView(ui.LayoutView):
    def __init__(self, guild: discord.Guild, user: discord.abc.User, bot: commands.Bot, target_user: discord.abc.User, data_warns: list):
        super().__init__(timeout=180)
        self.guild = guild
        self.user = user
        self.bot = bot
        self.target_user = target_user
        self.data_warns = data_warns
        self.page = 0
        self.per_page = 5
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
        
        total_warns = len(self.data_warns)
        self.max_pages = max(1, math.ceil(total_warns / self.per_page))
        self.page = max(0, min(self.page, self.max_pages - 1))

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {EMOJI_INFO} Casier de {self.target_user.display_name}"))
        
        if total_warns == 0:
            container.add_item(ui.TextDisplay(f"{EMOJI_SUCCESS} {self.target_user.mention} possède un casier vierge."))
        else:
            start = self.page * self.per_page
            end = start + self.per_page
            content = f"{getattr(E, 'PROFIL', 'ðŸ‘¤')} **Utilisateur :** {self.target_user.mention}\n{getattr(E, 'GRAPHIQUE', 'ðŸ“Š')} **Total :** `{total_warns}` avertissement(s)\n\n"
            
            options = []
            for i, w in enumerate(self.data_warns[start:end]):
                real_index = start + i
                raison = w.get('raison', 'Aucune raison spécifiée')
                staff_nom = w.get('staff_name', 'Inconnu')
                timestamp = w.get('timestamp', 'Inconnue')
                
                content += f"**#{real_index + 1}** â€¢ Staff: **{staff_nom}** â€¢ {timestamp}\n```\n{raison}\n```\n"
                options.append(discord.SelectOption(label=f"Supprimer l'avertissement #{real_index + 1}", value=str(real_index), description=raison[:50]))
                
            content += f"-# Page {self.page + 1}/{self.max_pages}"
            container.add_item(ui.TextDisplay(content))
            
            select_row = ui.ActionRow()
            select = ui.Select(placeholder=f"{getattr(E, 'ERREUR', 'âŒ')} Sélectionner un avertissement à retirer...", options=options)
            select.callback = self.select_callback
            select_row.add_item(select)
            container.add_item(select_row)
            
            if self.max_pages > 1:
                nav_row = ui.ActionRow()
                btn_prev = ui.Button(label=getattr(E, "BACK", "â¬…ï¸"), style=discord.ButtonStyle.secondary, disabled=(self.page == 0))
                btn_prev.callback = self.prev_page
                nav_row.add_item(btn_prev)
                
                btn_next = ui.Button(label=getattr(E, "NEXT", "âž¡ï¸"), style=discord.ButtonStyle.secondary, disabled=(self.page >= self.max_pages - 1))
                btn_next.callback = self.next_page
                nav_row.add_item(btn_next)
                container.add_item(nav_row)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    async def select_callback(self, interaction: discord.Interaction):
        index_to_remove = int(interaction.data["values"][0])
        confirm_view = WarnConfirmView(self.bot, self, self.target_user, index_to_remove)
        await interaction.response.edit_message(view=confirm_view)

    async def prev_page(self, interaction: discord.Interaction):
        self.page -= 1
        self._build()
        await interaction.response.edit_message(view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.page += 1
        self._build()
        await interaction.response.edit_message(view=self)


class WarnInfo(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @perm_command(level=3)
    @commands.hybrid_command(name="warninfo", description="Consulter le casier judiciaire d'un membre")
    @app_commands.describe(utilisateur="Le membre à inspecter")
    async def warninfo(self, ctx: commands.Context, utilisateur: discord.User = None):
        if not ctx.guild:
            return

        if not await ensure_command_permission(ctx, command_name="warninfo"):
            return

        if utilisateur is None:
            return await ctx.send(f"{EMOJI_ERROR} Paramètre manquant. Usage : `{ctx.prefix}warninfo <@membre>`")

        data = db_warns.load(ctx.guild.id) or {}
        user_warns = data.get(str(utilisateur.id), [])

        view = WarnInfoLayoutView(ctx.guild, ctx.author, self.bot, utilisateur, user_warns)
        await ctx.send(view=view)

    @warninfo.error
    async def warninfo_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingRequiredArgument):
            msg = f"{EMOJI_ERROR} Paramètre Manquant.\nUsage : `{ctx.prefix}warninfo <@membre>`"
            await ctx.send(msg)
        else:
            _log(f"Erreur inattendue : {error}", "ERROR")
            traceback.print_exc()

async def setup(bot: commands.Bot):
    await bot.add_cog(WarnInfo(bot))
