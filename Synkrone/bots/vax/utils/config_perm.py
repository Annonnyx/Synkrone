"""
CONFIG PERMISSIONS - Gestion hiérarchique des permissions de commandes
=====================================================================
- Découverte automatique des commandes compatibles via décorateur `perm_command`.
- Niveaux 1..9 (1 = plus haut niveau).
- Héritage: un membre avec le niveau 1 possède aussi 2, 3, ... 9.
- Les administrateurs (si activés) peuvent utiliser toutes les commandes protégées.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import discord
from discord.ext import commands

from utils.config_data import DataManager
from utils.config_prefix import prefix_config_manager
from utils.config_emoji import Emoji as E


MAX_PERMISSION_LEVEL = 9
MAX_ROLES_PER_LEVEL = 5
MAX_USERS_PER_LEVEL = 5
FALLBACK_DENY_MESSAGE = "❌ Accès refusé."


@dataclass(slots=True)
class CommandPermissionInfo:
    name: str
    suggested_level: int


def _clamp_level(level: int) -> int:
    try:
        value = int(level)
    except Exception:
        value = MAX_PERMISSION_LEVEL
    return max(1, min(MAX_PERMISSION_LEVEL, value))


def perm_command(level: int):
    """Décorateur de marquage: rend la commande configurable via ²perm."""

    clamped = _clamp_level(level)

    def decorator(target):
        # Peut recevoir une fonction ou un commands.Command.
        if hasattr(target, "callback") and callable(getattr(target, "callback", None)):
            setattr(target.callback, "__perm_level__", clamped)
            setattr(target, "__perm_level__", clamped)
            return target

        setattr(target, "__perm_level__", clamped)
        return target

    return decorator


class PermissionConfigManager:
    def __init__(self):
        self.data_manager = DataManager("staff/configuration/perm")

    def _normalize_level_data(self, level_data: dict[str, Any] | None) -> dict[str, list[int]]:
        src = level_data or {}
        roles = [int(x) for x in src.get("roles", []) if str(x).isdigit()]
        users = [int(x) for x in src.get("users", []) if str(x).isdigit()]
        return {
            "roles": roles[:MAX_ROLES_PER_LEVEL],
            "users": users[:MAX_USERS_PER_LEVEL],
        }

    def _normalize_config(self, raw: dict[str, Any] | None) -> dict[str, Any]:
        src = raw or {}
        levels_src = src.get("levels", {}) if isinstance(src.get("levels", {}), dict) else {}
        levels: dict[str, dict[str, list[int]]] = {}
        command_levels_src = src.get("command_levels", {}) if isinstance(src.get("command_levels", {}), dict) else {}

        for i in range(1, MAX_PERMISSION_LEVEL + 1):
            key = str(i)
            levels[key] = self._normalize_level_data(levels_src.get(key))

        command_levels: dict[str, int] = {}
        for cmd_name, lvl in command_levels_src.items():
            if not isinstance(cmd_name, str):
                continue
            command_levels[cmd_name.lower().strip()] = _clamp_level(lvl)

        return {
            "admins_enabled": bool(src.get("admins_enabled", True)),
            "active_levels": max(3, min(MAX_PERMISSION_LEVEL, int(src.get("active_levels", 3)))),
            "levels": levels,
            "command_levels": command_levels,
        }

    def load_guild_config(self, guild_id: int) -> dict[str, Any]:
        raw = self.data_manager.load(guild_id)
        return self._normalize_config(raw)

    def save_guild_config(self, guild_id: int, data: dict[str, Any]) -> None:
        self.data_manager.save(guild_id, self._normalize_config(data))

    def toggle_admins(self, guild_id: int) -> bool:
        data = self.load_guild_config(guild_id)
        data["admins_enabled"] = not data["admins_enabled"]
        self.save_guild_config(guild_id, data)
        return data["admins_enabled"]

    def get_active_levels(self, guild_id: int) -> int:
        data = self.load_guild_config(guild_id)
        return int(data.get("active_levels", 3))

    def add_permission_level(self, guild_id: int) -> tuple[bool, int]:
        data = self.load_guild_config(guild_id)
        current = int(data.get("active_levels", 3))
        if current >= MAX_PERMISSION_LEVEL:
            return False, current
        data["active_levels"] = current + 1
        self.save_guild_config(guild_id, data)
        return True, int(data["active_levels"])

    def remove_permission_level(self, guild_id: int, level: int) -> tuple[bool, int, int | None]:
        """Supprime un niveau actif, transfère sa config vers le niveau supérieur,
        puis renumérote pour garder une suite logique continue.

        Retourne: (ok, active_levels, niveau_cible_ou_None)
        """
        data = self.load_guild_config(guild_id)
        active = int(data.get("active_levels", 3))

        if active <= 3:
            return False, active, None

        lvl = _clamp_level(level)
        if lvl > active or lvl <= 1:
            return False, active, None

        target = lvl - 1

        # 1) Transfert roles/users du niveau supprimé vers le niveau supérieur.
        src_cfg = data["levels"][str(lvl)]
        dst_cfg = data["levels"][str(target)]

        dst_roles = list(dst_cfg["roles"])
        for role_id in src_cfg["roles"]:
            if role_id not in dst_roles and len(dst_roles) < MAX_ROLES_PER_LEVEL:
                dst_roles.append(role_id)
        dst_cfg["roles"] = dst_roles

        dst_users = list(dst_cfg["users"])
        for user_id in src_cfg["users"]:
            if user_id not in dst_users and len(dst_users) < MAX_USERS_PER_LEVEL:
                dst_users.append(user_id)
        dst_cfg["users"] = dst_users

        # 2) Transfert commandes du niveau supprimé puis décalage des niveaux supérieurs.
        cmd_levels: dict[str, int] = data["command_levels"]
        for cmd_name, assigned in list(cmd_levels.items()):
            assigned_lvl = _clamp_level(assigned)
            if assigned_lvl == lvl:
                cmd_levels[cmd_name] = target
            elif assigned_lvl > lvl:
                cmd_levels[cmd_name] = assigned_lvl - 1

        # 3) Décalage des blocs de niveaux pour renumérotation continue.
        for i in range(lvl + 1, active + 1):
            data["levels"][str(i - 1)] = data["levels"][str(i)]

        data["levels"][str(active)] = {"roles": [], "users": []}
        data["active_levels"] = active - 1
        self.save_guild_config(guild_id, data)
        return True, int(data["active_levels"]), target

    def get_level_data(self, guild_id: int, level: int) -> dict[str, list[int]]:
        data = self.load_guild_config(guild_id)
        return data["levels"][str(_clamp_level(level))]

    def add_role_to_level(self, guild_id: int, level: int, role_id: int) -> tuple[bool, str]:
        level = _clamp_level(level)
        data = self.load_guild_config(guild_id)
        key = str(level)
        roles = data["levels"][key]["roles"]

        if role_id in roles:
            return False, "Ce rôle est  déjà présent pour ce niveau."
        if len(roles) >= MAX_ROLES_PER_LEVEL:
            return False, f"Maximum {MAX_ROLES_PER_LEVEL} rôles pour ce niveau."

        roles.append(int(role_id))
        self.save_guild_config(guild_id, data)
        return True, "Rôle ajouté."

    def remove_role_from_level(self, guild_id: int, level: int, role_id: int) -> tuple[bool, str]:
        level = _clamp_level(level)
        data = self.load_guild_config(guild_id)
        roles = data["levels"][str(level)]["roles"]
        if role_id not in roles:
            return False, "Ce rôle n'est pas présent pour ce niveau."

        roles.remove(role_id)
        self.save_guild_config(guild_id, data)
        return True, "Rôle retiré."

    def add_user_to_level(self, guild_id: int, level: int, user_id: int) -> tuple[bool, str]:
        level = _clamp_level(level)
        data = self.load_guild_config(guild_id)
        key = str(level)
        users = data["levels"][key]["users"]

        if user_id in users:
            return False, "Cet utilisateur est  déjà présent pour ce niveau."
        if len(users) >= MAX_USERS_PER_LEVEL:
            return False, f"Maximum {MAX_USERS_PER_LEVEL} utilisateurs pour ce niveau."

        users.append(int(user_id))
        self.save_guild_config(guild_id, data)
        return True, "Utilisateur ajouté."

    def remove_user_from_level(self, guild_id: int, level: int, user_id: int) -> tuple[bool, str]:
        level = _clamp_level(level)
        data = self.load_guild_config(guild_id)
        users = data["levels"][str(level)]["users"]
        if user_id not in users:
            return False, "Cet utilisateur n'est pas présent pour ce niveau."

        users.remove(user_id)
        self.save_guild_config(guild_id, data)
        return True, "Utilisateur retiré."

    def discover_compatible_commands(self, bot: commands.Bot) -> list[CommandPermissionInfo]:
        """Découvre les commandes configurables pour ²perm.

        Seules les commandes explicitement marquées via @perm_command sont
        considérées comme compatibles.
        """
        found: dict[str, CommandPermissionInfo] = {}

        for cmd in bot.commands:
            if getattr(cmd, "hidden", False):
                continue

            cmd_name = str(getattr(cmd, "name", "")).strip()
            if not cmd_name:
                continue

            level = getattr(getattr(cmd, "callback", None), "__perm_level__", None)
            if level is None:
                level = getattr(cmd, "__perm_level__", None)
            if level is None:
                continue

            suggested = _clamp_level(level)
            key = cmd_name.lower()
            found[key] = CommandPermissionInfo(name=cmd_name, suggested_level=suggested)

        items = list(found.values())
        items.sort(key=lambda x: (x.suggested_level, x.name))
        return items

    def get_command_level_map(self, guild_id: int) -> dict[str, int]:
        data = self.load_guild_config(guild_id)
        return dict(data.get("command_levels", {}))

    def set_command_level(self, guild_id: int, command_name: str, level: int) -> None:
        data = self.load_guild_config(guild_id)
        data["command_levels"][command_name.lower().strip()] = _clamp_level(level)
        self.save_guild_config(guild_id, data)

    def remove_command_level(self, guild_id: int, command_name: str) -> bool:
        data = self.load_guild_config(guild_id)
        key = command_name.lower().strip()
        if key not in data["command_levels"]:
            return False
        del data["command_levels"][key]
        self.save_guild_config(guild_id, data)
        return True

    def get_commands_for_level(self, guild_id: int, level: int) -> list[str]:
        lvl = _clamp_level(level)
        command_levels = self.get_command_level_map(guild_id)
        cmds = [name for name, assigned in command_levels.items() if assigned == lvl]
        return sorted(cmds)

    def get_unassigned_compatible_commands(self, bot: commands.Bot, guild_id: int) -> list[CommandPermissionInfo]:
        assigned = set(self.get_command_level_map(guild_id).keys())
        return [c for c in self.discover_compatible_commands(bot) if c.name.lower() not in assigned]

    def get_command_required_level(self, command: commands.Command | None) -> int | None:
        if command is None:
            return None

        level = getattr(getattr(command, "callback", None), "__perm_level__", None)
        if level is None:
            level = getattr(command, "__perm_level__", None)
        if level is None:
            return None

        return _clamp_level(level)

    def _get_member_best_level(self, guild_id: int, member: discord.Member) -> int | None:
        data = self.load_guild_config(guild_id)
        matched_levels: list[int] = []

        for lvl in range(1, MAX_PERMISSION_LEVEL + 1):
            cfg = data["levels"][str(lvl)]
            if member.id in cfg["users"]:
                matched_levels.append(lvl)
                continue

            member_role_ids = {r.id for r in member.roles}
            if any(role_id in member_role_ids for role_id in cfg["roles"]):
                matched_levels.append(lvl)

        if not matched_levels:
            return None

        # Niveau le plus fort = valeur la plus petite
        return min(matched_levels)

    def can_use_level(self, guild_id: int, member: discord.Member, required_level: int) -> bool:
        required = _clamp_level(required_level)
        data = self.load_guild_config(guild_id)

        # Le propriétaire du serveur garde toujours l'accès.
        if member.id == member.guild.owner_id:
            return True

        if data["admins_enabled"] and member.guild_permissions.administrator:
            return True

        best = self._get_member_best_level(guild_id, member)
        if best is None:
            return False

        # Héritage: 1 >= 2 >= 3 ... (numériquement 1 est le plus fort)
        return best <= required

    def can_use_command_obj(self, guild: discord.Guild, member: discord.Member, command: commands.Command | None) -> bool:
        if command is None:
            data = self.load_guild_config(guild.id)
            if member.id == guild.owner_id:
                return True
            return bool(data["admins_enabled"] and member.guild_permissions.administrator)

        command_levels = self.get_command_level_map(guild.id)
        mapped_required = command_levels.get(command.name.lower())
        if mapped_required is not None:
            return self.can_use_level(guild.id, member, mapped_required)

        suggested = self.get_command_required_level(command)
        if suggested is None:
            data = self.load_guild_config(guild.id)
            if member.id == guild.owner_id:
                return True
            return bool(data["admins_enabled"] and member.guild_permissions.administrator)

        # Compatible mais non configurée => désactivée par défaut (hors bypass admin).
        if mapped_required is None:
            data = self.load_guild_config(guild.id)
            if member.id == guild.owner_id:
                return True
            if data["admins_enabled"] and member.guild_permissions.administrator:
                return True
            return False

        return self.can_use_level(guild.id, member, mapped_required)

    def can_use_command(self, bot: commands.Bot, guild: discord.Guild, member: discord.Member, command_name: str) -> bool:
        command_name = command_name.lower().strip()
        command_levels = self.get_command_level_map(guild.id)

        # Si la commande est explicitement configurée, on l'applique toujours.
        mapped_required = command_levels.get(command_name)
        if mapped_required is not None:
            return self.can_use_level(guild.id, member, mapped_required)

        command_obj = bot.all_commands.get(command_name)
        if command_obj is None:
            data = self.load_guild_config(guild.id)
            if member.id == guild.owner_id:
                return True
            return bool(data["admins_enabled"] and member.guild_permissions.administrator)

        if command_obj is not None and self.get_command_required_level(command_obj) is None:
            # Appel explicite d'une commande "protégée" sans marquage exploitable:
            # on n'ouvre jamais l'accès à tous par défaut.
            data = self.load_guild_config(guild.id)
            if member.id == guild.owner_id:
                return True
            return bool(data["admins_enabled"] and member.guild_permissions.administrator)

        return self.can_use_command_obj(guild, member, command_obj)


perm_config_manager = PermissionConfigManager()


def _get_access_prefix(ctx: commands.Context) -> str:
    prefix = getattr(ctx, "prefix", None)
    if isinstance(prefix, str) and prefix.strip():
        return prefix.strip()

    if ctx.guild:
        try:
            effective = prefix_config_manager.get_effective_prefixes(ctx.bot, ctx.guild.id, default_prefix="!")
            for value in effective:
                if value and value != "\x00":
                    return value
        except Exception:
            pass

    return "!"


def _permission_denied_message(ctx: commands.Context) -> str:
    command_name = None
    if ctx.command is not None:
        command_name = str(ctx.command.name).lower().strip()

    if ctx.guild and command_name:
        cmd_obj = ctx.bot.all_commands.get(command_name)
        if cmd_obj is not None and perm_config_manager.get_command_required_level(cmd_obj) is not None:
            command_levels = perm_config_manager.get_command_level_map(ctx.guild.id)
            prefix = _get_access_prefix(ctx)
            if command_name not in command_levels:
                return f"{getattr(E, 'ERREUR', '❌')} Commande non configurée. Utilisez {prefix}perm pour la configurer."
            return f"{getattr(E, 'ERREUR', '❌')} Permission insuffisante. Utilisez {prefix}perm pour la configurer."

    return FALLBACK_DENY_MESSAGE


async def _send_permission_denied(ctx: commands.Context) -> None:
    """Envoie le message d'erreur dans le canal adapté au contexte (slash, prefix, etc.)."""
    deny_text = _permission_denied_message(ctx)

    try:
        if ctx.interaction is not None and not ctx.interaction.response.is_done():
            await ctx.interaction.response.send_message(deny_text, ephemeral=True)
            return
    except Exception:
        pass

    try:
        await ctx.send(deny_text)
    except Exception:
        try:
            if ctx.interaction is not None:
                await ctx.interaction.followup.send(deny_text, ephemeral=True)
        except Exception:
            pass


