import discord
import json
import asyncio
import traceback
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from discord.ext import commands, tasks
from discord import app_commands, ui, File

# ==============================================================================
# --------------------------- CONFIGURATION & UTILS ----------------------------
# ==============================================================================

# Tentative d'importation du gestionnaire de configuration unifié
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / 'data' / 'boosters'
THUMBNAIL_PATH = BASE_DIR / "thumbnail.gif"
IMAGE_PATH = BASE_DIR / "image.gif"
BOOSTER_COLOR = 0xFF73FA

def parse_time_to_seconds(time_str: str) -> int:
    """Convertit une chaîne de temps (ex: 5m, 1h, 2j) en secondes. Minimum 60s."""
    time_str = time_str.strip().lower()
    if not time_str:
        return 600  # Par défaut 10 minutes

    multipliers = {'s': 1, 'm': 60, 'h': 3600, 'j': 86400, 'd': 86400}
    try:
        if time_str[-1] in multipliers:
            val = int(time_str[:-1]) * multipliers[time_str[-1]]
        else:
            val = int(time_str) * 60  # On assume des minutes par défaut
        return max(60, val)  # Forcer un minimum de 60 secondes (1 minute)
    except ValueError:
        return 600

def format_seconds(seconds: int) -> str:
    """Convertit des secondes en format lisible."""
    if seconds >= 86400: return f"{seconds // 86400} jour(s)"
    if seconds >= 3600: return f"{seconds // 3600} heure(s)"
    if seconds >= 60: return f"{seconds // 60} minute(s)"
    return f"{seconds} seconde(s)"

# ==============================================================================
# ----------------------------- INTERFACES UI ----------------------------------
# ==============================================================================

class BoosterConfigModal(ui.Modal, title='⚙️ Configuration des Boosters'):
    """Modal permettant de configurer l'ID du salon et le délai."""
    
    channel_input = ui.TextInput(
        label='ID du salon (Laisser vide = création auto)',
        placeholder='Ex: 1234567891011121314',
        required=False,
        max_length=25
    )
    
    cooldown_input = ui.TextInput(
        label='Fréquence de MAJ (s/m/h/j)',
        placeholder='Ex: 10m, 1h, 1j (Min: 1m)',
        default='10m',
        required=True,
        max_length=10
    )

    def __init__(self, cog: commands.Cog, guild_id: int, view: ui.View):
        super().__init__()
        self.cog = cog
        self.guild_id = guild_id
        self.parent_view = view

        # Préremplir si existant
        config = self.cog.load_config(self.guild_id)
        if config.get('channel_id'):
            self.channel_input.default = str(config['channel_id'])
        self.cooldown_input.default = format_seconds(config.get('cooldown', 600)).replace(' minute(s)', 'm').replace(' heure(s)', 'h')

    async def on_submit(self, interaction: discord.Interaction):
        config = self.cog.load_config(self.guild_id)
        
        # 1. Gestion du Cooldown
        seconds = parse_time_to_seconds(self.cooldown_input.value)
        config['cooldown'] = seconds
        
        # 2. Gestion de l'ID du salon
        chan_val = self.channel_input.value.strip()
        msg_extra = ""
        if chan_val.isdigit():
            chan = interaction.guild.get_channel(int(chan_val))
            if isinstance(chan, discord.TextChannel):
                config['channel_id'] = chan.id
                msg_extra = f"Salon défini sur {chan.mention}. "
            else:
                msg_extra = "⚠️ L'ID fourni n'est pas un salon texte valide. L'ancien paramètre est conservé. "
        elif not chan_val and config.get('channel_id'):
            # L'utilisateur a vidé le champ : on retire l'ID pour déclencher une création auto à l'activation
            config['channel_id'] = None
            msg_extra = "Salon réinitialisé (sera créé lors de l'activation). "

        # On force la mise à jour immédiate au prochain cycle
        config['last_update'] = 0 
        self.cog.save_config(self.guild_id, config)

        await interaction.response.send_message(f"✅ Configuration sauvegardée. {msg_extra}Fréquence : {format_seconds(seconds)}.", ephemeral=True)
        # On met à jour l'embed du panel de contrôle
        await self.parent_view.update_panel(interaction)

