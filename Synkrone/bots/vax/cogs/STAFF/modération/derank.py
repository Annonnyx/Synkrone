"""
COMMANDE DERANK - VAX V3
========================
Déclassement total d'un utilisateur (retrait de tous ses rôles amovibles).
Utilise l'architecture Layout V2, les retours persistants et le système 
de permissions Vax centralisé.
"""

from __future__ import annotations

import traceback
from typing import Optional

import discord
from discord import ui
from discord.ext import commands

# Imports standards Vax v3 selon nos directives de configuration
from utils.config_perm import ensure_command_permission, perm_command
from utils.config_theme import config_manager
from utils.config_emoji import Emoji as E

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
    print(f"{color}[DEBUG - Derank] [{level.upper()}] {message}{reset}")

# ==============================================================================
# ----------------------------- EMOJIS CENTRALISÉS -----------------------------
# ==============================================================================
# Configuration rapide des icônes utilisées dans ce module
ICO_SUCCESS = getattr(E, 'VALIDE', "âœ…")
ICO_ERROR   = getattr(E, 'ERREUR', "âŒ")
ICO_INFO    = getattr(E, 'INFO', "â„¹ï¸")
ICO_DOWN    = getattr(E, 'BAISSE', "ðŸ“‰")
ICO_ADMIN   = getattr(E, 'BOUCLIER', "ðŸ›¡ï¸")
ICO_GEARS   = getattr(E, 'MODIFIER', "âš™ï¸")

# ==============================================================================
# ------------------------- VUE LAYOUT V2 DE RÉSULTAT --------------------------
# ==============================================================================
class DerankResultView(ui.LayoutView):
    """Génère l'interface Layout V2 pour afficher le résultat du déclassement."""
    
    def __init__(
        self, 
        bot: commands.Bot, 
        guild: discord.Guild, 
        author: discord.Member, 
        target: discord.Member, 
        roles_text: str,
        is_error: bool = False
    ):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild = guild
        self.author = author
        self.target = target
        self.roles_text = roles_text
        self.is_error = is_error
        self._build()

    def _build(self) -> None:
        self.clear_items()
        
        # Récupération dynamique du thème du serveur
        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.author, self.bot)
        
        # En cas d'erreur, on force une couleur rougeoyante, sinon on applique le thème
        accent_color = 0xED4245 if self.is_error else int(theme.get("color", discord.Color.red().value))
        footer_text = theme.get("footer_text", "")

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        
        if self.is_error:
            container.add_item(ui.TextDisplay(f"## {ICO_ERROR} Échec de l'opération"))
            container.add_item(ui.TextDisplay(f"{self.roles_text}"))
        else:
            container.add_item(ui.TextDisplay(f"## {ICO_DOWN} Déclassement Effectué"))
            container.add_item(ui.TextDisplay(f"L'utilisateur {self.target.mention} a été intégralement déclassé par {self.author.mention}.\n"))
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
            container.add_item(ui.TextDisplay(f"**Rôles traités :**\n{self.roles_text}"))
            
        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))
            
        self.add_item(container)

# ==============================================================================
# ------------------------------ COG PRINCIPAL ---------------------------------
# ==============================================================================
class Derank(commands.Cog):
    """Module de modération avancé : Déclassement d'utilisateurs."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        debug_log("Cog Derank initialisé avec succès.", "SUCCESS")

    @perm_command(level=3) # Niveau 3 défini par défaut pour des actions de modération lourdes
    @commands.command(
        name="derank", 
        description="Retire tous les rôles d'un membre (Action définitive)"
    )
    async def derank(self, ctx: commands.Context, member: discord.Member):
        debug_log(f"Lancement de /derank par {ctx.author} ({ctx.author.id}) sur {member} ({member.id})", "INFO")

        # 1. Vérification des permissions Vax
        if not await ensure_command_permission(ctx, command_name="derank"):
            debug_log(f"Permission refusée pour {ctx.author}", "WARNING")
            return
            
        # 2. Sécurités de base (Messages persistants)
        if member.id == ctx.guild.owner_id:
            msg = "Impossible de déclasser le propriétaire du serveur."
            debug_log(msg, "ERROR")
            view = DerankResultView(self.bot, ctx.guild, ctx.author, member, msg, is_error=True)
            return await ctx.send(view=view)
        
        if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            msg = "Hiérarchie insuffisante : Ce membre possède un rôle égal ou supérieur au vôtre."
            debug_log(msg, "ERROR")
            view = DerankResultView(self.bot, ctx.guild, ctx.author, member, msg, is_error=True)
            return await ctx.send(view=view)

        # Signal de traitement au client Discord
        await ctx.defer()

        # 3. Filtrage et Tri
        to_remove = [r for r in member.roles[1:] if not r.managed]
        
        if not to_remove:
            msg = "Aucun rôle amovible n'a été trouvé sur cet utilisateur."
            debug_log(msg, "WARNING")
            view = DerankResultView(self.bot, ctx.guild, ctx.author, member, msg, is_error=True)
            return await ctx.send(view=view)

        # Tri du rôle le plus haut au plus bas
        to_remove.sort(key=lambda r: r.position, reverse=True)

        role_list_text = []
        bot_top_role = ctx.guild.me.top_role

        # 4. Traitement des rôles
        for r in to_remove:
            label = ""
            if r.permissions.administrator: 
                label = f" *({ICO_ADMIN} ADMIN)*"
            elif any([r.permissions.manage_guild, r.permissions.manage_roles, r.permissions.kick_members]):
                label = f" *({ICO_GEARS} GESTION)*"

            if r.position >= bot_top_role.position:
                debug_log(f"Impossible de retirer '{r.name}' : Position bot insuffisante.", "WARNING")
                role_list_text.append(f"> {ICO_ERROR} {r.mention}{label} *(Échec : Hiérarchie Bot)*")
            else:
                try:
                    await member.remove_roles(r, reason=f"Derank invoqué par {ctx.author}")
                    role_list_text.append(f"> {ICO_SUCCESS} {r.mention}{label}")
                    debug_log(f"Rôle '{r.name}' retiré avec succès.", "SUCCESS")
                except Exception as e:
                    debug_log(f"Erreur technique lors du retrait de '{r.name}' : {e}", "ERROR")
                    role_list_text.append(f"> {ICO_ERROR} {r.mention}{label} *(Erreur Technique)*")

        # Nettoyage du message d'invocation si préfixe textuel
        if not ctx.interaction and ctx.message:
            try: 
                await ctx.message.delete()
            except discord.HTTPException: 
                pass

        # 5. Rendu du résultat via Layout V2
        final_text = "\n".join(role_list_text)
        view = DerankResultView(self.bot, ctx.guild, ctx.author, member, final_text, is_error=False)
        await ctx.send(view=view)
        debug_log(f"Déclassement de {member} terminé avec succès.", "SUCCESS")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Derank(bot))
    debug_log("Cog Derank enregistré.", "SUCCESS")
