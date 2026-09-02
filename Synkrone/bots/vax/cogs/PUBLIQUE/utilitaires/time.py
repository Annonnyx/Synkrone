"""
MODULE TIME - VAX V3
====================
Planificateur temporel centralisé (Layout V2).
Intègre : Tableau de bord, Chronomètre temps-réel (avec Keep-Alive anti-lag), 
Minuteur, Alarme, Rappel (avec Fallback MP) et Agenda (récurrent).
"""

from __future__ import annotations

import asyncio
import time
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import discord
from discord import app_commands, ui
from discord.ext import commands, tasks

# Imports standards Vax v3
from utils.config_data import DataManager
from utils.config_perm import _send_permission_denied
from utils.config_emoji import Emoji as E

try:
    from utils.config_theme import config_manager
except ImportError:
    config_manager = None

# ==============================================================================
# ------------------------------ DÉBOGAGE GLOBAL -------------------------------
# ==============================================================================
DEBUG_MODE = True
DEBUG_ERRORS_ONLY = True

def debug_log(message: str, level: str = "INFO") -> None:
    if DEBUG_ERRORS_ONLY and level.upper() != "ERROR":
        return
    if not DEBUG_MODE and not DEBUG_ERRORS_ONLY:
        return

    colors = {
        "INFO": "\033[94m",
        "SUCCESS": "\033[92m",
        "ERROR": "\033[91m",
        "WARNING": "\033[93m",
    }
    reset = "\033[0m"
    color = colors.get(level.upper(), "\033[97m")
    print(f"{color}[DEBUG - Time] [{level.upper()}] {message}{reset}")

# ==============================================================================
# ----------------------------- EMOJIS CENTRALISÉS -----------------------------
# ==============================================================================
ICO_DASHBOARD = getattr(E, "GRAPHIQUE", "📊")
ICO_CHRONO    = getattr(E, "HORLOGE", "⏱️")
ICO_TIMER     = "⏳"
ICO_ALARM     = getattr(E, "ATTENTION", "🚨")
ICO_REMINDER  = "📌"
ICO_AGENDA    = "📅"

ICO_PLAY      = "▶️"
ICO_PAUSE     = "⏸️"
ICO_STOP      = "⏹️"
ICO_LAP       = "🔁"
ICO_ADD       = getattr(E, "AJOUTER", "➕")
ICO_TRASH     = getattr(E, "SUPPRIMER", "🗑️")
ICO_ALIVE     = "👋"

ICO_SUCCESS   = getattr(E, 'VALIDE', "✅")
ICO_ERROR     = getattr(E, 'ERREUR', "❌")


# ==============================================================================
# --------------------------- DATA & PARSING HELPERS ---------------------------
# ==============================================================================
# Stockage par ID de serveur (Guild ID)
time_db = DataManager("public/utilitaires/data_time")


def _migrate_legacy_time_data() -> None:
    """Migre les anciens fichiers data/utilitaires/data_time vers data/public/utilitaires/data_time."""
    project_root = Path(__file__).resolve().parents[3]
    legacy_dir = project_root / "data" / "utilitaires" / "data_time"
    new_dir = project_root / "data" / "public" / "utilitaires" / "data_time"

    if not legacy_dir.exists():
        return

    try:
        new_dir.mkdir(parents=True, exist_ok=True)
        for src in legacy_dir.glob("*.json"):
            dst = new_dir / src.name
            if not dst.exists():
                dst.write_bytes(src.read_bytes())
            src.unlink(missing_ok=True)

        if not any(legacy_dir.iterdir()):
            legacy_dir.rmdir()
    except Exception:
        # La migration est best-effort, sans bloquer le module.
        pass


_migrate_legacy_time_data()

def parse_duration_to_seconds(duration_str: str) -> int | None:
    duration_str = duration_str.lower().replace(" ", "")
    if not duration_str:
        return None

    matches = re.findall(r"(\d+)([dhmsj])", duration_str)
    if not matches:
        return None

    total = 0
    for value, unit in matches:
        amount = int(value)
        if unit in {"d", "j"}:
            total += amount * 86400
        elif unit == "h":
            total += amount * 3600
        elif unit == "m":
            total += amount * 60
        elif unit == "s":
            total += amount

    return total if total > 0 else None


