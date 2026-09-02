"""
COMMANDE PERM - Gestion des permissions hiérarchiques
======================================================
Layout V2 pour configurer les niveaux 1..9 et les accès admin/roles/utilisateurs.
"""

from __future__ import annotations

import traceback

import discord
from discord import ui
from discord.ext import commands

from utils.config_id import IdModal
from utils.config_theme import config_manager
from utils.config_perm import MAX_PERMISSION_LEVEL, ensure_command_permission, perm_config_manager
from utils.config_emoji import Emoji as E


ITEMS_PER_PAGE = 25


class RemoveEntriesView(ui.View):
    def __init__(
        self,
        *,
        author_id: int,
        kind: str,
        level: int,
        entries: list[discord.abc.Snowflake],
        on_remove,
        on_done,
    ):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.kind = kind
        self.level = level
        self.on_remove = on_remove
        self.on_done = on_done

        if not entries:
            return

        opts = [
            discord.SelectOption(
                label=(entry.name[:95] if hasattr(entry, "name") else str(entry.id)),
                value=str(entry.id),
                description=f"ID: {entry.id}",
            )
            for entry in entries[:25]
        ]

        select = ui.Select(
            placeholder=f"Retirer {self.kind} (permission {self.level})",
            min_values=1,
            max_values=1,
            options=opts,
        )
        select.callback = self._remove_callback
        self.add_item(select)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            return False
        return True

    async def _remove_callback(self, interaction: discord.Interaction):
        picked = interaction.data.get("values", [None])[0]
        if not picked or not picked.isdigit():
            return

        await self.on_remove(interaction, int(picked))
        await self.on_done(interaction)


