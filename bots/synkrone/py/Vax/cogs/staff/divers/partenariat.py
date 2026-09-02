import discord
from discord import app_commands, ui
from discord.ext import commands
from typing import Dict, Any, Optional
import logging
import json
from pathlib import Path
import os
import traceback

# ==============================================================================
# --------------------------- CONFIGURATION & CHEMINS --------------------------
# ==============================================================================

EMBED_COLOR = 0x2ecc71 # Couleur par défaut (émeraude) pour le fallback
BASE_DIR = Path(__file__).parent
DB_DIR = BASE_DIR / "DB" / "partenariat"

# Tentative d'import du config_manager global
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# ==============================================================================
# --------------------------- INTERFACES UTILISATEUR ---------------------------
# ==============================================================================

class ChannelModal(ui.Modal, title="Configuration du Salon"):
    channel_id = ui.TextInput(
        label="ID du salon de partenariat",
        placeholder="Ex: 123456789101112131",
        style=discord.TextStyle.short,
        required=True,
        min_length=17,
        max_length=20
    )

    def __init__(self, view: "PartenariatView"):
        super().__init__()
        self.parent_view = view

    async def on_submit(self, interaction: discord.Interaction):
        if not self.channel_id.value.isdigit():
            return await interaction.response.send_message("❌ L'ID doit être composé uniquement de chiffres.", ephemeral=True)
        
        channel = interaction.guild.get_channel(int(self.channel_id.value))
        if not channel:
            return await interaction.response.send_message("❌ Impossible de trouver ce salon. Vérifiez l'ID.", ephemeral=True)

        self.parent_view.config["channel_id"] = int(self.channel_id.value)
        self.parent_view.cog.save_config_sync(interaction.guild.id, self.parent_view.config)
        await self.parent_view.update_embed(interaction)


class RoleModal(ui.Modal, title="Configuration de la Notification"):
    role_id = ui.TextInput(
        label="ID du rôle à mentionner",
        placeholder="Ex: 123456789101112131",
        style=discord.TextStyle.short,
        required=True,
        min_length=17,
        max_length=20
    )

    def __init__(self, view: "PartenariatView"):
        super().__init__()
        self.parent_view = view

    async def on_submit(self, interaction: discord.Interaction):
        if not self.role_id.value.isdigit():
            return await interaction.response.send_message("❌ L'ID doit être composé uniquement de chiffres.", ephemeral=True)
        
        role = interaction.guild.get_role(int(self.role_id.value))
        if not role:
            return await interaction.response.send_message("❌ Impossible de trouver ce rôle. Vérifiez l'ID.", ephemeral=True)

        self.parent_view.config["ping_type"] = "role"
        self.parent_view.config["ping_id"] = int(self.role_id.value)
        self.parent_view.cog.save_config_sync(interaction.guild.id, self.parent_view.config)
        await self.parent_view.update_embed(interaction)


class ContentModal(ui.Modal, title="Message du Partenariat"):
    content = ui.TextInput(
        label="Contenu de l'annonce",
        placeholder="Rédigez le texte de votre partenariat ici...",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=4000
    )

    def __init__(self, view: "PartenariatView"):
        super().__init__()
        self.parent_view = view
        # Pré-remplir si déjà configuré dans la session actuelle
        if self.parent_view.config.get("content"):
            self.content.default = self.parent_view.config["content"]

    async def on_submit(self, interaction: discord.Interaction):
        self.parent_view.config["content"] = self.content.value
        self.parent_view.cog.save_config_sync(interaction.guild.id, self.parent_view.config)
        await self.parent_view.update_embed(interaction)


