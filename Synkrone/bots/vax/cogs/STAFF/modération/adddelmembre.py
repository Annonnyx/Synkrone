import discord
from discord import ui
from discord.ext import commands
from typing import Optional, Union
import traceback
import asyncio

# ==========================================
# GESTION DES CONFIGURATIONS (Séparation des préoccupations)
# ==========================================
# Intégration stricte de notre écosystème de configuration[cite: 3]
from utils.config_theme import config_manager
from utils.config_perm import ensure_command_permission, perm_command
from utils.config_emoji import Emoji as E

# ==========================================
# CONFIGURATION GLOBALE & DÉBOGAGE
# ==========================================
DEBUG_LOGS = True
ERROR_LOGS = True

# ==========================================
# CENTRALISATION DES EMOJIS UI
# ==========================================
EMOJI_SUCCESS = getattr(E, 'VALIDE', "âœ…")
EMOJI_ERROR = getattr(E, 'ERREUR', "âŒ")
EMOJI_UNLOCK = "ðŸ”“"
EMOJI_LOCK = "ðŸ”’"
EMOJI_MEMBER = getattr(E, 'PROFIL', "ðŸ‘¤")
EMOJI_ROLE = getattr(E, 'ROLE', "ðŸŽ­")
EMOJI_EVERYONE = getattr(E, 'MONDE', "ðŸŒ")
EMOJI_INFO = getattr(E, 'INFO', "â„¹ï¸")
EMOJI_BULLET = "ðŸ”¹"

# ==========================================
# UTILITAIRES DE LOGS (COLORIMÉTRIE)
# ==========================================
def log_info(message: str):
    """Affiche un log d'information en bleu profond pour le suivi d'exécution."""
    if DEBUG_LOGS:
        print(f"\033[94m[INFO]\033[0m {message}")

def log_success(message: str):
    """Affiche un log de succès en vert éclatant."""
    if DEBUG_LOGS:
        print(f"\033[92m[SUCCESS]\033[0m {message}")

def log_error(message: str):
    """Affiche un log d'erreur en rouge vif. Critique pour le débogage."""
    if ERROR_LOGS:
        print(f"\033[91m[ERROR]\033[0m {message}")