class PermLayoutView(ui.LayoutView):
    def __init__(self, bot: commands.Bot, guild: discord.Guild, user: discord.Member):
        super().__init__(timeout=600)
        self.bot = bot
        self.guild = guild
        self.user = user
        self.message: discord.Message | None = None
        self.selected_level: int | None = None
        self.pending_add_mode: str | None = None
        self.pending_remove_mode: str | None = None
        self.pending_delete_confirm = False
        self.associated_page = 0
        self.compatible_page = 0
        self.info_text = ""
        self._normalize_command_assignments()
        self._build()

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: ui.Item) -> None:
        user_id = getattr(getattr(interaction, "user", None), "id", "unknown")
        guild_id = getattr(getattr(interaction, "guild", None), "id", "unknown")
        print(f"[PERM][UI][ERROR] guild={guild_id} user={user_id} item={type(item).__name__}: {error}")
        traceback.print_exc()

        try:
            if interaction.response.is_done():
                await interaction.followup.send(f"{getattr(E, 'ERREUR', '❌')} Une erreur est survenue dans l'interface /perm. Vérifie la console.", ephemeral=True)
            else:
                await interaction.response.send_message(f"{getattr(E, 'ERREUR', '❌')} Une erreur est survenue dans l'interface /perm. Vérifie la console.", ephemeral=True)
        except Exception:
            pass

    def _canonical_command_name(self, command_name: str) -> str:
        raw = str(command_name or "").strip().lower()
        if not raw:
            return raw

        cmd = self.bot.all_commands.get(raw)
        if cmd is None:
            return raw
        return str(cmd.name).strip().lower() or raw

    def _normalize_command_assignments(self) -> None:
        data = perm_config_manager.load_guild_config(self.guild.id)
        cmd_levels = data.get("command_levels", {})
        if not isinstance(cmd_levels, dict) or not cmd_levels:
            return

        normalized: dict[str, int] = {}
        changed = False

        for raw_name, level in cmd_levels.items():
            canonical_name = self._canonical_command_name(raw_name)
            if canonical_name != str(raw_name).strip().lower():
                changed = True

            if canonical_name in normalized:
                previous = int(normalized[canonical_name])
                current = int(level)
                if current < previous:
                    normalized[canonical_name] = current
                    changed = True
                continue

            normalized[canonical_name] = int(level)

        if changed or len(normalized) != len(cmd_levels):
            data["command_levels"] = normalized
            perm_config_manager.save_guild_config(self.guild.id, data)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            return False
        return True

    def _perm_emoji(self, level: int) -> str:
        # Renvoie automatiquement E.N1, E.N2, etc. générés dans config_emoji.py
        return getattr(E, f"N{level}", f"{level}️⃣")

    async def _refresh_main(self, interaction: discord.Interaction):
        self._build()
        await interaction.response.edit_message(view=self)

    async def _refresh_main_silent(self):
        if self.message is not None:
            self._build()
            await self.message.edit(view=self)

    def _unassigned_compatible_commands(self):
        return perm_config_manager.get_unassigned_compatible_commands(self.bot, self.guild.id)

    def _paginate(self, items: list, page: int) -> tuple[list, int, int, int]:
        if not items:
            return [], 0, 0, 0

        total_pages = (len(items) - 1) // ITEMS_PER_PAGE + 1
        page = max(0, min(page, total_pages - 1))
        start = page * ITEMS_PER_PAGE
        end = start + ITEMS_PER_PAGE
        return items[start:end], page, total_pages, start

    def _level_lines(self) -> str:
        if self.selected_level is None:
            return (
                "- Si une permission est supprimée, c'est la permission supérieure qui hérite des commandes / rôles / utilisateurs configurés, même si la limite des rôles / utilisateurs est dépassée.\n"
                "- Une permission possède automatiquement le pouvoir des permissions inférieures."
            )

        cfg = perm_config_manager.get_level_data(self.guild.id, self.selected_level)

        role_mentions = []
        for role_id in cfg["roles"]:
            role = self.guild.get_role(int(role_id))
            role_mentions.append(role.mention if role else f"`{role_id}`")

        user_mentions = []
        for user_id in cfg["users"]:
            member = self.guild.get_member(int(user_id))
            user_mentions.append(member.mention if member else f"`{user_id}`")

        roles_txt = ", ".join(role_mentions) if role_mentions else "Aucun"
        users_txt = ", ".join(user_mentions) if user_mentions else "Aucun"

        return (
            f"- Rôles ({len(cfg['roles'])}/5) : {roles_txt}\n"
            f"- Utilisateurs ({len(cfg['users'])}/5) : {users_txt}"
        )

    def _associated_lines(self) -> str:
        if self.selected_level is None:
            return "Sélectionnez une permission pour voir les commandes associées."

        cmds = perm_config_manager.get_commands_for_level(self.guild.id, self.selected_level)
        if not cmds:
            return "Aucune commande associée à cette permission."

        page_items, page, _total_pages, start = self._paginate(cmds, self.associated_page)
        self.associated_page = page
        
        lines = []
        for idx, name in enumerate(page_items):
            emoji_num = getattr(E, f"N{idx + 1}", f"{idx + 1}️⃣")
            lines.append(f"{emoji_num} `²{name}`")
        return "\n".join(lines)

    def _compatible_unassigned_lines(self) -> str:
        cmds = self._unassigned_compatible_commands()
        if not cmds:
            return "Aucune commande compatible disponible."

        page_items, page, _total_pages, start = self._paginate(cmds, self.compatible_page)
        self.compatible_page = page
        
        lines = []
        for idx, item in enumerate(page_items):
            emoji_num = getattr(E, f"N{idx + 1}", f"{idx + 1}️⃣")
            lines.append(f"{emoji_num} `²{item.name}`")
        return "\n".join(lines)

    def _build(self):
        self.clear_items()
        conf = perm_config_manager.load_guild_config(self.guild.id)
        active_levels = perm_config_manager.get_active_levels(self.guild.id)
        if self.selected_level is not None:
            self.selected_level = max(1, min(self.selected_level, active_levels))
        else:
            self.pending_add_mode = None
            self.pending_remove_mode = None
            self.pending_delete_confirm = False
            self.associated_page = 0
            self.compatible_page = 0

        admins_state = "Activé" if conf["admins_enabled"] else "Désactivé"
        state_style = discord.ButtonStyle.success if conf["admins_enabled"] else discord.ButtonStyle.danger
        toggle_label = "Désactiver" if conf["admins_enabled"] else "Activer"
        toggle_style = discord.ButtonStyle.secondary

        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.bot)
        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text") or ""

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {getattr(E, 'LOCK', '🔐')} Configuration des Permissions"))
        if self.info_text:
            container.add_item(ui.TextDisplay(self.info_text))

        admin_row = ui.ActionRow()
        state_btn = ui.Button(label=f"État admin : {admins_state}", style=state_style, disabled=True)
        admin_row.add_item(state_btn)
        toggle_admin_btn = ui.Button(label=toggle_label, style=toggle_style, emoji=getattr(E, "BOUCLIER", "🛡️"))
        toggle_admin_btn.callback = self._toggle_admins
        admin_row.add_item(toggle_admin_btn)
        container.add_item(admin_row)

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
        container.add_item(ui.TextDisplay(f"## {getattr(E, 'MODIFIER', '🎚️')} Sélection de permission"))

        level_options = [
            discord.SelectOption(
                label="Accueil",
                value="home",
                emoji=getattr(E, "HOME", "🏠"),
                default=(self.selected_level is None),
            )
        ]

        for i in range(1, active_levels + 1):
            level_options.append(
                discord.SelectOption(
                    label=f"Permission {i}",
                    value=str(i),
                    emoji=self._perm_emoji(i),
                    default=(self.selected_level == i),
                )
            )

        if active_levels < MAX_PERMISSION_LEVEL:
            level_options.append(discord.SelectOption(label="Ajouter", value="add_level", emoji=getattr(E, "AJOUTER", "➕")))

        level_row = ui.ActionRow()
        level_select = ui.Select(
            placeholder="Choisir un niveau de permission",
            min_values=1,
            max_values=1,
            options=level_options,
        )
        level_select.callback = self._on_level_select
        level_row.add_item(level_select)
        container.add_item(level_row)

        if self.selected_level is not None and active_levels > 3 and self.selected_level > 1:
            current_cfg = perm_config_manager.get_level_data(self.guild.id, self.selected_level)
            associated_cmds = perm_config_manager.get_commands_for_level(self.guild.id, self.selected_level)
            needs_confirm = bool(current_cfg["roles"] or associated_cmds)

            delete_row = ui.ActionRow()
            if self.pending_delete_confirm and needs_confirm:
                confirm_btn = ui.Button(
                    label=f"Confirmer suppression P{self.selected_level}",
                    style=discord.ButtonStyle.danger,
                    emoji=getattr(E, "VALIDER", "✅"),
                )
                confirm_btn.callback = self._confirm_delete_selected_level
                delete_row.add_item(confirm_btn)

                cancel_btn = ui.Button(
                    label="Annuler",
                    style=discord.ButtonStyle.secondary,
                    emoji=getattr(E, "RETOUR", "↩️"),
                )
                cancel_btn.callback = self._cancel_delete_selected_level
                delete_row.add_item(cancel_btn)
            else:
                delete_btn = ui.Button(
                    label=f"Supprimer permission {self.selected_level}",
                    style=discord.ButtonStyle.danger,
                    emoji=getattr(E, "SUPPRIMER", "🗑️"),
                )
                delete_btn.callback = self._delete_selected_level
                delete_row.add_item(delete_btn)
            container.add_item(delete_row)

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
        if self.selected_level is None:
            container.add_item(ui.TextDisplay(f"## {getattr(E, 'HOME', '🏠')} Accueil"))
            container.add_item(ui.TextDisplay(self._level_lines()))

        if self.selected_level is not None:
            container.add_item(ui.TextDisplay(f"## {getattr(E, 'ROLE', '👥')} Gérer les rôles / utilisateurs"))
            container.add_item(ui.TextDisplay(self._level_lines()))
            cfg = perm_config_manager.get_level_data(self.guild.id, self.selected_level)

            row_add = ui.ActionRow()
            add_role_btn = ui.Button(label="Ajouter rôle", style=discord.ButtonStyle.primary, emoji=getattr(E, "ROLE", "🎭"))
            add_role_btn.callback = self._add_role
            row_add.add_item(add_role_btn)

            add_user_btn = ui.Button(label="Ajouter utilisateur", style=discord.ButtonStyle.primary, emoji=getattr(E, "PROFIL", "👤"))
            add_user_btn.callback = self._add_user
            row_add.add_item(add_user_btn)
            container.add_item(row_add)

            if cfg["roles"] or cfg["users"]:
                remove_options: list[discord.SelectOption] = []
                for rid in cfg["roles"]:
                    role = self.guild.get_role(int(rid))
                    role_label = role.name if role else f"ID {rid}"
                    remove_options.append(
                        discord.SelectOption(
                            label=f"Rôle: {role_label}"[:100],
                            value=f"role:{rid}",
                            emoji=getattr(E, "ROLE", "🎭"),
                        )
                    )
                for uid in cfg["users"]:
                    member = self.guild.get_member(int(uid))
                    user_label = member.display_name if member else f"ID {uid}"
                    remove_options.append(
                        discord.SelectOption(
                            label=f"Utilisateur: {user_label}"[:100],
                            value=f"user:{uid}",
                            emoji=getattr(E, "PROFIL", "👤"),
                        )
                    )

                if remove_options:
                    remove_row = ui.ActionRow()
                    remove_select = ui.Select(
                        placeholder="Retirer un rôle ou un utilisateur",
                        min_values=1,
                        max_values=1,
                        options=remove_options[:25],
                    )
                    remove_select.callback = self._on_inline_remove_any_select
                    remove_row.add_item(remove_select)
                    container.add_item(remove_row)

            if self.pending_add_mode == "role":
                role_select_row = ui.ActionRow()
                role_select = ui.RoleSelect(placeholder=f"Choisir un rôle", min_values=1, max_values=1)
                role_select.callback = self._on_inline_role_select
                role_select_row.add_item(role_select)
                container.add_item(role_select_row)

                role_action_row = ui.ActionRow()
                role_id_btn = ui.Button(label="Insérer ID rôle", style=discord.ButtonStyle.primary, emoji=getattr(E, "IDENTIFIANT", "🆔"))
                role_id_btn.callback = self._open_role_id_modal
                role_action_row.add_item(role_id_btn)

                cancel_btn = ui.Button(label="Annuler", style=discord.ButtonStyle.secondary, emoji=getattr(E, "RETOUR", "↩️"))
                cancel_btn.callback = self._cancel_inline_add
                role_action_row.add_item(cancel_btn)
                container.add_item(role_action_row)

            if self.pending_add_mode == "user":
                user_select_row = ui.ActionRow()
                user_select = ui.UserSelect(placeholder=f"Choisir un membre", min_values=1, max_values=1)
                user_select.callback = self._on_inline_user_select
                user_select_row.add_item(user_select)
                container.add_item(user_select_row)

                user_action_row = ui.ActionRow()
                user_id_btn = ui.Button(label="Insérer ID utilisateur", style=discord.ButtonStyle.primary, emoji=getattr(E, "IDENTIFIANT", "🆔"))
                user_id_btn.callback = self._open_user_id_modal
                user_action_row.add_item(user_id_btn)

                cancel_btn = ui.Button(label="Annuler", style=discord.ButtonStyle.secondary, emoji=getattr(E, "RETOUR", "↩️"))
                cancel_btn.callback = self._cancel_inline_add
                user_action_row.add_item(cancel_btn)
                container.add_item(user_action_row)

        if self.selected_level is not None:
            assigned_for_level = perm_config_manager.get_commands_for_level(self.guild.id, self.selected_level)
            _assigned_page_items, assigned_page, assigned_total_pages, _assigned_start = self._paginate(
                assigned_for_level,
                self.associated_page,
            )
            self.associated_page = assigned_page

            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
            if assigned_total_pages > 0:
                container.add_item(ui.TextDisplay(f"## {getattr(E, 'LISTE', '🧩')} Commandes associées ({assigned_page + 1}/{assigned_total_pages})"))
            else:
                container.add_item(ui.TextDisplay(f"## {getattr(E, 'LISTE', '🧩')} Commandes associées (0/0)"))
            container.add_item(ui.TextDisplay(self._associated_lines()))

            if assigned_for_level:
                assigned_page_items, assigned_page, assigned_total_pages, assigned_start = self._paginate(assigned_for_level, self.associated_page)
                self.associated_page = assigned_page

                unassign_row = ui.ActionRow()
                unassign_select = ui.Select(
                    placeholder="Retirer une ou plusieurs commandes de cette permission",
                    min_values=1,
                    max_values=len(assigned_page_items),
                    options=[
                        discord.SelectOption(
                            label=f"{idx + 1}. ²{name}"[:100], 
                            value=name, 
                            emoji=getattr(E, f"N{idx + 1}", "🧩")
                        )
                        for idx, name in enumerate(assigned_page_items)
                    ],
                )
                unassign_select.callback = self._on_unassign_command_select
                unassign_row.add_item(unassign_select)
                container.add_item(unassign_row)

                if assigned_total_pages > 1:
                    nav_row = ui.ActionRow()
                    prev_btn = ui.Button(label="Précédent", style=discord.ButtonStyle.secondary, emoji=getattr(E, 'FLECHE_GAUCHE', '◀'), disabled=(assigned_page == 0))
                    prev_btn.callback = self._associated_prev_page
                    nav_row.add_item(prev_btn)

                    page_btn = ui.Button(label=f"Page {assigned_page + 1}/{assigned_total_pages}", style=discord.ButtonStyle.secondary, disabled=True)
                    nav_row.add_item(page_btn)

                    next_btn = ui.Button(label="Suivant", style=discord.ButtonStyle.secondary, emoji=getattr(E, 'FLECHE_DROITE', '▶'), disabled=(assigned_page >= assigned_total_pages - 1))
                    next_btn.callback = self._associated_next_page
                    nav_row.add_item(next_btn)
                    container.add_item(nav_row)

        if self.selected_level is not None:
            unassigned = self._unassigned_compatible_commands()
            if unassigned:
                unassigned_page_items, compatible_page, compatible_total_pages, compatible_start = self._paginate(unassigned, self.compatible_page)
                self.compatible_page = compatible_page

                container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
                container.add_item(ui.TextDisplay(f"## {getattr(E, 'DOCUMENT', '📋')} Commandes compatibles ({compatible_page + 1}/{compatible_total_pages})"))
                container.add_item(ui.TextDisplay(self._compatible_unassigned_lines()))

                assign_row = ui.ActionRow()
                assign_select = ui.Select(
                    placeholder="Associer une ou plusieurs commandes à cette permission",
                    min_values=1,
                    max_values=len(unassigned_page_items),
                    options=[
                        discord.SelectOption(
                            label=f"{idx + 1}. ²{item.name}"[:100],
                            value=item.name,
                            emoji=getattr(E, f"N{idx + 1}", "🧩")
                        )
                        for idx, item in enumerate(unassigned_page_items)
                    ],
                )
                assign_select.callback = self._on_assign_command_select
                assign_row.add_item(assign_select)
                container.add_item(assign_row)

                if compatible_total_pages > 1:
                    nav_row = ui.ActionRow()
                    prev_btn = ui.Button(label="Précédent", style=discord.ButtonStyle.secondary, emoji=getattr(E, 'FLECHE_GAUCHE', '◀'), disabled=(compatible_page == 0))
                    prev_btn.callback = self._compatible_prev_page
                    nav_row.add_item(prev_btn)

                    page_btn = ui.Button(label=f"Page {compatible_page + 1}/{compatible_total_pages}", style=discord.ButtonStyle.secondary, disabled=True)
                    nav_row.add_item(page_btn)

                    next_btn = ui.Button(label="Suivant", style=discord.ButtonStyle.secondary, emoji=getattr(E, 'FLECHE_DROITE', '▶'), disabled=(compatible_page >= compatible_total_pages - 1))
                    next_btn.callback = self._compatible_next_page
                    nav_row.add_item(next_btn)
                    container.add_item(nav_row)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    async def _on_level_select(self, interaction: discord.Interaction):
        picked = interaction.data.get("values", ["home"])[0]
        self.pending_add_mode = None
        self.pending_remove_mode = None
        self.pending_delete_confirm = False
        self.associated_page = 0
        self.compatible_page = 0
        self.info_text = ""

        if picked == "home":
            self.selected_level = None
            return await self._refresh_main(interaction)

        if picked == "add_level":
            ok, new_total = perm_config_manager.add_permission_level(self.guild.id)
            if ok:
                self.selected_level = new_total
                self.info_text = f"{getattr(E, 'VALIDER', '✅')} Niveau ajouté. Total: {new_total}/{MAX_PERMISSION_LEVEL}."
            else:
                self.info_text = f"{getattr(E, 'ATTENTION', '⚠️')} Maximum de {MAX_PERMISSION_LEVEL} niveaux atteint."
            return await self._refresh_main(interaction)

        self.selected_level = int(picked)
        await self._refresh_main(interaction)

    async def _delete_selected_level(self, interaction: discord.Interaction):
        if self.selected_level is None:
            return await self._refresh_main(interaction)

        cfg = perm_config_manager.get_level_data(self.guild.id, self.selected_level)
        associated_cmds = perm_config_manager.get_commands_for_level(self.guild.id, self.selected_level)
        needs_confirm = bool(cfg["roles"] or associated_cmds)

        if needs_confirm:
            self.pending_delete_confirm = True
            self.info_text = f"{getattr(E, 'ATTENTION', '⚠️')} Cette permission contient des commandes ou rôles. Confirmez la suppression."
            return await self._refresh_main(interaction)

        await self._execute_delete_selected_level(interaction)

    async def _confirm_delete_selected_level(self, interaction: discord.Interaction):
        await self._execute_delete_selected_level(interaction)

    async def _cancel_delete_selected_level(self, interaction: discord.Interaction):
        self.pending_delete_confirm = False
        self.info_text = ""
        await self._refresh_main(interaction)

    async def _execute_delete_selected_level(self, interaction: discord.Interaction):
        self.pending_delete_confirm = False

        ok, new_total, target = perm_config_manager.remove_permission_level(self.guild.id, self.selected_level)
        if not ok:
            self.info_text = f"{getattr(E, 'ERREUR', '❌')} Impossible de supprimer cette permission."
            return await self._refresh_main(interaction)

        self.selected_level = target
        self.info_text = (
            f"{getattr(E, 'VALIDER', '✅')} Permission supprimée. Les éléments ont été transférés vers la permission `{target}`. "
            f"Niveaux actifs: {new_total}/{MAX_PERMISSION_LEVEL}."
        )
        await self._refresh_main(interaction)

    async def _on_assign_command_select(self, interaction: discord.Interaction):
        if self.selected_level is None:
            return await self._refresh_main(interaction)

        picked_values = interaction.data.get("values", [])
        if not picked_values:
            return await self._refresh_main(interaction)

        added_count = 0
        for cmd_name in picked_values:
            if not cmd_name:
                continue
            canonical_name = self._canonical_command_name(cmd_name)
            if not canonical_name:
                continue
            perm_config_manager.set_command_level(self.guild.id, canonical_name, self.selected_level)
            added_count += 1

        self.compatible_page = 0
        self.info_text = f"{getattr(E, 'VALIDER', '✅')} {added_count} commande(s) associée(s) à la permission {self.selected_level}." if added_count else ""
        self._build()
        await interaction.response.edit_message(view=self)

    async def _on_unassign_command_select(self, interaction: discord.Interaction):
        if self.selected_level is None:
            return await self._refresh_main(interaction)

        picked_values = interaction.data.get("values", [])
        if not picked_values:
            return await self._refresh_main(interaction)

        removed_count = 0
        for cmd_name in picked_values:
            if not cmd_name:
                continue
            canonical_name = self._canonical_command_name(cmd_name)
            removed = False
            if canonical_name:
                removed = perm_config_manager.remove_command_level(self.guild.id, canonical_name)

            # Compatibilité ancienne config: retire aussi la clé alias brute si présente.
            if perm_config_manager.remove_command_level(self.guild.id, cmd_name):
                removed = True

            if removed:
                removed_count += 1

        self.associated_page = 0
        if removed_count:
            self.info_text = f"{getattr(E, 'VALIDER', '✅')} {removed_count} commande(s) retirée(s) de la permission {self.selected_level}."
        else:
            self.info_text = f"{getattr(E, 'ERREUR', '❌')} Aucune commande retirée ( déjà dissociée ou invalide)."
        self._build()
        await interaction.response.edit_message(view=self)

    async def _associated_prev_page(self, interaction: discord.Interaction):
        self.associated_page = max(0, self.associated_page - 1)
        await self._refresh_main(interaction)

    async def _associated_next_page(self, interaction: discord.Interaction):
        self.associated_page += 1
        await self._refresh_main(interaction)

    async def _compatible_prev_page(self, interaction: discord.Interaction):
        self.compatible_page = max(0, self.compatible_page - 1)
        await self._refresh_main(interaction)

    async def _compatible_next_page(self, interaction: discord.Interaction):
        self.compatible_page += 1
        await self._refresh_main(interaction)

    async def _toggle_admins(self, interaction: discord.Interaction):
        new_state = perm_config_manager.toggle_admins(self.guild.id)
        self.info_text = f"{getattr(E, 'VALIDER', '✅')} Accès administrateurs: {'activé' if new_state else 'désactivé'}."
        self._build()
        await interaction.response.edit_message(view=self)

    async def _add_role(self, interaction: discord.Interaction):
        if self.selected_level is None:
            return await self._refresh_main(interaction)
        self.pending_add_mode = "role"
        self.pending_remove_mode = None
        self.info_text = ""
        await self._refresh_main(interaction)

    async def _add_user(self, interaction: discord.Interaction):
        if self.selected_level is None:
            return await self._refresh_main(interaction)
        self.pending_add_mode = "user"
        self.pending_remove_mode = None
        self.info_text = ""
        await self._refresh_main(interaction)

    async def _cancel_inline_add(self, interaction: discord.Interaction):
        self.pending_add_mode = None
        await self._refresh_main(interaction)

    async def _cancel_inline_remove(self, interaction: discord.Interaction):
        self.pending_remove_mode = None
        await self._refresh_main(interaction)

    async def _on_inline_role_select(self, interaction: discord.Interaction):
        if self.selected_level is None:
            return await self._refresh_main(interaction)

        picked = interaction.data.get("values", [None])[0]
        if not picked or not picked.isdigit():
            return await self._refresh_main(interaction)

        role = self.guild.get_role(int(picked))
        if role is None:
            return await self._refresh_main(interaction)

        ok, msg = perm_config_manager.add_role_to_level(self.guild.id, self.selected_level, role.id)
        self.pending_add_mode = None
        self.info_text = (f"{getattr(E, 'VALIDER', '✅')} " if ok else f"{getattr(E, 'ERREUR', '❌')} ") + msg
        self._build()
        await interaction.response.edit_message(view=self)

    async def _on_inline_user_select(self, interaction: discord.Interaction):
        if self.selected_level is None:
            return await self._refresh_main(interaction)

        picked = interaction.data.get("values", [None])[0]
        if not picked or not picked.isdigit():
            return await self._refresh_main(interaction)

        member = self.guild.get_member(int(picked))
        if member is None:
            try:
                member = await self.guild.fetch_member(int(picked))
            except (discord.NotFound, discord.HTTPException, discord.Forbidden):
                member = None

        if member is None:
            return await self._refresh_main(interaction)

        ok, msg = perm_config_manager.add_user_to_level(self.guild.id, self.selected_level, member.id)
        self.pending_add_mode = None
        self.info_text = (f"{getattr(E, 'VALIDER', '✅')} " if ok else f"{getattr(E, 'ERREUR', '❌')} ") + msg
        self._build()
        await interaction.response.edit_message(view=self)

    async def _open_role_id_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(IdModal("role", self._on_role_id_modal_submit))

    async def _open_user_id_modal(self, interaction: discord.Interaction):
        await interaction.response.send_modal(IdModal("user", self._on_user_id_modal_submit))

    async def _on_role_id_modal_submit(self, interaction: discord.Interaction, target):
        if self.selected_level is None:
            return

        role = target if isinstance(target, discord.Role) else None
        if role is None:
            return

        ok, msg = perm_config_manager.add_role_to_level(self.guild.id, self.selected_level, role.id)
        self.pending_add_mode = None
        self.info_text = (f"{getattr(E, 'VALIDER', '✅')} " if ok else f"{getattr(E, 'ERREUR', '❌')} ") + msg
        await self._refresh_main_silent()

    async def _on_user_id_modal_submit(self, interaction: discord.Interaction, target):
        if self.selected_level is None:
            return

        member = target if isinstance(target, discord.Member) else None
        if member is None:
            return

        ok, msg = perm_config_manager.add_user_to_level(self.guild.id, self.selected_level, member.id)
        self.pending_add_mode = None
        self.info_text = (f"{getattr(E, 'VALIDER', '✅')} " if ok else f"{getattr(E, 'ERREUR', '❌')} ") + msg
        await self._refresh_main_silent()

    async def _on_inline_remove_any_select(self, interaction: discord.Interaction):
        if self.selected_level is None:
            return await self._refresh_main(interaction)

        picked = interaction.data.get("values", [None])[0]
        if not picked or ":" not in picked:
            return await self._refresh_main(interaction)

        kind, raw_id = picked.split(":", 1)
        if not raw_id.isdigit():
            return await self._refresh_main(interaction)

        target_id = int(raw_id)
        if kind == "role":
            ok, msg = perm_config_manager.remove_role_from_level(self.guild.id, self.selected_level, target_id)
        elif kind == "user":
            ok, msg = perm_config_manager.remove_user_from_level(self.guild.id, self.selected_level, target_id)
        else:
            return await self._refresh_main(interaction)

        self.info_text = (f"{getattr(E, 'VALIDER', '✅')} " if ok else f"{getattr(E, 'ERREUR', '❌')} ") + msg
        self._build()
        await interaction.response.edit_message(view=self)


