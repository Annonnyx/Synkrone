import asyncio
import io
import random
from typing import Any, Optional

import aiohttp
import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont, ImageFile, ImageOps

from .utils import EconomyService, TeamMon

try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

ImageFile.LOAD_TRUNCATED_IMAGES = True

# --- Dictionnaires de Types ---
TYPES_FR = {
    "normal": "Normal", "fire": "Feu", "water": "Eau", "electric": "Électrik",
    "grass": "Plante", "ice": "Glace", "fighting": "Combat", "poison": "Poison",
    "ground": "Sol", "flying": "Vol", "psychic": "Psy", "bug": "Insecte",
    "rock": "Roche", "ghost": "Spectre", "dragon": "Dragon", "dark": "Ténèbres",
    "steel": "Acier", "fairy": "Fée"
}

TYPE_EMOJIS = {
    "Feu": "<:feu:1522937171135434833>", "Normal": "<:normal:1522937166496534609>",
    "Eau": "<:eau:1522937163249877103>", "Electrik": "<:elec:1522937159626264647>",
    "Plante": "<:plante:1522937156874539038>", "Glace": "<:glace:1522937153896579072>",
    "Combat": "<:combat:1522937150771826809>", "Poison": "<:poison:1522937148167295056>",
    "Sol": "<:sol:1522937144782618634>", "Vol": "<:vol:1522937142261710959>",
    "Psy": "<:psy:1522937139741065427>", "Insecte": "<:insecte:1522937136649736304>",
    "Roche": "<:roche:1522937133915046051>", "Dragon": "<:dragon:1522937131084025918>",
    "Tenebres": "<:tenebres:1522937127279661248>", "Acier": "<:acier:1522937124335259658>",
    "Fee": "<:fee:1522937121202245732>", "Spectre": "<:spectre:1522937118094131281>"
}

TYPE_COLORS = {
    "normal": (168, 167, 122), "fire": (238, 129, 48), "water": (99, 144, 240),
    "electric": (247, 208, 44), "grass": (122, 199, 76), "ice": (150, 217, 214),
    "fighting": (194, 46, 40), "poison": (163, 62, 161), "ground": (226, 191, 101),
    "flying": (169, 143, 243), "psychic": (249, 85, 135), "bug": (166, 185, 26),
    "rock": (182, 161, 54), "ghost": (115, 87, 151), "dragon": (111, 53, 252),
    "dark": (112, 87, 70), "steel": (183, 183, 206), "fairy": (214, 133, 173)
}

def get_type_emoji(type_en: str) -> str:
    fr_name = TYPES_FR.get(type_en, "Normal")
    mapping = {"Électrik": "Electrik", "Ténèbres": "Tenebres", "Fée": "Fee"}
    return TYPE_EMOJIS.get(mapping.get(fr_name, fr_name), "")

async def fetch_image(session: aiohttp.ClientSession, url: str) -> Optional[io.BytesIO]:
    try:
        async with session.get(url) as response:
            if response.status == 200:
                return io.BytesIO(await response.read())
    except Exception:
        pass
    return None

async def fetch_move_fr(session: aiohttp.ClientSession, move_name: str) -> str:
    """Récupère le nom français d'une capacité depuis PokeAPI."""
    try:
        url = f"https://pokeapi.co/api/v2/move/{move_name.lower().replace(' ', '-')}"
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                for name_entry in data.get("names", []):
                    if name_entry["language"]["name"] == "fr":
                        return name_entry["name"]
    except Exception:
        pass
    return move_name.capitalize()

