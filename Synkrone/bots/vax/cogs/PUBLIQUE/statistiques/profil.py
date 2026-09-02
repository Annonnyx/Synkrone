import discord
from discord import ui, app_commands
from discord.ext import commands
import time

try:
    from utils.config_data import DataManager
    from utils.config_theme import config_manager
    from utils.config_emoji import Emoji as E
    HAS_VAX_CORE = True
except ImportError:
    HAS_VAX_CORE = False

E_OFF = getattr(E, 'REFUSER', "ðŸ”´") if HAS_VAX_CORE else "ðŸ”´"
E_USER = getattr(E, 'PROFIL', "ðŸ‘¤") if HAS_VAX_CORE else "ðŸ‘¤"
E_CROWN = getattr(E, 'CLASSEMENT', "ðŸ†") if HAS_VAX_CORE else "ðŸ†"
E_UP = getattr(E, 'HAUSSE', "ðŸ“ˆ") if HAS_VAX_CORE else "ðŸ“ˆ"
E_STAR = getattr(E, 'ETOILE', "â­") if HAS_VAX_CORE else "â­"
E_MSG = "ðŸ’¬"
E_MIC = "ðŸŽ¤"
E_WARN = getattr(E, 'ATTENTION', "âš ï¸") if HAS_VAX_CORE else "âš ï¸"

lvl_db = DataManager("public/statistiques/leveling") if HAS_VAX_CORE else None
stats_db = DataManager("public/statistiques") if HAS_VAX_CORE else None

def get_progress_bar(current_xp: int, required_xp: int, length: int = 15) -> str:
    percent = min(1.0, current_xp / required_xp) if required_xp > 0 else 1.0
    filled = int(length * percent)
    empty = length - filled
    return f"[{'â–ˆ' * filled}{'.' * empty}] {int(percent * 100)}%"

def get_xp_requirement(level: int) -> int:
    return 5 * (level ** 2) + (50 * level) + 100

def format_time(seconds: int) -> str:
    h, r = divmod(int(seconds), 3600)
    m, s = divmod(r, 60)
    if h > 0: return f"{h}h {m}m"
    if m > 0: return f"{m}m {s}s"
    return f"{s}s"

class ProfileLayoutView(ui.LayoutView):
    def __init__(self, bot: commands.Bot, guild: discord.Guild, target: discord.Member):
        super().__init__(timeout=600)
        self.bot = bot
        self.guild = guild
        self.target = target
        self._build()

    def _build(self):
        self.clear_items()
        
        l_data = lvl_db.load(self.guild.id) if lvl_db else {}
        s_data = stats_db.load(self.guild.id) if stats_db else {}
        
        uid = str(self.target.id)
        u_lvl = l_data.get("users", {}).get(uid, {"xp": 0, "level": 1})
        u_stat = s_data.get("users", {}).get(uid, {"messages": 0, "vocal": 0, "mutes": 0, "deafs": 0})
        
        lvl = u_lvl.get("level", 1)
        xp = u_lvl.get("xp", 0)
        
        base_xp = get_xp_requirement(lvl - 1) if lvl > 1 else 0
        target_xp = get_xp_requirement(lvl)
        p_bar = get_progress_bar(xp - base_xp, target_xp - base_xp)
        
        # Récupération temps vocal en direct depuis stats_cog
        vocal_time = u_stat.get("vocal", 0)
        stats_cog = self.bot.get_cog("StatsCog")
        if stats_cog and self.target.id in stats_cog.voice_tracking:
            vocal_time += int(time.time() - stats_cog.voice_tracking[self.target.id])

        accent_color = 0x3498db
        footer_text = ""
        if HAS_VAX_CORE and config_manager:
            try:
                theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.target, self.bot)
                accent_color = int(theme.get("color", 0x3498db))
                footer_text = theme.get("footer_text", "")
            except: pass

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        
        desc = (
            f"### {E_USER} Profil de {self.target.display_name}\n\n"
            f"**{E_UP} Niveau :** `{lvl}`\n"
            f"**{E_STAR} Expérience :** `{xp} XP`\n"
            f"`{p_bar}` *(Progression)*\n\n"
            f"**ðŸ“Š Statistiques Globales**\n"
            f"- {E_MSG} Messages envoyés : `{u_stat.get('messages', 0)}`\n"
            f"- {E_MIC} Temps vocal : `{format_time(vocal_time)}`\n"
            f"- {E_WARN} Mutes / Sourdines : `{u_stat.get('mutes', 0)}` / `{u_stat.get('deafs', 0)}`"
        )
        
        try:
            container.add_item(ui.Section(desc, accessory=ui.Thumbnail(self.target.display_avatar.url, description="Avatar")))
        except:
            container.add_item(ui.TextDisplay(desc))

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))
            
        self.add_item(container)

class ProfilCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="profil", description="Affiche le profil et les statistiques d'un joueur.")
    @app_commands.describe(membre="Le membre dont vous souhaitez voir le profil")
    async def profil_cmd(self, ctx: commands.Context, membre: discord.Member = None):
        if not ctx.guild: return await ctx.send(f"{E_OFF} Cette commande exige un contexte de serveur.")
        await ctx.defer(ephemeral=False)
        target = membre or ctx.author
        await ctx.send(view=ProfileLayoutView(self.bot, ctx.guild, target))

async def setup(bot: commands.Bot):
    if bot.get_command("profil"): bot.remove_command("profil")
    await bot.add_cog(ProfilCog(bot))
