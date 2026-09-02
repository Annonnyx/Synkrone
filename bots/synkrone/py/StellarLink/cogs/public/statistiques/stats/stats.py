import discord
from discord.ext import commands, tasks
from discord import app_commands, ui
import sqlite3
import time
import os
import json
import re
from datetime import datetime, timedelta
import traceback
import logging



# --- CONFIGURATION ET CHEMINS DE PERSISTANCE ---
# Placer la base de données dans le même dossier que stats.py
DB_PATH = os.path.join(os.path.dirname(__file__), "stats_bot.db")

logger = logging.getLogger("bot.stats")

# --- CHARGEMENT DU CONFIG MANAGER PREMIUM ---
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# ==============================================================================
# ----------------------- COUCHE DE PERSISTANCE SQLITE ------------------------
# ==============================================================================

def get_db_connection():
    """Établit la connexion avec mappage par nom de colonne."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def setup_database():
    """Initialise le schéma relationnel en utilisant des BIGINT pour les IDs."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS activity (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id BIGINT, 
        guild_id BIGINT, 
        type TEXT, 
        value INTEGER, 
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

setup_database()

# ==============================================================================
# --------------------------- COMPOSANTS DE L'UI (VIEWS) -----------------------
# ==============================================================================

class TargetUserSelect(ui.UserSelect):
    """Sélecteur natif Discord pour cibler un utilisateur précis."""
    def __init__(self):
        super().__init__(
            placeholder="🔍 Sélectionnez un membre pour analyser son profil...",
            min_values=1,
            max_values=1,
            row=3
        )

    async def callback(self, interaction: discord.Interaction):
        view: 'StatsView' = self.view
        selected_user = self.values[0]
        
        if isinstance(selected_user, discord.User):
            member = interaction.guild.get_member(selected_user.id) or selected_user
        else:
            member = selected_user

        view.target_member = member
        view.current_mode = "profile"
        view.current_page = 1
        await view.update_view(interaction)


class PeriodSelect(ui.Select):
    """Sélecteur de plages temporelles."""
    def __init__(self, current_label: str):
        super().__init__(
            placeholder=f"🕒 Durée : {current_label}",
            options=[
                discord.SelectOption(label="Dernière Heure", value="1h", emoji="1️⃣"),
                discord.SelectOption(label="Dernières 24h", value="24h", emoji="🕧"),
                discord.SelectOption(label="7 Jours", value="7j", emoji="📅"),
                discord.SelectOption(label="30 Jours", value="30j", emoji="📆"),
                discord.SelectOption(label="Format Custom...", value="custom", emoji="⚙️")
            ], row=0
        )

    async def callback(self, interaction: discord.Interaction):
        view: 'StatsView' = self.view
        val = self.values[0]
        
        if val == "custom":
            await interaction.response.send_modal(CustomPeriodModal(view))
            return
        
        deltas = {"1h": 1, "24h": 24, "7j": 168, "30j": 720}
        view.current_period_hours = deltas.get(val, 720)
        view.current_period_label = val
        view.current_page = 1
        await view.update_view(interaction)


class ModeSelect(ui.Select):
    """Sélecteur de type de rendu graphique."""
    def __init__(self):
        super().__init__(
            placeholder="📊 Mode d'affichage des classements",
            options=[
                discord.SelectOption(label="Vue d'ensemble & Cumuls", value="overview", emoji="🏆"),
                discord.SelectOption(label="Liste paginée (Messages)", value="list_msg", emoji="💬"),
                discord.SelectOption(label="Liste paginée (Vocal)", value="list_voice", emoji="🎙️")
            ], row=1
        )

    async def callback(self, interaction: discord.Interaction):
        view: 'StatsView' = self.view
        view.current_mode = self.values[0]
        view.current_page = 1
        await view.update_view(interaction)


