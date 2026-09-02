import discord, json
from discord.ext import commands
from discord import app_commands
from pathlib import Path

try:
    from cogs.config_manager.utils import config_manager
except ImportError:
    config_manager = None

class RMute(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mute_role_cache = {} # Stockage : {guild_id: role_object}

    def create_embed(self, ctx, title, description, color=discord.Color.red()):
        if config_manager:
            return config_manager.get_formatted_embed(guild=ctx.guild, user=ctx.author, bot=self.bot, title=title, description=description)
        return discord.Embed(title=title, description=description, color=color)

    async def get_mute_role(self, guild):
        # Vérifie si le rôle est déjà en mémoire vive
        role = self.mute_role_cache.get(guild.id)
        if role and discord.utils.get(guild.roles, id=role.id):
            return role

        # Sinon, cherche ou crée
        role = discord.utils.get(guild.roles, name="🤫│𝑴𝒖𝒆𝒕")
        if not role:
            role = await guild.create_role(name="🤫│𝑴𝒖𝒆𝒕", reason="Système de Mute Local")
            for channel in guild.channels:
                try: await channel.set_permissions(role, send_messages=False, speak=False)
                except: continue
        
        self.mute_role_cache[guild.id] = role # Mise en mémoire
        return role

    def get_syntax_help(self):
        return (
            "### ❌ Erreur de Syntaxe\n"
            "**Format :** `!rmute <@membre/ID> <raison>`\n\n"
            "**Exemples :**\n"
            "• `!rmute @Vexa Spam` (Fonctionne avec l'ID)\n"
            "• `!rmute @Vexa @Test @User Raison` (Mute multiple)\n\n"
            "*Note : La raison est obligatoire pour les non-admins.*"
        )

    @commands.hybrid_command(name="rmute", description="🔇 Mute local permanent.")
    @discord.app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(membre="Le membre à mute (Mention ou ID)", raison="Raison de la sanction")
    @commands.has_permissions(moderate_members=True)
    async def rmute(self, ctx, membre: discord.Member, *, raison: str = None):
        await ctx.defer()

        if not ctx.author.guild_permissions.administrator and not raison:
            return await ctx.send(embed=self.create_embed(ctx, "⚠️ Aide RMute", self.get_syntax_help(), discord.Color.orange()), ephemeral=True)

        folder = Path(__file__).parent / "data"
        folder.mkdir(parents=True, exist_ok=True)
        file_path = folder / f"{ctx.guild.id}.json"
        data = json.loads(file_path.read_text(encoding="utf-8")) if file_path.exists() else {}
        
        key = f"{membre.id}_{ctx.channel.id}"
        if key in data:
            return await ctx.send(f"❌ {membre.mention} est déjà restreint ici.", ephemeral=True)

        await self.get_mute_role(ctx.guild)
        
        try:
            await ctx.channel.set_permissions(membre, send_messages=False, reason=f"RMute: {raison}")
            data[key] = {
                "user_id": membre.id, "channel_id": ctx.channel.id,
                "reason": raison or "Admin", "expires_at": 9999999999 # Marqueur Permanent
            }
            file_path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
            
            await ctx.send(embed=self.create_embed(ctx, "🔇 Mute Permanent", f"{membre.mention} est mute définitivement ici.\n**Raison :** {raison or 'Administrateur'}"))

            try:
                await membre.send(f"🤐 Vous avez été mute de façon **permanente** sur **{ctx.guild.name}** (Salon: #{ctx.channel.name}).")
            except: pass
        except Exception as e:
            await ctx.send(f"❌ Erreur : {e}", ephemeral=True)

    @rmute.error
    async def rmute_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Vous n'avez pas la permission `Modérer les membres`.", ephemeral=True)
        else:
            await ctx.send(embed=self.create_embed(ctx, "⚠️ Aide", self.get_syntax_help(), discord.Color.orange()), ephemeral=True)

async def setup(bot): await bot.add_cog(RMute(bot))