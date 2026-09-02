import io
import math
import asyncio
import textwrap
from typing import Any, cast, Union

import aiohttp
import discord
from discord import ui, app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

from .utils import EconomyService

try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

try:
    EMBED_COLOR = int(config.get("EMBED_COLOR", "0x2B2D31"), 16)
except NameError:
    EMBED_COLOR = 0x2B2D31

# --- CONFIGURATION VISUELLE ---
GRID_COLS, GRID_ROWS = 6, 5
CELL_SIZE = 160
MARGIN = 20
POKEDEX_SIZE = (
    GRID_COLS * CELL_SIZE + (GRID_COLS + 1) * MARGIN,
    GRID_ROWS * CELL_SIZE + (GRID_ROWS + 1) * MARGIN
)

GENERATIONS = {
    "all": (1, 1025, "Toutes les générations"),
    "gen1": (1, 151, "Génération 1"),
    "gen2": (152, 251, "Génération 2"),
    "gen3": (252, 386, "Génération 3"),
    "gen4": (387, 493, "Génération 4"),
    "gen5": (494, 649, "Génération 5"),
    "gen6": (650, 721, "Génération 6"),
    "gen7": (722, 809, "Génération 7"),
    "gen8": (810, 905, "Génération 8"),
    "gen9": (906, 1025, "Génération 9"),
}

POKEDEX_EMOJI = "<:pokedex:1523703818603335821>"
SHINY_EMOJI = "<:shiny:1522947934969270312>"

# --- CACHE EN MÉMOIRE POUR ACCÉLÉRER LA NAVIGATION ---
SPRITE_CACHE = {}
NAME_CACHE = {}

def get_font(size: int):
    """Essaie de charger une police lisible, sinon utilise celle par défaut."""
    for font_name in ["arial.ttf", "DejaVuSans.ttf", "tahoma.ttf", "cogs/Pokemon.ttf"]:
        try:
            return ImageFont.truetype(font_name, size)
        except IOError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()

async def fetch_pokemon_data(session: aiohttp.ClientSession, eco: EconomyService, p_id: int, is_shiny: bool):
    """Récupère le nom et le sprite d'un Pokémon de manière asynchrone, avec mise en cache."""
    # 1. Récupération du nom
    if p_id not in NAME_CACHE:
        NAME_CACHE[p_id] = await eco.get_species_name_fr(session, p_id)
    name = NAME_CACHE[p_id]

    # 2. Récupération du sprite
    cache_key = (p_id, is_shiny)
    if cache_key not in SPRITE_CACHE:
        sprite_path = "shiny/" if is_shiny else ""
        url = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{sprite_path}{p_id}.png"
        
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    img = Image.open(io.BytesIO(data)).convert("RGBA")
                    # Upscale sans flou (Pixel Art)
                    img = img.resize((112, 112), Image.Resampling.NEAREST)
                    SPRITE_CACHE[cache_key] = img
                else:
                    SPRITE_CACHE[cache_key] = None
        except Exception:
            SPRITE_CACHE[cache_key] = None
            
    return p_id, name, SPRITE_CACHE[cache_key]

