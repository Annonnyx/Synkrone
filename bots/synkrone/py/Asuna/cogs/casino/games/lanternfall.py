import discord
from discord.ext import commands
from discord import ui
import random, os, json, asyncio, time
from datetime import datetime
from pathlib import Path

# ===================== CONFIG MANAGER ========================
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

from cogs.casino.autres.achievements import add_xp, get_max_bet, XP_PER_GAME_COMMAND

# --- CONFIGURATION DU TERRAIN (15 COLONNES STRICTES) ---
# Codes : 0=, 1-7=Départs, 9=, 10=, 11=, 12=, 13=
RAW_GRID = [
    [0, 1, 0, 2, 0, 3, 0, 4, 0, 5, 0, 6, 0, 7, 0],  # L0
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],  # L1
    [0, 9, 0, 9, 0, 0, 0, 0, 0, 0, 0, 9, 0, 9, 0],  # L2
    [0, 0, 0, 0, 9, 0, 0, 0, 0, 0, 9, 0, 0, 0, 0],  # L3
    [0, 0, 0, 0, 0, 0, 0, 9, 0, 0, 0, 0, 0, 0, 0],  # L4
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],  # L5
    [0, 9, 0, 0, 0, 9, 0, 0, 0, 9, 0, 0, 0, 9, 0],  # L6
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],  # L7
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],  # L8
    [0, 0, 0, 0, 9, 0, 0, 0, 0, 0, 9, 0, 0, 0, 0],  # L9
    [0, 9, 0, 0, 0, 0, 0, 9, 0, 0, 0, 0, 0, 9, 0],  # L10
    [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],  # L11
    [10, 0, 11, 0, 12, 0, 13, 0, 13, 0, 12, 0, 11, 0, 10]  # L12
]

# Mapping des émojis
EMOJI_MAP = {
    0: "⬛", 9: "⚪", 10: "🟥", 11: "🟧", 12: "🔵", 13: "🟢",
    1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣", 6: "6️⃣", 7: "7️⃣"
}

# Multiplicateurs basés sur les codes couleurs
MULTI_MAP = {10: 1.6, 11: 1.9, 12: 2.2, 13: 2.5}

def draw_grid(pos=None):
    """Génère le rendu visuel ligne par ligne pour garantir l'alignement."""
    display = ""
    for r, row in enumerate(RAW_GRID):
        line = ""
        for c, cell in enumerate(row):
            if pos == (r, c):
                line += "🏮" # La lanterne remplace l'affichage de la case actuelle
            else:
                line += EMOJI_MAP.get(cell, "⬛")
        display += line + "\n"
    return display

# --- GESTION DES DONNÉES JSON ---
def get_data_path(guild_id, user_id):
    path = f"cogs/casino/data/{guild_id}/{user_id}.json"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path

def load_user(guild_id, user_id):
    path = get_data_path(guild_id, user_id)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f: return json.load(f)
    return {"Cols": 1000, "last_lantern_ts": 0}

