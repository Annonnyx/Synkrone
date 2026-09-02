import discord
from discord.ext import commands
from discord import ui
import os
import json
import time
from datetime import datetime, timedelta

# ===================== CONFIG MANAGER ========================
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

from cogs.casino.autres.achievements import (
    ACHIEVEMENTS, load_user_data, get_achievement_stats,
    build_achievement_pages, get_counter, tier_label,
    get_level, get_xp_progress, get_hourly_limit
)
from cogs.casino.admin.adminlimit import get_admin_hourly_limit

# ── HELPERS ─────────────────────────────────────────────────

def format_y(value: int) -> str:
    return f"{value:,}".replace(',', ' ')


def _progress_bar(current: int, total: int, length: int = 10) -> str:
    if total <= 0:
        return "▰" * length
    filled = max(0, min(length, int(length * current / total)))
    return "▰" * filled + "▱" * (length - filled)


def _get_embed(bot, guild, member, title, description):
    return bot.config.get_formatted_embed(
        title=title, description=description,
        bot_user=bot.user, guild=guild, user=member,
        target_id=guild.id if guild else None
    )

def _cooldown_str(last_iso: str | None, cooldown_h: float) -> str:
    """Retourne une chaîne de statut lisible pour un cooldown."""
    if not last_iso:
        return "✅ Disponible"
    try:
        last_dt = datetime.fromisoformat(last_iso)
        if last_dt.tzinfo is None:
            last_dt = last_dt.astimezone()
        diff = datetime.now().astimezone() - last_dt
        secs = cooldown_h * 3600 - diff.total_seconds()
        if secs <= 0:
            return "✅ Disponible"
        h, r = divmod(int(secs), 3600)
        m = r // 60
        return f"⏳ {h}h {m}m"
    except Exception:
        return "✅ Disponible"

def _cooldown_ts(last_ts: float, cooldown_s: int) -> str:
    rem = cooldown_s - (time.time() - last_ts)
    if rem <= 0:
        return "✅ Disponible"
    h, r = divmod(int(rem), 3600)
    m = r // 60
    return f"⏳ {h}h {m}m"

# ── STATISTIQUES DÉTAILLÉES PAR COMMANDE ──────────────────────────────────

def get_command_stats(data: dict) -> dict:
    """Collecte les statistiques détaillées pour chaque commande"""
    stats = data.get("stats", {})
    
    command_stats = {
        "🪙 Coinflip": {
            "emoji": "🪙",
            "command": "/coinflip",
            "parties_total": len(data.get("coinflip_stats", {}).get("parties_heure", [])),
            "derniere_heure": len(data.get("coinflip_stats", {}).get("parties_heure", [])),
            "description": "Jeu de pile ou face avec mise"
        },
        "💣 Mines": {
            "emoji": "💣",
            "command": "/mines",
            "parties_total": len(data.get("mines_stats", {}).get("parties_heure", [])),
            "derniere_heure": len(data.get("mines_stats", {}).get("parties_heure", [])),
            "description": "Jeu de déminage avec grille"
        },
        "🎰 Slots": {
            "emoji": "🎰",
            "command": "/slots",
            "parties_total": len(data.get("slots_stats", {}).get("parties_heure", [])),
            "derniere_heure": len(data.get("slots_stats", {}).get("parties_heure", [])),
            "description": "Machine à sous classique"
        },
        "🃏 Blackjack": {
            "emoji": "🃏",
            "command": "/blackjack",
            "parties_total": len(data.get("blackjack_stats", {}).get("parties_heure", [])),
            "derniere_heure": len(data.get("blackjack_stats", {}).get("parties_heure", [])),
            "description": "Jeu de 21 contre le casino"
        },
        "🎲 Roulette": {
            "emoji": "🎲",
            "command": "/roulette",
            "parties_total": len(data.get("roulette_stats", {}).get("parties_heure", [])),
            "derniere_heure": len(data.get("roulette_stats", {}).get("parties_heure", [])),
            "description": "Roulette européenne avec mises variées"
        },
        "🏮 LanternFall": {
            "emoji": "🏮",
            "command": "/lanternfall",
            "parties_total": 1 if data.get("last_lantern_ts", 0) > 0 else 0,
            "derniere_heure": 1 if data.get("last_lantern_ts", 0) > time.time() - 3600 else 0,
            "description": "Jeu d'énigmes avec lanternes"
        },
        "📦 MysteriBox": {
            "emoji": "📦",
            "command": "/mysteribox",
            "parties_total": data.get("mysteribox_limits", {}).get("daily_count", 0),
            "derniere_heure": len(data.get("mysteribox_limits", {}).get("last_openings", [])),
            "description": "Coffres mystères avec récompenses aléatoires"
        },
        "🦹 Rob": {
            "emoji": "🦹",
            "command": "/rob",
            "parties_total": stats.get("rob_success", 0) + stats.get("rob_backfire", 0),
            "derniere_heure": len(data.get("rob_data", {}).get("hourly_robs", [])),
            "description": "Vol d'autres joueurs avec risques"
        }
    }
    
    return command_stats

