import discord
from discord import ui, app_commands
from discord.ext import commands, tasks
import traceback

# ==============================================================================
# --- IMPORTS MÉTIER VAX ---
# ==============================================================================
try:
    from utils.config_data import DataManager
    from utils.config_theme import config_manager
    from utils.config_perm import ensure_command_permission, perm_command
    from utils.config_emoji import Emoji as E
    HAS_VAX_CORE = True
except ImportError as e:
    HAS_VAX_CORE = False
    print(f"\033[91m[ERREUR CRITIQUE] Impossible d'importer le noyau Vax : {e}\033[0m")

# ==============================================================================
# --- CONFIGURATION GLOBALE & DÉBOGAGE ---
# ==============================================================================
DEBUG_LOGS = True
ERROR_LOGS_ONLY = False

# ==============================================================================
# --- CENTRALISATION DES EMOJIS ---
# ==============================================================================
E_ON = getattr(E, 'VALIDER', "ðŸŸ¢") if HAS_VAX_CORE else "ðŸŸ¢"
E_OFF = getattr(E, 'REFUSER', "ðŸ”´") if HAS_VAX_CORE else "ðŸ”´"
E_WARN = getattr(E, 'ATTENTION', "âš ï¸") if HAS_VAX_CORE else "âš ï¸"
E_GEAR = getattr(E, 'MODIFIER', "âš™ï¸") if HAS_VAX_CORE else "âš™ï¸"
E_ADD = getattr(E, 'AJOUTER', "âž•") if HAS_VAX_CORE else "âž•"
E_TRASH = getattr(E, 'SUPPRIMER', "ðŸ—‘ï¸") if HAS_VAX_CORE else "ðŸ—‘ï¸"
E_UP = getattr(E, 'HAUSSE', "ðŸ“ˆ") if HAS_VAX_CORE else "ðŸ“ˆ"
E_ROLE = getattr(E, 'ROLE', "ðŸŽ­") if HAS_VAX_CORE else "ðŸŽ­"
E_MSG = "ðŸ’¬"

# ==============================================================================
# --- UTILITAIRES DE LOGS ---
# ==============================================================================
def log_sys(action: str, message: str, is_error: bool = False):
    if ERROR_LOGS_ONLY and not is_error: return
    if not DEBUG_LOGS and not is_error: return
    color = "\033[91m" if is_error else "\033[96m"
    prefix = "[ERREUR Leveling]" if is_error else "[INFO Leveling]"
    print(f"{color}{prefix} [{action}] {message}\033[0m")

def get_xp_requirement(level: int) -> int:
    return 5 * (level ** 2) + (50 * level) + 100

# ==============================================================================
# --- GESTIONNAIRE DE DONNÉES (DataManager) ---
# ==============================================================================
class LevelManager:
    def __init__(self):
        if HAS_VAX_CORE:
            self.data = DataManager("public/statistiques/leveling")
        else:
            log_sys("INIT", "DataManager introuvable. Échec système.", is_error=True)

    def get_default_config(self):
        return {
            "config": {"enabled": False, "xp_per_msg": 15, "xp_per_min_voice": 10, "levelup_channel": None, "levelup_msg": "ðŸŽ‰ Félicitations {user.mention}, tu passes au niveau **{level}** !"},
            "rewards": [],
            "users": {}
        }

    def load(self, guild_id: int) -> dict:
        try:
            raw = self.data.load(guild_id) or {}
            default = self.get_default_config()
            for k, v in default.items():
                if k not in raw: raw[k] = v
            for k, v in default["config"].items():
                if k not in raw["config"]: raw["config"][k] = v
            return raw
        except Exception as e:
            log_sys("DB_LOAD", f"Erreur de lecture DB pour {guild_id}: {e}", is_error=True)
            return self.get_default_config()

    def save(self, guild_id: int, config: dict):
        self.data.save(guild_id, config)

lvl_db = LevelManager()

