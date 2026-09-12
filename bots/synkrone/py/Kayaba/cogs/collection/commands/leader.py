import discord
from discord.ext import commands
from discord import app_commands
import math
import json
import os
import traceback

# ==============================================================================
# --------------------------- IMPORTATION UTILS --------------------------------
# ==============================================================================
try:
    from cogs.developpeur.commands.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# Configuration des chemins
BASE_DIR = os.path.dirname(__file__)
DATA_DEV_DIR = os.path.normpath(os.path.join(BASE_DIR, '..', 'data', 'dev'))
FAMILLE_DIR = os.path.join(DATA_DEV_DIR, 'famille')
USER_DATA_PATH = os.path.normpath(os.path.join(BASE_DIR, '..', 'data', 'interserver'))

# Chargement des emojis avec fallback intégré
def load_emojis():
    """Charge les emojis personnalisés avec fallback sur emojis standards"""
    emoji_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'emoji.json')
    
    # Emojis standards de fallback
    fallback_emojis = {
        "cartes": "🎴",
        "kronos": "💰", 
        "star": "⭐",
        "trophy": "🏆",
        "sword": "⚔️",
        "check": "✅",
        "handshake": "🤝",
        "cross": "❌",
        "gem": "💎",
        "chart": "📊",
        "user": "👤",
        "home": "🏠",
        "left_arrow": "⬅️",
        "right_arrow": "➡️",
        "plus": "➕",
        "info": "ℹ️"
    }
    
    try:
        with open(emoji_path, 'r', encoding='utf-8') as f:
            custom_emojis = json.load(f)
            
        # Fusionner avec fallback : garder les emojis personnalisés, utiliser fallback pour les manquants
        final_emojis = {}
        for key, fallback_value in fallback_emojis.items():
            final_emojis[key] = custom_emojis.get(key, fallback_value)
            
        return final_emojis
        
    except (FileNotFoundError, json.JSONDecodeError):
        # Si le fichier n'existe pas ou est invalide, utiliser uniquement les fallbacks
        return fallback_emojis

def format_number(n):
    """Formate un nombre avec des espaces comme séparateurs de milliers"""
    return f"{n:,}".replace(",", " ")