def draw_health_bar(draw: ImageDraw.Draw, x: int, y: int, name: str, current_hp: int, max_hp: int, types: list[str], font_large: ImageFont.FreeTypeFont, font_small: ImageFont.FreeTypeFont, font_default: ImageFont.FreeTypeFont):
    """Dessine la carte élargie du Pokémon avec 4 lignes distinctes (sans le %)."""
    hp_pct = max(0.0, current_hp / max_hp)
    
    # Boîte de fond ajustée à 350x140
    draw.rounded_rectangle([(x, y), (x + 350, y + 140)], radius=10, fill=(43, 45, 49, 230), outline=(20, 20, 20), width=2)
    
    # LIGNE 1 : Nom du Pokémon
    draw.text((x + 15, y + 10), name.capitalize(), fill="white", font=font_large)
    
    # LIGNE 2 : Pilules de types
    current_x = x + 15
    type_y = y + 45
    box_h = 24
    
    for t in types:
        t_color = TYPE_COLORS.get(t, (150, 150, 150))
        t_name = TYPES_FR.get(t, "Normal").upper()
        w = draw.textlength(t_name, font=font_small)
        box_w = w + 20
        
        draw.rounded_rectangle([(current_x, type_y), (current_x + box_w, type_y + box_h)], radius=12, fill=t_color)
        
        center_x = current_x + box_w / 2
        center_y = type_y + box_h / 2
        draw.text((center_x, center_y), t_name, fill="white", font=font_small, anchor="mm")
        
        current_x += box_w + 10

    # LIGNE 3 : Barre de PV
    bar_x = x + 15
    bar_w, bar_h = 250, 14
    bar_y = type_y + box_h + 10 
    
    draw.rounded_rectangle([(bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h)], radius=7, fill=(80, 80, 80, 255))
    
    color = (46, 204, 113) if hp_pct > 0.5 else (241, 196, 15) if hp_pct > 0.2 else (231, 76, 60)
    fill_w = max(10, int(bar_w * hp_pct)) if hp_pct > 0 else 0
    if fill_w > 0:
        draw.rounded_rectangle([(bar_x, bar_y), (bar_x + fill_w, bar_y + bar_h)], radius=7, fill=color)
        
    # LIGNE 4 : Texte des PV (Uniquement les chiffres)
    hp_numbers = f"{current_hp}/{max_hp}"
    
    text_x = x + 15
    text_y = bar_y + bar_h + 20 
    
    # On dessine uniquement les PV bruts avec la police Pokémon (font_large)
    draw.text((text_x, text_y), hp_numbers, fill="white", font=font_large, anchor="lm")

