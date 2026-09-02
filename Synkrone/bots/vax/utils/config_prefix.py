"""
CONFIGURATION PREFIX CENTRALISEE
================================
Gestion des prefixes serveurs (custom/global) et resolution du prefix global.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from utils.config_data import DataManager
from utils.config_theme import panelbot_config_manager


MAX_PREFIXES = 5
MAX_PREFIX_LENGTH = 5


class PrefixConfigManager:
    """Gestion centralisee des prefixes par serveur."""

    def __init__(self):
        self.data_manager = DataManager("staff/configuration/data_theme")
        self._migrate_legacy_prefix_data()

    def _migrate_legacy_prefix_data(self) -> None:
        """Migre les anciens prefixes serveur vers data_theme sans ecraser le theme."""
        project_root = Path(self.data_manager.project_root)
        legacy_dir = project_root / "data" / "addons" / "data_prefix"
        if not legacy_dir.exists():
            return

        try:
            legacy_files = list(legacy_dir.glob("*.json"))
        except Exception:
            legacy_files = []

        for legacy_file in legacy_files:
            try:
                guild_id = legacy_file.stem
                with legacy_file.open("r", encoding="utf-8") as handle:
                    legacy_raw = json.load(handle)
                normalized = self._normalize_config(legacy_raw)

                if not normalized["prefixes"] and not normalized["disable_global"]:
                    legacy_file.unlink(missing_ok=True)
                    continue

                current = self.data_manager.load(guild_id) or {}
                if not isinstance(current, dict):
                    current = {}

                current["prefixes"] = list(normalized["prefixes"])
                current["disable_global"] = bool(normalized["disable_global"])
                self.data_manager.save(guild_id, current)
                legacy_file.unlink(missing_ok=True)
            except Exception:
                continue

        # Tente de supprimer le dossier legacy vide.
        try:
            if legacy_dir.exists() and not any(legacy_dir.glob("*.json")):
                legacy_dir.rmdir()
        except Exception:
            pass

    def _normalize_config(self, raw: dict[str, Any] | None) -> dict[str, Any]:
        src = raw or {}
        prefixes_raw = src.get("prefixes", []) if isinstance(src.get("prefixes", []), list) else []

        prefixes: list[str] = []
        for entry in prefixes_raw:
            if not isinstance(entry, str):
                continue
            value = entry.strip()
            if not value:
                continue
            if len(value) > MAX_PREFIX_LENGTH:
                continue
            if value not in prefixes:
                prefixes.append(value)
            if len(prefixes) >= MAX_PREFIXES:
                break

        disable_global = bool(src.get("disable_global", False))
        # Si aucun préfixe serveur n'est défini, le préfixe global reste forcément actif.
        if not prefixes:
            disable_global = False

        return {
            "prefixes": prefixes,
            "disable_global": disable_global,
        }

    def get_server_config(self, guild_id: int) -> dict[str, Any]:
        return self._normalize_config(self.data_manager.load(guild_id))

    def save_server_config(self, guild_id: int, data: dict[str, Any]) -> None:
        normalized = self._normalize_config(data)
        existing = self.data_manager.load(guild_id) or {}
        if not isinstance(existing, dict):
            existing = {}

        has_custom_config = bool(normalized["prefixes"]) or bool(normalized["disable_global"])
        if has_custom_config:
            existing["prefixes"] = list(normalized["prefixes"])
            existing["disable_global"] = bool(normalized["disable_global"])
        else:
            existing.pop("prefixes", None)
            existing.pop("disable_global", None)

        if existing:
            self.data_manager.save(guild_id, existing)
        else:
            self.data_manager.delete(guild_id)

    def reset_server_config(self, guild_id: int) -> None:
        existing = self.data_manager.load(guild_id) or {}
        if not isinstance(existing, dict):
            existing = {}

        existing.pop("prefixes", None)
        existing.pop("disable_global", None)

        if existing:
            self.data_manager.save(guild_id, existing)
        else:
            self.data_manager.delete(guild_id)

    def get_effective_prefixes(self, bot, guild_id: int, default_prefix: str = "!") -> list[str]:
        cfg = self.get_server_config(guild_id)
        server_prefixes = cfg.get("prefixes", [])
        disable_global = bool(cfg.get("disable_global", False))
        if server_prefixes:
            # Les préfixes serveur sont prioritaires ; le global reste disponible
            # tant qu'il n'est pas explicitement désactivé.
            if disable_global:
                return list(server_prefixes)

            global_prefix = get_global_prefix(bot, fallback=default_prefix)
            merged = list(server_prefixes)
            if global_prefix and global_prefix not in merged:
                merged.append(global_prefix)
            return merged

        global_prefix = get_global_prefix(bot, fallback=default_prefix)
        return [global_prefix]


def get_global_prefix(bot, fallback: str = "!") -> str:
    """Retourne le prefix global: BotAdmin en memoire -> panelbot config -> fallback."""
    try:
        cog = bot.cogs.get("BotAdmin")
        if cog and hasattr(cog, "default_prefix"):
            in_memory = str(getattr(cog, "default_prefix")).strip()
            if in_memory:
                return in_memory
    except Exception:
        pass

    # Source de verite persistante du panel owner.
    try:
        owner_data = DataManager("owner").load("data_panelbot")
        if isinstance(owner_data, dict):
            owner_settings = owner_data.get("bot_settings", {})
            if isinstance(owner_settings, dict):
                owner_prefix = str(owner_settings.get("prefix", "")).strip()
                if owner_prefix:
                    return owner_prefix
    except Exception:
        pass

    try:
        settings = panelbot_config_manager.get_bot_settings() or {}
        config_prefix = str(settings.get("prefix", "")).strip()
        if config_prefix:
            return config_prefix
    except Exception:
        pass

    return fallback


prefix_config_manager = PrefixConfigManager()
