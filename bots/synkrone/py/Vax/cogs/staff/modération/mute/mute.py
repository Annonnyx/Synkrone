import discord, json
from discord.ext import commands
from discord import app_commands
from pathlib import Path

# --- SYSTÈME D'IMPORT CONFIG_MANAGER ---
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

class Mute(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mute_role_cache = {} # Cache mémoire pour éviter les requêtes API inutiles

    def create_embed(self, ctx, title, description, color=discord.Color.red()):
        if config_manager:
            return config_manager.get_formatted_embed(guild=ctx.guild, user=ctx.author, bot=self.bot, title=title, description=description)
        return discord.Embed(title=title, description=description, color=color)

    async def get_mute_role(self, guild):
        # Vérification du cache mémoire
        role = self.mute_role_cache.get(guild.id)
        if role and discord.utils.get(guild.roles, id=role.id):
            return role

        # Recherche ou création du rôle
        role = discord.utils.get(guild.roles, name="🤫│𝑴𝒖𝒆𝒕")
        if not role:
            role = await guild.create_role(name="🤫│𝑴𝒖𝒆𝒕", reason="Système de Mute Global")
            for channel in guild.channels:
                try:
                    await channel.set_permissions(role, send_messages=False, speak=False, add_reactions=False)
                except:
                    continue
        
        self.mute_role_cache[guild.id] = role
        return role

    def get_syntax_help(self):
        return (
            "### ❌ Erreur de Syntaxe : Mute\n"
            "Mute un membre de façon **permanente** sur tout le serveur.\n\n"
            "**Format :** `!mute <@membre/ID> <raison>`\n\n"
            "**Exemples :**\n"
            "• `!mute @Vexa Publicités` (ID accepté)\n"
            "• `!mute @Vexa @Test @User Raison` (Mute multiple)\n\n"
            "*Note : La raison est obligatoire si vous n'êtes pas Administrateur.*"
        )

    @commands.hybrid_command(name="mute", description="🔇 Mute global permanent (Tout le serveur).")
    @app_commands.describe(membre="Le membre à mute (Mention ou ID)", raison="Raison de la sanction")
    @commands.has_permissions(moderate_members=True)
    async def mute(self, ctx, membre: discord.Member, *, raison: str = None):
        await ctx.defer()

        # 1. Vérification Raison (Obligatoire pour non-admins)
        if not ctx.author.guild_permissions.administrator and not raison:
            return await ctx.send(embed=self.create_embed(ctx, "⚠️ Aide Mute", self.get_syntax_help(), discord.Color.orange()), ephemeral=True)

        if membre.top_role >= ctx.guild.me.top_role:
            return await ctx.send("❌ Hiérarchie : Ce membre est plus haut ou égal à moi.", ephemeral=True)

        # 2. Récupération du rôle et application
        role = await self.get_mute_role(ctx.guild)
        
        try:
            await membre.add_roles(role, reason=f"Mute Permanent par {ctx.author}: {raison}")
            
            # 3. Enregistrement dans le fichier GLOBAL
            folder = Path(__file__).parent / "data"
            folder.mkdir(parents=True, exist_ok=True)
            file_path = folder / f"{ctx.guild.id}_global.json"
            data = json.loads(file_path.read_text(encoding="utf-8")) if file_path.exists() else {}
            
            # On utilise l'ID seul comme clé pour le global
            data[str(membre.id)] = {
                "user_id": membre.id,
                "reason": raison or "Admin",
                "expires_at": 9999999999 # Marqueur de permanence
            }
            file_path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
            
            # 4. Confirmation salon et MP
            title = "🔇 Mute Global Définitif"
            desc = f"{membre.mention} a été mute **définitivement** sur tout le serveur.\n**Raison :** {raison or 'Administrateur'}"
            await ctx.send(embed=self.create_embed(ctx, title, desc))

            try:
                mp_emb = discord.Embed(title="🤐 Sanction Permanente", color=discord.Color.dark_red())
                mp_emb.description = f"Vous avez été mute de façon **définitive** sur **{ctx.guild.name}**."
                mp_emb.add_field(name="📝 Raison", value=raison or "Non spécifiée")
                await membre.send(embed=mp_emb)
            except:
                pass

        except Exception as e:
            await ctx.send(f"❌ Erreur lors de l'application du mute : {e}", ephemeral=True)

    @mute.error
    async def mute_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Vous n'avez pas la permission `Modérer les membres`.", ephemeral=True)
        else:
            await ctx.send(embed=self.create_embed(ctx, "⚠️ Erreur de Syntaxe", self.get_syntax_help(), discord.Color.orange()), ephemeral=True)

async def setup(bot):
    await bot.add_cog(Mute(bot))