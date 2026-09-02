import discord
from discord.ext import commands
import os
import json
import random
import datetime
import pytz
import asyncio
import time
from pathlib import Path

# ===================== CONFIG MANAGER ========================
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

from cogs.casino.autres.achievements import add_xp, XP_PER_GAME_COMMAND
from cogs.casino.admin.adminlimit import apply_admin_gain_limit, get_admin_hourly_limit

# --- CONFIGURATION DU RANDOM ---
MAX_USES_PER_HOUR = 3    # Nombre d'utilisations max par heure
COOLDOWN_HOURS = 1       # Fenêtre de réinitialisation (1 heure)

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
    if remaining > 0:
        return True, remaining
    return False, 0


def format_title(title: str, user_id: int) -> str:
    if title.startswith(PREMIUM_EMOJI):
        return title
    premium_active, _ = get_vote_bonus_status(user_id)
    return f"{PREMIUM_EMOJI} {title}" if premium_active else title

# --- VUE DES BOUTONS MYSTÈRES ---
class RandomMysteryView(discord.ui.View):
    def __init__(self, ctx, cog_instance):
        super().__init__(timeout=60.0)
        self.ctx = ctx
        self.cog = cog_instance

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ Ce coffre mystère ne vous appartient pas !", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            await self.message.edit(view=self)
        except:
            pass

    async def process_choice(self, interaction: discord.Interaction, button_name: str):
        # --- 1. SÉCURITÉ : VÉRIFICATION DES LIMITES AVANT DE JOUER ---
        guild_id = self.ctx.guild.id
        user_id = self.ctx.author.id
        user_data = load_user_data(guild_id, user_id)
        
        paris_tz = pytz.timezone('Europe/Paris')
        now = datetime.datetime.now(paris_tz)
        
        history = user_data.get("random_history", [])
        valid_history = []
        for time_str in history:
            try:
                launch_time = datetime.datetime.fromisoformat(time_str)
                if now - launch_time < datetime.timedelta(hours=COOLDOWN_HOURS):
                    valid_history.append(time_str)
            except:
                pass
                
        limit_value = get_admin_hourly_limit(guild_id, "chest", MAX_USES_PER_HOUR)
        if limit_value is not None and len(valid_history) >= limit_value:
            await interaction.response.send_message(f"❌ Vous avez déjà atteint la limite de {limit_value} utilisations pour cette heure.", ephemeral=True)
            return

        # --- 2. DÉSACTIVATION DES BOUTONS (PENDANT L'ANIMATION) ---
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)

        current_cols = user_data.get("Cols", 1000)

        # --- 3. CALCUL DU RÉSULTAT ---
        rewards_pool = [
            {"type": "win", "percent": 1, "status": "🎯 GAGNÉ !", "text": "📈 **Gain mineur de +1%** !"},
            {"type": "loss", "percent": -3, "status": "❌ PERDU...", "text": "📉 **Perte de -3%**... Le coffre était piégé !"},
            {"type": "win", "percent": 5, "status": "🔥 VICTOIRE ÉPIQUE !", "text": "💎 **Gain majeur de +5%** !"}
        ]
        
        chosen_reward = random.choice(rewards_pool)
        original_change = round(current_cols * (chosen_reward["percent"] / 100))
        premium_active, _ = get_vote_bonus_status(self.ctx.author.id)
        if chosen_reward["type"] == "win" and premium_active and original_change > 0:
            change_amount = original_change * 2
        else:
            change_amount = original_change
        new_cols = current_cols + change_amount
        
        # Sécurité pour ne pas avoir un solde négatif
        if new_cols < 0:
            new_cols = 0
            change_amount = -current_cols

        # Formatage du texte de la variation
        if change_amount >= 0:
            variation_text = f"💰 Gain : **+ {format_Cols(change_amount)} Cols**"
        else:
            variation_text = f"💸 Perte : **- {format_Cols(abs(change_amount))} Cols**"

        # --- 4. MISE À JOUR DES STATISTIQUES ET CALCUL DU COOLDOWN ---
        user_data["random_total_count"] = user_data.get("random_total_count", 0) + 1
        user_data["random_last_use"] = now.isoformat()
        
        valid_history.append(now.isoformat())
        user_data["random_history"] = valid_history
        user_data["random_uses_this_hour"] = len(valid_history)
        
        # Calcul de la petite phrase pour l'embed final
        limit_value = get_admin_hourly_limit(guild_id, "chest", MAX_USES_PER_HOUR)
        uses_left = float('inf') if limit_value is None else max(0, limit_value - len(valid_history))
        if uses_left > 0:
            s_pluriel = "s" if uses_left > 1 else ""
            cooldown_text = f"⏳ *Il vous reste **{uses_left} utilisation{s_pluriel}** pour cette heure.*\n*Sélectionnez à nouveau un coffre ci-dessous !*"
        else:
            oldest_launch = datetime.datetime.fromisoformat(valid_history[0])
            remaining = datetime.timedelta(hours=COOLDOWN_HOURS) - (now - oldest_launch)
            minutes, remainder = divmod(int(remaining.total_seconds()), 60)
            seconds = remainder
            time_str_fmt = f"{minutes}m et {seconds}s" if minutes > 0 else f"{seconds}s"
            cooldown_text = f"⏳ *Vous devez attendre **{time_str_fmt}** avant votre prochaine utilisation.*"

        # Sauvegarde du nouveau solde Cols et des stats
        if change_amount > 0:
            change_amount = apply_admin_gain_limit(guild_id, "chest", change_amount)
        user_data["Cols"] = new_cols
        premium_active, _ = get_vote_bonus_status(self.ctx.author.id)
        user_data = add_xp(user_data, XP_PER_GAME_COMMAND, premium_active)
        save_user_data(guild_id, user_id, user_data)

        # --- 5. ANIMATION DE CROCHETAGE ---
        animation_steps = [
            ("🎲 CROCHETAGE DU : " + button_name.upper(), "🛠️ *Vous insérez vos outils dans la serrure...*"),
            ("🎲 CROCHETAGE DU : " + button_name.upper(), "⚙️ *Clic... Clac... Les goupilles du coffre s'alignent...*"),
            (f"🗳️ {chosen_reward['status']} — {button_name.upper()}", 
             f"🔓 *Le verrou cède dans un grincement métallique !*\n\n"
             f"Le coffre s'ouvre enfin devant vos yeux, **{self.ctx.author.display_name}**.\n\n"
             f"{chosen_reward['text']}\n"
             f"{variation_text}\n\n"
             f"💳 **Nouveau solde :** `{format_Cols(new_cols)} Cols`\n\n"
             f"{cooldown_text}")
        ]

        for i, (step_title, step_desc) in enumerate(animation_steps):
            anim_embed = self.cog.bot.config.get_formatted_embed(
                title=format_title(step_title, self.ctx.author.id),
                description=step_desc,
                bot_user=self.cog.bot.user,
                guild=self.ctx.guild,
                user=self.ctx.author,
                target_id=self.ctx.guild.id if self.ctx.guild else None
            )
            
            if i < len(animation_steps) - 1:
                await self.message.edit(embed=anim_embed)
                await asyncio.sleep(1.2) # Temps de pause entre chaque étape de l'animation
            else:
                # Dernière étape de l'animation : on réactive les boutons si on a encore des essais
                if uses_left > 0:
                    for child in self.children:
                        child.disabled = False
                await self.message.edit(embed=anim_embed, view=self)

        # Si le joueur n'a plus d'essais, la vue arrête d'écouter
        if uses_left <= 0:
            self.stop()

    @discord.ui.button(label="Coffre d'Or", style=discord.ButtonStyle.primary, emoji="👑")
    async def button_one(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_choice(interaction, "Coffre d'Or")

    @discord.ui.button(label="Coffre d'Argent", style=discord.ButtonStyle.primary, emoji="💎")
    async def button_two(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_choice(interaction, "Coffre d'Argent")

    @discord.ui.button(label="Coffre de Bronze", style=discord.ButtonStyle.primary, emoji="🪙")
    async def button_three(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_choice(interaction, "Coffre de Bronze")


# --- COG RANDOM ---
class RandomSAO(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="chest", description="Ouvrez un coffre mystère.")
    async def chest_cmd(self, ctx: commands.Context):
        user_id = ctx.author.id
        guild_id = ctx.guild.id
        
        user_data = load_user_data(guild_id, user_id)
        
        paris_tz = pytz.timezone('Europe/Paris')
        now = datetime.datetime.now(paris_tz)
        
        history = user_data.get("random_history", [])
        
        # Filtrer l'historique pour le calcul du cooldown à l'entrée de la commande
        valid_history = []
        for time_str in history:
            try:
                launch_time = datetime.datetime.fromisoformat(time_str)
                if now - launch_time < datetime.timedelta(hours=COOLDOWN_HOURS):
                    valid_history.append(time_str)
            except:
                pass
        
        # Mise à jour des données de l'heure actuelle
        user_data["random_history"] = valid_history
        user_data["random_uses_this_hour"] = len(valid_history)
        save_user_data(guild_id, user_id, user_data)

        # Vérification de la limite de sécurité (3 utilisations par heure)
        if len(valid_history) >= MAX_USES_PER_HOUR:
            oldest_launch = datetime.datetime.fromisoformat(valid_history[0])
            remaining = datetime.timedelta(hours=COOLDOWN_HOURS) - (now - oldest_launch)
            
            minutes, remainder = divmod(int(remaining.total_seconds()), 60)
            seconds = remainder
            remaining_time = f"{minutes}m et {seconds}s" if minutes > 0 else f"{seconds}s"

            embed = self.bot.config.get_formatted_embed(
                title="⏳ OUTILS EMBROUILLÉS",
                description=(
                    f"Vos mains tremblent ! Vous avez déjà tenté de crocheter **3 coffres** cette heure-ci.\n\n"
                    f"Revenez dans **{remaining_time}** pour retrouver votre calme."
                ),
                bot_user=self.bot.user,
                guild=ctx.guild,
                user=ctx.author,
                target_id=ctx.guild.id if ctx.guild else None
            )
            return await ctx.send(embed=embed)

        # Affichage initial du choix des coffres
        embed = self.bot.config.get_formatted_embed(
            title=format_title("🎲 LES COFFRES MYSTÈRES D'AINCRAD", ctx.author.id),
            description=(
                f"Choisissez votre cible, **{ctx.author.display_name}** !\n"
                f"Chaque coffre possède un mécanisme unique. Serez-vous assez habile ?\n\n"
                f"✨ **Récompenses ou pièges possibles :**\n"
                f"•  `+1%` de votre solde total\n"
                f"•  `-3%` de votre solde total\n"
                f"•  `+5%` de votre solde total\n\n"
                f"*Sélectionnez un coffre ci-dessous pour lancer le crochetage.*"
            ),
            bot_user=self.bot.user,
            guild=ctx.guild,
            user=ctx.author,
            target_id=ctx.guild.id if ctx.guild else None
        )
        
        view = RandomMysteryView(ctx, self)
        view.message = await ctx.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(RandomSAO(bot))