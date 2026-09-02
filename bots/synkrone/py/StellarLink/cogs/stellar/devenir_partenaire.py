# ==============================================================================
# Nom du fichier : devenir_partenaire.py
# Description : Système de candidature "Partenaire" avec interface persistante
# ==============================================================================

import os
import json
import discord
import traceback
from datetime import datetime
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

# Salon "devenir partenaire" où se trouve le message
CHANNEL_PARTENAIRE_ID = 1518950123487367202

# Message spécifique sur lequel greffer le sélecteur
MESSAGE_PARTENAIRE_ID = 1518960477621850284

# Catégorie où seront créés les tickets de candidature
CATEGORY_TICKETS_ID = 1518311378966937651

# Rôle "Gestion des Partenariats" (toujours notifié)
ROLE_GESTION_PARTENARIAT_ID = 1518327264750862467

# ==============================================================================
# ------------------------- GESTION DES DONNÉES --------------------------------
# ==============================================================================
# Chemin absolu vers la racine du projet / data
DATA_DIR = os.path.join(os.getcwd(), "data", "staff", "configuration", "data_partenaire")

def save_application_data(guild_id: int, user_id: int, data: dict):
    """Sauvegarde les candidatures en JSON de manière asynchrone / thread-safe."""
    os.makedirs(DATA_DIR, exist_ok=True)
    file_path = os.path.join(DATA_DIR, f"{guild_id}_partenariats.json")
    
    try:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                content = json.load(f)
        else:
            content = {}

        if str(user_id) not in content:
            content[str(user_id)] = []
            
        content[str(user_id)].append(data)
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(content, f, indent=4, ensure_ascii=False)
    except Exception as e:
        print(f"[ERREUR] Sauvegarde JSON Partenariat : {e}")

# ==============================================================================
# ------------------------- MODAL DE CANDIDATURE -------------------------------
# ==============================================================================
class PartenaireModal(ui.Modal):
    """Formulaire modal dynamique qui s'ouvre après la sélection d'un type de partenariat."""

    def __init__(self, bot: commands.Bot, type_partenariat: str, cog_instance: commands.Cog):
        super().__init__(title=f"Demande : {type_partenariat}")
        self.bot = bot
        self.type_partenariat = type_partenariat
        self.cog_instance = cog_instance

        # 1. Champ : Nom du serveur
        self.nom_serveur = ui.TextInput(
            label="Nom de votre Serveur / Projet",
            style=discord.TextStyle.short,
            placeholder="Ex: Mon Super Serveur",
            required=True,
            max_length=100
        )
        self.add_item(self.nom_serveur)

        # 2. Champ : Lien du serveur
        self.lien_serveur = ui.TextInput(
            label="Lien d'invitation",
            style=discord.TextStyle.short,
            placeholder="https://discord.gg/...",
            required=True
        )
        self.add_item(self.lien_serveur)

        # 3. Champ : Description
        self.description = ui.TextInput(
            label="Description de votre projet",
            style=discord.TextStyle.paragraph,
            placeholder="Décrivez votre communauté, vos statistiques, et ce que vous attendez du partenariat...",
            required=True,
            min_length=30,
            max_length=3000
        )
        self.add_item(self.description)

        # 4. Champ : Avantages (Uniquement pour les "Partenaires")
        self.avantages = None
        if self.type_partenariat == "Partenaires":
            self.avantages = ui.TextInput(
                label="Piste d'avantages (Facultatif)",
                style=discord.TextStyle.paragraph,
                placeholder="Ex: Rôles exclusifs, salons dédiés, mentions mutuelles, giveaways croisés...",
                required=False,
                max_length=1000
            )
            self.add_item(self.avantages)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        user = interaction.user

        # 1. Sauvegarde des données
        application_data = {
            "type": self.type_partenariat,
            "nom_serveur": self.nom_serveur.value,
            "lien": self.lien_serveur.value,
            "description": self.description.value,
            "avantages": self.avantages.value if self.avantages else None,
            "timestamp": datetime.now().isoformat()
        }
        save_application_data(guild.id, user.id, application_data)

        # 2. Gestion des permissions du ticket
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
        }

        role_gestion = guild.get_role(ROLE_GESTION_PARTENARIAT_ID)
        if role_gestion:
            overwrites[role_gestion] = discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_messages=True)

        # 3. Récupération de la catégorie cible
        category = guild.get_channel(CATEGORY_TICKETS_ID)
        if not isinstance(category, discord.CategoryChannel):
            category = None

        # 4. Création du salon Ticket
        emoji = "💎" if self.type_partenariat == "Partenaires" else "🤝"

        try:
            ticket_channel = await guild.create_text_channel(
                name=f"{emoji}・partenariat-{user.name.lower()}",
                category=category,
                overwrites=overwrites,
                reason=f"Demande {self.type_partenariat} - {user.display_name}"
            )
        except Exception as e:
            print("Erreur création salon partenariat :", e)
            return await interaction.followup.send("❌ Une erreur est survenue lors de la création du ticket.", ephemeral=True)

        # 5. Message de confirmation
        await interaction.followup.send(f"✅ Ta demande a bien été envoyée ! Un responsable te répondra ici : {ticket_channel.mention}", ephemeral=True)

        # 6. Construction et Envoi de l'Embed dans le ticket
        title = f"{emoji} Nouvelle Demande : {self.type_partenariat}"
        description_embed = (
            f"Un nouveau serveur souhaite collaborer avec nous !\n\n"
            f"**Représentant :** {user.mention}\n"
            f"**Nom du Serveur :** `{self.nom_serveur.value}`\n"
            f"**Lien :** {self.lien_serveur.value}\n\n"
            f"**Description détaillée :**\n"
            f"> {self.description.value}"
        )

        # Ajout des avantages s'ils ont été remplis (uniquement pour Partenaires)
        if self.avantages and self.avantages.value.strip():
            description_embed += f"\n\n**Pistes d'avantages proposés :**\n> {self.avantages.value}"

        if config_manager:
            embed = config_manager.get_formatted_embed(guild, user, self.bot, title, description_embed, guild.id)
        else:
            embed = discord.Embed(title=title, description=description_embed, color=0x3498db)
        
        embed.set_thumbnail(url=user.display_avatar.url)

        # Préparation du ping (Utilisateur + Rôle Gestion Partenariat)
        pings = [user.mention]
        if role_gestion: pings.append(role_gestion.mention)

        await ticket_channel.send(content=" | ".join(pings), embed=embed)

    async def on_error(self, interaction: discord.Interaction, error: Exception):
        print("=== ERREUR DANS LA MODAL PARTENARIAT ===")
        traceback.print_exception(type(error), error, error.__traceback__)
        if not interaction.response.is_done():
            await interaction.response.send_message("❌ Une erreur est survenue lors du traitement.", ephemeral=True)

