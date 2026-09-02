import discord
from discord.ext import commands
import aiohttp
import math

# Tentative d'import du manager d'embed
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# On importe ta fonction de génération de profil et les emojis
try:
    from .pokemon import generate_pokemon_profile, TYPE_EMOJIS, SHINY_EMOJI
except ImportError:
    generate_pokemon_profile = None
    TYPE_EMOJIS = {}
    SHINY_EMOJI = "✨"

# Mapping pour la traduction FR -> API (Anglais)
TYPE_EN_TO_FR = {
    "normal": "Normal", "fire": "Feu", "water": "Eau", "electric": "Électrik",
    "grass": "Plante", "ice": "Glace", "fighting": "Combat", "poison": "Poison",
    "ground": "Sol", "flying": "Vol", "psychic": "Psy", "bug": "Insecte",
    "rock": "Roche", "ghost": "Spectre", "dragon": "Dragon", "dark": "Ténèbres",
    "steel": "Acier", "fairy": "Fée"
}

TYPE_FR_TO_EN = {v.lower(): k for k, v in TYPE_EN_TO_FR.items()}
TYPE_FR_TO_EN.update({"electrik": "electric", "electrique": "electric", "tenebres": "dark", "fee": "fairy"})

# ============================================================================
# ----------------------------- UTILITAIRES ----------------------------------
# ============================================================================

def get_search_help_embed(guild, author, bot) -> discord.Embed:
    """Génère l'embed par défaut pour la recherche (avec le config_manager si dispo)."""
    desc = (
        "Utilisez les menus déroulants ci-dessous pour configurer votre recherche de Pokémon.\n\n"
        "*(Vous pouvez toujours utiliser les arguments directement, ex: `/recherche Eau Vol 1`)*"
    )
    if config_manager:
        return config_manager.get_formatted_embed(guild, author, bot, "🔍 Aide : Recherche Pokémon", desc)
    else:
        return discord.Embed(title="🔍 Aide : Recherche Pokémon", description=desc, color=0x2B2D31)

# ============================================================================
# ----------------------------- API GRAPHQL ----------------------------------
# ============================================================================

async def fetch_filtered_pokemon(session: aiohttp.ClientSession, type1: str | None, type2: str | None, gen: int | None) -> list[dict]:
    url = "https://beta.pokeapi.co/graphql/v1beta"
    conditions = []
    if gen:
        conditions.append(f"generation_id: {{_eq: {gen}}}")
        
    type_conditions = []
    if type1 and type1.lower() in TYPE_FR_TO_EN:
        type_conditions.append(f"{{pokemon_v2_pokemontypes: {{pokemon_v2_type: {{name: {{_eq: \"{TYPE_FR_TO_EN[type1.lower()]}\"}}}}}}}}")
    if type2 and type2.lower() in TYPE_FR_TO_EN:
        type_conditions.append(f"{{pokemon_v2_pokemontypes: {{pokemon_v2_type: {{name: {{_eq: \"{TYPE_FR_TO_EN[type2.lower()]}\"}}}}}}}}")
        
    if type_conditions:
        conditions.append(f"pokemon_v2_pokemons: {{is_default: {{_eq: true}}, _and: [{', '.join(type_conditions)}]}}")

    where_clause = "{" + ", ".join(conditions) + "}"
    
    query = f"""
    query {{
      pokemon_v2_pokemonspecies(where: {where_clause}, order_by: {{id: asc}}) {{
        id
        pokemon_v2_pokemonspeciesnames(where: {{language_id: {{_eq: 5}}}}) {{
          name
        }}
        pokemon_v2_pokemons(where: {{is_default: {{_eq: true}}}}) {{
          pokemon_v2_pokemontypes {{
            pokemon_v2_type {{
              name
            }}
          }}
        }}
      }}
    }}
    """
    
    try:
        async with session.post(url, json={"query": query}) as resp:
            if resp.status == 200:
                data = await resp.json()
                results = []
                for node in data.get("data", {}).get("pokemon_v2_pokemonspecies", []):
                    names = node.get("pokemon_v2_pokemonspeciesnames", [])
                    name_fr = names[0]["name"] if names else f"Pokémon #{node['id']}"
                    
                    types = []
                    for p in node.get("pokemon_v2_pokemons", []):
                        for t in p.get("pokemon_v2_pokemontypes", []):
                            en_type = t["pokemon_v2_type"]["name"]
                            fr_type = TYPE_EN_TO_FR.get(en_type, en_type.capitalize())
                            types.append(fr_type)
                            
                    results.append({"id": str(node["id"]), "name": name_fr, "types": types})
                return results
    except Exception as e:
        print(f"Erreur GraphQL: {e}")
    return []

# ============================================================================
# --------------------------- BUILDER INTERACTIF -----------------------------
# ============================================================================

