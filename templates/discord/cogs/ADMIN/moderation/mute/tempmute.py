import discord, re, json, asyncio
from discord.ext import commands
from discord import app_commands
from pathlib import Path

# --- SYSTÈME D'IMPORT CONFIG_MANAGER ---
try:
    from cogs.config_manager.utils import config_manager
except ImportError:
    config_manager = None

class TempMute(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.mute_role_cache = {} # Cache mémoire du rôle par serveur

    def create_embed(self, ctx, title, description, color=discord.Color.orange()):
        if config_manager:
            return config_manager.get_formatted_embed(guild=ctx.guild, user=ctx.author, bot=self.bot, title=title, description=description)
        return discord.Embed(title=title, description=description, color=color)

    def get_data_file(self, guild_id):
        folder = Path(__file__).parent / "data"
        folder.mkdir(parents=True, exist_ok=True)
        file_path = folder / f"{guild_id}_global.json" # Fichier séparé pour le global mute
        if not file_path.exists(): file_path.write_text("{}", encoding="utf-8")
        return file_path

    async def get_mute_role(self, guild):
        # Vérification cache mémoire
        role = self.mute_role_cache.get(guild.id)
        if role and discord.utils.get(guild.roles, id=role.id):
            return role

        # Recherche ou création
        role = discord.utils.get(guild.roles, name="🤫│𝑴𝒖𝒆𝒕")
        if not role:
            role = await guild.create_role(name="🤫│𝑴𝒖𝒆𝒕", reason="Système de Mute Global")
            # Configuration automatique des salons pour ce rôle
            for channel in guild.channels:
                try: await channel.set_permissions(role, send_messages=False, speak=False, add_reactions=False)
                except: continue
        
        self.mute_role_cache[guild.id] = role
        return role

    def get_syntax_help(self):
        return (
            "### ❌ Erreur de Syntaxe : TempMute\n"
            "Mute un membre sur **l'ensemble du serveur**.\n\n"
            "**Format :** `!tempmute <@membre/ID> <durée> <raison>`\n\n"
            "**Exemples :**\n"
            "• `!tempmute @Vexa 2h Spam` (ID accepté)\n"
            "• `!tempmute @Vexa @Test 30m Raison` (Répétez la commande)\n\n"
            "**Unités :** `s`, `m`, `h`, `d`."
        )

    @commands.hybrid_command(name="tempmute", description="🔇 Mute global temporaire du serveur")
    @discord.app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(membre="Le membre à mute", durée="Ex: 10m, 2h", raison="Raison du mute")
    @commands.has_permissions(moderate_members=True)
    async def tempmute(self, ctx, membre: discord.Member, durée: str, *, raison: str = None):
        await ctx.defer()

        # 1. Parsing du temps
        units = {'d': 86400, 'h': 3600, 'm': 60, 's': 1}
        seconds = 0
        matches = re.findall(r"(\d+)([dhms])", durée.lower())
        for val, unit in matches:
            seconds += int(val) * units[unit]

        # 2. Vérification syntaxe/permissions
        if seconds <= 0 or (not ctx.author.guild_permissions.administrator and not raison):
            return await ctx.send(embed=self.create_embed(ctx, "⚠️ Aide TempMute", self.get_syntax_help()), ephemeral=True)

        if membre.top_role >= ctx.guild.me.top_role:
            return await ctx.send("❌ Je ne peux pas sanctionner ce membre (Hiérarchie).", ephemeral=True)

        # 3. Application du rôle
        role = await self.get_mute_role(ctx.guild)
        
        try:
            await membre.add_roles(role, reason=f"TempMute par {ctx.author}: {raison}")
            
            # 4. Enregistrement des données
            file_path = self.get_data_file(ctx.guild.id)
            data = json.loads(file_path.read_text(encoding="utf-8"))
            
            # Utilisation d'une clé simple car c'est global (pas lié à un salon)
            data[str(membre.id)] = {
                "user_id": membre.id,
                "reason": raison or "Admin",
                "expires_at": discord.utils.utcnow().timestamp() + seconds,
                "type": "global"
            }
            file_path.write_text(json.dumps(data, indent=4), encoding="utf-8")

            # 5. Confirmation et MP
            title = "🔇 Sanction Globale Appliquée"
            desc = f"{membre.mention} est désormais muet sur **tout le serveur**.\n**Durée :** {durée}\n**Raison :** {raison or 'Administrateur'}"
            await ctx.send(embed=self.create_embed(ctx, title, desc, discord.Color.red()))

            try:
                await membre.send(f"🤐 Vous avez été mute globalement sur **{ctx.guild.name}** pour **{durée}**.\n**Raison :** {raison or 'Admin'}")
            except: pass

        except Exception as e:
            await ctx.send(f"❌ Erreur lors de l'ajout du rôle : {e}", ephemeral=True)

    @tempmute.error
    async def tempmute_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Permission `Modérer les membres` requise.", ephemeral=True)
        else:
            await ctx.send(embed=self.create_embed(ctx, "⚠️ Erreur Syntaxe", self.get_syntax_help()), ephemeral=True)

async def setup(bot): await bot.add_cog(TempMute(bot))