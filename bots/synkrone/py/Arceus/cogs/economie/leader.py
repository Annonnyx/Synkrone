import math
import sqlite3
import io
import aiohttp
import asyncio
import discord
import datetime
from zoneinfo import ZoneInfo
from discord import ui
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

# ===================== CONFIGURATION DE LA DB ========================
DB_PATH = "data/economie/economy.db"

TABLE_USERS = "users"
TABLE_POKEMON = "inventory"

COL_USER_ID = "user_id"
COL_POKEMON_ID = "pokemon_id"
COL_SHINY = "is_shiny"

# ===================== CONFIGURATION VISUELLE ========================
EMOJI_SELECT_SOMMAIRE = "<:sac:1523705244146602114>"
EMOJI_SELECT_XP = "<:xp:1523704529386733822>"
EMOJI_SELECT_BALANCE = "<:pokdollars:1523704826951897289>"
EMOJI_SELECT_CLASSIC = "<:pokedex:1523703818603335821>"
EMOJI_SELECT_SHINY = "<:shiny:1522947934969270312>"

CATEGORIES = {
    "pokepoints": {"titre": "CLASSEMENT\nGÉNÉRAL", "color": (46, 204, 113), "icon_url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/items/master-ball.png", "suffix": "Pts"},
    "xp": {"titre": "CLASSEMENT NIVEAUX\nXP & Progression", "color": (52, 152, 219), "icon_url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/items/rare-candy.png", "suffix": "XP"},
    "balance": {"titre": "CLASSEMENT\nPOKÉDOLLARS", "color": (184, 134, 11), "icon_url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/items/nugget.png", "suffix": "₽"},
    "classic": {"titre": "CLASSEMENT POKÉDEX\nClassique", "color": (231, 76, 60), "icon_url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/items/max-revive.png", "suffix": "/ 1025"},
    "shiny": {"titre": "CLASSEMENT POKÉDEX\nShiny", "color": (155, 89, 182), "icon_url": "https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/items/shiny-charm.png", "suffix": "/ 1025"},
}

def format_number(num: int) -> str:
    return f"{int(num):,}".replace(",", " ")

def get_display_name(discord_user: discord.User | discord.Member) -> str:
    """Retourne le pseudo global (username) qui sert à ajouter en ami."""
    if not discord_user:
        return "Dresseur Inconnu"
    return discord_user.name

# ── CHARGEUR DE POLICES ──────────────────────────────────────
def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype("cogs/Pokemon.ttf", size)
    except IOError:
        return ImageFont.load_default()

