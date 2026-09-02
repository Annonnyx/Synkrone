import discord
from discord.ext import commands
from discord import app_commands
from discord import ui
import os
import json
import logging

# Configuration du logging
logger = logging.getLogger('discord')

# ==============================================================================
# --------------------------- IMPORTATION UTILS --------------------------------
# ==============================================================================
# Importation de ton config_manager exactement comme dans ton script artiste
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None
    logger.warning("config_manager non trouvé. Utilisation des embeds par défaut.")

# ==============================================================================
# ----------------------- CONFIGURATION DES IDs --------------------------------
# ==============================================================================
# Catégorie où seront créés les tickets
CATEGORY_TICKETS_ID = 1518311378966937651

# Rôle "Gérant" (aura accès au ticket et sera pingé)
ROLE_GESTION_ID = 1518327264750862467

# ==============================================================================
# ----------------------------- GESTION DES DONNÉES ----------------------------
# ==============================================================================
ROOT_DIR = os.getcwd()
DATA_DIR = os.path.join(ROOT_DIR, "data", "staff", "support")
os.makedirs(DATA_DIR, exist_ok=True)

def get_guild_data_path(guild_id: int) -> str:
    return os.path.join(DATA_DIR, f"{guild_id}.json")

def load_guild_data(guild_id: int) -> dict:
    path = get_guild_data_path(guild_id)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erreur de lecture JSON pour {guild_id}: {e}")
    return {"ticket_count": 0, "active_tickets": {}}

def save_guild_data(guild_id: int, data: dict):
    path = get_guild_data_path(guild_id)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Erreur d'écriture JSON pour {guild_id}: {e}")

# ==============================================================================
# ------------------------------ INTERFACES (UI) -------------------------------
# ==============================================================================

class SupportModal(ui.Modal):
    def __init__(self, bot, category: str, cog_instance):
        super().__init__(title=f"Support : {category[:30]}")
        self.bot = bot
        self.category = category
        self.cog = cog_instance

    description = ui.TextInput(
        label="Détaillez votre demande",
        style=discord.TextStyle.paragraph,
        placeholder="Expliquez-nous votre besoin en quelques lignes pour que l'équipe puisse vous aider...",
        required=True,
        min_length=15,
        max_length=2000
    )

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user

        data = load_guild_data(guild.id)
        data["ticket_count"] += 1
        ticket_id = data["ticket_count"]

        # 1. Récupération de la catégorie
        category_channel = guild.get_channel(CATEGORY_TICKETS_ID)
        if not isinstance(category_channel, discord.CategoryChannel):
            category_channel = None # Sécurité si la catégorie est introuvable

        # 2. Gestion des rôles et des permissions
        role_gestion = guild.get_role(ROLE_GESTION_ID)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        
        if role_gestion:
            overwrites[role_gestion] = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True)

        # 3. Création du salon dans la bonne catégorie
        safe_category = self.category.split(" ")[0].lower()
        channel_name = f"🎫│{safe_category}-{ticket_id:04d}"
        
        try:
            ticket_channel = await guild.create_text_channel(
                name=channel_name,
                category=category_channel,
                overwrites=overwrites,
                reason=f"Support demandé par {user.name}"
            )
        except discord.Forbidden:
            return await interaction.followup.send("❌ Je n'ai pas les permissions pour créer des salons.", ephemeral=True)
        except Exception as e:
            logger.error(f"Erreur création salon: {e}")
            return await interaction.followup.send("❌ Une erreur est survenue lors de la création du ticket.", ephemeral=True)

        # Enregistrement local
        data["active_tickets"][str(ticket_channel.id)] = {"user_id": user.id, "category": self.category}
        save_guild_data(guild.id, data)

        # 4. Construction de l'Embed de bienvenue via config_manager
        title_ticket = f"Ticket #{ticket_id:04d} - {self.category}"
        desc_ticket = (
            f"Bonjour {user.mention},\n\n"
            f"Notre équipe va prendre en charge votre demande sous peu.\n\n"
            f"**Votre message :**\n"
            f"> {self.description.value}"
        )

        if config_manager:
            # Même utilisation de config_manager que dans devenir_artiste.py
            embed = config_manager.get_formatted_embed(guild, user, self.bot, title_ticket, desc_ticket, guild.id)
        else:
            embed = discord.Embed(title=title_ticket, description=desc_ticket, color=0x2ecc71)
            
        embed.set_thumbnail(url=user.display_avatar.url)

        # 5. Pings et envoi du message (SANS le bouton "fermer")
        pings = [user.mention]
        if role_gestion:
            pings.append(role_gestion.mention)

        await ticket_channel.send(content=" | ".join(pings), embed=embed)

        # Confirmation silencieuse à l'utilisateur
        await interaction.followup.send(f"✅ Ton ticket a été créé avec succès : {ticket_channel.mention}", ephemeral=True)

