import discord
from discord.ext import commands
import json
import os
import sys

# ==========================================
# GESTION DES EMOJIS
# ==========================================
def load_emojis() -> dict:
    """Charge les emojis personnalisés avec fallback sur les emojis standards."""
    emoji_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'emoji.json')
    
    # Emojis standards de fallback
    fallback_emojis = {
        "cartes": "🎴", "kronos": "💰", "star": "⭐", "trophy": "🏆",
        "sword": "⚔️", "check": "✅", "handshake": "🤝", "cross": "❌",
        "gem": "💎", "chart": "📊", "user": "👤", "home": "🏠",
        "left_arrow": "⬅️", "right_arrow": "➡️", "plus": "➕", "info": "ℹ️"
    }
    
    try:
        with open(emoji_path, 'r', encoding='utf-8') as f:
            custom_emojis = json.load(f)
            
        # Fusionner avec fallback : garde les personnalisés, utilise fallback si manquant
        return {key: custom_emojis.get(key, default) for key, default in fallback_emojis.items()}
        
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback_emojis

emojis = load_emojis()

# ==========================================
# IMPORTATION DU CONFIG MANAGER
# ==========================================
BASE_DIR = os.path.dirname(__file__)
sys.path.append(os.path.join(BASE_DIR, '..', '..', '..', 'developpeur', 'commands', 'embed_type'))

try:
    from cogs.developpeur.commands.embed_type.utils import config_manager
    HAS_CONFIG_MANAGER = True
except ImportError:
    config_manager = None
    HAS_CONFIG_MANAGER = False


# ==========================================
# INTERFACE UTILISATEUR (UI) - VUES
# ==========================================
class HelpView(discord.ui.View):
    def __init__(self, prefix: str):
        super().__init__(timeout=120) # Temps un peu plus long pour laisser l'utilisateur lire
        self.current_page = "public"
        self.prefix = prefix # On stocke le préfixe du serveur
        
    @discord.ui.select(
        placeholder="📚 Naviguez dans les catégories...",
        options=[
            discord.SelectOption(
                label="Public",
                emoji="🌍",
                value="public",
                description="Commandes accessibles à tous les joueurs"
            ),
            discord.SelectOption(
                label="Administrateur",
                emoji="🛡️", 
                value="admin",
                description="Configuration et gestion du serveur"
            )
        ],
        custom_id="help_category_select"
    )
    async def callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        # Différer l'interaction pour éviter l'erreur "L'interaction a échoué" si le bot met du temps
        self.current_page = select.values[0]
        embed = self.create_help_embed(self.current_page, interaction.user)
        await interaction.response.edit_message(embed=embed, view=self)
    
    def create_help_embed(self, category: str, user: discord.User | discord.Member) -> discord.Embed:
        """Génère un embed visuellement agréable selon la catégorie choisie."""
        p = self.prefix

        if category == "admin":
            embed = discord.Embed(
                title="🛡️ Centre d'Administration",
                description="*Paramétrez le bot pour l'adapter parfaitement à votre serveur.*",
                color=discord.Color.brand_red()
            )
            embed.add_field(
                name="👑 Commandes serveur",
                value=(
                    f"**`{p}servembed`** • Configurez l'apparence des embeds sur ce serveur\n"
                    f"**`{p}prefix`** • Changez le préfixe d'appel du bot (`{p}` actuellement)"
                ),
                inline=False
            )
            
        else: # Public
            embed = discord.Embed(
                title="🌍 Bienvenue dans l'aide",
                description="*Découvrez toutes les fonctionnalités à votre disposition pour jouer !*",
                color=discord.Color.blurple()
            )
            embed.add_field(
                name="👤 Profils & Statistiques",
                value=(
                    f"**`{p}profil`** `[@user]` • Affichez les statistiques détaillées\n"
                    f"**`{p}collection`** • Admirez votre deck organisé par rareté\n"
                    f"**`{p}leader`** • Consultez les classements mondiaux"
                ),
                inline=False
            )
            embed.add_field(
                name="📚 Aide & Guide",
                value=(
                    f"**`{p}help`** • Affiche ce menu d'aide complet\n"
                    f"**`{p}guide`** • Explorez le guide complet du système de jeu\n"
                    f"**`{p}premium`** • Découvrez les avantages et fonctionnalités premium"
                ),
                inline=False
            )
            embed.add_field(
                name="🎯 Jeu & Progression",
                value=(
                    f"**`{p}collect`** • Tirez aléatoirement et découvrez de nouvelles cartes\n"
                    f"**`{p}daily`** • Récupérez votre récompense quotidienne (Argent/Cartes)\n"
                    f"**`{p}sleep`** • Mettez vos cartes en garderie pour gagner de l'XP"
                ),
                inline=False
            )
            embed.add_field(
                name="💰 Économie & Échanges",
                value=(
                    f"**`{p}shop`** • Explorez le marché communautaire\n"
                    f"**`{p}sell`** • Vendez vos cartes directement à Kayaba\n"
                    f"**`{p}boutique`** • Accédez à la boutique exclusive\n"
                    f"**`{p}echange`** `[@user]` • Proposez ou acceptez des échanges de cartes"
                ),
                inline=False
            )
            embed.add_field(
                name="⚔️ Interactions & Social",
                value=(
                    f"**`{p}pvp`** `[@user]` • Défiez un adversaire en duel\n"
                    f"**`{p}mp`** • Gérez vos notifications privées"
                ),
                inline=False
            )

        # Configuration du Footer et de la Couleur (Support du Config Manager)
        if HAS_CONFIG_MANAGER and config_manager:
            try:
                embed.color = config_manager.get_embed_color(user)
                embed.set_footer(
                    text=config_manager.get_embed_footer(user), 
                    icon_url=config_manager.get_embed_icon(user)
                )
            except Exception:
                # Fallback de sécurité si le config_manager plante
                embed.set_footer(text=f"Demandé par {user.display_name} • Système Kayaba Collection", icon_url=user.display_avatar.url if user.display_avatar else None)
        else:
            embed.set_footer(text=f"Demandé par {user.display_name} • Système Kayaba Collection", icon_url=user.display_avatar.url if user.display_avatar else None)
            
        return embed

# ==========================================
# COG PRINCIPAL
# ==========================================
class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_prefix(self, ctx: commands.Context) -> str:
        """Récupère le préfixe du bot de façon dynamique et sécurisée."""
        # 1. Priorité absolue : préfixe configuré via prefix.py (config_manager)
        if HAS_CONFIG_MANAGER and config_manager:
            try:
                if ctx.guild:
                    prefix = await config_manager.get_prefix(ctx.guild)
                    if prefix:
                        return prefix
            except Exception:
                pass
        
        # 2. Fallback : préfixe depuis le contexte Discord
        if hasattr(ctx, 'prefix') and ctx.prefix:
            return ctx.prefix
            
        # 3. Fallback final : préfixe par défaut
        return "."

    @commands.hybrid_command(name="help", description="Affiche le menu d'aide complet et interactif")
    async def help_command(self, ctx: commands.Context):
        # On récupère le bon préfixe avant de générer la vue
        prefix = await self.get_prefix(ctx)
        
        # On passe le préfixe à la vue pour qu'il s'affiche correctement
        view = HelpView(prefix=prefix)
        embed = view.create_help_embed("public", ctx.author)
        
        await ctx.send(embed=embed, view=view)

async def setup(bot):
    # Désactiver la commande d'aide par défaut de Discord.py (si ce n'est pas déjà fait dans ton main.py)
    # bot.remove_command("help") 
    await bot.add_cog(Help(bot))