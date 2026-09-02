"""
Compatibility wrapper for existing adminlimit imports.
Redirects to devlimit until adminlimit behavior is restored.
"""

from .devlimit import apply_admin_gain_limit, get_admin_hourly_limit

__all__ = [
    "apply_admin_gain_limit",
    "get_admin_hourly_limit",
]
