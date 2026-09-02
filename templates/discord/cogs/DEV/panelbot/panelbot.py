import discord
from discord.ext import commands, tasks
from discord import ui
import json
import os
from pathlib import Path

# ==============================================================================
# --------------------------- IMPORTATION UTILS --------------------------------
# ==============================================================================
try:
    from cogs.config_manager.utils import config_manager
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
        json.dump(list(dict.fromkeys([int(x) for x in ids]))[:5], f, indent=2)

# ==============================================================================
# --------------------------- COG PRINCIPAL ------------------------------------
# ==============================================================================

class BotAdmin(commands.Cog):
    def update_delay(self, delay_str: str):
        """Met à jour le délai de rotation à partir d'une chaîne (ex: 30s, 2m, 1h, 1j)."""
        delay_str = delay_str.strip().lower()
        try:
            if delay_str.endswith('j'):
                value = int(delay_str[:-1]) * 86400
            elif delay_str.endswith('h'):
                value = int(delay_str[:-1]) * 3600
            elif delay_str.endswith('m'):
                value = int(delay_str[:-1]) * 60
            elif delay_str.endswith('s'):
                value = int(delay_str[:-1])
            else:
                value = int(delay_str)
            value = max(15, value)  # Discord impose un minimum de 15s
            self.rotate_delay = value
            self.presence_loop.change_interval(seconds=self.rotate_delay)
            self._save_config()
        except Exception as e:
            print(f"[Erreur délai] {e}")

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.avatar_waiting_list = {}
        self.config_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "bot_config.json"))
        
        config = self._load_config()
        self.description_list = config.get("presences", ["Vax 1.4 | {servers} serveurs"])
        
        # Sécurité : L'API Discord limite les changements de présence (5 par minute maximum)
        # On impose un minimum de 15 secondes pour éviter le Rate Limit.
        self.rotate_delay = max(15, config.get("delay", 15))
        self.saved_status = config.get("status", "online")
        self.default_prefix = config.get("prefix", "!")
        self.version = config.get("version", "1.0")
        self.sync_mode = config.get("sync_mode", "global")

        self.presence_index = 0

    async def cog_load(self):
        """Meilleure pratique : Démarrer la tâche au chargement du Cog."""
        self.presence_loop.change_interval(seconds=self.rotate_delay)
        self.presence_loop.start()

    async def cog_unload(self):
        """Stopper la tâche si le Cog est rechargé ou déchargé."""
        self.presence_loop.cancel()

    def _load_config(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _save_config(self):
        data = {
            "presences": self.description_list,
            "delay": self.rotate_delay,
            "status": self.saved_status,
            "prefix": self.default_prefix,
            "sync_mode": self.sync_mode,
            "version": self.version
        }
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def _load_owners(self):
        return []

    async def update_presence_now(self):
        """Fonction dédiée pour mettre à jour la présence sans avancer l'index."""
        if not self.description_list: return
        try:
            raw_text = self.description_list[self.presence_index]
            
            # Optimisation majeure : On utilise le cache natif des utilisateurs uniques
            unique_user_count = len([u for u in self.bot.users if not u.bot])
            
            def format_number(n):
                return f"{n:,}".replace(",", " ")
            
            clean_text = raw_text.format(
                servers=format_number(len(self.bot.guilds)),
                users=format_number(unique_user_count),
                ping=round(self.bot.latency * 1000),
                name=self.bot.user.name,
                prefix=self.default_prefix,
                version=self.version
            )
            
            status_obj = getattr(discord.Status, self.saved_status, discord.Status.online)
            activity = discord.Game(name=clean_text)
            
            # On met à jour l'activité ET le statut simultanément
            await self.bot.change_presence(activity=activity, status=status_obj)
        except Exception as e:
            print(f"[Erreur Présence] {e}")

    @tasks.loop(seconds=15) # Sera écrasé dynamiquement par cog_load
    async def presence_loop(self):
        await self.update_presence_now()
        # On passe à l'index suivant pour le prochain tour
        self.presence_index = (self.presence_index + 1) % len(self.description_list)

    @presence_loop.before_loop
    async def before_presence(self):
        """Attend que le cache du bot soit prêt avant de lancer la boucle."""
        await self.bot.wait_until_ready()

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

    @commands.command(name="panelbot", description="Accéder au panneau de configuration technique du bots.")
    async def panelbot(self, ctx: commands.Context):
        if ctx.author.id not in self._load_owners() and not await self.bot.is_owner(ctx.author):
            return await ctx.send("❌ Accès refusé.", ephemeral=True)
        
        embed = self.get_custom_embed(ctx, f"Console de {self.bot.user.name}", self._main_desc())
        await ctx.send(embed=embed, view=MainAdminView(self))

# ==============================================================================
# --------------------------- VUES PRINCIPALES ---------------------------------
# ==============================================================================

class MainAdminView(ui.View):
    def __init__(self, cog):
        super().__init__(timeout=300) # Ajout du timeout recommandé de 300s
        self.cog = cog
        self._add_items()

    def _add_items(self):
        self.clear_items()

        # --- LIGNE 0 ---
        btn_sync = ui.Button(label="Sync", style=discord.ButtonStyle.success, emoji="🔄", row=0)
        btn_sync.callback = self.sync_commands
        self.add_item(btn_sync)

        btn_global = ui.Button(label="Global", style=discord.ButtonStyle.primary, emoji="🌐", row=0)
        btn_global.callback = self.global_settings
        self.add_item(btn_global)

        btn_desc = ui.Button(label="Descriptions", style=discord.ButtonStyle.secondary, emoji="⚙️", row=0)
        btn_desc.callback = self.descriptions
        self.add_item(btn_desc)

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

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Sécurité globale de la vue."""
        if interaction.user.id not in self.cog._load_owners() and not await self.cog.bot.is_owner(interaction.user):
            await interaction.response.send_message("❌ Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        return True

    async def sync_commands(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            await self.cog.bot.tree.sync()
            await interaction.followup.send("✅ Synchro Globale effectuée.", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur: {e}", ephemeral=True)

    async def global_settings(self, interaction: discord.Interaction):
        await interaction.response.send_modal(GlobalModal(self.cog))

    async def descriptions(self, interaction: discord.Interaction):
        embed = self.cog.get_custom_embed(interaction, "🎮 Gestion des Descriptions", f"**Liste actuelle :**\n{self.cog._get_description_list_text()}")
        await interaction.response.edit_message(embed=embed, view=DescriptionManagerView(self.cog))

    async def set_status(self, interaction: discord.Interaction):
        self.cog.saved_status = interaction.data['values'][0]
        self.cog._save_config()
        
        # Mise à jour immédiate, intelligente et sans redémarrage brutal
        await self.cog.update_presence_now()
        
        self._add_items()
        await interaction.response.edit_message(embed=self.cog.get_custom_embed(interaction, f"Console de {self.cog.bot.user.name}", self.cog._main_desc()), view=self)

# ==============================================================================
# --------------------------- AUTRES MODALS ------------------------------------
# ==============================================================================

class GlobalModal(ui.Modal, title="Paramètres Globaux"):
    name_input = ui.TextInput(label="Nom du Bot", min_length=2, max_length=32)
    version_input = ui.TextInput(label="Version", min_length=1, max_length=16)
    prefix_input = ui.TextInput(label="Préfixe", min_length=1, max_length=5)
    delay_input = ui.TextInput(label="Délai rotation (s/m/h/j)", min_length=1, max_length=8, placeholder="ex: 30s, 2m, 1h", required=True)

    def __init__(self, cog):
        super().__init__()
        self.cog = cog
        self.name_input.default = self.cog.bot.user.name
        self.version_input.default = self.cog.version
        self.prefix_input.default = self.cog.default_prefix
        # Valeur par défaut formatée pour le délai
        delay = self.cog.rotate_delay
        if delay % 86400 == 0:
            self.delay_input.default = f"{delay // 86400}j"
        elif delay % 3600 == 0:
            self.delay_input.default = f"{delay // 3600}h"
        elif delay % 60 == 0:
            self.delay_input.default = f"{delay // 60}m"
        else:
            self.delay_input.default = f"{delay}s"

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.bot.user.edit(username=self.name_input.value)
        self.cog.version = self.version_input.value
        self.cog.default_prefix = self.prefix_input.value
        self.cog.update_delay(self.delay_input.value)
        self.cog._save_config()
        # Synchronise la variable VERSION dans le .env
        # Chemin absolu vers le .env à la racine du projet
        env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', '.env'))
        version_line = f"VERSION={self.version_input.value}"
        try:
            lines = []
            found = False
            if os.path.exists(env_path):
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip().startswith('VERSION='):
                            lines.append(version_line + '\n')
                            found = True
                        else:
                            lines.append(line)
            if not found:
                lines.append(version_line + '\n')
            with open(env_path, 'w', encoding='utf-8') as f:
                f.writelines(lines)
        except Exception as e:
            print(f"[Panelbot] Impossible de mettre à jour VERSION dans .env : {e}")
        await self.cog.update_presence_now()
        await interaction.response.edit_message(embed=self.cog.get_custom_embed(interaction, f"Console de {self.cog.bot.user.name}", self.cog._main_desc()))

class DescriptionManagerView(ui.View):
    def __init__(self, cog): 
        super().__init__(timeout=300)
        self.cog = cog
        self._build()

    def _build(self):
        self.clear_items()
        add = ui.Button(label="Ajouter", style=discord.ButtonStyle.success, emoji="➕")
        add.callback = self.add_cb
        self.add_item(add)
        
        if self.cog.description_list:
            opts = [discord.SelectOption(label=f"{i+1}. {p[:50]}...", value=str(i)) for i, p in enumerate(self.cog.description_list)]
            edit = ui.Select(placeholder="Modifier...", options=opts)
            edit.callback = self.edit_cb
            self.add_item(edit)
            
            dele = ui.Select(placeholder="Supprimer...", options=opts)
            dele.callback = self.del_cb
            self.add_item(dele)
            
        back = ui.Button(label="Retour", style=discord.ButtonStyle.danger, emoji="⬅️")
        back.callback = self.back_cb
        self.add_item(back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in self.cog._load_owners() and not await self.cog.bot.is_owner(interaction.user):
            await interaction.response.send_message("❌ Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        return True

    async def add_cb(self, interaction): await interaction.response.send_modal(DescriptionAddModal(self.cog, self))
    async def edit_cb(self, interaction): await interaction.response.send_modal(DescriptionEditModal(self.cog, self, int(interaction.data['values'][0])))
    
    async def del_cb(self, interaction):
        self.cog.description_list.pop(int(interaction.data['values'][0]))
        self.cog._save_config()
        self._build()
        await interaction.response.edit_message(embed=self.cog.get_custom_embed(interaction, "🎮 Gestion des Descriptions", f"**Liste actuelle :**\n{self.cog._get_description_list_text()}"), view=self)
        
    async def back_cb(self, interaction): 
        await interaction.response.edit_message(embed=self.cog.get_custom_embed(interaction, f"Console de {self.cog.bot.user.name}", self.cog._main_desc()), view=MainAdminView(self.cog))

class DescriptionAddModal(ui.Modal, title="Ajouter une Description"):
    text = ui.TextInput(label="Texte", max_length=100)
    def __init__(self, cog, view): 
        super().__init__()
        self.cog = cog
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        self.cog.description_list.append(self.text.value)
        self.cog._save_config()
        self.view._build()
        await interaction.response.edit_message(embed=self.cog.get_custom_embed(interaction, "🎮 Gestion des Descriptions", f"**Liste actuelle :**\n{self.cog._get_description_list_text()}"), view=self.view)

class DescriptionEditModal(ui.Modal, title="Modifier Description"):
    text = ui.TextInput(label="Nouveau texte", max_length=100)
    def __init__(self, cog, view, idx): 
        super().__init__()
        self.cog = cog
        self.view = view
        self.idx = idx
        self.text.default = self.cog.description_list[idx]

    async def on_submit(self, interaction: discord.Interaction):
        self.cog.description_list[self.idx] = self.text.value
        self.cog._save_config()
        self.view._build()
        await interaction.response.edit_message(embed=self.cog.get_custom_embed(interaction, "🎮 Gestion des Descriptions", f"**Liste actuelle :**\n{self.cog._get_description_list_text()}"), view=self.view)

async def setup(bot): 
    await bot.add_cog(BotAdmin(bot))