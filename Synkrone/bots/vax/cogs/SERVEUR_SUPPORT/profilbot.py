# -*- coding: utf-8 -*-
"""
Cog ProfilVax - Gestionnaire de statistiques et salons dédiés Vax v3
===================================================================
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

import discord
from colorama import Fore, Style, init
from discord.ext import commands, tasks

from utils.config_profilbot import EmbedManager
from utils.config_emoji import Emoji as E

# --- Configuration & Logs ---
DEBUG_MODE = True
ERROR_ONLY_MODE = False

init(autoreset=True)

GUILD_ID = 1368235294192570520
CATEGORY_ID = 1368622083093037066
PROFILE_CHANNEL_ID = 1533522816710873338
UPDATE_INTERVAL = 180
JSON_FILE = Path(__file__).resolve().parents[2] / "data" / "serv_support" / "profilbot.json"
STATS_DB_FILE = Path(__file__).resolve().parents[2] / "data" / "serv_support" / "profilbot_stats.db"


class ProfilVax(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.embed_manager = None
        self.target_message_id: Optional[int] = None

    def _load_json_data(self) -> dict:
        if not JSON_FILE.exists():
            return {}
        try:
            with open(JSON_FILE, "r", encoding="utf-8") as f:
                payload = json.load(f)
            return payload if isinstance(payload, dict) else {}
        except Exception as e:
            if not ERROR_ONLY_MODE or DEBUG_MODE:
                print(f"{Fore.RED}[PROFILVAX ERROR] Impossible de lire le fichier JSON : {e}{Style.RESET_ALL}")
            return {}

    def _ensure_stats_db(self) -> None:
        try:
            STATS_DB_FILE.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(str(STATS_DB_FILE)) as conn:
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS command_stats (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id BIGINT NOT NULL,
                        command_name TEXT NOT NULL,
                        timestamp TEXT NOT NULL
                    )"""
                )
                conn.commit()
        except Exception as e:
            if DEBUG_MODE:
                print(f"{Fore.RED}[PROFILVAX ERROR] Creation DB stats impossible: {e}{Style.RESET_ALL}")

    def _record_command_usage(self, user_id: int, command_name: str) -> None:
        if not command_name:
            return
        try:
            self._ensure_stats_db()
            now_utc = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            with sqlite3.connect(str(STATS_DB_FILE)) as conn:
                conn.execute(
                    "INSERT INTO command_stats (user_id, command_name, timestamp) VALUES (?, ?, ?)",
                    (int(user_id), str(command_name), now_utc),
                )
                conn.commit()
        except Exception as e:
            if DEBUG_MODE:
                print(f"{Fore.RED}[PROFILVAX ERROR] Ecriture stats commande impossible: {e}{Style.RESET_ALL}")

    def _save_json_data(self, guild_id: int, channel_id: int, message_id: int):
        try:
            JSON_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = self._load_json_data()
            saved_msg_id = int(message_id or 0)
            if saved_msg_id <= 0:
                previous = data.get(str(guild_id), {}) if isinstance(data, dict) else {}
                try:
                    saved_msg_id = int(previous.get("message_id") or 0)
                except Exception:
                    saved_msg_id = 0

            data[str(guild_id)] = {
                "channel_id": channel_id,
                "message_id": saved_msg_id
            }
            with open(JSON_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            if not ERROR_ONLY_MODE:
                print(f"{Fore.RED}[PROFILVAX ERROR] Erreur sauvegarde JSON : {e}{Style.RESET_ALL}")

    def _resolve_saved_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        data = self._load_json_data()
        guild_data = data.get(str(guild.id), {})

        for candidate in (guild_data.get("channel_id"), PROFILE_CHANNEL_ID):
            if not candidate:
                continue
            try:
                channel = guild.get_channel(int(candidate))
            except (TypeError, ValueError):
                channel = None
            if isinstance(channel, discord.TextChannel):
                try:
                    self.target_message_id = int(guild_data.get("message_id") or 0) or None
                except Exception:
                    self.target_message_id = None
                return channel
        return None

    async def _resolve_forced_channel(self) -> Optional[discord.TextChannel]:
        try:
            cached = self.bot.get_channel(PROFILE_CHANNEL_ID)
            if isinstance(cached, discord.TextChannel):
                return cached

            fetched = await self.bot.fetch_channel(PROFILE_CHANNEL_ID)
            if isinstance(fetched, discord.TextChannel):
                return fetched

            if DEBUG_MODE:
                print(
                    f"{Fore.YELLOW}[PROFILVAX INFO] Le channel force {PROFILE_CHANNEL_ID} n'est pas un salon texte "
                    f"(type={type(fetched).__name__}).{Style.RESET_ALL}"
                )
        except Exception as e:
            if DEBUG_MODE:
                print(f"{Fore.RED}[PROFILVAX ERROR] Resolution channel force impossible: {e}{Style.RESET_ALL}")
        return None

    def _resolve_category_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        category = guild.get_channel(CATEGORY_ID)
        if isinstance(category, discord.CategoryChannel):
            text_channels = sorted(category.text_channels, key=lambda ch: ch.position)
            if text_channels:
                return text_channels[0]
        return None

    def _resolve_named_channel(self, guild: discord.Guild) -> Optional[discord.TextChannel]:
        keywords = ("profil", "profile", "bot-profil", "bot-profile")
        candidates = [
            ch for ch in guild.text_channels
            if any(k in ch.name.lower() for k in keywords)
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda ch: ch.position)
        return candidates[0]

    async def _ensure_single_profile_message(self, channel: discord.TextChannel, keep_message_id: int):
        removed = 0
        async for message in channel.history(limit=200):
            if message.id == keep_message_id:
                continue
            try:
                await message.delete()
                removed += 1
            except discord.Forbidden:
                if DEBUG_MODE:
                    print(f"{Fore.YELLOW}[PROFILVAX INFO] Impossible de supprimer des messages dans #{channel.name} (permissions insuffisantes).{Style.RESET_ALL}")
                break
            except discord.HTTPException:
                continue

        if removed and DEBUG_MODE and not ERROR_ONLY_MODE:
            print(f"{Fore.CYAN}[PROFILVAX INFO] {removed} message(s) supprime(s) pour garder un seul profil.{Style.RESET_ALL}")

    @commands.Cog.listener()
    async def on_ready(self):
        self._ensure_stats_db()
        if not self.embed_manager:
            self.embed_manager = await EmbedManager.create(self.bot)

        channel = await self.ensure_environment()
        if channel:
            await self.refresh_status_message(channel)
        if not self.update_loop.is_running():
            self.update_loop.start()

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):
        try:
            if not ctx.command or not ctx.author or ctx.author.bot:
                return
            cmd_name = getattr(ctx.command, "qualified_name", None) or getattr(ctx.command, "name", "")
            self._record_command_usage(ctx.author.id, cmd_name)
        except Exception as e:
            if DEBUG_MODE:
                print(f"{Fore.RED}[PROFILVAX ERROR] Tracking prefix command impossible: {e}{Style.RESET_ALL}")

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command):
        try:
            user = interaction.user
            if not user or user.bot:
                return
            cmd_name = getattr(command, "qualified_name", None) or getattr(command, "name", "")
            self._record_command_usage(user.id, cmd_name)
        except Exception as e:
            if DEBUG_MODE:
                print(f"{Fore.RED}[PROFILVAX ERROR] Tracking slash command impossible: {e}{Style.RESET_ALL}")

    async def ensure_environment(self) -> Optional[discord.TextChannel]:
        try:
            channel = await self._resolve_forced_channel()

            guild = channel.guild if channel else self.bot.get_guild(GUILD_ID)
            if not guild and channel:
                guild = channel.guild
            if not guild:
                if DEBUG_MODE:
                    print(f"{Fore.YELLOW}[PROFILVAX INFO] Serveur cible introuvable (GUILD_ID={GUILD_ID}).{Style.RESET_ALL}")
                return None

            if not channel:
                channel = self._resolve_saved_channel(guild)
            if not channel:
                channel = self._resolve_category_channel(guild)
            if not channel:
                channel = self._resolve_named_channel(guild)

            if not channel:
                if DEBUG_MODE:
                    print(
                        f"{Fore.YELLOW}[PROFILVAX INFO] Aucun salon texte exploitable trouve pour le profil "
                        f"(sans creation automatique).{Style.RESET_ALL}"
                    )
                return None

            self._save_json_data(guild.id, channel.id, int(self.target_message_id or 0))
            if DEBUG_MODE and not ERROR_ONLY_MODE:
                print(f"{Fore.CYAN}[PROFILVAX INFO] Salon profil actif: #{channel.name} ({channel.id}){Style.RESET_ALL}")
            return channel
        except Exception as e:
            if DEBUG_MODE:
                print(f"{Fore.RED}[PROFILVAX ERROR] ensure_environment : {e}{Style.RESET_ALL}")
            return None

    async def refresh_status_message(self, channel: discord.TextChannel):
        guild = channel.guild
        try:
            view, file = await self.embed_manager.get_stats_layout(guild)
        except Exception as e:
            print(f"{Fore.RED}[PROFILVAX ERROR] Generation layout impossible: {e}{Style.RESET_ALL}")
            return

        data = self._load_json_data()
        guild_data = data.get(str(guild.id), {})
        profile_message: Optional[discord.Message] = None

        if guild_data.get('message_id'):
            try:
                message = await channel.fetch_message(guild_data['message_id'])
                if file:
                    await message.edit(view=view, attachments=[file])
                else:
                    await message.edit(view=view, attachments=[])
                profile_message = message
                self.target_message_id = message.id
                if DEBUG_MODE and not ERROR_ONLY_MODE:
                    print(f"{Fore.GREEN}[PROFILVAX SUCCESS] Message {guild_data['message_id']} mis à jour (LayoutV2){Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.YELLOW}[PROFILVAX INFO] Message cible invalide ou non editable ({guild_data['message_id']}): {e}{Style.RESET_ALL}")

        if profile_message is None and self.bot.user:
            async for message in channel.history(limit=50):
                if message.author.id == self.bot.user.id:
                    try:
                        if file:
                            await message.edit(view=view, attachments=[file])
                        else:
                            await message.edit(view=view, attachments=[])
                        profile_message = message
                        self.target_message_id = message.id
                        self._save_json_data(guild.id, channel.id, message.id)
                        if DEBUG_MODE and not ERROR_ONLY_MODE:
                            print(f"{Fore.GREEN}[PROFILVAX SUCCESS] Message profil existant {message.id} reutilise.{Style.RESET_ALL}")
                        break
                    except Exception as e:
                        print(f"{Fore.YELLOW}[PROFILVAX INFO] Message historique {message.id} non editable: {e}{Style.RESET_ALL}")

        if profile_message is None:
            profile_message = await self._send_new_message(channel, view, file)

        if profile_message is not None:
            await self._ensure_single_profile_message(channel, profile_message.id)

    async def _send_new_message(self, channel, view, file):
        try:
            if file:
                msg = await channel.send(view=view, file=file)
            else:
                msg = await channel.send(view=view)
            self.target_message_id = msg.id
            self._save_json_data(channel.guild.id, channel.id, msg.id)
            if DEBUG_MODE and not ERROR_ONLY_MODE:
                print(f"{Fore.GREEN}[PROFILVAX SUCCESS] Nouveau message {msg.id} déployé avec succès.{Style.RESET_ALL}")
            return msg
        except Exception as e:
            print(f"{Fore.RED}[PROFILVAX ERROR] Échec de l'envoi du message : {e}{Style.RESET_ALL}")
            return None

    @tasks.loop(seconds=UPDATE_INTERVAL)
    async def update_loop(self):
        try:
            channel = await self.ensure_environment()
            if channel:
                await self.refresh_status_message(channel)
            elif DEBUG_MODE:
                print(f"{Fore.YELLOW}[PROFILVAX INFO] update_loop: aucun salon profil resolu.{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}[PROFILVAX LOOP ERROR] {e}{Style.RESET_ALL}")

    @update_loop.before_loop
    async def before_update_loop(self):
        await self.bot.wait_until_ready()

    def cog_unload(self):
        self.update_loop.cancel()


async def setup(bot):
    await bot.add_cog(ProfilVax(bot))