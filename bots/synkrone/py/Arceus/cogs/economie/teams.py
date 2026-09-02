import io
import re
import asyncio
from datetime import datetime, timedelta
from typing import Any

import aiohttp
import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

try:
    EMBED_COLOR = int(config.get("EMBED_COLOR", "0x2B2D31"), 16)
except NameError:
    EMBED_COLOR = 0x2B2D31

from .utils import EconomyService

SHINY_EMOJI = "<:shiny:1522947934969270312>"
POKEBALL_EMOJI = "<:pokeball:1522952715846684782>"

class TeamsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.eco = EconomyService(bot)

    def set_team_from_inputs(self, user_id: int, inputs: list[str]) -> tuple[bool, str]:
        if len(inputs) != 3:
            return False, "❌ Tu dois renseigner exactement 3 Pokémon."
        
        parsed_slots = []
        for val in inputs:
            val_clean = val.lower().strip()
            is_shiny = val_clean.startswith('s')
            try:
                pokemon_id = int(re.sub(r"\D", "", val_clean))
            except ValueError:
                return False, f"❌ L'entrée `{val}` n'est pas un ID de Pokémon valide."
            parsed_slots.append((pokemon_id, is_shiny))

        if len(set(parsed_slots)) != 3:
            return False, "❌ Tu ne peux pas utiliser deux fois le même Pokémon identique dans ton équipe."

        with self.eco._get_conn() as conn:
            inventory_ids_to_use = []
            
            for pokemon_id, is_shiny in parsed_slots:
                row = conn.execute(
                    "SELECT id FROM inventory WHERE user_id = ? AND pokemon_id = ? AND is_shiny = ? LIMIT 1",
                    (user_id, pokemon_id, int(is_shiny)),
                ).fetchone()
                
                if not row:
                    shiny_str = " Shiny" if is_shiny else ""
                    return False, f"❌ Tu ne possèdes pas de Pokémon avec l'ID Pokedex #{pokemon_id}{shiny_str} dans ton inventaire."
                
                inventory_id = row["id"]

                in_daycare = conn.execute(
                    "SELECT 1 FROM daycare WHERE user_id = ? AND pokemon_inv_id = ?",
                    (user_id, inventory_id),
                ).fetchone()
                if in_daycare:
                    return False, f"❌ Ton Pokémon #{pokemon_id} est actuellement à la garderie."
                
                inventory_ids_to_use.append(inventory_id)

            conn.execute("DELETE FROM teams WHERE user_id = ?", (user_id,))
            for slot, inv_id in enumerate(inventory_ids_to_use, start=1):
                conn.execute(
                    "INSERT OR REPLACE INTO teams (user_id, slot, inventory_id) VALUES (?, ?, ?)",
                    (user_id, slot, inv_id),
                )

        return True, "✅ Équipe mise à jour avec succès !"

    async def animate_loading(self, message: discord.Message | discord.Interaction, stop_event: asyncio.Event):
        """Anime le texte de chargement avec des points de suspension."""
        states = [".", "..", "..."]
        i = 0
        while not stop_event.is_set():
            content = f"Initialisation des données{states[i % 3]}"
            try:
                if isinstance(message, discord.Message):
                    await message.edit(content=content)
                else:
                    await message.edit_original_response(content=content)
            except discord.HTTPException:
                pass
            i += 1
            try:
                # Pause de 1 seconde entre chaque frame d'animation
                await asyncio.wait_for(stop_event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass

    async def generate_team_image(self, session: aiohttp.ClientSession, team: list, user: discord.Member | discord.User) -> discord.File | None:
        if not team:
            return None
        
        # Récupération du niveau du joueur
        user_level = 1
        with self.eco._get_conn() as conn:
            row = conn.execute("SELECT level FROM users WHERE user_id = ?", (user.id,)).fetchone()
            if row:
                user_level = row["level"]
        
        try:
            canvas = Image.open("cogs/teams.jpg").convert("RGBA")
        except Exception:
            canvas = Image.new("RGBA", (900, 360), (43, 45, 49, 255))
            
        W, H = canvas.size
        
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        draw_overlay = ImageDraw.Draw(overlay)
        
        # Ajout d'une police "medium" pour gérer la réduction d'échelle des noms longs
        try:
            font_large = ImageFont.truetype("cogs/Pokemon.ttf", 24)
            font_medium = ImageFont.truetype("cogs/Pokemon.ttf", 20)
            font_small = ImageFont.truetype("cogs/Pokemon.ttf", 16)
            font_tiny = ImageFont.truetype("cogs/Pokemon.ttf", 14)
        except Exception:
            font_large = ImageFont.load_default()
            font_medium = ImageFont.load_default()
            font_small = ImageFont.load_default()
            font_tiny = ImageFont.load_default()

        async def fetch_pokemon_data(mon):
            sprite_path = "shiny/" if getattr(mon, "is_shiny", False) else ""
            url = f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{sprite_path}{mon.pokemon_id}.png"
            sprite_data = None
            try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        sprite_data = await resp.read()
            except Exception:
                pass
            
            name_fr = await self.eco.get_species_name_fr(session, mon.pokemon_id)
            return (mon, sprite_data, name_fr)

        avatar_task = user.display_avatar.replace(size=128, format="png").read()
        team_tasks = [fetch_pokemon_data(mon) for mon in team[:3]]
        
        results = await asyncio.gather(avatar_task, *team_tasks, return_exceptions=True)
        avatar_bytes = results[0]
        team_results = results[1:]

        # 1. Rendu Utilisateur (Avec le niveau)
        if not isinstance(avatar_bytes, Exception):
            try:
                avatar_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
                avatar_img = avatar_img.resize((80, 80))
                
                avatar_x = W - 110
                avatar_y = 20
                canvas.paste(avatar_img, (avatar_x, avatar_y), avatar_img)
                
                text_base_x = avatar_x - 20
                username = user.name
                level_text = f"Niv. {user_level}"
                
                # Alignement à droite pour coller à l'avatar
                draw_overlay.text((text_base_x, avatar_y + 15), username, font=font_large, fill="white", anchor="ra", stroke_width=2, stroke_fill="black")
                draw_overlay.text((text_base_x, avatar_y + 45), level_text, font=font_small, fill="white", anchor="ra", stroke_width=1, stroke_fill="black")
            except Exception:
                pass

        # 2. Containers individuels
        box_width = 200
        box_height = 220
        total_boxes_width = (box_width * 3) + (40 * 2)
        start_x = (W - total_boxes_width) // 2
        box_y = 110
        sprite_size = 160
        
        for i, result in enumerate(team_results):
            if isinstance(result, Exception):
                continue
                
            mon, sprite_data, name_fr = result
            is_shiny = getattr(mon, "is_shiny", False)
            box_x = start_x + i * (box_width + 40)
            
            # --- Dessin du Container ---
            if is_shiny:
                # Bordure Shiny plus simple et cohérente : lueur extérieure dorée + bordure or vif
                draw_overlay.rounded_rectangle([box_x-3, box_y-3, box_x+box_width+3, box_y+box_height+3], radius=18, outline=(255, 215, 0, 100), width=4)
                draw_overlay.rounded_rectangle([box_x, box_y, box_x+box_width, box_y+box_height], fill=(0, 0, 0, 160), radius=15, outline=(255, 223, 0, 255), width=2)
            else:
                draw_overlay.rounded_rectangle([box_x, box_y, box_x+box_width, box_y+box_height], fill=(0, 0, 0, 160), radius=15, outline=(255, 255, 255, 60), width=2)

        canvas = Image.alpha_composite(canvas, overlay)
        draw = ImageDraw.Draw(canvas)

        for i, result in enumerate(team_results):
            if isinstance(result, Exception):
                continue
                
            mon, sprite_data, name_fr = result
            is_shiny = getattr(mon, "is_shiny", False)
            
            box_x = start_x + i * (box_width + 40)
            center_x = box_x + (box_width // 2)
            
            # Sprite
            if sprite_data:
                try:
                    sprite_img = Image.open(io.BytesIO(sprite_data)).convert("RGBA")
                    sprite_img = sprite_img.resize((sprite_size, sprite_size))
                    sprite_x = center_x - (sprite_size // 2)
                    sprite_y = box_y + 10
                    canvas.paste(sprite_img, (sprite_x, sprite_y), sprite_img)
                except Exception:
                    pass

            # Textes sous le Pokémon
            display_name = mon.name if mon.name and mon.name != "Inconnu" else name_fr
            shiny_sym = "✨" if is_shiny else ""
            id_text = f"#{mon.pokemon_id} {shiny_sym}"
            
            # Gestion dynamique de la taille du nom pour éviter de déborder
            name_font = font_large
            if len(display_name) >= 2:
                name_font = font_small
            elif len(display_name) >= 1:
                name_font = font_medium
            
            draw.text((center_x, box_y + box_height - 50), display_name, font=name_font, fill="white", anchor="mt", stroke_width=2, stroke_fill="black")
            draw.text((center_x, box_y + box_height - 25), id_text, font=font_small, fill="white", anchor="mt", stroke_width=1, stroke_fill="black")

        # 3. Ajout de la date et l'heure (VPS + 2h)
        current_time = datetime.now() + timedelta(hours=2)
        time_str = current_time.strftime("%d/%m/%y - %H:%M")
        draw.text((W - 10, H - 10), time_str, font=font_tiny, fill=(255, 255, 255, 180), anchor="rd", stroke_width=1, stroke_fill="black")

        buffer = io.BytesIO()
        canvas.save(buffer, format="PNG", optimize=True)
        buffer.seek(0)
        return discord.File(fp=buffer, filename="team.png")

    async def build_team_embed(self, user: discord.Member | discord.User) -> tuple[discord.Embed, discord.File | None]:
        self.eco.ensure_user(user.id)
        team = self.eco.get_user_team(user.id)

        if config_manager:
            guild = user.guild if isinstance(user, discord.Member) else None
            embed = config_manager.get_formatted_embed(
                guild=guild, user=user, bot=self.bot, title="", description=""
            )
        else:
            embed = discord.Embed(color=EMBED_COLOR)
            embed.set_footer(text="Par défaut, vos 3 premières captures sont utilisées.")

        embed.set_author(name=f"Équipe ⚔️ {user.display_name}", icon_url=user.display_avatar.url)

        file = None
        if team:
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                file = await self.generate_team_image(session, team, user)
                if file:
                    embed.set_image(url="attachment://team.png")

        return embed, file

    @commands.hybrid_command(name="teams", aliases=["team"], description="Affiche et configure ton équipe PvP.")
    async def teams(self, ctx: commands.Context[commands.Bot]):
        self.eco.ensure_user(ctx.author.id)
        
        loading_msg = await ctx.send("Initialisation des données.")
        stop_event = asyncio.Event()
        anim_task = asyncio.create_task(self.animate_loading(loading_msg, stop_event))
        
        embed, file = await self.build_team_embed(ctx.author)
        current_team = self.eco.get_user_team(ctx.author.id)
        view = TeamManageView(self, ctx.author.id, current_team)
        
        stop_event.set()
        await anim_task
        
        kwargs = {"content": "", "embed": embed, "view": view}
        if file:
            kwargs["attachments"] = [file]
            
        await loading_msg.edit(**kwargs)
        view.message = loading_msg


class TeamSetupModal(discord.ui.Modal, title="Configuration de l'Équipe"):
    def __init__(self, cog: TeamsCog, author_id: int, view: "TeamManageView", current_team: list):
        super().__init__()
        self.cog = cog
        self.author_id = author_id
        self.view_ref = view
        
        inputs_text = ["", "", ""]
        for mon in current_team:
            if 1 <= mon.slot <= 3:
                prefix = "s" if getattr(mon, "is_shiny", False) else ""
                inputs_text[mon.slot - 1] = f"{prefix}{mon.pokemon_id}"

        self.slot1 = discord.ui.TextInput(
            label="Pokémon - Emplacement 1 (ID Pokedex)", placeholder="Ex: 150 ou s150 pour shiny", default=inputs_text[0], required=True, max_length=15
        )
        self.slot2 = discord.ui.TextInput(
            label="Pokémon - Emplacement 2 (ID Pokedex)", placeholder="Ex: 151", default=inputs_text[1], required=True, max_length=15
        )
        self.slot3 = discord.ui.TextInput(
            label="Pokémon - Emplacement 3 (ID Pokedex)", placeholder="Ex: 25", default=inputs_text[2], required=True, max_length=15
        )
        
        self.add_item(self.slot1)
        self.add_item(self.slot2)
        self.add_item(self.slot3)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Ce formulaire ne t'appartient pas.", ephemeral=True)
            return

        raw_inputs = [self.slot1.value.strip(), self.slot2.value.strip(), self.slot3.value.strip()]
        success, message = self.cog.set_team_from_inputs(interaction.user.id, raw_inputs)
        
        if not success:
            await interaction.response.send_message(message, ephemeral=True)
            return

        await interaction.response.send_message("Initialisation des données.", ephemeral=True)
        stop_event = asyncio.Event()
        anim_task = asyncio.create_task(self.cog.animate_loading(interaction, stop_event))

        embed, file = await self.cog.build_team_embed(interaction.user)
        self.view_ref.current_team = self.cog.eco.get_user_team(interaction.user.id)

        stop_event.set()
        await anim_task

        await interaction.edit_original_response(content=message)
        if self.view_ref.message:
            try:
                if file:
                    await self.view_ref.message.edit(embed=embed, view=self.view_ref, attachments=[file])
                else:
                    await self.view_ref.message.edit(embed=embed, view=self.view_ref)
            except discord.HTTPException:
                pass


class TeamManageView(discord.ui.View):
    def __init__(self, cog: TeamsCog, author_id: int, current_team: list):
        super().__init__(timeout=300)
        self.cog = cog
        self.author_id = author_id
        self.current_team = current_team
        self.message: discord.Message | None = None
        
        self.open_modal.emoji = POKEBALL_EMOJI

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Cette interface ne t'appartient pas.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Définir ma team", style=discord.ButtonStyle.primary)
    async def open_modal(self, interaction: discord.Interaction, _: discord.ui.Button[Any]):
        await interaction.response.send_modal(TeamSetupModal(self.cog, self.author_id, self, self.current_team))

    @discord.ui.button(label="Conseil", style=discord.ButtonStyle.secondary, emoji="💡")
    async def conseil_btn(self, interaction: discord.Interaction, _: discord.ui.Button[Any]):
        advice_text = (
            "ℹ️ **Comment ajouter un Pokémon à votre équipe ?**\n\n"
            "• **Pokémon Classique** : Renseigne simplement son ID Pokedex (ex: `25` pour Pikachu).\n"
            "• **Pokémon Shiny** : Ajoute un `s` juste avant l'ID (ex: `s25`).\n\n"
            "⚠️ *Astuce :* Utilise la commande `/pokedex` pour visualiser la liste des Pokémon que tu possèdes."
        )
        await interaction.response.send_message(advice_text, ephemeral=True)

    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


async def setup(bot: commands.Bot):
    if bot.get_cog("TeamsCog"):
        await bot.remove_cog("TeamsCog")
    await bot.add_cog(TeamsCog(bot))