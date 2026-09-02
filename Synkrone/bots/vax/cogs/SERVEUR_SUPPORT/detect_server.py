import discord
from discord import ui
from discord.ext import commands
from datetime import datetime, timezone

from utils.config_emoji import Emoji as E

# ==============================================================================
# --------------------------- CONFIGURATION ------------------------------------
# ==============================================================================

# Variables globales de gestion des logs et du débogage
ENABLE_DEBUG_LOGS = True
ENABLE_ERROR_LOGS = True

# Centralisation globale des emojis du système (Standards Vax v3)
class TrackerEmojis:
    JOIN = "📥"
    LEAVE = "📤"
    OWNER = getattr(E, "OWNER", "👑")
    INVITER = "🪪"
    MEMBERS = "👥"
    CALENDAR = "📅"
    BOOST = getattr(E, "EXCELLENT", "✨")
    PIN = "📍"
    TIME = getattr(E, "HORLOGE", "🕒")
    PING = getattr(E, "CLOCHE", "🔔")
    SUCCESS = getattr(E, "VALIDE", "✅")
    ERROR = getattr(E, "ERREUR", "❌")

# Codes de formatage ANSI pour la coloration des terminaux
class LogColors:
    OK = "\033[92m"
    INFO = "\033[94m"
    ERR = "\033[91m"
    RESET = "\033[0m"

TARGET_GUILD_ID = 1368235294192570520
TARGET_CHANNEL_ID = 1437777847941988463
MENTION_ROLE_ID = 1437778159729639484

try:
    from utils.config_theme import config_manager
    HAS_MANAGER = True
except ImportError:
    config_manager = None
    HAS_MANAGER = False

# ==============================================================================
# ----------------------------- COMPOSANTS -------------------------------------
# ==============================================================================

