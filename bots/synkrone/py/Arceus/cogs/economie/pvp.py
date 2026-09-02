import asyncio
import io
import random
import time
from typing import Any, Optional

import aiohttp
import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont, ImageFile, ImageOps

from .utils import EconomyService

ImageFile.LOAD_TRUNCATED_IMAGES = True

# --- Dictionnaires de Configuration Pokémon ---
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

async def fetch_image_bytes(session: aiohttp.ClientSession, url: str) -> Optional[bytes]:
    try:
        async with session.get(url) as response:
            if response.status == 200:
                return await response.read()
    except Exception:
        pass
    return None

async def fetch_move_fr(session: aiohttp.ClientSession, move_name: str) -> str:
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

# --- Génération de l'interface Pillow ---
def draw_health_bar(draw: ImageDraw.Draw, x: int, y: int, name: str, current_hp: int, max_hp: int, types: list[str], font_large: ImageFont.FreeTypeFont, font_small: ImageFont.FreeTypeFont, is_shiny: bool = False):
    hp_pct = max(0.0, current_hp / max_hp)
    draw.rounded_rectangle([(x, y), (x + 350, y + 140)], radius=10, fill=(43, 45, 49, 230), outline=(20, 20, 20), width=2)
    
    display_name = f"{name.capitalize()} ✨" if is_shiny else name.capitalize()
    draw.text((x + 15, y + 10), display_name, fill="white", font=font_large)
    
    current_x = x + 15
    type_y = y + 45
    box_h = 24
    for t in types:
        t_color = TYPE_COLORS.get(t, (150, 150, 150))
        t_name = TYPES_FR.get(t, "Normal").upper()
        w = draw.textlength(t_name, font=font_small)
        box_w = w + 20
        draw.rounded_rectangle([(current_x, type_y), (current_x + box_w, type_y + box_h)], radius=12, fill=t_color)
        draw.text((current_x + box_w / 2, type_y + box_h / 2), t_name, fill="white", font=font_small, anchor="mm")
        current_x += box_w + 10

    bar_x, bar_w, bar_h = x + 15, 250, 14
    bar_y = type_y + box_h + 10 
    draw.rounded_rectangle([(bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h)], radius=7, fill=(80, 80, 80, 255))
    
    color = (46, 204, 113) if hp_pct > 0.5 else (241, 196, 15) if hp_pct > 0.2 else (231, 76, 60)
    fill_w = max(10, int(bar_w * hp_pct)) if hp_pct > 0 else 0
    if fill_w > 0:
        draw.rounded_rectangle([(bar_x, bar_y), (bar_x + fill_w, bar_y + bar_h)], radius=7, fill=color)
        
    draw.text((x + 15, bar_y + bar_h + 20), f"{current_hp}/{max_hp} PV", fill="white", font=font_large, anchor="lm")

