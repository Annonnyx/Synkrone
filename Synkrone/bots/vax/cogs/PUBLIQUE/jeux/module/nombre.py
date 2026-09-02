import random
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
    "id": "nombre",
    "label": "Nombre",
    "emoji": E.CIBLE,
    "mode": "solo",
    "description": "Trouve le nombre magique.",
}

GAME_RULES = "Devine le nombre entre 1 et 100 en 7 tentatives."



def _embed(bot: commands.Bot, guild: Optional[discord.Guild], user: discord.abc.User, title: str, description: str) -> discord.Embed:
    if config_manager:
        try:
            return config_manager.get_formatted_embed(guild=guild, user=user, bot=bot, title=title, description=description, target_id=guild.id if guild else None)
        except Exception:
            pass
    return discord.Embed(title=title, description=description, color=discord.Color.blurple())


class GuessModal(ui.Modal, title="Propose un nombre"):
    number = ui.TextInput(label="Nombre", placeholder="1-100", max_length=3)

    def __init__(self, view: "NumberView"):
        super().__init__()
        self.parent_view = view

    async def on_submit(self, interaction: discord.Interaction):
        if self.parent_view.finished:
            await interaction.response.send_message("Partie deja terminee.", ephemeral=True)
            return

        value = str(self.number.value).strip()
        if not value.isdigit():
            await interaction.response.send_message("Entre un nombre valide.", ephemeral=True)
            return

        guess = int(value)
        self.parent_view.tries += 1
        remaining = self.parent_view.max_tries - self.parent_view.tries

        if guess == self.parent_view.target:
            self.parent_view.finished = True
            message = f"Bien joue ! Le nombre etait **{self.parent_view.target}**."
        elif self.parent_view.tries >= self.parent_view.max_tries:
            self.parent_view.finished = True
            message = f"Perdu. Le nombre etait **{self.parent_view.target}**."
        elif guess < self.parent_view.target:
            message = f"Plus grand ! Tentatives restantes: **{remaining}**"
        else:
            message = f"Plus petit ! Tentatives restantes: **{remaining}**"

        if self.parent_view.finished:
            for item in self.parent_view.children:
                if isinstance(item, ui.Button):
                    item.disabled = True

        embed = _embed(self.parent_view.cog.bot, interaction.guild, interaction.user, "Trouve le nombre", message)
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class NumberView(ui.View):
    def __init__(self, cog: "GuessNumber", author_id: int):
        super().__init__(timeout=240)
        self.cog = cog
        self.author_id = author_id
        self.target = random.randint(1, 100)
        self.max_tries = 7
        self.tries = 0
        self.finished = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Cette partie ne t'appartient pas.", ephemeral=True)
            return False
        return True

    @ui.button(label="Deviner", style=discord.ButtonStyle.primary, emoji=E.CIBLE)
    async def guess_btn(self, interaction: discord.Interaction, _: ui.Button):
        await interaction.response.send_modal(GuessModal(self))


class GuessNumber(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def launch_from_hub(self, ctx: commands.Context, opponent=None):
        view = NumberView(self, ctx.author.id)
        embed = _embed(self.bot, ctx.guild, ctx.author, "Trouve le nombre", GAME_RULES)
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="nombre", description="Lance le jeu du nombre magique.")
    async def nombre_command(self, ctx: commands.Context):
        await self.launch_from_hub(ctx)


async def setup(bot: commands.Bot):
    await bot.add_cog(GuessNumber(bot))
