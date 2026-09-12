import discord
from discord import ui
from discord.ext import commands
from typing import Optional, Dict, Any, List
import logging
import json
from pathlib import Path
import os
import traceback
from functools import wraps

# ==============================================================================
# --- Configuration & Chemins ---
# ==============================================================================
EMBED_COLOR = 0x2b2d31

# Cherche le dossier data à côté de main.py
MAIN_PATH = Path(__file__).resolve().parent.parent.parent  # Ajuste la profondeur si besoin
DATA_DIR = MAIN_PATH / "data" / "addons" / "data_botsacces"

# --- Importation conditionnelle du Config Manager ---
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# ==============================================================================
# --- Composants UI : Sélecteurs Indépendants ---
# ==============================================================================
# L'utilisation de classes distinctes est obligatoire dans discord.py 
# pour les menus déroulants spécifiques (Channel, Role, User).

class ChannelConfigSelect(ui.ChannelSelect):
    def __init__(self, config_ref: dict):
        self.config_ref = config_ref
        current = self.config_ref.get("channels", [])
        self.shown_items = current[:25]
        defaults = [discord.Object(id=i) for i in self.shown_items]
        
        super().__init__(
            custom_id="sel_chan",
            placeholder="📂 Ajouter/Retirer des salons...",
            min_values=0,
            max_values=25,
            channel_types=[discord.ChannelType.text, discord.ChannelType.voice, discord.ChannelType.news]
        )
        self.default_values = defaults

    async def callback(self, interaction: discord.Interaction):
        try:
            current_set = set(self.config_ref.get("channels", []))
            shown_set = set(self.shown_items)
            selected_set = set(item.id for item in self.values)
            
            new_set = (current_set - shown_set).union(selected_set)
            self.config_ref["channels"] = list(new_set)
            await self.view.update_message(interaction)
        except Exception as e:
            await interaction.response.send_message("❌ Erreur lors de l'enregistrement.", ephemeral=True)
            logging.error(f"Erreur ChannelSelect: {e}\n{traceback.format_exc()}")

class RoleConfigSelect(ui.RoleSelect):
    def __init__(self, config_ref: dict):
        self.config_ref = config_ref
        current = self.config_ref.get("roles", [])
        self.shown_items = current[:25]
        defaults = [discord.Object(id=i) for i in self.shown_items]
        
        super().__init__(
            custom_id="sel_role",
            placeholder="🎭 Ajouter/Retirer des rôles...",
            min_values=0,
            max_values=25
        )
        self.default_values = defaults

    async def callback(self, interaction: discord.Interaction):
        try:
            current_set = set(self.config_ref.get("roles", []))
            shown_set = set(self.shown_items)
            selected_set = set(item.id for item in self.values)
            
            new_set = (current_set - shown_set).union(selected_set)
            self.config_ref["roles"] = list(new_set)
            await self.view.update_message(interaction)
        except Exception as e:
            logging.error(f"Erreur RoleSelect: {e}")

class UserConfigSelect(ui.UserSelect):
    def __init__(self, config_ref: dict):
        self.config_ref = config_ref
        current = self.config_ref.get("users", [])
        self.shown_items = current[:25]
        defaults = [discord.Object(id=i) for i in self.shown_items]
        
        super().__init__(
            custom_id="sel_user",
            placeholder="👤 Ajouter/Retirer des membres...",
            min_values=0,
            max_values=25
        )
        self.default_values = defaults

    async def callback(self, interaction: discord.Interaction):
        try:
            current_set = set(self.config_ref.get("users", []))
            shown_set = set(self.shown_items)
            selected_set = set(item.id for item in self.values)
            
            new_set = (current_set - shown_set).union(selected_set)
            self.config_ref["users"] = list(new_set)
            await self.view.update_message(interaction)
        except Exception as e:
            logging.error(f"Erreur UserSelect: {e}")

# ==============================================================================
# --- Composant UI : La View Globale ---
# ==============================================================================

