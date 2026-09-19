import discord
from discord import app_commands, ui
from typing import Optional, Dict, Any, List, Union, Tuple
from datetime import datetime, timedelta, timezone
import psutil
import platform
from pathlib import Path
import sqlite3
import aiosqlite

# Constantes
# Configuration du fuseau horaire avec fallback
try:
    from zoneinfo import ZoneInfo
    FRENCH_TIMEZONE = ZoneInfo('Europe/Berlin')
except ImportError:
    # Fallback si zoneinfo n'est pas disponible
    FRENCH_TIMEZONE = timezone.utc
    print("[WARNING] zoneinfo non disponible, utilisation de UTC")
except Exception:
    # Fallback si le fuseau horaire n'est pas trouvé
    FRENCH_TIMEZONE = timezone.utc
DEFAULT_COLOR = 0x3F6B52  # mousse (DA Synkrone)
DEV_STATS_DB_PATH = Path(__file__).parent / "../../../owner/commands/devmenu/dev_stats.db"
DEFAULT_SYNKRONE_URL = "https://synkrone.app/#asuna"

class EmbedManager:
    def _get_default_vote_url(self) -> str:
        if hasattr(self.bot, 'user') and getattr(self.bot.user, 'id', None):
            return f"https://top.gg/bot/{self.bot.user.id}/vote"
        return ""
    def _get_year_commands_count(self) -> int:
        """Retourne le nombre de commandes utilisées cette année (UTC)"""
        try:
            from datetime import datetime
            db_path = Path(__file__).parent / "../../../owner/commands/devmenu/dev_stats.db"
            db_path = db_path.resolve()
            if not db_path.exists():
                return 0
            now = datetime.utcnow()
            year_start = datetime(now.year, 1, 1)
            ts_year = int(year_start.timestamp())
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM command_usage_log WHERE timestamp >= ?", (ts_year,))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result and result[0] is not None else 0
        except Exception:
            return 0

    def _get_week_commands_count(self) -> int:
        """Retourne le nombre de commandes utilisées cette semaine (lundi-dimanche, UTC)"""
        try:
            from datetime import datetime, timedelta
            db_path = Path(__file__).parent / "../../../owner/commands/devmenu/dev_stats.db"
            db_path = db_path.resolve()
            if not db_path.exists():
                return 0
            now = datetime.utcnow()
            today = datetime(now.year, now.month, now.day)
            week_start = today - timedelta(days=today.isoweekday() - 1)
            ts_week = int(week_start.timestamp())
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM command_usage_log WHERE timestamp >= ?", (ts_week,))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result and result[0] is not None else 0
        except Exception:
            return 0

    def _get_today_commands_count(self) -> int:
        """Retourne le nombre de commandes utilisées aujourd'hui (UTC)"""
        try:
            from datetime import datetime
            db_path = Path(__file__).parent / "../../../owner/commands/devmenu/dev_stats.db"
            db_path = db_path.resolve()
            if not db_path.exists():
                return 0
            now = datetime.utcnow()
            today = datetime(now.year, now.month, now.day)
            ts_today = int(today.timestamp())
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM command_usage_log WHERE timestamp >= ?", (ts_today,))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result and result[0] is not None else 0
        except Exception:
            return 0

    def _get_month_commands_count(self) -> int:
        """Retourne le nombre de commandes utilisées ce mois-ci (slash+prefix, toutes guilds confondues)"""
        try:
            from datetime import datetime
            db_path = Path(__file__).parent / "../../../owner/commands/devmenu/dev_stats.db"
            db_path = db_path.resolve()
            if not db_path.exists():
                return 0
            now = datetime.utcnow()
            month_start = datetime(now.year, now.month, 1)
            ts_month = int(month_start.timestamp())
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM command_usage_log WHERE timestamp >= ?", (ts_month,))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result and result[0] is not None else 0
        except Exception:
            return 0
    """Gestionnaire centralisé pour la création et la gestion des embeds"""
    
    def __init__(self, bot):
        self.bot = bot
        self._cached_embeds: Dict[str, discord.Embed] = {}
        
    @classmethod
    async def create(cls, bot):
        """Méthode de création asynchrone"""
        instance = cls(bot)
        await instance.initialize()
        return instance
        
    async def initialize(self):
        """Initialisation asynchrone"""
        # Initialisation asynchrone si nécessaire
        pass
        
    async def _get_bot_stats(self):
        """Récupère les statistiques du bot depuis dev_stats.db (placeholder, non utilisé)"""
        # Cette méthode n'est plus utilisée, mais conservée pour compatibilité
        return {
            'last_restart': None,
            'unique_users': 0,
            'unique_owners': 0,
            'command_count': 0,
            'last_command': None
        }

    async def get_bot_profile_embed(self, guild: Optional[discord.Guild] = None) -> Tuple[discord.Embed, Optional[discord.File], discord.ui.View]:
        """Crée l'embed de profil du bot avec la vue des boutons et la bannière officielle Discord."""
        bot_user = self.bot.user
        guilds_count = len(self.bot.guilds)
        users_count = await self._compute_unique_member_count()
        ping = round(self.bot.latency * 1000)

        if not hasattr(self.bot, 'start_time'):
            self.bot.start_time = datetime.now(FRENCH_TIMEZONE)

        # Récupération des statistiques
        stats = await self._get_bot_stats()

        # Calcul correct des propriétaires uniques
        unique_owners = self._compute_unique_owners_count()

        # Récupérer le nombre total de commandes
        total_commands = self._get_total_commands_count()

        # Vérification de l'existence du gestionnaire d'embed personnalisé
        try:
            from cogs.addons.embed_type.utils import config_manager
            HAS_CUSTOM_EMBED = True
        except ImportError:
            try:
                from .utils import config_manager
                HAS_CUSTOM_EMBED = True
            except ImportError:
                config_manager = None
                HAS_CUSTOM_EMBED = False

        # Création de l'embed avec ou sans gestionnaire personnalisé
        if config_manager:
            embed = config_manager.get_formatted_embed(
                guild=guild,
                user=self.bot.user,
                bot=self.bot,
                target_id=guild.id if guild else None
            )
        else:
            embed = discord.Embed(
                color=DEFAULT_COLOR,
                timestamp=datetime.now(FRENCH_TIMEZONE)
            )

        # Auteur avec l'avatar du bot
        if hasattr(bot_user, 'display_avatar') and bot_user.display_avatar:
            avatar_url = bot_user.display_avatar.url
            embed.set_author(
                name=f"Profil de {bot_user.name}",
                icon_url=avatar_url
            )
            embed.set_thumbnail(url=avatar_url)
        else:
            avatar_url = None
            embed.set_author(name=f"Profil de {bot_user.name}")
        # Standard Synkrone : footer + timestamp si le gestionnaire custom n'en a pas mis
        try:
            if not embed.footer or not embed.footer.text:
                embed.set_footer(
                    text=f"{bot_user.name} • synkrone.app • /help",
                    icon_url=avatar_url,
                )
        except Exception:
            pass
        try:
            if not embed.timestamp:
                embed.timestamp = datetime.now(FRENCH_TIMEZONE)
        except Exception:
            pass
        try:
            if not getattr(embed, 'url', None):
                embed.url = 'https://synkrone.app/discord/bots'
        except Exception:
            pass

        # Description avec les informations
        last_restart = discord.utils.format_dt(self.bot.start_time, style="R")

        global_prefix = self._get_global_prefix(guild)
        embed.description = (
            f"\n"
            f"🔄 **Dernier redémarrage** : {last_restart}\n"
            f"⚡ **Latence** : `{ping}ms`\n"
            + (f"🔤 **Préfixe** : `{global_prefix}`\n" if global_prefix else "")
            + "\n"
        )

        # Section Statistiques dans un bloc de code
        month_commands = self._get_month_commands_count()
        week_commands = self._get_week_commands_count()
        today_commands = self._get_today_commands_count()
        year_commands = self._get_year_commands_count()
        stats_text = (
            f"👥 Membres uniques : {self._format_number_french(users_count)}\n"
            f"🌍 Serveurs : {self._format_number_french(guilds_count)}\n"
            f"👑 Propriétaires uniques : {self._format_number_french(unique_owners)}\n\n"
            f"⚡ Commandes utilisées : {self._format_number_french(total_commands)}\n"
            f"  - 📆 Cette année : {self._format_number_french(year_commands)}\n"
            f"  - 📅 Ce mois-ci : {self._format_number_french(month_commands)}\n"
            f"  - 🗓️ Cette semaine : {self._format_number_french(week_commands)}\n"
            f"  - 📆 Aujourd'hui : {self._format_number_french(today_commands)}"
        )

        embed.add_field(
            name="📊 Statistiques",
            value=f"```\n{stats_text}\n```",
            inline=False
        )

        # Field préfixes configurés pour ce serveur
        if guild:
            server_prefixes = self._get_server_prefixes(guild.id)
            if server_prefixes:
                prefixes_str = " ".join(f"`{p}`" for p in server_prefixes)
                # Ajoute le champ juste avant les stats
                embed.insert_field_at(
                    0 if global_prefix else 0,
                    name="🔤 Préfixes configurés",
                    value=prefixes_str,
                    inline=False
                )

        # Nouvelle gestion de la bannière officielle Discord
        file = None
        try:
            # On récupère les infos fraîches du bot depuis l'API
            fresh_bot_user = await self.bot.fetch_user(self.bot.user.id)
            if hasattr(fresh_bot_user, "banner") and fresh_bot_user.banner:
                embed.set_image(url=fresh_bot_user.banner.url)
        except Exception as e:
            print(f"[BANNIERE] Impossible de récupérer la bannière officielle : {e}")

        # Création de la vue avec les boutons
        bot_id = str(self.bot.user.id) if hasattr(self.bot, 'user') and hasattr(self.bot.user, 'id') else 'YOUR_BOT_ID'
        invite_url = f"https://discord.com/oauth2/authorize?client_id={bot_id}"

        # Lien d'invitation direct vers le serveur de support
        support_url = "https://discord.gg/p768u2Pgp3"

        vote_url = self.bot.vote_url if getattr(self.bot, 'vote_url', None) else self._get_default_vote_url()
        view = ProfileButtons(
            bot=self.bot,
            invite_url=invite_url,
            vote_url=vote_url,
            synkrone_url=getattr(self.bot, 'synkrone_url', DEFAULT_SYNKRONE_URL),
            support_url=support_url
        )

        return embed, file, view

    async def get_stats_embed(self, guild: discord.Guild) -> Tuple[discord.Embed, Optional[discord.File], discord.ui.View]:
        """Crée l'embed de statistiques pour addvax.py
        
        Returns:
            Tuple[discord.Embed, Optional[discord.File], discord.ui.View]: 
                L'embed, le fichier de bannière (si disponible) et la vue avec les boutons
        """
        try:
            file = None
            bot_user = self.bot.user
            guilds_count = len(self.bot.guilds)
            users_count = await self._compute_unique_member_count()
            ping = round(self.bot.latency * 1000)

            if not hasattr(self.bot, 'start_time'):
                self.bot.start_time = datetime.now(FRENCH_TIMEZONE)

            uptime = discord.utils.format_dt(self.bot.start_time, style="R")
            total_commands = self._get_total_commands_count()

            try:
                from cogs.addons.embed_type.utils import config_manager
                HAS_CUSTOM_EMBED = True
            except ImportError:
                try:
                    from .utils import config_manager
                    HAS_CUSTOM_EMBED = True
                except ImportError:
                    config_manager = None
                    HAS_CUSTOM_EMBED = False

            if config_manager:
                embed = config_manager.get_formatted_embed(
                    guild=guild,
                    user=self.bot.user,
                    bot=self.bot,
                    target_id=guild.id if guild else None
                )
            else:
                embed = discord.Embed(
                    color=DEFAULT_COLOR,
                    timestamp=datetime.now(FRENCH_TIMEZONE)
                )

            if hasattr(bot_user, 'display_avatar') and bot_user.display_avatar:
                avatar_url = bot_user.display_avatar.url
                embed.set_author(
                    name=f"Profil de {bot_user.name}",
                    icon_url=avatar_url
                )
                embed.set_thumbnail(url=avatar_url)
            else:
                avatar_url = None
                embed.set_author(name=f"Profil de {bot_user.name}")
            try:
                if not embed.footer or not embed.footer.text:
                    embed.set_footer(
                        text=f"{bot_user.name} • synkrone.app • /help",
                        icon_url=avatar_url,
                    )
            except Exception:
                pass
            try:
                if not embed.timestamp:
                    embed.timestamp = datetime.now(FRENCH_TIMEZONE)
            except Exception:
                pass
            try:
                if not getattr(embed, 'url', None):
                    embed.url = 'https://synkrone.app/discord/bots'
            except Exception:
                pass

            unique_owners = self._compute_unique_owners_count()
            last_restart = discord.utils.format_dt(self.bot.start_time, 'R')
            global_prefix = self._get_global_prefix(guild)
            embed.description = (
                "\n"
                f"🔄 **Dernier redémarrage** : {last_restart}\n"
                f"⚡ **Latence** : `{ping}ms`\n"
                + (f"🔤 **Préfixe** : `{global_prefix}`\n" if global_prefix else "")
                + "\n"
            )

            month_commands = self._get_month_commands_count()
            week_commands = self._get_week_commands_count()
            today_commands = self._get_today_commands_count()
            year_commands = self._get_year_commands_count()
            stats_text = (
                f"👥 Membres uniques : {self._format_number_french(users_count)}\n"
                f"🌍 Serveurs : {self._format_number_french(guilds_count)}\n"
                f"👑 Propriétaires uniques : {self._format_number_french(unique_owners)}\n\n"
                f"⚡ Commandes utilisées : {self._format_number_french(total_commands)}\n"
                f"  - 📆 Cette année : {self._format_number_french(year_commands)}\n"
                f"  - 📅 Ce mois-ci : {self._format_number_french(month_commands)}\n"
                f"  - 🗓️ Cette semaine : {self._format_number_french(week_commands)}\n"
                f"  - 📆 Aujourd'hui : {self._format_number_french(today_commands)}"
            )

            embed.add_field(
                name="📊 Statistiques",
                value=f"```\n{stats_text}\n```",
                inline=False
            )

            # Nouvelle gestion de la bannière officielle Discord
            try:
                fresh_bot_user = await self.bot.fetch_user(self.bot.user.id)
                if hasattr(fresh_bot_user, "banner") and fresh_bot_user.banner:
                    embed.set_image(url=fresh_bot_user.banner.url)
            except Exception as e:
                print(f"[BANNIERE] Impossible de récupérer la bannière officielle : {e}")

            bot_id = str(self.bot.user.id) if hasattr(self.bot, 'user') and hasattr(self.bot.user, 'id') else 'YOUR_BOT_ID'
            invite_url = f"https://discord.com/oauth2/authorize?client_id={bot_id}"
            vote_url = self.bot.vote_url if getattr(self.bot, 'vote_url', None) else self._get_default_vote_url()
            view = ProfileButtons(
                bot=self.bot,
                invite_url=invite_url,
                vote_url=vote_url,
                synkrone_url=getattr(self.bot, 'synkrone_url', DEFAULT_SYNKRONE_URL)
            )
            return embed, file, view
        except Exception as e:
            print(f"Erreur dans get_stats_embed: {e}")
            embed = discord.Embed(
                title="Erreur",
                description="Impossible de charger les statistiques.",
                color=0xA8462F  # brique (DA Synkrone)
            )
            return embed, None, None
    
    def _format_number_french(self, number: int) -> str:
        """Formate un nombre avec des espaces (format français)"""
        return f"{number:,}".replace(",", " ")
    
    # --- Méthodes utilitaires ---
    
    def _get_system_info(self) -> Tuple[float, float]:
        """Récupère les informations système"""
        cpu_usage = psutil.cpu_percent()
        ram_usage = psutil.virtual_memory().percent
        return cpu_usage, ram_usage
    
    async def _compute_unique_member_count(self) -> Optional[int]:
        """Calcule le nombre de membres uniques (humains uniquement) correctement"""
        try:
            unique_ids = set()
            
            # Parcourir toutes les guildes pour compter les membres humains uniques
            for g in self.bot.guilds:
                try:
                    if hasattr(g, 'members') and g.members:
                        # Compter uniquement les membres humains (exclure les bots)
                        unique_ids.update(m.id for m in g.members if not getattr(m, 'bot', False))
                    elif hasattr(g, 'member_count') and g.member_count:
                        # Si les membres ne sont pas chargés, utiliser fetch_members pour obtenir la liste complète
                        try:
                            async for member in g.fetch_members(limit=None):
                                if not getattr(member, 'bot', False):
                                    unique_ids.add(member.id)
                        except Exception:
                            # En dernier recours, estimer en retirant environ 5% de bots du member_count
                            estimated_humans = int(g.member_count * 0.95)
                            unique_ids.update(range(estimated_humans))
                except Exception:
                    continue
            
            return len(unique_ids) if unique_ids else 1
            
        except Exception:
            # En cas d'échec total, retourner une estimation basse
            return sum(getattr(g, 'member_count', 0) or 0 for g in self.bot.guilds) // 2 or 1
    
    def _compute_unique_owners_count(self) -> int:
        """Calcule le nombre de propriétaires uniques correctement"""
        try:
            owner_ids = {g.owner_id for g in self.bot.guilds if hasattr(g, 'owner_id') and g.owner_id}
            return len(owner_ids)
        except Exception:
            return len(self.bot.guilds)

    # --- Helpers préfixes ---

    def _get_server_prefixes(self, guild_id: int) -> list:
        """Retourne les préfixes personnalisés configurés pour un serveur (peut être vide)."""
        import os as _os, json as _json
        try:
            path = _os.path.join('cogs', 'addons', 'prefix', 'data', f'{guild_id}.json')
            if _os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    return _json.load(f).get('prefixes', [])
        except Exception:
            pass
        return []

    def _get_global_prefix(self, guild: Optional[discord.Guild] = None) -> Optional[str]:
        """Retourne le préfixe global actif, ou None si désactivé pour ce serveur."""
        import os as _os, json as _json
        # Vérifie la désactivation dans la config serveur
        if guild:
            config_path = _os.path.join('cogs', 'addons', 'prefix', 'data', f'{guild.id}.json')
            if _os.path.exists(config_path):
                try:
                    with open(config_path, 'r', encoding='utf-8') as f:
                        config = _json.load(f)
                        if config.get('disable_global', False):
                            return None
                except Exception:
                    pass
        # Sinon, retourne le global comme avant
        try:
            cog = self.bot.cogs.get('BotAdmin')
            if cog and hasattr(cog, 'default_prefix'):
                return cog.default_prefix
        except Exception:
            pass
        try:
            cfg = _os.path.join('cogs', 'owner', 'commands', 'panelbot', 'bot_config.json')
            if _os.path.exists(cfg):
                with open(cfg, 'r', encoding='utf-8') as f:
                    prefix = _json.load(f).get('prefix')
                if prefix:
                    return prefix
        except Exception:
            pass
        import os as _os2
        return _os2.getenv('PREFIX', '!')

    def _get_total_commands_count(self) -> int:
        """Récupère la somme slash+prefix depuis dev_stats.db/table command_stats"""
        try:
            db_path = Path(__file__).parent / "../../addons/devstats/dev_stats.db"
            db_path = db_path.resolve()
            if not db_path.exists():
                return 0
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()
            cursor.execute("SELECT SUM(slash_count)+SUM(prefix_count) FROM command_stats")
            result = cursor.fetchone()
            conn.close()
            return result[0] if result and result[0] is not None else 0
        except Exception:
            return 0

