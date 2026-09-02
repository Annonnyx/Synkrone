# -*- coding: utf-8 -*-
"""
Manager d'Interface LayoutV2 & Profil - Vax v3
===============================================
Centralisation de la génération des vues LayoutV2 (Container, TextDisplay, Sections, Boutons).
"""

from __future__ import annotations

import math
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
import traceback
from typing import Optional, Tuple

import discord
from discord import ui
from colorama import Fore, Style, init

from utils.config_emoji import Emoji as E
from utils.config_prefix import get_global_prefix, prefix_config_manager
from utils.config_theme import config_manager

# --- Configuration & Logs ---
DEBUG_MODE = True
ERROR_ONLY_MODE = False

init(autoreset=True)

DEFAULT_COLOR = 0x2b2d31
EMOJI_PROFILE = getattr(E, "PROFIL", "👤")
EMOJI_LINK = getattr(E, "LIEN", "🔗")
EMOJI_HELP = getattr(E, "QUESTION", "❓")

try:
    from zoneinfo import ZoneInfo
    FRENCH_TIMEZONE = ZoneInfo('Europe/Berlin')
except ImportError:
    FRENCH_TIMEZONE = timezone.utc
except Exception:
    FRENCH_TIMEZONE = timezone.utc


class ProfileButtons(discord.ui.View):
    """Boutons interactifs de navigation et d'action du profil Vax v3"""
    def __init__(self, bot, invite_url: str = None, vote_url: str = None, support_url: str = None):
        super().__init__(timeout=None)
        
        if not invite_url or 'YOUR_BOT_ID' in invite_url:
            if hasattr(bot, 'user') and hasattr(bot.user, 'id'):
                bot_id = bot.user.id
                invite_url = f"https://discord.com/oauth2/authorize?client_id={bot_id}&permissions=8&scope=bot%20applications.commands"
            else:
                invite_url = "https://discord.com/oauth2/authorize?client_id=1367891720871874560"
        
        bot_name = getattr(bot.user, 'name', 'Vax') if hasattr(bot, 'user') else 'Vax'
        
        self.add_item(discord.ui.Button(
            label=f"Inviter {bot_name}", 
            url=invite_url, 
            emoji=EMOJI_LINK,
            style=discord.ButtonStyle.link
        ))
        
        if vote_url and vote_url.startswith(('http://', 'https://')):
            self.add_item(discord.ui.Button(
                label="Voter", 
                url=vote_url, 
                emoji=getattr(E, "ETOILE", "⭐"),
                style=discord.ButtonStyle.link
            ))
        
        if support_url and support_url.startswith(('http://', 'https://')):
            self.add_item(discord.ui.Button(
                label="Support",
                url=support_url,
                emoji=EMOJI_HELP,
                style=discord.ButtonStyle.link
            ))


