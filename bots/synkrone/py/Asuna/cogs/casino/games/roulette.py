import discord
from discord.ext import commands
from discord import ui
import random, asyncio, os, json, time
from datetime import datetime, timedelta
from pathlib import Path

# ===================== CONFIG MANAGER ========================
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

from cogs.casino.autres.achievements import add_xp, get_hourly_limit, get_max_bet, XP_PER_GAME_COMMAND
from cogs.casino.admin.adminlimit import apply_admin_gain_limit, get_admin_hourly_limit

# ==========================
# CONFIG
# ==========================
MAX_BET = 10_000_000
MAX_PARTIES_PAR_HEURE = 20


# ==========================
# DATA
# ==========================
def get_user_file_path(guild_id: int, user_id: int):
    base_dir = os.path.join('cogs', 'casino', 'data', str(guild_id))
    os.makedirs(base_dir, exist_ok=True)
    return os.path.join(base_dir, f"{user_id}.json")

def load_user_data(guild_id: int, user_id: int):
    path = get_user_file_path(guild_id, user_id)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    return {
        "Cols": 1000,
        "roulette_stats": {"parties_heure": []}
    }

def save_user_data(guild_id: int, user_id: int, data: dict):
    with open(get_user_file_path(guild_id, user_id), 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

def format_Cols(value: int):
    return f"{int(value):,}".replace(",", " ")

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


def check_limite(guild_id: int, user_id: int):
    data = load_user_data(guild_id, user_id)
    now = datetime.now()

    if "roulette_stats" not in data:
        data["roulette_stats"] = {"parties_heure": []}

    une_heure = timedelta(hours=1)
    parties = data["roulette_stats"]["parties_heure"]

    parties = [p for p in parties if now - datetime.fromisoformat(p) <= une_heure]
    data["roulette_stats"]["parties_heure"] = parties
    save_user_data(guild_id, user_id, data)

    jouees = len(parties)
    default_limit = get_hourly_limit(data)
    limite = get_admin_hourly_limit(guild_id, "roulette", default_limit)

    return {
        "peut_jouer": True if limite is None else jouees < limite,
        "restantes": float('inf') if limite is None else max(0, limite - jouees),
        "jouees": jouees,
        "limit": limite
    }


# ==========================
# ROUE
# ==========================
ROUE_PATH = [
    (1,5), (1,6), (1,7), (1,8), (1,9), (2,10), (2,11), (3,12), (4,13), (5,13),
    (6,14), (7,14), (8,14), (9,14), (10,14), (11,13), (12,13), (13,12), (14,11), (14,10),
    (15,9), (15,8), (15,7), (15,6), (15,5), (14,4), (14,3), (13,2), (12,1), (11,1),
    (10,0), (9,0), (8,0), (7,0), (6,0), (5,1), (4,1), (3,2), (2,3), (2,4)
]

def get_info_from_index(idx):
    pos = ROUE_PATH[idx % len(ROUE_PATH)]
    if pos == (15,7):
        return "vert", "🟩", 0
    if idx % 2 == 0:
        return "rouge", "🟥", random.randint(2, 36)
    return "noir", "⬛", random.randint(1, 35)

def generate_visual_wheel(ball_pos_index=None):
    grid = [["⬜" for _ in range(15)] for _ in range(17)]

    for i, pos in enumerate(ROUE_PATH):
        color, emoji, _ = get_info_from_index(i)
        grid[pos[0]][pos[1]] = emoji

    if ball_pos_index is not None:
        pos = ROUE_PATH[ball_pos_index % len(ROUE_PATH)]
        grid[pos[0]][pos[1]] = "🟣"

    return "\n".join("".join(row) for row in grid)


# ==========================
# VIEW
# ==========================
class RouletteView(ui.View):

    def __init__(self, author, bot):
        super().__init__(timeout=180)
        self.author = author
        self.bot = bot
        self.mise = 0
        self.choix = None

    def format_title(self, base_title: str) -> str:
        premium_active, _ = get_vote_bonus_status(self.author.id)
        return f"{PREMIUM_EMOJI} {base_title}" if premium_active else base_title

    def get_mult(self):
        if self.choix == "vert":
            return 14
        return 1.7

    def get_emb(self, title, desc, ball=None):
        limite = check_limite(self.author.guild.id, self.author.id)

        limit_display = "∞" if limite['limit'] is None else limite['limit']
        description = (
            f"```\n{generate_visual_wheel(ball)}\n```\n"
            f"{desc}\n\n"
            f"🎮 Parties restantes : **{limite['restantes']}/{limit_display}**"
        )

        guild = getattr(self.author, 'guild', None)
        return self.bot.config.get_formatted_embed(
            title=title,
            description=description,
            bot_user=self.bot.user,
            guild=guild,
            user=self.author,
            target_id=guild.id if guild else None
        )

    def update_view(self, step):
        self.clear_items()

        if step == "initial":
            btn = ui.Button(label="Placer une mise", emoji="💰", style=discord.ButtonStyle.secondary)
            btn.callback = self.ouvrir_mise
            self.add_item(btn)

        elif step == "choisir_couleur":
            btn_rouge = ui.Button(label="Rouge", style=discord.ButtonStyle.secondary, emoji="🟥")
            btn_noir = ui.Button(label="Noir", style=discord.ButtonStyle.secondary, emoji="⬛")
            btn_vert = ui.Button(label="Vert", style=discord.ButtonStyle.secondary, emoji="🟩")
            btn_retour = ui.Button(label="Retour", style=discord.ButtonStyle.secondary, emoji="🔙")

            btn_rouge.callback = self.set_couleur_rouge
            btn_noir.callback = self.set_couleur_noir
            btn_vert.callback = self.set_couleur_vert
            btn_retour.callback = self.retour_initial

            self.add_item(btn_rouge)
            self.add_item(btn_noir)
            self.add_item(btn_vert)
            self.add_item(btn_retour)

        elif step == "final":
            btn_lancer = ui.Button(label="Lancer la roulette", style=discord.ButtonStyle.secondary, emoji="🎡")
            btn_retour = ui.Button(label="Retour", style=discord.ButtonStyle.secondary, emoji="🔙")

            btn_lancer.callback = self.lancer_jeu
            btn_retour.callback = self.retour_couleur
            
            self.add_item(btn_lancer)
            self.add_item(btn_retour)

        elif step == "resultat":
            btn_rejouer_meme = ui.Button(label=f"Rejouer ({format_Cols(self.mise)} Cols)", style=discord.ButtonStyle.secondary, emoji="🔁")
            btn_rejouer_autre = ui.Button(label="Nouvelle mise", style=discord.ButtonStyle.secondary, emoji="💰")

            btn_rejouer_meme.callback = self.rejouer_meme_mise
            btn_rejouer_autre.callback = self.ouvrir_mise

            self.add_item(btn_rejouer_meme)
            self.add_item(btn_rejouer_autre)

    # --- ACTIONS DE RETOUR ---
    async def retour_initial(self, i: discord.Interaction):
        if i.user != self.author:
            return await i.response.send_message("❌ Pas votre session.", ephemeral=True)
        self.update_view("initial")
        await i.response.edit_message(embed=self.get_emb(self.format_title("🎡 ROULETTE"), "Cliquez pour commencer."), view=self)

    async def retour_couleur(self, i: discord.Interaction):
        if i.user != self.author:
            return await i.response.send_message("❌ Pas votre session.", ephemeral=True)
        self.update_view("choisir_couleur")
        await i.response.edit_message(
            embed=self.get_emb(self.format_title("COULEUR"), f"💰 Mise actuelle : {format_Cols(self.mise)} Cols\n\nChoisissez votre couleur :"), 
            view=self
        )

    # --- ACTIONS DE MISE ---
    async def ouvrir_mise(self, i: discord.Interaction):
        if i.user != self.author:
            return await i.response.send_message("❌ Pas votre session.", ephemeral=True)
        await i.response.send_modal(RouletteMiseModal(self))

    async def rejouer_meme_mise(self, i: discord.Interaction):
        if i.user != self.author:
            return await i.response.send_message("❌ Pas votre session.", ephemeral=True)
            
        data = load_user_data(i.guild.id, self.author.id)
        if self.mise > data["Cols"]:
            return await i.response.send_message("❌ Solde insuffisant pour rejouer cette mise.", ephemeral=True)
            
        self.update_view("choisir_couleur")
        await i.response.edit_message(
            embed=self.get_emb("COULEUR", f"💰 Mise : {format_Cols(self.mise)} Cols\n\nChoisissez votre couleur :"), 
            view=self
        )

    # --- ACTIONS DE COULEUR ---
    async def set_couleur_rouge(self, i: discord.Interaction):
        if i.user != self.author:
            return await i.response.send_message("❌ Pas votre session.", ephemeral=True)
        self.choix = "rouge"
        self.update_view("final")
        await i.response.edit_message(embed=self.get_emb(self.format_title("CONFIRMATION"), "Mise configurée sur : **Rouge** 🟥"), view=self)

    async def set_couleur_noir(self, i: discord.Interaction):
        if i.user != self.author:
            return await i.response.send_message("❌ Pas votre session.", ephemeral=True)
        self.choix = "noir"
        self.update_view("final")
        await i.response.edit_message(embed=self.get_emb(self.format_title("CONFIRMATION"), "Mise configurée sur : **Noir** ⬛"), view=self)

    async def set_couleur_vert(self, i: discord.Interaction):
        if i.user != self.author:
            return await i.response.send_message("❌ Pas votre session.", ephemeral=True)
        self.choix = "vert"
        self.update_view("final")
        await i.response.edit_message(embed=self.get_emb(self.format_title("CONFIRMATION"), "Mise configurée sur : **Vert** 🟩"), view=self)

    # --- LANCEMENT JEU ---
    async def lancer_jeu(self, interaction: discord.Interaction):
        if interaction.user != self.author:
            return await interaction.response.send_message("❌ Pas votre session.", ephemeral=True)

        limite = check_limite(interaction.guild.id, self.author.id)

        if not limite["peut_jouer"]:
            limit_display = "∞" if limite["limit"] is None else limite["limit"]
            return await interaction.response.send_message(
                f"❌ Limite de {limit_display} roulettes par heure atteinte.",
                ephemeral=True
            )

        self.clear_items()
        await interaction.response.edit_message(view=None)

        current_idx = random.randint(0, len(ROUE_PATH)-1)
        steps = random.randint(35, 50)

        # Animation fluide
        for s in range(steps):
            current_idx = (current_idx + 1) % len(ROUE_PATH)

            if s % 2 == 0:
                await interaction.edit_original_response(
                    embed=self.get_emb("🎡 LA ROUE TOURNE", "🎲 La bille tourne...", current_idx)
                )

            await asyncio.sleep(0.07 + (s/steps)*0.05)

        res_color, res_emoji, res_num = get_info_from_index(current_idx)
        user_data = load_user_data(interaction.guild.id, self.author.id)

        win = (self.choix == res_color)

        try:
            from cogs.casino.autres.achievements import increment_counter
            user_data = increment_counter(user_data, "Cols_spent", self.mise)
        except ImportError:
            pass

        premium_active, _ = get_vote_bonus_status(self.author.id)
        if win:
            gain = int(self.mise * self.get_mult())
            if premium_active:
                gain *= 2
            gain = apply_admin_gain_limit(interaction.guild.id, "roulette", gain)
            user_data["Cols"] += (gain - self.mise)
            status = f"🏆 Gagné ! {res_emoji} {res_num}\n🎁 Gain : {format_Cols(gain)} Cols"
        else:
            user_data["Cols"] -= self.mise
            status = f"💸 Perdu... {res_emoji} {res_num}"

        user_data.setdefault("roulette_stats", {"parties_heure": []})
        user_data["roulette_stats"]["parties_heure"].append(datetime.now().isoformat())
        user_data.setdefault("xp", 0)
        user_data = add_xp(user_data, XP_PER_GAME_COMMAND, False)
        save_user_data(interaction.guild.id, self.author.id, user_data)

        self.update_view("resultat")

        await interaction.edit_original_response(
            embed=self.get_emb(self.format_title("RÉSULTAT"), f"{status}\n💳 Nouveau solde : {format_Cols(user_data['Cols'])} Cols", current_idx),
            view=self
        )


# ==========================
# MODALS
# ==========================
class RouletteMiseModal(ui.Modal, title="💰 MISE"):

    def __init__(self, v):
        super().__init__()
        self.v = v

        max_bet = get_max_bet(load_user_data(v.author.guild.id, v.author.id), MAX_BET)
        self.m = ui.TextInput(
            label="Montant à miser",
            placeholder=f"Max {format_Cols(max_bet)} Cols",
            min_length=1,
            max_length=10
        )
        self.add_item(self.m)

    async def on_submit(self, i: discord.Interaction):
        if not self.m.value.isdigit():
            return await i.response.send_message("❌ Nombre invalide.", ephemeral=True)

        val = int(self.m.value)
        data = load_user_data(i.guild.id, self.v.author.id)

        max_bet = get_max_bet(data, MAX_BET)
        if val <= 0 or val > max_bet:
            return await i.response.send_message(f"❌ Mise max = {format_Cols(max_bet)} Cols selon votre niveau.", ephemeral=True)

        if val > data["Cols"]:
            return await i.response.send_message("❌ Solde insuffisant.", ephemeral=True)

        self.v.mise = val
        self.v.update_view("choisir_couleur")

        await i.response.edit_message(
            embed=self.v.get_emb(self.v.format_title("COULEUR"), f"💰 Mise : {format_Cols(val)} Cols\n\nChoisissez votre couleur :"),
            view=self.v
        )


# ==========================
# COG
# ==========================
class RouletteMiyazaki(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="roulette", description="Jouer à la roulette avec limite horaire ajustée selon votre niveau")
    async def roulette(self, ctx):
        limite = check_limite(ctx.guild.id, ctx.author.id)

        if not limite["peut_jouer"]:
            limit_display = "∞" if limite["limit"] is None else limite["limit"]
            return await ctx.send(
                f"❌ Limite horaire atteinte. Maximum {limit_display} roulettes par heure.",
                ephemeral=True
            )

        v = RouletteView(ctx.author, self.bot)
        v.update_view("initial")

        await ctx.send(
            embed=v.get_emb(v.format_title("🎡 ROULETTE"), "Cliquez pour commencer."),
            view=v
        )


async def setup(bot):
    await bot.add_cog(RouletteMiyazaki(bot))