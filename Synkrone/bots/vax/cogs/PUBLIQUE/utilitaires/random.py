"""
MODULE RANDOM VAX V3
====================
Outils aléatoires (8-Ball, Rate, Tirage au sort) utilisant l'architecture Layout V2,
un sélecteur en haut pour changer de menu, des boutons d'actions replacés au-dessus,
des logs colorés et un respect strict des standards Vax v3.
"""

from __future__ import annotations

import random
import traceback
from typing import Optional

import discord
from discord import ui
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
    print(f"{color}[DEBUG - Random] [{level.upper()}] {message}{reset}")


# ==============================================================================
# --------------------------- FONCTIONS UTILITAIRES ----------------------------
# ==============================================================================
def get_rating_emoji(score: float) -> str:
    if score < 2:
        return "😵"
    if score < 4:
        return "😕"
    if score < 6:
        return "🙂"
    if score < 8:
        return "😎"
    if score < 9.5:
        return "🔥"
    return "🏆"


def get_ascii_bar(score: float) -> str:
    filled = max(0, min(10, int(round(score))))
    empty = 10 - filled
    return "▰" * filled + "▱" * empty


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
        except Exception:
            pass
    return discord.Color.blurple().value, "Outils aléatoires"


# ==============================================================================
# ---------------------------------- MODALES -----------------------------------
# ==============================================================================
class EightBallModal(ui.Modal, title="Pose ta question"):
    question_input = ui.TextInput(
        label="Quelle est ta question ?",
        placeholder="Le destin est-il écrit ?",
        style=discord.TextStyle.short,
        required=True,
        max_length=256,
    )

    def __init__(self, cog: "RandomCog", options_list: list[str]):
        super().__init__()
        self.cog = cog
        self.options_list = options_list

    async def on_submit(self, interaction: discord.Interaction) -> None:
        response = random.choice(self.cog.responses)
        question = str(self.question_input.value)
        result_text = (
            "## 🎱 8-Ball\n"
            f"Question de {interaction.user.mention} :\n"
            f"```\n{question}\n```\n"
            f"Réponse :\n"
            f"```\n{response}\n```"
        )
        debug_log(f"8-Ball interrogé par {interaction.user} ({interaction.user.id})", "SUCCESS")
        view = RandomLayoutView(
            self.cog,
            interaction.guild,
            interaction.user,
            active_tab="8ball",
            result_text=result_text,
            options_list=self.options_list,
        )
        await interaction.response.send_message(view=view, ephemeral=False)


class RateModal(ui.Modal, title="Noter quelque chose"):
    element_input = ui.TextInput(
        label="Quel élément veux-tu noter ?",
        placeholder="Écris ici...",
        min_length=1,
        max_length=100,
    )

    def __init__(self, cog: "RandomCog", options_list: list[str]):
        super().__init__()
        self.cog = cog
        self.options_list = options_list

    async def on_submit(self, interaction: discord.Interaction) -> None:
        score = round(random.uniform(0, 10), 1)
        bar = get_ascii_bar(score)
        emoji = get_rating_emoji(score)

        if score < 3:
            comment = "C'est pas ouf..."
        elif score < 6:
            comment = "Bof bof..."
        elif score < 8:
            comment = "Pas mal du tout !"
        elif score < 10:
            comment = "Excellent !"
        else:
            comment = "PARFAIT ! 10/10 !"

        result_text = (
            "## ⭐ Évaluation\n"
            f"{interaction.user.mention} a évalué :\n"
            f"```\n{self.element_input.value}\n```\n"
            f"Note : {score}/10 {emoji}\n`{bar}`\n\n"
            f"*{comment}*"
        )
        debug_log(f"Rate effectué par {interaction.user} ({interaction.user.id}) - Score: {score}/10", "SUCCESS")
        view = RandomLayoutView(
            self.cog,
            interaction.guild,
            interaction.user,
            active_tab="rate",
            result_text=result_text,
            options_list=self.options_list,
        )
        await interaction.response.send_message(view=view, ephemeral=False)


class AddOptionsModal(ui.Modal):
    def __init__(self, cog: "RandomCog", slots_needed: int, current_options: list[str]):
        super().__init__(title=f"Ajouter des options ({slots_needed} max)")
        self.cog = cog
        self.current_options = current_options
        self.inputs: list[ui.TextInput] = []

        for index in range(slots_needed):
            txt = ui.TextInput(
                label=f"Option {index + 1}",
                placeholder="Écris ton option ici...",
                required=(index == 0),
                max_length=80,
            )
            self.inputs.append(txt)
            self.add_item(txt)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        new_items = [str(inp.value).strip() for inp in self.inputs if inp.value and str(inp.value).strip()]
        total_combined = (self.current_options + new_items)[:25]
        debug_log(f"{len(new_items)} options ajoutées par {interaction.user}", "SUCCESS")
        view = RandomLayoutView(
            self.cog,
            interaction.guild,
            interaction.user,
            active_tab="choose",
            options_list=total_combined,
        )
        await interaction.response.edit_message(view=view)