# ==============================================================================
# --- MODALS D'ADMINISTRATION ---
# ==============================================================================
class ConfigRatesModal(ui.Modal, title="âš™ï¸ Ratios d'Expérience"):
    def __init__(self, view: "LvlAdminLayoutView"):
        super().__init__()
        self.view = view
        conf = lvl_db.load(view.guild.id)["config"]
        self.t = ui.TextInput(label="XP par Message", default=str(conf.get("xp_per_msg", 15)), max_length=4, required=True)
        self.v = ui.TextInput(label="XP par Minute en Vocal", default=str(conf.get("xp_per_min_voice", 10)), max_length=4, required=True)
        self.add_item(self.t); self.add_item(self.v)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            data = lvl_db.load(self.view.guild.id)
            data["config"]["xp_per_msg"] = max(0, int(self.t.value))
            data["config"]["xp_per_min_voice"] = max(0, int(self.v.value))
            lvl_db.save(self.view.guild.id, data)
            self.view.status_message = f"{E_ON} Ratios d'XP mis à jour."
            await self.view._refresh(interaction)
        except ValueError:
            if not interaction.response.is_done(): await interaction.response.defer()
            await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, valeurs numériques invalides.", delete_after=6)

class ConfigAlertModal(ui.Modal, title="ðŸ“¢ Alertes de Niveau"):
    def __init__(self, view: "LvlAdminLayoutView"):
        super().__init__()
        self.view = view
        conf = lvl_db.load(view.guild.id)["config"]
        self.c = ui.TextInput(label="ID du Salon (Vide = Salon du message)", default=str(conf.get("levelup_channel") or ""), max_length=20, required=False)
        self.m = ui.TextInput(label="Message de Level UP", default=conf.get("levelup_msg", ""), style=discord.TextStyle.paragraph, max_length=500, required=True)
        self.add_item(self.c); self.add_item(self.m)

    async def on_submit(self, interaction: discord.Interaction):
        data = lvl_db.load(self.view.guild.id)
        raw_c = self.c.value.strip()
        if raw_c and not raw_c.isdigit():
            if not interaction.response.is_done(): await interaction.response.defer()
            return await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, l'ID du salon est invalide.", delete_after=6)
        data["config"]["levelup_channel"] = int(raw_c) if raw_c else None
        data["config"]["levelup_msg"] = self.m.value.strip()
        lvl_db.save(self.view.guild.id, data)
        self.view.status_message = f"{E_ON} Configuration des alertes mise à  jour."
        await self.view._refresh(interaction)

