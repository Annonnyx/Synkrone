import random
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

import aiohttp
import discord
from discord.ext import commands

try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

try:
    EMBED_COLOR = int(config.get("EMBED_COLOR", "0x2B2D31"), 16)
except NameError:
    EMBED_COLOR = 0x2B2D31

from .utils import BALL_EMOJIS, BALL_FIELDS, BALL_LABELS, EconomyService, CHARM_EMOJIS, CHARM_LABELS

BALL_BASE_RATES = {
    "pokeball": 0.40,
    "superball": 0.60,
    "hyperball": 0.85,
    "masterball": 1.00,
}

RARITY_MOD = {
    "commun": 1.00,
    "rare": 0.70,
    "legendaire": 0.25,
    "fabuleux": 0.15,
}

SHINY_EMOJI = "<:shiny:1522947934969270312>"
POKEBALL_EMOJI = "<:pokeball:1522952715846684782>"
CAPTURE_LIMIT_PER_MINUTE = 10
CAPTURE_WINDOW_SECONDS = 60

@dataclass
class Encounter:
    pokemon_id: int
    species_name: str
    name_fr: str
    sprite_url: str | None
    is_shiny: bool
    rarity: str
    is_evolved: bool
    sexe: str
    is_owned: bool
    is_legendary: bool
    is_mythical: bool


class CaptureBallButton(discord.ui.Button[Any]):
    def __init__(self, ball_key: str):
        super().__init__(style=discord.ButtonStyle.secondary, label="0", emoji=BALL_EMOJIS[ball_key], row=1)
        self.ball_key = ball_key

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, CaptureView):
            await interaction.response.send_message("❌ Vue de capture invalide.", ephemeral=True)
            return
        await view.attempt_capture(interaction, self.ball_key)


