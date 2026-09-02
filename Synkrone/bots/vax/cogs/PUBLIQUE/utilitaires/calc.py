"""
MODULE CALCULETTE VAX V3
========================
Calculatrice interactive haute performance utilisant l'architecture Layout V2,
le gestionnaire de thème global, des logs colorés et un moteur de calcul sécurisé.
"""

from __future__ import annotations

import ast
import operator
import re
import discord
from discord import app_commands, ui
from discord.ext import commands

# Intégration de l'écosystème Vax v3
from utils.config_theme import config_manager

# ==============================================================================
# ------------------------------ DÉBOGAGE GLOBAL -------------------------------
# ==============================================================================
DEBUG_MODE = True
DEBUG_ERRORS_ONLY = True


def log_debug(message: str, level: str = "info") -> None:
    """Affiche des logs formatés dans la console selon le niveau de sévérité."""
    if DEBUG_ERRORS_ONLY and level != "error":
        return
    if not DEBUG_MODE and not DEBUG_ERRORS_ONLY:
        return

    colors = {
        "info": "\033[94m[INFO]\033[0m",
        "success": "\033[92m[SUCCÈS]\033[0m",
        "error": "\033[91m[ERREUR]\033[0m",
        "warning": "\033[93m[ATTENTION]\033[0m",
        "calc": "\033[35m[CALC]\033[0m",
    }
    prefix = colors.get(level, colors["info"])
    print(f"{prefix} [CalcModule] {message}")


# ==============================================================================
# --------------------------- GESTION DES EMOJIS -------------------------------
# ==============================================================================
EMOJI_TITLE = "🧮"
EMOJI_ADD = "➕"
EMOJI_SUB = "➖"
EMOJI_MUL = "✖️"
EMOJI_DIV = "➗"
EMOJI_MOD = "🏷️"
EMOJI_CALC = "✨"
EMOJI_INPUT = "✏️"
EMOJI_BACK = "⌫"
EMOJI_ERROR = "❌"
EMOJI_TRASH = "🗑️"


# ==============================================================================
# -------------------------- MOTEUR DE CALCUL SÉCURISÉ -------------------------
# ==============================================================================
def safe_eval(expression: str) -> float | int:
    """Évalue de manière sécurisée une expression mathématique simple avec support des pourcentages."""
    expression = expression.replace("×", "*").replace("÷", "/")
    expression = re.sub(r'(\d+(?:\.\d+)?)%', r'(\1 * 0.01)', expression)

    operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
    }

    def eval_node(node):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError("Type non supporté")
        elif isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type in operators:
                return operators[op_type](eval_node(node.left), eval_node(node.right))
            raise ValueError("Opérateur non supporté")
        elif isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type in operators:
                return operators[op_type](eval_node(node.operand))
            raise ValueError("Opérateur unaire non supporté")
        else:
            raise ValueError("Expression invalide")

    tree = ast.parse(expression, mode="eval")
    result = eval_node(tree.body)
    if isinstance(result, float) and result.is_integer():
        return int(result)
    return round(result, 6)


# ==============================================================================
# ------------------------- MODALE DE SAISIE LIBRE -----------------------------
# ==============================================================================
class CalcInputModal(ui.Modal, title="Saisie de calcul libre"):
    expression_input = ui.TextInput(
        label="Expression mathématique",
        placeholder="Ex: 8x4X6*8, 100+20%",
        style=discord.TextStyle.short,
        required=True,
        max_length=100,
    )

    def __init__(self, calc_view: CalcLayoutView):
        super().__init__()
        self.calc_view = calc_view

    async def on_submit(self, interaction: discord.Interaction):
        raw_val = self.expression_input.value.strip()
        normalized = raw_val.replace("x", "*").replace("X", "*")
        
        log_debug(f"Saisie modale reçue : '{raw_val}' -> Normalisée : '{normalized}'", "calc")
        
        try:
            result = safe_eval(normalized)
            self.calc_view.calculation_line = normalized
            self.calc_view.expression = f"{normalized} = {result}"
            log_debug(f"Calcul modale réussi : {normalized} = {result}", "success")
        except Exception as e:
            log_debug(f"Erreur de calcul modale sur '{normalized}' : {e}", "error")
            self.calc_view.calculation_line = normalized
            self.calc_view.expression = "Erreur"

        await self.calc_view._refresh(interaction)