def parse_agenda_interval(duration_str: str) -> int | None:
    total = parse_duration_to_seconds(duration_str)
    if total is None:
        return None

    min_interval = 7 * 86400
    max_interval = 90 * 86400
    if not (min_interval <= total <= max_interval):
        return None

    return total

def parse_target_time(time_str: str) -> float | None:
    try:
        now = datetime.now(timezone.utc)
        target = datetime.strptime(time_str, "%H:%M").replace(
            year=now.year, month=now.month, day=now.day, tzinfo=timezone.utc
        )
        if target <= now:
            target += timedelta(days=1)
        return target.timestamp()
    except ValueError:
        return None

def parse_datetime(dt_str: str) -> float | None:
    try:
        dt = datetime.strptime(dt_str, "%d/%m/%Y %H:%M")
        return dt.replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None

# ==============================================================================
# --------------------------------- MODALES ------------------------------------
# ==============================================================================
class BaseTimeModal(ui.Modal):
    def __init__(self, view: "TimeLayoutView", title: str):
        super().__init__(title=title)
        self.view = view

class TimerModal(BaseTimeModal):
    def __init__(self, view: "TimeLayoutView"):
        super().__init__(view, title="Nouveau Minuteur")
        self.t_title = ui.TextInput(label="Titre", placeholder="Ex: Cuisson des pâtes", max_length=50)
        self.t_duration = ui.TextInput(label="Durée (ex: 15m, 1h30, 45s)", max_length=20)
        self.add_item(self.t_title)
        self.add_item(self.t_duration)

    async def on_submit(self, interaction: discord.Interaction):
        secs = parse_duration_to_seconds(self.t_duration.value)
        if not secs:
            self.view.info_text = f"{ICO_ERROR} Durée invalide."
            return await self.view.refresh(interaction)
        
        target = datetime.now(timezone.utc).timestamp() + secs
        self.view.add_item_to_data({
            "id": f"timer_{int(target)}_{interaction.user.id}",
            "type": "timer",
            "title": self.t_title.value.strip(),
            "message": self.t_title.value.strip() or "Minuteur terminé",
            "target": target,
            "channel_id": interaction.channel_id,
            "author_id": interaction.user.id
        })
        self.view.info_text = f"{ICO_SUCCESS} Minuteur `{self.t_title.value.strip()}` lancé."
        await self.view.refresh(interaction)

class AlarmModal(BaseTimeModal):
    def __init__(self, view: "TimeLayoutView"):
        super().__init__(view, title="Nouvelle Alarme")
        self.t_title = ui.TextInput(label="Titre", placeholder="Ex: Réveil", max_length=50)
        self.t_time = ui.TextInput(label="Heure cible (HH:MM)", placeholder="18:30", max_length=5)
        self.add_item(self.t_title)
        self.add_item(self.t_time)

    async def on_submit(self, interaction: discord.Interaction):
        target_ts = parse_target_time(self.t_time.value)
        if not target_ts:
            self.view.info_text = f"{ICO_ERROR} Heure invalide (utilisez HH:MM)."
            return await self.view.refresh(interaction)
        
        self.view.add_item_to_data({
            "id": f"alarm_{int(target_ts)}_{interaction.user.id}",
            "type": "alarm",
            "title": self.t_title.value.strip(),
            "message": self.t_title.value.strip() or "Alarme terminée",
            "target": target_ts,
            "channel_id": interaction.channel_id,
            "author_id": interaction.user.id
        })
        self.view.info_text = f"{ICO_SUCCESS} Alarme programmée pour <t:{int(target_ts)}:t>."
        await self.view.refresh(interaction)

class ReminderModal(BaseTimeModal):
    def __init__(self, view: "TimeLayoutView"):
        super().__init__(view, title="Nouveau Rappel")
        self.t_message = ui.TextInput(label="Message", style=discord.TextStyle.paragraph, max_length=500)
        self.t_datetime = ui.TextInput(label="Date et Heure (JJ/MM/AAAA HH:MM)", placeholder="25/12/2026 08:00", max_length=16)
        self.add_item(self.t_message)
        self.add_item(self.t_datetime)

    async def on_submit(self, interaction: discord.Interaction):
        target_ts = parse_datetime(self.t_datetime.value)
        if not target_ts:
            self.view.info_text = f"{ICO_ERROR} Date/Heure invalide. Respectez le format JJ/MM/AAAA HH:MM."
            return await self.view.refresh(interaction)
        
        self.view.add_item_to_data({
            "id": f"rem_{int(target_ts)}_{interaction.user.id}",
            "type": "reminder",
            "title": self.t_message.value.strip(),
            "message": self.t_message.value.strip() or "Rappel",
            "target": target_ts,
            "channel_id": interaction.channel_id,
            "author_id": interaction.user.id
        })
        self.view.info_text = f"{ICO_SUCCESS} Rappel enregistré pour <t:{int(target_ts)}:f>."
        await self.view.refresh(interaction)

