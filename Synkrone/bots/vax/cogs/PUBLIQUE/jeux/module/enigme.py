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
    "id": "enigme",
    "label": "Enigme",
    "emoji": "🧠",
    "mode": "solo",
    "description": "Resous une enigme.",
}

GAME_RULES = "Lis l'enigme et propose ta reponse."

RIDDLES = [
    {"q": "Je tombe sans jamais me faire mal. Qui suis-je ?", "a": "la nuit", "h": "Elle revient tous les jours."},
    {"q": "Plus j'ai de gardiens, moins je suis en securite. Qui suis-je ?", "a": "un secret", "h": "On le partage parfois."},
    {"q": "Je peux remplir une piece sans prendre d'espace. Qui suis-je ?", "a": "la lumiere", "h": "Tu l'allumes."},
]


def _embed(bot: commands.Bot, guild: Optional[discord.Guild], user: discord.abc.User, title: str, description: str) -> discord.Embed:
    if config_manager:
        try:
            return config_manager.get_formatted_embed(guild=guild, user=user, bot=bot, title=title, description=description, target_id=guild.id if guild else None)
        except Exception:
            pass
    return discord.Embed(title=title, description=description, color=discord.Color.blurple())


class EnigmeAnswerModal(ui.Modal, title="Ta reponse"):
    answer = ui.TextInput(label="Reponse", max_length=120)

    def __init__(self, view: "EnigmeView"):
        super().__init__()
        self.parent_view = view

    async def on_submit(self, interaction: discord.Interaction):
        guess = str(self.answer.value).strip().lower()
        ok = guess == self.parent_view.answer
        if ok:
            self.parent_view.solved = True
            for item in self.parent_view.children:
                if isinstance(item, ui.Button):
                    item.disabled = True
        msg = "Bonne reponse !" if ok else "Mauvaise reponse, retente ta chance."
        embed = _embed(self.parent_view.cog.bot, interaction.guild, interaction.user, "Enigme", msg)
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class EnigmeView(ui.View):
    def __init__(self, cog: "Enigme", author_id: int):
        super().__init__(timeout=240)
        self.cog = cog
        self.author_id = author_id
        pick = random.choice(RIDDLES)
        self.question = pick["q"]
        self.answer = pick["a"]
        self.hint = pick["h"]
        self.solved = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Cette enigme ne t'appartient pas.", ephemeral=True)
            return False
        return True

    @ui.button(label="Repondre", style=discord.ButtonStyle.primary)
    async def answer_btn(self, interaction: discord.Interaction, _: ui.Button):
        await interaction.response.send_modal(EnigmeAnswerModal(self))

    @ui.button(label="Indice", style=discord.ButtonStyle.secondary)
    async def hint_btn(self, interaction: discord.Interaction, _: ui.Button):
        embed = _embed(self.cog.bot, interaction.guild, interaction.user, "Indice", self.hint)
        await interaction.response.edit_message(embed=embed, view=self)


class Enigme(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def launch_from_hub(self, ctx: commands.Context, opponent=None):
        view = EnigmeView(self, ctx.author.id)
        embed = _embed(self.bot, ctx.guild, ctx.author, "Enigme", f"{GAME_RULES}\n\n{view.question}")
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="enigme", description="Lance une enigme.")
    async def enigme_command(self, ctx: commands.Context):
        await self.launch_from_hub(ctx)


async def setup(bot: commands.Bot):
    await bot.add_cog(Enigme(bot))
