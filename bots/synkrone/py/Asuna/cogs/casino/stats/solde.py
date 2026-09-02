
import discord
from discord.ext import commands
import os
import json
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# --- GESTION DES DONNÉES UTILISATEUR ---
def get_user_file_path(guild_id: int, user_id: int):
    base_dir = os.path.join('cogs', 'casino', 'data', str(guild_id))
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)
    return os.path.join(base_dir, f"{user_id}.json")

def load_user_data(guild_id: int, user_id: int):
    path = get_user_file_path(guild_id, user_id)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"Cols": 1000} # Solde de départ si le fichier n'existe pas

def save_user_data(guild_id: int, user_id: int, data: dict):
    path = get_user_file_path(guild_id, user_id)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

def format_Cols(value: int) -> str:
    return f"{value:,}".replace(',', ' ')

class Solde(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="solde", description="Affiche votre solde.")
    async def solde(self, ctx: commands.Context, utilisateur: discord.User = None):
        """
        /solde - Affiche l’argent possédé.
        /solde IG/@TAG - Affiche l'argent d'un utilisateur
        """
        user = utilisateur or ctx.author
        user_data = load_user_data(ctx.guild.id, user.id)
        argent = user_data.get("Cols", 0)
        if config_manager:
            embed = config_manager.get_formatted_embed(
                guild=ctx.guild,
                user=user,
                bot=self.bot,
                title="💰 Solde",
                description=f"{user.mention} possède **{format_Cols(argent)} Cols**.",
                target_id=ctx.guild.id if ctx.guild else None
            )
        else:
            embed = discord.Embed(title="💰 Solde", description=f"{user.mention} possède **{format_Cols(argent)} Cols**.")
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="balance", description="Affiche votre solde.")
    async def balance(self, ctx: commands.Context):
        await self.solde(ctx)


async def setup(bot):
    await bot.add_cog(Solde(bot))
