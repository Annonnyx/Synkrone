"""
COMMANDE CLEAR - VAX V3
=======================
Système de purge avancé multi-cibles.
Intègre une interface Layout V2 persistante, la gestion des permissions Vax,
l'extraction par IDs, ainsi que des croisements temporels et quantitatifs.
Exclusivement en commande par préfixe.
"""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Optional

import discord
from discord import ui
from discord.ext import commands

# Imports standards Vax v3 pour la configuration et la sécurité[cite: 6, 8]
from utils.config_perm import ensure_command_permission, perm_command
from utils.config_emoji import Emoji as E
from utils.config_prefix import prefix_config_manager

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
    """Système de journalisation avec codes couleur ANSI pour la console."""
    if DEBUG_ERRORS_ONLY and level.upper() != "ERROR":
        return
    if not DEBUG_MODE and not DEBUG_ERRORS_ONLY:
        return

    colors = {
        "INFO": "\033[94m",       # Bleu
        "SUCCESS": "\033[92m",    # Vert
        "ERROR": "\033[91m",      # Rouge
        "WARNING": "\033[93m",    # Jaune
    }
    reset = "\033[0m"
    color = colors.get(level.upper(), "\033[97m")
    print(f"{color}[DEBUG - Clear] [{level.upper()}] {message}{reset}")


# ==============================================================================
# ----------------------------- EMOJIS CENTRALISÉS -----------------------------
# ==============================================================================
ICO_TRASH   = getattr(E, 'SUPPRIMER', "🗑️")
ICO_USER    = getattr(E, 'PROFIL', "👤")
ICO_ROLE    = getattr(E, 'ROLE', "🎭")
ICO_GLOBAL  = getattr(E, 'MONDE', "🌐")
ICO_TIME    = getattr(E, 'HORLOGE', "⏰")
ICO_NUM     = "🔢"
ICO_ALL     = "🧹"
ICO_ID      = getattr(E, 'IDENTIFIANT', "🆔")
ICO_CLOSE   = getattr(E, 'SUPPRIMER', "🗑️")  # Remplacement pour éviter la confusion avec le rouge suppression
ICO_INFO    = getattr(E, 'INFO', "ℹ️")
ICO_ERROR   = getattr(E, 'ERREUR', "❌")
ICO_SUCCESS = getattr(E, 'VALIDE', "✅")
ICO_GEARS   = getattr(E, 'MODIFIER', "⚙️")
LOAD_EMOJI  = getattr(E, 'LOAD', "<a:load:1531764005402710207>")


# ==============================================================================
# ------------------------------ FONCTIONS UTILS -------------------------------
# ==============================================================================
def parse_time_to_delta(time_str: str) -> Optional[timedelta]:
    """Convertit une chaîne (ex: 2h, 30m, 1j) en timedelta[cite: 5]."""
    time_str = time_str.lower().strip()
    try:
        if time_str.endswith('h'):
            return timedelta(hours=int(time_str[:-1]))
        elif time_str.endswith('m'):
            return timedelta(minutes=int(time_str[:-1]))
        elif time_str.endswith('j') or time_str.endswith('d'):
            return timedelta(days=int(time_str[:-1]))
        elif time_str.endswith('w'):
            return timedelta(weeks=int(time_str[:-1]))
    except ValueError:
        pass
    return None