class CaptureView(discord.ui.View):
    def __init__(self, cog: "CaptureCog", author: discord.Member | discord.User, encounter: Encounter):
        super().__init__(timeout=300)
        self.cog = cog
        self.author = author
        self.encounter = encounter
        self.caught = False
        self.message: discord.Message | None = None

        self.ball_buttons = {k: CaptureBallButton(k) for k in BALL_FIELDS}
        for key in BALL_FIELDS:
            self.add_item(self.ball_buttons[key])

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Cette capture ne vous appartient pas.", ephemeral=True)
            return False
        return True

    def build_embed(self) -> discord.Embed:
        enc = self.encounter
        
        rarity_text = {
            "fabuleux": "✨ Pokémon Fabuleux",
            "legendaire": "⭐ Pokémon Légendaire",
            "rare": "🔹 Pokémon Rare",
            "commun": "⚪ Pokémon Commun",
        }.get(enc.rarity, "Pokémon")

        shiny_text = f"Shiny {SHINY_EMOJI}" if enc.is_shiny else "Classique"
        evo_text = "Déjà évolué" if enc.is_evolved else "Forme de base"
        shiny_suffix = f" {SHINY_EMOJI}" if enc.is_shiny else ""
        owned_suffix = f" {POKEBALL_EMOJI}" if enc.is_owned else ""
        
        if config_manager:
            guild = self.author.guild if isinstance(self.author, discord.Member) else None
            embed = config_manager.get_formatted_embed(
                guild=guild, 
                user=self.author, 
                bot=self.cog.bot, 
                title="", 
                description=""
            )
        else:
            embed = discord.Embed(color=EMBED_COLOR)
            embed.set_footer(text="Maximum 10 utilisations de !capture par minute")

        embed.set_author(
            name=f"{self.author.display_name} lance une capture sauvage !",
            icon_url=self.author.display_avatar.url
        )

        embed.description = (
            f"# #{enc.pokemon_id} - {enc.sexe} {enc.name_fr}{shiny_suffix}{owned_suffix}\n"
            f"> **{rarity_text}**\n"
            f"> {shiny_text} | {evo_text}\n"
        )
        
        active_charms = self.cog.eco.get_active_charms(self.author.id)
        if active_charms:
            charms_text = "\n".join([f"-# {CHARM_EMOJIS[k]} {CHARM_LABELS[k]} : Fin <t:{int(expire)}:R>" for k, expire in active_charms.items()])
            embed.add_field(name="Charmes Actifs", value=charms_text, inline=False)
        
        if enc.sprite_url:
            embed.set_image(url=enc.sprite_url)
            
        return embed

    def update_ball_labels(self, user_id: int):
        quantities = self.cog.get_ball_quantities(user_id)
        for key, button in self.ball_buttons.items():
            qte = quantities.get(key, 0)
            button.label = str(qte)
            button.disabled = self.caught or qte <= 0

    async def attempt_capture(self, interaction: discord.Interaction, ball_key: str):
        user_id = interaction.user.id
        self.cog.eco.ensure_user(user_id)

        qty = self.cog.get_ball_quantity(user_id, ball_key)
        if qty <= 0:
            await interaction.response.send_message("❌ Tu n'as pas cette ball.", ephemeral=True)
            return

        self.cog.consume_ball(user_id, ball_key, 1)

        enc = self.encounter
        success = self.cog.roll_capture(enc, ball_key, user_id)

        self.update_ball_labels(user_id)
        embed = self.build_embed()

        if success:
            self.caught = True
            level = random.randint(8, 16) if enc.is_evolved else random.randint(1, 8)
            
            self.cog.eco.add_inventory_item(
                user_id=user_id, 
                pokemon_id=enc.pokemon_id, 
                name=enc.name_fr,
                is_shiny=enc.is_shiny, 
                legendary=enc.is_legendary,
                mythical=enc.is_mythical,
                sexe=enc.sexe,
                ball=ball_key,
                level=level
            )
            
            for button in self.ball_buttons.values():
                button.disabled = True
            embed.add_field(name="Résultat", value=f"✅ Capture réussie avec **{BALL_LABELS[ball_key]}** !", inline=False)
        else:
            embed.add_field(name="Résultat", value=f"❌ La **{BALL_LABELS[ball_key]}** a échoué...", inline=False)

        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class CaptureCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.eco = EconomyService(bot)
        self.capture_attempts: dict[int, deque[float]] = {}

    def _get_recent_attempts(self, user_id: int) -> deque[float]:
        now = time.time()
        attempts = self.capture_attempts.setdefault(user_id, deque())
        while attempts and now - attempts[0] > CAPTURE_WINDOW_SECONDS:
            attempts.popleft()
        return attempts

    def get_remaining_cooldown(self, user_id: int) -> int:
        attempts = self._get_recent_attempts(user_id)
        if len(attempts) >= CAPTURE_LIMIT_PER_MINUTE:
            return int(CAPTURE_WINDOW_SECONDS - (time.time() - attempts[0]))
        return 0

    def register_capture_attempt(self, user_id: int):
        attempts = self._get_recent_attempts(user_id)
        attempts.append(time.time())

    def get_ball_quantities(self, user_id: int) -> dict[str, int]:
        with self.eco._get_conn() as conn:
            row = conn.execute("SELECT pokeball, superball, hyperball, masterball FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if not row:
                return {k: 0 for k in BALL_FIELDS}
            return {k: int(row[k]) for k in BALL_FIELDS}

    def get_ball_quantity(self, user_id: int, ball_key: str) -> int:
        return self.get_ball_quantities(user_id).get(ball_key, 0)

    def consume_ball(self, user_id: int, ball_key: str, amount: int = 1):
        with self.eco._get_conn() as conn:
            conn.execute(f"UPDATE users SET {ball_key} = MAX(0, {ball_key} - ?) WHERE user_id = ?", (amount, user_id))

    def is_pokemon_owned(self, user_id: int, pokemon_id: int) -> bool:
        with self.eco._get_conn() as conn:
            row = conn.execute("SELECT 1 FROM inventory WHERE user_id = ? AND pokemon_id = ? LIMIT 1", (user_id, pokemon_id)).fetchone()
            return bool(row)

    def roll_capture(self, encounter: Encounter, ball_key: str, user_id: int) -> bool:
        if ball_key == "masterball":
            return True

        base = BALL_BASE_RATES.get(ball_key, 0.35)
        rarity_factor = RARITY_MOD.get(encounter.rarity, 1.00)
        evolved_factor = 0.85 if encounter.is_evolved else 1.00
        
        rate = base * rarity_factor * evolved_factor
        
        active_charms = self.eco.get_active_charms(user_id)
        if "charme_stabilite" in active_charms:
            rate *= 5
            
        rate = min(0.99, max(0.02, rate))
        return random.random() <= rate

    async def fetch_species_name_fr(self, session: aiohttp.ClientSession, species_json: dict[str, Any], fallback: str) -> str:
        names = species_json.get("names", [])
        return next((n["name"] for n in names if n.get("language", {}).get("name") == "fr"), fallback)

    async def random_from_category(self, session: aiohttp.ClientSession, category: str) -> tuple[dict[str, Any], dict[str, Any]]:
        for _ in range(30):
            pid = random.randint(1, 1025)
            async with session.get(f"https://pokeapi.co/api/v2/pokemon/{pid}") as rp:
                if rp.status != 200:
                    continue
                pokemon_data = await rp.json()

            async with session.get(f"https://pokeapi.co/api/v2/pokemon-species/{pokemon_data['id']}") as rs:
                if rs.status != 200:
                    continue
                species_data = await rs.json()

            is_myth = bool(species_data.get("is_mythical"))
            is_legend = bool(species_data.get("is_legendary"))
            is_evolved = species_data.get("evolves_from_species") is not None

            if category == "fabuleux" and is_myth:
                return pokemon_data, species_data
            if category == "legendaire" and is_legend and not is_myth:
                return pokemon_data, species_data
            if category == "evolved" and is_evolved:
                return pokemon_data, species_data
            if category == "any":
                return pokemon_data, species_data

        pid = random.randint(1, 1025)
        async with session.get(f"https://pokeapi.co/api/v2/pokemon/{pid}") as rp:
            pokemon_data = await rp.json()
        async with session.get(f"https://pokeapi.co/api/v2/pokemon-species/{pokemon_data['id']}") as rs:
            species_data = await rs.json()
        return pokemon_data, species_data

    async def build_encounter(self, session: aiohttp.ClientSession, user_id: int) -> Encounter:
        roll = random.random()
        active_charms = self.eco.get_active_charms(user_id)
        
        # --- TAUX APPARITION REVUS (Base très faible, Charme = 1/50) ---
        fabuleux_threshold = 0.02 if "charme_insigne" in active_charms else 0.004
        legendaire_threshold = 0.04 if "charme_insigne" in active_charms else 0.01
        
        if roll < fabuleux_threshold:
            target = "fabuleux"
        elif roll < legendaire_threshold:
            target = "legendaire"
        elif roll < 0.30:
            target = "evolved"
        else:
            target = "any"

        pokemon_data, species_data = await self.random_from_category(session, target)

        is_evolved = species_data.get("evolves_from_species") is not None
        is_mythical = bool(species_data.get("is_mythical"))
        is_legendary = bool(species_data.get("is_legendary"))

        if is_mythical:
            rarity = "fabuleux"
        elif is_legendary:
            rarity = "legendaire"
        elif is_evolved:
            rarity = "rare"
        else:
            rarity = "rare" if random.random() < 0.15 else "commun"

        # --- APPLICATION DU CHARME CHROMA (Shiny = 1/100) ---
        shiny_chance = (1 / 100) if "charme_chroma" in active_charms else (1 / 256)
        is_shiny = random.random() < shiny_chance
        
        gender_rate = species_data.get("gender_rate", -1)
        if gender_rate == -1:
            sexe = "⚲"
        elif gender_rate == 0:
            sexe = "♂"
        elif gender_rate == 8:
            sexe = "♀"
        else:
            sexe = "♀" if random.random() < (gender_rate / 8.0) else "♂"

        name_fr = await self.fetch_species_name_fr(session, species_data, pokemon_data["name"].capitalize())
        sprite_key = "front_shiny" if is_shiny else "front_default"
        artwork = pokemon_data.get("sprites", {}).get("other", {}).get("official-artwork", {})
        sprite_url = artwork.get(sprite_key) or pokemon_data.get("sprites", {}).get(sprite_key)
        is_owned = self.is_pokemon_owned(user_id, pokemon_data["id"])

        return Encounter(
            pokemon_id=int(pokemon_data["id"]),
            species_name=species_data["name"],
            name_fr=name_fr,
            sprite_url=sprite_url,
            is_shiny=is_shiny,
            rarity=rarity,
            is_evolved=is_evolved,
            sexe=sexe,
            is_owned=is_owned,
            is_legendary=is_legendary,
            is_mythical=is_mythical
        )

    @commands.hybrid_command(name="capture", description="Fait apparaitre 1 Pokémon sauvage et tente une capture.")
    async def capture(self, ctx: commands.Context[commands.Bot]):
        await ctx.defer()
        
        self.eco.ensure_user(ctx.author.id)

        cooldown = self.get_remaining_cooldown(ctx.author.id)
        if cooldown > 0:
            await ctx.send(
                f"❌ Limite atteinte: 10 utilisations de !capture par minute. Réessaie dans **{cooldown} secondes**.",
                reference=ctx.message,
            )
            return
            
        self.register_capture_attempt(ctx.author.id)

        timeout = aiohttp.ClientTimeout(total=120)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            encounter = await self.build_encounter(session, ctx.author.id)

        view = CaptureView(self, ctx.author, encounter)
        view.update_ball_labels(ctx.author.id)
        embed = view.build_embed()

        if ctx.interaction:
            msg = await ctx.interaction.followup.send(embed=embed, view=view, wait=True)
        else:
            msg = await ctx.send(embed=embed, view=view, reference=ctx.message, mention_author=True)
        view.message = msg

async def setup(bot: commands.Bot):
    if bot.get_cog("CaptureCog"):
        await bot.remove_cog("CaptureCog")
    await bot.add_cog(CaptureCog(bot))