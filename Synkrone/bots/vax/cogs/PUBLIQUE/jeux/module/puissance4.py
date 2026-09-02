from typing import Optional

import discord
from discord import ui
from discord.ext import commands

try:
    from utils.config_theme import config_manager
except ImportError:
    config_manager = None


GAME_META = {
    "id": "puissance4",
    "label": "Puissance 4",
    "emoji": "🟡",
    "mode": "multi",
    "description": "Aligne 4 jetons.",
}

GAME_RULES = "Joue dans une colonne pour aligner 4 jetons."

ROWS = 6
COLS = 7
EMPTY = "⚪"
P1 = "🔴"
P2 = "🟡"


def _embed(bot: commands.Bot, guild: Optional[discord.Guild], user: discord.abc.User, title: str, description: str) -> discord.Embed:
    if config_manager:
        try:
            return config_manager.get_formatted_embed(guild=guild, user=user, bot=bot, title=title, description=description, target_id=guild.id if guild else None)
        except Exception:
            pass
    return discord.Embed(title=title, description=description, color=discord.Color.blurple())


def _render(board: list[list[str]]) -> str:
    lines = ["".join(row) for row in board]
    footer = "1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣"
    return "\n".join(lines + [footer])


def _drop(board: list[list[str]], col: int, token: str) -> bool:
    for r in range(ROWS - 1, -1, -1):
        if board[r][col] == EMPTY:
            board[r][col] = token
            return True
    return False


def _win(board: list[list[str]], token: str) -> bool:
    for r in range(ROWS):
        for c in range(COLS):
            if c + 3 < COLS and all(board[r][c + k] == token for k in range(4)):
                return True
            if r + 3 < ROWS and all(board[r + k][c] == token for k in range(4)):
                return True
            if r + 3 < ROWS and c + 3 < COLS and all(board[r + k][c + k] == token for k in range(4)):
                return True
            if r + 3 < ROWS and c - 3 >= 0 and all(board[r + k][c - k] == token for k in range(4)):
                return True
    return False


class DropButton(ui.Button):
    def __init__(self, col: int):
        super().__init__(label=str(col + 1), style=discord.ButtonStyle.secondary)
        self.col = col

    async def callback(self, interaction: discord.Interaction):
        view: "Puissance4View" = self.view
        await view.play(interaction, self.col)


class Puissance4View(ui.View):
    def __init__(self, cog: "Puissance4", player1: discord.abc.User, player2: Optional[discord.abc.User] = None):
        super().__init__(timeout=300)
        self.cog = cog
        self.player1 = player1
        self.player2 = player2
        self.board = [[EMPTY for _ in range(COLS)] for _ in range(ROWS)]
        self.turn = P1
        self.finished = False

        for col in range(COLS):
            self.add_item(DropButton(col))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.finished:
            return False

        if self.player2 is None:
            return interaction.user.id == self.player1.id

        allowed = {self.player1.id, self.player2.id}
        if interaction.user.id not in allowed:
            await interaction.response.send_message("Tu n'es pas dans cette partie.", ephemeral=True)
            return False
        return True

    async def play(self, interaction: discord.Interaction, col: int):
        current = self.player1 if self.turn == P1 else (self.player2 or self.player1)
        if interaction.user.id != current.id:
            await interaction.response.send_message("Ce n'est pas ton tour.", ephemeral=True)
            return

        if not _drop(self.board, col, self.turn):
            await interaction.response.send_message("Cette colonne est pleine.", ephemeral=True)
            return

        token = self.turn
        winner = _win(self.board, token)
        draw = all(cell != EMPTY for row in self.board for cell in row)

        if winner or draw:
            self.finished = True
            for item in self.children:
                if isinstance(item, ui.Button):
                    item.disabled = True
            if winner:
                player = self.player1 if token == P1 else (self.player2 or self.player1)
                text = f"Victoire de {player.mention}."
            else:
                text = "Match nul."
        else:
            self.turn = P2 if self.turn == P1 else P1
            if self.turn == P2 and self.player2 is None:
                for auto_col in range(COLS):
                    if _drop(self.board, auto_col, P2):
                        break
                if _win(self.board, P2):
                    self.finished = True
                    for item in self.children:
                        if isinstance(item, ui.Button):
                            item.disabled = True
                    text = "L'IA gagne."
                elif all(cell != EMPTY for row in self.board for cell in row):
                    self.finished = True
                    for item in self.children:
                        if isinstance(item, ui.Button):
                            item.disabled = True
                    text = "Match nul."
                else:
                    self.turn = P1
                    text = f"Tour de {self.player1.mention}."
            else:
                next_player = self.player1 if self.turn == P1 else self.player2
                text = f"Tour de {next_player.mention if next_player else self.player1.mention}."

        embed = _embed(self.cog.bot, interaction.guild, interaction.user, "Puissance 4", f"{text}\n\n{_render(self.board)}")
        await interaction.response.edit_message(embed=embed, view=self)


class Puissance4(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def launch_from_hub(self, ctx: commands.Context, opponent: Optional[discord.User] = None):
        if opponent and opponent.bot:
            opponent = None
        view = Puissance4View(self, ctx.author, opponent)
        mode = f"Duel contre {opponent.mention}." if opponent else "Mode solo contre IA."
        embed = _embed(self.bot, ctx.guild, ctx.author, "Puissance 4", f"{GAME_RULES}\n\n{mode}\n\n{_render(view.board)}")
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="puissance4", description="Lance une partie de puissance 4.")
    async def puissance4_command(self, ctx: commands.Context, opponent: Optional[discord.User] = None):
        await self.launch_from_hub(ctx, opponent=opponent)


async def setup(bot: commands.Bot):
    await bot.add_cog(Puissance4(bot))
