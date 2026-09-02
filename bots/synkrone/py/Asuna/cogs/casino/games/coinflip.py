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

# --- CONSTANTES ET LIMITES ---
MAX_MISE = 10_000_000
MAX_PARTIES_HEURE = 20
PROBA_GAIN = 0.40  # 40% de chance de gagner
PROBA_PERTE = 0.60  # 60% de chance de perdre
MULTIPLICATEUR_GAIN = 1.7  # Le joueur gagne x1.2 sa mise

# --- FONCTIONS DE GESTION DES LIMITES ---
def check_limites_heure(guild_id: int, user_id: int):
    data = load_user_data(guild_id, user_id)
    
    if "coinflip_stats" not in data:
        data["coinflip_stats"] = {
            "parties_heure": [],
            "derniere_reset": datetime.now().isoformat()
        }
    
    stats = data["coinflip_stats"]
    maintenant = datetime.now()
    
    # Reset toutes les heures
    dernier_reset = datetime.fromisoformat(stats["derniere_reset"])
    if maintenant - dernier_reset >= timedelta(hours=1):
        stats["parties_heure"] = []
        stats["derniere_reset"] = maintenant.isoformat()
    
    # Nettoyer les anciennes parties (garder que l'heure actuelle)
    stats["parties_heure"] = [
        p for p in stats["parties_heure"] 
        if datetime.fromisoformat(p) > maintenant - timedelta(hours=1)
    ]
    
    parties_jouees = len(stats["parties_heure"])
    default_limit = get_hourly_limit(data)
    limite = get_admin_hourly_limit(guild_id, "coinflip", default_limit)
    parties_restantes = float('inf') if limite is None else limite - parties_jouees
    peut_jouer = True if limite is None else parties_restantes > 0
    
    # Calcul du temps restant avant reset
    temps_restant = timedelta(hours=1) - (maintenant - dernier_reset)
    temps_restant_minutes = max(0, int(temps_restant.total_seconds() / 60))
    
    return {
        "peut_jouer": peut_jouer,
        "parties_jouees": parties_jouees,
        "parties_restantes": parties_restantes,
        "temps_restant_minutes": temps_restant_minutes,
        "stats": stats,
        "limit": limite,
    }

def ajouter_partie_heure(stats: dict):
    stats["parties_heure"].append(datetime.now().isoformat())

# --- MODAL POUR ENTRER LA MISE ---
class CoinflipModal(ui.Modal, title="💰 MISE DE Cols"):
    mise_input = ui.TextInput(
        label="Montant à miser", 
        placeholder="max selon votre niveau", 
        min_length=1, 
        required=True
    )

    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view
        max_bet = get_max_bet(load_user_data(parent_view.author.guild.id, parent_view.author.id), MAX_MISE)
        self.mise_input.placeholder = f"Max {format_Cols(max_bet)} Cols"

    async def on_submit(self, interaction: discord.Interaction):
        if not self.mise_input.value.isdigit():
            return await interaction.response.send_message("❌ Erreur : Veuillez entrer un nombre entier.", ephemeral=True)
        
        mise = int(self.mise_input.value)
        user_data = load_user_data(interaction.guild.id, interaction.user.id)
        limites = check_limites_heure(interaction.guild.id, interaction.user.id)
        
        if mise <= 0 or user_data["Cols"] < mise:
            return await interaction.response.send_message(f"❌ Solde insuffisant ! (Vous possédez {format_Cols(user_data['Cols'])} Cols)", ephemeral=True)
        
        max_bet = get_max_bet(user_data, MAX_MISE)
        if mise > max_bet:
            return await interaction.response.send_message(f"❌ Mise maximale de **{format_Cols(max_bet)} Cols** dépassée !", ephemeral=True)
        
        if not limites["peut_jouer"]:
            limit_display = "∞" if limites["limit"] is None else limites["limit"]
            return await interaction.response.send_message(
                f"❌ Limite horaire atteinte !\n"
                f"🎮 Parties jouées : **{limites['parties_jouees']}/{limit_display}**\n"
                f"⏰ Prochain reset dans **{limites['temps_restant_minutes']}** minutes",
                ephemeral=True
            )
        
        # Ajouter la partie aux statistiques
        ajouter_partie_heure(limites["stats"])
        user_data["coinflip_stats"] = limites["stats"]
        user_data = add_xp(user_data, XP_PER_GAME_COMMAND, False)
        save_user_data(interaction.guild.id, interaction.user.id, user_data)
        from cogs.casino.autres.achievements import check_and_unlock
        check_and_unlock(interaction.guild.id, interaction.user.id, "coinflip", user_data)

        self.parent_view.mise = mise
        await self.parent_view.show_confirmation(interaction)

