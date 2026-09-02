"""
MUSIC BOT - Vax v3 Edition
===========================
Cog de lecture musicale moderne utilisant Layout V2, configurations centralisées,
système de vote pour le skip (2 secondes si seul dans le vocal), file d'attente complète,
modals pour Ajouter et Playlist (+5), et journalisation colorée.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import traceback
from typing import Any

import discord
from discord import ui
from discord.ext import commands
import yt_dlp

from utils.config_theme import config_manager
from utils.config_emoji import Emoji as E

# --- 1. CONFIGURATION DES LOGS & EMOJIS (Directive 1.a, 1.b & 1.c) ---
DEBUG_LOGS_ENABLED = True
ERROR_LOGS_ONLY = False

EMOJI_PLAY = "▶️"
EMOJI_ADD = getattr(E, "AJOUTER", "➕")
EMOJI_PLAYLIST = getattr(E, "HISTOIRE", "📜")
EMOJI_SKIP = "⏭️"
EMOJI_ERROR = getattr(E, "ERREUR", "❌")
EMOJI_SUCCESS = getattr(E, "VALIDE", "✅")
EMOJI_CONSOLE = "🎙️"
EMOJI_QUEUE = getattr(E, "LISTE", "📋")
EMOJI_VOTE = "🗳️"

# --- UTILITAIRES DE LOGS COLORÉS (Directive 4.b) ---
def _log_debug(message: str) -> None:
    if DEBUG_LOGS_ENABLED:
        print(f"\033[36m[DEBUG][MusicBot] {message}\033[0m")

def _log_success(message: str) -> None:
    if not ERROR_LOGS_ONLY:
        print(f"\033[32m[SUCCESS][MusicBot] {message}\033[0m")

def _log_error(message: str) -> None:
    print(f"\033[31m[ERROR][MusicBot] {message}\033[0m")


# --- CONFIGURATION HÉBERGEUR & YTDLP ---
FFMPEG_EXECUTABLE = "ffmpeg" 

YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'nocheckcertificate': True,
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -filter:a "volume=0.5"'
}


# --- 1. MODAL DE SAISIE POUR 1 MUSIQUE (BOUTON AJOUTER) ---
class MusicModal(ui.Modal, title="Ajouter une musique"):
    url_input = ui.TextInput(
        label="Lien ou recherche",
        placeholder="Artiste, titre ou URL YouTube...",
        required=True
    )

    def __init__(self, cog: MusicBot, ctx: commands.Context):
        super().__init__()
        self.cog = cog
        self.ctx = ctx

    async def on_submit(self, interaction: discord.Interaction):
        _log_debug(f"Modal 'MusicModal' soumis par {interaction.user} avec la valeur : {self.url_input.value}")
        try:
            await interaction.response.defer()
            await self.cog.execute_play(self.ctx, self.url_input.value)
            await interaction.channel.send(f"{EMOJI_SUCCESS} Requête envoyée pour : `{self.url_input.value}`", delete_after=3)
        except Exception as e:
            _log_error(f"Erreur critique dans le callback du MusicModal : {e}")
            print(f"\033[31m[CRITICAL_ERROR][MusicModal] {e}\033[0m")
            await interaction.channel.send(f"{EMOJI_ERROR} Une erreur est survenue lors de l'ajout de la musique : `{e}`", delete_after=5)


# --- 1.1. MODAL DE PLAYLIST (+5 MUSIQUES) ---
class PlaylistModal(ui.Modal, title="Ajouter une playlist (5 musiques)"):
    keyword_input = ui.TextInput(
        label="Mot-clé ou lien",
        placeholder="Entrez un mot-clé pour générer 5 musiques...",
        required=True,
        max_length=100
    )

    def __init__(self, cog: MusicBot, ctx: commands.Context):
        super().__init__()
        self.cog = cog
        self.ctx = ctx

    async def on_submit(self, interaction: discord.Interaction):
        _log_debug(f"Modal 'PlaylistModal' soumis par {interaction.user} avec le mot-clé : {self.keyword_input.value}")
        try:
            await interaction.response.defer()
            await self.cog.generate_playlist(self.ctx, self.keyword_input.value, count=5)
            await interaction.channel.send(f"{EMOJI_SUCCESS} Ajout de 5 musiques en cours pour `{self.keyword_input.value}`...", delete_after=3)
        except Exception as e:
            _log_error(f"Erreur critique dans le callback du PlaylistModal : {e}")
            print(f"\033[31m[CRITICAL_ERROR][PlaylistModal] {e}\033[0m")
            await interaction.channel.send(f"{EMOJI_ERROR} Une erreur est survenue lors de la génération de la playlist : `{e}`", delete_after=5)


# --- 2. CONTRÔLES DE LA CONSOLE (Layout V2 - Directive 2.a) ---
class AddButton(ui.Button):
    def __init__(self, cog: MusicBot, ctx: commands.Context, owner_id: int):
        super().__init__(label="Ajouter", style=discord.ButtonStyle.success, emoji=EMOJI_ADD, custom_id="music:add")
        self.cog = cog
        self.ctx = ctx
        self.owner_id = owner_id

    async def callback(self, interaction: discord.Interaction):
        _log_debug(f"Bouton 'Ajouter' cliqué par {interaction.user}")
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(f"{EMOJI_ERROR} Ce menu ne vous appartient pas.", ephemeral=True)
            return
        try:
            modal = MusicModal(self.cog, self.ctx)
            await interaction.response.send_modal(modal)
            _log_success("Modal 'MusicModal' ouvert avec succès.")
        except Exception as e:
            _log_error(f"Erreur lors de l'ouverture du MusicModal : {e}")
            traceback.print_exc()
            if not interaction.response.is_done():
                await interaction.response.send_message(f"{EMOJI_ERROR} Impossible d'ouvrir le formulaire : `{e}`", ephemeral=True)


class PlaylistButton(ui.Button):
    def __init__(self, cog: MusicBot, ctx: commands.Context, owner_id: int):
        super().__init__(label="Playlist (+5)", style=discord.ButtonStyle.primary, emoji=EMOJI_PLAYLIST, custom_id="music:playlist")
        self.cog = cog
        self.ctx = ctx
        self.owner_id = owner_id

    async def callback(self, interaction: discord.Interaction):
        _log_debug(f"Bouton 'Playlist (+5)' cliqué par {interaction.user}")
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(f"{EMOJI_ERROR} Ce menu ne vous appartient pas.", ephemeral=True)
            return
        try:
            modal = PlaylistModal(self.cog, self.ctx)
            await interaction.response.send_modal(modal)
            _log_success("Modal 'PlaylistModal' ouvert avec succès.")
        except Exception as e:
            _log_error(f"Erreur lors de l'ouverture du PlaylistModal : {e}")
            traceback.print_exc()
            if not interaction.response.is_done():
                await interaction.response.send_message(f"{EMOJI_ERROR} Impossible d'ouvrir le formulaire de playlist : `{e}`", ephemeral=True)


class VoteSkipButton(ui.Button):
    def __init__(self, cog: MusicBot, ctx: commands.Context, owner_id: int):
        super().__init__(label="Voter pour passer (3+)", style=discord.ButtonStyle.secondary, emoji=EMOJI_VOTE, custom_id="music:vote_skip")
        self.cog = cog
        self.ctx = ctx
        self.owner_id = owner_id

    async def callback(self, interaction: discord.Interaction):
        _log_debug(f"Bouton 'Voter pour passer' cliqué par {interaction.user}")
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(f"{EMOJI_ERROR} Ce menu ne vous appartient pas.", ephemeral=True)
            return
        try:
            await self.cog.handle_vote_skip(self.ctx, interaction)
        except Exception as e:
            _log_error(f"Erreur lors du traitement du vote de skip : {e}")
            traceback.print_exc()


class PlayControls(ui.LayoutView):
    def __init__(self, cog: MusicBot, ctx: commands.Context, owner_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.ctx = ctx
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            _log_error(f"Interaction bloquée pour {interaction.user} (propriétaire attendu : {self.owner_id})")
            await interaction.response.send_message(f"{EMOJI_ERROR} Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        return True

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: ui.Item | None) -> None:
        _log_error(f"Erreur d'interaction sur {item}: {error}")
        traceback.print_exc()
        if not interaction.response.is_done():
            await interaction.response.send_message(f"{EMOJI_ERROR} Une erreur technique est survenue pendant l'interaction.", ephemeral=True)


# --- 4. LE COG MUSIQUE ---
class MusicBot(commands.Cog):
    """Cog de gestion de la musique entièrement refondu sous l'architecture Vax v3."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.queues: dict[int, list[dict[str, Any]]] = {}
        self.current_tracks: dict[int, dict[str, Any] | None] = {}
        self.interfaces: dict[int, discord.Message] = {}
        self.skip_votes: dict[int, set[int]] = {}
        self.idle_tasks: dict[int, asyncio.Task] = {}
        
        if shutil.which(FFMPEG_EXECUTABLE):
            _log_success("FFmpeg détecté avec succès sur le système.")
        else:
            _log_error("FFmpeg est introuvable sur cet hébergeur.")
            print("\033[31m[CRITICAL_ERROR][MusicBot] FFmpeg introuvable dans le PATH système.\033[0m")

    def get_data(self, guild_id: int):
        if guild_id not in self.queues:
            self.queues[guild_id] = []
            self.current_tracks[guild_id] = None
            self.interfaces[guild_id] = None
            self.skip_votes[guild_id] = set()

    def _normalize_track_key(self, track: dict[str, Any] | None) -> str:
        if not track:
            return ""
        for key in ("id", "url", "webpage_url", "stream", "title"):
            value = track.get(key)
            if value:
                return str(value).strip().lower()
        return ""

    def _track_matches(self, first: dict[str, Any] | None, second: dict[str, Any] | None) -> bool:
        if not first or not second:
            return False

        first_key = self._normalize_track_key(first)
        second_key = self._normalize_track_key(second)
        if first_key and second_key and first_key == second_key:
            return True

        title_a = (first.get("title") or "").strip().lower()
        title_b = (second.get("title") or "").strip().lower()
        return bool(title_a and title_b and title_a == title_b)

    def _is_duplicate_track(self, guild_id: int, data: dict[str, Any]) -> bool:
        if self._track_matches(self.current_tracks.get(guild_id), data):
            return True
        return any(self._track_matches(track, data) for track in self.queues.get(guild_id, []))

    def _cancel_idle_timer(self, guild_id: int):
        task = self.idle_tasks.pop(guild_id, None)
        if task and not task.done():
            task.cancel()

    def _start_idle_timer(self, ctx: commands.Context):
        gid = ctx.guild.id
        self._cancel_idle_timer(gid)

        async def idle_disconnect():
            try:
                await asyncio.sleep(180)  # 3 minutes d'inactivité
                if ctx.voice_client and not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
                    self.queues[gid] = []
                    self.current_tracks[gid] = None
                    await ctx.voice_client.disconnect()
                    _log_success(f"Déconnexion automatique pour inactivité sur le serveur {ctx.guild.name}")
                    await ctx.send(f"{EMOJI_ERROR} Déconnexion automatique après 3 minutes d'inactivité.", delete_after=5)
            except asyncio.CancelledError:
                pass

        self.idle_tasks[gid] = self.bot.loop.create_task(idle_disconnect())

    async def update_display(self, ctx: commands.Context, status_text: str, force_new_message: bool = False):
        gid = ctx.guild.id
        self.get_data(gid)

        theme = config_manager.get_layout_v2_theme(gid, ctx.guild, ctx.author, self.bot)
        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text", "")

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {EMOJI_CONSOLE} Console Musicale - {status_text}"))

        track = self.current_tracks[gid]
        is_playing = bool(track and ctx.voice_client and (ctx.voice_client.is_playing() or ctx.voice_client.is_paused()))

        view_owner_id = ctx.author.id if hasattr(ctx, "author") and ctx.author else self.bot.user.id

        # --- BOUTONS PLACÉS DANS LE LAYOUT SOUS LE TITRE (ACTION ROW) ---
        row = ui.ActionRow()
        row.add_item(AddButton(self, ctx, view_owner_id))
        if is_playing:
            row.add_item(VoteSkipButton(self, ctx, view_owner_id))

        row.add_item(PlaylistButton(self, ctx, view_owner_id))
        container.add_item(row)
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

        if track:
            votes_count = len(self.skip_votes.get(gid, set()))
            container.add_item(ui.TextDisplay(f"### 🎵 En cours\n[{track['title']}]({track['url']}) | 🗳️ Votes de skip : `{votes_count}/3`"))
        else:
            container.add_item(ui.TextDisplay(f"### 🎵 En cours\n*Aucune musique en lecture.*"))

        queue = self.queues[gid]
        if queue:
            q_list = "\n".join([f"**{i+1}.** {t['title']}" for i, t in enumerate(queue[:10])])
            container.add_item(ui.TextDisplay(f"### {EMOJI_QUEUE} File d'attente ({len(queue)})\n{q_list}"))
        else:
            container.add_item(ui.TextDisplay(f"### {EMOJI_QUEUE} File d'attente\n*La file est actuellement vide.*"))

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        view = PlayControls(self, ctx, view_owner_id)
        view.add_item(container)

        if force_new_message:
            self.interfaces[gid] = await ctx.send(view=view)
        else:
            if self.interfaces[gid]:
                try:
                    await self.interfaces[gid].edit(view=view)
                except Exception as e:
                    _log_error(f"Erreur lors de l'édition du message de la console : {e}")
                    print(f"\033[31m[CRITICAL_ERROR][UpdateDisplay] {e}\033[0m")
                    self.interfaces[gid] = await ctx.send(view=view)
            else:
                self.interfaces[gid] = await ctx.send(view=view)

    @commands.command(name="play", description="Interface de contrôle et lecture musicale")
    async def play(self, ctx: commands.Context, *, search: str = None):
        if not ctx.guild:
            await ctx.send(f"{EMOJI_ERROR} Cette commande doit être utilisée sur un serveur.")
            return

        if not ctx.author.voice:
            await ctx.send(f"{EMOJI_ERROR} Vous devez être connecté dans un salon vocal pour utiliser cette commande.")
            return

        _log_debug(f"Commande 'play' invoquée par {ctx.author} avec la recherche : {search}")

        if search is None:
            await self.update_display(ctx, "Console active", force_new_message=True)
        else:
            await self.execute_play(ctx, search)

    async def execute_play(self, ctx: commands.Context, search: str):
        gid = ctx.guild.id
        self.get_data(gid)
        if not ctx.voice_client: 
            await ctx.author.voice.channel.connect()

        self._cancel_idle_timer(gid)

        async with ctx.typing():
            try:
                with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                    info = ydl.extract_info(search, download=False)
                    if 'entries' in info: 
                        info = info['entries'][0]
                    data = {
                        'id': info.get('id'),
                        'title': info.get('title', 'Musique'),
                        'url': info.get('webpage_url'),
                        'stream': info.get('url'),
                        'thumb': info.get('thumbnail')
                    }

                if self._is_duplicate_track(gid, data):
                    _log_debug(f"Piste  déjà présente, ignorée : {data['title']}")
                    await ctx.send(f"{EMOJI_ERROR} Cette musique est  déjà en cours ou dans la file d'attente.", delete_after=3)
                    return

                if ctx.voice_client.is_playing() or ctx.voice_client.is_paused():
                    self.queues[gid].append(data)
                    _log_success(f"Piste ajoutée à la file pour le serveur {ctx.guild.name}: {data['title']}")
                    await self.update_display(ctx, "Ajouté à la file")
                else:
                    await self.start_playing(ctx, data)
            except Exception as e:
                _log_error(f"Erreur lors de l'exécution de execute_play : {e}")
                print(f"\033[31m[CRITICAL_ERROR][ExecutePlay] {e}\033[0m")
                await ctx.send(f"{EMOJI_ERROR} Erreur technique : `{e}`", delete_after=5)

    async def start_playing(self, ctx: commands.Context, data: dict[str, Any]):
        gid = ctx.guild.id
        self.current_tracks[gid] = data
        self.skip_votes[gid] = set()
        self._cancel_idle_timer(gid)
        
        try:
            source = discord.FFmpegOpusAudio(
                data['stream'], 
                executable=FFMPEG_EXECUTABLE, 
                **FFMPEG_OPTIONS
            )
            ctx.voice_client.play(source, after=lambda e: self.bot.loop.create_task(self.play_next(ctx)))
            _log_success(f"Lecture démarrée sur {ctx.guild.name} : {data['title']}")
            await self.update_display(ctx, "Lecture en cours")
        except Exception as e:
            _log_error(f"Erreur technique FFmpeg lors de la lecture : {e}")
            print(f"\033[31m[CRITICAL_ERROR][StartPlaying] {e}\033[0m")
            await ctx.send(f"{EMOJI_ERROR} Erreur technique FFmpeg : `{e}`")

    async def handle_vote_skip(self, ctx: commands.Context, interaction: discord.Interaction):
        gid = ctx.guild.id
        self.get_data(gid)

        if not ctx.voice_client or not ctx.voice_client.is_playing():
            await interaction.channel.send(f"{EMOJI_ERROR} Rien n'est joué actuellement !", delete_after=3)
            await interaction.response.defer()
            return

        channel = ctx.author.voice.channel if ctx.author.voice else None
        if not channel or ctx.voice_client.channel.id != channel.id:
            await interaction.channel.send(f"{EMOJI_ERROR} Vous devez être dans le même salon vocal que le bot pour voter.", delete_after=3)
            await interaction.response.defer()
            return

        members_in_vc = [m for m in channel.members if not m.bot]
        is_alone = len(members_in_vc) == 1

        voters = self.skip_votes[gid]
        if interaction.user.id in voters:
            await interaction.channel.send(f"⚠️ Vous avez  déjà voté pour passer cette musique.", delete_after=3)
            await interaction.response.defer()
            return

        voters.add(interaction.user.id)

        if is_alone:
            await interaction.channel.send(f"{EMOJI_SKIP} Utilisateur seul dans le vocal : passage de la musique dans 2 secondes...", delete_after=3)
            await interaction.response.defer()
            await asyncio.sleep(2)
            if ctx.voice_client and ctx.voice_client.is_playing():
                ctx.voice_client.stop()
            return

        required_votes = 3
        _log_debug(f"Vote de skip enregistré pour {interaction.user} ({len(voters)}/{required_votes})")

        if len(voters) >= required_votes:
            ctx.voice_client.stop()
            await interaction.channel.send(f"{EMOJI_SKIP} Seuil requis atteint ({len(voters)}/{required_votes} votes). Musique passée !", delete_after=3)
            await interaction.response.defer()
        else:
            await interaction.channel.send(f"{EMOJI_VOTE} {interaction.user.mention} a voté pour passer (`{len(voters)}/{required_votes}` requis).", delete_after=4)
            await interaction.response.defer()
            await self.update_display(ctx, "Vote en cours")

    async def generate_playlist(self, ctx: commands.Context, keyword: str, count: int = 5):
        gid = ctx.guild.id
        self.get_data(gid)
        
        if not ctx.voice_client: 
            await ctx.author.voice.channel.connect()

        self._cancel_idle_timer(gid)
        
        search_queries = [
            f"{keyword} music", f"{keyword} songs", f"best {keyword}", f"top {keyword}",
            f"{keyword} playlist", f"{keyword} mix", f"{keyword} compilation", f"{keyword} hits"
        ]
        
        added_count = 0
        failed_count = 0
        
        async with ctx.typing():
            for i, query in enumerate(search_queries[:count]):
                try:
                    with yt_dlp.YoutubeDL(YDL_OPTIONS) as ydl:
                        info = ydl.extract_info(query, download=False)
                        if 'entries' in info: 
                            info = info['entries'][0]
                        
                        data = {
                            'id': info.get('id'),
                            'title': info.get('title', f'Musique {i+1}'),
                            'url': info.get('webpage_url'),
                            'stream': info.get('url'),
                            'thumb': info.get('thumbnail')
                        }

                        if self._is_duplicate_track(gid, data):
                            _log_debug(f"Piste de playlist  déjà présente, ignorée : {data['title']}")
                            continue
                        
                        self.queues[gid].append(data)
                        added_count += 1
                except Exception as e:
                    failed_count += 1
                    _log_error(f"Échec extraction recherche playlist '{query}': {e}")
                    print(f"\033[31m[ERROR][GeneratePlaylist] {e}\033[0m")
                    continue
        
        if not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused() and self.queues[gid]:
            first_track = self.queues[gid].pop(0)
            await self.start_playing(ctx, first_track)
        else:
            await self.update_display(ctx, f"Playlist ajoutée (+{added_count})")
        
        _log_success(f"Playlist générée pour {ctx.guild.name}: {added_count} ajoutées, {failed_count} échecs.")
        await ctx.send(f"{EMOJI_SUCCESS} **{added_count}** musiques ajoutées à la file !{f' ({failed_count} échecs)' if failed_count > 0 else ''}", delete_after=5)

    async def play_next(self, ctx: commands.Context):
        gid = ctx.guild.id
        if gid in self.queues and self.queues[gid]:
            next_track = self.queues[gid].pop(0)
            _log_debug(f"Passage à la piste suivante sur {ctx.guild.name}")
            await self.start_playing(ctx, next_track)
        else:
            self.current_tracks[gid] = None
            self.skip_votes[gid] = set()
            _log_debug(f"Fin de la file d'attente sur {ctx.guild.name}")
            await self.update_display(ctx, "Lecture terminée")
            self._start_idle_timer(ctx)


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicBot(bot))
    _log_success("Cog MusicBot chargé avec succès.")