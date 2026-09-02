import discord
from discord.ext import commands
import json
from pathlib import Path
from datetime import datetime

# Importer le gestionnaire de MP
try:
    from .mp import MPManager, MPView
except ImportError:
    MPManager = None
    MPView = None

# Importer config_manager
try:
    from ..developpeur.commands.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# Importer premium pour les avantages
try:
    from .premium import premium_manager
except ImportError:
    premium_manager = None

# Créer une vue personnalisée pour tracker.py
class TrackerMPView(discord.ui.View):
    """Vue pour le choix des préférences MP dans le message de bienvenue"""
    
    def __init__(self, user_id: int, bot):
        super().__init__(timeout=604800)  # 7 jours en secondes
        self.user_id = user_id
        self.bot = bot
        
        # Définir les boutons comme attributs
        self.enable_btn = discord.ui.Button(label="✅ Activer", style=discord.ButtonStyle.success, custom_id="tracker_mp_enable")
        self.disable_btn = discord.ui.Button(label="❌ Désactiver", style=discord.ButtonStyle.danger, custom_id="tracker_mp_disable")
        self.premium_btn = discord.ui.Button(label="🌟 Voir les avantages", style=discord.ButtonStyle.primary, custom_id="tracker_premium_info")
        
        # Ajouter les callbacks
        self.enable_btn.callback = self.enable_mp
        self.disable_btn.callback = self.disable_mp
        self.premium_btn.callback = self.show_premium_info
        
        # Ajouter les boutons à la vue
        self.add_item(self.enable_btn)
        self.add_item(self.disable_btn)
        self.add_item(self.premium_btn)
        
        self.update_view()
    
    def update_view(self):
        """Met à jour la vue selon le statut actuel"""
        current_status = MPManager.get_mp_preference(self.user_id) if MPManager else True
        
        if current_status:
            # Si activé, montrer seulement le bouton désactiver
            self.enable_btn.disabled = True
            self.enable_btn.label = "✅ Déjà activé"
            self.disable_btn.disabled = False
            self.disable_btn.label = "❌ Désactiver"
        else:
            # Si désactivé, montrer seulement le bouton activer
            self.enable_btn.disabled = False
            self.enable_btn.label = "✅ Activer"
            self.disable_btn.disabled = True
            self.disable_btn.label = "❌ Déjà désactivé"
    
    def create_embed(self):
        """Crée l'embed selon le statut actuel"""
        current_status = MPManager.get_mp_preference(self.user_id) if MPManager else True
        status_text = "✅ **Activés**" if current_status else "❌ **Désactivés**"
        
        if config_manager:
            try:
                embed = config_manager.get_formatted_embed(
                    guild=None, user=self.bot.get_user(self.user_id), bot=self.bot,
                    title="📬 Bienvenue sur l'Aventure !",
                    target_id=None
                )
                
                description = "Merci d'avoir rejoint notre collection de cartes !\n\n"
                description += "Pour suivre votre progression, le bot peut vous envoyer des messages privés concernant :\n\n"
                description += "📦 **Obtention de cartes**\n"
                description += "💰 **Vente de cartes**\n"
                description += "⚔️ **Récapitulatif de combat**\n\n"
                description += f"**Statut actuel :** {status_text}\n\n"
                description += "Choisissez si vous souhaitez recevoir ces notifications. Utilisez `.mp` pour modifier les notifications à tout moment.\n\n"
                description += "**🌟 Devenez premium** en boostant le [serveur support](https://discord.gg/p768u2Pgp3) !\n"
                description += "Recevez une notification automatique lors des changements de statut.\n"
                description += "Cliquez sur \"🌟 Voir les avantages\" pour en savoir plus.\n\n"
                description += "**📚 Commandes utiles :**\n"
                description += "• `.help` pour lister toutes les commandes\n"
                description += "• `.guide` pour comprendre l'aventure"
                
                embed.description = description
            except Exception as e:
                embed = discord.Embed(
                    title="📬 Bienvenue sur l'Aventure !",
                    description="Merci d'avoir rejoint notre collection de cartes !\n\n"
                    "Pour suivre votre progression, le bot peut vous envoyer des messages privés concernant :\n\n"
                    "📦 **Obtention de cartes** lors de vos tirages\n"
                    "💰 **Vente de cartes** sur le marché\n"
                    "⚔️ **Récapitulatif de combat** après les batailles\n\n"
                    f"**Statut actuel :** {status_text}\n\n"
                    "Choisissez si vous souhaitez recevoir ces notifications :\n\n"
                    "**🌟 Devenez premium** en boostant le [serveur support](https://discord.gg/p768u2Pgp3) !\n"
                    "Recevez une notification automatique lors des changements de statut.\n"
                    "Cliquez sur \"🌟 Voir les avantages\" pour en savoir plus.\n\n"
                    "**📚 Commandes utiles :**\n"
                    "• `.help` pour lister toutes les commandes\n"
                    "• `.guide` pour comprendre l'aventure",
                    color=0x5865F2
                )
        else:
            embed = discord.Embed(
                title="📬 Bienvenue sur l'Aventure !",
                description="Merci d'avoir rejoint notre collection de cartes !\n\n"
                "Pour suivre votre progression, le bot peut vous envoyer des messages privés concernant :\n\n"
                "📦 **Obtention de cartes** lors de vos tirages\n"
                "💰 **Vente de cartes** sur le marché\n"
                "⚔️ **Récapitulatif de combat** après les batailles\n\n"
                "Choisissez si vous souhaitez recevoir ces notifications :\n\n"
                "**🌟 Devenez premium** en boostant le [serveur support](https://discord.gg/p768u2Pgp3) !\n"
                "Recevez une notification automatique lors des changements de statut.\n"
                "Cliquez sur \"🌟 Voir les avantages\" pour en savoir plus.\n\n"
                "**📚 Commandes utiles :**\n"
                "• `.help` pour lister toutes les commandes\n"
                "• `.guide` pour comprendre l'aventure",
                color=0x5865F2
            )
        
        return embed
    
    async def show_premium_info(self, interaction: discord.Interaction):
        """Affiche les informations Premium"""
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Ce n'est pas votre choix !", ephemeral=True)
        
        try:
            # Importer la classe Premium pour créer l'embed
            from .premium import Premium
            
            # Créer une instance temporaire de Premium
            premium_cog = Premium(self.bot)
            embed = premium_cog.create_premium_embed(interaction.user)
            
            # Créer une vue avec le bouton vers le serveur
            from .premium import PremiumView
            view = PremiumView(interaction.user)
            
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            
        except Exception as e:
            await interaction.response.send_message("❌ Une erreur est survenue lors de l'affichage des avantages Premium.", ephemeral=True)
    
    async def enable_mp(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Ce n'est pas votre choix !", ephemeral=True)
        
        # Activer les MP
        success = MPManager.set_mp_preference(self.user_id, True) if MPManager else False
        
        if success:
            # Mettre à jour les boutons pour montrer le bouton désactiver
            self.enable_btn.disabled = True
            self.enable_btn.label = "✅ Déjà activé"
            self.disable_btn.disabled = False
            self.disable_btn.label = "❌ Désactiver"
            
            embed = self.create_embed()
            embed.description = "✅ **Messages Privés Activés**\n\nVous recevrez désormais les messages privés du bot concernant :\n\n📦 **Obtention de cartes**\n💰 **Vente de cartes**\n⚔️ **Récapitulatif de combat**\n\nVous pouvez désactiver cette option en cliquant sur le bouton **❌ Désactiver** ci-dessous !\n\n**🌟 Devenez premium** en boostant le [serveur support](https://discord.gg/p768u2Pgp3) !\nRecevez une notification automatique lors des changements de statut.\nCliquez sur \"🌟 Voir les avantages\" pour en savoir plus."
            
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("❌ Erreur lors de l'activation des MP.", ephemeral=True)
    
    async def disable_mp(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Ce n'est pas votre choix !", ephemeral=True)
        
        # Désactiver les MP
        success = MPManager.set_mp_preference(self.user_id, False) if MPManager else False
        
        if success:
            # Mettre à jour les boutons pour montrer le bouton activer
            self.enable_btn.disabled = False
            self.enable_btn.label = "✅ Activer"
            self.disable_btn.disabled = True
            self.disable_btn.label = "❌ Déjà désactivé"
            
            embed = self.create_embed()
            embed.description = "❌ **Messages Privés Désactivés**\n\nVous ne recevrez plus aucun message privé du bot.\n\nLes messages privés concernent :\n📦 Obtention de cartes\n💰 Vente de cartes\n⚔️ Récapitulatif de combat\n\nVous pouvez réactiver cette option en cliquant sur le bouton **✅ Activer** ci-dessous !\n\n**🌟 Devenez premium** en boostant le [serveur support](https://discord.gg/p768u2Pgp3) !\nRecevez une notification automatique lors des changements de statut.\nCliquez sur \"🌟 Voir les avantages** pour en savoir plus."
            
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("❌ Erreur lors de la désactivation des MP.", ephemeral=True)

class UserTracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # Définition du chemin cible corrigé
        self.data_dir = Path("cogs/collection/data/interserver")
        
        # Création des dossiers s'ils n'existent pas encore
        self.data_dir.mkdir(parents=True, exist_ok=True)

    async def check_and_create_file(self, user_id: int):
        """Vérifie si le JSON de l'utilisateur existe, sinon le crée."""
        file_path = self.data_dir / f"{user_id}.json"
        first_connection = False
        
        # Si le fichier n'existe pas, on le crée
        if not file_path.exists():
            # Données de base à insérer lors de la création
            default_data = {
                "user_id": user_id,
                "first_seen": True,
                "created_at": datetime.now().isoformat(),
                "slots": 1,
                "collection": {},
                "mp_enabled": True
            }
                
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(default_data, f, indent=4)
            first_connection = True
        else:
            # Vérifier si c'est la première connexion (pas de mp_enabled)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "mp_enabled" not in data:
                        # C'est la première connexion, ajouter mp_enabled
                        data["mp_enabled"] = True
                        with open(file_path, "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=4)
                        first_connection = True
            except Exception as e:
                pass
        
        # Envoyer un MP pour le choix des préférences MP (première connexion)
        if first_connection:
            await self.send_mp_welcome(user_id)
            return True  # Indique que c'est la première connexion
        
        return False

    async def send_mp_welcome(self, user_id: int):
        """Envoie un message de bienvenue avec le choix des préférences MP"""
        if not MPManager:
            return
            
        try:
            user = self.bot.get_user(user_id)
            if not user:
                return
                
            # Créer l'embed avec config_manager
            if config_manager:
                try:
                    embed = config_manager.get_formatted_embed(
                        guild=None, user=user, bot=self.bot,
                        title="📬 Bienvenue sur l'Aventure !",
                        target_id=None
                    )
                        
                    description = "Merci d'avoir rejoint notre collection de cartes !\n\n"
                    description += "Pour suivre votre progression, le bot peut vous envoyer des messages privés concernant :\n\n"
                    description += "📦 **Obtention de cartes**\n"
                    description += "💰 **Vente de cartes**\n"
                    description += "⚔️ **Récapitulatif de combat**\n\n"
                    description += "Choisissez si vous souhaitez recevoir ces notifications. Utilisez `.mp` pour modifier les notifications à tout moment.\n\n"
                    description += "**🌟 Devenez premium** en boostant le [serveur support](https://discord.gg/p768u2Pgp3) !\n"
                    description += "Recevez une notification automatique lors des changements de statut.\n"
                    description += "Cliquez sur \"🌟 Voir les avantages\" pour en savoir plus.\n\n"
                    description += "**📚 Commandes utiles :**\n"
                    description += "• `.help` pour lister toutes les commandes\n"
                    description += "• `.guide` pour comprendre l'aventure"
                        
                    embed.description = description
                except Exception as e:
                    embed = discord.Embed(
                        title="📬 Bienvenue sur l'Aventure !",
                        description="Merci d'avoir rejoint notre collection de cartes !\n\n"
                        "Pour suivre votre progression, le bot peut vous envoyer des messages privés concernant :\n\n"
                        "📦 **Obtention de cartes** lors de vos tirages\n"
                        "💰 **Vente de cartes** sur le marché\n"
                        "⚔️ **Récapitulatif de combat** après les batailles\n\n"
                        "Choisissez si vous souhaitez recevoir ces notifications :\n\n"
                        "**🌟 Devenez premium** en boostant le [serveur support](https://discord.gg/p768u2Pgp3) !\n"
                        "Recevez une notification automatique lors des changements de statut.\n"
                        "Cliquez sur \"🌟 Voir les avantages** pour en savoir plus.\n\n"
                        "**📚 Commandes utiles :**\n"
                        "• `.help` pour lister toutes les commandes\n"
                        "• `.guide` pour comprendre l'aventure",
                        color=0x5865F2
                    )
            else:
                embed = discord.Embed(
                    title="📬 Bienvenue sur l'Aventure !",
                    description="Merci d'avoir rejoint notre collection de cartes !\n\n"
                    "Pour suivre votre progression, le bot peut vous envoyer des messages privés concernant :\n\n"
                    "📦 **Obtention de cartes** lors de vos tirages\n"
                    "💰 **Vente de cartes** sur le marché\n"
                    "⚔️ **Récapitulatif de combat** après les batailles\n\n"
                    "Choisissez si vous souhaitez recevoir ces notifications :\n\n"
                    "**🌟 Devenez premium** en boostant le [serveur support](https://discord.gg/p768u2Pgp3) !\n"
                    "Recevez une notification automatique lors des changements de statut.\n"
                    "Cliquez sur \"🌟 Voir les avantages** pour en savoir plus.\n\n"
                    "**📚 Commandes utiles :**\n"
                    "• `.help` pour lister toutes les commandes\n"
                    "• `.guide` pour comprendre l'aventure",
                    color=0x5865F2
                )
                
            # Créer la vue pour le choix
            view = TrackerMPView(user_id, self.bot)
                
            await user.send(embed=view.create_embed(), view=view)
                
        except discord.Forbidden:
            # L'utilisateur a désactivé les MP
            MPManager.set_mp_preference(user_id, False)
        except Exception as e:
            pass

    # 1. Écouteur pour les commandes classiques (ex: !help)
    @commands.Cog.listener()
    async def on_command(self, ctx):
        # Ignore les bots pour ne pas créer de fichiers pour eux
        if not ctx.author.bot:
            first_time = await self.check_and_create_file(ctx.author.id)
            if first_time:
                # C'est la première fois que l'utilisateur utilise une commande
                pass

    # 2. Écouteur pour les commandes slash (interactions)
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        # On vérifie que c'est bien une commande d'application (Slash command)
        if interaction.type == discord.InteractionType.application_command:
            # Ignore les bots (bien que les bots ne puissent généralement pas utiliser de slash commands)
            if not interaction.user.bot:
                first_time = await self.check_and_create_file(interaction.user.id)
                if first_time:
                    # C'est la première fois que l'utilisateur utilise une commande slash
                    pass


# Fonction de configuration obligatoire pour charger le Cog
async def setup(bot):
    await bot.add_cog(UserTracker(bot))