# Classe pour les boutons du profil
class ProfileButtons(discord.ui.View):
    """Boutons interactifs sous l'embed de profil"""
    def __init__(self, bot, invite_url: str = None, vote_url: str = None, synkrone_url: str = None, support_url: str = None):
        super().__init__()
        
        # Si l'URL d'invitation n'est pas fournie, on la génère avec l'ID du bot
        if not invite_url or 'YOUR_BOT_ID' in invite_url:
            if hasattr(bot, 'user') and hasattr(bot.user, 'id'):
                bot_id = bot.user.id
                # Format d'URL avec les paramètres nécessaires
                invite_url = f"https://discord.com/oauth2/authorize?client_id={bot_id}&permissions=8&scope=bot%20applications.commands"
            else:
                # URL par défaut qui sera rejetée (pour forcer une erreur visible)
                invite_url = "https://discord.com/oauth2/authorize?client_id=INVALID_BOT_ID"
        
        # S'assurer que les URLs sont correctement encodées
        invite_url = invite_url.replace(' ', '%20').replace('+', '%2B')
        
        # Récupération du nom du bot pour le bouton
        bot_name = getattr(bot.user, 'name', 'Vax') if hasattr(bot, 'user') else 'Vax'
        
        # Bouton d'invitation
        self.add_item(discord.ui.Button(
            label=f"Inviter {bot_name}", 
            url=invite_url, 
            emoji="🔗",
            style=discord.ButtonStyle.link,
            row=0
        ))
        
        # Bouton de vote (seulement si l'URL de vote est fournie)
        if vote_url and vote_url.startswith(('http://', 'https://')):
            self.add_item(discord.ui.Button(
                label="Voter", 
                url=vote_url, 
                emoji="<:top:1528770071445373109>",
                style=discord.ButtonStyle.link,
                row=0
            ))

        # Bouton Synkrone
        if synkrone_url and synkrone_url.startswith(('http://', 'https://')):
            self.add_item(discord.ui.Button(
                label="Synkrone",
                url=synkrone_url,
                emoji="<:Synkrone:1528768996403318855>",
                style=discord.ButtonStyle.link,
                row=1
            ))
        
        # Bouton de support (seulement si l'URL de support est fournie)
        if support_url and support_url.startswith(('http://', 'https://')):
            self.add_item(discord.ui.Button(
                label="Support",
                url=support_url,
                emoji="❓",
                style=discord.ButtonStyle.link,
                row=1
            ))


def setup(bot):
    """Fonction de setup requise pour le chargement du cog"""
    # Ce fichier est un module utilitaire et non un cog à charger
    pass
