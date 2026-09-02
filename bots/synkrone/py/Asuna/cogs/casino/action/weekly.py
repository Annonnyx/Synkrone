import discord
from discord.ext import commands
import os
import json
import random
import datetime
import pytz
import time
from pathlib import Path

# ===================== CONFIG MANAGER ========================
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# --- CONFIGURATION DU WEEKLY ---
MIN_REWARD = 50000       # Valeur minimale donnée (plus grosse que daily)
MAX_REWARD = 100000      # Valeur maximale donnée (plus grosse que daily)
COOLDOWN_DAYS = 7        # Intervalle entre deux weekly (en jours)
HONNEUR_CHANCE = 0.05    # 5% de chance de gagner un honneur

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
            return json.load(f)
    return {"Cols": 1000, "Honneurs": 0} # Solde de départ si le fichier n'existe pas

def save_user_data(guild_id: int, user_id: int, data: dict):
    path = get_user_file_path(guild_id, user_id)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

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
    return (remaining > 0, remaining if remaining > 0 else 0)

# --- COG WEEKLY ---
class WeeklySAO(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="weekly", description="Récupérez votre bonus hebdomadaire.")
    async def weekly(self, ctx: commands.Context):
        user_id = ctx.author.id
        guild_id = ctx.guild.id
        premium_active, _ = get_vote_bonus_status(user_id)
        if not premium_active:
            embed = self.bot.config.get_formatted_embed(
                title="🔒 ACCÈS PREMIUM REQUIS",
                description=(
                    "Cette commande est réservée aux membres premium.\n"
                    "Votez via `/vote` pour activer votre bonus et débloquer hourly, weekly et monthly."
                ),
                bot_user=self.bot.user,
                guild=ctx.guild,
                user=ctx.author,
                target_id=ctx.guild.id if ctx.guild else None
            )
            return await ctx.send(embed=embed)

        # Chargement des données (donne 1000 si nouveau)
        user_data = load_user_data(guild_id, user_id)
        if "Honneurs" not in user_data:
            user_data["Honneurs"] = 0
        
        # Gestion du temps (Paris)
        paris_tz = pytz.timezone('Europe/Paris')
        now = datetime.datetime.now(paris_tz)
        
        last_weekly_str = user_data.get("last_weekly")
        can_claim = True
        remaining_time = ""

        if last_weekly_str:
            last_weekly = datetime.datetime.fromisoformat(last_weekly_str)
            delta = now - last_weekly
            
            if delta < datetime.timedelta(days=COOLDOWN_DAYS):
                can_claim = False
                remaining = datetime.timedelta(days=COOLDOWN_DAYS) - delta
                days, remainder = divmod(int(remaining.total_seconds()), 86400)
                hours, remainder = divmod(remainder, 3600)
                minutes, _ = divmod(remainder, 60)
                remaining_time = f"{days}j {hours}h {minutes}m"

        if not can_claim:
            # Embed de Cooldown (Utilise la couleur du manager)
            embed = self.bot.config.get_formatted_embed(
                title="⏳ PAS SI VITE, JOUEUR !",
                description=(
                    f"Le Grand Casino d'Aincrad n'est pas encore prêt à vous récompenser.\n\n"
                    f"Revenez dans **{remaining_time}** pour tenter d'obtenir jusqu'à **{format_Cols(MAX_REWARD)} Cols** !"
                ),
                bot_user=self.bot.user,
                guild=ctx.guild,
                user=ctx.author,
                target_id=ctx.guild.id if ctx.guild else None
            )
            return await ctx.send(embed=embed)

        # Calcul de la récompense
        reward = random.randint(MIN_REWARD, MAX_REWARD)
        honneur_gagne = False
        if random.random() < HONNEUR_CHANCE:
            user_data["Honneurs"] += 1
            honneur_gagne = True
        
        # Mise à jour des données
        user_data["Cols"] = user_data.get("Cols", 1000) + reward
        user_data["last_weekly"] = now.isoformat()
        save_user_data(guild_id, user_id, user_data)

        # Embed de Succès
        description = (
            f"Bienvenue, **{ctx.author.display_name}** !\n"
            f"Le Grand Casino d'Aincrad vous remet votre allocation hebdomadaire.\n\n"
            f"💰 Gain : **+ {format_Cols(reward)} Cols**\n"
            f"💳 Nouveau solde : **{format_Cols(user_data['Cols'])} Cols**"
        )
        if honneur_gagne:
            description += f"\n🏅 Félicitations ! Vous remportez également **1 Honneur** ! (Total : {user_data['Honneurs']})"

        embed = self.bot.config.get_formatted_embed(
            title="🎁 BONUS HEBDOMADAIRE — CASINO D'AINCRAD",
            description=description,
            bot_user=self.bot.user,
            guild=ctx.guild,
            user=ctx.author,
            target_id=ctx.guild.id if ctx.guild else None
        )
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(WeeklySAO(bot))
