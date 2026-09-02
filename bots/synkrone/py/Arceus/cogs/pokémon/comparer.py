import io
import discord
import aiohttp
from PIL import Image, ImageDraw, ImageFont
from discord.ext import commands

# Import du config_manager si disponible
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# ============================================================================
# --------------------------- CONSTANTES ET MAPPING --------------------------
# ============================================================================

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

TYPE_CHART = {
    "normal": {"rock": 0.5, "ghost": 0.0, "steel": 0.5},
    "fighting": {"normal": 2.0, "flying": 0.5, "poison": 0.5, "rock": 2.0, "bug": 0.5, "ghost": 0.0, "steel": 2.0, "psychic": 0.5, "ice": 2.0, "dark": 2.0, "fairy": 0.5},
    "flying": {"fighting": 2.0, "rock": 0.5, "bug": 2.0, "steel": 0.5, "grass": 2.0, "electric": 0.5},
    "poison": {"poison": 0.5, "ground": 0.5, "rock": 0.5, "ghost": 0.5, "steel": 0.0, "grass": 2.0, "fairy": 2.0},
    "ground": {"flying": 0.0, "poison": 2.0, "rock": 2.0, "bug": 0.5, "steel": 2.0, "fire": 2.0, "grass": 0.5, "electric": 2.0},
    "rock": {"fighting": 0.5, "flying": 2.0, "ground": 0.5, "bug": 2.0, "steel": 0.5, "fire": 2.0, "ice": 2.0},
    "bug": {"fighting": 0.5, "flying": 0.5, "poison": 0.5, "ghost": 0.5, "steel": 0.5, "fire": 0.5, "grass": 2.0, "psychic": 2.0, "fairy": 0.5},
    "ghost": {"normal": 0.0, "ghost": 2.0, "dark": 0.5},
    "steel": {"rock": 2.0, "steel": 0.5, "fire": 0.5, "water": 0.5, "electric": 0.5, "ice": 2.0, "fairy": 2.0},
    "fire": {"rock": 0.5, "bug": 2.0, "steel": 2.0, "fire": 0.5, "water": 0.5, "grass": 2.0, "ice": 2.0, "dragon": 0.5},
    "water": {"ground": 2.0, "rock": 2.0, "fire": 2.0, "water": 0.5, "grass": 0.5, "dragon": 0.5},
    "grass": {"flying": 0.5, "poison": 0.5, "ground": 2.0, "rock": 2.0, "bug": 0.5, "steel": 0.5, "fire": 0.5, "water": 2.0, "grass": 0.5, "dragon": 0.5},
    "electric": {"flying": 2.0, "ground": 0.0, "water": 2.0, "grass": 0.5, "electric": 0.5, "dragon": 0.5},
    "psychic": {"fighting": 2.0, "poison": 2.0, "steel": 0.5, "psychic": 0.5, "dark": 0.0},
    "ice": {"flying": 2.0, "ground": 2.0, "steel": 0.5, "fire": 0.5, "water": 0.5, "grass": 2.0, "ice": 0.5, "dragon": 2.0},
    "dragon": {"steel": 0.5, "dragon": 2.0, "fairy": 0.0},
    "dark": {"fighting": 0.5, "ghost": 2.0, "psychic": 2.0, "dark": 0.5, "fairy": 0.5},
    "fairy": {"fighting": 2.0, "poison": 0.5, "steel": 0.5, "fire": 0.5, "dragon": 2.0, "dark": 2.0}
}

# Ordre exact exigé : PV / ATQ / DEF, puis VIT / ATQ SPE / DEF SPE
ORDERED_STATS = [
    ("hp", "❤️", "PV"),
    ("attack", "⚔️", "ATQ"),
    ("defense", "🛡️", "DEF"),
    ("speed", "💨", "VIT"),
    ("special-attack", "🔮", "ATQ SPÉ"),
    ("special-defense", "🌟", "DEF SPÉ")
]

# ============================================================================
# ----------------------------- OUTILS / HELPERS -----------------------------
# ============================================================================

def get_best_multiplier(atk_types: list[str], def_types: list[str]) -> float:
    best = 0.0
    for a_type in atk_types:
        mult = 1.0
        for d_type in def_types:
            mult *= TYPE_CHART.get(a_type, {}).get(d_type, 1.0)
        if mult > best:
            best = mult
    return best

