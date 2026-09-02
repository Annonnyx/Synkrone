import discord
from discord.ext import commands
from discord import ui
import os
import json

# ===================== CONFIG MANAGER ========================
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# ── TAUX DE CONVERSION (modifiables facilement) ──────────────
# 1 point d'honneur = RATE_H2Y Cols (vente, taxe 5%)
RATE_H2Y = int(0.95 * 100_000)      # 1 honneur → 95 000 Cols
# 1 col converti = RATE_Y2H points d'honneur (achat)
RATE_Y2H = 1 / 100_000  # 100 000 Cols → 1 honneur
# Minimum d'honneur pour convertir en Cols
MIN_HONNEUR_H2Y = 1
# Minimum de Cols pour convertir en honneur
MIN_Cols_Y2H = 100_000

# ── DONNÉES ─────────────────────────────────────────────────

def _path(guild_id: int, user_id: int) -> str:
    base = os.path.join('cogs', 'casino', 'data', str(guild_id))
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, f"{user_id}.json")

def load_data(guild_id: int, user_id: int) -> dict:
    p = _path(guild_id, user_id)
    if os.path.exists(p):
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"Cols": 1000, "honneur": 0}

def save_data(guild_id: int, user_id: int, data: dict):
    with open(_path(guild_id, user_id), 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def fmt(value) -> str:
    return f"{int(value):,}".replace(',', ' ')

def pt_label(val):
    return "pt" if int(val) == 1 else "pts"

# ── MODALS ──────────────────────────────────────────────────

class HToYModal(ui.Modal, title="Convertir Honneur → Cols"):

    def __init__(self, bot, guild_id, user_id, interaction=None, message=None, view=None):
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id
        self.user_id = user_id
        self.interaction = interaction
        self.message = message
        self.view = view
        data = load_data(guild_id, user_id)
        max_h = data.get("honneur", 0)
        amount = ui.TextInput(
            label="Combien de points d'honneur ?",
            placeholder=f"Min {MIN_HONNEUR_H2Y} — Max {max_h}",
            min_length=1, max_length=10
        )
        self.add_item(amount)
        self.amount = amount

        # Un seul constructeur !
        def __init__(self, bot, guild_id, user_id):
            super().__init__()
            self.bot = bot
            self.guild_id = guild_id
            self.user_id = user_id
            data = load_data(guild_id, user_id)
            max_h = data.get("honneur", 0)
            amount = ui.TextInput(
                label="Combien de points d'honneur ?",
                placeholder=f"Min {MIN_HONNEUR_H2Y} — Max {max_h}",
                min_length=1, max_length=10
            )
            self.add_item(amount)
            self.amount = amount

    async def on_submit(self, interaction: discord.Interaction):
        try:
            raw = self.amount.value.strip().replace(' ', '').replace(',', '')
            if not raw.isdigit():
                return await interaction.response.send_message("❌ Valeur invalide.", ephemeral=True)

            h = int(raw)
            if h < MIN_HONNEUR_H2Y:
                return await interaction.response.send_message(
                    f"❌ Minimum : **{MIN_HONNEUR_H2Y}** pts d'honneur.", ephemeral=True
                )

            data = load_data(self.guild_id, self.user_id)
            if data.get("honneur", 0) < h:
                return await interaction.response.send_message(
                    f"❌ Vous n'avez que **{fmt(data.get('honneur', 0))}** pts d'honneur.", ephemeral=True
                )

            gains = int(h * RATE_H2Y)
            data["honneur"] -= h
            data["Cols"] = data.get("Cols", 0) + gains
            save_data(self.guild_id, self.user_id, data)

            embed = self.bot.config.get_formatted_embed(
                title="💱 Bureau de Change — Aincrad",
                description=(
                    f"Conversion réussie !\n\n"
                    f"Vous avez converti **{fmt(h)} {pt_label(h)} d'honneur** en **{fmt(gains)} Cols**.\n\n"
                    f"**Votre solde actuel**\n"
                    f"💴 Cols : **{fmt(data.get('Cols', 0))} Cols**\n"
                    f"🎖️ Honneur : **{fmt(data.get('honneur', 0))} {pt_label(data.get('honneur', 0))}**\n"
                ),
                bot_user=self.bot.user,
                guild=interaction.guild,
                user=interaction.user,
                target_id=interaction.guild.id if interaction.guild else None
            )
            await interaction.response.edit_message(embed=embed, view=self.view)
        except Exception as e:
            print(f"[HToYModal] Erreur callback: {e}")
            await interaction.response.send_message(f"❌ Erreur interne : {e}", ephemeral=True)

class YToHModal(ui.Modal, title="Convertir Cols → Honneur"):

    def __init__(self, bot, guild_id, user_id, interaction=None, message=None, view=None):
        super().__init__()
        self.bot = bot
        self.guild_id = guild_id
        self.user_id = user_id
        self.interaction = interaction
        self.message = message
        self.view = view
        data = load_data(guild_id, user_id)
        max_y = data.get("Cols", 0)
        max_h = max_y // 100_000
        amount = ui.TextInput(
            label="Combien de points d'honneur à acheter ?",
            placeholder=f"Min 1 — Max {max_h}",
            min_length=1, max_length=10
        )
        self.add_item(amount)
        self.amount = amount

        # Un seul constructeur !
        def __init__(self, bot, guild_id, user_id):
            super().__init__()
            self.bot = bot
            self.guild_id = guild_id
            self.user_id = user_id
            data = load_data(guild_id, user_id)
            max_y = data.get("Cols", 0)
            amount = ui.TextInput(
                label="Combien de Cols ?",
                placeholder=f"Min {MIN_Cols_Y2H:,} — Max {max_y:,} Cols".replace(',', ' '),
                min_length=1, max_length=12
            )
            self.add_item(amount)
            self.amount = amount

    async def on_submit(self, interaction: discord.Interaction):
        try:
            raw = self.amount.value.strip().replace(' ', '').replace(',', '')
            if not raw.isdigit():
                return await interaction.response.send_message("❌ Valeur invalide.", ephemeral=True)

            h = int(raw)
            if h < 1:
                return await interaction.response.send_message(
                    f"❌ Minimum : **1** pt d'honneur.", ephemeral=True
                )

            data = load_data(self.guild_id, self.user_id)
            max_h = data.get("Cols", 0) // 100_000
            if h > max_h:
                return await interaction.response.send_message(
                    f"❌ Vous pouvez acheter au maximum **{fmt(max_h)} {pt_label(max_h)}** d'honneur.", ephemeral=True
                )

            cout = h * 100_000
            if data.get("Cols", 0) < cout:
                return await interaction.response.send_message(
                    f"❌ Il vous faut **{fmt(cout)} Cols** pour acheter {fmt(h)} {pt_label(h)} d'honneur.", ephemeral=True
                )

            data["Cols"] -= cout
            data["honneur"] = data.get("honneur", 0) + h
            save_data(self.guild_id, self.user_id, data)

            embed = self.bot.config.get_formatted_embed(
                title="💱 Bureau de Change — Aincrad",
                description=(
                    f"Conversion réussie !\n\n"
                    f"Vous avez acheté **{fmt(h)} {pt_label(h)} d'honneur** pour **{fmt(cout)} Cols**.\n\n"
                    f"**Votre solde actuel**\n"
                    f"💴 Cols : **{fmt(data.get('Cols', 0))} Cols**\n"
                    f"🎖️ Honneur : **{fmt(data.get('honneur', 0))} {pt_label(data.get('honneur', 0))}**\n"
                ),
                bot_user=self.bot.user,
                guild=interaction.guild,
                user=interaction.user,
                target_id=interaction.guild.id if interaction.guild else None
            )
            await interaction.response.edit_message(embed=embed, view=self.view)
        except Exception as e:
            print(f"[YToHModal] Erreur callback: {e}")
            await interaction.response.send_message(f"❌ Erreur interne : {e}", ephemeral=True)

# ── VUE ─────────────────────────────────────────────────────

class ConvertSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label="Honneur → Cols",
                value="h2y",
                emoji="🎖️",
                description=f"1 honneur = {fmt(RATE_H2Y)} Cols"
            ),
            discord.SelectOption(
                label="Cols → Honneur",
                value="y2h",
                emoji="💴",
                description=f"{fmt(int(1/RATE_Y2H))} Cols = 1 honneur"
            ),
        ]
        super().__init__(placeholder="Choisissez une conversion...", options=options)

    async def callback(self, interaction: discord.Interaction):
        try:
            view: ConvertView = self.view
            if interaction.user.id != view.invoker_id:
                return await interaction.response.send_message("❌ Ce menu ne vous appartient pas.", ephemeral=True)

            if self.values[0] == "h2y":
                await interaction.response.send_modal(
                    HToYModal(view.bot, interaction.guild.id, interaction.user.id, interaction=interaction, message=interaction.message, view=view)
                )
            else:
                await interaction.response.send_modal(
                    YToHModal(view.bot, interaction.guild.id, interaction.user.id, interaction=interaction, message=interaction.message, view=view)
                )
        except Exception as e:
            print(f"[ConvertSelect] Erreur callback: {e}")
            await interaction.response.send_message(f"❌ Erreur interne : {e}", ephemeral=True)

