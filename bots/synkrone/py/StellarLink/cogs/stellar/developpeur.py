# ==============================================================================
# Nom du fichier : developpeur.py
# Description : Système de commande "Développeur" avec salon de logs & claim persistant
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

# Configuration du salon et message d'origine (Sélecteur)
CHANNEL_DEV_ID = 1518684731888111656
MESSAGE_DEV_ID = 1518699245925044488

# Catégorie où créer les tickets de commande
CATEGORY_TICKETS_ID = 1518311378966937651

# Salon public de commande (où l'embed de claim est envoyé)
CHANNEL_COMMANDE_ID = 1518701142610280583

# Rôles
ROLE_GESTION_ID = 1518327264750862467  # Rôle Gestion global
ROLE_DEVELOPPEUR_ID = 1518348176384594130  # Rôle Développeur autorisé à claim

# Options de tarification et emojis pour le sélecteur (sans parenthèses moches)
OPTIONS_DATA = {
    "web_simple": {"label": "Page Web Simple", "price": "5€ à 20€", "emoji": "📄", "desc": "Vitrine élégante, sans gestion de base de données."},
    "web_complet": {"label": "Site Internet Complet", "price": "10€ à 50€", "emoji": "🌐", "desc": "Site dynamique, base de données et fonctionnalités sur mesure."},
    "bot_synkrone": {"label": "Bot Discord Clé en Main", "price": "2€", "emoji": "🤖", "desc": "Solution standard rapide et efficace."},
    "bot_perso": {"label": "Bot Discord Personnalisé", "price": "3€", "emoji": "🛠️", "desc": "Sur-mesure total selon vos besoins spécifiques."},
    "script_bot": {"label": "Script Bot Discord", "price": "0,10€ à 5€", "emoji": "📜", "desc": "Correction ou ajout spécifique en Python/JS."}
}

# ==============================================================================
# ---------------------- BOUTON DE PRISE EN CHARGE (PERSISTANT) ----------------
# ==============================================================================
class ClaimTicketView(ui.View):
    """Vue persistante gérant le bouton de claim."""
    def __init__(self, ticket_id: Optional[int] = None):
        super().__init__(timeout=None)
        # Si un ID de ticket est fourni, on configure le custom_id de manière unique et prédictible
        if ticket_id is not None:
            self.claim_button.custom_id = f"claim_dev_{ticket_id}"

    @ui.button(label="🎯 Prendre la commande", style=discord.ButtonStyle.green, custom_id="dynamic_claim_dev_btn")
    async def claim_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        member = interaction.user
        
        # 1. Vérification du rôle Développeur
        dev_role = guild.get_role(ROLE_DEVELOPPEUR_ID)
        if not dev_role or dev_role not in member.roles:
            return await interaction.followup.send("❌ Seuls les membres avec le rôle Développeur peuvent prendre cette commande.", ephemeral=True)

        # 2. Extraction de l'ID du ticket depuis le custom_id personnalisé du bouton
        custom_id = button.custom_id
        if not custom_id.startswith("claim_dev_"):
            return await interaction.followup.send("❌ Erreur de configuration du bouton (ID invalide).", ephemeral=True)
        
        ticket_id = int(custom_id.split("_")[2])
        ticket_channel = guild.get_channel(ticket_id)

        if not ticket_channel:
            return await interaction.followup.send("❌ Le salon du ticket est introuvable (il a probablement été fermé).", ephemeral=True)

        # 3. Ajout du développeur dans le salon du ticket
        try:
            await ticket_channel.set_permissions(member, read_messages=True, send_messages=True, attach_files=True, manage_messages=True)
        except Exception as e:
            print("Erreur modification permissions claim :", e)
            return await interaction.followup.send("❌ Impossible de vous donner l'accès au ticket.", ephemeral=True)

        # 4. Message d'annonce dans le ticket
        await ticket_channel.send(f"💼 Le développeur {member.mention} vient de rejoindre le ticket pour prendre en charge la commande.")

        # 5. Désactivation définitive du bouton (Historique visuel du salon des commandes)
        button.label = f"Pris par {member.display_name}"
        button.style = discord.ButtonStyle.grey
        button.disabled = True
        
        await interaction.message.edit(view=self)
        await interaction.followup.send("✅ Vous avez pris en charge la commande avec succès !", ephemeral=True)


