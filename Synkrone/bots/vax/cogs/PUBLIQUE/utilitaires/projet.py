"""
MODULE PROJET (MYTODO) VAX V3
=============================
Gestionnaire de tâches et de projets personnel utilisant l'architecture Layout V2,
la commande `/projet`, la gestion des descriptions de projets et de tâches,
un sélecteur de filtre unique, une confirmation sécurisée pour la suppression de projet,
la pagination robuste par blocs, des retours persistants (sans messages éphémères),
des logs colorés et le respect strict des standards Vax v3.
"""

from __future__ import annotations

import math
import traceback
from typing import Any, Optional

import discord
from discord import app_commands, ui
from discord.ext import commands

from utils.config_data import DataManager
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
    """Affiche des logs formatés dans la console selon le niveau de sévérité."""
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
    print(f"{color}[DEBUG - Projet] [{level.upper()}] {message}{reset}")


# ==============================================================================
# --------------------------- ÉTATS & CONFIGURATION ----------------------------
# ==============================================================================
TASK_STATES = {
    "non_traite": {"emoji": E.STATUS_DND, "label": "Non traité"},
    "amelioration": {"emoji": getattr(E, "MODIFIER", "🛠️"), "label": "Attente d'amélioration"},
    "test": {"emoji": getattr(E, "JEU", "🎮"), "label": "Attente de test"},
    "bug": {"emoji": getattr(E, "INSECTE", "🐞"), "label": "Contient un bug"},
    "valide": {"emoji": E.STATUS_ONLINE, "label": "Validé"},
}


def get_theme_values(guild: Optional[discord.Guild], user: discord.abc.User, bot: commands.Bot) -> tuple[int, str]:
    if config_manager:
        try:
            theme = config_manager.get_layout_v2_theme(
                guild.id if guild else None,
                guild,
                user,
                bot,
            )
            return int(theme.get("color", discord.Color.blurple().value)), str(theme.get("footer_text") or "")
        except Exception as e:
            debug_log(f"Erreur get_theme_values: {e}", "ERROR")
            traceback.print_exc()
    return discord.Color.blurple().value, "Gestionnaire de Projets"


# ==============================================================================
# ---------------------------------- MODALES -----------------------------------
# ==============================================================================
class CreateProjectModal(ui.Modal, title="Créer un nouveau projet"):
    name_input = ui.TextInput(
        label="Nom du projet",
        placeholder="Ex: Refonte du serveur",
        max_length=100,
        required=True,
    )
    desc_input = ui.TextInput(
        label="Description du projet",
        placeholder="Objectifs et détails du projet...",
        style=discord.TextStyle.paragraph,
        max_length=300,
        required=False,
    )

    def __init__(self, parent_view: "TodoMainView"):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            data = self.parent_view.cog.load_data(interaction.user.id)
            new_project = {
                "name": str(self.name_input.value).strip(),
                "description": str(self.desc_input.value).strip(),
                "tasks": [],
            }
            data.setdefault("projects", []).append(new_project)
            self.parent_view.cog.save_data(interaction.user.id, data)
            debug_log(f"Projet créé par {interaction.user} : {new_project['name']}", "SUCCESS")
            await self.parent_view.refresh(interaction)
        except Exception as e:
            debug_log(f"Erreur CreateProjectModal: {e}", "ERROR")
            traceback.print_exc()
            if not interaction.response.is_done():
                await interaction.response.send_message(f"{E.ERREUR} Erreur lors de la création du projet.", ephemeral=False)


class EditProjectDescriptionModal(ui.Modal, title="Modifier description"):
    desc_input = ui.TextInput(
        label="Description (laisser vide pour vider)",
        style=discord.TextStyle.paragraph,
        max_length=300,
        required=False,
    )

    def __init__(self, project_view: "ProjectDetailView", current_desc: str):
        super().__init__()
        self.project_view = project_view
        self.desc_input.default = current_desc

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            data = self.project_view.cog.load_data(interaction.user.id)
            projects = data.get("projects", [])
            if self.project_view.project_index < len(projects):
                projects[self.project_view.project_index]["description"] = str(self.desc_input.value).strip()
                self.project_view.cog.save_data(interaction.user.id, data)
                debug_log(f"Description du projet modifiée par {interaction.user}", "SUCCESS")
            await self.project_view.refresh(interaction)
        except Exception as e:
            debug_log(f"Erreur EditProjectDescriptionModal: {e}", "ERROR")
            traceback.print_exc()
            if not interaction.response.is_done():
                await interaction.response.send_message(f"{E.ERREUR} Erreur lors de la modification de la description.", ephemeral=False)


