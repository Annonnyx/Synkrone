import discord
from discord.ext import commands
import traceback

# ==============================================================================
# --------------------------- IMPORTATION UTILS --------------------------------
# ==============================================================================
try:
    from cogs.developpeur.commands.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# ==============================================================================
# ----------------------------- COG STAGE ------------------------------------
# ==============================================================================

class Stage(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(
        name="stage", 
        description="Affiche les informations de progression."
    )
    async def stage(self, ctx: commands.Context):
        
        try:
            # 1. ACCUSÉ DE RÉCEPTION (Utile pour les Slash Commands)
            await ctx.defer(ephemeral=False)

            # 2. CONSTRUCTION DE L'EMBED AVEC LES INFOS DE STAGE
            if config_manager:
                embed = config_manager.get_formatted_embed(
                    guild=ctx.guild,
                    user=ctx.author,
                    bot=self.bot,
                    title=" Centre de Stage",
                    description="Bienvenue dans votre centre de progression !",
                    target_id=ctx.guild.id if ctx.guild else None
                )
            else:
                embed = discord.Embed(
                    title=" Centre de Stage",
                    description="Bienvenue dans votre centre de progression !",
                    color=0x2b2d31
                )

            # 3. CONTENU DE L'EMBED
            embed.add_field(
                name=" **Progression**",
                value="• Suivez votre évolution dans le jeu\n• Consultez vos accomplissements\n• Accédez aux récompenses",
                inline=False
            )
            
            embed.add_field(
                name=" **Objectifs**",
                value="• Atteignez de nouveaux paliers\n• Débloquez des fonctionnalités\n• Améliorez votre personnage",
                inline=False
            )

            embed.set_footer(text="Utilisez les autres commandes pour progresser !")

            # 4. ENVOI DE L'EMBED
            if ctx.interaction:
                # Pour Slash, on utilise followup puisqu'on a fait un defer()
                await ctx.send(embed=embed)
            else:
                # Pour Prefix, on utilise l'argument reference pour "Répondre" au message
                await ctx.send(embed=embed, reference=ctx.message, mention_author=True)

        except Exception as e:
            print(f"\033[91m[ERROR - Stage] Une erreur est survenue :\033[0m")
            traceback.print_exc()
            
            error_msg = " Une erreur est survenue lors de l'exécution de la commande."
            if ctx.interaction:
                await ctx.interaction.followup.send(error_msg, ephemeral=True)
            else:
                await ctx.send(error_msg, reference=ctx.message)

async def setup(bot: commands.Bot):
    if bot.get_command("ping"):
        bot.remove_command("ping")
    await bot.add_cog(Stage(bot))