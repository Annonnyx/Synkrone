# ==============================================================================
# ------------------------------ DÉBOGAGE GLOBAL -------------------------------
# ==============================================================================
DEBUG_MODE = True
DEBUG_ERRORS_ONLY = True


def log_debug(message: str, level: str = "info") -> None:
    """Affiche des logs formatés dans la console selon les directives Vax v3."""
    if not DEBUG_MODE:
        return
    if DEBUG_ERRORS_ONLY and level != "error":
        return

    colors = {
        "info": "\033[94m[INFO]\033[0m",
        "success": "\033[92m[SUCCÈS]\033[0m",
        "error": "\033[91m[ERREUR]\033[0m",
        "warning": "\033[93m[ATTENTION]\033[0m",
    }
    prefix = colors.get(level, colors["info"])
    print(f"{prefix} [SayModule] {message}")


# ==============================================================================
# ------------------------- CENTRALISATION DES EMOJIS --------------------------
# ==============================================================================
from utils.config_emoji import Emoji as E

EMOJI_SUCCESS = getattr(E, "VALIDE", "✅")
EMOJI_ERROR = getattr(E, "ERREUR", "❌")
EMOJI_SAY = getattr(E, "ANNONCE", "📢")


# ==============================================================================
# --------------------------- IMPORTATION UTILS --------------------------------
# ==============================================================================
try:
    from utils.config_perm import ensure_command_permission, perm_command
    log_debug("Module config_perm importé avec succès.", "success")
except ImportError as e:
    log_debug(f"Erreur d'importation de config_perm : {e}", "error")
    ensure_command_permission = None
    perm_command = None

try:
    from utils.config_balise import apply_balises
    log_debug("Module config_balise importé avec succès.", "success")
except ImportError as e:
    log_debug(f"Erreur d'importation de config_balise : {e}", "error")
    apply_balises = None

import discord
from discord.ext import commands


# ==============================================================================
# --------------------------- COG PRINCIPAL SAY --------------------------------
# ==============================================================================
class Say(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        log_debug("Cog Say initialisé avec succès.", "success")

    @perm_command(level=2) if perm_command else lambda x: x
    @commands.command(
        name="say",
        description="Fait parler le bot avec support des balises"
    )
    async def say(self, ctx: commands.Context, *, message: str = None):
        if ctx.guild and ensure_command_permission:
            if not await ensure_command_permission(ctx, command_name="say"):
                log_debug(f"Accès refusé à la commande say pour {ctx.author}", "warning")
                return

        if not message:
            log_debug("Tentative d'utilisation de say sans message.", "warning")
            await ctx.send(f"{EMOJI_ERROR} Utilisation : `!say <message>`")
            return

        # Application des balises dynamiques si le module est disponible
        processed_message = message
        if apply_balises and ctx.guild:
            try:
                processed_message = apply_balises(
                    message,
                    ctx.guild,
                    ctx.author,
                    self.bot,
                    prefix=ctx.prefix or "!"
                )
            except Exception as e:
                log_debug(f"Erreur lors de l'application des balises : {e}", "error")

        # Suppression du message original de l'utilisateur
        try:
            await ctx.message.delete()
            log_debug("Message d'invocation supprimé avec succès.", "info")
        except discord.HTTPException as e:
            log_debug(f"Impossible de supprimer le message d'invocation : {e}", "error")

        # Envoi du message persistant et visible dans le salon
        await ctx.send(processed_message)
        log_debug(f"Message transmis et publié par le bot dans le salon #{ctx.channel.name}", "success")


async def setup(bot):
    await bot.add_cog(Say(bot))
    log_debug("Cog Say enregistré et chargé.", "success")