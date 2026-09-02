"""
MODULE MEME - VAX V3
====================
Générateur de mèmes provenant de Reddit utilisant l'architecture Layout V2,
la commande hybride `/meme`, la configuration des thèmes (`theme`),
des retours persistants (sans messages éphémères), les variables globales de log,
les emojis centralisés et le respect strict des standards Vax v3.
"""

from __future__ import annotations

import traceback
from typing import Any, Optional

import aiohttp
import discord
from discord import app_commands, ui
from discord.ext import commands

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
    print(f"{color}[DEBUG - Meme] [{level.upper()}] {message}{reset}")


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
    return discord.Color.blurple().value, "Module Mème"


# ==============================================================================
# ------------------------- VUE LAYOUT V2 DU MÈME ------------------------------
# ==============================================================================
class MemeView(ui.LayoutView):
    def __init__(self, ctx: commands.Context, bot: commands.Bot, meme_data: dict[str, Any]):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.bot = bot
        self.meme_data = meme_data
        self._build_layout()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(f"{E.ERREUR} Ce menu ne vous appartient pas.", ephemeral=False)
            return False
        return True

    def _build_layout(self) -> None:
        try:
            self.clear_items()

            guild = self.ctx.guild
            color, footer = get_theme_values(guild, self.ctx.author, self.bot)

            container = ui.Container(accent_color=discord.Color(color), spoiler=False)

            title = f"🤣 {self.meme_data.get('title', 'Mème')}"
            subreddit = self.meme_data.get('subreddit', 'unknown')
            ups = self.meme_data.get('ups', 0)
            author = self.meme_data.get('author', 'unknown')
            image_url = self.meme_data.get('url')

            desc = f"Source : `r/{subreddit}` | 👍 {ups} | Posté par `u/{author}`"

            container.add_item(ui.TextDisplay(f"## {title}"))
            container.add_item(ui.TextDisplay(desc))

            if image_url:
                try:
                    gallery = ui.MediaGallery()
                    gallery.add_item(media=image_url, description="Mème Reddit")
                    container.add_item(gallery)
                except Exception as e:
                    debug_log(f"Erreur lors de l'ajout de la galerie média du mème : {e}", "WARNING")
                    container.add_item(ui.TextDisplay(image_url))

            if footer:
                container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
                container.add_item(ui.TextDisplay(footer))

            self.add_item(container)
        except Exception as e:
            debug_log(f"Erreur critique _build_layout MemeView: {e}", "ERROR")
            traceback.print_exc()


# ==============================================================================
# ------------------------------ COG PRINCIPAL ---------------------------------
# ==============================================================================
class Meme(commands.Cog):
    """Module dédié à la génération de mèmes via Reddit (Layout V2)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.api_url = "https://meme-api.com/gimme"
        debug_log("Cog Meme initialisé avec succès.", "SUCCESS")

    def cog_unload(self) -> None:
        debug_log("Cog Meme déchargé.", "WARNING")

    @commands.hybrid_command(
        name="meme", 
        description="Affiche un mème aléatoire provenant de Reddit."
    )
    @app_commands.describe(subreddit="Optionnel : nom d'un subreddit spécifique (ex: dankmemes)")
    async def meme(self, ctx: commands.Context, subreddit: Optional[str] = None) -> None:
        debug_log(f"Commande /meme invoquée par {ctx.author} ({ctx.author.id}) avec subreddit: {subreddit}", "INFO")
        
        target_url = f"{self.api_url}/{subreddit}" if subreddit else self.api_url

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(target_url) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Vérification si le contenu est NSFW (sécurité salon)
                        if data.get("nsfw") and ctx.guild and not ctx.channel.is_nsfw():
                            await ctx.send(f"{E.ERREUR} Le mème trouvé est classé NSFW. Veuillez utiliser cette commande dans un salon adapté.")
                            return

                        debug_log(f"Mème récupéré avec succès depuis r/{data.get('subreddit')}", "SUCCESS")

                        view = MemeView(ctx, self.bot, data)
                        if ctx.interaction:
                            await ctx.send(view=view)
                        else:
                            await ctx.reply(view=view, mention_author=False)

                    elif response.status == 404:
                        await ctx.send(f"{E.ERREUR} Le subreddit `r/{subreddit}` semble ne pas exister.")
                    else:
                        await ctx.send(f"{E.ERREUR} Impossible de récupérer un mème pour le moment.")

        except Exception as exc:
            debug_log(f"Erreur technique lors de la récupération du mème : {exc}", "ERROR")
            traceback.print_exc()
            await ctx.send(f"{E.ERREUR} Une erreur technique est survenue lors de la récupération du mème.")


async def setup(bot: commands.Bot) -> None:
    if bot.get_command("meme"):
        bot.remove_command("meme")
    await bot.add_cog(Meme(bot))
    debug_log("Cog Meme enregistré et chargé avec succès.", "SUCCESS")