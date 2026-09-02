import discord
from discord.ext import commands
import aiohttp
import traceback
import re

# Import du manager personnalisé pour les embeds (Fallback global)
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# ============================================================================
# --------------------------- CONSTANTES ET MAPPING --------------------------
# ============================================================================

POKEBALL_EMOJI = "<:pokeball:1522952715846684782>"

TYPE_TRANSLATION = {
    "normal": "Normal", "fire": "Feu", "water": "Eau", "electric": "Électrik",
    "grass": "Plante", "ice": "Glace", "fighting": "Combat", "poison": "Poison",
    "ground": "Sol", "flying": "Vol", "psychic": "Psy", "bug": "Insecte",
    "rock": "Roche", "ghost": "Spectre", "dragon": "Dragon", "dark": "Ténèbres",
    "steel": "Acier", "fairy": "Fée",
}

TYPE_EMOJIS = {
    "Feu": "<:feu:1522937171135434833>", "Normal": "<:normal:1522937166496534609>",
    "Eau": "<:eau:1522937163249877103>", "Électrik": "<:elec:1522937159626264647>",
    "Plante": "<:plante:1522937156874539038>", "Glace": "<:glace:1522937153896579072>",
    "Combat": "<:combat:1522937150771826809>", "Poison": "<:poison:1522937148167295056>",
    "Sol": "<:sol:1522937144782618634>", "Vol": "<:vol:1522937142261710959>",
    "Psy": "<:psy:1522937139741065427>", "Insecte": "<:insecte:1522937136649736304>",
    "Roche": "<:roche:1522937133915046051>", "Dragon": "<:dragon:1522937131084025918>",
    "Ténèbres": "<:tenebres:1522937127279661248>", "Acier": "<:acier:1522937124335259658>",
    "Fée": "<:fee:1522937121202245732>", "Spectre": "<:spectre:1522937118094131281>",
}

# Table des interactions de types (Défenseur: {Attaquant: Multiplicateur})
TYPE_CHART = {
    "Normal": {"Combat": 2.0, "Spectre": 0.0},
    "Feu": {"Feu": 0.5, "Eau": 2.0, "Plante": 0.5, "Glace": 0.5, "Insecte": 0.5, "Roche": 2.0, "Sol": 2.0, "Acier": 0.5, "Fée": 0.5},
    "Eau": {"Feu": 0.5, "Eau": 0.5, "Électrik": 2.0, "Plante": 2.0, "Glace": 0.5, "Acier": 0.5},
    "Électrik": {"Électrik": 0.5, "Sol": 2.0, "Vol": 0.5, "Acier": 0.5},
    "Plante": {"Feu": 2.0, "Eau": 0.5, "Électrik": 0.5, "Plante": 0.5, "Glace": 2.0, "Poison": 2.0, "Sol": 0.5, "Vol": 2.0, "Insecte": 2.0},
    "Glace": {"Feu": 2.0, "Glace": 0.5, "Combat": 2.0, "Roche": 2.0, "Acier": 2.0},
    "Combat": {"Vol": 2.0, "Psy": 2.0, "Insecte": 0.5, "Roche": 0.5, "Ténèbres": 0.5, "Fée": 2.0},
    "Poison": {"Plante": 0.5, "Combat": 0.5, "Poison": 0.5, "Sol": 2.0, "Psy": 2.0, "Insecte": 0.5, "Fée": 0.5},
    "Sol": {"Eau": 2.0, "Électrik": 0.0, "Plante": 2.0, "Glace": 2.0, "Poison": 0.5, "Roche": 0.5},
    "Vol": {"Électrik": 2.0, "Plante": 0.5, "Combat": 0.5, "Sol": 0.0, "Glace": 2.0, "Insecte": 0.5, "Roche": 2.0},
    "Psy": {"Combat": 0.5, "Psy": 0.5, "Insecte": 2.0, "Spectre": 2.0, "Ténèbres": 2.0},
    "Insecte": {"Feu": 2.0, "Plante": 0.5, "Combat": 0.5, "Sol": 0.5, "Vol": 2.0, "Roche": 2.0},
    "Roche": {"Normal": 0.5, "Feu": 0.5, "Eau": 2.0, "Plante": 2.0, "Combat": 2.0, "Poison": 0.5, "Sol": 2.0, "Vol": 0.5, "Acier": 2.0},
    "Spectre": {"Normal": 0.0, "Combat": 0.0, "Poison": 0.5, "Insecte": 0.5, "Spectre": 2.0, "Ténèbres": 2.0},
    "Dragon": {"Feu": 0.5, "Eau": 0.5, "Électrik": 0.5, "Plante": 0.5, "Glace": 2.0, "Dragon": 2.0, "Fée": 2.0},
    "Ténèbres": {"Combat": 2.0, "Psy": 0.0, "Insecte": 2.0, "Spectre": 0.5, "Ténèbres": 0.5, "Fée": 2.0},
    "Acier": {"Normal": 0.5, "Feu": 2.0, "Plante": 0.5, "Glace": 0.5, "Combat": 2.0, "Poison": 0.0, "Sol": 2.0, "Vol": 0.5, "Psy": 0.5, "Insecte": 0.5, "Roche": 0.5, "Dragon": 0.5, "Acier": 0.5, "Fée": 0.5},
    "Fée": {"Combat": 0.5, "Poison": 2.0, "Insecte": 0.5, "Dragon": 0.0, "Ténèbres": 0.5, "Acier": 2.0}
}


