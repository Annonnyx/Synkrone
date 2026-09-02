"""
MODULE KICK - VAX V3
=====================
Gestionnaire d'expulsion des membres utilisant l'architecture Layout V2,
la commande hybride `/kick`, la protection par permissions et configuration (`perm` et `theme`),
des retours persistants (sans messages éphémères), les variables globales de log,
les emojis centralisés et le respect strict des standards Vax v3.
"""

from __future__ import annotations

import datetime
import traceback
from typing import Any, Optional

import discord
from discord import app_commands, ui
from discord.ext import commands

from utils.config_emoji import Emoji as E
from utils.config_perm import ensure_command_permission, perm_command

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
    print(f"{color}[DEBUG - Kick] [{level.upper()}] {message}{reset}")


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
    return discord.Color.blurple().value, "Module Kick"


# ==============================================================================
# ------------------------- VUE LAYOUT V2 DU RÉSULTAT KICK ---------------------
# ==============================================================================
class KickResultView(ui.LayoutView):
    def __init__(self, ctx: commands.Context, bot: commands.Bot, title: str, description: str, thumbnail_url: Optional[str] = None):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.bot = bot
        self.title = title
        self.description = description
        self.thumbnail_url = thumbnail_url
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

            text_content = f"## {self.title}\n{self.description}"

            if self.thumbnail_url:
                try:
                    container.add_item(
                        ui.Section(
                            text_content,
                            accessory=ui.Thumbnail(self.thumbnail_url, description="Avatar du membre expulsé"),
                        )
                    )
                except Exception:
                    container.add_item(ui.TextDisplay(text_content))
            else:
                container.add_item(ui.TextDisplay(text_content))

            if footer:
                container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
                container.add_item(ui.TextDisplay(footer))

            self.add_item(container)
        except Exception as e:
            debug_log(f"Erreur critique _build_layout KickResultView: {e}", "ERROR")
            traceback.print_exc()


# ==============================================================================
# ------------------------------ COG PRINCIPAL ---------------------------------
# ==============================================================================
class Kick(commands.Cog):
    """ðŸ‘ž Module Kick â€” Expulsion ergonomique des membres (Layout V2)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        debug_log("Cog Kick initialisé avec succès.", "SUCCESS")

    def cog_unload(self) -> None:
        debug_log("Cog Kick déchargé.", "WARNING")

    @perm_command(level=2)
    @commands.command(
        name="kick",
        description="Expulse un membre du serveur (mention, ID ou pseudo)."
    )
    @commands.has_permissions(kick_members=True)
    @app_commands.describe(membre="Le membre à expulser (mention, ID ou pseudo)", reason="Raison de l'expulsion")
    async def kick(self, ctx: commands.Context, membre: str, *, reason: str = "Aucune raison fournie") -> None:
        debug_log(f"Commande /kick invoquée par {ctx.author} ({ctx.author.id}) pour cibler: {membre}", "INFO")

        if not ctx.guild:
            await ctx.send(f"{E.ERREUR} Cette commande ne peut être exécutée que dans un serveur.")
            return

        if not await ensure_command_permission(ctx, command_name="kick"):
            return

        member = None
        # 1. Recherche par mention
        if membre.startswith("<@") and membre.endswith(">"):
            membre_id = membre.replace("<@!", "").replace("<@", "").replace(">", "")
            if membre_id.isdigit():
                member = ctx.guild.get_member(int(membre_id))
        # 2. Recherche par ID
        elif membre.isdigit():
            member = ctx.guild.get_member(int(membre))
        # 3. Recherche par nom
        if member is None:
            member = discord.utils.find(lambda m: m.name == membre or m.display_name == membre, ctx.guild.members)

        if member is None:
            await ctx.send(f"{E.ERREUR} Utilisateur introuvable sur ce serveur.")
            return

        # Empêcher de s'expulser soi-même
        if member.id == ctx.author.id:
            await ctx.send(f"{E.ERREUR} Tu ne peux pas t'expulser toi-même.")
            return

        # Empêcher d'expulser le bot
        if member.id == self.bot.user.id:
            await ctx.send(f"{E.ERREUR} Je ne peux pas m'auto-expulser. Sympa l'ambiance !")
            return

        # Vérification de la hiérarchie des rôles
        if member.top_role >= ctx.author.top_role and ctx.guild.owner_id != ctx.author.id:
            await ctx.send(f"{E.ERREUR} Tu ne peux pas expulser ce membre car il a un rôle supérieur ou égal au tien.")
            return

        if member.top_role >= ctx.guild.me.top_role:
            await ctx.send(f"{E.ERREUR} Je ne peux pas expulser ce membre : mon rôle est trop bas dans la hiérarchie.")
            return

        try:
            # Notification MP (optionnelle)
            try:
                dm_title = f"ðŸ‘ž Expulsion de {ctx.guild.name}"
                dm_desc = f"Tu as été expulsé du serveur **{ctx.guild.name}**.\n**Raison :** {reason}"
                
                if config_manager:
                    dm_embed = config_manager.get_formatted_embed(
                        guild=ctx.guild,
                        user=member,
                        bot=self.bot,
                        title=dm_title,
                        description=dm_desc,
                        target_id=ctx.guild.id
                    )
                else:
                    dm_embed = discord.Embed(title=dm_title, description=dm_desc, color=0xff0000, timestamp=datetime.datetime.now(datetime.timezone.utc))
                
                await member.send(embed=dm_embed)
            except (discord.Forbidden, discord.HTTPException):
                pass

            # Récupération de l'avatar pour le thumbnail avant l'expulsion
            member_avatar_url = member.display_avatar.url

            # Action d'expulsion
            await member.kick(reason=f"Par: {ctx.author} | Raison: {reason}")
            debug_log(f"Membre {member} ({member.id}) expulsé par {ctx.author}", "SUCCESS")

            # Réponse persistante via Layout V2 au format exact demandé
            success_title = f"{member.name} est expulsé"
            success_desc = (
                f"-# `{member.id}`\n\n"
                f"**Membre :** `{member.name}`\n"
                f"Exclu par {ctx.author.mention}\n"
                f"**Raison :** `{reason}`"
            )
            
            view = KickResultView(ctx, self.bot, success_title, success_desc, thumbnail_url=member_avatar_url)
            if ctx.interaction:
                await ctx.send(view=view)
            else:
                await ctx.reply(view=view, mention_author=False)

        except Exception as exc:
            debug_log(f"Erreur critique lors de l'expulsion : {exc}", "ERROR")
            traceback.print_exc()
            await ctx.send(f"{E.ERREUR} Une erreur critique est survenue lors de l'expulsion.")

    @kick.error
    async def kick_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        debug_log(f"Erreur de commande kick : {error}", "ERROR")
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(f"{E.ERREUR} Tu n'as pas la permission `Expulser des membres`.")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send(f"{E.ERREUR} Utilisateur introuvable sur ce serveur.")
        else:
            await ctx.send(f"{E.ERREUR} Une erreur est survenue : {str(error)}")


async def setup(bot: commands.Bot) -> None:
    if bot.get_command("kick"):
        bot.remove_command("kick")
    await bot.add_cog(Kick(bot))
    debug_log("Cog Kick enregistré et chargé avec succès.", "SUCCESS")