class BoosterControlView(ui.View):
    """Vue gérant l'activation et l'accès au Modal."""
    def __init__(self, cog: commands.Cog, guild_id: int, author_id: int):
        super().__init__(timeout=300.0)
        self.cog = cog
        self.guild_id = guild_id
        self.author_id = author_id
        self.update_buttons()

    def update_buttons(self):
        """Ajuste dynamiquement la couleur et le texte du bouton d'activation."""
        config = self.cog.load_config(self.guild_id)
        is_enabled = config.get('enabled', False)
        
        self.toggle_btn.label = "Désactiver" if is_enabled else "Activer"
        self.toggle_btn.style = discord.ButtonStyle.danger if is_enabled else discord.ButtonStyle.success
        self.toggle_btn.emoji = "🛑" if is_enabled else "✅"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Sécurité : Seul l'auteur peut interagir avec ce panel."""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Vous n'êtes pas autorisé à utiliser ce menu.", ephemeral=True)
            return False
        return True

    @ui.button(custom_id="btn_toggle", row=0)
    async def toggle_btn(self, interaction: discord.Interaction, button: ui.Button):
        config = self.cog.load_config(self.guild_id)
        current_state = config.get('enabled', False)
        
        if not current_state:
            # ACTIVATION
            guild = interaction.guild
            # Vérification du salon
            if not config.get('channel_id'):
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(send_messages=False),
                    guild.me: discord.PermissionOverwrite(send_messages=True, embed_links=True, attach_files=True, read_message_history=True)
                }
                channel = await guild.create_text_channel("🚀│𝑩𝒐𝒐𝒔𝒕", overwrites=overwrites)
                config['channel_id'] = channel.id
                
            config['enabled'] = True
            config['last_update'] = 0 # Force la MAJ immédiate
            self.cog.save_config(self.guild_id, config)
            await interaction.response.send_message("✨ Système de boosters activé !", ephemeral=True)
        else:
            # DÉSACTIVATION
            config['enabled'] = False
            self.cog.save_config(self.guild_id, config)
            await interaction.response.send_message("🛑 Système désactivé.", ephemeral=True)

        self.update_buttons()
        await self.update_panel(interaction, edit_response=False)

    @ui.button(label="Configurer", style=discord.ButtonStyle.primary, emoji="⚙️", row=0)
    async def config_btn(self, interaction: discord.Interaction, button: ui.Button):
        """Ouvre le Modal de configuration."""
        modal = BoosterConfigModal(self.cog, self.guild_id, self)
        await interaction.response.send_modal(modal)

    async def update_panel(self, interaction: discord.Interaction, edit_response=True):
        """Actualise l'embed du panel de contrôle avec les nouvelles valeurs."""
        config = self.cog.load_config(self.guild_id)
        statut_txt = "`🟢 Activé`" if config.get('enabled') else "`🔴 Désactivé`"
        salon_txt = f"<#{config['channel_id']}>" if config.get('channel_id') else "`Non configuré (Création auto)`"
        freq_txt = format_seconds(config.get('cooldown', 600))

        embed = discord.Embed(
            title="🚀 Administration des Boosters",
            description=(
                "Bienvenue dans le panneau de gestion des remerciements.\n\n"
                f"**Statut :** {statut_txt}\n"
                f"**Salon :** {salon_txt}\n"
                f"**Mise à jour :** Chaque {freq_txt}"
            ),
            color=BOOSTER_COLOR
        )
        if THUMBNAIL_PATH.exists():
            embed.set_thumbnail(url="attachment://thumb.gif")

        # Edit original message
        if edit_response:
            try:
                await interaction.edit_original_response(embed=embed, view=self)
            except:
                pass
        else:
            try:
                await interaction.message.edit(embed=embed, view=self)
            except:
                pass

# ==============================================================================
# --------------------------- MODULE BOOSTERS (COG) ----------------------------
# ==============================================================================

