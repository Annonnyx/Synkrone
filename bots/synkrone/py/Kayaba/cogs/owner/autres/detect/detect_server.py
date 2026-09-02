import discord
from discord.ext import commands
from datetime import datetime, timezone
import traceback

# ==============================================================================
# --------------------------- CONFIGURATION ------------------------------------
# ==============================================================================

TARGET_GUILD_ID = 1368235294192570520
TARGET_CHANNEL_ID = 1495477354473066496
MENTION_ROLE_ID = 1437778159729639484

try:
    from cogs.addons.embed_type.utils import config_manager
    HAS_MANAGER = True
except ImportError:
    config_manager = None
    HAS_MANAGER = False


class TrackerStatusView(discord.ui.View):
    def __init__(self, action: str):
        super().__init__(timeout=None)
        is_join = action == 'join'
        label = "Serveur rejoint" if is_join else "Serveur quitté"
        emoji = "📥" if is_join else "📤"
        style = discord.ButtonStyle.success if is_join else discord.ButtonStyle.danger

        button = discord.ui.Button(label=label, emoji=emoji, style=style, disabled=True)
        self.add_item(button)


class DetectServer(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.join_times = {}

    async def _send_tracker_embed(self, guild: discord.Guild, action: str):
        # 1. Vérification de la Guilde Cible
        target_guild = self.bot.get_guild(TARGET_GUILD_ID)
        if not target_guild:
            try:
                target_guild = await self.bot.fetch_guild(TARGET_GUILD_ID)
            except:
                print(f"[DETECT-SERVER] Erreur : Impossible d'accéder à la guilde {TARGET_GUILD_ID}")
                return

        # 2. Vérification du Salon de Log
        log_channel = target_guild.get_channel(TARGET_CHANNEL_ID)
        if not log_channel:
            try:
                log_channel = await self.bot.fetch_channel(TARGET_CHANNEL_ID)
            except:
                print(f"[DETECT-SERVER] Erreur : Salon {TARGET_CHANNEL_ID} introuvable.")
                return

        # 3. Calcul des données
        now = datetime.now(timezone.utc)
        bot_count = sum(1 for m in guild.members if m.bot)
        human_count = (guild.member_count or 0) - bot_count
        boost_count = guild.premium_subscription_count or 0
        created_at = guild.created_at
        server_age = (now - created_at).days
        owner_name = guild.owner.display_name if guild.owner else "Inconnu"
        relative_creation = f"<t:{int(created_at.timestamp())}:R>"
        joined_at = self.join_times.get(guild.id, now)
        join_relative = f"<t:{int(joined_at.timestamp())}:R>"
        bot_word = "bot" if bot_count == 1 else "bots"
        boost_word = "boost" if boost_count == 1 else "boosts"
        time_spent_text = None
        if action == 'leave' and guild.id in self.join_times:
            delta = now - self.join_times[guild.id]
            time_spent_text = f"{delta.days}j {delta.seconds // 3600}h {(delta.seconds % 3600) // 60}m"
        # Recherche de l'inviteur si possible (nécessite permissions et audit logs)
        inviter_text = None
        if action == 'join':
            inviter_text = "?"
            try:
                if hasattr(guild, "audit_logs"):
                    async for entry in guild.audit_logs(action=discord.AuditLogAction.bot_add, limit=1):
                        if entry.target.id == self.bot.user.id:
                            inviter_text = f"{entry.user.display_name}"
                            break
            except Exception:
                inviter_text = "?"

        description = f"👑 **Le propriétaire est** `{owner_name}`.\n"
        if inviter_text is not None:
            description += f"🪪 **J'ai été invité par** `{inviter_text}`.\n"
        description += (
            f"👥 **Le serveur contient** `{human_count}` membres & `{bot_count}` {bot_word}.\n"
            f"📅 **Le serveur a été créé** {relative_creation}. **Il a** `{server_age}` jours.\n"
            f"✨ **Le serveur contient** `{boost_count}` {boost_word}."
        )

        if action == 'join':
            description += (
                f"\n\n────────────────\n"
                f"📍 **{self.bot.user.name}** est désormais sur **{len(self.bot.guilds)}** serveurs.\n"
                f"🕒 **J'ai rejoint {join_relative} le serveur.**"
            )
        elif action == 'leave':
            stay_text = time_spent_text if time_spent_text else "inconnu"
            description += (
                f"\n\n────────────────\n"
                f"📍 **{self.bot.user.name}** est désormais sur **{len(self.bot.guilds)}** serveurs.\n"
                f"🕒 **Je suis resté {stay_text} sur ce serveur.**"
            )
        else:
            description += (
                f"\n\n────────────────\n"
                f"📍 **{self.bot.user.name}** est désormais sur **{len(self.bot.guilds)}** serveurs."
            )

        # 4. Génération de l'Embed
        title = guild.name
        if HAS_MANAGER and config_manager:
            embed = config_manager.get_formatted_embed(
                guild=target_guild,
                user=self.bot.user,
                bot=self.bot,
                title=title,
                description=description,
                target_id=target_guild.id,
            )
            embed.remove_author()
        else:
            embed = discord.Embed(title=title, description=description, color=0x2ecc71 if action == 'join' else 0xe74c3c)
            footer_icon = self.bot.user.display_avatar.url if self.bot.user and self.bot.user.display_avatar else None
            embed.set_footer(text=f"Surveillance serveurs • {self.bot.user.name}", icon_url=footer_icon)

        embed.color = discord.Color.green() if action == 'join' else discord.Color.red()

        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        if guild.banner:
            embed.set_image(url=guild.banner.url)

        # 5. ENVOI RÉEL
        try:
            await log_channel.send(
                content=f"<@&{MENTION_ROLE_ID}>",
                embed=embed,
                view=TrackerStatusView(action),
            )
            print(f"[DETECT-SERVER] Log envoyé avec succès pour {guild.name} ({action})")
        except discord.Forbidden:
            print(f"[DETECT-SERVER] Erreur : Le bot n'a pas la permission d'écrire dans le salon {log_channel.name}")
        except Exception as e:
            print(f"[DETECT-SERVER] Erreur inattendue : {e}")

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        self.join_times[guild.id] = datetime.now(timezone.utc)
        await self._send_tracker_embed(guild, 'join')

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        await self._send_tracker_embed(guild, 'leave')
        self.join_times.pop(guild.id, None)

async def setup(bot: commands.Bot):
    await bot.add_cog(DetectServer(bot))