class ConfirmView(ui.View):
    def __init__(self, parent_view: "PartenariatView", interaction_original: discord.Interaction):
        super().__init__(timeout=60)
        self.parent_view = parent_view
        self.interaction_original = interaction_original

    @ui.button(label="Confirmer l'envoi", style=discord.ButtonStyle.green, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        
        config = self.parent_view.config
        channel = interaction.guild.get_channel(config["channel_id"])
        
        # Formatage du ping
        ping_text = ""
        if config["ping_type"] == "here":
            ping_text = "@here\n"
        elif config["ping_type"] == "everyone":
            ping_text = "@everyone\n"
        elif config["ping_type"] == "role" and config.get("ping_id"):
            ping_text = f"<@&{config['ping_id']}>\n"

        final_content = f"{ping_text}{config['content']}"

        try:
            # Envoi dans le salon cible
            await channel.send(content=final_content)
            
            # Désactivation de la vue principale
            for child in self.parent_view.children:
                child.disabled = True
            
            embed = self.parent_view.cog.create_custom_embed(
                interaction.guild, self.parent_view.author,
                "✅ Partenariat Envoyé",
                f"Le partenariat a été envoyé avec succès dans {channel.mention} !"
            )
            
            await self.parent_view.message.edit(embed=embed, view=self.parent_view)
            await interaction.followup.send("✅ Envoi confirmé et exécuté.", ephemeral=True)
            
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur lors de l'envoi : {e}", ephemeral=True)

    @ui.button(label="Annuler", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_message("Envoi annulé.", ephemeral=True)



# Nouveau sélecteur pour la notification
class NotificationSelect(ui.Select):
    def __init__(self, parent_view: "PartenariatView"):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(label="Aucune notification", description="Ne pas notifier", emoji="🚫", value="none"),
            discord.SelectOption(label="Notifier un Rôle", description="Renseigner l'ID d'un rôle", emoji="🔔", value="ping_role"),
            discord.SelectOption(label="Notifier @here", description="Activer le ping here", emoji="📍", value="ping_here"),
            discord.SelectOption(label="Notifier @everyone", description="Activer le ping everyone", emoji="🌍", value="ping_everyone"),
        ]
        super().__init__(placeholder="Sélectionnez la notification...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val == "none":
            self.parent_view.config["ping_type"] = None
            self.parent_view.config["ping_id"] = None
            self.parent_view.cog.save_config_sync(interaction.guild.id, self.parent_view.config)
            await self.parent_view.update_embed(interaction)
        elif val == "ping_role":
            await interaction.response.send_modal(RoleModal(self.parent_view))
        elif val == "ping_here":
            self.parent_view.config["ping_type"] = "here"
            self.parent_view.config["ping_id"] = None
            self.parent_view.cog.save_config_sync(interaction.guild.id, self.parent_view.config)
            await self.parent_view.update_embed(interaction)
        elif val == "ping_everyone":
            self.parent_view.config["ping_type"] = "everyone"
            self.parent_view.config["ping_id"] = None
            self.parent_view.cog.save_config_sync(interaction.guild.id, self.parent_view.config)
            await self.parent_view.update_embed(interaction)

# Sélecteur pour les autres options
class OptionsSelect(ui.Select):
    def __init__(self, parent_view: "PartenariatView"):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(label="Salon de partenariat", description="Définir l'ID du salon cible", emoji="📢", value="channel"),
            discord.SelectOption(label="Contenu du message", description="Rédiger le partenariat", emoji="📝", value="content"),
            discord.SelectOption(label="Envoyer le partenariat", description="Valider et envoyer", emoji="📤", value="send"),
        ]
        super().__init__(placeholder="Configurer le partenariat...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val == "channel":
            await interaction.response.send_modal(ChannelModal(self.parent_view))
        elif val == "content":
            await interaction.response.send_modal(ContentModal(self.parent_view))
        elif val == "send":
            # Vérifications avant envoi
            if not self.parent_view.config.get("channel_id"):
                return await interaction.response.send_message("❌ Vous devez configurer le salon de partenariat !", ephemeral=True)
            if not self.parent_view.config.get("content"):
                return await interaction.response.send_message("❌ Vous devez rédiger le contenu du message !", ephemeral=True)
            # Double confirmation
            confirm_embed = discord.Embed(
                title="🔒 Confirmation requise",
                description="Êtes-vous sûr de vouloir envoyer ce partenariat avec les paramètres actuels ?",
                color=discord.Color.yellow()
            )
            await interaction.response.send_message(embed=confirm_embed, view=ConfirmView(self.parent_view, interaction), ephemeral=True)


class PartenariatView(ui.View):
    def __init__(self, cog: commands.Cog, guild: discord.Guild, author: discord.Member, config: dict):
        super().__init__(timeout=300) # Timeout de sécurité de 5 minutes
        self.cog = cog
        self.guild = guild
        self.author = author
        self.config = config
        self.message: Optional[discord.Message] = None
        
        self.add_item(NotificationSelect(self))
        self.add_item(OptionsSelect(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Sécurité : Seul l'auteur de la commande peut interagir."""
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Vous ne pouvez pas interagir avec ce menu.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        """Désactive le sélecteur si inactif."""
        for child in self.children:
            child.disabled = True
        if self.message:
            try: await self.message.edit(view=self)
            except: pass

    async def update_embed(self, interaction: discord.Interaction):
        """Génère l'aperçu réel et met à jour le message."""
        chan_id = self.config.get("channel_id")
        chan_display = f"<#{chan_id}>" if chan_id else "❌ Non configuré"
        
        ping_type = self.config.get("ping_type")
        if ping_type == "here": ping_display = "@here"
        elif ping_type == "everyone": ping_display = "@everyone"
        elif ping_type == "role" and self.config.get("ping_id"): ping_display = f"<@&{self.config['ping_id']}>"
        else: ping_display = "❌ Aucune notification"

        content = self.config.get("content", "❌ Aucun contenu rédigé.")
        
        desc = (
            f"**Salon cible :** {chan_display}\n"
            f"**Notification :** {ping_display}\n\n"
            f"**Aperçu du message :**\n"
            f"```text\n{content}\n```"
        )
        
        embed = self.cog.create_custom_embed(self.guild, self.author, "🤝 Gestionnaire de Partenariat", desc)
        
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)


# ==============================================================================
# --------------------------- COG PRINCIPAL ------------------------------------
# ==============================================================================

class Partenariat(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.logger = logging.getLogger('bot')
        self.configs: Dict[int, Dict[str, Any]] = {}

    async def cog_load(self):
        """Initialisation et création de l'arborescence."""
        DB_DIR.mkdir(parents=True, exist_ok=True)
        self._load_all_configs()

    def _load_all_configs(self):
        """Chargement dynamique des JSON en mémoire."""
        if not DB_DIR.exists(): return
        for file in os.listdir(DB_DIR):
            if file.endswith('.json'):
                try:
                    guild_id = int(file.replace('.json', ''))
                    self.load_config_sync(guild_id)
                except Exception as e:
                    self.logger.error(f"Erreur chargement config partenariat {file} : {e}")

    def load_config_sync(self, guild_id: int) -> dict:
        """Charge ou initialise la configuration d'un serveur."""
        if guild_id in self.configs:
            return self.configs[guild_id]

        path = DB_DIR / f"{guild_id}.json"
        default = {
            "channel_id": None,
            "ping_type": None,  # 'here', 'everyone', 'role', or None
            "ping_id": None,
            "content": None
        }

        if not path.exists():
            self.configs[guild_id] = default
            self.save_config_sync(guild_id, default)
            return default

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                final_config = {**default, **data}
                self.configs[guild_id] = final_config
                return final_config
        except Exception:
            return default

    def save_config_sync(self, guild_id: int, config: dict):
        """Persistance des données en JSON."""
        self.configs[guild_id] = config
        path = DB_DIR / f"{guild_id}.json"
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            self.logger.error(f"Erreur sauvegarde JSON Partenariat {guild_id}: {e}")

    def create_custom_embed(self, guild, user, title, description):
        """Mécanisme de fallback : Utilise config_manager si présent, sinon l'embed natif."""
        if config_manager:
            return config_manager.get_formatted_embed(
                guild=guild, 
                user=user, 
                bot=self.bot, 
                title=title, 
                description=description
            )
        embed = discord.Embed(title=title, description=description, color=EMBED_COLOR)
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text=f"Demandé par {user.display_name}", icon_url=user.display_avatar.url)
        return embed

    # ==========================================================================
    # --------------------------- COMMANDE HYBRIDE -----------------------------
    # ==========================================================================

    @commands.hybrid_command(
        name="partenariat", 
        description="Génère et configure un message de partenariat dans le salon désigné."
    )
    @app_commands.default_permissions(administrator=True)
    @commands.has_permissions(administrator=True) # Adaptable selon les rôles du serveur
    async def partenariat_cmd(self, ctx: commands.Context):
        try:
            if ctx.interaction:
                await ctx.defer(ephemeral=False)
                
            config = self.load_config_sync(ctx.guild.id)
            view = PartenariatView(self, ctx.guild, ctx.author, config)
            
            # Initialisation de la description avec l'état actuel de la DB
            chan_id = config.get("channel_id")
            chan_display = f"<#{chan_id}>" if chan_id else "❌ Non configuré"
            
            ping_type = config.get("ping_type")
            if ping_type == "here": ping_display = "@here"
            elif ping_type == "everyone": ping_display = "@everyone"
            elif ping_type == "role" and config.get("ping_id"): ping_display = f"<@&{config['ping_id']}>"
            else: ping_display = "❌ Aucune notification"

            content = config.get("content", "❌ Aucun contenu rédigé.")

            desc = (
                f"**Salon cible :** {chan_display}\n"
                f"**Notification :** {ping_display}\n\n"
                f"**Aperçu du message :**\n"
                f"```text\n{content}\n```"
            )
            
            embed = self.create_custom_embed(ctx.guild, ctx.author, "🤝 Gestionnaire de Partenariat", desc)
            
            if ctx.interaction:
                msg = await ctx.send(embed=embed, view=view)
            else:
                msg = await ctx.send(embed=embed, view=view, reference=ctx.message, mention_author=True)
                
            view.message = msg # Sauvegarde l'instance du message pour gérer le timeout

        except Exception as e:
            self.logger.error(f"[ERROR - Partenariat] {e}\n{traceback.format_exc()}")
            error_msg = "❌ Une erreur est survenue lors de l'exécution de la commande."
            if ctx.interaction:
                await ctx.interaction.followup.send(error_msg, ephemeral=True)
            else:
                await ctx.send(error_msg, reference=ctx.message)

async def setup(bot: commands.Bot):
    await bot.add_cog(Partenariat(bot))