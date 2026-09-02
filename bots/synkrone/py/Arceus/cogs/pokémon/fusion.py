import discord
from discord.ext import commands
import aiohttp
import io
import math
from PIL import Image, ImageDraw, ImageFont

# Tentative d'import du manager d'embed (Fallback global)
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# ============================================================================
# --------------------------- CONSTANTES ET MAPPING --------------------------
# ============================================================================

TYPE_EN_TO_FR = {
    "normal": "Normal", "fire": "Feu", "water": "Eau", "electric": "Électrik",
    "grass": "Plante", "ice": "Glace", "fighting": "Combat", "poison": "Poison",
    "ground": "Sol", "flying": "Vol", "psychic": "Psy", "bug": "Insecte",
    "rock": "Roche", "ghost": "Spectre", "dragon": "Dragon", "dark": "Ténèbres",
    "steel": "Acier", "fairy": "Fée"
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
    "Fée": "<:fee:1522937121202245732>", "Spectre": "<:spectre:1522937118094131281>"
}

# ============================================================================
# ----------------------------- OUTILS / HELPERS -----------------------------
# ============================================================================

def get_embed(guild, user, bot, title, description):
    """Fallback automatique si le config_manager n'est pas trouvé."""
    if config_manager:
        embed = config_manager.get_formatted_embed(guild, user, bot, title=title, description=description, target_id=guild.id if guild else None)
    else:
        embed = discord.Embed(title=title, description=description, color=0x2B2D31)
    
    # Ajout du thumbnail du Bot
    if bot.user.display_avatar:
        embed.set_thumbnail(url=bot.user.display_avatar.url)
        
    return embed

def mix_names(name1: str, name2: str) -> str:
    """Mélange les deux noms pour créer le nom hybride."""
    part1 = name1[:math.ceil(len(name1) / 2)]
    part2 = name2[math.floor(len(name2) / 2):]
    return (part1 + part2).capitalize()

