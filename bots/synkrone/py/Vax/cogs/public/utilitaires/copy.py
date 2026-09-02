import discord
from discord.ext import commands
from discord import app_commands
import traceback
from typing import Optional
import io

# ==============================================================================
# --------------------------- IMPORTATION UTILS --------------------------------
# ==============================================================================
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# ==============================================================================
# ----------------------------- COG COPY MESSAGE -------------------------------
# ==============================================================================

class CopyMessage(commands.Cog):
    """Cog gérant la récupération du formatage brut d'un message."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        
        # Ajout d'une commande "Context Menu" (Clic Droit -> Applications -> Copier Source)
        self.ctx_menu = app_commands.ContextMenu(
            name='Copier la source',
            callback=self.copy_context_menu,
        )
        self.bot.tree.add_command(self.ctx_menu)

    async def cog_unload(self):
        """Nettoyage de la commande contextuelle lors du déchargement du Cog."""
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)

    # --------------------------------------------------------------------------
    # CORE LOGIC
    # --------------------------------------------------------------------------

    async def _process_copy(self, ctx_or_interaction, message: discord.Message):
        """Logique métier centralisée pour traiter et formater le message."""
        content = message.content
        
        # 1. Vérification du contenu vide (Embeds, Images seules)
        if not content:
            error_desc = "Ce message ne contient pas de texte brut (uniquement un embed, une pièce jointe ou un message système)."
            return await self._send_error(ctx_or_interaction, error_desc)

        # 2. Sécurité : Échapper les triples backticks déjà présents dans le message
        safe_content = content.replace("```", "`\u200b`\u200b`")
        
        # 3. Formatage final dans un bloc de code (Concaténation pour éviter les erreurs f-string)
        formatted_text = "```\n" + safe_content + "\n```"

        # 4. Gestion de la limite de caractères de Discord (2000 chars)
        if len(formatted_text) > 2000:
            # Si le message est trop long, on génère un fichier .txt à la volée
            file = discord.File(io.BytesIO(content.encode('utf-8')), filename="message_source.txt")
            msg_text = "⚠️ Le message est trop long pour un bloc Discord. Voici le fichier source :"
            
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.followup.send(content=msg_text, file=file)
            else:
                await ctx_or_interaction.send(content=msg_text, file=file, reference=ctx_or_interaction.message)
        else:
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.followup.send(content=formatted_text)
            else:
                await ctx_or_interaction.send(content=formatted_text, reference=ctx_or_interaction.message)

    async def _send_error(self, ctx_or_interaction, description: str):
        """Gestion centralisée des erreurs avec le ConfigManager."""
        is_interaction = isinstance(ctx_or_interaction, discord.Interaction)
        guild = ctx_or_interaction.guild
        user = ctx_or_interaction.user if is_interaction else ctx_or_interaction.author

        if config_manager:
            embed = config_manager.get_formatted_embed(
                guild=guild,
                user=user,
                bot=self.bot,
                title="❌ Impossible de copier",
                description=description,
                target_id=guild.id if guild else None
            )
        else:
            embed = discord.Embed(title="❌ Impossible de copier", description=description, color=0xff0000)

        if is_interaction:
            await ctx_or_interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await ctx_or_interaction.send(embed=embed, reference=ctx_or_interaction.message)

    # --------------------------------------------------------------------------
    # COMMANDES UTILISATEUR
    # --------------------------------------------------------------------------

    @app_commands.checks.cooldown(1, 3.0, key=lambda i: (i.guild_id, i.user.id))
    async def copy_context_menu(self, interaction: discord.Interaction, message: discord.Message):
        """Action du menu contextuel (Clic Droit)."""
        await interaction.response.defer(ephemeral=True)
        await self._process_copy(interaction, message)

    @commands.hybrid_command(name="copy", description="Copie le message ciblé avec tout son formatage Markdown.")
    @app_commands.describe(message_id="ID du message (inutile si vous répondez au message en question avec !copy)")
    async def copy_cmd(self, ctx: commands.Context, message_id: Optional[str] = None):
        """Commande hybride (Prefix & Slash)."""
        
        target_message = None

        # 1. Cas d'usage "Préfixe" : l'utilisateur répond à un message (!copy)
        if ctx.message.reference and ctx.message.reference.message_id:
            try:
                target_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            except discord.NotFound:
                return await self._send_error(ctx, "Le message d'origine a été supprimé ou est introuvable.")

        # 2. Cas d'usage "Slash / Préfixe manuel" : l'utilisateur fournit un ID
        elif message_id and message_id.isdigit():
            # 2.1 Chercher dans le salon courant
            try:
                target_message = await ctx.channel.fetch_message(int(message_id))
            except discord.NotFound:
                # 2.2 Chercher dans tous les salons texte du serveur
                if ctx.guild:
                    for channel in ctx.guild.text_channels:
                        if channel.id == ctx.channel.id:
                            continue
                        try:
                            target_message = await channel.fetch_message(int(message_id))
                            if target_message:
                                break
                        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                            continue
                # 2.3 Chercher dans tous les serveurs où le bot est présent
                if not target_message:
                    for guild in self.bot.guilds:
                        if ctx.guild and guild.id == ctx.guild.id:
                            continue
                        for channel in guild.text_channels:
                            try:
                                target_message = await channel.fetch_message(int(message_id))
                                if target_message:
                                    break
                            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                                continue
                        if target_message:
                            break
                if not target_message:
                    return await self._send_error(ctx, f"Impossible de trouver un message avec l'ID `{message_id}` dans ce salon, ce serveur ou les serveurs où je suis présent.")

        # 3. Aucun ciblage
        if not target_message:
            return await self._send_error(ctx, "Vous devez **répondre** à un message ou fournir un **ID de message** valide.")

        # Accusé de réception pour éviter le Timeout
        if ctx.interaction:
            await ctx.defer(ephemeral=False)

        await self._process_copy(ctx, target_message)

async def setup(bot: commands.Bot):
    await bot.add_cog(CopyMessage(bot))