class BotAccessView(ui.View):
    def __init__(self, cog: "BotAccess", ctx: commands.Context, config: dict):
        super().__init__(timeout=300)
        self.cog = cog
        self.ctx = ctx
        self.config = config
        
        # Boutons Dynamiques
        self.btn_chan = ui.Button(label="Mode Salons", style=discord.ButtonStyle.secondary, row=0, custom_id="btn_chan")
        self.btn_chan.callback = self.toggle_chan_mode
        self.add_item(self.btn_chan)
        
        self.btn_ent = ui.Button(label="Mode Utilisateurs/Rôles", style=discord.ButtonStyle.secondary, row=0, custom_id="btn_ent")
        self.btn_ent.callback = self.toggle_ent_mode
        self.add_item(self.btn_ent)

        # Ajout des sélecteurs propres
        self.add_item(ChannelConfigSelect(self.config))
        self.add_item(RoleConfigSelect(self.config))
        self.add_item(UserConfigSelect(self.config))

        self.update_button_states()

    def update_button_states(self):
        c_mode = self.config.get("channel_mode", "blacklist")
        e_mode = self.config.get("entity_mode", "blacklist")
        self.btn_chan.emoji = "⚪" if c_mode == "whitelist" else "⚫"
        self.btn_ent.emoji = "⚪" if e_mode == "whitelist" else "⚫"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Sécurité absolue : Intercepte les actions des autres utilisateurs."""
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        """Gestion propre de l'expiration du menu."""
        for item in self.children:
            item.disabled = True
        try:
            if hasattr(self, 'message') and self.message:
                await self.message.edit(view=self)
        except Exception:
            pass

    async def toggle_chan_mode(self, interaction: discord.Interaction):
        cur = self.config.get("channel_mode", "blacklist")
        self.config["channel_mode"] = "whitelist" if cur == "blacklist" else "blacklist"
        await self.update_message(interaction, rebuild_view=False)

    async def toggle_ent_mode(self, interaction: discord.Interaction):
        cur = self.config.get("entity_mode", "blacklist")
        self.config["entity_mode"] = "whitelist" if cur == "blacklist" else "blacklist"
        await self.update_message(interaction, rebuild_view=False)

    async def update_message(self, interaction: discord.Interaction, rebuild_view=True):
        """Sauvegarde les données et met à jour l'affichage."""
        self.cog.save_config_sync(interaction.guild.id, self.config)
        embed = self.cog.build_embed(interaction.guild, interaction.user, self.config)
        
        if rebuild_view:
            # Reconstruit la vue pour actualiser les "default_values" visuelles des sélecteurs
            new_view = BotAccessView(self.cog, self.ctx, self.config)
            await interaction.response.edit_message(embed=embed, view=new_view)
            self.stop()
        else:
            self.update_button_states()
            await interaction.response.edit_message(embed=embed, view=self)

# ==============================================================================
# --- Cog Principal ---
# ==============================================================================

