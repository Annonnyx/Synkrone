"""
MODULE SLOWMODE - VAX V3
=========================
Gestionnaire du délai slowmode des salons utilisant l'architecture Layout V2,
la commande hybride `/slowmode`, la protection par permissions et configuration,
des retours persistants (sans messages éphémères), les variables globales de log,
les emojis centralisés et le respect strict des standards Vax v3.
"""

from __future__ import annotations

import math
import re
import traceback
from typing import Any, Optional

import discord
from discord import app_commands, ui
from discord.ext import commands

from utils.config_emoji import Emoji as E
from utils.config_perm import _send_permission_denied, ensure_command_permission, perm_command

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
    """Affiche des logs formatés dans la console selon le niveau de sévérité."""
    if DEBUG_ERRORS_ONLY and level.upper() != "ERROR":
        return
    if not DEBUG_MODE and not DEBUG_ERRORS_ONLY:
        return

    colors = {
        "INFO": "\033[94m",
        "SUCCESS": "\033[92m",
        "ERROR": "\033[91m",
        "WARNING": "\033[93m",
    }
    reset = "\033[0m"
    color = colors.get(level.upper(), "\033[97m")
    print(f"{color}[DEBUG - Slowmode] [{level.upper()}] {message}{reset}")


# ==============================================================================
# --------------------------- CONFIGURATION DU THÈME ---------------------------
# ==============================================================================
def get_theme_values(guild: Optional[discord.Guild], user: discord.abc.User, bot: commands.Bot) -> tuple[int, str]:
    if config_manager:
        try:
            theme = config_manager.get_layout_v2_theme(
                guild.id if guild else None,
                guild,
                user,
                bot,
            )
            return int(theme.get("color", discord.Color.blurple().value)), str(theme.get("footer_text") or "")
        except Exception as e:
            debug_log(f"Erreur get_theme_values: {e}", "ERROR")
            traceback.print_exc()
    return discord.Color.blurple().value, "Gestionnaire de Slowmode"


# ==============================================================================
# ------------------------------- UTILITAIRE TEMPS -----------------------------
# ==============================================================================
def parse_time_arg(arg: str) -> int:
    """
    Parse une chaîne de temps (ex: 10s, 2m, 1h, 0, 0s, 0m, 0h) en secondes.
    Retourne -1 si invalide.
    """
    try:
        arg = str(arg).strip().lower()
        if arg in ("0", "0s", "0m", "0h"):
            return 0
        match = re.fullmatch(r"(\d+)([smh]?)", arg)
        if not match:
            return -1
        value, unit = match.groups()
        value = int(value)
        if unit == "" or unit == "s":
            return value
        elif unit == "m":
            return value * 60
        elif unit == "h":
            return value * 3600
        return -1
    except Exception as e:
        debug_log(f"Erreur parse_time_arg: {e}", "ERROR")
        return -1


# ==============================================================================
# ---------------------------------- MODALE ------------------------------------
# ==============================================================================
class SlowmodeModal(ui.Modal, title="Modifier le slowmode"):
    temps = ui.TextInput(
        label="Nouveau délai (ex: 10s, 2m, 1h, 0)",
        placeholder="0 pour désactiver",
        required=True
    )

    def __init__(self, cog: "Slowmode", ctx: commands.Context):
        super().__init__()
        self.cog = cog
        self.ctx = ctx

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            seconds = parse_time_arg(self.temps.value)
            if seconds == -1 or seconds < 0 or seconds > 21600:
                await interaction.response.send_message(f"{E.ERREUR} Veuillez entrer un délai valide entre 0 et 6h (ex: 10s, 2m, 1h, 0).", ephemeral=False)
                return

            await interaction.channel.edit(slowmode_delay=seconds)
            
            if seconds == 0:
                title = f"{getattr(E, 'UNLOCK', 'ðŸ”“')} Slowmode Désactivé"
                desc = f"Le mode lent a été retiré de {interaction.channel.mention}."
            else:
                title = f"{getattr(E, 'TEMPS', 'â³')} Slowmode Activé"
                desc = f"Le délai entre les messages est maintenant de **{seconds} secondes** dans {interaction.channel.mention}."

            debug_log(f"Slowmode modifié à {seconds}s dans #{interaction.channel.name} par {interaction.user}", "SUCCESS")
            
            view = SlowmodeView(self.cog, self.ctx)
            view._build_layout_content(title, desc)
            await interaction.response.edit_message(view=view)

        except discord.Forbidden:
            debug_log(f"Erreur permissions insuffisantes slowmode pour {interaction.user}", "ERROR")
            await interaction.response.send_message(f"{E.ERREUR} Je n'ai pas les permissions nécessaires pour modifier ce salon.", ephemeral=False)
        except Exception as e:
            debug_log(f"Erreur SlowmodeModal: {e}", "ERROR")
            traceback.print_exc()
            await interaction.response.send_message(f"{E.ERREUR} Une erreur est survenue lors de la configuration du slowmode.", ephemeral=False)