# ==============================================================================
# ------------------------- VUE LAYOUT V2 PRINCIPALE ---------------------------
# ==============================================================================
class RandomLayoutView(ui.LayoutView):
    def __init__(
        self,
        cog: "RandomCog",
        guild: Optional[discord.Guild],
        user: discord.abc.User,
        active_tab: str = "8ball",
        result_text: Optional[str] = None,
        options_list: Optional[list[str]] = None,
    ):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.user = user
        self.active_tab = active_tab
        self.result_text = result_text
        self.options_list = options_list or []
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(f"{E.ERREUR} Ce menu ne vous appartient pas.", ephemeral=False)
            return False
        return True

    def _build(self) -> None:
        self.clear_items()
        accent_color, footer_text = get_theme_values(self.guild, self.user, self.cog.bot)

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)

        # 1. SÉLECTEUR EN HAUT POUR CHANGER DE MENU (8-BALL, RATE, TIRAGE)
        select_tabs = ui.Select(
            placeholder="🧭 Choisir un outil aléatoire...",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label="8-Ball",
                    value="8ball",
                    description="Poser une question au destin",
                    emoji="🎱",
                    default=(self.active_tab == "8ball")
                ),
                discord.SelectOption(
                    label="Rate",
                    value="rate",
                    description="Noter un élément de 0 à 10",
                    emoji="⭐",
                    default=(self.active_tab == "rate")
                ),
                discord.SelectOption(
                    label="Tirage au sort",
                    value="choose",
                    description="Gérer et tirer au sort des options",
                    emoji="🎲",
                    default=(self.active_tab == "choose")
                ),
            ]
        )
        select_tabs.callback = self.on_tab_select_callback
        row_select_tabs = ui.ActionRow()
        row_select_tabs.add_item(select_tabs)
        container.add_item(row_select_tabs)

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

        # 2. BOUTONS D'ACTIONS POSITIONNÉS AU-DESSUS (POUR TIRAGE OU AUTRES)
        if self.active_tab == "8ball":
            row_action = ui.ActionRow()
            btn_modal_8ball = ui.Button(
                label="Poser ma question",
                style=discord.ButtonStyle.primary,
                emoji="🎱",
            )
            btn_modal_8ball.callback = self.on_8ball_action_click
            row_action.add_item(btn_modal_8ball)
            container.add_item(row_action)
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

        elif self.active_tab == "rate":
            row_action = ui.ActionRow()
            btn_modal_rate = ui.Button(
                label="Valeur à noter",
                style=discord.ButtonStyle.primary,
                emoji="⭐",
            )
            btn_modal_rate.callback = self.on_rate_action_click
            row_action.add_item(btn_modal_rate)
            container.add_item(row_action)
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

        elif self.active_tab == "choose":
            row_actions = ui.ActionRow()

            if len(self.options_list) < 25:
                slots_left = 25 - len(self.options_list)
                btn_add = ui.Button(
                    label=f"Ajouter ({min(5, slots_left)} max)",
                    style=discord.ButtonStyle.success,
                    emoji=E.AJOUTER,
                )
                btn_add.callback = self.on_add_options_click
                row_actions.add_item(btn_add)

            if len(self.options_list) >= 2:
                btn_roll = ui.Button(
                    label="Lancer le tirage",
                    style=discord.ButtonStyle.primary,
                    emoji=E.CIBLE,
                )
                btn_roll.callback = self.on_roll_click
                row_actions.add_item(btn_roll)

            if row_actions.children:
                container.add_item(row_actions)
                container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

        # 3. AFFICHAGE DES RÉSULTATS OU DES GUIDES / LISTES PAR ONGLET
        if self.result_text:
            container.add_item(ui.TextDisplay(self.result_text))
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
        else:
            if self.active_tab == "8ball":
                container.add_item(ui.TextDisplay("# 🎱 8-Ball"))
                container.add_item(ui.TextDisplay("Clique sur le bouton ci-dessus pour poser ta question."))
            elif self.active_tab == "rate":
                container.add_item(ui.TextDisplay("# ⭐ Rate"))
                container.add_item(ui.TextDisplay("Clique sur le bouton ci-dessus pour noter quelque chose."))
            else:
                container.add_item(ui.TextDisplay("# 🎲 Tirage au sort"))
                if self.options_list:
                    formatted = "\n".join(f"**{idx + 1}.** `{opt}`" for idx, opt in enumerate(self.options_list))
                    container.add_item(ui.TextDisplay(f"Options ({len(self.options_list)}/25) :\n{formatted}"))
                else:
                    container.add_item(ui.TextDisplay("Aucune option pour le moment. Ajoutes-en pour lancer un tirage !"))

        # Sélecteur de suppression d'options si l'onglet Tirage possède des options
        if self.active_tab == "choose" and self.options_list:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
            select_options = [
                discord.SelectOption(
                    label=f"{idx + 1}. {opt[:90]}",
                    value=str(idx),
                    description=f"Option numéro {idx + 1}",
                )
                for idx, opt in enumerate(self.options_list)
            ]
            remove_select = ui.Select(
                placeholder="Sélectionner les options à supprimer...",
                min_values=1,
                max_values=min(len(select_options), 25),
                options=select_options,
            )
            remove_select.callback = self.on_remove_select_callback

            row_select = ui.ActionRow()
            row_select.add_item(remove_select)
            container.add_item(row_select)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    # ----------------- CALLBACKS INTERACTIFS -----------------
    async def on_tab_select_callback(self, interaction: discord.Interaction) -> None:
        selected_value = interaction.data.get("values", ["8ball"])[0]
        debug_log(f"Navigation vers l'onglet : {selected_value}", "INFO")
        view = RandomLayoutView(
            self.cog,
            interaction.guild,
            interaction.user,
            active_tab=selected_value,
            options_list=self.options_list
        )
        await interaction.response.edit_message(view=view)

    async def on_8ball_action_click(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(EightBallModal(self.cog, self.options_list))

    async def on_rate_action_click(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(RateModal(self.cog, self.options_list))

    async def on_add_options_click(self, interaction: discord.Interaction) -> None:
        slots_to_show = min(5, 25 - len(self.options_list))
        await interaction.response.send_modal(AddOptionsModal(self.cog, slots_to_show, self.options_list))

    async def on_remove_select_callback(self, interaction: discord.Interaction) -> None:
        values = interaction.data.get("values", []) if interaction.data else []
        indexes_to_remove = {int(value) for value in values if str(value).isdigit()}
        filtered = [opt for idx, opt in enumerate(self.options_list) if idx not in indexes_to_remove]
        debug_log(f"{len(indexes_to_remove)} option(s) supprimée(s)", "INFO")
        view = RandomLayoutView(
            self.cog,
            interaction.guild,
            interaction.user,
            active_tab="choose",
            options_list=filtered
        )
        await interaction.response.edit_message(view=view)

    async def on_roll_click(self, interaction: discord.Interaction) -> None:
        if len(self.options_list) < 2:
            await interaction.response.send_message(
                f"{E.ERREUR} Il faut au moins 2 options pour effectuer un tirage au sort.",
                ephemeral=False
            )
            return

        shuffled = list(self.options_list)
        random.shuffle(shuffled)
        top_results = shuffled[:25]

        ranking = "\n".join(f"**{idx + 1}.** `{opt}`" for idx, opt in enumerate(top_results))
        result = (
            "## 🎲 Tirage terminé\n"
            f"{interaction.user.mention} a effectué un tirage (Top {len(top_results)}) :\n"
            f"{ranking}\n\n"
            f"🏆 Grand gagnant : `{top_results[0]}`"
        )
        debug_log(f"Tirage effectué par {interaction.user}. Gagnant : {top_results[0]}", "SUCCESS")

        view = RandomLayoutView(
            self.cog,
            interaction.guild,
            interaction.user,
            active_tab="choose",
            result_text=result,
            options_list=self.options_list,
        )
        await interaction.response.send_message(view=view, ephemeral=False)


# ==============================================================================
# ------------------------------ COG PRINCIPAL ---------------------------------
# ==============================================================================
class RandomCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.responses = [
            "Oui, absolument.",
            "C'est certain.",
            "Sans aucun doute.",
            "Très probablement.",
            "Peut-être bien.",
            "Demande plus tard.",
            "Mieux vaut ne pas te le dire maintenant.",
            "Je ne peux pas prédire.",
            "Ne compte pas là-dessus.",
            "Ma réponse est non.",
            "Mes sources disent non.",
        ]
        debug_log("Cog RandomCog initialisé avec succès.", "SUCCESS")

    def cog_unload(self) -> None:
        debug_log("Cog RandomCog déchargé.", "WARNING")

    @commands.hybrid_command(
        name="random",
        description="Ouvre le menu interactif des outils aléatoires (8-Ball, Rate, Tirage).",
    )
    async def random_command(self, ctx: commands.Context) -> None:
        if not ctx.guild:
            await ctx.send(f"{E.ERREUR} Cette commande doit être utilisée sur un serveur.")
            return

        debug_log(f"Commande /random invoquée par {ctx.author} ({ctx.author.id})", "INFO")
        try:
            view = RandomLayoutView(self, ctx.guild, ctx.author, active_tab="8ball")
            if ctx.interaction:
                await ctx.send(view=view, ephemeral=False)
            else:
                await ctx.reply(view=view, mention_author=False)
        except Exception as exc:
            debug_log(f"Erreur lors de l'exécution de la commande /random: {exc}", "ERROR")
            traceback.print_exc()


async def setup(bot: commands.Bot) -> None:
    for old_cmd in ["8ball", "rate", "fun", "jeux", "choose", "random"]:
        if bot.get_command(old_cmd):
            bot.remove_command(old_cmd)
    await bot.add_cog(RandomCog(bot))
    debug_log("Cog RandomCog enregistré et chargé.", "SUCCESS")