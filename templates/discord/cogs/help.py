import discord
from discord.ext import commands
from discord import ui

try:
    from cogs.config_manager.utils import config_manager
except ImportError:
    config_manager = None

try:
    from cogs.config_manager.stats_store import stats_db
except ImportError:
    stats_db = None

try:
    from synkrone_slash import runtime_prefix, slash_enabled
except ImportError:
    def runtime_prefix(bot=None, default="*"):
        return default

    def slash_enabled():
        return True

# ==============================================================================
# --------------------------- DONNÉES DES COMMANDES ----------------------------
# ==============================================================================
COMMANDS_STRUCTURE = {
    "Propriétaire": {
        "Général": [
            ("💻", "devembed", "Configurer le style de l'embed global"),
            ("🤖", "panelbot", "Configurer l'identité globale du bot"),
        ]
    },
    "Configuration": {
        "Salons & Salons Vocaux": [
            ("📥", "bienvenue", "Configurer le message et le salon des nouveaux membres"),
            ("📤", "aurevoir", "Configurer le message et le salon de départ"),
            ("👋", "bonjour", "Configurer l'heure, le salon & les messages de bonjour"),
            ("📡", "notif", "Mettre en avant les vidéos, lives et streams"),
            ("📜", "log", "Créer les salons de logs du serveur"),
            ("📊", "statsserver", "Configurer les salons vocaux de statistiques"),
            ("🎤", "voice", "Configurer le système de vocaux personnalisés"),
        ],
        "Styles & Modules": [
            ("🛡️", "antiscam", "Configurer le mode antiscam"),
            ("📝", "custom", "Configurer les messages customs (mots-clés)"),
            ("🎨", "servembed", "Configurer le style de l'embed du serveur"),
            ("🎫", "ticket", "Configurer le système de tickets"),
            ("⚙️", "config", "Ouvrir le hub de configuration du serveur"),
        ]
    },
    "Utilitaires ADMIN": {
        "Gestion & Outils": [
            ("➕", "addmembre", "Ajouter rapidement un utilisateur dans un salon"),
            ("📢", "annonce", "Poster une annonce rapidement"),
            ("🧹", "clear", "Effacer des lots de messages en masse"),
            ("➖", "delmembre", "Retirer rapidement un utilisateur dans un salon"),
            ("🪧", "embed", "Créer ou modifier un embed"),
            ("😀", "emoji", "Ajouter ou récupérer un emoji"),
            ("🗣️", "say", "Faire parler le bot"),
        ]
    },
    "Modération": {
        "Sanctions & Expulsions": [
            ("🔨", "ban", "Bannir complètement un utilisateur du serveur"),
            ("📋", "banlist", "Afficher la liste des utilisateurs bannis"),
            ("⏳", "tempban", "Bannir temporairement un utilisateur"),
            ("🕊️", "unban", "Débannir un utilisateur"),
            ("📉", "derank", "Retirer tous les rôles d'un utilisateur"),
            ("🥾", "kick", "Expulser un utilisateur du serveur"),
        ],
        "Mutes & Restrictions": [
            ("🔇", "mute", "Rendre un utilisateur muet"),
            ("🗂️", "mutelist", "Afficher la liste des utilisateurs muets"),
            ("🔊", "unmute", "Rendre la parole à un utilisateur"),
            ("🤐", "rmute", "Rendre un utilisateur muet de manière stricte/rôle"),
            ("⏱️", "tempmute", "Rendre un utilisateur muet temporairement"),
            ("🛑", "temprmute", "Rendre un utilisateur muet temporairement avec restriction"),
        ],
        "Sécurité & Salon": [
            ("🔒", "lock", "Verrouiller un salon"),
            ("🔐", "lockall", "Verrouiller tous les salons du serveur"),
            ("🔓", "unlock", "Déverrouiller un salon"),
            ("🐢", "slowmode", "Définir le mode lent sur un salon"),
            ("🔓", "unlockall", "Déverrouiller tous les salons du serveur"),
        ],
        "Suivi & Alertes": [
            ("⚠️", "warn", "Avertir un utilisateur"),
            ("ℹ️", "warninfo", "Afficher les détails d'un avertissement"),
            ("📚", "warnlist", "Afficher la liste des avertissements d'un utilisateur"),
        ]
    },
    "Public": {
        "Général": [
            ("🔍", "custom", "Afficher les mots-clés custom disponibles (commande publique)"),
            ("🎲", "dice", "Lancer des dés (nombre et faces au choix)"),
            ("🏓", "ping", "Afficher la latence du bot"),
            ("🔧", "prefix", "Afficher ou changer le préfixe"),
            ("📊", "stats", "Afficher les statistiques runtime du bot"),
            ("❓", "help", "Menu d'aide interactif"),
        ]
    }
}


