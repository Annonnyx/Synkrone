import discord
from discord.ext import commands
from discord import ui
import random, os, json, asyncio, time
from datetime import datetime, timedelta
from pathlib import Path

from cogs.casino.autres.achievements import add_xp, get_hourly_limit, get_max_bet, XP_PER_GAME_COMMAND
from cogs.casino.admin.adminlimit import apply_admin_gain_limit, get_admin_hourly_limit

# --- GESTION DES LIMITES ---
MAX_SLOTS_HEURE = 20

# --- GESTION DES DONNÉES ---
def get_user_file_path(guild_id: int, user_id: int):
    base_dir = os.path.join('cogs', 'casino', 'data', str(guild_id))
    if not os.path.exists(base_dir): os.makedirs(base_dir)
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
    with open(path, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4)

def check_slots_limite_heure(guild_id: int, user_id: int) -> dict:
    data = load_user_data(guild_id, user_id)
    now = datetime.now()
    if "slots_stats" not in data:
        data["slots_stats"] = {"parties_heure": [], "derniere_reset": now.isoformat()}
    stats = data["slots_stats"]
    try:
        derniere_reset = datetime.fromisoformat(stats["derniere_reset"])
    except ValueError:
        derniere_reset = now
    if now - derniere_reset > timedelta(hours=1):
        stats["parties_heure"] = []
        stats["derniere_reset"] = now.isoformat()
    stats["parties_heure"] = [
        p for p in stats["parties_heure"]
        if datetime.fromisoformat(p) > now - timedelta(hours=1)
    ]
    parties_count = len(stats["parties_heure"])
    default_limit = get_hourly_limit(data)
    limite = get_admin_hourly_limit(guild_id, "slots", default_limit)
    parties_restantes = float('inf') if limite is None else limite - parties_count
    temps_restant = derniere_reset + timedelta(hours=1) - now
    minutes_restantes = int(temps_restant.total_seconds() / 60)
    return {
        "parties_jouees": parties_count,
        "parties_restantes": max(0, parties_restantes),
        "peut_jouer": True if limite is None else parties_restantes > 0,
        "stats": stats,
        "temps_restant_minutes": minutes_restantes,
        "limit": limite,
    }

# ===================== CONFIG MANAGER ========================
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# --- SYSTÈME DE JACKPOT ---
def get_jackpot_data(guild_id: int):
    path = os.path.join('cogs', 'casino', 'data', str(guild_id), "jackpot.json")
    if os.path.exists(path):
        with open(path, 'r') as f: return json.load(f)
    return {"total": 5000, "last_win_date": ""}

def update_jackpot(guild_id: int, amount: int, reset=False):
    path = os.path.join('cogs', 'casino', 'data', str(guild_id), "jackpot.json")
    data = get_jackpot_data(guild_id)
    if reset:
        data["total"] = 5000 # Valeur de base après reset
        data["last_win_date"] = datetime.now().strftime("%Y-%m-%d")
    else:
        data["total"] += amount
    with open(path, 'w') as f: json.dump(data, f, indent=4)

def format_Cols(value: int) -> str:
    return f"{value:,}".replace(',', ' ')

VOTE_DATA_FILE = Path.cwd() / "data" / "public" / "data_vote" / "users.json"
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

# --- CONFIGURATION ---
# Tous les multiplicateurs >= 1.05 : tout combo gagnant rembourse la mise + au moins 5%
SYMBOLS_CONFIG = {
    "💎": 2.0,   # Diamant   — x2.0
    "🔔": 1.6,   # Cloche    — x1.6
    "🍋": 1.3,   # Citron    — x1.3
    "🍒": 1.15,  # Cerise    — x1.15
    "🍇": 1.05,  # Raisin    — x1.05
}
JACKPOT_PROBABILITY = 0.0001  # 0.01% chance de déclencher le jackpot

