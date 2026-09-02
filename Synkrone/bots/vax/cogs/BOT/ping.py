"""
MODULE PING VAX V3
==================
Module de test de latence élégant et ultra-performant utilisant l'architecture Layout V2,
le gestionnaire de thème global, des logs colorés et un GIF animé natif intégré.
"""

from __future__ import annotations

import asyncio
import traceback
import discord
from discord import app_commands, ui
from discord.ext import commands

# Intégration de l'écosystème Vax v3
from utils.config_theme import config_manager

# ==============================================================================
# ------------------------------ DÉBOGAGE GLOBAL -------------------------------
# ==============================================================================
DEBUG_MODE = True
DEBUG_ERRORS_ONLY = True


def log_debug(message: str, level: str = "info") -> None:
    """Affiche des logs formatés dans la console selon le niveau de sévérité."""
    if DEBUG_ERRORS_ONLY and level != "error":
        return
    if not DEBUG_MODE and not DEBUG_ERRORS_ONLY:
        return

    colors = {
        "info": "\033[94m[INFO]\033[0m",
        "success": "\033[92m[SUCCÈS]\033[0m",
        "error": "\033[91m[ERREUR]\033[0m",
        "warning": "\033[93m[ATTENTION]\033[0m",
        "ping": "\033[35m[PING]\033[0m",
    }
    prefix = colors.get(level, colors["info"])
    print(f"{prefix} [PingModule] {message}")


# ==============================================================================
# --------------------------- GESTION DES EMOJIS -------------------------------
# ==============================================================================
EMOJI_TITLE = "🏓"
EMOJI_LOADING = "⌛"
EMOJI_SUCCESS = "✨"
EMOJI_ERROR = "❌"


# ==============================================================================
# ------------------------- VUE LAYOUT V2 DU PING ------------------------------
# ==============================================================================
class PingLayoutView(ui.LayoutView):
    """Interface Layout V2 haut de gamme pour l'affichage de la latence du bot."""

    def __init__(self, bot: commands.Bot, guild: discord.Guild | None, author: discord.Member, latency_ms: int | None = None):
        super().__init__(timeout=60)
        self.bot = bot
        self.guild = guild
        self.author = author
        self.latency_ms = latency_ms
        self.message: discord.Message | None = None
        self._build()

    def _build(self):
        try:
            self.clear_items()

            theme = (
                config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.author, self.bot)
                if config_manager and self.guild
                else {"color": discord.Color.blurple().value, "footer_text": ""}
            )
            accent_color = int(theme.get("color", discord.Color.blurple().value))
            footer_text = theme.get("footer_text", "")

            # Conteneur principal Layout V2
            container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)

            # Titre & État dynamique
            if self.latency_ms is not None:
                container.add_item(ui.TextDisplay(f"# {EMOJI_TITLE} Pong !"))
                description = f"Ma latence globale s'élève à **{self.latency_ms}ms** {EMOJI_SUCCESS}"
            else:
                container.add_item(ui.TextDisplay(f"# {EMOJI_TITLE} Recherche en cours..."))
                description = f"Calcul de la latence de vos services en cours... {EMOJI_LOADING}"

            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

            # Utilisation d'une Section avec Thumbnail pour intégrer le GIF unique de manière élégante et native
            container.add_item(
                ui.Section(
                    description,
                    accessory=ui.Thumbnail("https://media0.giphy.com/media/v1.Y2lkPTZjMDliOTUydTEwZ3BrdWgzZjh4bGd6cW16aWVsNzE1M3dicHN1emU4dTkxcGhxdyZlcD12MV9naWZzX3NlYXJjaCZjdD1n/ECwTCTrHPVqKI/giphy.gif", description="Animation Ping")
                )
            )

            if footer_text:
                container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
                container.add_item(ui.TextDisplay(footer_text))

            self.add_item(container)
            log_debug("Vue Layout V2 Ping construite avec succès.", "success")
        except Exception as e:
            log_debug(f"ERREUR CRITIQUE lors de la construction de la vue _build : {e}", "error")
            traceback.print_exc()


# ==============================================================================
# ----------------------------- COG PINGPONG -----------------------------------
# ==============================================================================
class Ping(commands.Cog):
    """Module avancé de test de latence utilisant l'architecture Layout V2 et l'élite du design Vax v3."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log_debug("Cog Ping initialisé avec succès.", "success")

    def cog_unload(self):
        log_debug("Cog Ping déchargé.", "warning")

    @commands.hybrid_command(
        name="ping",
        description="🏓 Affiche la latence du bot avec une interface soignée."
    )
    @app_commands.guild_only()
    async def ping(self, ctx: commands.Context):
        log_debug(f"Commande /ping invoquée par {ctx.author} ({ctx.author.id})", "info")
        try:
            # 1. Construction de la vue initiale de chargement (Layout V2)
            view = PingLayoutView(bot=self.bot, guild=ctx.guild, author=ctx.author, latency_ms=None)

            # 2. Envoi du message initial (Persistant, sans message éphémère)
            if ctx.interaction:
                await ctx.interaction.response.defer(ephemeral=False)
                msg = await ctx.interaction.followup.send(view=view, wait=True)
            else:
                msg = await ctx.send(view=view, reference=ctx.message, mention_author=True)

            view.message = msg

            # 3. Calcul de la latence réelle
            await asyncio.sleep(0.5)
            latency = round(self.bot.latency * 1000)
            log_debug(f"Latence mesurée : {latency}ms", "ping")

            # 4. Mise à jour de la vue avec la latence mesurée
            updated_view = PingLayoutView(bot=self.bot, guild=ctx.guild, author=ctx.author, latency_ms=latency)
            updated_view.message = msg

            if ctx.interaction:
                await ctx.interaction.edit_original_response(view=updated_view)
            else:
                await msg.edit(view=updated_view)

            log_debug("Message Ping mis à jour avec succès.", "success")

        except Exception as e:
            log_debug(f"ERREUR CRITIQUE lors de l'exécution de /ping : {e}", "error")
            traceback.print_exc()
            
            error_msg = f"{EMOJI_ERROR} Une erreur est survenue lors de l'exécution de la commande."
            if ctx.interaction and not ctx.interaction.response.is_done():
                await ctx.interaction.response.send_message(error_msg, ephemeral=False)
            elif ctx.interaction:
                await ctx.interaction.followup.send(error_msg, ephemeral=False)
            else:
                await ctx.send(error_msg, reference=ctx.message)


async def setup(bot: commands.Bot):
    if bot.get_command("ping"):
        bot.remove_command("ping")
    await bot.add_cog(Ping(bot))
    log_debug("Cog Ping enregistré et chargé.", "success")