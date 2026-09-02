import discord
from discord.ext import commands
from discord import ui
import json
from pathlib import Path

try:
    from cogs.config_manager.utils import config_manager
except ImportError:
    config_manager = None

DATA_FILE = Path("data/custom_commands_config.json")

def load_data():
    if not DATA_FILE.parent.exists():
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def get_guild_commands(guild_id: int):
    data = load_data()
    guild_id_str = str(guild_id)
    if guild_id_str not in data:
        data[guild_id_str] = {"commands": {}}
        save_data(data)
    return data[guild_id_str]["commands"]

# ==============================================================================
# --------------------------- MODALS -------------------------------------------
# ==============================================================================
class CustomCommandModal(ui.Modal):
    def __init__(self, parent_view, keyword: str = None, message: str = None):
        is_edit = keyword is not None
        title = "✏️ Modifier la commande" if is_edit else "➕ Ajouter une commande"
        super().__init__(title=title)
        
        self.parent_view = parent_view
        self.is_edit = is_edit
        self.old_keyword = keyword

        self.keyword_input = ui.TextInput(
            label="Mot clé",
            placeholder="Ex: minecraft",
            default=keyword if keyword else "",
            max_length=50,
            required=True
        )
        self.message_input = ui.TextInput(
            label="Message personnalisé",
            style=discord.TextStyle.paragraph,
            placeholder="Ex: Le jeu des cubes !",
            default=message if message else "",
            max_length=1000,
            required=True
        )
        
        self.add_item(self.keyword_input)
        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction):
        new_keyword = self.keyword_input.value.strip().lower()
        new_message = self.message_input.value.strip()

        data = load_data()
        guild_id_str = str(interaction.guild.id)
        if guild_id_str not in data:
            data[guild_id_str] = {"commands": {}}

        cmds = data[guild_id_str]["commands"]

        if self.is_edit and self.old_keyword != new_keyword:
            if self.old_keyword in cmds:
                del cmds[self.old_keyword]

        cmds[new_keyword] = new_message
        save_data(data)

        self.parent_view.commands = cmds
        self.parent_view.selected_keyword = new_keyword
        await self.parent_view.update_ui(interaction)

# ==============================================================================
# --------------------------- VUES & SELECTEURS --------------------------------
# ==============================================================================
class SingleCommandSelect(ui.Select):
    def __init__(self, commands_dict: dict, page: int):
        self.commands_dict = commands_dict
        self.page = page
        
        items = list(commands_dict.items())
        start_idx = page * 25
        end_idx = start_idx + 25
        current_page_items = items[start_idx:end_idx]

        options = []
        for idx, (kw, msg) in enumerate(current_page_items, start=start_idx + 1):
            desc = msg if len(msg) <= 100 else msg[:97] + "..."
            options.append(discord.SelectOption(label=f"{idx}. {kw}", description=desc, value=kw))

        if not options:
            options.append(discord.SelectOption(label="Aucune commande", value="none", description="Utilisez le bouton Ajouter"))

        super().__init__(placeholder="🔍 Sélectionner un mot clé custom...", options=options, row=0, disabled=not commands_dict)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            return

        self.view.selected_keyword = self.values[0]
        await self.view.update_ui(interaction)