# ============================================================================
# ----------------------------- OUTILS / HELPERS -----------------------------
# ============================================================================

def parse_custom_emoji(emoji_str: str) -> discord.PartialEmoji | None:
    match = re.match(r"^<a?:(?P<name>[^:]+):(?P<id>\d+)>$", emoji_str)
    if not match:
        return None
    return discord.PartialEmoji(name=match.group("name"), id=int(match.group("id")))


def get_embed(guild, user, bot, title, description, url_image=None):
    """Fallback automatique si le config_manager n'est pas trouvé."""
    if config_manager:
        embed = config_manager.get_formatted_embed(guild, user, bot, title=title, description=description, target_id=guild.id if guild else None)
    else:
        embed = discord.Embed(title=title, description=description, color=0x2b2d31)
    
    if url_image:
        embed.set_thumbnail(url=url_image)
    return embed


def calculate_weaknesses(types: list[str]) -> dict:
    """Croise les faiblesses des types choisis (jusqu'à 2) et retourne les affinités."""
    multipliers = {t: 1.0 for t in TYPE_CHART.keys()}
    
    for def_type in types:
        if def_type not in TYPE_CHART:
            continue
        for atk_type, mult in TYPE_CHART[def_type].items():
            multipliers[atk_type] *= mult

    results = {"X4": [], "X2": [], "X0.5": [], "X0.25": [], "X0": []}
    for atk, val in multipliers.items():
        if val == 4.0: results["X4"].append(atk)
        elif val == 2.0: results["X2"].append(atk)
        elif val == 0.5: results["X0.5"].append(atk)
        elif val == 0.25: results["X0.25"].append(atk)
        elif val == 0.0: results["X0"].append(atk)
        
    return results


