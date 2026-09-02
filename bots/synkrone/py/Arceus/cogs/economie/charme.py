import time
from typing import Any

import discord
from discord.ext import commands

from .utils import EconomyService, CHARM_FIELDS, CHARM_EMOJIS, CHARM_LABELS

try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

class CharmUseButton(discord.ui.Button[Any]):
    def __init__(self, charm_key: str, quantity: int):
        super().__init__(
            style=discord.ButtonStyle.success if quantity > 0 else discord.ButtonStyle.secondary,
            label=f"Utiliser ({quantity})",
            emoji=CHARM_EMOJIS[charm_key],
            disabled=quantity <= 0
        )
        self.charm_key = charm_key

    async def callback(self, interaction: discord.Interaction):
        view: CharmsView = self.view
        success, msg = view.cog.eco.use_charm(interaction.user.id, self.charm_key)
        
        if success:
            embed = view.cog.build_charms_embed(interaction.guild, interaction.user)
            new_view = CharmsView(view.cog, interaction.user.id)
            await interaction.response.edit_message(embed=embed, view=new_view)
        else:
            await interaction.response.send_message(msg, ephemeral=True)

class CharmsView(discord.ui.View):
    def __init__(self, cog: "CharmsCog", author_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.author_id = author_id
        
        with self.cog.eco._get_conn() as conn:
            row = conn.execute("SELECT charme_stabilite, charme_chroma, charme_insigne, charme_xp FROM users WHERE user_id = ?", (author_id,)).fetchone()
            
        for charm_key in CHARM_FIELDS:
            qty = row[charm_key] if row else 0
            self.add_item(CharmUseButton(charm_key, qty))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        return True

class CharmsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.eco = EconomyService(bot)

    def build_charms_embed(self, guild: discord.Guild | None, user: discord.abc.User) -> discord.Embed:
        self.eco.ensure_user(user.id)
        
        desc = (
            "Sélectionnez un charme à consommer. L'effet dure **1 heure** et se cumule.\n\n"
            f"{CHARM_EMOJIS['charme_stabilite']} **Charme Stabilité** → *Augmente le taux de réussite de capture* **[x5]**\n"
            f"{CHARM_EMOJIS['charme_chroma']} **Charme Chroma** → *Augmente le taux d'apparition de shiny* **[1/100]**\n"
            f"{CHARM_EMOJIS['charme_insigne']} **Charme Insigne** → *Augmente le taux d'apparition de légendaire & fabuleux* **[1/50]**\n"
            f"{CHARM_EMOJIS['charme_xp']} **Charme XP** → *Double les gains d'expérience* **[x2]**\n"
        )
        
        if config_manager:
            embed = config_manager.get_formatted_embed(
                guild=guild, 
                user=user, 
                bot=self.bot, 
                title="", 
                description=desc
            )
        else:
            embed = discord.Embed(title="", description=desc, color=0x2B2D31)
            
        embed.set_author(name=f"Inventaire de charmes de {user.display_name}", icon_url=user.display_avatar.url)

        with self.eco._get_conn() as conn:
            row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user.id,)).fetchone()

        now = time.time()
        col_nom = []
        col_qte = []
        col_etat = []

        for charm_key in CHARM_FIELDS:
            qty = row[charm_key] if row else 0
            expire = row[f"{charm_key}_expire"] if row else 0
            
            col_nom.append(f"{CHARM_EMOJIS[charm_key]} {CHARM_LABELS[charm_key]}")
            col_qte.append(f"`{qty}`")
            
            if expire > now:
                col_etat.append(f"🟢 <t:{int(expire)}:R>")
            else:
                col_etat.append("🔴 Inactif")

        embed.add_field(name="Charme", value="\n".join(col_nom), inline=True)
        embed.add_field(name="Possédé", value="\n".join(col_qte), inline=True)
        embed.add_field(name="État", value="\n".join(col_etat), inline=True)

        return embed

    @commands.hybrid_command(name="charme", description="Affiche et permet de consommer vos charmes.")
    async def charme(self, ctx: commands.Context[commands.Bot]):
        self.eco.ensure_user(ctx.author.id)
        
        view = CharmsView(self, ctx.author.id)
        embed = self.build_charms_embed(ctx.guild, ctx.author)
        
        msg = await ctx.send(embed=embed, view=view, reference=ctx.message)
        view.message = msg

async def setup(bot: commands.Bot):
    if bot.get_cog("CharmsCog"):
        await bot.remove_cog("CharmsCog")
    await bot.add_cog(CharmsCog(bot))