import math
import aiohttp
import discord
from discord.ext import commands
from typing import Any

try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

try:
    # Récupération de la couleur du thème (Dark Mode par défaut)
    EMBED_COLOR = int(config.get("EMBED_COLOR", "0x2B2D31"), 16)
except (NameError, TypeError):
    EMBED_COLOR = 0x2B2D31

class FormSelect(discord.ui.Select):
    def __init__(self, forms_page: list[dict[str, Any]]):
        options = []
        for form in forms_page:
            options.append(
                discord.SelectOption(
                    label=form["name"][:100],  # Limite de 100 caractères imposée par Discord
                    value=str(form["id"])
                )
            )
        super().__init__(
            placeholder="Sélectionne une forme spécifique...",
            min_values=1,
            max_values=1,
            options=options,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        form_id = int(self.values[0])
        form_name = next((f.label for f in self.options if f.value == str(form_id)), "Inconnu")
        
        # Récupération du sprite via l'ID de l'API (ID > 10000 pour les formes)
        sprite_url = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{form_id}.png"
        
        embed = discord.Embed(
            title=f"Forme Spécifique : {form_name}",
            color=EMBED_COLOR
        )
        embed.set_image(url=sprite_url)
        embed.set_footer(text="Navigue entre les pages pour voir d'autres formes.")
        
        await interaction.response.edit_message(embed=embed, view=self.view)


class FormeView(discord.ui.View):
    def __init__(self, forms: list[dict[str, Any]], author_id: int):
        super().__init__(timeout=300)
        self.forms = forms
        self.author_id = author_id
        self.current_page = 0
        self.items_per_page = 25
        self.max_pages = math.ceil(len(self.forms) / self.items_per_page)
        self.message: discord.Message | None = None
        
        self.update_components()

    def update_components(self):
        self.clear_items()
        
        # Boutons de pagination
        if self.max_pages > 1:
            prev_btn = discord.ui.Button(label="◀", style=discord.ButtonStyle.secondary, disabled=self.current_page == 0, row=0)
            prev_btn.callback = self.prev_page
            self.add_item(prev_btn)
            
            page_indicator = discord.ui.Button(label=f"Page {self.current_page + 1}/{self.max_pages}", style=discord.ButtonStyle.secondary, disabled=True, row=0)
            self.add_item(page_indicator)
            
            next_btn = discord.ui.Button(label="▶", style=discord.ButtonStyle.secondary, disabled=self.current_page == self.max_pages - 1, row=0)
            next_btn.callback = self.next_page
            self.add_item(next_btn)

        # Menu déroulant de la page actuelle
        start_idx = self.current_page * self.items_per_page
        end_idx = start_idx + self.items_per_page
        forms_page = self.forms[start_idx:end_idx]
        
        if forms_page:
            self.add_item(FormSelect(forms_page))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Cette interface ne t'appartient pas.", ephemeral=True)
            return False
        return True

    async def prev_page(self, interaction: discord.Interaction):
        self.current_page -= 1
        self.update_components()
        await interaction.response.edit_message(view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page += 1
        self.update_components()
        await interaction.response.edit_message(view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class FormeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.forms_cache: list[dict[str, Any]] = []

    async def fetch_forms(self) -> list[dict[str, Any]]:
        """Récupère dynamiquement toutes les formes alternatives depuis l'API."""
        if self.forms_cache:
            return self.forms_cache
            
        async with aiohttp.ClientSession() as session:
            # On charge une grande limite pour avoir accès à toutes les données d'un coup
            async with session.get("https://pokeapi.co/api/v2/pokemon?limit=1500") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for p in data["results"]:
                        url = p["url"]
                        p_id = int(url.rstrip("/").split("/")[-1])
                        
                        # Dans PokéAPI, les Pokémon classiques ont un ID de 1 à 1025. 
                        # Les formes spécifiques (Méga, Alola, Galar, Hisui, etc.) ont un ID > 10000.
                        if p_id > 10000:
                            self.forms_cache.append({
                                "name": p["name"].replace("-", " ").title(),
                                "id": p_id
                            })
        return self.forms_cache

    @commands.hybrid_command(name="forme", description="Affiche la liste de TOUTES les formes spécifiques de Pokémon.")
    async def forme(self, ctx: commands.Context[commands.Bot]):
        await ctx.defer()
        
        forms = await self.fetch_forms()
        if not forms:
            return await ctx.send("❌ Impossible de récupérer les données des formes depuis l'API.", reference=ctx.message)

        view = FormeView(forms, ctx.author.id)
        
        if config_manager and hasattr(ctx, "guild") and ctx.guild:
            embed = config_manager.get_formatted_embed(
                guild=ctx.guild, 
                user=ctx.author, 
                bot=self.bot, 
                title="✨ Formes Spécifiques de Pokémon", 
                description="Sélectionne une forme dans le menu déroulant pour afficher son image."
            )
        else:
            embed = discord.Embed(
                title="✨ Formes Spécifiques de Pokémon",
                description="Sélectionne une forme dans le menu déroulant pour afficher son image.",
                color=EMBED_COLOR
            )
            
        embed.set_footer(text=f"Total de formes trouvées : {len(forms)}")
        
        msg = await ctx.send(embed=embed, view=view, reference=ctx.message)
        view.message = msg


async def setup(bot: commands.Bot):
    if bot.get_cog("FormeCog"):
        await bot.remove_cog("FormeCog")
    await bot.add_cog(FormeCog(bot))