# ==============================================================================
# ----------------------- VUE PERSISTANTE ET SÉLECTEUR -------------------------
# ==============================================================================
class PartenaireSelect(ui.Select):
    """Sélecteur persistant pour le choix du type de partenariat."""
    def __init__(self, bot: commands.Bot, cog_instance: commands.Cog):
        self.bot = bot
        self.cog_instance = cog_instance
        
        options = [
            discord.SelectOption(
                label="Partenaires", 
                value="Partenaires", 
                description="Regroupe nos partenaires privilégiés vous offrant des avantages exclusifs.", 
                emoji="💎"
            ),
            discord.SelectOption(
                label="Partenariats", 
                value="Partenariats", 
                description="Centralise l'ensemble des serveurs qui collaborent avec nous.", 
                emoji="🤝"
            )
        ]
        
        super().__init__(
            placeholder="🔗 Soumettre une demande de partenariat...", 
            min_values=1, 
            max_values=1, 
            options=options, 
            custom_id="persistent_partenaire_selector"
        )

    async def callback(self, interaction: discord.Interaction):
        if not self.values:
            return await interaction.response.defer()

        selected_type = self.values[0]
        
        # Ouverture de la Modal dynamique IMMÉDIATEMENT
        modal = PartenaireModal(bot=self.bot, type_partenariat=selected_type, cog_instance=self.cog_instance)
        await interaction.response.send_modal(modal)

        # Réinitialisation visuelle propre
        try:
            for option in self.options:
                option.default = False
            
            if interaction.message:
                await interaction.message.edit(view=self.view)
        except Exception as e:
            print(f"[Avertissement] Impossible de réinitialiser le menu partenariat : {e}")

class PartenaireView(ui.View):
    """Vue persistante contenant le menu déroulant."""
    def __init__(self, bot: commands.Bot, cog_instance: commands.Cog):
        super().__init__(timeout=None) # Toujours None pour une vue persistante
        self.add_item(PartenaireSelect(bot, cog_instance))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Sécurité globale pour la vue."""
        if interaction.user.bot:
            return False
        return True

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: ui.Item):
        print("=== ERREUR DANS LE SELECTEUR PARTENARIAT ===")
        traceback.print_exception(type(error), error, error.__traceback__)

# ==============================================================================
# -------------------------------- COG PRINCIPAL -------------------------------
# ==============================================================================
class DevenirPartenaireCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        """Recharge la vue persistante au démarrage du bot."""
        self.bot.add_view(PartenaireView(self.bot, self))

    @commands.hybrid_command(name="setup_partenaire_menu", description="[Admin] Injecte le sélecteur de partenariat dans le message cible.")
    @commands.has_permissions(administrator=True)
    async def setup_partenaire(self, ctx: commands.Context):
        await ctx.defer(ephemeral=True)

        if ctx.guild.id != GUILD_TARGET_ID:
            return await ctx.send("❌ Commande réservée au serveur cible.", ephemeral=True)

        channel = self.bot.get_channel(CHANNEL_PARTENAIRE_ID)
        if not channel:
            return await ctx.send(f"❌ Impossible de trouver le salon : `{CHANNEL_PARTENAIRE_ID}`.", ephemeral=True)

        try:
            message = await channel.fetch_message(MESSAGE_PARTENAIRE_ID)
            
            # Injection du nouveau sélecteur
            await message.edit(view=PartenaireView(self.bot, self))
            await ctx.send(f"✅ Menu déroulant de partenariats déployé et synchronisé : {message.jump_url}", ephemeral=True)
            
        except discord.NotFound:
            await ctx.send("❌ Message introuvable.", ephemeral=True)
        except discord.Forbidden:
            await ctx.send("❌ Permissions insuffisantes (le bot doit être l'auteur du message).", ephemeral=True)
        except Exception as e:
            print("Erreur SETUP PARTENARIAT:", e)
            await ctx.send(f"❌ Erreur inattendue : {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(DevenirPartenaireCog(bot))