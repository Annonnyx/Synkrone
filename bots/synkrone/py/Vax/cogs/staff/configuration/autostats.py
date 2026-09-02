import discord
from discord.ext import tasks, commands
from discord import ui
import time
from datetime import datetime
import json
import traceback
import logging
from pathlib import Path
from typing import Dict, Any, Optional

# ==============================================================================
# --------------------------- CONFIGURATION & LOGS -----------------------------
# ==============================================================================

# Logger professionnel pour remonter les alertes sans polluer la console standard
logger = logging.getLogger('bot.server_stats')

BASE_DIR = Path(__file__).parent
# Correction du chemin pour viser le vrai dossier data racine du projet (chemin absolu)
DATA_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "staff" / "configuration" / "data_autostats"

# Intégration du gestionnaire global d'embeds (Fallback natif en cas d'absence)
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None
    logger.warning("[Stats] EmbedConfigManager introuvable. Fallback natif activé.")

# ==============================================================================
# ----------------------------- UI COMPONENTS ----------------------------------
# ==============================================================================

class DelayModal(ui.Modal, title="Modifier le délai d'envoi"):
    """Modale pour définir la fréquence d'actualisation des statistiques."""
    delay = ui.TextInput(
        label="Délai (ex: 30s, 5m, 2h, 1j)", 
        placeholder="Ex: 5m", 
        required=True
    )

    def __init__(self, parent_view: 'StatsConfigView'):
        super().__init__()
        self.parent_view = parent_view
        current_delay = self.parent_view.config.get('delay', 300)
        self.delay.default = self.parent_view.format_delay(current_delay)

    def parse_delay(self, val: str) -> int:
        val = val.strip().lower()
        if val.endswith("j"): return int(val[:-1]) * 86400
        if val.endswith("h"): return int(val[:-1]) * 3600
        if val.endswith("m"): return int(val[:-1]) * 60
        if val.endswith("s"): return int(val[:-1])
        return int(val)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            value = self.parse_delay(self.delay.value)
            if value < 30:
                raise ValueError("Le délai minimum est de 30 secondes (Anti Rate-Limit).")
            
            self.parent_view.config['delay'] = value
            self.parent_view.cog.save_config(self.parent_view.guild.id, self.parent_view.config)
            await self.parent_view.update_message(interaction)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)


class SalonTextuelModal(ui.Modal, title="Configuration du salon textuel"):
    """Modale pour configurer le salon de réception."""
    salon_id = ui.TextInput(
        label="ID du salon textuel", 
        placeholder="Ex: 123456789012345678", 
        required=True,
        min_length=17,
        max_length=22
    )

    def __init__(self, parent_view: 'StatsConfigView'):
        super().__init__()
        self.parent_view = parent_view
        current_ch = self.parent_view.config.get('ch_stats_text')
        if current_ch:
            self.salon_id.default = str(current_ch)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            new_id = int(self.salon_id.value.strip())
            channel = self.parent_view.guild.get_channel(new_id)
            
            if not isinstance(channel, discord.TextChannel):
                raise ValueError("Le salon spécifié est introuvable ou n'est pas textuel.")

            self.parent_view.config['ch_stats_text'] = new_id
            self.parent_view.cog.save_config(self.parent_view.guild.id, self.parent_view.config)
            await self.parent_view.update_message(interaction)
        except ValueError as e:
            await interaction.response.send_message(f"❌ Erreur : {e}", ephemeral=True)
        except Exception:
            await interaction.response.send_message("❌ ID invalide.", ephemeral=True)


