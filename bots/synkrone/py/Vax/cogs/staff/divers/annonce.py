import discord
from discord import ui
from discord.ext import commands
from typing import Optional, Dict, Any
import logging
import json
from pathlib import Path
import traceback
from functools import wraps

# ==============================================================================
# --------------------------- CONFIGURATION & UTILS ----------------------------
# ==============================================================================
# Chemin persistant et ciblé (racine du bot / data / staff / divers / annonce)
BASE_DIR = Path.cwd()
DATA_DIR = BASE_DIR / "data" / "staff" / "divers" / "annonce"

try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

def handle_errors(func):
    """Décorateur robuste pour capturer et logger les erreurs de l'UI."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logging.getLogger('bot').error(f"Erreur UI ({func.__name__}): {e}\n{traceback.format_exc()}")
            interaction = next((arg for arg in args if isinstance(arg, discord.Interaction)), None)
            if interaction:
                if not interaction.response.is_done():
                    await interaction.response.send_message("❌ Une erreur interne est survenue. L'erreur a été transmise aux logs.", ephemeral=True)
                else:
                    await interaction.followup.send("❌ Une erreur interne est survenue. L'erreur a été transmise aux logs.", ephemeral=True)
            return None
    return wrapper

# ==============================================================================
# --------------------------- INTERFACES UTILISATEUR ---------------------------
# ==============================================================================

class AnnonceDraftView(ui.View):
    """Vue pour finaliser et envoyer l'annonce (Aperçu, Choix des cibles, Double Confirm)."""
    def __init__(self, cog, guild: discord.Guild, embed: discord.Embed):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.draft_embed = embed
        self.config = self.cog.load_config_sync(guild.id)
        
        self.selected_channel: Optional[discord.TextChannel] = None
        self.selected_role: Optional[discord.Role] = None
        self.confirm_step = False

        # --- SÉLECTEUR DE SALON CIBLE (Max 25 pour éviter les crashs Discord) ---
        channel_options = []
        for cid in self.config.get("channels", []):
            channel = guild.get_channel(int(cid))
            if channel and isinstance(channel, discord.TextChannel):
                channel_options.append(discord.SelectOption(label=channel.name[:100], value=str(channel.id), description=f"#{channel.name}"[:100]))
        
        if not channel_options:
            channel_options.append(discord.SelectOption(label="Aucun salon configuré", value="none"))

        self.channel_select = ui.Select(
            placeholder="📍 Choisissez le salon cible...", 
            options=channel_options[:25], 
            min_values=1, 
            max_values=1, 
            row=0
        )
        self.channel_select.callback = self.on_channel_select
        self.add_item(self.channel_select)

        # --- SÉLECTEUR DE RÔLE CIBLE (Max 25) ---
        role_options = [discord.SelectOption(label="Aucun ping", value="none", description="Ne mentionner personne")]
        for rid in self.config.get("roles", []):
            role = guild.get_role(int(rid))
            if role:
                role_options.append(discord.SelectOption(label=role.name[:100], value=str(role.id), description=f"@{role.name}"[:100]))

        self.role_select = ui.Select(
            placeholder="🔔 Choisissez le rôle à notifier...", 
            options=role_options[:25], 
            min_values=1, 
            max_values=1, 
            row=1
        )
        self.role_select.callback = self.on_role_select
        self.add_item(self.role_select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.permissions.administrator:
            await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            return False
        return True

    async def on_channel_select(self, interaction: discord.Interaction):
        if self.channel_select.values[0] != "none":
            self.selected_channel = self.guild.get_channel(int(self.channel_select.values[0]))
        self.confirm_step = False
        self.send_btn.label = "🚀 Envoyer l'Annonce"
        self.send_btn.style = discord.ButtonStyle.green
        await interaction.response.edit_message(view=self)

    async def on_role_select(self, interaction: discord.Interaction):
        if self.role_select.values[0] != "none":
            self.selected_role = self.guild.get_role(int(self.role_select.values[0]))
        else:
            self.selected_role = None
        await interaction.response.edit_message(view=self)

    @ui.button(label="🚀 Envoyer l'Annonce", style=discord.ButtonStyle.green, row=2)
    @handle_errors
    async def send_btn(self, interaction: discord.Interaction, button: ui.Button):
        if not self.selected_channel:
            return await interaction.response.send_message("⚠️ Veuillez sélectionner un salon valide avant d'envoyer.", ephemeral=True)

        if not self.confirm_step:
            self.confirm_step = True
            button.label = "⚠️ Confirmer l'envoi"
            button.style = discord.ButtonStyle.danger
            return await interaction.response.edit_message(view=self)

        content = self.selected_role.mention if self.selected_role else None
        
        try:
            await self.selected_channel.send(content=content, embed=self.draft_embed)
            
            # Verrouillage complet de la vue (Anti-Doublon)
            button.label = "✅ Annonce Envoyée"
            button.style = discord.ButtonStyle.secondary
            button.disabled = True
            self.channel_select.disabled = True
            self.role_select.disabled = True
            
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(f"✅ L'annonce a bien été publiée dans {self.selected_channel.mention}.", ephemeral=True)
            
        except discord.Forbidden:
            self.confirm_step = False
            button.label = "🚀 Envoyer l'Annonce"
            button.style = discord.ButtonStyle.green
            await interaction.response.edit_message(view=self)
            await interaction.followup.send(f"❌ Je n'ai pas la permission d'écrire dans {self.selected_channel.mention}.", ephemeral=True)

    @ui.button(label="🔙 Annuler et Retour", style=discord.ButtonStyle.secondary, row=2)
    @handle_errors
    async def back_btn(self, interaction: discord.Interaction, button: ui.Button):
        panel = AnnoncePanel(self.cog)
        embed = self.cog.get_panel_embed(interaction.guild, interaction.user)
        await interaction.response.edit_message(embed=embed, view=panel)


class AnnonceModal(ui.Modal, title="Création de l'Annonce"):
    """Modal de saisie gérant les retours 'None' pour éviter les exceptions."""
    def __init__(self, cog, guild: discord.Guild, author: discord.Member, config: dict):
        super().__init__()
        self.cog = cog
        self.guild = guild
        self.author = author
        self.config = config
        
        last = self.config.get("last_draft", {})

        self.ann_title = ui.TextInput(label="Titre de l'annonce", placeholder="Ex: Mise à jour...", default=last.get("title") or "", required=True, max_length=256)
        self.ann_desc = ui.TextInput(label="Description", style=discord.TextStyle.paragraph, placeholder="Votre contenu ici...", default=last.get("desc") or "", required=True)
        self.ann_thumb = ui.TextInput(label="URL Miniature (Optionnel)", placeholder="https://...", default=last.get("thumb") or "", required=False)

        self.add_item(self.ann_title)
        self.add_item(self.ann_desc)
        self.add_item(self.ann_thumb)

    @handle_errors
    async def on_submit(self, interaction: discord.Interaction):
        self.config["last_draft"] = {
            "title": str(self.ann_title.value),
            "desc": str(self.ann_desc.value),
            "thumb": str(self.ann_thumb.value) if self.ann_thumb.value else ""
        }
        self.cog.save_config_sync(self.guild.id, self.config)

        if config_manager:
            embed = config_manager.get_formatted_embed(
                guild=self.guild, user=self.author, bot=interaction.client,
                title=self.ann_title.value, description=self.ann_desc.value
            )
        else:
            embed = discord.Embed(title=self.ann_title.value, description=self.ann_desc.value, color=0x3498db)
            embed.set_author(name=self.guild.name, icon_url=self.guild.icon.url if self.guild.icon else None)

        if self.ann_thumb.value and self.ann_thumb.value.startswith("http"):
            try:
                embed.set_thumbnail(url=self.ann_thumb.value)
            except: pass

        view = AnnonceDraftView(self.cog, self.guild, embed)
        await interaction.response.edit_message(embed=embed, view=view)


class ConfigManagerView(ui.View):
    """Vue double-sélecteur sécurisée avec ciblage explicite."""
    def __init__(self, cog, guild: discord.Guild, user: discord.Member, mode: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.user = user
        self.mode = mode
        self.config = self.cog.load_config_sync(guild.id)
        
        # 1. SÉLECTEUR D'AJOUT : Enregistré dans self.add_select
        if mode == "channels":
            self.add_select = ui.ChannelSelect(
                placeholder="➕ Ajouter des salons...", min_values=1, max_values=25,
                channel_types=[discord.ChannelType.text, discord.ChannelType.news], row=0
            )
        else:
            self.add_select = ui.RoleSelect(
                placeholder="➕ Ajouter des rôles...", min_values=1, max_values=25, row=0
            )
        self.add_select.callback = self.add_callback
        self.add_item(self.add_select)

        # 2. SÉLECTEUR DE SUPPRESSION : Enregistré dans self.remove_select
        remove_options = []
        current_items = [int(x) for x in self.config.get(self.mode, [])]
        
        for item_id in current_items:
            if mode == "channels":
                obj = guild.get_channel(item_id)
                label = obj.name[:100] if obj else f"Inconnu ({item_id})"
                desc = f"#{obj.name}"[:100] if obj else "Canal inaccessible"
                emoji = "📁"
            else:
                obj = guild.get_role(item_id)
                label = obj.name[:100] if obj else f"Inconnu ({item_id})"
                desc = f"@{obj.name}"[:100] if obj else "Rôle inaccessible"
                emoji = "🏷️"
            
            remove_options.append(discord.SelectOption(label=label, value=str(item_id), description=desc, emoji=emoji))

        safe_options = remove_options[:25]

        if not safe_options:
            safe_options.append(discord.SelectOption(label=f"Aucun élément à supprimer", value="none"))
            self.remove_select = ui.Select(placeholder="➖ Supprimer des éléments...", options=safe_options, disabled=True, row=1)
        else:
            max_val = min(25, len(safe_options))
            self.remove_select = ui.Select(
                placeholder="➖ Sélectionner pour supprimer...", 
                options=safe_options, 
                min_values=1, 
                max_values=max_val, 
                row=1
            )
            self.remove_select.callback = self.remove_callback
        
        self.add_item(self.remove_select)

    @handle_errors
    async def add_callback(self, interaction: discord.Interaction):
        # Utilisation de self.add_select au lieu de l'index aléatoire self.children[0]
        current_list = set(int(x) for x in self.config.get(self.mode, []))
        
        for item in self.add_select.values:
            current_list.add(item.id)
            
        self.config[self.mode] = list(current_list)
        self.cog.save_config_sync(self.guild.id, self.config)
        await self.refresh_view(interaction)

    @handle_errors
    async def remove_callback(self, interaction: discord.Interaction):
        # Utilisation de self.remove_select au lieu de self.children[1]
        if self.remove_select.values[0] == "none": return
        
        current_list = set(int(x) for x in self.config.get(self.mode, []))
        for val in self.remove_select.values:
            item_id = int(val)
            if item_id in current_list:
                current_list.remove(item_id)
                
        self.config[self.mode] = list(current_list)
        self.cog.save_config_sync(self.guild.id, self.config)
        await self.refresh_view(interaction)

    async def refresh_view(self, interaction: discord.Interaction):
        view = ConfigManagerView(self.cog, self.guild, self.user, self.mode)
        title = "📁 Gestion des Salons" if self.mode == "channels" else "🏷️ Gestion des Rôles"
        desc = (
            "Utilisez le premier menu pour **ajouter** de nouveaux éléments à votre liste.\n"
            "Utilisez le second menu pour **supprimer** des éléments de votre liste actuelle.\n"
            "-# *Note : La suppression affiche un maximum de 25 éléments en même temps.*"
        )
        embed = discord.Embed(title=title, description=desc, color=0x2b2d31)
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="🔙 Annuler et Retour", style=discord.ButtonStyle.secondary, row=2)
    @handle_errors
    async def back_btn(self, interaction: discord.Interaction, button: ui.Button):
        panel = AnnoncePanel(self.cog)
        embed = self.cog.get_panel_embed(self.guild, self.user)
        await interaction.response.edit_message(embed=embed, view=panel)


class AnnoncePanel(ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.permissions.administrator:
            await interaction.response.send_message("❌ Réservé aux administrateurs.", ephemeral=True)
            return False
        return True

    @ui.button(label="Créer une Annonce", style=discord.ButtonStyle.primary, custom_id="ann_panel_create", emoji="✍️", row=0)
    @handle_errors
    async def btn_create(self, interaction: discord.Interaction, button: ui.Button):
        config = self.cog.load_config_sync(interaction.guild.id)
        if not config.get("channels"):
            return await interaction.response.send_message("⚠️ Vous devez d'abord configurer au moins un salon via le bouton 'Gérer les Salons'.", ephemeral=True)
        
        modal = AnnonceModal(self.cog, interaction.guild, interaction.user, config)
        await interaction.response.send_modal(modal)

    @ui.button(label="Gérer les Salons", style=discord.ButtonStyle.secondary, custom_id="ann_panel_channels", emoji="📁", row=0)
    @handle_errors
    async def btn_config_channels(self, interaction: discord.Interaction, button: ui.Button):
        view = ConfigManagerView(self.cog, interaction.guild, interaction.user, "channels")
        desc = "Utilisez le premier menu pour **ajouter** des salons.\nUtilisez le second menu pour **supprimer** des salons existants."
        embed = discord.Embed(title="📁 Gestion des Salons", description=desc, color=0x2b2d31)
        await interaction.response.edit_message(embed=embed, view=view)

    @ui.button(label="Gérer les Rôles", style=discord.ButtonStyle.secondary, custom_id="ann_panel_roles", emoji="🏷️", row=0)
    @handle_errors
    async def btn_config_roles(self, interaction: discord.Interaction, button: ui.Button):
        view = ConfigManagerView(self.cog, interaction.guild, interaction.user, "roles")
        desc = "Utilisez le premier menu pour **ajouter** des rôles.\nUtilisez le second menu pour **supprimer** des rôles existants."
        embed = discord.Embed(title="🏷️ Gestion des Rôles", description=desc, color=0x2b2d31)
        await interaction.response.edit_message(embed=embed, view=view)


# ==============================================================================
# ----------------------------- COG ANNONCE ------------------------------------
# ==============================================================================

class AnnonceCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger('bot')
        self.configs: Dict[int, Dict[str, Any]] = {}

    async def cog_load(self):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.logger.error(f"Impossible de créer le dossier de données : {e}")
            
        self.bot.add_view(AnnoncePanel(self))

    def load_config_sync(self, guild_id: int) -> dict:
        if guild_id in self.configs:
            return self.configs[guild_id]

        path = DATA_DIR / f"{guild_id}.json"
        default = {
            'channels': [],
            'roles': [],
            'last_draft': {}
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
        except Exception as e:
            self.logger.error(f"Erreur lecture JSON {guild_id}: {e}")
            return default

    def save_config_sync(self, guild_id: int, config: dict):
        self.configs[guild_id] = config
        path = DATA_DIR / f"{guild_id}.json"
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            self.logger.error(f"Erreur sauvegarde JSON {guild_id}: {e}")

    def get_panel_embed(self, guild: discord.Guild, user: discord.Member) -> discord.Embed:
        config = self.load_config_sync(guild.id)
        
        ch_list = [f"<#{c}>" for c in config.get("channels", []) if guild.get_channel(int(c))]
        ch_text = "\n".join(f"› {c}" for c in ch_list[:15]) if ch_list else "*Aucun salon configuré.*"
        if len(ch_list) > 15: ch_text += f"\n*... et {len(ch_list) - 15} autres.*"
        
        rl_list = [f"<@&{r}>" for r in config.get("roles", []) if guild.get_role(int(r))]
        rl_text = "\n".join(f"› {r}" for r in rl_list[:15]) if rl_list else "*Aucun rôle configuré.*"
        if len(rl_list) > 15: rl_text += f"\n*... et {len(rl_list) - 15} autres.*"

        description = (
            "Bienvenue dans le gestionnaire global d'annonces de votre serveur.\n\n"
            "**📁 Salons d'annonce configurés :**\n"
            f"{ch_text}\n\n"
            "**🏷️ Rôles autorisés :**\n"
            f"{rl_text}\n\n"
            "**Comment procéder ?**\n"
            "**1.** Utilisez les boutons **Gérer** ci-dessous pour ajouter/supprimer.\n"
            "**2.** Cliquez sur **Créer une Annonce** pour rédiger et expédier en toute sécurité."
        )

        if config_manager:
            return config_manager.get_formatted_embed(
                guild=guild, user=user, bot=self.bot,
                title="📢 Panneau de Contrôle - Annonces", description=description
            )
        else:
            embed = discord.Embed(title="📢 Panneau de Contrôle - Annonces", description=description, color=0x2b2d31)
            if self.bot.user.avatar:
                embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            return embed

    @commands.hybrid_command(name="annonce", description="Gérer et créer des annonces sur le serveur.")
    @commands.has_permissions(administrator=True)
    async def annonce_cmd(self, ctx: commands.Context):
        embed = self.get_panel_embed(ctx.guild, ctx.author)
        view = AnnoncePanel(self)
        
        if ctx.interaction:
            await ctx.send(embed=embed, view=view, ephemeral=False)
        else:
            await ctx.send(embed=embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(AnnonceCog(bot))