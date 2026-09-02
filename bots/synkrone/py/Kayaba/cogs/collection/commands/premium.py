import discord
from discord.ext import commands
import json
import os
import sys

# ==========================================
# GESTION DES EMOJIS
# ==========================================
def load_emojis() -> dict:
    """Charge les emojis personnalisés avec fallback sur les emojis standards."""
    emoji_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'emoji.json')
    
    # Emojis standards de fallback
    fallback_emojis = {
        "cartes": "🎴", "kronos": "💰", "star": "⭐", "trophy": "🏆",
        "sword": "⚔️", "check": "✅", "handshake": "🤝", "cross": "❌",
        "gem": "💎", "chart": "📊", "user": "👤", "home": "🏠",
        "left_arrow": "⬅️", "right_arrow": "➡️", "plus": "➕", "info": "ℹ️",
        "crown": "👑", "sparkles": "✨", "gift": "🎁", "clock": "⏰"
    }
    
    try:
        with open(emoji_path, 'r', encoding='utf-8') as f:
            custom_emojis = json.load(f)
            
        # Fusionner avec fallback : garde les personnalisés, utilise fallback si manquant
        return {key: custom_emojis.get(key, default) for key, default in fallback_emojis.items()}
        
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback_emojis

emojis = load_emojis()

# ==========================================
# IMPORTATION DES VARIABLES DE VALEURS
# ==========================================
try:
    # Importer depuis collect.py
    from .collect import (
        COOLDOWN_BASE, COOLDOWN_PREMIUM, CARTE_BASE, CARTE_PREMIUM,
        BONUS_RARE_PREMIUM, BONUS_EPIQUE_PREMIUM, BONUS_LEGENDAIRE_PREMIUM, MALUS_COMMUN_PREMIUM
    )
except ImportError as e:
    print(f"[PREMIUM] Erreur import collect.py: {e}")
    print(f"[PREMIUM] Utilisation des valeurs par défaut pour collect.py:")
    # Valeurs par défaut si l'import échoue
    COOLDOWN_BASE = 1
    COOLDOWN_PREMIUM = 0.5
    CARTE_BASE = 5
    CARTE_PREMIUM = 8
    BONUS_RARE_PREMIUM = 1.15
    BONUS_EPIQUE_PREMIUM = 1.20
    BONUS_LEGENDAIRE_PREMIUM = 1.25
    MALUS_COMMUN_PREMIUM = 0.85
    print(f"  - COOLDOWN_BASE: {COOLDOWN_BASE}")
    print(f"  - COOLDOWN_PREMIUM: {COOLDOWN_PREMIUM}")
    print(f"  - CARTE_BASE: {CARTE_BASE}")
    print(f"  - CARTE_PREMIUM: {CARTE_PREMIUM}")
    print(f"  - BONUS_RARE_PREMIUM: {BONUS_RARE_PREMIUM}")
    print(f"  - BONUS_EPIQUE_PREMIUM: {BONUS_EPIQUE_PREMIUM}")
    print(f"  - BONUS_LEGENDAIRE_PREMIUM: {BONUS_LEGENDAIRE_PREMIUM}")
    print(f"  - MALUS_COMMUN_PREMIUM: {MALUS_COMMUN_PREMIUM}")

try:
    # Importer depuis daily.py
    from .daily import (
        DAILY_SLOTS_MIN, DAILY_SLOTS_MAX, DAILY_COL_MIN, DAILY_COL_MAX,
        PREMIUM_MULTIPLIER, PREMIUM_SLOTS_MIN, PREMIUM_SLOTS_MAX, 
        PREMIUM_COL_MIN, PREMIUM_COL_MAX
    )