# ==============================================================================
# ------------------------- VUE LAYOUT V2 DU SLOWMODE --------------------------
# ==============================================================================
class SlowmodeView(ui.LayoutView):
    def __init__(self, cog: "Slowmode", ctx: commands.Context, custom_title: Optional[str] = None, custom_desc: Optional[str] = None):
        super().__init__(timeout=300)
        self.cog = cog
        self.ctx = ctx
        
        delay = ctx.channel.slowmode_delay
        if custom_title and custom_desc:
            self.title = custom_title
            self.desc = custom_desc
        else:
            if delay == 0:
                self.title = f"{getattr(E, 'TEMPS', 'â³')} Slowmode Actuel"
                self.desc = f"Aucun slowmode n'est actif dans {ctx.channel.mention}."
            else:
                self.title = f"{getattr(E, 'TEMPS', 'â³')} Slowmode Actuel"
                self.desc = f"Le délai actuel entre chaque message est de **{delay} secondes** dans {ctx.channel.mention}."

        self._build_layout()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(f"{E.ERREUR} Ce menu ne vous appartient pas.", ephemeral=False)
            return False
        return True

    def _build_layout_content(self, title: str, desc: str) -> None:
        self.title = title
        self.desc = desc
        self._build_layout()

    def _build_layout(self) -> None:
        try:
            self.clear_items()

            guild = self.ctx.guild
            color, footer = get_theme_values(guild, self.ctx.author, self.cog.bot)

            container = ui.Container(accent_color=discord.Color(color), spoiler=False)

            container.add_item(ui.TextDisplay(f"## {self.title}"))
            container.add_item(ui.TextDisplay(self.desc))
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

            action_row = ui.ActionRow()
            modify_btn = ui.Button(label="Modifier le slowmode", style=discord.ButtonStyle.primary, emoji=getattr(E, 'MODIFIER', 'âš™ï¸'))

            async def modify_callback(interaction: discord.Interaction) -> None:
                try:
                    if not interaction.user.guild_permissions.manage_channels:
                        await interaction.response.send_message(f"{E.ERREUR} Vous n'avez pas la permission `Gérer les salons`.", ephemeral=False)
                        return
                    await interaction.response.send_modal(SlowmodeModal(self.cog, self.ctx))
                except Exception as e:
                    debug_log(f"Erreur modify_callback: {e}", "ERROR")
                    traceback.print_exc()

            modify_btn.callback = modify_callback
            action_row.add_item(modify_btn)
            container.add_item(action_row)

            if footer:
                container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
                container.add_item(ui.TextDisplay(footer))

            self.add_item(container)
        except Exception as e:
            debug_log(f"Erreur critique _build_layout SlowmodeView: {e}", "ERROR")
            traceback.print_exc()

    async def refresh(self, interaction: discord.Interaction) -> None:
        try:
            self._build_layout()
            if interaction.response.is_done():
                await interaction.edit_original_response(view=self)
            else:
                await interaction.response.edit_message(view=self)
        except Exception as e:
            debug_log(f"Erreur refresh SlowmodeView: {e}", "ERROR")
            traceback.print_exc()