class Perm(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="perm")
    async def perm(self, ctx: commands.Context):
        try:
            guild_id = getattr(getattr(ctx, "guild", None), "id", "unknown")
            user_id = getattr(getattr(ctx, "author", None), "id", "unknown")
            print(f"[PERM] Invocation reçue: guild={guild_id} user={user_id}")

            if not ctx.guild or not isinstance(ctx.author, discord.Member):
                return await ctx.send(f"{getattr(E, 'ERREUR', '❌')} Cette commande doit être utilisée sur un serveur.")

            if not await ensure_command_permission(ctx, command_name="perm"):
                print(f"[PERM] Accès refusé: guild={guild_id} user={user_id}")
                return

            view = PermLayoutView(self.bot, ctx.guild, ctx.author)
            message = await ctx.send(view=view)
            view.message = message
            print(f"[PERM] Vue envoyée avec succès: message_id={message.id}")
        except Exception as e:
            print(f"[PERM][ERROR] Échec d'exécution de /perm: {e}")
            traceback.print_exc()
            try:
                await ctx.send(f"{getattr(E, 'ERREUR', '❌')} Erreur interne /perm. Détail affiché en console.")
            except Exception:
                pass

    @perm.error
    async def perm_error(self, ctx: commands.Context, error: commands.CommandError):
        guild_id = getattr(getattr(ctx, "guild", None), "id", "unknown")
        user_id = getattr(getattr(ctx, "author", None), "id", "unknown")
        print(f"[PERM][COMMAND_ERROR] guild={guild_id} user={user_id}: {error}")
        traceback.print_exc()

        try:
            await ctx.send(f"{getattr(E, 'ERREUR', '❌')} Erreur commande /perm. Voir console.")
        except Exception:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Perm(bot))