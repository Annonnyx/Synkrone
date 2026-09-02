import discord
from discord import app_commands, ui
from discord.ext import commands
from typing import Optional, Dict, Any
import logging
import json
import re
from pathlib import Path
import os
import traceback
from functools import wraps
import datetime

# ==============================================================================
# --------------------------- CONFIGURATION & CHEMINS --------------------------
# ==============================================================================
EMBED_COLOR = 0x2b2d31
BASE_DIR = Path(__file__).parent
DB_DIR = BASE_DIR / "DB" / "Feedback"

# Cible centralisée (Serveur de Support du Bot)
TARGET_GUILD_ID = 1368235294192570520
TARGET_CHANNEL_ID = 1502093940663255212

# Emojis de vote (Réactions)
EMOJI_OUI = "<:oui:1505166323389432020>"
EMOJI_NON = "<:non:1505166321242083451>"

# Emojis des Bots
BOT_EMOJIS = {
    "Yui": "<:yui:1505166357623214110>",
    "Asuna": "<:Asuna:1505137735877525564>",
    "Kayaba": "<:Kayaba:1502091430854922344>",
    "Vax": "<:Vax:1472428869876191435>",
    "Autres": "<:Synkrone:1502091722392469724>"
}

# --- SYSTÈME D'IMPORT CONFIG_MANAGER ---
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

def handle_errors(func):
    """Décorateur pour capturer et logger les erreurs de manière robuste."""
    @wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except Exception as e:
            logger = logging.getLogger('bot')
            logger.error(f"[Feedback Cog] Erreur dans {func.__name__}: {e}\n{traceback.format_exc()}")
            return None
    return wrapper

# ==============================================================================
# --------------------------- INTERFACE UTILISATEUR (UI) -----------------------
# ==============================================================================

class FeedbackModal(ui.Modal):
    def __init__(self, view_state: "FeedbackView"):
        super().__init__(title="Détails du Feedback", timeout=300.0)
        self.view_state = view_state
        
        is_add_feature = (self.view_state.feedback_type == "Ajouter une feature")
        
        name_label = "Idée de nom de commande" if is_add_feature else "Nom de la commande / Feature"
        name_placeholder = "Ex: /profil" if is_add_feature else "Ex: /ping"
        
        self.cmd_name = ui.TextInput(
            label=name_label,
            placeholder=name_placeholder,
            style=discord.TextStyle.short,
            required=True,
            max_length=50
        )
        
        self.cmd_desc = ui.TextInput(
            label="Description détaillée",
            placeholder="Expliquez votre retour en détail...",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000
        )
        
        self.add_item(self.cmd_name)
        self.add_item(self.cmd_desc)

    async def on_submit(self, interaction: discord.Interaction):
        # 1. Accusé de réception silencieux
        await interaction.response.defer(ephemeral=True)
        
        cog = self.view_state.cog
        bot = cog.bot
        user = interaction.user
        source_guild = interaction.guild
        
        # --- TRAITEMENT DU NOM DE LA COMMANDE ---
        raw_cmd = self.cmd_name.value.strip()
        if raw_cmd.startswith('/'):
            formatted_cmd = raw_cmd
        else:
            clean_cmd = re.sub(r'^[^\w\s]+', '', raw_cmd).strip()
            formatted_cmd = f"/{clean_cmd}"

        # --- CONSTRUCTION DE L'EMBED LOG ---
        emoji_bot = BOT_EMOJIS.get("Yui", "🤖")
        embed_title = f"{emoji_bot} | Yui - {self.view_state.feedback_type}"
        
        guild_name = source_guild.name if source_guild else 'Message Privé'
        guild_id = source_guild.id if source_guild else 'N/A'
        
        # Formatage exact demandé pour le serveur et l'utilisateur
        embed_desc = (
            f"# `{formatted_cmd}`\n\n"
            f"{self.cmd_desc.value}\n\n"
            f"-# Serveur : {guild_name} - `{guild_id}`\n"
            f"-# ID Utilisateur : `{user.id}`"
        )
        
        # 2. Envoi au salon centralisé et Création de l'invitation
        invite_url = None
        try:
            target_channel = bot.get_channel(TARGET_CHANNEL_ID)
            if not target_channel:
                target_channel = await bot.fetch_channel(TARGET_CHANNEL_ID)

            # Création de l'invitation valable 7 jours (604800 secondes)
            try:
                invite = await target_channel.create_invite(
                    max_age=604800, 
                    max_uses=0, 
                    reason=f"Invitation Feedback générée pour {user.name}"
                )
                invite_url = invite.url
            except Exception as e:
                cog.logger.error(f"[Feedback Cog] Impossible de générer l'invitation : {e}")

            log_embed = cog.create_custom_embed(source_guild, user, embed_title, embed_desc)
            log_embed.set_author(name=f"Feedback de {user.display_name}", icon_url=user.display_avatar.url)
            log_embed.timestamp = datetime.datetime.now()
            
            log_msg = await target_channel.send(embed=log_embed)
            await log_msg.add_reaction(discord.PartialEmoji.from_str(EMOJI_OUI))
            await log_msg.add_reaction(discord.PartialEmoji.from_str(EMOJI_NON))

        except discord.Forbidden:
            cog.logger.error("[Feedback Cog] Erreur: Le bot n'a pas accès au salon centralisé ou manque de permissions.")
        except Exception as e:
            cog.logger.error(f"[Feedback Cog] Impossible d'envoyer le log centralisé: {e}")
        
        # 3. Sauvegarde locale
        cog.save_global_feedback_data({
            "user_id": user.id,
            "user_name": user.name,
            "source_guild_id": guild_id,
            "type": self.view_state.feedback_type,
            "target": "Yui",
            "command": formatted_cmd,
            "description": self.cmd_desc.value,
            "timestamp": datetime.datetime.now().isoformat()
        })
        
        # 4. Message de confirmation pour l'utilisateur avec Lien d'Invitation
        success_msg = (
            "> Merci pour votre contribution. Votre retour a bien été transmis à l'équipe de développement !\n"
            f"## {self.view_state.feedback_type} : `{formatted_cmd}`\n"
            f"```\n{self.cmd_desc.value}\n```"
        )
        if invite_url:
            success_msg += (
                f"\n🔗 [Votre feedback est désormais visible dans le salon dédié.]({invite_url})"
            )
        success_embed = cog.create_custom_embed(
            source_guild, user, "✅ Feedback Envoyé !", success_msg
        )
        await interaction.edit_original_response(embed=success_embed, view=None)

