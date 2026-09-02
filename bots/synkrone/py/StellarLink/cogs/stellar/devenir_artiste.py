# ==============================================================================
# Nom du fichier : devenir_artiste.py
# Description : Système de candidature "Artiste" avec interface persistante
# ==============================================================================

import os
import discord
import traceback
from discord.ext import commands
from discord import app_commands, ui
from typing import Optional

# ==============================================================================
# --------------------------- IMPORTATION UTILS --------------------------------
# ==============================================================================
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# ==============================================================================
# ----------------------- CONFIGURATION DES IDs --------------------------------
# ==============================================================================
# Serveur cible de l'événement
GUILD_TARGET_ID = 1518305648918401184 

# Salon "devenir artiste" où se trouve le message
CHANNEL_ARTISTE_ID = 1518628795702055023

# Message spécifique sur lequel greffer le sélecteur
MESSAGE_ARTISTE_ID = 1518637847324655677

# Catégorie où seront créés les tickets de candidature
CATEGORY_TICKETS_ID = 1518311378966937651

# Rôle "Gestion" général (toujours notifié)
ROLE_GESTION_GENERAL_ID = 1518327264750862467

# Dictionnaire associant chaque domaine à son rôle de "Gérant de domaine" spécifique
DOMAIN_ROLES = {
    "Développeur": 000000000000000000,
    "Designer 2D": 000000000000000000,
    "Designer 3D": 000000000000000000,
    "Designer Audio": 000000000000000000,
    "Monteur Vidéo": 000000000000000000
}

# Emojis associés pour le nommage des tickets et l'affichage
DOMAIN_EMOJIS = {
    "Développeur": "💻",
    "Designer 2D": "🎨",
    "Designer 3D": "🧊",
    "Designer Audio": "🎵",
    "Monteur Vidéo": "🎬"
}

# ==============================================================================
# ------------------------- MODAL DE CANDIDATURE -------------------------------
# ==============================================================================
class ArtisteModal(ui.Modal):
    """Formulaire modal qui s'ouvre après la sélection d'un domaine."""
    
    presentation = ui.TextInput(
        label="Présentation & Portfolio",
        style=discord.TextStyle.paragraph,
        placeholder="Ex: Passionné de 3D depuis 4 ans sur Blender. Voici mon portfolio : https://...",
        required=True,
        min_length=30,
        max_length=3000
    )

    def __init__(self, bot: commands.Bot, domaine: str, cog_instance: commands.Cog):
        super().__init__(title=f"Rejoindre l'équipe : {domaine}")
        self.bot = bot
        self.domaine = domaine
        self.cog_instance = cog_instance

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user

        # 1. Gestion des permissions du ticket
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
        }

        # Ajout du rôle général
        role_general = guild.get_role(ROLE_GESTION_GENERAL_ID)
        if role_general:
            overwrites[role_general] = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True)

        # Ajout du rôle spécifique au domaine
        role_specifique_id = DOMAIN_ROLES.get(self.domaine)
        role_specifique = guild.get_role(role_specifique_id) if role_specifique_id else None
        if role_specifique:
            overwrites[role_specifique] = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True)

        # 2. Récupération de la catégorie cible
        category = guild.get_channel(CATEGORY_TICKETS_ID)
        if not isinstance(category, discord.CategoryChannel):
            category = None # Sécurité si l'ID est incorrect ou introuvable

        # 3. Création du salon Ticket
        emoji = DOMAIN_EMOJIS.get(self.domaine, "🎨")

        try:
            ticket_channel = await guild.create_text_channel(
                name=f"{emoji}・artiste-{user.name.lower()}",
                category=category,
                overwrites=overwrites,
                reason=f"Candidature {self.domaine} - {user.display_name}"
            )
        except Exception as e:
            print("Erreur création salon :", e)
            return await interaction.followup.send("❌ Une erreur est survenue lors de la création du ticket.", ephemeral=True)

        # 4. Message de confirmation
        await interaction.followup.send(f"✅ Ta candidature a été envoyée ! L'équipe t'attend ici : {ticket_channel.mention}", ephemeral=True)

        # 5. Construction et Envoi de l'Embed dans le ticket
        title = f"{emoji} Nouvelle Candidature : {self.domaine}"
        description = (
            f"Une nouvelle pépite souhaite rejoindre l'équipe !\n\n"
            f"**Candidat :** {user.mention}\n\n"
            f"**Présentation & Portfolio :**\n"
            f"> {self.presentation.value}"
        )

        if config_manager:
            embed = config_manager.get_formatted_embed(guild, user, self.bot, title, description, guild.id)
        else:
            embed = discord.Embed(title=title, description=description, color=0x2ecc71)
        
        embed.set_thumbnail(url=user.display_avatar.url)

        # Préparation du ping (Candidat + Général + Spécifique)
        pings = [user.mention]
        if role_general: pings.append(role_general.mention)
        if role_specifique: pings.append(role_specifique.mention)

        await ticket_channel.send(content=" | ".join(pings), embed=embed)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        """Capte et affiche les erreurs silencieuses de la Modal"""
        print("=== ERREUR DANS LA MODAL ARTISTE ===")
        traceback.print_exception(type(error), error, error.__traceback__)
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Une erreur est survenue lors du traitement de ta candidature.", ephemeral=True)

