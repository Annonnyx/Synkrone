import discord
from discord.ext import commands
from discord import ui
import random
import asyncio
import os
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

# ===================== CONFIG MANAGER ========================
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

from cogs.casino.autres.achievements import add_xp, XP_PER_GAME_COMMAND
from cogs.casino.admin.adminlimit import apply_admin_gain_limit

# --- GESTION DES DONNÉES (Structure identique au Coinflip) ---
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

def check_daily_limit(guild_id: int, user_id: int) -> tuple[bool, str]:
    """Vérifie si l'utilisateur a atteint sa limite quotidienne de coffres"""
    user_data = load_user_data(guild_id, user_id)
    if 'mysteribox_limits' not in user_data:
        user_data['mysteribox_limits'] = {
            'daily_count': 0,
            'last_openings': [],
            'last_reset': datetime.now().strftime('%Y-%m-%d')
        }
        save_user_data(guild_id, user_id, user_data)
        return True, ""

    limits = user_data['mysteribox_limits']
    today = datetime.now().strftime('%Y-%m-%d')
    
    # Réinitialiser si c'est un nouveau jour
    if limits['last_reset'] != today:
        limits['daily_count'] = 0
        limits['last_openings'] = []
        limits['last_reset'] = today
        save_user_data(guild_id, user_id, user_data)
        return True, ""
    
    # Vérifier la limite de 3 coffres par jour
    if limits['daily_count'] >= 3:
        return False, f"❌ Limite quotidienne atteinte ! (3/3 coffres ouverts)"
    
    # Vérifier l'intervalle de 8 heures entre les ouvertures
    if limits['last_openings']:
        last_opening = datetime.fromisoformat(limits['last_openings'][-1])
        time_since_last = datetime.now() - last_opening
        
        if time_since_last < timedelta(hours=8):
            remaining_time = timedelta(hours=8) - time_since_last
            hours = int(remaining_time.total_seconds() // 3600)
            minutes = int((remaining_time.total_seconds() % 3600) // 60)
            return False, f"❌ Attendez {hours}h {minutes}min avant d'ouvrir un autre coffre !"
    
    return True, ""

def update_opening_count(guild_id: int, user_id: int):
    """Met à jour le compteur d'ouvertures de coffres"""
    user_data = load_user_data(guild_id, user_id)

    if 'mysteribox_limits' not in user_data:
        user_data['mysteribox_limits'] = {
            'daily_count': 0,
            'last_openings': [],
            'last_reset': datetime.now().strftime('%Y-%m-%d')
        }

    limits = user_data['mysteribox_limits']
    limits['daily_count'] += 1
    limits['last_openings'].append(datetime.now().isoformat())
    
    # Garder seulement les 3 dernières ouvertures
    if len(limits['last_openings']) > 3:
        limits['last_openings'] = limits['last_openings'][-3:]
    
    save_user_data(guild_id, user_id, user_data)

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


def format_title(title: str, user_id: int) -> str:
    if title.startswith(PREMIUM_EMOJI):
        return title
    premium_active, _ = get_vote_bonus_status(user_id)
    return f"{PREMIUM_EMOJI} {title}" if premium_active else title

# --- MODAL POUR LA MISE ---
class MysteriBoxModal(ui.Modal, title="📦 OUVERTURE DE COFFRE"):
    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        # Prix fixe de 200 000 Cols
        prix = 200000
        
        # Vérifier les limites
        can_open, message = check_daily_limit(interaction.guild.id, interaction.user.id)
        if not can_open:
            return await interaction.response.send_message(message, ephemeral=True)
        
        user_data = load_user_data(interaction.guild.id, interaction.user.id)
        
        if user_data["Cols"] < prix:
            return await interaction.response.send_message(f"❌ Solde insuffisant ! ({format_Cols(user_data['Cols'])} Cols)", ephemeral=True)

        self.parent_view.mise = prix
        await self.parent_view.process_opening(interaction)

# --- VUE PRINCIPALE ---
class MysteriBoxView(ui.View):
    def __init__(self, author, bot):
        super().__init__(timeout=60)
        self.author = author
        self.bot = bot
        self.mise = 0
        self.message = None

    @ui.button(label="Briser le sceau", style=discord.ButtonStyle.primary, emoji="📦")
    async def btn_open(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.author:
            return await interaction.response.send_message("❌ Ce coffre est scellé pour quelqu'un d'autre.", ephemeral=True)
        
        # Prix fixe de 200 000 Cols
        prix = 200000
        
        # Vérifier les limites
        can_open, message = check_daily_limit(interaction.guild.id, interaction.user.id)
        if not can_open:
            return await interaction.response.send_message(message, ephemeral=True)
        
        user_data = load_user_data(interaction.guild.id, interaction.user.id)
        
        if user_data["Cols"] < prix:
            return await interaction.response.send_message(f"❌ Solde insuffisant ! ({format_Cols(user_data['Cols'])} Cols)", ephemeral=True)

        self.mise = prix
        await self.process_opening(interaction)

    async def process_opening(self, interaction: discord.Interaction):
        # Désactivation du bouton pendant l'ouverture
        self.clear_items()
        await interaction.response.edit_message(content="⧗ *Le Grand Casino d'Aincrad examine votre mise...*", view=self)
        
        # Animation de suspense
        steps = ["🔮 *Les runes du coffre s'illuminent...*", "🔑 *Le mécanisme s'active...*", "✨ *Révélation du contenu...*"]
        for step in steps:
            embed_anim = self.bot.config.get_formatted_embed(
                title=format_title("📦 MYSTERI BOX", self.author.id),
                description=f"💰 Prix : **{format_Cols(self.mise)} Cols**\n\n{step}",
                bot_user=self.bot.user,
                guild=interaction.guild,
                user=interaction.user,
                target_id=interaction.guild.id if interaction.guild else None
            )
            await interaction.edit_original_response(content=None, embed=embed_anim)
            await asyncio.sleep(1.2)

        # Système de récompense avec plus de chances de perdre
        rand = random.random()
        
        # Charger les données utilisateur pour calculer les pertes en pourcentage
        user_data = load_user_data(interaction.guild.id, self.author.id)
        solde_total = user_data["Cols"]
        
        if rand < 0.15:  # 15% de chance de gagner entre 0 et 100 000
            gain = random.randint(0, 100000)
            result_type = "gain"
        elif rand < 0.25:  # 10% de chance de gagner entre 100 001 et 300 000
            gain = random.randint(100001, 300000)
            result_type = "gain"
        elif rand < 0.30:  # 5% de chance de gagner entre 300 001 et 500 000 (max)
            gain = random.randint(300001, 500000)
            result_type = "gain"
        elif rand < 0.35:  # 5% de chance de ne rien gagner
            gain = 0
            result_type = "neutre"
        else:  # 65% de chance de perdre (entre 1% et 20% du solde total)
            pourcentage_perte = random.uniform(0.01, 0.20)  # 1% à 20%
            perte = int(solde_total * pourcentage_perte)
            gain = -perte
            result_type = "perte"
        
        # Mettre à jour le compteur d'ouvertures
        update_opening_count(interaction.guild.id, self.author.id)
        
        # Recharger les données utilisateur (car elles ont pu être modifiées)
        user_data = load_user_data(interaction.guild.id, self.author.id)
        # On retire le prix et on ajoute le gain
        if gain > 0:
            gain = apply_admin_gain_limit(interaction.guild.id, "mysteribox", gain)
        user_data["Cols"] = user_data["Cols"] - self.mise + gain
        premium_active, _ = get_vote_bonus_status(self.author.id)
        user_data = add_xp(user_data, XP_PER_GAME_COMMAND, premium_active)
        save_user_data(interaction.guild.id, self.author.id, user_data)
        
        # Vérifier les succès pour MysteriBox
        from cogs.casino.autres.achievements import check_and_unlock
        check_and_unlock(interaction.guild.id, self.author.id, "yakuza_opened", user_data)

        # Résultat visuel
        if result_type == "gain":
            if gain > 0:
                premium_active, _ = get_vote_bonus_status(self.author.id)
                if premium_active:
                    gain *= 2
                title, color_status = "✨ BUTIN TROUVÉ", f"🎁 Vous avez gagné : `+{format_Cols(gain)} Cols`"
            else:
                title, color_status = "📦 COFFRE VIDE", "💰 Vous n'avez rien gagné."
        elif result_type == "perte":
            title, color_status = "🚨 MAÌTRE DU CASINO !", f"⚠️ Le casino vous a dépossédé de : `{format_Cols(abs(gain))} Cols`"
        else:
            title, color_status = "📦 COFFRE VIDE", "🤔 Vous n'avez rien gagné."

        embed_final = self.bot.config.get_formatted_embed(
            title=format_title(title, self.author.id),
            description=f"💰 Prix d'ouverture : **{format_Cols(self.mise)} Cols**\n\n{color_status}",
            bot_user=self.bot.user,
            guild=interaction.guild,
            user=interaction.user,
            target_id=interaction.guild.id if interaction.guild else None
        )
        embed_final.add_field(name="💳 Nouveau Solde", value=f"**{format_Cols(user_data['Cols'])} Cols**")
        
        # Ajout du bouton rejouer
        self.clear_items()
        retry_btn = ui.Button(label="Ouvrir un autre coffre", style=discord.ButtonStyle.primary, emoji="🔄")
        async def retry_callback(i):
            if i.user != self.author: 
                return await i.response.send_message("❌ Ce n'est pas votre session.", ephemeral=True)
            
            # Prix fixe de 200 000 Cols
            prix = 200000
            
            # Vérifier les limites
            can_open, message = check_daily_limit(i.guild.id, i.user.id)
            if not can_open:
                return await i.response.send_message(message, ephemeral=True)
            
            user_data = load_user_data(i.guild.id, i.user.id)
            
            if user_data["Cols"] < prix:
                return await i.response.send_message(f"❌ Solde insuffisant ! ({format_Cols(user_data['Cols'])} Cols)", ephemeral=True)

            self.mise = prix
            await self.process_opening(i)
        retry_btn.callback = retry_callback
        self.add_item(retry_btn)

        await interaction.edit_original_response(embed=embed_final, view=self)

# --- COG ---
class MysteriBoxSAO(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="mysteribox", description="Ouvrez un coffre mystérieux du Grand Casino d'Aincrad.")
    async def mysteribox(self, ctx: commands.Context):
        user_data = load_user_data(ctx.guild.id, ctx.author.id)
        # Afficher les informations de limites
        limits_info = ""
        if 'mysteribox_limits' in user_data:
            limits = user_data['mysteribox_limits']
            today = datetime.now().strftime('%Y-%m-%d')
            if limits['last_reset'] == today:
                limits_info = f"📊 **Aujourd'hui : {limits['daily_count']}/3 coffres ouverts\n"
                # Calculer le temps d'attente si nécessaire
                if limits['last_openings'] and limits['daily_count'] < 3:
                    last_opening = datetime.fromisoformat(limits['last_openings'][-1])
                    time_since_last = datetime.now() - last_opening
                    if time_since_last < timedelta(hours=8):
                        remaining_time = timedelta(hours=8) - time_since_last
                        hours = int(remaining_time.total_seconds() // 3600)
                        minutes = int((remaining_time.total_seconds() % 3600) // 60)
                        limits_info += f"⏰ Prochain coffre disponible dans : {hours}h {minutes}min\n\n"
                    else:
                        limits_info += "✅ Prochain coffre disponible immédiatement\n\n"
                elif limits['daily_count'] >= 3:
                    limits_info += "❌ Limite quotidienne atteinte\n\n"
                else:
                    limits_info += "✅ Prochain coffre disponible immédiatement\n\n"
        legend = (
            "🎁 **Gains possibles :**\n"
            "• 15% : 0 - 100 000 Cols\n"
            "• 10% : 100 001 - 300 000 Cols\n"
            "• 5% : 300 001 - 500 000 Cols\n"
            "• 5% : Rien du tout\n"
            "• 65% : Perte de 1% à 20% du solde total\n\n"
            f"💰 **Prix d'ouverture : 200 000 Cols**\n\n"
            f"{limits_info}"
            "⚠️ **Attention :** Les pertes sont calculées en pourcentage de votre solde total !"
        )
        view = MysteriBoxView(ctx.author, self.bot)
        embed = self.bot.config.get_formatted_embed(
            title=format_title("📦 MYSTERI BOX - Sword Art Online", ctx.author.id),
            description=legend,
            bot_user=self.bot.user,
            guild=ctx.guild,
            user=ctx.author,
            target_id=ctx.guild.id if ctx.guild else None
        )
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

async def setup(bot):
    await bot.add_cog(MysteriBoxSAO(bot))