class StatsFieldsSelect(ui.Select):
    """Sélecteur principal contenant les 24 variantes de statistiques possibles."""
    def __init__(self, parent_view: 'StatsConfigView'):
        self.parent_view = parent_view
        current_fields = self.parent_view.config.get('fields', [])
        
        raw_options = [
            # Démographie & Présence
            ("total", "Membres Total", "Membres du serveur", "👥"),
            ("humans", "Membres Humains", "Utilisateurs standards", "👤"),
            ("bots", "Membres Bots", "Applications", "🤖"),
            ("online_total", "En ligne Tous", "Membres connectés", "🟢"),
            ("online_humans", "En ligne Humains", "Utilisateurs connectés", "🏃‍♂️"),
            ("online_bots", "En ligne Bots", "Bots en service", "⚙️"),
            ("boosts", "Boosts", "Niveau et nombre de boosts", "💎"),
            # Vocal
            ("vocal_total", "En Vocal", "Dans les salons vocaux", "🎤"),
            ("vocal_stream", "Stream", "Partages d'écran actifs", "📺"),
            ("vocal_cam", "Caméra", "Webcams allumées", "📹"),
            ("vocal_muted", "Muet", "Microphones coupés", "🔇"),
            ("vocal_deaf", "Sourdine", "Casques coupés", "🎧"),
            # Messages
            ("msg_24h", "Messages Aujourd'hui", "Aujourd'hui", "💬"),
            ("msg_week", "Messages Semaine", "Cette semaine", "📅"),
            ("msg_month", "Messages Mois", "Ce mois-ci", "🗓️"),
            # Top Membres
            ("top_vocal", "Top Membre Vocal", "Membre avec le plus d'heures", "🌟"),
            ("top_msg", "Top Membre Messages", "Membres les plus actifs", "🏅"),
            # Records
            ("record_members", "Record Membres", "Pic historique de membres", "📈"),
            ("record_online", "Record En ligne", "Pic historique connectés", "🔥"),
            ("record_vocal", "Record Vocal", "Pic historique en vocal", "🎙️"),
            ("record_boosts", "Record Boosts", "Pic historique de boosts", "🚀"),
            ("record_msg_24h", "Record Msg/Jour", "Meilleure journée", "🏆"),
            ("record_msg_week", "Record Msg/Semaine", "Meilleure semaine", "👑"),
            ("record_msg_month", "Record Msg/Mois", "Meilleur mois", "💠"),
        ]
        
        options = []
        for val, label, desc, emoji in raw_options:
            options.append(discord.SelectOption(
                label=label, 
                value=val, 
                description=desc, 
                emoji=emoji,
                default=(val in current_fields)
            ))

        super().__init__(
            placeholder="📊 Sélectionnez les données à afficher",
            min_values=1,
            max_values=24,
            options=options,
            row=1 # Affiché sous les boutons (qui sont en row=0)
        )

    async def callback(self, interaction: discord.Interaction):
        self.parent_view.config['fields'] = self.values
        self.parent_view.cog.save_config(self.parent_view.guild.id, self.parent_view.config)
        await self.parent_view.update_message(interaction)