class EmbedManager:
    """Gestionnaire centralisé pour la création des LayoutV2 du profil et des stats du bot"""
    
    def __init__(self, bot):
        self.bot = bot
        
    @classmethod
    async def create(cls, bot):
        instance = cls(bot)
        return instance
        
    def _format_number_french(self, number: int) -> str:
        return f"{number:,}".replace(",", " ")

    def _stats_db_candidates(self) -> list[Path]:
        project_root = Path(__file__).resolve().parent.parent
        return [
            project_root / "data" / "serv_support" / "profilbot_stats.db",
            project_root / "botprofil" / "stats.db",
        ]

    def _table_exists(self, conn: sqlite3.Connection, table_name: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table_name,),
        ).fetchone()
        return bool(row)

    def _table_columns(self, conn: sqlite3.Connection, table_name: str) -> set[str]:
        try:
            rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
            return {str(r[1]) for r in rows if len(r) > 1}
        except Exception:
            return set()

    def _count_commands_since(self, since_utc: Optional[datetime] = None) -> int:
        total = 0
        fallback_result: Optional[int] = None
        since_timestamp = int(since_utc.timestamp()) if since_utc else None
        since_text = since_utc.strftime("%Y-%m-%d %H:%M:%S") if since_utc else None

        for db_path in self._stats_db_candidates():
            if not db_path.exists():
                continue

            try:
                with sqlite3.connect(str(db_path)) as conn:
                    # Format historique 1: table command_stats(user_id, command_name, timestamp)
                    if self._table_exists(conn, "command_stats"):
                        cols = self._table_columns(conn, "command_stats")

                        if "timestamp" in cols:
                            if since_text:
                                row = conn.execute(
                                    "SELECT COUNT(*) FROM command_stats WHERE timestamp >= ?",
                                    (since_text,),
                                ).fetchone()
                            else:
                                row = conn.execute("SELECT COUNT(*) FROM command_stats").fetchone()
                            value = int(row[0]) if row and row[0] is not None else 0
                            if value > 0:
                                total += value
                            elif fallback_result is None:
                                fallback_result = value
                            continue

                        # Format historique 2: agrégat slash/prefix sans timestamp détaillé.
                        if {"slash_count", "prefix_count"}.issubset(cols) and since_utc is None:
                            row = conn.execute("SELECT COALESCE(SUM(slash_count),0) + COALESCE(SUM(prefix_count),0) FROM command_stats").fetchone()
                            value = int(row[0]) if row and row[0] is not None else 0
                            if value > 0:
                                total += value
                            elif fallback_result is None:
                                fallback_result = value
                            continue

                    # Format legacy: command_usage_log(timestamp en epoch)
                    if self._table_exists(conn, "command_usage_log"):
                        cols = self._table_columns(conn, "command_usage_log")
                        if "timestamp" in cols:
                            if since_timestamp is not None:
                                row = conn.execute(
                                    "SELECT COUNT(*) FROM command_usage_log WHERE timestamp >= ?",
                                    (since_timestamp,),
                                ).fetchone()
                            else:
                                row = conn.execute("SELECT COUNT(*) FROM command_usage_log").fetchone()
                            value = int(row[0]) if row and row[0] is not None else 0
                            if value > 0:
                                total += value
                            elif fallback_result is None:
                                fallback_result = value
            except Exception:
                continue

        if total > 0:
            return total
        return fallback_result or 0

    def _get_year_commands_count(self) -> int:
        try:
            now = datetime.utcnow()
            start = datetime(now.year, 1, 1)
            return self._count_commands_since(start)
        except Exception:
            return 0

    def _get_week_commands_count(self) -> int:
        try:
            now = datetime.utcnow()
            today = datetime(now.year, now.month, now.day)
            week_start = today - timedelta(days=today.isoweekday() - 1) if hasattr(today, 'isoweekday') else today
            return self._count_commands_since(week_start)
        except Exception:
            return 0

    def _get_today_commands_count(self) -> int:
        try:
            now = datetime.utcnow()
            today = datetime(now.year, now.month, now.day)
            return self._count_commands_since(today)
        except Exception:
            return 0

    def _get_month_commands_count(self) -> int:
        try:
            now = datetime.utcnow()
            month_start = datetime(now.year, now.month, 1)
            return self._count_commands_since(month_start)
        except Exception:
            return 0

    async def _compute_unique_member_count(self) -> int:
        try:
            unique_ids = set()
            for g in self.bot.guilds:
                if hasattr(g, 'members') and g.members:
                    unique_ids.update(m.id for m in g.members if not getattr(m, 'bot', False))
                elif hasattr(g, 'member_count') and g.member_count:
                    estimated = int(g.member_count * 0.95)
                    unique_ids.update(range(estimated))
            return len(unique_ids) if unique_ids else 1
        except Exception:
            return sum(getattr(g, 'member_count', 0) or 0 for g in self.bot.guilds) // 2 or 1
    
    def _compute_unique_owners_count(self) -> int:
        try:
            return len({g.owner_id for g in self.bot.guilds if hasattr(g, 'owner_id') and g.owner_id})
        except Exception:
            return len(self.bot.guilds)

    def _get_total_commands_count(self) -> int:
        try:
            return self._count_commands_since(None)
        except Exception:
            return 0

    def _get_global_prefix(self, guild: Optional[discord.Guild] = None) -> Optional[str]:
        return get_global_prefix(self.bot, fallback="!")

    def _get_server_prefixes(self, guild: Optional[discord.Guild]) -> list[str]:
        if guild is None:
            return []
        try:
            # On n'affiche ici que les prefixes custom serveur,
            # pas les prefixes effectifs (qui incluent le global).
            cfg = prefix_config_manager.get_server_config(guild.id)
            prefixes = cfg.get("prefixes", [])
            return prefixes if isinstance(prefixes, list) else []
        except Exception:
            return []

    async def _build_layout_view(self, guild: Optional[discord.Guild] = None) -> Tuple[ui.LayoutView, Optional[discord.File]]:
        try:
            bot_user = self.bot.user
            guilds_count = len(self.bot.guilds)
            users_count = await self._compute_unique_member_count()
            latency_seconds = getattr(self.bot, "latency", None)
            if isinstance(latency_seconds, (int, float)) and math.isfinite(latency_seconds) and latency_seconds >= 0:
                ping_display = f"{round(latency_seconds * 1000)}ms"
            else:
                ping_display = "N/A"

            if not hasattr(self.bot, 'start_time'):
                self.bot.start_time = datetime.now(FRENCH_TIMEZONE)

            unique_owners = self._compute_unique_owners_count()
            total_commands = self._get_total_commands_count()
            last_restart = discord.utils.format_dt(self.bot.start_time, style="R")
            last_refresh = discord.utils.format_dt(discord.utils.utcnow(), style="T")
            global_prefix = self._get_global_prefix(guild)

            # Récupération de la couleur et footer via les managers du projet
            theme_vals = config_manager.get_resolved_values(guild.id if guild else 0)
            accent_color = int(theme_vals.get("color", DEFAULT_COLOR))
            footer_template = str(theme_vals.get("footer", config_manager.DEFAULT_FOOTER))
            footer_resolved = config_manager.format_footer_text(footer_template, guild, self.bot.user, self.bot, for_layout=True)

            # Création de la vue LayoutV2
            view = ui.LayoutView(timeout=None)
            container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)

            # En-tête / Auteur
            bot_name = bot_user.name if bot_user else "Vax"
            container.add_item(ui.TextDisplay(f"# {EMOJI_PROFILE} Profil de {bot_name}"))

            # Boutons en haut de la carte.
            bot_id = str(bot_user.id) if bot_user else '1367891720871874560'
            invite_url = f"https://discord.com/oauth2/authorize?client_id={bot_id}&permissions=8&scope=bot%20applications.commands"
            support_url = "https://discord.gg/p768u2Pgp3"
            vote_url = getattr(self.bot, 'vote_url', 'https://top.gg/fr/bot/1367891720871874560')

            action_row = ui.ActionRow()
            action_row.add_item(discord.ui.Button(label=f"Inviter {bot_name}", url=invite_url, emoji=EMOJI_LINK, style=discord.ButtonStyle.link))
            action_row.add_item(discord.ui.Button(label="Voter", url=vote_url, emoji=getattr(E, "ETOILE", "⭐"), style=discord.ButtonStyle.link))
            action_row.add_item(discord.ui.Button(label="Support", url=support_url, emoji=EMOJI_HELP, style=discord.ButtonStyle.link))
            container.add_item(action_row)
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
            
            info_text = (
                f"{getattr(E, 'RAFRAICHIR', '🔄')} **Dernier redémarrage** : {last_restart}\n"
                f"{getattr(E, 'ECLAIR', '⚡')} **Latence** : `{ping_display}`\n"
                + (f"🔤 **Préfixe** : `{global_prefix}`\n" if global_prefix else "")
            )

            # Affiche le thumbnail en haut a droite.
            if bot_user and bot_user.display_avatar:
                container.add_item(
                    ui.Section(
                        ui.TextDisplay(f"## {getattr(E, 'INFO', 'ℹ️')} Informations"),
                        ui.TextDisplay(info_text),
                        accessory=ui.Thumbnail(bot_user.display_avatar.url, description="Avatar du bot"),
                    )
                )
            else:
                container.add_item(ui.TextDisplay(f"## {getattr(E, 'INFO', 'ℹ️')} Informations"))
                container.add_item(ui.TextDisplay(info_text))

            server_prefixes = self._get_server_prefixes(guild)
            if server_prefixes:
                prefixes_text = " ".join(f"`{p}`" for p in server_prefixes)
                container.add_item(ui.TextDisplay(f"🔤 **Préfixes configurés** : {prefixes_text}"))

            # Statistiques détaillées dans un bloc de code
            month_commands = self._get_month_commands_count()
            week_commands = self._get_week_commands_count()
            today_commands = self._get_today_commands_count()
            year_commands = self._get_year_commands_count()
            
            stats_text = (
                f"👥 Membres uniques : {self._format_number_french(users_count)}\n"
                f"🌍 Serveurs : {self._format_number_french(guilds_count)}\n"
                f"👑 Propriétaires uniques : {self._format_number_french(unique_owners)}\n\n"
                f"{getattr(E, 'ECLAIR', '⚡')} Commandes utilisées : {self._format_number_french(total_commands)}\n"
                f"  - 📆 Cette année : {self._format_number_french(year_commands)}\n"
                f"  - 📅 Ce mois-ci : {self._format_number_french(month_commands)}\n"
                f"  - 🗓️ Cette semaine : {self._format_number_french(week_commands)}\n"
                f"  - {getattr(E, 'GRAPHIQUE', '📊')} Aujourd'hui : {self._format_number_french(today_commands)}"
            )

            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
            container.add_item(ui.TextDisplay(f"## {getattr(E, 'GRAPHIQUE', '📊')} Statistiques globales"))
            container.add_item(ui.TextDisplay(f"```\n{stats_text}\n```"))

            # Bannière du bot en bas.
            banner_url: Optional[str] = None
            try:
                if bot_user and bot_user.banner:
                    banner_url = bot_user.banner.url
                elif bot_user:
                    fetched_user = await self.bot.fetch_user(bot_user.id)
                    if fetched_user and fetched_user.banner:
                        banner_url = fetched_user.banner.url
            except Exception:
                banner_url = None

            if banner_url:
                try:
                    container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
                    gallery = ui.MediaGallery()
                    gallery.add_item(media=banner_url, description=f"Banniere de {bot_name}")
                    container.add_item(gallery)
                except Exception:
                    pass

            if footer_resolved:
                container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
                container.add_item(ui.TextDisplay(footer_resolved))

            view.add_item(container)
            return view, None
        except Exception as e:
            print(f"{Fore.RED}[PROFILBOT ERROR] build layout failed: {e}{Style.RESET_ALL}")
            traceback.print_exc()

            # Fallback minimal pour ne jamais casser la commande/cog.
            fallback_view = ui.LayoutView(timeout=30)
            fallback_container = ui.Container(accent_color=discord.Color(DEFAULT_COLOR), spoiler=False)
            fallback_container.add_item(ui.TextDisplay(f"# {getattr(E, 'ATTENTION', '⚠️')} Profil indisponible"))
            fallback_container.add_item(ui.TextDisplay("Une erreur est survenue pendant la generation du layout."))
            fallback_view.add_item(fallback_container)
            return fallback_view, None

    async def get_profile_layout(self, guild: Optional[discord.Guild] = None) -> Tuple[ui.LayoutView, Optional[discord.File]]:
        return await self._build_layout_view(guild)

    async def get_stats_layout(self, guild: discord.Guild) -> Tuple[ui.LayoutView, Optional[discord.File]]:
        return await self._build_layout_view(guild)