import discord
from discord import app_commands, ui
from discord.ext import commands
import json
import math
import traceback
from pathlib import Path

# ==============================================================================
# ------------------------- CONFIGURATION GLOBALE ------------------------------
# ==============================================================================

# Chemin racine du bot (dossier contenant main.py) et chemin de sauvegarde
BASE_DIR = Path.cwd() 
DATA_DIR = BASE_DIR / "data" / "public" / "utilitaires" / "data_mytodo"

# --- Importation dynamique du Config Manager ---
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# Définition des états possibles pour les tâches
TASK_STATES = {
    "non_traite": {"emoji": "🔴", "label": "Non traité"},
    "amelioration": {"emoji": "🔵", "label": "Attente d'amélioration"},
    "test": {"emoji": "🟣", "label": "Attente de test"},
    "bug": {"emoji": "🟠", "label": "Contient un bug"},
    "valide": {"emoji": "🟢", "label": "Validé"}
}

# ==============================================================================
# ------------------------------ GESTION DONNÉES -------------------------------
# ==============================================================================

class TodoDataManager:
    """Gestionnaire de persistance des données Todo List par utilisateur."""
    
    @staticmethod
    def get_user_file(user_id: int) -> Path:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        return DATA_DIR / f"{user_id}.json"

    @staticmethod
    def load_data(user_id: int) -> dict:
        path = TodoDataManager.get_user_file(user_id)
        default_data = {"projects": []}
        if not path.exists():
            return default_data
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return default_data

    @staticmethod
    def save_data(user_id: int, data: dict):
        path = TodoDataManager.get_user_file(user_id)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[ERREUR] Sauvegarde Todo {user_id}: {e}")

# ==============================================================================
# --------------------------------- MODALS -------------------------------------
# ==============================================================================

class CreateProjectModal(ui.Modal, title="Créer un nouveau projet"):
    name_input = ui.TextInput(label="Nom du projet", placeholder="Ex: Refonte du serveur", max_length=100, required=True)

    def __init__(self, view_to_refresh):
        super().__init__()
        self.view_to_refresh = view_to_refresh

    async def on_submit(self, interaction: discord.Interaction):
        data = TodoDataManager.load_data(interaction.user.id)
        data["projects"].append({"name": self.name_input.value.strip(), "tasks": []})
        TodoDataManager.save_data(interaction.user.id, data)
        await self.view_to_refresh.update_view(interaction)

class EditProjectModal(ui.Modal, title="Modifier le nom du projet"):
    name_input = ui.TextInput(label="Nouveau nom", max_length=100, required=True)

    def __init__(self, view_to_refresh, project_idx: int, current_name: str):
        super().__init__()
        self.view_to_refresh = view_to_refresh
        self.project_idx = project_idx
        self.name_input.default = current_name

    async def on_submit(self, interaction: discord.Interaction):
        data = TodoDataManager.load_data(interaction.user.id)
        data["projects"][self.project_idx]["name"] = self.name_input.value.strip()
        TodoDataManager.save_data(interaction.user.id, data)
        await self.view_to_refresh.update_view(interaction)

class AddTaskModal(ui.Modal, title="Ajouter une tâche"):
    task_input = ui.TextInput(label="Description de la tâche", style=discord.TextStyle.paragraph, max_length=500, required=True)

    def __init__(self, view_to_refresh, project_idx: int):
        super().__init__()
        self.view_to_refresh = view_to_refresh
        self.project_idx = project_idx

    async def on_submit(self, interaction: discord.Interaction):
        data = TodoDataManager.load_data(interaction.user.id)
        new_task = {"content": self.task_input.value.strip(), "status": "non_traite"}
        data["projects"][self.project_idx]["tasks"].append(new_task)
        TodoDataManager.save_data(interaction.user.id, data)
        await self.view_to_refresh.update_view(interaction)