class TargetSelect(ui.Select):
    """Sélecteur de prisme de données (Serveur / Soi / Tiers)."""
    def __init__(self):
        super().__init__(
            placeholder="🎯 Choisir la cible des données",
            options=[
                discord.SelectOption(label="Global Serveur", value="target_global", emoji="🌍"),
                discord.SelectOption(label="Mon Profil", value="target_me", emoji="👤"),
                discord.SelectOption(label="Profil de...", value="target_select_user", emoji="🔍")
            ], row=2
        )

    async def callback(self, interaction: discord.Interaction):
        view: 'StatsView' = self.view
        val = self.values[0]
        
        if val == "target_global":
            view._show_user_picker = False
            view.current_mode = "overview"
            view.target_member = None
        elif val == "target_me":
            view._show_user_picker = False
            view.current_mode = "profile"
            view.target_member = view.executor
        elif val == "target_select_user":
            view._show_user_picker = True
            
        await view.update_view(interaction)


class ToggleIdButton(ui.Button):
    """Bouton de masquage dynamique des identifiants."""
    def __init__(self, show_ids: bool):
        super().__init__(
            label="Masquer les IDs" if show_ids else "Afficher les IDs",
            style=discord.ButtonStyle.secondary, emoji="🏷️", row=4
        )

    async def callback(self, interaction: discord.Interaction):
        view: 'StatsView' = self.view
        view.show_ids = not view.show_ids
        await view.update_view(interaction)


class PaginationButton(ui.Button):
    """Gestionnaire universel de pagination."""
    def __init__(self, label: str, emoji: str, is_next: bool, disabled: bool):
        super().__init__(label=label, style=discord.ButtonStyle.primary, emoji=emoji, row=4, disabled=disabled)
        self.is_next = is_next

    async def callback(self, interaction: discord.Interaction):
        view: 'StatsView' = self.view
        if self.is_next:
            view.current_page += 1
        else:
            view.current_page = max(1, view.current_page - 1)
        await view.update_view(interaction)

# ==============================================================================
# ----------------------------- COMPOSANT MODAL --------------------------------
# ==============================================================================

class CustomPeriodModal(ui.Modal, title='Durée personnalisée'):
    duration_input = ui.TextInput(
        label='Entrez une durée (ex: 45m, 12h, 5j)',
        placeholder='Format : [nombre][m/h/j]',
        style=discord.TextStyle.short,
        required=True,
        max_length=10
    )

    def __init__(self, view: 'StatsView'):
        super().__init__()
        self.stats_view = view

    async def on_submit(self, interaction: discord.Interaction):
        value = self.duration_input.value.strip().lower()
        match = re.match(r'^(\d+)([mhj])$', value)
        
        if not match:
            await interaction.response.send_message("❌ Format temporel incorrect (`m`, `h`, `j`).", ephemeral=True)
            return

        amount = int(match.group(1))
        unit = match.group(2)
        
        if unit == 'm': hours = amount / 60
        elif unit == 'h': hours = amount
        elif unit == 'j': hours = amount * 24
        else: hours = 24

        self.stats_view.current_period_hours = hours
        self.stats_view.current_period_label = value
        self.stats_view.current_page = 1
        await self.stats_view.update_view(interaction)

# ==============================================================================
# -------------------------- VUE DE CONTRÔLE PRINCIPALE ------------------------
# ==============================================================================

