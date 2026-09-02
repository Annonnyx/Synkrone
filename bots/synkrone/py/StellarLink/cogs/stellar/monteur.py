# ==============================================================================
# Nom du fichier : monteur_video.py
# Description : Système de commande "Monteur Vidéo" avec salon de logs, claim persistant
#               et sauvegarde locale des données de commande.
# ==============================================================================

import os
import json
import discord
import traceback
from datetime import datetime
from pathlib import Path
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

# Configuration du salon et message d'origine (Sélecteur) -> À adapter
CHANNEL_MONTEUR_ID = 1518685529657446530  # Remplacez par l'ID du salon de commande vidéo
MESSAGE_MONTEUR_ID = 1518971230768861315  # Remplacez par l'ID du message ciblé

# Catégorie où créer les tickets de commande
CATEGORY_TICKETS_ID = 1518311378966937651

# Salon public de commande (où l'embed de claim est envoyé)
CHANNEL_COMMANDE_ID = 1518701142610280583

# Rôles
ROLE_GESTION_ID = 1518327264750862467  # Rôle Gestion global
ROLE_MONTEUR_VIDEO_ID = 1518441868000493618  # Remplacez par l'ID du rôle Monteur Vidéo

# ==============================================================================
# ------------------ GESTION DES DONNÉES (RÈGLE DATA) --------------------------
# ==============================================================================
# Chemin de data imposé : /data/staff/configuration/data_video/
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data" / "staff" / "configuration" / "data_video"