class AgendaModal(BaseTimeModal):
    def __init__(self, view: "TimeLayoutView"):
        super().__init__(view, title="Nouvel Agenda Récurrent")
        self.t_title = ui.TextInput(label="Message / Tâche", style=discord.TextStyle.paragraph, max_length=200)
        self.t_datetime = ui.TextInput(label="Première occurrence (JJ/MM/AAAA HH:MM)", placeholder="Ex: 01/01/2027 12:00")
        self.t_interval = ui.TextInput(label="Répétition (7j à 90j)", placeholder="7j", max_length=10)
        self.add_item(self.t_title)
        self.add_item(self.t_datetime)
        self.add_item(self.t_interval)

    async def on_submit(self, interaction: discord.Interaction):
        target_ts = parse_datetime(self.t_datetime.value)
        interval_secs = parse_agenda_interval(self.t_interval.value)

        if not target_ts or not interval_secs:
            self.view.info_text = f"{ICO_ERROR} Date ou Répétition invalide. Utilisez 7j à 90j."
            return await self.view.refresh(interaction)

        self.view.add_item_to_data({
            "id": f"agenda_{int(target_ts)}_{interaction.user.id}",
            "type": "agenda",
            "title": self.t_title.value.strip(),
            "message": self.t_title.value.strip() or "Agenda",
            "target": target_ts,
            "interval": interval_secs,
            "channel_id": interaction.channel_id,
            "author_id": interaction.user.id
        })
        self.view.info_text = f"{ICO_SUCCESS} Agenda créé ! Prochain déclenchement : <t:{int(target_ts)}:f>."
        await self.view.refresh(interaction)

class AgendaEditModal(ui.Modal, title="Modifier l'agenda"):
    def __init__(self, view: "TimeLayoutView", item: dict):
        super().__init__()
        self.view = view
        self.item = item
        self.t_title = ui.TextInput(label="Nom / Message", style=discord.TextStyle.paragraph, default=item.get("title", ""), max_length=200)
        self.t_interval = ui.TextInput(label="Fréquence (7j à 90j)", default=str(item.get("interval", 0)) if item.get("interval") else "7j", max_length=10)
        self.add_item(self.t_title)
        self.add_item(self.t_interval)

    async def on_submit(self, interaction: discord.Interaction):
        new_title = self.t_title.value.strip()
        interval_secs = parse_agenda_interval(self.t_interval.value)
        if not new_title:
            await interaction.response.send_message(f"{ICO_ERROR} Le nom ne peut pas être vide.", ephemeral=True)
            return
        if not interval_secs:
            await interaction.response.send_message(f"{ICO_ERROR} Fréquence invalide.", ephemeral=True)
            return

        data = self.view.get_data()
        for entry in data.get("items", []):
            if entry.get("id") == self.item.get("id"):
                entry["title"] = new_title
                entry["message"] = new_title
                entry["interval"] = interval_secs
                break
        self.view.save_data(data)
        self.view.info_text = f"{ICO_SUCCESS} Agenda mis à jour."
        await self.view.refresh(interaction)

class AgendaRenameModal(ui.Modal, title="Renommer l'agenda"):
    def __init__(self, view: "TimeLayoutView", item: dict):
        super().__init__()
        self.view = view
        self.item = item
        self.t_title = ui.TextInput(label="Nouveau nom / message", style=discord.TextStyle.paragraph, default=item.get("title", ""), max_length=200)
        self.add_item(self.t_title)

    async def on_submit(self, interaction: discord.Interaction):
        new_title = self.t_title.value.strip()
        if not new_title:
            await interaction.response.send_message(f"{ICO_ERROR} Le nom ne peut pas être vide.", ephemeral=True)
            return

        data = self.view.get_data()
        for entry in data.get("items", []):
            if entry.get("id") == self.item.get("id"):
                entry["title"] = new_title
                entry["message"] = new_title
                break
        self.view.save_data(data)
        self.view.info_text = f"{ICO_SUCCESS} Agenda renommé."
        await self.view.refresh(interaction)