# ==============================================================================
# ---------------------------------- MODALS ------------------------------------
# ==============================================================================
class ClearAmountModal(ui.Modal, title="Suppression par Quantité"):
    def __init__(self, view: "ClearLayoutView"):
        super().__init__()
        self.view = view
        self.amount_input = ui.TextInput(
            label="Nombre de messages à supprimer",
            placeholder="Ex: 50, 100, 500 (Max 1000)",
            required=True,
            max_length=4
        )
        self.add_item(self.amount_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            amount = int(self.amount_input.value.strip())
            if amount <= 0 or amount > 1000:
                return await interaction.response.send_message(
                    f"{ICO_ERROR} Le nombre doit être compris entre 1 et 1000.",
                    ephemeral=True,
                )

            await self.view.run_purge_action(interaction, action_key="quantity", limit=amount)
        except ValueError:
            await interaction.response.send_message(
                f"{ICO_ERROR} Valeur numérique invalide.",
                ephemeral=True,
            )


class ClearDurationModal(ui.Modal, title="Suppression par Durée"):
    def __init__(self, view: "ClearLayoutView"):
        super().__init__()
        self.view = view
        self.duration_input = ui.TextInput(
            label="Format temporel (Max 14 jours)",
            placeholder="Ex: 30m, 2h, 1j, 1w",
            required=True,
            max_length=10
        )
        self.add_item(self.duration_input)

    async def on_submit(self, interaction: discord.Interaction):
        delta = parse_time_to_delta(self.duration_input.value)
        if not delta:
            return await interaction.response.send_message(
                f"{ICO_ERROR} Format invalide. Utilisez : 30m, 2h, 1j, 1w.",
                ephemeral=True,
            )
            
        cutoff_time = discord.utils.utcnow() - delta
        await self.view.run_purge_action(interaction, action_key="duration", after=cutoff_time)


class ClearTargetIdModal(ui.Modal, title="Ajouter une cible via ID"):
    def __init__(self, view: "ClearLayoutView"):
        super().__init__()
        self.view = view
        self.id_input = ui.TextInput(
            label="ID utilisateur ou rôle",
            placeholder="Ex: 123456789101112345",
            max_length=25,
            required=True,
        )
        self.add_item(self.id_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw_id = self.id_input.value.strip()
        if not raw_id.isdigit():
            return await interaction.response.send_message(
                f"{ICO_ERROR} L'ID fourni n'est pas valide.",
                ephemeral=True,
            )

        guild = interaction.guild
        if guild is None:
            return await interaction.response.send_message(
                f"{ICO_ERROR} Cette action nécessite un serveur.",
                ephemeral=True,
            )

        obj_id = int(raw_id)
        member = guild.get_member(obj_id)
        if member is None:
            try:
                member = await guild.fetch_member(obj_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                member = None

        if member is not None:
            self.view.add_target("user", member.id)
            self.view.info_text = f"{ICO_SUCCESS} Utilisateur ajouté aux cibles actives."
            await self.view.refresh_modal_submit(interaction)
            return await interaction.followup.send(
                f"{ICO_SUCCESS} Cible ajoutée : {member.mention}",
                ephemeral=True,
            )

        role = guild.get_role(obj_id)
        if role is not None:
            self.view.add_target("role", role.id)
            self.view.info_text = f"{ICO_SUCCESS} Rôle ajouté aux cibles actives."
            await self.view.refresh_modal_submit(interaction)
            return await interaction.followup.send(
                f"{ICO_SUCCESS} Cible ajoutée : {role.mention}",
                ephemeral=True,
            )

        await interaction.response.send_message(
            f"{ICO_ERROR} Aucun utilisateur ou rôle trouvé avec cet ID.",
            ephemeral=True,
        )


# ==============================================================================
# ------------------------- INTERFACE LAYOUT V2 PRINCIPALE ---------------------
# ==============================================================================
class ClearLayoutView(ui.LayoutView):
    """Interface interactive Layout V2 pour piloter les purges[cite: 6]."""
    
    def __init__(self, cog: "Clear", guild: discord.Guild, user: discord.Member, channel: discord.TextChannel):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild = guild
        self.user = user
        self.channel = channel
        self.message: Optional[discord.Message] = None
        
        self.current_section = "global"
        self.target_user_ids: list[int] = []
        self.target_role_ids: list[int] = []
        self.info_text = ""
        
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(f"{ICO_ERROR} Ce panneau ne t'appartient pas.", ephemeral=True)
            return False
        return True

    def add_target(self, target_type: str, target_id: int) -> None:
        if target_type == "user":
            if target_id not in self.target_user_ids:
                self.target_user_ids.append(target_id)
        elif target_type == "role":
            if target_id not in self.target_role_ids:
                self.target_role_ids.append(target_id)

    def clear_targets(self) -> None:
        self.target_user_ids.clear()
        self.target_role_ids.clear()

    def has_targets(self) -> bool:
        return bool(self.target_user_ids or self.target_role_ids)

    def _resolve_target_member_ids(self) -> set[int]:
        member_ids = set(self.target_user_ids)
        for role_id in self.target_role_ids:
            role = self.guild.get_role(role_id)
            if role is not None:
                member_ids.update(member.id for member in role.members)
        return member_ids

    def _format_active_targets(self) -> str:
        if not self.has_targets():
            return "Aucune cible sélectionnée."

        lines: list[str] = []
        if self.target_user_ids:
            user_mentions = " ".join(f"<@{user_id}>" for user_id in self.target_user_ids)
            lines.append(f"Utilisateurs : {user_mentions}")
        if self.target_role_ids:
            role_mentions = " ".join(f"<@&{role_id}>" for role_id in self.target_role_ids)
            lines.append(f"Rôles : {role_mentions}")
        return "\n".join(lines)

    def _format_scope_label(self) -> str:
        return "purge ciblée" if self.has_targets() else "purge globale"

    async def refresh(self, interaction: discord.Interaction | None = None, clear_info: bool = False):
        self._build()
        if self.message is not None:
            if interaction is not None and not interaction.response.is_done():
                await interaction.response.edit_message(view=self)
            else:
                await self.message.edit(view=self, allowed_mentions=discord.AllowedMentions.none())
        elif interaction is not None:
            if interaction.response.is_done():
                await interaction.edit_original_response(view=self)
            else:
                await interaction.response.edit_message(view=self)

        if clear_info:
            self.info_text = ""

    async def refresh_modal_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.refresh(interaction=None)

    def _should_skip_message(self, message: discord.Message) -> bool:
        return self.message is not None and message.id == self.message.id

    async def _collect_messages(
        self,
        *,
        limit: Optional[int],
        after,
        predicate=None,
    ) -> list[discord.Message]:
        messages: list[discord.Message] = []
        async for message in self.channel.history(limit=None, after=after):
            if self._should_skip_message(message):
                continue
            if predicate is None or predicate(message):
                messages.append(message)
                if limit is not None and len(messages) >= limit:
                    break
        return messages

    async def _delete_messages(self, messages: list[discord.Message], *, bulk: bool = True) -> list[discord.Message]:
        deleted: list[discord.Message] = []
        if not messages:
            return deleted

        if not bulk:
            for message in messages:
                await message.delete()
                deleted.append(message)
            return deleted

        for index in range(0, len(messages), 100):
            chunk = messages[index:index + 100]
            if not chunk:
                continue
            if len(chunk) == 1:
                await chunk[0].delete()
            else:
                await self.channel.delete_messages(chunk)
            deleted.extend(chunk)
        return deleted

    async def _restore_channel(self) -> discord.TextChannel:
        cloned_channel = await self.channel.clone(reason=f"Restauration du salon demandée par {self.user}")
        await cloned_channel.edit(
            category=self.channel.category,
            position=self.channel.position,
            sync_permissions=False,
        )
        return cloned_channel

    async def execute_purge(self, limit: Optional[int] = None, after=None, purge_all: bool = False):
        """Moteur centralisé de purge avec vérification robuste de la cible."""
        fourteen_days_ago = discord.utils.utcnow() - timedelta(days=14)
        effective_after = after
        if purge_all and effective_after is None:
            effective_after = fourteen_days_ago
        elif self.has_targets() and effective_after is None:
            effective_after = fourteen_days_ago
        elif effective_after and effective_after < fourteen_days_ago:
            effective_after = fourteen_days_ago
            
        target_member_ids = self._resolve_target_member_ids()
        check_func = None
        if target_member_ids:
            check_func = lambda m: m.author.id in target_member_ids and not self._should_skip_message(m)
        elif effective_after:
            check_func = lambda m: m.created_at > effective_after and not self._should_skip_message(m)
        else:
            check_func = lambda m: not self._should_skip_message(m)
                
        try:
            if limit is not None:
                deleted_messages = await self._collect_messages(
                    limit=limit,
                    after=effective_after,
                    predicate=check_func,
                )
                deleted = await self._delete_messages(deleted_messages)
            elif purge_all:
                deleted = await self.channel.purge(limit=None, check=check_func, after=effective_after)
            elif effective_after is not None:
                deleted = await self.channel.purge(limit=None if target_member_ids else limit, check=check_func, after=effective_after)
            else:
                deleted = await self.channel.purge(limit=limit, check=check_func)

            count = len(deleted)
            target_str = self._format_scope_label()
            return True, count, target_str
            
        except discord.Forbidden:
            return False, 0, "Permissions insuffisantes pour purger ce salon."
        except discord.HTTPException as e:
            debug_log(f"Erreur API lors de la purge : {e}", "ERROR")
            return False, 0, "Erreur API lors de la purge."

    async def run_restore_action(self, interaction: discord.Interaction):
        scope = "restauration du salon"
        self.info_text = f"{LOAD_EMOJI} Exécution de la {scope}..."
        await self.refresh(interaction)

        try:
            await interaction.followup.send(
                f"{LOAD_EMOJI} Restauration en cours...",
                ephemeral=True,
            )
            original_channel = self.channel
            restored_channel = await self._restore_channel()
            new_view = ClearLayoutView(self.cog, self.guild, self.user, restored_channel)
            new_view.info_text = f"{ICO_SUCCESS} Salon restauré avec les mêmes paramètres."
            panel_message = await restored_channel.send(view=new_view)
            new_view.message = panel_message
            self.stop()
            await original_channel.delete(reason=f"Restauration du salon demandée par {interaction.user}")
            await interaction.followup.send(
                f"{ICO_SUCCESS} Action effectuée : restauration du salon {restored_channel.mention}.",
                ephemeral=True,
            )
        except discord.Forbidden:
            await interaction.followup.send(
                f"{ICO_ERROR} Action échouée : restauration du salon. Permissions insuffisantes.",
                ephemeral=True,
            )
        except discord.HTTPException as e:
            debug_log(f"Erreur API lors de la restauration du salon : {e}", "ERROR")
            await interaction.followup.send(
                f"{ICO_ERROR} Action échouée : restauration du salon. Erreur API.",
                ephemeral=True,
            )

    async def run_purge_action(self, interaction: discord.Interaction, action_key: str, limit: Optional[int] = None, after=None):
        if action_key != "all" and self.current_section == "targeted" and not self.has_targets():
            return await interaction.response.send_message(
                f"{ICO_ERROR} Ajoute au moins un utilisateur ou un rôle avant de lancer une purge ciblée.",
                ephemeral=True,
            )
        if action_key == "all" and self.current_section == "targeted" and not self.has_targets():
            return await interaction.response.send_message(
                f"{ICO_ERROR} Aucune cible active pour la purge totale ciblée.",
                ephemeral=True,
            )

        action_labels = {
            "quantity": "par quantité",
            "duration": "par durée",
            "all": "totale",
        }
        scope = self._format_scope_label()
        self.info_text = f"{LOAD_EMOJI} Exécution de la {scope} {action_labels.get(action_key, '')}..."

        if interaction.type == discord.InteractionType.modal_submit:
            await interaction.response.defer(ephemeral=True)
            await self.refresh(interaction=None)
        else:
            await self.refresh(interaction)

        success, count, details = await self.execute_purge(
            limit=limit,
            after=after,
            purge_all=(action_key == "all"),
        )

        if success:
            self.info_text = f"{ICO_SUCCESS} {scope.capitalize()} {action_labels.get(action_key, '')} terminée : {count} messages supprimés."
            debug_log(f"Purge réussie par {interaction.user}: {count} messages ({scope} {action_labels.get(action_key, '')})", "SUCCESS")
            await self.refresh(interaction=None)
            await interaction.followup.send(
                f"{ICO_SUCCESS} Action effectuée : {scope} {action_labels.get(action_key, '')}. {count} messages supprimés.",
                ephemeral=True,
            )
            return

        self.info_text = f"{ICO_ERROR} {details}"
        await self.refresh(interaction=None)
        await interaction.followup.send(
            f"{ICO_ERROR} Action échouée : {scope} {action_labels.get(action_key, '')}. {details}",
            ephemeral=True,
        )

    def _build(self) -> None:
        self.clear_items()
        
        # Thème Vax[cite: 6]
        accent_color = discord.Color.blurple().value
        footer_text = ""
        if config_manager:
            theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.cog.bot)
            accent_color = int(theme.get("color", accent_color))
            footer_text = theme.get("footer_text", "")

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        
        container.add_item(ui.TextDisplay(f"# {ICO_TRASH} Panneau de Contrôle Clear"))
        if self.info_text:
            container.add_item(ui.TextDisplay(f"**{self.info_text}**"))

        # Bouton à droite (accessory) pour fermer le panneau proprement au lieu d'une ligne dédiée
        close_btn = ui.Button(label="Fermer le panneau", style=discord.ButtonStyle.secondary, emoji=ICO_CLOSE)
        async def _close_callback(interaction: discord.Interaction):
            try:
                if self.message:
                    await self.message.delete()
                else:
                    await interaction.message.delete()
            except discord.HTTPException:
                pass
        close_btn.callback = _close_callback

        # Barre d'action dédiée pour rester compatible avec Layout V2
        close_row = ui.ActionRow()
        close_row.add_item(close_btn)
        container.add_item(close_row)

        nav_select = ui.Select(
            placeholder="Sélectionne le mode de purge...",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label="Purge Globale", value="global", emoji=ICO_GLOBAL, default=(self.current_section=="global")),
                discord.SelectOption(label="Purge par Utilisateur / Rôle", value="targeted", emoji=ICO_USER, default=(self.current_section=="targeted")),
            ],
            custom_id="clear_mode_select_v3"
        )
        
        # Callback inline pour le select de navigation
        async def _on_nav_select(interaction: discord.Interaction):
            values = interaction.values if hasattr(interaction, "values") else interaction.data.get("values", [])
            if values:
                self.current_section = values[0]
                if self.current_section == "global":
                    self.clear_targets()
                await self.refresh(interaction)
                
        nav_select.callback = _on_nav_select
        nav_row = ui.ActionRow()
        nav_row.add_item(nav_select)
        container.add_item(nav_row)
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

        if self.current_section == "global":
            self._render_global_section(container)
        else:
            self._render_targeted_section(container)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    def _render_global_section(self, container: ui.Container):
        container.add_item(ui.TextDisplay(f"## {ICO_GLOBAL} Purge Globale du Salon"))
        
        prefix = "!"
        try:
            effective = prefix_config_manager.get_effective_prefixes(self.cog.bot, self.guild.id, default_prefix="!")
            for p in effective:
                if p and p != "\x00":
                    prefix = p
                    break
        except Exception:
            pass

        help_text = (
            "**Commandes textuelles rapides :**\n"
            f"> `{prefix}clear 50` - Supprime les 50 derniers messages de TOUS les utilisateurs\n"
            f"> `{prefix}clear 2h` - Supprime les messages des 2 dernières heures de TOUS les utilisateurs\n\n"
            "Ou utilisez les boutons interactifs ci-dessous :"
        )
        container.add_item(ui.TextDisplay(help_text))
        
        action_row = ui.ActionRow()
        action_select = ui.Select(
            placeholder="Choisir une action de purge...",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label="Purger par quantité", value="quantity", emoji=ICO_NUM),
                discord.SelectOption(label="Purger par durée", value="duration", emoji=ICO_TIME),
                discord.SelectOption(label="Tout purger", value="all", emoji=ICO_ALL),
                discord.SelectOption(label="Restaurer", value="restore", emoji="♻️"),
            ],
            custom_id="clear_global_action_select_v4",
        )

        async def _global_action_cb(interaction: discord.Interaction):
            values = interaction.values if hasattr(interaction, "values") else interaction.data.get("values", [])
            if not values:
                return await interaction.response.send_message(f"{ICO_ERROR} Aucune action sélectionnée.", ephemeral=True)
            action = values[0]
            if action == "quantity":
                return await interaction.response.send_modal(ClearAmountModal(self))
            if action == "duration":
                return await interaction.response.send_modal(ClearDurationModal(self))
            if action == "restore":
                await interaction.response.defer(ephemeral=True)
                return await self.run_restore_action(interaction)
            await self.run_purge_action(interaction, action_key="all")

        action_select.callback = _global_action_cb
        action_row.add_item(action_select)
        container.add_item(action_row)

    def _render_targeted_section(self, container: ui.Container):
        container.add_item(ui.TextDisplay(f"## {ICO_USER} Purge Ciblée (Utilisateur ou Rôle)"))
        
        prefix = "!"
        try:
            effective = prefix_config_manager.get_effective_prefixes(self.cog.bot, self.guild.id, default_prefix="!")
            for p in effective:
                if p and p != "\x00":
                    prefix = p
                    break
        except Exception:
            pass

        help_text = (
            "**Commandes textuelles rapides :**\n"
            f"> `{prefix}clear @user` - Supprime TOUS les messages de @user\n"
            f"> `{prefix}clear @role 50` - Supprime les 50 derniers messages des membres avec @role\n"
            f"> `{prefix}clear 50 @User1 @User2` - Supprime 50 messages parmi User1 et User2\n"
        )
        container.add_item(ui.TextDisplay(help_text))
        
        container.add_item(ui.TextDisplay(f"**Cibles actives :**\n{self._format_active_targets()}"))
        
        # Sélecteurs natifs cumulables
        user_row = ui.ActionRow()
        user_sel = ui.UserSelect(placeholder="Ajouter un ou plusieurs membres...", min_values=1, max_values=10, custom_id="clear_user_select_v4")
        async def _user_cb(interaction: discord.Interaction):
            values = interaction.values if hasattr(interaction, "values") else interaction.data.get("values", [])
            if values:
                for target in values:
                    resolved_id = target.id if hasattr(target, "id") else int(target)
                    self.add_target("user", resolved_id)
                self.info_text = f"{ICO_SUCCESS} Utilisateur(s) ajouté(s) aux cibles actives."
            await self.refresh(interaction)
        user_sel.callback = _user_cb
        user_row.add_item(user_sel)
        container.add_item(user_row)

        role_row = ui.ActionRow()
        role_sel = ui.RoleSelect(placeholder="Ajouter un ou plusieurs rôles...", min_values=1, max_values=10, custom_id="clear_role_select_v4")
        async def _role_cb(interaction: discord.Interaction):
            values = interaction.values if hasattr(interaction, "values") else interaction.data.get("values", [])
            if values:
                for target in values:
                    resolved_id = target.id if hasattr(target, "id") else int(target)
                    self.add_target("role", resolved_id)
                self.info_text = f"{ICO_SUCCESS} Rôle(s) ajouté(s) aux cibles actives."
            await self.refresh(interaction)
        role_sel.callback = _role_cb
        role_row.add_item(role_sel)
        container.add_item(role_row)
        
        id_row = ui.ActionRow()
        add_id_btn = ui.Button(label="Insérer un ID", style=discord.ButtonStyle.secondary, emoji=ICO_ID)
        add_id_btn.callback = lambda i: i.response.send_modal(ClearTargetIdModal(self))
        id_row.add_item(add_id_btn)

        reset_btn = ui.Button(label="Réinitialiser les cibles", style=discord.ButtonStyle.secondary, emoji="🧼")
        async def _reset_targets(interaction: discord.Interaction):
            self.clear_targets()
            self.info_text = f"{ICO_INFO} Les cibles actives ont été réinitialisées."
            await self.refresh(interaction)
        reset_btn.callback = _reset_targets
        id_row.add_item(reset_btn)
        container.add_item(id_row)

        action_row = ui.ActionRow()
        action_select = ui.Select(
            placeholder="Choisir une action ciblée...",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label="Purger par quantité", value="quantity", emoji=ICO_NUM),
                discord.SelectOption(label="Purger par durée", value="duration", emoji=ICO_TIME),
                discord.SelectOption(label="Tout purger", value="all", emoji=ICO_ALL),
            ],
            custom_id="clear_target_action_select_v4",
        )

        async def _target_action_cb(interaction: discord.Interaction):
            values = interaction.values if hasattr(interaction, "values") else interaction.data.get("values", [])
            if not values:
                return await interaction.response.send_message(f"{ICO_ERROR} Aucune action sélectionnée.", ephemeral=True)
            action = values[0]
            if action == "quantity":
                return await interaction.response.send_modal(ClearAmountModal(self))
            if action == "duration":
                return await interaction.response.send_modal(ClearDurationModal(self))
            await self.run_purge_action(interaction, action_key="all")

        action_select.callback = _target_action_cb
        action_row.add_item(action_select)
        container.add_item(action_row)


