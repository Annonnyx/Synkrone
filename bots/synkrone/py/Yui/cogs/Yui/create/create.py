import discord

from discord.ext import commands

import discord.ui as ui

try:
    from cogs.developpeur.commands.embed_type.utils import config_manager
except ImportError:
    config_manager = None



# ==============================================================================

# --------------------------- VUES INTERACTIVES --------------------------------

# ==============================================================================



class CreateChoiceView(ui.View):

    """Vue interactive pour le menu de création"""

    def __init__(self, cog, ctx, name: str):

        super().__init__(timeout=120)

        self.cog = cog

        self.ctx = ctx

        self.author_id = ctx.author.id

        self.name = name

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Seul l'auteur de la commande peut utiliser ce menu.", ephemeral=True)
            return False
        return True

   

    async def _handle_call(self, interaction: discord.Interaction, func):

        """Centralise le defer et l'appel pour éviter les erreurs d'interaction"""

        await interaction.response.defer()

        await func(interaction, self.ctx, self.name)



    @ui.button(label="Vocal", emoji="🎤", style=discord.ButtonStyle.primary)

    async def voice(self, inter, btn): await self._handle_call(inter, self.cog.create_voice_channel)

   

    @ui.button(label="Texte", emoji="💬", style=discord.ButtonStyle.primary)

    async def text(self, inter, btn): await self._handle_call(inter, self.cog.create_text_channel)

   

    @ui.button(label="Forum", emoji="📋", style=discord.ButtonStyle.primary)

    async def forum(self, inter, btn): await self._handle_call(inter, self.cog.create_forum_channel)

   

    @ui.button(label="Catégorie", emoji="📁", style=discord.ButtonStyle.primary)

    async def cat(self, inter, btn): await self._handle_call(inter, self.cog.create_category)

   

    @ui.button(label="Rôle", emoji="🎭", style=discord.ButtonStyle.secondary)

    async def role(self, inter, btn): await self._handle_call(inter, self.cog.create_role)



# ==============================================================================

# --------------------------- COG PRINCIPAL ------------------------------------

# ==============================================================================



class Create(commands.Cog):

    def __init__(self, bot):

        self.bot = bot



    def create_embed(self, ctx, title: str, description: str):

        """Génère un embed propre et uniforme"""
        if config_manager:
            embed = config_manager.get_formatted_embed(
                guild=ctx.guild,
                user=ctx.author,
                bot=self.bot,
                title=title,
                description=description,
                target_id=ctx.guild.id if ctx.guild else None,
            )
            embed.remove_author()
            return embed

        embed = discord.Embed(title=title, description=description, color=0x2b2d31)
        user = ctx.author
        embed.set_footer(text=f"Exécuté par {user.display_name}", icon_url=user.display_avatar.url)
        return embed



    # --- MÉTHODES DE CRÉATION ---



    async def create_voice_channel(self, interaction, ctx, name):

        channel = await ctx.guild.create_voice_channel(name=name, reason=f"Action par {ctx.author}")
        print(f"✅ Salon vocal '{name}' créé par {ctx.author} dans le serveur {ctx.guild.name}")
        await interaction.followup.send(embed=self.create_embed(ctx, "✅ Salon Vocal", f"Le salon {channel.mention} a été créé."))



    async def create_text_channel(self, interaction, ctx, name):

        channel = await ctx.guild.create_text_channel(name=name, reason=f"Action par {ctx.author}")
        print(f"✅ Salon textuel '{name}' créé par {ctx.author} dans le serveur {ctx.guild.name}")
        await interaction.followup.send(embed=self.create_embed(ctx, "✅ Salon Textuel", f"Le salon {channel.mention} a été créé."))



    async def create_forum_channel(self, interaction, ctx, name):

        """Création de forum sécurisée"""

        try:

            # La méthode correcte est create_forum (discord.py 2.7.1)

            channel = await ctx.guild.create_forum(name=name, reason=f"Action par {ctx.author}")
            print(f"✅ Salon forum '{name}' créé par {ctx.author} dans le serveur {ctx.guild.name}")
            await interaction.followup.send(embed=self.create_embed(ctx, "✅ Salon Forum", f"Le forum {channel.mention} a été créé."))

        except AttributeError:

            await interaction.followup.send("❌ Erreur technique : Votre version de discord.py ne supporte pas les Forums.")

        except Exception as e:

            await interaction.followup.send(f"❌ Impossible de créer le forum : {e}")



    async def create_category(self, interaction, ctx, name):

        cat = await ctx.guild.create_category(name=name, reason=f"Action par {ctx.author}")
        print(f"✅ Catégorie '{name}' créée par {ctx.author} dans le serveur {ctx.guild.name}")
        await interaction.followup.send(embed=self.create_embed(ctx, "✅ Catégorie", f"La catégorie **{cat.name}** a été créée."))



    async def create_role(self, interaction, ctx, name):

        """Création d'un rôle simple"""

        try:

            # Vérification de permission basique

            if not ctx.guild.me.guild_permissions.manage_roles:

                print(f"❌ Impossible de créer le rôle '{name}' : Le bot n'a pas la permission 'Gérer les rôles' dans le serveur {ctx.guild.name}")

                return await interaction.followup.send("❌ Erreur : Je n'ai pas la permission 'Gérer les rôles'.")

            

            # Création du rôle simple

            role = await ctx.guild.create_role(

                name=name,

                reason=f"Créé par {ctx.author}",

                colour=discord.Colour.blue(),

                mentionable=True

            )

            

            print(f"✅ Rôle '{name}' créé par {ctx.author} dans le serveur {ctx.guild.name}")

            await interaction.followup.send(embed=self.create_embed(ctx, "✅ Rôle Créé", f"Le rôle {role.mention} a été créé avec succès."))



        except discord.Forbidden as e:

            print(f"❌ Impossible de créer le rôle '{name}' : Permission refusée dans le serveur {ctx.guild.name} (Erreur: {e})")

            await interaction.followup.send("❌ Erreur : Je n'ai pas les permissions nécessaires pour créer un rôle.")

        except Exception as e:

            print(f"❌ Impossible de créer le rôle '{name}' dans le serveur {ctx.guild.name} : {type(e).__name__} - {e}")

            await interaction.followup.send(f"❌ Une erreur est survenue : {e}")



    # --- COMMANDE PRINCIPALE ---



    @commands.hybrid_command(name="create", description="Ouvre le menu de creation guidee (salon/role/categorie/forum).")

    @commands.has_permissions(manage_channels=True, manage_roles=True)

    async def create_cmd(self, ctx, *, name: str):

        """Lance le menu de création d'élément"""

        # Nettoyage rapide du nom (Discord n'aime pas les noms vides)

        name = name.strip()

        if not name:

            return await ctx.send("❌ Veuillez fournir un nom valide.")



        embed = self.create_embed(

            ctx,

            "🛠️ Assistant de Création",

            f"Que souhaitez-vous créer avec le nom : **{name}** ?"

        )

       

        view = CreateChoiceView(self, ctx, name)

        await ctx.send(embed=embed, view=view)

async def setup(bot):

    await bot.add_cog(Create(bot))