async def get_id_from_french_name(session: aiohttp.ClientSession, name: str) -> int | None:
    url = "https://beta.pokeapi.co/graphql/v1beta"
    query = """
    query($name: String!) {
      pokemon_v2_pokemonspeciesname(where: {language_id: {_eq: 5}, name: {_ilike: $name}}, limit: 1) {
        pokemon_species_id
      }
    }
    """
    try:
        payload = {"query": query, "variables": {"name": f"{name.lower()}%"}}
        async with session.post(url, json=payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                results = data.get("data", {}).get("pokemon_v2_pokemonspeciesname", [])
                if results:
                    return results[0]["pokemon_species_id"]
    except Exception:
        pass
    return None

async def fetch_pokemon_data(session: aiohttp.ClientSession, query: str):
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

async def generate_merged_image(session: aiohttp.ClientSession, url1: str, url2: str, name1: str, name2: str) -> discord.File | None:
    try:
        async with session.get(url1) as r1, session.get(url2) as r2:
            data1 = await r1.read()
            data2 = await r2.read()

        img1 = Image.open(io.BytesIO(data1)).convert("RGBA")
        img2 = Image.open(io.BytesIO(data2)).convert("RGBA")

        # Redimensionnement au cas où ce serait trop grand
        img1.thumbnail((300, 300))
        img2.thumbnail((300, 300))

        w1, h1 = img1.size
        w2, h2 = img2.size
        spacing = 50
        text_padding = 40
        
        total_width = w1 + w2 + spacing
        max_height = max(h1, h2) + text_padding

        new_img = Image.new("RGBA", (total_width, max_height), (0, 0, 0, 0))
        
        # Positionnement des sprites
        img1_y = max_height - text_padding - h1
        img2_y = max_height - text_padding - h2
        new_img.paste(img1, (0, img1_y), img1)
        new_img.paste(img2, (w1 + spacing, img2_y), img2)

        # Ajout du texte
        draw = ImageDraw.Draw(new_img)
        try:
            # Tente de charger une police par défaut plus grande si disponible
            font = ImageFont.load_default(size=22)
        except Exception:
            font = ImageFont.load_default()

        # Fonction utilitaire pour centrer le texte selon les versions de Pillow
        def get_text_width(text):
            try:
                return draw.textbbox((0, 0), text, font=font)[2]
            except AttributeError:
                return draw.textsize(text, font=font)[0]

        tw1 = get_text_width(name1)
        tw2 = get_text_width(name2)

        x1 = (w1 - tw1) // 2
        x2 = w1 + spacing + (w2 - tw2) // 2
        y_text = max_height - text_padding + 10

        draw.text((x1, y_text), name1, fill=(255, 255, 255, 255), font=font)
        draw.text((x2, y_text), name2, fill=(255, 255, 255, 255), font=font)

        buffer = io.BytesIO()
        new_img.save(buffer, format="PNG")
        buffer.seek(0)
        
        return discord.File(fp=buffer, filename="compare.png")
    except Exception as e:
        print(f"Erreur Pillow: {e}")
        return None

# ============================================================================
# --------------------------- INTERFACE UTILISATEUR --------------------------
# ============================================================================

class ComparerModal(discord.ui.Modal, title='Comparaison Pokémon'):
    poke1 = discord.ui.TextInput(label='Premier Pokémon (Nom ou ID)', placeholder='Ex: Pikachu', required=True)
    poke2 = discord.ui.TextInput(label='Second Pokémon (Nom ou ID)', placeholder='Ex: Evoli', required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        cog = getattr(self.view, "cog", None)
        if cog:
            await cog.run_comparison(interaction, str(self.poke1), str(self.poke2))

class ComparerView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=120)
        self.cog = cog

    @discord.ui.button(label="Nouvelle comparaison", style=discord.ButtonStyle.primary, custom_id="btn_comp_modal", emoji="🔄")
    async def open_modal(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = ComparerModal()
        modal.view = self
        await interaction.response.send_modal(modal)


# ============================================================================
# ------------------------------- COG PRINCIPAL ------------------------------
# ============================================================================

class ComparerCommand(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def run_comparison(self, context_or_interaction, poke1: str, poke2: str):
        is_interaction = isinstance(context_or_interaction, discord.Interaction)
        
        async with aiohttp.ClientSession() as session:
            d1 = await fetch_pokemon_data(session, poke1)
            d2 = await fetch_pokemon_data(session, poke2)
            
            error_msg = "❌ Un des deux Pokémon est introuvable. Vérifiez l'orthographe."
            if not d1 or not d2:
                if is_interaction:
                    await context_or_interaction.followup.send(error_msg, ephemeral=True)
                else:
                    await context_or_interaction.send(error_msg)
                return

            n1 = d1['name_fr']
            n2 = d2['name_fr']

            # ----------------- TYPES & DOMINANCE -----------------
            t1_en = [t["type"]["name"] for t in d1["types"]]
            t2_en = [t["type"]["name"] for t in d2["types"]]

            t1_fr = [TYPE_TRANSLATION.get(t, t.capitalize()) for t in t1_en]
            t2_fr = [TYPE_TRANSLATION.get(t, t.capitalize()) for t in t2_en]

            t1_formatted = " | ".join([f"{TYPE_EMOJIS.get(t, '❓')} {t}" for t in t1_fr])
            t2_formatted = " | ".join([f"{TYPE_EMOJIS.get(t, '❓')} {t}" for t in t2_fr])

            mult_1_vs_2 = get_best_multiplier(t1_en, t2_en)
            mult_2_vs_1 = get_best_multiplier(t2_en, t1_en)

            dominance_text = "⚔️ **Égalité des types** (Aucun avantage majeur)."
            if mult_1_vs_2 > mult_2_vs_1:
                dominance_text = f"🟢 **{n1}** a l'avantage ! (Dégâts potentiels **x{mult_1_vs_2}**)"
            elif mult_2_vs_1 > mult_1_vs_2:
                dominance_text = f"🔴 **{n2}** a l'avantage ! (Dégâts potentiels **x{mult_2_vs_1}**)"

            # ----------------- STATISTIQUES & TOTAL -----------------
            stats1 = {s["stat"]["name"]: s["base_stat"] for s in d1["stats"]}
            stats2 = {s["stat"]["name"]: s["base_stat"] for s in d2["stats"]}
            
            tot1 = sum(stats1.values())
            tot2 = sum(stats2.values())
            
            str_tot1 = f"**{tot1}**" if tot1 > tot2 else str(tot1)
            str_tot2 = f"**{tot2}**" if tot2 > tot1 else str(tot2)

            # ----------------- EMBED -----------------
            desc = (
                f"**{n1}** : {t1_formatted}\n"
                f"**{n2}** : {t2_formatted}\n\n"
                f"⚖️ **Dominance :**\n> {dominance_text}\n\n"
                f"📊 **Total des statistiques :**\n> **{n1}** : {str_tot1}  |  **{n2}** : {str_tot2}"
            )

            if config_manager:
                guild = context_or_interaction.guild if hasattr(context_or_interaction, "guild") else None
                user = context_or_interaction.user if is_interaction else context_or_interaction.author
                embed = config_manager.get_formatted_embed(
                    guild=guild, user=user, bot=self.bot, 
                    title=f"Comparaison : {n1} vs {n2}", description=desc
                )
            else:
                embed = discord.Embed(title=f"Comparaison : {n1} vs {n2}", description=desc, color=0x2B2D31)

            # ----------------- FIELDS (Ordre exact) -----------------
            for stat_en, emoji, nom_fr in ORDERED_STATS:
                v1, v2 = stats1.get(stat_en, 0), stats2.get(stat_en, 0)
                str_v1 = f"**{v1}**" if v1 > v2 else str(v1)
                str_v2 = f"**{v2}**" if v2 > v1 else str(v2)
                
                embed.add_field(name=f"{emoji} {nom_fr}", value=f"{str_v1} 🆚 {str_v2}", inline=True)

            # ----------------- GENERATION IMAGE -----------------
            url1 = d1.get("sprites", {}).get("other", {}).get("official-artwork", {}).get("front_default") or d1["sprites"]["front_default"]
            url2 = d2.get("sprites", {}).get("other", {}).get("official-artwork", {}).get("front_default") or d2["sprites"]["front_default"]

            image_file = await generate_merged_image(session, url1, url2, n1, n2)
            if image_file:
                embed.set_image(url="attachment://compare.png")

            # ----------------- ENVOI -----------------
            view = ComparerView(self)
            kwargs = {"embed": embed, "view": view}
            if image_file:
                kwargs["file"] = image_file

            if is_interaction:
                await context_or_interaction.followup.send(**kwargs)
            else:
                await context_or_interaction.send(**kwargs)


    @commands.hybrid_command(name="comparer", description="Compare deux Pokémon.")
    async def comparer_cmd(self, ctx: commands.Context, poke1: str = None, poke2: str = None):
        if not poke1 or not poke2:
            embed = discord.Embed(
                title="⚖️ Comparateur Pokémon", 
                description="Cliquez sur le bouton ci-dessous pour choisir les deux Pokémon à comparer (Nom Français, Anglais ou ID).", 
                color=0x2B2D31
            )
            await ctx.send(embed=embed, view=ComparerView(self))
            return

        await ctx.defer()
        await self.run_comparison(ctx, poke1, poke2)

async def setup(bot: commands.Bot):
    await bot.add_cog(ComparerCommand(bot))