def gen_battle_image(
    my_sprite_bytes: Optional[bytes], opp_sprite_bytes: Optional[bytes],
    my_data: dict, opp_data: dict, pvp_info: Optional[dict] = None
) -> io.BytesIO:
    try:
        bg = Image.open("cogs/fond.png").convert("RGBA")
    except FileNotFoundError:
        bg = Image.new("RGBA", (1000, 500), (43, 45, 49, 255))
        
    bg = bg.resize((1000, 500), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(bg)
    
    try:
        font_large = ImageFont.truetype("cogs/Pokemon.ttf", 26)
        font_small = ImageFont.truetype("cogs/Pokemon.ttf", 14)
        font_player = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        font_large = font_small = font_player = ImageFont.load_default()

    # Affichage des interfaces de statut PV
    draw_health_bar(draw, 480, 55, opp_data["name"], opp_data["current_hp"], opp_data["max_hp"], opp_data["types"], font_large, font_small, opp_data.get("is_shiny", False))
    if my_data["name"] != "---":
        draw_health_bar(draw, 20, 350, my_data["name"], my_data["current_hp"], my_data["max_hp"], my_data["types"], font_large, font_small, my_data.get("is_shiny", False))

    # Importation et affichage des Sprites Pokémon
    if opp_sprite_bytes: 
        try:
            opp_sprite = Image.open(io.BytesIO(opp_sprite_bytes)).convert("RGBA").resize((200, 200), Image.Resampling.NEAREST)
            bg.paste(opp_sprite, (630, 200), opp_sprite) 
        except Exception: pass

    if my_sprite_bytes and my_data["current_hp"] > 0:
        try:
            my_sprite = Image.open(io.BytesIO(my_sprite_bytes)).convert("RGBA").resize((220, 220), Image.Resampling.NEAREST)
            my_sprite = ImageOps.mirror(my_sprite) 
            bg.paste(my_sprite, (140, 160), my_sprite)
        except Exception: pass

    # Cartes d'identité des dresseurs (PvP)
    if pvp_info:
        # Bloc Ennemi (Haut Droite)
        if pvp_info.get("opp_avatar"):
            try:
                av_opp = Image.open(io.BytesIO(pvp_info["opp_avatar"])).convert("RGBA").resize((45, 45))
                bg.paste(av_opp, (480, 5), av_opp)
            except: pass
        draw.text((535, 18), f"{pvp_info['opp_name']} (Niv. {pvp_info['opp_level']})", fill=(231, 76, 60), font=font_player)

        # Bloc Joueur (Bas Gauche)
        if pvp_info.get("my_avatar"):
            try:
                av_my = Image.open(io.BytesIO(pvp_info["my_avatar"])).convert("RGBA").resize((45, 45))
                bg.paste(av_my, (20, 295), av_my)
            except: pass
        draw.text((75, 308), f"{pvp_info['my_name']} (Niv. {pvp_info['my_level']})", fill=(46, 204, 113), font=font_player)

    buffer = io.BytesIO()
    bg.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


# --- Interface Utilisateur des Combats (Views) ---
class PvPBattleView(discord.ui.View):
    def __init__(self, session, player_id: int):
        super().__init__(timeout=None)
        self.session = session
        self.player_id = player_id
        self.build_ui()

    def build_ui(self):
        self.clear_items()
        is_p1 = (self.player_id == self.session.p1.id)
        my_data = self.session.p1_data if is_p1 else self.session.p2_data
        my_idx = self.session.p1_idx if is_p1 else self.session.p2_idx
        
        my_mon = my_data[my_idx]
        is_my_turn = (self.session.current_turn == (1 if is_p1 else 2))
        is_ko = my_mon["current_hp"] <= 0

        # Menu déroulant de switch de l'équipe
        options = []
        for i, mon in enumerate(my_data):
            status = f"{mon['current_hp']}/{mon['max_hp']} PV"
            options.append(discord.SelectOption(
                label=f"{mon['name'].capitalize()} ({status})",
                description="Prêt au combat" if mon["current_hp"] > 0 else "K.O.", value=str(i), default=(i == my_idx)
            ))
        select = discord.ui.Select(placeholder="Changer de Pokémon...", options=options, row=0, disabled=not is_my_turn)
        select.callback = self.switch_callback
        self.add_item(select)

        # Boutons des 4 capacités
        for i in range(4):
            btn = discord.ui.Button(style=discord.ButtonStyle.primary, row=1 if i < 2 else 2)
            if i < len(my_mon["moves"]):
                move = my_mon["moves"][i]
                btn.label = move.get("name_fr", move["name"]).capitalize()
                btn.disabled = (not is_my_turn or is_ko)
                emoji_str = get_type_emoji(move["type"])
                if emoji_str: btn.emoji = discord.PartialEmoji.from_str(emoji_str)
                btn.callback = self.make_attack_callback(i)
            else:
                btn.label = "---"
                btn.disabled = True
            self.add_item(btn)

    def make_attack_callback(self, idx):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.player_id: return
            await interaction.response.defer()
            await self.session.process_turn(interaction, action_type="attack", value=idx)
        return callback

    async def switch_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.player_id: return
        await interaction.response.defer()
        await self.session.process_turn(interaction, action_type="switch", value=int(interaction.data["values"][0]))


# --- Moteur de Session PvP ---
class PvPBattleSession:
    def __init__(self, cog, p1: discord.User, p2: discord.User, p1_data, p2_data, p1_av, p2_av, p1_lvl, p2_lvl):
        self.cog = cog
        self.p1 = p1
        self.p2 = p2
        self.p1_data = p1_data
        self.p2_data = p2_data
        self.p1_avatar = p1_av
        self.p2_avatar = p2_av
        self.p1_level = p1_lvl
        self.p2_level = p2_lvl
        
        self.p1_idx = 0
        self.p2_idx = 0
        self.current_turn = 1 if random.random() < 0.5 else 2
        self.turn_log = [f"⚔️ Match trouvé ! Le tirage au sort désigne **{self.p1.name if self.current_turn == 1 else self.p2.name}** pour commencer !"]
        
        self.p1_afk = 0
        self.p2_afk = 0
        self.timer_task = None
        
        self.p1_msg = None
        self.p2_msg = None
        self.view_p1 = None
        self.view_p2 = None

    async def start(self):
        self.view_p1 = PvPBattleView(self, self.p1.id)
        self.view_p2 = PvPBattleView(self, self.p2.id)
        
        embed1 = self.get_battle_embed(self.p1.id)
        embed2 = self.get_battle_embed(self.p2.id)
        
        f1, f2 = self.gen_images_for_both()
        
        try:
            self.p1_msg = await self.p1.send(embed=embed1, file=f1, view=self.view_p1)
            self.p2_msg = await self.p2.send(embed=embed2, file=f2, view=self.view_p2)
        except discord.Forbidden:
            await self.end_battle(None, None, forced_reason="Impossible d'initier le combat : l'un des joueurs possède ses messages privés fermés.")
            return

        self.start_timer()

    def start_timer(self):
        if self.timer_task: self.timer_task.cancel()
        self.timer_task = asyncio.create_task(self.turn_timeout_loop())

    async def turn_timeout_loop(self):
        await asyncio.sleep(30)
        
        if self.current_turn == 1:
            self.p1_afk += 1
            afk_count = self.p1_afk
        else:
            self.p2_afk += 1
            afk_count = self.p2_afk

        if afk_count == 1:
            self.turn_log = [f"⏳ **{self.p1.name if self.current_turn == 1 else self.p2.name}** a mis plus de 30 secondes à répondre ! Son tour est sauté."]
            self.current_turn = 2 if self.current_turn == 1 else 1
            self.start_timer()
            await self.sync_messages()
        else:
            winner = self.p2 if self.current_turn == 1 else self.p1
            loser = self.p1 if self.current_turn == 1 else self.p2
            await self.end_battle(winner.id, loser.id, f"Forfait automatique : {loser.name} a manqué 2 tours consécutifs.")

    def gen_images_for_both(self):
        lost_p1 = all(m["current_hp"] <= 0 for m in self.p1_data)
        lost_p2 = all(m["current_hp"] <= 0 for m in self.p2_data)
        
        m1 = self.p1_data[self.p1_idx] if not lost_p1 else {"name": "---", "current_hp": 0, "max_hp": 1, "types": []}
        m2 = self.p2_data[self.p2_idx] if not lost_p2 else {"name": "---", "current_hp": 0, "max_hp": 1, "types": []}

        # Perspective Joueur 1 (Allié à gauche, Ennemi à droite)
        info_p1 = {"my_name": self.p1.name, "my_level": self.p1_level, "my_avatar": self.p1_avatar, "opp_name": self.p2.name, "opp_level": self.p2_level, "opp_avatar": self.p2_avatar}
        b1 = gen_battle_image(m1.get("sprite_bytes"), m2.get("sprite_bytes"), m1, m2, info_p1)
        
        # Perspective Joueur 2 (Inversée pour afficher l'écran proprement)
        info_p2 = {"my_name": self.p2.name, "my_level": self.p2_level, "my_avatar": self.p2_avatar, "opp_name": self.p1.name, "opp_level": self.p1_level, "opp_avatar": self.p1_avatar}
        b2 = gen_battle_image(m2.get("sprite_bytes"), m1.get("sprite_bytes"), m2, m1, info_p2)
        
        return discord.File(b1, filename="battle.png"), discord.File(b2, filename="battle.png")

    def get_battle_embed(self, player_id):
        desc = "\n".join(self.turn_log)
        emb = discord.Embed(title="🏟️ Arène de Combat PvP 1v1", description=desc, color=0x2B2D31)
        emb.set_image(url="attachment://battle.png")
        return emb

    async def process_turn(self, interaction: discord.Interaction, action_type: str, value: int):
        if self.timer_task: self.timer_task.cancel()
        self.turn_log.clear()
        
        is_p1 = (interaction.user.id == self.p1.id)
        atk_data = self.p1_data if is_p1 else self.p2_data
        def_data = self.p2_data if is_p1 else self.p1_data
        atk_idx = self.p1_idx if is_p1 else self.p2_idx
        def_idx = self.p2_idx if is_p1 else self.p1_idx

        if is_p1: self.p1_afk = 0
        else: self.p2_afk = 0

        if action_type == "switch":
            if is_p1: self.p1_idx = value
            else: self.p2_idx = value
            self.turn_log.append(f"🔄 **{interaction.user.name}** retire son Pokémon et envoie **{atk_data[value]['name'].capitalize()}** !")
        elif action_type == "attack":
            attacker = atk_data[atk_idx]
            defender = def_data[def_idx]
            move = attacker["moves"][value]
            
            dmg, mult = self.calculate_damage(attacker, defender, move)
            defender["current_hp"] = max(0, defender["current_hp"] - dmg)
            
            eff = " ✨ C'est super efficace !" if mult > 1 else " Ce n'est pas très efficace..." if mult < 1 else ""
            m_name = move.get("name_fr", move["name"]).capitalize()
            shiny_tag = "✨ " if attacker.get("is_shiny") else ""
            self.turn_log.append(f"⚔️ {shiny_tag}**{attacker['name'].capitalize()}** utilise **{m_name}** ! **{dmg}** dégâts infligés !{eff}")

            if defender["current_hp"] <= 0:
                opp_name = self.p2.name if is_p1 else self.p1.name
                self.turn_log.append(f"💀 **{defender['name'].capitalize()}** de {opp_name} est mis K.O. !")

        # Analyse des conditions de victoire
        win_p1 = all(m["current_hp"] <= 0 for m in self.p2_data)
        win_p2 = all(m["current_hp"] <= 0 for m in self.p1_data)

        if win_p1:
            await self.end_battle(self.p1.id, self.p2.id, f"🏆 Victoire éclatante de **{self.p1.name}** ! Toute l'équipe adverse est au tapis.")
        elif win_p2:
            await self.end_battle(self.p2.id, self.p1.id, f"🏆 Victoire éclatante de **{self.p2.name}** ! Toute l'équipe adverse est au tapis.")
        else:
            self.current_turn = 2 if self.current_turn == 1 else 1
            self.start_timer()
            await self.sync_messages(interaction)

    def calculate_damage(self, attacker, defender, move):
        power = move.get("power", 40)
        mult = self.cog.eco.type_multiplier([move["type"]], defender.get("types", []))
        stab = 1.5 if move["type"] in attacker.get("types", []) else 1.0
        base_dmg = ((12) * power * (attacker["attack"] / max(1, defender["defense"]))) / 50 + 2
        return max(1, int(base_dmg * mult * stab * random.uniform(0.85, 1.0))), mult

    async def sync_messages(self, interaction: discord.Interaction = None):
        self.view_p1.build_ui()
        self.view_p2.build_ui()
        f1, f2 = self.gen_images_for_both()

        if interaction:
            if interaction.user.id == self.p1.id:
                await interaction.edit_original_response(embed=self.get_battle_embed(self.p1.id), attachments=[f1], view=self.view_p1)
                await self.p2_msg.edit(embed=self.get_battle_embed(self.p2.id), attachments=[f2], view=self.view_p2)
            else:
                await interaction.edit_original_response(embed=self.get_battle_embed(self.p2.id), attachments=[f2], view=self.view_p2)
                await self.p1_msg.edit(embed=self.get_battle_embed(self.p1.id), attachments=[f1], view=self.view_p1)
        else:
            if self.p1_msg: await self.p1_msg.edit(embed=self.get_battle_embed(self.p1.id), attachments=[f1], view=self.view_p1)
            if self.p2_msg: await self.p2_msg.edit(embed=self.get_battle_embed(self.p2.id), attachments=[f2], view=self.view_p2)

    async def end_battle(self, winner_id, loser_id, reason="Fin du combat", forced_reason=None):
        if self.timer_task: self.timer_task.cancel()
        
        self.cog.active_matches.pop(self.p1.id, None)
        self.cog.active_matches.pop(self.p2.id, None)

        if forced_reason:
            try: await self.p1.send(forced_reason)
            except: pass
            try: await self.p2.send(forced_reason)
            except: pass
            return

        self.cog.match_history.append((self.p1.id, self.p2.id, time.time()))

        # Attribution des récompenses (Farming de base = 100 XP, PvP = x3 donc 300 XP de base)
        win_xp = self.cog.eco.gain_xp(winner_id, 300) 
        self.cog.eco.gain_xp(loser_id, 10) # 10 XP fixe pour le perdant

        try:
            with self.cog.eco._get_conn() as conn:
                conn.execute("UPDATE users SET balance = balance + 500 WHERE user_id = ?", (winner_id,))
        except: pass

        emb1 = self.get_battle_embed(self.p1.id)
        emb2 = self.get_battle_embed(self.p2.id)
        
        reward_summary = f"{reason}\n\n🥇 **Gagnant:** +500₽ | +{win_xp} XP (Charme inclus)\n🥈 **Perdant:** +10 XP"
        emb1.add_field(name="🏁 Résultats du Match", value=reward_summary, inline=False)
        emb2.add_field(name="🏁 Résultats du Match", value=reward_summary, inline=False)

        for item in self.view_p1.children: item.disabled = True
        for item in self.view_p2.children: item.disabled = True

        f1, f2 = self.gen_images_for_both()
        if self.p1_msg: await self.p1_msg.edit(embed=emb1, attachments=[f1], view=self.view_p1)
        if self.p2_msg: await self.p2_msg.edit(embed=emb2, attachments=[f2], view=self.view_p2)


# --- Classe Principale Cog PvP ---
class PvPCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.eco = EconomyService(bot)
        
        self.pvp_queue = []        # Liste d'attente
        self.active_matches = {}   # Enregistrement des matchs en cours
        self.match_history = []    # Historique glissant pour la restriction anti-spam

    def get_user_level(self, user_id: int) -> int:
        try:
            with self.eco._get_conn() as conn:
                row = conn.execute("SELECT level FROM users WHERE user_id = ?", (user_id,)).fetchone()
                return row[0] if row else 50
        except: return 50

    async def prepare_pokemon_data(self, session, pokemon_id, is_shiny=False):
        stats = await self.eco.fetch_pokemon_stats(session, pokemon_id)
        if not stats: return None
        
        valid_moves = [m for m in stats.get("moves", []) if m.get("power", 0) > 0]
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
        stats["is_shiny"] = is_shiny
        
        sprite_url = (f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/shiny/{pokemon_id}.png" 
                      if is_shiny else f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{pokemon_id}.png")
        stats["sprite_bytes"] = await fetch_image_bytes(session, sprite_url)
        return stats

    @commands.hybrid_group(name="pvp", description="Arène d'affrontements en temps réel Joueur contre Joueur.")
    async def pvp(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("💡 Système d'arène : utilisez `/pvp join` pour vous inscrire ou `/pvp leave` pour vous retirer.")

    @pvp.command(name="join", description="Rejoindre l'arène de matchmaking PvP.")
    async def pvp_join(self, ctx: commands.Context):
        user = ctx.author
        if user.id in [u.id for u in self.pvp_queue]: return await ctx.send("⚠️ Vous êtes déjà sur la liste d'attente arène.")
        if user.id in self.active_matches: return await ctx.send("❌ Action impossible : vous êtes déjà engagé dans un combat.")
        
        my_team = self.eco.get_user_team(user.id)[:3]
        if not my_team: return await ctx.send("❌ Équipe vide. Définissez vos Pokémon avec `/teams` avant d'entrer en arène.")

        now = time.time()
        self.match_history = [m for m in self.match_history if now - m[2] < 120]

        opponent = None
        for potential in self.pvp_queue:
            past_matches = sum(1 for m in self.match_history if (m[0] == user.id and m[1] == potential.id) or (m[0] == potential.id and m[1] == user.id))
            if past_matches < 3:
                opponent = potential
                break

        if opponent:
            self.pvp_queue.remove(opponent)
            await ctx.send(f"⚔️ **Match trouvé !** {user.mention} 🆚 {opponent.mention}. Le duel commence immédiatement dans vos **Messages Privés** !")
            
            async with aiohttp.ClientSession() as session:
                p1_av = await fetch_image_bytes(session, str(user.display_avatar.with_format("png").url))
                p2_av = await fetch_image_bytes(session, str(opponent.display_avatar.with_format("png").url))
                
                p1_data, p2_data = [], []
                for mon in my_team:
                    d = await self.prepare_pokemon_data(session, mon.pokemon_id, is_shiny=getattr(mon, "is_shiny", False))
                    if d: p1_data.append(d)
                for mon in self.eco.get_user_team(opponent.id)[:3]:
                    d = await self.prepare_pokemon_data(session, mon.pokemon_id, is_shiny=getattr(mon, "is_shiny", False))
                    if d: p2_data.append(d)

            p1_lvl = self.get_user_level(user.id)
            p2_lvl = self.get_user_level(opponent.id)

            session_pvp = PvPBattleSession(self, user, opponent, p1_data, p2_data, p1_av, p2_av, p1_lvl, p2_lvl)
            self.active_matches[user.id] = session_pvp
            self.active_matches[opponent.id] = session_pvp
            await session_pvp.start()
        else:
            self.pvp_queue.append(user)
            await ctx.send("⏳ Inscription validée. Vous êtes en file d'attente. Restez attentif, un message vous sera envoyé ici dès qu'un joueur est trouvé !")

    @pvp.command(name="leave", description="Quitter la file de recherche à tout moment.")
    async def pvp_leave(self, ctx: commands.Context):
        user_ids = [u.id for u in self.pvp_queue]
        if ctx.author.id in user_ids:
            self.pvp_queue = [u for u in self.pvp_queue if u.id != ctx.author.id]
            await ctx.send("✅ Désinscription validée. Vous avez quitté la file d'attente PvP.")
        else:
            await ctx.send("❌ Vous n'êtes actuellement pas enregistré en recherche de match.")

async def setup(bot: commands.Bot):
    await bot.add_cog(PvPCog(bot))