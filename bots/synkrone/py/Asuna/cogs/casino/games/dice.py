import discord
from discord.ext import commands
from discord import app_commands, ui
import random
import asyncio
import os
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from cogs.casino.autres.achievements import add_xp, get_hourly_limit, get_max_bet, XP_PER_GAME_COMMAND
from cogs.casino.admin.adminlimit import apply_admin_gain_limit, get_admin_hourly_limit

# ===================== CONFIG MANAGER ========================
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

BASE_DIR = Path.cwd()
DATA_DIR = BASE_DIR / "data" / "public" / "data_vote"

# --- GESTION DES DONNÉES ---
def get_user_file_path(guild_id: int, user_id: int):
    base_dir = os.path.join('cogs', 'casino', 'data', str(guild_id))
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)
    return os.path.join(base_dir, f"{user_id}.json")


def load_user_data(guild_id: int, user_id: int):
    path = get_user_file_path(guild_id, user_id)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        data.setdefault("Cols", 1000)
        data.setdefault("xp", 0)
        return data
    return {"Cols": 1000, "xp": 0}


def save_user_data(guild_id: int, user_id: int, data: dict):
    path = get_user_file_path(guild_id, user_id)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)


def format_Cols(value: int) -> str:
    return f"{value:,}".replace(',', ' ')


VOTE_DATA_FILE = DATA_DIR / "users.json"
PREMIUM_EMOJI = "<:premium:1528794484295467170>"


def get_vote_bonus_status(user_id: int):
    if not VOTE_DATA_FILE.exists():
        return False, 0
    try:
        with open(VOTE_DATA_FILE, 'r', encoding='utf-8') as f:
            vote_data = json.load(f)
    except Exception:
        return False, 0

    user_entry = vote_data.get(str(user_id), {})
    bonus_end = user_entry.get("bonus_end_timestamp")
    if not bonus_end:
        return False, 0

    now = time.time()
    remaining = int(bonus_end - now)
    if remaining > 0:
        return True, remaining
    return False, 0


# --- CONSTANTES ET LIMITES ---
MAX_MISE = 10_000_000
MAX_PARTIES_HEURE = 20

# Multiplicateurs pour 1 seul dé
DICE_1_MULTIPLIERS = {
    1: 0,
    2: 0,
    3: 0.15,
    4: 0.75,
    5: 1.4,
    6: 2.6
}

# Combinaisons possibles pour 2 à 5 dés
COMBOS = [
    "Yams (5 identiques)",
    "Carré (4 identiques)",
    "Full (3+2)",
    "Brelan (3 identiques)",
    "Double paire",
    "Suite",
    "Paire",
    "Rien"
]

COMBO_MULTIPLIERS = {
    "Yams (5 identiques)": {2: 0.0, 3: 0.0, 4: 0.0, 5: 16.0},
    "Carré (4 identiques)": {2: 0.0, 3: 0.0, 4: 9.0, 5: 11.5},
    "Full (3+2)": {2: 0.0, 3: 0.0, 4: 0.0, 5: 7.0},
    "Brelan (3 identiques)": {2: 0.0, 3: 6.5, 4: 5.2, 5: 4.3},
    "Double paire": {2: 0.0, 3: 0.0, 4: 4.5, 5: 3.4},
    "Suite": {2: 3.8, 3: 3.0, 4: 2.4, 5: 2.0},
    "Paire": {2: 2.5, 3: 2.0, 4: 1.6, 5: 1.3},
    "Rien": {2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0}
}


def get_combo_multiplier(combo_name: str, nb_des: int) -> float:
    return COMBO_MULTIPLIERS.get(combo_name, {}).get(nb_des, 0.0)


