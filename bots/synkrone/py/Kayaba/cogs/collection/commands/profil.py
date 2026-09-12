import discord
from discord.ext import commands
import math
import json
import os
import sys
from datetime import datetime, timedelta

# Configuration des chemins
BASE_DIR = os.path.dirname(__file__)
DATA_DEV_DIR = os.path.normpath(os.path.join(BASE_DIR, '..', 'data', 'dev'))
FAMILLE_DIR = os.path.join(DATA_DEV_DIR, 'famille')
USER_DATA_PATH = os.path.normpath(os.path.join(BASE_DIR, '..', 'data', 'interserver'))

# Importer config_manager
try:
    from cogs.developpeur.commands.embed_type.utils import config_manager
    HAS_CONFIG_MANAGER = True
except ImportError:
    config_manager = None
    HAS_CONFIG_MANAGER = False

# Chargement des emojis avec fallback intégré
def load_emojis():
    """Charge les emojis personnalisés avec fallback sur emojis standards"""
    emoji_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'emoji.json')
    
    fallback_emojis = {
        "cartes": "🎴", "col": "💰", "star": "⭐", "trophy": "🏆",
        "sword": "⚔️", "check": "✅", "handshake": "🤝", "cross": "❌",
        "gem": "💎", "chart": "📊", "user": "👤", "home": "🏠",
        "left_arrow": "⬅️", "right_arrow": "➡️", "plus": "➕",
        "info": "ℹ️", "clock": "⏰", "shield": "🛡️", "crown": "👑"
    }
    
    try:
        with open(emoji_path, 'r', encoding='utf-8') as f:
            custom_emojis = json.load(f)
            
        final_emojis = {}
        for key, fallback_value in fallback_emojis.items():
            final_emojis[key] = custom_emojis.get(key, fallback_value)
            
        return final_emojis
        
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback_emojis

emojis = load_emojis()

# --- Fonctions utilitaires ---
def format_number(n):
    return f"{n:,}".replace(",", " ")