# --- VUE PRINCIPALE ---
class CoinflipView(ui.View):
    def __init__(self, author, bot):
        super().__init__(timeout=60)
        self.author = author
        self.bot = bot
        self.mise = 0
        self.message = None
        self.game_finished = False 
        self.update_view_items("initial")

    async def on_timeout(self):
        if not self.message: return
        try:
            if not self.game_finished:
                await self.message.edit(content="💤 *Vous avez été trop long..*", embed=None, view=None)
            else:
                await self.message.edit(view=None)
        except:
            pass

    def update_view_items(self, step):
        self.clear_items()
        if step == "initial":
            self.add_item(self.btn_initial_mise)
        elif step == "confirmation":
            self.add_item(self.confirm_bet)
            self.add_item(self.modify_bet)
        elif step == "selection":
            self.add_item(self.btn_pile)
            self.add_item(self.btn_face)
            self.add_item(self.btn_random)
        elif step == "resultat":
            self.add_item(self.btn_changer_mise)
            if self.mise > 0:
                btn_rejouer = ui.Button(
                    label=f"Rejouer ({format_Cols(self.mise)} Cols)", 
                    style=discord.ButtonStyle.success, 
                    emoji="💰"
                )
                btn_rejouer.callback = self.btn_rejouer_meme_mise
                self.add_item(btn_rejouer)

    @ui.button(label="Placer une mise", style=discord.ButtonStyle.secondary, emoji="💰")
    async def btn_initial_mise(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.author:
            return await interaction.response.send_message("❌ Ce n'est pas votre session.", ephemeral=True)
        await interaction.response.send_modal(CoinflipModal(self))

    @ui.button(label="Confirmer", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm_bet(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.author:
            return await interaction.response.send_message("❌ Ce n'est pas votre session.", ephemeral=True)
        await self.show_selection(interaction)

    @ui.button(label="Modifier", style=discord.ButtonStyle.primary, emoji="✏️")
    async def modify_bet(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.author:
            return await interaction.response.send_message("❌ Ce n'est pas votre session.", ephemeral=True)
        await interaction.response.send_modal(CoinflipModal(self))

    async def show_selection(self, interaction: discord.Interaction):
        """Affiche l'étape du choix Pile ou Face"""
        self.game_finished = False
        self.update_view_items("selection")
        premium_active, bonus_remaining = get_vote_bonus_status(self.author.id)
        title = f"{PREMIUM_EMOJI} 🎯 CHOIX DU CAMP" if premium_active else "🎯 CHOIX DU CAMP"
        description = f"💰 Mise enregistrée : **{format_Cols(self.mise)} Cols**\n\nSur quel côté pariez-vous ?"

        embed = self.bot.config.get_formatted_embed(
            title=title,
            description=description,
            bot_user=self.bot.user,
            guild=interaction.guild,
            user=interaction.user,
            target_id=interaction.guild.id if interaction.guild else None
        )
        if interaction.response.is_done():
            await interaction.edit_original_response(content=None, embed=embed, view=self)
        else:
            await interaction.response.edit_message(content=None, embed=embed, view=self)

    async def process_game(self, interaction: discord.Interaction, choix: str):
        if interaction.user != self.author:
            return await interaction.response.send_message("❌ Ce n'est pas votre session.", ephemeral=True)
        
        if choix == "random":
            choix = random.choice(["pile", "face"])

        await interaction.response.edit_message(content="⌛ *Le jeton tourne...*", embed=None, view=None)
        await asyncio.sleep(2)

        resultat_choisi = random.random() < PROBA_GAIN 
        
        if resultat_choisi:
            resultat = choix
            win = True
        else:
            resultat = "face" if choix == "pile" else "pile"
            win = False
        
        user_data = load_user_data(interaction.guild.id, self.author.id)
        
        # Ajouter la mise aux statistiques totales
        from cogs.casino.autres.achievements import increment_counter
        user_data = increment_counter(user_data, "Cols_spent", self.mise)
        
        premium_active, bonus_remaining = get_vote_bonus_status(self.author.id)

        if win:
            gain_total = int(self.mise * MULTIPLICATEUR_GAIN)
            if premium_active:
                gain_total *= 2
            profit = gain_total - self.mise
            profit = apply_admin_gain_limit(interaction.guild.id, "coinflip", profit)
            user_data["Cols"] += profit
            title = "✨ VICTOIRE ÉCLATANTE ✨"
            msg = f"Le jeton s'immobilise sur **{resultat.upper()}** !\n\n🎁 Vous remportez **{format_Cols(self.mise + profit)} Cols** (gain net : +{format_Cols(profit)} Cols)."
        else:
            user_data["Cols"] -= self.mise
            title = "💀 DÉFAITE"
            msg = f"Le jeton s'immobilise sur **{resultat.upper()}**...\n\n💸 Vous avez perdu votre mise de **{format_Cols(self.mise)} Cols**."

        if premium_active:
            title = f"{PREMIUM_EMOJI} {title}"

        save_user_data(interaction.guild.id, self.author.id, user_data)
        from cogs.casino.autres.achievements import check_and_unlock
        check_and_unlock(interaction.guild.id, self.author.id, "coinflip", user_data)
        
        self.game_finished = True 
        self.update_view_items("resultat")

        embed = self.bot.config.get_formatted_embed(
            title=title,
            description=msg,
            bot_user=self.bot.user,
            guild=interaction.guild,
            user=interaction.user,
            target_id=interaction.guild.id if interaction.guild else None
        )
        limites = check_limites_heure(interaction.guild.id, self.author.id)
        limit_display = "∞" if limites['limit'] is None else limites['limit']
        embed.add_field(name="💳 Nouveau Solde", value=f"**{format_Cols(user_data['Cols'])} Cols**")
        embed.add_field(name="🎮 Parties restantes", value=f"**{limites['parties_restantes']}/{limit_display}**", inline=False)
        
        await interaction.edit_original_response(content=None, embed=embed, view=self)

    @ui.button(label="Pile", style=discord.ButtonStyle.secondary, emoji="🪙")
    async def btn_pile(self, interaction: discord.Interaction, button: ui.Button):
        await self.process_game(interaction, "pile")

    @ui.button(label="Face", style=discord.ButtonStyle.secondary, emoji="👤")
    async def btn_face(self, interaction: discord.Interaction, button: ui.Button):
        await self.process_game(interaction, "face")

    @ui.button(label="Aléatoire", style=discord.ButtonStyle.secondary, emoji="🎲")
    async def btn_random(self, interaction: discord.Interaction, button: ui.Button):
        await self.process_game(interaction, "random")

    @ui.button(label="Changer mise", style=discord.ButtonStyle.secondary, emoji="🔄")
    async def btn_changer_mise(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user != self.author:
            return await interaction.response.send_message("❌ Ce n'est pas votre session.", ephemeral=True)
        await interaction.response.send_modal(CoinflipModal(self))

    async def btn_rejouer_meme_mise(self, interaction: discord.Interaction):
        """Logique du bouton Rejouer"""
        if interaction.user != self.author:
            return await interaction.response.send_message("❌ Ce n'est pas votre session.", ephemeral=True)
        
        user_data = load_user_data(interaction.guild.id, self.author.id)
        limites = check_limites_heure(interaction.guild.id, self.author.id)
        
        if user_data["Cols"] < self.mise: 
            return await interaction.response.send_message("❌ Fonds insuffisants.", ephemeral=True)
        
        if not limites["peut_jouer"]: 
            return await interaction.response.send_message("❌ Limite horaire atteinte !", ephemeral=True)
        
        # Consommer une partie
        ajouter_partie_heure(limites["stats"])
        user_data["coinflip_stats"] = limites["stats"]
        save_user_data(interaction.guild.id, self.author.id, user_data)
        from cogs.casino.autres.achievements import check_and_unlock
        check_and_unlock(interaction.guild.id, self.author.id, "coinflip", user_data)
        
        # Relancer l'étape de sélection
        await self.show_selection(interaction)

    async def show_confirmation(self, interaction):
        limites = check_limites_heure(interaction.guild.id, self.author.id)
        self.update_view_items("confirmation") # On passe à l'étape confirmation
        premium_active, bonus_remaining = get_vote_bonus_status(self.author.id)
        
        desc = f"Souhaitez-vous engager **{format_Cols(self.mise)} Cols** dans ce lancer ?\n\n"
        desc += f"🎮 Parties restantes : **{limites['parties_restantes']}/{limites['limit']}**\n"
        desc += "*Cliquez sur Confirmer pour continuer ou Modifier pour changer le montant.*"
        
        title = f"{PREMIUM_EMOJI} 🛡️ CONFIRMATION DU PARI" if premium_active else "🛡️ CONFIRMATION DU PARI"
        embed = self.bot.config.get_formatted_embed(
            title=title,
            description=desc,
            bot_user=self.bot.user,
            guild=interaction.guild,
            user=interaction.user,
            target_id=interaction.guild.id if interaction.guild else None
        )
        await interaction.response.edit_message(embed=embed, view=self)

# --- COG ---
class CoinflipMiyazaki(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="coinflip", description="Tentez de doubler vos gains au jeu de la pièce.")
    async def coinflip(self, ctx: commands.Context):
        user_data = load_user_data(ctx.guild.id, ctx.author.id)
        limites = check_limites_heure(ctx.guild.id, ctx.author.id)
        premium_active, bonus_remaining = get_vote_bonus_status(ctx.author.id)
        
        # Si limite atteinte, afficher directement le message d'erreur
        limit_display = "∞" if limites["limit"] is None else limites["limit"]
        if not limites["peut_jouer"]:
            embed = discord.Embed(
                title="❌ Limite horaire atteinte",
                description=f"🎮 Parties jouées : **{limites['parties_jouees']}/{limit_display}**\n"
                           f"⏰ Prochain reset dans **{limites['temps_restant_minutes']}** minutes\n\n"
                           f"💰 Solde actuel : **{format_Cols(user_data['Cols'])} Cols**",
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed, ephemeral=True)
        
        title = f"{PREMIUM_EMOJI} 🪙 JEU DU COINFLIP" if premium_active else "🪙 JEU DU COINFLIP"
        limit_display = "∞" if limites["limit"] is None else limites["limit"]
        embed = self.bot.config.get_formatted_embed(
            title=title,
            description=(
                f"Bienvenue au casino, **{ctx.author.display_name}** !\n\n"
                f"💰 Votre capital actuel : **{format_Cols(user_data['Cols'])} Cols**\n"
                f"🎮 Parties restantes : **{limites['parties_restantes']}/{limit_display}**\n\n"
                "Prêt à tenter votre chance ? Cliquez sur le bouton ci-dessous pour définir votre mise."
            ),
            bot_user=self.bot.user
        )
        view = CoinflipView(ctx.author, self.bot)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

async def setup(bot):
    await bot.add_cog(CoinflipMiyazaki(bot))