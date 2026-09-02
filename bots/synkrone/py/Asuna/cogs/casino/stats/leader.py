import discord
from discord.ext import commands
from discord import ui
import os
import json
import math

from cogs.casino.autres.achievements import ACHIEVEMENTS, get_level

# ===================== CONFIG MANAGER ========================
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# ── DONNÉES ─────────────────────────────────────────────────

def get_all_users_data(guild_id: int):
    users_list = []
    base_dir = os.path.join('cogs', 'casino', 'data', str(guild_id))
    if not os.path.exists(base_dir):
        return []
    for filename in os.listdir(base_dir):
        if not filename.endswith('.json'):
            continue
        user_id = filename.replace('.json', '')
        path = os.path.join(base_dir, filename)
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            stats = data.get("stats", {})
            # Calcul honneur total tiré des succès
            total_honneur_ach = 0
            try:
                unlocked = data.get("achievements", {})
                for key, u in unlocked.items():
                    tier = u.get("tier", 0)
                    for i in range(tier):
                        total_honneur_ach += ACHIEVEMENTS[key]["tiers"][i]["honneur"]
            except Exception:
                pass
            users_list.append({
                "id": int(user_id),
                "Cols": data.get("Cols", 0),
                "honneur": data.get("honneur", 0),
                "total_wins": stats.get("total_wins", 0),
                "honneur_ach": total_honneur_ach,
                "level": get_level(data),
            })
        except Exception:
            continue
    return users_list

def format_val(value: int) -> str:
    return f"{value:,}".replace(',', ' ')

# ── VUE ─────────────────────────────────────────────────────

CATEGORIES = {
    "Cols":        ("💴 Classement des Fortunes",          "Cols"),
    "honneur":     ("🎖️ Classement de l'Honneur",          "pts"),
    "honneur_ach": ("✨ Classement des Légendaires",       "pts succès"),
    "level":       ("🌟 Classement des Niveaux",          "lvl"),
}
PER_PAGE = 10

class LeaderboardView(ui.View):
    def __init__(self, bot, users_data, ctx):
        super().__init__(timeout=120)
        self.bot = bot
        self.users_data = users_data
        self.ctx = ctx
        self.category = "Cols"
        self.page = 0

    def get_sorted(self):
        return sorted(
            self.users_data,
            key=lambda x: x.get(self.category, 0), reverse=True
        )

    async def build_embed(self) -> discord.Embed:
        data = self.get_sorted()
        title, unit = CATEGORIES[self.category]
        total_pages = max(1, math.ceil(len(data) / PER_PAGE))

        # Boutons pagination
        for item in self.children:
            if isinstance(item, ui.Button):
                if item.custom_id == "prev":
                    item.disabled = self.page == 0
                elif item.custom_id == "next":
                    item.disabled = (self.page + 1) * PER_PAGE >= len(data)

        embed = self.bot.config.get_formatted_embed(
            title=title,
            description="",
            bot_user=self.bot.user,
            guild=self.ctx.guild,
            user=self.ctx.author,
            target_id=self.ctx.guild.id if self.ctx.guild else None
        )

        if not data:
            embed.description = "*Aucun joueur dans ce classement.*"
            return embed

        start = self.page * PER_PAGE
        page_data = data[start:start + PER_PAGE]
        lines = []
        for i, user in enumerate(page_data, start + 1):
            member = self.ctx.guild.get_member(user['id']) if self.ctx.guild else None
            if not member:
                member = self.bot.get_user(user['id'])
            if not member:
                try:
                    member = await self.bot.fetch_user(user['id'])
                except Exception:
                    member = None
            name = member.display_name if member else f"Joueur inconnu ({user['id']})"
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"`#{i}`"
            lines.append(f"{medal} **{name}** — {format_val(user[self.category])} {unit}")

        embed.description = "\n".join(lines)
        embed.set_footer(text=f"Page {self.page + 1}/{total_pages}")

        try:
            first = self.ctx.guild.get_member(data[0]['id']) if self.ctx.guild else None
            if not first:
                first = self.bot.get_user(data[0]['id']) or await self.bot.fetch_user(data[0]['id'])
            if first:
                embed.set_thumbnail(url=first.display_avatar.url)
        except Exception:
            pass

        return embed

    @ui.select(
        placeholder="Choisir une catégorie...",
        options=[
            discord.SelectOption(label="Fortunes",   value="Cols",        emoji="💴"),
            discord.SelectOption(label="Honneur",           value="honneur",     emoji="🎖️"),
            discord.SelectOption(label="Succès",            value="honneur_ach", emoji="✨"),
            discord.SelectOption(label="Niveaux",           value="level",       emoji="🌟"),
        ]
    )
    async def select_category(self, interaction: discord.Interaction, select: ui.Select):
        self.category = select.values[0]
        self.page = 0
        await interaction.response.edit_message(embed=await self.build_embed(), view=self)

    @ui.button(label="◀", style=discord.ButtonStyle.gray, custom_id="prev")
    async def prev_page(self, interaction: discord.Interaction, button: ui.Button):
        if self.page > 0:
            self.page -= 1
        await interaction.response.edit_message(embed=await self.build_embed(), view=self)

    @ui.button(label="▶", style=discord.ButtonStyle.gray, custom_id="next")
    async def next_page(self, interaction: discord.Interaction, button: ui.Button):
        data = self.get_sorted()
        if (self.page + 1) * PER_PAGE < len(data):
            self.page += 1
        await interaction.response.edit_message(embed=await self.build_embed(), view=self)

# ── COG ─────────────────────────────────────────────────────

class LeaderboardSAO(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="leader", aliases=["top"], description="Affiche le classement du Grand Casino d'Aincrad.")
    async def leader(self, ctx: commands.Context):
        users_data = get_all_users_data(ctx.guild.id)
        if not users_data:
            embed = self.bot.config.get_formatted_embed(
                title="🏆 Classement",
                description="*Aucun joueur pour l'instant.*",
                bot_user=self.bot.user,
                guild=ctx.guild,
                user=ctx.author,
                target_id=ctx.guild.id if ctx.guild else None
            )
            return await ctx.send(embed=embed)
        view = LeaderboardView(self.bot, users_data, ctx)
        embed = await view.build_embed()
        await ctx.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(LeaderboardSAO(bot))
