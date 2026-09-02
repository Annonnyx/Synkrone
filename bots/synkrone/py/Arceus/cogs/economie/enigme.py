import io
import random
from typing import Any

import aiohttp
import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

from .utils import EconomyService

try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

try:
    EMBED_COLOR = int(config.get("EMBED_COLOR", "0x2B2D31"), 16)
except NameError:
    EMBED_COLOR = 0x2B2D31

POKEDOLLAR_EMOJI = "₽"
REWARD_COINS = 250
REWARD_XP = 50

TYPES_FR = {
    "normal": "Normal", "fire": "Feu", "water": "Eau", "electric": "Électrik",
    "grass": "Plante", "ice": "Glace", "fighting": "Combat", "poison": "Poison",
    "ground": "Sol", "flying": "Vol", "psychic": "Psy", "bug": "Insecte",
    "rock": "Roche", "ghost": "Spectre", "dragon": "Dragon", "dark": "Ténèbres",
    "steel": "Acier", "fairy": "Fée"
}

TYPE_EMOJIS = {
    "Feu": "<:feu:1522937171135434833>",
    "Normal": "<:normal:1522937166496534609>",
    "Eau": "<:eau:1522937163249877103>",
    "Électrik": "<:elec:1522937159626264647>",
    "Plante": "<:plante:1522937156874539038>",
    "Glace": "<:glace:1522937153896579072>",
    "Combat": "<:combat:1522937150771826809>",
    "Poison": "<:poison:1522937148167295056>",
    "Sol": "<:sol:1522937144782618634>",
    "Vol": "<:vol:1522937142261710959>",
    "Psy": "<:psy:1522937139741065427>",
    "Insecte": "<:insecte:1522937136649736304>",
    "Roche": "<:roche:1522937133915046051>",
    "Dragon": "<:dragon:1522937131084025918>",
    "Ténèbres": "<:tenebres:1522937127279661248>",
    "Acier": "<:acier:1522937124335259658>",
    "Fée": "<:fee:1522937121202245732>",
    "Spectre": "<:spectre:1522937118094131281>"
}

TYPE_EFFECTIVENESS = {
    "fire": {"grass": 2.0, "ice": 2.0, "bug": 2.0, "steel": 2.0, "water": 0.5, "rock": 0.5, "dragon": 0.5},
    "water": {"fire": 2.0, "ground": 2.0, "rock": 2.0, "water": 0.5, "grass": 0.5, "dragon": 0.5},
    "grass": {"water": 2.0, "ground": 2.0, "rock": 2.0, "fire": 0.5, "grass": 0.5, "poison": 0.5, "flying": 0.5, "bug": 0.5, "dragon": 0.5, "steel": 0.5},
    "electric": {"water": 2.0, "flying": 2.0, "electric": 0.5, "grass": 0.5, "dragon": 0.5, "ground": 0.0},
    "fighting": {"normal": 2.0, "ice": 2.0, "rock": 2.0, "dark": 2.0, "steel": 2.0, "poison": 0.5, "flying": 0.5, "psychic": 0.5, "bug": 0.5, "fairy": 0.5, "ghost": 0.0},
    "ground": {"fire": 2.0, "electric": 2.0, "poison": 2.0, "rock": 2.0, "steel": 2.0, "grass": 0.5, "bug": 0.5, "flying": 0.0},
    "psychic": {"fighting": 2.0, "poison": 2.0, "psychic": 0.5, "steel": 0.5, "dark": 0.0},
    "ice": {"grass": 2.0, "ground": 2.0, "flying": 2.0, "dragon": 2.0, "fire": 0.5, "water": 0.5, "ice": 0.5, "steel": 0.5},
    "dragon": {"dragon": 2.0, "steel": 0.5, "fairy": 0.0},
    "dark": {"psychic": 2.0, "ghost": 2.0, "fighting": 0.5, "dark": 0.5, "fairy": 0.5},
    "fairy": {"fighting": 2.0, "dragon": 2.0, "dark": 2.0, "fire": 0.5, "poison": 0.5, "steel": 0.5},
    "poison": {"grass": 2.0, "fairy": 2.0, "poison": 0.5, "ground": 0.5, "rock": 0.5, "ghost": 0.5, "steel": 0.0},
    "flying": {"grass": 2.0, "fighting": 2.0, "bug": 2.0, "electric": 0.5, "rock": 0.5, "steel": 0.5},
    "bug": {"grass": 2.0, "psychic": 2.0, "dark": 2.0, "fire": 0.5, "fighting": 0.5, "poison": 0.5, "flying": 0.5, "ghost": 0.5, "steel": 0.5, "fairy": 0.5},
    "rock": {"fire": 2.0, "ice": 2.0, "flying": 2.0, "bug": 2.0, "fighting": 0.5, "ground": 0.5, "steel": 0.5},
    "ghost": {"psychic": 2.0, "ghost": 2.0, "dark": 0.5, "normal": 0.0},
    "steel": {"ice": 2.0, "rock": 2.0, "fairy": 2.0, "fire": 0.5, "water": 0.5, "electric": 0.5, "steel": 0.5},
}


