# ==============================================================================
# Nom du fichier : designer_3d.py
# Description : Système de commande "Designer 3D" avec salon de logs & claim persistant
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
GUILD_TARGET_ID = 1518305648918401184 

# Configuration du salon et message d'origine (Sélecteur) -> À adapter pour la 3D
CHANNEL_DEV_ID = 1518685491527159838
MESSAGE_DEV_ID = 1518714740040405003

# Catégorie où créer les tickets de commande
CATEGORY_TICKETS_ID = 1518311378966937651

# Salon public de commande (où l'embed de claim est envoyé)
CHANNEL_COMMANDE_ID = 1518701142610280583

# Rôles
ROLE_GESTION_ID = 1518327264750862467  # Rôle Gestion global
ROLE_DESIGNER_3D_ID = 1518441636152082512  # Rôle de l'équipe 3D (ajustable au besoin)

# Options de tarification basées sur le catalogue 3D
OPTIONS_DATA = {
    "modele_sur_mesure": {
        "label": "Modèle 3D Sur-Mesure", 
        "price": "Sur devis", 
        "emoji": "🧊", 
        "desc": "Modèles High Poly principalement destinés à l'impression 3D."
    }
}

# ==============================================================================
# ---------------------- BOUTON DE PRISE EN CHARGE (PERSISTANT) ----------------
# ==============================================================================
class Claim3DTicketView(ui.View):
    """Vue persistante gérant le bouton de claim pour le Design 3D."""
    def __init__(self, ticket_id: Optional[int] = None):
        super().__init__(timeout=None)
        if ticket_id is not None:
            self.claim_button.custom_id = f"claim_design3d_{ticket_id}"

    @ui.button(label="🎯 Prendre la commande", style=discord.ButtonStyle.green, custom_id="dynamic_claim_design3d_btn")
    async def claim_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        member = interaction.user
        
        # 1. Vérification du rôle Designer 3D
        designer_role = guild.get_role(ROLE_DESIGNER_3D_ID)
        if not designer_role or designer_role not in member.roles:
            return await interaction.followup.send("❌ Seuls les membres avec le rôle Designer 3D peuvent prendre cette commande.", ephemeral=True)

        # 2. Extraction de l'ID du ticket depuis le custom_id
        custom_id = button.custom_id
        if not custom_id.startswith("claim_design3d_"):
            return await interaction.followup.send("❌ Erreur de configuration du bouton (ID invalide).", ephemeral=True)
        
        ticket_id = int(custom_id.split("_")[2])
        ticket_channel = guild.get_channel(ticket_id)

        if not ticket_channel:
            return await interaction.followup.send("❌ Le salon du ticket est introuvable (il a probablement été fermé).", ephemeral=True)

        # 3. Ajout du designer dans le salon du ticket
        try:
            await ticket_channel.set_permissions(member, read_messages=True, send_messages=True, attach_files=True, manage_messages=True)
        except Exception as e:
            print("Erreur modification permissions claim 3D :", e)
            return await interaction.followup.send("❌ Impossible de vous donner l'accès au ticket.", ephemeral=True)

        # 4. Message d'annonce dans le ticket
        await ticket_channel.send(f"🧊 Le modéliste 3D {member.mention} vient de rejoindre le ticket pour prendre en charge la commande.")

        # 5. Désactivation définitive du bouton
        button.label = f"Pris par {member.display_name}"
        button.style = discord.ButtonStyle.grey
        button.disabled = True
        
        await interaction.message.edit(view=self)
        await interaction.followup.send("✅ Vous avez pris en charge la commande avec succès !", ephemeral=True)