class RenameProjectModal(ui.Modal, title="Renommer le projet"):
    name_input = ui.TextInput(label="Nouveau nom", max_length=100, required=True)

    def __init__(self, project_view: "ProjectDetailView", current_name: str):
        super().__init__()
        self.project_view = project_view
        self.name_input.default = current_name

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            data = self.project_view.cog.load_data(interaction.user.id)
            if self.project_view.project_index < len(data.get("projects", [])):
                data["projects"][self.project_view.project_index]["name"] = str(self.name_input.value).strip()
                self.project_view.cog.save_data(interaction.user.id, data)
                debug_log(f"Projet renommé par {interaction.user}", "SUCCESS")
            await self.project_view.refresh(interaction)
        except Exception as e:
            debug_log(f"Erreur RenameProjectModal: {e}", "ERROR")
            traceback.print_exc()
            if not interaction.response.is_done():
                await interaction.response.send_message(f"{E.ERREUR} Erreur lors du renommage du projet.", ephemeral=False)


class AddTaskModal(ui.Modal, title="Ajouter des tâches"):
    task_input = ui.TextInput(
        label="Descriptions (séparées par ;)",
        placeholder="Ex: Tâche 1; Tâche 2; Tâche 3",
        style=discord.TextStyle.paragraph,
        max_length=1000,
        required=True,
    )

    def __init__(self, project_view: "ProjectDetailView"):
        super().__init__()
        self.project_view = project_view

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            data = self.project_view.cog.load_data(interaction.user.id)
            projects = data.get("projects", [])
            if self.project_view.project_index >= len(projects):
                await interaction.response.send_message(f"{E.ERREUR} Projet introuvable.", ephemeral=False)
                return

            raw = str(self.task_input.value).strip()
            tasks = [item.strip() for item in raw.split(";") if item.strip()]
            if not tasks:
                await interaction.response.send_message(f"{E.ERREUR} Aucune tâche valide détectée.", ephemeral=False)
                return

            for text in tasks:
                projects[self.project_view.project_index]["tasks"].append(
                    {"content": text, "description": "", "status": "non_traite"}
                )

            self.project_view.cog.save_data(interaction.user.id, data)
            debug_log(f"{len(tasks)} tâche(s) ajoutée(s) au projet par {interaction.user}", "SUCCESS")
            await self.project_view.refresh(interaction)
        except Exception as e:
            debug_log(f"Erreur AddTaskModal: {e}", "ERROR")
            traceback.print_exc()
            if not interaction.response.is_done():
                await interaction.response.send_message(f"{E.ERREUR} Erreur lors de l'ajout des tâches.", ephemeral=False)


class RenameTaskModal(ui.Modal, title="Renommer la tâche"):
    content_input = ui.TextInput(
        label="Nouveau titre / nom",
        style=discord.TextStyle.short,
        max_length=200,
        required=True,
    )

    def __init__(self, project_view: "ProjectDetailView", task_index: int, current_content: str):
        super().__init__()
        self.project_view = project_view
        self.task_index = task_index
        self.content_input.default = current_content

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            data = self.project_view.cog.load_data(interaction.user.id)
            projects = data.get("projects", [])
            if self.project_view.project_index < len(projects):
                tasks = projects[self.project_view.project_index].get("tasks", [])
                if self.task_index < len(tasks):
                    tasks[self.task_index]["content"] = str(self.content_input.value).strip()
                    self.project_view.cog.save_data(interaction.user.id, data)
                    debug_log(f"Tâche {self.task_index} renommée par {interaction.user}", "SUCCESS")
            await self.project_view.refresh(interaction)
        except Exception as e:
            debug_log(f"Erreur RenameTaskModal: {e}", "ERROR")
            traceback.print_exc()
            if not interaction.response.is_done():
                await interaction.response.send_message(f"{E.ERREUR} Erreur lors du renommage de la tâche.", ephemeral=False)


class EditTaskDescriptionModal(ui.Modal, title="Modifier desc. de la tâche"):
    desc_input = ui.TextInput(
        label="Description (laisser vide pour vider)",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=False,
    )

    def __init__(self, project_view: "ProjectDetailView", task_index: int, current_desc: str):
        super().__init__()
        self.project_view = project_view
        self.task_index = task_index
        self.desc_input.default = current_desc

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            data = self.project_view.cog.load_data(interaction.user.id)
            projects = data.get("projects", [])
            if self.project_view.project_index < len(projects):
                tasks = projects[self.project_view.project_index].get("tasks", [])
                if self.task_index < len(tasks):
                    tasks[self.task_index]["description"] = str(self.desc_input.value).strip()
                    self.project_view.cog.save_data(interaction.user.id, data)
                    debug_log(f"Description de la tâche {self.task_index} modifiée par {interaction.user}", "SUCCESS")
            await self.project_view.refresh(interaction)
        except Exception as e:
            debug_log(f"Erreur EditTaskDescriptionModal: {e}", "ERROR")
            traceback.print_exc()
            if not interaction.response.is_done():
                await interaction.response.send_message(f"{E.ERREUR} Erreur lors de la modification de la description.", ephemeral=False)


