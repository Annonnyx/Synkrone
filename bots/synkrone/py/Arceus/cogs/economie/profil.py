import io
import time
import datetime
import asyncio
from zoneinfo import ZoneInfo
from typing import Union

import aiohttp
import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

from .utils import (
    BALL_EMOJIS, BALL_FIELDS, BALL_LABELS, SUPERBONBON_EMOJI, 
    CHARM_FIELDS, CHARM_EMOJIS, CHARM_LABELS, EconomyService
)

try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

try:
    EMBED_COLOR = int(config.get("EMBED_COLOR", "0x2B2D31"), 16)
except NameError:
    EMBED_COLOR = 0x2B2D31

# Mapping interne -> Noms des items sur l'API Pokémon
API_ITEMS = {
    "pokeball": "poke-ball",
    "superball": "great-ball",
    "hyperball": "ultra-ball",
    "masterball": "master-ball",
    "superbonbon": "rare-candy",
    "charme_stabilite": "catch-charm",
    "charme_chroma": "shiny-charm",
    "charme_insigne": "mark-charm",
    "charme_xp": "lucky-egg" # Sprite associé pour le rendu visuel
}


def get_display_name(discord_user: Union[discord.User, discord.Member]) -> str:
    """Retourne le pseudo global (username) comme dans leader.py."""
    if not discord_user:
        return "Dresseur Inconnu"
    return discord_user.name


def format_price(amount: int) -> str:
    return f"{amount:,}".replace(",", " ")


def get_font(size: int):
    """Charge la police Pokemon.ttf depuis le dossier cogs."""
    try:
        return ImageFont.truetype("cogs/Pokemon.ttf", size)
    except IOError:
        return ImageFont.load_default()


def load_fallback_font(size: int):
    """Charge une police classique (Arial) pour le pseudo et le Pokédollar."""
    for font_name in ["arial.ttf", "DejaVuSans.ttf", "FreeSans.ttf", "LiberationSans-Regular.ttf"]:
        try:
            return ImageFont.truetype(font_name, size)
        except IOError:
            continue
    return ImageFont.load_default()


async def fetch_sprite(session: aiohttp.ClientSession, p_id: int, is_shiny: bool):
    """Récupère le sprite du Pokémon depuis l'API officielle."""
    sprite_path = "shiny/" if is_shiny else ""
    url = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{sprite_path}{p_id}.png"
    try:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.read()
                img = Image.open(io.BytesIO(data)).convert("RGBA")
                return img.resize((90, 90), Image.Resampling.NEAREST)
    except Exception:
        pass
    return None


async def fetch_item_sprite(session: aiohttp.ClientSession, api_name: str):
    """Récupère l'icône de l'objet depuis l'API officielle."""
    url = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/items/{api_name}.png"
    try:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.read()
                img = Image.open(io.BytesIO(data)).convert("RGBA")
                return img.resize((40, 40), Image.Resampling.LANCZOS)
    except Exception:
        pass
    return None


def create_circular_avatar(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Rend l'avatar circulaire."""
    img = img.resize(size, Image.Resampling.LANCZOS).convert("RGBA")
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0) + size, fill=255)
    result = Image.new("RGBA", size, (0, 0, 0, 0))
    result.paste(img, (0, 0), mask)
    return result