# --- FONCTIONS DE GESTION DES LIMITES ---
def check_limites_heure(guild_id: int, user_id: int):
    data = load_user_data(guild_id, user_id)
    if "dice_stats" not in data:
        data["dice_stats"] = {"parties_heure": [], "derniere_reset": datetime.now().isoformat()}
    
    stats = data["dice_stats"]
    maintenant = datetime.now()
    dernier_reset = datetime.fromisoformat(stats["derniere_reset"])
    
    if maintenant - dernier_reset >= timedelta(hours=1):
        stats["parties_heure"] = []
        stats["derniere_reset"] = maintenant.isoformat()
    
    stats["parties_heure"] = [p for p in stats["parties_heure"] if datetime.fromisoformat(p) > maintenant - timedelta(hours=1)]
    
    parties_jouees = len(stats["parties_heure"])
    default_limit = get_hourly_limit(data)
    limite = get_admin_hourly_limit(guild_id, "dice", default_limit)
    parties_restantes = float('inf') if limite is None else limite - parties_jouees
    return {
        "peut_jouer": True if limite is None else parties_restantes > 0,
        "parties_jouees": parties_jouees,
        "parties_restantes": max(0, parties_restantes),
        "temps_restant_minutes": max(0, int((timedelta(hours=1) - (maintenant - dernier_reset)).total_seconds() / 60)),
        "stats": stats,
        "limit": limite
    }


def ajouter_partie_heure(stats: dict):
    stats["parties_heure"].append(datetime.now().isoformat())


def evaluer_combinaison(des):
    counts = {i: des.count(i) for i in range(1, 7)}
    valeurs = list(counts.values())
    sorted_des = sorted(des)

    if len(des) == 5:
        if 5 in valeurs:
            combo = COMBOS[0]
        elif 4 in valeurs:
            combo = COMBOS[1]
        elif 3 in valeurs and 2 in valeurs:
            combo = COMBOS[2]
        elif 3 in valeurs:
            combo = COMBOS[3]
        elif valeurs.count(2) == 2:
            combo = COMBOS[4]
        elif sorted_des in [[1,2,3,4,5], [2,3,4,5,6]]:
            combo = COMBOS[5]
        elif 2 in valeurs:
            combo = COMBOS[6]
        else:
            combo = COMBOS[7]
    elif len(des) == 4:
        if 4 in valeurs:
            combo = COMBOS[1]
        elif 3 in valeurs:
            combo = COMBOS[3]
        elif valeurs.count(2) == 2:
            combo = COMBOS[4]
        elif sorted_des in [list(range(x, x+4)) for x in range(1, 4)]:
            combo = COMBOS[5]
        elif 2 in valeurs:
            combo = COMBOS[6]
        else:
            combo = COMBOS[7]
    elif len(des) == 3:
        if 3 in valeurs:
            combo = COMBOS[3]
        elif sorted_des in [list(range(x, x+3)) for x in range(1, 5)]:
            combo = COMBOS[5]
        elif 2 in valeurs:
            combo = COMBOS[6]
        else:
            combo = COMBOS[7]
    elif len(des) == 2:
        if 2 in valeurs:
            combo = COMBOS[6]
        elif abs(des[0] - des[1]) == 1:
            combo = COMBOS[5]
        else:
            combo = COMBOS[7]
    else:
        combo = COMBOS[7]

    multiplier = get_combo_multiplier(combo, len(des))
    return combo, multiplier


# --- MODAL ---
class DiceModal(ui.Modal, title="💰 MISE DE COLS"):
    mise_input = ui.TextInput(label="Montant à miser", placeholder="max selon votre niveau", min_length=1, required=True)

    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view
        max_bet = get_max_bet(load_user_data(parent_view.author.guild.id, parent_view.author.id), MAX_MISE)
        self.mise_input.placeholder = f"Max {format_Cols(max_bet)} Cols"

    async def on_submit(self, interaction: discord.Interaction):
        if not self.mise_input.value.isdigit():
            return await interaction.response.send_message("❌ Chiffres uniquement.", ephemeral=True)
        
        mise = int(self.mise_input.value)
        user_data = load_user_data(interaction.guild.id, interaction.user.id)
        limites = check_limites_heure(interaction.guild.id, interaction.user.id)
        
        if mise <= 0 or user_data["Cols"] < mise:
            return await interaction.response.send_message(f"❌ Solde insuffisant !", ephemeral=True)
        max_bet = get_max_bet(user_data, MAX_MISE)
        if mise > max_bet:
            return await interaction.response.send_message(f"❌ Mise max : {format_Cols(max_bet)} selon votre niveau.", ephemeral=True)
        if not limites["peut_jouer"]:
            return await interaction.response.send_message("❌ Limite horaire atteinte !", ephemeral=True)

        self.parent_view.mise = mise
        await self.parent_view.show_confirmation(interaction)


