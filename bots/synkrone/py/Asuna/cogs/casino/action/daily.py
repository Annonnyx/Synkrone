import discord
from discord.ext import commands
import os
import json
import random
import datetime
import pytz

# ===================== CONFIG MANAGER ========================
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# --- CONFIGURATION DU DAILY ---
MIN_REWARD = 5000       # Valeur minimale donnée
MAX_REWARD = 10000      # Valeur maximale donnée
COOLDOWN_HOURS = 24     # Intervalle entre deux daily (en heures)

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

# --- COG DAILY ---
class DailySAO(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="daily", description="Récupérez votre bonus quotidien.")
    async def daily(self, ctx: commands.Context):
        user_id = ctx.author.id
        guild_id = ctx.guild.id
        
        # Chargement des données (donne 1000 si nouveau)
        user_data = load_user_data(guild_id, user_id)
        
        # Gestion du temps (Paris)
        paris_tz = pytz.timezone('Europe/Paris')
        now = datetime.datetime.now(paris_tz)
        
        last_daily_str = user_data.get("last_daily")
        can_claim = True
        remaining_time = ""

        if last_daily_str:
            last_daily = datetime.datetime.fromisoformat(last_daily_str)
            delta = now - last_daily
            
            if delta < datetime.timedelta(hours=COOLDOWN_HOURS):
                can_claim = False
                remaining = datetime.timedelta(hours=COOLDOWN_HOURS) - delta
                hours, remainder = divmod(int(remaining.total_seconds()), 3600)
                minutes, _ = divmod(remainder, 60)
                remaining_time = f"{hours}h et {minutes}m"

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
        
        # Mise à jour des données
        user_data["Cols"] = user_data.get("Cols", 1000) + reward
        user_data["last_daily"] = now.isoformat()
        
        # Stats pour les succès
        from cogs.casino.autres.achievements import increment_counter, check_and_unlock
        user_data = increment_counter(user_data, "daily_count")
        # Gérer le streak
        yesterday = now - datetime.timedelta(days=1)
        last_daily_str = user_data.get("last_daily_before_streak", "")
        if last_daily_str:
            try:
                last_daily = datetime.datetime.fromisoformat(last_daily_str)
                if (now.date() - last_daily.date()).days == 1:
                    user_data = increment_counter(user_data, "daily_streak")
                else:
                    user_data["stats"]["daily_streak"] = 1  # Reset streak
            except:
                user_data["stats"]["daily_streak"] = 1
        else:
            user_data = increment_counter(user_data, "daily_streak")
        user_data["last_daily_before_streak"] = now.isoformat()
        
        # Vérifier les succès
        check_and_unlock(guild_id, user_id, "daily_count", user_data)
        check_and_unlock(guild_id, user_id, "daily_streak", user_data)
        
        save_user_data(guild_id, user_id, user_data)

        # Embed de Succès
        embed = self.bot.config.get_formatted_embed(
            title="🎁 BONUS QUOTIDIEN — CASINO D'AINCRAD",
            description=(
                f"Bienvenue, **{ctx.author.display_name}** !\n"
                f"Le Grand Casino d'Aincrad vous remet votre allocation journalière.\n\n"
                f"💰 Gain : **+ {format_Cols(reward)} Cols**\n"
                f"💳 Nouveau solde : **{format_Cols(user_data['Cols'])} Cols**"
            ),
            bot_user=self.bot.user,
            guild=ctx.guild,
            user=ctx.author,
            target_id=ctx.guild.id if ctx.guild else None
        )
        
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(DailySAO(bot))