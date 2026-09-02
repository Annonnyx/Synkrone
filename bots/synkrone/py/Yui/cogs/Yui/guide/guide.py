import discord
from discord.ext import commands

# --- Importation du Gestionnaire de Configuration (Embeds harmonisés) ---
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# ==============================================================================
# --------------------------- COMPONENTS (UI) ----------------------------------
# ==============================================================================

class HelpSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Accueil", value="home", emoji="🏠", description="Vue d'ensemble et démarrage rapide."),
            discord.SelectOption(label="Infos & Utilitaires", value="utility", emoji="🧭", description="Architecture, infos, design et vue."),
            discord.SelectOption(label="Création & IA", value="create", emoji="🛠️", description="Déploiement simple, massif ou IA."),
            discord.SelectOption(label="Modération & Accès", value="moderation", emoji="🧹", description="Gestion des rôles, permissions et salons."),
            discord.SelectOption(label="Nettoyage", value="cleanup", emoji="🔥", description="Destruction et purge de masse."),
            discord.SelectOption(label="Sauvegarde (Backup)", value="backup", emoji="💾", description="Création et restauration de données."),
        ]
        super().__init__(
            placeholder="📍 Naviguez dans les catégories du guide...", 
            min_values=1, 
            max_values=1, 
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        view: GuideView = self.view
        page = self.values[0]
        embed = view.make_page_embed(interaction, page)
        await interaction.response.edit_message(embed=embed, view=view)


class GuideView(discord.ui.View):
    def __init__(self, bot: commands.Bot, author_id: int):
        # Sécurité : Timeout de 300s (5 minutes) pour éviter la surcharge mémoire
        super().__init__(timeout=300)
        self.bot = bot
        self.author_id = author_id
        self.add_item(HelpSelect())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Vérifie que seul l'auteur de la commande peut interagir avec le menu."""
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ **Accès refusé** : Vous n'êtes pas l'auteur de cette commande.", 
                ephemeral=True
            )
            return False
        return True

    def base_embed(self, source, title: str, description: str) -> discord.Embed:
        """Génère l'embed en utilisant le config_manager s'il est disponible."""
        user = source.user if isinstance(source, discord.Interaction) else source.author
        guild = source.guild

        if config_manager:
            embed = config_manager.get_formatted_embed(
                guild=guild,
                user=user,
                bot=self.bot,
                title=title,
                description=description,
                target_id=guild.id if guild else None,
            )
            embed.remove_author()
        else:
            embed = discord.Embed(title=title, description=description, color=0x2B2D31)

        if self.bot.user and self.bot.user.display_avatar:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            if not config_manager:
                embed.set_footer(text="Guide Administratif Central", icon_url=self.bot.user.display_avatar.url)
        return embed

    def make_page_embed(self, source, page: str) -> discord.Embed:
        """Routeur vers la bonne page d'aide."""
        builders = {
            "home": self.page_home,
            "utility": self.page_utility,
            "create": self.page_create,
            "moderation": self.page_moderation,
            "cleanup": self.page_cleanup,
            "backup": self.page_backup,
        }
        return builders.get(page, self.page_home)(source)

    # ==========================================================================
    # --------------------------- PAGES D'AIDE ---------------------------------
    # ==========================================================================

    def page_home(self, source):
        desc = (
            "Bienvenue dans le **Centre de Contrôle Administratif**.\n"
            "Naviguez via le menu déroulant ci-dessous pour découvrir toutes les fonctionnalités mises à votre disposition.\n\n"
            "**⚙️ Informations Globales :**\n"
            "> **Préfixe classique** : `?` (Modifiable via `?prefix`)\n"
            "> **Préfixe moderne** : `/` (Commandes Slash supportées)\n\n"
            "**📌 Raccourcis Essentiels :**\n"
            "• 🤖 **IA** : `?newserv` - Création assistée par IA.\n"
            "• 🏗️ **Déploiement** : `?build` - Création en masse.\n"
            "• 🔒 **Sécurité** : `?admin` - Bascule de confidentialité.\n"
            "• 💾 **Sécurité** : `?backup` - Sauvegarde instantanée.\n"
            "• 🧹 **Organisation** : `?reorga` - Agencement du serveur.\n\n"
            "-# *Sélectionnez une catégorie ci-dessous pour plus de détails.*"
        )
        return self.base_embed(source, "🏠 Accueil & Vue d'ensemble", desc)

    def page_utility(self, source):
        desc = (
            "**⚙️ GuideInteractif** (`?guide`)\n"
            "> Ouvre ce menu interactif complet et détaillé.\n\n"
            "**📊 Analyse Serveur** (`?info`)\n"
            "> Génère un rapport détaillé du serveur : statistiques, rôles, membres, bots et configuration.\n\n"
            "**📐 Agencement** (`?reorga`)\n"
            "> Déplace et réorganise intelligemment vos salons et vos catégories pour une structure parfaite.\n\n"
            "**🎨 Thème Embed** (`?servembed` ou `?edit`)\n"
            "> Lance l'assistant de personnalisation pour harmoniser l'identité visuelle de vos messages.\n\n"
            "**🔑 Gestion Préfixe** (`?prefix`)\n"
            "> Configurez les préfixes textuels (ajout, retrait, modification).\n\n"
            "**👁️ Mode Lecture** (`?view`)\n"
            "> Verrouille instantanément le salon actuel en lecture seule pour tous les membres."
        )
        return self.base_embed(source, "🧭 Utilitaires & Architecture", desc)

    def page_create(self, source):
        desc = (
            "**🧠 Génération IA** (`?newserv`)\n"
            "> **Nouveau !** Créez un serveur complet et optimisé en quelques secondes, propulsé par l'Intelligence Artificielle.\n\n"
            "**🏗️ Déploiement Massif** (`?build`)\n"
            "> Interface de création multiple. Générez plusieurs salons et rôles simultanément en une seule action.\n\n"
            "**🛠️ Création Ciblée** (`?create <nom>`)\n"
            "> Ouvre un menu élégant pour créer un élément précis : salon vocal, salon textuel, forum, catégorie ou rôle.\n\n"
            "**🎯 Attribution Directe** (`?addrole <@user/ID> <@role/ID>`)\n"
            "> Assigne instantanément un rôle existant à un membre ciblé."
        )
        return self.base_embed(source, "🛠️ Création & Intelligence Artificielle", desc)

    def page_moderation(self, source):
        desc = (
            "**🛡️ Bascule Privée** (`?admin`)\n"
            "> Rend instantanément le salon actuel privé (ou public) en ajustant les permissions d'accès.\n\n"
            "**🧹 Purge Ciblée** (`?clear [nombre] [@membre]`)\n"
            "> Nettoie les messages récents selon un volume précis, avec la possibilité de cibler un utilisateur.\n\n"
            "**📉 Rétrogradation** (`?derank <@membre>`)\n"
            "> Démét immédiatement un membre de ses rôles amovibles (selon la hiérarchie du bot).\n\n"
            "**👥 Gestion de Masse** (`?rolemembre`)\n"
            "> Interface avancée pour attribuer des rôles à plusieurs membres, incluant des durées temporaires.\n\n"
            "**🔓 Contrôle d'Accès** (`?accesadd` / `?accesdel`)\n"
            "> Octroie ou révoque le droit de lecture/écriture d'un membre ou d'un rôle pour le salon actuel.\n\n"
            "**➖ Révocation Rôle** (`?delrole <@user/ID> <@role/ID>`)\n"
            "> Retire un rôle spécifique à un utilisateur de façon ciblée."
        )
        return self.base_embed(source, "🧹 Modération & Sécurité", desc)

    def page_cleanup(self, source):
        desc = (
            "⚠️ *Ces commandes effectuent des actions destructives. Utilisez-les avec précaution.*\n\n"
            "**🧨 Destruction Massive** (`?unbuild`)\n"
            "> Permet de sélectionner et supprimer de multiples salons et rôles en une seule passe.\n\n"
            "**🔥 Purge Intégrale** (`?purge`)\n"
            "> Ouvre le menu de suppression radicale : effacez des catégories entières, des vocaux ou tous les émojis d'un coup.\n\n"
            "**🗑️ Suppression Ciblée** (`?sup <ID/#salon/@role>`)\n"
            "> Demande une confirmation sécurisée avant de détruire définitivement un salon ou un rôle spécifique."
        )
        return self.base_embed(source, "🔥 Nettoyage & Destruction", desc)

    def page_backup(self, source):
        desc = (
            "**💾 Gestionnaire de Sauvegarde** (`?backup`)\n"
            "> Accédez au terminal de sauvegarde complet. Protégez votre architecture contre les raids ou les erreurs.\n\n"
            "**Fonctionnalités incluses :**\n"
            "> • **Créer** une nouvelle image du serveur.\n"
            "> • **Éditer** ou renommer une sauvegarde existante.\n"
            "> • **Gérer** vos multiples points de restauration.\n\n"
            "**Méthodes de restauration :**\n"
            "> 🔄 **Restaurer (Écrase)** : Nettoie le serveur actuel avant de réinjecter la sauvegarde.\n"
            "> ➕ **Ajouter (Fusion)** : Conserve vos salons actuels et ajoute le contenu de la sauvegarde."
        )
        return self.base_embed(source, "💾 Système de Backup", desc)

# ==============================================================================
# ----------------------------- COG INITIALIZATION -----------------------------
# ==============================================================================

class Guide(commands.Cog):
    """Module de centre d'aide interactif."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name="guide", 
        description="Affiche le Centre de Contrôle Administratif et le guide des commandes."
    )
    async def guide(self, ctx: commands.Context):
        """
        Déploie l'interface d'aide hybride (Slash + Prefix).
        """
        view = GuideView(self.bot, ctx.author.id)
        embed = view.make_page_embed(ctx, "home")
        
        # Envoi intelligent selon le contexte (Slash vs Prefix)
        if ctx.interaction:
            await ctx.send(embed=embed, view=view)
        else:
            # Répond au message en mentionnant l'utilisateur pour une meilleure UX
            await ctx.send(embed=embed, view=view, reference=ctx.message, mention_author=False)

async def setup(bot: commands.Bot):
    # Sécurité : Si une commande native 'guide' existe, on l'écrase proprement.
    if bot.get_command("guide"):
        bot.remove_command("guide")
    await bot.add_cog(Guide(bot))