# --- SELECTOR ---
class DiceSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="1 Dé", value="1", emoji="🎲"),
            discord.SelectOption(label="2 Dés", value="2", emoji="🎲"),
            discord.SelectOption(label="3 Dés", value="3", emoji="🎲"),
            discord.SelectOption(label="4 Dés", value="4", emoji="🎲"),
            discord.SelectOption(label="5 Dés", value="5", emoji="🎲"),
        ]
        super().__init__(placeholder="Nombre de dés...", options=options)

    async def callback(self, interaction: discord.Interaction):
        self.view.nb_des = int(self.values[0])
        await self.view.show_confirmation(interaction)


# --- VUE ---
class DiceView(ui.View):
    def __init__(self, author, bot):
        super().__init__(timeout=300)
        self.author = author
        self.bot = bot
        self.mise = 0
        self.nb_des = 5
        self.message = None

    def update_items(self, step):
        self.clear_items()
        if step == "initial":
            self.add_item(self.btn_initial_mise)
        elif step == "confirmation":
            self.add_item(DiceSelect())
            self.add_item(self.confirm_roll)
            self.add_item(self.modify_bet)
        elif step == "resultat":
            self.add_item(self.btn_changer_mise)
            btn_rejouer = ui.Button(label=f"Rejouer ({format_Cols(self.mise)} Cols)", style=discord.ButtonStyle.success, emoji="🔄")
            btn_rejouer.callback = self.btn_rejouer_meme_mise
            self.add_item(btn_rejouer)

    @ui.button(label="Placer une mise", style=discord.ButtonStyle.secondary, emoji="💰")
    async def btn_initial_mise(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.author: return
        await interaction.response.send_modal(DiceModal(self))

    @ui.button(label="Lancer les dés !", style=discord.ButtonStyle.success, emoji="🎲")
    async def confirm_roll(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.author: return
        await self.process_game(interaction)

    @ui.button(label="Modifier Mise", style=discord.ButtonStyle.primary, emoji="✏️")
    async def modify_bet(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.author: return
        await interaction.response.send_modal(DiceModal(self))

    @ui.button(label="Changer mise", style=discord.ButtonStyle.secondary, emoji="🎲")
    async def btn_changer_mise(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.author: return
        await interaction.response.send_modal(DiceModal(self))

    async def btn_rejouer_meme_mise(self, interaction: discord.Interaction):
        if interaction.user != self.author: return
        user_data = load_user_data(interaction.guild.id, self.author.id)
        limites = check_limites_heure(interaction.guild.id, self.author.id)
        if user_data["Cols"] < self.mise or not limites["peut_jouer"]:
            return await interaction.response.send_message("❌ Impossible de rejouer (Fonds ou Limite).", ephemeral=True)
        await self.process_game(interaction)

    async def show_confirmation(self, interaction):
        self.update_items("confirmation")
        limites = check_limites_heure(interaction.guild.id, self.author.id)
        premium_active, bonus_remaining = get_vote_bonus_status(self.author.id)
        mot_de = "dé" if self.nb_des == 1 else "dés"
        title = f"{PREMIUM_EMOJI} 🛡️ CONFIGURATION" if premium_active else "🛡️ CONFIGURATION"
        limit_display = "∞" if limites["limit"] is None else limites["limit"]
        desc = (f"💰 Mise : **{format_Cols(self.mise)} Cols**\n"
                f"🎲 Quantité : **{self.nb_des} {mot_de}**\n"
                f"🎮 Parties : **{limites['parties_restantes']}/{limit_display}**")
        embed = self.get_embed(title, desc, interaction.guild)
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    async def process_game(self, interaction: discord.Interaction):
        # Déduction mise et stats
        limites = check_limites_heure(interaction.guild.id, self.author.id)
        ajouter_partie_heure(limites["stats"])
        user_data = load_user_data(interaction.guild.id, self.author.id)
        user_data["Cols"] -= self.mise
        user_data["dice_stats"] = limites["stats"]
        save_user_data(interaction.guild.id, self.author.id, user_data)

        await interaction.response.edit_message(content="🎲 *Les dés roulent sur la table...*", embed=None, view=None)
        await asyncio.sleep(2)

        des = [random.randint(1, 6) for _ in range(self.nb_des)]
        premium_active, bonus_remaining = get_vote_bonus_status(self.author.id)

        if self.nb_des == 1:
            valeur = des[0]
            mult = DICE_1_MULTIPLIERS[valeur]
            gain = int(self.mise * mult)
            nom_combo = f"Face {valeur}"
        else:
            nom_combo, multiplier = evaluer_combinaison(des)
            gain = int(self.mise * multiplier)

        if premium_active and gain > 0:
            gain *= 2
        gain = apply_admin_gain_limit(interaction.guild.id, "dice", gain)

        user_data = load_user_data(interaction.guild.id, self.author.id)
        user_data["Cols"] += gain
        premium_active, _ = get_vote_bonus_status(self.author.id)
        user_data = add_xp(user_data, XP_PER_GAME_COMMAND, False)
        save_user_data(interaction.guild.id, self.author.id, user_data)
        from cogs.casino.autres.achievements import check_and_unlock
        check_and_unlock(interaction.guild.id, self.author.id, "dice", user_data)

        title = "✨ VICTOIRE" if gain > self.mise else "💀 DÉFAITE" if gain == 0 else "⚖️ RÉSULTAT"
        if premium_active:
            title = f"{PREMIUM_EMOJI} {title}"

        mot_de = "dé" if self.nb_des == 1 else "dés"
        limit_display = "∞" if limites['limit'] is None else limites['limit']
        res_desc = (f"🎲 Résultat ({self.nb_des} {mot_de}) : **{' '.join(map(str, des))}**\n"
                    f"📝 Analyse : **{nom_combo}**\n\n"
                    f"🎁 Gain : **{format_Cols(gain)} Cols**\n\n"
                    f"💳 Solde : **{format_Cols(user_data['Cols'])} Cols**\n"
                    f"🎮 Parties restantes : **{limites['parties_restantes']}/{limit_display}**")

        self.update_items("resultat")
        embed = self.get_embed(title, res_desc, interaction.guild)
        await interaction.edit_original_response(content=None, embed=embed, view=self)

    def get_embed(self, title, desc, guild):
        if config_manager:
            return config_manager.get_formatted_embed(guild=guild, user=self.author, bot=self.bot, title=title, description=desc)
        return discord.Embed(title=title, description=desc, color=0x2b2d31)


class DiceMiyazaki(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="dice", description="Jeu de dés avec mise.")
    async def dice(self, ctx: commands.Context):
        user_data = load_user_data(ctx.guild.id, ctx.author.id)
        limites = check_limites_heure(ctx.guild.id, ctx.author.id)
        if not limites["peut_jouer"]:
            return await ctx.send(f"❌ Limite atteinte. Reset dans {limites['temps_restant_minutes']} min.", ephemeral=True)
        
        premium_active, bonus_remaining = get_vote_bonus_status(ctx.author.id)
        title = f"{PREMIUM_EMOJI} 🎲 JEU DE DÉS" if premium_active else "🎲 JEU DE DÉS"
        limit_display = "∞" if limites['limit'] is None else limites['limit']
        desc = (
            f"💰 Solde : **{format_Cols(user_data['Cols'])} Cols**\n"
            f"🎮 Parties restantes : **{limites['parties_restantes']}/{limit_display}**"
        )
        view = DiceView(ctx.author, self.bot)
        view.update_items("initial")
        embed = view.get_embed(title, desc, ctx.guild)
        view.message = await ctx.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(DiceMiyazaki(bot))