class AgendaDelayModal(ui.Modal, title="Modifier le délai"):
    def __init__(self, view: "TimeLayoutView", item: dict):
        super().__init__()
        self.view = view
        self.item = item
        self.t_interval = ui.TextInput(label="Nouvelle fréquence (7j à 90j)", default=str(item.get("interval", 0)) if item.get("interval") else "7j", max_length=10)
        self.add_item(self.t_interval)

    async def on_submit(self, interaction: discord.Interaction):
        interval_secs = parse_agenda_interval(self.t_interval.value)
        if not interval_secs:
            await interaction.response.send_message(f"{ICO_ERROR} Fréquence invalide.", ephemeral=True)
            return

        data = self.view.get_data()
        for entry in data.get("items", []):
            if entry.get("id") == self.item.get("id"):
                entry["interval"] = interval_secs
                break
        self.view.save_data(data)
        self.view.info_text = f"{ICO_SUCCESS} Délai mis à jour."
        await self.view.refresh(interaction)


# ==============================================================================
# ------------------------- INTERFACE LAYOUT V2 PRINCIPALE ---------------------
# ==============================================================================
class TimeLayoutView(ui.LayoutView):
    def __init__(self, cog: "TimeModule", guild: discord.Guild, user: discord.Member):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild = guild
        self.user = user
        self.current_section = "dashboard"
        self.info_text = ""
        self.message: Optional[discord.Message] = None
        self.pending_agenda_id: Optional[str] = None
        
        # Données de chronomètre gérées en mémoire
        self.chrono_data = self.cog.active_chronos.setdefault(self.user.id, {
            "is_running": False, "start_time": 0.0, "accumulated": 0.0, "laps": []
        })
        self.last_keepalive = time.time()
        self.chrono_task: Optional[asyncio.Task] = None
        
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(f"{ICO_ERROR} Ce menu ne t'appartient pas.", ephemeral=True)
            return False
        return True

    def get_data(self) -> dict:
        return time_db.load(self.guild.id) or {"items": []}

    def save_data(self, data: dict) -> None:
        time_db.save(self.guild.id, data)

    def add_item_to_data(self, item: dict) -> None:
        data = self.get_data()
        data.setdefault("items", []).append(item)
        self.save_data(data)

    async def refresh(self, interaction: discord.Interaction):
        self.last_keepalive = time.time() # Tout clic réinitialise le keep-alive
        self._build()
        if interaction.response.is_done():
            await interaction.edit_original_response(view=self)
        else:
            await interaction.response.edit_message(view=self)
        self.info_text = ""

    async def refresh_silent(self):
        if self.message:
            self._build()
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    # ------------------ CHRONO BACKGROUND TASK ------------------
    def manage_chrono_task(self):
        """Lance ou arrête la tâche de rafraîchissement en direct selon l'état."""
        if self.current_section == "chrono" and self.chrono_data["is_running"]:
            if not self.chrono_task or self.chrono_task.done():
                self.chrono_task = asyncio.create_task(self._chrono_live_update())
        else:
            if self.chrono_task and not self.chrono_task.done():
                self.chrono_task.cancel()

    async def _chrono_live_update(self):
        """Met à jour le chrono chaque seconde pour une fluidité maximale."""
        try:
            while self.current_section == "chrono" and self.chrono_data["is_running"]:
                await asyncio.sleep(1)

                inactive_time = time.time() - self.last_keepalive
                if inactive_time > 300:
                    self.chrono_data["is_running"] = False
                    self.chrono_data["accumulated"] += time.time() - self.chrono_data["start_time"]
                    self.info_text = f"{ICO_ERROR} Chrono arrêté automatiquement (5 minutes d'inactivité)."
                    await self.refresh_silent()
                    break

                await self.refresh_silent()
        except asyncio.CancelledError:
            pass

    def _build(self) -> None:
        self.clear_items()
        
        accent_color = discord.Color.blurple().value
        footer_text = ""
        if config_manager and self.guild:
            theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.cog.bot)
            accent_color = int(theme.get("color", accent_color))
            footer_text = theme.get("footer_text", "")

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        
        container.add_item(ui.TextDisplay("# ⚙️ Planificateur Temporel"))
        if self.info_text:
            container.add_item(ui.TextDisplay(f"**{self.info_text}**"))

        nav_row = ui.ActionRow()
        nav_select = ui.Select(
            placeholder="Sélectionne un outil...",
            min_values=1, max_values=1,
            options=[
                discord.SelectOption(label="Tableau de bord", value="dashboard", emoji=ICO_DASHBOARD, default=(self.current_section=="dashboard")),
                discord.SelectOption(label="Chronomètre", value="chrono", emoji=ICO_CHRONO, default=(self.current_section=="chrono")),
                discord.SelectOption(label="Minuteur", value="timer", emoji=ICO_TIMER, default=(self.current_section=="timer")),
                discord.SelectOption(label="Alarme", value="alarm", emoji=ICO_ALARM, default=(self.current_section=="alarm")),
                discord.SelectOption(label="Rappels", value="reminder", emoji=ICO_REMINDER, default=(self.current_section=="reminder")),
                discord.SelectOption(label="Agenda", value="agenda", emoji=ICO_AGENDA, default=(self.current_section=="agenda")),
            ]
        )
        nav_select.callback = self._on_nav_select
        nav_row.add_item(nav_select)
        container.add_item(nav_row)
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

        if self.current_section == "dashboard":
            self._render_dashboard(container)
        elif self.current_section == "chrono":
            self._render_chrono(container)
            self.manage_chrono_task()
        elif self.current_section in ["timer", "alarm", "reminder", "agenda"]:
            self._render_list_module(container, self.current_section)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    # ------------------ CALLBACKS & RENDERS ------------------
    async def _on_nav_select(self, interaction: discord.Interaction):
        self.current_section = interaction.data.get("values", ["dashboard"])[0]
        self.info_text = ""
        self.manage_chrono_task() # Stopper ou lancer la task chrono si besoin
        await self.refresh(interaction)

    def _render_dashboard(self, container: ui.Container):
        data = self.get_data()
        items = [i for i in data.get("items", []) if i.get("author_id") == self.user.id]
        
        counts = {"timer": 0, "alarm": 0, "reminder": 0, "agenda": 0}
        for i in items:
            counts[i.get("type", "")] = counts.get(i.get("type", ""), 0) + 1
            
        c_status = "En cours" if self.chrono_data["is_running"] else "Arrêté"
        
        container.add_item(ui.TextDisplay("## 📊 Aperçu de vos tâches"))
        desc = (
            f"- {ICO_CHRONO} Chrono : `{c_status}`\n"
            f"- {ICO_TIMER} Minuteurs actifs : `{counts['timer']}`\n"
            f"- {ICO_ALARM} Alarmes programmées : `{counts['alarm']}`\n"
            f"- {ICO_REMINDER} Rappels : `{counts['reminder']}`\n"
            f"- {ICO_AGENDA} Agendas récurrents : `{counts['agenda']}`\n"
        )
        container.add_item(ui.TextDisplay(desc))

    def _render_chrono(self, container: ui.Container):
        container.add_item(ui.TextDisplay("## ⏱️ Chronomètre"))
        
        c = self.chrono_data
        elapsed = c["accumulated"]
        if c["is_running"]:
            elapsed += time.time() - c["start_time"]
            
        hours, rem = divmod(elapsed, 3600)
        mins, secs = divmod(rem, 60)
        display_time = f"{int(hours):02}:{int(mins):02}:{secs:05.2f}"
        
        container.add_item(ui.TextDisplay(f"### ⏳ Temps : `{display_time}`"))
        
        if c["laps"]:
            laps_text = "\n".join([f"`Tour {i+1}` : {l}" for i, l in enumerate(c["laps"][-5:])])
            container.add_item(ui.TextDisplay(f"**Derniers Tours :**\n{laps_text}"))

        row = ui.ActionRow()
        
        if not c["is_running"]:
            btn_play = ui.Button(label="Démarrer", style=discord.ButtonStyle.success, emoji=ICO_PLAY)
            btn_play.callback = self._cb_chrono_play
            row.add_item(btn_play)
        else:
            btn_pause = ui.Button(label="Pause", style=discord.ButtonStyle.secondary, emoji=ICO_PAUSE)
            btn_pause.callback = self._cb_chrono_pause
            row.add_item(btn_pause)
            
            btn_lap = ui.Button(label="Tour", style=discord.ButtonStyle.primary, emoji=ICO_LAP)
            btn_lap.callback = self._cb_chrono_lap
            row.add_item(btn_lap)

        btn_stop = ui.Button(label="Réinitialiser", style=discord.ButtonStyle.danger, emoji=ICO_STOP)
        btn_stop.callback = self._cb_chrono_stop
        row.add_item(btn_stop)
        
        # Le bouton Keep-Alive apparaît si le chrono tourne depuis +4 minutes sans interaction
        if c["is_running"] and (time.time() - self.last_keepalive > 240):
            btn_alive = ui.Button(label="Je suis là", style=discord.ButtonStyle.primary, emoji=ICO_ALIVE)
            btn_alive.callback = self._cb_chrono_alive
            row.add_item(btn_alive)

        container.add_item(row)

    async def _cb_chrono_play(self, interaction: discord.Interaction):
        self.chrono_data["is_running"] = True
        self.chrono_data["start_time"] = time.time()
        self.manage_chrono_task()
        await self.refresh(interaction)

    async def _cb_chrono_pause(self, interaction: discord.Interaction):
        self.chrono_data["is_running"] = False
        self.chrono_data["accumulated"] += time.time() - self.chrono_data["start_time"]
        self.manage_chrono_task()
        await self.refresh(interaction)

    async def _cb_chrono_lap(self, interaction: discord.Interaction):
        elapsed = self.chrono_data["accumulated"] + (time.time() - self.chrono_data["start_time"])
        hours, rem = divmod(elapsed, 3600)
        mins, secs = divmod(rem, 60)
        self.chrono_data["laps"].append(f"{int(hours):02}:{int(mins):02}:{secs:05.2f}")
        await self.refresh(interaction)

    async def _cb_chrono_stop(self, interaction: discord.Interaction):
        self.chrono_data.update({"is_running": False, "start_time": 0.0, "accumulated": 0.0, "laps": []})
        self.info_text = f"{ICO_SUCCESS} Chronomètre remis à zéro."
        self.manage_chrono_task()
        await self.refresh(interaction)
        
    async def _cb_chrono_alive(self, interaction: discord.Interaction):
        # Le refresh mettra last_keepalive à jour automatiquement
        await self.refresh(interaction)

    def _render_list_module(self, container: ui.Container, item_type: str):
        mapping = {
            "timer": ("Minuteurs", ICO_TIMER, TimerModal),
            "alarm": ("Alarmes", ICO_ALARM, AlarmModal),
            "reminder": ("Rappels", ICO_REMINDER, ReminderModal),
            "agenda": ("Agendas Récurrents", ICO_AGENDA, AgendaModal)
        }
        title, icon, ModalClass = mapping[item_type]
        
        container.add_item(ui.TextDisplay(f"## {icon} Gestion des {title}"))
        
        data = self.get_data()
        items = [i for i in data.get("items", []) if i.get("type") == item_type and i.get("author_id") == self.user.id]
        
        if items:
            list_txt = ""
            opts = []
            for idx, item in enumerate(items[:25]):
                suffix = f" (Répète: {item.get('interval', 0)}s)" if item_type == "agenda" else ""
                list_txt += f"**{idx+1}.** {item['title'][:40]} - Prévu: <t:{int(item['target'])}:R>{suffix}\n"
                opts.append(discord.SelectOption(label=f"{item['title'][:20]}", value=item['id'], emoji=ICO_TRASH))

            container.add_item(ui.TextDisplay(list_txt))

            action_row = ui.ActionRow()
            if item_type == "agenda" and self.pending_agenda_id:
                target_item = next((x for x in items if x.get("id") == self.pending_agenda_id), None)
                if target_item:
                    action_opts = [
                        discord.SelectOption(label="Renommer", value="rename", emoji="✏️"),
                        discord.SelectOption(label="Modifier délai", value="delay", emoji="⏱️"),
                        discord.SelectOption(label="Supprimer", value="delete", emoji=ICO_TRASH),
                        discord.SelectOption(label="Annuler", value="cancel", emoji="❌"),
                    ]
                    action_select = ui.Select(placeholder="⚙️ Choisis une action...", options=action_opts)

                    async def _agenda_action_cb(interaction: discord.Interaction):
                        action = action_select.values[0]
                        if action == "cancel":
                            self.pending_agenda_id = None
                            self.info_text = f"{ICO_SUCCESS} Retour au menu de gestion."
                            await self.refresh(interaction)
                            return

                        d = self.get_data()
                        target_item = next((x for x in d.get("items", []) if x.get("id") == self.pending_agenda_id), None)
                        if not target_item:
                            self.info_text = f"{ICO_ERROR} Élément introuvable."
                            await self.refresh(interaction)
                            return

                        if action == "delete":
                            d["items"] = [x for x in d.get("items", []) if x.get("id") != self.pending_agenda_id]
                            self.save_data(d)
                            self.pending_agenda_id = None
                            self.info_text = f"{ICO_SUCCESS} Agenda supprimé."
                            await self.refresh(interaction)
                            return

                        if action == "rename":
                            await interaction.response.send_modal(AgendaRenameModal(self, target_item))
                        elif action == "delay":
                            await interaction.response.send_modal(AgendaDelayModal(self, target_item))

                    action_select.callback = _agenda_action_cb
                    action_row.add_item(action_select)
                    container.add_item(action_row)
                else:
                    self.pending_agenda_id = None
            else:
                manage_select = ui.Select(placeholder="🛠️ Gérer un élément...", options=opts)

                async def _manage_cb(interaction: discord.Interaction):
                    target_id = manage_select.values[0]
                    d = self.get_data()
                    target_item = next((x for x in d.get("items", []) if x.get("id") == target_id), None)
                    if not target_item:
                        self.info_text = f"{ICO_ERROR} Élément introuvable."
                        await self.refresh(interaction)
                        return

                    if item_type != "agenda":
                        d["items"] = [x for x in d.get("items", []) if x.get("id") != target_id]
                        self.save_data(d)
                        self.info_text = f"{ICO_SUCCESS} Élément supprimé avec succès."
                        await self.refresh(interaction)
                        return

                    self.pending_agenda_id = target_id
                    await self.refresh(interaction)

                manage_select.callback = _manage_cb
                action_row.add_item(manage_select)
                container.add_item(action_row)
        else:
            container.add_item(ui.TextDisplay("_Aucun élément actif dans cette catégorie._"))

        if ModalClass:
            add_row = ui.ActionRow()
            add_btn = ui.Button(label="Ajouter", style=discord.ButtonStyle.primary, emoji=ICO_ADD)
            async def _add_cb(interaction: discord.Interaction):
                await interaction.response.send_modal(ModalClass(self))
            add_btn.callback = _add_cb
            add_row.add_item(add_btn)
            container.add_item(add_row)


