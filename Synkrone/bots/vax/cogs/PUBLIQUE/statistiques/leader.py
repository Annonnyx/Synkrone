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
E_CROWN = getattr(E, 'CLASSEMENT', "ðŸ†") if HAS_VAX_CORE else "ðŸ†"
E_MSG = "ðŸ’¬"
E_MIC = "ðŸŽ¤"
E_STAR = getattr(E, 'ETOILE', "â­") if HAS_VAX_CORE else "â­"
E_LEFT = getattr(E, 'FLECHE_GAUCHE', "â¬…ï¸") if HAS_VAX_CORE else "â¬…ï¸"
E_RIGHT = getattr(E, 'FLECHE_DROITE', "âž¡ï¸") if HAS_VAX_CORE else "âž¡ï¸"

lvl_db = DataManager("public/statistiques/leveling") if HAS_VAX_CORE else None
stats_db = DataManager("public/statistiques") if HAS_VAX_CORE else None

def format_time(seconds: int) -> str:
    h, r = divmod(int(seconds), 3600)
    m, s = divmod(r, 60)
    if h > 0: return f"{h}h {m}m"
    if m > 0: return f"{m}m {s}s"
    return f"{s}s"

class LeaderboardLayoutView(ui.LayoutView):
    def __init__(self, bot: commands.Bot, guild: discord.Guild, user: discord.Member):
        super().__init__(timeout=600)
        self.bot = bot
        self.guild = guild
        self.user = user
        self.lb_type = "xp" # 'xp', 'messages', 'vocal'
        self.lb_page = 1
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            if not interaction.response.is_done(): await interaction.response.defer()
            await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, cette console est protégée.", delete_after=6)
            return False
        return True

    def _build(self):
        self.clear_items()
        accent_color = 0x3498db
        footer_text = ""
        if HAS_VAX_CORE and config_manager:
            try:
                theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.bot)
                accent_color = int(theme.get("color", 0x3498db))
                footer_text = theme.get("footer_text", "")
            except: pass

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        
        # Collecte et tri des données
        users_data = {}
        if self.lb_type == "xp":
            data = lvl_db.load(self.guild.id) if lvl_db else {}
            users_data = {int(k): v.get("xp", 0) for k, v in data.get("users", {}).items() if v.get("xp", 0) > 0}
        else:
            data = stats_db.load(self.guild.id) if stats_db else {}
            for k, v in data.get("users", {}).items():
                uid = int(k)
                val = v.get(self.lb_type, 0)
                if self.lb_type == "vocal":
                    stats_cog = self.bot.get_cog("StatsCog")
                    if stats_cog and uid in stats_cog.voice_tracking:
                        val += int(time.time() - stats_cog.voice_tracking[uid])
                if val > 0: users_data[uid] = val

        users_list = sorted(users_data.items(), key=lambda x: x[1], reverse=True)
        items_per_page = 10
        max_p = max(1, (len(users_list) + items_per_page - 1) // items_per_page)
        self.lb_page = min(max(1, self.lb_page), max_p)
        
        start = (self.lb_page - 1) * items_per_page
        chunk = users_list[start:start + items_per_page]
        
        icons = {"xp": E_STAR, "messages": E_MSG, "vocal": E_MIC}
        names = {"xp": "Expérience (XP)", "messages": "Messages Envoyés", "vocal": "Temps en Vocal"}
        
        desc = f"### {E_CROWN} Classement : {names[self.lb_type]}\n\n"
        if not chunk:
            desc += "> ðŸ“­ Aucun classement disponible pour le moment."
        else:
            for i, (uid, val) in enumerate(chunk, start=start + 1):
                med = "ðŸ¥‡" if i==1 else "ðŸ¥ˆ" if i==2 else "ðŸ¥‰" if i==3 else "ðŸ”¹"
                m = self.guild.get_member(uid)
                m_txt = m.mention if m else f"<@{uid}>"
                
                if self.lb_type == "xp": val_txt = f"`{val} XP`"
                elif self.lb_type == "messages": val_txt = f"`{val} msgs`"
                else: val_txt = f"`{format_time(val)}`"
                
                desc += f"{med} **#{i}** {m_txt} - {val_txt}\n"
            desc += f"\n*Page {self.lb_page}/{max_p}*"

        container.add_item(ui.TextDisplay(desc))

        # Sélecteur de catégorie
        row1 = ui.ActionRow()
        opts = [
            discord.SelectOption(label="Classement : XP", value="xp", emoji=E_STAR, default=self.lb_type=="xp"),
            discord.SelectOption(label="Classement : Messages", value="messages", emoji=E_MSG, default=self.lb_type=="messages"),
            discord.SelectOption(label="Classement : Vocal", value="vocal", emoji=E_MIC, default=self.lb_type=="vocal")
        ]
        sel = ui.Select(placeholder="Changer de classement...", options=opts)
        async def cb_sort(interaction):
            if not interaction.response.is_done(): await interaction.response.defer()
            self.lb_type = interaction.data['values'][0]
            self.lb_page = 1
            await self._refresh(interaction)
        sel.callback = cb_sort
        row1.add_item(sel)
        container.add_item(row1)

        # Pagination
        row2 = ui.ActionRow()
        btn_prev = ui.Button(label="Précédent", style=discord.ButtonStyle.secondary, emoji=E_LEFT, disabled=self.lb_page <= 1)
        async def prev_cb(i): 
            if not i.response.is_done(): await i.response.defer()
            self.lb_page -= 1
            await self._refresh(i)
        btn_prev.callback = prev_cb
        row2.add_item(btn_prev)
        
        btn_next = ui.Button(label="Suivant", style=discord.ButtonStyle.secondary, emoji=E_RIGHT, disabled=self.lb_page >= max_p)
        async def next_cb(i):
            if not i.response.is_done(): await i.response.defer()
            self.lb_page += 1
            await self._refresh(i)
        btn_next.callback = next_cb
        row2.add_item(btn_next)
        container.add_item(row2)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    async def _refresh(self, interaction: discord.Interaction):
        self._build()
        if interaction.response.is_done(): await interaction.edit_original_response(view=self)
        else: await interaction.response.edit_message(view=self)

class LeaderboardCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="leaderboard", aliases=["leader", "top"], description="Affiche les classements du serveur.")
    async def leader_cmd(self, ctx: commands.Context):
        if not ctx.guild: return await ctx.send(f"{E_OFF} Cette commande exige un contexte de serveur.")
        await ctx.defer(ephemeral=False)
        await ctx.send(view=LeaderboardLayoutView(self.bot, ctx.guild, ctx.author))

async def setup(bot: commands.Bot):
    if bot.get_command("leaderboard"): bot.remove_command("leaderboard")
    await bot.add_cog(LeaderboardCog(bot))