# ==========================================
# COG PRINCIPAL : GESTION DES ACCÈS
# ==========================================
class ChannelAccess(commands.Cog):
    """
    Gestion avancée des accès aux salons via LayoutV2 et permissions hiérarchiques.
    Conçu par Vax v3.
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log_info("Initialisation du module ChannelAccess (LayoutV2 strict)...")

    def _build_layout_view(self, ctx: commands.Context, title: str, description: str, color_hex: int, footer_text: str) -> ui.LayoutView:
        """Génère un LayoutV2 moderne pour standardiser les réponses du bot sans utiliser d'embeds obsolètes[cite: 3]."""
        view = ui.LayoutView(timeout=180)
        container = ui.Container(accent_color=discord.Color(color_hex), spoiler=False)
        
        container.add_item(ui.TextDisplay(f"# {title}"))
        container.add_item(ui.TextDisplay(description))
        
        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))
            
        view.add_item(container)
        return view

    def _format_target_name(self, target: Union[discord.Member, discord.Role], is_default: bool = False) -> str:
        """Formate l'affichage de la cible avec des backticks pour désamorcer les pings visuels natifs."""
        if is_default:
            return f"{EMOJI_EVERYONE} `@everyone`"
        if isinstance(target, discord.Role):
            return f"{EMOJI_ROLE} `@{target.name}`"
        return f"{EMOJI_MEMBER} `@{target.display_name}`"

    @perm_command(level=3)
    @commands.hybrid_command(
        name="addmembre", 
        description="Ouvre l'accès du salon à des membres, rôles, ou au serveur entier (@everyone)."
    )
    async def add_membre(
        self, 
        ctx: commands.Context, 
        cible: Optional[Union[discord.Member, discord.Role]] = None,
        cible2: Optional[Union[discord.Member, discord.Role]] = None,
        cible3: Optional[Union[discord.Member, discord.Role]] = None
    ):
        log_info(f"Déclenchement de 'addmembre' par {ctx.author} dans #{ctx.channel.name}")
        
        if not await ensure_command_permission(ctx, command_name="addmembre"):
            log_error(f"Rejet : Accès refusé pour {ctx.author} sur 'addmembre'[cite: 3].")
            return

        # Les messages éphémères sont bannis selon nos directives architecturales
        await ctx.defer(ephemeral=False)
        
        targets = [t for t in [cible, cible2, cible3] if t is not None]
        if not targets:
            targets = [ctx.guild.default_role]

        added_displays = []
        users_to_ping = []

        try:
            for t in targets:
                is_default = isinstance(t, discord.Role) and t.is_default()
                await ctx.channel.set_permissions(t, view_channel=True, send_messages=True)
                
                # Formatage sûr pour l'affichage (désactive le ping visuel)
                added_displays.append(self._format_target_name(t, is_default))
                
                # Extraction stricte des membres physiques pour la notification silencieuse
                if isinstance(t, discord.Member):
                    users_to_ping.append(t.mention)
                    
                log_success(f"ACL (view/send) accordées à {t.name if hasattr(t, 'name') else 'everyone'} dans #{ctx.channel.name}")

            theme = config_manager.get_layout_v2_theme(ctx.guild.id, ctx.guild, ctx.author, self.bot)
            color = int(theme.get("color", 0x57F287))
            footer = theme.get("footer_text", "")

            desc = f"{EMOJI_INFO} Le salon est désormais **visible** et **accessible** pour :\n"
            desc += "\n".join([f"{EMOJI_BULLET} {m}" for m in added_displays])
            
            view = self._build_layout_view(ctx, f"{EMOJI_UNLOCK} Accès Ajouté", desc, color, footer)
            
            # 1. Envoi strict du LayoutV2 SANS argument 'content' pour contourner l'erreur 50035[cite: 3]
            await ctx.send(view=view)

            # 2. Ghost Ping : Notification push silencieuse pour les membres (ajout -> suppression ultra-rapide)
            if users_to_ping:
                ping_content = " ".join(users_to_ping)
                mention_rules = discord.AllowedMentions(users=True, roles=False, everyone=False)
                ping_msg = await ctx.channel.send(content=ping_content, allowed_mentions=mention_rules)
                await asyncio.sleep(0.1) # Infime délai pour garantir la prise en compte du push par les serveurs Discord
                await ping_msg.delete()
                log_info(f"Ghost ping exécuté avec succès pour {len(users_to_ping)} utilisateur(s).")

        except discord.Forbidden:
            log_error(f"Erreur d'élévation : Le bot manque de droits sur #{ctx.channel.name}")
            await ctx.send(f"{EMOJI_ERROR} Privilèges insuffisants pour modifier la hiérarchie de ce salon.")
        except Exception as e:
            log_error(f"Exception système critique dans 'addmembre' : {e}")
            traceback.print_exc()
            await ctx.send(f"{EMOJI_ERROR} Une erreur système est survenue lors du traitement des permissions.")

    @perm_command(level=3)
    @commands.hybrid_command(
        name="delmembre", 
        description="Verrouille l'accès du salon et révoque les droits d'écriture (membres, rôles, @everyone)."
    )
    async def del_membre(
        self, 
        ctx: commands.Context, 
        cible: Optional[Union[discord.Member, discord.Role]] = None,
        cible2: Optional[Union[discord.Member, discord.Role]] = None,
        cible3: Optional[Union[discord.Member, discord.Role]] = None
    ):
        log_info(f"Déclenchement de 'delmembre' par {ctx.author} dans #{ctx.channel.name}")

        if not await ensure_command_permission(ctx, command_name="delmembre"):
            log_error(f"Rejet : Accès refusé pour {ctx.author} sur 'delmembre'[cite: 3].")
            return

        await ctx.defer(ephemeral=False)
        
        targets = [t for t in [cible, cible2, cible3] if t is not None]
        if not targets:
            targets = [ctx.guild.default_role]

        removed_displays = []

        try:
            for t in targets:
                is_default = isinstance(t, discord.Role) and t.is_default()
                
                # Révocation absolue des droits (view=False, send=False) pour une étanchéité parfaite
                await ctx.channel.set_permissions(t, view_channel=False, send_messages=False)
                removed_displays.append(self._format_target_name(t, is_default))
                log_success(f"ACL (view=False, send=False) appliquées pour {t.name if hasattr(t, 'name') else 'everyone'} sur #{ctx.channel.name}")

            theme = config_manager.get_layout_v2_theme(ctx.guild.id, ctx.guild, ctx.author, self.bot)
            color = int(theme.get("color", 0xED4245))
            footer = theme.get("footer_text", "")

            desc = f"{EMOJI_INFO} Le salon est désormais **strictement masqué et verrouillé** pour :\n"
            desc += "\n".join([f"{EMOJI_BULLET} {m}" for m in removed_displays])
            
            view = self._build_layout_view(ctx, f"{EMOJI_LOCK} Accès Retiré", desc, color, footer)
            await ctx.send(view=view)

        except discord.Forbidden:
            log_error(f"Erreur d'élévation : Le bot manque de droits sur #{ctx.channel.name}")
            await ctx.send(f"{EMOJI_ERROR} Privilèges insuffisants pour modifier la hiérarchie de ce salon.")
        except Exception as e:
            log_error(f"Exception système critique dans 'delmembre' : {e}")
            traceback.print_exc()
            await ctx.send(f"{EMOJI_ERROR} Une erreur système est survenue lors de la fermeture du salon.")


async def setup(bot: commands.Bot):
    await bot.add_cog(ChannelAccess(bot))
    log_success("Module 'ChannelAccess' compilé et chargé dans le cycle d'exécution.")
