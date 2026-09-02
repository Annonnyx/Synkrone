import random
from typing import Optional

import discord
from discord import ui
from discord.ext import commands

try:
    from utils.config_theme import config_manager
except ImportError:
    config_manager = None


GAME_META = {
    "id": "2048",
    "label": "2048",
    "emoji": "🔢",
    "mode": "solo",
    "description": "Fusionne les tuiles jusqu'a 2048.",
}

GAME_RULES = "Deplace les tuiles avec les fleches. Quand deux valeurs identiques se touchent, elles fusionnent."


def _build_embed(bot: commands.Bot, guild: Optional[discord.Guild], user: discord.abc.User, title: str, description: str) -> discord.Embed:
    if config_manager:
        try:
            return config_manager.get_formatted_embed(
                guild=guild,
                user=user,
                bot=bot,
                title=title,
                description=description,
                target_id=guild.id if guild else None,
            )
        except Exception:
            pass

    embed = discord.Embed(title=title, description=description, color=discord.Color.blurple())
    embed.set_footer(text="Jeu 2048")
    return embed


def _spawn_tile(board: list[list[int]]) -> None:
    empties = [(r, c) for r in range(4) for c in range(4) if board[r][c] == 0]
    if not empties:
        return
    r, c = random.choice(empties)
    board[r][c] = 4 if random.random() < 0.1 else 2


def _compress(row: list[int]) -> tuple[list[int], int]:
    values = [value for value in row if value]
    merged: list[int] = []
    score_gain = 0
    idx = 0
    while idx < len(values):
        if idx + 1 < len(values) and values[idx] == values[idx + 1]:
            value = values[idx] * 2
            merged.append(value)
            score_gain += value
            idx += 2
        else:
            merged.append(values[idx])
            idx += 1
    merged += [0] * (4 - len(merged))
    return merged, score_gain


def _apply_move(board: list[list[int]], direction: str) -> tuple[bool, int]:
    score_gain = 0
    moved = False

    if direction in {"left", "right"}:
        for row_idx in range(4):
            original = list(board[row_idx])
            row = list(reversed(original)) if direction == "right" else original
            compressed, gain = _compress(row)
            new_row = list(reversed(compressed)) if direction == "right" else compressed
            if new_row != original:
                moved = True
            board[row_idx] = new_row
            score_gain += gain
        return moved, score_gain

    for col_idx in range(4):
        original = [board[r][col_idx] for r in range(4)]
        col = list(reversed(original)) if direction == "down" else original
        compressed, gain = _compress(col)
        new_col = list(reversed(compressed)) if direction == "down" else compressed
        if new_col != original:
            moved = True
        for r in range(4):
            board[r][col_idx] = new_col[r]
        score_gain += gain

    return moved, score_gain


def _has_moves(board: list[list[int]]) -> bool:
    for row in board:
        if 0 in row:
            return True
    for r in range(4):
        for c in range(4):
            value = board[r][c]
            if r + 1 < 4 and board[r + 1][c] == value:
                return True
            if c + 1 < 4 and board[r][c + 1] == value:
                return True
    return False


def _render_board(board: list[list[int]]) -> str:
    lines = []
    for row in board:
        line = " ".join(f"{value:>5}" if value else "    ." for value in row)
        lines.append(line)
    return "\n".join(lines)


class Game2048View(ui.View):
    def __init__(self, cog: "Game2048", author_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.author_id = author_id
        self.board = [[0, 0, 0, 0] for _ in range(4)]
        self.score = 0
        _spawn_tile(self.board)
        _spawn_tile(self.board)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Cette partie ne t'appartient pas.", ephemeral=True)
            return False
        return True

    async def _play(self, interaction: discord.Interaction, direction: str) -> None:
        moved, gain = _apply_move(self.board, direction)
        if moved:
            self.score += gain
            _spawn_tile(self.board)

        if not _has_moves(self.board):
            for button in self.children:
                if isinstance(button, ui.Button):
                    button.disabled = True

        title = "2048"
        desc = f"Score: **{self.score}**\n```\n{_render_board(self.board)}\n```"
        if not _has_moves(self.board):
            desc += "\nPartie terminee."
        embed = _build_embed(self.cog.bot, interaction.guild, interaction.user, title, desc)
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="⬅", style=discord.ButtonStyle.secondary)
    async def left(self, interaction: discord.Interaction, _: ui.Button):
        await self._play(interaction, "left")

    @ui.button(label="⬆", style=discord.ButtonStyle.secondary)
    async def up(self, interaction: discord.Interaction, _: ui.Button):
        await self._play(interaction, "up")

    @ui.button(label="⬇", style=discord.ButtonStyle.secondary)
    async def down(self, interaction: discord.Interaction, _: ui.Button):
        await self._play(interaction, "down")

    @ui.button(label="➡", style=discord.ButtonStyle.secondary)
    async def right(self, interaction: discord.Interaction, _: ui.Button):
        await self._play(interaction, "right")


class Game2048(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def launch_from_hub(self, ctx: commands.Context, opponent=None) -> None:
        view = Game2048View(self, ctx.author.id)
        embed = _build_embed(self.bot, ctx.guild, ctx.author, "2048", f"{GAME_RULES}\n\n```\n{_render_board(view.board)}\n```")
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="jeu2048", description="Lance une partie de 2048.")
    async def game_2048(self, ctx: commands.Context):
        await self.launch_from_hub(ctx)


async def setup(bot: commands.Bot):
    await bot.add_cog(Game2048(bot))