class StatsView(ui.View):
    def __init__(self, cog: 'Stats', guild: discord.Guild, executor: discord.Member, target_member: discord.Member = None):
        super().__init__(timeout=300.0)
        self.cog = cog
        self.guild = guild
        self.executor = executor
        self.target_member = target_member
        
        self.current_period_hours = 720  
        self.current_period_label = "30j"
        self.current_mode = "profile" if target_member else "overview"
        self.show_ids = False
        self.current_page = 1
        self.items_per_page = 10
        self._show_user_picker = False
        self.message = None
        
        self.build_ui()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.executor.id:
            await interaction.response.send_message("❌ Menu réservé à l'exécuteur de la commande.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass

    def build_ui(self):
        """Réorganise l'arborescence des composants selon l'état."""
        self.clear_items()
        
        self.add_item(PeriodSelect(self.current_period_label))
        self.add_item(ModeSelect())
        self.add_item(TargetSelect())

        if self._show_user_picker:
            self.add_item(TargetUserSelect())

        self.add_item(ToggleIdButton(self.show_ids))

        if self.current_mode in ["list_msg", "list_voice"]:
            self.add_item(PaginationButton("Précédent", "◀", is_next=False, disabled=(self.current_page == 1)))
            self.add_item(PaginationButton("Suivant", "▶", is_next=True, disabled=False))

    async def update_view(self, interaction: discord.Interaction):
        self.build_ui()
        embed = await self.generate_embed()
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    def format_user_display(self, user_id: int) -> str:
        return f"<@{user_id}> `({user_id})`" if self.show_ids else f"<@{user_id}>"

    async def generate_embed(self) -> discord.Embed:
        # Calcul du timestamp de référence au format SQLite ISO
        since = (datetime.now() - timedelta(hours=self.current_period_hours)).strftime('%Y-%m-%d %H:%M:%S')
        conn = get_db_connection()
        cursor = conn.cursor()

        title = f"📊 Centre de Données — {self.current_period_label}"
        desc = ""

        try:
            # --- APPAREIL DE RENDU : MODE PROFIL ---
            if self.current_mode == "profile" or self.target_member is not None:
                member_target = self.target_member or self.executor
                
                cursor.execute(
                    "SELECT type, SUM(value) as total FROM activity WHERE user_id = ? AND guild_id = ? AND timestamp > ? GROUP BY type", 
                    (member_target.id, self.guild.id, since)
                )
                res = {row['type']: row['total'] for row in cursor.fetchall()}
                
                v_live = int(time.time() - self.cog.voice_tracking.get(member_target.id, time.time())) if member_target.id in self.cog.voice_tracking else 0
                
                desc = (
                    f"### 👤 Profil de {member_target.mention}\n\n"
                    f"💬 **Messages émis** : `{res.get('message', 0)}`\n"
                    f"🎙️ **Temps en Vocal** : `{self.cog.format_duration(res.get('voice_duration', 0) + v_live)}`\n"
                    f"🔇 **Coupures Micro** : `{res.get('mute_count', 0)}` fois\n"
                    f"🎧 **Mutes Casque** : `{res.get('deaf_count', 0)}` fois\n"
                )

            # --- APPAREIL DE RENDU : MODE SERVEUR (SYNTHÈSE) ---
            elif self.current_mode == "overview":
                cursor.execute(
                    "SELECT type, SUM(value) as total FROM activity WHERE guild_id = ? AND timestamp > ? GROUP BY type", 
                    (self.guild.id, since)
                )
                totals = {row['type']: row['total'] for row in cursor.fetchall()}
                total_v_live = sum(int(time.time() - start_t) for start_t in self.cog.voice_tracking.values())
                
                current_voice = len([m for m in self.guild.members if m.voice and not m.bot])
                current_muted = len([m for m in self.guild.members if m.voice and (m.voice.self_mute or m.voice.mute) and not m.bot])
                current_deaf = len([m for m in self.guild.members if m.voice and (m.voice.self_deaf or m.voice.deaf) and not m.bot])

                desc = (
                    f"### 🌍 Indicateurs Globaux\n"
                    f"💬 **Volume Messages** : `{totals.get('message', 0)}`\n"
                    f"🎙️ **Volume Vocal** : `{self.cog.format_duration((totals.get('voice_duration', 0) or 0) + total_v_live)}`\n"
                    f"🔨 **Sanctions (Bans)** : `{totals.get('ban_count', 0)}` enregistrées\n\n"
                    f"### 🎯 État des Salons Vocaux (Live)\n"
                    f"👥 **Connectés** : `{current_voice}` membres\n"
                    f"🎙️ **Sourdines Micro** : `{current_muted}` actifs\n"
                    f"🎧 **Sourdines Totales** : `{current_deaf}` isolés\n"
                )

            # --- APPAREIL DE RENDU : LISTES COMPLETES ---
            elif self.current_mode in ["list_msg", "list_voice"]:
                stat_type = 'message' if self.current_mode == "list_msg" else 'voice_duration'
                emoji = "💬" if stat_type == 'message' else "🎙️"
                
                cursor.execute(
                    "SELECT user_id, SUM(value) as total FROM activity WHERE guild_id = ? AND type = ? AND timestamp > ? GROUP BY user_id ORDER BY total DESC", 
                    (self.guild.id, stat_type, since)
                )
                data = {row['user_id']: row['total'] for row in cursor.fetchall()}
                
                if stat_type == 'voice_duration':
                    for u_id, start_t in self.cog.voice_tracking.items():
                        data[u_id] = data.get(u_id, 0) + int(time.time() - start_t)
                        
                sorted_data = sorted(data.items(), key=lambda x: x[1], reverse=True)
                
                start_idx = (self.current_page - 1) * self.items_per_page
                end_idx = start_idx + self.items_per_page
                page_data = sorted_data[start_idx:end_idx]
                
                lines = []
                for i, (u_id, val) in enumerate(page_data, start=start_idx + 1):
                    val_str = f"`{val}` messages" if stat_type == 'message' else f"`{self.cog.format_duration(val)}`"
                    lines.append(f"**{i}.** {self.format_user_display(u_id)} : {val_str}")
                
                total_pages = max(1, (len(sorted_data) + self.items_per_page - 1) // self.items_per_page)
                desc = f"### {emoji} Tableau d'activité (Page {self.current_page}/{total_pages})\n" + ("\n".join(lines) if lines else "*Aucune ligne de log.*")

        except Exception as e:
            logger.error(f"Erreur fatale : {e}\n{traceback.format_exc()}")
            desc = "❌ Corruption temporaire de l'extraction."
        finally:
            conn.close()

        if config_manager:
            embed = config_manager.get_formatted_embed(self.guild, self.executor, self.cog.bot, title, desc, self.guild.id)
        else:
            embed = discord.Embed(title=title, description=desc, color=0x2b2d31)
            embed.set_footer(text=f"Propriété exclusive de {self.executor.display_name}")

        return embed

# ==============================================================================
# ------------------------------- COG DE RECOUVREMENT --------------------------
# ==============================================================================

class Stats(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.voice_tracking = {}
        self.cleanup_task.start()

    def cog_unload(self):
        self.cleanup_task.cancel()


    # Suppression de la gestion de config JSON, tracking toujours actif
    def log_activity(self, user_id: int, guild_id: int, act_type: str, value: int = 1):
        try:
            conn = get_db_connection()
            conn.execute(
                "INSERT INTO activity (user_id, guild_id, type, value) VALUES (?, ?, ?, ?)", 
                (user_id, guild_id, act_type, value)
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    @tasks.loop(hours=24)
    async def cleanup_task(self):
        limit = datetime.now() - timedelta(days=30)
        try:
            conn = get_db_connection()
            conn.execute("DELETE FROM activity WHERE timestamp < ?", (limit,))
            conn.commit()
            conn.close()
        except Exception:
            pass

    def format_duration(self, total_seconds: int) -> str:
        hours, remainder = divmod(int(max(0, total_seconds)), 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0: return f"{hours}h {minutes}m"
        if minutes > 0: return f"{minutes}m {seconds}s"
        return f"{seconds}s"

    # --- RECRUTEMENT ANALYTIQUE DES LISTENERS ---

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild: return
        self.log_activity(message.author.id, message.guild.id, 'message', 1)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        self.log_activity(user.id, guild.id, 'ban_count', 1)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot: return

        if not before.self_mute and after.self_mute:
            self.log_activity(member.id, member.guild.id, 'mute_count', 1)
        if not before.self_deaf and after.self_deaf:
            self.log_activity(member.id, member.guild.id, 'deaf_count', 1)

        joined = not before.channel and after.channel
        left = before.channel and not after.channel

        if joined:
            self.voice_tracking[member.id] = time.time()
        elif left:
            start_time = self.voice_tracking.pop(member.id, None)
            if start_time:
                duration = int(time.time() - start_time)
                if duration > 2:
                    self.log_activity(member.id, member.guild.id, 'voice_duration', duration)

    # --- COMMANDE HYBRIDE PREMIUM ---

    @commands.hybrid_command(name="stats", description="Pilote analytique de monitoring du serveur.")
    @app_commands.describe(membre="Analyse ciblée immédiate")
    async def stats_cmd(self, ctx: commands.Context, membre: discord.Member = None):
        if not ctx.guild:
            await ctx.send("❌ Commande interne de guilde.")
            return

        try:
            await ctx.defer()
            view = StatsView(self, ctx.guild, ctx.author, target_member=membre)
            embed = await view.generate_embed()
            
            msg = await ctx.send(embed=embed, view=view)
            view.message = msg
            
        except Exception:
            logger.error(traceback.format_exc())
            await ctx.send("❌ Échec d'allocation du module d'interface.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Stats(bot))