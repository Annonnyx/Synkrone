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
    "id": "flags",
    "label": "Flags",
    "emoji": "🏁",
    "mode": "solo",
    "description": "Devine le pays a partir du drapeau.",
}

GAME_RULES = "Observe le drapeau et trouve le pays correspondant."

FLAGS = [
    ("🇫🇷", "france"),
    ("🇯🇵", "japon"),
    ("🇮🇹", "italie"),
    ("🇨🇦", "canada"),
    ("🇪🇸", "espagne"),
    ("🇧🇷", "bresil"),
]


def _embed(bot: commands.Bot, guild: Optional[discord.Guild], user: discord.abc.User, title: str, description: str) -> discord.Embed:
    if config_manager:
        try:
            return config_manager.get_formatted_embed(guild=guild, user=user, bot=bot, title=title, description=description, target_id=guild.id if guild else None)
        except Exception:
            pass
    return discord.Embed(title=title, description=description, color=discord.Color.blurple())


class FlagAnswerModal(ui.Modal, title="Nom du pays"):
    answer = ui.TextInput(label="Ta reponse", max_length=80)

    def __init__(self, view: "FlagsView"):
        super().__init__()
        self.parent_view = view

    async def on_submit(self, interaction: discord.Interaction):
        guess = str(self.answer.value).strip().lower()
        if guess == self.parent_view.country:
            text = f"Exact ! Le drapeau etait **{self.parent_view.country.title()}**."
            for item in self.parent_view.children:
                if isinstance(item, ui.Button):
                    item.disabled = True
        else:
            text = "Mauvaise reponse, retente."
        embed = _embed(self.parent_view.cog.bot, interaction.guild, interaction.user, "Flags", text)
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class FlagsView(ui.View):
    def __init__(self, cog: "Flags", author_id: int):
        super().__init__(timeout=240)
        self.cog = cog
        self.author_id = author_id
        self.flag, self.country = random.choice(FLAGS)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Cette partie ne t'appartient pas.", ephemeral=True)
            return False
        return True

    @ui.button(label="Repondre", style=discord.ButtonStyle.primary)
    async def answer_btn(self, interaction: discord.Interaction, _: ui.Button):
        await interaction.response.send_modal(FlagAnswerModal(self))

    @ui.button(label="Indice", style=discord.ButtonStyle.secondary)
    async def hint_btn(self, interaction: discord.Interaction, _: ui.Button):
        hint = f"Le nom contient {len(self.country)} lettres."
        embed = _embed(self.cog.bot, interaction.guild, interaction.user, "Indice", hint)
        await interaction.response.edit_message(embed=embed, view=self)


class Flags(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def launch_from_hub(self, ctx: commands.Context, opponent=None):
        view = FlagsView(self, ctx.author.id)
        embed = _embed(self.bot, ctx.guild, ctx.author, "Flags", f"{GAME_RULES}\n\nQuel pays correspond a ce drapeau: {view.flag}")
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="flags", description="Lance une partie de Flags.")
    async def flags_command(self, ctx: commands.Context):
        await self.launch_from_hub(ctx)


async def setup(bot: commands.Bot):
    await bot.add_cog(Flags(bot))
