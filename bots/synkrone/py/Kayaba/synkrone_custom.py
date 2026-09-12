# Managed by Synkrone. Applies default vs server customization.
import asyncio
import hashlib
import inspect
import ipaddress
import json
import socket
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import discord
from discord.ext import commands

ACTIVITY = {
    "playing": discord.ActivityType.playing,
    "watching": discord.ActivityType.watching,
    "listening": discord.ActivityType.listening,
    "streaming": discord.ActivityType.streaming,
    "competing": discord.ActivityType.competing,
}

CHANNEL_KEYS = ("welcome", "goodbye", "logs", "tickets")
WELCOME_RELS = (
    "cogs/ADMIN/configuration/joinleave/bienvenue/data/{gid}/config.json",
    "cogs/staff/configuration/joinleave/bienvenue/data/{gid}/config.json",
)
GOODBYE_RELS = (
    "cogs/ADMIN/configuration/joinleave/aurevoir/data_leave/{gid}/config.json",
    "cogs/staff/configuration/joinleave/aurevoir/data_leave/{gid}/config.json",
)
WELCOME_SEED = {
    "channel_id": None,
    "embed_title": "Bienvenue sur {guild}",
    "embed_description": "{user.mention} nous a rejoint !",
    "content_message": "On acclame tous {user.mention} !\nNous sommes désormais {guild.count}.",
    "enabled": True,
}
GOODBYE_SEED = {
    "channel_id": None,
    "embed_title": "Départ de {user}",
    "embed_description": "Triste de te voir partir...",
    "content_message": "{user.mention} nous a quitté.\nNous sommes désormais {guild.count}.",
    "enabled": True,
}

FONT_IDS = ("ibm-plex-sans", "zilla-slab", "source-serif-4", "ibm-plex-mono", "fraunces")
FONT_URLS = {
    "ibm-plex-sans": "https://cdn.jsdelivr.net/fontsource/fonts/ibm-plex-sans@5.2.5/latin-400-normal.ttf",
    "zilla-slab": "https://cdn.jsdelivr.net/fontsource/fonts/zilla-slab@5.2.5/latin-400-normal.ttf",
    "source-serif-4": "https://cdn.jsdelivr.net/fontsource/fonts/source-serif-4@5.2.5/latin-400-normal.ttf",
    "ibm-plex-mono": "https://cdn.jsdelivr.net/fontsource/fonts/ibm-plex-mono@5.2.5/latin-400-normal.ttf",
    "fraunces": "https://cdn.jsdelivr.net/fontsource/fonts/fraunces@5.2.5/latin-400-normal.ttf",
}

_COOLDOWN_HITS = {}
_AVATAR_CACHE = {}


def _read(path: Path):
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def load_defaults():
    return _read(Path("config") / "defaults.json")


def load_guild(guild_id):
    return _read(Path("data") / "synkrone_custom" / ("%s.json" % guild_id))


def resolved_for(guild_id):
    custom = load_guild(guild_id)
    if custom:
        return custom
    return load_defaults()


def _patch_joinleave(rels, guild_id, channel_id, seed):
    for rel in rels:
        path = Path(rel.format(gid=guild_id))
        data = _read(path) or dict(seed)
        data["channel_id"] = int(channel_id)
        data["enabled"] = True
        _write(path, data)


def _font_folders():
    here = Path(__file__).resolve().parent
    return (
        here / "synkrone_fonts",
        Path("synkrone_fonts"),
        Path("data") / "synkrone_fonts",
    )


def card_font_path(guild_id):
    custom = load_guild(guild_id) if guild_id else {}
    defaults = load_defaults()
    font_id = str(
        ((custom.get("identity") or {}).get("font"))
        or ((defaults.get("identity") or {}).get("font"))
        or "ibm-plex-sans"
    )
    if font_id not in FONT_IDS:
        font_id = "ibm-plex-sans"
    for folder in _font_folders():
        path = folder / ("%s.ttf" % font_id)
        if path.exists():
            return str(path)
    return None


def card_font(guild_id, size, fallback=None):
    from PIL import ImageFont

    paths = [card_font_path(guild_id)]
    if fallback:
        paths.append(str(fallback))
    for path in paths:
        if not path:
            continue
        try:
            return ImageFont.truetype(path, int(size))
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=int(size))
    except TypeError:
        return ImageFont.load_default()


