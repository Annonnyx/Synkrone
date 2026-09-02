import discord
from discord.ext import commands
from discord import app_commands
import os

# ==============================================================================
# --------------------------- IMPORTATION UTILS --------------------------------
# ==============================================================================
try:
    from cogs.developpeur.commands.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# ==========================================
# VUES ET COMPOSANTS
# ==========================================

class GuideSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Accueil", description="Menu principal du guide", emoji="🏠", value="home"),
            discord.SelectOption(label="Taux de drop", description="Chances d'obtention par rareté", emoji="🎲", value="drops"),
            discord.SelectOption(label="Système de dégâts", description="Calcul des dégâts et bonus", emoji="⚔️", value="damage"),
            discord.SelectOption(label="Système Économique", description="Vente, Shop et Boutique", emoji="💰", value="economy"),
            discord.SelectOption(label="Système PvP", description="Règles des combats tour par tour", emoji="🏟️", value="pvp"),
            discord.SelectOption(label="Garderie", description="Système d'XP et garderie", emoji="⛺", value="sleep"),
            discord.SelectOption(label="Premium", description="Avantages et fonctionnalités", emoji="👑", value="premium"),
        ]
        super().__init__(placeholder="Choisissez un chapitre du guide...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        view: GuideView = self.view
        value = self.values[0]
        
        if value == "home":
            embed = view.create_home_embed(interaction)
        elif value == "drops":
            embed = view.create_drops_embed(interaction)
        elif value == "damage":
            embed = view.create_damage_embed(interaction)
        elif value == "economy":
            embed = view.create_economy_embed(interaction)
        elif value == "pvp":
            embed = view.create_pvp_embed(interaction)
        elif value == "sleep":
            embed = view.create_sleep_embed(interaction)
        elif value == "premium":
            embed = view.create_premium_embed(interaction)
            
        await interaction.response.edit_message(embed=embed, view=view)

class GuideView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=600)
        self.bot = bot
        self.add_item(GuideSelect())

    def get_base_embed(self, source, title, description):
        """Détecte automatiquement si la source est Context ou Interaction"""
        user = source.user if isinstance(source, discord.Interaction) else source.author
        guild = source.guild
        bot = self.bot

        if config_manager:
            embed = config_manager.get_formatted_embed(
                guild=guild, user=user, bot=bot,
                title=title, description=description
            )
        else:
            embed = discord.Embed(title=title, description=description, color=0x2b2d31)
        
        # Thumbnail de l'image du bot sur tous les embeds
        if bot.user.avatar:
            embed.set_thumbnail(url=bot.user.avatar.url)
            embed.set_footer(text="Guide Officiel Kayaba • Système de jeu", icon_url=bot.user.avatar.url)
            
        return embed

    def create_home_embed(self, source):
        desc = (
            "Bienvenue dans le guide officiel de **Kayaba Collection**.\n\n"
            "Utilisez le menu déroulant ci-dessous pour naviguer entre les différentes sections.\n\n"
            "**Sections disponibles :**\n"
            "• 🎲 **Taux de drop** : Probabilités d'obtention des cartes.\n"
            "• ⚔️ **Système de dégâts** : Formules et calculs du score VS.\n"
            "• 💰 **Système Économique** : Vente, Shop, Boutique et Marché.\n"
            "• 🏟️ **Système PvP** : Combat tour par tour et précision.\n"
            "• ⛺ **Garderie** : Système d'XP et mise en repos des cartes.\n"
            "• 👑 **Premium** : Avantages exclusifs et fonctionnalités."
        )
        return self.get_base_embed(source, "🏠 Menu du Guide", desc)

    def create_drops_embed(self, source):
        desc = (
            "Voici les probabilités d'obtention des cartes lors des tirages :\n\n"
            "⚪ **Commun** : `70%` de chance\n"
            "🔵 **Rare** : `20%` de chance\n"
            "🟣 **Épique** : `8%` de chance\n"
            "🟡 **Légendaire** : `2%` de chance\n\n"
            "-# Les taux sont fixes pour garantir l'équité entre les joueurs."
        )
        return self.get_base_embed(source, "🎲 Taux de Drop", desc)

    def create_damage_embed(self, source):
        exclusivity_table = (
            "```py\n"
            "• 1 exemplaire       : +3000\n"
            "• 2 à 10 ex.         : +1500\n"
            "• 11 à 100 ex.       : +1000\n"
            "• 101 à 500 ex.      : +800\n"
            "• 501 à 1 000 ex.    : +600\n"
            "• 1 001 à 2 500 ex.  : +400\n"
            "• 2 501 à 5 000 ex.  : +200\n"
            "• 5 001 à 10 000 ex. : +100\n"
            "• + 10 001 ex.       : +0\n"
            "```"
        )
        
        desc = (
            "Le système de puissance n'est pas linéaire. Voici comment est calculée votre force :\n\n"
            "### ⚙️ Formule du Score (VS)\n"
            "**VS = Vr + Be + Puissance + (Valeur × 0,001)**\n\n"
            "**✨ Bonus de Rareté (Vr) :**\n"
            "• Commun : `0` | Rare : `300`\n"
            "• Épique : `500` | Légendaire : `1000`\n\n"
            "**💎 Bonus d'Exclusivité (Be) :**\n"
            f"{exclusivity_table}"
        )
        return self.get_base_embed(source, "⚔️ Système de Dégâts", desc)

    def create_economy_embed(self, source):
        desc = (
            "L'économie de Kayaba Collection repose sur la gestion de vos ressources et de vos cartes.\n\n"
            "**🏪 Vente directe (`.sell`) :**\n"
            "• Vendez instantanément vos cartes au prix de leur **valeur de base**.\n"
            "• Parfait pour obtenir rapidement des <:col:1482462727468486738> Col.\n"
            "-# ⚠️ Le prix du marché peut être différent de la valeur de base.\n\n"
            "**🛒 Marché communautaire (`.shop`) :**\n"
            "• Mettez vos cartes en vente au prix de votre choix.\n"
            "• Filtres avancés : par rareté, famille, ID, cartes manquantes.\n"
            "• Affichage du vendeur et système de pagination.\n"
            "• Commission : 0% (vous recevez 100% du prix).\n\n"
            "**🛍️ Boutique exclusive (`.boutique`) :**\n"
            "• Cartes rares et exclusives à prix fixe.\n"
            "• Rotation mensuelle des offres.\n"
            "• Accès prioritaire pour les membres Premium.\n\n"
            "**🎴 Tirages (`.collect`) :**\n"
            "• Cooldown : 1 heure (30 minutes pour Premium).\n"
            "• 5 cartes par tirage (8 pour Premium).\n"
            "• Bonus de drop selon votre statut Premium.\n\n"
            "**🎁 Récompense quotidienne (`.daily`) :**\n"
            "• Disponible toutes les 24 heures.\n"
            "• Slots et <:col:1482462727468486738> Col aléatoires.\n"
            "• Multiplicateur x3 pour les membres Premium."
        )
        return self.get_base_embed(source, "💰 Système Économique", desc)

    def create_pvp_embed(self, source):
        desc = (
            "Le PvP est un combat stratégique au tour par tour.\n\n"
            "**Règles de base :**\n"
            "• **Équipe** : Maximum `4 cartes` par joueur.\n"
            "• **Priorité** : Le slot 1 est utilisé en premier. La carte avec la plus haute **vitesse** commence.\n\n"
            "### 🎯 Système de Précision\n"
            "En cas d'échec de votre statistique de précision :\n"
            "• `50.0%` : **Passe le tour** (Échec total)\n"
            "• `35.0%` : Inflige **25%** des dégâts\n"
            "• `10.5%` : Inflige **50%** des dégâts\n"
            "• `04.5%` : Inflige **75%** des dégâts\n\n"
            "**Condition de victoire :** Éliminer toutes les cartes adverses."
        )
        return self.get_base_embed(source, "🏟️ Système PvP", desc)

    def create_sleep_embed(self, source):
        desc = (
            "La garderie vous permet de faire gagner de l'XP à vos cartes pendant qu'elles se reposent.\n\n"
            "**⛺ Système de Garderie :**\n"
            "• **Slots disponibles** : 2 slots (3 pour Premium).\n"
            "• **Durée maximale** : 8 heures (12 heures pour Premium).\n"
            "• **XP gagné** : Basé sur la valeur de la carte × multiplicateur de temps.\n\n"
            "**📊 Calcul de l'XP :**\n"
            "• **Formule** : `XP = (Valeur carte × 0.001) × (heures en garderie / 8)`\n"
            "• **Bonus Premium** : Multiplicateur ×1.5 sur l'XP gagné.\n"
            "• **Maximum** : Une carte peut gagner jusqu'à 50% de sa valeur en XP.\n\n"
            "**⏰ Gestion des cartes :**\n"
            "• **Ajout** : Placez vos cartes dans les slots disponibles.\n"
            "• **Retrait** : Récupérez vos cartes avec l'XP accumulé.\n"
            "• **Récompense** : Plus une carte reste longtemps, plus elle gagne d'XP.\n\n"
            "**🎯 Stratégie :**\n"
            "• Mettez vos cartes les plus chères en garderie pour maximiser l'XP.\n"
            "• Les cartes Premium gagnent 50% d'XP en plus.\n"
            "• Planifiez vos retraits pour ne pas dépasser la durée maximale."
        )
        return self.get_base_embed(source, "⛺ Système de Garderie", desc)

    def create_premium_embed(self, source):
        desc = (
            "Le statut Premium débloque des avantages exclusifs et accélère votre progression.\n\n"
            "**👑 Comment devenir Premium :**\n"
            "• Rejoignez le serveur support : https://discord.gg/p768u2Pgp3\n"
            "• Boostez le serveur avec le rôle Booster.\n"
            "• Le statut est automatiquement détecté et appliqué.\n\n"
            "**🌟 Avantages Premium :**\n"
            "• **Daily ×3** : 3x plus de slots et de <:col:1482462727468486738> Col.\n"
            "• **Collection** : 8 cartes par tirage (au lieu de 5).\n"
            "• **Cooldown** : 30 minutes au lieu d'1 heure pour `.collect`.\n"
            "• **Drops améliorés** : +15% Rare, +20% Épique, +25% Légendaire.\n"
            "• **Garderie** : 3 slots et 12 heures maximum.\n"
            "• **XP bonus** : +50% d'XP gagné en garderie.\n"
            "• **Badge exclusif** : Affichage spécial sur votre profil.\n"
            "• **Support prioritaire** : Accès rapide au support technique.\n\n"
            "**💎 Valeur ajoutée :**\n"
            "• Progression 2-3x plus rapide.\n"
            "• Accès à des fonctionnalités exclusives.\n"
            "• Avantages compétitifs en PvP.\n"
            "• Économie optimisée avec des bonus réguliers."
        )
        return self.get_base_embed(source, "👑 Avantages Premium", desc)

# ==========================================
# COG PRINCIPAL
# ==========================================

class Guide(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="guide", description="Affiche le guide complet du système de jeu")
    async def guide(self, ctx: commands.Context):
        view = GuideView(self.bot)
        embed = view.create_home_embed(ctx)
        await ctx.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(Guide(bot))