class DeleteTaskModal(ui.Modal, title="Supprimer une tâche"):
    task_num_input = ui.TextInput(label="Numéro de la tâche à supprimer", placeholder="Ex: 1", max_length=3, required=True)

    def __init__(self, view_to_refresh, project_idx: int):
        super().__init__()
        self.view_to_refresh = view_to_refresh
        self.project_idx = project_idx

    async def on_submit(self, interaction: discord.Interaction):
        data = TodoDataManager.load_data(interaction.user.id)
        tasks = data["projects"][self.project_idx]["tasks"]
        
        try:
            task_num = int(self.task_num_input.value.strip())
            if 1 <= task_num <= len(tasks):
                tasks.pop(task_num - 1)
                TodoDataManager.save_data(interaction.user.id, data)
                await self.view_to_refresh.update_view(interaction)
            else:
                await interaction.response.send_message("❌ Numéro de tâche invalide.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("❌ Veuillez entrer un numéro valide.", ephemeral=True)

# ==============================================================================
# ----------------------------- VUES / MENUS -----------------------------------
# ==============================================================================

class ConfirmDeleteProjectView(ui.View):
    """Vue de double confirmation pour supprimer un projet."""
    def __init__(self, parent_view, project_idx: int):
        super().__init__(timeout=120)
        self.parent_view = parent_view
        self.project_idx = project_idx
        
        btn_confirm = ui.Button(label="Confirmer la suppression", style=discord.ButtonStyle.danger, emoji="⚠️")
        btn_cancel = ui.Button(label="Annuler", style=discord.ButtonStyle.secondary)

        async def confirm_cb(interaction: discord.Interaction):
            data = TodoDataManager.load_data(interaction.user.id)
            data["projects"].pop(self.project_idx)
            TodoDataManager.save_data(interaction.user.id, data)
            main_view = TodoMainView(self.parent_view.cog, interaction.user)
            await main_view.update_view(interaction)

        async def cancel_cb(interaction: discord.Interaction):
            await self.parent_view.update_view(interaction)

        btn_confirm.callback = confirm_cb
        btn_cancel.callback = cancel_cb
        self.add_item(btn_confirm)
        self.add_item(btn_cancel)


class TaskStateSelectView(ui.View):
    """Vue pour changer l'état d'une tâche."""
    def __init__(self, parent_view, project_idx: int, task_idx: int):
        super().__init__(timeout=180)
        self.parent_view = parent_view
        self.project_idx = project_idx
        self.task_idx = task_idx
        self.user = parent_view.user
        self.cog = parent_view.cog

        options = [
            discord.SelectOption(label=info["label"], value=key, emoji=info["emoji"])
            for key, info in TASK_STATES.items()
        ]
        
        select = ui.Select(placeholder="Choisissez le nouvel état...", options=options, row=0)
        
        async def state_callback(interaction: discord.Interaction):
            new_state = select.values[0]
            data = TodoDataManager.load_data(interaction.user.id)
            data["projects"][self.project_idx]["tasks"][self.task_idx]["status"] = new_state
            TodoDataManager.save_data(interaction.user.id, data)
            await self.parent_view.update_view(interaction)

        select.callback = state_callback
        self.add_item(select)

        btn_back = ui.Button(label="Retour au projet", style=discord.ButtonStyle.secondary, emoji="🔙", row=1)
        async def back_callback(interaction: discord.Interaction):
            await self.parent_view.update_view(interaction)
            
        btn_back.callback = back_callback
        self.add_item(btn_back)


class ProjectDetailView(ui.View):
    """Vue de détail d'un projet spécifique (Tâches)."""
    def __init__(self, cog, user: discord.Member, project_idx: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.user = user
        self.project_idx = project_idx
        self.page = 0
        self.items_per_page = 20

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Vous n'êtes pas le propriétaire de cette liste.", ephemeral=True)
            return False
        return True

    def get_embed(self, data: dict) -> discord.Embed:
        project = data["projects"][self.project_idx]
        tasks = project["tasks"]
        
        title = f"📁 Projet : {project['name']}"
        desc = f"**Total des tâches :** `{len(tasks)}`\n\n"

        if not tasks:
            desc += "*Aucune tâche dans ce projet.*"
        else:
            start = self.page * self.items_per_page
            end = start + self.items_per_page
            page_tasks = tasks[start:end]

            for i, task in enumerate(page_tasks, start=start + 1):
                state_info = TASK_STATES.get(task["status"], TASK_STATES["non_traite"])
                desc += f"`{i}.` {state_info['emoji']} {task['content']}\n"
            
            max_pages = max(1, math.ceil(len(tasks) / self.items_per_page))
            desc += f"\n-# Page {self.page + 1}/{max_pages}"

        return self.cog.create_embed(self.user, title, desc)

    async def update_view(self, interaction: discord.Interaction):
        data = TodoDataManager.load_data(self.user.id)
        if self.project_idx >= len(data["projects"]): 
            main_view = TodoMainView(self.cog, self.user)
            return await main_view.update_view(interaction)

        project = data["projects"][self.project_idx]
        tasks = project["tasks"]
        max_pages = max(1, math.ceil(len(tasks) / self.items_per_page))
        self.page = max(0, min(self.page, max_pages - 1))

        self.clear_items()

        # 1. Sélecteur d'options du projet
        opt_select = ui.Select(placeholder="⚙️ Options du projet...", options=[
            discord.SelectOption(label="Modifier le nom", value="edit", emoji="✏️"),
            discord.SelectOption(label="Ajouter une tâche", value="add_task", emoji="➕"),
            discord.SelectOption(label="Supprimer une tâche", value="del_task", emoji="➖"),
            discord.SelectOption(label="Supprimer le projet", value="delete", emoji="🗑️")
        ], row=0)
        
        async def opt_callback(inter: discord.Interaction):
            val = opt_select.values[0]
            if val == "edit":
                await inter.response.send_modal(EditProjectModal(self, self.project_idx, project["name"]))
            elif val == "add_task":
                await inter.response.send_modal(AddTaskModal(self, self.project_idx))
            elif val == "del_task":
                await inter.response.send_modal(DeleteTaskModal(self, self.project_idx))
            elif val == "delete":
                confirm_embed = self.cog.create_embed(self.user, "⚠️ Attention", "Voulez-vous vraiment supprimer ce projet de façon définitive ?")
                await inter.response.send_message(embed=confirm_embed, view=ConfirmDeleteProjectView(self, self.project_idx), ephemeral=True)
                
        opt_select.callback = opt_callback
        self.add_item(opt_select)

        # 2. Sélecteur de tâches pour modifier l'état
        start = self.page * self.items_per_page
        end = start + self.items_per_page
        page_tasks = tasks[start:end]

        if page_tasks:
            task_options = [
                discord.SelectOption(
                    label=f"Tâche {start + i + 1}: {task['content'][:50]}...",
                    value=str(start + i),
                    emoji=TASK_STATES.get(task["status"], TASK_STATES["non_traite"])["emoji"]
                ) for i, task in enumerate(page_tasks)
            ]
            task_select = ui.Select(placeholder="Changer l'état d'une tâche...", options=task_options, row=1)
            
            async def task_callback(inter: discord.Interaction):
                task_idx = int(task_select.values[0])
                state_view = TaskStateSelectView(self, self.project_idx, task_idx)
                embed = self.cog.create_embed(self.user, "Changement d'état", "Choisissez le nouvel état pour cette tâche.")
                await inter.response.edit_message(embed=embed, view=state_view)
            
            task_select.callback = task_callback
            self.add_item(task_select)

        # 3. Boutons de navigation
        btn_prev = ui.Button(emoji="◀️", style=discord.ButtonStyle.gray, row=2, disabled=(self.page == 0))
        btn_next = ui.Button(emoji="▶️", style=discord.ButtonStyle.gray, row=2, disabled=(self.page >= max_pages - 1))
        btn_back = ui.Button(label="Retour aux projets", style=discord.ButtonStyle.primary, emoji="🔙", row=2)

        async def prev_cb(inter): self.page -= 1; await self.update_view(inter)
        async def next_cb(inter): self.page += 1; await self.update_view(inter)
        async def back_cb(inter): 
            main_view = TodoMainView(self.cog, self.user)
            await main_view.update_view(inter)

        btn_prev.callback = prev_cb
        btn_next.callback = next_cb
        btn_back.callback = back_cb

        self.add_item(btn_prev)
        self.add_item(btn_back)
        self.add_item(btn_next)

        embed = self.get_embed(data)
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)


class TodoMainView(ui.View):
    """Vue principale (Liste des projets)."""
    def __init__(self, cog, user: discord.Member):
        super().__init__(timeout=300)
        self.cog = cog
        self.user = user
        self.page = 0
        self.items_per_page = 20

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ C'est la Todo List d'un autre utilisateur.", ephemeral=True)
            return False
        return True

    def get_embed(self, data: dict) -> discord.Embed:
        projects = data.get("projects", [])
        title = "📋 Vue d'ensemble des projets"
        desc = ""

        if not projects:
            desc = "*Vous n'avez aucun projet pour le moment. Cliquez sur 'Créer un projet' pour commencer.*"
        else:
            start = self.page * self.items_per_page
            end = start + self.items_per_page
            page_projects = projects[start:end]

            for i, p in enumerate(page_projects, start=start + 1):
                total_tasks = len(p["tasks"])
                completed_tasks = sum(1 for t in p["tasks"] if t["status"] == "valide")
                desc += f"`{i}.` **{p['name']}** - `{completed_tasks}/{total_tasks}` tâches terminées\n"
            
            max_pages = max(1, math.ceil(len(projects) / self.items_per_page))
            desc += f"\n-# Page {self.page + 1}/{max_pages}"

        return self.cog.create_embed(self.user, title, desc)

    async def update_view(self, interaction: discord.Interaction = None):
        data = TodoDataManager.load_data(self.user.id)
        projects = data.get("projects", [])
        max_pages = max(1, math.ceil(len(projects) / self.items_per_page))
        self.page = max(0, min(self.page, max_pages - 1))
        
        self.clear_items()

        # 1. Sélecteur de projets
        start = self.page * self.items_per_page
        end = start + self.items_per_page
        page_projects = projects[start:end]

        if page_projects:
            options = [
                discord.SelectOption(label=p["name"][:100], value=str(start + i), emoji="📂")
                for i, p in enumerate(page_projects)
            ]
            select = ui.Select(placeholder="Ouvrir un projet...", options=options, row=0)
            
            async def select_callback(inter: discord.Interaction):
                project_idx = int(select.values[0])
                project_view = ProjectDetailView(self.cog, self.user, project_idx)
                await project_view.update_view(inter)
            
            select.callback = select_callback
            self.add_item(select)

        # 2. Boutons de navigation et de création
        btn_create = ui.Button(label="Créer un projet", style=discord.ButtonStyle.success, emoji="✨", row=1)
        btn_prev = ui.Button(emoji="◀️", style=discord.ButtonStyle.gray, row=1, disabled=(self.page == 0))
        btn_next = ui.Button(emoji="▶️", style=discord.ButtonStyle.gray, row=1, disabled=(self.page >= max_pages - 1))

        async def create_cb(inter): await inter.response.send_modal(CreateProjectModal(self))
        async def prev_cb(inter): self.page -= 1; await self.update_view(inter)
        async def next_cb(inter): self.page += 1; await self.update_view(inter)

        btn_create.callback = create_cb
        btn_prev.callback = prev_cb
        btn_next.callback = next_cb

        self.add_item(btn_prev)
        self.add_item(btn_create)
        self.add_item(btn_next)

        embed = self.get_embed(data)
        
        if interaction:
            if interaction.response.is_done():
                await interaction.edit_original_response(embed=embed, view=self)
            else:
                await interaction.response.edit_message(embed=embed, view=self)
        return embed, self

# ==============================================================================
# ------------------------------ COG PRINCIPAL ---------------------------------
# ==============================================================================

class MyTodo(commands.Cog):
    """Cog de gestion de Todo List personnelle interactive."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def create_embed(self, user: discord.Member, title: str, description: str) -> discord.Embed:
        """Méthode centralisée pour générer les embeds avec Config Manager en priorité."""
        if config_manager:
            embed = config_manager.get_formatted_embed(
                guild=user.guild, 
                user=user, 
                bot=self.bot, 
                title=title, 
                description=description
            )
            # Surcharge de l'auteur pour répondre à la demande spécifique de l'utilisateur
            embed.set_author(name=f"Ma Todo List", icon_url=user.display_avatar.url)
            return embed
        
        # Fallback standard si config_manager est indisponible
        embed = discord.Embed(title=title, description=description, color=0x3498db)
        embed.set_author(name=f"Ma Todo List", icon_url=user.display_avatar.url)
        embed.set_footer(text="Gestionnaire de Projets & Tâches")
        return embed

    @commands.hybrid_command(name="mytodo", description="Ouvre votre gestionnaire de Todo List personnel.")
    async def mytodo(self, ctx: commands.Context):
        try:
            if ctx.interaction:
                await ctx.defer(ephemeral=False)

            view = TodoMainView(self, ctx.author)
            embed, view_instance = await view.update_view()

            if ctx.interaction:
                await ctx.send(embed=embed, view=view_instance)
            else:
                await ctx.send(embed=embed, view=view_instance, reference=ctx.message)
                
        except Exception as e:
            print(f"[ERREUR - MyTodo] : {e}")
            traceback.print_exc()
            await ctx.send("❌ Une erreur est survenue lors de l'ouverture de votre Todo List.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(MyTodo(bot))