except ImportError as e:
    print(f"[PREMIUM] Erreur import daily.py: {e}")
    print(f"[PREMIUM] Utilisation des valeurs par défaut pour daily.py:")
    # Valeurs par défaut si l'import échoue
    DAILY_SLOTS_MIN = 1
    DAILY_SLOTS_MAX = 5
    DAILY_COL_MIN = 1
    DAILY_COL_MAX = 50000
    PREMIUM_MULTIPLIER = 3
    PREMIUM_SLOTS_MIN = 3
    PREMIUM_SLOTS_MAX = 20
    PREMIUM_COL_MIN = 10000
    PREMIUM_COL_MAX = 150000
    print(f"  - DAILY_SLOTS_MIN: {DAILY_SLOTS_MIN}")
    print(f"  - DAILY_SLOTS_MAX: {DAILY_SLOTS_MAX}")
    print(f"  - DAILY_COL_MIN: {DAILY_COL_MIN}")
    print(f"  - DAILY_COL_MAX: {DAILY_COL_MAX}")
    print(f"  - PREMIUM_MULTIPLIER: {PREMIUM_MULTIPLIER}")
    print(f"  - PREMIUM_SLOTS_MIN: {PREMIUM_SLOTS_MIN}")
    print(f"  - PREMIUM_SLOTS_MAX: {PREMIUM_SLOTS_MAX}")
    print(f"  - PREMIUM_COL_MIN: {PREMIUM_COL_MIN}")
    print(f"  - PREMIUM_COL_MAX: {PREMIUM_COL_MAX}")

# ==========================================
# IMPORTATION DU CONFIG MANAGER
# ==========================================
BASE_DIR = os.path.dirname(__file__)
sys.path.append(os.path.join(BASE_DIR, '..', '..', '..', 'developpeur', 'commands', 'embed_type'))

try:
    from cogs.developpeur.commands.embed_type.utils import config_manager
    HAS_CONFIG_MANAGER = True
except ImportError as e:
    print(f"[PREMIUM] Erreur import config_manager: {e}")
    config_manager = None
    HAS_CONFIG_MANAGER = False

# ==========================================
# GESTION DES UTILISATEURS PREMIUM
# ==========================================
class PremiumManager:
    def __init__(self):
        self.premium_users = set()
        self.support_guild_id = 1368235294192570520  # Serveur support
        self.booster_role_id = 1436852950059192504  # Rôle booster
        self.premium_data_file = os.path.join(BASE_DIR, '..', 'data', 'premium.json')
        self.last_update = 0
        self.load_premium_users()
    
    def load_premium_users(self):
        """Charge la liste des utilisateurs premium depuis le fichier JSON"""
        try:
            if os.path.exists(self.premium_data_file):
                with open(self.premium_data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.premium_users = set(data.get('premium_users', []))
                    self.last_update = data.get('last_update', 0)
        except Exception:
            self.premium_users = set()
            self.last_update = 0
    
    def save_premium_users(self):
        """Sauvegarde la liste des utilisateurs premium dans le fichier JSON"""
        try:
            os.makedirs(os.path.dirname(self.premium_data_file), exist_ok=True)
            with open(self.premium_data_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'premium_users': list(self.premium_users),
                    'last_update': self.last_update
                }, f, indent=2)
        except Exception:
            pass
    
    async def update_premium_users(self, bot):
        """Met à jour la liste des utilisateurs premium depuis le serveur support"""
        import time
        current_time = time.time()
        
        # Vérifier si 2 minutes se sont écoulées (120 secondes)
        if current_time - self.last_update < 120:
            return
        
        try:
            # Récupérer le serveur support
            support_guild = bot.get_guild(self.support_guild_id)
            if not support_guild:
                return
            
            # Récupérer tous les membres avec le rôle booster
            booster_role = support_guild.get_role(self.booster_role_id)
            if not booster_role:
                return
            
            # Mettre à jour la liste des utilisateurs premium
            new_premium_users = set()
            for member in support_guild.members:
                if booster_role in member.roles:
                    new_premium_users.add(member.id)
            
            # Comparer avec l'ancienne liste pour détecter les changements
            old_premium_users = self.premium_users.copy()
            
            # Utilisateurs qui ont gagné le statut premium
            gained_users = new_premium_users - old_premium_users
            # Utilisateurs qui ont perdu le statut premium
            lost_users = old_premium_users - new_premium_users
            
            # Envoyer les notifications
            for user_id in gained_users:
                self.add_premium(user_id)
            
            for user_id in lost_users:
                self.remove_premium(user_id)
            
            # Sauvegarder les changements
            self.premium_users = new_premium_users
            self.last_update = current_time
            self.save_premium_users()
            
        except Exception as e:
            print(f"[PREMIUM] Erreur lors de la mise à jour des utilisateurs premium: {e}")
    
    def is_premium(self, user_id: int) -> bool:
        """Vérifie si un utilisateur est premium"""
        return user_id in self.premium_users
    
    def add_premium(self, user_id: int):
        """Ajoute un utilisateur aux premium"""
        self.premium_users.add(user_id)
        self.save_premium_users()
        
        # Envoyer un message privé pour avertir l'utilisateur
        import asyncio
        asyncio.create_task(self.send_premium_notification(user_id, gained=True))
    
    def remove_premium(self, user_id: int):
        """Retire un utilisateur des premium"""
        self.premium_users.discard(user_id)
        self.save_premium_users()
        
        # Envoyer un message privé pour avertir l'utilisateur
        import asyncio
        asyncio.create_task(self.send_premium_notification(user_id, gained=False))
    
    async def send_premium_notification(self, user_id: int, gained: bool):
        """Envoie une notification MP à l'utilisateur"""
        try:
            user = self.bot.get_user(user_id)
            if not user:
                return
            
            if gained:
                message = "🌟 Vous avez obtenu les avantages premium"
                color = discord.Color.gold()
                title = "🌟 Avantages Premium Activés"
            else:
                message = "🌟 Vous avez perdu les avantages premium"
                color = discord.Color.red()
                title = "🌟 Avantages Premium Perdus"
            
            embed = discord.Embed(
                title=title,
                description=message,
                color=color
            )
            embed.set_footer(text="Serveur support: https://discord.gg/p768u2Pgp3")
            
            await user.send(embed=embed)
            print(f"[PREMIUM] Notification MP envoyée à l'utilisateur {user_id} - {'Gagné' if gained else 'Perdu'}")
            
        except discord.Forbidden:
            print(f"[PREMIUM] Impossible d'envoyer un MP à l'utilisateur {user_id} - MP désactivés")
        except Exception as e:
            print(f"[PREMIUM] Erreur lors de l'envoi de la notification MP: {e}")

