import discord
from discord.ext import commands, tasks
from discord import app_commands
from discord import ui
import json
import os
import random
from datetime import datetime
import traceback
from pathlib import Path

# ==============================================================================
# --------------------------- IMPORTATION UTILS --------------------------------
# ==============================================================================
try:
    from cogs.config_manager.utils import config_manager
except ImportError:
    config_manager = None

# ==============================================================================
# --------------------------- GESTION DES DONNÉES ------------------------------
# ==============================================================================
DATA_FILE = Path("data/bonjour_config.json")

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

def get_guild_config(guild_id: int):
    data = load_data()
    guild_id_str = str(guild_id)
    needs_save = False
    
    if guild_id_str not in data:
        data[guild_id_str] = {
            "channel_id": None,
            "time": "08:00",
            "messages": {},
            "shuffled_schedule": [],
            "last_shuffled_month": None,
            "last_sent_date": None
        }
        needs_save = True
        
    if needs_save:
        save_data(data)
        
    return data[guild_id_str]

def update_guild_config(guild_id: int, new_config: dict, reset_sent: bool = False):
    data = load_data()
    if reset_sent:
        new_config["last_sent_date"] = None
    data[str(guild_id)] = new_config
    save_data(data)

# ==============================================================================
# --------------------------- MODALS -------------------------------------------
# ==============================================================================
class TimeModal(ui.Modal, title="⏰ Configuration de l'heure"):
    time_input = ui.TextInput(
        label="Heure d'envoi (Format HH:MM)",
        placeholder="Ex: 08:30, 23:54",
        min_length=5,
        max_length=5,
        style=discord.TextStyle.short,
        required=True
    )

    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view
        self.time_input.default = self.parent_view.config["time"]

    async def on_submit(self, interaction: discord.Interaction):
        time_str = self.time_input.value
        try:
            datetime.strptime(time_str, "%H:%M")
        except ValueError:
            return await interaction.response.send_message("❌ Format invalide. Utilisez bien HH:MM (ex: 08:00 ou 23:54).", ephemeral=True)
        
        self.parent_view.config["time"] = time_str
        update_guild_config(interaction.guild.id, self.parent_view.config, reset_sent=True)
        await self.parent_view.update_ui(interaction)

class MessagesModal(ui.Modal):
    def __init__(self, parent_view, start_idx: int, end_idx: int):
        super().__init__(title=f"📝 Messages (Jours {start_idx} à {end_idx})")
        self.parent_view = parent_view
        self.start_idx = start_idx
        self.end_idx = end_idx

        for i in range(start_idx, end_idx + 1):
            day_str = str(i)
            self.add_item(ui.TextInput(
                label=f"Message {i}",
                style=discord.TextStyle.short,
                placeholder=f"Phrase pour le jour {i}...",
                default=self.parent_view.config["messages"].get(day_str, ""),
                required=False,
                max_length=1000
            ))

    async def on_submit(self, interaction: discord.Interaction):
        for i, child in enumerate(self.children):
            day_str = str(self.start_idx + i)
            self.parent_view.config["messages"][day_str] = child.value
            
        update_guild_config(interaction.guild.id, self.parent_view.config)
        await self.parent_view.update_ui(interaction)

# ==============================================================================
# --------------------------- SELECTEURS ---------------------------------------
# ==============================================================================
class MessageGroupSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Jours 1 à 4", value="1-4", emoji="1️⃣"),
            discord.SelectOption(label="Jours 5 à 8", value="5-8", emoji="2️⃣"),
            discord.SelectOption(label="Jours 9 à 12", value="9-12", emoji="3️⃣"),
            discord.SelectOption(label="Jours 13 à 16", value="13-16", emoji="4️⃣"),
            discord.SelectOption(label="Jours 17 à 20", value="17-20", emoji="5️⃣"),
            discord.SelectOption(label="Jours 21 à 24", value="21-24", emoji="6️⃣"),
            discord.SelectOption(label="Jours 25 à 28", value="25-28", emoji="7️⃣"),
            discord.SelectOption(label="Jours 29 à 31", value="29-31", emoji="8️⃣"),
        ]
        super().__init__(placeholder="✏️ Modifier un groupe de phrases...", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view.ctx.author.id:
            return await interaction.response.send_message("❌ Ce menu ne vous appartient pas.", ephemeral=True)
            
        start, end = map(int, self.values[0].split("-"))
        await interaction.response.send_modal(MessagesModal(self.view, start, end))

class ChannelSelect(ui.ChannelSelect):
    def __init__(self):
        super().__init__(
            placeholder="📢 Choisir le salon d'envoi...",
            channel_types=[discord.ChannelType.text],
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view.ctx.author.id:
            return await interaction.response.send_message("❌ Ce menu ne vous appartient pas.", ephemeral=True)
            
        self.view.config["channel_id"] = self.values[0].id
        update_guild_config(interaction.guild.id, self.view.config, reset_sent=True)
        await self.view.update_ui(interaction)

class TimeSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=f"{str(i).zfill(2)}:00", value=f"{str(i).zfill(2)}:00", emoji="⏰")
            for i in range(24)
        ]
        options.append(
            discord.SelectOption(label="Heure personnalisée...", value="custom", emoji="✏️", description="Saisir une heure précise (ex: 23:54)")
        )
        super().__init__(placeholder="⏰ Choisir l'heure d'envoi...", options=options, row=2)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view.ctx.author.id:
            return await interaction.response.send_message("❌ Ce menu ne vous appartient pas.", ephemeral=True)
            
        selected_value = self.values[0]
        
        if selected_value == "custom":
            await interaction.response.send_modal(TimeModal(self.view))
        else:
            self.view.config["time"] = selected_value
            update_guild_config(interaction.guild.id, self.view.config, reset_sent=True)
            await self.view.update_ui(interaction)

