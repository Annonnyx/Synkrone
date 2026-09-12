# -*- coding: utf-8 -*-
"""
COG ANNONCE - Gestionnaire de publications Vax v3
=================================================
Système avancé de création et publication d'annonces avec support LayoutV2, 
permissions hiérarchiques, et stockage optimisé via DataManager.
"""

from __future__ import annotations

from typing import Any, Optional
import discord
from discord import ui
from discord.ext import commands

from utils.config_data import DataManager
from utils.config_emoji import Emoji as E
from utils.config_id import IdModal
from utils.config_perm import ensure_command_permission, perm_command
from utils.config_theme import config_manager

# ==========================================
# CONFIGURATION GLOBALE & VARIABLES
# ==========================================
DEBUG_MODE = True
ERROR_ONLY_MODE = False

# Centralisation absolue des emojis
EMOJI_MEMO = getattr(E, "MEMO", "ðŸ“")
EMOJI_MODIFIER = getattr(E, "MODIFIER", "âœï¸")
EMOJI_SUPPRIMER = getattr(E, "SUPPRIMER", "ðŸ—‘ï¸")
EMOJI_RETOUR = getattr(E, "RETOUR", "â—€ï¸")
EMOJI_VALIDER = getattr(E, "VALIDER", "âœ…")
EMOJI_REFUSER = getattr(E, "REFUSER", "âŒ")
EMOJI_ATTENTION = getattr(E, "ATTENTION", "âš ï¸")
EMOJI_LIEN = getattr(E, "LIEN", "ðŸ”—")
EMOJI_DOSSIER = getattr(E, "DOCUMENT", "ðŸ“")
EMOJI_ROLE = getattr(E, "ROLE", "ðŸ·ï¸")
EMOJI_ENVOYER = getattr(E, "SEND", "ðŸš€")
EMOJI_CREER = getattr(E, "CREATE", "âœï¸")
EMOJI_SANS_PING = getattr(E, "CLOCHE", "ðŸ”•")
EMOJI_CIBLE = getattr(E, "CIBLE", "ðŸ“")
EMOJI_MONDE = getattr(E, "MONDE", "ðŸŒ")
EMOJI_ID = getattr(E, "IDENTIFIANT", "ðŸ†”")

# ==========================================
# SYSTÈME DE LOGS VAX V3
# ==========================================
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
    print(f"{color}[ANNONCE] [{level.upper()}] {message}{reset}")

# ==========================================
# GESTIONNAIRE DE DONNÉES (CRUD VIA DATAMANAGER)
# ==========================================
class AnnonceManager:
    """Gestionnaire des configurations d'annonce basé sur le DataManager standard."""
    
    def __init__(self):
        self.db = DataManager("staff/divers/annonce")

    def _normalize(self, raw: dict[str, Any] | None) -> dict[str, Any]:
        src = raw or {}
        return {
            "channel_id": int(src["channel_id"]) if str(src.get("channel_id", "")).isdigit() else None,
            "role_target": str(src.get("role_target", "none")),
            "custom_role_id": int(src["custom_role_id"]) if str(src.get("custom_role_id", "")).isdigit() else None,
            "last_draft": src.get("last_draft", {}) if isinstance(src.get("last_draft", {}), dict) else {}
        }

    def load_config(self, guild_id: int) -> dict[str, Any]:
        raw = self.db.load(guild_id)
        return self._normalize(raw)

    def save_config(self, guild_id: int, config: dict[str, Any]) -> None:
        self.db.save(guild_id, self._normalize(config))
        custom_log("success", f"Configuration enregistrée pour le serveur {guild_id}")

annonce_config_manager = AnnonceManager()