class BotAccess(commands.Cog):
    """
    Système premium de gestion des accès du bot.
    Permet de verrouiller l'usage par salons, membres et rôles.
    """
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.logger = logging.getLogger('bot.botacces')
        self.configs: Dict[int, Dict[str, Any]] = {}

    async def cog_load(self):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            self._load_all_configs()
            # self.logger.info("✅ Cog BotAccess chargé avec succès.")
        except Exception as e:
            self.logger.error(f"❌ Erreur critique lors de l'initialisation de BotAccess: {e}")

    def _load_all_configs(self):
        if not DATA_DIR.exists(): return
        for file in os.listdir(DATA_DIR):
            if file.endswith('.json'):
                try:
                    gid = int(file.replace('.json', ''))
                    self.load_config_sync(gid)
                except Exception as e:
                    self.logger.error(f"Erreur lecture fichier {file}: {e}")

    # --- Persistance (JSON) ---

    def load_config_sync(self, guild_id: int) -> dict:
        if guild_id in self.configs:
            return self.configs[guild_id]

        path = DATA_DIR / f"{guild_id}.json"
        default = {
            "channel_mode": "blacklist",
            "channels": [],
            "entity_mode": "blacklist",
            "roles": [],
            "users": []
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
            self.logger.error(f"Fichier corrompu {guild_id}: {e}")
            return default

    def save_config_sync(self, guild_id: int, config: dict):
        self.configs[guild_id] = config
        path = DATA_DIR / f"{guild_id}.json"
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)
        except Exception as e:
            self.logger.error(f"Erreur écriture JSON {guild_id}: {e}")

    # --- Génération de l'Embed ---

    def format_mentions(self, items: List[int], fmt: str) -> str:
        if not items: return "Aucun."
        text = " ".join(fmt.format(i) for i in items)
        # Limite stricte pour éviter l'erreur d'API Discord (HTTPException)
        if len(text) > 900:
            return text[:890] + "... *(et d'autres)*"
        return text

    def build_embed(self, guild: discord.Guild, user: discord.Member, config: dict) -> discord.Embed:
        c_mode = config.get("channel_mode", "blacklist")
        e_mode = config.get("entity_mode", "blacklist")
        
        c_text = self.format_mentions(config.get("channels", []), "<#{}>")
        r_text = self.format_mentions(config.get("roles", []), "<@&{}>")
        u_text = self.format_mentions(config.get("users", []), "<@{}>")

        c_emoji = "⚪ **Whitelist** (Autorisés)" if c_mode == "whitelist" else "⚫ **Blacklist** (Interdits)"
        e_emoji = "⚪ **Whitelist** (Autorisés)" if e_mode == "whitelist" else "⚫ **Blacklist** (Interdits)"

        desc = (
            "Configurez les restrictions d'utilisation des commandes de votre bot.\n"
            "-# *Les administrateurs ignorent ces restrictions. Si vous configurez plus de 25 éléments, seuls les 25 premiers s'affichent dans le menu, mais tous sont sauvegardés et appliqués.*\n\n"
            f"### 📍 Salons\nMode : {c_emoji}\n> {c_text}\n\n"
            f"### 👥 Membres & 🎭 Rôles\nMode : {e_emoji}\n"
            f"**Rôles :**\n> {r_text}\n"
            f"**Membres :**\n> {u_text}"
        )

        title = "⚙️ Configuration des Accès Bot"

        # Gestion ultra-sécurisée du fallback config_manager
        if config_manager:
            try:
                embed = config_manager.get_formatted_embed(
                    guild=guild, user=user, bot=self.bot, title=title, description=desc
                )
                if embed: return embed
            except Exception as e:
                self.logger.error(f"Erreur config_manager, fallback activé: {e}")
        
        embed = discord.Embed(title=title, description=desc, color=EMBED_COLOR)
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        return embed

    # --- Commande (Hybrid) ---

    @commands.hybrid_command(name="botacces", description="Gère les permissions globales du bot.")
    @commands.has_permissions(administrator=True)
    async def botacces(self, ctx: commands.Context):
        try:
            config = self.load_config_sync(ctx.guild.id)
            embed = self.build_embed(ctx.guild, ctx.author, config)
            view = BotAccessView(self, ctx, config)
            
            if ctx.interaction:
                view.message = await ctx.send(embed=embed, view=view, ephemeral=False)
            else:
                view.message = await ctx.send(embed=embed, view=view)
        except Exception as e:
            self.logger.error(f"Erreur exécution /botacces : {e}\n{traceback.format_exc()}")
            await ctx.send("❌ Une erreur interne empêche l'affichage du menu.", ephemeral=True)

    # --- Intercepteur de Commandes Global ---

    def bot_check(self, ctx: commands.Context) -> bool:
        """Méthode native de discord.py : Intercepte TOUTES les commandes."""
        if not ctx.guild or ctx.author.bot:
            return True

        if ctx.author.guild_permissions.administrator:
            return True

        config = self.load_config_sync(ctx.guild.id)
        
        # 1. Filtre Entités
        entity_mode = config.get("entity_mode", "blacklist")
        roles_config = config.get("roles", [])
        users_config = config.get("users", [])
        
        role_ids = [r.id for r in getattr(ctx.author, "roles", [])]
        has_entity_match = (ctx.author.id in users_config) or any(rid in roles_config for rid in role_ids)

        if entity_mode == "blacklist" and has_entity_match:
            self.bot.loop.create_task(self._send_rejection(ctx, "🚫 Vous ou l'un de vos rôles est sur liste noire du bot."))
            return False
        elif entity_mode == "whitelist" and (roles_config or users_config) and not has_entity_match:
            self.bot.loop.create_task(self._send_rejection(ctx, "🔒 L'accès au bot est restreint par une liste blanche."))
            return False

        # 2. Filtre Salons
        channel_mode = config.get("channel_mode", "blacklist")
        channels = config.get("channels", [])

        if channel_mode == "blacklist" and ctx.channel.id in channels:
            self.bot.loop.create_task(self._send_rejection(ctx, "🔕 L'utilisation des commandes est interdite dans ce salon."))
            return False
        elif channel_mode == "whitelist" and channels and ctx.channel.id not in channels:
            chan_list = " ".join(f"<#{c}>" for c in channels[:10])
            self.bot.loop.create_task(self._send_rejection(ctx, f"💬 Le bot ne peut être utilisé que dans ces salons :\n{chan_list}"))
            return False

        return True

    async def _send_rejection(self, ctx: commands.Context, message: str):
        """Gère proprement la réponse de rejet selon le contexte (Slash vs Prefix)."""
        try:
            if ctx.interaction:
                if not ctx.interaction.response.is_done():
                    await ctx.interaction.response.send_message(message, ephemeral=True)
                else:
                    await ctx.interaction.followup.send(message, ephemeral=True)
            else:
                await ctx.send(message, delete_after=7)
                try: await ctx.message.delete()
                except: pass
        except Exception as e:
            self.logger.error(f"Erreur d'envoi du rejet: {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(BotAccess(bot))