class Step1Select(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Ajouter une feature", emoji="✨", description="Proposer une nouveauté"),
            discord.SelectOption(label="Améliorer une feature", emoji="📈", description="Suggérer une amélioration"),
            discord.SelectOption(label="Nerfer une feature", emoji="⚖️", description="Équilibrer une fonction"),
            discord.SelectOption(label="Supprimer une feature", emoji="🗑️", description="Retirer une fonction obsolète"),
            discord.SelectOption(label="Signaler un bug", emoji="🐛", description="Rapporter un dysfonctionnement")
        ]
        super().__init__(placeholder="📍 Choisissez le type de feedback...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        self.view.feedback_type = self.values[0]
        self.view.bot_target = "Yui"
        modal = FeedbackModal(self.view)
        await interaction.response.send_modal(modal)


class BackButton(ui.Button):
    def __init__(self):
        super().__init__(label="Retour", style=discord.ButtonStyle.secondary, emoji="⬅️", row=1)

    async def callback(self, interaction: discord.Interaction):
        if self.view.step > 1:
            self.view.step -= 1
            await self.view.refresh_ui(interaction)

class FeedbackView(ui.View):
    def __init__(self, cog, ctx: commands.Context):
        super().__init__(timeout=None)
        self.cog = cog
        self.ctx = ctx
        self.author = ctx.author
        self.step = 1
        self.feedback_type = None
        self.bot_target = "Yui"
        self.update_components()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Ce menu interactif ne vous appartient pas.", ephemeral=True)
            return False
        return True

    def update_components(self):
        self.clear_items()
        self.add_item(Step1Select())

    async def refresh_ui(self, interaction: discord.Interaction):
        self.update_components()
        title = "📝 Formulaire de Feedback"
        desc = "Bienvenue dans le centre de feedback.\nVeuillez sélectionner **le type de retour** que vous souhaitez nous faire part."
        embed = self.cog.create_custom_embed(self.ctx.guild, self.author, title, desc)
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        pass  # Désactivé, le formulaire n'expire plus

# ==============================================================================
# --------------------------------- COG MAIN -----------------------------------
# ==============================================================================

class FeedbackCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.logger = logging.getLogger('bot')

    async def cog_load(self):
        DB_DIR.mkdir(parents=True, exist_ok=True)

    def create_custom_embed(self, guild, user, title, description):
        if config_manager:
            return config_manager.get_formatted_embed(
                guild=guild, 
                user=user, 
                bot=self.bot, 
                title=title, 
                description=description,
                target_id=guild.id if guild else None
            )
        embed = discord.Embed(title=title, description=description, color=EMBED_COLOR)
        return embed

    def save_global_feedback_data(self, payload: dict):
        path = DB_DIR / "global_feedbacks.json"
        try:
            data = []
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            data.append(payload)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            self.logger.error(f"[Feedback Cog] Erreur sauvegarde archive globale JSON: {e}")

    @commands.hybrid_command(name="feedback", description="Soumettre une idée, une amélioration ou signaler un bug à l'équipe de développement.")
    @handle_errors
    async def feedback(self, ctx: commands.Context):
        if ctx.interaction:
            await ctx.interaction.response.defer(ephemeral=False)
        view = FeedbackView(self, ctx)
        title = "📝 Formulaire de Feedback"
        desc = "Bienvenue dans le centre de feedback.\nVeuillez sélectionner **le type de retour** que vous souhaitez nous faire part."
        embed = self.create_custom_embed(ctx.guild, ctx.author, title, desc)
        if ctx.interaction:
            view.message = await ctx.interaction.followup.send(embed=embed, view=view, wait=True)
        else:
            view.message = await ctx.send(embed=embed, view=view, reference=ctx.message, mention_author=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(FeedbackCog(bot))