# ==============================================================================
# ------------------------------ COG PRINCIPAL ---------------------------------
# ==============================================================================
class Clear(commands.Cog):
    """Cog de modération : Purge avancée et interactive."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        debug_log("Cog Clear initialisé avec succès.", "SUCCESS")

    @perm_command(level=2) # Niveau de permission standard Vax pour la modération[cite: 6]
    @commands.command(name="clear", aliases=["purge"], description="Outil de purge complet.")
    async def clear_cmd(self, ctx: commands.Context, *args):
        debug_log(f"Commande !clear invoquée par {ctx.author}", "INFO")

        if not ctx.guild:
            await ctx.send(f"{ICO_ERROR} Commande restreinte aux serveurs.", delete_after=5)
            return

        if not await ensure_command_permission(ctx, command_name="clear"):
            debug_log(f"Permission refusée pour {ctx.author}", "WARNING")
            return

        # Comportement par défaut : Aucun argument = Purge 2 minutes + Menu persistant
        if not args:
            try:
                two_mins_ago = discord.utils.utcnow() - timedelta(minutes=2)
                recent_messages = [
                    message async for message in ctx.channel.history(limit=None, after=two_mins_ago)
                    if message.id != ctx.message.id
                ]
                deleted = []
                for message in recent_messages:
                    await message.delete()
                    deleted.append(message)
                
                view = ClearLayoutView(self, ctx.guild, ctx.author, ctx.channel)
                view.info_text = f"{ICO_SUCCESS} Purge initiale de {len(deleted)} messages (2 dernières minutes) effectuée."
                
                try: 
                    await ctx.message.delete()
                except discord.HTTPException: 
                    pass
                    
                message = await ctx.send(view=view)
                view.message = message
                return
            except Exception as e:
                debug_log(f"Erreur lors de la purge par défaut : {e}", "ERROR")
                await ctx.send(f"{ICO_ERROR} Erreur inattendue.", delete_after=5)
                return

        # Logique Textuelle (Analyse des arguments type `!clear 50 @user` ou `!clear 2h`)[cite: 5]
        target_members = ctx.message.mentions
        target_roles = ctx.message.role_mentions
        
        amount = None
        duration = None
        
        for arg in args:
            if arg.isdigit():
                amount = int(arg)
            elif re.match(r'^\d+[hmjdw]$', arg.lower()):
                duration = parse_time_to_delta(arg)

        fourteen_days_ago = discord.utils.utcnow() - timedelta(days=14)
        after_time = (discord.utils.utcnow() - duration) if duration else None
        
        if after_time and after_time < fourteen_days_ago:
            after_time = fourteen_days_ago

        check_func = None
        if target_members or target_roles:
            member_ids = {m.id for m in target_members}
            for role in target_roles:
                member_ids.update({m.id for m in role.members})
                
            check_func = lambda m: m.author.id in member_ids and (m.created_at > after_time if after_time else True)
        else:
            if after_time:
                check_func = lambda m: m.created_at > after_time

        try:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass

            # Si une quantité est spécifiée, on prend exactement ce montant. Sinon, on fixe un plafond sécurisé.
            search_limit = amount if amount is not None else (1000 if (target_members or target_roles) else 100)
            deleted = await ctx.channel.purge(limit=search_limit, check=check_func, after=after_time)
            count = len(deleted)
            
            if target_members or target_roles:
                await ctx.send(f"{ICO_SUCCESS} Purge ciblée terminée : **{count}** messages supprimés.", delete_after=7)
            else:
                await ctx.send(f"{ICO_ALL} Purge globale terminée : **{count}** messages supprimés.", delete_after=7)
                
            debug_log(f"Purge textuelle réussie : {count} messages par {ctx.author}.", "SUCCESS")
            
        except discord.Forbidden:
            await ctx.send(f"{ICO_ERROR} Le bot manque de permissions (`manage_messages`) pour purger ici.", delete_after=7)
        except discord.HTTPException as e:
            await ctx.send(f"{ICO_ERROR} Erreur API (limite de 14 jours ou service indisponible).", delete_after=7)
            debug_log(f"Exception HTTP lors de la purge : {e}", "ERROR")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Clear(bot))
    debug_log("Cog Clear enregistré au sein du bot.", "SUCCESS")