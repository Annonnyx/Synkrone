"""
MODULE DICE (JEU DE DÉS) - VAX V3
================================
Gestionnaire de lancer de dés interactif utilisant l'architecture Layout V2,
la commande hybride `/dice`, la personnalisation dynamique via modale,
les retours persistants (sans messages éphémères), les variables globales de log,
les emojis centralisés et le respect strict des standards Vax v3.
"""

from __future__ import annotations

import math
import random
import traceback
from typing import Any, Optional

import discord
from discord import app_commands, ui
from discord.ext import commands

from utils.config_emoji import Emoji as E

try:
    from utils.config_theme import config_manager
except ImportError:
    config_manager = None

# ==============================================================================
# ------------------------------ DÉBOGAGE GLOBAL -------------------------------
# ==============================================================================
DEBUG_MODE = True
DEBUG_ERRORS_ONLY = True


def debug_log(message: str, level: str = "INFO") -> None:
    """Affiche des logs formatés dans la console selon le niveau de sévérité."""
    if DEBUG_ERRORS_ONLY and level.upper() != "ERROR":
        return
    if not DEBUG_MODE and not DEBUG_ERRORS_ONLY:
        return

    colors = {
        "INFO": "\033[94m",
        "SUCCESS": "\033[92m",
        "ERROR": "\033[91m",
        "WARNING": "\033[93m",
    }
    reset = "\033[0m"
    color = colors.get(level.upper(), "\033[97m")
    print(f"{color}[DEBUG - Dice] [{level.upper()}] {message}{reset}")


# ==============================================================================
# --------------------------- CONFIGURATION DU THÈME ---------------------------
# ==============================================================================
def get_theme_values(guild: Optional[discord.Guild], user: discord.abc.User, bot: commands.Bot) -> tuple[int, str]:
    if config_manager:
        try:
            theme = config_manager.get_layout_v2_theme(
                guild.id if guild else None,
                guild,
                user,
                bot,
            )
            return int(theme.get("color", discord.Color.blurple().value)), str(theme.get("footer_text") or "")
        except Exception as e:
            debug_log(f"Erreur get_theme_values: {e}", "ERROR")
            traceback.print_exc()
    return discord.Color.blurple().value, "Module Dice"


# ==============================================================================
# ---------------------------------- MODALE ------------------------------------
# ==============================================================================
class CustomDiceModal(ui.Modal):
    nb_des_input = ui.TextInput(
        label="Nombre de dés",
        placeholder="Ex: 5",
        default="1",
        min_length=1,
        max_length=3,
        required=True
    )
    nb_faces_input = ui.TextInput(
        label="Nombre de faces",
        placeholder="Ex: 100",
        default="20",
        min_length=1,
        max_length=5,
        required=True
    )

    def __init__(self, parent_view: "DiceView"):
        super().__init__(title=f"{E.MODIFIER} Dés sur mesure")
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            if not self.nb_des_input.value.isdigit() or not self.nb_faces_input.value.isdigit():
                await interaction.response.send_message(f"{E.ERREUR} Nombres entiers uniquement.", ephemeral=False)
                return
            
            nb_des = int(self.nb_des_input.value)
            nb_faces = int(self.nb_faces_input.value)

            if nb_des <= 0 or nb_faces <= 1:
                await interaction.response.send_message(f"{E.ERREUR} Il faut au moins 1 dé et 2 faces.", ephemeral=False)
                return
            
            if nb_des > 100:
                await interaction.response.send_message(f"{E.ERREUR} Limite de sécurité : 100 dés maximum.", ephemeral=False)
                return

            self.parent_view.nb_des = nb_des
            self.parent_view.nb_faces = nb_faces
            self.parent_view.is_dirty = True
            
            debug_log(f"Dés sur mesure configurés par {interaction.user} : {nb_des}d{nb_faces}", "SUCCESS")
            await self.parent_view.update_ui(interaction)
        except Exception as e:
            debug_log(f"Erreur CustomDiceModal: {e}", "ERROR")
            traceback.print_exc()


