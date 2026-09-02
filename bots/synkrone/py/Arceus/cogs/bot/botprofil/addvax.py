import discord
from discord.ext import commands, tasks
from colorama import Fore, Style, init
from datetime import datetime
from pathlib import Path
import os
import json
import asyncio
from typing import Optional

# --- Configuration & Imports ---
try:
    from .util_embed import EmbedManager
except ImportError:
    # Simule le manager si absent pour éviter les crashs de démarrage
    class EmbedManager:
        @staticmethod
        async def create(bot): return EmbedManager()
        async def _compute_unique_member_count(self): return 0
        async def get_stats_embed(self, guild): 
            embed = discord.Embed(title="Stats Vax")
            return embed, None, None  # Retourne None pour la vue

init(autoreset=True)

# Constantes de configuration
GUILD_ID = 1368235294192570520
CATEGORY_ID = 1368622083093037066  # Optionnel : catégorie où créer le salon
UPDATE_INTERVAL = 120  # Mis à jour à 120 secondes (2 minutes)
JSON_FILE = Path(__file__).parent / "addvax.json"

# Dictionnaire pour stocker les canaux par serveur
channel_ids = {}

class BotConnexion(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.embed_manager = None
        self.target_message_id = self._load_json_data()

    def _load_json_data(self) -> dict:
        """Charge les données sauvegardées"""
        if not JSON_FILE.exists():
            return {}
        try:
            with open(JSON_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"{Fore.RED}[JSON ERROR] Impossible de lire le fichier : {e}")
            return {}

    def _save_json_data(self, guild_id: int, channel_id: int, message_id: int):
        """Sauvegarde les données pour le prochain démarrage"""
        try:
            data = self._load_json_data()
            data[str(guild_id)] = {
                "channel_id": channel_id,
                "message_id": message_id
            }
            with open(JSON_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            pass

    @commands.Cog.listener()
    async def on_ready(self):
        """Déclencheur principal au démarrage"""
        # Initialisation du manager d'embed
        if not self.embed_manager:
            self.embed_manager = await EmbedManager.create(self.bot)

        # 2. Vérification / Création de l'environnement
        channel = await self.ensure_environment()
        
        if channel:
            # 3. Premier déploiement immédiat
            await self.refresh_status_message(channel)
            
            # 4. Lancement de la boucle de 2 minutes (si pas déjà lancée)
            if not self.update_loop.is_running():
                self.update_loop.start()

    async def ensure_environment(self) -> Optional[discord.TextChannel]:
        """Crée un nouveau salon pour les statistiques"""
        try:
            guild = self.bot.get_guild(GUILD_ID)
            if not guild:
                return None

            # Vérifier si le bot a les permissions nécessaires
            if not guild.me.guild_permissions.manage_channels:
                return None

            # Vérifier si on a déjà un salon pour ce serveur
            data = self._load_json_data()
            guild_data = data.get(str(guild.id), {})
            
            # Vérifier si le salon existe déjà
            if 'channel_id' in guild_data:
                channel = guild.get_channel(guild_data['channel_id'])
                if channel:
                    self.target_message_id = guild_data.get('message_id')
                    return channel
            
            # Si on arrive ici, on doit créer un nouveau salon
            try:
                # Vérifier si la catégorie existe
                category = guild.get_channel(CATEGORY_ID) if CATEGORY_ID else None
                
                # Vérifier si le bot peut créer un salon
                if not guild.me.guild_permissions.manage_channels:
                    return None

                # Créer les permissions
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(
                        read_messages=True,    # Peut voir le salon
                        send_messages=False,   # Ne peut pas envoyer de messages
                        add_reactions=False,   # Ne peut pas ajouter de réactions
                        create_public_threads=False,  # Ne peut pas créer de fils publics
                        create_private_threads=False, # Ne peut pas créer de fils privés
                        send_messages_in_threads=False, # Ne peut pas envoyer de messages dans les fils
                        use_application_commands=False  # Ne peut pas utiliser les commandes d'application
                    ),
                    guild.me: discord.PermissionOverwrite(
                        read_messages=True,
                        send_messages=True,
                        embed_links=True,
                        read_message_history=True,
                        manage_messages=True
                    )
                }

                # Créer le salon avec le nom du bot
                bot_name = self.bot.user.name.lower().replace(' ', '-')[:20]  # Limiter à 20 caractères
                channel_name = f"➕│{bot_name}"
                
                channel = await guild.create_text_channel(
                    name=channel_name,
                    category=category if isinstance(category, discord.CategoryChannel) else None,
                    overwrites=overwrites,
                    reason="Initialisation automatique Vax 1.4"
                )
                
                return channel
                
            except (discord.Forbidden, discord.HTTPException, Exception):
                return None
                
        except Exception:
            return None

    async def refresh_status_message(self, channel: discord.TextChannel):
        """Gère la création ou l'édition du message de statistiques"""
        guild = channel.guild
        embed, file, view = await self.embed_manager.get_stats_embed(guild)

        # Charger les données existantes
        data = self._load_json_data()
        guild_data = data.get(str(guild.id), {})

        if guild_data.get('message_id'):
            try:
                # Tentative d'édition du message existant
                message = await channel.fetch_message(guild_data['message_id'])
                await message.edit(embed=embed, view=view)
                print(f"[SUCCESS] Message {guild_data['message_id']} mis à jour avec succès")
                return
            except discord.NotFound:
                print(f"[INFO] Message {guild_data.get('message_id')} non trouvé, création d'un nouveau message")
            except discord.Forbidden:
                print(f"[ERROR] Permission refusée pour modifier le message {guild_data.get('message_id')}")
            except Exception as e:
                print(f"[ERROR] Erreur lors de la modification du message {guild_data.get('message_id')}: {e}")

        # Si on arrive ici, il faut créer un nouveau message
        await self._send_new_message(channel, embed, file, view)

    async def _send_new_message(self, channel, embed, file, view):
        """Sous-méthode pour envoyer un nouveau message et enregistrer l'ID"""
        try:
            print(f"[INFO] Création d'un nouveau message de statistiques")
            msg = await channel.send(embed=embed, view=view)
            # Mettre à jour les données
            self.target_message_id = msg.id
            self._save_json_data(channel.guild.id, channel.id, msg.id)
            print(f"[SUCCESS] Nouveau message {msg.id} créé et sauvegardé")
        except Exception as e:
            print(f"{Fore.RED}[ERROR] Erreur lors de la création du message : {e}")

    @tasks.loop(seconds=UPDATE_INTERVAL)
    async def update_loop(self):
        """Boucle de mise à jour toutes les 2 minutes"""
        try:
            guild = self.bot.get_guild(GUILD_ID)
            if not guild:
                return
                
            # Charger les données du salon
            data = self._load_json_data()
            guild_data = data.get(str(guild.id), {})
            
            if 'channel_id' in guild_data:
                channel = guild.get_channel(guild_data['channel_id'])
                if channel:
                    # Mise à jour du message
                    await self.refresh_status_message(channel)
        except Exception as e:
            print(f"{Fore.RED}[LOOP ERROR] Erreur dans la boucle de 2min : {e}")

    @update_loop.before_loop
    async def before_update_loop(self):
        """Attend que le bot soit prêt avant de lancer la boucle"""
        await self.bot.wait_until_ready()

    def cog_unload(self):
        """Arrête proprement la tâche quand le cog est déchargé"""
        self.update_loop.cancel()

async def setup(bot):
    await bot.add_cog(BotConnexion(bot))