import discord
from discord.ext import commands, tasks
from discord import ui
import json
import os
import asyncio
import time
import traceback
from pathlib import Path

# ==============================================================================
# --------------------------- IMPORTATION UTILS --------------------------------
# ==============================================================================
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# ==============================================================================
# --------------------------- UTILITAIRES JSON ---------------------------------
# ==============================================================================

def _get_guild_mod_path() -> Path:
    return Path(__file__).parent / "guild_mod.json"

def load_guild_mod() -> list[int]:
    p = _get_guild_mod_path()
    if not p.exists(): return []
    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return [int(x) for x in data] if isinstance(data, list) else []
    except: return []

def save_guild_mod(ids: list[int]) -> None:
    p = _get_guild_mod_path()
    with p.open("w", encoding="utf-8") as f:
        # On garde les 5 premiers IDs uniques
        json.dump(list(dict.fromkeys([int(x) for x in ids]))[:5], f, indent=2)

# ==============================================================================
# --------------------------- COG PRINCIPAL ------------------------------------
# ==============================================================================

class BotAdmin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.avatar_waiting_list = {} 
        self.owner_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "profil", "owner", "owner.json"))
        self.config_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "bot_config.json"))
        
        config = self._load_config()
        self.description_list = config.get("presences", ["Vax 1.4 | {servers} serveurs"])
        self.rotate_delay = config.get("delay", 10)
        self.saved_status = config.get("status", "online")
        _raw_prefix = config.get("prefix") or os.getenv("PREFIX", "!")
        self.default_prefix = _raw_prefix
        self.sync_mode = config.get("sync_mode", "global")
        
        self.presence_index = 0
        self.presence_loop.start()

    def _load_config(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _save_config(self):
        data = {
            "presences": self.description_list, "delay": self.rotate_delay, 
            "status": self.saved_status, "prefix": self.default_prefix, "sync_mode": self.sync_mode
        }
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def _load_owners(self):
        try:
            if os.path.exists(self.owner_path):
                with open(self.owner_path, 'r') as f:
                    d = json.load(f)
                    return [int(x) for x in d] if isinstance(d, list) else [int(d)]
            return []
        except: return []

    @tasks.loop(seconds=10)
    async def presence_loop(self):
        if not self.description_list: return
        try:
            raw_text = self.description_list[self.presence_index]
            
            # Calculer les utilisateurs uniques (sans les bots) sur tous les serveurs
            unique_users = set()
            for guild in self.bot.guilds:
                for member in guild.members:
                    if not member.bot:
                        unique_users.add(member.id)
            
            unique_user_count = len(unique_users)
            
            # Formatage des nombres avec espaces
            def format_number(n):
                return f"{n:,}".replace(",", " ")
            
            clean_text = raw_text.format(
                servers=format_number(len(self.bot.guilds)), 
                users=format_number(unique_user_count), 
                ping=round(self.bot.latency * 1000), 
                name=self.bot.user.name,
                prefix=self.default_prefix
            )
            status_obj = getattr(discord.Status, self.saved_status, discord.Status.online)
            await self.bot.change_presence(activity=discord.Game(name=clean_text), status=status_obj)
            self.presence_index = (self.presence_index + 1) % len(self.description_list)
        except: pass

    def get_custom_embed(self, inter, title, description):
        user = inter.user if isinstance(inter, discord.Interaction) else inter.author
        guild = inter.guild if hasattr(inter, 'guild') else None
        
        if config_manager:
            embed = config_manager.get_formatted_embed(
                guild=guild, user=user, bot=self.bot,
                title=title, description=description,
                target_id=guild.id if guild else None
            )
        else:
            embed = discord.Embed(title=title, description=description, color=0x2b2d31)
        
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        return embed

    def _get_description_list_text(self):
        return "\n".join([f"`{i+1}` - {p[:45]}..." if len(p) > 45 else f"`{i+1}` - {p}" for i, p in enumerate(self.description_list)]) or "*Aucune*"

    def _main_desc(self):
        fr_status = {"online": "En ligne", "idle": "Absent", "dnd": "Ne pas déranger", "invisible": "Invisible"}
        status_emoji = {"online": "🟢", "idle": "🌙", "dnd": "🔴", "invisible": "⚫"}.get(self.saved_status, "❓")
        return (
            f"**Statut :** {status_emoji} `{fr_status.get(self.saved_status, self.saved_status)}` | **Prefix :** `{self.default_prefix}`\n"
            f"**Mode Sync :** `{self.sync_mode.upper()}` | **Rotation :** `{self.rotate_delay}s` \n\n"
            f"**Descriptions :**\n{self._get_description_list_text()}"
        )

    @commands.hybrid_command(name="panelbot", help="Ouvrir le panneau de configuration du bot.")
    async def panelbot(self, ctx: commands.Context):
        if ctx.author.id not in self._load_owners() and not await self.bot.is_owner(ctx.author):
            return await ctx.send("❌ Accès refusé.")
        
        embed = self.get_custom_embed(ctx, f"Console de {self.bot.user.name}", self._main_desc())
        await ctx.send(embed=embed, view=MainAdminView(self))

# ==============================================================================
# --------------------------- VUES PRINCIPALES ---------------------------------
# ==============================================================================

class MainAdminView(ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        self._add_items()

    def _add_items(self):
        self.clear_items()
        
        # --- LIGNE 0 ---
        btn_sync = ui.Button(label="Sync", style=discord.ButtonStyle.success, emoji="🔄", row=0)
        btn_sync.callback = self.sync_commands
        self.add_item(btn_sync)

        btn_name = ui.Button(label="Nom", style=discord.ButtonStyle.primary, emoji="✏️", row=0)
        btn_name.callback = self.change_name
        self.add_item(btn_name)

        btn_avatar = ui.Button(label="Avatar", style=discord.ButtonStyle.primary, emoji="🖼️", row=0)
        btn_avatar.callback = self.change_avatar
        self.add_item(btn_avatar)

        btn_prefix = ui.Button(label="Prefix", style=discord.ButtonStyle.primary, emoji="⌨️", row=0)
        btn_prefix.callback = self.change_prefix
        self.add_item(btn_prefix)

        # --- LIGNE 1 ---
        btn_guild = ui.Button(label="Synchro Guilde", style=discord.ButtonStyle.secondary, emoji="🏠", row=1)
        btn_guild.callback = self.guild_menu
        self.add_item(btn_guild)

        btn_desc = ui.Button(label="Descriptions", style=discord.ButtonStyle.secondary, emoji="⚙️", row=1)
        btn_desc.callback = self.descriptions
        self.add_item(btn_desc)

        # --- LIGNE 2 (SELECT SYNC) ---
        sync_opts = [
            discord.SelectOption(label="Globale", value="global", emoji="🌐", default=(self.cog.sync_mode == "global")),
            discord.SelectOption(label="Synchro Guilde", value="guild", emoji="🏠", default=(self.cog.sync_mode == "guild"))
        ]
        sel_sync = ui.Select(placeholder="Mode de synchronisation...", options=sync_opts, row=2)
        sel_sync.callback = self.set_sync_mode
        self.add_item(sel_sync)

        # --- LIGNE 3 (SELECT STATUS) ---
        stat_opts = [
            discord.SelectOption(label="En ligne", value="online", emoji="🟢", default=(self.cog.saved_status == "online")),
            discord.SelectOption(label="Absent", value="idle", emoji="🌙", default=(self.cog.saved_status == "idle")),
            discord.SelectOption(label="Ne pas déranger", value="dnd", emoji="🔴", default=(self.cog.saved_status == "dnd")),
            discord.SelectOption(label="Invisible", value="invisible", emoji="⚫", default=(self.cog.saved_status == "invisible"))
        ]
        sel_stat = ui.Select(placeholder="Changer le statut visuel...", options=stat_opts, row=3)
        sel_stat.callback = self.set_status
        self.add_item(sel_stat)

    async def sync_commands(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            if self.cog.sync_mode == "guild":
                ids = load_guild_mod()
                count = 0
                for g_id in ids:
                    guild = self.cog.bot.get_guild(g_id)
                    if guild: 
                        await self.cog.bot.tree.sync(guild=guild)
                        count += 1
                msg = f"✅ Synchro Guilde effectuée sur `{count}/5` serveurs."
            else:
                await self.cog.bot.tree.sync()
                msg = "✅ Synchro Globale effectuée."
            await interaction.followup.send(msg, ephemeral=True)
        except Exception as e: await interaction.followup.send(f"❌ Erreur: {e}", ephemeral=True)

    async def change_name(self, interaction: discord.Interaction):
        await interaction.response.send_modal(NameModal(self.cog))

    async def change_avatar(self, interaction: discord.Interaction):
        self.cog.avatar_waiting_list[interaction.user.id] = interaction
        await interaction.response.send_message("📸 Envoyez l'image.", ephemeral=True)

    async def change_prefix(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PrefixModal(self.cog))

    async def guild_menu(self, interaction: discord.Interaction):
        view = GuildManagerView(self.cog)
        embed = self.cog.get_custom_embed(interaction, "🏠 Synchro Guilde", view.get_list_text())
        await interaction.response.edit_message(embed=embed, view=view)

    async def descriptions(self, interaction: discord.Interaction):
        embed = self.cog.get_custom_embed(interaction, "🎮 Gestion des Descriptions", f"**Liste actuelle :**\n{self.cog._get_description_list_text()}")
        await interaction.response.edit_message(embed=embed, view=DescriptionManagerView(self.cog))

    async def set_sync_mode(self, interaction: discord.Interaction):
        self.cog.sync_mode = interaction.data['values'][0]
        self.cog._save_config()
        self._add_items()
        await interaction.response.edit_message(embed=self.cog.get_custom_embed(interaction, f"Console de {self.cog.bot.user.name}", self.cog._main_desc()), view=self)

    async def set_status(self, interaction: discord.Interaction):
        self.cog.saved_status = interaction.data['values'][0]
        self.cog._save_config()
        status_obj = getattr(discord.Status, self.cog.saved_status)
        await self.cog.bot.change_presence(status=status_obj)
        self._add_items()
        await interaction.response.edit_message(embed=self.cog.get_custom_embed(interaction, f"Console de {self.cog.bot.user.name}", self.cog._main_desc()), view=self)

# ==============================================================================
# --------------------------- GESTION SYNCHRO GUILDE ---------------------------
# ==============================================================================

class GuildManagerView(ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        self._build()

    def get_list_text(self):
        ids = load_guild_mod()
        lines = []
        for g_id in ids:
            guild = self.cog.bot.get_guild(g_id)
            name = f"**{guild.name}**" if guild else "*Serveur Inconnu*"
            lines.append(f"└ {name} (`{g_id}`)")
        return f"**Serveurs autorisés ({len(ids)}/5) :**\n" + ("\n".join(lines) if lines else "*Aucune synchro active*")

    def _build(self):
        self.clear_items()
        ids = load_guild_mod()
        add = ui.Button(label="Ajouter Synchro", style=discord.ButtonStyle.success, emoji="➕", disabled=(len(ids) >= 5))
        add.callback = self.add_callback
        self.add_item(add)
        if ids:
            opts = []
            for g_id in ids:
                guild = self.cog.bot.get_guild(g_id)
                label = f"{guild.name[:20]}..." if guild and len(guild.name) > 20 else (guild.name if guild else str(g_id))
                opts.append(discord.SelectOption(label=label, description=f"ID: {g_id}", value=str(g_id)))
            dele = ui.Select(placeholder="Retirer de la Synchro...", options=opts)
            dele.callback = self.del_callback
            self.add_item(dele)
        back = ui.Button(label="Retour", style=discord.ButtonStyle.danger, emoji="⬅️")
        back.callback = self.back_callback
        self.add_item(back)

    async def add_callback(self, interaction): await interaction.response.send_modal(GuildAddModal(self.cog, self))
    async def back_callback(self, interaction): await interaction.response.edit_message(embed=self.cog.get_custom_embed(interaction, f"Console de {self.cog.bot.user.name}", self.cog._main_desc()), view=MainAdminView(self.cog))
    async def del_callback(self, interaction):
        ids = load_guild_mod()
        target = int(interaction.data['values'][0])
        if target in ids: ids.remove(target)
        save_guild_mod(ids)
        self._build()
        await interaction.response.edit_message(embed=self.cog.get_custom_embed(interaction, "🏠 Synchro Guilde", self.get_list_text()), view=self)

class GuildAddModal(ui.Modal, title="Ajouter Synchro"):
    id_input = ui.TextInput(label="ID du serveur", min_length=15, max_length=20)
    def __init__(self, cog, view): super().__init__(); self.cog, self.view = cog, view
    async def on_submit(self, interaction: discord.Interaction):
        try:
            g_id = int(self.id_input.value.strip())
            ids = load_guild_mod()
            if g_id in ids: return await interaction.response.send_message("ID déjà présent.", ephemeral=True)
            ids.append(g_id); save_guild_mod(ids); self.view._build()
            await interaction.response.edit_message(embed=self.cog.get_custom_embed(interaction, "🏠 Synchro Guilde", self.view.get_list_text()), view=self.view)
        except: await interaction.response.send_message("ID invalide.", ephemeral=True)

# ==============================================================================
# --------------------------- AUTRES MODALS ------------------------------------
# ==============================================================================

class NameModal(ui.Modal, title="Modifier le Nom"):
    name_input = ui.TextInput(label="Nom du Bot", min_length=2, max_length=32)
    def __init__(self, cog): super().__init__(); self.cog = cog; self.name_input.default = self.cog.bot.user.name
    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.bot.user.edit(username=self.name_input.value)
        await interaction.response.edit_message(embed=self.cog.get_custom_embed(interaction, f"Console de {self.cog.bot.user.name}", self.cog._main_desc()))

class PrefixModal(ui.Modal, title="Modifier le Prefix"):
    pref = ui.TextInput(label="Nouveau Prefix", min_length=1, max_length=5)
    def __init__(self, cog): super().__init__(); self.cog = cog; self.pref.default = self.cog.default_prefix
    async def on_submit(self, interaction: discord.Interaction):
        self.cog.default_prefix = self.pref.value; self.cog._save_config()
        await interaction.response.edit_message(embed=self.cog.get_custom_embed(interaction, f"Console de {self.cog.bot.user.name}", self.cog._main_desc()))

class DescriptionManagerView(ui.View):
    def __init__(self, cog): super().__init__(timeout=None); self.cog = cog; self._build()
    def _build(self):
        self.clear_items()
        add = ui.Button(label="Ajouter", style=discord.ButtonStyle.success, emoji="➕"); add.callback = self.add_cb; self.add_item(add)
        if self.cog.description_list:
            opts = [discord.SelectOption(label=f"{i+1}. {p[:50]}...", value=str(i)) for i, p in enumerate(self.cog.description_list)]
            edit = ui.Select(placeholder="Modifier...", options=opts); edit.callback = self.edit_cb; self.add_item(edit)
            dele = ui.Select(placeholder="Supprimer...", options=opts); dele.callback = self.del_cb; self.add_item(dele)
        back = ui.Button(label="Retour", style=discord.ButtonStyle.danger, emoji="⬅️"); back.callback = self.back_cb; self.add_item(back)
    async def add_cb(self, interaction): await interaction.response.send_modal(DescriptionAddModal(self.cog, self))
    async def edit_cb(self, interaction): await interaction.response.send_modal(DescriptionEditModal(self.cog, self, int(interaction.data['values'][0])))
    async def del_cb(self, interaction):
        self.cog.description_list.pop(int(interaction.data['values'][0])); self.cog._save_config(); self._build()
        await interaction.response.edit_message(embed=self.cog.get_custom_embed(interaction, "🎮 Gestion des Descriptions", f"**Liste actuelle :**\n{self.cog._get_description_list_text()}"), view=self)
    async def back_cb(self, interaction): await interaction.response.edit_message(embed=self.cog.get_custom_embed(interaction, f"Console de {self.cog.bot.user.name}", self.cog._main_desc()), view=MainAdminView(self.cog))

class DescriptionAddModal(ui.Modal, title="Ajouter une Description"):
    text = ui.TextInput(label="Texte", max_length=100)
    def __init__(self, cog, view): super().__init__(); self.cog, self.view = cog, view
    async def on_submit(self, interaction: discord.Interaction):
        self.cog.description_list.append(self.text.value); self.cog._save_config(); self.view._build()
        await interaction.response.edit_message(embed=self.cog.get_custom_embed(interaction, "🎮 Gestion des Descriptions", f"**Liste actuelle :**\n{self.cog._get_description_list_text()}"), view=self.view)

class DescriptionEditModal(ui.Modal, title="Modifier Description"):
    text = ui.TextInput(label="Nouveau texte", max_length=100)
    def __init__(self, cog, view, idx): super().__init__(); self.cog, self.view, self.idx = cog, view, idx; self.text.default = self.cog.description_list[idx]
    async def on_submit(self, interaction: discord.Interaction):
        self.cog.description_list[self.idx] = self.text.value; self.cog._save_config(); self.view._build()
        await interaction.response.edit_message(embed=self.cog.get_custom_embed(interaction, "🎮 Gestion des Descriptions", f"**Liste actuelle :**\n{self.cog._get_description_list_text()}"), view=self.view)

async def setup(bot): await bot.add_cog(BotAdmin(bot))