def get_font(size: int):
    """Utilise strictement la police du dossier cogs."""
    try:
        return ImageFont.truetype("cogs/Pokemon.ttf", size)
    except IOError:
        return ImageFont.load_default()

def format_val(val: float) -> str:
    """Affiche un entier si le float se termine par .0 (ex: 96.0 -> 96), sinon le float."""
    return f"{int(val)}" if val == int(val) else f"{val}"

async def fetch_sprite(session: aiohttp.ClientSession, p_id: int):
    url = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{p_id}.png"
    try:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.read()
                img = Image.open(io.BytesIO(data)).convert("RGBA")
                return img.resize((150, 150), Image.Resampling.NEAREST)
    except Exception:
        pass
    return None

async def generate_comparison_image(session: aiohttp.ClientSession, p1_id: int, name1: str, val1: str, p2_id: int, name2: str, val2: str):
    canvas = Image.new("RGBA", (600, 300), (43, 45, 49, 255))
    draw = ImageDraw.Draw(canvas)
    
    font_name = get_font(20)
    font_val = get_font(16)
    font_vs = get_font(40)
    
    sprite1 = await fetch_sprite(session, p1_id)
    sprite2 = await fetch_sprite(session, p2_id)
    
    if sprite1:
        canvas.paste(sprite1, (75, 40), sprite1)
    if sprite2:
        canvas.paste(sprite2, (375, 40), sprite2)
        
    text_name1 = f"A. {name1}"
    w_name1 = draw.textlength(text_name1, font=font_name)
    draw.text((150 - w_name1/2, 200), text_name1, font=font_name, fill="white")
    w_val1 = draw.textlength(val1, font=font_val)
    draw.text((150 - w_val1/2, 240), val1, font=font_val, fill=(46, 204, 113))
    
    text_name2 = f"B. {name2}"
    w_name2 = draw.textlength(text_name2, font=font_name)
    draw.text((450 - w_name2/2, 200), text_name2, font=font_name, fill="white")
    w_val2 = draw.textlength(val2, font=font_val)
    draw.text((450 - w_val2/2, 240), val2, font=font_val, fill=(241, 196, 15))
    
    w_vs = draw.textlength("VS", font=font_vs)
    draw.text((300 - w_vs/2, 120), "VS", font=font_vs, fill=(231, 76, 60))
    
    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

async def generate_four_sprites_image(session: aiohttp.ClientSession, p_ids: list[int]):
    """Génère une image contenant 4 sprites côte à côte pour le jeu de description."""
    canvas = Image.new("RGBA", (600, 150), (43, 45, 49, 255))
    for i, pid in enumerate(p_ids):
        sprite = await fetch_sprite(session, pid)
        if sprite:
            canvas.paste(sprite, (i * 150, 0), sprite)
            
    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


