# ==============================================================================
# Nom du fichier : designer_2d.py
# Description : Système de commande "Designer 2D" avec salon de logs & claim persistant
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

# Configuration du salon et message d'origine (Sélecteur) -> À adapter si nécessaire
CHANNEL_DESIGNER_ID = 1518685470286938153
MESSAGE_DESIGNER_ID = 1518707217254318152

# Catégorie où créer les tickets de commande
CATEGORY_TICKETS_ID = 1518311378966937651

# Salon public de commande (où l'embed de claim est envoyé)
CHANNEL_COMMANDE_ID = 1518701142610280583

# Rôles
ROLE_GESTION_ID = 1518327264750862467  # Rôle Gestion global
ROLE_DESIGNER_2D_ID = 1518305648918401193  # Rôle Designer 2D autorisé à claim

# Options de tarification basées sur le catalogue produit
OPTIONS_DATA = {
    "logo_visuel": {
        "label": "Logo / Visuel / Affiche", 
        "price": "20€ à 60€", 
        "emoji": "🎨", 
        "desc": "Création sur-mesure de vos supports de communication. Délai : 4 à 7 jours."
    },
    "direction_artistique": {
        "label": "Direction Artistique (DA)", 
        "price": "Sur devis", 
        "emoji": "✨", 
        "desc": "Univers visuel complet et charte graphique unique. Délai : 7 jours ou plus."
    },
    "packs_emotes_badges": {
        "label": "Packs Emotes & Badges Sub", 
        "price": "25€ à 140€+", 
        "emoji": "👑", 
        "desc": "De 5 à plus de 30 émoticones/badges personnalisés. Délai : 1 à 7 jours."
    }
}

# ==============================================================================
# ---------------------- BOUTON DE PRISE EN CHARGE (PERSISTANT) ----------------
# ==============================================================================
class ClaimDesignerTicketView(ui.View):
    """Vue persistante gérant le bouton de claim pour le Design 2D."""
    def __init__(self, ticket_id: Optional[int] = None):
        super().__init__(timeout=None)
        if ticket_id is not None:
            self.claim_button.custom_id = f"claim_design2d_{ticket_id}"

    @ui.button(label="🎯 Prendre la commande", style=discord.ButtonStyle.green, custom_id="dynamic_claim_design2d_btn")
    async def claim_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        member = interaction.user
        
        # 1. Vérification du rôle Designer 2D
        designer_role = guild.get_role(ROLE_DESIGNER_2D_ID)
        if not designer_role or designer_role not in member.roles:
            return await interaction.followup.send("❌ Seuls les membres avec le rôle Designer 2D peuvent prendre cette commande.", ephemeral=True)

        # 2. Extraction de l'ID du ticket depuis le custom_id
        custom_id = button.custom_id
        if not custom_id.startswith("claim_design2d_"):
            return await interaction.followup.send("❌ Erreur de configuration du bouton (ID invalide).", ephemeral=True)
        
        ticket_id = int(custom_id.split("_")[2])
        ticket_channel = guild.get_channel(ticket_id)

        if not ticket_channel:
            return await interaction.followup.send("❌ Le salon du ticket est introuvable (il a probablement été fermé).", ephemeral=True)

        # 3. Ajout du designer dans le salon du ticket
        try:
            await ticket_channel.set_permissions(member, read_messages=True, send_messages=True, attach_files=True, manage_messages=True)
        except Exception as e:
            print("Erreur modification permissions claim 2D :", e)
            return await interaction.followup.send("❌ Impossible de vous donner l'accès au ticket.", ephemeral=True)

        # 4. Message d'annonce dans le ticket
        await ticket_channel.send(f"🎨 Le designer 2D {member.mention} vient de rejoindre le ticket pour prendre en charge la commande.")

        # 5. Désactivation définitive du bouton
        button.label = f"Pris par {member.display_name}"
        button.style = discord.ButtonStyle.grey
        button.disabled = True
        
        await interaction.message.edit(view=self)
        await interaction.followup.send("✅ Vous avez pris en charge la commande avec succès !", ephemeral=True)


