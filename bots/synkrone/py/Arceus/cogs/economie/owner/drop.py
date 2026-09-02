import aiohttp
import discord
from discord.ext import commands

from cogs.economie.utils import EconomyService

class AdminDropCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.eco = EconomyService(bot)

    async def find_pokemon_id(self, session: aiohttp.ClientSession, identifier: str) -> int | None:
        """Tente de trouver l'ID d'un pokémon via son nom (FR/EN) ou son ID numérique."""
        if identifier.isdigit():
            return int(identifier)
        
        try:
            url = f"https://pokeapi.co/api/v2/pokemon/{identifier.lower()}"
            async with session.get(url) as r:
                if r.status == 200:
                    data = await r.json()
                    return data["id"]
        except:
            return None
        return None

    async def execute_drop(self, ctx, membre, pokemon, quantite, shiny: bool):
        target = membre or ctx.author
        
        if not pokemon:
            await ctx.send("❌ Usage: !drop/!sdrop <@user/ID> <nom/ID pokémon> [quantité]", reference=ctx.message)
            return

        self.eco.ensure_user(target.id)

        async with aiohttp.ClientSession() as session:
            pid = await self.find_pokemon_id(session, pokemon)
            if not pid or pid > 1025:
                await ctx.send(f"❌ Pokémon '{pokemon}' introuvable.", reference=ctx.message)
                return
            
            name_fr = await self.eco.get_species_name_fr(session, pid)

        # Ajout dans l'inventaire
        for _ in range(quantite):
            self.eco.add_inventory_item(
                user_id=target.id,
                pokemon_id=pid,
                name=name_fr,
                is_shiny=shiny,
                legendary=False,
                mythical=False,
                sexe="⚲",
                ball="masterball" if shiny else "pokeball", # Petit bonus: Shiny en Masterball
                level=1
            )

        status = "Shiny ✨" if shiny else "Normal"
        await ctx.send(f"✅ Ajouté `{quantite}x {name_fr} ({status})` à {target.mention}.", reference=ctx.message)

    @commands.command(name="drop", description="[Admin] Ajoute des Pokémon normaux.")
    @commands.has_permissions(administrator=True)
    async def drop(self, ctx: commands.Context[commands.Bot], membre: discord.Member | discord.User = None, pokemon: str = None, quantite: int = 1):
        await self.execute_drop(ctx, membre, pokemon, quantite, shiny=False)

    @commands.command(name="sdrop", description="[Admin] Ajoute des Pokémon shiny.")
    @commands.has_permissions(administrator=True)
    async def sdrop(self, ctx: commands.Context[commands.Bot], membre: discord.Member | discord.User = None, pokemon: str = None, quantite: int = 1):
        await self.execute_drop(ctx, membre, pokemon, quantite, shiny=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminDropCog(bot))