import discord
from discord.ext import commands

try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# Utilisation de tes emojis pour le style
POKEBALL_EMOJI = "<:pokeball:1522952715846684782>"
SHINY_EMOJI = "<:shiny:1522947934969270312>"
SUPERBONBON_EMOJI = "<:superbonbon:1522998956055990342>"
POKEDEX_EMOJI = "<:pokedex:1523703818603335821>"


HELP_CATEGORIES: dict[str, dict[str, str]] = {
    "main": {
        "title": f"{POKEBALL_EMOJI} Menu d'aide - Centre Pokémon",
        "description": (
            "Bienvenue dresseur !\n"
            "Ce menu regroupe toutes les commandes disponibles, classées par catégorie.\n\n"
            f"{POKEBALL_EMOJI} Préfixes disponibles : `/` et `'`\n"
            f"{SHINY_EMOJI} Ouvre le sélecteur pour naviguer catégorie par catégorie."
        ),
    },
    "aventure": {
        "title": f"{POKEBALL_EMOJI} Aventure & Équipe",
        "description": (
            f"{POKEBALL_EMOJI} `'capture` : Fait apparaître 1 Pokémon sauvage et tente une capture.\n"
            f"{SUPERBONBON_EMOJI} `'profil` : Affiche ta carte de dresseur complète.\n"
            f"⚔️ `'teams` : Affiche et configure ton équipe PvP.\n"
            f"🌙 `'sleep` : Ouvre ta garderie pour des revenus passifs."
        ),
    },
    "economie": {
        "title": f"{SUPERBONBON_EMOJI} Économie & Progression",
        "description": (
            f"💸 `'daily` | `'hourly` | `'weekly` | `'monthly` : Récupère tes bonus en Pokédollars.\n"
            f"🗳️ `'vote` : Vérifie ton vote et récupère ta récompense.\n"
            f"✨ `'charme` : Affiche et active tes charmes.\n"
            f"🤲 `'don` : Fais un don de Pokémon, objets ou argent.\n"
            f"♻️ `'doublon` : Gère tes doublons (relâche, évolution, recyclage).\n"
            f"🧩 `'enigme` : Lance le mini-jeu Pokémon du jour.\n"
            f"🏆 `'leader` : Consulte le classement des dresseurs."
        ),
    },
    "social": {
        "title": "🤝 Interaction entre joueurs",
        "description": (
            "🔄 `'echange` : Échange un Pokémon avec un autre joueur, avec confirmation des deux côtés.\n"
            "🛒 `'commerce` : Ouvre le marché joueur à joueur pour vendre et acheter des Pokémon.\n"
            "✉️ `'mail` : Ouvre l'interface Modmail pour communiquer en privé."
        ),
    },
    "combat": {
        "title": "⚔️ Combat & Matchmaking",
        "description": (
            "🌿 `'farm` : Défie un Pokémon sauvage avec ton équipe.\n"
            "🔥 `'pvp join` : Rejoins la file de matchmaking PvP en temps réel.\n"
            "🚪 `'pvp leave` : Quitte la file PvP à tout moment."
        ),
    },
    "pokedex": {
        "title": f"{POKEDEX_EMOJI} Pokédex & Outils",
        "description": (
            f"{POKEDEX_EMOJI} `'pokedex` : Affiche le Pokédex visuel interactif.\n"
            "📘 `'pokemon <cible>` : Affiche la fiche complète d'un Pokémon.\n"
            "🔎 `'recherche` : Lance une recherche avancée par filtres.\n"
            "🧭 `'search` : Repère les doublons des autres que tu ne possèdes pas.\n"
            "📊 `'comparer <cible1> <cible2>` : Compare deux Pokémon rapidement.\n"
            "🛡️ `'faiblesse <cible>` : Affiche les faiblesses et résistances.\n"
            "🧬 `'fusion <cible1> <cible2>` : Crée une fusion visuelle des deux Pokémon.\n"
            "🎲 `'randomteam` : Génère une équipe aléatoire instantanément."
        ),
    },
}


class HelpCategorySelect(discord.ui.Select):
    def __init__(self, view: "HelpMenuView"):
        self.view_ref = view
        options = [
            discord.SelectOption(label="Accueil", value="main", emoji="🏠", description="Vue d'ensemble des commandes"),
            discord.SelectOption(label="Aventure", value="aventure", emoji="🌍", description="Capture, profil, équipe, sleep"),
            discord.SelectOption(label="Économie", value="economie", emoji="💰", description="Bonus, charmes, don, doublons"),
            discord.SelectOption(label="Social", value="social", emoji="🤝", description="Échange, commerce, mail"),
            discord.SelectOption(label="Combat", value="combat", emoji="⚔️", description="Farm et PvP"),
            discord.SelectOption(label="Pokédex & Outils", value="pokedex", emoji=discord.PartialEmoji.from_str(POKEDEX_EMOJI), description="Pokédex, recherche, search, fusion"),
        ]
        super().__init__(
            placeholder="Choisis une catégorie d'aide...",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        key = self.values[0]
        self.view_ref.current_key = key
        await interaction.response.edit_message(embed=self.view_ref.build_embed(), view=self.view_ref)


class HelpMenuView(discord.ui.View):
    def __init__(self, cog: "HelpCog", author_id: int, guild: discord.Guild | None, author: discord.abc.User):
        super().__init__(timeout=300)
        self.cog = cog
        self.author_id = author_id
        self.guild = guild
        self.author = author
        self.current_key = "main"
        self.message: discord.Message | None = None
        self.add_item(HelpCategorySelect(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Ce menu d'aide ne vous appartient pas.", ephemeral=True)
            return False
        return True

    def build_embed(self) -> discord.Embed:
        section = HELP_CATEGORIES[self.current_key]
        if config_manager:
            embed = config_manager.get_formatted_embed(
                self.guild,
                self.author,
                self.cog.bot,
                section["title"],
                section["description"],
            )
        else:
            embed = discord.Embed(
                title=section["title"],
                description=section["description"],
                color=0x2B2D31,
            )
            embed.set_footer(text="Navigation: utilise le sélecteur pour changer de catégorie.")
        return embed

    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, (discord.ui.Select, discord.ui.Button)):
                item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="help", aliases=["h", "aide", "a"], description="Affiche la liste des commandes")
    async def help_command(self, ctx: commands.Context):
        view = HelpMenuView(self, ctx.author.id, ctx.guild, ctx.author)
        embed = view.build_embed()
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

async def setup(bot):
    await bot.add_cog(HelpCog(bot))