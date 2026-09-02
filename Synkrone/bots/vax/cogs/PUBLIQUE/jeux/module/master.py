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
    "id": "mastermind",
    "label": "Mastermind",
    "emoji": "🧩",
    "mode": "multi",
    "description": "Trouve le code secret.",
}

GAME_RULES = "Devine le code de 4 chiffres (1 a 6)."



def _embed(bot: commands.Bot, guild: Optional[discord.Guild], user: discord.abc.User, title: str, description: str) -> discord.Embed:
    if config_manager:
        try:
            return config_manager.get_formatted_embed(guild=guild, user=user, bot=bot, title=title, description=description, target_id=guild.id if guild else None)
        except Exception:
            pass
    return discord.Embed(title=title, description=description, color=discord.Color.blurple())


def _score_guess(secret: str, guess: str) -> tuple[int, int]:
    exact = sum(1 for idx in range(4) if guess[idx] == secret[idx])
    total = 0
    for digit in "123456":
        total += min(secret.count(digit), guess.count(digit))
    partial = total - exact
    return exact, partial


class MasterGuessModal(ui.Modal, title="Propose un code"):
    code = ui.TextInput(label="Code (4 chiffres entre 1 et 6)", placeholder="ex: 1234", max_length=4)

    def __init__(self, view: "MastermindView"):
        super().__init__()
        self.parent_view = view

    async def on_submit(self, interaction: discord.Interaction):
        if self.parent_view.finished:
            await interaction.response.send_message("Partie terminee.", ephemeral=True)
            return

        guess = str(self.code.value).strip()
        if len(guess) != 4 or any(ch not in "123456" for ch in guess):
            await interaction.response.send_message("Format invalide. Utilise 4 chiffres de 1 a 6.", ephemeral=True)
            return

        self.parent_view.attempts += 1
        exact, partial = _score_guess(self.parent_view.secret, guess)
        self.parent_view.history.append(f"{guess} -> exact:{exact} / place:{partial}")

        if exact == 4:
            self.parent_view.finished = True
            msg = f"Gagne en {self.parent_view.attempts} tentatives. Code: **{self.parent_view.secret}**"
        elif self.parent_view.attempts >= self.parent_view.max_attempts:
            self.parent_view.finished = True
            msg = f"Perdu. Code secret: **{self.parent_view.secret}**"
        else:
            left = self.parent_view.max_attempts - self.parent_view.attempts
            msg = f"Tentatives restantes: **{left}**"

        if self.parent_view.finished:
            for item in self.parent_view.children:
                if isinstance(item, ui.Button):
                    item.disabled = True

        history_text = "\n".join(self.parent_view.history[-10:]) or "Aucune"
        embed = _embed(
            self.parent_view.cog.bot,
            interaction.guild,
            interaction.user,
            "Mastermind",
            f"{msg}\n\n```\n{history_text}\n```",
        )
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class MastermindView(ui.View):
    def __init__(self, cog: "Mastermind", author_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.author_id = author_id
        self.secret = "".join(random.choice("123456") for _ in range(4))
        self.attempts = 0
        self.max_attempts = 10
        self.finished = False
        self.history: list[str] = []

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Cette partie ne t'appartient pas.", ephemeral=True)
            return False
        return True

    @ui.button(label="Proposer", style=discord.ButtonStyle.primary)
    async def guess_btn(self, interaction: discord.Interaction, _: ui.Button):
        await interaction.response.send_modal(MasterGuessModal(self))


class Mastermind(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def launch_from_hub(self, ctx: commands.Context, opponent=None):
        view = MastermindView(self, ctx.author.id)
        embed = _embed(self.bot, ctx.guild, ctx.author, "Mastermind", GAME_RULES)
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="mastermind", description="Lance une partie de Mastermind.")
    async def mastermind_command(self, ctx: commands.Context):
        await self.launch_from_hub(ctx)


async def setup(bot: commands.Bot):
    await bot.add_cog(Mastermind(bot))