# ==============================================================================
# ------------------------------ COG PRINCIPAL ---------------------------------
# ==============================================================================
class Slowmode(commands.Cog):
    """â³ Module Slowmode â€” Gestion ergonomique des délais de salon (Layout V2)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        debug_log("Cog Slowmode initialisé avec succès.", "SUCCESS")

    def cog_unload(self) -> None:
        debug_log("Cog Slowmode déchargé.", "WARNING")

    @perm_command(level=3)
    @commands.command(
        name="slowmode",
        description="Affiche ou modifie le délai de slowmode du salon."
    )
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx: commands.Context, temps: Optional[str] = None) -> None:
        """
        Affiche ou modifie le slowmode du salon.
        - Sans argument : affiche l'état actuel + panneau interactif.
        - Avec argument : modifie directement (ex: /slowmode 10s, /slowmode 2m, /slowmode 1h, /slowmode 0)
        """
        debug_log(f"Commande /slowmode invoquée par {ctx.author} ({ctx.author.id}) avec args: {temps}", "INFO")

        if not ctx.guild:
            await ctx.send(f"{E.ERREUR} Cette commande ne peut être exécutée que dans un serveur.")
            return

        # Utilisation de ensure_command_permission avec cleanup_on_denied=True et gestion correcte du fallback
        if not await ensure_command_permission(ctx, command_name="slowmode", cleanup_on_denied=True):
            return

        try:
            if temps is None:
                view = SlowmodeView(self, ctx)
                if ctx.interaction:
                    await ctx.send(view=view, ephemeral=False)
                else:
                    await ctx.reply(view=view, mention_author=False)
                return

            seconds = parse_time_arg(temps)
            if seconds == -1 or seconds < 0 or seconds > 21600:
                await ctx.send(f"{E.ERREUR} Veuillez entrer un délai valide entre 0 et 6h (ex: 10s, 2m, 1h, 0).")
                return

            await ctx.channel.edit(slowmode_delay=seconds)

            if seconds == 0:
                title = "ðŸ”“ Slowmode Désactivé"
                description = f"Le mode lent a été retiré de {ctx.channel.mention}."
            else:
                title = "â³ Slowmode Activé"
                description = f"Le délai entre les messages est maintenant de **{seconds} secondes** dans {ctx.channel.mention}."

            debug_log(f"Slowmode appliqué ({seconds}s) dans #{ctx.channel.name} par {ctx.author}", "SUCCESS")

            view = SlowmodeView(self, ctx, custom_title=title, custom_desc=description)
            if ctx.interaction:
                await ctx.send(view=view, ephemeral=False)
            else:
                await ctx.reply(view=view, mention_author=False)

        except discord.Forbidden:
            debug_log(f"Erreur permissions insuffisantes slowmode pour {ctx.author}", "ERROR")
            await ctx.send(f"{E.ERREUR} Je n'ai pas les permissions nécessaires pour modifier ce salon.")
        except Exception as exc:
            debug_log(f"Erreur lors de l'exécution de la commande /slowmode : {exc}", "ERROR")
            traceback.print_exc()
            await ctx.send(f"{E.ERREUR} Une erreur est survenue lors de la configuration du slowmode.")

    @slowmode.error
    async def slowmode_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        debug_log(f"Erreur de commande slowmode : {error}", "ERROR")
        if isinstance(error, commands.MissingPermissions):
            await _send_permission_denied(ctx)
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"{E.ERREUR} Veuillez entrer un délai valide (ex: 10s, 2m, 1h, 0).")


async def setup(bot: commands.Bot) -> None:
    if bot.get_command("slowmode"):
        bot.remove_command("slowmode")
    await bot.add_cog(Slowmode(bot))
    debug_log("Cog Slowmode enregistré et chargé avec succès.", "SUCCESS")
