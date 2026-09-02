import discord
from discord.ext import commands
from discord import app_commands
import json, os, asyncio
from datetime import datetime

# Gestion des imports pour le Config Manager
try:
    from ..utils import config_manager
    HAS_CUSTOM_EMBED = True
except ImportError:
    try:
        from cogs.addons.embed_type.utils import config_manager
        HAS_CUSTOM_EMBED = True
    except ImportError:
        config_manager = None
        HAS_CUSTOM_EMBED = False

class Ban(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = os.path.join(self.base_dir, "banlist_serveur")
        self.tintin_path = os.path.join(self.base_dir, "tintin.png")
        
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

    def _get_server_file(self, guild_id):
         return os.path.join(self.data_dir, f"{guild_id}.json")

    def _load_bans(self, guild_id):
        file_path = self._get_server_file(guild_id)
        if not os.path.exists(file_path): return {}
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except: return {}

    def _save_bans(self, guild_id, data):
        file_path = self._get_server_file(guild_id)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def get_formatted_embed(self, guild, user, title, description, color_type="default"):
        """Génère un embed via config_manager ou fallback."""
        if config_manager:
            return config_manager.get_formatted_embed(guild, user, self.bot, title, description, guild.id)
        else:
            color = discord.Color.red() if color_type == "error" else discord.Color.blue()
            embed = discord.Embed(title=title, description=description, color=color)
            embed.set_footer(text=f"VAX System • {user.display_name}")
            return embed

    @commands.hybrid_command(name="ban", description="🚫 Bannir un membre avec animation Tintin.")
    @commands.has_permissions(ban_members=True)
    @app_commands.describe(member="Le membre à bannir", reason="Raison du bannissement")
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Aucune raison fournie"):
        
        # 1. Vérification si l'utilisateur est déjà banni du serveur
        try:
            ban_entry = await ctx.guild.fetch_ban(member)
            if ban_entry:
                embed = self.get_formatted_embed(ctx.guild, ctx.author, "Action Impossible", f"❌ {member.mention} est **déjà banni** de ce serveur.", "error")
                return await ctx.send(embed=embed, ephemeral=True)
        except discord.NotFound:
            pass # L'utilisateur n'est pas banni, on continue

        # 2. Vérification Hiérarchie : Modérateur vs Cible
        if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            embed = self.get_formatted_embed(ctx.guild, ctx.author, "Erreur de Hiérarchie", "❌ Vous ne pouvez pas bannir ce membre car il possède un rôle **égal ou supérieur** au vôtre.", "error")
            return await ctx.send(embed=embed, ephemeral=True)

        # 3. Vérification Hiérarchie : Bot vs Cible
        if member.top_role >= ctx.guild.me.top_role:
            embed = self.get_formatted_embed(ctx.guild, ctx.author, "Erreur de Permissions", "❌ Je ne peux pas bannir ce membre car son rôle est **égal ou supérieur au mien**.", "error")
            return await ctx.send(embed=embed, ephemeral=True)

        # 4. Vérification Permissions Bot
        if not ctx.guild.me.guild_permissions.ban_members:
            embed = self.get_formatted_embed(ctx.guild, ctx.author, "Erreur Critique", "❌ Je n'ai pas la permission système `Bannir des membres`.", "error")
            return await ctx.send(embed=embed, ephemeral=True)

        # Si tout est OK, on lance la procédure
        bans = self._load_bans(ctx.guild.id)
        
        # --- Étape 1 : Décompte ---
        embed = self.get_formatted_embed(ctx.guild, ctx.author, "⚡ Séquence de bannissement", f"⚠️ {member.mention} va être banni dans **5** secondes.")
        
        file = None
        if os.path.exists(self.tintin_path):
            file = discord.File(self.tintin_path, filename="tintin.png")
            embed.set_image(url="attachment://tintin.png")

        msg = await ctx.send(embed=embed, file=file)

        for i in range(4, 0, -1):
            await asyncio.sleep(1)
            embed.description = f"⚠️ {member.mention} va être banni dans **{i}** secondes."
            await msg.edit(embed=embed)

        await asyncio.sleep(1)

        # --- Étape 2 : Exécution ---
        try:
            # MP avant le ban
            try:
                dm_embed = discord.Embed(title="🚫 Bannissement", description=f"Vous avez été banni de **{ctx.guild.name}**\n**Raison :** {reason}", color=discord.Color.red())
                if os.path.exists(self.tintin_path):
                    dm_embed.set_image(url="attachment://tintin.png")
                    await member.send(embed=dm_embed, file=discord.File(self.tintin_path, filename="tintin.png"))
                else:
                    await member.send(embed=dm_embed)
            except: 
                pass # MP Fermés

            await ctx.guild.ban(member, reason=f"Par {ctx.author}: {reason}", delete_message_seconds=604800)
            
            # Sauvegarde JSON locale
            now = datetime.now()
            bans[str(member.id)] = {
                "Nom complet": str(member),
                "Raison": reason,
                "Date": now.strftime("%d/%m/%Y"),
                "Heure": now.strftime("%H:%M"),
                "Modérateur": str(ctx.author)
            }
            self._save_bans(ctx.guild.id, bans)

            # --- Étape 3 : Embed Final ---
            final_desc = f"🗑️ {member.mention} a été banni avec succès.\n**Raison :** {reason}\n*Tous ses messages des 7 derniers jours ont été supprimés.*"
            final_embed = self.get_formatted_embed(ctx.guild, ctx.author, "✅ Bannissement effectué", final_desc)
            if os.path.exists(self.tintin_path):
                final_embed.set_image(url="attachment://tintin.png")

            await msg.edit(embed=final_embed)

        except Exception as e:
            error_embed = self.get_formatted_embed(ctx.guild, ctx.author, "Erreur d'exécution", f"❌ Impossible de bannir le membre : {e}", "error")
            await ctx.send(embed=error_embed, ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Ban(bot))