class DetectServer(commands.Cog):
    """Cog de détection de serveur basé sur une UI Layout V2 native et moderne."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.join_times = {}

    def _resolve_bot_joined_at(self, guild: discord.Guild):
        member = guild.get_member(self.bot.user.id) if self.bot.user else None
        if member and member.joined_at:
            return member.joined_at
        return self.join_times.get(guild.id)

    def _debug(self, message: str):
        if ENABLE_DEBUG_LOGS:
            print(f"{LogColors.INFO}[DETECT-SERVER] {message}{LogColors.RESET}")

    def _success(self, message: str):
        if ENABLE_DEBUG_LOGS:
            print(f"{LogColors.OK}[DETECT-SERVER] {message}{LogColors.RESET}")

    def _error(self, message: str):
        if ENABLE_ERROR_LOGS:
            print(f"{LogColors.ERR}[DETECT-SERVER] {message}{LogColors.RESET}")

    async def _send_tracker_layout(self, guild: discord.Guild, action: str, dest_channel: discord.abc.Messageable = None):
        self._debug(f"Génération du layout pour {guild.name} ({action})...")
        is_join = (action == 'join')

        # 1. Résolution de la destination (Salon de log par défaut ou salon de test)
        target_channel = dest_channel
        if not target_channel:
            target_guild = self.bot.get_guild(TARGET_GUILD_ID)
            if not target_guild:
                try:
                    target_guild = await self.bot.fetch_guild(TARGET_GUILD_ID)
                except Exception as e:
                    self._error(f"Impossible d'accéder à la guilde cible ({TARGET_GUILD_ID}) : {e}")
                    return

            target_channel = target_guild.get_channel(TARGET_CHANNEL_ID)
            if not target_channel:
                try:
                    target_channel = await self.bot.fetch_channel(TARGET_CHANNEL_ID)
                except Exception as e:
                    self._error(f"Salon de log ({TARGET_CHANNEL_ID}) introuvable : {e}")
                    return

        # 2. Collecte des métriques et informations du serveur
        now = datetime.now(timezone.utc)
        bot_count = sum(1 for m in guild.members if m.bot)
        human_count = (guild.member_count or 0) - bot_count
        boost_count = guild.premium_subscription_count or 0
        created_at = guild.created_at
        server_age = (now - created_at).days
        owner_name = guild.owner.display_name if guild.owner else "Inconnu"
        relative_creation = f"<t:{int(created_at.timestamp())}:R>"
        joined_at = self._resolve_bot_joined_at(guild) or now
        join_relative = f"<t:{int(joined_at.timestamp())}:R>"

        bot_word = "bot" if bot_count == 1 else "bots"
        boost_word = "boost" if boost_count == 1 else "boosts"

        time_spent_text = None
        if not is_join and joined_at:
            delta = now - joined_at
            time_spent_text = f"{delta.days}j {delta.seconds // 3600}h {(delta.seconds % 3600) // 60}m"

        inviter_text = None
        if is_join:
            inviter_text = "?"
            try:
                if hasattr(guild, "audit_logs"):
                    async for entry in guild.audit_logs(action=discord.AuditLogAction.bot_add, limit=1):
                        if entry.target.id == self.bot.user.id:
                            inviter_text = f"{entry.user.display_name}"
                            break
            except Exception:
                inviter_text = "?"

        # 3. Construction des blocs de texte pur (formaté proprement sans séparateurs archaïques)
        desc_lines = [f"{TrackerEmojis.OWNER} **Propriétaire :** `{owner_name}`"]
        if inviter_text is not None:
            desc_lines.append(f"{TrackerEmojis.INVITER} **Invité par :** `{inviter_text}`")

        desc_lines.extend([
            f"{TrackerEmojis.MEMBERS} **Membres :** `{human_count}` humains, `{bot_count}` {bot_word}",
            f"{TrackerEmojis.CALENDAR} **Création :** {relative_creation} (`{server_age}` jours)",
            f"{TrackerEmojis.BOOST} **Boosts :** `{boost_count}` {boost_word}",
            ""
        ])

        if is_join:
            desc_lines.extend([
                f"{TrackerEmojis.PIN} **{self.bot.user.name}** est sur **{len(self.bot.guilds)}** serveurs.",
                f"{TrackerEmojis.TIME} **Rejoint :** {join_relative}"
            ])
        else:
            stay_text = time_spent_text if time_spent_text else "inconnu"
            desc_lines.extend([
                f"{TrackerEmojis.PIN} **{self.bot.user.name}** est sur **{len(self.bot.guilds)}** serveurs.",
                f"{TrackerEmojis.TIME} **Présence :** {stay_text}"
            ])

        content_text = "\n".join(desc_lines)

        # 4. Résolution dynamique du thème via config_theme
        accent_color = 0x2ecc71 if is_join else 0xe74c3c
        footer_text = ""
        if HAS_MANAGER and config_manager:
            try:
                theme = config_manager.get_layout_v2_theme(guild.id, guild, self.bot.user, self.bot)
                if theme.get("color"):
                    accent_color = int(theme["color"])
                if theme.get("footer_text"):
                    footer_text = theme["footer_text"]
            except Exception as e:
                self._error(f"Impossible de résoudre le thème : {e}")

        # 5. Architecture du Layout V2
        view = ui.LayoutView(timeout=None)
        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)

        # 5.1 En-tête : Bouton d'état (Rejoint / Quitté) tout en haut
        status_row = ui.ActionRow()
        btn_label = "Serveur rejoint" if is_join else "Serveur quitté"
        btn_emoji = TrackerEmojis.JOIN if is_join else TrackerEmojis.LEAVE
        btn_style = discord.ButtonStyle.success if is_join else discord.ButtonStyle.danger
        status_button = ui.Button(label=btn_label, emoji=btn_emoji, style=btn_style, disabled=True)
        status_row.add_item(status_button)
        container.add_item(status_row)

        # 5.2 Titre & Informations avec icône (Thumbnail) si présente
        title_emoji = TrackerEmojis.JOIN if is_join else TrackerEmojis.LEAVE
        section_content = f"# {title_emoji} {guild.name}\n\n{content_text}"

        if guild.icon:
            container.add_item(
                ui.Section(
                    section_content,
                    accessory=ui.Thumbnail(guild.icon.url, description=f"Icône de {guild.name}")
                )
            )
        else:
            container.add_item(ui.TextDisplay(section_content))

        # 5.3 Média : Bannière (Affichée uniquement si le serveur en possède une, zéro substitution blanche)
        if guild.banner:
            try:
                gallery = ui.MediaGallery()
                gallery.add_item(media=guild.banner.url, description="Bannière du serveur")
                container.add_item(gallery)
            except Exception as e:
                self._error(f"Échec de l'intégration de la bannière : {e}")

        # 5.4 Notification de Ping intégrée élégamment dans le layout
        ping_text = f"**Alerte système {TrackerEmojis.PING} :** <@&{MENTION_ROLE_ID}>"
        container.add_item(ui.TextDisplay(ping_text))

        # 5.5 Footer dynamique s'il est configuré
        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        view.add_item(container)

        # 6. Déploiement du message persistant
        try:
            await target_channel.send(view=view)
            self._success(f"Log V2 déployé avec succès pour {guild.name} ({action})")
        except discord.Forbidden:
            self._error(f"Droits insuffisants pour écrire dans le salon {target_channel}.")
        except Exception as e:
            self._error(f"Anomalie inattendue lors de l'envoi : {e}")

    # ==============================================================================
    # ----------------------------- EVENTS & COMMANDES -----------------------------
    # ==============================================================================

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        self.join_times[guild.id] = datetime.now(timezone.utc)
        await self._send_tracker_layout(guild, 'join')

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        await self._send_tracker_layout(guild, 'leave')
        self.join_times.pop(guild.id, None)


async def setup(bot: commands.Bot):
    await bot.add_cog(DetectServer(bot))