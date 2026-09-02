"""
Temporary compatibility module for admin limit imports.
This stub preserves current game imports while disabling admin limit behavior.
"""

from __future__ import annotations


def get_admin_hourly_limit(guild_id: int, game: str, default_limit):
    """Return the original hourly limit without applying any admin override."""
    return default_limit


def apply_admin_gain_limit(guild_id: int, game: str, gain):
    """Return the gain unchanged while admin gain limits are disabled."""
    return gain