# ==============================================================================
# ------------------------- VUE DÉTAIL DU PROJET -------------------------------
# ==============================================================================
class ProjectDetailView(ui.LayoutView):
    def __init__(self, cog: "ProjetCog", user: discord.Member, project_index: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.user = user
        self.project_index = project_index
        self.page = 0
        self.items_per_page = 10
        self.active_filter: str = "all"
        self.selected_task_index: int | None = None
        self.changing_status_active: bool = False
        self.deleting_project_confirm: bool = False
        self._build_layout()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(f"{E.ERREUR} Ce menu ne vous appartient pas.", ephemeral=False)
            return False
        return True

    def _resolve_data(self) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any] | None]:
        try:
            data = self.cog.load_data(self.user.id)
            projects = data.get("projects", [])
            project = projects[self.project_index] if self.project_index < len(projects) else None
            return data, projects, project
        except Exception as e:
            debug_log(f"Erreur _resolve_data: {e}", "ERROR")
            traceback.print_exc()
            return {}, [], None

    def _build_layout(self) -> None:
        try:
            self.clear_items()
            data, projects, project = self._resolve_data()
            if project is None:
                return

            all_tasks = project.get("tasks", [])
            done_count = sum(1 for t in all_tasks if str(t.get("status")) == "valide")

            if self.active_filter == "all":
                filtered = [(idx, task) for idx, task in enumerate(all_tasks)]
            else:
                filtered = [
                    (idx, task)
                    for idx, task in enumerate(all_tasks)
                    if str(task.get("status", "non_traite")) == self.active_filter
                ]

            max_pages = max(1, math.ceil(len(filtered) / self.items_per_page))
            self.page = max(0, min(self.page, max_pages - 1))

            guild = self.user.guild if hasattr(self.user, "guild") else None
            color, footer = get_theme_values(guild, self.user, self.cog.bot)

            container = ui.Container(accent_color=discord.Color(color), spoiler=False)

            # ---------------- SECTION PROJET (EN HAUT) ----------------
            proj_name = project.get("name", "Sans nom")
            proj_desc = project.get("description", "").strip()

            project_header_lines = [
                f"## {getattr(E, 'DOCUMENT', '📁')} Projet : {proj_name}",
                f"Nombre total de tâches : `{len(all_tasks)}` | Terminées : `{done_count}/{len(all_tasks)}`",
            ]
            if proj_desc:
                project_header_lines.append(f"*{proj_desc}*")

            container.add_item(ui.TextDisplay("\n".join(project_header_lines)))
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

            # Si la confirmation de suppression est active
            if getattr(self, "deleting_project_confirm", False):
                container.add_item(ui.TextDisplay(f"{getattr(E, 'ATTENTION', '⚠️')} **Êtes-vous sûr de vouloir supprimer définitivement le projet `{proj_name}` ?**"))
                row_confirm = ui.ActionRow()
                btn_yes = ui.Button(label="Oui, supprimer", style=discord.ButtonStyle.danger, emoji=getattr(E, 'REFUSER', '❌'))
                btn_no = ui.Button(label="Annuler", style=discord.ButtonStyle.secondary, emoji=getattr(E, 'RETOUR', '↩️'))

                async def confirm_yes_callback(interaction: discord.Interaction) -> None:
                    try:
                        data_local = self.cog.load_data(self.user.id)
                        local_projects = data_local.get("projects", [])
                        if self.project_index < len(local_projects):
                            local_projects.pop(self.project_index)
                            self.cog.save_data(self.user.id, data_local)
                            debug_log(f"Projet supprimé par {interaction.user}", "WARNING")
                        main_view = TodoMainView(self.cog, self.user)
                        await interaction.response.edit_message(view=main_view)
                    except Exception as e:
                        debug_log(f"Erreur confirm_yes_callback: {e}", "ERROR")
                        traceback.print_exc()

                async def confirm_no_callback(interaction: discord.Interaction) -> None:
                    try:
                        self.deleting_project_confirm = False
                        self._build_layout()
                        await interaction.response.edit_message(view=self)
                    except Exception as e:
                        debug_log(f"Erreur confirm_no_callback: {e}", "ERROR")
                        traceback.print_exc()

                btn_yes.callback = confirm_yes_callback
                btn_no.callback = confirm_no_callback
                row_confirm.add_item(btn_yes)
                row_confirm.add_item(btn_no)
                container.add_item(row_confirm)
            else:
                # Sélecteur d'options du projet
                project_options = ui.Select(
                    placeholder="⚙️ Gérer le projet...",
                    options=[
                        discord.SelectOption(label="Renommer le projet", value="rename", emoji=getattr(E, 'MODIFIER', '✏️')),
                        discord.SelectOption(label="Modifier la description", value="edit_desc", emoji=getattr(E, 'TEXT', '📝')),
                        discord.SelectOption(label="Ajouter des tâches", value="add", emoji=getattr(E, 'AJOUTER', '➕')),
                        discord.SelectOption(label="Supprimer le projet", value="delete_project", emoji=getattr(E, 'REFUSER', '❌')),
                    ],
                )

                async def project_options_callback(interaction: discord.Interaction) -> None:
                    try:
                        choice = project_options.values[0]
                        if choice == "rename":
                            await interaction.response.send_modal(RenameProjectModal(self, str(project.get("name", ""))))
                            return
                        if choice == "edit_desc":
                            await interaction.response.send_modal(EditProjectDescriptionModal(self, str(project.get("description", ""))))
                            return
                        if choice == "add":
                            await interaction.response.send_modal(AddTaskModal(self))
                            return
                        if choice == "delete_project":
                            self.deleting_project_confirm = True
                            self._build_layout()
                            await interaction.response.edit_message(view=self)
                            return
                    except Exception as e:
                        debug_log(f"Erreur project_options_callback: {e}", "ERROR")
                        traceback.print_exc()

                project_options.callback = project_options_callback
                row_project = ui.ActionRow()
                row_project.add_item(project_options)
                container.add_item(row_project)

            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

            # ---------------- SECTION TÂCHES DU PROJET ----------------
            container.add_item(ui.TextDisplay(f"### {getattr(E, 'LISTE', '📋')} Tâches du projet"))

            # Sélecteur de filtre unique pour les états avec leurs vrais emojis
            filter_options = [
                discord.SelectOption(label="Tout afficher", value="all", emoji=getattr(E, 'LISTE', '📋'), default=(self.active_filter == "all"))
            ]
            for key, info in TASK_STATES.items():
                filter_options.append(
                    discord.SelectOption(
                        label=info["label"][:100],
                        value=key,
                        emoji=info["emoji"],
                        default=(self.active_filter == key),
                    )
                )

            filter_select = ui.Select(
                placeholder="🔍 Filtrer par état unique...",
                min_values=1,
                max_values=1,
                options=filter_options,
            )

            async def filter_callback(interaction: discord.Interaction) -> None:
                try:
                    self.active_filter = filter_select.values[0]
                    self.page = 0
                    self.selected_task_index = None
                    self.changing_status_active = False
                    self._build_layout()
                    await interaction.response.edit_message(view=self)
                except Exception as e:
                    debug_log(f"Erreur filter_callback: {e}", "ERROR")
                    traceback.print_exc()

            filter_select.callback = filter_callback
            row_filter = ui.ActionRow()
            row_filter.add_item(filter_select)
            container.add_item(row_filter)

            # Affichage de la liste des tâches au format demandé : <emoji etat> <emoji description> <nom de la tache> avec numérotation
            task_content_lines = []
            if not filtered:
                task_content_lines.append("*Aucune tâche ne correspond à ce filtre.*")
            else:
                start = self.page * self.items_per_page
                end = start + self.items_per_page
                page_tasks = filtered[start:end]
                for rank, (_, task) in enumerate(page_tasks, start=start + 1):
                    state = TASK_STATES.get(str(task.get("status", "non_traite")), TASK_STATES["non_traite"])
                    desc_emoji = f" {getattr(E, 'INFO', 'ℹ️')}" if str(task.get("description", "")).strip() else ""
                    task_content_lines.append(f"`{rank}.` {state['emoji']}{desc_emoji} **{task.get('content', '')}**")
                task_content_lines.append(f"\n-# Page {self.page + 1}/{max_pages}")

            container.add_item(ui.TextDisplay("\n".join(task_content_lines)))

            start = self.page * self.items_per_page
            end = start + self.items_per_page
            page_tasks = filtered[start:end]

            # Sélecteur pour gérer une tâche avec le bon emoji d'état correspondant à chaque tâche
            if page_tasks:
                task_select = ui.Select(
                    placeholder="📌 Gérer une tâche...",
                    options=[
                        discord.SelectOption(
                            label=f"Tâche {start + idx + 1}: {str(task.get('content', ''))[:70]}",
                            value=str(original_index),
                            emoji=TASK_STATES.get(str(task.get("status", "non_traite")), TASK_STATES["non_traite"])["emoji"],
                        )
                        for idx, (original_index, task) in enumerate(page_tasks[:25])
                    ],
                )

                async def task_select_callback(interaction: discord.Interaction) -> None:
                    try:
                        self.selected_task_index = int(task_select.values[0])
                        self.changing_status_active = False
                        self._build_layout()
                        await interaction.response.edit_message(view=self)
                    except Exception as e:
                        debug_log(f"Erreur task_select_callback: {e}", "ERROR")
                        traceback.print_exc()

                task_select.callback = task_select_callback
                row_task = ui.ActionRow()
                row_task.add_item(task_select)
                container.add_item(row_task)

            # Si une tâche est sélectionnée, affichage immédiat sous le sélecteur des choix de gestion
            if self.selected_task_index is not None and 0 <= self.selected_task_index < len(all_tasks):
                current_task = all_tasks[self.selected_task_index]
                current_state = TASK_STATES.get(str(current_task.get("status", "non_traite")), TASK_STATES["non_traite"])

                container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
                container.add_item(ui.TextDisplay(f"🎯 **Tâche sélectionnée :** `{current_task.get('content', '')}` ({current_state['emoji']} {current_state['label']})"))

                task_mgmt_options = [
                    discord.SelectOption(label="Renommer la tâche", value="rename_task", emoji="✏️"),
                    discord.SelectOption(label="Changer l'état de la tâche", value="change_status", emoji="⚙️"),
                    discord.SelectOption(label="Modifier la description de la tâche", value="edit_desc_task", emoji="📝"),
                    discord.SelectOption(label="Supprimer la tâche", value="delete_task", emoji="❌"),
                    discord.SelectOption(label="Quitter le menu de tâche", value="quit_task", emoji="↩️"),
                ]

                task_mgmt_select = ui.Select(
                    placeholder="🛠️ Action sur la tâche sélectionnée...",
                    options=task_mgmt_options,
                )

                async def task_mgmt_callback(interaction: discord.Interaction) -> None:
                    try:
                        action = task_mgmt_select.values[0]
                        if action == "quit_task":
                            self.selected_task_index = None
                            self.changing_status_active = False
                            self._build_layout()
                            await interaction.response.edit_message(view=self)
                            return
                        if action == "rename_task":
                            await interaction.response.send_modal(RenameTaskModal(self, self.selected_task_index, str(current_task.get("content", ""))))
                            return
                        if action == "edit_desc_task":
                            await interaction.response.send_modal(EditTaskDescriptionModal(self, self.selected_task_index, str(current_task.get("description", ""))))
                            return
                        if action == "delete_task":
                            data_local = self.cog.load_data(self.user.id)
                            local_projects = data_local.get("projects", [])
                            if self.project_index < len(local_projects):
                                local_tasks = local_projects[self.project_index].get("tasks", [])
                                if self.selected_task_index < len(local_tasks):
                                    local_tasks.pop(self.selected_task_index)
                                    self.cog.save_data(self.user.id, data_local)
                                    debug_log(f"Tâche supprimée par {interaction.user}", "SUCCESS")
                            self.selected_task_index = None
                            self.changing_status_active = False
                            self._build_layout()
                            await interaction.response.edit_message(view=self)
                            return

                        # Si action == "change_status", on active l'affichage du sélecteur d'états
                        self.changing_status_active = True
                        self._build_layout()
                        await interaction.response.edit_message(view=self)
                    except Exception as e:
                        debug_log(f"Erreur task_mgmt_callback: {e}", "ERROR")
                        traceback.print_exc()

                task_mgmt_select.callback = task_mgmt_callback
                row_mgmt = ui.ActionRow()
                row_mgmt.add_item(task_mgmt_select)
                container.add_item(row_mgmt)

                # Si l'utilisateur a demandé à changer l'état, affichage du sélecteur d'états avec les bons emojis d'état
                if getattr(self, "changing_status_active", False):
                    status_options = []
                    for key, state_info in TASK_STATES.items():
                        status_options.append(
                            discord.SelectOption(label=state_info["label"][:100], value=key, emoji=state_info["emoji"])
                        )
                    status_options.append(discord.SelectOption(label="Quitter le menu d'état", value="quit_status", emoji="↩️"))

                    status_select = ui.Select(
                        placeholder="📌 Sélectionner le nouvel état...",
                        options=status_options,
                    )

                    async def status_callback(interaction: discord.Interaction) -> None:
                        try:
                            selected_val = status_select.values[0]
                            if selected_val == "quit_status":
                                self.changing_status_active = False
                                self._build_layout()
                                await interaction.response.edit_message(view=self)
                                return

                            selected_status = selected_val
                            data_local = self.cog.load_data(self.user.id)
                            local_projects = data_local.get("projects", [])
                            if self.project_index < len(local_projects):
                                local_tasks = local_projects[self.project_index].get("tasks", [])
                                if self.selected_task_index < len(local_tasks):
                                    local_tasks[self.selected_task_index]["status"] = selected_status
                                    self.cog.save_data(self.user.id, data_local)
                                    debug_log(f"Statut de la tâche mis à jour : {selected_status}", "SUCCESS")
                            self.changing_status_active = False
                            self._build_layout()
                            await interaction.response.edit_message(view=self)
                        except Exception as e:
                            debug_log(f"Erreur status_callback: {e}", "ERROR")
                            traceback.print_exc()

                    status_select.callback = status_callback
                    row_status = ui.ActionRow()
                    row_status.add_item(status_select)
                    container.add_item(row_status)

            # ---------------- SÉLECTEUR DE LECTURE DES DESCRIPTIONS (SANS NUMÉROTATION DE PAGE) ----------------
            tasks_with_desc = [(idx, t) for idx, t in enumerate(all_tasks) if str(t.get("description", "")).strip()]
            if tasks_with_desc:
                desc_max_pages = max(1, math.ceil(len(tasks_with_desc) / 25))
                self.desc_page = getattr(self, "desc_page", 0)
                self.desc_page = max(0, min(self.desc_page, desc_max_pages - 1))

                start_d = self.desc_page * 25
                end_d = start_d + 25
                page_desc_tasks = tasks_with_desc[start_d:end_d]

                desc_select = ui.Select(
                    placeholder="📖 Lire la description d'une tâche...",
                    options=[
                        discord.SelectOption(
                            label=f"Desc: {str(t.get('content', ''))[:80]}",
                            value=str(idx),
                            emoji=getattr(E, 'DOCUMENT', '📄'),
                        )
                        for idx, t in page_desc_tasks
                    ],
                )

                async def desc_select_callback(interaction: discord.Interaction) -> None:
                    try:
                        t_idx = int(desc_select.values[0])
                        if 0 <= t_idx < len(all_tasks):
                            target_task = all_tasks[t_idx]
                            desc_text = target_task.get("description", "").strip()
                            
                            embed = discord.Embed(
                                title=f"{getattr(E, 'DOCUMENT', '📄')} Description de la tâche",
                                description=f"**{target_task.get('content', '')}**\n```\n{desc_text}\n```",
                                color=discord.Color.blurple()
                            )
                            await interaction.response.send_message(embed=embed, ephemeral=True)
                    except Exception as e:
                        debug_log(f"Erreur desc_select_callback: {e}", "ERROR")
                        traceback.print_exc()

                desc_select.callback = desc_select_callback
                row_desc = ui.ActionRow()
                row_desc.add_item(desc_select)
                container.add_item(row_desc)

                if desc_max_pages > 1:
                    desc_nav = ui.ActionRow()
                    btn_prev_desc = ui.Button(label="◀️ Desc", style=discord.ButtonStyle.secondary, disabled=(self.desc_page == 0))
                    btn_next_desc = ui.Button(label="Desc ▶️", style=discord.ButtonStyle.secondary, disabled=(self.desc_page >= desc_max_pages - 1))

                    async def prev_desc_callback(interaction: discord.Interaction) -> None:
                        try:
                            self.desc_page -= 1
                            self._build_layout()
                            await interaction.response.edit_message(view=self)
                        except Exception as e:
                            debug_log(f"Erreur prev_desc_callback: {e}", "ERROR")
                            traceback.print_exc()

                    async def next_desc_callback(interaction: discord.Interaction) -> None:
                        try:
                            self.desc_page += 1
                            self._build_layout()
                            await interaction.response.edit_message(view=self)
                        except Exception as e:
                            debug_log(f"Erreur next_desc_callback: {e}", "ERROR")
                            traceback.print_exc()

                    btn_prev_desc.callback = prev_desc_callback
                    btn_next_desc.callback = next_desc_callback
                    desc_nav.add_item(btn_prev_desc)
                    desc_nav.add_item(btn_next_desc)
                    container.add_item(desc_nav)

            # ---------------- BARRE DE NAVIGATION ----------------
            nav = ui.ActionRow()
            prev_btn = ui.Button(emoji=getattr(E, 'BACK', '⬅️'), style=discord.ButtonStyle.secondary, disabled=(self.page == 0))
            home_btn = ui.Button(label="Accueil projets", style=discord.ButtonStyle.primary, emoji=getattr(E, 'ACCUEIL', '🏠'))
            next_btn = ui.Button(emoji=getattr(E, 'NEXT', '➡️'), style=discord.ButtonStyle.secondary, disabled=(self.page >= max_pages - 1))

            async def prev_callback(interaction: discord.Interaction) -> None:
                try:
                    self.page -= 1
                    self.selected_task_index = None
                    self.changing_status_active = False
                    self.deleting_project_confirm = False
                    self._build_layout()
                    await interaction.response.edit_message(view=self)
                except Exception as e:
                    debug_log(f"Erreur prev_callback: {e}", "ERROR")
                    traceback.print_exc()

            async def next_callback(interaction: discord.Interaction) -> None:
                try:
                    self.page += 1
                    self.selected_task_index = None
                    self.changing_status_active = False
                    self.deleting_project_confirm = False
                    self._build_layout()
                    await interaction.response.edit_message(view=self)
                except Exception as e:
                    debug_log(f"Erreur next_callback: {e}", "ERROR")
                    traceback.print_exc()

            async def home_callback(interaction: discord.Interaction) -> None:
                try:
                    main_view = TodoMainView(self.cog, self.user)
                    await interaction.response.edit_message(view=main_view)
                except Exception as e:
                    debug_log(f"Erreur home_callback: {e}", "ERROR")
                    traceback.print_exc()

            prev_btn.callback = prev_callback
            next_btn.callback = next_callback
            home_btn.callback = home_callback

            nav.add_item(prev_btn)
            nav.add_item(home_btn)
            nav.add_item(next_btn)
            container.add_item(nav)

            if footer:
                container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
                container.add_item(ui.TextDisplay(footer))

            self.add_item(container)
        except Exception as e:
            debug_log(f"Erreur critique dans _build_layout de ProjectDetailView : {e}", "ERROR")
            traceback.print_exc()

    async def refresh(self, interaction: discord.Interaction) -> None:
        try:
            self._build_layout()
            if interaction.response.is_done():
                await interaction.edit_original_response(view=self)
            else:
                await interaction.response.edit_message(view=self)
        except Exception as e:
            debug_log(f"Erreur refresh ProjectDetailView: {e}", "ERROR")
            traceback.print_exc()


