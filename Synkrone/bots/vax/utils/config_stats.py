from __future__ import annotations

import json
import logging
import sqlite3
import shutil
from pathlib import Path
from typing import Any

import discord
from discord import ui
from PIL import ImageFont
from discord.ext import commands

from utils.config_data import DataManager
from utils.config_perm import ensure_command_permission

try:
    from utils.config_theme import config_manager
except ImportError:
    config_manager = None

logger = logging.getLogger("bot.stats.config")


def _find_project_root() -> Path:
    current = Path(__file__).resolve()
    for candidate in [current.parent, *current.parents]:
        if (candidate / "main.py").exists():
            return candidate
    return current.parents[4]


PROJECT_ROOT = _find_project_root()


def _find_stats_module_root() -> Path:
    candidate = PROJECT_ROOT / "cogs" / "public" / "statistiques"
    if candidate.exists():
        return candidate

    # Fallback defensif si la structure venait a changer.
    current = Path(__file__).resolve()
    for parent in [current.parent, *current.parents]:
        maybe = parent / "cogs" / "public" / "statistiques"
        if maybe.exists():
            return maybe
    return candidate


MODULE_ROOT = _find_stats_module_root()
ASSETS_DIR = MODULE_ROOT / "assets"
FONT_PATH = ASSETS_DIR / "TradeWinds-Regular.ttf"

# DB centralisee des statistiques.
STATS_DB_DIR = PROJECT_ROOT / "data" / "public" / "stats"
STATS_DB_PATH = STATS_DB_DIR / "stats_bot.db"

# Donnees JSON unifiees sous data/public/statistiques/<guild_id>/
STATS_DATA_DIR = PROJECT_ROOT / "data" / "public" / "statistiques"

# DataManager pour preferences/panels statistiques.
STATS_META_DATA = DataManager("public/statistiques/meta")


def ensure_stats_data_dir() -> None:
    STATS_DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_server_dir(guild_id: int | str, *, create: bool = False) -> Path:
    server_dir = STATS_DATA_DIR / str(guild_id)
    if create:
        ensure_stats_data_dir()
        server_dir.mkdir(parents=True, exist_ok=True)
    return server_dir


def get_user_stats_path(guild_id: int | str, user_id: int | str) -> Path:
    return get_server_dir(guild_id, create=False) / f"{user_id}.json"


def get_level_config_path(guild_id: int | str) -> Path:
    return get_server_dir(guild_id, create=False) / "lvl.json"


def get_lvlup_config_path(guild_id: int | str) -> Path:
    return get_server_dir(guild_id, create=False) / "lvlup_config.json"


def get_level_title_prefs_path(guild_id: int | str) -> Path:
    return get_server_dir(guild_id, create=False) / "lvl_title_prefs.json"


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def get_db_connection() -> sqlite3.Connection:
    STATS_DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(STATS_DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def migrate_legacy_stats_db() -> None:
    """Migre l'ancienne DB stats vers data/public/stats sans ecraser l'existante."""
    if STATS_DB_PATH.exists() and STATS_DB_PATH.stat().st_size > 0:
        return

    legacy_candidates = [
        PROJECT_ROOT / "util" / "stats_bot.db",
        MODULE_ROOT / "stats_bot.db",
        MODULE_ROOT / "stats" / "stats_bot.db",
    ]

    STATS_DB_DIR.mkdir(parents=True, exist_ok=True)
    for legacy in legacy_candidates:
        try:
            if legacy.exists() and legacy.stat().st_size > 0:
                shutil.copy2(legacy, STATS_DB_PATH)
                logger.info("DB stats migree: %s -> %s", legacy, STATS_DB_PATH)
                return
        except Exception:
            logger.exception("Echec migration DB legacy depuis %s", legacy)


def setup_activity_database() -> None:
    migrate_legacy_stats_db()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id BIGINT,
            guild_id BIGINT,
            type TEXT,
            value INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    conn.commit()
    conn.close()


def build_themed_embed(
    guild: discord.Guild,
    user: discord.abc.User,
    bot: commands.Bot,
    title: str,
    description: str,
    *,
    fallback_color: int = 0x2B2D31,
) -> discord.Embed:
    layout_theme = get_layout_theme(guild, user, bot)
    color_value = int(layout_theme.get("color", fallback_color))
    footer_text = str(layout_theme.get("footer_embed_text") or "").strip()

    embed = discord.Embed(title=title, description=description, color=color_value)
    if footer_text:
        footer_icon_url = None
        if getattr(bot, "user", None):
            footer_icon_url = bot.user.display_avatar.url
        embed.set_footer(text=footer_text, icon_url=footer_icon_url)
    else:
        embed.set_footer(text=f"Propriete exclusive de {user.display_name}")

    # Fallback de compatibilite: si layout indisponible, essayer le formatteur historique.
    if config_manager and not footer_text:
        try:
            return config_manager.get_formatted_embed(guild, user, bot, title, description, guild.id)
        except Exception:
            logger.exception("Impossible de generer un embed themed, fallback applique.")

    return embed


def build_themed_container(
    guild: discord.Guild | None,
    user: discord.abc.User,
    bot: commands.Bot,
    title: str,
    description: str,
    *,
    heading_level: int = 2,
) -> ui.Container:
    layout_theme = get_layout_theme(guild, user, bot)
    color_value = int(layout_theme.get("color", discord.Color.blurple().value))
    footer_text = str(layout_theme.get("footer_text") or "").strip()

    container = ui.Container(accent_color=discord.Color(color_value), spoiler=False)
    heading_level = min(max(int(heading_level), 1), 3)
    heading_prefix = "#" * heading_level

    if title:
        container.add_item(ui.TextDisplay(f"{heading_prefix} {title}"))
    if description:
        container.add_item(ui.TextDisplay(description))

    if footer_text:
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
        container.add_item(ui.TextDisplay(footer_text))

    return container


def get_layout_theme(guild: discord.Guild | None, user: discord.abc.User, bot: commands.Bot) -> dict[str, Any]:
    if config_manager and guild is not None:
        try:
            return config_manager.get_layout_v2_theme(guild.id, guild, user, bot)
        except Exception:
            logger.exception("Impossible de charger le theme layout v2, fallback applique.")
    return {"color": discord.Color.blurple().value, "footer_text": ""}


def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(str(FONT_PATH), size)
    except Exception:
        return ImageFont.load_default()


async def ensure_stats_command_permission(ctx: commands.Context, command_name: str) -> bool:
    return await ensure_command_permission(ctx, command_name=command_name)