# ==========================================
# MODALS (CRÉATION D'ANNONCE)
# ==========================================
class AnnonceModal(ui.Modal):
    """Modal de saisie pour la création d'une annonce (Titre optionnel)."""
    def __init__(self, parent_view: ui.LayoutView, guild: discord.Guild, config: dict):
        super().__init__(title="Création de l'Annonce")
        self.parent_view = parent_view
        self.guild = guild
        self.config = config
        
        last = self.config.get("last_draft", {})

        self.ann_title = ui.TextInput(
            label="Titre de l'annonce (Optionnel)", 
            placeholder="Ex: Mise à  jour...", 
            default=last.get("title") or "", 
            required=False, 
            max_length=256
        )
        self.ann_desc = ui.TextInput(
            label="Description", 
            style=discord.TextStyle.paragraph, 
            placeholder="Votre contenu ici...", 
            default=last.get("desc") or "", 
            required=True, 
            max_length=4000
        )
        self.ann_thumb = ui.TextInput(
            label="URL Miniature (Optionnel)", 
            placeholder="https://...", 
            default=last.get("thumb") or "", 
            required=False
        )

        self.add_item(self.ann_title)
        self.add_item(self.ann_desc)
        self.add_item(self.ann_thumb)

    async def on_submit(self, interaction: discord.Interaction):
        # 1. Différer immédiatement pour garantir la stabilité de l'UI
        await interaction.response.defer()
        custom_log("info", f"Soumission du modal d'annonce par {interaction.user} sur {self.guild.name}")
        
        title_val = str(self.ann_title.value).strip() if self.ann_title.value else None
        desc_val = str(self.ann_desc.value)
        thumb_val = str(self.ann_thumb.value).strip() if self.ann_thumb.value else ""

        self.config["last_draft"] = {
            "title": title_val or "",
            "desc": desc_val,
            "thumb": thumb_val
        }
        annonce_config_manager.save_config(self.guild.id, self.config)

        embed = config_manager.get_formatted_embed(
            guild=self.guild, user=interaction.user, bot=interaction.client,
            title=title_val, description=desc_val
        )

        if thumb_val and thumb_val.startswith("http"):
            try:
                embed.set_thumbnail(url=thumb_val)
            except Exception as e:
                custom_log("error", f"Erreur miniature : {e}")

        draft_view = AnnonceDraftLayoutView(self.parent_view.cog, self.guild, interaction.user, embed)
        
        # 2. Utiliser edit_original_response suite au defer()
        await interaction.edit_original_response(embed=None, view=draft_view)