# ==============================================================================
# ----------------------- VUE PERSISTANTE ET SÉLECTEUR -------------------------
# ==============================================================================
class ArtisteSelect(ui.Select):
    """Sélecteur persistant pour le choix du domaine artistique."""
    def __init__(self, bot: commands.Bot, cog_instance: commands.Cog):
        self.bot = bot
        self.cog_instance = cog_instance
        
        options = [
            discord.SelectOption(label="Développeur", value="Développeur", description="Rejoignez nos rangs de codeurs créatifs.", emoji="💻"),
            discord.SelectOption(label="Designer 2D", value="Designer 2D", description="Apportez votre touche visuelle à nos projets.", emoji="🎨"),
            discord.SelectOption(label="Designer 3D", value="Designer 3D", description="Modelez nos idées en trois dimensions.", emoji="🧊"),
            discord.SelectOption(label="Designer Audio", value="Designer Audio", description="Devenez le maestro sonore de l'équipe.", emoji="🎵"),
            discord.SelectOption(label="Monteur Vidéo", value="Monteur Vidéo", description="Donnez vie et rythme à nos visuels.", emoji="🎬")
        ]
        
        super().__init__(
            placeholder="🤝 Postulez dans votre domaine...", 
            min_values=1, 
            max_values=1, 
            options=options, 
            custom_id="persistent_artiste_selector"
        )

    async def callback(self, interaction: discord.Interaction):
        # 1. Vérification Anti-Crash
        if not self.values:
            return await interaction.response.defer()

        selected_domaine = self.values[0]
        
        # 2. Ouverture de la Modal IMMÉDIATEMENT
        modal = ArtisteModal(bot=self.bot, domaine=selected_domaine, cog_instance=self.cog_instance)
        await interaction.response.send_modal(modal)

        # 3. Réinitialisation visuelle propre (sans recréer la vue)
        try:
            for option in self.options:
                option.default = False # S'assure que rien ne reste sélectionné
            
            if interaction.message:
                await interaction.message.edit(view=self.view)
        except Exception as e:
            print(f"[Avertissement] Impossible de réinitialiser le menu : {e}")

class ArtisteView(ui.View):
    """Vue persistante contenant le menu déroulant."""
    def __init__(self, bot: commands.Bot, cog_instance: commands.Cog):
        super().__init__(timeout=None)
        self.add_item(ArtisteSelect(bot, cog_instance))

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: ui.Item):
        """Capte et affiche les erreurs silencieuses de la Vue"""
        print("=== ERREUR DANS LE SELECTEUR ARTISTE ===")
        traceback.print_exception(type(error), error, error.__traceback__)

# ==============================================================================
# -------------------------------- COG PRINCIPAL -------------------------------
# ==============================================================================
class DevenirArtisteCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        """Recharge la vue persistante au démarrage du bot."""
        self.bot.add_view(ArtisteView(self.bot, self))

    @commands.hybrid_command(name="setup_artiste_menu", description="[Admin] Injecte le sélecteur dans le message cible.")
    @commands.has_permissions(administrator=True)
    async def setup_artiste(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)

        if ctx.guild.id != GUILD_TARGET_ID:
            return await ctx.send("❌ Commande réservée au serveur cible.", ephemeral=True)

        channel = self.bot.get_channel(CHANNEL_ARTISTE_ID)
        if not channel:
            return await ctx.send(f"❌ Impossible de trouver le salon : `{CHANNEL_ARTISTE_ID}`.", ephemeral=True)

        try:
            message = await channel.fetch_message(MESSAGE_ARTISTE_ID)
            
            # Injection du nouveau sélecteur
            await message.edit(view=ArtisteView(self.bot, self))
            await ctx.send(f"✅ Menu déroulant déployé et synchronisé : {message.jump_url}", ephemeral=True)
            
        except discord.NotFound:
            await ctx.send("❌ Message introuvable.", ephemeral=True)
        except discord.Forbidden:
            await ctx.send("❌ Permissions insuffisantes (le bot doit être l'auteur du message).", ephemeral=True)
        except Exception as e:
            print("Erreur SETUP:", e)
            await ctx.send(f"❌ Erreur inattendue : {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(DevenirArtisteCog(bot))