class SearchBuilderView(discord.ui.View):
    def __init__(self, bot, author):
        super().__init__(timeout=300)
        self.bot = bot
        self.author = author
        self.selected_gen = None
        self.selected_type1 = None
        self.selected_type2 = None

        # 1. Sélecteur de Génération
        self.gen_select = discord.ui.Select(placeholder="🌍 Choisir une Génération...", min_values=1, max_values=1, row=0)
        for i in range(1, 10):
            self.gen_select.add_option(label=f"Génération {i}", value=str(i))
        self.gen_select.callback = self.gen_callback
        self.add_item(self.gen_select)

        # 2. Sélecteur Type 1
        self.type1_select = discord.ui.Select(placeholder="🔥 Choisir le Type 1...", min_values=1, max_values=1, row=1)
        for t_fr in TYPE_EN_TO_FR.values():
            emoji_str = TYPE_EMOJIS.get(t_fr.replace("É", "E").replace("é", "e").replace("è", "e").replace("ê", "e").replace("ë", "e"), "❓")
            emoji_obj = discord.PartialEmoji.from_str(emoji_str) if emoji_str.startswith("<") else None
            self.type1_select.add_option(label=t_fr, value=t_fr, emoji=emoji_obj)
        self.type1_select.callback = self.type1_callback
        self.add_item(self.type1_select)

        # 3. Sélecteur Type 2
        self.type2_select = discord.ui.Select(placeholder="💧 Choisir le Type 2 (Optionnel)...", min_values=1, max_values=1, row=2)
        self.type2_select.add_option(label="Aucun (Type 2)", value="none", emoji="❌")
        for t_fr in TYPE_EN_TO_FR.values():
            emoji_str = TYPE_EMOJIS.get(t_fr.replace("É", "E").replace("é", "e").replace("è", "e").replace("ê", "e").replace("ë", "e"), "❓")
            emoji_obj = discord.PartialEmoji.from_str(emoji_str) if emoji_str.startswith("<") else None
            self.type2_select.add_option(label=t_fr, value=t_fr, emoji=emoji_obj)
        self.type2_select.callback = self.type2_callback
        self.add_item(self.type2_select)

        # 4. Bouton de validation
        self.search_btn = discord.ui.Button(label="Lancer la recherche", style=discord.ButtonStyle.success, emoji="🔍", row=3)
        self.search_btn.callback = self.search_callback
        self.add_item(self.search_btn)

    async def gen_callback(self, interaction: discord.Interaction):
        self.selected_gen = int(self.gen_select.values[0])
        await interaction.response.defer()

    async def type1_callback(self, interaction: discord.Interaction):
        self.selected_type1 = self.type1_select.values[0]
        await interaction.response.defer()

    async def type2_callback(self, interaction: discord.Interaction):
        val = self.type2_select.values[0]
        self.selected_type2 = None if val == "none" else val
        await interaction.response.defer()

    async def search_callback(self, interaction: discord.Interaction):
        if not self.selected_gen and not self.selected_type1 and not self.selected_type2:
            return await interaction.response.send_message("❌ Veuillez sélectionner au moins un critère de recherche !", ephemeral=True)
        
        await interaction.response.defer()
        
        async with aiohttp.ClientSession() as session:
            results = await fetch_filtered_pokemon(session, self.selected_type1, self.selected_type2, self.selected_gen)

        if not results:
            return await interaction.followup.send("❌ Aucun Pokémon ne correspond à ces critères exacts.", ephemeral=True)

        title_parts = []
        if self.selected_type1: title_parts.append(self.selected_type1)
        if self.selected_type2: title_parts.append(self.selected_type2)
        type_str = " + ".join(title_parts) if title_parts else "Tous types"
        gen_str = f"Génération {self.selected_gen}" if self.selected_gen else "Toutes générations"
        title_info = f"🔍 {type_str} | {gen_str}"

        # On affiche les résultats de la recherche
        view = RechercheView(self.bot, self.author, results, title_info)
        embed = view._get_embed(interaction.guild, interaction.user)
        
        await interaction.message.edit(embed=embed, view=view)
        view.message = interaction.message

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Cette interface ne vous appartient pas.", ephemeral=True)
            return False
        return True

# ============================================================================
# ----------------------------- PAGINATION UI --------------------------------
# ============================================================================