# ── ACTIVITÉ ─────────────────────────────────────────────────

ACTIVITY_COOLDOWNS = [
    # (label, data_key, type, valeur)
    # type "iso"    = clé ISO string,  valeur = heures de cooldown
    # type "ts"     = timestamp float, valeur = secondes de cooldown
    # type "hourly" = stats_key contenant une liste parties_heure, valeur = max/heure
    # type "rob"    = rob_data.hourly_robs, valeur = max/heure
    # type "daily"  = limits avec daily_count et last_reset, valeur = max/jour
    # type "none"   = pas de limite
    ("🎁 Daily",        "last_daily",          "iso",    24),
    ("📅 Weekly",       "last_weekly",         "iso",    168),
    ("⏰ Hourly",       "last_hourly",         "iso",    1),
    ("🗓️ Monthly",     "last_monthly",        "iso",    720),
    ("🏮 LanternFall",  "last_lantern_ts",     "ts",     3600),
    ("🪙 Coinflip",     "coinflip_stats",      "hourly", 20),
    ("💣 Mines",        "mines_stats",         "hourly", 20),
    ("🎰 Slots",        "slots_stats",         "hourly", 20),
    ("🃏 Blackjack",    "blackjack_stats",     "hourly", 20),
    ("🎲 Roulette",     "roulette_stats",      "hourly", 20),
    ("📦 MysteriBox",   "mysteribox_limits",   "daily",  3),
    ("🦹 Rob",          "rob_data",            "rob",    5),
]

def _count_recent_plays(parties_heure: list) -> int:
    """Compte les parties jouées dans la dernière heure."""
    try:
        cutoff = datetime.now() - timedelta(hours=1)
        return sum(1 for p in parties_heure if datetime.fromisoformat(p) > cutoff)
    except Exception:
        return 0

ACTIVITY_STATS_KEYS = [
    ("🎮 Parties jouées (total)", "total_games", "/blackjack, /coinflip, /mines, /slots, /roulette, /lanternfall, /mysteribox"),
    ("🏆 Victoires (total)",      "total_wins", "/blackjack, /coinflip, /mines, /slots, /roulette, /lanternfall, /mysteribox"),
    ("💴 Total misé",             "Cols_spent", "/blackjack, /coinflip, /mines, /slots, /roulette, /lanternfall, /mysteribox"),
    ("📅 Daily consécutifs",      "daily_streak", "/daily"),
    ("📅 Total daily",            "daily_count", "/daily"),
    ("🦹 Vols réussis",           "rob_success", "/rob"),
    ("🚨 Vols ratés (pris)",      "rob_backfire", "/rob"),
]