# ==============================================================================
# ------------------------- VUE PRINCIPALE DES PROJETS -------------------------
# ==============================================================================
class TodoMainView(ui.LayoutView):
    def __init__(self, cog: "ProjetCog", user: discord.Member):
        super().__init__(timeout=300)
        self.cog = cog
        self.user = user
        self.page = 0
        self.items_per_page = 10
        self._build_layout()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(f"{E.ERREUR} Ce menu ne vous appartient pas.", ephemeral=False)
            return False
        return True

    def _build_layout(self) -> None:
        try:
            self.clear_items()

            data = self.cog.load_data(self.user.id)
            projects = data.get("projects", [])

            max_pages = max(1, math.ceil(len(projects) / self.items_per_page))
            self.page = max(0, min(self.page, max_pages - 1))

            guild = self.user.guild if hasattr(self.user, "guild") else None
            color, footer = get_theme_values(guild, self.user, self.cog.bot)

            container = ui.Container(accent_color=discord.Color(color), spoiler=False)
            container.add_item(ui.TextDisplay("## 🗂️ Vue d'ensemble de vos projets"))

            start = self.page * self.items_per_page
            end = start + self.items_per_page
            page_projects = projects[start:end]

            # ---------------- SÉLECTEUR & BOUTONS PLACÉS AU-DESSUS DE LA LISTE ----------------
            if page_projects:
                selector = ui.Select(
                    placeholder="📂 Ouvrir un projet...",
                    options=[
                        discord.SelectOption(label=str(project.get("name", "Sans nom"))[:100], value=str(start + i), emoji="📁")
                        for i, project in enumerate(page_projects[:25])
                    ],
                )

                async def selector_callback(interaction: discord.Interaction) -> None:
                    try:
                        project_index = int(selector.values[0])
                        detail_view = ProjectDetailView(self.cog, self.user, project_index)
                        await interaction.response.edit_message(view=detail_view)
                    except Exception as e:
                        debug_log(f"Erreur lors de l'ouverture du projet via le sélecteur : {e}", "ERROR")
                        traceback.print_exc()
                        if not interaction.response.is_done():
                            await interaction.response.send_message(f"{E.ERREUR} Impossible d'ouvrir ce projet.", ephemeral=False)

                selector.callback = selector_callback
                row_selector = ui.ActionRow()
                row_selector.add_item(selector)
                container.add_item(row_selector)

            nav = ui.ActionRow()
            prev_btn = ui.Button(emoji="⬅️", style=discord.ButtonStyle.secondary, disabled=(self.page == 0))
            create_btn = ui.Button(label="Créer un projet", style=discord.ButtonStyle.success, emoji="➕")
            next_btn = ui.Button(emoji="➡️", style=discord.ButtonStyle.secondary, disabled=(self.page >= max_pages - 1))

            async def prev_callback(interaction: discord.Interaction) -> None:
                try:
                    self.page -= 1
                    self._build_layout()
                    await interaction.response.edit_message(view=self)
                except Exception as e:
                    debug_log(f"Erreur prev_callback TodoMainView: {e}", "ERROR")
                    traceback.print_exc()

            async def next_callback(interaction: discord.Interaction) -> None:
                try:
                    self.page += 1
                    self._build_layout()
                    await interaction.response.edit_message(view=self)
                except Exception as e:
                    debug_log(f"Erreur next_callback TodoMainView: {e}", "ERROR")
                    traceback.print_exc()

            async def create_callback(interaction: discord.Interaction) -> None:
                try:
                    await interaction.response.send_modal(CreateProjectModal(self))
                except Exception as e:
                    debug_log(f"Erreur create_callback TodoMainView: {e}", "ERROR")
                    traceback.print_exc()

            prev_btn.callback = prev_callback
            next_btn.callback = next_callback
            create_btn.callback = create_callback

            nav.add_item(prev_btn)
            nav.add_item(create_btn)
            nav.add_item(next_btn)
            container.add_item(nav)

            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

            # ---------------- LISTE DES PROJETS ----------------
            if not projects:
                text = "*Aucun projet. Cliquez sur 'Créer un projet' pour commencer.*"
            else:
                lines = []
                for index, project in enumerate(page_projects, start=start + 1):
                    tasks = project.get("tasks", [])
                    done = sum(1 for task in tasks if str(task.get("status")) == "valide")
                    lines.append(f"`{index}.` **{project.get('name', 'Sans nom')}** `{done}/{len(tasks)}`")
                lines.append(f"\n-# Page {self.page + 1}/{max_pages}")
                text = "\n".join(lines)

            container.add_item(ui.TextDisplay(text))

            if footer:
                container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
                container.add_item(ui.TextDisplay(footer))

            self.add_item(container)
        except Exception as e:
            debug_log(f"Erreur critique dans _build_layout de TodoMainView : {e}", "ERROR")
            traceback.print_exc()

    async def refresh(self, interaction: discord.Interaction) -> None:
        try:
            self._build_layout()
            if interaction.response.is_done():
                await interaction.edit_original_response(view=self)
            else:
                await interaction.response.edit_message(view=self)
        except Exception as e:
            debug_log(f"Erreur refresh TodoMainView: {e}", "ERROR")
            traceback.print_exc()


