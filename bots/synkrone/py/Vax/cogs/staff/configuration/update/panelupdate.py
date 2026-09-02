HAS_CUSTOM_EMBED = True  # Défini par défaut pour éviter l'erreur de variable non définie
import discord
import json
import os
import asyncio
import logging
from discord import app_commands, ui
from discord.ext import commands, tasks

# Configuration du logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('PanelUpdate')

try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# Import de get_themed_embed depuis update.py
try:
    from .update import get_themed_embed
    logger.debug("get_themed_embed importé depuis update.py")
except ImportError:
    logger.warning("get_themed_embed non disponible, utilisation de l'embed par défaut")
    get_themed_embed = None

# --- CONFIGURATION DEV ---
DEV_GUILD_ID = 1368235294192570520
DEV_PANEL_CHANNEL_ID = 1472403276535304274
DEV_ALLOWED_ROLE_ID = 1369430431212114002

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
DEV_JSON_PATH = os.path.join(DATA_DIR, "dev.json")

# --- UTILS ---
def load_dev_config():
    logger.debug(f"Tentative de chargement de la config depuis: {DEV_JSON_PATH}")
    if os.path.exists(DEV_JSON_PATH):
        try:
            with open(DEV_JSON_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
                logger.debug(f"Config chargée avec succès: {config}")
                return config
        except Exception as e:
            logger.error(f"Erreur lors du chargement de la config: {e}")
            return {"draft_version": "", "draft_devlog": "", "panel_msg_id": None}
    else:
        logger.warning(f"Fichier de config non trouvé: {DEV_JSON_PATH}")
        return {"draft_version": "", "draft_devlog": "", "panel_msg_id": None}

def save_dev_config(data):
    logger.debug(f"Tentative de sauvegarde de la config: {data}")
    if not os.path.exists(DATA_DIR):
        logger.info(f"Création du dossier data: {DATA_DIR}")
        os.makedirs(DATA_DIR)
    try:
        with open(DEV_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        logger.debug("Config sauvegardée avec succès")
    except Exception as e:
        logger.error(f"Erreur lors de la sauvegarde de la config: {e}")

def check_permission(user, guild):
    """Vérifie si l'utilisateur est Owner ou a le rôle spécifique"""
    logger.debug(f"Vérification des permissions pour user: {user.id} ({user.name}) dans guild: {guild.id}")
    
    if user.id == guild.owner_id:
        logger.debug("Permission accordée: utilisateur est owner")
        return True
    
    user_roles = [role.id for role in user.roles]
    logger.debug(f"Rôles de l'utilisateur: {user_roles}")
    logger.debug(f"Rôle requis: {DEV_ALLOWED_ROLE_ID}")
    
    if DEV_ALLOWED_ROLE_ID in user_roles:
        logger.debug("Permission accordée: utilisateur a le rôle requis")
        return True
    
    logger.debug("Permission refusée")
    return False

# --- MODAL ÉDITION ---
class UpdateEditModal(ui.Modal, title="Éditer l'Update"):
    version = ui.TextInput(label="Version", placeholder="v1.0.0", max_length=15)
    devlog = ui.TextInput(label="Devlog", style=discord.TextStyle.paragraph, placeholder="Détails de la mise à jour...", required=True)

    def __init__(self, bot, view_instance):
        super().__init__()
        self.bot = bot
        self.view_instance = view_instance
        config = load_dev_config()
        self.version.default = config.get("draft_version", "")
        self.devlog.default = config.get("draft_devlog", "")

    async def on_submit(self, interaction: discord.Interaction):
        logger.debug(f"Modal soumis par {interaction.user.id}: version='{self.version.value}', devlog='{self.devlog.value[:50]}...'")
        try:
            config = load_dev_config()
            config["draft_version"] = self.version.value
            config["draft_devlog"] = self.devlog.value
            save_dev_config(config)
            logger.debug("Brouillon sauvegardé, mise à jour de l'affichage")
            await self.view_instance.update_draft_display(interaction)
            await interaction.followup.send("✅ Brouillon sauvegardé !", ephemeral=True)
            logger.debug("Modal traité avec succès")
        except Exception as e:
            logger.error(f"Erreur dans on_submit: {e}")
            await interaction.followup.send("❌ Erreur lors de la sauvegarde", ephemeral=True)

# --- VUE DU BROUILLON ---
class DraftControlView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.confirm_step = 0

    async def update_draft_display(self, interaction: discord.Interaction):
        logger.debug(f"Mise à jour de l'affichage du brouillon pour {interaction.user.id}")
        try:
            config = load_dev_config()
            logger.debug(f"Config pour l'affichage: {config}")
            
            embed = discord.Embed(
                title=f"{self.bot.user.name} - Mise à jour {config.get('draft_version', 'vX.X')}",
                description=config.get("draft_devlog", "Pas de contenu"),
                color=0x3498db
            )
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            
            logger.debug(f"HAS_CUSTOM_EMBED: {HAS_CUSTOM_EMBED}, config_manager: {config_manager is not None}")
            if config_manager:
                logger.debug("Application du formatage custom embed")
                formatted = config_manager.get_formatted_embed(interaction.guild, interaction.user, self.bot, embed.title, embed.description, interaction.guild.id)
                embed = formatted
                embed.set_thumbnail(url=self.bot.user.display_avatar.url)
                logger.debug("Embed custom appliqué")

            if not interaction.response.is_done():
                logger.debug("Response pas encore faite, utilisation de response.edit_message")
                await interaction.response.edit_message(embed=embed, view=self)
            else:
                logger.debug("Response déjà faite, utilisation de edit_original_response")
                await interaction.edit_original_response(embed=embed, view=self)
            
            logger.debug("Affichage du brouillon mis à jour avec succès")
        except Exception as e:
            logger.error(f"Erreur dans update_draft_display: {e}")
            raise

    @ui.button(emoji="✏️", label="Éditer", style=discord.ButtonStyle.secondary, custom_id="draft_edit")
    async def edit_btn(self, interaction: discord.Interaction, button: ui.Button):
        logger.debug(f"Bouton éditer cliqué par {interaction.user.id}")
        try:
            await interaction.response.send_modal(UpdateEditModal(self.bot, self))
            logger.debug("Modal d'édition envoyé")
        except Exception as e:
            logger.error(f"Erreur dans edit_btn: {e}")

    @ui.button(emoji="📤", label="Envoyer", style=discord.ButtonStyle.success, custom_id="draft_send")
    async def send_btn(self, interaction: discord.Interaction, button: ui.Button):
        logger.debug(f"Bouton envoyer cliqué par {interaction.user.id}, confirm_step: {self.confirm_step}")
        
        if self.confirm_step == 0:
            logger.debug("Première confirmation demandée")
            self.confirm_step = 1
            button.label = "Êtes-vous sûr ?"
            button.style = discord.ButtonStyle.danger
            await interaction.response.edit_message(view=self)
            await asyncio.sleep(3)
            if self.confirm_step == 1:
                self.confirm_step = 0
                button.label = "Envoyer"
                button.style = discord.ButtonStyle.success
                try: 
                    await interaction.edit_original_response(view=self)
                    logger.debug("Timeout de confirmation, bouton réinitialisé")
                except: 
                    logger.warning("Erreur lors de la réinitialisation du bouton après timeout")
            return

        if self.confirm_step == 1:
            logger.debug("Deuxième confirmation demandée")
            self.confirm_step = 2
            button.label = "Vraiment sûr (Irréversible) ?"
            await interaction.response.edit_message(view=self)
            return

        if self.confirm_step == 2:
            logger.debug("Confirmation finale, envoi de l'update")
            await interaction.response.defer()
            config = load_dev_config()
            logger.debug(f"Config pour envoi: {config}")
            
            if not os.path.exists(DATA_DIR):
                logger.error(f"Dossier data inexistant: {DATA_DIR}")
                await interaction.followup.send("❌ Aucune configuration trouvée", ephemeral=True)
                return
                
            server_files = [f for f in os.listdir(DATA_DIR) if f.endswith(".json") and f != "dev.json"]
            logger.debug(f"Fichiers serveur trouvés: {server_files}")
            
            if not server_files:
                logger.warning("Aucun fichier serveur trouvé")
                await interaction.followup.send("❌ Aucun serveur configuré", ephemeral=True)
                return
            
            # Embed de base pour l'envoi
            embed = discord.Embed(
                title=f"{self.bot.user.name} - Mise à jour {config.get('draft_version')}",
                description=config.get('draft_devlog'),
                color=0x5865F2
            )
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            
            count = 0
            dm_lines = []
            for filename in server_files:
                logger.debug(f"Traitement du fichier: {filename}")
                try:
                    with open(os.path.join(DATA_DIR, filename), "r") as f:
                        data = json.load(f)
                    logger.debug(f"Données chargées pour {filename}: {data}")
                    
                    guild_id = int(filename.replace(".json", ""))
                    guild = self.bot.get_guild(guild_id)
                    logger.debug(f"Guild {guild_id}: {guild.name if guild else 'Non trouvé'}")
                    if not guild: 
                        logger.warning(f"Guild {guild_id} non trouvé, passage au suivant")
                        continue

                    channel = guild.get_channel(data.get("channel_id"))
                    logger.debug(f"Channel trouvé: {channel.name if channel else 'Non trouvé'} (ID: {data.get('channel_id')})")
                    notified = False
                    if channel:
                        role_id = data.get("role_id")
                        content = f"<@&{role_id}>" if role_id else None
                        logger.debug(f"Content à envoyer: {content}")
                        
                        final_embed = embed
                        if config_manager:
                            logger.debug("Application du formatage custom pour l'envoi")
                            final_embed = config_manager.get_formatted_embed(guild, guild.me, self.bot, embed.title, embed.description, guild.id)
                            final_embed.set_thumbnail(url=self.bot.user.display_avatar.url)
                            logger.debug("Embed custom appliqué pour l'envoi")

                        await channel.send(content=content, embed=final_embed)
                        logger.debug(f"Message envoyé avec succès dans {channel.name}")
                        count += 1
                        notified = bool(role_id)
                        if notified:
                            dm_lines.append(f"`{guild.name}` a reçu l'update & a été notifié.")
                        else:
                            dm_lines.append(f"`{guild.name}` a reçu l'update.")
                    else:
                        logger.warning(f"Channel non trouvé pour le serveur {guild.name}")
                except Exception as e:
                    logger.error(f"Erreur envoi update vers {filename}: {e}")
                    import traceback
                    logger.error(traceback.format_exc())

            # Envoi du récapitulatif en DM à l'utilisateur
            try:
                user = interaction.user
                if dm_lines:
                    msg = "\n".join(dm_lines)
                else:
                    msg = "Aucun serveur n'a reçu l'update."
                await user.send(f"Récapitulatif de l'update :\n{msg}")
            except Exception as e:
                logger.error(f"Erreur lors de l'envoi du DM récapitulatif : {e}")

            await interaction.followup.send(f"✅ Update déployée sur {count} serveurs !", ephemeral=True)
            self.confirm_step = 0
            button.label = "Envoyer"
            button.style = discord.ButtonStyle.success

# --- VUE DU PANEL PRINCIPAL ---
class PanelView(ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @ui.button(label="Nouveau / Brouillon", style=discord.ButtonStyle.primary, custom_id="panel_new_draft")
    async def new_draft(self, interaction: discord.Interaction, button: ui.Button):
        logger.debug(f"Bouton nouveau brouillon cliqué par {interaction.user.id}")
        
        # Utilisation de la fonction de vérification centralisée
        if not check_permission(interaction.user, interaction.guild):
            logger.warning(f"Permission refusée pour {interaction.user.id}")
            return await interaction.response.send_message("❌ Accès refusé : Rôle manquant.", ephemeral=True)

        logger.debug("Permission accordée, chargement de la config")
        config = load_dev_config()
        logger.debug(f"Config pour le brouillon: {config}")
        
        embed = discord.Embed(
            title=f"Brouillon : {config.get('draft_version', 'vX.X')}",
            description=config.get('draft_devlog', "Vide..."),
            color=0x95a5a6
        )
        embed.add_field(name="Lien Panel", value=f"[Retour au Panel](https://discord.com/channels/{DEV_GUILD_ID}/{DEV_PANEL_CHANNEL_ID})")
        
        view = DraftControlView(self.bot)
        try:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            logger.debug("Brouillon envoyé avec succès")
        except Exception as e:
            logger.error(f"Erreur lors de l'envoi du brouillon: {e}")

# --- COG ---
class PanelUpdate(commands.Cog):
    def __init__(self, bot):
        logger.debug("Initialisation du cog PanelUpdate")
        self.bot = bot
        self.update_stats_task.start()
        logger.debug("Tâche de stats démarrée")

    def cog_unload(self):
        self.update_stats_task.cancel()

    async def get_stats(self):
        logger.debug("Récupération des statistiques")
        if not os.path.exists(DATA_DIR):
            logger.warning(f"Dossier data inexistant: {DATA_DIR}")
            return {"servers_active": 0, "roles_active": 0, "unique_users": 0, "total_guilds": len(self.bot.guilds)}
            
        server_files = [f for f in os.listdir(DATA_DIR) if f.endswith(".json") and f != "dev.json"]
        logger.debug(f"Fichiers serveur pour stats: {server_files}")
        
        total_servers_active = 0
        total_roles_active = 0
        unique_users = set()

        for filename in server_files:
            try:
                guild_id = int(filename.replace(".json", ""))
                logger.debug(f"Stats pour guild {guild_id}")
                with open(os.path.join(DATA_DIR, filename), "r") as f:
                    data = json.load(f)
                logger.debug(f"Données stats: {data}")
                
                if data.get("channel_id"):
                    total_servers_active += 1
                    logger.debug(f"Serveur {guild_id} a un channel actif")
                
                if data.get("role_id"):
                    total_roles_active += 1
                    logger.debug(f"Serveur {guild_id} a un rôle actif")
                    guild = self.bot.get_guild(guild_id)
                    if guild:
                        role = guild.get_role(data["role_id"])
                        if role:
                            for member in role.members:
                                unique_users.add(member.id)
                            logger.debug(f"Rôle {role.name} a {len(role.members)} membres")
            except Exception as e:
                logger.error(f"Erreur stats pour {filename}: {e}")
                continue
        
        stats_result = {
            "servers_active": total_servers_active,
            "roles_active": total_roles_active,
            "unique_users": len(unique_users),
            "total_guilds": len(self.bot.guilds)
        }
        logger.debug(f"Stats finales: {stats_result}")
        return stats_result

    @tasks.loop(hours=1)
    async def update_stats_task(self):
        logger.debug("Début de la tâche de mise à jour des stats")
        dev_config = load_dev_config()
        msg_id = dev_config.get("panel_msg_id")
        logger.debug(f"Panel msg ID: {msg_id}")
        if not msg_id: 
            logger.debug("Pas de panel_msg_id, arrêt de la tâche")
            return

        channel = self.bot.get_channel(DEV_PANEL_CHANNEL_ID)
        logger.debug(f"Channel trouvé: {channel.name if channel else 'Non trouvé'}")
        if not channel: 
            logger.warning("Channel panel non trouvé")
            return

        try:
            msg = await channel.fetch_message(msg_id)
            logger.debug(f"Message panel récupéré: {msg.id}")
            stats = await self.get_stats()
            logger.debug(f"Stats récupérées: {stats}")
            
            embed = msg.embeds[0] if msg.embeds else discord.Embed(title="Panel Update")
            embed.description = (
                f"### 📊 Statistiques Live\n"
                f"- **Serveurs configurés :** `{stats['servers_active']}` / `{stats['total_guilds']}`\n"
                f"- **Rôles activés :** `{stats['roles_active']}`\n"
                f"- **Portée (utilisateurs uniques) :** `{stats['unique_users']}`\n"
            )
            embed.timestamp = discord.utils.utcnow()
            
            # Vérifie que le message appartient bien au bot avant d'éditer
            if msg.author.id == self.bot.user.id:
                await msg.edit(embed=embed, view=PanelView(self.bot))
                logger.debug("Panel mis à jour avec succès")
            else:
                # Le message appartient à un autre utilisateur, on en crée un nouveau
                logger.warning("Le message panel n'appartient pas au bot — création d'un nouveau message.")
                try:
                    await msg.delete()
                except Exception:
                    pass
                new_msg = await channel.send(embed=embed, view=PanelView(self.bot))
                # Sauvegarde du nouvel ID
                config = load_dev_config()
                config["panel_msg_id"] = new_msg.id
                save_dev_config(config)
                logger.debug("Nouveau panel créé avec succès")
        except Exception as e:
            logger.error(f"Erreur update task panel: {e}")
            import traceback
            logger.error(traceback.format_exc())

    @update_stats_task.before_loop
    async def before_task(self):
        await self.bot.wait_until_ready()
        # Création automatique du panel une fois le bot prêt
        await self.create_panel_if_needed()

    async def create_panel_if_needed(self):
        """Crée automatiquement le panel s'il n'existe pas"""
        logger.debug("Vérification de la création automatique du panel")
        
        # Attendre que le bot soit complètement prêt
        await asyncio.sleep(5)
        
        try:
            # Récupérer le guild et le salon
            guild = self.bot.get_guild(DEV_GUILD_ID)
            if not guild:
                logger.error(f"Guild de développement {DEV_GUILD_ID} non trouvé")
                return
            
            logger.debug(f"Guild trouvé: {guild.name}")
            
            channel = self.bot.get_channel(DEV_PANEL_CHANNEL_ID)
            if not channel:
                logger.error(f"Channel de panel {DEV_PANEL_CHANNEL_ID} non trouvé dans le guild {guild.name}")
                return
            
            logger.debug(f"Channel trouvé: {channel.name}")
            
            # Vérifier si un panel existe déjà
            config = load_dev_config()
            existing_msg_id = config.get("panel_msg_id")
            
            if existing_msg_id:
                logger.debug(f"Vérification du message panel existant: {existing_msg_id}")
                try:
                    existing_msg = await channel.fetch_message(existing_msg_id)
                    logger.debug("Panel existant trouvé et valide, pas de création nécessaire")
                    return
                except discord.NotFound:
                    logger.warning("Message panel existant non trouvé, création d'un nouveau panel")
                except discord.Forbidden:
                    logger.error("Permission refusée pour accéder au message panel existant")
                    return
                except Exception as e:
                    logger.error(f"Erreur lors de la vérification du message panel: {e}")
                    return
            
            # Création du nouveau panel
            logger.info("Création d'un nouveau panel de mise à jour")
            
            stats = await self.get_stats()
            logger.debug(f"Stats pour le nouveau panel: {stats}")
            
            desc = (
                f"### 📊 Statistiques Live\n"
                f"- **Serveurs configurés :** `{stats['servers_active']}` / `{stats['total_guilds']}`\n"
                f"- **Rôles activés :** `{stats['roles_active']}`\n"
                f"- **Portée (utilisateurs uniques) :** `{stats['unique_users']}`\n"
            )

            embed = await get_themed_embed(self.bot, guild, guild.me, desc) if get_themed_embed else discord.Embed(
                description=desc,
                color=0x2ecc71
            )
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            
            logger.debug("Embed du panel créé, tentative d'envoi")
            
            try:
                msg = await channel.send(embed=embed, view=PanelView(self.bot))
                logger.info(f"✅ Panel créé avec succès! Message ID: {msg.id}")
                logger.info(f"✅ Panel envoyé dans le salon {channel.name} (ID: {channel.id})")
                logger.info(f"✅ Guild: {guild.name} (ID: {guild.id})")
                
                # Sauvegarder l'ID du message
                config["panel_msg_id"] = msg.id
                save_dev_config(config)
                logger.info(f"✅ ID du message panel sauvegardé: {msg.id}")
                
            except discord.Forbidden:
                logger.error("❌ Permission refusée: le bot ne peut pas envoyer de messages dans ce salon")
                logger.error(f"❌ Vérifiez que le bot a la permission 'Envoyer des messages' dans {channel.name}")
            except discord.HTTPException as e:
                logger.error(f"❌ Erreur HTTP lors de l'envoi du panel: {e}")
                logger.error(f"❌ Code d'erreur: {e.status} si disponible")
            except Exception as e:
                logger.error(f"❌ Erreur inattendue lors de la création du panel: {e}")
                import traceback
                logger.error(f"❌ Traceback complet: {traceback.format_exc()}")
                
        except Exception as e:
            logger.error(f"❌ Erreur critique dans create_panel_if_needed: {e}")
            import traceback
            logger.error(f"❌ Traceback: {traceback.format_exc()}")

async def setup(bot):
    logger.debug("Setup du cog PanelUpdate")
    try:
        await bot.add_cog(PanelUpdate(bot))
        logger.debug("Cog PanelUpdate ajouté avec succès")
    except Exception as e:
        logger.error(f"Erreur lors du setup du cog PanelUpdate: {e}")
        import traceback
        logger.error(traceback.format_exc())
        raise