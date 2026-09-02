import discord, re, json, asyncio
from discord.ext import commands
from discord import app_commands
from pathlib import Path
from typing import Optional

# --- SYSTÈME D'IMPORT CONFIG_MANAGER ---
try:
    from cogs.config_manager.utils import config_manager
except ImportError:
    config_manager = None

class TempRMute(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def create_embed(self, ctx, title, description, color=discord.Color.red()):
        if config_manager:
            return config_manager.get_formatted_embed(guild=ctx.guild, user=ctx.author, bot=self.bot, title=title, description=description)
        return discord.Embed(title=title, description=description, color=color)

    def get_data_file(self, guild_id):
        folder = Path(__file__).parent / "data"
        folder.mkdir(parents=True, exist_ok=True)
        file_path = folder / f"{guild_id}.json"
        if not file_path.exists(): file_path.write_text("{}", encoding="utf-8")
        return file_path

    def get_syntax_help(self):
        return (
            "### ❌ Erreur de Syntaxe / Argument Manquant\n"
            "La commande n'a pas pu être exécutée. Voici comment l'utiliser :\n\n"
            "**Format :** `!temprmute <@membre ou ID> <durée> <raison>`\n\n"
            "**Exemples :**\n"
            "• **Simple :** `!temprmute @Vexa 10m Spam` (Fonctionne aussi avec l'ID : `136678...`)\n"
            "• **Multiple :** `!temprmute @Vexa 1h @Test 1h Spam` (Répétez le motif)\n"
            "• **Slash :** `/temprmute membre:@Vexa durée:30m raison:Flood`\n\n"
            "**Unités de temps :** `s` (secondes), `m` (minutes), `h` (heures), `d` (jours).\n"
            "*Note : La raison est obligatoire si vous n'êtes pas Administrateur.*"
        )

    async def get_or_create_mute_role(self, guild):
        role = discord.utils.get(guild.roles, name="🤫│𝑴𝒖𝒆𝒕")
        if not role:
            role = await guild.create_role(name="🤫│𝑴𝒖𝒆𝒕", reason="Système de Mute")
            for channel in guild.channels:
                try: await channel.set_permissions(role, send_messages=False, speak=False)
                except: continue
        return role

    @commands.hybrid_command(name="temprmute", description="⏳ Mute local temporaire dans ce salon")
    @discord.app_commands.default_permissions(moderate_members=True)
    @app_commands.describe(membre="Le membre à mute (Mention ou ID)", durée="Ex: 10m, 2h", raison="Raison de la sanction")
    @commands.has_permissions(moderate_members=True)
    async def temprmute(self, ctx, membre: discord.Member, durée: str, *, raison: str = None):
        await ctx.defer()

        # 1. Parsing du temps
        units = {'d': 86400, 'h': 3600, 'm': 60, 's': 1}
        seconds = 0
        for val, unit in re.findall(r"(\d+)([dhms])", durée.lower()):
            seconds += int(val) * units[unit]

        # 2. Vérification Manuelle (Syntaxe/Raison)
        if seconds <= 0 or (not ctx.author.guild_permissions.administrator and not raison):
            return await ctx.send(embed=self.create_embed(ctx, "⚠️ Aide TempRMute", self.get_syntax_help(), discord.Color.orange()), ephemeral=True)

        # 3. Traitement
        file_path = self.get_data_file(ctx.guild.id)
        data = json.loads(file_path.read_text(encoding="utf-8"))
        key = f"{membre.id}_{ctx.channel.id}"

        if key in data:
            return await ctx.send(f"❌ {membre.mention} est déjà restreint dans ce salon.", ephemeral=True)
        if membre.top_role >= ctx.guild.me.top_role:
            return await ctx.send("❌ Hiérarchie : Je ne peux pas sanctionner ce membre.", ephemeral=True)

        await self.get_or_create_mute_role(ctx.guild)
        
        try:
            await ctx.channel.set_permissions(membre, send_messages=False, reason=f"Mute: {raison}")
            
            data[key] = {
                "user_id": membre.id, "channel_id": ctx.channel.id,
                "reason": raison or "Admin", "expires_at": discord.utils.utcnow().timestamp() + seconds
            }
            file_path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
            
            await ctx.send(embed=self.create_embed(ctx, "🔇 Mute Salon Appliqué", f"Le membre {membre.mention} a été réduit au silence pour **{durée}**.\n**Raison :** {raison or 'Administrateur'}"))

            # Envoi MP
            try:
                mp_emb = discord.Embed(title="🤐 Sanction Locale", color=discord.Color.red())
                mp_emb.description = f"Bonjour, vous avez été mute sur le serveur **{ctx.guild.name}**."
                mp_emb.add_field(name="📍 Salon", value=ctx.channel.name)
                mp_emb.add_field(name="⏳ Durée", value=durée)
                mp_emb.add_field(name="📝 Raison", value=raison or "Non spécifiée (Admin)")
                mp_emb.set_footer(text="Ceci est un mute local automatique.")
                await membre.send(embed=mp_emb)
            except: pass

        except Exception as e:
            await ctx.send(f"❌ Erreur lors de la modification des permissions : {e}", ephemeral=True)

    @temprmute.error
    async def temprmute_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ **Accès Refusé** : Vous n'avez pas la permission `Modérer les membres`.", ephemeral=True)
        elif isinstance(error, (commands.MemberNotFound, commands.BadArgument, commands.MissingRequiredArgument)):
            # Ici on renvoie l'aide détaillée si le membre n'est pas trouvé ou l'argument est manquant
            await ctx.send(embed=self.create_embed(ctx, "⚠️ Commande Incomplète ou Invalide", self.get_syntax_help(), discord.Color.orange()), ephemeral=True)
        else:
            print(f"Erreur non gérée : {error}")
            await ctx.send(f"❌ Une erreur inattendue est survenue.", ephemeral=True)

async def setup(bot): await bot.add_cog(TempRMute(bot))