class BaseMinigameView(discord.ui.View):
    def __init__(self, cog: "MinigameCog", author: discord.abc.User):
        super().__init__(timeout=60)
        self.cog = cog
        self.author = author
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Ce jeu ne t'appartient pas !", ephemeral=True)
            return False
        return True

    def disable_all(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True

    async def on_timeout(self):
        self.disable_all()
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def process_result(self, interaction: discord.Interaction, is_win: bool, correct_answer: str, embed: discord.Embed):
        self.disable_all()
        
        if is_win:
            with self.cog.eco._get_conn() as conn:
                conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (REWARD_COINS, self.author.id))
            
            # On stocke l'XP réelle (potentiellement doublée) renvoyée par la méthode
            actual_xp = self.cog.eco.gain_xp(self.author.id, REWARD_XP)
            
            embed.add_field(name="Résultat", value=f"✅ **Gagné !** {correct_answer}\nTu remportes `+{REWARD_COINS}` {POKEDOLLAR_EMOJI} et `+{actual_xp}` XP !", inline=False)
        else:
            embed.add_field(name="Résultat", value=f"❌ **Perdu !** {correct_answer}", inline=False)

        await interaction.response.edit_message(embed=embed, view=self)

class HigherLowerView(BaseMinigameView):
    def __init__(self, cog: "MinigameCog", author: discord.abc.User, embed: discord.Embed, val_a: float, val_b: float, ans_text: str):
        super().__init__(cog, author)
        self.embed = embed
        self.val_a = val_a
        self.val_b = val_b
        self.ans_text = ans_text

    @discord.ui.button(label="Plus ⬆️", style=discord.ButtonStyle.primary)
    async def btn_higher(self, interaction: discord.Interaction, button: discord.ui.Button):
        is_win = self.val_a > self.val_b
        await self.process_result(interaction, is_win, self.ans_text, self.embed)

    @discord.ui.button(label="Moins ⬇️", style=discord.ButtonStyle.primary)
    async def btn_lower(self, interaction: discord.Interaction, button: discord.ui.Button):
        is_win = self.val_a < self.val_b
        await self.process_result(interaction, is_win, self.ans_text, self.embed)


class MultiChoiceView(BaseMinigameView):
    def __init__(self, cog: "MinigameCog", author: discord.abc.User, embed: discord.Embed, correct_value: str, ans_text: str, choices_data: list[dict]):
        super().__init__(cog, author)
        self.embed = embed
        self.correct_value = correct_value
        self.ans_text = ans_text
        
        for c in choices_data:
            btn = discord.ui.Button(label=c["label"], style=discord.ButtonStyle.secondary, custom_id=c["value"], emoji=c.get("emoji"))
            btn.callback = self.make_callback(btn)
            self.add_item(btn)

    def make_callback(self, button: discord.ui.Button):
        async def callback(interaction: discord.Interaction):
            is_win = button.custom_id == self.correct_value
            button.style = discord.ButtonStyle.success if is_win else discord.ButtonStyle.danger
            
            if not is_win:
                for child in self.children:
                    if isinstance(child, discord.ui.Button) and child.custom_id == self.correct_value:
                        child.style = discord.ButtonStyle.success

            await self.process_result(interaction, is_win, self.ans_text, self.embed)
        return callback


class MinigameCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.eco = EconomyService(bot)

    def get_base_embed(self, user: discord.abc.User, title: str, description: str) -> discord.Embed:
        if config_manager and hasattr(user, "guild"):
            embed = config_manager.get_formatted_embed(
                guild=getattr(user, "guild", None), 
                user=user, 
                bot=self.bot, 
                title=title, 
                description=description
            )
        else:
            embed = discord.Embed(title=title, description=description, color=EMBED_COLOR)
        return embed

    async def fetch_pokemon(self, session: aiohttp.ClientSession, p_id: int):
        async with session.get(f"https://pokeapi.co/api/v2/pokemon/{p_id}") as resp:
            return await resp.json()

    @commands.hybrid_command(name="enigme", aliases=["quiz", "minijeu"], description="Mini-jeu Pokémon : devine les stats, types ou descriptions !")
    async def devine(self, ctx: commands.Context[commands.Bot]):
        self.eco.ensure_user(ctx.author.id)
        await ctx.defer()
        
        mode = random.choice(["weight", "height", "stats", "type_possess", "description", "type_effective"])
        
        async with aiohttp.ClientSession() as session:
            if mode in ["weight", "height", "stats"]:
                # --- MODE COMPARAISON (A vs B) ---
                while True:
                    p1_id, p2_id = random.sample(range(1, 1025), 2)
                    data1 = await self.fetch_pokemon(session, p1_id)
                    data2 = await self.fetch_pokemon(session, p2_id)
                    
                    name1 = await self.eco.get_species_name_fr(session, p1_id)
                    name2 = await self.eco.get_species_name_fr(session, p2_id)
                    name1, name2 = name1.capitalize(), name2.capitalize()
                    
                    if mode == "weight":
                        val1, val2 = data1["weight"] / 10, data2["weight"] / 10
                        unit, title_mode = "kg", "Poids"
                        emoji, adjective = "⚖️", "lourd"
                    elif mode == "height":
                        val1, val2 = data1["height"] / 10, data2["height"] / 10
                        unit, title_mode = "m", "Taille"
                        emoji, adjective = "📏", "grand"
                    else:
                        val1 = sum(s["base_stat"] for s in data1["stats"])
                        val2 = sum(s["base_stat"] for s in data2["stats"])
                        unit, title_mode = "BST", "Statistiques"
                        emoji, adjective = "📈", "fort"

                    if val1 != val2:
                        break

                desc = f"Le Pokémon A est-il **plus** ou **moins** {adjective} que le B ?"
                embed = self.get_base_embed(ctx.author, f"{emoji} Mini-Jeu : {title_mode}", desc)
                
                str_val1 = f"{format_val(val1)} {unit}"
                str_val2 = f"??? {unit}"
                buffer = await generate_comparison_image(session, p1_id, name1, str_val1, p2_id, name2, str_val2)
                file = discord.File(buffer, filename="compare.png")
                embed.set_image(url="attachment://compare.png")
                
                ans_text = f"Le Pokémon B (**{name2}**) avait une valeur de **{format_val(val2)} {unit}**."
                view = HigherLowerView(self, ctx.author, embed, val1, val2, ans_text)
                msg = await ctx.send(file=file, embed=embed, view=view, reference=ctx.message)

            elif mode == "type_possess":
                # --- MODE TYPE POSSÉDÉ ---
                p_id = random.randint(1, 1025)
                data = await self.fetch_pokemon(session, p_id)
                name = await self.eco.get_species_name_fr(session, p_id)
                
                actual_types = [t["type"]["name"] for t in data["types"]]
                correct_type = random.choice(actual_types)
                
                wrong_choices = random.sample([t for t in TYPES_FR.keys() if t not in actual_types], 3)
                choices = wrong_choices + [correct_type]
                random.shuffle(choices)
                
                desc = f"Quel type possède **{name.capitalize()}** ?"
                embed = self.get_base_embed(ctx.author, "🧠 Mini-Jeu : Type", desc)
                
                artwork_url = data["sprites"]["other"]["official-artwork"]["front_default"]
                if artwork_url:
                    embed.set_thumbnail(url=artwork_url)
                
                ans_text = f"La bonne réponse était le type **{TYPES_FR[correct_type]}**."
                choices_data = [{"label": TYPES_FR[c], "value": c, "emoji": TYPE_EMOJIS.get(TYPES_FR[c])} for c in choices]
                
                view = MultiChoiceView(self, ctx.author, embed, correct_type, ans_text, choices_data)
                msg = await ctx.send(embed=embed, view=view, reference=ctx.message)

            elif mode == "description":
                # --- MODE POKÉDEX DESCRIPTION ---
                while True:
                    p_id = random.randint(1, 1025)
                    name = await self.eco.get_species_name_fr(session, p_id)
                    async with session.get(f"https://pokeapi.co/api/v2/pokemon-species/{p_id}") as resp:
                        if resp.status == 200:
                            species_data = await resp.json()
                            fr_entries = [e["flavor_text"] for e in species_data["flavor_text_entries"] if e["language"]["name"] == "fr"]
                            if fr_entries:
                                break

                desc_text = random.choice(fr_entries).replace('\n', ' ').replace('\x0c', ' ').replace('\r', ' ')
                desc_text = desc_text.replace(name, "???").replace(name.upper(), "???").replace(name.capitalize(), "???")
                
                wrong_ids = set()
                while len(wrong_ids) < 3:
                    w_id = random.randint(1, 1025)
                    if w_id != p_id:
                        wrong_ids.add(w_id)

                all_ids = list(wrong_ids) + [p_id]
                random.shuffle(all_ids)

                choices_data = []
                for c_id in all_ids:
                    c_name = await self.eco.get_species_name_fr(session, c_id)
                    choices_data.append({"label": c_name.capitalize(), "value": str(c_id)})

                desc = f"À quel Pokémon appartient cette description ?\n\n*« {desc_text} »*"
                embed = self.get_base_embed(ctx.author, "📖 Mini-Jeu : Pokédex", desc)
                
                # Image Pillow des 4 sprites
                buffer = await generate_four_sprites_image(session, all_ids)
                file = discord.File(buffer, filename="sprites.png")
                embed.set_image(url="attachment://sprites.png")
                
                ans_text = f"C'était la description de **{name.capitalize()}** !"
                
                view = MultiChoiceView(self, ctx.author, embed, str(p_id), ans_text, choices_data)
                msg = await ctx.send(file=file, embed=embed, view=view, reference=ctx.message)

            elif mode == "type_effective":
                # --- MODE EFFICACITÉ DES TYPES ---
                valid_defenders = [d for d in TYPES_FR.keys() if any(TYPE_EFFECTIVENESS.get(a, {}).get(d, 1.0) >= 2.0 for a in TYPES_FR.keys())]
                target_def = random.choice(valid_defenders)
                
                effective_attackers = [a for a in TYPES_FR.keys() if TYPE_EFFECTIVENESS.get(a, {}).get(target_def, 1.0) >= 2.0]
                correct_atk = random.choice(effective_attackers)
                
                wrong_attackers = [a for a in TYPES_FR.keys() if TYPE_EFFECTIVENESS.get(a, {}).get(target_def, 1.0) <= 1.0]
                wrong_choices = random.sample(wrong_attackers, 3)
                
                choices = wrong_choices + [correct_atk]
                random.shuffle(choices)
                
                desc = f"Quel type est **super efficace** face au type **{TYPES_FR[target_def]}** {TYPE_EMOJIS.get(TYPES_FR[target_def], '')} ?"
                embed = self.get_base_embed(ctx.author, "🔥 Mini-Jeu : Faiblesses", desc)
                
                ans_text = f"Le type **{TYPES_FR[correct_atk]}** est super efficace contre le type {TYPES_FR[target_def]} !"
                choices_data = [{"label": TYPES_FR[c], "value": c, "emoji": TYPE_EMOJIS.get(TYPES_FR[c])} for c in choices]
                
                view = MultiChoiceView(self, ctx.author, embed, correct_atk, ans_text, choices_data)
                msg = await ctx.send(embed=embed, view=view, reference=ctx.message)

        view.message = msg


async def setup(bot: commands.Bot):
    if bot.get_cog("MinigameCog"):
        await bot.remove_cog("MinigameCog")
    await bot.add_cog(MinigameCog(bot))