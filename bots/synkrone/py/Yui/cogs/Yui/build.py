import discord
from discord.ext import commands
from discord import app_commands, ui
import asyncio
import traceback

# ===================== IMPORTATION CONFIG MANAGER ====================
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# ==============================================================================
# --------------------------- VUES DE RETOUR -----------------------------------
# ==============================================================================

class ReturnView(ui.View):
    """Vue qui s'affiche après une création, avec un bouton pour retourner au menu."""
    def __init__(self, bot: commands.Bot, author: discord.Member, original_message: discord.Message):
        super().__init__(timeout=600) # Timeout 10 minutes
        self.bot = bot
        self.author = author
        self.message = original_message

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message("❌ Ce menu ne vous est pas destiné.", ephemeral=True)
            return False
        return True

    @ui.button(label="Retour au Menu Principal", style=discord.ButtonStyle.primary, emoji="🔙")
    async def btn_return(self, interaction: discord.Interaction, button: ui.Button):
        # On recrée le menu principal
        view = BuilderMenu(self.bot, self.author)
        view.message = self.message
        embed = view.generate_embed(interaction.guild)
        
        # On met à jour le message d'origine
        await interaction.response.edit_message(embed=embed, view=view)


# ==============================================================================
# --------------------------- MODALS DE CRÉATION -------------------------------
# ==============================================================================

class CategoryPackModal(ui.Modal):
    def __init__(self, bot: commands.Bot, author: discord.Member, original_message: discord.Message):
        super().__init__(title="🏗️ Création de Pack (Catégorie + Salons)", timeout=600)
        self.bot = bot
        self.author = author
        self.message = original_message

        self.cat_name = ui.TextInput(label="Nom de la Catégorie", required=True, max_length=100)
        self.txt_channels = ui.TextInput(label="Salons Textuels (séparés par des virgules)", style=discord.TextStyle.paragraph, required=False)
        self.voc_channels = ui.TextInput(label="Salons Vocaux (séparés par des virgules)", style=discord.TextStyle.paragraph, required=False)
        self.forum_channels = ui.TextInput(label="Salons Forums (séparés par des virgules)", style=discord.TextStyle.paragraph, required=False)

        self.add_item(self.cat_name)
        self.add_item(self.txt_channels)
        self.add_item(self.voc_channels)
        self.add_item(self.forum_channels)

    async def on_submit(self, interaction: discord.Interaction):
        # On valide l'interaction du modal
        await interaction.response.defer()
        guild = interaction.guild
        
        # Mise à jour de l'embed pour montrer le chargement (on retire la view pendant le chargement)
        loading_embed = discord.Embed(title="⏳ Création en cours...", description="Veuillez patienter pendant la création du pack...", color=0xf39c12)
        await self.message.edit(embed=loading_embed, view=None)
        
        created_count = 0
        failed_count = 0

        try:
            category = await guild.create_category(name=self.cat_name.value.strip(), reason=f"Mass Pack Build par {self.author}")
            created_count += 1
            await asyncio.sleep(0.5)

            async def process_channels(raw_values, channel_type):
                nonlocal created_count, failed_count
                if not raw_values: return
                names = [n.strip() for n in raw_values.split(',') if n.strip()]
                for name in names:
                    try:
                        if channel_type == 'text': await guild.create_text_channel(name=name, category=category)
                        elif channel_type == 'voice': await guild.create_voice_channel(name=name, category=category)
                        elif channel_type == 'forum': await guild.create_forum(name=name, category=category)
                        created_count += 1
                        await asyncio.sleep(0.5)
                    except Exception:
                        failed_count += 1

            await process_channels(self.txt_channels.value, 'text')
            await process_channels(self.voc_channels.value, 'voice')
            await process_channels(self.forum_channels.value, 'forum')

            desc = f"**Catégorie :** {category.mention}\n**Succès :** {created_count} élément(s).\n**Échecs :** {failed_count} élément(s)."
            
            # Embed de succès
            if config_manager:
                final_embed = config_manager.get_formatted_embed(guild=guild, user=self.author, bot=self.bot, title="✅ Pack Créé avec Succès", description=desc)
            else:
                final_embed = discord.Embed(title="✅ Pack Créé avec Succès", description=desc, color=0x2ecc71)

            # Restaure la vue de retour sur le message
            await self.message.edit(embed=final_embed, view=ReturnView(self.bot, self.author, self.message))

        except Exception as e:
            await self.message.edit(embed=discord.Embed(title="❌ Erreur Critique", description=str(e), color=0xe74c3c), view=ReturnView(self.bot, self.author, self.message))


