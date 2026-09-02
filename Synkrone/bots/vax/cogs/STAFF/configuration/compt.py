# -*- coding: utf-8-sig -*-
"""
COG COMPTEURS - Gestionnaire de statistiques vocales & compteurs Vax v3
=====================================================================
Version optimisée (UTF-8 avec BOM).
- Menu de navigation principal (Résumé, Emplacement, Fréquence, Choix, Config).
- Sélecteur de catégorie natif avec recherche.
- Sélecteurs de statistiques par thèmes.
- Configuration libre du nom des salons avec balise {count}.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import traceback
from typing import Any, Optional

import discord
from discord import ui
from discord.ext import commands, tasks

# Imports des utilitaires de l'architecture Vax
from utils.config_data import DataManager
from utils.config_emoji import Emoji as E
from utils.config_id import IdModal
from utils.config_perm import ensure_command_permission, perm_command
from utils.config_theme import config_manager

# ==========================================
# CONFIGURATION GLOBALE & LOGS
# ==========================================
DEBUG_MODE = True
ERROR_ONLY_MODE = False

def custom_log(level: str, message: str):
    is_error = level.lower() == "error"
    if ERROR_ONLY_MODE and not is_error:
        return
    if not DEBUG_MODE and not is_error:
        return

    colors = {
        "info": "\033[94m",    # Bleu
        "success": "\033[92m", # Vert
        "warning": "\033[93m", # Jaune
        "error": "\033[91m"    # Rouge
    }
    color = colors.get(level.lower(), "\033[0m")
    reset = "\033[0m"
    print(f"{color}[COMPTEURS] [{level.upper()}] {message}{reset}")

# Emojis Unicode bruts (Obligatoires pour les noms des salons Discord)
UNI_GRAPHIQUE = getattr(E, "GRAPHIQUE_FALLBACK", "📊")
UNI_PROFIL = getattr(E, "PROFIL_FALLBACK", "👤")
UNI_ONLINE = getattr(E, "STATUS_ONLINE_FALLBACK", "🟢")
UNI_BOT = getattr(E, "VAX_FALLBACK", "🤖")
UNI_ACCUEIL = getattr(E, "ACCUEIL_FALLBACK", "👋")
UNI_DOCUMENT = getattr(E, "DOCUMENT_FALLBACK", "📁")
UNI_ROLE = getattr(E, "ROLE_FALLBACK", "🎭")
UNI_VOCAL = "🎙️"
UNI_SALONS = "🔊"

# Mapping des noms pour l'affichage propre
STATS_LABELS = {
    "member": "Membres (Humains)",
    "online": "En ligne",
    "bots": "Bots",
    "voice": "En vocal",
    "dernier_membre": "Dernier rejoint",
    "salons": "Nombre de salons",
    "vocaux": "Nombre de vocaux",
    "roles": "Nombre de rôles"
}

# ==========================================
# GESTIONNAIRE DE DONNÉES (CRUD)
# ==========================================
class CompteursManager:
    def __init__(self):
        self.legacy_db = DataManager("utilitaires/compteurs")
        self.db = DataManager("public/utilitaires/compteurs")
        self._migrate_legacy_data()

    def _migrate_legacy_data(self) -> None:
        if not os.path.exists(self.legacy_db.path):
            return
        os.makedirs(self.db.path, exist_ok=True)
        for filename in os.listdir(self.legacy_db.path):
            if not filename.endswith(".json"): continue
            src = os.path.join(self.legacy_db.path, filename)
            dst = os.path.join(self.db.path, filename)
            if not os.path.exists(dst):
                shutil.copy2(src, dst)

    def load_guild(self, guild_id: int) -> dict[str, Any]:
        return self.db.load(guild_id) or {}

    def save_guild(self, guild_id: int, data: dict[str, Any]) -> None:
        self.db.save(guild_id, data)

compteurs_config_manager = CompteursManager()

# ==========================================
# UTILITAIRES & MODALS
# ==========================================
def parse_cooldown_to_seconds(raw: str) -> int:
    raw = raw.strip().lower()
    if raw.isdigit(): return int(raw)
    match = re.match(r"^(\d+)([smhj])$", raw)
    if not match: return 600
    val, unit = int(match.group(1)), match.group(2)
    multipliers = {"s": 1, "m": 60, "h": 3600, "j": 86400}
    return val * multipliers.get(unit, 60)

class CustomCooldownModal(ui.Modal, title="Cooldown personnalisé"):
    def __init__(self, view: "CompteursLayoutView"):
        super().__init__()
        self.view = view
        self.cd_input = ui.TextInput(
            label="Format (ex: 45s, 15m, 2h, 1j)",
            default=str(view.config.get("cooldown_raw", "10m")),
            max_length=10, required=True
        )
        self.add_item(self.cd_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        val = self.cd_input.value.strip()
        secs = parse_cooldown_to_seconds(val)
        
        self.view.config["cooldown_raw"] = val
        self.view.config["cooldown"] = secs
        compteurs_config_manager.save_guild(self.view.guild.id, self.view.config)
        self.view.cog.restart_task_for_guild(self.view.guild.id)
        
        await self.view._refresh_silent()
        await interaction.followup.send(f"{E.VALIDER} Cooldown défini à **{val}** ({secs}s).", ephemeral=True)


class RenameStatModal(ui.Modal, title="Configurer la statistique"):
    def __init__(self, view: "CompteursLayoutView", stat_key: str, current_format: str):
        super().__init__()
        self.view = view
        self.stat_key = stat_key
        
        self.format_input = ui.TextInput(
            label="Texte du salon (utiliser {count})",
            placeholder="Ex: 👤 Membres : {count}",
            default=current_format,
            max_length=90, 
            required=True
        )
        self.add_item(self.format_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        val = self.format_input.value.strip()
        
        # Sécurité : Forcer la présence de la balise
        if "{count}" not in val:
            val += " {count}"
            
        if "custom_names" not in self.view.config:
            self.view.config["custom_names"] = {}
            
        self.view.config["custom_names"][self.stat_key] = val
        compteurs_config_manager.save_guild(interaction.guild.id, self.view.config)
        
        # Force l'actualisation immédiate des salons avec le nouveau nom
        await self.view.cog.refresh_guild_channels(interaction.guild)
        await self.view._refresh_silent()
        await interaction.followup.send(f"{E.VALIDER} Nom mis à jour : `{val}`", ephemeral=True)


# ==========================================
# COMPOSANTS UI (NAVIGATION & SÉLECTEURS)
# ==========================================
class MainNavSelect(ui.Select):
    def __init__(self, view: "CompteursLayoutView"):
        self.parent_view = view
        options = [
            discord.SelectOption(label="Résumé", value="resume", emoji=E.LISTE, description="Vue d'ensemble des compteurs", default=(view.current_page == "resume")),
            discord.SelectOption(label="Emplacement", value="emplacement", emoji=E.DOCUMENT, description="Catégorie d'hébergement", default=(view.current_page == "emplacement")),
            discord.SelectOption(label="Fréquence", value="frequence", emoji=E.HORLOGE, description="Délai d'actualisation", default=(view.current_page == "frequence")),
            discord.SelectOption(label="Choix de statistiques", value="choix", emoji=E.AJOUTER, description="Activer/Désactiver des compteurs", default=(view.current_page == "choix")),
            discord.SelectOption(label="Configuration de statistiques", value="config", emoji=E.MODIFIER, description="Modifier les noms et balises", default=(view.current_page == "config")),
        ]
        super().__init__(placeholder="Navigation principale...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.parent_view.current_page = self.values[0]
        await self.parent_view._refresh_silent()


class CategoryChannelSelect(ui.ChannelSelect):
    def __init__(self, parent_view: "CompteursLayoutView"):
        self.parent_view = parent_view
        super().__init__(
            placeholder="🔍 Rechercher et lier une catégorie existante...",
            channel_types=[discord.ChannelType.category],
            min_values=1, max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        cat = self.values[0]
        self.parent_view.config["category_id"] = cat.id
        compteurs_config_manager.save_guild(interaction.guild.id, self.parent_view.config)
        await self.parent_view._refresh_silent()
        await interaction.followup.send(f"{E.VALIDER} Catégorie définie sur **{cat.name}**.", ephemeral=True)


async def handle_stats_update(interaction: discord.Interaction, view: "CompteursLayoutView", new_values: list[str], group_keys: list[str]):
    """Logique commune pour mettre à jour les statistiques selon le groupe choisi."""
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    current_stats = view.config.get("stats", [])
    
    # Remplacement sécurisé des statistiques actives
    updated_stats = [s for s in current_stats if s not in group_keys]
    updated_stats.extend(new_values)
    view.config["stats"] = updated_stats

    # Création de catégorie auto si nécessaire
    category = guild.get_channel(view.config.get("category_id")) if view.config.get("category_id") else None
    if updated_stats and not category:
        try:
            overwrites = {guild.default_role: discord.PermissionOverwrite(connect=False)}
            category = await guild.create_category(f"{UNI_GRAPHIQUE}│Compteurs", overwrites=overwrites)
            view.config["category_id"] = category.id
        except discord.Forbidden:
            return await interaction.followup.send(f"{E.REFUSER} Je n'ai pas la permission de créer des catégories.", ephemeral=True)

    vals = view.cog.get_stats_values(guild)

    # Application des changements (Création / Suppression)
    for key in group_keys:
        if key in new_values:
            channel = guild.get_channel(view.config.get(key))
            if not channel:
                name = view.cog.get_channel_name(guild.id, key, vals[key])
                try: channel = await guild.create_voice_channel(name, category=category)
                except discord.HTTPException: continue
            view.config[key] = channel.id
        else:
            if key in view.config:
                ch = guild.get_channel(view.config[key])
                if ch:
                    try: await ch.delete(reason="Option désactivée")
                    except discord.HTTPException: pass
                view.config.pop(key, None)

    # Nettoyage si tout est désactivé
    if len(view.config["stats"]) == 0:
        if "category_id" in view.config:
            cat = guild.get_channel(view.config["category_id"])
            if cat:
                try: await cat.delete(reason="Module compteur désactivé")
                except discord.HTTPException: pass
            view.config.pop("category_id", None)

    compteurs_config_manager.save_guild(guild.id, view.config)
    view.cog.restart_task_for_guild(guild.id)
    
    await view._refresh_silent()
    await interaction.followup.send(f"{E.VALIDER} Statistiques mises à jour avec succès.", ephemeral=True)


class StatsActivitySelect(ui.Select):
    def __init__(self, view: "CompteursLayoutView"):
        self.parent_view = view
        current_data = view.config.get("stats", [])
        options = [
            discord.SelectOption(label=STATS_LABELS["member"], value="member", emoji=E.PROFIL, default=("member" in current_data)),
            discord.SelectOption(label=STATS_LABELS["online"], value="online", emoji=E.STATUS_ONLINE, default=("online" in current_data)),
            discord.SelectOption(label=STATS_LABELS["bots"], value="bots", emoji=E.VAX, default=("bots" in current_data)),
            discord.SelectOption(label=STATS_LABELS["dernier_membre"], value="dernier_membre", emoji=E.ACCUEIL, default=("dernier_membre" in current_data)),
        ]
        super().__init__(placeholder="👤 Statistiques d'Activité & Membres...", min_values=0, max_values=len(options), options=options)

    async def callback(self, interaction: discord.Interaction):
        await handle_stats_update(interaction, self.parent_view, self.values, ["member", "online", "bots", "dernier_membre"])

class StatsServerSelect(ui.Select):
    def __init__(self, view: "CompteursLayoutView"):
        self.parent_view = view
        current_data = view.config.get("stats", [])
        options = [
            discord.SelectOption(label=STATS_LABELS["salons"], value="salons", emoji=E.DOCUMENT, default=("salons" in current_data)),
            discord.SelectOption(label=STATS_LABELS["vocaux"], value="vocaux", emoji=E.HORLOGE, default=("vocaux" in current_data)),
            discord.SelectOption(label=STATS_LABELS["roles"], value="roles", emoji=E.ROLE, default=("roles" in current_data)),
            discord.SelectOption(label=STATS_LABELS["voice"], value="voice", emoji=E.TEMPS, default=("voice" in current_data)),
        ]
        super().__init__(placeholder="📁 Statistiques Serveur & Structure...", min_values=0, max_values=len(options), options=options)

    async def callback(self, interaction: discord.Interaction):
        await handle_stats_update(interaction, self.parent_view, self.values, ["salons", "vocaux", "roles", "voice"])


class CooldownSelect(ui.Select):
    def __init__(self, view: "CompteursLayoutView"):
        self.parent_view = view
        current_raw = view.config.get("cooldown_raw", "10m")
        options = [
            discord.SelectOption(label="Instantané", value="instant", emoji=E.ECLAIR, default=(current_raw == "instant")),
            discord.SelectOption(label="1 minute", value="1m", emoji=E.HORLOGE, default=(current_raw == "1m")),
            discord.SelectOption(label="5 minutes", value="5m", emoji=E.HORLOGE, default=(current_raw == "5m")),
            discord.SelectOption(label="10 minutes", value="10m", emoji=E.HORLOGE, default=(current_raw == "10m")),
            discord.SelectOption(label="30 minutes", value="30m", emoji=E.HORLOGE, default=(current_raw == "30m")),
            discord.SelectOption(label="1 heure", value="1h", emoji=E.TEMPS, default=(current_raw == "1h")),
            discord.SelectOption(label="Personnalisé", value="custom", emoji=E.MODIFIER, default=(current_raw not in ["instant", "1m", "5m", "10m", "30m", "1h"])),
        ]
        super().__init__(placeholder="⏱️ Fréquence de mise à jour...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val == "custom":
            return await interaction.response.send_modal(CustomCooldownModal(self.parent_view))
            
        await interaction.response.defer(ephemeral=True)
        secs = 0 if val == "instant" else parse_cooldown_to_seconds(val)
        self.parent_view.config["cooldown_raw"] = val
        self.parent_view.config["cooldown"] = secs
        compteurs_config_manager.save_guild(self.parent_view.guild.id, self.parent_view.config)
        self.parent_view.cog.restart_task_for_guild(self.parent_view.guild.id)
        
        await self.parent_view._refresh_silent()
        await interaction.followup.send(f"{E.VALIDER} Fréquence mise à jour : **{val}**.", ephemeral=True)


class RenameStatSelect(ui.Select):
    def __init__(self, view: "CompteursLayoutView"):
        self.parent_view = view
        active_stats = view.config.get("stats", [])
        
        stat_meta = {
            "member": (STATS_LABELS["member"], E.PROFIL),
            "online": (STATS_LABELS["online"], E.STATUS_ONLINE),
            "bots": (STATS_LABELS["bots"], E.VAX),
            "dernier_membre": (STATS_LABELS["dernier_membre"], E.ACCUEIL),
            "salons": (STATS_LABELS["salons"], E.DOCUMENT),
            "vocaux": (STATS_LABELS["vocaux"], E.HORLOGE),
            "roles": (STATS_LABELS["roles"], E.ROLE),
            "voice": (STATS_LABELS["voice"], E.TEMPS)
        }
        
        options = []
        for k in active_stats:
            if k in stat_meta:
                options.append(discord.SelectOption(label=stat_meta[k][0], value=k, emoji=stat_meta[k][1]))
                
        if not options:
            options.append(discord.SelectOption(label="Aucune statistique active", value="none", emoji=E.REFUSER))
            
        super().__init__(placeholder="Sélectionnez un compteur à renommer...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val == "none":
            await interaction.response.defer()
            return
            
        # On passe "{count}" en valeur brute pour récupérer le template complet
        current_format = self.parent_view.cog.get_channel_name(interaction.guild.id, val, "{count}")
        await interaction.response.send_modal(RenameStatModal(self.parent_view, val, current_format))


# ==========================================
# GESTIONNAIRE DE VUES (LAYOUTV2)
# ==========================================
class CompteursLayoutView(ui.LayoutView):
    def __init__(self, cog: "CompteursCog", guild: discord.Guild, author: discord.Member):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild = guild
        self.author = author
        self.message: Optional[discord.Message] = None
        self.config = compteurs_config_manager.load_guild(self.guild.id)
        self.current_page = "resume"
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(f"{E.REFUSER} Ce menu de configuration ne vous appartient pas.", ephemeral=True)
            return False
        return True

    async def _refresh_silent(self):
        self.config = compteurs_config_manager.load_guild(self.guild.id)
        self._build()
        if self.message:
            try: await self.message.edit(view=self)
            except discord.HTTPException: pass

    def _build(self):
        self.clear_items()
        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.author, self.cog.bot)
        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text", "")

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        
        # Header global
        container.add_item(ui.TextDisplay(f"# {E.GRAPHIQUE} Compteurs & Statistiques"))
        
        # Navigation Principale (Toujours présente)
        nav_row = ui.ActionRow()
        nav_row.add_item(MainNavSelect(self))
        container.add_item(nav_row)
        
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

        # ================= PAGE : RÉSUMÉ =================
        if self.current_page == "resume":
            cat_id = self.config.get("category_id")
            cat_obj = self.guild.get_channel(cat_id) if cat_id else None
            cat_name = f"**{cat_obj.name}**" if isinstance(cat_obj, discord.CategoryChannel) else "*Automatique*"
            cd_raw = self.config.get("cooldown_raw", "10m")
            active_stats = self.config.get("stats", [])
            active_count = len(active_stats)
            
            channels_text = ""
            if active_stats:
                for key in active_stats:
                    cid = self.config.get(key)
                    if cid:
                        ch = self.guild.get_channel(cid)
                        ch_display = ch.mention if ch else "*Salon introuvable ou supprimé*"
                        label = STATS_LABELS.get(key, key)
                        channels_text += f"- **{label}** : {ch_display}\n"
            else:
                channels_text = "*Aucun compteur configuré.*"
            
            resume_text = (
                f"**Catégorie d'hébergement :** {cat_name}\n"
                f"**Fréquence d'actualisation :** `{cd_raw}`\n"
                f"**Compteurs actifs :** `{active_count}`\n\n"
                f"**Salons configurés :**\n{channels_text}"
            )
            container.add_item(ui.TextDisplay(f"### {E.LISTE} Résumé de la configuration"))
            container.add_item(ui.TextDisplay(resume_text))

        # ================= PAGE : EMPLACEMENT =================
        elif self.current_page == "emplacement":
            cat_id = self.config.get("category_id")
            cat_obj = self.guild.get_channel(cat_id) if cat_id else None
            cat_name = f"**{cat_obj.name}**" if isinstance(cat_obj, discord.CategoryChannel) else "*Automatique*"
            
            container.add_item(ui.TextDisplay(f"### {E.DOCUMENT} Emplacement\nCatégorie actuelle : {cat_name}"))
            
            cat_select_row = ui.ActionRow()
            cat_select_row.add_item(CategoryChannelSelect(self))
            container.add_item(cat_select_row)

            cat_btn_row = ui.ActionRow()
            btn_cat_auto = ui.Button(label="Générer Auto", style=discord.ButtonStyle.success, emoji=E.RAFRAICHIR)
            btn_cat_auto.callback = self.on_cat_auto_click
            cat_btn_row.add_item(btn_cat_auto)

            btn_cat_id = ui.Button(label="Lier un ID", style=discord.ButtonStyle.secondary, emoji=E.IDENTIFIANT)
            btn_cat_id.callback = self.on_cat_id_click
            cat_btn_row.add_item(btn_cat_id)
            container.add_item(cat_btn_row)


        # ================= PAGE : FRÉQUENCE =================
        elif self.current_page == "frequence":
            cd_raw = self.config.get("cooldown_raw", "10m")
            container.add_item(ui.TextDisplay(f"### {E.HORLOGE} Fréquence d'actualisation\nActuelle : `{cd_raw}`"))
            cd_row = ui.ActionRow()
            cd_row.add_item(CooldownSelect(self))
            container.add_item(cd_row)

        # ================= PAGE : CHOIX =================
        elif self.current_page == "choix":
            container.add_item(ui.TextDisplay(f"### {E.AJOUTER} Choix des statistiques"))
            stats_act_row = ui.ActionRow()
            stats_act_row.add_item(StatsActivitySelect(self))
            container.add_item(stats_act_row)

            stats_srv_row = ui.ActionRow()
            stats_srv_row.add_item(StatsServerSelect(self))
            container.add_item(stats_srv_row)

        # ================= PAGE : CONFIG =================
        elif self.current_page == "config":
            active_stats = self.config.get("stats", [])
            current_names_text = ""
            if active_stats:
                for key in active_stats:
                    template = self.cog.get_channel_name(self.guild.id, key, "{count}")
                    label = STATS_LABELS.get(key, key)
                    current_names_text += f"- **{label}** : `{template}`\n"
            else:
                current_names_text = "*Aucune statistique active.*"

            container.add_item(ui.TextDisplay(f"### {E.MODIFIER} Configuration de statistiques"))
            container.add_item(ui.TextDisplay("Utilisez le menu ci-dessous pour renommer un salon.\n*Vous devez utiliser la balise `{count}` pour indiquer où placer le chiffre.*\n\n**Formats actuels :**\n" + current_names_text))
            
            rename_row = ui.ActionRow()
            rename_row.add_item(RenameStatSelect(self))
            container.add_item(rename_row)


        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    async def on_cat_auto_click(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if "category_id" in self.config:
            self.config.pop("category_id")
            compteurs_config_manager.save_guild(self.guild.id, self.config)
        await self._refresh_silent()
        await interaction.followup.send(f"{E.VALIDER} Le bot générera une catégorie automatiquement.", ephemeral=True)

    async def on_cat_id_click(self, interaction: discord.Interaction):
        async def callback(inter, target):
            await inter.response.defer(ephemeral=True)
            if isinstance(target, discord.CategoryChannel):
                self.config["category_id"] = target.id
                compteurs_config_manager.save_guild(self.guild.id, self.config)
                await self._refresh_silent()
                await inter.followup.send(f"{E.VALIDER} Catégorie liée avec succès.", ephemeral=True)
            else:
                await inter.followup.send(f"{E.REFUSER} ID invalide (ce n'est pas une catégorie).", ephemeral=True)

        await interaction.response.send_modal(IdModal("category", callback))


# ==========================================
# COG PRINCIPAL & GESTION DES TACHES
# ==========================================
class CompteursCog(commands.Cog, name="Compteurs"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guild_tasks: dict[int, asyncio.Task] = {}
        self.bot.loop.create_task(self.init_dynamic_tasks())

    def cog_unload(self):
        for task in self.guild_tasks.values():
            task.cancel()

    async def init_dynamic_tasks(self):
        await self.bot.wait_until_ready()
        for guild in self.bot.guilds:
            self.restart_task_for_guild(guild.id)

    def restart_task_for_guild(self, guild_id: int):
        if guild_id in self.guild_tasks:
            self.guild_tasks[guild_id].cancel()
            del self.guild_tasks[guild_id]
            
        config = compteurs_config_manager.load_guild(guild_id)
        if not config.get("stats"): return
            
        cooldown = config.get("cooldown", 600)
        if cooldown <= 0: return
            
        task = self.bot.loop.create_task(self.guild_refresh_loop(guild_id, cooldown))
        self.guild_tasks[guild_id] = task

    async def guild_refresh_loop(self, guild_id: int, interval: int):
        await self.bot.wait_until_ready()
        while True:
            try:
                await asyncio.sleep(interval)
                guild = self.bot.get_guild(guild_id)
                if guild: await self.refresh_guild_channels(guild)
            except asyncio.CancelledError:
                break
            except Exception as e:
                custom_log("error", f"Erreur loop {guild_id}: {e}")

    def get_stats_values(self, guild: discord.Guild) -> dict[str, Any]:
        humans = [m for m in guild.members if not m.bot]
        bots = [m for m in guild.members if m.bot]
        online = [m for m in humans if m.status != discord.Status.offline]
        voice = sum(len(vc.members) for vc in guild.voice_channels)
        
        sorted_members = sorted(
            [m for m in guild.members if not m.bot], 
            key=lambda m: m.joined_at or discord.utils.utcnow(), 
            reverse=True
        )
        dernier_membre = sorted_members[0].display_name if sorted_members else "Aucun"

        return {
            "member": len(humans), "online": len(online), "bots": len(bots),
            "voice": voice, "dernier_membre": dernier_membre,
            "salons": len(guild.channels), "vocaux": len(guild.voice_channels), "roles": len(guild.roles)
        }

    def get_channel_name(self, guild_id: int, key: str, count_val: Any) -> str:
        """Récupère le nom formaté du salon en fonction de la configuration utilisateur ou par défaut."""
        data = compteurs_config_manager.load_guild(guild_id)
        custom_names = data.get("custom_names", {})
        
        default_names = {
            "member": f"{UNI_PROFIL}│Membres : {{count}}",
            "online": f"{UNI_ONLINE}│En ligne : {{count}}",
            "bots": f"{UNI_BOT}│Bots : {{count}}",
            "voice": f"{UNI_VOCAL}│En vocal : {{count}}",
            "dernier_membre": f"{UNI_ACCUEIL}│Bienvenue : {{count}}",
            "salons": f"{UNI_DOCUMENT}│Salons : {{count}}",
            "vocaux": f"{UNI_SALONS}│Vocaux : {{count}}",
            "roles": f"{UNI_ROLE}│Rôles : {{count}}"
        }
        
        template = custom_names.get(key, default_names.get(key, "Stats : {count}"))
        return template.replace("{count}", str(count_val))

    async def refresh_guild_channels(self, guild: discord.Guild, voice_only: bool = False):
        data = compteurs_config_manager.load_guild(guild.id)
        active_stats = data.get("stats", [])
        if not data or not active_stats: return
            
        vals = self.get_stats_values(guild)
        
        for key in active_stats:
            cid = data.get(key)
            if cid:
                if voice_only and key not in {"voice", "dernier_membre"}: continue
                
                ch = guild.get_channel(cid)
                if ch:
                    new_name = self.get_channel_name(guild.id, key, vals[key])
                    if ch.name != new_name:
                        try: await ch.edit(name=new_name)
                        except discord.HTTPException: pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        config = compteurs_config_manager.load_guild(member.guild.id)
        if config.get("cooldown", 600) == 0 and before.channel != after.channel:
            await self.refresh_guild_channels(member.guild, voice_only=True)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        config = compteurs_config_manager.load_guild(member.guild.id)
        if config.get("cooldown", 600) == 0 and member.guild:
            await self.refresh_guild_channels(member.guild, voice_only=False)

    @perm_command(level=3)
    @commands.hybrid_command(name="compt", description="Gère les compteurs et statistiques du serveur.")
    async def compt(self, ctx: commands.Context):
        init_msg = await ctx.send(f"{E.LOAD} Chargement du panel...")
        
        try:
            if not ctx.guild:
                return await init_msg.edit(content=f"{E.REFUSER} Commande serveur uniquement.")
            if not await ensure_command_permission(ctx, command_name="compt"):
                return await init_msg.delete()

            custom_log("info", f"Compteurs ouverts par {ctx.author.name} ({ctx.guild.name})")
            
            view = CompteursLayoutView(self, ctx.guild, ctx.author)
            await init_msg.edit(content=None, view=view)
            view.message = init_msg
            
        except Exception as e:
            error_trace = traceback.format_exc()
            await init_msg.edit(
                content=f"{E.ATTENTION} **Erreur interne :**\n`{e}`\n```py\n{error_trace[:1500]}\n```",
                view=None
            )

async def setup(bot: commands.Bot):
    await bot.add_cog(CompteursCog(bot))