import discord
from discord.ext import commands
from discord import ui
from datetime import datetime

# ==============================================================================
# --------------------------- UTILS (Même logique) -----------------------------
# ==============================================================================
try:
    from cogs.developpeur.commands.embed_type.utils import config_manager
except ImportError:
    config_manager = None

class InspectorSelect(ui.Select):
    def __init__(self, cog, guild):
        self.cog = cog
        self.guild = guild
        options = [
            discord.SelectOption(label="Profil & Stats", description="Informations générales du serveur", emoji="📊", value="stats"),
            discord.SelectOption(label="Liste des Rôles", description="Hiérarchie et détails des rôles", emoji="👥", value="roles"),
            discord.SelectOption(label="Salons", description="Organisation des salons textuels et vocaux", emoji="💬", value="channels"),
            discord.SelectOption(label="Émojis", description="Liste des émojis du serveur", emoji="✨", value="emojis"),
            discord.SelectOption(label="Liste des Bots", description="Tous les automates présents", emoji="🤖", value="bots"),
            discord.SelectOption(label="Administrateurs", description="Membres avec les permissions admin", emoji="🛡️", value="admins"),
        ]
        super().__init__(placeholder="Choisissez une catégorie à inspecter...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]
        
        if value == "stats":
            embed = self.cog.get_stats_embed(interaction)
        elif value == "roles":
            embed = self.cog.get_roles_embed(interaction)
        elif value == "channels":
            embed = self.cog.get_channels_embed(interaction)
        elif value == "emojis":
            embed = self.cog.get_emojis_embed(interaction)
        elif value == "bots":
            embed = self.cog.get_bots_embed(interaction)
        elif value == "admins":
            embed = self.cog.get_admins_embed(interaction)

        await interaction.response.edit_message(embed=embed, view=self.view)

class InspectorView(ui.View):
    def __init__(self, cog, guild, author_id):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.add_item(InspectorSelect(cog, guild))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Seul l'auteur de la commande peut utiliser ce menu.", ephemeral=True)
            return False
        return True

# ==============================================================================
# --------------------------- COG PRINCIPAL ------------------------------------
# ==============================================================================

class GuildInspector(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_custom_embed(self, inter, title, description, color=0x2b2d31):
        user = inter.user if isinstance(inter, discord.Interaction) else inter.author
        guild = inter.guild
        if config_manager:
            embed = config_manager.get_formatted_embed(
                guild=guild, user=user, bot=self.bot,
                title=title, description=description,
                target_id=guild.id
            )
            # Retrait complet de l'auteur
            embed.remove_author()
        else:
            embed = discord.Embed(title=title, description=description, color=color)
        
        if self.bot.user.display_avatar:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        return embed

    # --- GENERATEURS D'EMBEDS ---

    def get_stats_embed(self, inter):
        g = inter.guild
        owner = g.owner.mention if g.owner else "Inconnu"
        created = f"<t:{int(g.created_at.timestamp())}:R>"
        
        bots = len([m for m in g.members if m.bot])
        humans = g.member_count - bots
        
        desc = (
            f"**Propriétaire :** {owner}\n"
            f"**Création :** {created}\n\n"
            f"📈 **Membres :** {g.member_count}\n"
            f"👤 **Humains :** {humans}\n"
            f"🤖 **Bots :** {bots}"
        )
        return self.get_custom_embed(inter, f"📊 Statistiques de {g.name}", desc)

    def get_roles_embed(self, inter):
        g = inter.guild
        roles = sorted(g.roles[1:], key=lambda r: r.position, reverse=True)
        
        # Pagination : 100 rôles par page
        per_page = 100
        total_pages = (len(roles) + per_page - 1) // per_page
        page = 1  # Page 1 par défaut
        
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        page_roles = roles[start_idx:end_idx]
        
        role_text = [f"• {r.mention}" for r in page_roles]
        
        desc = "\n".join(role_text) if role_text else "Aucun rôle."
        desc += f"\n\n*Page {page}/{total_pages} - Total : {len(roles)} rôles*"
        
        return self.get_custom_embed(inter, "👥 Liste des Rôles", desc)

    def get_channels_embed(self, inter):
        g = inter.guild
        categories = sorted(g.categories, key=lambda c: c.position)
        
        desc = f"**{len(categories)} catégories trouvées**\n\n"
        
        for cat in categories:
            if cat.channels:
                desc += f"📂 **{cat.name}** ({len(cat.channels)} salons)\n"
                
                # Salons textuels
                text_channels = [c for c in cat.channels if isinstance(c, discord.TextChannel)]
                if text_channels:
                    desc += "  💬 " + ", ".join([f"#{c.name}" for c in text_channels]) + "\n"
                
                # Salons vocaux
                voice_channels = [c for c in cat.channels if isinstance(c, discord.VoiceChannel)]
                if voice_channels:
                    desc += "  🔊 " + ", ".join([c.name for c in voice_channels]) + "\n"
                
                desc += "\n"
        
        return self.get_custom_embed(inter, "💬 Structure des Salons", desc)

    def get_emojis_embed(self, inter):
        g = inter.guild
        static = [e for e in g.emojis if not e.animated]
        animated = [e for e in g.emojis if e.animated]
        
        desc = f"**Total :** {len(g.emojis)} émojis\n\n"
        
        if static:
            desc += f"**Fixes ({len(static)}) :**\n"
            desc += " ".join([str(e) for e in static]) + "\n\n"
        
        if animated:
            desc += f"**Animés ({len(animated)}) :**\n"
            desc += " ".join([str(e) for e in animated])
        
        return self.get_custom_embed(inter, "✨ Émojis du Serveur", desc)

    def get_bots_embed(self, inter):
        g = inter.guild
        bots = [m for m in g.members if m.bot]
        
        if bots:
            bot_list = [f"• {m.mention} ({m.display_name})" for m in bots]
            desc = "\n".join(bot_list)
            desc += f"\n\n*Total : {len(bots)} bots*"
        else:
            desc = "Aucun bot sur ce serveur."
        
        return self.get_custom_embed(inter, "🤖 Liste des Bots", desc)

    def get_admins_embed(self, inter):
        g = inter.guild
        admins = [m for m in g.members if m.guild_permissions.administrator and not m.bot]
        
        if admins:
            admin_list = [f"• {m.mention} ({m.display_name})" for m in admins]
            desc = "\n".join(admin_list)
            desc += f"\n\n*Total : {len(admins)} administrateurs*"
        else:
            desc = "Aucun administrateur (humain) trouvé."
        
        return self.get_custom_embed(inter, "🛡️ Administrateurs", desc)

    # --- COMMANDE ---

    @commands.hybrid_command(name="info", description="Ouvre le panneau d'inspection du serveur")
    @commands.has_permissions(administrator=True)
    async def inspect(self, ctx):
        embed = self.get_custom_embed(
            ctx, 
            "🔍 Inspecteur de Serveur", 
            f"Bienvenue dans l'outil d'analyse de **{ctx.guild.name}**.\n\n"
            "Utilisez le menu déroulant ci-dessous pour explorer les données du serveur."
        )
        await ctx.send(embed=embed, view=InspectorView(self, ctx.guild, ctx.author.id))

async def setup(bot):
    await bot.add_cog(GuildInspector(bot))