# ==============================================================================
# --------------------------- VUE PRINCIPALE -----------------------------------
# ==============================================================================
class BonjourView(ui.View):
    def __init__(self, ctx, bot):
        super().__init__(timeout=600)
        self.ctx = ctx
        self.bot = bot
        self.config = get_guild_config(ctx.guild.id)
        
        self.add_item(MessageGroupSelect())
        self.add_item(ChannelSelect())
        self.add_item(TimeSelect())

    def get_embed(self) -> discord.Embed:
        channel_mention = f"<#{self.config['channel_id']}>" if self.config['channel_id'] else "`Non défini`"
        time_str = f"`{self.config['time']}`"
        
        msg_list = ""
        for i in range(1, 32):
            content = self.config["messages"].get(str(i), "").strip()
            display_content = content if content else "*Vide*"
            msg_list += f"**{i}.** {display_content}\n"

        title = "🌅 Configuration Bonjour"
        desc = (
            f"> **Salon cible :** {channel_mention}\n"
            f"> **Heure d'envoi :** {time_str}\n"
            f"\n## 📋 Vos façons de dire bonjour\n"
            f"{msg_list}\n"
            f"*Astuce : Le 1er de chaque mois, ces phrases seront mélangées pour une diffusion aléatoire.*"
        )
        
        if len(desc) > 4096:
            desc = desc[:4093] + "..."

        if config_manager:
            embed = config_manager.get_formatted_embed(
                guild=self.ctx.guild, 
                user=self.ctx.author, 
                bot=self.bot,
                title=title, 
                description=desc,
                target_id=self.ctx.guild.id if self.ctx.guild else None
            )
        else:
            embed = discord.Embed(title=title, description=desc, color=0x57F287)
            embed.set_footer(text=f"Configuré par {self.ctx.author.display_name}")
            
        return embed

    async def update_ui(self, interaction: discord.Interaction):
        embed = self.get_embed()
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

# ==============================================================================
# --------------------------- COG & TÂCHE AUTO ---------------------------------
# ==============================================================================
class BonjourCog(commands.Cog):
    """🌅 Module Bonjour — Message quotidien aléatoire."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bonjour_loop.start()

    def cog_unload(self):
        self.bonjour_loop.cancel()

    @commands.hybrid_command(
        name="bonjour",
        description="Configure les messages quotidiens automatiques (jusqu'à 31)."
    )
    @app_commands.default_permissions(manage_guild=True)
    @commands.has_permissions(manage_guild=True)
    async def bonjour_cmd(self, ctx: commands.Context):
        try:
            view = BonjourView(ctx, self.bot)
            embed = view.get_embed()
            await ctx.send(embed=embed, view=view)
        except Exception:
            traceback.print_exc()

    @bonjour_cmd.error
    async def bonjour_cmd_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ Vous n'avez pas la permission de configurer cette commande (nécessite **Gérer le serveur**).", ephemeral=True)
        else:
            raise error

    @tasks.loop(minutes=1)
    async def bonjour_loop(self):
        """Boucle qui vérifie l'heure et gère l'envoi des messages."""
        now = datetime.now()
        current_time = now.strftime("%H:%M")
        current_day = now.day
        current_month = now.month
        today_str = now.strftime("%Y-%m-%d")

        data = load_data()
        needs_save = False

        for guild_id_str, config in data.items():
            if not config.get("channel_id") or config.get("time") != current_time:
                continue
                
            if config.get("last_sent_date") == today_str:
                continue

            if config.get("last_shuffled_month") != current_month:
                valid_messages = [msg for msg in config["messages"].values() if msg.strip()]
                if valid_messages:
                    random.shuffle(valid_messages)
                    while len(valid_messages) < 31:
                        valid_messages.extend(valid_messages)
                    config["shuffled_schedule"] = valid_messages[:31]
                else:
                    config["shuffled_schedule"] = []
                    
                config["last_shuffled_month"] = current_month
                needs_save = True

            schedule = config.get("shuffled_schedule", [])
            if schedule:
                message_to_send = schedule[current_day - 1]
                
                channel = self.bot.get_channel(config["channel_id"])
                if channel:
                    try:
                        await channel.send(f"*{message_to_send}*")
                        config["last_sent_date"] = today_str
                        needs_save = True
                    except discord.Forbidden:
                        print(f"[Bonjour] Permissions manquantes dans le salon {channel.id}")
                    except Exception as e:
                        print(f"[Bonjour] Erreur d'envoi : {e}")

        if needs_save:
            save_data(data)

    @bonjour_loop.before_loop
    async def before_bonjour_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(BonjourCog(bot))