class RewardAddModal(ui.Modal, title="âž• Palier de Rôle"):
    lvl = ui.TextInput(label="Niveau requis", placeholder="Ex: 10", required=True, max_length=3)
    rid = ui.TextInput(label="ID du Rôle", placeholder="Ex: 123456789012345678", required=True, max_length=20)
    
    def __init__(self, view: "LvlAdminLayoutView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        if not self.lvl.value.isdigit() or not self.rid.value.isdigit():
            if not interaction.response.is_done(): await interaction.response.defer()
            return await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, données invalides.", delete_after=6)
        data = lvl_db.load(self.view.guild.id)
        l_req, r_id = int(self.lvl.value), int(self.rid.value)
        data["rewards"] = [r for r in data["rewards"] if r["level"] != l_req]
        data["rewards"].append({"level": l_req, "role_id": r_id})
        data["rewards"].sort(key=lambda x: x["level"])
        lvl_db.save(self.view.guild.id, data)
        self.view.status_message = f"{E_ON} Récompense ajoutée pour le niveau `{l_req}`."
        await self.view._refresh(interaction)

# ==============================================================================
# --- INTERFACE UTILISATEUR (Layout V2) ---
# ==============================================================================
class LvlAdminLayoutView(ui.LayoutView):
    def __init__(self, cog: "LevelCog", guild: discord.Guild, user: discord.Member):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild = guild
        self.user = user
        self.status_message = ""
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            if not interaction.response.is_done(): await interaction.response.defer()
            await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, ce menu est verrouillé.", delete_after=6)
            return False
        return True

    def _build(self):
        self.clear_items()
        data = lvl_db.load(self.guild.id)
        conf = data["config"]
        
        accent_color = 0x3498db
        footer_text = ""
        if HAS_VAX_CORE and config_manager:
            try:
                theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.cog.bot)
                accent_color = int(theme.get("color", 0x3498db))
                footer_text = theme.get("footer_text", "")
            except: pass

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {E_UP} Ingénierie Leveling"))
        
        if self.status_message:
            container.add_item(ui.TextDisplay(f"> {self.status_message}"))
            self.status_message = ""

        state_txt = f"{E_ON} `Activé`" if conf["enabled"] else f"{E_OFF} `Désactivé`"
        chan_txt = f"<#{conf['levelup_channel']}>" if conf.get("levelup_channel") else "`Salon actuel`"
        
        desc = (
            f"**État du module :** {state_txt}\n\n"
            f"**Ratios actuels :**\n"
            f"- XP par Message : `{conf['xp_per_msg']}`\n"
            f"- XP par Minute Vocal : `{conf['xp_per_min_voice']}`\n\n"
            f"**Alertes Level-UP :**\n"
            f"- Salon ciblé : {chan_txt}\n"
            f"- Message : `{conf['levelup_msg']}`\n\n"
            f"### {E_ROLE} Paliers de Rôles\n"
        )

        rewards = data.get("rewards", [])
        if not rewards:
            desc += "> *Aucune récompense configurée.*"
        else:
            for r in rewards:
                role = self.guild.get_role(r['role_id'])
                role_txt = role.mention if role else f"`ID: {r['role_id']}`"
                desc += f"ðŸ”¸ **Niveau {r['level']}** âž” {role_txt}\n"
                
        container.add_item(ui.TextDisplay(desc))

        row1 = ui.ActionRow()
        btn_toggle = ui.Button(label="Désactiver" if conf["enabled"] else "Activer", style=discord.ButtonStyle.danger if conf["enabled"] else discord.ButtonStyle.success, emoji=E_OFF if conf["enabled"] else E_ON)
        async def tgl_cb(i):
            if not i.response.is_done(): await i.response.defer()
            d = lvl_db.load(self.guild.id)
            d["config"]["enabled"] = not d["config"]["enabled"]
            lvl_db.save(self.guild.id, d)
            self.status_message = f"{E_ON} Module {'activé' if d['config']['enabled'] else 'désactivé'}."
            await self._refresh(i)
        btn_toggle.callback = tgl_cb
        row1.add_item(btn_toggle)

        btn_rates = ui.Button(label="Ratios XP", style=discord.ButtonStyle.primary, emoji=E_UP)
        btn_rates.callback = lambda i: i.response.send_modal(ConfigRatesModal(self))
        row1.add_item(btn_rates)
        
        btn_alert = ui.Button(label="Alertes", style=discord.ButtonStyle.primary, emoji=E_MSG)
        btn_alert.callback = lambda i: i.response.send_modal(ConfigAlertModal(self))
        row1.add_item(btn_alert)
        container.add_item(row1)

        row2 = ui.ActionRow()
        b_add = ui.Button(label="Ajouter Rôle", style=discord.ButtonStyle.success, emoji=E_ADD)
        b_add.callback = lambda i: i.response.send_modal(RewardAddModal(self))
        row2.add_item(b_add)
        
        if rewards:
            opts = [discord.SelectOption(label=f"Supprimer Palier Niv. {r['level']}", value=str(r['level']), emoji=E_TRASH) for r in rewards[:25]]
            sel = ui.Select(placeholder="Sélectionner un palier à supprimer...", options=opts)
            async def del_cb(interaction):
                if not interaction.response.is_done(): await interaction.response.defer()
                lvl_target = int(interaction.data['values'][0])
                d = lvl_db.load(self.guild.id)
                d["rewards"] = [r for r in d["rewards"] if r["level"] != lvl_target]
                lvl_db.save(self.guild.id, d)
                self.status_message = f"{E_TRASH} Palier de niveau {lvl_target} supprimé."
                await self._refresh(interaction)
            sel.callback = del_cb
            row2.add_item(sel)

        container.add_item(row2)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    async def _refresh(self, interaction: discord.Interaction):
        self._build()
        if interaction.response.is_done():
            await interaction.edit_original_response(view=self)
        else:
            await interaction.response.edit_message(view=self)