# Instance globale du gestionnaire premium
premium_manager = PremiumManager()

# ==========================================
# INTERFACE UTILISATEUR (UI) - VUES
# ==========================================
class PremiumView(discord.ui.View):
    def __init__(self, user: discord.User):
        super().__init__(timeout=120)
        self.user = user
        
        # Ajouter un bouton de type link qui envoie directement sur le serveur
        self.add_item(discord.ui.Button(
            label="🚀 Rejoindre le Serveur Support",
            style=discord.ButtonStyle.link,
            url="https://discord.gg/p768u2Pgp3"
        ))

# ==========================================
# COG PRINCIPAL
# ==========================================
class Premium(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.update_task = None
    
    async def cog_load(self):
        """Démarrer la tâche de mise à jour automatique"""
        self.update_task = self.bot.loop.create_task(self.auto_update_premium())
    
    async def cog_unload(self):
        """Arrêter la tâche de mise à jour lors du déchargement"""
        if self.update_task:
            self.update_task.cancel()
    
    async def auto_update_premium(self):
        """Met à jour automatiquement la liste des premium toutes les 2 minutes"""
        import asyncio
        while True:
            try:
                await premium_manager.update_premium_users(self.bot)
                await asyncio.sleep(120)  # 2 minutes
            except Exception:
                await asyncio.sleep(120)  # Continue même en cas d'erreur

    def create_premium_embed(self, user: discord.User | discord.Member) -> discord.Embed:
        """Crée un embed détaillé des avantages premium avec conditions spécifiques"""
        is_premium = premium_manager.is_premium(user.id)
        
        if is_premium:
            title = f"{emojis['crown']} Premium Activé • {user.display_name}"
            description = f"**{emojis['sparkles']} Vous profitez déjà de tous les avantages exclusifs !**"
            color = discord.Color.gold()
        else:
            title = f"{emojis['gem']} Découvrez l'Offre Premium"
            description = f"**{emojis['sparkles']} Débloquez des fonctionnalités exclusives et accélérez votre progression !**"
            color = discord.Color.purple()
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=color
        )
        
        # === AVANTAGES DÉTAILLÉS AVEC CONDITIONS ===
        
        # Daily Rewards
        daily_text = (
            f"**{emojis['gift']} Récompense Quotidienne**\n"
            f"• **Slots** : {DAILY_SLOTS_MIN}-{DAILY_SLOTS_MAX} → {PREMIUM_SLOTS_MIN}-{PREMIUM_SLOTS_MAX}\n"
            f"• **Col** : {DAILY_COL_MIN:,}-{DAILY_COL_MAX:,} → {PREMIUM_COL_MIN:,}-{PREMIUM_COL_MAX:,}\n"
            f"• **Multiplicateur** : x1 → x{PREMIUM_MULTIPLIER}\n"
            f"• **Condition** : Daily disponible toutes les 24h"
        )
        
        # Collection System
        collect_text = (
            f"**{emojis['cartes']} Système de Collection**\n"
            f"• **Cartes par tirage** : {CARTE_BASE} → {CARTE_PREMIUM}\n"
            f"• **Cooldown** : {COOLDOWN_BASE}h → {COOLDOWN_PREMIUM}h\n"
            f"• **Bonus de drop** :\n"
            f"  - Commun : x1 → x{MALUS_COMMUN_PREMIUM}\n"
            f"  - Rare : x1 → x{BONUS_RARE_PREMIUM}\n"
            f"  - Épique : x1 → x{BONUS_EPIQUE_PREMIUM}\n"
            f"  - Légendaire : x1 → x{BONUS_LEGENDAIRE_PREMIUM}\n"
            f"• **Condition** : Cooldown réduit et bonus de probabilité"
        )
        
        # Échanges et Transferts
        exchange_text = (
            f"**{emojis['handshake']} Échanges & Transferts**\n"
            f"• **Cooldown échange** : 60min → 10min\n"
            f"• **Transactions** : Aucune limitation\n"
            f"• **MP automatique** : Notifications activées par défaut\n"
            f"• **Condition** : Réduction du cooldown de 83%"
        )
        
        # Garderie (Sleep System)
        sleep_text = (
            f"**⛺ Système de Garderie**\n"
            f"• **Slots disponibles** : 2 → 3 slots\n"
            f"• **Durée maximale** : 8h → 12h\n"
            f"• **Bonus XP** : x1 → x1.5\n"
            f"• **Maximum XP** : 50% valeur carte → 75% valeur carte\n"
            f"• **Condition** : Plus de capacité et gain accéléré"
        )
        
        # Marché et Économie
        economy_text = (
            f"**💰 Économie & Marché**\n"
            f"• **Commission shop** : 0% (déjà gratuit pour tous)\n"
            f"• **Limite de vente** : 25 cartes → Illimité\n"
            f"• **Filtres avancés** : Accès prioritaire aux nouveaux filtres\n"
            f"• **Transactions** : Pas de frais cachés\n"
            f"• **Condition** : Avantages de commodité"
        )
        
        # PvP et Compétition
        pvp_text = (
            f"**{emojis['sword']} PvP & Compétitions**\n"
            f"• **Bonus ELO** : x1 → x1.2\n"
            f"• **Tournois exclusifs** : Accès prioritaire\n"
            f"• **Classements** : Badge spécial dans les tops\n"
            f"• **Équipes** : 4 cartes → 5 cartes maximum\n"
            f"• **Condition** : Avantages compétitifs"
        )
        
        # Avantages Sociaux
        social_text = (
            f"**{emojis['user']} Avantages Sociaux**\n"
            f"• **Badge Premium** : Affichage sur profil et collection\n"
            f"• **Support prioritaire** : Réponse garantie sous 24h\n"
            f"• **Accès bêta** : Nouvelles fonctionnalités en avant-première\n"
            f"• **Serveur exclusif** : Salon VIP et avantages communautaires\n"
            f"• **Condition** : Statut visible et reconnaissance"
        )
        
        # Ajouter tous les champs
        embed.add_field(name="🎁 Récompenses Quotidiennes", value=daily_text, inline=False)
        embed.add_field(name="🎴 Collection & Tirages", value=collect_text, inline=False)
        embed.add_field(name="⛺ Garderie & XP", value=sleep_text, inline=False)
        embed.add_field(name="💰 Économie & Marché", value=economy_text, inline=False)
        embed.add_field(name="🤝 Échanges & Transferts", value=exchange_text, inline=False)
        embed.add_field(name="⚔️ PvP & Compétitions", value=pvp_text, inline=False)
        embed.add_field(name="👑 Avantages Sociaux", value=social_text, inline=False)
        
        # === COMMENT DEVENIR PREMIUM ===
        how_to_text = (
            f"**🚀 Comment devenir Premium ?**\n\n"
            f"1. **Rejoignez le serveur support**\n"
            f"   • Lien : https://discord.gg/p768u2Pgp3\n"
            f"   • Accès aux salons exclusifs\n\n"
            f"2. **Activez le rôle Booster**\n"
            f"   • Boostez le serveur avec Nitro\n"
            f"   • Le statut est automatiquement détecté\n"
            f"   • Activation instantanée des avantages\n\n"
            f"3. **Profitez des avantages**\n"
            f"   • Tous les bonus sont appliqués automatiquement\n"
            f"   • Pas de configuration manuelle requise\n"
            f"   • Statut conservé tant que le boost est actif"
        )
        
        embed.add_field(name="📋 Guide d'Activation", value=how_to_text, inline=False)
        
        # === VALEUR AJOUTÉE ===
        if not is_premium:
            value_text = (
                f"**💎 Valeur ajoutée Premium :**\n"
                f"• **Progression** : 2-3x plus rapide\n"
                f"• **Économie** : +150% de gains quotidiens\n"
                f"• **Temps** : -50% de cooldowns\n"
                f"• **Compétitivité** : +20% de bonus PvP\n"
                f"• **Confort** : Fonctionnalités exclusives\n\n"
                f"**🎯 Investissement recommandé pour :**\n"
                f"• Joueurs actifs (1h+ par jour)\n"
                f"• Collectionneurs passionnés\n"
                f"• Compétiteurs PvP\n"
                f"• Joueurs voulant optimiser leur temps"
            )
            embed.add_field(name="📊 Analyse Valeur", value=value_text, inline=False)
        
        # Configuration du Footer, Couleur et Auteur (Support du Config Manager)
        if HAS_CONFIG_MANAGER and config_manager:
            try:
                embed.color = config_manager.get_embed_color(user)
                embed.set_footer(
                    text=f"{'Statut Premium Activé' if is_premium else 'Devenez Premium aujourd\'hui'} • {config_manager.get_embed_footer(user)}", 
                    icon_url=config_manager.get_embed_icon(user)
                )
                embed.set_author(
                    name=f"{user.display_name} • Système Kayaba Collection",
                    icon_url=user.display_avatar.url if user.display_avatar else None
                )
            except Exception:
                # Fallback de sécurité si le config_manager plante
                embed.set_footer(
                    text=f"{'Statut Premium Activé' if is_premium else 'Devenez Premium aujourd\'hui'} • Système Kayaba Collection",
                    icon_url=user.display_avatar.url if user.display_avatar else None
                )
                embed.set_author(
                    name=f"{user.display_name} • Système Kayaba Collection",
                    icon_url=user.display_avatar.url if user.display_avatar else None
                )
        else:
            embed.set_footer(
                text=f"{'Statut Premium Activé' if is_premium else 'Devenez Premium aujourd\'hui'} • Système Kayaba Collection",
                icon_url=user.display_avatar.url if user.display_avatar else None
            )
            embed.set_author(
                name=f"{user.display_name} • Système Kayaba Collection",
                icon_url=user.display_avatar.url if user.display_avatar else None
            )
        
        return embed

    @commands.command(name="premium", description="Affiche les avantages premium et votre statut")
    async def premium_command(self, ctx: commands.Context):
        """Affiche les informations sur l'offre premium (disponible en MP et serveur)"""
        print(f"[PREMIUM] Commande premium exécutée par {ctx.author.name} (ID: {ctx.author.id})")
        
        try:
            await ctx.defer()
            print(f"[PREMIUM] Défer exécuté")
            
            embed = self.create_premium_embed(ctx.author)
            view = PremiumView(ctx.author)
            
            print(f"[PREMIUM] Embed créé, envoi en cours...")
            await ctx.send(embed=embed, view=view)
            print(f"[PREMIUM] Message envoyé avec succès")
            
        except Exception as e:
            print(f"[PREMIUM] ERREUR: {e}")
            await ctx.send(f"{emojis['cross']} Une erreur est survenue lors de l'affichage des informations premium.")
            import traceback
            traceback.print_exc()