class LeaderboardView(discord.ui.View):
    def __init__(self, bot, initial_data="Collection", ctx=None):
        super().__init__(timeout=300)  # 5 minutes d'interaction
        self.bot = bot
        self.current_type = initial_data
        self.current_page = 0
        self.items_per_page = 50
        self.emojis = load_emojis()
        self.ctx = ctx  # Stocker le contexte pour le config_manager
    
    @discord.ui.select(
        placeholder="🏆 Choisissez un classement...",
        options=[
            discord.SelectOption(label="Collection", value="Collection", description="Classement des collections de cartes", emoji="<:cartes:1480707463794921473>"),
            discord.SelectOption(label="Patrimoine", value="Patrimoine", description="Classement des richesses", emoji="<:col:1482462727468486738>"),
            discord.SelectOption(label="Niveaux", value="Niveaux", description="Classement des niveaux XP", emoji="<:xp:1483151442020667594>"),
            discord.SelectOption(label="PvP", value="PvP", description="Classement des combats PvP", emoji="<:pvp:1480717291007246396>")
        ],
        row=0
    )
    async def leaderboard_select(self, interaction: discord.Interaction, select: discord.ui.Select):
        """Gère la sélection du type de classement"""
        self.current_type = select.values[0]
        self.current_page = 0
        await self.update_leaderboard(interaction)
        
    def get_user_collection_stats(self):
        """Charge les statistiques de collection de tous les utilisateurs"""
        stats = []
        
        if not os.path.exists(USER_DATA_PATH):
            return stats
        
        # Calculer le total possible de cartes depuis les fichiers personnages
        total_possible_cards = 0
        if os.path.exists(FAMILLE_DIR):
            for famille in os.listdir(FAMILLE_DIR):
                famille_path = os.path.join(FAMILLE_DIR, famille)
                if os.path.isdir(famille_path):
                    personnages_file = os.path.join(famille_path, 'personnages.json')
                    if os.path.exists(personnages_file):
                        try:
                            with open(personnages_file, 'r', encoding='utf-8') as f:
                                personnages_data = json.load(f)
                                total_possible_cards += len(personnages_data.get('personnages', []))
                        except:
                            continue
        
        for filename in os.listdir(USER_DATA_PATH):
            # Ignorer les fichiers qui ne sont pas des fichiers utilisateurs (comme shop.json)
            if not (filename.endswith('.json') and filename.replace('.json', '').isdigit()):
                continue
                
            try:
                with open(os.path.join(USER_DATA_PATH, filename), 'r', encoding='utf-8') as f:
                    user_data = json.load(f)
                
                user_id = int(filename.replace('.json', ''))
                collection = user_data.get('collection', {})
                
                # Compter les cartes uniques et totales
                unique_cards = len([card_id for card_id, count in collection.items() if count > 0])
                
                # Récupérer le nom d'utilisateur
                user_name = self.bot.get_user(user_id).display_name if self.bot.get_user(user_id) else f"User_{user_id}"
                
                stats.append({
                    'user': user_name,
                    'user_id': user_id,
                    'owned': unique_cards,
                    'total': total_possible_cards,
                    'timestamp': user_data.get('created_at', '')  # Pour déterminer qui a atteint la valeur en premier
                })
                
            except Exception as e:
                print(f"[leader.py] Erreur chargement utilisateur {filename}: {e}")
                continue
        
        # Trier par nombre de cartes uniques, puis par timestamp pour les égalités
        stats.sort(key=lambda x: (-x['owned'], x['timestamp']))
        return stats
    
    def get_user_money_stats(self):
        """Charge les statistiques de richesse de tous les utilisateurs"""
        stats = []
        
        if not os.path.exists(USER_DATA_PATH):
            return stats
        
        for filename in os.listdir(USER_DATA_PATH):
            # Ignorer les fichiers qui ne sont pas des fichiers utilisateurs
            if not (filename.endswith('.json') and filename.replace('.json', '').isdigit()):
                continue
                
            try:
                with open(os.path.join(USER_DATA_PATH, filename), 'r', encoding='utf-8') as f:
                    user_data = json.load(f)
                
                user_id = int(filename.replace('.json', ''))
                money = user_data.get('col', 0)
                
                # Récupérer le nom d'utilisateur
                user_name = self.bot.get_user(user_id).display_name if self.bot.get_user(user_id) else f"User_{user_id}"
                
                stats.append({
                    'user': user_name,
                    'user_id': user_id,
                    'money': money,
                    'timestamp': user_data.get('created_at', '')  # Pour déterminer qui a atteint la valeur en premier
                })
                
            except Exception as e:
                print(f"[leader.py] Erreur chargement argent {filename}: {e}")
                continue
        
        # Trier par richesse, puis par timestamp pour les égalités
        stats.sort(key=lambda x: (-x['money'], x['timestamp']))
        return stats
    
    def get_user_level_stats(self):
        """Charge les statistiques de niveaux XP de tous les utilisateurs"""
        stats = []
        
        if not os.path.exists(USER_DATA_PATH):
            return stats
        
        # Charger le système de niveaux
        level_system_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'level_system.json')
        level_data = {}
        try:
            with open(level_system_path, 'r', encoding='utf-8') as f:
                level_data = json.load(f)
        except:
            pass
        
        def calculate_level_from_xp(xp):
            """Calcule le niveau à partir de l'XP"""
            levels = level_data.get('levels', {})
            user_level = 1
            for level_str, required_xp in levels.items():
                if xp >= required_xp:
                    user_level = int(level_str)
                else:
                    break
            return user_level
        
        for filename in os.listdir(USER_DATA_PATH):
            # Ignorer les fichiers qui ne sont pas des fichiers utilisateurs
            if not (filename.endswith('.json') and filename.replace('.json', '').isdigit()):
                continue
                
            try:
                with open(os.path.join(USER_DATA_PATH, filename), 'r', encoding='utf-8') as f:
                    user_data = json.load(f)
                
                user_id = int(filename.replace('.json', ''))
                xp = user_data.get('xp', 0)
                level = calculate_level_from_xp(xp)
                
                # Récupérer le nom d'utilisateur
                user_name = self.bot.get_user(user_id).display_name if self.bot.get_user(user_id) else f"User_{user_id}"
                
                stats.append({
                    'user': user_name,
                    'user_id': user_id,
                    'level': level,
                    'xp': xp,
                    'timestamp': user_data.get('created_at', '')  # Pour déterminer qui a atteint le niveau en premier
                })
                
            except Exception as e:
                print(f"[leader.py] Erreur chargement niveau {filename}: {e}")
                continue
        
        # Trier par niveau, puis par XP, puis par timestamp pour les égalités
        stats.sort(key=lambda x: (-x['level'], -x['xp'], x['timestamp']))
        return stats
    
    def get_user_pvp_stats(self):
        """Charge les statistiques PvP de tous les utilisateurs"""
        stats = []
        
        if not os.path.exists(USER_DATA_PATH):
            return stats
        
        for filename in os.listdir(USER_DATA_PATH):
            # Ignorer les fichiers qui ne sont pas des fichiers utilisateurs
            if not (filename.endswith('.json') and filename.replace('.json', '').isdigit()):
                continue
                
            try:
                with open(os.path.join(USER_DATA_PATH, filename), 'r', encoding='utf-8') as f:
                    user_data = json.load(f)
                
                user_id = int(filename.replace('.json', ''))
                pvp_stats = user_data.get('pvp_stats', {})
                
                elo = pvp_stats.get('elo', 1000)
                total_fights = pvp_stats.get('total_fights', 0)
                wins = pvp_stats.get('wins', 0)
                draws = pvp_stats.get('draws', 0)
                losses = pvp_stats.get('losses', 0)
                
                # Récupérer le nom d'utilisateur
                user_name = self.bot.get_user(user_id).display_name if self.bot.get_user(user_id) else f"User_{user_id}"
                
                if total_fights > 0:  # N'inclure que les joueurs avec au moins 1 combat
                    stats.append({
                        'user': user_name,
                        'user_id': user_id,
                        'elo': elo,
                        'total_fights': total_fights,
                        'win': wins,
                        'draw': draws,
                        'losses': losses,
                        'timestamp': user_data.get('created_at', '')  # Pour déterminer qui a atteint l'ELO en premier
                    })
                
            except Exception as e:
                print(f"[leader.py] Erreur chargement PvP {filename}: {e}")
                continue
        
        # Trier par ELO, puis par timestamp pour les égalités
        stats.sort(key=lambda x: (-x['elo'], x['timestamp']))
        return stats
        
    async def update_leaderboard(self, interaction: discord.Interaction, ctx=None):
        """Met à jour le leaderboard selon le type actuel"""
        if self.current_type == "Collection":
            data = self.get_user_collection_stats()
        elif self.current_type == "Patrimoine":
            data = self.get_user_money_stats()
        elif self.current_type == "Niveaux":
            data = self.get_user_level_stats()
        else:  # PvP
            data = self.get_user_pvp_stats()
        
        if not data:
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="📊 Aucune donnée",
                    description=f"Aucune donnée disponible pour le classement {self.current_type}.",
                    color=discord.Color.red()
                ),
                view=self
            )
            return
        
        self.max_pages = math.ceil(len(data) / self.items_per_page) if data else 1
        
        if self.current_page >= self.max_pages:
            self.current_page = 0
        
        embed = self.create_leaderboard_embed(data)
        self.update_button_states()  # Mettre à jour l'état des boutons
        await interaction.response.edit_message(embed=embed, view=self)
    
    def create_leaderboard_embed(self, data):
        """Crée un embed élégant pour le leaderboard en utilisant config_manager"""
        start = self.current_page * self.items_per_page
        end = start + self.items_per_page
        current_items = data[start:end]
        
        # Calculer max_pages
        self.max_pages = math.ceil(len(data) / self.items_per_page) if data else 1
        
        # Icônes selon le type (utilisant les emojis personnalisés)
        icons = {
            "Collection": self.emojis.get('cartes', '📚'),
            "Patrimoine": self.emojis.get('kronos', '💰'),
            "Niveaux": self.emojis.get('xp', '<:xp:1483151442020667594>'),
            "PvP": self.emojis.get('sword', '⚔️')
        }
        icon = icons.get(self.current_type, "📊")
        
        # Trouver le classement de l'utilisateur
        user_rank_text = ""
        if self.ctx and hasattr(self.ctx, 'author'):
            user_id = self.ctx.author.id
            user_rank = None
            user_value = None
            
            for i, item in enumerate(data, start=1):
                if item.get('user_id') == user_id:
                    user_rank = i
                    if self.current_type == "Collection":
                        percentage = (item['owned'] / item['total'] * 100) if item['total'] > 0 else 0
                        if percentage == int(percentage):
                            percentage_str = f"{int(percentage)}%"
                        else:
                            percentage_str = f"{percentage:.1f}%"
                        user_value = f"`{item['owned']} / {item['total']}` {self.emojis.get('cartes', '🎴')} *{percentage_str}*"
                    elif self.current_type == "Patrimoine":
                        user_value = f"`{format_number(item['money'])}` {self.emojis.get('kronos', '💰')}"
                    elif self.current_type == "Niveaux":
                        user_value = f"**Niv. {item['level']}** - `{format_number(item['xp'])}` {self.emojis.get('xp', '<:xp:1483151442020667594>')}"
                    else:  # PvP
                        win_rate = (item['win'] / item['total_fights'] * 100) if item['total_fights'] > 0 else 0
                        win_rate_str = f"{int(win_rate)}%" if win_rate == int(win_rate) else f"{win_rate:.1f}%"
                        user_value = f"ELO {format_number(item['elo'])} ({win_rate_str})"
                    break
            
            if user_rank:
                # Médailles pour le top 3
                medal = ""
                if user_rank == 1:
                    medal = "🥇"
                elif user_rank == 2:
                    medal = "🥈"
                elif user_rank == 3:
                    medal = "🥉"
                else:
                    medal = f"#{user_rank}"
                
                user_rank_text = f"**Vous êtes** {medal} avec {user_value}\n\n"
            else:
                user_rank_text = f"**Vous n'êtes pas classé** dans cette catégorie\n\n"
        
        # Créer une seule ligne par utilisateur selon le type
        leaderboard_text = ""
        previous_value = None
        current_rank = 0
        
        for i, item in enumerate(current_items, start=start + 1):
            if self.current_type == "Collection":
                percentage = (item['owned'] / item['total'] * 100) if item['total'] > 0 else 0
                # Formater le pourcentage sans décimales si c'est un entier
                if percentage == int(percentage):
                    percentage_str = f"{int(percentage)}%"
                else:
                    percentage_str = f"{percentage:.1f}%"
                
                # Gérer les égalités pour les rangs
                current_value = item['owned']
                if previous_value is None or current_value != previous_value:
                    current_rank = i
                previous_value = current_value
                
                # Médailles pour le top 3
                medal = ""
                if current_rank == 1:
                    medal = "🥇"
                elif current_rank == 2:
                    medal = "🥈"
                elif current_rank == 3:
                    medal = "🥉"
                else:
                    medal = f"#{current_rank}"
                
                # Utiliser les emojis personnalisés
                cartes_emoji = self.emojis.get('cartes', '🎴')
                
                leaderboard_text += f"{medal} {item['user']} - `{item['owned']} / {item['total']}` {cartes_emoji} *{percentage_str}*\n"
                
            elif self.current_type == "Patrimoine":
                # Gérer les égalités pour les rangs
                current_value = item['money']
                if previous_value is None or current_value != previous_value:
                    current_rank = i
                previous_value = current_value
                
                # Médailles pour le top 3
                medal = ""
                if current_rank == 1:
                    medal = "🥇"
                elif current_rank == 2:
                    medal = "🥈"
                elif current_rank == 3:
                    medal = "🥉"
                else:
                    medal = f"#{current_rank}"
                
                # Utiliser l'emoji personnalisé kronos après la valeur
                kronos_emoji = self.emojis.get('kronos', '💰')
                
                leaderboard_text += f"{medal} {item['user']} - `{format_number(item['money'])}` {kronos_emoji}\n"
                
            elif self.current_type == "Niveaux":
                # Gérer les égalités pour les rangs (d'abord par niveau, puis par XP)
                current_value = (item['level'], item['xp'])
                if previous_value is None or current_value != previous_value:
                    current_rank = i
                previous_value = current_value
                
                # Médailles pour le top 3
                medal = ""
                if current_rank == 1:
                    medal = "🥇"
                elif current_rank == 2:
                    medal = "🥈"
                elif current_rank == 3:
                    medal = "🥉"
                else:
                    medal = f"#{current_rank}"
                
                # Utiliser les emojis personnalisés
                xp_emoji = self.emojis.get('xp', '<:xp:1483151442020667594>')
                
                leaderboard_text += f"{medal} {item['user']} - **Niv. {item['level']}** - `{format_number(item['xp'])}` {xp_emoji}\n"
                
            else:  # PvP
                win_rate = (item['win'] / item['total_fights'] * 100) if item['total_fights'] > 0 else 0
                # Formater le pourcentage sans décimales si c'est un entier
                if win_rate == int(win_rate):
                    win_rate_str = f"{int(win_rate)}%"
                else:
                    win_rate_str = f"{win_rate:.1f}%"
                
                # Gérer les égalités pour les rangs
                current_value = item['elo']
                if previous_value is None or current_value != previous_value:
                    current_rank = i
                previous_value = current_value
                
                # Médailles pour le top 3
                medal = ""
                if current_rank == 1:
                    medal = "🥇"
                elif current_rank == 2:
                    medal = "🥈"
                elif current_rank == 3:
                    medal = "🥉"
                else:
                    medal = f"#{current_rank}"
                
                # Utiliser les emojis personnalisés
                trophy_emoji = self.emojis.get('trophy', '🏆')
                sword_emoji = self.emojis.get('sword', '⚔️')
                
                leaderboard_text += f"{medal} {item['user']} - {trophy_emoji} ELO {format_number(item['elo'])} ({sword_emoji} {item['total_fights']} combats • {win_rate_str})\n"
        
        # Utiliser config_manager pour créer l'embed
        if config_manager:
            try:
                embed = config_manager.get_formatted_embed(
                    guild=self.ctx.guild if self.ctx and hasattr(self.ctx, 'guild') else None,  # Utiliser le serveur si disponible
                    user=self.ctx.author if self.ctx and hasattr(self.ctx, 'author') else None,  # Utiliser l'utilisateur de la commande
                    bot=self.bot,
                    title=f"{icon} Classement {self.current_type}",
                    description=f"{user_rank_text}**Top {len(data)} joueurs** • Page {self.current_page + 1}/{self.max_pages}\n\n{leaderboard_text}",
                    target_id=self.ctx.guild.id if self.ctx and hasattr(self.ctx, 'guild') else None  # Utiliser l'ID du serveur
                )
                # Ajouter le thumbnail du premier utilisateur du classement
                if current_items and len(current_items) > 0:
                    first_user_id = current_items[0].get('user_id')
                    if first_user_id:
                        first_user = self.bot.get_user(first_user_id)
                        if first_user and first_user.avatar:
                            embed.set_thumbnail(url=first_user.avatar.url)
                        elif first_user:
                            # Si l'utilisateur n'a pas d'avatar personnalisé, utiliser l'avatar par défaut
                            embed.set_thumbnail(url=first_user.default_avatar.url)
            except Exception as e:
                print(f"[leader.py] Erreur config_manager: {e}")
                # Fallback si config_manager échoue
                embed = discord.Embed(
                    title=f"{icon} Classement {self.current_type}",
                    description=f"{user_rank_text}**Top {len(data)} joueurs** • Page {self.current_page + 1}/{self.max_pages}\n\n{leaderboard_text}",
                    color=discord.Color.purple() if self.current_type == "Collection" else 
                          discord.Color.gold() if self.current_type == "Patrimoine" else
                          discord.Color.green() if self.current_type == "Niveaux" else
                          discord.Color.red()  # PvP
                )
                # Ajouter le thumbnail du premier utilisateur du classement
                if current_items and len(current_items) > 0:
                    first_user_id = current_items[0].get('user_id')
                    if first_user_id:
                        first_user = self.bot.get_user(first_user_id)
                        if first_user and first_user.avatar:
                            embed.set_thumbnail(url=first_user.avatar.url)
                        elif first_user:
                            # Si l'utilisateur n'a pas d'avatar personnalisé, utiliser l'avatar par défaut
                            embed.set_thumbnail(url=first_user.default_avatar.url)
        else:
            # Fallback complet si config_manager n'est pas disponible
            embed = discord.Embed(
                title=f"{icon} Classement {self.current_type}",
                description=f"{user_rank_text}**Top {len(data)} joueurs** • Page {self.current_page + 1}/{self.max_pages}\n\n{leaderboard_text}",
                color=discord.Color.purple() if self.current_type == "Collection" else 
                          discord.Color.gold() if self.current_type == "Patrimoine" else
                          discord.Color.green() if self.current_type == "Niveaux" else
                          discord.Color.red()  # PvP
            )
            # Ajouter le thumbnail du premier utilisateur du classement
            if current_items and len(current_items) > 0:
                first_user_id = current_items[0].get('user_id')
                if first_user_id:
                    first_user = self.bot.get_user(first_user_id)
                    if first_user and first_user.avatar:
                        embed.set_thumbnail(url=first_user.avatar.url)
                    elif first_user:
                        # Si l'utilisateur n'a pas d'avatar personnalisé, utiliser l'avatar par défaut
                        embed.set_thumbnail(url=first_user.default_avatar.url)
        
        return embed
    
    @discord.ui.button(label="Précédent", emoji="<:gauche:1480718835010240613>", style=discord.ButtonStyle.gray, row=1)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_leaderboard(interaction)
        else:
            await interaction.response.send_message("Vous êtes déjà sur la première page !", ephemeral=True)
    
    @discord.ui.button(label="Suivant", emoji="<:droite:1480718813816164403>", style=discord.ButtonStyle.gray, row=1)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Calculer max_pages dynamiquement
        if self.current_type == "Collection":
            data = self.get_user_collection_stats()
        elif self.current_type == "Patrimoine":
            data = self.get_user_money_stats()
        elif self.current_type == "Niveaux":
            data = self.get_user_level_stats()
        else:  # PvP
            data = self.get_user_pvp_stats()
        
        self.max_pages = math.ceil(len(data) / self.items_per_page) if data else 1
        
        if self.current_page < self.max_pages - 1:
            self.current_page += 1
            await self.update_leaderboard(interaction)
        else:
            await interaction.response.send_message("Vous êtes déjà sur la dernière page !", ephemeral=True)
    
    def update_button_states(self):
        """Met à jour l'état des boutons de pagination"""
        # Calculer max_pages dynamiquement
        if self.current_type == "Collection":
            data = self.get_user_collection_stats()
        elif self.current_type == "Patrimoine":
            data = self.get_user_money_stats()
        elif self.current_type == "Niveaux":
            data = self.get_user_level_stats()
        else:  # PvP
            data = self.get_user_pvp_stats()
        
        self.max_pages = math.ceil(len(data) / self.items_per_page) if data else 1
        
        # Désactiver/activer le bouton précédent
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.label == "Précédent":
                    child.disabled = (self.current_page == 0 or self.max_pages <= 1)
                elif child.label == "Suivant":
                    child.disabled = (self.current_page >= self.max_pages - 1 or self.max_pages <= 1)