def get_user_data(user_id):
    user_file = os.path.join(USER_DATA_PATH, f"{user_id}.json")
    if os.path.exists(user_file):
        try:
            with open(user_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return None
    return None

def get_card_data(card_id):
    if not os.path.exists(FAMILLE_DIR): return None
    for famille in os.listdir(FAMILLE_DIR):
        famille_path = os.path.join(FAMILLE_DIR, famille)
        if os.path.isdir(famille_path):
            personnages_file = os.path.join(famille_path, 'personnages.json')
            if os.path.exists(personnages_file):
                try:
                    with open(personnages_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        for perso in data.get('personnages', []):
                            if perso.get('id') == card_id:
                                return perso
                except:
                    continue
    return None

def calculate_collection_value(collection):
    total_value = 0
    for card_id, count in collection.items():
        if count > 0:
            card_data = get_card_data(card_id)
            if card_data:
                total_value += card_data.get('valeur', 0) * count
    return total_value

def get_total_possible_cards():
    total = 0
    if os.path.exists(FAMILLE_DIR):
        for famille in os.listdir(FAMILLE_DIR):
            famille_path = os.path.join(FAMILLE_DIR, famille)
            if os.path.isdir(famille_path):
                personnages_file = os.path.join(famille_path, 'personnages.json')
                if os.path.exists(personnages_file):
                    try:
                        with open(personnages_file, 'r', encoding='utf-8') as f:
                            total += len(json.load(f).get('personnages', []))
                    except:
                        continue
    return total

def get_all_cards_by_family():
    families = {}
    if os.path.exists(FAMILLE_DIR):
        for famille_name in os.listdir(FAMILLE_DIR):
            famille_path = os.path.join(FAMILLE_DIR, famille_name)
            if os.path.isdir(famille_path):
                personnages_file = os.path.join(famille_path, 'personnages.json')
                if os.path.exists(personnages_file):
                    try:
                        with open(personnages_file, 'r', encoding='utf-8') as f:
                            families[famille_name] = json.load(f).get('personnages', [])
                    except:
                        continue
    return families

def get_xp_for_level(level):
    try:
        path = os.path.join(os.path.dirname(__file__), '..', 'data', 'level_system.json')
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f).get('levels', {}).get(str(level), 0)
    except:
        return 0

def calculate_level_from_xp(xp):
    try:
        path = os.path.join(os.path.dirname(__file__), '..', 'data', 'level_system.json')
        with open(path, 'r', encoding='utf-8') as f:
            levels = json.load(f).get('levels', {})
            
        current_level = 1
        for level, required_xp in sorted(levels.items(), key=lambda x: int(x[0])):
            if xp >= required_xp:
                current_level = int(level)
            else:
                break
        return current_level
    except:
        return 1

def get_xp_for_next_level(current_xp):
    current_level = calculate_level_from_xp(current_xp)
    next_level_xp = get_xp_for_level(current_level + 1)
    if next_level_xp == 0:
        return None
    return next_level_xp - current_xp


# --- VUES ---

class ProfileView(discord.ui.View):
    def __init__(self, bot, target_user, viewer_user):
        super().__init__(timeout=180)
        self.bot = bot
        self.target_user = target_user
        self.viewer_user = viewer_user
        self.user_data = get_user_data(target_user.id)
        self.all_families = get_all_cards_by_family()
        
    @discord.ui.select(
        placeholder="📋 Choisissez une section",
        options=[
            discord.SelectOption(label="Profil principal", value="main", emoji="🏠"),
            discord.SelectOption(label="Succès", value="success", emoji="✅"),
            discord.SelectOption(label="Cooldowns", value="cooldowns", emoji="⏰"),
            discord.SelectOption(label="Cartes", value="cards", emoji="🎴"),
            discord.SelectOption(label="PvP", value="pvp", emoji="⚔️"),
            discord.SelectOption(label="Classements", value="rankings", emoji="🏆")
        ],
        row=0
    )
    async def callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        # Sécurité : Seul celui qui a tapé la commande peut naviguer
        if interaction.user.id != self.viewer_user.id:
            return await interaction.response.send_message("❌ Vous ne pouvez pas interagir avec ce menu.", ephemeral=True)

        selected = select.values[0]
        
        # Redirection vers la bonne vue selon le choix
        if selected == "main":
            view = ProfileView(self.bot, self.target_user, self.viewer_user)
            await interaction.response.edit_message(embed=view.create_main_embed(), view=view)
        elif selected == "cooldowns":
            view = CooldownsView(self.bot, self.target_user, self.viewer_user, self.user_data)
            await interaction.response.edit_message(embed=view.create_main_embed(), view=view)
        elif selected == "cards":
            view = CardsMenuView(self.bot, self.target_user, self.viewer_user, self.all_families, self.user_data)
            await interaction.response.edit_message(embed=view.create_main_embed(), view=view)
        elif selected == "pvp":
            view = PvPMenuView(self.bot, self.target_user, self.viewer_user, self.user_data)
            await interaction.response.edit_message(embed=view.create_main_embed(), view=view)
        elif selected == "rankings":
            view = RankingsMenuView(self.bot, self.target_user, self.viewer_user)
            await interaction.response.edit_message(embed=view.create_main_embed(), view=view)
        elif selected == "success":
            view = SuccessView(self.bot, self.target_user, self.viewer_user, self.user_data)
            await interaction.response.edit_message(embed=view.create_main_embed(), view=view)

    def create_main_embed(self):
        """Crée l'embed principal du profil"""
        if not self.user_data:
            embed = discord.Embed(
                title=f"{emojis['user']} Profil de {self.target_user.display_name}",
                description=f"**{emojis['cross']} Ce joueur n'a pas encore créé son profil**",
                color=discord.Color.red()
            )
            embed.set_thumbnail(url=self.target_user.display_avatar.url)
            return embed

        current_xp = self.user_data.get('xp', 0)
        current_level = calculate_level_from_xp(current_xp)
        is_premium = self.user_data.get('premium', False)
        premium_text = f"{emojis['crown']} **PREMIUM**" if is_premium else ""
        
        embed = discord.Embed(
            title=f"{emojis['user']} Profil de {self.target_user.display_name} {premium_text}",
            description=f"**Niveau {current_level}** • **{current_xp:,}** XP",
            color=discord.Color.gold() if is_premium else discord.Color.blue()
        )
        embed.set_thumbnail(url=self.target_user.display_avatar.url)
        
        # --- Progression ---
        xp_for_next = get_xp_for_next_level(current_xp)
        progression_info = f"📊 **Niveau actuel:** {current_level}\n⭐ **XP total:** {format_number(current_xp)}\n"
        if xp_for_next is not None:
            progression_info += f"🎯 **XP prochain niveau:** {format_number(xp_for_next)}"
        else:
            progression_info += "🏆 **Niveau maximum atteint!**"
            
        embed.add_field(name="📈 **Progression**", value=progression_info, inline=False)
        
        # --- Stats principales ---
        collection = self.user_data.get('collection', {})
        unique_cards = len([c for c, count in collection.items() if count > 0])
        col_amount = self.user_data.get('col', 0)
        collection_value = calculate_collection_value(collection)
        
        main_stats = (
            f"{emojis['cartes']} **Cartes uniques:** {unique_cards} / {get_total_possible_cards()}\n"
            f"**Solde Col:** {format_number(col_amount)} {emojis['col']}\n"
            f"**Valeur collection:** {format_number(collection_value)} {emojis['col']}\n"
        )
        embed.add_field(name="📊 **Statistiques Principales**", value=main_stats, inline=False)
        
        embed.set_footer(text=f"Mis à jour {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        return embed

class CooldownsView(discord.ui.View):
    def __init__(self, bot, target_user, viewer_user, user_data):
        super().__init__(timeout=180)
        self.bot = bot
        self.target_user = target_user
        self.viewer_user = viewer_user
        self.user_data = user_data or {}
        
    def create_main_embed(self):
        embed = discord.Embed(
            title=f"⏰ Cooldowns de {self.target_user.display_name}",
            description="Gérez et surveillez vos temps de récupération.",
            color=discord.Color.orange()
        )
        
        collect_end = self.user_data.get('collect_cooldown_end')
        daily_last = self.user_data.get('last_daily')
        
        # Logique simplifiée pour l'affichage (à adapter avec tes fonctions temporelles si besoin)
        embed.add_field(name="⚡ **Collecte**", value=f"Fin : {collect_end or 'Disponible'}", inline=False)
        embed.add_field(name="🎁 **Quotidienne**", value=f"Dernière : {daily_last or 'Disponible'}", inline=False)
        return embed
    
    @discord.ui.button(label="Retour Profil", emoji="🏠", style=discord.ButtonStyle.secondary, row=0)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.viewer_user.id: return
        view = ProfileView(self.bot, self.target_user, self.viewer_user)
        await interaction.response.edit_message(embed=view.create_main_embed(), view=view)

class CardsMenuView(discord.ui.View):
    def __init__(self, bot, target_user, viewer_user, all_families, user_data):
        super().__init__(timeout=180)
        self.bot = bot
        self.target_user = target_user
        self.viewer_user = viewer_user
        self.all_families = all_families
        self.user_data = user_data or {}
        self.current_page = 0
        self.cards_per_page = 8
        
    def create_main_embed(self):
        collection = self.user_data.get('collection', {})
        unique_cards = len([c for c, count in collection.items() if count > 0])
        
        embed = discord.Embed(
            title=f"🎴 Collection de {self.target_user.display_name}",
            description=f"**{unique_cards}** cartes uniques possédées.",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Ce menu sera enrichi pour naviguer entre les familles.")
        return embed
    
    # RECONSTRUCTION DE LA FONCTION QUI ÉTAIT COUPÉE
    def create_family_embed(self, family_name):
        family_cards = self.all_families.get(family_name, [])
        collection = self.user_data.get('collection', {})
        
        embed = discord.Embed(title=f"📁 {family_name}", color=discord.Color.purple())
        
        start_idx = self.current_page * self.cards_per_page
        end_idx = start_idx + self.cards_per_page
        page_cards = family_cards[start_idx:end_idx]
        
        for card in page_cards:
            card_id = card.get('id', '')
            owned = collection.get(card_id, 0)
            rarity = card.get('rarete', 'Commun')
            rarity_emoji = {"Légendaire": "🟡", "Epique": "🟣", "Rare": "🔵", "Commun": "🟢"}.get(rarity, "🟢")
            value = card.get('valeur', 0)
            
            status = f"✅ **{owned}x** possédé(s)" if owned > 0 else "❌ **0x** non possédé"
            
            card_text = f"{rarity_emoji} **{card.get('nom', 'Inconnu')}**\nStatut: {status} | Valeur: {value}"
            embed.add_field(name="\u200b", value=card_text, inline=False)
            
        return embed
    
    @discord.ui.button(label="Retour Profil", emoji="🏠", style=discord.ButtonStyle.secondary, row=0)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.viewer_user.id: return
        view = ProfileView(self.bot, self.target_user, self.viewer_user)
        await interaction.response.edit_message(embed=view.create_main_embed(), view=view)

class PvPMenuView(discord.ui.View):
    def __init__(self, bot, target_user, viewer_user, user_data):
        super().__init__(timeout=180)
        self.bot = bot
        self.target_user = target_user
        self.viewer_user = viewer_user
        self.user_data = user_data or {}
        
    def create_main_embed(self):
        embed = discord.Embed(
            title=f"⚔️ Centre PvP de {self.target_user.display_name}",
            color=discord.Color.red()
        )
        
        pvp_stats = self.user_data.get('pvp_stats', {})
        if not pvp_stats:
            embed.description = "❌ **Aucune statistique PvP enregistrée**\nParticipez à des combats pour débloquer ces fonctionnalités !"
            return embed
            
        elo = pvp_stats.get('elo', 1000)
        wins = pvp_stats.get('wins', 0)
        total_fights = pvp_stats.get('total_fights', 0)
        
        embed.add_field(name="Stats", value=f"ELO: {elo}\nVictoires: {wins}/{total_fights}", inline=False)
        return embed

    @discord.ui.button(label="Retour Profil", emoji="🏠", style=discord.ButtonStyle.secondary, row=0)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.viewer_user.id: return
        view = ProfileView(self.bot, self.target_user, self.viewer_user)
        await interaction.response.edit_message(embed=view.create_main_embed(), view=view)

class RankingsMenuView(discord.ui.View):
    def __init__(self, bot, target_user, viewer_user):
        super().__init__(timeout=180)
        self.bot = bot
        self.target_user = target_user
        self.viewer_user = viewer_user
        
    def create_main_embed(self):
        embed = discord.Embed(
            title="🏆 Classements Globaux",
            description="Découvrez les meilleurs joueurs.",
            color=discord.Color.gold()
        )
        embed.add_field(name="Catégories", value="🎴 Collection\n💰 Patrimoine\n⚔️ PvP", inline=False)
        return embed
    
    @discord.ui.button(label="Retour Profil", emoji="🏠", style=discord.ButtonStyle.secondary, row=0)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.viewer_user.id: return
        view = ProfileView(self.bot, self.target_user, self.viewer_user)
        await interaction.response.edit_message(embed=view.create_main_embed(), view=view)

class SuccessView(discord.ui.View):
    def __init__(self, bot, target_user, viewer_user, user_data):
        super().__init__(timeout=180)
        self.bot = bot
        self.target_user = target_user
        self.viewer_user = viewer_user
        self.user_data = user_data or {}
        
    def create_main_embed(self):
        embed = discord.Embed(
            title=f"✅ Succès de {self.target_user.display_name}",
            description="Vos accomplissements récents apparaîtront ici.",
            color=discord.Color.green()
        )
        return embed

    @discord.ui.button(label="Retour Profil", emoji="🏠", style=discord.ButtonStyle.secondary, row=0)
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.viewer_user.id: return
        view = ProfileView(self.bot, self.target_user, self.viewer_user)
        await interaction.response.edit_message(embed=view.create_main_embed(), view=view)

class Profile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="profil", aliases=["profile"])
    async def profil(self, ctx: commands.Context, target: discord.Member = None):
        """Affiche le profil d'un utilisateur avec menus détaillés"""
        if target is None:
            target = ctx.author
        
        view = ProfileView(self.bot, target, ctx.author)
        await ctx.send(embed=view.create_main_embed(), view=view)

async def setup(bot):
    await bot.add_cog(Profile(bot))