class BoostersModule(commands.Cog):
    """Cog gérant les remerciements dynamiques des Boosters Discord."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger('bot.boosters')
        self.configs: Dict[int, Dict[str, Any]] = {}
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    async def cog_load(self):
        """Initialisation."""
        self._load_all_configs()
        if not self.update_task_loop.is_running():
            self.update_task_loop.start()

    async def cog_unload(self):
        """Nettoyage."""
        self.update_task_loop.cancel()

    # --- GESTION DES DONNÉES (JSON & CACHE) ---

    def _load_all_configs(self):
        for file in DATA_DIR.glob("*.json"):
            try:
                self.load_config(int(file.stem))
            except Exception as e:
                self.logger.error(f"Erreur de chargement JSON: {e}")

    def load_config(self, guild_id: int) -> dict:
        if guild_id in self.configs:
            return self.configs[guild_id]

        file_path = DATA_DIR / f"{guild_id}.json"
        default_config = {
            "enabled": False, 
            "channel_id": None, 
            "message_id": None, 
            "cooldown": 600, 
            "last_update": 0
        }

        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    final_config = {**default_config, **data}
                    self.configs[guild_id] = final_config
                    return final_config
            except Exception:
                pass
        
        self.configs[guild_id] = default_config
        return default_config

    def save_config(self, guild_id: int, config: dict):
        self.configs[guild_id] = config
        file_path = DATA_DIR / f"{guild_id}.json"
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            self.logger.error(f"Erreur écriture JSON {guild_id}: {e}")

    # --- LOGIQUE D'AFFICHAGE & MISE À JOUR ---

    async def update_boosters_panel(self, guild: discord.Guild, channel: discord.TextChannel, config: dict):
        """Met à jour le message d'honneur (Édition silencieuse ou Suppression/Renvoi)."""
        try:
            boosters = guild.premium_subscribers
            boosters.sort(key=lambda x: x.premium_since)

            now_ts = int(datetime.now().timestamp())
            title = "✨ Tableau d'Honneur des Boosters"
            description = (
                f"Dernière mise à jour : <t:{now_ts}:R>\n\n"
                "Un immense merci à nos précieux boosters qui font vivre le serveur ! 🚀\n"
                "Votre soutien permet de débloquer des fonctionnalités exclusives."
            )

            if config_manager:
                embed = config_manager.get_formatted_embed(
                    guild=guild, user=self.bot.user, bot=self.bot,
                    title=title, description=description, target_id=guild.id
                )
            else:
                embed = discord.Embed(title=title, description=description, color=BOOSTER_COLOR)

            list_text = "".join([f"• {m.mention} • <t:{int(m.premium_since.timestamp())}:d>\n" for m in boosters[:25]])
            embed.add_field(
                name=f"🚀 Liste des contributeurs ({len(boosters)})",
                value=list_text if list_text else "*Aucun boost actif actuellement.*",
                inline=False
            )

            stats_text = (
                f"• Boosts actifs : **{guild.premium_subscription_count}**\n"
                f"• Niveau du serveur : **Niveau {guild.premium_tier}**"
            )
            embed.add_field(name="📊 Statistiques", value=stats_text, inline=False)

            files_to_send = []
            if THUMBNAIL_PATH.exists():
                files_to_send.append(File(str(THUMBNAIL_PATH), filename="thumb.gif"))
                embed.set_thumbnail(url="attachment://thumb.gif")
            if IMAGE_PATH.exists():
                files_to_send.append(File(str(IMAGE_PATH), filename="banner.gif"))
                embed.set_image(url="attachment://banner.gif")

            # Logique "Toujours Dernier Message"
            last_message = None
            async for msg in channel.history(limit=1):
                last_message = msg

            old_msg_id = config.get('message_id')
            
            if last_message and last_message.id == old_msg_id:
                # C'est déjà le dernier message, édition silencieuse
                await last_message.edit(embed=embed)
            else:
                # Nouveau message ou pas de message = suppression et renvoi
                if old_msg_id:
                    try:
                        old_msg = await channel.fetch_message(old_msg_id)
                        await old_msg.delete()
                    except discord.NotFound:
                        pass

                new_msg = await channel.send(embed=embed, files=files_to_send)
                config['message_id'] = new_msg.id
            
            # Mise à jour du timer
            config['last_update'] = int(time.time())
            self.save_config(guild.id, config)

        except Exception as e:
            self.logger.error(f"Erreur update_boosters_panel [{guild.id}]: {e}")

    # --- BOUCLE DE MISE À JOUR (Dynamique) ---

    @tasks.loop(minutes=1) # Vérification globale toutes les 1 minutes
    async def update_task_loop(self):
        """Vérifie si les serveurs ont dépassé leur propre cooldown."""
        await self.bot.wait_until_ready()
        current_time = int(time.time())

        for guild_id, config in list(self.configs.items()):
            if not config.get('enabled') or not config.get('channel_id'):
                continue
            
            last_update = config.get('last_update', 0)
            cooldown = config.get('cooldown', 600)

            # Si le délai est écoulé
            if current_time - last_update >= cooldown:
                guild = self.bot.get_guild(guild_id)
                if guild:
                    channel = guild.get_channel(config.get('channel_id'))
                    if channel:
                        await self.update_boosters_panel(guild, channel, config)
                        await asyncio.sleep(1) # Lissage API

    # --- ÉVÉNEMENTS (Instantanés) ---

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Détecte l'arrivée d'un nouveau booster (Mise à jour prioritaire)."""
        if before.premium_since is None and after.premium_since is not None:
            config = self.load_config(after.guild.id)
            if not config.get('enabled') or not config.get('channel_id'):
                return

            channel = after.guild.get_channel(config['channel_id'])
            if not channel: return

            title_celeb = "❤️ NOUVEAU BOOSTER !"
            desc_celeb = (
                f"Un immense merci à {after.mention} qui vient de booster le serveur !\n"
                f"Nous sommes maintenant à **{after.guild.premium_subscription_count}** boosts. ✨"
            )

            if config_manager:
                embed_celeb = config_manager.get_formatted_embed(
                    guild=after.guild, user=after, bot=self.bot,
                    title=title_celeb, description=desc_celeb, target_id=after.guild.id
                )
            else:
                embed_celeb = discord.Embed(title=title_celeb, description=desc_celeb, color=BOOSTER_COLOR)
            
            embed_celeb.set_author(name=after.display_name, icon_url=after.display_avatar.url)
            
            files_celeb = []
            if IMAGE_PATH.exists():
                files_celeb.append(File(str(IMAGE_PATH), filename="celebration.gif"))
                embed_celeb.set_image(url="attachment://celebration.gif")

            await channel.send(content=after.mention, embed=embed_celeb, files=files_celeb)
            
            # Attente de 3s puis forçage du panel en bas
            await asyncio.sleep(3)
            await self.update_boosters_panel(after.guild, channel, config)

    # --- COMMANDES (Admin) ---

    @commands.hybrid_command(name="boost", description="Configuration du système de boosters.")
    @commands.has_permissions(manage_guild=True)
    @app_commands.default_permissions(manage_guild=True)
    async def boost(self, ctx: commands.Context):
        """Interface hybride (Slash + Prefix) pour configurer le module."""
        await ctx.defer(ephemeral=True)
        
        config = self.load_config(ctx.guild.id)
        statut_txt = "`🟢 Activé`" if config.get('enabled') else "`🔴 Désactivé`"
        salon_txt = f"<#{config['channel_id']}>" if config.get('channel_id') else "`Non configuré (Création auto)`"
        freq_txt = format_seconds(config.get('cooldown', 600))
        
        embed = discord.Embed(
            title="🚀 Administration des Boosters",
            description=(
                "Bienvenue dans le panneau de gestion des remerciements.\n\n"
                f"**Statut :** {statut_txt}\n"
                f"**Salon :** {salon_txt}\n"
                f"**Mise à jour :** Chaque {freq_txt}"
            ),
            color=BOOSTER_COLOR
        )
        
        files_cfg = []
        if THUMBNAIL_PATH.exists():
            files_cfg.append(File(str(THUMBNAIL_PATH), filename="thumb.gif"))
            embed.set_thumbnail(url="attachment://thumb.gif")

        view = BoosterControlView(self, ctx.guild.id, ctx.author.id)
        await ctx.send(embed=embed, view=view, files=files_cfg, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(BoostersModule(bot))