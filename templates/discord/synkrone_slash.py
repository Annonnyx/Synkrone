# Managed by Synkrone. Registers slash commands on each guild (instant) and globally.
import json
import os
from pathlib import Path


def read_panel_config():
    path = Path("config") / "bot.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def slash_enabled(cfg=None):
    data = cfg if isinstance(cfg, dict) else read_panel_config()
    if "slashCommands" in data:
        return bool(data.get("slashCommands"))
    raw = os.getenv("ENABLE_SLASH_COMMANDS", "true")
    return str(raw).lower() in ("1", "true", "yes")


async def sync_app_commands(bot, cfg=None, guild=None, log_prefix="[synkrone]"):
    data = cfg if isinstance(cfg, dict) else read_panel_config()
    enabled = slash_enabled(data)
    try:
        if guild is not None:
            if not enabled:
                bot.tree.clear_commands(guild=guild)
                await bot.tree.sync(guild=guild)
                print("%s slash disabled on guild %s" % (log_prefix, guild.id))
                return
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print("%s slash synced on guild %s (%s)" % (log_prefix, guild.id, len(synced)))
            return

        pending = len(bot.tree.get_commands())
        print("%s slash commands in tree: %s" % (log_prefix, pending))
        if not enabled:
            bot.tree.clear_commands(guild=None)
            for item in list(bot.guilds):
                bot.tree.clear_commands(guild=item)
                await bot.tree.sync(guild=item)
            await bot.tree.sync()
            print("%s slash commands disabled" % log_prefix)
            return

        for item in list(bot.guilds):
            try:
                bot.tree.copy_global_to(guild=item)
                synced = await bot.tree.sync(guild=item)
                print("%s slash synced on guild %s (%s)" % (log_prefix, item.id, len(synced)))
            except Exception as err:
                print("%s slash sync failed on guild %s: %s" % (log_prefix, item.id, err))
        synced = await bot.tree.sync()
        print("%s slash commands registered globally (%s)" % (log_prefix, len(synced)))
    except Exception as err:
        print("%s slash sync failed: %s" % (log_prefix, err))