def gen_battle_image(
    my_sprite_bytes: Optional[io.BytesIO], opp_sprite_bytes: Optional[io.BytesIO],
    my_data: dict, opp_data: dict
) -> io.BytesIO:
    # Largeur globale à 1000px
    try:
        bg = Image.open("cogs/fond.png").convert("RGBA")
    except FileNotFoundError:
        bg = Image.new("RGBA", (1000, 500), (43, 45, 49, 255))
        
    bg = bg.resize((1000, 500), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(bg)
    
    try:
        font_large = ImageFont.truetype("cogs/Pokemon.ttf", 26)
        font_small = ImageFont.truetype("cogs/Pokemon.ttf", 14)
    except OSError:
        font_large = font_small = ImageFont.load_default()

    try:
        font_default = ImageFont.truetype("arial.ttf", 15)
    except OSError:
        font_default = ImageFont.load_default()

    # --- UI et Sprite Ennemi ---
    draw_health_bar(draw, 480, 20, opp_data["name"], opp_data["current_hp"], opp_data["max_hp"], opp_data["types"], font_large, font_small, font_default)
    
    # SUPPRESSION de la condition "opp_data['current_hp'] > 0" pour garder le sprite au K.O.
    if opp_sprite_bytes: 
        try:
            opp_sprite = Image.open(opp_sprite_bytes).convert("RGBA")
            opp_sprite = opp_sprite.resize((200, 200), Image.Resampling.NEAREST)
            bg.paste(opp_sprite, (630, 140), opp_sprite) 
        except Exception: pass

    # --- UI et Sprite Joueur ---
    if my_sprite_bytes and my_data["current_hp"] > 0:
        try:
            my_sprite = Image.open(my_sprite_bytes).convert("RGBA")
            my_sprite = my_sprite.resize((220, 220), Image.Resampling.NEAREST)
            my_sprite = ImageOps.mirror(my_sprite) 
            bg.paste(my_sprite, (140, 160), my_sprite)
        except Exception: pass

    # Carte joueur
    if my_data["name"] != "---":
        draw_health_bar(draw, 20, 350, my_data["name"], my_data["current_hp"], my_data["max_hp"], my_data["types"], font_large, font_small, font_default)

    buffer = io.BytesIO()
    bg.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


class BattleView(discord.ui.View):
    def __init__(self, ctx, my_data, opp_data, economy_service, bot):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.eco = economy_service
        self.bot = bot
        self.my_data = my_data
        self.opp_data = opp_data
        self.my_idx = 0
        self.turn_log = ["Que le combat commence !"]
        
        self.build_ui()
        self.battle_image = self.gen_current_image()

    def get_my_current_mon(self): return self.my_data[self.my_idx]
    def get_opp_mon(self): return self.opp_data[0]

    def gen_current_image(self) -> io.BytesIO:
        my_mon = self.get_my_current_mon()
        opp_mon = self.get_opp_mon()
        lost = all(mon["current_hp"] <= 0 for mon in self.my_data)
        
        return gen_battle_image(
            my_sprite_bytes=my_mon.get("sprite_bytes") if not lost else None,
            opp_sprite_bytes=opp_mon.get("sprite_bytes"),
            my_data=my_mon if not lost else {"name": "---", "current_hp": 0, "max_hp": 1, "types": []},
            opp_data=opp_mon
        )

    def build_ui(self):
        self.clear_items()
        my_mon = self.get_my_current_mon()
        is_ko = my_mon["current_hp"] <= 0
        
        options = []
        for i, mon in enumerate(self.my_data):
            status = f"{mon['current_hp']}/{mon['max_hp']} PV"
            desc = "Prêt au combat" if mon["current_hp"] > 0 else "K.O."
            options.append(discord.SelectOption(
                label=f"{mon['name'].capitalize()} ({status})",
                description=desc, value=str(i), default=(i == self.my_idx)
            ))

        select = discord.ui.Select(placeholder="Changer de Pokémon...", options=options, row=0)
        select.callback = self.switch_pokemon_callback
        self.add_item(select)

        for i in range(4):
            btn = discord.ui.Button(style=discord.ButtonStyle.primary, row=1 if i < 2 else 2)
            if i < len(my_mon["moves"]):
                move = my_mon["moves"][i]
                btn.label = move.get("name_fr", move["name"]).capitalize()
                btn.disabled = is_ko
                
                emoji_str = get_type_emoji(move["type"])
                if emoji_str:
                    btn.emoji = discord.PartialEmoji.from_str(emoji_str)
                    
                btn.callback = self.make_attack_callback(i)
            else:
                btn.label = "---"
                btn.disabled = True
            self.add_item(btn)

    def make_attack_callback(self, move_index):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.ctx.author.id:
                return await interaction.response.send_message("❌ Ce n'est pas ton combat !", ephemeral=True)
            
            # 🔴 DEFER IMMEDIAT : On prévient Discord qu'on traite l'info pour éviter l'échec de l'interaction
            await interaction.response.defer()
            await self.process_turn(interaction, move_index)
        return callback

    async def switch_pokemon_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Ce n'est pas ton combat !", ephemeral=True)

        new_idx = int(interaction.data["values"][0])
        if self.my_data[new_idx]["current_hp"] <= 0:
            return await interaction.response.send_message("❌ Ce Pokémon est K.O. !", ephemeral=True)
            
        # 🔴 DEFER IMMEDIAT pour le changement d'équipe
        await interaction.response.defer()
        
        if new_idx == self.my_idx:
            return
            
        self.turn_log = [f"🔄 En avant, **{self.my_data[new_idx]['name'].capitalize()}** !"]
        self.my_idx = new_idx
        
        if self.get_opp_mon()["current_hp"] > 0:
            self.do_enemy_attack()
            
        await self.update_view(interaction)

    def calculate_damage(self, attacker, defender, move):
        level = 50 
        power = move.get("power", 40)
        a = attacker["attack"]
        d = defender["defense"]
        
        type_mult = self.eco.type_multiplier([move["type"]], defender.get("types", []))
        stab = 1.5 if move["type"] in attacker.get("types", []) else 1.0
        crit = 1.5 if random.random() < 0.0625 else 1.0
        
        base_dmg = ((2 * level / 5 + 2) * power * (a / max(1, d))) / 50 + 2
        return max(1, int(base_dmg * type_mult * stab * crit * random.uniform(0.85, 1.0))), type_mult

    def do_attack(self, attacker, defender, move):
        dmg, type_mult = self.calculate_damage(attacker, defender, move)
        defender["current_hp"] = max(0, defender["current_hp"] - dmg)
        
        eff = " C'est super efficace !" if type_mult > 1 else " Ce n'est pas très efficace..." if type_mult < 1 else ""
        move_name = move.get("name_fr", move["name"]).capitalize()
        self.turn_log.append(f"⚔️ **{attacker['name'].capitalize()}** utilise *{move_name}*. {dmg} dégâts !{eff}")

    def do_enemy_attack(self):
        attacker = self.get_opp_mon()
        defender = self.get_my_current_mon()
        if attacker["current_hp"] <= 0 or defender["current_hp"] <= 0: return
        
        valid_moves = [m for m in attacker["moves"] if m.get("power", 0) > 0]
        move = random.choice(valid_moves) if valid_moves else attacker["moves"][0]
        self.do_attack(attacker, defender, move)

    async def process_turn(self, interaction: discord.Interaction, move_index: int):
        self.turn_log.clear()
        my_mon = self.get_my_current_mon()
        opp_mon = self.get_opp_mon()

        move = my_mon["moves"][move_index]
        self.do_attack(my_mon, opp_mon, move)
        
        if opp_mon["current_hp"] > 0:
            self.do_enemy_attack()
        else:
            self.turn_log.append(f"☠️ **{opp_mon['name'].capitalize()}** sauvage est K.O. !")

        if my_mon["current_hp"] <= 0:
            self.turn_log.append(f"☠️ **{my_mon['name'].capitalize()}** est K.O. ! Choisis un autre Pokémon.")

        await self.update_view(interaction)

    def get_embed(self, title, description):
        if config_manager and hasattr(self.ctx.author, "guild"):
            return config_manager.get_formatted_embed(
                guild=getattr(self.ctx.author, "guild", None), 
                user=self.ctx.author, bot=self.bot, title=title, description=description
            )
        return discord.Embed(title=title, description=description, color=0x2B2D31)

    async def update_view(self, interaction: discord.Interaction):
        win = self.get_opp_mon()["current_hp"] <= 0
        lost = all(mon["current_hp"] <= 0 for mon in self.my_data)
        
        embed = self.get_embed("Combat Pokémon", "\n".join(self.turn_log))
        
        if win or lost:
            for item in self.children: item.disabled = True 
            if win:
                gain, base_xp = 150, 100
                with self.eco._get_conn() as conn:
                    conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (gain, self.ctx.author.id))
                
                # On stocke l'XP réelle (potentiellement doublée par le charme)
                actual_xp = self.eco.gain_xp(self.ctx.author.id, base_xp)
                
                embed.add_field(name="Victoire !", value=f"Tu remportes +{gain}₽ et +{actual_xp} XP !", inline=False)
            else:
                embed.add_field(name="Défaite...", value="Toute ton équipe est K.O. Tu fuis en panique sans rien gagner.", inline=False)
        else:
            self.build_ui() 

        file = discord.File(self.gen_current_image(), filename="battle.png")
        embed.set_image(url="attachment://battle.png")
        
        # 🔴 CHANGEMENT ICI : edit_original_response au lieu de response.edit_message car l'interaction a été reportée (defer)
        await interaction.edit_original_response(embed=embed, attachments=[file], view=self)


class FarmCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.eco = EconomyService(bot)

    async def prepare_pokemon_data(self, session, pokemon_id, is_opp=False, is_shiny=False):
        stats = await self.eco.fetch_pokemon_stats(session, pokemon_id)
        if not stats: return None
        
        # 1. On filtre pour garder uniquement ses VRAIES attaques qui font des dégâts
        valid_moves = [m for m in stats.get("moves", []) if m.get("power", 0) > 0]
        
        # 2. On choisit jusqu'à 4 attaques au hasard dans ce panel
        if valid_moves:
            stats["moves"] = random.sample(valid_moves, min(4, len(valid_moves)))
        else: 
            stats["moves"] = [{"name": "Charge", "type": "normal", "power": 40}] 
            
        moves_tasks = [fetch_move_fr(session, m["name"]) for m in stats["moves"]]
        fr_names = await asyncio.gather(*moves_tasks)
        for m, fr_name in zip(stats["moves"], fr_names):
            m["name_fr"] = fr_name

        stats["name"] = await self.eco.get_species_name_fr(session, pokemon_id)
        
        stats["max_hp"] = (stats["hp"] * 2) + 110
        stats["current_hp"] = stats["max_hp"]
        
        sprite_url = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{pokemon_id}.png" if not is_shiny else f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/shiny/{pokemon_id}.png"
        
        stats["sprite_bytes"] = await fetch_image(session, sprite_url)
        return stats

    @commands.hybrid_command(name="farm", description="Défie un Pokémon sauvage avec ta team.")
    @commands.cooldown(1, 15, commands.BucketType.user)
    async def farm(self, ctx: commands.Context[commands.Bot]):
        my_team = self.eco.get_user_team(ctx.author.id)[:3]
        if not my_team:
            return await ctx.send("❌ Tu dois configurer une équipe avec `/teams`.")

        msg = await ctx.send("🔍 Recherche d'un Pokémon sauvage en cours...")

        async with aiohttp.ClientSession() as session:
            my_data = []
            for mon in my_team:
                data = await self.prepare_pokemon_data(session, mon.pokemon_id, is_opp=False, is_shiny=getattr(mon, "is_shiny", False))
                if data: my_data.append(data)

            opp_id = random.randint(1, 1025)
            opp_data = await self.prepare_pokemon_data(session, opp_id, is_opp=True, is_shiny=random.random() < 0.01)

        if not my_data or not opp_data:
            return await msg.edit(content="❌ Erreur lors de la préparation du combat.")

        battle_view = BattleView(ctx, my_data, [opp_data], self.eco, self.bot)
        
        embed = battle_view.get_embed(f"Un {opp_data['name'].capitalize()} sauvage apparaît !", "Que vas-tu faire ?")
        file = discord.File(battle_view.battle_image, filename="battle.png")
        embed.set_image(url="attachment://battle.png")
        
        await msg.edit(content=None, embed=embed, attachments=[file], view=battle_view)

async def setup(bot: commands.Bot):
    await bot.add_cog(FarmCog(bot))