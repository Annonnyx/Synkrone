# -*- coding: utf-8 -*-
"""
COG GIVEAWAY - Gestionnaire de Tirages au Sort Vax v3
=====================================================
Système avancé de giveaways interactifs avec LayoutV2.
Supporte les conditions de rôles, le reroll, les durées rapides, 
et un affichage dynamique 100% public (zéro message éphémère).
"""

from __future__ import annotations

import asyncio
import random
import time
import traceback
from datetime import datetime, timedelta
from typing import Any, Optional

import discord
import pytz
from discord import app_commands, ui
from discord.ext import commands, tasks

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

FRENCH_TZ = pytz.timezone('Europe/Paris')

def custom_log(level: str, message: str):
    """Système de logs colorés respectant les variables globales de debug."""
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
    print(f"{color}[GIVEAWAY] [{level.upper()}] {message}{reset}")

# ==========================================
# CENTRALISATION DES EMOJIS
# ==========================================
EMOJI_CADEAU = getattr(E, "CADEAU", "ðŸŽ")
EMOJI_CLASSEMENT = getattr(E, "CLASSEMENT", "ðŸ†")
EMOJI_HORLOGE = getattr(E, "HORLOGE", "â°")
EMOJI_SALON = getattr(E, "DOCUMENT", "ðŸ“")
EMOJI_CLOCHE = getattr(E, "CLOCHE", "ðŸ””")
EMOJI_VALIDER = getattr(E, "VALIDER", "âœ…")
EMOJI_REFUSER = getattr(E, "REFUSER", "âŒ")
EMOJI_PARAMETRES = getattr(E, "PARAMETRES", "âš™ï¸")
EMOJI_ENVOYER = getattr(E, "SEND", "ðŸš€")
EMOJI_MODIFIER = getattr(E, "MODIFIER", "âœï¸")
EMOJI_SUPPRIMER = getattr(E, "SUPPRIMER", "ðŸ—‘ï¸")
EMOJI_RAFRAICHIR = getattr(E, "RAFRAICHIR", "ðŸ”„")
EMOJI_LOCK = getattr(E, "LOCK", "ðŸ”’")
EMOJI_UNLOCK = getattr(E, "UNLOCK", "ðŸ”“")
EMOJI_ROLE = getattr(E, "ROLE", "ðŸŽ­")
EMOJI_ID = getattr(E, "IDENTIFIANT", "ðŸ†”")
EMOJI_RETOUR = getattr(E, "RETOUR", "â—€ï¸")
EMOJI_ATTENTION = getattr(E, "ATTENTION", "âš ï¸")

# Durées rapides configurables
DURATIONS = {
    "30m": timedelta(minutes=30),
    "1h": timedelta(hours=1),
    "3h": timedelta(hours=3),
    "6h": timedelta(hours=6),
    "9h": timedelta(hours=9),
    "12h": timedelta(hours=12),
    "1j": timedelta(days=1),
    "3j": timedelta(days=3),
    "1 mois": timedelta(days=30)
}

# ==========================================
# GESTIONNAIRE DE DONNÉES (CRUD)
# ==========================================
class GiveawayManager:
    """Gestionnaire centralisé des giveaways par serveur via DataManager."""
    def __init__(self):
        self.db = DataManager("public/utilitaires/giveaways")

    def _normalize(self, raw: dict[str, Any] | None) -> dict[str, Any]:
        src = raw or {}
        return {
            "settings": src.get("settings", {}),
            "active": src.get("active", {})
        }

    def load_guild(self, guild_id: int) -> dict[str, Any]:
        return self._normalize(self.db.load(guild_id))

    def save_guild(self, guild_id: int, data: dict[str, Any]) -> None:
        self.db.save(guild_id, self._normalize(data))

    def get_all_guilds(self) -> list[str]:
        return self.db.get_all_files()

gw_config_manager = GiveawayManager()

