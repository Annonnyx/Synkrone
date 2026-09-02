from typing import Optional

import discord
from discord import ui
from discord.ext import commands

from utils.config_emoji import Emoji as E

try:
    from utils.config_theme import config_manager
except ImportError:
    config_manager = None


GAME_META = {
    "id": "morpion",
    "label": "Morpion",
    "emoji": E.REFUSER,
    "mode": "multi",
    "description": "Duel tactique en 3x3.",
}

GAME_RULES = "Aligne 3 symboles pour gagner."


def _embed(bot: commands.Bot, guild: Optional[discord.Guild], user: discord.abc.User, title: str, description: str) -> discord.Embed:
    if config_manager:
        try:
            return config_manager.get_formatted_embed(guild=guild, user=user, bot=bot, title=title, description=description, target_id=guild.id if guild else None)
        except Exception:
            pass
    return discord.Embed(title=title, description=description, color=discord.Color.blurple())


def _winner(board: list[str]) -> Optional[str]:
    lines = [
        (0, 1, 2),
        (3, 4, 5),
        (6, 7, 8),
        (0, 3, 6),
        (1, 4, 7),
        (2, 5, 8),
        (0, 4, 8),
        (2, 4, 6),
    ]
    for a, b, c in lines:
        if board[a] != " " and board[a] == board[b] == board[c]:
            return board[a]
    return None


class MorpionButton(ui.Button):
    def __init__(self, index: int):
        super().__init__(label=" ", style=discord.ButtonStyle.secondary, row=index // 3)
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        view: "MorpionView" = self.view
        await view.play(interaction, self)


class MorpionView(ui.View):
    def __init__(self, cog: "Morpion", player_x: discord.abc.User, player_o: Optional[discord.abc.User] = None):
        super().__init__(timeout=300)
        self.cog = cog
        self.player_x = player_x
        self.player_o = player_o
        self.board = [" "] * 9
        self.turn = "X"
        self.finished = False

        for i in range(9):
            self.add_item(MorpionButton(i))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.finished:
            return False
        if self.player_o is None:
            return interaction.user.id == self.player_x.id
        allowed = {self.player_x.id, self.player_o.id}
        if interaction.user.id not in allowed:
            await interaction.response.send_message("Tu n'es pas dans cette partie.", ephemeral=True)
            return False
        return True

    async def play(self, interaction: discord.Interaction, button: MorpionButton):
        if self.board[button.index] != " ":
            await interaction.response.send_message("Case deja prise.", ephemeral=True)
            return

        current_user = self.player_x if self.turn == "X" else (self.player_o or self.player_x)
        if interaction.user.id != current_user.id:
            await interaction.response.send_message("Ce n'est pas ton tour.", ephemeral=True)
            return

        self.board[button.index] = self.turn
        button.label = self.turn
        button.style = discord.ButtonStyle.danger if self.turn == "X" else discord.ButtonStyle.success
        button.disabled = True

        winner = _winner(self.board)
        draw = all(cell != " " for cell in self.board)

        if winner or draw:
            self.finished = True
            for item in self.children:
                if isinstance(item, ui.Button):
                    item.disabled = True
            if winner == "X":
                text = f"Victoire de {self.player_x.mention}."
            elif winner == "O" and self.player_o is not None:
                text = f"Victoire de {self.player_o.mention}."
            else:
                text = "Match nul."
        else:
            self.turn = "O" if self.turn == "X" else "X"
            if self.turn == "O" and self.player_o is None:
                free = [i for i, cell in enumerate(self.board) if cell == " "]
                if free:
                    idx = free[0]
                    self.board[idx] = "O"
                    auto_btn = self.children[idx]
                    if isinstance(auto_btn, ui.Button):
                        auto_btn.label = "O"
                        auto_btn.style = discord.ButtonStyle.success
                        auto_btn.disabled = True
                winner = _winner(self.board)
                draw = all(cell != " " for cell in self.board)
                self.turn = "X"
                if winner or draw:
                    self.finished = True
                    for item in self.children:
                        if isinstance(item, ui.Button):
                            item.disabled = True
                    text = "L'IA gagne." if winner == "O" else ("Tu gagnes !" if winner == "X" else "Match nul.")
                else:
                    text = "Ton tour."
            else:
                next_player = self.player_x if self.turn == "X" else self.player_o
                text = f"Tour de {next_player.mention if next_player else self.player_x.mention}."

        embed = _embed(self.cog.bot, interaction.guild, interaction.user, "Morpion", text)
        await interaction.response.edit_message(embed=embed, view=self)


class Morpion(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def launch_from_hub(self, ctx: commands.Context, opponent: Optional[discord.User] = None):
        if opponent and opponent.bot:
            opponent = None
        view = MorpionView(self, ctx.author, opponent)
        desc = GAME_RULES + (f"\n\nJoueur O: {opponent.mention}" if opponent else "\n\nMode solo contre IA.")
        embed = _embed(self.bot, ctx.guild, ctx.author, "Morpion", desc)
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="morpion", description="Lance une partie de morpion.")
    async def morpion_command(self, ctx: commands.Context, opponent: Optional[discord.User] = None):
        await self.launch_from_hub(ctx, opponent=opponent)


async def setup(bot: commands.Bot):
    await bot.add_cog(Morpion(bot))
