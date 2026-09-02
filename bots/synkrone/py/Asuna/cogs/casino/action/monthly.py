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

# --- CONFIGURATION DU MONTHLY ---
MIN_REWARD = 150000     # Valeur minimale donnée par mois
MAX_REWARD = 300000     # Valeur maximale donnée par mois
COOLDOWN_HOURS = 720    # Intervalle entre deux monthly (30 jours * 24 heures)

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
    return {"Cols": 1000} # Solde de départ si le fichier n'existe pas

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

# --- COG MONTHLY ---
class MonthlySAO(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="monthly", description="Récupérez votre bonus mensuel.")
    async def monthly(self, ctx: commands.Context):
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

        # Chargement des données
        user_data = load_user_data(guild_id, user_id)
        
        # Gestion du temps (Paris)
        paris_tz = pytz.timezone('Europe/Paris')
        now = datetime.datetime.now(paris_tz)
        
        last_monthly_str = user_data.get("last_monthly")
        can_claim = True
        remaining_time = ""

        if last_monthly_str:
            last_monthly = datetime.datetime.fromisoformat(last_monthly_str)
            delta = now - last_monthly
            
            if delta < datetime.timedelta(hours=COOLDOWN_HOURS):
                can_claim = False
                remaining = datetime.timedelta(hours=COOLDOWN_HOURS) - delta
                days = remaining.days
                hours, remainder = divmod(remaining.seconds, 3600)
                minutes, _ = divmod(remainder, 60)
                
                # Formatage du temps restant en Jours, Heures, Minutes
                if days > 0:
                    remaining_time = f"{days}j, {hours}h et {minutes}m"
                else:
                    remaining_time = f"{hours}h et {minutes}m"

        if not can_claim:
            # Embed de Cooldown
            embed = self.bot.config.get_formatted_embed(
                title="⏳ UN PEU DE PATIENCE, GUERRIER !",
                description=(
                    f"Le coffre mensuel du Grand Casino d'Aincrad est encore verrouillé pour vous.\n\n"
                    f"Revenez dans **{remaining_time}** pour réclamer jusqu'à **{format_Cols(MAX_REWARD)} Cols** !"
                ),
                bot_user=self.bot.user,
                guild=ctx.guild,
                user=ctx.author,
                target_id=ctx.guild.id if ctx.guild else None
            )
            return await ctx.send(embed=embed)

        # Calcul de la récompense
        reward = random.randint(MIN_REWARD, MAX_REWARD)
        
        # Mise à jour des données
        user_data["Cols"] = user_data.get("Cols", 1000) + reward
        user_data["last_monthly"] = now.isoformat()
        
        # Stats pour les succès
        from cogs.casino.autres.achievements import increment_counter, check_and_unlock
        user_data = increment_counter(user_data, "monthly_count")
        
        # Vérifier les succès associés au monthly
        check_and_unlock(guild_id, user_id, "monthly_count", user_data)
        
        save_user_data(guild_id, user_id, user_data)

        # Embed de Succès
        embed = self.bot.config.get_formatted_embed(
            title="💎 PACK MENSUEL — COFFRE D'AINCRAD",
            description=(
                f"Félicitations, **{ctx.author.display_name}** !\n"
                f"Votre fidélité ce mois-ci est récompensée par la haute direction du Casino.\n\n"
                f"💰 Gain Mensuel : **+ {format_Cols(reward)} Cols**\n"
                f"💳 Nouveau solde : **{format_Cols(user_data['Cols'])} Cols**"
            ),
            bot_user=self.bot.user,
            guild=ctx.guild,
            user=ctx.author,
            target_id=ctx.guild.id if ctx.guild else None
        )
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(MonthlySAO(bot))