def save_order_data(guild_id: int, user_id: int, order_type: str, description: str):
    """Sauvegarde les informations de la commande dans le dossier data approprié."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    file_path = DATA_DIR / f"{guild_id}_orders.json"
    
    data = []
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
            
    data.append({
        "timestamp": datetime.now().isoformat(),
        "user_id": user_id,
        "order_type": order_type,
        "description": description
    })
    
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# ==============================================================================
# ------------------------- CATALOGUE PRODUITS ---------------------------------
# ==============================================================================
OPTIONS_DATA = {
    "video_courte": {
        "label": "Vidéo Courte (Verticale)", 
        "price": "15€", 
        "emoji": "📱", 
        "desc": "Idéal pour TikTok, Shorts, Reels. Format 30s à 1 min. Délai : 1 à 2 jours."
    },
    "video_longue": {
        "label": "Vidéo Longue (Horizontale)", 
        "price": "10€ / minute", 
        "emoji": "🎬", 
        "desc": "Idéal pour YouTube ou présentations. Format > 1 min. Délai : 4 à 7 jours."
    }
}

# ==============================================================================
# ---------------------- BOUTON DE PRISE EN CHARGE (PERSISTANT) ----------------
# ==============================================================================
class ClaimVideoTicketView(ui.View):
    """Vue persistante gérant le bouton de claim pour le Montage Vidéo."""
    def __init__(self, ticket_id: Optional[int] = None):
        super().__init__(timeout=None)
        if ticket_id is not None:
            self.claim_button.custom_id = f"claim_video_{ticket_id}"

    @ui.button(label="🎯 Prendre la commande", style=discord.ButtonStyle.green, custom_id="dynamic_claim_video_btn")
    async def claim_button(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        member = interaction.user
        
        # 1. Vérification du rôle Monteur Vidéo
        monteur_role = guild.get_role(ROLE_MONTEUR_VIDEO_ID)
        if not monteur_role or monteur_role not in member.roles:
            return await interaction.followup.send("❌ Seuls les membres avec le rôle Monteur Vidéo peuvent prendre cette commande.", ephemeral=True)

        # 2. Extraction de l'ID du ticket depuis le custom_id
        custom_id = button.custom_id
        if not custom_id.startswith("claim_video_"):
            return await interaction.followup.send("❌ Erreur de configuration du bouton (ID invalide).", ephemeral=True)
        
        ticket_id = int(custom_id.split("_")[2])
        ticket_channel = guild.get_channel(ticket_id)

        if not ticket_channel:
            return await interaction.followup.send("❌ Le salon du ticket est introuvable (il a probablement été fermé).", ephemeral=True)

        # 3. Ajout du monteur dans le salon du ticket
        try:
            await ticket_channel.set_permissions(member, read_messages=True, send_messages=True, attach_files=True, manage_messages=True)
        except Exception as e:
            print("Erreur modification permissions claim vidéo :", e)
            return await interaction.followup.send("❌ Impossible de vous donner l'accès au ticket.", ephemeral=True)

        # 4. Message d'annonce dans le ticket
        await ticket_channel.send(f"🎬 Le monteur vidéo {member.mention} vient de rejoindre le ticket pour prendre en charge la commande.")

        # 5. Désactivation définitive du bouton
        button.label = f"Pris par {member.display_name}"
        button.style = discord.ButtonStyle.grey
        button.disabled = True
        
        await interaction.message.edit(view=self)
        await interaction.followup.send("✅ Vous avez pris en charge la commande avec succès !", ephemeral=True)

# ==============================================================================
# ------------------------- MODAL DE COMMANDE ----------------------------------
# ==============================================================================
class VideoModal(ui.Modal):
    """Formulaire de description du projet vidéo."""
    
    description = ui.TextInput(
        label="Description de votre projet vidéo",
        style=discord.TextStyle.paragraph,
        placeholder="Liens vers les rushs, style de montage (dynamique, vlog, pro), durée approximative...",
        required=True,
        min_length=20,
        max_length=3000
    )

    def __init__(self, bot: commands.Bot, option_key: str, cog_instance: commands.Cog):
        self.info = OPTIONS_DATA[option_key]
        self.option_key = option_key
        super().__init__(title=f"Commande : {self.info['label']}")
        self.bot = bot
        self.cog_instance = cog_instance

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user

        # 1. Sauvegarde des données (Architecture exigée)
        save_order_data(guild.id, user.id, self.info['label'], self.description.value)

        # 2. Configuration des permissions du ticket (Client + Gestion uniquement)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
        }

        role_gestion = guild.get_role(ROLE_GESTION_ID)
        if role_gestion:
            overwrites[role_gestion] = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True)

        # 3. Récupération de la catégorie cible
        category = guild.get_channel(CATEGORY_TICKETS_ID)
        if not isinstance(category, discord.CategoryChannel):
            category = None

        # 4. Création du salon Ticket
        try:
            ticket_channel = await guild.create_text_channel(
                name=f"{self.info['emoji']}・video-{user.name.lower()}",
                category=category,
                overwrites=overwrites,
                reason=f"Commande Vidéo {self.info['label']} - {user.display_name}"
            )
        except Exception as e:
            print("Erreur création salon vidéo :", e)
            return await interaction.followup.send("❌ Une erreur est survenue lors de la création de votre ticket.", ephemeral=True)

        # 5. Message de confirmation immédiat au client
        await interaction.followup.send(f"✅ Votre ticket de commande a été créé ici : {ticket_channel.mention}", ephemeral=True)

        # 6. Utilisation du config_manager pour l'embed interne du Ticket
        title_ticket = f"{self.info['emoji']} Nouvelle Commande : {self.info['label']}"
        desc_ticket = (
            f"Merci pour votre commande {user.mention} !\n"
            f"Un Monteur Vidéo va prendre en charge votre demande d'un instant à l'autre.\n\n"
            f"**Tarif indicatif :** {self.info['price']}\n"
            f"**Délai estimé :** {self.info['desc'].split('Délai : ')[-1]}\n\n"
            f"**Cahier des charges fourni :**\n> {self.description.value}"
        )

        if config_manager:
            embed_ticket = config_manager.get_formatted_embed(guild, user, self.bot, title_ticket, desc_ticket, guild.id)
        else:
            embed_ticket = discord.Embed(title=title_ticket, description=desc_ticket, color=0x2ecc71)
        
        embed_ticket.set_thumbnail(url=user.display_avatar.url)
        
        pings_ticket = [user.mention]
        if role_gestion: 
            pings_ticket.append(role_gestion.mention)
            
        await ticket_channel.send(content=" | ".join(pings_ticket), embed=embed_ticket)

        # 7. Utilisation du config_manager pour l'embed du salon public des Commandes
        channel_commande = guild.get_channel(CHANNEL_COMMANDE_ID)
        if channel_commande:
            role_monteur = guild.get_role(ROLE_MONTEUR_VIDEO_ID)
            
            title_cmd = f"🎬 Nouveau projet vidéo disponible !"
            desc_cmd = (
                f"**Client :** {user.mention}\n"
                f"**Type de projet :** {self.info['label']}\n"
                f"**Base tarifaire :** {self.info['price']}\n\n"
                f"**Description de la demande :**\n```txt\n{self.description.value}\n```"
            )
            
            if config_manager:
                embed_commande = config_manager.get_formatted_embed(guild, user, self.bot, title_cmd, desc_cmd, guild.id)
            else:
                embed_commande = discord.Embed(title=title_cmd, description=desc_cmd, color=0xe67e22)
                
            embed_commande.set_footer(text=f"ID du Client : {user.id}")
            
            # Instanciation de la vue persistante liée au ticket
            view_claim = ClaimVideoTicketView(ticket_id=ticket_channel.id)
            await channel_commande.send(content=role_monteur.mention if role_monteur else None, embed=embed_commande, view=view_claim)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        print("=== ERREUR DANS LA MODAL VIDEO ===")
        traceback.print_exception(type(error), error, error.__traceback__)
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Une erreur est survenue lors du traitement de votre commande.", ephemeral=True)

# ==============================================================================
# ----------------------- VUE PERSISTANTE ET SÉLECTEUR -------------------------
# ==============================================================================
class VideoSelect(ui.Select):
    """Sélecteur persistant pour le catalogue de montage vidéo."""
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
            placeholder="🎬 Commandez votre montage vidéo...", 
            min_values=1, 
            max_values=1, 
            options=options, 
            custom_id="persistent_video_selector"
        )

    async def callback(self, interaction: discord.Interaction):
        if not self.values:
            return await interaction.response.defer()

        selected_key = self.values[0]
        
        modal = VideoModal(bot=self.bot, option_key=selected_key, cog_instance=self.cog_instance)
        await interaction.response.send_modal(modal)

        # Réinitialisation visuelle du sélecteur
        try:
            for option in self.options:
                option.default = False
            if interaction.message:
                await interaction.message.edit(view=self.view)
        except Exception as e:
            print(f"[Avertissement] Impossible de réinitialiser le menu vidéo : {e}")

class VideoView(ui.View):
    """Vue globale contenant le sélecteur vidéo."""
    def __init__(self, bot: commands.Bot, cog_instance: commands.Cog):
        super().__init__(timeout=None)
        self.add_item(VideoSelect(bot, cog_instance))

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: ui.Item):
        print("=== ERREUR DANS LE SELECTEUR VIDEO ===")
        traceback.print_exception(type(error), error, error.__traceback__)

# ==============================================================================
# -------------------------------- COG PRINCIPAL -------------------------------
# ==============================================================================
class MonteurVideoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        """Recharge les structures de vues persistantes au démarrage du bot."""
        # 1. Enregistrement du sélecteur du catalogue
        self.bot.add_view(VideoView(self.bot, self))
        
        # 2. Écouteur universel pour capter les interactions de claim
        self.bot.add_view(ClaimVideoTicketView())

    @commands.hybrid_command(name="setup_video_menu", description="[Admin] Injecte le sélecteur vidéo dans le message cible.")
    @commands.has_permissions(administrator=True)
    async def setup_video(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)

        if ctx.guild.id != GUILD_TARGET_ID:
            return await ctx.send("❌ Commande réservée au serveur cible.", ephemeral=True)

        channel = self.bot.get_channel(CHANNEL_MONTEUR_ID)
        if not channel:
            return await ctx.send(f"❌ Impossible de trouver le salon : `{CHANNEL_MONTEUR_ID}`.", ephemeral=True)

        try:
            message = await channel.fetch_message(MESSAGE_MONTEUR_ID)
            
            # Injection
            await message.edit(view=VideoView(self.bot, self))
            await ctx.send(f"✅ Menu de commande Monteur Vidéo déployé avec succès : {message.jump_url}", ephemeral=True)
            
        except discord.NotFound:
            await ctx.send("❌ Message introuvable.", ephemeral=True)
        except discord.Forbidden:
            await ctx.send("❌ Permissions insuffisantes (le bot doit être l'auteur du message).", ephemeral=True)
        except Exception as e:
            print("Erreur SETUP VIDEO:", e)
            await ctx.send(f"❌ Erreur inattendue : {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(MonteurVideoCog(bot))