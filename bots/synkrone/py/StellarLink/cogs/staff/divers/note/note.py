import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from datetime import datetime
import math
import traceback

# ==========================================
# CONSTANTES ET CONFIGURATION
# ==========================================
NOTE_TIMEOUT = 300  # Sécurité : Timeout de 300s selon vos directives
NOTES_PER_PAGE = 10
NOTE_COLOR = 0x3498db
DATA_DIR = "./data/note"

# Import dynamique du config_manager (Priorité Absolue)
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

def log(mode: str, message: str):
    """Système de logs pour le suivi technique."""
    print(f"[NOTE] [{mode.upper()}] {message}")

# ==========================================
# GESTIONNAIRE DE DONNÉES (CRUD)
# ==========================================
class NoteManager:
    def __init__(self):
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)

    def _get_guild_dir(self, guild_id: int) -> str:
        guild_dir = os.path.join(DATA_DIR, str(guild_id))
        if not os.path.exists(guild_dir):
            os.makedirs(guild_dir)
        return guild_dir

    def get_file_path(self, guild_id: int, name: str) -> str:
        return os.path.join(self._get_guild_dir(guild_id), f"{name.lower()}.json")

    def create_note(self, guild_id: int, name: str, title: str, short_description: str, content: str, author_id: int) -> bool:
        filepath = self.get_file_path(guild_id, name)
        if os.path.exists(filepath):
            return False
        
        now = datetime.now().isoformat()
        data = {
            "content": content[:2000],
            "title": title,
            "author_id": author_id,
            "created_at": now,
            "updated_at": now,
            "is_public": True,
            "short_description": short_description[:100],
            "markdown_enabled": False
        }
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            log("crud", f"Note '{name}' créée pour la guilde {guild_id}")
            return True
        except Exception as e:
            log("error", f"Erreur lors de la création de la note: {e}")
            return False

    def get_note(self, guild_id: int, name: str) -> dict | None:
        filepath = self.get_file_path(guild_id, name)
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    def update_note(self, guild_id: int, name: str, data_updates: dict) -> bool:
        filepath = self.get_file_path(guild_id, name)
        if not os.path.exists(filepath):
            return False
        
        note_data = self.get_note(guild_id, name)
        if not note_data:
            return False
            
        note_data.update(data_updates)
        note_data["updated_at"] = datetime.now().isoformat()
        
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(note_data, f, indent=4)
            log("crud", f"Note '{name}' mise à jour pour la guilde {guild_id}")
            return True
        except Exception as e:
            log("error", f"Erreur lors de la mise à jour: {e}")
            return False

    def delete_note(self, guild_id: int, name: str) -> bool:
        filepath = self.get_file_path(guild_id, name)
        if os.path.exists(filepath):
            os.remove(filepath)
            log("crud", f"Note '{name}' supprimée pour la guilde {guild_id}")
            return True
        return False

    def get_all_notes(self, guild_id: int) -> dict:
        guild_dir = self._get_guild_dir(guild_id)
        notes = {}
        for filename in os.listdir(guild_dir):
            if filename.endswith('.json'):
                name = filename[:-5]
                note_data = self.get_note(guild_id, name)
                if note_data:
                    notes[name] = note_data
        return notes