# ==============================================================================
# ------------------------- MODAL DE COMMANDE ----------------------------------
# ==============================================================================
class Designer2DModal(ui.Modal):
    """Formulaire de description du projet graphique."""
    
    description = ui.TextInput(
        label="Description de votre projet graphique",
        style=discord.TextStyle.paragraph,
        placeholder="Détaillez vos idées, couleurs, inspirations, formats ou quantité (ex: pack de 10 emotes)...",
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
                name=f"{self.info['emoji']}・graphisme-{user.name.lower()}",
                category=category,
                overwrites=overwrites,
                reason=f"Commande 2D {self.info['label']} - {user.display_name}"
            )
        except Exception as e:
            print("Erreur création salon 2d :", e)
            return await interaction.followup.send("❌ Une erreur est survenue lors de la création de votre ticket.", ephemeral=True)

        # 4. Message de confirmation immédiat au client
        await interaction.followup.send(f"✅ Votre ticket de commande a été créé ici : {ticket_channel.mention}", ephemeral=True)

        # 5. Utilisation du config_manager pour l'embed interne du Ticket
        title_ticket = f"{self.info['emoji']} Nouvelle Commande : {self.info['label']}"
        desc_ticket = (
            f"Merci pour votre commande {user.mention} !\n"
            f"Un designer 2D va prendre en charge votre demande d'un instant à l'autre.\n\n"
            f"**Tarif indicatif :** {self.info['price']}\n\n"
            f"**Cahier des charges fourni :**\n> {self.description.value}"
        )

        if config_manager:
            embed_ticket = config_manager.get_formatted_embed(guild, user, self.bot, title_ticket, desc_ticket, guild.id)
        else:
            embed_ticket = discord.Embed(title=title_ticket, description=desc_ticket, color=0x9b59b6)
        
        embed_ticket.set_thumbnail(url=user.display_avatar.url)
        
        pings_ticket = [user.mention]
        if role_gestion: 
            pings_ticket.append(role_gestion.mention)
            
        await ticket_channel.send(content=" | ".join(pings_ticket), embed=embed_ticket)

        # 6. Utilisation du config_manager pour l'embed du salon public des Commandes
        channel_commande = guild.get_channel(CHANNEL_COMMANDE_ID)
        if channel_commande:
            role_designer = guild.get_role(ROLE_DESIGNER_2D_ID)
            
            title_cmd = f"🎨 Nouvelle création graphique disponible !"
            desc_cmd = (
                f"**Client :** {user.mention}\n"
                f"**Type de projet :** {self.info['label']}\n"
                f"**Base tarifaire :** {self.info['price']}\n\n"
                f"**Description de la demande :**\n```txt\n{self.description.value}\n```"
            )
            
            if config_manager:
                embed_commande = config_manager.get_formatted_embed(guild, user, self.bot, title_cmd, desc_cmd, guild.id)
            else:
                embed_commande = discord.Embed(title=title_cmd, description=desc_cmd, color=0xe91e63)
                
            embed_commande.set_footer(text=f"ID du Client : {user.id}")
            
            # Instanciation de la vue persistante liée au ticket
            view_claim = ClaimDesignerTicketView(ticket_id=ticket_channel.id)
            await channel_commande.send(content=role_designer.mention if role_designer else None, embed=embed_commande, view=view_claim)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        print("=== ERREUR DANS LA MODAL DESIGNER 2D ===")
        traceback.print_exception(type(error), error, error.__traceback__)
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Une erreur est survenue lors du traitement de votre commande.", ephemeral=True)


# ==============================================================================
# ----------------------- VUE PERSISTANTE ET SÉLECTEUR -------------------------
# ==============================================================================
class Designer2DSelect(ui.Select):
    """Sélecteur persistant pour le catalogue de design 2D."""
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
            placeholder="🎨 Commandez votre visuel ou pack...", 
            min_values=1, 
            max_values=1, 
            options=options, 
            custom_id="persistent_designer2d_selector"
        )

    async def callback(self, interaction: discord.Interaction):
        if not self.values:
            return await interaction.response.defer()

        selected_key = self.values[0]
        
        modal = Designer2DModal(bot=self.bot, option_key=selected_key, cog_instance=self.cog_instance)
        await interaction.response.send_modal(modal)

        # Réinitialisation visuelle du sélecteur
        try:
            for option in self.options:
                option.default = False
            if interaction.message:
                await interaction.message.edit(view=self.view)
        except Exception as e:
            print(f"[Avertissement] Impossible de réinitialiser le menu 2d : {e}")


class Designer2DView(ui.View):
    """Vue globale contenant le sélecteur."""
    def __init__(self, bot: commands.Bot, cog_instance: commands.Cog):
        super().__init__(timeout=None)
        self.add_item(Designer2DSelect(bot, cog_instance))

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: ui.Item):
        print("=== ERREUR DANS LE SELECTEUR DESIGNER 2D ===")
        traceback.print_exception(type(error), error, error.__traceback__)


# ==============================================================================
# -------------------------------- COG PRINCIPAL -------------------------------
# ==============================================================================
class Designer2DCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        """Recharge les structures de vues persistantes au démarrage du bot."""
        # 1. Enregistrement du sélecteur du catalogue
        self.bot.add_view(Designer2DView(self.bot, self))
        
        # 2. Écouteur universel pour capter les interactions sur n'importe quel bouton de claim 2D (même après 48h)
        self.bot.add_view(ClaimDesignerTicketView())

    @commands.hybrid_command(name="setup_designer_menu", description="[Admin] Injecte le sélecteur graphique dans le message cible.")
    @commands.has_permissions(administrator=True)
    async def setup_designer(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)

        if ctx.guild.id != GUILD_TARGET_ID:
            return await ctx.send("❌ Commande réservée au serveur cible.", ephemeral=True)

        channel = self.bot.get_channel(CHANNEL_DESIGNER_ID)
        if not channel:
            return await ctx.send(f"❌ Impossible de trouver le salon : `{CHANNEL_DESIGNER_ID}`.", ephemeral=True)

        try:
            message = await channel.fetch_message(MESSAGE_DESIGNER_ID)
            
            # Injection
            await message.edit(view=Designer2DView(self.bot, self))
            await ctx.send(f"✅ Menu de commande Designer 2D déployé avec succès : {message.jump_url}", ephemeral=True)
            
        except discord.NotFound:
            await ctx.send("❌ Message introuvable.", ephemeral=True)
        except discord.Forbidden:
            await ctx.send("❌ Permissions insuffisantes (le bot doit être l'auteur du message).", ephemeral=True)
        except Exception as e:
            print("Erreur SETUP DESIGNER 2D:", e)
            await ctx.send(f"❌ Erreur inattendue : {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Designer2DCog(bot))