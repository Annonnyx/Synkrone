import discord
from discord.ext import commands
import os
import json

# ===================== CONFIG MANAGER ========================
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# --- GESTION DES DONNÉES ---
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
    return {"Cols": 1000}

def save_user_data(guild_id: int, user_id: int, data: dict):
    path = get_user_file_path(guild_id, user_id)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

def format_Cols(value: int) -> str:
    return f"{value:,}".replace(',', ' ')

# --- COG ---
class GiveSAO(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="give", description="💰 Transférer des Cols à un autre joueur du casino")
    @commands.guild_only()
    async def give(self, ctx: commands.Context, membre: discord.Member, montant: int):
        """Donner de l'argent à un autre joueur (max 20% de votre fortune)"""
        
        # Vérifications de base
        if membre == ctx.author:
            return await ctx.send("❌ Vous ne pouvez pas vous donner d'argent à vous-même !")
        
        if montant <= 0:
            return await ctx.send("❌ Le montant doit être positif !")
        
        # Charger les données des deux utilisateurs
        donneur_data = load_user_data(ctx.guild.id, ctx.author.id)
        receveur_data = load_user_data(ctx.guild.id, membre.id)
        
        # Calculer le maximum autorisé (20% de la fortune du donneur)
        max_autorise = int(donneur_data["Cols"] * 0.20)
        
        if montant > donneur_data["Cols"]:
            return await ctx.send(f"❌ Solde insuffisant ! Vous avez **{format_Cols(donneur_data['Cols'])} Cols**")
        
        if montant > max_autorise:
            return await ctx.send(f"❌ Vous ne pouvez donner que **20% maximum** de votre fortune !\n"
                                f"Maximum autorisé : **{format_Cols(max_autorise)} Cols**")
        
        # Effectuer le transfert
        donneur_data["Cols"] -= montant
        receveur_data["Cols"] += montant
        
        # Sauvegarder les données
        save_user_data(ctx.guild.id, ctx.author.id, donneur_data)
        save_user_data(ctx.guild.id, membre.id, receveur_data)
        
        # Embed de confirmation
        embed = self.bot.config.get_formatted_embed(
            title="💰 TRANSFERT VALIDÉ — CASINO D'AINCRAD",
            description=(
                f"**{ctx.author.display_name}** a transféré **{format_Cols(montant)} Cols** à **{membre.display_name}**\n"
                f"*La transaction a été enregistrée par le système du casino.*\n\n"
                f"💳 **Nouveau solde de {ctx.author.display_name}** : {format_Cols(donneur_data['Cols'])} Cols\n"
                f"💳 **Nouveau solde de {membre.display_name}** : {format_Cols(receveur_data['Cols'])} Cols"
            ),
            bot_user=self.bot.user,
            guild=ctx.guild,
            user=ctx.author,
            target_id=ctx.guild.id if ctx.guild else None
        )
        
        await ctx.send(embed=embed)
        
        # Notifier le receveur en MP
        try:
            embed_mp = self.bot.config.get_formatted_embed(
                title="💸 DON REÇU — CASINO D'AINCRAD !",
                description=(
                    f"**{ctx.author.display_name}** vous a transféré **{format_Cols(montant)} Cols** au casino !\n\n"
                    f"💳 Votre nouveau solde : **{format_Cols(receveur_data['Cols'])} Cols**"
                ),
                bot_user=self.bot.user,
                guild=ctx.guild,
                user=membre,
                target_id=ctx.guild.id if ctx.guild else None
            )
            await membre.send(embed=embed_mp)
        except discord.Forbidden:
            # Le receveur a désactivé les MPs
            pass

async def setup(bot):
    await bot.add_cog(GiveSAO(bot))