# ==============================================================================
# --- COG PRINCIPAL (Moteur d'Expérience) ---
# ==============================================================================
class LevelCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log_sys("INIT", "Module Leveling V3 déployé.")
        self.vocal_xp_task.start()

    def cog_unload(self):
        self.vocal_xp_task.cancel()

    async def add_xp(self, guild: discord.Guild, member: discord.Member, amount: int):
        data = lvl_db.load(guild.id)
        if not data["config"]["enabled"]: return

        u_id = str(member.id)
        user_data = data["users"].setdefault(u_id, {"xp": 0, "level": 1})
        
        old_level = user_data["level"]
        user_data["xp"] += amount

        while user_data["xp"] >= get_xp_requirement(user_data["level"]):
            user_data["level"] += 1

        new_level = user_data["level"]
        lvl_db.save(guild.id, data)

        if new_level > old_level:
            await self.handle_level_up(guild, member, new_level, data)

    async def handle_level_up(self, guild: discord.Guild, member: discord.Member, new_level: int, data: dict):
        conf = data["config"]
        chan_id = conf.get("levelup_channel")
        channel = guild.get_channel(chan_id) if chan_id else None
        
        msg_raw = conf.get("levelup_msg", "ðŸŽ‰ {user.mention} passe niveau **{level}** !")
        msg = msg_raw.replace("{user.mention}", member.mention).replace("{user}", member.name).replace("{level}", str(new_level))
        
        if channel:
            try: await channel.send(msg)
            except: pass
        else:
            if guild.system_channel:
                try: await guild.system_channel.send(msg)
                except: pass

        roles_to_add = []
        for reward in data.get("rewards", []):
            if new_level >= reward["level"]:
                role = guild.get_role(reward["role_id"])
                if role and role not in member.roles:
                    roles_to_add.append(role)
        
        if roles_to_add:
            try:
                await member.add_roles(*roles_to_add, reason=f"Level UP ({new_level})")
            except discord.Forbidden:
                log_sys("ROLE_ERR", f"Permissions insuffisantes pour ajouter des rôles à {member.name}.", is_error=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild: return
        data = lvl_db.load(message.guild.id)
        if not data["config"]["enabled"]: return
        
        xp_gain = data["config"].get("xp_per_msg", 15)
        if xp_gain > 0:
            await self.add_xp(message.guild, message.author, xp_gain)

    @tasks.loop(minutes=1.0)
    async def vocal_xp_task(self):
        for guild in self.bot.guilds:
            data = lvl_db.load(guild.id)
            if not data["config"]["enabled"]: continue
            
            xp_per_min = data["config"].get("xp_per_min_voice", 10)
            if xp_per_min <= 0: continue

            afk_channel = guild.afk_channel
            for channel in guild.voice_channels:
                if afk_channel and channel == afk_channel: continue
                for member in channel.members:
                    if member.bot: continue
                    if member.voice and (member.voice.deaf or member.voice.self_deaf): continue
                    await self.add_xp(guild, member, xp_per_min)

    @vocal_xp_task.before_loop
    async def before_vocal_task(self):
        await self.bot.wait_until_ready()

    @perm_command(level=2) # Verrouillage Vax
    @commands.hybrid_command(name="lvl", description="Administration du système d'expérience.")
    async def lvl_cmd(self, ctx: commands.Context):
        try:
            if not ctx.guild:
                return await ctx.send(f"{E_OFF} Serveur uniquement.")

            if HAS_VAX_CORE and not await ensure_command_permission(ctx, command_name="lvl"):
                return

            if getattr(ctx, "interaction", None) is not None and not ctx.interaction.response.is_done():
                await ctx.defer(ephemeral=False)

            view = LvlAdminLayoutView(self, ctx.guild, ctx.author)
            await ctx.send(view=view)
        except Exception as e:
            log_sys("CMD_ERR", f"Erreur commande lvl: {e}", is_error=True)
            try:
                await ctx.send(f"{E_OFF} Une erreur est survenue pendant l'ouverture du panneau leveling.")
            except Exception:
                pass

async def setup(bot: commands.Bot):
    if bot.get_cog("LevelCog"):
        log_sys("INIT", "LevelCog déjà chargé, chargement ignoré.")
        return
    if bot.get_command("lvl"): bot.remove_command("lvl")
    await bot.add_cog(LevelCog(bot))