class StatsConfigView(ui.View):
    def __init__(self, cog: commands.Cog, guild: discord.Guild, config: dict, user: discord.Member):
        super().__init__(timeout=300.0)
        self.cog = cog
        self.guild = guild
        self.config = config
        self.user = user
        self.add_item(StatsFieldsSelect(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        return True

    def format_delay(self, delay: int) -> str:
        if delay % 86400 == 0: return f"{delay//86400}j"
        if delay % 3600 == 0: return f"{delay//3600}h"
        if delay % 60 == 0: return f"{delay//60}m"
        return f"{delay}s"

    async def update_message(self, interaction: discord.Interaction):
        embed = self.cog.build_preview_embed(self.guild, self.config, self.user)
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    # Placé sur la ligne 0 pour apparaître au-dessus du sélecteur
    @ui.button(label="Modifier le salon textuel", style=discord.ButtonStyle.blurple, emoji="💬", row=0)
    async def edit_channel(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(SalonTextuelModal(self))

    # Placé sur la ligne 0 pour apparaître au-dessus du sélecteur
    @ui.button(label="Modifier le délai", style=discord.ButtonStyle.gray, emoji="⏱️", row=0)
    async def edit_delay(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(DelayModal(self))


# ==============================================================================
# ----------------------------- COG SERVER STATS -------------------------------
# ==============================================================================

class ServerStats(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.configs: Dict[int, Dict[str, Any]] = {}
        
        # Buffers en mémoire pour optimiser les performances (I/O JSON)
        self.message_buffer: Dict[int, int] = {} 
        self.user_msg_buffer: Dict[int, Dict[str, int]] = {} 
        
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    async def cog_load(self):
        self.update_stats_loop.start()

    async def cog_unload(self):
        self.update_stats_loop.cancel()

    # --- Persistance & Migration ---

    def _migrate_config(self, config: dict) -> dict:
        """Structure et met à jour dynamiquement les données du serveur."""
        if 'records' not in config:
            config['records'] = {
                "members": {"value": 0, "date": "N/A"},
                "online": {"value": 0, "date": "N/A"},
                "vocal": {"value": config.pop('vocal_record', 0), "date": "N/A"},
                "boosts": {"value": 0, "date": "N/A"},
                "msg_24h": {"value": 0, "date": "N/A"},
                "msg_week": {"value": 0, "date": "N/A"},
                "msg_month": {"value": 0, "date": "N/A"}
            }
        if 'msg_history' not in config:
            config['msg_history'] = {"daily": {}, "weekly": {}, "monthly": {}}
            
        if 'user_activity' not in config:
            config['user_activity'] = {
                "voice_all_time": {}, 
                "msg": {
                    "date_day": self.get_time_keys()["daily"], "daily": {},
                    "date_week": self.get_time_keys()["weekly"], "weekly": {},
                    "date_month": self.get_time_keys()["monthly"], "monthly": {}
                }
            }
        return config

    def load_config(self, guild_id: int) -> dict:
        if guild_id in self.configs:
            return self.configs[guild_id]

        default = {
            'module_enabled': True,
            'ch_stats_text': None,
            'delay': 300,
            'fields': [
                "total", "humans", "bots", "online_total", "vocal_total", 
                "record_vocal", "msg_24h", "msg_week", "msg_month"
            ],
            'last_stats': {}
        }
        
        file_path = DATA_DIR / f"{guild_id}.json"
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                config = {**default, **data}
            except Exception as e:
                logger.error(f"[Stats] Corrupt JSON for {guild_id}: {e}")
                config = default.copy()
        else:
            config = default.copy()
            
        config = self._migrate_config(config)
        self.configs[guild_id] = config
        return config

    def save_config(self, guild_id: int, config: dict):
        self.configs[guild_id] = config
        file_path = DATA_DIR / f"{guild_id}.json"
        if config.get('ch_stats_text') or file_path.exists():
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=4)
            except Exception as e:
                logger.error(f"[Stats] Erreur sauvegarde {guild_id}: {e}")

    # --- Utilitaires Statistiques ---

    def get_time_keys(self):
        now = datetime.now()
        return {
            "daily": now.strftime("%Y-%m-%d"),
            "weekly": now.strftime("%Y-W%W"),
            "monthly": now.strftime("%Y-%m"),
            "display_date": now.strftime("%d/%m/%Y")
        }

    def format_duration(self, seconds: int) -> str:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        if hours > 0: 
            return f"{hours}h {minutes}min" if minutes > 0 else f"{hours}h"
        return f"{minutes}min"

    def format_msg_count(self, count: int) -> str:
        return f"{count} message{'s' if count > 1 else ''}"

    def get_top_user(self, data_dict: dict) -> tuple:
        """Retourne un tuple (user_id, valeur) pour le dictionnaire donné."""
        if not data_dict: return (None, 0)
        best_uid = max(data_dict, key=data_dict.get)
        return (best_uid, data_dict[best_uid])

    def get_guild_stats(self, guild: discord.Guild, config: dict) -> dict:
        humans = sum(1 for m in guild.members if not m.bot)
        bots = guild.member_count - humans
        
        online_members = [m for m in guild.members if m.status != discord.Status.offline]
        online_total = len(online_members)
        online_humans = sum(1 for m in online_members if not m.bot)
        online_bots = online_total - online_humans

        v_tot, v_str, v_cam, v_mut, v_deaf = 0, 0, 0, 0, 0
        for vc in guild.voice_channels:
            v_tot += len(vc.members)
            for m in vc.members:
                if not m.voice: continue
                if m.voice.self_stream: v_str += 1
                if m.voice.self_video: v_cam += 1
                if m.voice.self_mute or m.voice.mute: v_mut += 1
                if m.voice.self_deaf or m.voice.deaf: v_deaf += 1

        tk = self.get_time_keys()
        hist = config.get('msg_history', {})
        msg_day = hist.get("daily", {}).get(tk["daily"], 0)
        msg_week = hist.get("weekly", {}).get(tk["weekly"], 0)
        msg_month = hist.get("monthly", {}).get(tk["monthly"], 0)

        user_act = config.get('user_activity', {})
        top_voice_id, top_voice_val = self.get_top_user(user_act.get("voice_all_time", {}))
        top_msg_day_id, top_msg_day_val = self.get_top_user(user_act.get("msg", {}).get("daily", {}))
        top_msg_week_id, top_msg_week_val = self.get_top_user(user_act.get("msg", {}).get("weekly", {}))
        top_msg_month_id, top_msg_month_val = self.get_top_user(user_act.get("msg", {}).get("monthly", {}))

        return {
            "total": guild.member_count, "humans": humans, "bots": bots,
            "boosts": guild.premium_subscription_count,
            "online_total": online_total, "online_humans": online_humans, "online_bots": online_bots,
            "vocal_total": v_tot, "vocal_stream": v_str, "vocal_cam": v_cam, 
            "vocal_muted": v_mut, "vocal_deaf": v_deaf,
            
            "msg_24h": msg_day, "msg_week": msg_week, "msg_month": msg_month,
            
            "top_vocal_id": top_voice_id, "top_vocal_val": top_voice_val,
            "top_msg_day_id": top_msg_day_id, "top_msg_day_val": top_msg_day_val,
            "top_msg_week_id": top_msg_week_id, "top_msg_week_val": top_msg_week_val,
            "top_msg_month_id": top_msg_month_id, "top_msg_month_val": top_msg_month_val,

            "records": config.get('records', {})
        }

    # --- Builders Visuels ---

    def create_custom_embed(self, guild: discord.Guild, user: discord.Member, title: Optional[str], description: str, color: int = 0x2b2d31) -> discord.Embed:
        if config_manager:
            return config_manager.get_formatted_embed(
                guild=guild, user=user, bot=self.bot, title=title, description=description
            )
        embed = discord.Embed(title=title, description=description, color=color)
        if guild and guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        return embed

    def build_stats_layout(self, stats: dict, active_fields: list) -> str:
        """Génère un affichage propre, organisé en catégories distinctes."""
        sections = {
            "👥 Démographie & Présence": [],
            "🎤 Activité Vocale": [],
            "💬 Échanges & Messages": [],
            "🏆 Classements & Top Membres": [],
            "📈 Records Historiques": []
        }

        # Format: (Section, Label avec italique, Emoji)
        mapping_standard = {
            "total": ("👥 Démographie & Présence", "Membres *Total*", "👥"),
            "humans": ("👥 Démographie & Présence", "Membres *Humains*", "👤"),
            "bots": ("👥 Démographie & Présence", "Membres *Bots*", "🤖"),
            "online_total": ("👥 Démographie & Présence", "En ligne *Tous*", "🟢"),
            "online_humans": ("👥 Démographie & Présence", "En ligne *Humains*", "🏃‍♂️"),
            "online_bots": ("👥 Démographie & Présence", "En ligne *Bots*", "⚙️"),
            "boosts": ("👥 Démographie & Présence", "Boosts", "💎"),
            
            "vocal_total": ("🎤 Activité Vocale", "En Vocal", "🎤"),
            "vocal_stream": ("🎤 Activité Vocale", "*Stream*", "📺"),
            "vocal_cam": ("🎤 Activité Vocale", "*Caméra*", "📹"),
            "vocal_muted": ("🎤 Activité Vocale", "*Muet*", "🔇"),
            "vocal_deaf": ("🎤 Activité Vocale", "*Sourdine*", "🎧"),
            
            "msg_24h": ("💬 Échanges & Messages", "Messages *Aujourd'hui*", "💬"),
            "msg_week": ("💬 Échanges & Messages", "Messages *Semaine*", "📅"),
            "msg_month": ("💬 Échanges & Messages", "Messages *Mois*", "🗓️")
        }

        mapping_records = {
            "record_members": ("📈 Records Historiques", "Record *Membres*", "📈", "members"),
            "record_online": ("📈 Records Historiques", "Record *En ligne*", "🔥", "online"),
            "record_vocal": ("📈 Records Historiques", "Record *Vocal*", "🎙️", "vocal"),
            "record_boosts": ("📈 Records Historiques", "Record *Boosts*", "🚀", "boosts"),
            "record_msg_24h": ("📈 Records Historiques", "Record Msg *Aujourd'hui*", "🏆", "msg_24h"),
            "record_msg_week": ("📈 Records Historiques", "Record Msg *Semaine*", "👑", "msg_week"),
            "record_msg_month": ("📈 Records Historiques", "Record Msg *Mois*", "💠", "msg_month"),
        }

        # Traitement des stats standards
        for field in active_fields:
            if field in mapping_standard:
                sec, label, emo = mapping_standard[field]
                sections[sec].append(f"› {emo} {label} : **{stats.get(field, 0)}**")

            # Traitement des Records (Affiche la valeur et la date en format `JJ/MM/AAAA`)
            elif field in mapping_records:
                sec, label, emo, rec_key = mapping_records[field]
                rec_data = stats.get("records", {}).get(rec_key, {"value": 0, "date": "N/A"})
                v = rec_data.get('value', 0)
                d = rec_data.get('date', 'N/A')
                sections[sec].append(f"› {emo} {label} : **{v}** `{d}`")

        # Traitement des Top Membres (Construction spécifique pour un visuel premium)
        if "top_vocal" in active_fields:
            uid = stats.get("top_vocal_id")
            val = stats.get("top_vocal_val", 0)
            mention = f"<@{uid}>" if uid else "Aucun"
            formatted_time = f"*{self.format_duration(val)}*"
            sections["🏆 Classements & Top Membres"].append(f"› 🌟 Top Vocal : {mention} {formatted_time}")

        if "top_msg" in active_fields:
            sections["🏆 Classements & Top Membres"].append("› 🏅 **Membres les plus Actifs :**")
            
            d_id, d_val = stats.get("top_msg_day_id"), stats.get("top_msg_day_val", 0)
            w_id, w_val = stats.get("top_msg_week_id"), stats.get("top_msg_week_val", 0)
            m_id, m_val = stats.get("top_msg_month_id"), stats.get("top_msg_month_val", 0)
            
            # Formatage avec abréviations soignées et italique
            sections["🏆 Classements & Top Membres"].append(f"ㅤ├ *Jour* : {f'<@{d_id}>' if d_id else 'N/A'} - *{self.format_msg_count(d_val)}*")
            sections["🏆 Classements & Top Membres"].append(f"ㅤ├ *Semaine* : {f'<@{w_id}>' if w_id else 'N/A'} - *{self.format_msg_count(w_val)}*")
            sections["🏆 Classements & Top Membres"].append(f"ㅤ└ *Mois* : {f'<@{m_id}>' if m_id else 'N/A'} - *{self.format_msg_count(m_val)}*")

        # Assemblage final
        desc = ""
        for section_title, lines in sections.items():
            if lines:
                desc += f"**{section_title}**\n" + "\n".join(lines) + "\n\n"
                
        return desc.strip() if desc else "*Aucune donnée configurée pour l'affichage.*"

    def build_preview_embed(self, guild: discord.Guild, config: dict, user: discord.Member) -> discord.Embed:
        ch_id = config.get('ch_stats_text')
        stats = self.get_guild_stats(guild, config)
        
        desc = (
            f"**Salon cible :** {f'<#{ch_id}>' if ch_id else '`Non défini`'}\n"
            f"**Fréquence d'actualisation :** `{StatsConfigView(self, guild, config, user).format_delay(config.get('delay', 300))}`\n\n"
            "**── APERÇU DE L'AFFICHAGE ──**\n\n"
        )
        
        desc += self.build_stats_layout(stats, config.get('fields', []))
        desc += "\n\n-# Utilisez le menu et les boutons ci-dessous pour modifier la configuration."
        
        embed = self.create_custom_embed(guild, user, "⚙️ Configuration AutoStats", desc)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        return embed

    # --- Événements & Tâches ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Mise en cache très performante des compteurs de messages."""
        if message.author.bot or not message.guild: return
        
        gid = message.guild.id
        uid = str(message.author.id)
        
        if gid not in self.user_msg_buffer:
            self.user_msg_buffer[gid] = {}
            
        self.message_buffer[gid] = self.message_buffer.get(gid, 0) + 1
        self.user_msg_buffer[gid][uid] = self.user_msg_buffer[gid].get(uid, 0) + 1

    @tasks.loop(seconds=30)
    async def update_stats_loop(self):
        try:
            tk = self.get_time_keys()
            
            for guild in self.bot.guilds:
                config = self.load_config(guild.id)
                if not config.get('module_enabled'): continue

                data_changed = False
                
                # 1. Mise à jour du temps de VOCAL global (Ajoute 30s à tous ceux connectés)
                for vc in guild.voice_channels:
                    for member in vc.members:
                        if not member.bot:
                            uid = str(member.id)
                            config['user_activity']['voice_all_time'][uid] = config['user_activity']['voice_all_time'].get(uid, 0) + 30
                            data_changed = True

                # 2. Gestion des dates de reset pour les Tops Messages
                msg_act = config['user_activity']['msg']
                if msg_act['date_day'] != tk['daily']:
                    msg_act['daily'] = {}; msg_act['date_day'] = tk['daily']
                    data_changed = True
                if msg_act['date_week'] != tk['weekly']:
                    msg_act['weekly'] = {}; msg_act['date_week'] = tk['weekly']
                    data_changed = True
                if msg_act['date_month'] != tk['monthly']:
                    msg_act['monthly'] = {}; msg_act['date_month'] = tk['monthly']
                    data_changed = True

                # 3. Dépôt des Buffers dans la persistance
                buffered_server_msgs = self.message_buffer.pop(guild.id, 0)
                if buffered_server_msgs > 0:
                    hist = config['msg_history']
                    hist['daily'][tk['daily']] = hist['daily'].get(tk['daily'], 0) + buffered_server_msgs
                    hist['weekly'][tk['weekly']] = hist['weekly'].get(tk['weekly'], 0) + buffered_server_msgs
                    hist['monthly'][tk['monthly']] = hist['monthly'].get(tk['monthly'], 0) + buffered_server_msgs
                    data_changed = True

                buffered_user_msgs = self.user_msg_buffer.pop(guild.id, {})
                for uid, count in buffered_user_msgs.items():
                    msg_act['daily'][uid] = msg_act['daily'].get(uid, 0) + count
                    msg_act['weekly'][uid] = msg_act['weekly'].get(uid, 0) + count
                    msg_act['monthly'][uid] = msg_act['monthly'].get(uid, 0) + count
                    data_changed = True

                # 4. Vérification et Update des Records Globaux
                stats = self.get_guild_stats(guild, config)
                recs = config['records']
                
                checks = [
                    ("members", stats['total']),
                    ("online", stats['online_total']),
                    ("vocal", stats['vocal_total']),
                    ("boosts", stats['boosts']),
                    ("msg_24h", stats['msg_24h']),
                    ("msg_week", stats['msg_week']),
                    ("msg_month", stats['msg_month'])
                ]
                
                for r_key, current_val in checks:
                    if current_val > recs.get(r_key, {}).get('value', 0):
                        recs[r_key] = {"value": current_val, "date": tk['display_date']}
                        data_changed = True

                if data_changed:
                    self.save_config(guild.id, config)

                # 5. Publication de l'Embed si nécessaire
                if not config.get('ch_stats_text'): continue
                
                delay = max(30, int(config.get('delay', 300)))
                now = time.time()
                if not hasattr(self, '_last_sent'): self._last_sent = {}
                last_sent = self._last_sent.get(guild.id, 0)
                
                if now - last_sent >= delay:
                    last_stats = config.get('last_stats', {})
                    # Critères de déclenchement (changement d'état majeur)
                    keys_to_check = ["total", "online_total", "vocal_total", "vocal_stream"]
                    if any(stats.get(k, 0) != last_stats.get(k, 0) for k in keys_to_check):
                        channel = guild.get_channel(config['ch_stats_text'])
                        if channel:
                            desc = self.build_stats_layout(stats, config.get('fields', []))
                            embed = self.create_custom_embed(guild, self.bot.user, None, desc)
                            embed.set_author(name=f"Évolution des Statistiques - {guild.name}", icon_url=guild.icon.url if guild.icon else None)
                            if guild.icon:
                                embed.set_thumbnail(url=guild.icon.url)
                            
                            try:
                                await channel.send(embed=embed)
                                self._last_sent[guild.id] = now
                            except discord.Forbidden:
                                logger.warning(f"[Stats] Permissions manquantes dans {guild.name}")
                            
                    config['last_stats'] = stats
                    self.save_config(guild.id, config)

        except Exception as e:
            logger.error(f"[Stats] Erreur critique dans la boucle : {e}\n{traceback.format_exc()}")

    @update_stats_loop.before_loop
    async def before_update_stats_loop(self):
        await self.bot.wait_until_ready()

    # --- Commandes ---

    @commands.hybrid_command(name="autostats", description="Configure le panneau dynamique des statistiques du serveur.")
    @commands.has_permissions(administrator=True)
    async def autostats(self, ctx: commands.Context):
        await ctx.defer(ephemeral=False)
        config = self.load_config(ctx.guild.id)
        view = StatsConfigView(self, ctx.guild, config, ctx.author)
        embed = self.build_preview_embed(ctx.guild, config, ctx.author)
        await ctx.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerStats(bot))