class RechercheView(discord.ui.View):
    def __init__(self, bot, author, pokemon_list, title_info: str):
        super().__init__(timeout=300)
        self.bot = bot
        self.author = author
        self.pokemon_list = pokemon_list
        self.title_info = title_info
        self.page = 0
        self.per_page = 25
        self.max_pages = max(0, math.ceil(len(pokemon_list) / self.per_page) - 1)
        
        self._update_components()

    def _get_embed(self, guild, author) -> discord.Embed:
        start = self.page * self.per_page
        end = start + self.per_page
        subset = self.pokemon_list[start:end]
        
        description = ""
        for i, poke in enumerate(subset, start=start + 1):
            type_emojis = "".join([TYPE_EMOJIS.get(t.replace("É", "E").replace("é", "e"), "❓") for t in poke["types"]])
            description += f"**{i}.** {type_emojis} **{poke['name']}** *(#{poke['id']})*\n"
            
        # On place le compte de résultats à la fin de la description, sans toucher au footer
        description += f"\n*🎯 {len(self.pokemon_list)} Pokémon trouvé(s) au total.*"
        
        if config_manager:
            # On génère l'embed via ton manager : le footer natif sera conservé
            embed = config_manager.get_formatted_embed(guild, author, self.bot, self.title_info, description)
        else:
            embed = discord.Embed(title=self.title_info, description=description, color=0x2B2D31)
            
        return embed

    def _update_components(self):
        self.clear_items()
        start = self.page * self.per_page
        end = start + self.per_page
        subset = self.pokemon_list[start:end]

        # Ligne 0 : Menu Sélecteur
        select = discord.ui.Select(placeholder="Sélectionnez un Pokémon pour voir sa fiche...", min_values=1, max_values=1, row=0)
        for i, poke in enumerate(subset, start=start + 1):
            select.add_option(
                label=f"{i}. {poke['name']}", 
                value=poke['id'], 
                description=" | ".join(poke["types"])
            )
        select.callback = self.select_callback
        self.add_item(select)

        # Ligne 1 : Navigation et actions
        # 1. Bouton Retour
        btn_back = discord.ui.Button(label="Retour", style=discord.ButtonStyle.danger, emoji="↩️", row=1)
        btn_back.callback = self.back_to_search
        self.add_item(btn_back)

        # 2. Bouton Précédent
        btn_prev = discord.ui.Button(label="◀", style=discord.ButtonStyle.secondary, disabled=(self.page == 0), row=1)
        btn_prev.callback = self.prev_page
        self.add_item(btn_prev)

        # 3. Bouton Page (Désactivé, sert juste d'indicateur visuel)
        btn_page = discord.ui.Button(label=f"Page {self.page + 1} / {self.max_pages + 1}", style=discord.ButtonStyle.secondary, disabled=True, row=1)
        self.add_item(btn_page)

        # 4. Bouton Suivant
        btn_next = discord.ui.Button(label="▶", style=discord.ButtonStyle.secondary, disabled=(self.page >= self.max_pages), row=1)
        btn_next.callback = self.next_page
        self.add_item(btn_next)

    async def back_to_search(self, interaction: discord.Interaction):
        # On retourne sur l'interface du builder interactif
        view = SearchBuilderView(self.bot, self.author)
        embed = get_search_help_embed(interaction.guild, interaction.user, self.bot)
        await interaction.response.edit_message(embed=embed, view=view)

    async def prev_page(self, interaction: discord.Interaction):
        self.page -= 1
        self._update_components()
        await interaction.response.edit_message(embed=self._get_embed(interaction.guild, interaction.user), view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.page += 1
        self._update_components()
        await interaction.response.edit_message(embed=self._get_embed(interaction.guild, interaction.user), view=self)

    async def select_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        query_id = interaction.data["values"][0]
        
        if generate_pokemon_profile:
            embed, view = await generate_pokemon_profile(self.bot, interaction.guild, interaction.user, query_id)
            if embed and view:
                msg = await interaction.followup.send(embed=embed, view=view, wait=True, ephemeral=True)
                view.message = msg
            else:
                await interaction.followup.send("❌ Impossible de charger ce Pokémon.", ephemeral=True)
        else:
            await interaction.followup.send(f"Détails du Pokémon ID: {query_id}", ephemeral=True)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Cette recherche ne vous appartient pas.", ephemeral=True)
            return False
        return True

# ============================================================================
# ----------------------------- COG RECHERCHE --------------------------------
# ============================================================================

class RechercheCommand(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="recherche", description="Recherche des Pokémon par filtres.")
    async def recherche(self, ctx: commands.Context, type1: str = None, type2: str = None, gen: int = None):
        await ctx.defer()
        
        # Aucun argument : On charge le Builder Interactif
        if not type1 and not type2 and not gen:
            embed = get_search_help_embed(ctx.guild, ctx.author, self.bot)
            view = SearchBuilderView(self.bot, ctx.author)
            msg = await ctx.send(embed=embed, view=view)
            return

        # Avec arguments : Mode raccourci
        async with aiohttp.ClientSession() as session:
            results = await fetch_filtered_pokemon(session, type1, type2, gen)

        if not results:
            return await ctx.send("❌ Aucun Pokémon ne correspond à ces critères.")

        title_parts = []
        if type1: title_parts.append(type1.capitalize())
        if type2: title_parts.append(type2.capitalize())
        type_str = " + ".join(title_parts) if title_parts else "Tous types"
        gen_str = f"Génération {gen}" if gen else "Toutes générations"
        title_info = f"🔍 Recherche : {type_str} | {gen_str}"

        view = RechercheView(self.bot, ctx.author, results, title_info)
        embed = view._get_embed(ctx.guild, ctx.author)
        
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

async def setup(bot: commands.Bot):
    await bot.add_cog(RechercheCommand(bot))