# ==========================================
# MODALS DE CONFIGURATION CIBLÉS
# ==========================================
class PrizeModal(ui.Modal, title="Modifier le Gain"):
    def __init__(self, view: "GiveawaySetupLayoutView"):
        super().__init__()
        self.view = view
        self.prize = ui.TextInput(label="Nom du lot", default=view.config["prize"], max_length=150, required=True)
        self.add_item(self.prize)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.view.config["prize"] = str(self.prize.value)
        await self.view._refresh_silent()
        await interaction.channel.send(f"{EMOJI_VALIDER} {interaction.user.mention}, Gain mis à jour : **{self.view.config['prize']}**.", delete_after=7)

class CustomWinnersModal(ui.Modal, title="Nombre de Gagnants (Custom)"):
    def __init__(self, view: "GiveawaySetupLayoutView"):
        super().__init__()
        self.view = view
        self.winners = ui.TextInput(label="Saisir un nombre exact", placeholder="Ex: 15", max_length=3, required=True)
        self.add_item(self.winners)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        val = self.winners.value.strip()
        if not val.isdigit() or int(val) < 1:
            await interaction.channel.send(f"{EMOJI_REFUSER} {interaction.user.mention}, veuillez entrer un nombre valide supérieur à 0.", delete_after=7)
            return
        self.view.config["winners"] = int(val)
        await self.view._refresh_silent()
        await interaction.channel.send(f"{EMOJI_VALIDER} {interaction.user.mention}, Nombre de gagnants défini sur **{val}**.", delete_after=7)

class CustomDateModal(ui.Modal, title="Date et Heure Précises"):
    def __init__(self, view: "GiveawaySetupLayoutView"):
        super().__init__()
        self.view = view
        now = datetime.now(FRENCH_TZ)
        end_default = now + timedelta(hours=1)
        
        self.date = ui.TextInput(label="Date (JJ/MM/AAAA)", default=end_default.strftime("%d/%m/%Y"), min_length=10, max_length=10)
        self.time = ui.TextInput(label="Heure (HH:MM)", default=end_default.strftime("%H:%M"), min_length=5, max_length=5)
        self.add_item(self.date)
        self.add_item(self.time)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            date_str = f"{self.date.value} {self.time.value}"
            end_dt = datetime.strptime(date_str, "%d/%m/%Y %H:%M")
            end_dt = FRENCH_TZ.localize(end_dt)
            
            if end_dt <= datetime.now(FRENCH_TZ):
                await interaction.channel.send(f"{EMOJI_REFUSER} {interaction.user.mention}, La date de fin doit être dans le futur.", delete_after=7)
                return

            self.view.config["end_timestamp"] = end_dt.timestamp()
            await self.view._refresh_silent()
            await interaction.channel.send(f"{EMOJI_VALIDER} {interaction.user.mention}, Date de fin configurée avec précision.", delete_after=7)
        except ValueError:
            await interaction.channel.send(f"{EMOJI_REFUSER} {interaction.user.mention}, Format de date ou d'heure invalide.", delete_after=7)


