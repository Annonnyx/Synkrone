import discord
from discord.ext import commands
from discord import ui
import os
import json
import math

# Gestion des imports pour le Config Manager
try:
    from ..utils import config_manager
    HAS_CUSTOM_EMBED = True
except ImportError:
    try:
        from cogs.config_manager.utils import config_manager
        HAS_CUSTOM_EMBED = True
    except ImportError:
        config_manager = None
        HAS_CUSTOM_EMBED = False

class BanPagination(ui.View):
    """Système de boutons pour naviguer dans la banlist."""
    def __init__(self, embeds, user_id):
        super().__init__(timeout=60)
        self.embeds = embeds
        self.user_id = user_id
        self.current_page = 0

    @ui.button(label="◀️", style=discord.ButtonStyle.grey)
    async def previous(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Ce n'est pas votre menu.", ephemeral=True)
        if self.current_page > 0:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.embeds[self.current_page])

    @ui.button(label="▶️", style=discord.ButtonStyle.grey)
    async def next(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("❌ Ce n'est pas votre menu.", ephemeral=True)
        if self.current_page < len(self.embeds) - 1:
            self.current_page += 1
            await interaction.response.edit_message(embed=self.embeds[self.current_page])

class Banlist(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = os.path.join(self.base_dir, "banlist_serveur")
        
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

    def _get_server_file(self, guild_id):
        return os.path.join(self.data_dir, f"{guild_id}.json")

    def _load_bans(self, guild_id):
        file_path = self._get_server_file(guild_id)
        if not os.path.exists(file_path): 
            return {}
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except: 
            return {}

    def get_formatted_embed(self, guild, user, title, description, color_type="default"):
        """Génère un embed via config_manager ou fallback."""
        if config_manager:
            return config_manager.get_formatted_embed(guild, user, self.bot, title, description, guild.id)
        else:
            color = discord.Color.red() if color_type == "error" else discord.Color.blue()
            embed = discord.Embed(title=title, description=description, color=color)
            embed.set_footer(text=f"VAX System • {user.display_name}")
            return embed

    @commands.hybrid_command(name="banlist", description="📋 Affiche la liste des bannis du serveur.")
    @discord.app_commands.default_permissions(ban_members=True)
    @commands.has_permissions(ban_members=True)
    async def banlist(self, ctx: commands.Context):
        bans = self._load_bans(ctx.guild.id)

        if not bans:
            return await ctx.send("✅ Aucun banni enregistré.", ephemeral=True)

        entries = list(bans.items())
        pages = math.ceil(len(entries)/10)
        embeds = []

        for i in range(pages):
            description = ""
            for j in range(i*10, min((i+1)*10, len(entries))):
                uid, data = entries[j]
                description += f"**{data['Nom complet']}** (`{uid}`)\n└ 📅 {data['Date']} | 👮 {data['Modérateur']}\n"
            
            embed = self.get_formatted_embed(ctx.guild, ctx.author, f"🚫 Banlist - Page {i+1}/{pages}", description)
            embeds.append(embed)

        view = BanPagination(embeds, ctx.author.id)
        await ctx.send(embed=embeds[0], view=view, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Banlist(bot))