SUBCATEGORY_COMMAND_ORDER = {
    "Gestion & Outils": {
        "addmembre": 0,
        "delmembre": 1,
    },
    "Sanctions & Expulsions": {
        "ban": 0,
        "banlist": 1,
        "tempban": 2,
        "unban": 3,
        "derank": 4,
        "kick": 5,
    },
    "Sécurité & Salon": {
        "lock": 0,
        "lockall": 1,
        "unlock": 2,
        "unlockall": 3,
        "slowmode": 4,
    },
}


def sort_commands(sub_name: str, cmd_list: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    custom_order = SUBCATEGORY_COMMAND_ORDER.get(sub_name)
    if custom_order:
        return sorted(cmd_list, key=lambda cmd: (custom_order.get(cmd[1], 999), cmd[1]))
    return sorted(cmd_list, key=lambda cmd: cmd[1])


def loaded_command_names(bot: commands.Bot) -> set[str]:
    names = set()
    for cmd in bot.commands:
        names.add(cmd.name)
        names.update(cmd.aliases or [])
    return names


def format_invocation(name: str, prefix: str, slash_on: bool) -> str:
    prefix_form = f"`{prefix}{name}`"
    slash_form = f"`/{name}`"
    if slash_on:
        return f"{slash_form} {prefix_form}"
    return prefix_form


# ==============================================================================
# --------------------------- UI : MENU DÉROULANT ------------------------------
# ==============================================================================
class HelpDropdown(ui.Select):
    def __init__(self, is_owner: bool, is_admin: bool):
        options = [
            discord.SelectOption(label="Accueil", description="Revenir à la page principale", emoji="🏠", value="Accueil"),
            discord.SelectOption(label="Public", description="Commandes accessibles à tous", emoji="🌍", value="Public")
        ]

        if is_admin or is_owner:
            options.insert(1, discord.SelectOption(label="Configuration", description="Paramétrer le serveur", emoji="⚙️", value="Configuration"))
            options.insert(2, discord.SelectOption(label="Utilitaires ADMIN", description="Outils de gestion pratiques", emoji="🛠️", value="Utilitaires ADMIN"))
            options.insert(3, discord.SelectOption(label="Modération", description="Sécurité et sanctions", emoji="🛡️", value="Modération"))
            options.append(discord.SelectOption(label="Vue Complète", description="Afficher toutes les commandes d'un coup", emoji="📑", value="Longue"))

        if is_owner:
            options.insert(1, discord.SelectOption(label="Propriétaire", description="Commandes exclusives au créateur", emoji="👑", value="Propriétaire"))

        super().__init__(placeholder="🔍 Parcourez les catégories de commandes...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        cog = self.view.cog
        ctx = self.view.ctx

        if category == "Accueil":
            embed = await cog.get_home_embed(ctx)
        elif category == "Longue":
            embed = cog.get_long_embed(ctx, self.view.is_owner)
        else:
            embed = cog.get_category_embed(ctx, category)

        await interaction.response.edit_message(embed=embed)

class HelpView(ui.View):
    def __init__(self, ctx: commands.Context, cog: commands.Cog, is_owner: bool, is_admin: bool):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.cog = cog
        self.is_owner = is_owner
        self.add_item(HelpDropdown(is_owner, is_admin))

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if hasattr(self, 'message') and self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

# ==============================================================================
# --------------------------- COG PRINCIPAL ------------------------------------
# ==============================================================================
class HelpCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.remove_command("help")

    def _prefix(self, ctx: commands.Context | None = None) -> str:
        used = getattr(ctx, "prefix", None) if ctx else None
        if used and used not in ("/", ""):
            return str(used)
        return runtime_prefix(self.bot, default="*")

    def _slash_on(self) -> bool:
        try:
            return bool(slash_enabled())
        except Exception:
            return True

    def _visible_commands(self, cmd_list: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
        loaded = loaded_command_names(self.bot)
        return [item for item in cmd_list if item[1] in loaded]

    def _format_line(self, emoji: str, name: str, desc: str, ctx: commands.Context) -> str:
        inv = format_invocation(name, self._prefix(ctx), self._slash_on())
        return f"{emoji} {inv} - *{desc}*\n"

    async def get_home_embed(self, ctx: commands.Context) -> discord.Embed:
        guild = ctx.guild
        bot_user = self.bot.user
        
        app_info = await self.bot.application_info()
        owner_mention = app_info.owner.mention if app_info.owner else "Inconnu"

        total_members = int((guild.member_count if guild else 0) or (len(guild.members) if guild else 0) or 0)
        bots_count = sum(1 for member in guild.members if member.bot) if guild else 0
        humans_count = max(0, total_members - bots_count)
        bot_texte = "bot" if bots_count <= 1 else "bots"
        
        if stats_db:
            cmd_total, cmd_month, cmd_today = stats_db.get_stats()
        else:
            cmd_total = cmd_month = cmd_today = 0

        prefix = self._prefix(ctx)
        if self._slash_on():
            invoke_hint = (
                f"Toutes les commandes existent en slash (`/commande`) et en préfixe (`{prefix}commande`)."
            )
        else:
            invoke_hint = f"Les commandes s'utilisent avec le préfixe `{prefix}` (slash désactivé)."

        desc = (
            f"👋 Bonjour ! Je suis **{bot_user.name}**, un bot exclusif au serveur **{guild.name if guild else '?'}** !\n\n"
            f"👑 Mon propriétaire est {owner_mention}.\n\n"
            f"👥 Nous sommes actuellement **{total_members}** personnes sur le serveur, comptant **{bots_count}** {bot_texte} pour **{humans_count}** humains !\n\n"
            f"📈 **{cmd_total:,}** commandes ont été lancées avec ce bot depuis sa création, dont **{cmd_month:,}** ce mois-ci & **{cmd_today:,}** aujourd'hui.\n\n"
            f"💡 *Le saviez-vous ?* {invoke_hint}\n\n"
            f"🔽 **Utilisez le menu déroulant ci-dessous pour naviguer entre les catégories.**"
        )

        if config_manager:
            embed = config_manager.get_formatted_embed(guild, ctx.author, self.bot, "🏠 Accueil - Centre d'Aide", desc, guild.id if guild else None)
        else:
            embed = discord.Embed(title="🏠 Accueil - Centre d'Aide", description=desc, color=0x2b2d31)

        if bot_user and bot_user.avatar:
            embed.set_thumbnail(url=bot_user.avatar.url)
        
        return embed

    def get_category_embed(self, ctx: commands.Context, category_name: str) -> discord.Embed:
        subcategories = COMMANDS_STRUCTURE.get(category_name, {})
        desc = f"Retrouvez ci-dessous l'ensemble des fonctionnalités pour la catégorie **{category_name}**.\n\n"
        
        for sub_name, cmd_list in subcategories.items():
            visible = self._visible_commands(cmd_list)
            if not visible:
                continue
            desc += f"### 📌 {sub_name}\n"
            sorted_commands = sort_commands(sub_name, visible)
            for emoji, cmd_name, cmd_desc in sorted_commands:
                desc += self._format_line(emoji, cmd_name, cmd_desc, ctx)
            desc += "\n"

        if config_manager:
            embed = config_manager.get_formatted_embed(ctx.guild, ctx.author, self.bot, f"📂 Catégorie : {category_name}", desc, ctx.guild.id if ctx.guild else None)
        else:
            embed = discord.Embed(title=f"📂 Catégorie : {category_name}", description=desc, color=0x2b2d31)

        if self.bot.user and self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
            
        return embed

    def get_long_embed(self, ctx: commands.Context, is_owner: bool) -> discord.Embed:
        desc = "Voici la liste complète de toutes les commandes disponibles sur le bot.\n\n"

        for category_name, subcategories in COMMANDS_STRUCTURE.items():
            if category_name == "Propriétaire" and not is_owner:
                continue

            block = ""
            for sub_name, cmd_list in subcategories.items():
                visible = self._visible_commands(cmd_list)
                if not visible:
                    continue
                block += f"### 📌 {sub_name}\n"
                sorted_commands = sort_commands(sub_name, visible)
                for emoji, cmd_name, cmd_desc in sorted_commands:
                    block += self._format_line(emoji, cmd_name, cmd_desc, ctx)
                block += "\n"
            if block:
                desc += f"## 📁 {category_name}\n{block}"

        if config_manager:
            embed = config_manager.get_formatted_embed(ctx.guild, ctx.author, self.bot, "📑 Vue Complète - Liste des commandes", desc, ctx.guild.id if ctx.guild else None)
        else:
            embed = discord.Embed(title="📑 Vue Complète - Liste des commandes", description=desc, color=0x2b2d31)

        if self.bot.user and self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
            
        return embed

    @commands.hybrid_command(name="help", description="Affiche le menu d'aide interactif du bot.")
    async def help_cmd(self, ctx: commands.Context):
        is_owner = await self.bot.is_owner(ctx.author)
        is_admin = bool(ctx.guild and (ctx.author.guild_permissions.administrator or ctx.author.guild_permissions.manage_guild))

        view = HelpView(ctx, self, is_owner, is_admin)
        embed = await self.get_home_embed(ctx)
        
        message = await ctx.send(embed=embed, view=view)
        view.message = message

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