async def ensure_command_permission(
    ctx: commands.Context,
    command_name: str | None = None,
    *,
    cleanup_on_denied: bool = False,
    denied_delete_after: float = 8.0,
) -> bool:
    """Garde simple pour commandes préfixées.

    Retourne True si l'utilisateur a le droit, sinon envoie un message d'erreur.
    """

    if not ctx.guild:
        return True

    if await ctx.bot.is_owner(ctx.author):
        return True

    member: discord.Member | None
    if isinstance(ctx.author, discord.Member):
        member = ctx.author
    else:
        member = ctx.guild.get_member(ctx.author.id)
        if member is None:
            try:
                member = await ctx.guild.fetch_member(ctx.author.id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                member = None

    # En contexte serveur, on refuse par défaut si le membre n'est pas résolu.
    if member is None:
        await _handle_permission_denied(
            ctx,
            delete_invocation=cleanup_on_denied,
            delete_fallback_after=denied_delete_after if cleanup_on_denied else 0,
        )
        return False

    if command_name:
        allowed = perm_config_manager.can_use_command(ctx.bot, ctx.guild, member, command_name)
    elif ctx.command is not None:
        allowed = perm_config_manager.can_use_command_obj(ctx.guild, member, ctx.command)
    else:
        cmd_name = command_name or ""
        allowed = perm_config_manager.can_use_command(ctx.bot, ctx.guild, member, cmd_name)
    if allowed:
        return True

    await _handle_permission_denied(
        ctx,
        delete_invocation=cleanup_on_denied,
        delete_fallback_after=denied_delete_after if cleanup_on_denied else 0,
    )
    return False


async def _handle_permission_denied(
    ctx: commands.Context,
    *,
    delete_invocation: bool = True,
    delete_fallback_after: float = 8.0,
) -> None:
    await _send_permission_denied(ctx)

    if delete_invocation:
        msg = getattr(ctx, "message", None)
        if msg is not None:
            try:
                await msg.delete()
            except Exception:
                pass


async def _safe_delete_later(message: discord.Message, delay: float) -> None:
    try:
        await asyncio.sleep(delay)
        await message.delete()
    except Exception:
        pass