# ==========================================
# VUES LAYOUT V2
# ==========================================
class GiveawaySetupLayoutView(ui.LayoutView):
    """LayoutV2 pour configurer le giveaway avant son lancement."""
    def __init__(self, cog, guild: discord.Guild, author: discord.Member, defaults: dict):
        super().__init__(timeout=900)
        self.cog = cog
        self.guild = guild
        self.author = author
        self.current_menu = "main" # main | roles
        
        self.config = {
            "prize": "Nitro",
            "winners": 1,
            "channel_id": defaults.get("last_channel_id", None),
            "end_timestamp": (datetime.now(FRENCH_TZ) + timedelta(hours=1)).timestamp(),
            "mention_role": None,
            "req_role": None,
            "block_role": None
        }
        self.message: Optional[discord.Message] = None
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.defer()
            await interaction.channel.send(f"{EMOJI_REFUSER} {interaction.user.mention}, vous n'êtes pas l'auteur de cette configuration.", delete_after=7)
            return False
        return True

    async def _refresh_silent(self):
        """Rafraîchissement global après un modal ou action silencieuse."""
        self._build()
        if self.message:
            try: await self.message.edit(view=self)
            except discord.HTTPException: pass

    def _build(self):
        self.clear_items()
        if self.current_menu == "main":
            self._build_main()
        elif self.current_menu == "roles":
            self._build_roles()

    def _build_main(self):
        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.author, self.cog.bot)
        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text", "")

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        
        # Le bouton de lancement en haut à droite via accessory
        btn_launch = ui.Button(label="Lancer", style=discord.ButtonStyle.success, emoji=EMOJI_ENVOYER)
        btn_launch.callback = self.on_launch_click
        
        title_section = ui.Section(
            ui.TextDisplay(f"# {EMOJI_CADEAU} Préparation du Giveaway"),
            accessory=btn_launch
        )
        container.add_item(title_section)
        
        mention = f"<@&{self.config['mention_role']}>" if self.config['mention_role'] else 'Aucune'
        req_role = f"<@&{self.config['req_role']}>" if self.config['req_role'] else 'Aucun'
        block_role = f"<@&{self.config['block_role']}>" if self.config['block_role'] else 'Aucun'
        chan_id = self.config['channel_id']
        chan_display = f"<#{chan_id}>" if chan_id else "Non défini"

        desc = (
            f"**{EMOJI_CADEAU} Gain :** `{self.config['prize']}`\n"
            f"**{EMOJI_CLASSEMENT} Gagnants :** `{self.config['winners']}`\n"
            f"**{EMOJI_HORLOGE} Fin :** <t:{int(self.config['end_timestamp'])}:R>\n"
            f"**{EMOJI_SALON} Salon :** {chan_display}\n\n"
            f"**{EMOJI_ROLE} Paramètres des Rôles :**\n"
            f"ðŸ”” **Mention :** {mention} | âœ… **Requis :** {req_role} | ðŸš« **Interdit :** {block_role}"
        )
        container.add_item(ui.TextDisplay(desc))

        # --- CATÉGORIE : GAIN & GAGNANTS (ActionRow 1) ---
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
        container.add_item(ui.TextDisplay("## ðŸŽ Gain & Gagnants"))
        
        win_row = ui.ActionRow()
        win_opts = []
        for i in range(1, 11):
            emoji_attr = getattr(E, f"N{i}", "ðŸ”¢")
            win_opts.append(discord.SelectOption(label=str(i), value=str(i), emoji=emoji_attr, default=(self.config["winners"] == i)))
        win_opts.append(discord.SelectOption(label="Custom...", value="custom", emoji=EMOJI_MODIFIER))
        
        win_select = ui.Select(placeholder="Nombre de gagnants", options=win_opts)
        win_select.callback = self.on_winners_select
        win_row.add_item(win_select)
        container.add_item(win_row)

        # --- CATÉGORIE : DURÉE & DATE (ActionRow 2) ---
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
        container.add_item(ui.TextDisplay("## â±ï¸ Durée & Date"))
        
        dur_row = ui.ActionRow()
        dur_opts = [discord.SelectOption(label=k, value=k, description=f"Se termine dans {k}") for k in DURATIONS.keys()]
        dur_opts.append(discord.SelectOption(label="Custom...", value="custom", emoji=EMOJI_MODIFIER, description="Définir une date précise"))
        dur_select = ui.Select(placeholder="Durée rapide (ex: 1h, 1j, 1 mois...)", options=dur_opts)
        dur_select.callback = self.on_duration_select
        dur_row.add_item(dur_select)
        container.add_item(dur_row)

        # --- CATÉGORIE : SALON (ActionRow 3) ---
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
        container.add_item(ui.TextDisplay("## ðŸ“ Salon & Paramètres finaux"))
        
        chan_row = ui.ActionRow()
        chan_select = ui.ChannelSelect(placeholder="Sélectionner le salon de publication", channel_types=[discord.ChannelType.text, discord.ChannelType.news])
        if chan_id and self.guild.get_channel(chan_id):
            chan_select.default_values = [discord.Object(id=chan_id)]
        chan_select.callback = self.on_channel_select
        chan_row.add_item(chan_select)
        container.add_item(chan_row)

        # --- BOUTONS D'ACTION (ActionRow 4) - Limite maximale respectée ---
        btns_row = ui.ActionRow()
        
        prize_btn = ui.Button(label="Modifier Gain", style=discord.ButtonStyle.secondary, emoji=EMOJI_MODIFIER)
        prize_btn.callback = self.on_prize_click
        btns_row.add_item(prize_btn)
        
        chan_id_btn = ui.Button(label="ID Salon manuel", style=discord.ButtonStyle.secondary, emoji=EMOJI_ID)
        chan_id_btn.callback = self.on_chan_id_click
        btns_row.add_item(chan_id_btn)

        roles_btn = ui.Button(label="Gérer Rôles", style=discord.ButtonStyle.primary, emoji=EMOJI_ROLE)
        roles_btn.callback = self.on_roles_menu_click
        btns_row.add_item(roles_btn)
        
        container.add_item(btns_row)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    def _build_roles(self):
        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.author, self.cog.bot)
        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text", "")

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {EMOJI_ROLE} Configuration des Rôles"))

        # ActionRow 1 : Mention Select
        mention_row = ui.ActionRow()
        mention_select = ui.RoleSelect(placeholder="ðŸ”” Rôle à mentionner à la création...")
        if self.config["mention_role"] and self.guild.get_role(self.config["mention_role"]):
            mention_select.default_values = [discord.Object(id=self.config["mention_role"])]
        mention_select.callback = lambda i: self.on_role_select(i, "mention_role")
        mention_row.add_item(mention_select)
        container.add_item(mention_row)

        # ActionRow 2 : Req Select
        req_row = ui.ActionRow()
        req_select = ui.RoleSelect(placeholder="âœ… Rôle requis pour participer...")
        if self.config["req_role"] and self.guild.get_role(self.config["req_role"]):
            req_select.default_values = [discord.Object(id=self.config["req_role"])]
        req_select.callback = lambda i: self.on_role_select(i, "req_role")
        req_row.add_item(req_select)
        container.add_item(req_row)

        # ActionRow 3 : Block Select
        block_row = ui.ActionRow()
        block_select = ui.RoleSelect(placeholder="ðŸš« Rôle interdit pour participer...")
        if self.config["block_role"] and self.guild.get_role(self.config["block_role"]):
            block_select.default_values = [discord.Object(id=self.config["block_role"])]
        block_select.callback = lambda i: self.on_role_select(i, "block_role")
        block_row.add_item(block_select)
        container.add_item(block_row)
        
        # ActionRow 4 : Boutons actions (IDs manuels + Retour + Vider)
        btn_actions_row = ui.ActionRow()
        mention_id_btn = ui.Button(label="ID Mention", style=discord.ButtonStyle.secondary, emoji=EMOJI_ID)
        mention_id_btn.callback = lambda i: self.open_role_id_modal(i, "mention_role")
        btn_actions_row.add_item(mention_id_btn)
        
        req_id_btn = ui.Button(label="ID Requis", style=discord.ButtonStyle.secondary, emoji=EMOJI_ID)
        req_id_btn.callback = lambda i: self.open_role_id_modal(i, "req_role")
        btn_actions_row.add_item(req_id_btn)
        
        block_id_btn = ui.Button(label="ID Interdit", style=discord.ButtonStyle.secondary, emoji=EMOJI_ID)
        block_id_btn.callback = lambda i: self.open_role_id_modal(i, "block_role")
        btn_actions_row.add_item(block_id_btn)
        
        clear_btn = ui.Button(label="Vider", style=discord.ButtonStyle.danger, emoji=EMOJI_SUPPRIMER)
        clear_btn.callback = self.on_clear_roles
        btn_actions_row.add_item(clear_btn)
        
        back_btn = ui.Button(label="Retour", style=discord.ButtonStyle.primary, emoji=EMOJI_RETOUR)
        back_btn.callback = self.on_back_main
        btn_actions_row.add_item(back_btn)
        
        container.add_item(btn_actions_row)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    # --- Callbacks Principaux ---
    async def on_prize_click(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PrizeModal(self))

    async def on_date_click(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CustomDateModal(self))

    async def on_chan_id_click(self, interaction: discord.Interaction):
        async def callback(inter, target):
            if isinstance(target, discord.abc.GuildChannel):
                self.config["channel_id"] = target.id
                await self._refresh_silent()
                await inter.channel.send(f"{EMOJI_VALIDER} {inter.user.mention}, Salon défini sur {target.mention}.", delete_after=7)
        await interaction.response.send_modal(IdModal("channel", callback))

    async def on_roles_menu_click(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.current_menu = "roles"
        self._build()
        await interaction.message.edit(view=self)

    async def on_winners_select(self, interaction: discord.Interaction):
        val = interaction.data["values"][0]
        if val == "custom":
            await interaction.response.send_modal(CustomWinnersModal(self))
        else:
            await interaction.response.defer()
            self.config["winners"] = int(val)
            await self._refresh_silent()

    async def on_duration_select(self, interaction: discord.Interaction):
        val = interaction.data["values"][0]
        if val == "custom":
            await interaction.response.send_modal(CustomDateModal(self))
        else:
            await interaction.response.defer()
            delta = DURATIONS.get(val)
            if delta:
                self.config["end_timestamp"] = (datetime.now(FRENCH_TZ) + delta).timestamp()
                await self._refresh_silent()
                await interaction.channel.send(f"{EMOJI_VALIDER} {interaction.user.mention}, Durée rapide appliquée : **{val}**.", delete_after=7)

    async def on_channel_select(self, interaction: discord.Interaction):
        await interaction.response.defer()
        values = interaction.data.get("values", [])
        if values:
            self.config["channel_id"] = int(values[0])
            await self._refresh_silent()

    async def on_launch_click(self, interaction: discord.Interaction):
        await interaction.response.defer()
        c = self.config
        channel = self.guild.get_channel(c["channel_id"]) if c["channel_id"] else interaction.channel
        
        if not channel:
            await interaction.channel.send(f"{EMOJI_REFUSER} {interaction.user.mention}, le salon cible est invalide ou introuvable.", delete_after=10)
            return

        # Création d'un ID de giveaway interne indépendant du message Discord
        gw_id = f"gw_{int(time.time() * 1000)}"

        gw_data = {
            "id": gw_id,
            "message_id": 0,
            "channel_id": channel.id,
            "guild_id": self.guild.id,
            "host_id": self.author.id,
            "prize": c["prize"],
            "winners": c["winners"],
            "end_timestamp": c["end_timestamp"],
            "req_role": c["req_role"],
            "block_role": c["block_role"],
            "participants": [],
            "ended": False,
            "locked": False
        }

        content = f"<@&{c['mention_role']}>" if c['mention_role'] else None
        public_view = PublicGiveawayLayoutView(self.cog, gw_data)

        # Envoi direct avec la vue pour éviter les étapes intermédiaires
        try:
            msg = await channel.send(content=content, view=public_view)
        except discord.Forbidden:
            await interaction.channel.send(f"{EMOJI_REFUSER} {interaction.user.mention}, je n'ai pas les permissions requises pour envoyer le giveaway dans {channel.mention}.", delete_after=10)
            return

        # Assignation du vrai ID message post-envoi
        gw_data["message_id"] = msg.id
        
        # Sauvegarde DB persistante
        db_data = gw_config_manager.load_guild(self.guild.id)
        db_data["settings"]["last_channel_id"] = channel.id
        db_data["active"][gw_id] = gw_data
        gw_config_manager.save_guild(self.guild.id, db_data)

        custom_log("success", f"Giveaway lancé par {self.author.name} dans #{channel.name}")
        await interaction.channel.send(f"{EMOJI_ENVOYER} {interaction.user.mention}, Giveaway propulsé avec succès dans {channel.mention} !", delete_after=10)
        
        if self.message:
            try: await self.message.delete()
            except: pass

    # --- Callbacks Roles ---
    async def open_role_id_modal(self, interaction: discord.Interaction, target_key: str):
        async def callback(inter, target):
            if isinstance(target, discord.Role):
                self.config[target_key] = target.id
                await self._refresh_silent()
                await inter.channel.send(f"{EMOJI_VALIDER} {inter.user.mention}, Rôle configuré via ID : {target.mention}.", delete_after=7)
        await interaction.response.send_modal(IdModal("role", callback))

    async def on_role_select(self, interaction: discord.Interaction, target_key: str):
        await interaction.response.defer()
        values = interaction.data.get("values", [])
        if values:
            self.config[target_key] = int(values[0])
            await self._refresh_silent()

    async def on_clear_roles(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.config["mention_role"] = None
        self.config["req_role"] = None
        self.config["block_role"] = None
        await self._refresh_silent()
        await interaction.channel.send(f"{EMOJI_SUPPRIMER} {interaction.user.mention}, Tous les rôles liés au giveaway ont été retirés.", delete_after=7)

    async def on_back_main(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.current_menu = "main"
        self._build()
        await interaction.message.edit(view=self)


class PublicGiveawayLayoutView(ui.LayoutView):
    """LayoutV2 affiché publiquement pour la participation. Zéro éphémère."""
    def __init__(self, cog, data: dict):
        super().__init__(timeout=None)
        self.cog = cog
        self.data = data
        self._build()

    def _build(self):
        self.clear_items()
        guild = self.cog.bot.get_guild(self.data["guild_id"])
        theme = config_manager.get_layout_v2_theme(guild.id, guild, None, self.cog.bot) if guild else {}
        accent_color = int(theme.get("color", discord.Color.purple().value))
        footer_text = theme.get("footer_text", "")

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# ðŸŽ‰ GIVEAWAY : {self.data['prize']}"))

        desc = ""
        if self.data.get("ended", False):
            desc += f"**Statut :** {EMOJI_VALIDER} Terminé\n"
            if self.data.get("winners_list"):
                mentions = ", ".join(f"<@{w}>" for w in self.data["winners_list"])
                desc += f"**Gagnant(s) :** {mentions}\n"
            else:
                desc += f"**Gagnant(s) :** Aucun\n"
        else:
            desc += f"**Fin :** <t:{int(self.data['end_timestamp'])}:R> (<t:{int(self.data['end_timestamp'])}:f>)\n"
            desc += f"**Gagnants :** `{self.data['winners']}`\n"
            if self.data.get("locked"):
                desc += f"\n{EMOJI_LOCK} **Participations temporairement suspendues.**\n"

        participants_count = len(self.data.get("participants", []))
        chance = (self.data['winners'] / max(1, participants_count)) * 100
        desc += f"**Participants :** `{participants_count}` (Chance: {min(100.0, chance):.1f}%)\n"

        if self.data.get("req_role"):
            desc += f"âœ… **Rôle requis :** <@&{self.data['req_role']}>\n"
        if self.data.get("block_role"):
            desc += f"ðŸš« **Rôle interdit :** <@&{self.data['block_role']}>\n"

        container.add_item(ui.TextDisplay(desc))

        action_row = ui.ActionRow()

        if not self.data.get("ended"):
            is_locked = self.data.get("locked", False)
            btn_style = discord.ButtonStyle.danger if is_locked else discord.ButtonStyle.success
            btn_emoji = EMOJI_LOCK if is_locked else EMOJI_CADEAU
            btn_label = "Bloqué" if is_locked else f"Participer | {participants_count}"
            
            # Utilisation de l'ID interne robuste
            join_btn = ui.Button(label=btn_label, style=btn_style, emoji=btn_emoji, custom_id=f"gw_join_{self.data['id']}")
            join_btn.callback = self.on_join
            action_row.add_item(join_btn)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        container.add_item(action_row)
        self.add_item(container)

    async def on_join(self, interaction: discord.Interaction):
        await interaction.response.defer()
        db_data = gw_config_manager.load_guild(interaction.guild_id)
        gw_id = self.data["id"]
        
        if gw_id not in db_data["active"]:
            return

        self.data = db_data["active"][gw_id]

        if self.data["ended"] or self.data["locked"]:
            return

        # Contrôle des rôles avec auto-nettoyage public
        if self.data["req_role"]:
            role = interaction.guild.get_role(self.data["req_role"])
            if role and role not in interaction.user.roles:
                await interaction.channel.send(f"{EMOJI_ATTENTION} {interaction.user.mention}, le rôle {role.mention} est requis pour participer.", delete_after=7)
                return
                
        if self.data["block_role"]:
            role = interaction.guild.get_role(self.data["block_role"])
            if role and role in interaction.user.roles:
                await interaction.channel.send(f"{EMOJI_REFUSER} {interaction.user.mention}, le rôle {role.mention} vous interdit de participer.", delete_after=7)
                return

        uid = interaction.user.id
        if uid in self.data["participants"]:
            self.data["participants"].remove(uid)
        else:
            self.data["participants"].append(uid)

        # Sauvegarde et mise à  jour native en temps réel
        db_data["active"][gw_id] = self.data
        gw_config_manager.save_guild(interaction.guild_id, db_data)
        
        self._build()
        await interaction.message.edit(view=self)


# ==========================================
# COG PRINCIPAL
# ==========================================
class GiveawayCog(commands.Cog, name="Giveaway"):
    def __init__(self, bot):
        self.bot = bot
        self.gw_task.start()
        self.bot.loop.create_task(self.restore_persistent_views())

    def cog_unload(self):
        self.gw_task.cancel()

    async def restore_persistent_views(self):
        """Réattache les vues des giveaways actifs au redémarrage."""
        await self.bot.wait_until_ready()
        guilds = gw_config_manager.get_all_guilds()
        
        for g_file in guilds:
            guild_id = int(g_file.replace(".json", ""))
            guild = self.bot.get_guild(guild_id)
            if not guild: continue
            
            db_data = gw_config_manager.load_guild(guild_id)
            changed = False
            
            for gw_id, g_data in list(db_data["active"].items()):
                if g_data.get("ended"): continue
                    
                channel = guild.get_channel(g_data["channel_id"])
                if not channel: continue
                
                try:
                    msg = await channel.fetch_message(int(g_data["message_id"]))
                    # L'édition rebind automatiquement les custom_id discord liés à gw_id
                    await msg.edit(view=PublicGiveawayLayoutView(self, g_data))
                    custom_log("info", f"Vue restaurée: GW {gw_id}")
                except discord.NotFound:
                    del db_data["active"][gw_id]
                    changed = True
                    custom_log("warning", f"Nettoyage GW {gw_id} introuvable.")
                except Exception:
                    pass
            
            if changed:
                gw_config_manager.save_guild(guild_id, db_data)

    async def execute_end_giveaway(self, guild: discord.Guild, data: dict, message: discord.Message, is_reroll: bool = False):
        """Procède au tirage au sort."""
        participants = data["participants"]
        winners_nb = data["winners"]
        prize = data["prize"]
        gw_id = data["id"]

        db_data = gw_config_manager.load_guild(guild.id)

        if not is_reroll:
            data["ended"] = True
            data["ended_at_ts"] = datetime.now().timestamp()
        
        winners_list = []
        if len(participants) > 0:
            winners_list = random.sample(participants, min(winners_nb, len(participants)))
            data["winners_list"] = winners_list
        
        db_data["active"][gw_id] = data
        gw_config_manager.save_guild(guild.id, db_data)

        public_view = PublicGiveawayLayoutView(self, data)
        try: await message.edit(view=public_view)
        except: pass

        if winners_list:
            mentions = ", ".join(f"<@{w}>" for w in winners_list)
            if is_reroll:
                await message.channel.send(f"ðŸ”„ **NOUVEAU TIRAGE**\nFélicitations à {mentions} qui remporte(nt) **{prize}** !")
            else:
                await message.reply(f"{EMOJI_CADEAU} **Le tirage est terminé !**\nFélicitations à {mentions} ! Vous remportez **{prize}** !")
            
            # Notifications MP
            for w in winners_list:
                try:
                    u = await self.bot.fetch_user(w)
                    await u.send(f"ðŸŽ‰ **Bravo !** Tu as gagné **{prize}** sur **{guild.name}** !\nðŸ”— {message.jump_url}")
                except: pass
        else:
            await message.reply(f"ðŸ **Terminé !**\nIl n'y avait aucun participant valide pour **{prize}**.")

    @tasks.loop(minutes=1)
    async def gw_task(self):
        """Vérifie la fin des giveaways actifs et purge l'historique."""
        now = datetime.now().timestamp()
        guilds = gw_config_manager.get_all_guilds()
        
        for g_file in guilds:
            guild_id = int(g_file.replace(".json", ""))
            guild = self.bot.get_guild(guild_id)
            if not guild: continue
            
            db_data = gw_config_manager.load_guild(guild_id)
            changed = False
            
            for gw_id, g_data in list(db_data["active"].items()):
                if not g_data.get("ended") and now >= g_data["end_timestamp"]:
                    channel = guild.get_channel(g_data["channel_id"])
                    if channel:
                        try:
                            msg = await channel.fetch_message(g_data["message_id"])
                            await self.execute_end_giveaway(guild, g_data, msg)
                        except:
                            g_data["ended"] = True
                            g_data["ended_at_ts"] = now
                            changed = True
                            
                # Purge JSON après 7 jours
                if g_data.get("ended") and g_data.get("ended_at_ts"):
                    if now - g_data["ended_at_ts"] > 7 * 24 * 3600:
                        del db_data["active"][gw_id]
                        changed = True

            if changed:
                gw_config_manager.save_guild(guild_id, db_data)

    @gw_task.before_loop
    async def before_gw_task(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        """Purge la BDD instantanément si le message est supprimé manuellement."""
        if message.author != self.bot.user or not message.guild:
            return
        
        db_data = gw_config_manager.load_guild(message.guild.id)
        # On cherche si ce message correspond à un giveaway actif
        target_gw_id = None
        for gw_id, data in db_data["active"].items():
            if data["message_id"] == message.id:
                target_gw_id = gw_id
                break
                
        if target_gw_id:
            del db_data["active"][target_gw_id]
            gw_config_manager.save_guild(message.guild.id, db_data)
            custom_log("warning", f"Message de giveaway supprimé, purge BDD effectuée pour {target_gw_id}.")

    @perm_command(level=3)
    @commands.command(name="giveaway", description="Lancer le gestionnaire de giveaways.")
    async def giveaway_cmd(self, ctx: commands.Context):
        """Point d'entrée de la configuration Vax v3."""
        if not ctx.guild:
            await ctx.send(f"{EMOJI_REFUSER} Les giveaways se font sur serveur.")
            return

        if not await ensure_command_permission(ctx, command_name="giveaway"):
            return

        settings = gw_config_manager.load_guild(ctx.guild.id).get("settings", {})
        
        custom_log("info", f"Configuration Giveaway demandée par {ctx.author.name}")
        view = GiveawaySetupLayoutView(self, ctx.guild, ctx.author, settings)
        msg = await ctx.send(view=view)
        view.message = msg

async def setup(bot):
    await bot.add_cog(GiveawayCog(bot))