def generate_slots_grid(matrix=None):
    if matrix is None:
        matrix = [["❓", "❓", "❓"] for _ in range(3)]
    grid =  "```\n"
    grid += "------- MACHINE -------\n"
    grid += f"   {matrix[0][0]}  |  {matrix[0][1]}  |  {matrix[0][2]}\n"
    grid += f"▶  {matrix[1][0]}  |  {matrix[1][1]}  |  {matrix[1][2]}  ◀\n"
    grid += f"   {matrix[2][0]}  |  {matrix[2][1]}  |  {matrix[2][2]}\n"
    grid += "-----------------------\n"
    grid += "```"
    return grid

def generate_payout_table(mise, jackpot_val):
    table = f"🏆 **JACKPOT ACTUEL : {format_Cols(jackpot_val)} Cols**\n\n"
    table += "**📋 TABLEAU DES GAINS**\n"
    for emoji, mult in SYMBOLS_CONFIG.items():
        if emoji == "💎":
            table += f"🏆 `x{mult}` : **{format_Cols(int(mise * mult))} Cols**\n"
        else:
            potentiel = int(mise * mult) if mise > 0 else 0
            table += f"{emoji} `x{mult}` : **{format_Cols(potentiel)} Cols**\n"
    return table

# --- VUE DU JEU ---
class SlotsView(ui.View):
    def __init__(self, author, bot, guild, slots_stats=None, ancienne_mise=0):
        super().__init__(timeout=180)
        self.author = author
        self.bot = bot
        self.guild = guild
        self.slots_stats = slots_stats
        self.mise = ancienne_mise

    def get_emb(self, title, desc, matrix=None, guild_id=None):
        premium_active, _ = get_vote_bonus_status(self.author.id)
        title_prefix = f"{PREMIUM_EMOJI} 🎰 {title}" if premium_active else f"🎰 {title}"
        jackpot_val = get_jackpot_data(guild_id)["total"] if guild_id else 0
        limites = check_slots_limite_heure(self.guild.id, self.author.id)
        full_desc = f"{generate_slots_grid(matrix)}\n"
        max_bet = get_max_bet(load_user_data(self.guild.id, self.author.id), 10_000_000)
        full_desc += f"💰 Mise : **{format_Cols(self.mise)} Cols**\n"
        limit_display = "∞" if limites['limit'] is None else limites['limit']
        full_desc += f"🎮 Parties restantes : **{limites['parties_restantes']}/{limit_display}**\n\n"
        full_desc += f"{generate_payout_table(self.mise, jackpot_val)}\n"
        full_desc += f"\n{desc}"
        return self.bot.config.get_formatted_embed(title=title_prefix, description=full_desc, bot_user=self.bot.user, guild=self.guild, user=self.author, target_id=self.guild.id if self.guild else None)

    def update_view(self, step):
        self.clear_items()
        if step == "initial":
            btn = ui.Button(label="Placer une mise", style=discord.ButtonStyle.secondary, emoji="💰")
            btn.callback = self.ouvrir_modal_mise
            self.add_item(btn)
        elif step == "confirm":
            btn_start = ui.Button(label="Lancer la machine", style=discord.ButtonStyle.success, emoji="🎰")
            btn_start.callback = self.lancer_slots
            btn_back = ui.Button(label="Annuler", style=discord.ButtonStyle.danger)
            btn_back.callback = self.retour_accueil
            self.add_item(btn_start)
            self.add_item(btn_back)
        elif step == "resultat":
            btn_re = ui.Button(label="Nouvelle mise", style=discord.ButtonStyle.secondary, emoji="💰")
            btn_re.callback = self.ouvrir_modal_mise
            btn_same = ui.Button(label=f"Rejouer ({format_Cols(self.mise)} Cols)", style=discord.ButtonStyle.primary, emoji="🔄")
            btn_same.callback = self.rejouer_meme_somme
            self.add_item(btn_re)
            self.add_item(btn_same)

    async def ouvrir_modal_mise(self, i):
        if i.user != self.author: return await i.response.send_message("❌ Ce n'est pas votre session.", ephemeral=True)
        await i.response.send_modal(MiseSlotsModal(self))

    async def retour_accueil(self, i):
        if i.user != self.author: return await i.response.send_message("❌ Ce n'est pas votre session.", ephemeral=True)
        self.update_view("initial")
        data = load_user_data(i.guild.id, self.author.id)
        await i.response.edit_message(embed=self.get_emb("Machine à sous", f"💳 Solde : **{format_Cols(data['Cols'])} Cols**", guild_id=i.guild.id), view=self)

    async def rejouer_meme_somme(self, i):
        if i.user != self.author: return await i.response.send_message("❌ Ce n'est pas votre session.", ephemeral=True)
        data = load_user_data(i.guild.id, self.author.id)
        if data["Cols"] < self.mise: return await i.response.send_message("❌ Solde insuffisant.", ephemeral=True)
        await self.lancer_slots(i)

    async def lancer_slots(self, i):
        if i.user != self.author: return await i.response.send_message("❌ Ce n'est pas votre session.", ephemeral=True)

        # Vérifier les limites avant de jouer
        limites = check_slots_limite_heure(i.guild.id, self.author.id)
        limit_display = "∞" if limites['limit'] is None else limites['limit']
        if not limites["peut_jouer"]:
            return await i.response.send_message(f"❌ Limite horaire atteinte ! ({limites['parties_jouees']}/{limit_display} parties)", ephemeral=True)

        # Déduction immédiate de la mise
        user_data = load_user_data(i.guild.id, self.author.id)
        
        # Ajouter la mise aux statistiques totales
        from cogs.casino.autres.achievements import increment_counter
        user_data = increment_counter(user_data, "Cols_spent", self.mise)
        
        user_data["Cols"] -= self.mise
        # Comptage de la partie jouée
        user_data["slots_stats"] = limites["stats"]
        user_data["slots_stats"]["parties_heure"].append(datetime.now().isoformat())
        save_user_data(i.guild.id, self.author.id, user_data)

        self.clear_items()
        await i.response.edit_message(view=None)

        # Animation
        for _ in range(3):
            fake_m = [[random.choice(list(SYMBOLS_CONFIG.keys())) for _ in range(3)] for _ in range(3)]
            await i.edit_original_response(embed=self.get_emb("Machine à sous : Tirage...", "Bonne chance !", fake_m, i.guild.id))
            await asyncio.sleep(0.7)

        # Résultat final
        m = [[random.choice(list(SYMBOLS_CONFIG.keys())) for _ in range(3)] for _ in range(3)]
        total_gain = 0
        combos = []

        # Calcul Jackpot (0.01% de chance OU 3 diamants sur la ligne centrale)
        jackpot_data = get_jackpot_data(i.guild.id)
        won_jackpot = False
        today = datetime.now().strftime("%Y-%m-%d")

        if m[1][0] == m[1][1] == m[1][2] == "💎" or random.random() < JACKPOT_PROBABILITY:
            if jackpot_data["last_win_date"] != today:
                won_jackpot = True
                total_gain = jackpot_data["total"]
                update_jackpot(i.guild.id, 0, reset=True)

        if not won_jackpot:
            # 1. Horizontale (Centrale x1.0, lignes adjacentes x0.6 — min garanti x1.05)
            for idx, row in enumerate(m):
                if row[0] == row[1] == row[2]:
                    ratio = 1.0 if idx == 1 else 0.6
                    total_gain += int(self.mise * (SYMBOLS_CONFIG[row[0]] - 1) * ratio)
                    combos.append(f"Ligne {idx+1}")
            # 2. Verticale (x0.5 — min garanti x1.05 car SYMBOLS_CONFIG >= 1.05)
            for col in range(3):
                if m[0][col] == m[1][col] == m[2][col]:
                    total_gain += int(self.mise * (SYMBOLS_CONFIG[m[0][col]] - 1) * 0.5)
                    combos.append(f"Colonne {col+1}")
            # 3. Diagonale (x0.4)
            if m[0][0] == m[1][1] == m[2][2]:
                total_gain += int(self.mise * (SYMBOLS_CONFIG[m[0][0]] - 1) * 0.4)
                combos.append("Diagonale ↘")
            if m[0][2] == m[1][1] == m[2][0]:
                total_gain += int(self.mise * (SYMBOLS_CONFIG[m[0][2]] - 1) * 0.4)
                combos.append("Diagonale ↙")

        # Garantie : en victoire, le gain net est au moins égal à la mise (hors jackpot)
        if total_gain > 0 and not won_jackpot:
            total_gain = max(total_gain, self.mise)

        premium_active, _ = get_vote_bonus_status(self.author.id)
        if premium_active and total_gain > 0:
            total_gain *= 2
        total_gain = apply_admin_gain_limit(i.guild.id, "slots", total_gain)

        # Mise à jour solde final
        user_data = load_user_data(i.guild.id, self.author.id)
        if won_jackpot:
            user_data["Cols"] += self.mise + total_gain
            status = f"🎊 👑 **JACKPOT !** 👑 🎊\nGain : **{format_Cols(total_gain)} Cols**"
        elif total_gain > 0:
            user_data["Cols"] += self.mise + total_gain
            status = f"🎊 **VICTOIRE !**\nCombos : `{', '.join(combos)}`\nGain net : **{format_Cols(total_gain)} Cols**"
        else:
            update_jackpot(i.guild.id, self.mise) # Perte va au Jackpot
            status = "❌ **DÉFAITE**\nLe jackpot augmente..."

        premium_active, _ = get_vote_bonus_status(self.author.id)
        user_data = add_xp(user_data, XP_PER_GAME_COMMAND, premium_active)
        save_user_data(i.guild.id, self.author.id, user_data)
        self.update_view("resultat")
        desc = f"--- \n{status}\n💳 Solde : **{format_Cols(user_data['Cols'])} Cols**"
        await i.edit_original_response(embed=self.get_emb("Machine à sous", desc, m, i.guild.id), view=self)