def format_weakness_display(results: dict, types: list[str], name: str = None) -> str:
    """Formate le dictionnaire de faiblesses en un texte lisible pour l'embed."""
    types_str = " | ".join([f"{TYPE_EMOJIS.get(t, '')} {t}" for t in types])
    
    header = f"**Types défensifs :** {types_str}\n\n"
    if name:
        header = f"### {name}\n" + header
        
    lines = []
    
    if results["X4"]:
        lines.append("🔴 **Dégâts reçus x4 (Faiblesse double) :**\n" + " | ".join([f"{TYPE_EMOJIS.get(t, '')} {t}" for t in results["X4"]]))
    
    if results["X2"]:
        lines.append("🟠 **Dégâts reçus x2 (Faiblesse) :**\n" + " | ".join([f"{TYPE_EMOJIS.get(t, '')} {t}" for t in results["X2"]]))
    
    if results["X0.5"]:
        lines.append("🟢 **Dégâts reçus x0.5 (Résistance) :**\n" + " | ".join([f"{TYPE_EMOJIS.get(t, '')} {t}" for t in results["X0.5"]]))
    
    if results["X0.25"]:
        lines.append("🔵 **Dégâts reçus x0.25 (Double résistance) :**\n" + " | ".join([f"{TYPE_EMOJIS.get(t, '')} {t}" for t in results["X0.25"]]))
    
    if results["X0"]:
        lines.append("⚪ **Dégâts reçus x0 (Immunité) :**\n" + " | ".join([f"{TYPE_EMOJIS.get(t, '')} {t}" for t in results["X0"]]))
        
    if not lines:
        lines.append("Aucune faiblesse ou résistance notable.")
        
    return header + "\n\n".join(lines)