def save_user(guild_id, user_id, data):
    with open(get_data_path(guild_id, user_id), 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

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


def format_title(title: str, user_id: int) -> str:
    if title.startswith(PREMIUM_EMOJI):
        return title
    premium_active, _ = get_vote_bonus_status(user_id)
    return f"{PREMIUM_EMOJI} {title}" if premium_active else title


def format_y(v): return f"{int(v):,}".replace(',', ' ')

# --- VUES DU JEU ---
class LanternFallView(ui.View):
    def __init__(self, author, bot, guild, mise):
        super().__init__(timeout=600)
        self.author, self.bot, self.guild, self.mise = author, bot, guild, mise
        self.choice = None

    def get_main_embed(self, status, pos=None):
        def m(x): return format_y(self.mise * x)
        # Légende demandée
        legend = (
            f"🟢 **x2.5** ({m(2.5)}) | 🔵 **x2.2** ({m(2.2)})\n"
            f"🟧 **x1.9** ({m(1.9)}) | 🟥 **x1.6** ({m(1.6)})"
        )
        description = (
            f"💰 Mise : **{format_y(self.mise)} Cols**\n"
            f"📊 {legend}\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"```\n{draw_grid(pos)}\n```\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"{status}"
        )
        return self.bot.config.get_formatted_embed(title=format_title("🏮 LANTERN FALL", self.author.id), description=description, bot_user=self.bot.user, guild=self.guild, user=self.author, target_id=self.guild.id if self.guild else None)

    async def update_selection_view(self, interaction):
        self.clear_items()
        select = ui.Select(placeholder="📍 Choisissez votre position de départ")
        for i in range(1, 8):
            select.add_option(label=f"Position {i}", value=str(i), emoji=EMOJI_MAP[i])
        select.callback = self.handle_selection
        self.add_item(select)
        await interaction.response.edit_message(embed=self.get_main_embed("Sélectionnez votre position..."), view=self)
        self.message = await interaction.original_response()

    async def handle_selection(self, i: discord.Interaction):
        if i.user.id != self.author.id: 
            return await i.response.send_message("❌ Ce n'est pas votre session.", ephemeral=True)
        self.choice = int(i.data['values'][0])
        self.clear_items()
        btn = ui.Button(label="Lancer la lanterne", style=discord.ButtonStyle.success, emoji="🎋")
        btn.callback = self.start_animation
        self.add_item(btn)
        
        start_c = (self.choice * 2) - 1
        await i.response.edit_message(embed=self.get_main_embed("Prêt au lancer ?", (0, start_c)), view=self)

    async def start_animation(self, i: discord.Interaction):
        if i.user.id != self.author.id: 
            return await i.response.send_message("❌ Ce n'est pas votre session.", ephemeral=True)
        self.clear_items()
        await i.response.edit_message(view=self)
        self.message = await i.original_response()

        curr_r, curr_c = 0, (self.choice * 2) - 1
        max_iterations = 20  # Sécurité pour éviter une boucle infinie
        iteration = 0
        
        try:
            while curr_r < 12 and iteration < max_iterations:
                await asyncio.sleep(0.6)
                curr_r += 1
                iteration += 1
                
                # Mouvement physique (Dérive)
                move = random.choices([-1, 0, 1], weights=[35, 30, 35])[0]
                curr_c = max(0, min(14, curr_c + move))
                
                # Rebond sur (Code 9)
                if curr_r < 12 and RAW_GRID[curr_r][curr_c] == 9:
                    curr_c = max(0, min(14, curr_c + random.choice([-1, 1])))
                
                if self.message:
                    await self.message.edit(embed=self.get_main_embed("", (curr_r, curr_c)), view=self)
                else:
                    await i.edit_original_response(embed=self.get_main_embed("", (curr_r, curr_c)), view=self)
            
            # Forcer la fin si on atteint la limite d'itérations
            if iteration >= max_iterations:
                curr_r = 12
                
        except Exception as e:
            # En cas d'erreur, terminer la partie à la dernière ligne
            curr_r = 12
            curr_c = max(0, min(14, curr_c))
        
        # --- CALCUL DU RÉSULTAT ---
        # Si la lanterne est sur un mur (0) à la ligne 12, la déplacer vers une case de gain
        if curr_r == 12 and RAW_GRID[12][curr_c] == 0:
            # Force un mouvement vers une case de gain (10, 11, 12, ou 13)
            gain_positions = [c for c in range(15) if RAW_GRID[12][c] in [10, 11, 12, 13]]
            if gain_positions:
                curr_c = random.choice(gain_positions)
        # La lanterne s'arrête sur la case où elle est réellement positionnée
        final_code = RAW_GRID[curr_r][curr_c]
        multiplier = MULTI_MAP.get(final_code, 0.0)
        total_gain = int(self.mise * multiplier)
        premium_active, _ = get_vote_bonus_status(self.author.id)
        if premium_active and total_gain > 0:
            total_gain *= 2

        data = load_user(i.guild.id, self.author.id)
        # Calcul du nouveau solde : solde - mise + gain total
        data["Cols"] = data["Cols"] - self.mise + total_gain
        data["last_lantern_ts"] = datetime.now().timestamp()
        data = add_xp(data, XP_PER_GAME_COMMAND, False)
        save_user(i.guild.id, self.author.id, data)
        
        # Vérifier les succès pour LanternFall
        from cogs.casino.autres.achievements import increment_counter, check_and_unlock
        data = increment_counter(data, "lantern_games")
        check_and_unlock(i.guild.id, self.author.id, "lantern_games", data)

        if multiplier > 1:
            # Récupérer le nom de la couleur pour l'affichage
            color_names = {10: "rouge", 11: "orange", 12: "bleu", 13: "vert"}
            color_name = color_names.get(final_code, "inconnue")
            res_msg = f"✨ **VICTOIRE !**\n🏮 Case {color_name} (x{multiplier})\n💰 Gain : `+{format_y(total_gain)} Cols`"
        elif multiplier == 1:
            res_msg = f"⚖️ **REMBOURSEMENT**\n💰 Montant : `{format_y(total_gain)} Cols`"
        else:
            res_msg = f"💀 **DÉFAITE...**\n💰 Perte : `-{format_y(self.mise)} Cols`"

        final_status = f"{res_msg}\n💳 Nouveau solde : **{format_y(data['Cols'])} Cols**"
        await i.edit_original_response(embed=self.get_main_embed(final_status, (curr_r, curr_c)), view=None)

# --- COMMANDES ---
class LanternFallCog(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.hybrid_command(name="lanternfall", description="Jeu de la lanterne tombante avec des multiplicateurs variables")
    async def lanternfall(self, ctx):
        data = load_user(ctx.guild.id, ctx.author.id)
        
        # Cooldown 1h
        now = datetime.now().timestamp()
        last_ts = data.get("last_lantern_ts", 0)
        diff_s = now - last_ts
        if diff_s < 3600:
            diff = 3600 - diff_s
            return await ctx.send(f"⏳ Revenez dans **{int(diff//60)}m {int(diff%60)}s**.", ephemeral=True)

        class Lobby(ui.View):
            def __init__(self, author, bot):
                super().__init__(); self.author, self.bot = author, bot
            @ui.button(label="Jouer", style=discord.ButtonStyle.primary, emoji="🏮")
            async def play(self, i: discord.Interaction, btn):
                if i.user.id != self.author.id: 
                    return await i.response.send_message("❌ Ce n'est pas votre session.", ephemeral=True)
                await i.response.send_modal(MiseModal(self.bot, self.author))

        class MiseModal(ui.Modal, title="Mise Lantern Fall"):
            amount = ui.TextInput(label="Montant à miser", placeholder="max selon votre niveau")
            def __init__(self, bot, author):
                super().__init__(); self.bot, self.author = bot, author
                user_data = load_user(self.author.guild.id, self.author.id)
                max_bet = get_max_bet(user_data, 10_000_000)
                self.amount.placeholder = f"Max {format_y(max_bet)} Cols"
            async def on_submit(self, i: discord.Interaction):
                try: val = int(self.amount.value)
                except: return await i.response.send_message("❌ Nombre invalide", ephemeral=True)
                
                u_data = load_user(i.guild.id, self.author.id)
                max_bet = get_max_bet(u_data, 10_000_000)
                if val <= 0 or val > u_data["Cols"] or val > max_bet:
                    return await i.response.send_message(f"❌ Mise invalide (max {format_y(max_bet)} Cols selon votre niveau).", ephemeral=True)
                
                game = LanternFallView(self.author, self.bot, i.guild, val)
                await game.update_selection_view(i)

        embed = self.bot.config.get_formatted_embed(
            title=format_title("🏮 LANTERN FALL", ctx.author.id), 
            description=f"💳 Solde : **{format_y(data['Cols'])} Cols**\n\nPrêt à tenter votre chance ?",
            bot_user=self.bot.user,
            guild=ctx.guild,
            user=ctx.author,
            target_id=ctx.guild.id if ctx.guild else None
        )
        await ctx.send(embed=embed, view=Lobby(ctx.author, self.bot))

async def setup(bot): await bot.add_cog(LanternFallCog(bot))