# ==============================================================================
# ------------------------- MODAL DE COMMANDE ----------------------------------
# ==============================================================================
class DeveloppeurModal(ui.Modal):
    """Formulaire de description du projet."""
    
    description = ui.TextInput(
        label="Description de votre projet",
        style=discord.TextStyle.paragraph,
        placeholder="Décrivez précisément votre besoin, vos fonctionnalités attendues, etc...",
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

        # 1. Configuration des permissions du ticket
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
                name=f"{self.info['emoji']}・dev-{user.name.lower()}",
                category=category,
                overwrites=overwrites,
                reason=f"Commande Dev {self.info['label']} - {user.display_name}"
            )
        except Exception as e:
            print("Erreur création salon dev :", e)
            return await interaction.followup.send("❌ Une erreur est survenue lors de la création de votre ticket.", ephemeral=True)

        # 4. Message de confirmation immédiat au client
        await interaction.followup.send(f"✅ Votre ticket de commande a été créé ici : {ticket_channel.mention}", ephemeral=True)

        # 5. Utilisation du config_manager pour l'embed interne du Ticket
        title_ticket = f"{self.info['emoji']} Nouvelle Commande : {self.info['label']}"
        desc_ticket = (
            f"Merci pour votre commande {user.mention} !\n"
            f"Un développeur va prendre en charge votre demande d'un instant à l'autre.\n\n"
            f"**Tarif indicatif :** {self.info['price']}\n\n"
            f"**Détails du projet :**\n> {self.description.value}"
        )

        if config_manager:
            embed_ticket = config_manager.get_formatted_embed(guild, user, self.bot, title_ticket, desc_ticket, guild.id)
        else:
            embed_ticket = discord.Embed(title=title_ticket, description=desc_ticket, color=0x3498db)
        
        embed_ticket.set_thumbnail(url=user.display_avatar.url)
        
        pings_ticket = [user.mention]
        if role_gestion: 
            pings_ticket.append(role_gestion.mention)
            
        await ticket_channel.send(content=" | ".join(pings_ticket), embed=embed_ticket)

        # 6. Utilisation du config_manager pour l'embed envoyé dans le salon public des Commandes
        channel_commande = guild.get_channel(CHANNEL_COMMANDE_ID)
        if channel_commande:
            role_dev = guild.get_role(ROLE_DEVELOPPEUR_ID)
            
            title_cmd = f"💼 Nouvelle offre disponible !"
            desc_cmd = (
                f"**Client :** {user.mention}\n"
                f"**Type :** {self.info['label']}\n"
                f"**Tarif estimé :** {self.info['price']}\n\n"
                f"**Cahier des charges :**\n```txt\n{self.description.value}\n```"
            )
            
            if config_manager:
                embed_commande = config_manager.get_formatted_embed(guild, user, self.bot, title_cmd, desc_cmd, guild.id)
            else:
                embed_commande = discord.Embed(title=title_cmd, description=desc_cmd, color=0xe67e22)
                
            embed_commande.set_footer(text=f"ID du Client : {user.id}")
            
            # Instanciation de la vue avec le bouton lié à l'ID unique de ce nouveau ticket
            view_claim = ClaimTicketView(ticket_id=ticket_channel.id)
            await channel_commande.send(content=role_dev.mention if role_dev else None, embed=embed_commande, view=view_claim)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        print("=== ERREUR DANS LA MODAL DEVELOPPEUR ===")
        traceback.print_exception(type(error), error, error.__traceback__)
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Une erreur est survenue lors du traitement de votre commande.", ephemeral=True)