# ==============================================================================
# ------------------------- VUE LAYOUT V2 DE LA CALCULETTE ---------------------
# ==============================================================================
class CalcLayoutView(ui.LayoutView):
    """Interface Layout V2 pour une calculatrice interactive hautement ergonomique et épurée."""

    def __init__(self, cog: "CalcCommand", user_id: int, guild: discord.Guild, author: discord.Member, initial_calculation: str = "0", initial_expression: str = "0"):
        super().__init__(timeout=300)
        self.cog = cog
        self.user_id = user_id
        self.guild = guild
        self.author = author
        self.calculation_line = initial_calculation
        self.expression = initial_expression
        self.message: discord.Message | None = None
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            try:
                log_debug(f"Accès refusé au panneau de calcul pour {interaction.user} (Propriétaire : {self.author})", "warning")
                await interaction.response.send_message(
                    f"{EMOJI_ERROR} **Accès refusé.** Ce panneau de calcul appartient à {self.author.mention}.",
                    ephemeral=False
                )
            except Exception as e:
                log_debug(f"Erreur lors de l'envoi du message d'accès refusé : {e}", "error")
            return False
        return True

    def _build(self):
        try:
            self.clear_items()

            theme = (
                config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.author, self.cog.bot)
                if config_manager
                else {"color": discord.Color.blurple().value, "footer_text": ""}
            )
            accent_color = int(theme.get("color", discord.Color.blurple().value))
            footer_text = theme.get("footer_text", "")

            container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
            container.add_item(ui.TextDisplay(f"# {EMOJI_TITLE} Calculette Interactive"))
            container.add_item(ui.TextDisplay(f"### 🧮 Calcul : `{self.calculation_line}`"))
            container.add_item(ui.TextDisplay(f"### 📥 Expression : `{self.expression}`"))

            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

            # Ligne 1 : Saisie, %, ⌫, ÷
            row1 = ui.ActionRow()
            b_input = ui.Button(style=discord.ButtonStyle.secondary, emoji=EMOJI_INPUT)
            b_input.callback = self.cb_open_modal
            row1.add_item(b_input)

            b_pct = ui.Button(label="%", style=discord.ButtonStyle.secondary)
            b_pct.callback = lambda i: self.append_char(i, "%")
            row1.add_item(b_pct)

            b_back = ui.Button(label="⌫", style=discord.ButtonStyle.secondary)
            b_back.callback = self.cb_backspace
            row1.add_item(b_back)

            b_div = ui.Button(label="÷", style=discord.ButtonStyle.primary)
            b_div.callback = lambda i: self.append_char(i, "/")
            row1.add_item(b_div)
            container.add_item(row1)

            # Ligne 2 : 7, 8, 9, *
            row2 = ui.ActionRow()
            for digit in ["7", "8", "9"]:
                btn = ui.Button(label=digit, style=discord.ButtonStyle.secondary)
                btn.callback = lambda i, d=digit: self.append_char(i, d)
                row2.add_item(btn)

            b_mul = ui.Button(label="×", style=discord.ButtonStyle.primary)
            b_mul.callback = lambda i: self.append_char(i, "*")
            row2.add_item(b_mul)
            container.add_item(row2)

            # Ligne 3 : 4, 5, 6, -
            row3 = ui.ActionRow()
            for digit in ["4", "5", "6"]:
                btn = ui.Button(label=digit, style=discord.ButtonStyle.secondary)
                btn.callback = lambda i, d=digit: self.append_char(i, d)
                row3.add_item(btn)

            b_sub = ui.Button(label="-", style=discord.ButtonStyle.primary)
            b_sub.callback = lambda i: self.append_char(i, "-")
            row3.add_item(b_sub)
            container.add_item(row3)

            # Ligne 4 : 1, 2, 3, +
            row4 = ui.ActionRow()
            for digit in ["1", "2", "3"]:
                btn = ui.Button(label=digit, style=discord.ButtonStyle.secondary)
                btn.callback = lambda i, d=digit: self.append_char(i, d)
                row4.add_item(btn)

            b_add = ui.Button(label="+", style=discord.ButtonStyle.primary)
            b_add.callback = lambda i: self.append_char(i, "+")
            row4.add_item(b_add)
            container.add_item(row4)

            # Ligne 5 : 0, ., AC, =
            row5 = ui.ActionRow()
            b_zero = ui.Button(label="0", style=discord.ButtonStyle.secondary)
            b_zero.callback = lambda i: self.append_char(i, "0")
            row5.add_item(b_zero)

            b_dot = ui.Button(label=".", style=discord.ButtonStyle.secondary)
            b_dot.callback = lambda i: self.append_char(i, ".")
            row5.add_item(b_dot)

            b_ac = ui.Button(label="AC", style=discord.ButtonStyle.danger)
            b_ac.callback = self.cb_ac
            row5.add_item(b_ac)

            b_eq = ui.Button(label="=", style=discord.ButtonStyle.success)
            b_eq.callback = self.cb_calculate
            row5.add_item(b_eq)
            container.add_item(row5)

            if footer_text:
                container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
                container.add_item(ui.TextDisplay(footer_text))

            self.add_item(container)
            log_debug("Vue Layout V2 de la calculette construite avec succès.", "success")
        except Exception as e:
            log_debug(f"ERREUR CRITIQUE lors de la construction de la vue _build : {e}", "error")
            import traceback
            traceback.print_exc()

    async def _refresh(self, interaction: discord.Interaction):
        try:
            self._build()
            if not interaction.response.is_done():
                await interaction.response.edit_message(view=self)
            else:
                await interaction.edit_original_response(view=self)
        except Exception as e:
            log_debug(f"Erreur lors du rafraîchissement de la vue : {e}", "error")

    async def append_char(self, interaction: discord.Interaction, char: str):
        operators_set = {"+", "-", "*", "/"}
        
        if "=" in self.expression:
            parts = self.expression.split("=")
            last_result = parts[-1].strip()
            if char in operators_set:
                self.calculation_line = last_result + char
            else:
                self.calculation_line = char
            self.expression = self.calculation_line
        elif self.calculation_line in ("0", "Erreur"):
            if char in operators_set:
                self.calculation_line = "0" + char
            else:
                self.calculation_line = char
            self.expression = self.calculation_line
        else:
            last_char = self.calculation_line[-1] if self.calculation_line else ""
            if last_char in operators_set and char in operators_set:
                self.calculation_line = self.calculation_line[:-1] + char
            else:
                self.calculation_line += char
            self.expression = self.calculation_line

        log_debug(f"Calcul mis à jour : {self.calculation_line}", "calc")
        await self._refresh(interaction)

    async def cb_ac(self, interaction: discord.Interaction):
        self.calculation_line = "0"
        self.expression = "0"
        log_debug("Calculatrice réinitialisée (AC)", "calc")
        await self._refresh(interaction)

    async def cb_open_modal(self, interaction: discord.Interaction):
        try:
            await interaction.response.send_modal(CalcInputModal(self))
        except Exception as e:
            log_debug(f"Erreur lors de l'ouverture de la modale : {e}", "error")

    async def cb_backspace(self, interaction: discord.Interaction):
        if "=" in self.expression:
            self.calculation_line = "0"
            self.expression = "0"
        elif len(self.calculation_line) > 1:
            self.calculation_line = self.calculation_line[:-1]
            self.expression = self.calculation_line
        else:
            self.calculation_line = "0"
            self.expression = "0"
        log_debug(f"Effacement, calcul : {self.calculation_line}", "calc")
        await self._refresh(interaction)

    async def cb_calculate(self, interaction: discord.Interaction):
        try:
            current_expr = self.calculation_line.replace("x", "*").replace("X", "*")
            result = safe_eval(current_expr)
            log_debug(f"Calcul effectué : {current_expr} = {result}", "success")
            self.expression = f"{self.calculation_line} = {result}"
        except Exception as e:
            log_debug(f"Erreur de calcul sur '{self.calculation_line}' : {e}", "error")
            self.expression = "Erreur"
        await self._refresh(interaction)


