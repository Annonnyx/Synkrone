import discord
from discord.ext import commands
from discord import ui

# ===================== CONFIG MANAGER ========================
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

from cogs.casino.autres.achievements import (
    load_user_data,
    get_achievement_stats,
    build_achievement_pages,
)


def format_y(value: int) -> str:
    return f"{value:,}".replace(',', ' ')


def _get_embed(bot, guild, member, title, description):
    return bot.config.get_formatted_embed(
        title=title,
        description=description,
        bot_user=bot.user,
        guild=guild,
        user=member,
        target_id=guild.id if guild else None,
    )


class SuccesView(ui.View):
    def __init__(self, bot, guild, member, data, invoker_id: int):
        super().__init__(timeout=120)
        self.bot = bot
        self.guild = guild
        self.member = member
        self.data = data
        self.invoker_id = invoker_id
        self.pages = build_achievement_pages(data)
        self.current_page = 0

        self._btn_prev = ui.Button(label='◀', style=discord.ButtonStyle.gray)
        self._btn_next = ui.Button(label='▶', style=discord.ButtonStyle.gray)
        self._btn_prev.callback = self._prev
        self._btn_next.callback = self._next
        self.update_buttons()
        self.add_item(self._btn_prev)
        self.add_item(self._btn_next)

    def update_buttons(self):
        self._btn_prev.disabled = self.current_page == 0
        self._btn_next.disabled = self.current_page >= len(self.pages) - 1

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.invoker_id:
            await interaction.response.send_message("❌ Cette vue ne vous appartient pas.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        try:
            await self.message.edit(view=self)
        except Exception:
            pass

    def build_embed(self) -> discord.Embed:
        stats = get_achievement_stats(self.data)
        total_pages = max(1, len(self.pages))
        header = (
            f"🏆 **{stats['unlocked_achievements']}/{stats['total_achievements']}** succès débloqués "
            f"· **{stats['unlocked_paliers']}/{stats['total_paliers']}** paliers\n"
            f"✨ Honneur gagné via succès : **{format_y(stats['honneur_earned'])} pts**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        page_content = self.pages[self.current_page] if self.pages else "*Aucun succès disponible.*"
        description = header + page_content
        embed = _get_embed(
            self.bot,
            self.guild,
            self.member,
            f"🏆 Succès — {self.member.display_name}",
            description,
        )
        embed.set_footer(text=f"Page {self.current_page + 1}/{total_pages}")
        embed.set_thumbnail(url=self.member.display_avatar.url)
        return embed

    async def _prev(self, interaction: discord.Interaction):
        self.current_page = max(0, self.current_page - 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def _next(self, interaction: discord.Interaction):
        self.current_page = min(len(self.pages) - 1, self.current_page + 1)
        self.update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


class SuccesSAO(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="succes", description="Affiche l'avancé des succès.")
    async def succes(self, ctx: commands.Context, membre: discord.Member = None):
        membre = membre or ctx.author
        data = load_user_data(ctx.guild.id, membre.id)
        view = SuccesView(self.bot, ctx.guild, membre, data, ctx.author.id)
        embed = view.build_embed()
        sent = await ctx.send(embed=embed, view=view)
        view.message = sent


async def setup(bot):
    await bot.add_cog(SuccesSAO(bot))