# ==============================================================================
# ------------------------- MODAL DE COMMANDE ----------------------------------
# ==============================================================================
class Designer3DModal(ui.Modal):
    """Formulaire de description du projet de modélisation 3D."""
    
    description = ui.TextInput(
        label="Détails de votre projet 3D",
        style=discord.TextStyle.paragraph,
        placeholder="Décrivez le modèle, l'usage (impression, jeu...), le niveau de détail attendu...",
        required=True,
        min_length=20,
        max_length=3000
    )

    def __init__(self, bot: commands.Bot, option_key: str, cog_instance: commands.Cog):
        self.info = OPTIONS_DATA[option_key]
        super().__init__(title=f"Commande : {self.info['label']}")
        self.bot = bot
        self.cog_instance = cog_instance

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user

        # 1. Configuration des permissions du ticket (Client + Gestion uniquement)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
        }

        role_gestion = guild.get_role(ROLE_GESTION_ID)
        if role_gestion:
            overwrites[role_gestion] = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True)

        # 2. Récupération de la catégorie cible
        category = guild.get_channel(CATEGORY_TICKETS_ID)
        if not isinstance(category, discord.CategoryChannel):
            category = None

        # 3. Création du salon Ticket
        try:
            ticket_channel = await guild.create_text_channel(
                name=f"{self.info['emoji']}・3d-{user.name.lower()}",
                category=category,
                overwrites=overwrites,
                reason=f"Commande 3D {self.info['label']} - {user.display_name}"
            )
        except Exception as e:
            print("Erreur création salon 3d :", e)
            return await interaction.followup.send("❌ Une erreur est survenue lors de la création de votre ticket.", ephemeral=True)

        # 4. Message de confirmation immédiat au client
        await interaction.followup.send(f"✅ Votre ticket de commande a été créé ici : {ticket_channel.mention}", ephemeral=True)

        # 5. Utilisation du config_manager pour l'embed interne du Ticket (avec rappels des CGV)
        title_ticket = f"{self.info['emoji']} Nouvelle Commande : {self.info['label']}"
        desc_ticket = (
            f"Merci pour votre commande {user.mention} !\n"
            f"Un modéliste 3D va étudier votre demande pour réaliser un devis.\n\n"
            f"📌 **Rappel des conditions :**\n"
            f"• **Acompte :** 50% requis pour lancer la fabrication.\n"
            f"• **Suivi :** Suivi de l'avancée par captures d'écran.\n"
            f"• **Livraison :** Fichiers finaux délivrés après paiement complet.\n\n"
            f"**Description de votre besoin :**\n> {self.description.value}"
        )

        if config_manager:
            embed_ticket = config_manager.get_formatted_embed(guild, user, self.bot, title_ticket, desc_ticket, guild.id)
        else:
            embed_ticket = discord.Embed(title=title_ticket, description=desc_ticket, color=0x34495e)
        
        embed_ticket.set_thumbnail(url=user.display_avatar.url)
        
        pings_ticket = [user.mention]
        if role_gestion: 
            pings_ticket.append(role_gestion.mention)
            
        await ticket_channel.send(content=" | ".join(pings_ticket), embed=embed_ticket)

        # 6. Utilisation du config_manager pour l'embed du salon public des Commandes
        channel_commande = guild.get_channel(CHANNEL_COMMANDE_ID)
        if channel_commande:
            role_designer_3d = guild.get_role(ROLE_DESIGNER_3D_ID)
            
            title_cmd = f"🧊 Nouvelle offre de modélisation 3D !"
            desc_cmd = (
                f"**Client :** {user.mention}\n"
                f"**Type de projet :** {self.info['label']}\n"
                f"**Tarif :** {self.info['price']}\n\n"
                f"**Cahier des charges :**\n```txt\n{self.description.value}\n```"
            )
            
            if config_manager:
                embed_commande = config_manager.get_formatted_embed(guild, user, self.bot, title_cmd, desc_cmd, guild.id)
            else:
                embed_commande = discord.Embed(title=title_cmd, description=desc_cmd, color=0x1abc9c)
                
            embed_commande.set_footer(text=f"ID du Client : {user.id}")
            
            # Instanciation de la vue persistante liée au ticket
            view_claim = Claim3DTicketView(ticket_id=ticket_channel.id)
            await channel_commande.send(content=role_designer_3d.mention if role_designer_3d else None, embed=embed_commande, view=view_claim)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        print("=== ERREUR DANS LA MODAL DESIGNER 3D ===")
        traceback.print_exception(type(error), error, error.__traceback__)
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Une erreur est survenue lors du traitement de votre commande.", ephemeral=True)