class SupportSelect(ui.Select):
    def __init__(self, bot, cog_instance):
        self.bot = bot
        self.cog = cog_instance
        
        options = [
            discord.SelectOption(label="Réclamer une récompense de giveaway", value="Giveaway", emoji="🎁"),
            discord.SelectOption(label="Signaler un artiste", value="Signalement", emoji="⚠️"),
            discord.SelectOption(label="Autres demandes", value="Autre", emoji="📩")
        ]
        
        super().__init__(
            placeholder="Sélectionnez le motif de votre ticket...", 
            min_values=1, 
            max_values=1, 
            options=options, 
            custom_id="premium_support_select"
        )

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        await interaction.response.send_modal(SupportModal(self.bot, category, self.cog))

class SupportSetupView(ui.View):
    def __init__(self, bot, cog_instance):
        super().__init__(timeout=None)
        self.add_item(SupportSelect(bot, cog_instance))

# ==============================================================================
# -------------------------------- COG PRINCIPAL -------------------------------
# ==============================================================================

class SupportCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(SupportSetupView(self.bot, self))
        logger.info("[Cog] Support system chargé et vue persistante activée.")

    @commands.hybrid_command(name="setup_support", description="[Admin] Déploie l'interface de création de tickets.")
    @commands.has_permissions(administrator=True)
    async def setup_support(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)

        title = "🎫 Centre d'Assistance"
        desc = (
            "Bienvenue dans notre centre de support.\n"
            "Pour garantir une réponse rapide de notre équipe, merci de choisir la catégorie qui correspond à votre besoin via le menu ci-dessous.\n\n"
            "**Les catégories :**\n"
            "🎁 **Récompense de giveaway :** Vous avez gagné à l'un de nos concours.\n"
            "⚠️ **Signaler un artiste :** Un problème de comportement, d'arnaque ou de plagiat.\n"
            "📩 **Autres demandes :** Tout ce qui ne rentre pas dans les autres catégories.\n\n"
            "*L'équipe vous répondra dans les plus brefs délais.*"
        )

        if config_manager:
            embed = config_manager.get_formatted_embed(ctx.guild, ctx.author, self.bot, title, desc, ctx.guild.id)
            if ctx.guild.icon:
                embed.set_thumbnail(url=ctx.guild.icon.url)
        else:
            embed = discord.Embed(title=title, description=desc, color=0x2b2d31)
            if ctx.guild.icon:
                embed.set_thumbnail(url=ctx.guild.icon.url)

        try:
            await ctx.channel.send(embed=embed, view=SupportSetupView(self.bot, self))
            await ctx.send("✅ Panneau de support déployé avec succès.", ephemeral=True)
        except discord.Forbidden:
            await ctx.send("❌ Je n'ai pas la permission d'envoyer des messages ici.", ephemeral=True)
        except Exception as e:
            logger.error(f"Erreur lors du déploiement : {e}")
            await ctx.send("❌ Une erreur est survenue lors du déploiement.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(SupportCog(bot))