# ==============================================================================
# ------------------------------ COG PRINCIPAL ---------------------------------
# ==============================================================================
class TimeModule(commands.Cog):
    """Cog Planificateur centralisant la gestion du temps pour les utilisateurs."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_chronos = {}
        self.time_loop.start()
        debug_log("Cog TimeModule initialisé.", "SUCCESS")

    def cog_unload(self):
        self.time_loop.cancel()
        debug_log("Cog TimeModule déchargé.", "WARNING")

    @tasks.loop(seconds=1)
    async def time_loop(self):
        """Vérifie l'expiration des tâches à la seconde et déclenche les alertes."""
        now = datetime.now(timezone.utc).timestamp()

        try:
            for guild in self.bot.guilds:
                try:
                    data = time_db.load(guild.id)
                    if not data or "items" not in data:
                        continue

                    items = data.get("items", [])
                    updated = False
                    active_items = []

                    for item in items:
                        target = item.get("target", now + 999)
                        if now >= target:
                            await self.trigger_alert(guild, item)

                            if item.get("type") == "agenda" and item.get("interval"):
                                interval = max(1, int(item.get("interval", 0)))
                                item["target"] = now + interval
                                active_items.append(item)
                            updated = True
                        else:
                            active_items.append(item)

                    if updated:
                        data["items"] = active_items
                        time_db.save(guild.id, data)

                except Exception as e:
                    debug_log(f"Erreur time_loop sur le serveur {guild.id}: {e}", "ERROR")

        except Exception as e:
            debug_log(f"Erreur globale time_loop: {e}", "ERROR")

    @time_loop.before_loop
    async def before_time_loop(self):
        await self.bot.wait_until_ready()

    async def trigger_alert(self, guild: discord.Guild, item: dict):
        """Envoie l'alerte au canal d'origine ou en MP si le salon n'existe plus."""
        try:
            user_id = item.get("author_id")
            channel_id = item.get("channel_id")
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
            if not user:
                return

            target_channel = self.bot.get_channel(channel_id) if channel_id else None
            is_agenda = item.get("type") == "agenda"
            if is_agenda:
                target_send = user
            elif isinstance(target_channel, (discord.TextChannel, discord.Thread, discord.VoiceChannel, discord.StageChannel)):
                target_send = target_channel
            else:
                target_send = user

            color = discord.Color.blurple().value
            if config_manager and guild:
                theme = config_manager.get_layout_v2_theme(guild.id, guild, user, self.bot)
                color = int(theme.get("color", color))

            icons = {"timer": ICO_TIMER, "alarm": ICO_ALARM, "reminder": ICO_REMINDER, "agenda": ICO_AGENDA}
            ico = icons.get(item.get("type"), "🔔")
            type_lbl = str(item.get("type", "alerte")).capitalize()
            title = str(item.get("title") or item.get("message") or "Alerte")
            content = str(item.get("message") or title)

            footer_text = ""
            if config_manager and guild:
                theme = config_manager.get_layout_v2_theme(guild.id, guild, user, self.bot)
                footer_text = str(theme.get("footer_text", ""))
            if not footer_text:
                footer_text = "Vax • Planificateur temporel"

            view = ui.LayoutView(timeout=None)
            container = ui.Container(accent_color=discord.Color(color), spoiler=False)
            container.add_item(ui.TextDisplay(f"## {ico} {type_lbl} terminée"))

            ack_row = ui.ActionRow()
            ack_btn = ui.Button(label="Acquitter", style=discord.ButtonStyle.success, emoji=ICO_SUCCESS)

            async def _ack_cb(interaction: discord.Interaction):
                if interaction.user.id != user_id:
                    await interaction.response.send_message(f"{ICO_ERROR} Action réservée à <@{user_id}>.", ephemeral=True)
                    return
                try:
                    await interaction.message.delete()
                except Exception:
                    await interaction.response.defer()

            ack_btn.callback = _ack_cb
            ack_row.add_item(ack_btn)
            container.add_item(ack_row)
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
            container.add_item(ui.TextDisplay(content))
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))
            view.add_item(container)

            await target_send.send(
                view=view,
                allowed_mentions=discord.AllowedMentions(users=True),
            )
            debug_log(f"Alerte '{title}' envoyée à {user_id}", "SUCCESS")

        except discord.Forbidden:
            try:
                user = self.bot.get_user(item.get("author_id")) or await self.bot.fetch_user(item.get("author_id"))
                if user:
                    await user.send(f"{ICO_ERROR} Je n'ai pas pu envoyer l'alerte dans le salon, donc je te l'envoie ici.")
            except Exception:
                pass
        except Exception as e:
            debug_log(f"Erreur trigger_alert: {e}", "ERROR")

    @commands.hybrid_command(name="time", description="Ouvre le Planificateur Temporel (Chrono, Minuteur, Alarme, Agenda)")
    async def time_cmd(self, ctx: commands.Context):
        debug_log(f"Commande /time invoquée par {ctx.author}", "INFO")
        
        if not ctx.guild:
            await ctx.send(f"{ICO_ERROR} Cet outil requiert l'environnement d'un serveur pour hériter du thème.")
            return

        try:
            view = TimeLayoutView(self, ctx.guild, ctx.author)
            if ctx.interaction:
                message = await ctx.send(view=view)
                view.message = message
            else:
                message = await ctx.reply(view=view, mention_author=False)
                view.message = message
        except Exception as exc:
            debug_log(f"Erreur lors de l'exécution de /time : {exc}", "ERROR")
            await ctx.send(f"{ICO_ERROR} Une erreur est survenue lors de l'ouverture du planificateur.")

    @time_cmd.error
    async def time_cmd_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.MissingPermissions):
            await _send_permission_denied(ctx)
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"{ICO_ERROR} Argument invalide.")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TimeModule(bot))
    debug_log("Cog TimeModule enregistré avec succès.", "SUCCESS")