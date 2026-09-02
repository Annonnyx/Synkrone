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
    "id": "anagram",
    "label": "Anagram",
    "emoji": "🔤",
    "mode": "solo",
    "description": "Trouve le mot melange.",
}

GAME_RULES = "Devine le mot cache a partir des lettres melangees."

WORDS = [
    "discord",
    "python",
    "serveur",
    "commande",
    "interaction",
    "musique",
    "niveau",
    "profil",
]


def _embed(bot: commands.Bot, guild: Optional[discord.Guild], user: discord.abc.User, title: str, description: str) -> discord.Embed:
    if config_manager:
        try:
            return config_manager.get_formatted_embed(guild=guild, user=user, bot=bot, title=title, description=description, target_id=guild.id if guild else None)
        except Exception:
            pass
    return discord.Embed(title=title, description=description, color=discord.Color.blurple())


class AnswerModal(ui.Modal, title="Propose ta reponse"):
    answer = ui.TextInput(label="Mot", max_length=64, required=True)

    def __init__(self, view: "AnagramView"):
        super().__init__()
        self.parent_view = view

    async def on_submit(self, interaction: discord.Interaction):
        guess = str(self.answer.value).strip().lower()
        if guess == self.parent_view.current_word:
            self.parent_view.solved = True
            for item in self.parent_view.children:
                if isinstance(item, ui.Button):
                    item.disabled = True
            text = f"Bravo {interaction.user.mention}, tu as trouve **{self.parent_view.current_word}**."
        else:
            text = f"Ce n'est pas ca. Essaie encore."
        embed = _embed(self.parent_view.cog.bot, interaction.guild, interaction.user, "Anagram", text)
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class AnagramView(ui.View):
    def __init__(self, cog: "Anagram", author_id: int):
        super().__init__(timeout=240)
        self.cog = cog
        self.author_id = author_id
        self.current_word = random.choice(WORDS)
        letters = list(self.current_word)
        random.shuffle(letters)
        self.scrambled = "".join(letters)
        self.solved = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Cette partie ne t'appartient pas.", ephemeral=True)
            return False
        return True

    @ui.button(label="Repondre", style=discord.ButtonStyle.primary)
    async def answer_btn(self, interaction: discord.Interaction, _: ui.Button):
        await interaction.response.send_modal(AnswerModal(self))

    @ui.button(label="Indice", style=discord.ButtonStyle.secondary)
    async def hint_btn(self, interaction: discord.Interaction, _: ui.Button):
        hint = self.current_word[0] + "_" * (len(self.current_word) - 2) + self.current_word[-1]
        embed = _embed(self.cog.bot, interaction.guild, interaction.user, "Anagram", f"Indice: `{hint}`")
        await interaction.response.edit_message(embed=embed, view=self)


class Anagram(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def launch_from_hub(self, ctx: commands.Context, opponent=None):
        view = AnagramView(self, ctx.author.id)
        embed = _embed(self.bot, ctx.guild, ctx.author, "Anagram", f"{GAME_RULES}\n\nMot melange: **{view.scrambled}**")
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="anagram", description="Lance une anagram.")
    async def anagram_command(self, ctx: commands.Context):
        await self.launch_from_hub(ctx)


async def setup(bot: commands.Bot):
    await bot.add_cog(Anagram(bot))