async def get_id_from_french_name(session: aiohttp.ClientSession, name: str) -> int | None:
    """Vérifie si un nom existe en français via l'API GraphQL et retourne son ID."""
    url = "https://beta.pokeapi.co/graphql/v1beta"
    query = """
    query($name: String!) {
      pokemon_v2_pokemonspeciesname(where: {language_id: {_eq: 5}, name: {_ilike: $name}}, limit: 1) {
        pokemon_species_id
      }
    }
    """
    try:
        payload = {"query": query, "variables": {"name": f"{name.lower()}"}}
        async with session.post(url, json=payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                results = data.get('data', {}).get('pokemon_v2_pokemonspeciesname', [])
                if results:
                    return results[0]['pokemon_species_id']
    except Exception:
        pass
    return None

async def fetch_pokemon_data(session: aiohttp.ClientSession, query: str):
    """Récupère les informations complètes d'un Pokémon."""
    query_clean = query.lower().strip()
    poke_id = query_clean
    
    if not query_clean.isdigit():
        french_id = await get_id_from_french_name(session, query_clean)
        if french_id:
            poke_id = str(french_id)

    url = f"https://pokeapi.co/api/v2/pokemon/{poke_id}"
    async with session.get(url) as resp:
        if resp.status == 200:
            data = await resp.json()
            
            # Fetch le nom en français
            async with session.get(data["species"]["url"]) as species_resp:
                if species_resp.status == 200:
                    s_data = await species_resp.json()
                    data["name_fr"] = next((n["name"] for n in s_data["names"] if n["language"]["name"] == "fr"), data["name"].capitalize())
                else:
                    data["name_fr"] = data["name"].capitalize()
            return data
    return None

# ============================================================================
# ----------------------------- GÉNÉRATION D'IMAGES --------------------------
# ============================================================================

async def create_spliced_fusion_image(session: aiohttp.ClientSession, url1: str, url2: str) -> discord.File:
    """Découpe les sprites horizontalement et crée une fusion symétrique."""
    # Canvas symétrique carré
    img = Image.new("RGBA", (400, 400), (43, 45, 49, 255))
    draw = ImageDraw.Draw(img)

    # Ligne de séparation (marquant la fusion)
    draw.rectangle([0, 0, 400, 200], fill=(35, 37, 40, 255)) # Moitié Haute
    draw.rectangle([0, 200, 400, 400], fill=(28, 30, 33, 255)) # Moitié Basse
    
    # Effet Laser au centre
    draw.line([0, 200, 400, 200], fill=(0, 255, 150, 180), width=4)

    # Halo central lumineux
    draw.ellipse([80, 80, 320, 320], fill=(43, 45, 49, 255), outline=(0, 255, 150, 120), width=2)

    async def fetch_img(url):
        try:
            async with session.get(url) as r:
                return Image.open(io.BytesIO(await r.read())).convert("RGBA").resize((240, 240))
        except Exception:
            return Image.new("RGBA", (240, 240), (0, 0, 0, 0))

    img1 = await fetch_img(url1)
    img2 = await fetch_img(url2)

    # --- DÉCOUPE HORIZONTALE STRICTE ---
    # Tête (Moitié haute du Sprite 1)
    top_half = img1.crop((0, 0, 240, 120))
    # Corps (Moitié basse du Sprite 2)
    bottom_half = img2.crop((0, 120, 240, 240))

    # --- RECOMBINAISON ---
    hybrid = Image.new("RGBA", (240, 240), (0, 0, 0, 0))
    hybrid.paste(top_half, (0, 0))
    hybrid.paste(bottom_half, (0, 120))

    # Centrage de l'hybride sur le Canvas (400x400 -> centre = 200, donc offset de 80 car l'image fait 240)
    img.paste(hybrid, (80, 80), hybrid)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return discord.File(buf, filename="fusion.png")

# ============================================================================
# ----------------------------- LOGIQUE CENTRALE -----------------------------
# ============================================================================

async def process_fusion(bot, interaction_or_ctx, author, query1: str, query2: str, is_interaction=False):
    async with aiohttp.ClientSession() as session:
        p1 = await fetch_pokemon_data(session, query1)
        p2 = await fetch_pokemon_data(session, query2)

        if not p1 or not p2:
            error_msg = "❌ Impossible de générer la fusion. Vérifiez l'orthographe ou l'ID des Pokémon."
            if is_interaction:
                return await interaction_or_ctx.followup.send(error_msg, ephemeral=True)
            else:
                return await interaction_or_ctx.send(error_msg)

        id1, id2 = p1["id"], p2["id"]
        nom1, nom2 = p1["name_fr"], p2["name_fr"]

        # Nouveau Nom
        fusion_name = mix_names(nom1, nom2)

        # Nouveaux Types
        types_p1 = [TYPE_EN_TO_FR.get(t['type']['name'], t['type']['name'].capitalize()) for t in p1['types']]
        types_p2 = [TYPE_EN_TO_FR.get(t['type']['name'], t['type']['name'].capitalize()) for t in p2['types']]
        
        type1 = types_p1[0]
        type2 = types_p2[-1] 

        fusion_types = [type1]
        if type2 != type1:
            fusion_types.append(type2)

        types_formatted = " | ".join([f"{TYPE_EMOJIS.get(t, '❓')} {t}" for t in fusion_types])

        # Nouvelles stats (Moyenne)
        stats1 = {s["stat"]["name"]: s["base_stat"] for s in p1["stats"]}
        stats2 = {s["stat"]["name"]: s["base_stat"] for s in p2["stats"]}
        
        # Génération de l'image découpée horizontalement
        sprite1_url = p1.get("sprites", {}).get("other", {}).get("official-artwork", {}).get("front_default") or p1["sprites"]["front_default"]
        sprite2_url = p2.get("sprites", {}).get("other", {}).get("official-artwork", {}).get("front_default") or p2["sprites"]["front_default"]
        
        # Test de l'image custom Infinite Fusion (Aegide) - Fallback sur notre découpe
        fusion_url_custom = f"https://raw.githubusercontent.com/Aegide/custom-fusion-sprites/main/CustomBattlers/{id1}.{id2}.png"
        
        async with session.get(fusion_url_custom) as resp:
            if resp.status == 200:
                img_data = await resp.read()
                file = discord.File(io.BytesIO(img_data), filename="fusion.png")
            else:
                file = await create_spliced_fusion_image(session, sprite1_url, sprite2_url)

        # Description Épurée et formatée Markdown
        desc = (
            f"# 🧬 {fusion_name}\n"
            f"*(Fusion de {nom1} et {nom2})*\n\n"
            f"{types_formatted}\n\n"
            f"### 📊 Statistiques estimées\n"
        )

        embed = get_embed(interaction_or_ctx.guild, author, bot, "🧪 Centre de Fusion Pokémon", desc)
        embed.set_image(url="attachment://fusion.png")

        # Ajout des stats en fields pour que ce soit aéré
        stats_names = [("hp", "❤️ PV"), ("attack", "⚔️ ATQ"), ("defense", "🛡️ DEF"), ("special-attack", "🔮 ATQ SPÉ"), ("special-defense", "🌟 DEF SPÉ"), ("speed", "💨 VIT")]
        for s_en, s_fr in stats_names:
            avg_stat = math.floor((stats1.get(s_en, 0) + stats2.get(s_en, 0)) / 2)
            embed.add_field(name=s_fr, value=f"**{avg_stat}**", inline=True)

        view = FusionView(bot, author, query1, query2)

        if is_interaction:
            await interaction_or_ctx.message.edit(embed=embed, view=view, attachments=[file])
        else:
            await interaction_or_ctx.send(embed=embed, view=view, file=file)


# ============================================================================
# ----------------------------- INTERFACES (UI) ------------------------------
# ============================================================================

class FusionModal(discord.ui.Modal, title="🧪 Nouvelle Fusion"):
    poke1 = discord.ui.TextInput(
        label="Tête (Pokémon 1)", 
        style=discord.TextStyle.short, 
        placeholder="Ex: Dracaufeu", 
        required=True
    )
    poke2 = discord.ui.TextInput(
        label="Corps (Pokémon 2)", 
        style=discord.TextStyle.short, 
        placeholder="Ex: Tortank", 
        required=True
    )

    def __init__(self, bot, author):
        super().__init__()
        self.bot = bot
        self.author = author

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await process_fusion(self.bot, interaction, self.author, self.poke1.value, self.poke2.value, is_interaction=True)


class FusionView(discord.ui.View):
    def __init__(self, bot, author, current_p1, current_p2):
        super().__init__(timeout=300)
        self.bot = bot
        self.author = author
        self.current_p1 = current_p1
        self.current_p2 = current_p2

    @discord.ui.button(label="Inverser la fusion", style=discord.ButtonStyle.primary, emoji="🔄")
    async def swap_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await process_fusion(self.bot, interaction, self.author, self.current_p2, self.current_p1, is_interaction=True)

    @discord.ui.button(label="Changer de fusion", style=discord.ButtonStyle.success, emoji="🧪")
    async def change_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(FusionModal(self.bot, self.author))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Cette interface de fusion ne vous appartient pas.", ephemeral=True)
            return False
        return True


# ============================================================================
# ------------------------------- COG PRINCIPAL ------------------------------
# ============================================================================

class FusionCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="fusion", description="Fusionne deux Pokémon.")
    async def fusion(self, ctx: commands.Context, poke1: str, poke2: str):
        await ctx.defer()
        await process_fusion(self.bot, ctx, ctx.author, poke1, poke2, is_interaction=False)

async def setup(bot):
    await bot.add_cog(FusionCommand(bot))