class Leader(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="leader", description="Affiche les classements")
    async def leader(self, ctx: commands.Context):
        """Affiche les classements avec une interface élégante et directe"""
        print(f"[leader.py] Commande leader exécutée par {ctx.author.id}")
        
        try:
            # 1. ACCUSÉ DE RÉCEPTION
            await ctx.defer(ephemeral=False)

            # 2. Créer la vue élégante avec le classement collection par défaut
            view = LeaderboardView(self.bot, initial_data="Collection", ctx=ctx)
            
            # 3. Charger les données initiales
            data = view.get_user_collection_stats()
            print(f"[leader.py] Données de collection chargées: {len(data)} utilisateurs")
            
            if not data:
                error_msg = "📊 Aucune donnée de collection disponible pour le moment !"
                if ctx.interaction:
                    await ctx.interaction.followup.send(error_msg)
                else:
                    await ctx.send(error_msg, reference=ctx.message)
                return
            
            # 4. Créer l'embed avec config_manager
            embed = view.create_leaderboard_embed(data)
            view.update_button_states()  # Mettre à jour l'état des boutons
            
            # 5. Envoyer le message avec la vue interactive
            if ctx.interaction:
                await ctx.interaction.followup.send(embed=embed, view=view)
            else:
                await ctx.send(embed=embed, view=view, reference=ctx.message)
            
            print(f"[leader.py] Interface élégante envoyée avec succès")

        except Exception as e:
            print(f"[leader.py] Erreur lors de l'exécution de la commande : {e}")
            traceback.print_exc()
            
            error_msg = "❌ Une erreur est survenue lors de l'exécution de la commande."
            if ctx.interaction:
                await ctx.interaction.followup.send(error_msg, ephemeral=True)
            else:
                await ctx.send(error_msg, reference=ctx.message)

async def setup(bot):
    await bot.add_cog(Leader(bot))
