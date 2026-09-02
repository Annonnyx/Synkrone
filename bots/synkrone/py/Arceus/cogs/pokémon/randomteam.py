import discord
from discord.ext import commands
import aiohttp
import random
import asyncio
import io
from PIL import Image, ImageDraw, ImageFont

# Tentative d'import du manager d'embed (Fallback global)
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# ============================================================================
# --------------------------- CONSTANTES ET MAPPING --------------------------
# ============================================================================

SHINY_EMOJI = "<:shiny:1522947934969270312>"

TYPE_EN_TO_FR = {
    "normal": "Normal", "fire": "Feu", "water": "Eau", "electric": "Électrik",
    "grass": "Plante", "ice": "Glace", "fighting": "Combat", "poison": "Poison",
    "ground": "Sol", "flying": "Vol", "psychic": "Psy", "bug": "Insecte",
    "rock": "Roche", "ghost": "Spectre", "dragon": "Dragon", "dark": "Ténèbres",
    "steel": "Acier", "fairy": "Fée"
}

TYPE_FR_TO_EN = {v.lower(): k for k, v in TYPE_EN_TO_FR.items()}
TYPE_FR_TO_EN.update({"electrik": "electric", "electrique": "electric", "tenebres": "dark", "fee": "fairy"})

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
    
    embed.set_thumbnail(url=user.display_avatar.url)
    return embed

async def fetch_filtered_pokemon_pool(session: aiohttp.ClientSession, type1: str | None, gen: int | None) -> list[dict]:
    """Récupère une liste de Pokémon correspondant aux filtres via GraphQL."""
    if not type1 and not gen:
        random_ids = random.sample(range(1, 1026), 6)
        return [{"id": str(i), "name_fr": f"ID {i}"} for i in random_ids]

    url = "https://beta.pokeapi.co/graphql/v1beta"
    conditions = []
    
    if gen:
        conditions.append(f"generation_id: {{_eq: {gen}}}")
        
    type_conditions = []
    if type1 and type1.lower() in TYPE_FR_TO_EN:
        type_conditions.append(f"{{pokemon_v2_pokemontypes: {{pokemon_v2_type: {{name: {{_eq: \"{TYPE_FR_TO_EN[type1.lower()]}\"}}}}}}}}")
        
    if type_conditions:
        conditions.append(f"pokemon_v2_pokemons: {{is_default: {{_eq: true}}, _and: [{', '.join(type_conditions)}]}}")

    where_clause = "{" + ", ".join(conditions) + "}"
    
    query = f"""
    query {{
      pokemon_v2_pokemonspecies(where: {where_clause}) {{
        id
        pokemon_v2_pokemonspeciesnames(where: {{language_id: {{_eq: 5}}}}) {{
          name
        }}
      }}
    }}
    """
    try:
        async with session.post(url, json={"query": query}) as resp:
            data = await resp.json()
            results = []
            for node in data.get("data", {}).get("pokemon_v2_pokemonspecies", []):
                names = node.get("pokemon_v2_pokemonspeciesnames", [])
                name_fr = names[0]["name"] if names else f"Pokémon #{node['id']}"
                results.append({"id": str(node["id"]), "name_fr": name_fr})
            return results
    except Exception as e:
        print(f"Erreur GraphQL: {e}")
        return []

# ============================================================================
# ----------------------------- GÉNÉRATEUR D'IMAGE ---------------------------
# ============================================================================

