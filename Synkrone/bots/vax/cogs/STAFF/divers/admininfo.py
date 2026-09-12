"""
MODULE ADMININFO - VAX V3
=========================
Affichage interactif (Layout V2) de l'administration du serveur.
S'ouvre EN PRIORITÉ sur la page des bots et intégrations.
Intègre le thème dynamique, les permissions centralisées et des retours 100% persistants.
"""

from __future__ import annotations

import discord
from discord import ui
from discord.ext import commands

# Imports standards Vax v3 pour la configuration et la sécurité[cite: 6]
from utils.config_perm import ensure_command_permission, perm_command
from utils.config_emoji import Emoji as E

try:
    from utils.config_theme import config_manager
except ImportError:
    config_manager = None

# ==============================================================================
# ------------------------------ DÉBOGAGE GLOBAL -------------------------------
# ==============================================================================
DEBUG_MODE = True
DEBUG_ERRORS_ONLY = True

def debug_log(message: str, level: str = "INFO") -> None:
    """Système de journalisation avec codes couleur ANSI pour la console."""
    if DEBUG_ERRORS_ONLY and level.upper() != "ERROR":
        return
    if not DEBUG_MODE and not DEBUG_ERRORS_ONLY:
        return

    colors = {
        "INFO": "\033[94m",       # Bleu
        "SUCCESS": "\033[92m",    # Vert
        "ERROR": "\033[91m",      # Rouge
        "WARNING": "\033[93m",    # Jaune
    }
    reset = "\033[0m"
    color = colors.get(level.upper(), "\033[97m")
    print(f"{color}[DEBUG - AdminInfo] [{level.upper()}] {message}{reset}")

# ==============================================================================
# ----------------------------- EMOJIS CENTRALISÉS -----------------------------
# ==============================================================================
# Configuration rapide des icônes pour le module
ICO_ADMIN   = getattr(E, 'OWNER', "ðŸ‘‘")
ICO_BOT     = getattr(E, 'VAX', "ðŸ¤–")
ICO_INFO    = getattr(E, 'INFO', "â„¹ï¸")
ICO_ERROR   = getattr(E, 'ERREUR', "âŒ")
ICO_SUCCESS = getattr(E, 'VALIDE', "âœ…")
ICO_SHIELD  = getattr(E, 'BOUCLIER', "ðŸ›¡ï¸")