class ConvertView(ui.View):
    def __init__(self, bot, invoker_id):
        super().__init__(timeout=60)
        self.bot = bot
        self.invoker_id = invoker_id
        self.add_item(ConvertSelect())

# ── COG ─────────────────────────────────────────────────────

class ConvertSAO(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="convert", description="Convertir vos Cols en Honneur ou votre Honneur en Cols.")
    async def convert(self, ctx: commands.Context):
        data = load_data(ctx.guild.id, ctx.author.id)

        embed = self.bot.config.get_formatted_embed(
            title="💱 Bureau de Change — Aincrad",
            description=(
                f"Choisissez votre conversion dans le menu ci-dessous.\n\n"
                f"**Votre solde actuel**\n"
                f"💴 Cols : **{fmt(data.get('Cols', 0))} Cols**\n"
                f"🎖️ Honneur : **{fmt(data.get('honneur', 0))} {pt_label(data.get('honneur', 0))}**\n\n"
                f"**Taux de change**\n"
                f"🎖️ → 💴 : `1 honneur = {fmt(RATE_H2Y)} Cols`\n"
                f"💴 → 🎖️ : `100 000 Cols = 1 honneur`\n\n"
                f"-# *L'honneur est rare et précieux — la conversion Cols→Honneur est volontairement coûteuse.*"
            ),
            bot_user=self.bot.user,
            guild=ctx.guild,
            user=ctx.author,
            target_id=ctx.guild.id if ctx.guild else None
        )
        view = ConvertView(self.bot, ctx.author.id)
        await ctx.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(ConvertSAO(bot))