# ==========================================
# INTERFACES UTILISATEUR (VIEWS LAYOUT V2)
# ==========================================
class AnnonceDraftLayoutView(ui.LayoutView):
    """Vue LayoutV2 pour la prévisualisation, confirmation et l'envoi de l'annonce."""
    def __init__(self, cog, guild: discord.Guild, user: discord.Member, draft_embed: discord.Embed):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild = guild
        self.user = user
        self.draft_embed = draft_embed
        self.config = annonce_config_manager.load_config(self.guild.id)
        
        self.confirm_step = False
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.channel.send(f"{EMOJI_REFUSER} {interaction.user.mention}, ce menu ne vous appartient pas.")
            if not interaction.response.is_done():
                await interaction.response.defer()
            return False
        return True

    def _build(self):
        self.clear_items()
        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.cog.bot)
        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text", "")

        chan_id = self.config.get("channel_id")
        channel_obj = self.guild.get_channel(chan_id) if chan_id else None
        channel_str = channel_obj.mention if channel_obj else "Aucun salon configuré."

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {EMOJI_MEMO} Prévisualisation de l'Annonce"))
        
        draft_info = self.config.get("last_draft", {})
        title_txt = f"### {draft_info.get('title')}\n" if draft_info.get("title") else ""
        desc_txt = draft_info.get("desc", "*Aucun contenu*")
        
        thumb_url = draft_info.get("thumb")
        if thumb_url and thumb_url.startswith("http"):
            try:
                container.add_item(
                    ui.Section(
                        f"{title_txt}{desc_txt}",
                        accessory=ui.Thumbnail(thumb_url, description="Miniature annonce")
                    )
                )
            except Exception:
                container.add_item(ui.TextDisplay(f"{title_txt}{desc_txt}"))
        else:
            container.add_item(ui.TextDisplay(f"{title_txt}{desc_txt}"))

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
        container.add_item(ui.TextDisplay(f"ðŸ“ **Salon cible configuré** : {channel_str}"))

        action_row = ui.ActionRow()
        
        if not channel_obj:
            err_btn = ui.Button(label="Configurez un salon d'abord", style=discord.ButtonStyle.secondary, disabled=True)
            action_row.add_item(err_btn)
        elif self.confirm_step:
            confirm_btn = ui.Button(label="Confirmer l'envoi", style=discord.ButtonStyle.danger, emoji=EMOJI_VALIDER)
            confirm_btn.callback = self.on_confirm_send
            action_row.add_item(confirm_btn)
            
            cancel_btn = ui.Button(label="Annuler", style=discord.ButtonStyle.secondary, emoji=EMOJI_REFUSER)
            cancel_btn.callback = self.on_cancel_send
            action_row.add_item(cancel_btn)
        else:
            send_btn = ui.Button(label="Envoyer l'Annonce", style=discord.ButtonStyle.primary, emoji=EMOJI_ENVOYER)
            send_btn.callback = self.on_init_send
            action_row.add_item(send_btn)

        back_btn = ui.Button(label="Retour", style=discord.ButtonStyle.success, emoji=EMOJI_RETOUR)
        back_btn.callback = self.on_back
        action_row.add_item(back_btn)
        
        container.add_item(action_row)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    async def on_init_send(self, interaction: discord.Interaction):
        custom_log("info", f"Demande d'initialisation d'envoi par {interaction.user}")
        chan_id = self.config.get("channel_id")
        if not chan_id or not self.guild.get_channel(chan_id):
            await interaction.channel.send(f"{EMOJI_ATTENTION} {interaction.user.mention}, veuillez configurer un salon cible valide.")
            if not interaction.response.is_done():
                await interaction.response.defer()
            return

        self.confirm_step = True
        self._build()
        await interaction.response.edit_message(view=self)

    async def on_cancel_send(self, interaction: discord.Interaction):
        self.confirm_step = False
        self._build()
        await interaction.response.edit_message(view=self)

    async def on_confirm_send(self, interaction: discord.Interaction):
        await interaction.response.defer()

        chan_id = self.config.get("channel_id")
        channel = self.guild.get_channel(chan_id) if chan_id else None
        if not channel:
            await interaction.channel.send(f"{EMOJI_REFUSER} {interaction.user.mention}, Salon cible introuvable.")
            return

        role_target = self.config.get("role_target", "none")
        custom_role_id = self.config.get("custom_role_id")
        ping_content = None

        if role_target == "everyone":
            ping_content = "@everyone"
        elif role_target == "here":
            ping_content = "@here"
        elif role_target == "custom" and custom_role_id:
            r_obj = self.guild.get_role(custom_role_id)
            if r_obj:
                ping_content = r_obj.mention

        try:
            await channel.send(content=ping_content, embed=self.draft_embed)
            await interaction.channel.send(f"{EMOJI_VALIDER} {interaction.user.mention}, l'annonce a bien été publiée dans {channel.mention}.")
            custom_log("success", f"Annonce publiée par {interaction.user} dans #{channel.name}")
            
            panel = AnnoncePanelLayoutView(self.cog, self.guild, self.user)
            await interaction.edit_original_response(embed=None, view=panel)
            
        except discord.Forbidden:
            self.confirm_step = False
            self._build()
            await interaction.edit_original_response(view=self)
            await interaction.channel.send(f"{EMOJI_REFUSER} {interaction.user.mention}, je n'ai pas la permission d'écrire dans {channel.mention}.")

    async def on_back(self, interaction: discord.Interaction):
        panel = AnnoncePanelLayoutView(self.cog, self.guild, self.user)
        await interaction.response.edit_message(embed=None, view=panel)