async def create_team_image_async(session: aiohttp.ClientSession, team_data: list) -> discord.File:
    """Génère une image 900x600 avec un fond Pokéball."""
    img = Image.new("RGB", (900, 600))
    draw = ImageDraw.Draw(img)

    # Fond Pokéball (Rouge / Blanc)
    draw.rectangle([0, 0, 900, 300], fill=(227, 53, 13))
    draw.rectangle([0, 300, 900, 600], fill=(255, 255, 255))
    
    # Ceinture noire
    draw.rectangle([0, 285, 900, 315], fill=(34, 34, 36))
    
    # Cercle central
    draw.ellipse([450-70, 300-70, 450+70, 300+70], fill=(34, 34, 36))
    draw.ellipse([450-45, 300-45, 450+45, 300+45], fill=(255, 255, 255))
    draw.ellipse([450-25, 300-25, 450+25, 300+25], fill=(255, 255, 255), outline=(34, 34, 36), width=4)

    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except IOError:
        font = ImageFont.load_default()

    centers_x = [150, 450, 750]
    centers_y = [140, 460]

    # Halos sous les Pokémon
    for i in range(6):
        cx = centers_x[i % 3]
        cy = centers_y[i // 3]
        halo_color = (200, 40, 10) if (i // 3) == 0 else (235, 235, 235)
        draw.ellipse([cx-65, cy-80, cx+65, cy+50], fill=halo_color)

    for i, poke in enumerate(team_data):
        cx = centers_x[i % 3]
        cy = centers_y[i // 3]

        try:
            async with session.get(poke['sprite']) as resp:
                sprite_bytes = await resp.read()
            sprite_img = Image.open(io.BytesIO(sprite_bytes)).convert("RGBA")
            sprite_img = sprite_img.resize((140, 140))
        except Exception:
            sprite_img = Image.new("RGBA", (140, 140), (0, 0, 0, 0))

        img.paste(sprite_img, (cx - 70, cy - 90), sprite_img)

        name = f"{poke['name']}"
        try:
            bbox = draw.textbbox((0, 0), name, font=font)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]
        except AttributeError:
            tw = draw.textlength(name, font=font)
            th = 20
            
        nx = cx - (tw / 2)
        ny = cy + 60
        
        padding = 6
        draw.rounded_rectangle(
            [nx - padding, ny - padding, nx + tw + padding, ny + th + padding], 
            radius=8, 
            fill=(30, 32, 36)
        )
        draw.text((nx, ny), name, fill=(255, 255, 255), font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return discord.File(buf, filename="team.png")

# ============================================================================
# ----------------------------- LOGIQUE CENTRALE -----------------------------
# ============================================================================

async def generate_and_send_team(bot, interaction_or_ctx, author, gen=None, p_type=None, is_interaction=False):
    """Génère l'équipe et met en forme la description selon l'ordre demandé."""
    async with aiohttp.ClientSession() as session:
        pool = await fetch_filtered_pokemon_pool(session, p_type, gen)
        
        if not pool:
            msg = "❌ Aucun Pokémon ne correspond à ces critères."
            if is_interaction:
                return await interaction_or_ctx.followup.send(msg, ephemeral=True)
            else:
                return await interaction_or_ctx.send(msg)
        
        chosen_pokemons = random.choices(pool, k=6) if len(pool) < 6 else random.sample(pool, 6)
        
        team = []
        for p in chosen_pokemons:
            async with session.get(f"https://pokeapi.co/api/v2/pokemon/{p['id']}") as resp:
                poke_data = await resp.json()
            
            name_fr = p['name_fr']
            if name_fr.startswith("ID "):
                async with session.get(f"https://pokeapi.co/api/v2/pokemon-species/{p['id']}") as spec_resp:
                    if spec_resp.status == 200:
                        spec_data = await spec_resp.json()
                        name_fr = next((n["name"] for n in spec_data["names"] if n["language"]["name"] == "fr"), poke_data["name"].capitalize())
                    else:
                        name_fr = poke_data["name"].capitalize()

            is_female = random.random() < 0.5
            gender_str = "♀️" if is_female else "♂️"
            is_shiny = random.random() < 0.05
            shiny_str = f" {SHINY_EMOJI}" if is_shiny else ""
            
            sprites = poke_data['sprites']
            if is_female:
                sprite_url = sprites.get('front_shiny_female') or sprites.get('front_shiny') if is_shiny else sprites.get('front_female') or sprites.get('front_default')
            else:
                sprite_url = sprites.get('front_shiny') if is_shiny else sprites.get('front_default')
                
            if not sprite_url:
                sprite_url = sprites.get('front_default')

            types = [TYPE_EN_TO_FR.get(t['type']['name'], t['type']['name'].capitalize()) for t in poke_data['types']]
            
            team.append({
                "name": name_fr,
                "sprite": sprite_url,
                "types": types,
                "gender": gender_str,
                "shiny_badge": shiny_str
            })

        file = await create_team_image_async(session, team)

        # Création de la description nettoyée (Sexe devant, nom, emojis types uniquement)
        desc = ""
        for p in team:
            emoji_str = " ".join([TYPE_EMOJIS.get(t, "❓") for t in p['types']])
            desc += f"{p['gender']} **{p['name']}**{p['shiny_badge']} - {emoji_str}\n"
        
        gen_str = f"| Génération {gen}" if gen else ""
        type_str = f"| Type {p_type}" if p_type else ""
        title = f"🎲 Équipe Aléatoire {type_str} {gen_str}".strip()
        
        embed = get_embed(interaction_or_ctx.guild, author, bot, title, desc)
        embed.set_image(url="attachment://team.png")
        
        view = TeamBuilderView(bot, author, gen, p_type)

        if is_interaction:
            await interaction_or_ctx.message.edit(embed=embed, view=view, attachments=[file])
        else:
            await interaction_or_ctx.send(embed=embed, view=view, file=file)

# ============================================================================
# ----------------------------- INTERFACES (UI) ------------------------------
# ============================================================================

class TeamBuilderView(discord.ui.View):
    def __init__(self, bot, author, current_gen=None, current_type=None):
        super().__init__(timeout=300)
        self.bot = bot
        self.author = author
        self.selected_gen = current_gen
        self.selected_type = current_type

        # 1. Sélecteur de Génération
        self.gen_select = discord.ui.Select(placeholder="🌍 Filtrer par Génération...", min_values=1, max_values=1, row=0)
        self.gen_select.add_option(label="Toutes les générations", value="none", emoji="🌍")
        for i in range(1, 10):
            self.gen_select.add_option(label=f"Génération {i}", value=str(i), default=(str(i) == str(current_gen)))
        self.gen_select.callback = self.gen_callback
        self.add_item(self.gen_select)

        # 2. Sélecteur de Type
        self.type_select = discord.ui.Select(placeholder="🔥 Filtrer par Type...", min_values=1, max_values=1, row=1)
        self.type_select.add_option(label="Tous les types", value="none", emoji="🔄")
        for t_fr in TYPE_EN_TO_FR.values():
            emoji_str = TYPE_EMOJIS.get(t_fr, "❓")
            emoji_obj = discord.PartialEmoji.from_str(emoji_str) if emoji_str.startswith("<") else None
            self.type_select.add_option(label=t_fr, value=t_fr, emoji=emoji_obj, default=(t_fr == current_type))
        self.type_select.callback = self.type_callback
        self.add_item(self.type_select)

        # 3. Bouton Régénérer
        self.generate_btn = discord.ui.Button(label="Regénérer l'équipe", style=discord.ButtonStyle.primary, emoji="🔄", row=2)
        self.generate_btn.callback = self.generate_callback
        self.add_item(self.generate_btn)

    async def gen_callback(self, interaction: discord.Interaction):
        val = self.gen_select.values[0]
        self.selected_gen = None if val == "none" else int(val)
        await interaction.response.defer()

    async def type_callback(self, interaction: discord.Interaction):
        val = self.type_select.values[0]
        self.selected_type = None if val == "none" else val
        await interaction.response.defer()

    async def generate_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await generate_and_send_team(self.bot, interaction, self.author, self.selected_gen, self.selected_type, is_interaction=True)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        return True

# ============================================================================
# ------------------------------- COG PRINCIPAL ------------------------------
# ============================================================================

class TeamCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="randomteam", description="Génère une équipe de 6 Pokémon aléatoires immédiatement.")
    async def randomteam(self, ctx: commands.Context):
        await ctx.defer()
        await generate_and_send_team(self.bot, ctx, ctx.author, gen=None, p_type=None, is_interaction=False)

async def setup(bot):
    await bot.add_cog(TeamCommand(bot))