async def fetch_pokemon_data(query: str) -> tuple[dict, str, str]:
    """Récupère les informations depuis l'API Pokémon (Gère l'ID, Nom EN ou FR)."""
    async with aiohttp.ClientSession() as session:
        query_clean = str(query).strip().lower().lstrip("0")
        poke_id = query_clean
        
        # Résolution FR vers ID si le terme n'est pas numérique
        if not query_clean.isdigit():
            graphql_query = """
            query($name: String!) {
              pokemon_v2_pokemonspeciesname(where: {language_id: {_eq: 5}, name: {_ilike: $name}}, limit: 1) {
                pokemon_species_id
              }
            }
            """
            try:
                payload = {"query": graphql_query, "variables": {"name": f"{query_clean}%"}}
                async with session.post("https://beta.pokeapi.co/graphql/v1beta", json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results = data.get("data", {}).get("pokemon_v2_pokemonspeciesname", [])
                        if results:
                            poke_id = str(results[0]["pokemon_species_id"])
            except Exception:
                pass

        # Récupération finale sur l'API principale
        async with session.get(f"https://pokeapi.co/api/v2/pokemon/{poke_id}") as resp_data:
            if resp_data.status != 200:
                return None, f"❌ Pokémon '{query}' introuvable. Vérifiez l'orthographe ou l'ID.", None
            data = await resp_data.json()
            
        async with session.get(f"https://pokeapi.co/api/v2/pokemon-species/{data['id']}") as resp_species:
            if resp_species.status == 200:
                species = await resp_species.json()
                name_fr = next((n["name"] for n in species["names"] if n["language"]["name"] == "fr"), data["name"].capitalize())
            else:
                name_fr = data["name"].capitalize()
                
        image = data.get("sprites", {}).get("other", {}).get("official-artwork", {}).get("front_default") or data.get("sprites", {}).get("front_default")
        return data, name_fr, image


# ============================================================================
# ----------------------------- INTERFACES (UI) ------------------------------
# ============================================================================

class PokemonSearchModal(discord.ui.Modal, title="Recherche de Faiblesses"):
    query = discord.ui.TextInput(
        label="Nom ou ID du Pokémon",
        style=discord.TextStyle.short,
        placeholder="Exemple : Bulbizarre, Dracaufeu, 150...",
        required=True
    )

    def __init__(self, bot, view):
        super().__init__()
        self.bot = bot
        self.view_parent = view

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        data, name_fr, image = await fetch_pokemon_data(self.query.value)
        
        if not data:
            return await interaction.followup.send(name_fr, ephemeral=True)

        types_api = [t["type"]["name"] for t in data["types"]]
        types_fr = [TYPE_TRANSLATION.get(t, t.capitalize()) for t in types_api]
        
        results = calculate_weaknesses(types_fr)
        desc = format_weakness_display(results, types_fr, name_fr)
        
        embed = get_embed(interaction.guild, interaction.user, self.bot, "📊 Analyse Stratégique", desc, image)
        
        await interaction.message.edit(embed=embed, view=self.view_parent)


class TypeSelect(discord.ui.Select):
    def __init__(self, bot):
        self.bot = bot
        options = []
        for t in TYPE_CHART.keys():
            emoji_obj = parse_custom_emoji(TYPE_EMOJIS[t])
            options.append(discord.SelectOption(label=t, emoji=emoji_obj if emoji_obj else None))
            
        super().__init__(
            placeholder="📍 Sélectionnez 1 ou 2 types...",
            min_values=1,
            max_values=2,
            options=options,
            row=0  # Force le Select sur la première ligne
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        types_choisis = self.values
        
        results = calculate_weaknesses(types_choisis)
        desc = format_weakness_display(results, types_choisis)
        
        embed = get_embed(interaction.guild, interaction.user, self.bot, "📊 Analyse Stratégique", desc)
        
        await interaction.message.edit(embed=embed, view=self.view)


class WeaknessView(discord.ui.View):
    def __init__(self, bot, author):
        super().__init__(timeout=300)
        self.bot = bot
        self.author = author
        self.message = None

        self.add_item(TypeSelect(bot))

    # row=1 garantit que le bouton se trouve en dessous du Select
    @discord.ui.button(label="Rechercher par Pokémon", style=discord.ButtonStyle.primary, row=1)
    async def search_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # On définit l'emoji manuellement pour éviter toute erreur de parsing si l'emoji Custom échoue
        button_emoji = parse_custom_emoji(POKEBALL_EMOJI) or "🔍"
        button.emoji = button_emoji
        
        await interaction.response.send_modal(PokemonSearchModal(self.bot, self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


# ============================================================================
# ------------------------------- COG PRINCIPAL ------------------------------
# ============================================================================

class FaiblessesCommand(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name="faiblesses",
        aliases=["faiblesse"],
        description="Affiche le tableau des faiblesses stratégiques."
    )
    async def faiblesses(self, ctx: commands.Context, *, query: str = None):
        await ctx.defer(ephemeral=False)
        
        try:
            # SI L'UTILISATEUR ENTRE UNE RECHERCHE DIRECTEMENT (!faiblesses bulbizarre)
            if query:
                data, name_fr, image = await fetch_pokemon_data(query)
                if not data:
                    return await ctx.send(name_fr)
                    
                types_api = [t["type"]["name"] for t in data["types"]]
                types_fr = [TYPE_TRANSLATION.get(t, t.capitalize()) for t in types_api]
                
                results = calculate_weaknesses(types_fr)
                desc = format_weakness_display(results, types_fr, name_fr)
                
                embed = get_embed(ctx.guild, ctx.author, self.bot, "📊 Analyse Stratégique", desc, image)
                
                view = WeaknessView(self.bot, ctx.author)
                msg = await ctx.send(embed=embed, view=view)
                view.message = msg
            
            # SI L'UTILISATEUR OUVRE LE MENU INTERACTIF (!faiblesses)
            else:
                desc = (
                    "**Comment utiliser cette commande ?**\n\n"
                    "1️⃣ **Sélectionnez 1 ou 2 types** dans le menu déroulant ci-dessous pour voir leurs interactions combinées.\n"
                    "2️⃣ **Cliquez sur le bouton de recherche** pour analyser directement un Pokémon (Nom ou ID)."
                )
                embed = get_embed(ctx.guild, ctx.author, self.bot, "📊 Centre d'Analyse Stratégique", desc)
                
                view = WeaknessView(self.bot, ctx.author)
                msg = await ctx.send(embed=embed, view=view)
                view.message = msg

        except Exception as e:
            print("[ERROR - FaiblessesCommand] Une erreur fatale est survenue :")
            traceback.print_exc()
            
            error_msg = "❌ Une erreur inattendue s'est produite lors du calcul des faiblesses."
            if ctx.interaction:
                await ctx.interaction.followup.send(error_msg, ephemeral=True)
            else:
                await ctx.send(error_msg, reference=ctx.message)

async def setup(bot: commands.Bot):
    await bot.add_cog(FaiblessesCommand(bot))