# ==============================================================================
# ------------------------------ COG PRINCIPAL ---------------------------------
# ==============================================================================
class ProjetCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data_manager = DataManager("public/utilitaires/data_mytodo")
        debug_log("Cog ProjetCog initialisé avec succès.", "SUCCESS")

    def cog_unload(self) -> None:
        debug_log("Cog ProjetCog déchargé.", "WARNING")

    def load_data(self, user_id: int) -> dict[str, Any]:
        data = self.data_manager.load(user_id)
        if not isinstance(data, dict):
            data = {}
        data.setdefault("projects", [])
        return data

    def save_data(self, user_id: int, data: dict[str, Any]) -> None:
        self.data_manager.save(user_id, data)

    @commands.hybrid_command(
        name="projet",
        description="Ouvre votre gestionnaire personnel de projets et de tâches."
    )
    async def projet(self, ctx: commands.Context) -> None:
        debug_log(f"Commande /projet invoquée par les services de {ctx.author} ({ctx.author.id})", "INFO")
        try:
            view = TodoMainView(self, ctx.author)
            if ctx.interaction:
                await ctx.send(view=view, ephemeral=False)
            else:
                await ctx.reply(view=view, mention_author=False)
        except Exception as exc:
            debug_log(f"Erreur lors de l'exécution de la commande /projet : {exc}", "ERROR")
            traceback.print_exc()
            await ctx.send(f"{E.ERREUR} Une erreur est survenue lors de l'ouverture du gestionnaire de projets.")


async def setup(bot: commands.Bot) -> None:
    for old_cmd in ["mytodo", "todo", "projet"]:
        if bot.get_command(old_cmd):
            bot.remove_command(old_cmd)
    await bot.add_cog(ProjetCog(bot))
    debug_log("Cog ProjetCog enregistré et chargé.", "SUCCESS")