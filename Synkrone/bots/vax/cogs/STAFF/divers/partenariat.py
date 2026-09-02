# -*- coding: utf-8 -*-
"""
COG PARTENARIAT - Gestionnaire de Partenariats Vax v3
=====================================================
Système avancé de configuration et d'envoi de partenariats
avec support complet du LayoutV2, DataManager et permissions Vax.
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

# Centralisation globale des emojis Vax v3
EMOJI_PARTENARIAT = getattr(E, "LIEN", "ðŸ”—")
EMOJI_MEMO = getattr(E, "MEMO", "ðŸ“")
EMOJI_VALIDER = getattr(E, "VALIDER", "âœ…")
EMOJI_REFUSER = getattr(E, "REFUSER", "âŒ")
EMOJI_ATTENTION = getattr(E, "ATTENTION", "âš ï¸")
EMOJI_ENVOYER = getattr(E, "SEND", "ðŸš€")
EMOJI_CIBLE = getattr(E, "CIBLE", "ðŸ“")
EMOJI_CLOCHE = getattr(E, "CLOCHE", "ðŸ””")
EMOJI_SANS_PING = "ðŸ”•" # Fallback statique
EMOJI_ROLE = getattr(E, "ROLE", "ðŸŽ­")
EMOJI_MONDE = getattr(E, "MONDE", "ðŸŒ")
EMOJI_ID = getattr(E, "IDENTIFIANT", "ðŸ†”")
EMOJI_CREER = getattr(E, "CREATE", "âœï¸")

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
    print(f"{color}[PARTENARIAT] [{level.upper()}] {message}{reset}")

# ==========================================
# GESTIONNAIRE DE DONNÉES (CRUD)
# ==========================================
class PartenariatManager:
    """Interface de stockage JSON via le DataManager standard."""
    
    def __init__(self):
        self.db = DataManager("staff/divers/partenariat")

    def _normalize(self, raw: dict[str, Any] | None) -> dict[str, Any]:
        src = raw or {}
        return {
            "channel_id": int(src["channel_id"]) if str(src.get("channel_id", "")).isdigit() else None,
            "ping_type": str(src.get("ping_type", "none")), # none, here, everyone, custom
            "ping_id": int(src["ping_id"]) if str(src.get("ping_id", "")).isdigit() else None,
            "content": str(src.get("content", ""))
        }

    def load_config(self, guild_id: int) -> dict[str, Any]:
        raw = self.db.load(guild_id)
        return self._normalize(raw)

    def save_config(self, guild_id: int, config: dict[str, Any]) -> None:
        self.db.save(guild_id, self._normalize(config))
        custom_log("success", f"Configuration enregistrée pour le serveur {guild_id}")

part_config_manager = PartenariatManager()

# ==========================================
# MODALS 
# ==========================================
class PartenariatContentModal(ui.Modal):
    """Modal de saisie pour le contenu du partenariat."""
    def __init__(self, parent_view: ui.LayoutView, config: dict):
        super().__init__(title="Message de Partenariat")
        self.parent_view = parent_view
        self.config = config

        self.content_input = ui.TextInput(
            label="Contenu de l'annonce",
            placeholder="Rédigez le texte de votre partenariat ici...",
            style=discord.TextStyle.paragraph,
            default=self.config.get("content", ""),
            required=True,
            max_length=4000
        )
        self.add_item(self.content_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        self.config["content"] = str(self.content_input.value)
        part_config_manager.save_config(interaction.guild_id, self.config)
        
        custom_log("info", f"Contenu du partenariat mis à jour par {interaction.user}")
        await self.parent_view._refresh_silent()
        
        # Validation publique et persistante
        await interaction.channel.send(f"{EMOJI_VALIDER} {interaction.user.mention}, le contenu du partenariat a été enregistré.")

# ==========================================
# INTERFACES UTILISATEUR (LAYOUT V2)
# ==========================================
class PartenariatLayoutView(ui.LayoutView):
    """Vue LayoutV2 complète pour la configuration et l'envoi du partenariat."""
    def __init__(self, cog, guild: discord.Guild, user: discord.Member):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild = guild
        self.user = user
        self.config = part_config_manager.load_config(self.guild.id)
        self.confirm_step = False
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.channel.send(f"{EMOJI_REFUSER} {interaction.user.mention}, ce menu de configuration ne vous appartient pas.")
            if not interaction.response.is_done():
                await interaction.response.defer()
            return False
        return True

    async def _refresh_silent(self):
        """Rafraîchissement invisible de la vue."""
        self._build()
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    def _save_and_refresh(self):
        part_config_manager.save_config(self.guild.id, self.config)
        self._build()

    def _build(self):
        self.clear_items()
        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.cog.bot)
        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text", "")

        chan_id = self.config.get("channel_id")
        channel_obj = self.guild.get_channel(chan_id) if chan_id else None
        ch_text = channel_obj.mention if channel_obj else "âŒ Aucun salon configuré."
        
        ping_type = self.config.get("ping_type", "none")
        ping_id = self.config.get("ping_id")

        if ping_type == "everyone":
            rl_text = "@everyone"
        elif ping_type == "here":
            rl_text = "@here"
        elif ping_type == "custom" and ping_id:
            r_obj = self.guild.get_role(ping_id)
            rl_text = r_obj.mention if r_obj else f"`Rôle ID: {ping_id}` (Introuvable)"
        else:
            rl_text = "ðŸ”• Aucune"

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        
        # Section En-tête
        title_section = ui.Section(
            ui.TextDisplay(f"# {EMOJI_PARTENARIAT} Gestionnaire de Partenariats"),
            accessory=ui.Button(label="Rédiger", style=discord.ButtonStyle.success, emoji=EMOJI_CREER)
        )
        title_section.accessory.callback = self.on_write_content
        container.add_item(title_section)

        desc = (
            f"**{EMOJI_CIBLE} Salon de publication :** {ch_text}\n"
            f"**{EMOJI_CLOCHE} Paramètre de ping :** {rl_text}\n\n"
            "**Aperçu du contenu :**"
        )
        container.add_item(ui.TextDisplay(desc))

        # Aperçu intelligent
        content_text = self.config.get("content", "*Aucun contenu défini. Cliquez sur le bouton 'Rédiger' pour commencer.*")
        if len(content_text) > 1500:
            content_text = content_text[:1500] + "...\n*(Aperçu tronqué pour l'affichage)*"
            
        container.add_item(ui.TextDisplay(f"```text\n{content_text}\n```"))

        # Gestion des états : Configuration ou Confirmation
        if self.confirm_step:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
            container.add_item(ui.TextDisplay(f"### {EMOJI_ATTENTION} Action irréversible"))
            container.add_item(ui.TextDisplay("Êtes-vous sûr de vouloir envoyer ce partenariat avec les paramètres actuels ?"))
            
            action_row = ui.ActionRow()
            confirm_btn = ui.Button(label="Confirmer l'envoi", style=discord.ButtonStyle.danger, emoji=EMOJI_VALIDER)
            confirm_btn.callback = self.on_confirm_send
            action_row.add_item(confirm_btn)
            
            cancel_btn = ui.Button(label="Annuler", style=discord.ButtonStyle.secondary, emoji=EMOJI_REFUSER)
            cancel_btn.callback = self.on_cancel_send
            action_row.add_item(cancel_btn)
            container.add_item(action_row)
        else:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
            container.add_item(ui.TextDisplay(f"### {EMOJI_CIBLE} Configuration Technique"))

            # Sélecteur du salon cible
            chan_select_row = ui.ActionRow()
            channel_select = ui.ChannelSelect(
                placeholder="Sélectionner le salon cible...",
                min_values=1, max_values=1,
                channel_types=[discord.ChannelType.text, discord.ChannelType.news],
            )
            if channel_obj:
                channel_select.default_values = [discord.Object(id=channel_obj.id)]
            channel_select.callback = self.on_channel_select
            chan_select_row.add_item(channel_select)
            container.add_item(chan_select_row)

            # Sélecteur du type de ping
            role_options = [
                discord.SelectOption(label="Aucun ping", value="none", description="Ne mentionner personne", emoji=EMOJI_SANS_PING, default=(ping_type == "none")),
                discord.SelectOption(label="Ping @here", value="here", description="Notifier les membres en ligne", emoji=EMOJI_CIBLE, default=(ping_type == "here")),
                discord.SelectOption(label="Ping @everyone", value="everyone", description="Notifier tout le serveur", emoji=EMOJI_MONDE, default=(ping_type == "everyone")),
                discord.SelectOption(label="Ping Custom", value="custom", description="Choisir un rôle spécifique", emoji=EMOJI_ROLE, default=(ping_type == "custom")),
            ]
            role_select_row = ui.ActionRow()
            role_select = ui.Select(placeholder="Mode de notification...", options=role_options, min_values=1, max_values=1)
            role_select.callback = self.on_ping_mode_select
            role_select_row.add_item(role_select)
            container.add_item(role_select_row)

            # Sélecteur dynamique si ping Custom
            if ping_type == "custom":
                custom_row = ui.ActionRow()
                role_picker = ui.RoleSelect(placeholder="Choisir le rôle dans la liste...", min_values=1, max_values=1)
                if ping_id and self.guild.get_role(ping_id):
                    role_picker.default_values = [discord.Object(id=ping_id)]
                role_picker.callback = self.on_custom_role_select
                custom_row.add_item(role_picker)
                container.add_item(custom_row)
                
                id_row = ui.ActionRow()
                id_btn = ui.Button(label="Insérer ID Rôle", style=discord.ButtonStyle.secondary, emoji=EMOJI_ID)
                id_btn.callback = self.open_role_id_modal
                id_row.add_item(id_btn)
                container.add_item(id_row)

            # Bouton d'envoi final
            send_row = ui.ActionRow()
            send_btn = ui.Button(label="Procéder à l'envoi", style=discord.ButtonStyle.primary, emoji=EMOJI_ENVOYER)
            send_btn.callback = self.on_init_send
            send_row.add_item(send_btn)
            container.add_item(send_row)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    # ------------------ CALLBACKS ------------------
    async def on_write_content(self, interaction: discord.Interaction):
        custom_log("info", f"Ouverture du modal de rédaction par {interaction.user}")
        await interaction.response.send_modal(PartenariatContentModal(self, self.config))

    async def on_channel_select(self, interaction: discord.Interaction):
        values = getattr(interaction, "values", []) or (interaction.data.get("values", []) if interaction.data else [])
        if values:
            item = values[0]
            chan_id = item.id if hasattr(item, "id") else int(item)
            self.config["channel_id"] = chan_id
            self._save_and_refresh()
            await interaction.channel.send(f"{EMOJI_VALIDER} {interaction.user.mention}, le salon de publication a été défini sur <#{chan_id}>.")
            
        if interaction.response.is_done():
            await interaction.message.edit(view=self)
        else:
            await interaction.response.edit_message(view=self)

    async def on_ping_mode_select(self, interaction: discord.Interaction):
        values = getattr(interaction, "values", []) or (interaction.data.get("values", []) if interaction.data else [])
        if values:
            mode = values[0]
            self.config["ping_type"] = mode
            if mode != "custom":
                self.config["ping_id"] = None
            self._save_and_refresh()
            await interaction.channel.send(f"{EMOJI_VALIDER} {interaction.user.mention}, le mode de notification est défini sur `{mode}`.")
            
        if interaction.response.is_done():
            await interaction.message.edit(view=self)
        else:
            await interaction.response.edit_message(view=self)

    async def on_custom_role_select(self, interaction: discord.Interaction):
        values = getattr(interaction, "values", []) or (interaction.data.get("values", []) if interaction.data else [])
        if values:
            item = values[0]
            role_id = item.id if hasattr(item, "id") else int(item)
            self.config["ping_type"] = "custom"
            self.config["ping_id"] = role_id
            self._save_and_refresh()
            await interaction.channel.send(f"{EMOJI_VALIDER} {interaction.user.mention}, le rôle cible <@&{role_id}> a été enregistré.")
            
        if interaction.response.is_done():
            await interaction.message.edit(view=self)
        else:
            await interaction.response.edit_message(view=self)

    async def open_role_id_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(IdModal("role", self._on_role_id_submit))

    async def _on_role_id_submit(self, interaction: discord.Interaction, target: Any):
        if target and isinstance(target, discord.Role):
            self.config["ping_type"] = "custom"
            self.config["ping_id"] = target.id
            part_config_manager.save_config(self.guild.id, self.config)
            await interaction.channel.send(f"{EMOJI_VALIDER} {interaction.user.mention}, le rôle <@&{target.id}> a été configuré via son ID.")
            
        self._build()
        if interaction.message:
            try: await interaction.message.edit(view=self)
            except discord.HTTPException: pass

    async def on_init_send(self, interaction: discord.Interaction):
        chan_id = self.config.get("channel_id")
        content = self.config.get("content")

        if not chan_id or not self.guild.get_channel(chan_id):
            await interaction.channel.send(f"{EMOJI_ATTENTION} {interaction.user.mention}, vous devez définir un salon cible valide avant d'envoyer.")
            if not interaction.response.is_done(): await interaction.response.defer()
            return
            
        if not content:
            await interaction.channel.send(f"{EMOJI_ATTENTION} {interaction.user.mention}, le message du partenariat est vide.")
            if not interaction.response.is_done(): await interaction.response.defer()
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
            await interaction.channel.send(f"{EMOJI_REFUSER} {interaction.user.mention}, le salon est introuvable au moment de l'envoi.")
            return

        # Construction du ping
        ping_type = self.config.get("ping_type", "none")
        ping_id = self.config.get("ping_id")
        ping_text = ""

        if ping_type == "here":
            ping_text = "@here\n"
        elif ping_type == "everyone":
            ping_text = "@everyone\n"
        elif ping_type == "custom" and ping_id:
            ping_text = f"<@&{ping_id}>\n"

        final_content = f"{ping_text}{self.config['content']}"

        try:
            await channel.send(content=final_content)
            await interaction.channel.send(f"{EMOJI_VALIDER} {interaction.user.mention}, le partenariat a été envoyé avec succès dans {channel.mention} ! ðŸš€")
            custom_log("success", f"Partenariat expédié par {interaction.user} dans #{channel.name}")
            
            # Réinitialise la vue principale après succès
            self.confirm_step = False
            self._build()
            await interaction.edit_original_response(view=self)
            
        except discord.Forbidden:
            self.confirm_step = False
            self._build()
            await interaction.edit_original_response(view=self)
            await interaction.channel.send(f"{EMOJI_REFUSER} {interaction.user.mention}, je n'ai pas les permissions nécessaires pour poster dans {channel.mention}.")
        except Exception as e:
            custom_log("error", f"Echec de publication : {e}")
            await interaction.channel.send(f"{EMOJI_REFUSER} {interaction.user.mention}, une erreur inattendue a bloqué l'envoi.")

# ==========================================
# COG PRINCIPAL
# ==========================================
class PartenariatCog(commands.Cog, name="Partenariat"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @perm_command(level=2)
    @commands.command(name="partenariat", description="Interface Vax pour configurer et envoyer des partenariats.")
    async def partenariat_cmd(self, ctx: commands.Context):
        """Déclenche le panneau LayoutV2 du partenariat."""
        if not ctx.guild:
            await ctx.send(f"{EMOJI_REFUSER} {ctx.author.mention}, les partenariats ne sont gérables que sur serveur.")
            return

        # Protection hiérarchique Vax v3
        if not await ensure_command_permission(ctx, command_name="partenariat"):
            return

        custom_log("info", f"Démarrage du panneau Partenariat par {ctx.author} sur {ctx.guild.name}")
        view = PartenariatLayoutView(self, ctx.guild, ctx.author)
        msg = await ctx.send(view=view)
        view.message = msg

async def setup(bot: commands.Bot):
    await bot.add_cog(PartenariatCog(bot))
    custom_log("success", "Module Partenariat (LayoutV2) chargé et opérationnel.")
