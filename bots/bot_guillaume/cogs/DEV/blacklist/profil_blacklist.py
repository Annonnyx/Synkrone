import json
from pathlib import Path
import discord
from discord import app_commands, ui
from discord.ext import commands, tasks

# ==============================================================================
# --------------------------- IMPORTATION UTILS --------------------------------
# ==============================================================================
try:
    from cogs.config_manager.utils import config_manager
except ImportError:
    config_manager = None

CREATOR_ID = 1366780122891419784
OWNER_JSON = Path(__file__).parent.parent / "owner" / "owner.json"
BLACKLIST_JSON = Path(__file__).parent / "blacklist.json"

# --- PERSISTANCE ---

def load_blacklist() -> dict:
    if not BLACKLIST_JSON.exists():
        return {"users": [], "servers": []}
    try:
        with BLACKLIST_JSON.open("r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"users": [], "servers": []}

def save_blacklist(data: dict):
    with BLACKLIST_JSON.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_owner_ids() -> list[int]:
    try:
        if OWNER_JSON.exists():
            with OWNER_JSON.open("r", encoding="utf-8") as f:
                return [int(x) for x in json.load(f)]
    except: pass
    return []

# --- LOGIQUE D'AFFICHAGE ---

async def get_blacklist_list_data(bot: commands.Bot):
    data = load_blacklist()
    users = data.get("users", [])
    servers = data.get("servers", [])
    
    lines = [
        f"🛡️ **Système de Sécurité**",
        f"└ Statut : Opérationnel\n",
        f"👤 **Utilisateurs Blacklistés ({len(users)})**"
    ]
    
    if not users:
        lines.append("└ *Aucun utilisateur banni*")
    else:
        for u in users:
            lines.append(f"└ • {u.get('name', 'Inconnu')} - `{u.get('id')}`")
    
    lines.append(f"\n🏠 **Serveurs Blacklistés ({len(servers)})**")
    
    if not servers:
        lines.append("└ *Aucun serveur banni*")
    else:
        for s in servers:
            lines.append(f"└ • {s.get('name', 'Inconnu')} - `{s.get('id')}`")
    
    return "\n".join(lines)

# --- MODAL DE GESTION ---

class BlacklistModal(ui.Modal):
    def __init__(self, action: str):
        super().__init__(title=f"Blacklist : {action}")
        self.action = action
        self.target_id = ui.TextInput(label="ID de l'utilisateur ou du serveur", placeholder="Entrez l'ID numérique...", required=True)
        self.add_item(self.target_id)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            tid = int(self.target_id.value.strip())
        except:
            return await interaction.response.send_message("❌ ID invalide.", ephemeral=True)

        data = load_blacklist()
        
        if self.action == "Ajouter":
            if tid == CREATOR_ID:
                return await interaction.response.send_message("❌ Impossible de bannir le Créateur.", ephemeral=True)
            
            # Détection automatique du type (User ou Guild)
            name, key = "Inconnu", "users"
            try:
                user = await interaction.client.fetch_user(tid)
                name, key = str(user), "users"
            except:
                try:
                    guild = await interaction.client.fetch_guild(tid)
                    name, key = guild.name, "servers"
                except: pass

            if not any(e['id'] == tid for e in data[key]):
                data[key].append({"id": tid, "name": name})
                save_blacklist(data)
                # Expulsion immédiate si le bot est sur le serveur ou si c'est l'owner du serv
                for g in interaction.client.guilds:
                    if g.id == tid or g.owner_id == tid:
                        await g.leave()
            else:
                return await interaction.response.send_message("ℹ️ Cet ID est déjà dans la liste.", ephemeral=True)
        
        else: # Retirer
            data["users"] = [e for e in data["users"] if e['id'] != tid]
            data["servers"] = [e for e in data["servers"] if e['id'] != tid]
            save_blacklist(data)

        await interaction.response.defer(ephemeral=True)
        cog = interaction.client.get_cog("BlacklistAdminCog")
        if cog: await cog.update_message(interaction)

# --- VIEW AVEC BOUTONS ---

class BlacklistView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(label="Ajouter", emoji="➕", style=discord.ButtonStyle.danger, custom_id="bl_add")
    async def add_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(BlacklistModal("Ajouter"))

    @ui.button(label="Retirer", emoji="♻️", style=discord.ButtonStyle.green, custom_id="bl_rem")
    async def rem_btn(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(BlacklistModal("Retirer"))

# --- COG PRINCIPAL ---

class BlacklistAdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.auto_clean.start()

    def cog_unload(self):
        self.auto_clean.cancel()

    @tasks.loop(minutes=10)
    async def auto_clean(self):
        """Nettoyage automatique cyclique."""
        data = load_blacklist()
        b_users = [int(u['id']) for u in data.get("users", [])]
        b_servs = [int(s['id']) for s in data.get("servers", [])]
        for g in self.bot.guilds:
            if g.id in b_servs or g.owner_id in b_users:
                await g.leave()

    async def update_message(self, interaction: discord.Interaction):
        title = f"🚫 Liste Noire de {self.bot.user.name}"
        text = await get_blacklist_list_data(self.bot)
        
        if config_manager:
            embed = config_manager.get_formatted_embed(
                guild=interaction.guild, user=interaction.user, bot=self.bot,
                title=title, description=text, target_id=interaction.guild.id if interaction.guild else None
            )
        else:
            embed = discord.Embed(title=title, description=text, color=0x2b2d31)

        async for msg in interaction.channel.history(limit=10):
            if msg.author == self.bot.user and msg.embeds and title in (msg.embeds[0].title or ""):
                await msg.edit(embed=embed, view=BlacklistView())
                break

    @commands.hybrid_command(name="blacklist", help="Gérer la sécurité de Vax Développeur.")
    async def blacklist(self, ctx: commands.Context):
        owners = load_owner_ids()
        if ctx.author.id != CREATOR_ID and ctx.author.id not in owners:
            return await ctx.send("❌ Accès restreint.", ephemeral=True)

        title = f"🚫 Liste Noire de {self.bot.user.name}"
        text = await get_blacklist_list_data(self.bot)

        if config_manager:
            embed = config_manager.get_formatted_embed(
                guild=ctx.guild, user=ctx.author, bot=self.bot,
                title=title, description=text, target_id=ctx.guild.id if ctx.guild else None
            )
        else:
            embed = discord.Embed(title=title, description=text, color=0x2b2d31)

        await ctx.send(embed=embed, view=BlacklistView())

async def setup(bot: commands.Bot):
    if bot.get_command("blacklist"): bot.remove_command("blacklist")
    await bot.add_cog(BlacklistAdminCog(bot))