class CommandManageView(ui.View):
    def __init__(self, ctx, bot, keyword, message):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.bot = bot
        self.keyword = keyword
        self.message = message

    @ui.button(label="Modifier", style=discord.ButtonStyle.primary, emoji="✏️")
    async def edit_btn(self, interaction: discord.Interaction, button: ui.Button):
        # Vérification Admin pour modification
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("❌ Vous n'avez pas la permission de modifier cette commande.", ephemeral=True)
        await interaction.response.send_modal(CustomCommandModal(self, keyword=self.keyword, message=self.message))

    @ui.button(label="Supprimer", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_btn(self, interaction: discord.Interaction, button: ui.Button):
        # Vérification Admin pour suppression
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("❌ Vous n'avez pas la permission de supprimer cette commande.", ephemeral=True)
            
        data = load_data()
        guild_id_str = str(interaction.guild.id)
        if guild_id_str in data and self.keyword in data[guild_id_str]["commands"]:
            del data[guild_id_str]["commands"][self.keyword]
            save_data(data)
            
        await interaction.response.send_message(f"🗑️ Le mot clé `{self.keyword}` a été supprimé.", ephemeral=True)
        try:
            await interaction.message.delete()
        except:
            pass

class CustomCommandsView(ui.View):
    def __init__(self, ctx, bot, is_admin: bool):
        super().__init__(timeout=600)
        self.ctx = ctx
        self.bot = bot
        self.is_admin = is_admin
        self.message = None
        self.commands = get_guild_commands(ctx.guild.id)
        self.selected_keyword = None
        self.page = 0
        self.max_pages = max(0, (len(self.commands) - 1) // 25)

        self.setup_components()

    def create_custom_embed(self, title: str, description: str) -> discord.Embed:
        if config_manager:
            return config_manager.get_formatted_embed(
                guild=self.ctx.guild,
                user=self.ctx.author,
                bot=self.bot,
                title=title,
                description=description,
                target_id=self.ctx.guild.id,
            )
        return discord.Embed(title=title, description=description, color=0x57F287)

    def setup_components(self):
        self.clear_items()
        
        # Sélecteur principal des commandes (25 max par page)
        if self.is_admin:
            self.add_item(SingleCommandSelect(self.commands, self.page))

        # Bouton Ajouter (Uniquement pour les admins)
        if self.is_admin:
            add_button = ui.Button(label="Ajouter", style=discord.ButtonStyle.success, emoji="➕", row=1)
            add_button.callback = self.add_callback
            self.add_item(add_button)

            edit_button = ui.Button(
                label="Modifier",
                style=discord.ButtonStyle.primary,
                emoji="✏️",
                row=1,
                disabled=not self.selected_keyword,
            )
            edit_button.callback = self.edit_callback
            self.add_item(edit_button)

            delete_button = ui.Button(
                label="Supprimer",
                style=discord.ButtonStyle.danger,
                emoji="🗑️",
                row=1,
                disabled=not self.selected_keyword,
            )
            delete_button.callback = self.delete_callback
            self.add_item(delete_button)

        # Pagination si nécessaire (> 25 éléments)
        if self.max_pages > 0:
            prev_button = ui.Button(label="◀️ Précédent", style=discord.ButtonStyle.secondary, disabled=self.page == 0, row=2)
            prev_button.callback = self.prev_callback
            self.add_item(prev_button)

            next_button = ui.Button(label="Suivant ▶️", style=discord.ButtonStyle.secondary, disabled=self.page >= self.max_pages, row=2)
            next_button.callback = self.next_callback
            self.add_item(next_button)

    async def add_callback(self, interaction: discord.Interaction):
        if not self.is_admin:
            return
        await interaction.response.send_modal(CustomCommandModal(self))

    async def edit_callback(self, interaction: discord.Interaction):
        if not self.is_admin or not self.selected_keyword:
            return

        message = self.commands.get(self.selected_keyword, "")
        await interaction.response.send_modal(
            CustomCommandModal(self, keyword=self.selected_keyword, message=message)
        )

    async def delete_callback(self, interaction: discord.Interaction):
        if not self.is_admin or not self.selected_keyword:
            return

        data = load_data()
        guild_id_str = str(interaction.guild.id)
        if guild_id_str in data and self.selected_keyword in data[guild_id_str]["commands"]:
            del data[guild_id_str]["commands"][self.selected_keyword]
            save_data(data)

        self.commands = get_guild_commands(interaction.guild.id)
        self.selected_keyword = None
        await self.update_ui(interaction)

    async def prev_callback(self, interaction: discord.Interaction):
        if self.page > 0:
            self.page -= 1
            self.setup_components()
            await self.update_ui(interaction)

    async def next_callback(self, interaction: discord.Interaction):
        if self.page < self.max_pages:
            self.page += 1
            self.setup_components()
            await self.update_ui(interaction)

    def get_embed(self) -> discord.Embed:
        items = list(self.commands.items())
        start_idx = self.page * 25
        end_idx = start_idx + 25
        current_page_items = items[start_idx:end_idx]

        desc_list = ""
        if not current_page_items:
            desc_list = "*Aucune commande personnalisée enregistrée.*"
        else:
            for idx, (kw, msg) in enumerate(current_page_items, start=start_idx + 1):
                desc_list += f"**{idx}.** `{kw}` - {msg}\n"

        title = "📋 Liste des Commandes Custom"
        desc = (
            f"> Mode : **{'Administration' if self.is_admin else 'Consultation'}**\n"
            f"> Page **{self.page + 1}** / **{max(1, self.max_pages + 1)}**\n\n"
            f"{desc_list}"
        )

        if self.selected_keyword:
            selected_message = self.commands.get(self.selected_keyword, "")
            if len(selected_message) > 300:
                selected_message = selected_message[:297] + "..."
            desc += (
                f"\n🔎 **Sélection actuelle**\n"
                f"`{self.selected_keyword}`\n"
                f"{selected_message}"
            )

        return self.create_custom_embed(title, desc)

    async def update_ui(self, interaction: discord.Interaction):
        self.max_pages = max(0, (len(self.commands) - 1) // 25)
        if self.page > self.max_pages:
            self.page = max(0, self.max_pages)
        self.setup_components()
        
        embed = self.get_embed()
        if not interaction.response.is_done():
            await interaction.response.defer()
        if self.message:
            await self.message.edit(embed=embed, view=self)
        else:
            await interaction.edit_original_response(embed=embed, view=self)

# ==============================================================================
# --------------------------- COG PRINCIPAL ------------------------------------
# ==============================================================================
class CustomCommandsCog(commands.Cog):
    """💬 Module de gestion des commandes custom par mots-clés."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name="custom",
        aliases=["customs"],
        description="Affiche ou configure la liste des commandes custom par mots-clés."
    )
    async def customs_cmd(self, ctx: commands.Context):
        # Vérification si l'utilisateur est admin (Manage Guild)
        is_admin = ctx.author.guild_permissions.manage_guild
        
        view = CustomCommandsView(ctx, self.bot, is_admin)
        embed = view.get_embed()
        msg = await ctx.send(embed=embed, view=view, ephemeral=not is_admin)
        view.message = msg

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # Vérification stricte : le contenu du message doit correspondre EXACTEMENT au mot clé (ignorant la casse)
        content_cleaned = message.content.strip().lower()
        
        guild_commands = get_guild_commands(message.guild.id)
        
        if content_cleaned in guild_commands:
            response_text = guild_commands[content_cleaned]
            try:
                await message.channel.send(response_text)
            except Exception as e:
                print(f"[CustomCommands] Erreur d'envoi : {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(CustomCommandsCog(bot))