async def generate_profile_card(session: aiohttp.ClientSession, user: discord.abc.User, 
                                level: int, xp: int, balance: int, dex_c: int, dex_s: int, 
                                recent_pokemon: list, user_row: dict, now: float, item_sprites: dict) -> io.BytesIO:
    """Génère l'image de la Carte de Dresseur."""
    width, height = 1200, 1350
    canvas = Image.new("RGBA", (width, height), (43, 45, 49, 255))
    draw = ImageDraw.Draw(canvas)
    
    font_pseudo = load_fallback_font(40)
    font_title = get_font(40)
    font_subtitle = get_font(30)
    font_text = get_font(24)
    font_small = get_font(20)
    font_inventory = get_font(24)
    
    font_arial = load_fallback_font(26) 
    font_footer = load_fallback_font(18)

    # Contour de la carte
    draw.rounded_rectangle([10, 10, width - 10, height - 10], radius=25, outline=(52, 152, 219), width=5)

    # ==========================================
    #             PARTIE HAUTE
    # ==========================================
    if user.display_avatar:
        try:
            avatar_bytes = await user.display_avatar.with_size(128).read()
            avatar_img = create_circular_avatar(Image.open(io.BytesIO(avatar_bytes)), (150, 150))
            canvas.paste(avatar_img, (60, 40), avatar_img)
        except Exception:
            pass

    # Utilisation du pseudo global (username) identique à leader.py
    pseudo = get_display_name(user)

    now_dt = datetime.datetime.now(datetime.timezone.utc).astimezone(ZoneInfo("Europe/Paris"))
    header_date_str = now_dt.strftime("%d/%m/%Y - %H:%M")
    bbox_date = draw.textbbox((0, 0), header_date_str, font=font_small)
    date_width = bbox_date[2] - bbox_date[0]
    draw.text((width - 40 - date_width, 40), header_date_str, font=font_small, fill=(150, 150, 150, 255))

    draw.text((250, 50), pseudo, font=font_pseudo, fill=(255, 255, 255, 255))
    draw.text((250, 100), f"Niveau {level}", font=font_text, fill=(52, 152, 219, 255))

    xp_required = level * 100
    draw.text((250, 140), f"XP: {format_price(xp)} / {format_price(xp_required)}", font=font_small, fill=(200, 200, 200))
    
    # Barre d'XP élargie
    bar_x, bar_y, bar_w, bar_h = 250, 170, 850, 18
    draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], radius=9, fill=(30, 30, 30))
    fill_w = min(bar_w, int(bar_w * (xp / xp_required)))
    if fill_w > 0:
        draw.rounded_rectangle([bar_x, bar_y, bar_x + fill_w, bar_y + bar_h], radius=9, fill=(46, 204, 113))

    y_stats = 230
    x_stats = 60
    
    solde_base = f"💰 Solde : {format_price(balance)} "
    bbox_solde = draw.textbbox((0, 0), solde_base, font=font_text)
    w_solde = bbox_solde[2] - bbox_solde[0]
    
    draw.text((x_stats, y_stats), solde_base, font=font_text, fill=(241, 196, 15))
    draw.text((x_stats + w_solde, y_stats - 2), "₽", font=font_arial, fill=(241, 196, 15)) 
    
    draw.text((x_stats, y_stats + 45), f"📖 Pokédex Classique : {format_price(dex_c)} / 1025", font=font_text, fill=(231, 76, 60))
    draw.text((x_stats, y_stats + 90), f"✨ Pokédex Shiny : {format_price(dex_s)} / 1025", font=font_text, fill=(155, 89, 182))

    draw.line([(40, 380), (width - 40, 380)], fill=(80, 80, 80), width=3)

    # ==========================================
    #             PARTIE CENTRALE (SAC À DOS)
    # ==========================================
    x_icon = 60
    x_label = 120
    # x_qty est resserré à 420 pour que l'espace après les mots plus longs (ex: Charme Stabilité) soit esthétique
    x_qty = 600
    
    draw.text((x_icon, 410), "🎒 Objets Classiques", font=font_subtitle, fill=(52, 152, 219))
    
    y_bag = 480
    
    # Objets classiques (Balls)
    for k in BALL_FIELDS:
        qty = user_row[k] if user_row and k in user_row.keys() else 0
        label = BALL_LABELS.get(k, k.capitalize())
        
        sprite = item_sprites.get(k)
        if sprite:
            canvas.paste(sprite, (x_icon, y_bag - 10), sprite)
            
        draw.text((x_label, y_bag), label, font=font_inventory, fill="white")
        draw.text((x_qty, y_bag), f"{format_price(qty)}", font=font_inventory, fill="white")
        y_bag += 55
        
    # Superbonbon
    sb_qty = user_row["superbonbon"] if user_row and "superbonbon" in user_row.keys() else 0
    sprite_sb = item_sprites.get("superbonbon")
    if sprite_sb:
        canvas.paste(sprite_sb, (x_icon, y_bag - 10), sprite_sb)
    draw.text((x_label, y_bag), "Superbonbon", font=font_inventory, fill="white")
    draw.text((x_qty, y_bag), f"{format_price(sb_qty)}", font=font_inventory, fill="white")
    
    y_bag += 80

    # Charmes
    draw.text((x_icon, y_bag), "✨ Charmes", font=font_subtitle, fill=(52, 152, 219))
    
    y_charm = y_bag + 60
    for k in CHARM_FIELDS:
        qty = user_row[k] if user_row and k in user_row.keys() else 0
        label = CHARM_LABELS.get(k, k.capitalize())
        
        expire_key = f"{k}_expire"
        etat = "Inactif"
        etat_color = (231, 76, 60)
        
        if user_row and expire_key in user_row.keys() and user_row[expire_key] > now:
            remaining_seconds = user_row[expire_key] - now
            hours = int(remaining_seconds // 3600)
            
            if hours >= 1:
                etat = f"{hours}h restantes"
            else:
                minutes = int(remaining_seconds // 60)
                etat = f"{minutes}m restantes"
                
            etat_color = (46, 204, 113)
            
        draw.text((x_label, y_charm), label, font=font_inventory, fill="white")
        
        # Affichage propre de la quantité et du temps restant sans aucun ":"
        qty_text = f"{format_price(qty)} ["
        draw.text((x_qty, y_charm), qty_text, font=font_inventory, fill="white")
        
        bbox_qty = draw.textbbox((0, 0), qty_text, font=font_inventory)
        w_qty = bbox_qty[2] - bbox_qty[0]
        
        draw.text((x_qty + w_qty, y_charm), etat, font=font_inventory, fill=etat_color)
        
        bbox_etat = draw.textbbox((0, 0), etat, font=font_inventory)
        w_etat = bbox_etat[2] - bbox_etat[0]
        
        draw.text((x_qty + w_qty + w_etat, y_charm), "]", font=font_inventory, fill="white")
        
        y_charm += 55

    y_sep_bas = y_charm + 30
    draw.line([(40, y_sep_bas), (width - 40, y_sep_bas)], fill=(80, 80, 80), width=3)

    # ==========================================
    #             PARTIE BASSE (POKÉMONS)
    # ==========================================
    title_stats = "📊 Dernières captures"
    bbox_title = draw.textbbox((0, 0), title_stats, font=font_subtitle)
    draw.text(((width - (bbox_title[2] - bbox_title[0])) // 2, y_sep_bas + 30), title_stats, font=font_subtitle, fill=(52, 152, 219))

    y_recent = y_sep_bas + 100
    
    start_x = 150 
    spacing = 300 
    
    for i, mon in enumerate(recent_pokemon):
        cx = start_x + (i * spacing)
        
        sprite = await fetch_sprite(session, mon['pokemon_id'], mon['is_shiny'])
        if sprite:
            canvas.paste(sprite, (cx - 45, y_recent), sprite)
            
        shiny_star = "✨ " if mon['is_shiny'] else ""
        name_str = f"{shiny_star}{mon['name']}"
        bbox_name = draw.textbbox((0, 0), name_str, font=font_small)
        w_name = bbox_name[2] - bbox_name[0]
        
        draw.text((cx - (w_name // 2), y_recent + 100), name_str, font=font_small, fill="white")
        
        id_str = f"#{mon['pokemon_id']}"
        bbox_id = draw.textbbox((0, 0), id_str, font=font_small)
        w_id = bbox_id[2] - bbox_id[0]
        
        draw.text((cx - (w_id // 2), y_recent + 125), id_str, font=font_small, fill=(150, 150, 150))

    # ==========================================
    #             FOOTER
    # ==========================================

    buffer = io.BytesIO()
    canvas.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


class Profil2Cog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.eco = EconomyService(bot)

    @commands.hybrid_command(name="profil", description="Affiche ton profil complet avec ta carte de dresseur.")
    async def profil2(self, ctx: commands.Context, membre: Union[discord.Member, discord.User] = None):
        await ctx.defer()
        
        # Message d'attente initial identique à leader.py
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
            user = membre or ctx.author
            self.eco.ensure_user(user.id)
            now = time.time()

            with self.eco._get_conn() as conn:
                user_row = conn.execute("SELECT * FROM users WHERE user_id = ?", (user.id,)).fetchone()
                
                try:
                    dex_class_row = conn.execute("SELECT COUNT(DISTINCT pokemon_id) AS c FROM inventory WHERE user_id = ?", (user.id,)).fetchone()
                    dex_classique = dex_class_row["c"] if dex_class_row else 0
                    
                    dex_shiny_row = conn.execute("SELECT COUNT(DISTINCT pokemon_id) AS c FROM inventory WHERE user_id = ? AND is_shiny = 1", (user.id,)).fetchone()
                    dex_shiny = dex_shiny_row["c"] if dex_shiny_row else 0
                except Exception:
                    dex_classique, dex_shiny = 0, 0

                recent_4 = []
                try:
                    recent_4 = conn.execute("SELECT pokemon_id, name, ball, is_shiny FROM inventory WHERE user_id = ? ORDER BY id DESC LIMIT 4", (user.id,)).fetchall()
                except Exception: 
                    pass

            balance_amount = user_row["balance"] if user_row and "balance" in user_row.keys() else 0
            xp_amount = user_row["xp"] if user_row and "xp" in user_row.keys() else 0
            level_amount = user_row["level"] if user_row and "level" in user_row.keys() else 1

            # --- GÉNÉRATION PILLOW ---
            async with aiohttp.ClientSession() as session:
                tasks = [fetch_item_sprite(session, api_name) for api_name in API_ITEMS.values()]
                downloaded_sprites = await asyncio.gather(*tasks)
                item_sprites = dict(zip(API_ITEMS.keys(), downloaded_sprites))

                image_buffer = await generate_profile_card(
                    session, user, level_amount, xp_amount, balance_amount, 
                    dex_classique, dex_shiny, recent_4, 
                    user_row, now, item_sprites
                )
                file = discord.File(fp=image_buffer, filename="trainer_card.png")

            # --- EMBED ---
            if config_manager and hasattr(ctx, "guild") and ctx.guild:
                embed = config_manager.get_formatted_embed(
                    guild=ctx.guild, user=user, bot=self.bot, title="", description=""
                )
            else:
                embed = discord.Embed(title="", color=EMBED_COLOR)
                
            embed.set_footer(text="Astuce: utilise /shop pour acheter des balls ou des charmes")
            embed.set_image(url="attachment://trainer_card.png")

            anim_task.cancel()
            # Utilisation correcte de attachments=[file] pour éviter les exceptions discord.py sur msg.edit()
            await msg.edit(content=None, attachments=[file], embed=embed)

        except Exception as e:
            anim_task.cancel()
            await msg.edit(content=f"❌ Une erreur est survenue lors de la création de la carte : {e}")


async def setup(bot: commands.Bot):
    if bot.get_cog("Profil2Cog"):
        await bot.remove_cog("Profil2Cog")
    await bot.add_cog(Profil2Cog(bot))