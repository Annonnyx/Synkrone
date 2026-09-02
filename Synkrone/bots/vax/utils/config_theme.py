from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import discord
from discord import ui

from utils.config_balise import apply_balises, format_balise_line, get_balise_groups, resolve_balises
from utils.config_data import DataManager
from utils.config_emoji import Emoji


DEFAULT_COLOR = 0x8000A8
DEFAULT_FOOTER = "{bot_nom} {version} - {date} - {heure_hhmm} - {serveur}"
GLOBAL_KEY = "global_config"


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _migrate_legacy_theme_data() -> None:
    project_root = _project_root()
    legacy_dir = project_root / "data" / "addons" / "data_embed_type"
    if not legacy_dir.exists():
        return

    global_dst_dir = project_root / "data" / "serv_support"
    server_dst_dir = project_root / "data" / "staff" / "configuration" / "data_theme"
    global_dst_dir.mkdir(parents=True, exist_ok=True)
    server_dst_dir.mkdir(parents=True, exist_ok=True)

    for json_file in legacy_dir.glob("*.json"):
        if json_file.name.lower() == f"{GLOBAL_KEY}.json":
            target = global_dst_dir / json_file.name
        else:
            target = server_dst_dir / json_file.name

        try:
            if not target.exists():
                target.write_text(json_file.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception:
            continue

    # Nettoyage legacy seulement si tous les fichiers ont ete traites.
    try:
        remaining = list(legacy_dir.glob("*.json"))
        if remaining:
            for src in remaining:
                src.unlink(missing_ok=True)
        legacy_dir.rmdir()
    except Exception:
        pass


def _load_owner_panelbot_data() -> dict[str, Any]:
    owner_manager = DataManager("owner")
    raw = owner_manager.load("data_panelbot")
    return raw if isinstance(raw, dict) else {}


def _load_panelbot_theme_defaults() -> dict[str, Any]:
    raw = _load_owner_panelbot_data()
    if not isinstance(raw, dict) or not raw:
        # Fallback de compatibilite avec les anciennes structures.
        data_manager = DataManager("staff/configuration")
        raw = data_manager.load("panelbot_config")
    if not isinstance(raw, dict):
        return {"color": DEFAULT_COLOR, "footer": DEFAULT_FOOTER}

    layout_v2 = raw.get("layout_v2_config", {}) if isinstance(raw.get("layout_v2_config", {}), dict) else {}
    embed_config = raw.get("embed_config", {}) if isinstance(raw.get("embed_config", {}), dict) else {}

    def _coerce_color(value: Any) -> int | None:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            if stripped.startswith("#"):
                try:
                    return int(stripped[1:], 16)
                except ValueError:
                    return None
            if stripped.isdigit():
                return int(stripped)
            return None
        try:
            return int(value)
        except Exception:
            return None

    color = _coerce_color(layout_v2.get("color"))
    if color is None:
        color = _coerce_color(layout_v2.get("accent_color"))
    if color is None:
        color = _coerce_color(embed_config.get("color"))
    if color is None:
        color = DEFAULT_COLOR

    footer = layout_v2.get("footer")
    if footer is None or (isinstance(footer, str) and not footer.strip()):
        footer = embed_config.get("footer")
    if footer is None or (isinstance(footer, str) and not footer.strip()):
        footer = DEFAULT_FOOTER

    return {"color": int(color), "footer": str(footer)}


class PanelbotConfigManager:
    def __init__(self):
        _migrate_legacy_theme_data()
        self.global_manager = DataManager("serv_support")

    def _normalize(self, raw: dict[str, Any] | None) -> dict[str, Any]:
        src = raw or {}

        bot_settings = src.get("bot_settings", {}) if isinstance(src.get("bot_settings", {}), dict) else {}
        layout_v2 = src.get("layout_v2_config", {}) if isinstance(src.get("layout_v2_config", {}), dict) else {}
        owner_ids = src.get("owner_ids", []) if isinstance(src.get("owner_ids", []), list) else []

        if "color" in src or "accent_color" in src or "footer" in src:
            layout_v2 = {
                "color": src.get("color", src.get("accent_color", layout_v2.get("color", DEFAULT_COLOR))),
                "footer": src.get("footer", layout_v2.get("footer", DEFAULT_FOOTER)),
            }
        elif "color" in layout_v2 or "accent_color" in layout_v2 or "footer" in layout_v2:
            layout_v2 = {
                "color": layout_v2.get("color", layout_v2.get("accent_color", DEFAULT_COLOR)),
                "footer": layout_v2.get("footer", DEFAULT_FOOTER),
            }

        normalized = {
            "bot_settings": bot_settings,
            "layout_v2_config": {
                "color": int(layout_v2.get("color", DEFAULT_COLOR)),
                "footer": str(layout_v2.get("footer", DEFAULT_FOOTER)),
            },
            "owner_ids": [int(owner_id) for owner_id in owner_ids if str(owner_id).isdigit()],
        }

        for key in ("prefix", "version", "delay", "status", "presences", "sync_mode"):
            if key in src and key not in normalized["bot_settings"]:
                normalized["bot_settings"][key] = src[key]

        return normalized

    def load_full_config(self) -> dict[str, Any]:
        return self._normalize(self.global_manager.load(GLOBAL_KEY))

    def save_full_config(self, data: dict[str, Any]) -> None:
        self.global_manager.save(GLOBAL_KEY, self._normalize(data))

    def get_bot_settings(self) -> dict[str, Any]:
        return self.load_full_config().get("bot_settings", {})

    def update_bot_settings(self, key: str, value: Any) -> None:
        full = self.load_full_config()
        full.setdefault("bot_settings", {})[key] = value
        self.save_full_config(full)

    def get_layout_v2_config(self) -> dict[str, Any]:
        return self.load_full_config().get("layout_v2_config", {})

    def update_layout_v2_config(self, key: str, value: Any) -> None:
        full = self.load_full_config()
        full.setdefault("layout_v2_config", {})[key] = value
        self.save_full_config(full)


panelbot_config_manager = PanelbotConfigManager()


class EmbedConfigManager:
    @property
    def DEFAULT_COLOR(self) -> int:
        return _load_panelbot_theme_defaults()["color"]

    @property
    def DEFAULT_FOOTER(self) -> str:
        return _load_panelbot_theme_defaults()["footer"]

    def __init__(self):
        _migrate_legacy_theme_data()
        self.global_manager = DataManager("serv_support")
        self.server_manager = DataManager("staff/configuration/data_theme")

    def _normalize(self, raw: dict[str, Any] | None) -> dict[str, Any]:
        src = raw or {}
        if not src:
            return {}

        if "layout_v2_config" in src and isinstance(src["layout_v2_config"], dict):
            src = src["layout_v2_config"]

        defaults = _load_panelbot_theme_defaults()
        color = src.get("color", defaults["color"])
        footer = src.get("footer", defaults["footer"])
        if color is None and footer is None:
            return {}

        return {
            "color": int(color if color is not None else defaults["color"]),
            "footer": str(footer if footer is not None else defaults["footer"]),
        }

    def load_config(self, guild_id: int | None) -> dict[str, Any]:
        if guild_id is None:
            return {}
        return self._normalize(self.server_manager.load(guild_id))

    def save_config(self, guild_id: int | None, data: dict[str, Any]) -> None:
        if isinstance(guild_id, dict) and (data is None or isinstance(data, int)):
            guild_id, data = data, guild_id
        if guild_id is None:
            return
        normalized = self._normalize(data)
        existing = self.server_manager.load(guild_id) or {}
        if not isinstance(existing, dict):
            existing = {}

        # Nettoie un ancien format imbrique pour eviter d'ignorer des cles partagees.
        existing.pop("layout_v2_config", None)

        if not normalized:
            existing.pop("color", None)
            existing.pop("footer", None)
        else:
            existing.update(normalized)

        if existing:
            self.server_manager.save(guild_id, existing)
        else:
            self.server_manager.delete(guild_id)

    def is_server_theme_modified(self, guild_id: int | None) -> bool:
        current = self.load_config(guild_id)
        defaults = _load_panelbot_theme_defaults()
        return bool(current) and (
            int(current.get("color", defaults["color"])) != int(defaults["color"])
            or str(current.get("footer", defaults["footer"])) != str(defaults["footer"])
        )

    def reset_server_theme_to_default(self, guild_id: int | None) -> None:
        self.delete_config(guild_id)

    def delete_config(self, guild_id: int | None = None) -> None:
        if guild_id is None:
            self.global_manager.delete(GLOBAL_KEY)
        else:
            existing = self.server_manager.load(guild_id) or {}
            if not isinstance(existing, dict):
                existing = {}

            existing.pop("layout_v2_config", None)
            existing.pop("color", None)
            existing.pop("footer", None)

            if existing:
                self.server_manager.save(guild_id, existing)
            else:
                self.server_manager.delete(guild_id)

    def get_server_theme_values(self, guild_id: int | None) -> dict[str, Any]:
        return self.load_config(guild_id)

    def get_color(self, guild_id: int | None, force_global: bool = False) -> int:
        resolved = self.get_resolved_values(guild_id, force_global=force_global)
        return int(resolved.get("color", DEFAULT_COLOR))

    def get_resolved_values(self, guild_id: int | None, force_global: bool = False) -> dict[str, Any]:
        global_config = _load_panelbot_theme_defaults()
        guild_config = self.load_config(guild_id)
        if force_global or not guild_config:
            return {
                "color": int(global_config.get("color", DEFAULT_COLOR)),
                "footer": str(global_config.get("footer", DEFAULT_FOOTER)),
            }

        resolved = {
            "color": int(global_config.get("color", DEFAULT_COLOR)),
            "footer": str(global_config.get("footer", DEFAULT_FOOTER)),
        }
        resolved.update(guild_config)
        return resolved

    def get_layout_v2_theme(self, guild_id: int | None, guild, user, bot, force_global: bool = False) -> dict[str, Any]:
        resolved = self.get_resolved_values(guild_id, force_global=force_global)
        footer_template = str(resolved.get("footer", DEFAULT_FOOTER))
        footer_embed_text = self.format_footer_text(footer_template, guild, user, bot)
        footer_layout_text = self.format_footer_text(footer_template, guild, user, bot, for_layout=True)
        return {
            "color": resolved.get("color", DEFAULT_COLOR),
            "footer": footer_template,
            # `footer_text` reste la clef historique consommee par les Layout V2.
            "footer_text": footer_layout_text,
            "footer_embed_text": footer_embed_text,
            "guild_id": guild_id,
            "force_global": force_global,
        }

    def format_footer_text(self, footer_template: str, guild, user, bot, *, for_layout: bool = False) -> str:
        if not footer_template:
            return ""

        try:
            from utils.config_prefix import get_global_prefix

            prefix = get_global_prefix(bot, fallback="!")
        except Exception:
            prefix = "!"

        owner_data = _load_owner_panelbot_data()
        owner_bot_settings = owner_data.get("bot_settings", {}) if isinstance(owner_data.get("bot_settings", {}), dict) else {}
        version = str(owner_bot_settings.get("version", ""))
        if not version:
            version = str(panelbot_config_manager.get_bot_settings().get("version", ""))
        formatted = apply_balises(
            footer_template,
            guild,
            user,
            bot,
            version=version,
            prefix=prefix,
        )
        if for_layout and formatted:
            return f"{Emoji.VAX} {formatted}"
        return formatted

    def get_formatted_embed(
        self,
        guild,
        user,
        bot,
        title: str | None,
        description: str | None,
        target_id: int | None = None,
        force_global: bool = False,
    ) -> discord.Embed:
        guild_id = target_id if target_id is not None else getattr(guild, "id", None)
        theme = self.get_layout_v2_theme(guild_id, guild, user, bot, force_global=force_global)
        color = int(theme.get("color", DEFAULT_COLOR))
        footer_text = str(theme.get("footer_embed_text", "") or "").strip()

        embed = discord.Embed(
            title=title or None,
            description=description or None,
            color=discord.Color(color),
        )

        if footer_text:
            footer_icon_url = None
            if getattr(bot, "user", None):
                footer_icon_url = bot.user.display_avatar.url
            embed.set_footer(text=footer_text, icon_url=footer_icon_url)
        if getattr(bot, "user", None):
            embed.set_thumbnail(url=bot.user.display_avatar.url)
        return embed

    def get_bot_banner_url(self, bot=None) -> str | None:
        bot_user = getattr(bot, "user", None)
        if bot_user is None:
            return None
        banner = getattr(bot_user, "banner", None)
        if banner:
            return banner.url
        return bot_user.display_avatar.url

    def get_panelbot_version(self) -> str:
        owner_data = _load_owner_panelbot_data()
        owner_bot_settings = owner_data.get("bot_settings", {}) if isinstance(owner_data.get("bot_settings", {}), dict) else {}
        version = str(owner_bot_settings.get("version", ""))
        if version:
            return version
        return str(panelbot_config_manager.get_bot_settings().get("version", ""))


config_manager = EmbedConfigManager()


class EmbedCustomizerView(ui.View):
    def __init__(self, *args, timeout: float | None = 600, **kwargs):
        super().__init__(timeout=timeout)
        self.args = args
        self.kwargs = kwargs


class BaliseCatalogLayoutView(ui.LayoutView):
    def __init__(
        self,
        guild: discord.Guild | None,
        user: discord.abc.User,
        bot: discord.Client | None,
        *args,
        timeout: float | None = 600,
        **kwargs,
    ):
        super().__init__(timeout=timeout)
        self.args = args
        self.kwargs = kwargs
        self.add_item(ui.TextDisplay("## Balises disponibles"))

        try:
            from utils.config_prefix import get_global_prefix

            prefix = get_global_prefix(bot, fallback="!") if bot is not None else "!"
        except Exception:
            prefix = "!"

        version = config_manager.get_panelbot_version()
        resolved_vals = resolve_balises(guild, user, bot, version=version, prefix=prefix)

        for group in get_balise_groups():
            self.add_item(ui.TextDisplay(f"### {group['emoji']} {group['title']}"))
            lines = [format_balise_line(token, label, str(resolved_vals.get(token, ""))) for token, label in group["items"]]
            self.add_item(ui.TextDisplay("\n".join(lines)))


__all__ = [
    "DEFAULT_COLOR",
    "DEFAULT_FOOTER",
    "GLOBAL_KEY",
    "PanelbotConfigManager",
    "panelbot_config_manager",
    "EmbedConfigManager",
    "config_manager",
    "EmbedCustomizerView",
    "BaliseCatalogLayoutView",
]
