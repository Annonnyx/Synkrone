"""
MODULE COINFLIP VAX V3
======================
Mini-jeu interactif Pile ou Face utilisant l'architecture Layout V2, les URLs directes
de GIFs animés, le gestionnaire de thème global, des logs colorés et un respect
strict de l'affichage du GIF via une section avec miniature (thumbnail) pour garantir
le rendu animé natif et fluide dans le layout.
"""

from __future__ import annotations

import asyncio
import random
import discord
from discord import app_commands, ui
from discord.ext import commands

from utils.config_emoji import Emoji
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
        "coinflip": "\033[35m[COINFLIP]\033[0m",
    }
    prefix = colors.get(level, colors["info"])
    print(f"{prefix} [CoinFlipModule] {message}")


# ==============================================================================
# --------------------------- GESTION DES EMOJIS & URLS ------------------------
# ==============================================================================
EMOJI_TITLE = "🪙"
EMOJI_BUTTON = "🪙"
EMOJI_ERROR = Emoji.REFUSER
EMOJI_PILE = Emoji.OWNER
EMOJI_FACE = Emoji.PROFIL
EMOJI_LOAD = Emoji.LOAD

# Liste des URLs de GIFs de coinflip valides
COIN_GIF_URLS = [
    "https://media.tenor.com/bd3puNXKLwUAAAAM/coin-toss.gif",
    "https://cdn.dribbble.com/userupload/38645367/file/original-f4d7fd2ca5db3f590e952dab760ce75e.gif",
    "https://media.tenor.com/ELWc6po28wQAAAAM/coin-flip.gif"
]


# ==============================================================================
# ------------------------- VUE LAYOUT V2 DU COINFLIP --------------------------
# ==============================================================================
class CoinFlipLayoutView(ui.LayoutView):
    """Interface Layout V2 pour le jeu du Pile ou Face avec bouton en haut et affichage du GIF en dessous."""

    def __init__(self, bot: commands.Bot, guild: discord.Guild | None, author: discord.Member, result: str | None = None, gif_url: str | None = None):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild = guild
        self.author = author
        self.result = result
        self.gif_url = gif_url or random.choice(COIN_GIF_URLS)
        self.is_flipping: bool = False
        self.message: discord.Message | None = None
        self._build()

    def _get_next_gif(self) -> str:
        """Sélectionne un GIF différent de celui actuellement affiché pour garantir l'animation."""
        available = [u for u in COIN_GIF_URLS if u != self.gif_url]
        return random.choice(available) if available else random.choice(COIN_GIF_URLS)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            try:
                log_debug(f"Accès refusé au panneau pour {interaction.user} (Propriétaire : {self.author})", "warning")
                await interaction.response.send_message(
                    f"{EMOJI_ERROR} **Accès refusé.** Ce jeu appartient à {self.author.mention}.",
                    ephemeral=False
                )
            except Exception as e:
                log_debug(f"Erreur lors de l'envoi du message d'accès refusé : {e}", "error")
            return False
        return True

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

            # --- 1. BOUTON TOUT EN HAUT DANS LE LAYOUT ---
            row_top = ui.ActionRow()
            btn_flip = ui.Button(
                label="Lancement en cours..." if self.is_flipping else "Lancer la pièce",
                style=discord.ButtonStyle.primary,
                emoji=EMOJI_LOAD if self.is_flipping else EMOJI_BUTTON,
                disabled=self.is_flipping
            )
            btn_flip.callback = self.cb_flip
            row_top.add_item(btn_flip)
            container.add_item(row_top)

            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

            # --- 2. TITRE & AFFICHAGE DU RÉSULTAT ---
            container.add_item(ui.TextDisplay(f"# {EMOJI_TITLE} Pile ou face"))
            
            if self.is_flipping:
                result_text = f"### La pièce tourne... {EMOJI_LOAD}"
            elif self.result:
                chosen_emoji = EMOJI_PILE if self.result == "Pile" else EMOJI_FACE
                result_text = f"### Résultat : {chosen_emoji} `{self.result} !`"
            else:
                result_text = "### Clique sur le bouton pour lancer la pièce !"

            # --- 3. AFFICHAGE DU RÉSULTAT ET DU GIF ANIMÉ ---
            container.add_item(
                ui.Section(
                    result_text,
                    accessory=ui.Thumbnail(self.gif_url, description="Animation du lancer de pièce")
                )
            )

            if footer_text:
                container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
                container.add_item(ui.TextDisplay(footer_text))

            self.add_item(container)
            log_debug("Vue Layout V2 CoinFlip construite avec succès.", "success")
        except Exception as e:
            log_debug(f"ERREUR CRITIQUE lors de la construction de la vue _build : {e}", "error")
            import traceback
            traceback.print_exc()

    async def cb_flip(self, interaction: discord.Interaction):
        try:
            # 1. Mise à jour visuelle : État de chargement
            self.is_flipping = True
            self._build()

            if not interaction.response.is_done():
                await interaction.response.edit_message(view=self)
            else:
                await interaction.edit_original_response(view=self)

            # Simulation du lancer
            await asyncio.sleep(1.0)

            # 2. Tirage du résultat et changement garanti du GIF
            self.result = random.choice(["Pile", "Face"])
            self.gif_url = self._get_next_gif()
            self.is_flipping = False
            self._build()

            await interaction.edit_original_response(view=self)
            log_debug(f"Lancement de pièce effectué : {self.result} (GIF : {self.gif_url})", "coinflip")

        except Exception as e:
            self.is_flipping = False
            log_debug(f"Erreur lors du lancer de pièce interactif : {e}", "error")
            if not interaction.response.is_done():
                await interaction.response.send_message(f"{EMOJI_ERROR} Une erreur est survenue : {str(e)}", ephemeral=False)
            else:
                await interaction.followup.send(f"{EMOJI_ERROR} Une erreur est survenue : {str(e)}", ephemeral=False)


# ==============================================================================
# --------------------------- COG PRINCIPAL ------------------------------------
# ==============================================================================
class CoinFlip(commands.Cog):
    """Commande /coinflip — Pile ou face interactif utilisant le Layout V2."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log_debug("Cog CoinFlip initialisé avec succès.", "success")

    def cog_unload(self):
        log_debug("Cog CoinFlip déchargé.", "warning")

    @commands.hybrid_command(
        name="coinflip",
        description="🪙 Lance une pièce : pile ou face avec une interface interactive."
    )
    @app_commands.guild_only()
    async def coinflip(self, ctx: commands.Context):
        log_debug(f"Commande /coinflip invoquée par {ctx.author} ({ctx.author.id})", "info")
        try:
            result = random.choice(["Pile", "Face"])
            gif_url = random.choice(COIN_GIF_URLS)
            log_debug(f"Résultat initial généré : {result}", "coinflip")

            view = CoinFlipLayoutView(bot=self.bot, guild=ctx.guild, author=ctx.author, result=result, gif_url=gif_url)

            message = await ctx.send(view=view)
            view.message = message
            log_debug("Message CoinFlip envoyé avec succès.", "success")

        except Exception as e:
            log_debug(f"ERREUR CRITIQUE lors de l'exécution de /coinflip : {e}", "error")
            import traceback
            traceback.print_exc()
            await ctx.send(f"{EMOJI_ERROR} Une erreur est survenue lors de l'exécution de la commande.")


async def setup(bot: commands.Bot):
    await bot.add_cog(CoinFlip(bot))
    log_debug("Cog CoinFlip enregistré et chargé.", "success")