# ==========================================
# CLASSES DE BASE ET GESTION DES EMBEDS
# ==========================================
class BaseNoteView(discord.ui.View):
    def __init__(self, cog_instance, author_id: int, timeout: int = NOTE_TIMEOUT):
        super().__init__(timeout=timeout)
        self.cog_instance = cog_instance
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Vérification stricte de sécurité."""
        if interaction.user.id != self.author_id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Vous n'avez pas la permission d'utiliser ce menu.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if hasattr(self, 'message') and self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    def create_note_embed(self, title: str, description: str, guild: discord.Guild, user: discord.Member | discord.User, bot: commands.Bot) -> discord.Embed:
        """Générateur centralisé avec priorité absolue au config_manager."""
        if config_manager and guild and user and bot:
            try:
                return config_manager.get_formatted_embed(
                    title=title,
                    description=description,
                    guild=guild,
                    user=user,
                    bot=bot,
                    target_id=guild.id
                )
            except Exception as e:
                log("error", f"Erreur config_manager: {e}\n{traceback.format_exc()}")
                
        # Fallback global si config_manager est absent ou échoue
        embed = discord.Embed(title=title, description=description, color=NOTE_COLOR)
        if bot.user.avatar:
            embed.set_author(name=bot.user.name, icon_url=bot.user.display_avatar.url)
        embed.set_footer(text="Système de Notes Multi-Serveur")
        return embed

# ==========================================
# MODALS (CRÉATION ET ÉDITION)
# ==========================================
class NoteModal(discord.ui.Modal):
    def __init__(self, view: BaseNoteView, mode: str = "create", note_name: str = None, note_data: dict = None):
        super().__init__(title="Créer une Note" if mode == "create" else f"Modifier: {note_name}"[:45])
        self.view = view
        self.mode = mode
        self.note_name = note_name

        self.n_name = discord.ui.TextInput(
            label="Nom de la note (sans espace)", 
            max_length=20, 
            required=True,
            default=note_name if mode == "edit" else None
        )
        self.n_title = discord.ui.TextInput(
            label="Titre affiché", max_length=50, required=True, 
            default=note_data.get("title") if note_data else None
        )
        self.n_short = discord.ui.TextInput(
            label="Description courte", max_length=100, required=True, 
            default=note_data.get("short_description") if note_data else None
        )
        self.n_content = discord.ui.TextInput(
            label="Contenu", style=discord.TextStyle.paragraph, max_length=2000, required=True, 
            default=note_data.get("content") if note_data else None
        )
        
        self.add_item(self.n_name)
        self.add_item(self.n_title)
        self.add_item(self.n_short)
        self.add_item(self.n_content)

    async def on_submit(self, interaction: discord.Interaction):
        manager = self.view.cog_instance.note_manager
        guild_id = interaction.guild.id
        new_name = self.n_name.value.lower().replace(" ", "_")

        try:
            if self.mode == "create":
                success = manager.create_note(guild_id, new_name, self.n_title.value, self.n_short.value, self.n_content.value, interaction.user.id)
                if not success:
                    return await interaction.response.send_message("❌ Une note avec ce nom existe déjà.", ephemeral=True)
            else:
                if new_name != self.note_name:
                    if manager.get_note(guild_id, new_name):
                        return await interaction.response.send_message("❌ Le nouveau nom choisi existe déjà.", ephemeral=True)
                    
                    note_data = manager.get_note(guild_id, self.note_name)
                    if note_data:
                        success = manager.create_note(guild_id, new_name, self.n_title.value, self.n_short.value, self.n_content.value, note_data['author_id'])
                        if success:
                            manager.update_note(guild_id, new_name, {
                                "is_public": note_data.get('is_public', True),
                                "markdown_enabled": note_data.get('markdown_enabled', False),
                                "created_at": note_data['created_at']
                            })
                            manager.delete_note(guild_id, self.note_name)
                            if hasattr(self.view, 'note_name'):
                                self.view.note_name = new_name
                    else:
                        return await interaction.response.send_message("❌ Erreur: Note source introuvable.", ephemeral=True)
                else:
                    manager.update_note(guild_id, self.note_name, {
                        "title": self.n_title.value,
                        "short_description": self.n_short.value,
                        "content": self.n_content.value
                    })

            log("info", f"Note {new_name} gérée par {interaction.user}")
            
            # Rafraîchissement dynamique de la vue parente
            if hasattr(self.view, 'update_view'):
                await self.view.update_view(interaction)
            elif hasattr(self.view, 'refresh_menu'):
                await self.view.refresh_menu(interaction)
                
        except Exception as e:
            log("error", f"Erreur dans le modal: {e}")
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Une erreur interne est survenue.", ephemeral=True)

# ==========================================
# INTERFACES UTILISATEUR (VIEWS)
# ==========================================
class ConfirmDeleteView(BaseNoteView):
    def __init__(self, cog_instance, author_id, note_name, parent_view):
        super().__init__(cog_instance, author_id)
        self.note_name = note_name
        self.parent_view = parent_view

    @discord.ui.button(label="Confirmer", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog_instance.note_manager.delete_note(interaction.guild.id, self.note_name)
        if hasattr(self.parent_view, 'parent_view'):
            await self.parent_view.parent_view.update_view(interaction)
        else:
            await interaction.response.send_message("✅ Note supprimée avec succès.", ephemeral=True)

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.parent_view.refresh_menu(interaction)

class EditNoteMenuView(BaseNoteView):
    def __init__(self, cog_instance, author_id, note_name, parent_view):
        super().__init__(cog_instance, author_id)
        self.note_name = note_name
        self.parent_view = parent_view

    async def refresh_menu(self, interaction: discord.Interaction):
        note_data = self.cog_instance.note_manager.get_note(interaction.guild.id, self.note_name)
        if not note_data:
            return await interaction.response.send_message("❌ Note introuvable ou supprimée.", ephemeral=True)

        content_display = f"```md\n{note_data['content']}\n```" if note_data.get('markdown_enabled') else note_data['content']
        desc = (
            f"**📝 Commande:** `/note name:{self.note_name}`\n"
            f"**🏷️ Titre:** {note_data.get('title', self.note_name)}\n"
            f"**🔐 Visibilité:** {'🌐 Publique' if note_data['is_public'] else '🔒 Privée (Admin uniquement)'}\n\n"
            f"**Description courte:**\n{note_data['short_description']}\n\n"
            f"**📄 Aperçu du Contenu:**\n{content_display}"
        )

        embed = self.create_note_embed(f"🔧 Édition : {note_data.get('title', self.note_name)}", desc, interaction.guild, interaction.user, self.cog_instance.bot)
        
        if interaction.response.is_done():
            await interaction.message.edit(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Modifier", style=discord.ButtonStyle.primary, emoji="✏️", row=0)
    async def edit_content(self, interaction: discord.Interaction, button: discord.ui.Button):
        note_data = self.cog_instance.note_manager.get_note(interaction.guild.id, self.note_name)
        if not note_data:
            return await interaction.response.send_message("❌ Note introuvable.", ephemeral=True)
        await interaction.response.send_modal(NoteModal(self, mode="edit", note_name=self.note_name, note_data=note_data))

    @discord.ui.button(label="Markdown", style=discord.ButtonStyle.secondary, emoji="📄", row=0)
    async def toggle_markdown(self, interaction: discord.Interaction, button: discord.ui.Button):
        note_data = self.cog_instance.note_manager.get_note(interaction.guild.id, self.note_name)
        self.cog_instance.note_manager.update_note(interaction.guild.id, self.note_name, {"markdown_enabled": not note_data["markdown_enabled"]})
        await self.refresh_menu(interaction)

    @discord.ui.button(label="Visibilité", style=discord.ButtonStyle.secondary, emoji="🔄", row=0)
    async def toggle_visibility(self, interaction: discord.Interaction, button: discord.ui.Button):
        note_data = self.cog_instance.note_manager.get_note(interaction.guild.id, self.note_name)
        self.cog_instance.note_manager.update_note(interaction.guild.id, self.note_name, {"is_public": not note_data["is_public"]})
        await self.refresh_menu(interaction)

    @discord.ui.button(label="Supprimer", style=discord.ButtonStyle.danger, emoji="🗑️", row=1)
    async def delete_note(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ConfirmDeleteView(self.cog_instance, self.author_id, self.note_name, self)
        embed = self.create_note_embed("⚠️ Action Irréversible", f"Confirmez-vous la suppression de la note `{self.note_name}` ?", interaction.guild, interaction.user, self.cog_instance.bot)
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Retour", style=discord.ButtonStyle.success, emoji="◀", row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.parent_view.update_view(interaction)

class NoteSelect(discord.ui.Select):
    def __init__(self, options):
        super().__init__(placeholder="Sélectionnez une note pour la configurer...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_note = self.values[0]
        edit_view = EditNoteMenuView(self.view.cog_instance, self.view.author_id, selected_note, self.view)
        await edit_view.refresh_menu(interaction)

class NoteView(BaseNoteView):
    def __init__(self, cog_instance, author_id):
        super().__init__(cog_instance, author_id)
        self.current_page = 0
        self.max_pages = 1

    async def update_view(self, interaction: discord.Interaction):
        guild_id = interaction.guild.id
        all_notes = self.cog_instance.note_manager.get_all_notes(guild_id)
        sorted_keys = sorted(all_notes.keys())
        
        self.max_pages = math.ceil(len(sorted_keys) / NOTES_PER_PAGE) or 1
        self.current_page = max(0, min(self.current_page, self.max_pages - 1))
        
        start = self.current_page * NOTES_PER_PAGE
        end = start + NOTES_PER_PAGE
        page_keys = sorted_keys[start:end]

        desc = (
            "📝 **Gestionnaire de Notes**\n"
            "Sauvegardez et réutilisez des blocs de texte dynamiquement.\n\n"
            "**Exemples d'utilisation :**\n"
            "• `/note name:recrutement`\n"
            "• `/note name:reglement`\n\n"
            "**📚 Notes disponibles sur ce serveur :**\n"
        )

        if not sorted_keys:
            desc += "*Aucune note n'a été créée pour le moment.*"
        else:
            for i, key in enumerate(page_keys, start=start + 1):
                note = all_notes[key]
                icon = "🌐" if note.get("is_public", True) else "🔒"
                desc += f"`{i}.` {icon} **{key}** - {note.get('short_description', 'N/A')}\n"

        embed = self.create_note_embed("Système de Notes Centralisé", desc, interaction.guild, interaction.user, self.cog_instance.bot)
        
        self.clear_items()
        
        if page_keys:
            options = [
                discord.SelectOption(
                    label=f"{i+1}. {k}", 
                    description=all_notes[k].get('short_description', '')[:100],
                    emoji="📄",
                    value=k
                ) for i, k in enumerate(page_keys, start=start + 1)
            ]
            self.add_item(NoteSelect(options))

        # Pagination & Ajout
        prev_btn = discord.ui.Button(emoji="◀", style=discord.ButtonStyle.gray, custom_id="prev", row=2, disabled=self.current_page == 0)
        prev_btn.callback = self.nav_callback
        next_btn = discord.ui.Button(emoji="▶", style=discord.ButtonStyle.gray, custom_id="next", row=2, disabled=self.current_page >= self.max_pages - 1)
        next_btn.callback = self.nav_callback
        add_btn = discord.ui.Button(emoji="➕", label="Nouvelle Note", style=discord.ButtonStyle.success, custom_id="add", row=2)
        add_btn.callback = self.nav_callback

        self.add_item(prev_btn)
        self.add_item(discord.ui.Button(label=f"Page {self.current_page + 1}/{self.max_pages}", disabled=True, row=2))
        self.add_item(next_btn)
        self.add_item(add_btn)

        if interaction.response.is_done():
            await interaction.message.edit(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    async def nav_callback(self, interaction: discord.Interaction):
        custom_id = interaction.data["custom_id"]
        if custom_id == "prev":
            self.current_page -= 1
        elif custom_id == "next":
            self.current_page += 1
        elif custom_id == "add":
            return await interaction.response.send_modal(NoteModal(self, mode="create"))
        await self.update_view(interaction)

# ==========================================
# COG PRINCIPAL
# ==========================================
class NoteCog(commands.Cog, name="Notes"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.note_manager = NoteManager()

    @commands.hybrid_command(name="note", description="Affiche le panel de gestion des notes ou le contenu d'une note spécifique.")
    @app_commands.describe(name="Le nom exact de la note à afficher (laisser vide pour le panel)")
    async def note_cmd(self, ctx: commands.Context, name: str = None):
        """Commande hybride principale du système de note."""
        # 1. MODE LISTE / PANEL D'ADMINISTRATION
        if name is None:
            if not ctx.author.guild_permissions.administrator:
                return await ctx.send("❌ Vous devez être Administrateur pour accéder au panel de gestion.", ephemeral=True)
                
            view = NoteView(self, ctx.author.id)
            all_notes = self.note_manager.get_all_notes(ctx.guild.id)
            sorted_keys = sorted(all_notes.keys())
            
            view.max_pages = math.ceil(len(sorted_keys) / NOTES_PER_PAGE) or 1
            page_keys = sorted_keys[0:NOTES_PER_PAGE]

            desc = (
                "📝 **Gestionnaire de Notes**\n"
                "Sauvegardez et réutilisez des blocs de texte dynamiquement.\n\n"
                "**📚 Notes disponibles :**\n"
            )

            if not sorted_keys:
                desc += "*Aucune note n'a été créée pour le moment.*"
            else:
                for i, key in enumerate(page_keys, start=1):
                    note = all_notes[key]
                    icon = "🌐" if note.get("is_public", True) else "🔒"
                    desc += f"`{i}.` {icon} **{key}** - {note.get('short_description', 'N/A')}\n"

            embed = view.create_note_embed("Système de Notes Centralisé", desc, ctx.guild, ctx.author, self.bot)
            
            if page_keys:
                options = [
                    discord.SelectOption(label=f"{i+1}. {k}", description=all_notes[k].get('short_description', '')[:100], emoji="📄", value=k) 
                    for i, k in enumerate(page_keys, start=1)
                ]
                view.add_item(NoteSelect(options))

            prev_btn = discord.ui.Button(emoji="◀", style=discord.ButtonStyle.gray, custom_id="prev", row=2, disabled=True)
            prev_btn.callback = view.nav_callback
            next_btn = discord.ui.Button(emoji="▶", style=discord.ButtonStyle.gray, custom_id="next", row=2, disabled=view.max_pages <= 1)
            next_btn.callback = view.nav_callback
            add_btn = discord.ui.Button(emoji="➕", label="Nouvelle Note", style=discord.ButtonStyle.success, custom_id="add", row=2)
            add_btn.callback = view.nav_callback

            view.add_item(prev_btn)
            view.add_item(discord.ui.Button(label=f"Page 1/{view.max_pages}", disabled=True, row=2))
            view.add_item(next_btn)
            view.add_item(add_btn)

            msg = await ctx.send(embed=embed, view=view)
            view.message = msg
            return

        # 2. MODE AFFICHAGE DE NOTE (UTILISATEUR FINAL)
        note_data = self.note_manager.get_note(ctx.guild.id, name)
        if not note_data:
            return await ctx.send(f"❌ La note `{name}` n'existe pas sur ce serveur.", ephemeral=True)

        if not note_data["is_public"] and not ctx.author.guild_permissions.administrator:
            return await ctx.send("🔒 Cette note est restreinte au personnel administratif.", ephemeral=True)

        content = note_data["content"]
        if note_data.get("markdown_enabled"):
            content = f"```md\n{content}\n```"

        created_dt = datetime.fromisoformat(note_data["created_at"])
        
        desc = (
            f"**👤 Auteur:** <@{note_data['author_id']}>\n"
            f"**📅 Créée le:** <t:{int(created_dt.timestamp())}:F>\n\n"
            f"{content}"
        )

        temp_view = BaseNoteView(self, ctx.author.id)
        embed = temp_view.create_note_embed(note_data["title"], desc, ctx.guild, ctx.author, self.bot)
        await ctx.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(NoteCog(bot))