# --- MODAL ---
class MiseSlotsModal(ui.Modal, title="Machine à sous : Mise"):
    m = ui.TextInput(label="Somme à miser", placeholder="max selon votre niveau", min_length=1)
    def __init__(self, v):
        super().__init__()
        self.v = v
        data = load_user_data(v.author.guild.id, v.author.id)
        max_bet = get_max_bet(data, 10_000_000)
        self.m.placeholder = f"Max {format_Cols(max_bet)} Cols"
    async def on_submit(self, i):
        if not self.m.value.isdigit(): return await i.response.send_message("❌ Nombre invalide.", ephemeral=True)
        montant = int(self.m.value)
        data = load_user_data(i.guild.id, self.v.author.id)
        max_bet = get_max_bet(data, 10_000_000)
        if montant <= 0 or montant > max_bet or montant > data["Cols"]:
            return await i.response.send_message(f"❌ Mise invalide (max {format_Cols(max_bet)} Cols selon votre niveau) ou solde insuffisant.", ephemeral=True)
        self.v.mise = montant
        self.v.update_view("confirm")
        await i.response.edit_message(embed=self.v.get_emb("Confirmation", "Faites chauffer les rouleaux !", guild_id=i.guild.id), view=self.v)

# --- COG ---
class SlotsMiyazaki(commands.Cog):
    def __init__(self, bot): self.bot = bot
    @commands.hybrid_command(name="slots", description="🎰 Jouez aux machines à sous.")
    async def slots(self, ctx):
        data = load_user_data(ctx.guild.id, ctx.author.id)
        limites = check_slots_limite_heure(ctx.guild.id, ctx.author.id)
        limit_display = "∞" if limites['limit'] is None else limites['limit']
        if not limites["peut_jouer"]:
            embed = discord.Embed(
                title="❌ Limite horaire atteinte",
                description=f"🎮 Parties jouées : **{limites['parties_jouees']}/{limit_display}**\n"
                            f"⏰ Prochain reset dans **{limites['temps_restant_minutes']}** minutes\n\n"
                            f"💰 Solde actuel : **{format_Cols(data['Cols'])} Cols**",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed, ephemeral=True)
        view = SlotsView(ctx.author, self.bot, ctx.guild, limites["stats"])
        view.update_view("initial")
        await ctx.send(embed=view.get_emb("Machine à sous", f"💳 Votre solde : **{format_Cols(data['Cols'])} Cols**", guild_id=ctx.guild.id), view=view)

async def setup(bot):
    await bot.add_cog(SlotsMiyazaki(bot))