# ==========================================
# FONCTIONS UTILITAIRES POUR LES AUTRES COMMANDES
# ==========================================
def is_premium_user(user_id: int) -> bool:
    """Fonction utilitaire pour vérifier si un utilisateur est premium"""
    return premium_manager.is_premium(user_id)

def get_premium_boosts(user_id: int) -> dict:
    """Retourne les multiplicateurs et avantages pour un utilisateur premium"""
    if premium_manager.is_premium(user_id):
        return {
            # Avantages Daily (variables importées depuis daily.py)
            "daily_multiplier": PREMIUM_MULTIPLIER,
            "daily_slots_min": PREMIUM_SLOTS_MIN,
            "daily_slots_max": PREMIUM_SLOTS_MAX,
            "daily_col_min": PREMIUM_COL_MIN,
            "daily_col_max": PREMIUM_COL_MAX,
            
            # Avantages Collect (variables importées depuis collect.py)
            "collect_cards": CARTE_PREMIUM,
            "collect_cooldown_hours": COOLDOWN_PREMIUM,
            "collect_rare_bonus": BONUS_RARE_PREMIUM,
            "collect_epic_bonus": BONUS_EPIQUE_PREMIUM,
            "collect_legendary_bonus": BONUS_LEGENDAIRE_PREMIUM,
            "collect_common_malus": MALUS_COMMUN_PREMIUM,
            
            # Avantages Échanges
            "exchange_cooldown_minutes": 10,
            
            # Avantages Random/Boutique
            "random_cards": 6,
            "random_unique_chance": 0.05,  # 5%
            
            # Avantages PvP
            "pvp_elo_bonus": 1.2,            # Bonus d'ELO accru
            "pvp_tournaments_access": True,
            
            # Avantages Sociaux
            "has_badge": True,
            "priority_support": True,
            "premium_commands": True
        }
    else:
        return {
            # Avantages Daily (variables importées depuis daily.py)
            "daily_multiplier": 1,
            "daily_slots_min": DAILY_SLOTS_MIN,
            "daily_slots_max": DAILY_SLOTS_MAX,
            "daily_col_min": DAILY_COL_MIN,
            "daily_col_max": DAILY_COL_MAX,
            
            # Avantages Collect (variables importées depuis collect.py)
            "collect_cards": CARTE_BASE,
            "collect_cooldown_hours": COOLDOWN_BASE,
            "collect_rare_bonus": 1.0,
            "collect_epic_bonus": 1.0,
            "collect_legendary_bonus": 1.0,
            "collect_common_malus": 1.0,
            
            # Avantages Échanges
            "exchange_cooldown_minutes": 60,
            
            # Avantages Random/Boutique
            "random_cards": 5,
            "random_unique_chance": 0.0,
            
            # Avantages PvP
            "pvp_elo_bonus": 1.0,
            "pvp_tournaments_access": False,
            
            # Avantages Sociaux
            "has_badge": False,
            "priority_support": False,
            "premium_commands": False
        }

async def setup(bot):
    await bot.add_cog(Premium(bot))