# ==============================================================================
# --------------------------- COG PRINCIPAL ------------------------------------
# ==============================================================================
class CalcCommand(commands.Cog):
    """Module de calculatrice interactive hautement esthétique basé sur le Layout V2."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log_debug("Cog CalcCommand initialisé avec succès.", "success")

    def cog_unload(self):
        log_debug("Cog CalcCommand déchargé.", "warning")

    @commands.hybrid_command(
        name="calc",
        description="🧮 Ouvre une calculette interactive directement dans le salon"
    )
    @app_commands.describe(expression="Expression mathématique optionnelle à évaluer directement")
    @app_commands.guild_only()
    async def calc(self, ctx: commands.Context, *, expression: str | None = None):
        log_debug(f"Ouverture de la calculette pour {ctx.author} ({ctx.author.id})", "info")
        try:
            initial_calc = "0"
            initial_expr = "0"
            if expression:
                normalized = expression.replace("x", "*").replace("X", "*")
                initial_calc = expression
                try:
                    res = safe_eval(normalized)
                    initial_expr = f"{expression} = {res}"
                except Exception:
                    initial_expr = "Erreur"

            view = CalcLayoutView(self, ctx.author.id, ctx.guild, ctx.author, initial_calculation=initial_calc, initial_expression=initial_expr)
            message = await ctx.send(view=view)
            view.message = message
            log_debug("Calculette envoyée avec succès dans le salon.", "success")
        except Exception as e:
            log_debug(f"ERREUR CRITIQUE lors de l'envoi de la calculette : {e}", "error")
            import traceback
            traceback.print_exc()
            await ctx.send(f"{EMOJI_ERROR} Une erreur est survenue lors de l'initialisation de la calculatrice.")


async def setup(bot: commands.Bot):
    await bot.add_cog(CalcCommand(bot))
    log_debug("Cog CalcCommand enregistré et chargé.", "success")