def _fetch_bytes_sync(url, limit=8 * 1024 * 1024):
    req = Request(url, headers={"User-Agent": "SynkroneBot/1.0"})
    with urlopen(req, timeout=12) as resp:
        ctype = str(resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype and not ctype.startswith("image/") and ctype != "font/ttf" and "octet-stream" not in ctype:
            if "font" not in ctype and not ctype.startswith("application/"):
                raise ValueError("unexpected content-type %s" % ctype)
        data = resp.read(limit + 1)
    if len(data) > limit:
        raise ValueError("payload too large")
    return data


def _host_is_public(host):
    host = str(host or "").strip().lower().rstrip(".")
    if not host or host in ("localhost", "127.0.0.1", "::1") or host.endswith(".local") or host.endswith(".internal"):
        return False
    try:
        parsed_ip = ipaddress.ip_address(host)
        return bool(parsed_ip.is_global)
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except (ValueError, TypeError, IndexError):
            return False
        if not ip.is_global:
            return False
    return True


def safe_https_url(url):
    raw = str(url or "").strip()
    parsed = urlparse(raw)
    if parsed.scheme != "https" or parsed.username or parsed.password:
        return None
    if not _host_is_public(parsed.hostname):
        return None
    return raw


def command_names(command):
    names = []
    if command is None:
        return names
    for attr in ("qualified_name", "name"):
        val = getattr(command, attr, None)
        if val:
            text = str(val).strip().lower()
            if text and text not in names:
                names.append(text)
    return names


def _lookup(mapping, names):
    if not mapping or not isinstance(mapping, dict) or not names:
        return None
    lowered = {str(key).strip().lower(): value for key, value in mapping.items()}
    for name in names:
        if name in lowered:
            return lowered[name]
    return None


def _is_guild_admin(guild, user):
    if guild is None or user is None:
        return False
    if getattr(guild, "owner_id", None) == getattr(user, "id", None):
        return True
    perms = getattr(user, "guild_permissions", None)
    return bool(perms and getattr(perms, "administrator", False))


def evaluate_command_gate(guild, user, command):
    if guild is None or user is None:
        return True, ""
    payload = load_guild(guild.id)
    names = command_names(command)
    if not names:
        return True, ""
    required = _lookup(payload.get("commandPerms") or {}, names)
    role_id = str(required or "").strip()
    if role_id and not _is_guild_admin(guild, user):
        roles = getattr(user, "roles", None) or []
        if not any(str(getattr(role, "id", "")) == role_id for role in roles):
            return False, "Cette commande est réservée à un rôle de ce serveur."
    seconds = _lookup(payload.get("cooldowns") or {}, names)
    try:
        wait = max(0, min(3600, int(seconds or 0)))
    except (TypeError, ValueError):
        wait = 0
    if wait:
        key = (guild.id, getattr(user, "id", 0), names[0])
        last = _COOLDOWN_HITS.get(key, 0.0)
        now = time.monotonic()
        remain = wait - (now - last)
        if remain > 0:
            return False, "Patiente encore %ss avant de réutiliser `%s`." % (max(1, int(remain)), names[0])
        _COOLDOWN_HITS[key] = now
    return True, ""


def install_hooks(bot):
    if getattr(bot, "_synkrone_gate_installed", False):
        return
    bot._synkrone_gate_installed = True

    async def prefix_check(ctx):
        ok, msg = evaluate_command_gate(ctx.guild, ctx.author, ctx.command)
        if ok:
            return True
        try:
            await ctx.send(msg, ephemeral=True)
        except Exception:
            try:
                await ctx.send(msg)
            except Exception:
                pass
        return False

    bot.add_check(prefix_check)
    prev = getattr(bot.tree, "interaction_check", None)

    async def slash_check(interaction):
        if callable(prev):
            result = prev(interaction)
            if inspect.isawaitable(result):
                result = await result
            if result is False:
                return False
        ok, msg = evaluate_command_gate(interaction.guild, interaction.user, getattr(interaction, "command", None))
        if ok:
            return True
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except Exception:
            pass
        return False

    bot.tree.interaction_check = slash_check


def _ensure_font_file(font_id):
    for folder in _font_folders():
        path = folder / ("%s.ttf" % font_id)
        if path.exists():
            return path
    dest = Path("data") / "synkrone_fonts" / ("%s.ttf" % font_id)
    if dest.exists():
        return dest
    url = FONT_URLS.get(font_id)
    if not url:
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(_fetch_bytes_sync(url, limit=2 * 1024 * 1024))
    return dest


async def ensure_fonts():
    for font_id in FONT_IDS:
        try:
            await asyncio.to_thread(_ensure_font_file, font_id)
        except Exception as err:
            print("[synkrone] font %s: %s" % (font_id, err))


async def apply_presence(bot):
    identity = load_defaults().get("identity") or {}
    text = str(identity.get("activityText") or "").strip()
    if not text:
        return
    kind = ACTIVITY.get(str(identity.get("activityType") or "playing"), discord.ActivityType.playing)
    await bot.change_presence(activity=discord.Activity(type=kind, name=text[:120]))


async def _apply_guild_avatar(guild, url, custom):
    me = guild.me
    if me is None:
        return
    safe = safe_https_url(url)
    identity = dict(custom.get("identity") or {})
    applied = str(identity.get("avatarApplied") or "")
    if not safe:
        if applied:
            try:
                await me.edit(avatar=None)
            except Exception as err:
                print("[synkrone] clear avatar on guild %s: %s" % (guild.id, err))
            identity["avatarApplied"] = ""
            custom["identity"] = identity
            _write(Path("data") / "synkrone_custom" / ("%s.json" % guild.id), custom)
        return
    if applied == safe and getattr(me, "guild_avatar", None):
        return
    cache_key = hashlib.sha256(safe.encode("utf-8")).hexdigest()
    blob = _AVATAR_CACHE.get(cache_key)
    if blob is None:
        blob = await asyncio.to_thread(_fetch_bytes_sync, safe)
        if not blob.startswith(b"\x89PNG") and blob[:2] != b"\xff\xd8":
            raise ValueError("avatar must be PNG or JPEG")
        _AVATAR_CACHE[cache_key] = blob
    await me.edit(avatar=blob)
    identity["avatarUrl"] = safe
    identity["avatarApplied"] = safe
    custom["identity"] = identity
    _write(Path("data") / "synkrone_custom" / ("%s.json" % guild.id), custom)


async def apply_guild_profile(guild):
    custom = load_guild(guild.id)
    defaults = load_defaults()
    identity = custom.get("identity") or {}
    default_identity = defaults.get("identity") or {}
    nick = str(identity.get("displayName") or default_identity.get("displayName") or "").strip()
    kwargs = {}
    if nick and guild.me and guild.me.nick != nick[:32]:
        kwargs["nick"] = nick[:32]
    if kwargs and guild.me:
        try:
            await guild.me.edit(**kwargs)
        except Exception as err:
            print("[synkrone] nick on guild %s: %s" % (guild.id, err))
    try:
        await _apply_guild_avatar(guild, identity.get("avatarUrl") or "", custom)
    except Exception as err:
        print("[synkrone] avatar on guild %s: %s" % (guild.id, err))


async def ensure_auto_channels(guild):
    defaults = load_defaults()
    install = defaults.get("install") or {}
    custom = load_guild(guild.id)
    channels = dict(custom.get("channels") or {})
    roles = dict(custom.get("roles") or {})
    created = 0
    quota = int((defaults.get("limits") or {}).get("autoCreatedMax") or 20)
    category = None
    category_id = str(channels.get("category") or "").strip()
    if category_id.isdigit():
        found = guild.get_channel(int(category_id))
        if found is not None:
            category = found

    for key, spec in install.items():
        if not isinstance(spec, dict) or spec.get("provision") != "auto":
            continue
        if created >= quota:
            break
        name = str(spec.get("autoName") or key).strip()[:90] or key
        if key == "mute":
            if roles.get("mute"):
                continue
            try:
                role = await guild.create_role(name=name)
                roles["mute"] = str(role.id)
                created += 1
            except Exception as err:
                print("[synkrone] auto role mute: %s" % err)
            continue
        if key not in CHANNEL_KEYS:
            continue
        if channels.get(key):
            continue
        try:
            kwargs = {"name": name}
            if category is not None:
                kwargs["category"] = category
            channel = await guild.create_text_channel(**kwargs)
            channels[key] = str(channel.id)
            created += 1
            if key == "welcome":
                _patch_joinleave(WELCOME_RELS, guild.id, channel.id, WELCOME_SEED)
            elif key == "goodbye":
                _patch_joinleave(GOODBYE_RELS, guild.id, channel.id, GOODBYE_SEED)
        except Exception as err:
            print("[synkrone] auto channel %s: %s" % (key, err))
    if created:
        custom["channels"] = channels
        custom["roles"] = roles
        _write(Path("data") / "synkrone_custom" / ("%s.json" % guild.id), custom)


async def apply_runtime(bot, new_guild=None):
    try:
        install_hooks(bot)
    except Exception as err:
        print("[synkrone] command gate: %s" % err)
    try:
        await ensure_fonts()
    except Exception as err:
        print("[synkrone] fonts: %s" % err)
    try:
        await apply_presence(bot)
    except Exception as err:
        print("[synkrone] presence: %s" % err)
    targets = [new_guild] if new_guild is not None else list(bot.guilds)
    for guild in targets:
        if guild is None:
            continue
        try:
            if new_guild is not None:
                await ensure_auto_channels(guild)
            await apply_guild_profile(guild)
        except Exception as err:
            print("[synkrone] custom guild %s: %s" % (guild.id, err))
