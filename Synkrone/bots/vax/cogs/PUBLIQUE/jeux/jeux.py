from __future__ import annotations

from discord.ext import commands

from utils.config_emoji import Emoji as E


GAMES = [
    {
        "name": "jeu2048",
        "label": "2048",
        "cog": "Game2048",
        "description": "Jeu solo de glissement et fusion des tuiles.",
    },
    {
        "name": "anagram",
        "label": "Anagram",
        "cog": "Anagram",
        "description": "Trouve le mot melange.",
    },
    {
        "name": "enigme",
        "label": "Enigme",
        "cog": "Enigme",
        "description": "Resous une enigme.",
    },
    {
        "name": "flags",
        "label": "Flags",
        "cog": "Flags",
        "description": "Devine le pays a partir du drapeau.",
    },
    {
        "name": "mastermind",
        "label": "Mastermind",
        "cog": "Mastermind",
        "description": "Trouve le code secret.",
    },
    {
        "name": "morpion",
        "label": "Morpion",
        "cog": "Morpion",
        "description": "Duel tactique en 3x3.",
    },
    {
        "name": "nombre",
        "label": "Nombre",
        "cog": "GuessNumber",
        "description": "Trouve le nombre magique.",
    },
    {
        "name": "pfc",
        "label": "Pierre Feuille Ciseaux",
        "cog": "PFC",
        "description": "Duel rapide et classe.",
    },
    {
        "name": "puissance4",
        "label": "Puissance 4",
        "cog": "Puissance4",
        "description": "Aligne 4 jetons.",
    },
]


class Jeux(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    def _build_menu(self) -> str:
        lines = [f"{E.JEU} Jeux disponibles", ""]
        for game in GAMES:
            lines.append(f"- {game['label']} : /game {game['name']}")
        lines.append("")
        lines.append("Utilise /game ou /games avec le nom du jeu pour le lancer.")
        return "\n".join(lines)

    async def _launch_game(self, ctx: commands.Context, game_name: str) -> None:
        game = next((item for item in GAMES if item["name"] == game_name), None)
        if game is None:
            await ctx.send("Jeu introuvable.")
            return

        cog = self.bot.get_cog(game["cog"])
        if cog is None or not hasattr(cog, "launch_from_hub"):
            await ctx.send(f"Le jeu {game['label']} n'est pas disponible pour le moment.")
            return

        await cog.launch_from_hub(ctx)

    @commands.hybrid_group(
        name="game",
        aliases=["games"],
        description="Hub des jeux disponibles",
        invoke_without_command=True,
    )
    async def game(self, ctx: commands.Context) -> None:
        await ctx.send(self._build_menu())

    @game.command(name="jeu2048", description="Lance 2048.")
    async def jeu2048(self, ctx: commands.Context) -> None:
        await self._launch_game(ctx, "jeu2048")

    @game.command(name="anagram", description="Lance Anagram.")
    async def anagram(self, ctx: commands.Context) -> None:
        await self._launch_game(ctx, "anagram")

    @game.command(name="enigme", description="Lance Enigme.")
    async def enigme(self, ctx: commands.Context) -> None:
        await self._launch_game(ctx, "enigme")

    @game.command(name="flags", description="Lance Flags.")
    async def flags(self, ctx: commands.Context) -> None:
        await self._launch_game(ctx, "flags")

    @game.command(name="mastermind", description="Lance Mastermind.")
    async def mastermind(self, ctx: commands.Context) -> None:
        await self._launch_game(ctx, "mastermind")

    @game.command(name="morpion", description="Lance Morpion.")
    async def morpion(self, ctx: commands.Context) -> None:
        await self._launch_game(ctx, "morpion")

    @game.command(name="nombre", description="Lance le jeu du nombre magique.")
    async def nombre(self, ctx: commands.Context) -> None:
        await self._launch_game(ctx, "nombre")

    @game.command(name="pfc", description="Lance Pierre Feuille Ciseaux.")
    async def pfc(self, ctx: commands.Context) -> None:
        await self._launch_game(ctx, "pfc")

    @game.command(name="puissance4", description="Lance Puissance 4.")
    async def puissance4(self, ctx: commands.Context) -> None:
        await self._launch_game(ctx, "puissance4")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Jeux(bot))
