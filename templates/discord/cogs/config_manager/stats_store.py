import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord.ext import commands, tasks


class StatsDatabase:
    def __init__(self, db_path="data/stats.db", json_path="data/runtime_stats.json"):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.json_path = json_path
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.create_table()

    def create_table(self):
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS command_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    command_name TEXT,
                    user_id INTEGER,
                    timestamp TEXT
                )
                """
            )

    def log_command(self, command_name: str, user_id: int):
        now = datetime.utcnow().isoformat()
        with self.conn:
            self.conn.execute(
                "INSERT INTO command_logs (command_name, user_id, timestamp) VALUES (?, ?, ?)",
                (command_name, user_id, now),
            )

    def get_stats(self):
        now = datetime.utcnow()
        current_month = now.strftime("%Y-%m")
        current_day = now.strftime("%Y-%m-%d")
        with self.conn:
            total = self.conn.execute("SELECT COUNT(*) FROM command_logs").fetchone()[0]
            month = self.conn.execute(
                "SELECT COUNT(*) FROM command_logs WHERE timestamp LIKE ?",
                (f"{current_month}%",),
            ).fetchone()[0]
            today = self.conn.execute(
                "SELECT COUNT(*) FROM command_logs WHERE timestamp LIKE ?",
                (f"{current_day}%",),
            ).fetchone()[0]
        return total, month, today

    def unique_users(self) -> int:
        with self.conn:
            row = self.conn.execute(
                "SELECT COUNT(DISTINCT user_id) FROM command_logs"
            ).fetchone()
        return int(row[0] if row else 0)

    def snapshot(self, bot=None) -> dict:
        total, month, today = self.get_stats()
        start = getattr(bot, "start_time", None) if bot is not None else None
        now = datetime.now(timezone.utc)
        uptime = 0
        started_at = None
        if start is not None:
            if getattr(start, "tzinfo", None) is None:
                start = start.replace(tzinfo=timezone.utc)
            uptime = max(0, int((now - start).total_seconds()))
            started_at = start.isoformat()
        guilds = []
        if bot is not None:
            guilds = [{"id": str(g.id), "name": g.name} for g in list(bot.guilds)]
        data = {
            "startedAt": started_at,
            "uptimeSeconds": uptime,
            "guildCount": len(guilds),
            "guilds": guilds,
            "uniqueUsers": self.unique_users(),
            "commandsTotal": total,
            "commandsMonth": month,
            "commandsToday": today,
            "updatedAt": now.isoformat(),
        }
        path = Path(self.json_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return data


stats_db = StatsDatabase()


class StatsLog(commands.Cog):
    """Logs every prefix / hybrid / slash command once and writes runtime_stats.json."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._seen = set()

    async def cog_load(self):
        self.flush_loop.start()

    async def cog_unload(self):
        self.flush_loop.cancel()

    def _log(self, name: str, user_id: int, key: str):
        if not name or key in self._seen:
            return
        self._seen.add(key)
        if len(self._seen) > 4000:
            self._seen.clear()
        stats_db.log_command(name, user_id)

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):
        if not ctx.command:
            return
        if ctx.interaction is not None:
            return
        key = f"p:{ctx.message.id if ctx.message else ctx.prefix}:{ctx.command.name}:{ctx.author.id}"
        self._log(ctx.command.name, ctx.author.id, key)

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command):
        name = getattr(command, "qualified_name", None) or getattr(command, "name", None)
        if not name or not interaction.user:
            return
        key = f"s:{interaction.id}:{name}:{interaction.user.id}"
        self._log(str(name).split()[0], interaction.user.id, key)

    @tasks.loop(seconds=60)
    async def flush_loop(self):
        try:
            stats_db.snapshot(self.bot)
        except Exception:
            pass

    @flush_loop.before_loop
    async def before_flush(self):
        await self.bot.wait_until_ready()
        if getattr(self.bot, "start_time", None) is None:
            self.bot.start_time = datetime.now(timezone.utc)
        stats_db.snapshot(self.bot)


async def setup(bot: commands.Bot):
    await bot.add_cog(StatsLog(bot))
