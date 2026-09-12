import discord
from discord.ext import commands
import json
from pathlib import Path
from datetime import datetime

# Chemin vers les données utilisateur
USER_DATA_PATH = Path("cogs/collection/data/interserver")

# Importer config_manager
try:
    from cogs.developpeur.commands.embed_type.utils import config_manager
except ImportError:
    config_manager = None

class MPManager:
    """Gestionnaire des préférences de messages privés"""
    
    @staticmethod
    def get_mp_preference(user_id: int) -> bool:
        """Récupère la préférence MP d'un utilisateur depuis son JSON"""
        try:
            user_file = USER_DATA_PATH / f"{user_id}.json"
            if user_file.exists():
                with open(user_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("mp_enabled", True)  # Par défaut: True
            return True
        except Exception as e:
            print(f"[DEBUG] Erreur lecture préférence MP pour {user_id}: {e}")
            return True
    
    @staticmethod
    def set_mp_preference(user_id: int, enabled: bool) -> bool:
        """Définit la préférence MP d'un utilisateur dans son JSON"""
        try:
            # S'assurer que le dossier existe
            USER_DATA_PATH.mkdir(parents=True, exist_ok=True)
            user_file = USER_DATA_PATH / f"{user_id}.json"
            
            # Si le fichier n'existe pas, le créer avec des données de base
            if not user_file.exists():
                data = {
                    "user_id": user_id,
                    "first_seen": True,
                    "created_at": datetime.now().isoformat(),
                    "slots": 10,
                    "collection": {},
                    "mp_enabled": enabled
                }
            else:
                # Sinon, mettre à jour le fichier existant
                with open(user_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                data["mp_enabled"] = enabled
                
            with open(user_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            
            return True
        except Exception as e:
            print(f"[DEBUG] Erreur sauvegarde préférence MP pour {user_id}: {e}")
            return False
    
    @staticmethod
    async def send_mp_if_enabled(bot, user_id: int, content: str = None, embed: discord.Embed = None) -> bool:
        """Envoie un MP si l'utilisateur l'a autorisé"""
        try:
            if not MPManager.get_mp_preference(user_id):
                return False

            user = bot.get_user(user_id) or await bot.fetch_user(user_id)
            if user:
                if embed:
                    await user.send(content=content, embed=embed)
                else:
                    await user.send(content=content)
                return True
            return False
            
        except discord.Forbidden:
            # L'utilisateur a désactivé les MP du serveur ou a bloqué le bot
            print(f"[MP DEBUG] Forbidden - MP bloqué par l'utilisateur {user_id}")
            MPManager.set_mp_preference(user_id, False)
            return False
        except Exception as e:
            print(f"[MP DEBUG] Erreur envoi MP à {user_id}: {e}")
            return False


class MPView(discord.ui.View):
    """Vue pour le choix des préférences MP"""
    
    def __init__(self, bot, target_user):
        super().__init__(timeout=604800)  # 7 jours en secondes
        self.bot = bot
        self.target_user = target_user
        self.user_id = target_user.id
        
        # Définir les boutons
        self.enable_btn = discord.ui.Button(label="✅ Activer", style=discord.ButtonStyle.success, custom_id="mp_enable")
        self.disable_btn = discord.ui.Button(label="❌ Désactiver", style=discord.ButtonStyle.danger, custom_id="mp_disable")
        
        # Ajouter les callbacks
        self.enable_btn.callback = self.enable_mp
        self.disable_btn.callback = self.disable_mp
        
        # Ajouter les boutons à la vue
        self.add_item(self.enable_btn)
        self.add_item(self.disable_btn)
        
        # Mettre à jour l'état visuel des boutons
        self.update_buttons()
    
    def update_buttons(self):
        """Met à jour l'état (grisé ou non) des boutons selon le statut actuel"""
        current_status = MPManager.get_mp_preference(self.user_id)
        
        if current_status:
            self.enable_btn.disabled = True
            self.disable_btn.disabled = False
        else:
            self.enable_btn.disabled = False
            self.disable_btn.disabled = True
    
    def get_description_text(self):
        """Retourne le texte de description mis à jour"""
        current_status = MPManager.get_mp_preference(self.user_id)
        status_text = "✅ **Activés**" if current_status else "❌ **Désactivés**"
        
        desc = f"**État actuel :** {status_text}\n\n"
        desc += "Recevez en privé les notifications liées à votre aventure :\n"
        desc += "📦 **Nouvelle carte** obtenue\n"
        desc += "💰 **Achat ou vente** sur le marché\n"
        desc += "⚔️ **Résultat PvP** et récapitulatif\n"
        desc += "🏆 **Succès accompli**\n"
        desc += "⬆️ **Passage de niveau**\n"
        desc += "🎁 **Récompense obtenue**\n\n"
        desc += "Choisissez si vous souhaitez activer ou désactiver ces notifications :"
        
        return desc

    def create_embed(self, context_or_interaction):
        """Crée l'embed selon le statut actuel"""
        
        # Gérer la différence entre ctx (commande) et interaction (bouton)
        guild = context_or_interaction.guild
        user = getattr(context_or_interaction, 'author', getattr(context_or_interaction, 'user', None))
        
        description = self.get_description_text()
        
        if config_manager:
            try:
                target_id = guild.id if guild else None
                embed = config_manager.get_formatted_embed(
                    guild, user, self.bot,
                    title="📬 Gestion des Messages Privés",
                    target_id=target_id
                )
                embed.description = description
                return embed
            except Exception as e:
                print(f"[mp.py] Erreur config_manager: {e}")
        
        # Fallback si config_manager n'est pas disponible ou plante
        embed = discord.Embed(
            title="📬 Gestion des Messages Privés",
            description=description,
            color=0x5865F2
        )
        return embed
    
    async def enable_mp(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Ce n'est pas votre menu !", ephemeral=True)
        
        MPManager.set_mp_preference(self.user_id, True)
        self.update_buttons()
        
        embed = self.create_embed(interaction)
        await interaction.response.edit_message(embed=embed, view=self)
    
    async def disable_mp(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Ce n'est pas votre menu !", ephemeral=True)
        
        MPManager.set_mp_preference(self.user_id, False)
        self.update_buttons()
        
        embed = self.create_embed(interaction)
        await interaction.response.edit_message(embed=embed, view=self)


class MP(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="choicemp")
    async def mp(self, ctx: commands.Context):
        """Gérer vos préférences de messages privés"""
        
        # Ordre corrigé : bot, puis utilisateur
        view = MPView(self.bot, ctx.author)
        embed = view.create_embed(ctx)
        
        await ctx.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(MP(bot))