async def generate_pokedex_image(session: aiohttp.ClientSession, eco: EconomyService, p_ids: list[int], owned_data: dict[int, int], is_shiny: bool):
    """Génère l'image du Pokédex avec 30 Pokémon maximum."""
    img = Image.new("RGB", POKEDEX_SIZE, (43, 45, 49))  # Fond Discord classique
    draw = ImageDraw.Draw(img)
    
    font_id = get_font(18)
    font_name = get_font(20) # Légèrement plus grand
    font_qty = get_font(18)

    tasks = [fetch_pokemon_data(session, eco, p_id, is_shiny) for p_id in p_ids]
    results = await asyncio.gather(*tasks)

    for i, (p_id, name, sprite) in enumerate(results):
        row, col = divmod(i, GRID_COLS)
        x = MARGIN + col * (CELL_SIZE + MARGIN)
        y = MARGIN + row * (CELL_SIZE + MARGIN)

        is_owned = p_id in owned_data
        qty = owned_data.get(p_id, 0)
        
        if not is_owned:
            bg_color = (231, 76, 60) # Rouge
        elif qty > 1:
            bg_color = (52, 152, 219) # Bleu
        else:
            bg_color = (46, 204, 113) # Vert
        
        # Fond de la cellule (coins arrondis)
        if hasattr(draw, "rounded_rectangle"):
            draw.rounded_rectangle([x, y, x + CELL_SIZE, y + CELL_SIZE], radius=15, fill=bg_color)
        else:
            draw.rectangle([x, y, x + CELL_SIZE, y + CELL_SIZE], fill=bg_color)
            
        # Contour intérieur subtil
        draw.rectangle([x+4, y+4, x + CELL_SIZE - 4, y + CELL_SIZE - 4], outline=(255, 255, 255, 60), width=1)
        
        # Sprite au centre
        if sprite:
            sprite_x = x + (CELL_SIZE - sprite.width) // 2
            sprite_y = y + (CELL_SIZE - sprite.height) // 2 - 12
            img.paste(sprite, (sprite_x, sprite_y), sprite)
        
        # ID en haut à gauche
        draw.text((x + 10, y + 8), f"#{p_id}", font=font_id, fill="white", stroke_width=1, stroke_fill="black")
        
        # Quantité en HAUT à DROITE si possédé
        if is_owned:
            qty_text = f"x{qty}"
            bbox = draw.textbbox((0, 0), qty_text, font=font_qty)
            text_w = bbox[2] - bbox[0]
            draw.text((x + CELL_SIZE - text_w - 10, y + 8), qty_text, font=font_qty, fill="white", stroke_width=1, stroke_fill="black")
            
        # Nom sur une ou deux lignes en bas
        name_lines = textwrap.wrap(name, width=12)
        if len(name_lines) > 2:
            name_lines = name_lines[:2] # Limite à 2 lignes
            
        line_h = 22 # Hauteur approximative d'une ligne
        start_y = y + CELL_SIZE - 8 - (len(name_lines) * line_h)
        
        for idx, line in enumerate(name_lines):
            line_w = draw.textlength(line, font=font_name)
            line_x = x + (CELL_SIZE - line_w) / 2
            draw.text((line_x, start_y + (idx * line_h)), line, font=font_name, fill="white", stroke_width=1, stroke_fill="black")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


class PokedexJumpModal(ui.Modal, title="Navigation Pokédex"):
    page_input = ui.TextInput(
        label="1. Aller à la page (Optionnel)",
        style=discord.TextStyle.short,
        placeholder="Ex: 5",
        required=False
    )
    id_input = ui.TextInput(
        label="2. OU Chercher par ID (Optionnel)",
        style=discord.TextStyle.short,
        placeholder="Ex: 150 pour Mewtwo",
        required=False
    )

    def __init__(self, view: "PokedexView"):
        super().__init__()
        self.pokedex_view = view

    async def on_submit(self, interaction: discord.Interaction):
        view = self.pokedex_view
        val_id = self.id_input.value.strip()
        val_page = self.page_input.value.strip()

        if val_id and val_id.isdigit():
            target_id = int(val_id)
            if 1 <= target_id <= 1025:
                view.generation = "all"
                view.page = (target_id - 1) // 30
                await view.update_message(interaction)
                return
            else:
                await interaction.response.send_message("❌ Cet ID n'existe pas (1 à 1025).", ephemeral=True)
                return

        if val_page and val_page.isdigit():
            target_page = int(val_page) - 1
            if 0 <= target_page < view.max_pages:
                view.page = target_page
                await view.update_message(interaction)
                return
            else:
                await interaction.response.send_message(f"❌ Page invalide. Choix entre 1 et {view.max_pages}.", ephemeral=True)
                return

        await interaction.response.send_message("❌ Tu dois remplir au moins l'un des deux champs avec un nombre valide.", ephemeral=True)