# ==============================================================================
# ----------------------- VUE PERSISTANTE ET SÉLECTEUR -------------------------
# ==============================================================================
class DeveloppeurSelect(ui.Select):
    """Sélecteur persistant pour les offres de développement."""
    def __init__(self, bot: commands.Bot, cog_instance: commands.Cog):
        self.bot = bot
        self.cog_instance = cog_instance
        
        options = []
        for key, value in OPTIONS_DATA.items():
            options.append(discord.SelectOption(
                label=f"{value['label']} ➜ {value['price']}", # Rendu visuel plus propre
                value=key,
                description=value['desc'][:100],
                emoji=value['emoji']
            ))
        
        super().__init__(
            placeholder="🛒 Choisissez ce dont vous avez besoin...", 
            min_values=1, 
            max_values=1, 
            options=options, 
            custom_id="persistent_developpeur_selector"
        )

    async def callback(self, interaction: discord.Interaction):
        if not self.values:
            return await interaction.response.defer()

        selected_key = self.values[0]
        
        modal = DeveloppeurModal(bot=self.bot, option_key=selected_key, cog_instance=self.cog_instance)
        await interaction.response.send_modal(modal)

        # Réinitialisation visuelle du sélecteur
        try:
            for option in self.options:
                option.default = False
            if interaction.message:
                await interaction.message.edit(view=self.view)
        except Exception as e:
            print(f"[Avertissement] Impossible de réinitialiser le menu dev : {e}")


class DeveloppeurView(ui.View):
    """Vue globale contenant le sélecteur."""
    def __init__(self, bot: commands.Bot, cog_instance: commands.Cog):
        super().__init__(timeout=None)
        self.add_item(DeveloppeurSelect(bot, cog_instance))

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: ui.Item):
        print("=== ERREUR DANS LE SELECTEUR DEVELOPPEUR ===")
        traceback.print_exception(type(error), error, error.__traceback__)


# ==============================================================================
# -------------------------------- COG PRINCIPAL -------------------------------
# ==============================================================================
class DeveloppeurCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        """Recharge les structures de vues persistantes au démarrage complet."""
        # 1. Enregistrement du sélecteur d'origine
        self.bot.add_view(DeveloppeurView(self.bot, self))
        
        # 2. Écouteur universel des boutons de Claim :
        # En enregistrant une instance vide au reboot sans spécifier d'ID dans le constructeur,
        # discord.py associe l'événement à n'importe quel bouton dont le custom_id commence par "claim_dev_"
        self.bot.add_view(ClaimTicketView())

    @commands.hybrid_command(name="setup_developpeur_menu", description="[Admin] Injecte le sélecteur développement dans le message cible.")
    @commands.has_permissions(administrator=True)
    async def setup_developpeur(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)

        if ctx.guild.id != GUILD_TARGET_ID:
            return await ctx.send("❌ Commande réservée au serveur cible.", ephemeral=True)

        channel = self.bot.get_channel(CHANNEL_DEV_ID)
        if not channel:
            return await ctx.send(f"❌ Impossible de trouver le salon : `{CHANNEL_DEV_ID}`.", ephemeral=True)

        try:
            message = await channel.fetch_message(MESSAGE_DEV_ID)
            
            # Injection
            await message.edit(view=DeveloppeurView(self.bot, self))
            await ctx.send(f"✅ Menu de commande Développeur déployé avec succès : {message.jump_url}", ephemeral=True)
            
        except discord.NotFound:
            await ctx.send("❌ Message introuvable.", ephemeral=True)
        except discord.Forbidden:
            await ctx.send("❌ Permissions insuffisantes (le bot doit être l'auteur du message).", ephemeral=True)
        except Exception as e:
            print("Erreur SETUP DEV:", e)
            await ctx.send(f"❌ Erreur inattendue : {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(DeveloppeurCog(bot))