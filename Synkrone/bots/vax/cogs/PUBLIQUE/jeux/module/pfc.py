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
    "id": "pfc",
    "label": "Pierre Feuille Ciseaux",
    "emoji": "✂️",
    "mode": "multi",
    "description": "Duel rapide et classe.",
}

GAME_RULES = "Choisis Pierre, Feuille ou Ciseaux."

CHOICES = {
    "pierre": "🪨",
    "feuille": "📄",
    "ciseaux": "✂️",
}



def _embed(bot: commands.Bot, guild: Optional[discord.Guild], user: discord.abc.User, title: str, description: str) -> discord.Embed:
    if config_manager:
        try:
            return config_manager.get_formatted_embed(guild=guild, user=user, bot=bot, title=title, description=description, target_id=guild.id if guild else None)
        except Exception:
            pass
    return discord.Embed(title=title, description=description, color=discord.Color.blurple())


def _beats(a: str, b: str) -> bool:
    return (a == "pierre" and b == "ciseaux") or (a == "feuille" and b == "pierre") or (a == "ciseaux" and b == "feuille")


class PFCButton(ui.Button):
    def __init__(self, key: str):
        super().__init__(label=key.title(), emoji=CHOICES[key], style=discord.ButtonStyle.secondary)
        self.key = key

    async def callback(self, interaction: discord.Interaction):
        view: "PFCView" = self.view
        await view.play(interaction, self.key)


class PFCView(ui.View):
    def __init__(self, cog: "PFC", player1: discord.abc.User, player2: Optional[discord.abc.User] = None):
        super().__init__(timeout=180)
        self.cog = cog
        self.player1 = player1
        self.player2 = player2
        self.picks: dict[int, str] = {}
        for key in ("pierre", "feuille", "ciseaux"):
            self.add_item(PFCButton(key))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.player2 is None:
            return interaction.user.id == self.player1.id
        allowed = {self.player1.id, self.player2.id}
        if interaction.user.id not in allowed:
            await interaction.response.send_message("Tu n'es pas dans ce duel.", ephemeral=True)
            return False
        return True

    async def play(self, interaction: discord.Interaction, choice: str):
        if interaction.user.id in self.picks:
            await interaction.response.send_message("Tu as deja choisi.", ephemeral=True)
            return

        self.picks[interaction.user.id] = choice

        if self.player2 is None:
            bot_choice = random.choice(list(CHOICES.keys()))
            user_choice = choice
            if user_choice == bot_choice:
                result = "Egalite."
            elif _beats(user_choice, bot_choice):
                result = "Tu gagnes !"
            else:
                result = "Tu perds."

            desc = (
                f"Toi: {CHOICES[user_choice]} {user_choice}\n"
                f"IA: {CHOICES[bot_choice]} {bot_choice}\n\n"
                f"**{result}**"
            )
            for item in self.children:
                if isinstance(item, ui.Button):
                    item.disabled = True
            embed = _embed(self.cog.bot, interaction.guild, interaction.user, "Pierre Feuille Ciseaux", desc)
            await interaction.response.edit_message(embed=embed, view=self)
            return

        if len(self.picks) < 2:
            await interaction.response.send_message("Choix enregistre. En attente de l'autre joueur.", ephemeral=True)
            return

        p1 = self.picks[self.player1.id]
        p2 = self.picks[self.player2.id]
        if p1 == p2:
            result = "Egalite."
        elif _beats(p1, p2):
            result = f"Victoire de {self.player1.mention}."
        else:
            result = f"Victoire de {self.player2.mention}."

        for item in self.children:
            if isinstance(item, ui.Button):
                item.disabled = True

        desc = (
            f"{self.player1.mention}: {CHOICES[p1]} {p1}\n"
            f"{self.player2.mention}: {CHOICES[p2]} {p2}\n\n"
            f"**{result}**"
        )
        embed = _embed(self.cog.bot, interaction.guild, interaction.user, "Pierre Feuille Ciseaux", desc)
        await interaction.response.edit_message(embed=embed, view=self)


class PFC(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def launch_from_hub(self, ctx: commands.Context, opponent: Optional[discord.User] = None):
        if opponent and opponent.bot:
            opponent = None
        view = PFCView(self, ctx.author, opponent)
        mode = f"Duel contre {opponent.mention}." if opponent else "Mode solo contre IA."
        embed = _embed(self.bot, ctx.guild, ctx.author, "Pierre Feuille Ciseaux", f"{GAME_RULES}\n\n{mode}")
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="pfc", description="Lance un Pierre Feuille Ciseaux.")
    async def pfc_command(self, ctx: commands.Context, opponent: Optional[discord.User] = None):
        await self.launch_from_hub(ctx, opponent=opponent)


async def setup(bot: commands.Bot):
    await bot.add_cog(PFC(bot))