class MassCreateModal(ui.Modal):
    def __init__(self, bot: commands.Bot, action_type: str, author: discord.Member, original_message: discord.Message):
        titles = {
            'role': "🛠️ Création de Rôles", 'text_channel': "💬 Création Textuels",
            'voice_channel': "🔊 Création Vocaux", 'category': "📂 Création Catégories",
            'forum': "📝 Création Forums"
        }
        super().__init__(title=titles.get(action_type, "Création"), timeout=600)
        self.bot = bot
        self.action_type = action_type
        self.author = author
        self.message = original_message

        self.items_input = ui.TextInput(label="Noms (séparés par des virgules)", style=discord.TextStyle.paragraph, required=True, max_length=1000)
        self.add_item(self.items_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild
        names = [n.strip() for n in self.items_input.value.split(',') if n.strip()]
        
        loading_embed = discord.Embed(title=f"⏳ Création de {len(names)} élément(s) en cours...", color=0xf39c12)
        await self.message.edit(embed=loading_embed, view=None)

        created, failed = 0, 0
        for name in names:
            try:
                if self.action_type == 'role': await guild.create_role(name=name)
                elif self.action_type == 'text_channel': await guild.create_text_channel(name=name)
                elif self.action_type == 'voice_channel': await guild.create_voice_channel(name=name)
                elif self.action_type == 'category': await guild.create_category(name=name)
                elif self.action_type == 'forum': await guild.create_forum(name=name)
                created += 1
                await asyncio.sleep(0.5)
            except Exception: failed += 1

        desc = f"**Succès :** {created} élément(s).\n**Échecs :** {failed} élément(s)."
        if config_manager:
            final_embed = config_manager.get_formatted_embed(guild=guild, user=self.author, bot=self.bot, title="✅ Création Terminée", description=desc)
        else:
            final_embed = discord.Embed(title="✅ Création Terminée", description=desc, color=0x2ecc71)

        await self.message.edit(embed=final_embed, view=ReturnView(self.bot, self.author, self.message))


# ==============================================================================
# --------------------------- SELECTEUR ET MENU PRINCIPAL ----------------------
# ==============================================================================

class BuilderSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Pack : Catégorie + Salons", value="pack", emoji="📦", description="Crée une structure complète"),
            discord.SelectOption(label="Créer des Rôles", value="role", emoji="🎭", description="Crée plusieurs rôles d'un coup"),
            discord.SelectOption(label="Créer des Salons Textuels", value="text_channel", emoji="💬", description="Crée des salons écrits"),
            discord.SelectOption(label="Créer des Salons Vocaux", value="voice_channel", emoji="🔊", description="Crée des salons vocaux"),
            discord.SelectOption(label="Créer des Forums", value="forum", emoji="📝", description="Crée des salons forums"),
        ]
        super().__init__(placeholder="Que souhaitez-vous créer ?", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        # self.view contient la référence vers BuilderMenu
        val = self.values[0]
        
        # Ouvre le Modal approprié en lui transmettant le message d'origine
        if val == 'pack':
            await interaction.response.send_modal(CategoryPackModal(self.view.bot, self.view.author, self.view.message))
        else:
            await interaction.response.send_modal(MassCreateModal(self.view.bot, val, self.view.author, self.view.message))


class BuilderMenu(ui.View):
    def __init__(self, bot: commands.Bot, author: discord.Member):
        super().__init__(timeout=600) # Timeout 10 minutes
        self.bot = bot
        self.author = author
        self.message = None # Sera attribué lors de l'envoi du message initial

        self.add_item(BuilderSelect())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message("❌ Ce menu ne vous est pas destiné.", ephemeral=True)
            return False
        return True

    def generate_embed(self, guild: discord.Guild) -> discord.Embed:
        title = "🏗️ Constructeur de Serveur"
        desc = (
            "Bienvenue dans l'outil de création massive.\n"
            "Utilisez le menu déroulant ci-dessous pour sélectionner le type d'éléments à construire.\n\n"
            "💡 **Astuce** : Le mode `Pack` permet de créer une catégorie et ses salons d'un coup."
        )
        if config_manager:
            return config_manager.get_formatted_embed(guild=guild, user=self.author, bot=self.bot, title=title, description=desc)
        else:
            return discord.Embed(title=title, description=desc, color=0xf1c40f)


# ==============================================================================
# --------------------------- COG BUILDER --------------------------------------
# ==============================================================================

class MassBuilderCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="build", description="Menu avancé et dynamique pour construire le serveur.")
    @commands.has_permissions(administrator=True)
    @app_commands.default_permissions(administrator=True)
    async def massbuilder(self, ctx: commands.Context):
        view = BuilderMenu(self.bot, ctx.author)
        embed = view.generate_embed(ctx.guild)

        if ctx.interaction:
            await ctx.send(embed=embed, view=view)
            # Sauvegarde de la référence au message original
            view.message = await ctx.interaction.original_response()
        else:
            msg = await ctx.send(embed=embed, view=view, reference=ctx.message)
            # Sauvegarde de la référence au message original
            view.message = msg

    @massbuilder.error
    async def massbuilder_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            error_msg = "❌ Vous devez être Administrateur pour utiliser cette commande."
            if ctx.interaction:
                await ctx.interaction.response.send_message(error_msg, ephemeral=True)
            else:
                await ctx.send(error_msg, delete_after=5)

async def setup(bot: commands.Bot):
    await bot.add_cog(MassBuilderCog(bot))