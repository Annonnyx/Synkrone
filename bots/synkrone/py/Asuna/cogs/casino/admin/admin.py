import discord
from discord.ext import commands
from discord import ui
import os
import json
import time
from datetime import datetime, timedelta

# ===================== CONFIG MANAGER ========================
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# --- UTILITAIRES ---
def format_v(value: int) -> str:
    return f"{value:,}".replace(',', ' ')

def load_admin_data(guild_id: int, user_id: int):
    path = os.path.join('cogs', 'casino', 'data', str(guild_id), f"{user_id}.json")
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return None

def save_admin_data(guild_id: int, user_id: int, data: dict):
    path = os.path.join('cogs', 'casino', 'data', str(guild_id), f"{user_id}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)

# --- MODAL ÉCONOMIE ---
class AdminEcoModal(ui.Modal):
    def __init__(self, title, key, user_id, guild_id, parent_view):
        super().__init__(title=title)
        self.key, self.user_id, self.guild_id = key, user_id, guild_id
        self.parent_view = parent_view
        self.input = ui.TextInput(
            label="Modification (ex: +5000 ou -2000)", 
            placeholder="Utilisez + pour ajouter ou - pour retirer",
            required=True
        )
        self.add_item(self.input)

    async def on_submit(self, interaction: discord.Interaction):
        data = load_admin_data(self.guild_id, self.user_id)
        val_str = self.input.value.replace(" ", "") # Nettoie les espaces
        
        try:
            current_val = int(data.get(self.key, 0))
            if val_str.startswith('+'):
                data[self.key] = current_val + int(val_str[1:])
            elif val_str.startswith('-'):
                data[self.key] = max(0, current_val - int(val_str[1:]))
            else:
                data[self.key] = int(val_str) # Définit la valeur brute si pas de signe

            save_admin_data(self.guild_id, self.user_id, data)
            self.parent_view.data = data
            await self.parent_view.refresh(interaction)
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur : Format invalide ({e})", ephemeral=True)

# --- PANNEAU ADMIN ---
class AdminPanelView(ui.View):
    def __init__(self, bot, member, data):
        super().__init__(timeout=300)
        self.bot, self.member, self.data = bot, member, data

    def get_times(self):
        now = datetime.now().astimezone()
        
        # Daily
        ld = self.data.get("last_daily")
        d_ready, d_str = True, "✅ Prêt"
        if ld:
            try:
                diff = now - datetime.fromisoformat(ld)
                if diff.total_seconds() < 86400:
                    d_ready = False
                    rem = 86400 - diff.total_seconds()
                    d_str = f"⏳ {int(rem//3600)}h {int((rem%3600)//60)}m"
            except: pass

        # Lantern
        ll = self.data.get("last_lantern_ts", 0)
        l_ready, l_str = True, "✅ Prêt"
        if time.time() - ll < 10800:
            l_ready = False
            rem = 10800 - (time.time() - ll)
            l_str = f"⏳ {int(rem//3600)}h {int((rem%3600)//60)}m"

        return d_ready, d_str, l_ready, l_str

    async def refresh(self, interaction: discord.Interaction):
        embed = await self.generate_embed()
        new_view = AdminPanelView(self.bot, self.member, self.data)
        new_view.update_options()
        await interaction.response.edit_message(embed=embed, view=new_view)

    async def generate_embed(self):
        _, d_str, _, l_str = self.get_times()
        embed = self.bot.config.get_formatted_embed(
            title=f"🛠 ADMIN : {self.member.display_name}",
            description=f"Cols : **{format_v(self.data.get('Cols', 0))}**\nHonneur : **{format_v(self.data.get('honneur', 0))}**",
            bot_user=self.bot.user,
            guild=self.member.guild if hasattr(self.member, 'guild') else None,
            user=self.member,
            target_id=self.member.guild.id if hasattr(self.member, 'guild') else None
        )
        embed.add_field(name="🎁 Daily", value=f"`{d_str}`", inline=True)
        embed.add_field(name="🏮 Lantern", value=f"`{l_str}`", inline=True)
        return embed

    def update_options(self):
        d_ready, _, l_ready, _ = self.get_times()
        options = [
            discord.SelectOption(label="Modifier Cols", value="edit_Cols", emoji="💴"),
            discord.SelectOption(label="Modifier Honneur", value="edit_hon", emoji="🎖️"),
            discord.SelectOption(
                label="Bloquer Daily (24h)" if d_ready else "Réinitialiser Daily (Prêt)", 
                value="daily_action", emoji="🎁"
            ),
            discord.SelectOption(
                label="Bloquer Lantern (3h)" if l_ready else "Réinitialiser Lantern (Prêt)", 
                value="lantern_action", emoji="🏮"
            )
        ]
        self.select_admin.options = options

    @ui.select(placeholder="⚙️ Actions d'administration...")
    async def select_admin(self, interaction: discord.Interaction, select: ui.Select):
        choice = select.values[0]
        gid, uid = interaction.guild.id, self.member.id
        d_ready, _, l_ready, _ = self.get_times()

        if choice == "edit_Cols":
            await interaction.response.send_modal(AdminEcoModal("Éditer Cols", "Cols", uid, gid, self))
        elif choice == "edit_hon":
            await interaction.response.send_modal(AdminEcoModal("Éditer Honneur", "honneur", uid, gid, self))
        
        elif choice == "daily_action":
            if d_ready: # Bloquer
                self.data["last_daily"] = datetime.now().astimezone().isoformat()
            else: # Réinitialiser
                self.data["last_daily"] = None
            save_admin_data(gid, uid, self.data)
            await self.refresh(interaction)

        elif choice == "lantern_action":
            if l_ready: # Bloquer
                self.data["last_lantern_ts"] = time.time()
            else: # Réinitialiser
                self.data["last_lantern_ts"] = 0
            save_admin_data(gid, uid, self.data)
            await self.refresh(interaction)

class AdminCommand(commands.Cog):
    def __init__(self, bot): self.bot = bot

    @commands.hybrid_command(name="admin")
    @commands.has_permissions(administrator=True)
    async def admin_panel(self, ctx, target: discord.User):
        data = load_admin_data(ctx.guild.id, target.id)
        if not data: return await ctx.send("❌ Données introuvables.")
        
        view = AdminPanelView(self.bot, target, data)
        view.update_options()
        await ctx.send(embed=await view.generate_embed(), view=view)

async def setup(bot):
    await bot.add_cog(AdminCommand(bot))