def load_fallback_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Charge une police classique pour les caractères spéciaux comme le Pokédollar (₽)."""
    for font_name in ["arial.ttf", "DejaVuSans.ttf", "FreeSans.ttf", "LiberationSans-Regular.ttf"]:
        try:
            return ImageFont.truetype(font_name, size)
        except IOError:
            continue
    return ImageFont.load_default()

# ── PAGINATION LOGIQUE ──────────────────────────────────────
def get_page_info(page: int, total_items: int):
    if page == 0: return 0, min(10, total_items)
    elif page == 1: return 10, min(50, total_items)
    else:
        start = 50 + (page - 2) * 50
        return start, min(start + 50, total_items)

def get_total_pages(total_items: int) -> int:
    if total_items <= 10: return 1
    if total_items <= 50: return 2
    return 2 + math.ceil((total_items - 50) / 50)

def get_user_page(rank: int | str) -> int | None:
    """Calcule la page sur laquelle se trouve le joueur à partir de son rang."""
    if not isinstance(rank, int):
        return None
    if rank <= 10: return 1
    if rank <= 50: return 2
    return 2 + math.ceil((rank - 50) / 50)

# ── GÉNÉRATION PILLOW (IMAGE) ────────────────────────────────
async def fetch_image(session: aiohttp.ClientSession, url: str) -> Image.Image | None:
    try:
        # Ajout d'un timeout de 5 secondes pour éviter le freeze si l'API est lente
        async with session.get(url, timeout=5) as resp:
            if resp.status == 200:
                data = await resp.read()
                return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception:
        pass
    return None

def create_circular_avatar(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    img = img.resize(size, Image.Resampling.LANCZOS).convert("RGBA")
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0) + size, fill=255)
    result = Image.new("RGBA", size, (0, 0, 0, 0))
    result.paste(img, (0, 0), mask)
    return result

def draw_right_aligned_score(draw: ImageDraw.Draw, x_right: float, y: float, score_base: str, suffix: str, font_main, font_suffix, color: tuple):
    """Dessine le score avec un alignement à droite, gérant la police principale et celle de secours."""
    text_base = score_base + " "
    bbox_base = draw.textbbox((0, 0), text_base, font=font_main)
    w_base = bbox_base[2] - bbox_base[0]
    
    bbox_suf = draw.textbbox((0, 0), suffix, font=font_suffix)
    w_suf = bbox_suf[2] - bbox_suf[0]
    
    total_w = w_base + w_suf
    start_x = x_right - total_w
    
    draw.text((start_x, y), text_base, fill=color, font=font_main)
    draw.text((start_x + w_base, y), suffix, fill=color, font=font_suffix)

async def generate_leaderboard_image(bot: commands.Bot, data_slice: list[dict], category: str, page: int, total_pages: int, start_rank: int, author: discord.Member | discord.User, author_data: dict | None, author_rank: int | str) -> io.BytesIO:
    width, height = 1200, 1650 
    base_img = Image.new("RGBA", (width, height), (33, 35, 39, 255))
    draw = ImageDraw.Draw(base_img)
    
    cat_info = CATEGORIES[category]
    theme_color = cat_info["color"]
    
    font_title = load_font(50)
    font_rank1 = load_font(42)
    font_large = load_font(30)
    font_medium = load_font(26)
    font_small = load_font(20)
    font_footer = load_font(22)

    font_fallback_large = load_fallback_font(30) if category == "balance" else font_large
    font_fallback_n = None 
    font_fallback_small = load_fallback_font(20) if category == "balance" else font_small

    async with aiohttp.ClientSession() as session:
        # --- 1. EN-TÊTE ET TITRE ---
        header_height = 180
        draw.rectangle([0, 0, width, header_height], fill=theme_color)
        
        title_text = cat_info["titre"].upper()
        title_bbox = draw.multiline_textbbox((0, 0), title_text, font=font_title, spacing=10)
        title_h = title_bbox[3] - title_bbox[1]
        y_title = (header_height - title_h) // 2 - 10
        
        draw.multiline_text((200, y_title), title_text, fill=(225, 228, 233), font=font_title, spacing=10)
        
        icon_img = await fetch_image(session, cat_info["icon_url"])
        if icon_img:
            icon_img = icon_img.resize((120, 120), Image.Resampling.LANCZOS)
            y_icon = (header_height - 120) // 2
            base_img.paste(icon_img, (50, y_icon), icon_img)

        # --- 2. LIGNE DE L'UTILISATEUR (Épinglée) ---
        y_offset = 210
        draw.rounded_rectangle([30, y_offset, width - 30, y_offset + 100], radius=15, fill=(43, 45, 49, 255), outline=(52, 152, 219, 255), width=4)
        
        rang_txt = f"#{author_rank}" if isinstance(author_rank, int) else "Non classé"
        draw.text((60, y_offset + 25), rang_txt, fill=(52, 152, 219), font=font_rank1)
        
        if author.display_avatar:
            try:
                avatar_bytes = await author.display_avatar.with_size(128).read()
                avatar_img = create_circular_avatar(Image.open(io.BytesIO(avatar_bytes)), (80, 80))
                base_img.paste(avatar_img, (380, y_offset + 10), avatar_img)
            except: pass
            
        auth_score_base = f"{format_number(author_data[category])}" if author_data else "0"
        draw.text((480, y_offset + 35), get_display_name(author), fill=(255, 255, 255), font=font_large)
        
        draw_right_aligned_score(draw, width - 50, y_offset + 35, auth_score_base, cat_info['suffix'], font_large, font_fallback_large, theme_color)

        y_offset += 140
        draw.line([(60, y_offset), (width - 60, y_offset)], fill=(100, 100, 100, 255), width=3)
        y_offset += 40

        # --- 3. AFFICHAGE DE LA LISTE ---
        if page == 0:
            for i, user in enumerate(data_slice):
                rank = start_rank + i
                discord_user = bot.get_user(user['user_id'])
                name = get_display_name(discord_user)
                if len(name) > 20: name = name[:17] + "..."
                
                score_base = f"Niv. {user['level']} | {format_number(user['xp'])}" if category == "xp" else f"{format_number(user[category])}"

                if rank == 1:
                    h = 130; bg = (50, 50, 40, 255); outline = (255, 215, 0, 255); r_font = font_rank1; n_font = font_large
                elif rank == 2:
                    h = 110; bg = (40, 40, 40, 255); outline = (192, 192, 192, 255); r_font = font_large; n_font = font_large
                elif rank == 3:
                    h = 110; bg = (45, 35, 30, 255); outline = (205, 127, 50, 255); r_font = font_large; n_font = font_large
                else:
                    h = 90; bg = (43, 45, 49, 255); outline = None; r_font = font_medium; n_font = font_medium

                font_fallback_n = load_fallback_font(n_font.size) if category == "balance" else n_font

                draw.rounded_rectangle([30, y_offset, width - 30, y_offset + h], radius=12, fill=bg, outline=outline, width=3 if outline else 0)
                draw.text((60, y_offset + (h//2 - r_font.size//2)), f"#{rank}", fill=outline if outline else (200, 200, 200), font=r_font)

                if discord_user and discord_user.display_avatar:
                    av_size = 90 if rank == 1 else 80 if rank <= 3 else 70
                    try:
                        av_bytes = await discord_user.display_avatar.with_size(128).read()
                        av_img = create_circular_avatar(Image.open(io.BytesIO(av_bytes)), (av_size, av_size))
                        base_img.paste(av_img, (160, y_offset + (h - av_size)//2), av_img)
                    except: pass
                
                draw.text((270, y_offset + (h//2 - n_font.size//2)), name, fill=(255, 255, 255), font=n_font)
                
                draw_right_aligned_score(draw, width - 50, y_offset + (h//2 - n_font.size//2), score_base, cat_info['suffix'], n_font, font_fallback_n, theme_color)
                
                y_offset += h + 15

        else:
            col_width = (width - 90) // 2
            row_height = 50
            
            for i, user in enumerate(data_slice):
                rank = start_rank + i
                discord_user = bot.get_user(user['user_id'])
                name = get_display_name(discord_user)
                if len(name) > 16: name = name[:14] + ".."
                
                score_base = f"Niv. {user['level']} | {format_number(user['xp'])}" if category == "xp" else f"{format_number(user[category])}"

                col = 0 if i < len(data_slice) / 2 else 1
                row_idx = i if col == 0 else i - math.ceil(len(data_slice)/2)
                
                x_base = 30 if col == 0 else 60 + col_width
                y_base = y_offset + (row_idx * (row_height + 10))
                
                bg = (40, 42, 45, 255) if i % 2 == 0 else (33, 35, 39, 255)
                draw.rounded_rectangle([x_base, y_base, x_base + col_width, y_base + row_height], radius=8, fill=bg)
                
                draw.text((x_base + 15, y_base + 10), f"#{rank}", fill=(180, 180, 180), font=font_small)
                draw.text((x_base + 80, y_base + 10), name, fill=(255, 255, 255), font=font_small)
                
                draw_right_aligned_score(draw, x_base + col_width - 15, y_base + 10, score_base, cat_info['suffix'], font_small, font_fallback_small, theme_color)

    # Footer
    now = datetime.datetime.now(ZoneInfo("Europe/Paris"))
    date_str = now.strftime("%d/%m/%Y - %H:%M")
    date_bbox = draw.textbbox((0, 0), date_str, font=font_footer)
    date_w = date_bbox[2] - date_bbox[0]
    draw.text(((width - date_w) // 2, height - 80), date_str, fill=(150, 150, 150), font=font_footer)
    
    user_page = get_user_page(author_rank)
    if user_page:
        page_str = f"Page {page + 1} / {total_pages} - Tu es page {user_page}"
    else:
        page_str = f"Page {page + 1} / {total_pages}"
        
    page_bbox = draw.textbbox((0, 0), page_str, font=font_footer)
    page_w = page_bbox[2] - page_bbox[0]
    draw.text(((width - page_w) // 2, height - 40), page_str, fill=(150, 150, 150), font=font_footer)

    buffer = io.BytesIO()
    base_img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

# ── RÉCUPÉRATION DES DONNÉES ────────────────────────────────
def get_leaderboard_data() -> list[dict]:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            users_rows = conn.execute(f"SELECT * FROM {TABLE_USERS}").fetchall()
            if not users_rows: return []
            
            inv_map = {}
            try:
                inv_rows = conn.execute(f"""
                    SELECT {COL_USER_ID},
                           COUNT(DISTINCT {COL_POKEMON_ID}) as classic_dex,
                           COUNT(DISTINCT CASE WHEN {COL_SHINY} = 1 THEN {COL_POKEMON_ID} END) as shiny_dex
                    FROM {TABLE_POKEMON}
                    GROUP BY {COL_USER_ID}
                """).fetchall()
                inv_map = {row[COL_USER_ID]: {"classic": row["classic_dex"], "shiny": row["shiny_dex"]} for row in inv_rows}
            except sqlite3.OperationalError as e: 
                print(f"[Leaderboard] ⚠️ Erreur SQL lors de la lecture du Pokédex : {e}")

            data = []
            for u in users_rows:
                uid = u["user_id"] if "user_id" in u.keys() else u["id"] if "id" in u.keys() else None
                if not uid: continue
                
                classic_count = inv_map.get(uid, {}).get("classic", 0)
                shiny_count = inv_map.get(uid, {}).get("shiny", 0)
                
                keys = u.keys()
                xp = u["xp"] if "xp" in keys else 0
                level = u["level"] if "level" in keys else 1
                balance = u["balance"] if "balance" in keys else u["money"] if "money" in keys else 0
                
                balls_points = sum([u[k] * w for k, w in [("pokeball", 1), ("superball", 3), ("hyperball", 7), ("masterball", 300), ("superbonbon", 40)] if k in keys])
                charm_points = sum([u[k] * 1000 for k in ["charme_stabilite", "charme_chroma", "charme_insigne"] if k in keys])
                
                pokepoints = (xp // 10) + (balance // 10) + (classic_count * 20) + (shiny_count * 100) + balls_points + charm_points
                
                data.append({
                    "user_id": uid,
                    "xp": xp,
                    "level": level,
                    "balance": balance,
                    "classic": classic_count,
                    "shiny": shiny_count,
                    "pokepoints": pokepoints
                })
            return data
    except Exception as e:
        print(f"[Leaderboard] Erreur générale DB : {e}")
        return []

# ── LE MODAL DE SELECTION DE PAGE ───────────────────────────
class PageJumpModal(ui.Modal, title="Aller à la page"):
    page_input = ui.TextInput(label="Numéro de la page", placeholder="Ex: 3", min_length=1, max_length=5)

    def __init__(self, view: "LeaderboardView", total_pages: int):
        super().__init__()
        self.view = view
        self.total_pages = total_pages

    async def on_submit(self, interaction: discord.Interaction):
        val = self.page_input.value.strip()
        if not val.isdigit():
            await interaction.response.send_message("❌ Veuillez entrer un nombre entier valide.", ephemeral=True)
            return
        
        target_page = int(val)
        if target_page < 1 or target_page > self.total_pages:
            await interaction.response.send_message(f"❌ La page demandée n'existe pas. Choisissez entre 1 et {self.total_pages}.", ephemeral=True)
            return

        # On "defer" instantanément pour éviter le plantage
        await interaction.response.defer()
        self.view.page = target_page - 1
        await self.view.update_leaderboard(interaction)

# ── INTERFACE GRAPHIQUE (VIEWS & BUTTONS) ───────────────────
class LeaderboardView(ui.View):
    def __init__(self, bot: commands.Bot, users_data: list[dict], ctx: commands.Context):
        super().__init__(timeout=120)
        self.bot = bot
        self.users_data = users_data
        self.ctx = ctx
        self.category = "pokepoints"
        self.page = 0
        self.message = None

    def get_sorted_data(self):
        filtered_data = [u for u in self.users_data if u.get(self.category, 0) > 0]
        return sorted(filtered_data, key=lambda x: x.get(self.category, 0), reverse=True)

    async def update_leaderboard(self, interaction: discord.Interaction | None = None):
        data = self.get_sorted_data()
        total_pages = get_total_pages(len(data))

        author_id = self.ctx.author.id
        author_data = next((u for u in data if u["user_id"] == author_id), None)
        author_rank = data.index(author_data) + 1 if author_data else "Non classé"

        for item in self.children:
            if isinstance(item, ui.Button):
                if item.custom_id == "prev":
                    item.disabled = self.page == 0
                elif item.custom_id == "next":
                    item.disabled = self.page >= total_pages - 1 or total_pages == 0
                elif item.custom_id == "page_jump":
                    item.label = f"{self.page + 1} / {max(1, total_pages)}"

        start, end = get_page_info(self.page, len(data))
        page_data = data[start:end]
        
        if not page_data:
            embed = discord.Embed(title=CATEGORIES[self.category]["titre"].replace('\n', ' - '), description="❌ *Aucun dresseur n'a de points dans cette catégorie ou la base de données est mal lue.*", color=0x2B2D31)
            if interaction: 
                await interaction.edit_original_response(content=None, embed=embed, attachments=[], view=self)
            return embed, None

        buffer = await generate_leaderboard_image(
            self.bot, page_data, self.category, self.page, total_pages, start + 1, 
            self.ctx.author, author_data, author_rank
        )
        file = discord.File(fp=buffer, filename="leaderboard.png")

        if interaction:
            # Comme on a déjà "defer" l'interaction, on utilise edit_original_response
            await interaction.edit_original_response(content=None, embed=None, attachments=[file], view=self)
        
        return None, file

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ Seul l'auteur de la commande peut interagir.", ephemeral=True)
            return False
        return True

    @ui.select(
        placeholder="🏆 Choisissez un classement...",
        options=[
            discord.SelectOption(label="Sommaire", value="pokepoints", description="Basé sur le cumul de tout le patrimoine", emoji=EMOJI_SELECT_SOMMAIRE),
            discord.SelectOption(label="Niveau & XP", value="xp", emoji=EMOJI_SELECT_XP),
            discord.SelectOption(label="Pokédollars", value="balance", emoji=EMOJI_SELECT_BALANCE),
            discord.SelectOption(label="Pokédex Classique", value="classic", emoji=EMOJI_SELECT_CLASSIC),
            discord.SelectOption(label="Pokédex Shiny", value="shiny", emoji=EMOJI_SELECT_SHINY),
        ],
        row=0
    )
    async def select_category(self, interaction: discord.Interaction, select: ui.Select):
        # On empêche l'échec de l'interaction en mettant l'API en attente
        await interaction.response.defer()
        self.category = select.values[0]
        self.page = 0
        await self.update_leaderboard(interaction)

    @ui.button(label="◀ Précédent", style=discord.ButtonStyle.secondary, custom_id="prev", row=1)
    async def prev_page(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        if self.page > 0:
            self.page -= 1
        await self.update_leaderboard(interaction)

    @ui.button(label="1 / 1", style=discord.ButtonStyle.primary, custom_id="page_jump", row=1)
    async def jump_page(self, interaction: discord.Interaction, button: ui.Button):
        data = self.get_sorted_data()
        total_pages = get_total_pages(len(data))
        modal = PageJumpModal(self, total_pages)
        await interaction.response.send_modal(modal)

    @ui.button(label="Suivant ▶", style=discord.ButtonStyle.secondary, custom_id="next", row=1)
    async def next_page(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        if self.page < get_total_pages(len(self.get_sorted_data())) - 1:
            self.page += 1
        await self.update_leaderboard(interaction)

    async def on_timeout(self):
        if self.message:
            try:
                for item in self.children: item.disabled = True
                await self.message.edit(view=self)
            except Exception: pass

# ── LE COG & LA COMMANDE HYBRIDE ───────────────────────────
class LeaderboardCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name="leader",
        aliases=["top", "leaderboard"],
        description="Affiche le classement des dresseurs."
    )
    async def leaderboard(self, ctx: commands.Context):
        await ctx.defer()
        
        msg = await ctx.send("Patience, Les statistiques chargent.")
        
        async def loading_animation():
            try:
                dots = 1
                while True:
                    await msg.edit(content=f"Patience, Les statistiques chargent{'.' * dots}")
                    dots = (dots % 3) + 1
                    await asyncio.sleep(0.6)
            except asyncio.CancelledError:
                pass
                
        anim_task = asyncio.create_task(loading_animation())
        
        try:
            users_data = get_leaderboard_data()
            if not users_data:
                anim_task.cancel()
                embed = discord.Embed(title="🏆 Classement", description="❌ *Aucune donnée trouvée.*", color=0xD32F2F)
                return await msg.edit(content=None, embed=embed)
                
            view = LeaderboardView(self.bot, users_data, ctx)
            embed, file = await view.update_leaderboard()
            
            anim_task.cancel()
            
            if file:
                view.message = await msg.edit(content=None, attachments=[file], view=view)
            else:
                view.message = await msg.edit(content=None, embed=embed, view=view)
                
        except Exception as e:
            anim_task.cancel()
            await msg.edit(content=f"❌ Une erreur est survenue lors de la création du classement : {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(LeaderboardCog(bot))