# ==============================================================================
# ----------------------- VUE PERSISTANTE ET SÉLECTEUR -------------------------
# ==============================================================================
class Designer3DSelect(ui.Select):
    """Sélecteur persistant pour le catalogue de modélisation 3D."""
    def __init__(self, bot: commands.Bot, cog_instance: commands.Cog):
        self.bot = bot
        self.cog_instance = cog_instance
        
        options = []
        for key, value in OPTIONS_DATA.items():
            options.append(discord.SelectOption(
                label=f"{value['label']} ➜ {value['price']}",
                value=key,
                description=value['desc'][:100],
                emoji=value['emoji']
            ))
        
        super().__init__(
            placeholder="🧊 Commandez votre modèle 3D sur-mesure...", 
            min_values=1, 
            max_values=1, 
            options=options, 
            custom_id="persistent_designer3d_selector"
        )

    async def callback(self, interaction: discord.Interaction):
        if not self.values:
            return await interaction.response.defer()

        selected_key = self.values[0]
        
        modal = Designer3DModal(bot=self.bot, option_key=selected_key, cog_instance=self.cog_instance)
        await interaction.response.send_modal(modal)

        # Réinitialisation visuelle du sélecteur
        try:
            for option in self.options:
                option.default = False
            if interaction.message:
                await interaction.message.edit(view=self.view)
        except Exception as e:
            print(f"[Avertissement] Impossible de réinitialiser le menu 3d : {e}")


class Designer3DView(ui.View):
    """Vue globale contenant le sélecteur 3D."""
    def __init__(self, bot: commands.Bot, cog_instance: commands.Cog):
        super().__init__(timeout=None)
        self.add_item(Designer3DSelect(bot, cog_instance))

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: ui.Item):
        print("=== ERREUR DANS LE SELECTEUR DESIGNER 3D ===")
        traceback.print_exception(type(error), error, error.__traceback__)


# ==============================================================================
# -------------------------------- COG PRINCIPAL -------------------------------
# ==============================================================================
class Designer3DCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        """Recharge les structures de vues persistantes au démarrage du bot."""
        # 1. Enregistrement du sélecteur du catalogue 3D
        self.bot.add_view(Designer3DView(self.bot, self))
        
        # 2. Écouteur universel pour capter les boutons de claim 3D (persistant après redémarrage)
        self.bot.add_view(Claim3DTicketView())

    @commands.hybrid_command(name="setup_designer3d_menu", description="[Admin] Injecte le sélecteur de modélisation dans le message cible.")
    @commands.has_permissions(administrator=True)
    async def setup_designer3d(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)

        if ctx.guild.id != GUILD_TARGET_ID:
            return await ctx.send("❌ Commande réservée au serveur cible.", ephemeral=True)

        channel = self.bot.get_channel(CHANNEL_DEV_ID)
        if not channel:
            return await ctx.send(f"❌ Impossible de trouver le salon : `{CHANNEL_DEV_ID}`.", ephemeral=True)

        try:
            message = await channel.fetch_message(MESSAGE_DEV_ID)
            
            # Injection
            await message.edit(view=Designer3DView(self.bot, self))
            await ctx.send(f"✅ Menu de commande Designer 3D déployé avec succès : {message.jump_url}", ephemeral=True)
            
        except discord.NotFound:
            await ctx.send("❌ Message introuvable.", ephemeral=True)
        except discord.Forbidden:
            await ctx.send("❌ Permissions insuffisantes (le bot doit être l'auteur du message).", ephemeral=True)
        except Exception as e:
            print("Erreur SETUP DESIGNER 3D:", e)
            await ctx.send(f"❌ Erreur inattendue : {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Designer3DCog(bot))