def build_activity_embed(bot, guild, member, data):
    stats = data.get("stats", {})

    # ── Cooldowns
    cd_lines = []
    for label, key, kind, value in ACTIVITY_COOLDOWNS:
        if kind == "iso":
            status = _cooldown_str(data.get(key), value)
        elif kind == "ts":
            ts = data.get(key, 0)
            status = _cooldown_ts(ts, value)
        elif kind == "hourly":
            stats_block = data.get(key, {})
            plays = stats_block.get("parties_heure", [])
            played = _count_recent_plays(plays)
            game = key.replace("_stats", "")
            limit = get_admin_hourly_limit(guild.id, game, get_hourly_limit(data))
            if limit is None:
                status = "✅ Illimité"
            else:
                remaining = max(0, limit - played)
                if remaining == 0:
                    try:
                        dt_list = [datetime.fromisoformat(p) for p in plays]
                        oldest = min(dt_list)
                        rem_s = max(0, 3600 - (datetime.now() - oldest).total_seconds())
                        h, r = divmod(int(rem_s), 3600)
                        m = r // 60
                        status = f"⏳ {h}h {m:02d}m"
                    except Exception:
                        status = "⏳ ~1h"
                else:
                    status = f"✅ {remaining}/{limit} restantes"
        elif kind == "rob":
            rob_data = data.get("rob_data", {})
            raw = rob_data.get("hourly_robs", [])
            now_dt = datetime.now()
            cutoff = now_dt - timedelta(hours=1)
            hourly = [t for t in raw if datetime.fromisoformat(t) > cutoff]
            remaining = max(0, value - len(hourly))
            if remaining == 0:
                try:
                    oldest = min(datetime.fromisoformat(t) for t in hourly)
                    rem_s = max(0, 3600 - (now_dt - oldest).total_seconds())
                    h, r = divmod(int(rem_s), 3600)
                    m = r // 60
                    status = f"⏳ {h}h {m:02d}m"
                except Exception:
                    status = "⏳ ~1h"
            else:
                status = f"✅ {remaining}/{value} restants"
        elif kind == "daily":
            limits_data = data.get(key, {})
            daily_count = limits_data.get("daily_count", 0)
            last_openings = limits_data.get("last_openings", [])
            last_reset = limits_data.get("last_reset", "")
            today = datetime.now().strftime("%Y-%m-%d")
            # Vérifier si on est sur un nouveau jour
            if last_reset != today:
                daily_count = 0
            remaining = max(0, value - daily_count)
            if remaining == 0:
                # Calculer temps jusqu'à minuit
                now = datetime.now()
                midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
                rem_s = (midnight - now).total_seconds()
                h, r = divmod(int(rem_s), 3600)
                m = r // 60
                status = f"⏳ {h}h {m:02d}m (demain)"
            else:
                # Vérifier cooldown 8h entre ouvertures
                if last_openings:
                    try:
                        last_opening = datetime.fromisoformat(last_openings[-1])
                        time_since = datetime.now() - last_opening
                        if time_since < timedelta(hours=8):
                            rem = timedelta(hours=8) - time_since
                            h = int(rem.total_seconds() // 3600)
                            m = int((rem.total_seconds() % 3600) // 60)
                            status = f"⏳ {h}h {m}m (8h cd)"
                        else:
                            status = f"✅ {remaining}/{value} restants"
                    except Exception:
                        status = f"✅ {remaining}/{value} restants"
                else:
                    status = f"✅ {remaining}/{value} restants"
        elif kind == "none":
            status = "✅ Illimité"
        else:
            status = "✅ Disponible"
        cd_lines.append(f"**{label}** : {status}")

    # ── Compteurs
    stat_lines = []
    for label, key in ACTIVITY_STATS_KEYS:
        val = stats.get(key, 0)
        stat_lines.append(f"**{label}** : `{format_y(val)}`")

    description = (
        "**── Cooldowns ──**\n"
        + "\n".join(cd_lines)
        + "\n\n**── Statistiques ──**\n"
        + "\n".join(stat_lines)
    )
    embed = _get_embed(bot, guild, member,
                       f"📊 Activité — {member.display_name}", description)
    embed.set_thumbnail(url=member.display_avatar.url)
    return embed

# ── VUE PRINCIPALE ───────────────────────────────────────────

class ProfilSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Profil",   value="profil",   emoji="⚔️",  description="Vos statistiques générales"),
            discord.SelectOption(label="Cooldowns", value="cooldowns", emoji="⏳",  description="Tous vos cooldowns de jeux"),
            discord.SelectOption(label="Statistiques", value="stats", emoji="📊",  description="Toutes vos statistiques de jeux"),
            discord.SelectOption(label="Classement", value="classement", emoji="🥇", description="Votre position dans les classements"),
            discord.SelectOption(label="Succès",    value="succes",   emoji="🏆",  description="Vos achievements débloqués"),
        ]
        super().__init__(placeholder="📍 Choisissez un onglet...", options=options)

    async def callback(self, interaction: discord.Interaction):
        view: ProfilView = self.view
        if interaction.user.id != view.invoker_id:
            return await interaction.response.send_message("❌ Ce profil ne vous appartient pas.", ephemeral=True)
        onglet = self.values[0]
        view.onglet = onglet
        if onglet == "succes":
            view.succes_page = 0
        view.update_buttons()
        embed = view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)

