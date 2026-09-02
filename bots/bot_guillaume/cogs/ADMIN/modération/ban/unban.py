import discord
from discord.ext import commands
import os
import json

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

class Unban(commands.Cog):
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

    def _save_bans(self, guild_id, data):
        file_path = self._get_server_file(guild_id)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def get_formatted_embed(self, guild, user, title, description, color_type="default"):
        """Génère un embed via config_manager ou fallback."""
        if config_manager:
            return config_manager.get_formatted_embed(guild, user, self.bot, title, description, guild.id)
        else:
            color = discord.Color.red() if color_type == "error" else discord.Color.green()
            embed = discord.Embed(title=title, description=description, color=color)
            embed.set_footer(text=f"VAX System • {user.display_name}")
            return embed

    @commands.hybrid_command(name="unban", description="♻️ Débannir un utilisateur")
    @discord.app_commands.default_permissions(ban_members=True)
    @commands.has_permissions(ban_members=True)
    @discord.app_commands.describe(user_id="L'ID de l'utilisateur à débannir")
    async def unban(self, ctx: commands.Context, user_id: str):
        bans = self._load_bans(ctx.guild.id)

        if user_id not in bans:
            return await ctx.send("❌ Cet utilisateur n'est pas dans la banlist locale.", ephemeral=True)

        try:
            # On essaye de récupérer l'utilisateur via ID
            user = await self.bot.fetch_user(int(user_id))
            await ctx.guild.unban(user)
            
            del bans[user_id]
            self._save_bans(ctx.guild.id, bans)
            
            embed = self.get_formatted_embed(ctx.guild, ctx.author, "♻️ Débannissement", f"{user.mention} a été débanni avec succès.")
            await ctx.send(embed=embed)
            
        except discord.NotFound:
            await ctx.send("❌ Utilisateur introuvable ou déjà débanni.", ephemeral=True)
        except discord.Forbidden:
            await ctx.send("❌ Je n'ai pas la permission de débannir cet utilisateur.", ephemeral=True)
        except Exception as e:
            await ctx.send(f"❌ Une erreur est survenue : {e}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Unban(bot))