# ==============================================================================
# ------------------------- INTERFACE LAYOUT V2 PRINCIPALE ---------------------
# ==============================================================================
class AdminInfoLayoutView(ui.LayoutView):
    """Vue Layout V2 gérant l'affichage des informations, priorisant les bots."""
    
    def __init__(self, cog: "AdminInfoCommand", guild: discord.Guild, user: discord.Member):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.user = user
        # ðŸŽ¯ DIRECTIVE VAX : Affichage prioritaire de la page des bots
        self.current_section = "bots" 
        self.info_text = ""
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Sécurité Vax : Rejet des interactions illégitimes via feedback persistant temporaire."""
        if interaction.user.id != self.user.id:
            # Zéro éphémère : Envoi d'un message persistant qui s'autodétruit
            await interaction.response.send_message(f"{ICO_ERROR} Ce menu ne vous appartient pas.", delete_after=7)
            return False
        return True

    async def refresh(self, interaction: discord.Interaction):
        """Met à jour l'affichage de manière fluide."""
        self._build()
        if interaction.response.is_done():
            await interaction.edit_original_response(view=self)
        else:
            await interaction.response.edit_message(view=self)
        self.info_text = ""

    def _build(self) -> None:
        self.clear_items()
        
        # Résolution dynamique du thème Vax[cite: 6]
        accent_color = discord.Color.blurple().value
        footer_text = ""
        if config_manager:
            theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.cog.bot)
            accent_color = int(theme.get("color", accent_color))
            footer_text = theme.get("footer_text", "")

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        
        # En-tête avec feedback intégré
        container.add_item(ui.TextDisplay(f"# {ICO_SHIELD} Informations du Serveur"))
        if self.info_text:
            container.add_item(ui.TextDisplay(f"**{self.info_text}**"))

        # Menu Sélecteur avec intégration LayoutV2 standard[cite: 6]
        nav_row = ui.ActionRow()
        nav_select = ui.Select(
            placeholder="Sélectionne la liste à afficher...",
            min_values=1, max_values=1,
            options=[
                discord.SelectOption(label="Bots & Intégrations", value="bots", emoji=ICO_BOT, default=(self.current_section=="bots")),
                discord.SelectOption(label="Équipe d'Administration", value="admins", emoji=ICO_ADMIN, default=(self.current_section=="admins")),
            ]
        )
        
        async def _on_nav_select(interaction: discord.Interaction):
            self.current_section = interaction.data.get("values", ["bots"])[0]
            await self.refresh(interaction)
            
        nav_select.callback = _on_nav_select
        nav_row.add_item(nav_select)
        container.add_item(nav_row)
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

        # Rendu de la section sélectionnée
        if self.current_section == "bots":
            self._render_bots(container)
        elif self.current_section == "admins":
            self._render_admins(container)

        # Application du footer Vax[cite: 6]
        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    def _render_bots(self, container: ui.Container) -> None:
        """Génère le texte pour la liste des bots présents (Section Prioritaire)."""
        bots = [m for m in self.guild.members if m.bot]
        bots = sorted(bots, key=lambda x: x.name.lower())
        
        container.add_item(ui.TextDisplay(f"## {ICO_BOT} Intégrations Automatisées"))
        
        if not bots:
            container.add_item(ui.TextDisplay(f"_{ICO_INFO} Aucun bot n'est présent sur ce serveur._"))
            return
            
        bot_count = len(bots)
        desc = f"**{bot_count} bot{'s' if bot_count > 1 else ''} identifié{'s' if bot_count > 1 else ''}**\n\n"
        
        lines = []
        for bot in bots[:50]:
            flags = f" *( {ICO_SHIELD} Admin )*" if bot.guild_permissions.administrator else ""
            lines.append(f"â€¢ {bot.mention} - `{bot.name}`{flags}")
            
        desc += "\n".join(lines)
        
        if bot_count > 50:
            desc += f"\n\n*... et {bot_count - 50} autres entités.*"
            
        container.add_item(ui.TextDisplay(desc))

    def _render_admins(self, container: ui.Container) -> None:
        """Génère le texte pour l'équipe d'administration (Propriétaire exclus)."""
        owner = self.guild.owner
        admins = [
            m for m in self.guild.members 
            if m.guild_permissions.administrator and not m.bot and (owner is None or m.id != owner.id)
        ]
        admins = sorted(admins, key=lambda x: x.name.lower())

        container.add_item(ui.TextDisplay(f"## {ICO_ADMIN} Direction & Administrateurs"))

        desc = ""
        if owner:
            desc += f"**Propriétaire du serveur :**\n> {owner.mention} - `{owner.name}`\n\n"
        
        if not admins and not owner:
            desc += f"_{ICO_INFO} Aucun administrateur trouvé._"
        elif admins:
            desc += f"**Administrateurs ({len(admins)}) :**\n"
            lines = [f"â€¢ {admin.mention} - `{admin.name}`" for admin in admins]
            
            if len(lines) > 40:
                desc += "\n".join(lines[:40])
                desc += f"\n\n*... et {len(lines) - 40} autres administrateurs.*"
            else:
                desc += "\n".join(lines)
        elif owner and not admins:
            desc += f"_{ICO_INFO} Aucun autre administrateur trouvé sur ce serveur._"

        container.add_item(ui.TextDisplay(desc))


# ==============================================================================
# ------------------------------ COG PRINCIPAL ---------------------------------
# ==============================================================================
class AdminInfoCommand(commands.Cog):
    """Cog d'Information : Affichage du panel d'administration (Bots en priorité)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        debug_log("Cog AdminInfo initialisé avec succès.", "SUCCESS")

    @perm_command(level=3) # Niveau 3 Vax pour les commandes staff standard[cite: 6]
    @commands.hybrid_command(name="admininfo", description="Affiche l'équipe d'administration et les bots du serveur.")
    @discord.app_commands.guild_only()
    async def admininfo(self, ctx: commands.Context):
        debug_log(f"Commande /admininfo exécutée par {ctx.author} ({ctx.author.id})", "INFO")

        if not ctx.guild:
            await ctx.send(f"{ICO_ERROR} Cette commande est exclusive aux serveurs.", delete_after=7)
            return
            
        # Vérification Vax stricte des permissions[cite: 6]
        if not await ensure_command_permission(ctx, command_name="admininfo"):
            debug_log(f"Accès refusé pour {ctx.author}", "WARNING")
            return

        await ctx.defer()

        try:
            if not ctx.guild.chunked:
                await ctx.guild.chunk(cache=True)
                debug_log(f"Membres du serveur '{ctx.guild.name}' mis en cache.", "INFO")
        except Exception as e:
            debug_log(f"Échec de la mise en cache : {e}", "WARNING")

        try:
            view = AdminInfoLayoutView(self, ctx.guild, ctx.author)
            await ctx.send(view=view)
            debug_log(f"Menu AdminInfo déployé pour {ctx.author}", "SUCCESS")
        except Exception as exc:
            debug_log(f"Erreur lors de l'exécution : {exc}", "ERROR")
            await ctx.send(f"{ICO_ERROR} Une erreur technique a empêché l'affichage du menu.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AdminInfoCommand(bot))
    debug_log("Cog AdminInfo enregistré.", "SUCCESS")
