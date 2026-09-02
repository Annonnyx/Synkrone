import discord
from discord.ext import commands
from discord import ui
import random
import traceback

# ==============================================================================
# --------------------------- IMPORTATION UTILS --------------------------------
# ==============================================================================
try:
    from cogs.config_manager.utils import config_manager
except ImportError:
    config_manager = None


# ==============================================================================
# --------------------------- MODAL CUSTOM -------------------------------------
# ==============================================================================
class CustomDiceModal(ui.Modal, title="⚙️ Dés sur mesure"):
    nb_des_input = ui.TextInput(
        label="Nombre de dés",
        placeholder="Ex: 5",
        default="1",
        min_length=1,
        max_length=3,
        required=True
    )
    nb_faces_input = ui.TextInput(
        label="Nombre de faces",
        placeholder="Ex: 100",
        default="20",
        min_length=1,
        max_length=5,
        required=True
    )

    def __init__(self, parent_view):
        super().__init__()
        self.parent_view = parent_view

    async def on_submit(self, interaction: discord.Interaction):
        if not self.nb_des_input.value.isdigit() or not self.nb_faces_input.value.isdigit():
            return await interaction.response.send_message("❌ Nombres entiers uniquement.", ephemeral=True)
        
        nb_des = int(self.nb_des_input.value)
        nb_faces = int(self.nb_faces_input.value)

        if nb_des <= 0 or nb_faces <= 1:
            return await interaction.response.send_message("❌ Il faut au moins 1 dé et 2 faces.", ephemeral=True)
        
        if nb_des > 100:
            return await interaction.response.send_message("❌ Limite de sécurité : 100 dés maximum.", ephemeral=True)

        self.parent_view.nb_des = nb_des
        self.parent_view.nb_faces = nb_faces
        self.parent_view.is_dirty = True
        
        await self.parent_view.update_ui(interaction)


# ==============================================================================
# --------------------------- SELECTEURS ---------------------------------------
# ==============================================================================
class DiceCountSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=f"{i} Dé{'s' if i > 1 else ''}", value=str(i), emoji="🎲") 
            for i in range(1, 7)
        ]
        super().__init__(placeholder="Quantité de dés...", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view.ctx.author.id:
            return await interaction.response.send_message("❌ Ce menu ne vous appartient pas.", ephemeral=True)
            
        self.view.nb_des = int(self.values[0])
        self.view.is_dirty = True
        await self.view.update_ui(interaction)


class DiceFacesSelect(ui.Select):
    def __init__(self):
        faces = [4, 6, 8, 10, 12, 20, 100]
        options = [
            discord.SelectOption(label=f"{f} Faces", value=str(f), emoji="💠") 
            for f in faces
        ]
        super().__init__(placeholder="Type de dé...", options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view.ctx.author.id:
            return await interaction.response.send_message("❌ Ce menu ne vous appartient pas.", ephemeral=True)
            
        self.view.nb_faces = int(self.values[0])
        self.view.is_dirty = True
        await self.view.update_ui(interaction)


# ==============================================================================
# --------------------------- VUE PRINCIPALE -----------------------------------
# ==============================================================================
class DiceView(ui.View):
    def __init__(self, ctx, bot):
        super().__init__(timeout=600)
        self.ctx = ctx
        self.bot = bot
        
        self.nb_des = 1
        self.nb_faces = 6
        self.results = []
        
        self.is_dirty = False 
        
        self.add_item(DiceCountSelect())
        self.add_item(DiceFacesSelect())
        
        self.roll_dice()

    def roll_dice(self):
        self.results = [random.randint(1, self.nb_faces) for _ in range(self.nb_des)]
        self.is_dirty = False

    def get_embed(self) -> discord.Embed:
        total = sum(self.results)
        
        if self.is_dirty:
            title = "⚙️ Configuration en attente..."
            desc = (
                f"> **Jet prévu :** `{self.nb_des}d{self.nb_faces}`\n"
                f"> \n"
                f"> ⏳ *Les dés sont dans votre main...*\n"
                f"> 👇 *Cliquez sur **Lancer** pour les jeter !*"
            )
        else:
            title = "🎲 Résultat du lancer"
            
            # Formatage propre : si peu de dés, on fait des petits blocs, sinon on groupe.
            if len(self.results) > 20:
                res_str = f"` {', '.join(map(str, self.results[:20]))} ... ` *(+ {len(self.results)-20} autres)*"
            else:
                res_str = " ".join([f"` {r} `" for r in self.results])
                
            desc = (
                f"> **Tirage :** `{self.nb_des}d{self.nb_faces}`\n"
                f"> **Détails :** {res_str}\n"
                f"> \n"
                f"> # 🎯 Total : {total}"
            )

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
            fallback_color = 0x2b2d31 if self.is_dirty else 0x57F287
            embed = discord.Embed(title=title, description=desc, color=fallback_color)
            embed.set_footer(text=f"Lancé par {self.ctx.author.display_name}", icon_url=self.ctx.author.display_avatar.url)
        
        return embed

    async def update_ui(self, interaction: discord.Interaction):
        if self.is_dirty:
            self.action_button.label = "Lancer"
            self.action_button.style = discord.ButtonStyle.primary
            self.action_button.emoji = "🎲"
        else:
            self.action_button.label = "Relancer"
            self.action_button.style = discord.ButtonStyle.success
            self.action_button.emoji = "🔄"

        embed = self.get_embed()
        
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="Relancer", style=discord.ButtonStyle.success, emoji="🔄", row=2)
    async def action_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Ce menu ne vous appartient pas.", ephemeral=True)
        
        self.roll_dice()
        await self.update_ui(interaction)

    @ui.button(label="Custom", style=discord.ButtonStyle.secondary, emoji="⚙️", row=2)
    async def custom_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("❌ Ce menu ne vous appartient pas.", ephemeral=True)
        
        await interaction.response.send_modal(CustomDiceModal(self))


# ==============================================================================
# --------------------------- COG ----------------------------------------------
# ==============================================================================
class Dice(commands.Cog):
    """🎲 Module Dice — Lancer personnalisable."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name="dice",
        description="Lance un ou plusieurs dés personnalisables (1d6 par défaut)."
    )
    async def dice(self, ctx: commands.Context):
        try:
            view = DiceView(ctx, self.bot)
            embed = view.get_embed()
            
            if ctx.interaction:
                await ctx.send(embed=embed, view=view)
            else:
                await ctx.send(embed=embed, view=view, reference=ctx.message)
                
        except Exception:
            print("[ERROR - Dice] :")
            traceback.print_exc()


async def setup(bot: commands.Bot):
    if bot.get_command("dice"):
        bot.remove_command("dice")
    await bot.add_cog(Dice(bot))