class AnnoncePanelLayoutView(ui.LayoutView):
    """Vue LayoutV2 principale gérant l'interface d'accueil et les sélecteurs dynamiques."""
    def __init__(self, cog, guild: discord.Guild, user: discord.Member):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild = guild
        self.user = user
        self.config = annonce_config_manager.load_config(self.guild.id)
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.channel.send(f"{EMOJI_REFUSER} {interaction.user.mention}, ce menu ne vous appartient pas.")
            if not interaction.response.is_done():
                await interaction.response.defer()
            return False
        return True

    def _build(self):
        self.clear_items()
        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.cog.bot)
        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text", "")

        chan_id = self.config.get("channel_id")
        channel_obj = self.guild.get_channel(chan_id) if chan_id else None
        ch_text = channel_obj.mention if channel_obj else "Aucun salon configuré."
        
        role_target = self.config.get("role_target", "none")
        custom_role_id = self.config.get("custom_role_id")

        if role_target == "everyone":
            rl_text = "@everyone"
        elif role_target == "here":
            rl_text = "@here"
        elif role_target == "custom" and custom_role_id:
            r_obj = self.guild.get_role(custom_role_id)
            rl_text = r_obj.mention if r_obj else f"`Rôle ID: {custom_role_id}` (Introuvable)"
        else:
            rl_text = "Aucun ping"

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        
        title_section = ui.Section(
            ui.TextDisplay(f"# {EMOJI_MEMO} Gestionnaire d'Annonces"),
            accessory=ui.Button(
                label="Créer une Annonce",
                style=discord.ButtonStyle.success,
                emoji=EMOJI_CREER
            )
        )
        title_section.accessory.callback = self.on_create
        container.add_item(title_section)

        desc = (
            "Bienvenue dans le gestionnaire global d'annonces de votre serveur.\n\n"
            f"ðŸ“ **Salon de diffusion :** {ch_text}\n"
            f"ðŸ”” **Rôle de notification :** {rl_text}\n\n"
            "**Configuration directe :**\n"
            "Modifiez instantanément vos cibles via les sélecteurs ci-dessous."
        )
        container.add_item(ui.TextDisplay(desc))

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
        container.add_item(ui.TextDisplay(f"### {EMOJI_CIBLE} Modifier le salon de publication"))

        chan_select_row = ui.ActionRow()
        channel_select = ui.ChannelSelect(
            placeholder="Sélectionner le salon de l'annonce...",
            min_values=1,
            max_values=1,
            channel_types=[discord.ChannelType.text, discord.ChannelType.news],
        )
        if channel_obj:
            channel_select.default_values = [discord.Object(id=channel_obj.id)]
        channel_select.callback = self.on_channel_select
        chan_select_row.add_item(channel_select)
        container.add_item(chan_select_row)

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
        container.add_item(ui.TextDisplay(f"### {EMOJI_SANS_PING} Modifier le rôle de notification"))

        role_options = [
            discord.SelectOption(label="Aucun", value="none", description="Ne mentionner personne", emoji=EMOJI_SANS_PING, default=(role_target == "none")),
            discord.SelectOption(label="Here", value="here", description="Mentionner @here", emoji=EMOJI_CIBLE, default=(role_target == "here")),
            discord.SelectOption(label="Everyone", value="everyone", description="Mentionner @everyone", emoji=EMOJI_MONDE, default=(role_target == "everyone")),
            discord.SelectOption(label="Custom", value="custom", description="Choisir un rôle spécifique du serveur", emoji=EMOJI_ROLE, default=(role_target == "custom")),
        ]

        role_select_row = ui.ActionRow()
        role_select = ui.Select(
            placeholder="Mode de notification...",
            options=role_options,
            min_values=1,
            max_values=1,
        )
        role_select.callback = self.on_role_select_mode
        role_select_row.add_item(role_select)
        container.add_item(role_select_row)

        if role_target == "custom":
            custom_role_obj = self.guild.get_role(custom_role_id) if custom_role_id else None
            custom_role_str = custom_role_obj.mention if custom_role_obj else (f"`ID: {custom_role_id}`" if custom_role_id else "Aucun rôle sélectionné")
            
            container.add_item(ui.TextDisplay(f"*Rôle custom actuel :* {custom_role_str}"))

            custom_row = ui.ActionRow()
            role_picker = ui.RoleSelect(placeholder="Choisir le rôle custom dans la liste...", min_values=1, max_values=1)
            if custom_role_obj:
                role_picker.default_values = [discord.Object(id=custom_role_obj.id)]
            role_picker.callback = self.on_custom_role_select
            custom_row.add_item(role_picker)
            container.add_item(custom_row)

            id_row = ui.ActionRow()
            id_btn = ui.Button(label="Insérer ID Rôle", style=discord.ButtonStyle.secondary, emoji=EMOJI_ID)
            id_btn.callback = self.open_role_id_modal
            id_row.add_item(id_btn)
            container.add_item(id_row)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    def _save_and_refresh(self):
        annonce_config_manager.save_config(self.guild.id, self.config)
        self._build()

    async def on_channel_select(self, interaction: discord.Interaction):
        values = getattr(interaction, "values", [])
        if not values and interaction.data:
            values = interaction.data.get("values", [])
        
        if values:
            item = values[0]
            chan_id = item.id if hasattr(item, "id") else int(item)
            self.config["channel_id"] = chan_id
            self._save_and_refresh()
            custom_log("success", f"Salon de diffusion mis à jour pour {self.guild.name} -> ID: {chan_id}")
            await interaction.channel.send(f"{EMOJI_VALIDER} {interaction.user.mention}, salon de publication mis à jour avec succès.")
        
        if interaction.response.is_done():
            await interaction.message.edit(view=self)
        else:
            await interaction.response.edit_message(view=self)

    async def on_role_select_mode(self, interaction: discord.Interaction):
        values = getattr(interaction, "values", [])
        if not values and interaction.data:
            values = interaction.data.get("values", [])

        if values:
            val = values[0]
            self.config["role_target"] = val
            if val != "custom":
                self.config["custom_role_id"] = None
            self._save_and_refresh()
            custom_log("success", f"Mode de notification mis à jour pour {self.guild.name} -> Mode: {val}")
            await interaction.channel.send(f"{EMOJI_VALIDER} {interaction.user.mention}, mode de notification mis à jour : `{val}`.")
        
        if interaction.response.is_done():
            await interaction.message.edit(view=self)
        else:
            await interaction.response.edit_message(view=self)

    async def on_custom_role_select(self, interaction: discord.Interaction):
        values = getattr(interaction, "values", [])
        if not values and interaction.data:
            values = interaction.data.get("values", [])

        if values:
            item = values[0]
            role_id = item.id if hasattr(item, "id") else int(item)
            self.config["role_target"] = "custom"
            self.config["custom_role_id"] = role_id
            self._save_and_refresh()
            custom_log("success", f"Rôle custom enregistré pour {self.guild.name} -> ID: {role_id}")
            await interaction.channel.send(f"{EMOJI_VALIDER} {interaction.user.mention}, rôle custom <@&{role_id}> enregistré.")
        
        if interaction.response.is_done():
            await interaction.message.edit(view=self)
        else:
            await interaction.response.edit_message(view=self)

    async def open_role_id_modal(self, interaction: discord.Interaction):
        custom_log("info", f"Ouverture de l'IdModal (rôle) pour {interaction.user}")
        await interaction.response.send_modal(IdModal("role", self._on_role_id_submit))

    async def _on_role_id_submit(self, interaction: discord.Interaction, target: Any):
        if target and isinstance(target, discord.Role):
            self.config["role_target"] = "custom"
            self.config["custom_role_id"] = target.id
            annonce_config_manager.save_config(self.guild.id, self.config)
            custom_log("success", f"Rôle custom défini par ID pour {self.guild.name} -> ID: {target.id}")
            await interaction.channel.send(f"{EMOJI_VALIDER} {interaction.user.mention}, rôle custom <@&{target.id}> défini via l'ID.")
        
        self._build()
        if interaction.message:
            try:
                await interaction.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def on_create(self, interaction: discord.Interaction):
        config = annonce_config_manager.load_config(self.guild.id)
        if not config.get("channel_id"):
            await interaction.channel.send(f"{EMOJI_ATTENTION} {interaction.user.mention}, vous devez d'abord configurer un salon de diffusion via le sélecteur ci-dessous.")
            if not interaction.response.is_done():
                await interaction.response.defer()
            return
            
        custom_log("info", f"Ouverture du modal de création d'annonce par {interaction.user}")
        modal = AnnonceModal(self, self.guild, config)
        await interaction.response.send_modal(modal)

# ==========================================
# COG PRINCIPAL
# ==========================================
class AnnonceCog(commands.Cog, name="Annonce"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @perm_command(level=2)
    @commands.hybrid_command(name="annonce", description="Gérer et créer des annonces sur le serveur.")
    async def annonce_cmd(self, ctx: commands.Context):
        """Point d'entrée du module Annonce respectant les autorisations."""
        if not ctx.guild:
            await ctx.send(f"{EMOJI_REFUSER} {ctx.author.mention}, cette commande doit être exécutée sur un serveur.")
            return

        if not await ensure_command_permission(ctx, command_name="annonce"):
            return

        custom_log("success", f"Exécution de la commande /annonce par {ctx.author} dans {ctx.guild.name}")
        view = AnnoncePanelLayoutView(self, ctx.guild, ctx.author)
        await ctx.send(view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(AnnonceCog(bot))
    custom_log("success", "Module Annonce (LayoutV2) chargé avec succès.")