class ProfilView(ui.View):
    def __init__(self, bot, guild, member, data, invoker_id):
        super().__init__(timeout=120)
        self.bot = bot
        self.guild = guild
        self.member = member
        self.data = data
        self.invoker_id = invoker_id
        self.onglet = "profil"
        self.succes_page = 0
        self._succes_pages = build_achievement_pages(data)

        self.add_item(ProfilSelect())
        self._btn_prev = ui.Button(label="◀", style=discord.ButtonStyle.gray, row=1)
        self._btn_prev.callback = self._prev
        self._btn_next = ui.Button(label="▶", style=discord.ButtonStyle.gray, row=1)
        self._btn_next.callback = self._next
        self.update_buttons()

    def update_buttons(self):
        # Retire les boutons de pagination s'ils sont déjà là
        for item in list(self.children):
            if item in (self._btn_prev, self._btn_next):
                self.remove_item(item)
        if self.onglet == "succes" and len(self._succes_pages) > 1:
            self._btn_prev.disabled = self.succes_page == 0
            self._btn_next.disabled = self.succes_page >= len(self._succes_pages) - 1
            self.add_item(self._btn_prev)
            self.add_item(self._btn_next)

    async def _prev(self, interaction: discord.Interaction):
        if interaction.user.id != self.invoker_id:
            return await interaction.response.send_message("❌", ephemeral=True)
        self.succes_page = max(0, self.succes_page - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _next(self, interaction: discord.Interaction):
        if interaction.user.id != self.invoker_id:
            return await interaction.response.send_message("❌", ephemeral=True)
        self.succes_page = min(len(self._succes_pages) - 1, self.succes_page + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    def build_embed(self) -> discord.Embed:
        # Recharge les succès à chaque appel pour garantir la mise à jour
        self._succes_pages = build_achievement_pages(self.data)
        if self.onglet == "profil":
            return self._embed_profil()
        elif self.onglet == "cooldowns":
            return self._embed_cooldowns()
        elif self.onglet == "stats":
            return self._embed_stats()
        elif self.onglet == "classement":
            return self._embed_classement()
        else:
            return self._embed_succes()

    # ── Onglet Cooldowns ────────────────────────────────────
    def _embed_cooldowns(self) -> discord.Embed:
        data = self.data
        # Catégories dynamiques - MysteriBox et premium dans Autres
        jeux_labels = ["🪙 Coinflip", "💣 Mines", "🎰 Slots", "🃏 Blackjack", "🎲 Roulette"]
        autres_labels = ["🎁 Daily", "⏰ Hourly", "🗓️ Monthly", "🦹 Rob", "📅 Weekly", "🏮 LanternFall", "📦 MysteriBox"]
        
        # Collecte et tri des cooldowns
        jeux_items = []
        autres_items = []
        
        for label, key, kind, value in ACTIVITY_COOLDOWNS:
            status, dispo, sort_key = self._get_cooldown_status(data, kind, key, value)
            item = {"label": label, "status": status, "dispo": dispo, "sort_key": sort_key}
            if label in jeux_labels:
                jeux_items.append(item)
            elif label in autres_labels:
                autres_items.append(item)
        
        # Tri : dispos d'abord (plus de restants = en haut), puis épuisés par temps restant
        def sort_items(items):
            dispos = [i for i in items if i["dispo"]]
            epuises = [i for i in items if not i["dispo"]]
            # Dispos : plus de restants = prioritaire
            dispos.sort(key=lambda x: (-x["sort_key"], x["label"]))
            # Épuisés : moins de temps = prioritaire (pour voir ce qui arrive bientôt)
            epuises.sort(key=lambda x: (x["sort_key"], x["label"]))
            return dispos + epuises
        
        jeux_items = sort_items(jeux_items)
        autres_items = sort_items(autres_items)
        
        # Formatage visuel amélioré
        def format_section(title, items):
            if not items:
                return ""
            lines = [f"**{title}**"]
            for item in items:
                emoji = "🟢" if item["dispo"] else "🔴"
                lines.append(f"{emoji} **{item['label']}** · {item['status']}")
            return "\n".join(lines)
        
        sections = []
        if jeux_items:
            sections.append(format_section("🎮 JEUX DE CASINO", jeux_items))
        if autres_items:
            sections.append(format_section("📋 AUTRES ACTIVITÉS", autres_items))
        
        description = "\n\n".join(sections)
        if not description:
            description = "*Aucun cooldown disponible.*"
        
        embed = _get_embed(self.bot, self.guild, self.member,
                           f"⏳ Cooldowns — {self.member.display_name}", description)
        embed.set_thumbnail(url=self.member.display_avatar.url)
        return embed
    
    def _get_cooldown_status(self, data, kind, key, value):
        """Retourne (status_text, disponible, sort_key)"""
        if kind == "iso":
            status = _cooldown_str(data.get(key), value)
            dispo = not status.startswith("⏳")
            return status, dispo, 0
        
        elif kind == "ts":
            ts = data.get(key, 0)
            rem = value - (datetime.now().timestamp() - ts)
            if rem <= 0:
                return "✅ Disponible", True, 999
            h, r = divmod(int(rem), 3600)
            m = r // 60
            return f"⏳ {h}h {m:02d}m", False, rem
        
        elif kind == "hourly":
            stats_block = data.get(key, {})
            plays = stats_block.get("parties_heure", [])
            played = _count_recent_plays(plays)
            game = key.replace("_stats", "")
            limit = get_admin_hourly_limit(self.guild.id, game, get_hourly_limit(data))
            if limit is None:
                return "✅ Illimité", True, 999
            remaining = max(0, limit - played)
            if remaining == 0:
                try:
                    dt_list = [datetime.fromisoformat(p) for p in plays]
                    oldest = min(dt_list)
                    rem_s = max(0, 3600 - (datetime.now() - oldest).total_seconds())
                    h, r = divmod(int(rem_s), 3600)
                    m = r // 60
                    return f"⏳ {h}h {m:02d}m", False, rem_s
                except:
                    return "⏳ ~1h", False, 3600
            return f"✅ {remaining}/{limit}", True, remaining
        
        elif kind == "rob":
            rob_data = data.get("rob_data", {})
            raw = rob_data.get("hourly_robs", [])
            now_dt = datetime.now()
            cutoff = now_dt - timedelta(hours=1)
            hourly = [t for t in raw if datetime.fromisoformat(t) > cutoff]
            remaining = max(0, value - len(hourly))
            if remaining == 0:
                try:
                    oldest = min(datetime.fromisoformat(t) for t in hourly)
                    rem_s = max(0, 3600 - (now_dt - oldest).total_seconds())
                    h, r = divmod(int(rem_s), 3600)
                    m = r // 60
                    return f"⏳ {h}h {m:02d}m", False, rem_s
                except:
                    return "⏳ ~1h", False, 3600
            return f"✅ {remaining}/{value}", True, remaining
        
        elif kind == "daily":
            limits_data = data.get(key, {})
            daily_count = limits_data.get("daily_count", 0)
            last_openings = limits_data.get("last_openings", [])
            last_reset = limits_data.get("last_reset", "")
            today = datetime.now().strftime("%Y-%m-%d")
            if last_reset != today:
                daily_count = 0
            remaining = max(0, value - daily_count)
            if remaining == 0:
                now = datetime.now()
                midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
                rem_s = (midnight - now).total_seconds()
                h, r = divmod(int(rem_s), 3600)
                m = r // 60
                return f"⏳ {h}h {m:02d}m", False, rem_s
            # Cooldown 8h entre ouvertures - mais on affiche juste disponible/pas disponible
            if last_openings:
                try:
                    last_opening = datetime.fromisoformat(last_openings[-1])
                    time_since = datetime.now() - last_opening
                    if time_since < timedelta(hours=8):
                        rem = timedelta(hours=8) - time_since
                        rem_s = rem.total_seconds()
                        h = int(rem_s // 3600)
                        m = int((rem_s % 3600) // 60)
                        # Sans le (8h cd)
                        return f"⏳ {h}h {m}m", False, rem_s
                except:
                    pass
            return f"✅ {remaining}/{value}", True, remaining
        
        elif kind == "none":
            return "✅ Illimité", True, 999
        
        return "✅ Disponible", True, 999

    # ── Onglet Statistiques ────────────────────────────────
    def _embed_stats(self) -> discord.Embed:
        command_stats = get_command_stats(self.data)
        stats = self.data.get("stats", {})
        
        # En-tête avec statistiques générales
        total_parties = sum(s["parties_total"] for s in command_stats.values())
        total_victoires = stats.get("total_wins", 0)
        total_mise = stats.get("Cols_spent", 0)
        win_rate = (total_victoires / total_parties * 100) if total_parties > 0 else 0
        
        header = (
            f"**🎯 Vue d'ensemble de {self.member.mention}**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 **Total Parties** : `{format_y(total_parties)}` · "
            f"🏆 **Total Victoires** : `{format_y(total_victoires)}` · "
            f"📈 **Taux de Victoire** : `{win_rate:.1f}%`\n"
            f"💰 **Total Misé** : `{format_y(total_mise)} Cols`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        
        # Sections par catégorie
        sections = []
        
        # Jeux de Casino
        casino_games = ["🪙 Coinflip", "💣 Mines", "🎰 Slots", "🃏 Blackjack", "🎲 Roulette"]
        casino_section = "**🎰 JEUX DE CASINO**\n"
        for game_name in casino_games:
            if game_name in command_stats:
                game = command_stats[game_name]
                # Enlever l'emoji du nom pour éviter le double
                clean_name = game_name.split(' ', 1)[1] if ' ' in game_name else game_name
                if game["parties_total"] > 0:
                    casino_section += (
                        f"{game['emoji']} **{clean_name}** · `{game['command']}`\n"
                        f"  └ Parties : `{format_y(game['parties_total'])}` · "
                        f"Dernière heure : `{game['derniere_heure']}`\n"
                    )
                else:
                    casino_section += (
                        f"{game['emoji']} **{clean_name}** · `{game['command']}`\n"
                        f"  └ Parties : `0` · Jamais joué\n"
                    )
        sections.append(casino_section)
        
        # Activités Spéciales
        special_games = ["🏮 LanternFall", "📦 MysteriBox", "🦹 Rob"]
        special_section = "**⭐ ACTIVITÉS SPÉCIALES**\n"
        for game_name in special_games:
            if game_name in command_stats:
                game = command_stats[game_name]
                # Enlever l'emoji du nom pour éviter le double
                clean_name = game_name.split(' ', 1)[1] if ' ' in game_name else game_name
                if game["parties_total"] > 0:
                    special_section += (
                        f"{game['emoji']} **{clean_name}** · `{game['command']}`\n"
                        f"  └ Parties : `{format_y(game['parties_total'])}` · "
                        f"Dernière heure : `{game['derniere_heure']}`\n"
                    )
                else:
                    status_text = "Jamais volé" if game_name == "🦹 Rob" else "Jamais joué"
                    special_section += (
                        f"{game['emoji']} **{clean_name}** · `{game['command']}`\n"
                        f"  └ Parties : `0` · {status_text}\n"
                    )
        sections.append(special_section)
        
        # Résumé Daily et autres stats
        daily_section = (
            f"**📅 RÉCOMPENSES QUOTIDIENNES**\n"
            f"🎁 **Daily consécutifs** : `{format_y(stats.get('daily_streak', 0))}` jours\n"
            f"📊 **Total Daily réclamés** : `{format_y(stats.get('daily_count', 0))}` fois\n\n"
            f"**🦹 ACTIVITÉS DE VOL**\n"
            f"🦹 **Vols réussis** : `{format_y(stats.get('rob_success', 0))}`\n"
            f"🚨 **Vols ratés (pris)** : `{format_y(stats.get('rob_backfire', 0))}`\n"
        )
        sections.append(daily_section)
        
        # Assemblage final
        description = header + "\n\n".join(sections)
        
        embed = _get_embed(self.bot, self.guild, self.member,
                           f"📊 Statistiques Détaillées — {self.member.display_name}", description)
        embed.set_thumbnail(url=self.member.display_avatar.url)
        return embed

    # ── Onglet Classement ─────────────────────────────────
    def _embed_classement(self) -> discord.Embed:
        try:
            all_members = self.guild.members
        except Exception:
            all_members = [self.member]
        user_id = self.member.id
        all_data = []
        for m in all_members:
            try:
                d = load_user_data(self.guild.id, m.id)
                if d:
                    all_data.append((m, d))
            except Exception:
                continue
        cols_sorted = sorted(all_data, key=lambda x: x[1].get("Cols", 0), reverse=True)
        honneur_sorted = sorted(all_data, key=lambda x: x[1].get("honneur", 0), reverse=True)
        def get_succes_count(d):
            stats = get_achievement_stats(d)
            return stats.get("unlocked_achievements", 0)
        succes_sorted = sorted(all_data, key=lambda x: get_succes_count(x[1]), reverse=True)
        def get_rank(sorted_list):
            for idx, (m, d) in enumerate(sorted_list, 1):
                if m.id == user_id:
                    return idx, d
            return None, None
        rank_cols, d_cols = get_rank(cols_sorted)
        rank_honneur, d_honneur = get_rank(honneur_sorted)
        rank_succes, d_succes = get_rank(succes_sorted)
        def pretty_rank(rank, total):
            if not rank:
                return "N/A"
            if rank == 1:
                return f"🥇 1er / {total}"
            elif rank == 2:
                return f"🥈 2e / {total}"
            elif rank == 3:
                return f"🥉 3e / {total}"
            else:
                return f"#{rank} / {total}"
        # Affichage plus joli et plus complet
        description = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏅 **Cols** : {pretty_rank(rank_cols, len(cols_sorted))}  —  `{format_y(d_cols.get('Cols', 0) if d_cols else 0)} Cols`\n"
            f"💠 **Points d'Honneur** : {pretty_rank(rank_honneur, len(honneur_sorted))}  —  `{format_y(d_honneur.get('honneur', 0) if d_honneur else 0)}`\n"
            f"🏆 **Succès débloqués** : {pretty_rank(rank_succes, len(succes_sorted))}  —  `{get_succes_count(d_succes) if d_succes else 0}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "\n*Utilisez la commande `/leader` pour voir tous les classements détaillés du serveur.*"
        )
        embed = _get_embed(self.bot, self.guild, self.member,
                           f"🥇 Classement — {self.member.display_name}", description)
        embed.set_thumbnail(url=self.member.display_avatar.url)
        return embed

    # ── Onglet Profil ─────────────────────────────────────────
    def _embed_profil(self) -> discord.Embed:
        d = self.data
        stats = get_achievement_stats(d)
        Cols = d.get("Cols", 0)
        honneur = d.get("honneur", 0)

        level, xp_in_level, xp_to_next = get_xp_progress(d)
        progress = _progress_bar(xp_in_level, xp_to_next, length=10)
        description = (
            f"🎚️ **Niveau** : `{level}`\n"
            f"📈 **XP** : `{format_y(xp_in_level)}/{format_y(xp_to_next)}` {progress}\n"
            f"💴 **Solde actuel** : `{format_y(Cols)} Cols`\n"
            f"🎖️ **Points d'Honneur** : `{format_y(honneur)}`\n"
            f"🏆 **Succès** : `{stats['unlocked_achievements']}/{stats['total_achievements']}`\n"
            f"└ Paliers : `{stats['unlocked_paliers']}/{stats['total_paliers']}`"
        )
        embed = _get_embed(self.bot, self.guild, self.member,
                           f"⚔️ Profil — {self.member.display_name}", description)
        embed.set_thumbnail(url=self.member.display_avatar.url)
        return embed

    # ── Onglet Succès ─────────────────────────────────────────
    def _embed_succes(self) -> discord.Embed:
        stats = get_achievement_stats(self.data)
        total_pages = max(1, len(self._succes_pages))

        header = (
            f"🏆 **{stats['unlocked_achievements']}/{stats['total_achievements']}** succès débloqués "
            f"· **{stats['unlocked_paliers']}/{stats['total_paliers']}** paliers\n"
            f"✨ Honneur gagné via succès : **{format_y(stats['honneur_earned'])} pts**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )

        page_content = self._succes_pages[self.succes_page] if self._succes_pages else "*Aucun succès disponible.*"
        description = header + page_content

        embed = _get_embed(self.bot, self.guild, self.member,
                           f"🏆 Succès — {self.member.display_name}", description)
        embed.set_footer(text=f"Page {self.succes_page + 1}/{total_pages}")
        embed.set_thumbnail(url=self.member.display_avatar.url)
        return embed

# ── COG ──────────────────────────────────────────────────────

class ProfilSAO(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="profil", description="Affiche votre profil interactif au Casino d'Aincrad.")
    async def profil(self, ctx: commands.Context, membre: discord.Member = None):
        membre = membre or ctx.author
        data = load_user_data(ctx.guild.id, membre.id)

        if not data:
            return await ctx.send("❌ Aucun compte trouvé.", ephemeral=True)

        view = ProfilView(self.bot, ctx.guild, membre, data, ctx.author.id)
        embed = view.build_embed()
        await ctx.send(embed=embed, view=view)

    @commands.hybrid_command(name="lvl", description="Affiche votre niveau actuel et progression XP.")
    async def lvl(self, ctx: commands.Context, membre: discord.Member = None):
        membre = membre or ctx.author
        data = load_user_data(ctx.guild.id, membre.id)

        if not data:
            return await ctx.send("❌ Aucun compte trouvé.", ephemeral=True)

        level, xp_in_level, xp_to_next = get_xp_progress(data)
        progress = _progress_bar(xp_in_level, xp_to_next, length=10)
        description = (
            f"🎚️ **Niveau** : `{level}`\n"
            f"📈 **XP** : `{format_y(xp_in_level)}/{format_y(xp_to_next)}`\n"
            f"{progress}"
        )
        embed = _get_embed(self.bot, ctx.guild, membre, f"🏅 Niveau — {membre.display_name}", description)
        embed.set_thumbnail(url=membre.display_avatar.url)
        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(ProfilSAO(bot))