# ==============================================================================
# ------------------------- VUE LAYOUT V2 DES DÉS ------------------------------
# ==============================================================================
class DiceView(ui.LayoutView):
    def __init__(self, ctx: commands.Context, bot: commands.Bot):
        super().__init__(timeout=600)
        self.ctx = ctx
        self.bot = bot
        
        self.nb_des = 1
        self.nb_faces = 6
        self.results = []
        self.is_dirty = False 
        
        self.roll_dice()
        self._build_layout()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(f"{E.ERREUR} Ce menu ne vous appartient pas.", ephemeral=False)
            return False
        return True

    def roll_dice(self) -> None:
        self.results = [random.randint(1, self.nb_faces) for _ in range(self.nb_des)]
        self.is_dirty = False
        debug_log(f"Lancer de dés effectué : {self.nb_des}d{self.nb_faces} -> Somme: {sum(self.results)}", "INFO")

    def _build_layout(self) -> None:
        try:
            self.clear_items()

            guild = self.ctx.guild
            color, footer = get_theme_values(guild, self.ctx.author, self.bot)

            container = ui.Container(accent_color=discord.Color(color), spoiler=False)

            # En-titre & Description
            if self.is_dirty:
                title = f"{E.MODIFIER} Configuration en attente..."
                desc = (
                    f"> **Jet prévu :** `{self.nb_des}d{self.nb_faces}`\n"
                    f"> \n"
                    f"> {E.TEMPS} *Les dés sont dans votre main...*\n"
                    f"> 👇 *Cliquez sur **Lancer** pour les jeter !*"
                )
            else:
                title = f"{E.DES} Résultat du lancer"
                total = sum(self.results)
                if len(self.results) > 20:
                    res_str = f"` {', '.join(map(str, self.results[:20]))} ... ` *(+ {len(self.results)-20} autres)*"
                else:
                    res_str = " ".join([f"` {r} `" for r in self.results])
                
                desc = (
                    f"> **Tirage :** `{self.nb_des}d{self.nb_faces}`\n"
                    f"> **Détails :** {res_str}\n"
                    f"> \n"
                    f"> # {E.CIBLE} Total : {total}"
                )

            container.add_item(ui.TextDisplay(f"## {title}"))
            container.add_item(ui.TextDisplay(desc))
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

            # Sélecteur de quantité de dés (1 à 6)
            count_options = [
                discord.SelectOption(label=f"{i} Dé{'s' if i > 1 else ''}", value=str(i), emoji=E.DES, default=(self.nb_des == i)) 
                for i in range(1, 7)
            ]
            count_select = ui.Select(placeholder="Quantité de dés...", options=count_options)

            async def count_callback(interaction: discord.Interaction) -> None:
                try:
                    self.nb_des = int(count_select.values[0])
                    self.is_dirty = True
                    await self.update_ui(interaction)
                except Exception as e:
                    debug_log(f"Erreur count_callback: {e}", "ERROR")
                    traceback.print_exc()

            count_select.callback = count_callback
            row_count = ui.ActionRow()
            row_count.add_item(count_select)
            container.add_item(row_count)

            # Sélecteur de types de faces (4, 6, 8, 10, 12, 20, 100)
            faces_list = [4, 6, 8, 10, 12, 20, 100]
            faces_options = [
                discord.SelectOption(label=f"{f} Faces", value=str(f), emoji=E.DIAMANT, default=(self.nb_faces == f)) 
                for f in faces_list
            ]
            faces_select = ui.Select(placeholder="Type de dé...", options=faces_options)

            async def faces_callback(interaction: discord.Interaction) -> None:
                try:
                    self.nb_faces = int(faces_select.values[0])
                    self.is_dirty = True
                    await self.update_ui(interaction)
                except Exception as e:
                    debug_log(f"Erreur faces_callback: {e}", "ERROR")
                    traceback.print_exc()

            faces_select.callback = faces_callback
            row_faces = ui.ActionRow()
            row_faces.add_item(faces_select)
            container.add_item(row_faces)

            # Boutons d'action (Lancer/Relancer & Custom)
            action_row = ui.ActionRow()
            
            btn_label = "Lancer" if self.is_dirty else "Relancer"
            btn_style = discord.ButtonStyle.primary if self.is_dirty else discord.ButtonStyle.success
            btn_emoji = E.DES if self.is_dirty else E.RAFRAICHIR

            roll_btn = ui.Button(label=btn_label, style=btn_style, emoji=btn_emoji)
            async def roll_callback(interaction: discord.Interaction) -> None:
                try:
                    self.roll_dice()
                    await self.update_ui(interaction)
                except Exception as e:
                    debug_log(f"Erreur roll_callback: {e}", "ERROR")
                    traceback.print_exc()
            roll_btn.callback = roll_callback

            custom_btn = ui.Button(label="Custom", style=discord.ButtonStyle.secondary, emoji=E.MODIFIER)
            async def custom_callback(interaction: discord.Interaction) -> None:
                try:
                    await interaction.response.send_modal(CustomDiceModal(self))
                except Exception as e:
                    debug_log(f"Erreur custom_callback: {e}", "ERROR")
                    traceback.print_exc()
            custom_btn.callback = custom_callback

            action_row.add_item(roll_btn)
            action_row.add_item(custom_btn)
            container.add_item(action_row)

            if footer:
                container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
                container.add_item(ui.TextDisplay(footer))

            self.add_item(container)
        except Exception as e:
            debug_log(f"Erreur critique _build_layout DiceView: {e}", "ERROR")
            traceback.print_exc()

    async def update_ui(self, interaction: discord.Interaction) -> None:
        try:
            self._build_layout()
            if interaction.response.is_done():
                await interaction.edit_original_response(view=self)
            else:
                await interaction.response.edit_message(view=self)
        except Exception as e:
            debug_log(f"Erreur update_ui DiceView: {e}", "ERROR")
            traceback.print_exc()


# ==============================================================================
# --------------------------- COG PRINCIPAL ------------------------------------
# ==============================================================================
class Dice(commands.Cog):
    """🎲 Module Dice — Lancer personnalisable (Layout V2)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        debug_log("Cog Dice initialisé avec succès.", "SUCCESS")

    def cog_unload(self) -> None:
        debug_log("Cog Dice déchargé.", "WARNING")

    @commands.hybrid_command(
        name="dice",
        description="Lance un ou plusieurs dés personnalisables (1d6 par défaut)."
    )
    async def dice(self, ctx: commands.Context) -> None:
        debug_log(f"Commande /dice invoquée par {ctx.author} ({ctx.author.id})", "INFO")
        try:
            view = DiceView(ctx, self.bot)
            if ctx.interaction:
                await ctx.send(view=view, ephemeral=False)
            else:
                await ctx.reply(view=view, mention_author=False)
        except Exception as exc:
            debug_log(f"Erreur lors de l'exécution de la commande /dice : {exc}", "ERROR")
            traceback.print_exc()
            await ctx.send(f"{E.ERREUR} Une erreur est survenue lors de l'ouverture du gestionnaire de dés.")


async def setup(bot: commands.Bot) -> None:
    if bot.get_command("dice"):
        bot.remove_command("dice")
    await bot.add_cog(Dice(bot))
    debug_log("Cog Dice enregistré et chargé avec succès.", "SUCCESS")