class PokedexView(ui.View):
    def __init__(self, cog: "PokedexCog", author_id: int, target_user: discord.abc.User, classic_data: dict, shiny_data: dict):
        super().__init__(timeout=180)
        self.cog = cog
        self.author_id = author_id
        self.target_user = target_user
        self.classic_data = classic_data
        self.shiny_data = shiny_data
        
        self.mode = "classic"
        self.generation = "all"
        self.page = 0
        self.message: discord.Message | None = None
        self.animation_task = None
        
        self._build_components()

    @property
    def current_data(self):
        return self.classic_data if self.mode == "classic" else self.shiny_data

    @property
    def max_pages(self):
        start, end, _ = GENERATIONS[self.generation]
        total_mons = end - start + 1
        return math.ceil(total_mons / 30)

    def get_completion_stats(self):
        start, end, gen_name = GENERATIONS[self.generation]
        total_in_gen = end - start + 1
        owned_in_gen = len([pid for pid in self.current_data.keys() if start <= pid <= end])
        return gen_name, owned_in_gen, total_in_gen

    def _build_components(self):
        self.clear_items()
        
        # Sélecteur de Génération
        gen_options = [
            discord.SelectOption(label=name, value=k, emoji=POKEDEX_EMOJI, default=(k == self.generation))
            for k, (_, _, name) in GENERATIONS.items()
        ]
        gen_select = ui.Select(placeholder="Choisir une Génération", options=gen_options, row=0)
        gen_select.callback = self.on_gen_select
        self.add_item(gen_select)

        # Sélecteur de Mode
        mode_options = [
            discord.SelectOption(label="Pokédex Classique", value="classic", emoji=POKEDEX_EMOJI, default=(self.mode == "classic")),
            discord.SelectOption(label="Pokédex Shiny", value="shiny", emoji="✨", default=(self.mode == "shiny"))
        ]
        mode_select = ui.Select(placeholder="Choisir le Mode", options=mode_options, row=1)
        mode_select.callback = self.on_mode_select
        self.add_item(mode_select)

        # Navigation
        btn_prev = ui.Button(label="◀", style=discord.ButtonStyle.primary, row=2, disabled=(self.page == 0))
        btn_prev.callback = self.on_prev

        # Le bouton de page fait maintenant office de bouton "Aller à..."
        btn_page = ui.Button(label=f"Page {self.page + 1} / {self.max_pages} 🔍", style=discord.ButtonStyle.secondary, row=2)
        btn_page.callback = self.on_jump

        btn_next = ui.Button(label="▶", style=discord.ButtonStyle.primary, row=2, disabled=(self.page >= self.max_pages - 1))
        btn_next.callback = self.on_next

        self.add_item(btn_prev)
        self.add_item(btn_page)
        self.add_item(btn_next)
        
    async def loading_animation(self, msg: discord.WebhookMessage):
        dots = 1
        try:
            while True:
                await asyncio.sleep(0.7)
                dots = (dots % 3) + 1
                await msg.edit(content=f"Chargement de la page{'.' * dots}")
        except asyncio.CancelledError:
            try:
                await msg.delete()
            except discord.HTTPException:
                pass

    async def update_message(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        # Déclenchement de l'animation de chargement
        loader_msg = await interaction.followup.send("Chargement de la page.", ephemeral=True)
        self.animation_task = asyncio.create_task(self.loading_animation(loader_msg))
        
        # Sécurité des pages
        self.page = max(0, min(self.page, self.max_pages - 1))
        
        # Reconstruction des boutons (mise à jour du n° de page)
        self._build_components()
        
        start, end, gen_name = GENERATIONS[self.generation]
        p_start = start + (self.page * 30)
        p_end = min(p_start + 30, end + 1)
        p_ids = list(range(p_start, p_end))

        async with aiohttp.ClientSession() as session:
            buffer = await generate_pokedex_image(session, self.cog.eco, p_ids, self.current_data, self.mode == "shiny")
            file = discord.File(buffer, "pokedex.png")
            
            # --- Création de l'Embed ---
            _, owned, total = self.get_completion_stats()
            title_prefix = POKEDEX_EMOJI if self.mode == "classic" else SHINY_EMOJI
            mode_str = "Classique" if self.mode == "classic" else "Shiny"
            
            if config_manager and hasattr(interaction, "guild"):
                embed = config_manager.get_formatted_embed(
                    guild=interaction.guild, 
                    user=interaction.user, 
                    bot=self.cog.bot, 
                    title=f"{title_prefix} Pokédex {mode_str}", 
                    description=""
                )
            else:
                embed = discord.Embed(title=f"{title_prefix} Pokédex {mode_str}", color=EMBED_COLOR)
                embed.set_footer(text="Naviguez entre les pages ou changez de filtre.")

            embed.set_author(
                name=f"{gen_name} | {mode_str} : {owned} / {total}",
                icon_url=self.target_user.display_avatar.url
            )
            embed.set_image(url="attachment://pokedex.png")
            
            await interaction.edit_original_response(embed=embed, attachments=[file], view=self)
            
        # Stop l'animation
        if self.animation_task:
            self.animation_task.cancel()

    async def on_gen_select(self, interaction: discord.Interaction):
        self.generation = interaction.data["values"][0]
        # On ne remet pas systématiquement à 0, la limite sera ajustée dans update_message
        await self.update_message(interaction)

    async def on_mode_select(self, interaction: discord.Interaction):
        self.mode = interaction.data["values"][0]
        await self.update_message(interaction)

    async def on_prev(self, interaction: discord.Interaction):
        self.page -= 1
        await self.update_message(interaction)

    async def on_next(self, interaction: discord.Interaction):
        self.page += 1
        await self.update_message(interaction)

    async def on_jump(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PokedexJumpModal(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Ce Pokédex ne vous appartient pas.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class PokedexCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.eco = EconomyService(bot)

    @commands.hybrid_command(name="pokedex", description="Affiche le Pokédex visuel interactif d'un membre ou le vôtre.")
    async def pokedex(self, ctx: commands.Context, membre: Union[discord.Member, discord.User] = None):
        await ctx.defer()
        
        target_user = membre or ctx.author
        self.eco.ensure_user(target_user.id)
        
        with self.eco._get_conn() as conn:
            rows = conn.execute(
                "SELECT pokemon_id, is_shiny, COUNT(*) as c FROM inventory WHERE user_id = ? GROUP BY pokemon_id, is_shiny",
                (target_user.id,)
            ).fetchall()
            
        classic_data = {r["pokemon_id"]: r["c"] for r in rows if r["is_shiny"] == 0}
        shiny_data = {r["pokemon_id"]: r["c"] for r in rows if r["is_shiny"] == 1}

        # On init la vue (L'auteur reste la personne qui fait la commande pour qu'elle puisse naviguer)
        view = PokedexView(self, ctx.author.id, target_user, classic_data, shiny_data)
        
        # Données du chargement initial (Toutes les Gen, Classique, Page 1)
        p_ids = list(range(1, 31))
        _, owned, total = view.get_completion_stats()
        
        async with aiohttp.ClientSession() as session:
            buffer = await generate_pokedex_image(session, self.eco, p_ids, classic_data, False)
            file = discord.File(buffer, "pokedex.png")
            
            if config_manager and hasattr(ctx, "guild") and ctx.guild:
                embed = config_manager.get_formatted_embed(
                    guild=ctx.guild, 
                    user=target_user, 
                    bot=self.bot, 
                    title=f"{POKEDEX_EMOJI} Pokédex Classique", 
                    description=""
                )
            else:
                embed = discord.Embed(title=f"{POKEDEX_EMOJI} Pokédex Classique", color=EMBED_COLOR)
                embed.set_footer(text="Naviguez entre les pages ou changez de filtre.")
                
            embed.set_author(
                name=f"Toutes les générations | Classique : {owned} / {total}",
                icon_url=target_user.display_avatar.url
            )
            embed.set_image(url="attachment://pokedex.png")
            
            msg = await ctx.send(embed=embed, file=file, view=view, reference=ctx.message)
            view.message = msg


async def setup(bot: commands.Bot):
    if bot.get_cog("PokedexCog"):
        await bot.remove_cog("PokedexCog")
    await bot.add_cog(PokedexCog(bot))