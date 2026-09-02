import random
import re
import traceback
from typing import Any

import aiohttp
import discord
from discord.ext import commands

# Import du manager personnalise pour les embeds (Fallback global)
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None


# ============================================================================
# --------------------------- CONSTANTES ET MAPPING --------------------------
# ============================================================================

SHINY_EMOJI = "<:shiny:1522947934969270312>"
POKEBALL_EMOJI = "<:pokeball:1522952715846684782>"
CLASSIC_EMOJI = "<:rappelmax:1522981827273293834>"

TYPE_TRANSLATION = {
    "normal": "Normal",
    "fire": "Feu",
    "water": "Eau",
    "electric": "Electrik",
    "grass": "Plante",
    "ice": "Glace",
    "fighting": "Combat",
    "poison": "Poison",
    "ground": "Sol",
    "flying": "Vol",
    "psychic": "Psy",
    "bug": "Insecte",
    "rock": "Roche",
    "ghost": "Spectre",
    "dragon": "Dragon",
    "dark": "Tenebres",
    "steel": "Acier",
    "fairy": "Fee",
}

TYPE_EMOJIS = {
    "Feu": "<:feu:1522937171135434833>",
    "Normal": "<:normal:1522937166496534609>",
    "Eau": "<:eau:1522937163249877103>",
    "Electrik": "<:elec:1522937159626264647>",
    "Plante": "<:plante:1522937156874539038>",
    "Glace": "<:glace:1522937153896579072>",
    "Combat": "<:combat:1522937150771826809>",
    "Poison": "<:poison:1522937148167295056>",
    "Sol": "<:sol:1522937144782618634>",
    "Vol": "<:vol:1522937142261710959>",
    "Psy": "<:psy:1522937139741065427>",
    "Insecte": "<:insecte:1522937136649736304>",
    "Roche": "<:roche:1522937133915046051>",
    "Dragon": "<:dragon:1522937131084025918>",
    "Tenebres": "<:tenebres:1522937127279661248>",
    "Acier": "<:acier:1522937124335259658>",
    "Fee": "<:fee:1522937121202245732>",
    "Spectre": "<:spectre:1522937118094131281>",
}

GEN_TO_ARABIC = {
    "i": "1",
    "ii": "2",
    "iii": "3",
    "iv": "4",
    "v": "5",
    "vi": "6",
    "vii": "7",
    "viii": "8",
    "ix": "9",
}


# ============================================================================
# ----------------------------- OUTILS / HELPERS -----------------------------
# ============================================================================

def parse_custom_emoji(emoji_str: str) -> discord.PartialEmoji | None:
    match = re.match(r"^<a?:(?P<name>[^:]+):(?P<id>\d+)>$", emoji_str)
    if not match:
        return None
    return discord.PartialEmoji(name=match.group("name"), id=int(match.group("id")))


def message_is_shiny(message: discord.Message | None) -> bool:
    if not message or not message.embeds:
        return False
    description = message.embeds[0].description or ""
    lines = description.split("\n") if description else []
    title_index = next((i for i, line in enumerate(lines) if line.startswith("# #")), 0)
    return bool(lines) and SHINY_EMOJI in lines[title_index]


def find_path_to_species(
    chain_node: dict[str, Any],
    target_species_name: str,
    path: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]] | None:
    current_path = (path or []) + [chain_node]
    if chain_node["species"]["name"] == target_species_name:
        return current_path

    for child in chain_node.get("evolves_to", []):
        result = find_path_to_species(child, target_species_name, current_path)
        if result:
            return result
    return None


def get_gender_requirement_marker(evolution_details: list[dict[str, Any]]) -> str:
    for detail in evolution_details:
        gender = detail.get("gender")
        if gender == 1:
            return "♀️"
        if gender == 2:
            return "♂️"
    return ""


def format_types_for_option(pokemon_data: dict[str, Any]) -> str:
    translated_types: list[str] = []
    for t in pokemon_data.get("types", []):
        en_type = t["type"]["name"]
        translated_types.append(TYPE_TRANSLATION.get(en_type, en_type.capitalize()))
    return " | ".join(translated_types)[:100] or "Type inconnu"


def harmonize_gender_markers(options: list[dict[str, str]]) -> list[dict[str, str]]:
    if not options:
        return options

    has_male = any(opt.get("gender_marker") == "♂️" for opt in options)
    has_female = any(opt.get("gender_marker") == "♀️" for opt in options)

    if has_male and not has_female:
        for opt in options:
            if not opt.get("gender_marker"):
                opt["gender_marker"] = "♀️"
    elif has_female and not has_male:
        for opt in options:
            if not opt.get("gender_marker"):
                opt["gender_marker"] = "♂️"

    for opt in options:
        marker = opt.get("gender_marker", "")
        if marker:
            opt["label"] = f"{opt['prefix']} : {marker} #{opt['id']} - {opt['name_fr']}"[:100]
        else:
            opt["label"] = f"{opt['prefix']} : #{opt['id']} - {opt['name_fr']}"[:100]

    return options


# ============================================================================
# ----------------------------- LOGIQUE API ----------------------------------
# ============================================================================

async def get_id_from_french_name(session: aiohttp.ClientSession, name: str) -> int | None:
    url = "https://beta.pokeapi.co/graphql/v1beta"
    query = """
    query($name: String!) {
      pokemon_v2_pokemonspeciesname(where: {language_id: {_eq: 5}, name: {_ilike: $name}}, limit: 1) {
        pokemon_species_id
      }
    }
    """
    try:
        payload = {"query": query, "variables": {"name": f"{name.lower()}%"}}
        async with session.post(url, json=payload) as resp:
            if resp.status == 200:
                data = await resp.json()
                results = data.get("data", {}).get("pokemon_v2_pokemonspeciesname", [])
                if results:
                    return results[0]["pokemon_species_id"]
    except Exception:
        pass
    return None


async def get_species_fr_name(session: aiohttp.ClientSession, query: str) -> str:
    try:
        async with session.get(f"https://pokeapi.co/api/v2/pokemon-species/{query}") as resp:
            if resp.status == 200:
                data = await resp.json()
                return next((n["name"] for n in data["names"] if n["language"]["name"] == "fr"), query.capitalize())
    except Exception:
        pass
    return query.capitalize()


async def build_profile_option(
    session: aiohttp.ClientSession,
    species_query: str,
    prefix: str,
    gender_marker: str = "",
) -> dict[str, str] | None:
    try:
        async with session.get(f"https://pokeapi.co/api/v2/pokemon/{species_query}") as resp_pokemon:
            if resp_pokemon.status != 200:
                return None
            pokemon_data = await resp_pokemon.json()

        async with session.get(f"https://pokeapi.co/api/v2/pokemon-species/{pokemon_data['id']}") as resp_species:
            if resp_species.status != 200:
                return None
            species_data = await resp_species.json()

        name_fr = next((n["name"] for n in species_data["names"] if n["language"]["name"] == "fr"), pokemon_data["name"].capitalize())
        if gender_marker:
            label = f"{prefix} : {gender_marker} #{pokemon_data['id']} - {name_fr}"[:100]
        else:
            label = f"{prefix} : #{pokemon_data['id']} - {name_fr}"[:100]

        return {
            "query": species_data["name"],
            "id": str(pokemon_data["id"]),
            "name_fr": name_fr,
            "prefix": prefix,
            "label": label,
            "description": format_types_for_option(pokemon_data),
            "gender_marker": gender_marker,
        }
    except Exception:
        return None


async def generate_pokemon_profile(
    bot: commands.Bot,
    guild: discord.Guild | None,
    author: discord.Member | discord.User,
    query: str | None,
    keep_shiny: bool = False,
):
    timeout = aiohttp.ClientTimeout(total=300)
    query_clean = (query or "").strip().lower().lstrip("0")

    async with aiohttp.ClientSession(timeout=timeout) as session:
        poke_id = query_clean
        if not query_clean:
            poke_id = str(random.randint(1, 1025))
        elif not query_clean.isdigit():
            french_id = await get_id_from_french_name(session, query_clean)
            if french_id:
                poke_id = str(french_id)

        async with session.get(f"https://pokeapi.co/api/v2/pokemon/{poke_id}") as resp_data:
            if resp_data.status != 200:
                return None, None
            data = await resp_data.json()

        async with session.get(f"https://pokeapi.co/api/v2/pokemon-species/{data['id']}") as resp_species:
            if resp_species.status != 200:
                return None, None
            species = await resp_species.json()

        async with session.get(species["evolution_chain"]["url"]) as resp_chain:
            if resp_chain.status != 200:
                return None, None
            chain_data = await resp_chain.json()

        actual_id = data["id"]
        name_fr = next((n["name"] for n in species["names"] if n["language"]["name"] == "fr"), data["name"].capitalize())
        gen_roman = species["generation"]["name"].split("-")[1]
        gen_arabic = GEN_TO_ARABIC.get(gen_roman, gen_roman.upper())

        types_list = []
        for t in data.get("types", []):
            en_type = t["type"]["name"]
            fr_type = TYPE_TRANSLATION.get(en_type, en_type.capitalize())
            emoji = TYPE_EMOJIS.get(fr_type, "❓")
            types_list.append(f"{emoji} {fr_type}")

        rarity_line = ""
        if species.get("is_mythical"):
            rarity_line = "Pokémon Fabuleux\n"
        elif species.get("is_legendary"):
            rarity_line = "Pokémon légendaire\n"

        shiny_suffix = f" {SHINY_EMOJI}" if keep_shiny else ""
        desc_principale = (
            f"{rarity_line}"
            f"# #{actual_id} - {name_fr}{shiny_suffix}\n"
            f"## Génération {gen_arabic}\n"
            f"## Types : {' | '.join(types_list)}\n\n"
        )

        entries_fr = [entry["flavor_text"] for entry in species.get("flavor_text_entries", []) if entry.get("language", {}).get("name") == "fr"]
        if entries_fr:
            desc_fr = entries_fr[0].replace("\n", " ").replace("\f", " ")
            desc_principale += f"```text\n{desc_fr}\n```"

        path = find_path_to_species(chain_data["chain"], species["name"]) or [chain_data["chain"]]
        current_node = path[-1]

        prev_options: list[dict[str, str]] = []
        prev_nodes = list(reversed(path[:-1]))
        for idx, node in enumerate(prev_nodes, start=1):
            option = await build_profile_option(session, node["species"]["name"], prefix=f"Évol. -{idx}")
            if option:
                prev_options.append(option)

        next_options: list[dict[str, str]] = []
        for child in current_node.get("evolves_to", []):
            gender_marker = get_gender_requirement_marker(child.get("evolution_details", []))
            option = await build_profile_option(
                session,
                child["species"]["name"],
                prefix="Évol. +1",
                gender_marker=gender_marker,
            )
            if option:
                next_options.append(option)

        next_options = harmonize_gender_markers(next_options)

        if config_manager:
            embed = config_manager.get_formatted_embed(
                guild=guild,
                user=author,
                bot=bot,
                title="",
                description=desc_principale,
                target_id=guild.id if guild else None,
            )
            footer_text = embed.footer.text if embed.footer and embed.footer.text else ""
            footer_icon = embed.footer.icon_url if embed.footer and embed.footer.icon_url else None
            if footer_text:
                if footer_icon:
                    embed.set_footer(text=footer_text, icon_url=footer_icon)
                else:
                    embed.set_footer(text=footer_text)
        else:
            embed = discord.Embed(description=desc_principale, color=0x2B2D31)

        normal_url = data.get("sprites", {}).get("other", {}).get("official-artwork", {}).get("front_default") or data.get("sprites", {}).get("front_default")
        shiny_url = data.get("sprites", {}).get("other", {}).get("official-artwork", {}).get("front_shiny") or data.get("sprites", {}).get("front_shiny")

        if keep_shiny and shiny_url:
            embed.set_thumbnail(url=shiny_url)
        elif normal_url:
            embed.set_thumbnail(url=normal_url)

        stats_dict = {s["stat"]["name"]: s["base_stat"] for s in data.get("stats", [])}
        embed.add_field(name="❤️ PV", value=f"**{stats_dict.get('hp', 0)}**", inline=True)
        embed.add_field(name="⚔️ ATQ", value=f"**{stats_dict.get('attack', 0)}**", inline=True)
        embed.add_field(name="🛡️ DEF", value=f"**{stats_dict.get('defense', 0)}**", inline=True)
        embed.add_field(name="💨 VIT", value=f"**{stats_dict.get('speed', 0)}**", inline=True)
        embed.add_field(name="🔮 ATQ SPE", value=f"**{stats_dict.get('special-attack', 0)}**", inline=True)
        embed.add_field(name="🌟 DEF SPE", value=f"**{stats_dict.get('special-defense', 0)}**", inline=True)

        view = PokemonProfileView(
            bot=bot,
            author=author,
            normal_url=normal_url,
            shiny_url=shiny_url,
            name_fr=name_fr,
            prev_options=prev_options,
            next_options=next_options,
            initial_shiny=keep_shiny,
        )
        return embed, view


# ============================================================================
# --------------------------- INTERFACE UTILISATEUR --------------------------
# ============================================================================

class PokemonNavButton(discord.ui.Button[Any]):
    def __init__(self, bot: commands.Bot, query: str, label: str):
        super().__init__(style=discord.ButtonStyle.secondary, label=label, emoji=POKEBALL_EMOJI)
        self.bot = bot
        self.query = query

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        keep_shiny = message_is_shiny(interaction.message)
        embed, view = await generate_pokemon_profile(self.bot, interaction.guild, interaction.user, self.query, keep_shiny=keep_shiny)
        if embed and view:
            view.message = interaction.message
            await interaction.message.edit(embed=embed, view=view)
        else:
            await interaction.followup.send("❌ Impossible de charger l'évolution.", ephemeral=True)


class EvolutionSelect(discord.ui.Select[Any]):
    def __init__(self, bot: commands.Bot, placeholder: str, options_data: list[dict[str, str]]):
        pokeball = parse_custom_emoji(POKEBALL_EMOJI)
        options: list[discord.SelectOption] = []
        for opt in options_data:
            options.append(
                discord.SelectOption(
                    label=opt["label"][:100],
                    value=opt["query"],
                    description=opt["description"][:100],
                    emoji=pokeball,
                )
            )

        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        keep_shiny = message_is_shiny(interaction.message)
        query = self.values[0]
        embed, view = await generate_pokemon_profile(self.bot, interaction.guild, interaction.user, query, keep_shiny=keep_shiny)
        if embed and view:
            view.message = interaction.message
            await interaction.message.edit(embed=embed, view=view)
        else:
            await interaction.followup.send("❌ Impossible de charger l'évolution.", ephemeral=True)


class PokemonFormButton(discord.ui.Button[Any]):
    def __init__(self, normal_url: str | None, shiny_url: str | None, name_fr: str, initial_shiny: bool = False):
        self.normal_url = normal_url
        self.shiny_url = shiny_url
        self.name_fr = name_fr
        self.is_shiny = initial_shiny
        if self.is_shiny:
            super().__init__(style=discord.ButtonStyle.primary, label="Afficher classique", emoji=CLASSIC_EMOJI)
        else:
            super().__init__(style=discord.ButtonStyle.primary, label="Afficher Shiny", emoji=SHINY_EMOJI)

    async def callback(self, interaction: discord.Interaction):
        self.is_shiny = not self.is_shiny
        embed = interaction.message.embeds[0]
        lines = embed.description.split("\n") if embed.description else []
        title_index = next((i for i, line in enumerate(lines) if line.startswith("# #")), 0)

        if self.is_shiny:
            if lines and SHINY_EMOJI not in lines[title_index]:
                lines[title_index] = f"{lines[title_index]} {SHINY_EMOJI}".strip()
            if self.shiny_url:
                embed.set_thumbnail(url=self.shiny_url)
            self.label = "Afficher classique"
            self.style = discord.ButtonStyle.primary
            self.emoji = parse_custom_emoji(CLASSIC_EMOJI) or CLASSIC_EMOJI
        else:
            if lines:
                lines[title_index] = lines[title_index].replace(f" {SHINY_EMOJI}", "")
            if self.normal_url:
                embed.set_thumbnail(url=self.normal_url)
            self.label = "Afficher Shiny"
            self.style = discord.ButtonStyle.primary
            self.emoji = parse_custom_emoji(SHINY_EMOJI) or SHINY_EMOJI

        embed.description = "\n".join(lines)
        await interaction.response.edit_message(embed=embed, view=self.view)


class PokemonProfileView(discord.ui.View):
    def __init__(
        self,
        bot: commands.Bot,
        author: discord.Member | discord.User,
        normal_url: str | None,
        shiny_url: str | None,
        name_fr: str,
        prev_options: list[dict[str, str]],
        next_options: list[dict[str, str]],
        initial_shiny: bool = False,
    ):
        super().__init__(timeout=300.0)
        self.author = author
        self.message: discord.Message | None = None

        # Evolutions precedentes
        if len(prev_options) == 1:
            self.add_item(PokemonNavButton(bot, prev_options[0]["query"], prev_options[0]["prefix"]))
        elif len(prev_options) > 1:
            self.add_item(EvolutionSelect(bot, "Choisir une evolution precedente", prev_options))

        # Evolution +1 avant le bouton shiny/classique
        if len(next_options) == 1:
            self.add_item(PokemonNavButton(bot, next_options[0]["query"], next_options[0]["prefix"]))
        elif len(next_options) > 1:
            self.add_item(EvolutionSelect(bot, "Choisir une evolution +1", next_options))

        if shiny_url and normal_url:
            self.add_item(PokemonFormButton(normal_url, shiny_url, name_fr, initial_shiny=initial_shiny))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Cette interaction ne vous appartient pas.", ephemeral=True)
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


# ============================================================================
# ------------------------------- COG PRINCIPAL ------------------------------
# ============================================================================

class PokemonCommand(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name="pokemon",
        description="Affiche la fiche d'un Pokémon.",
    )
    async def pokemon_profile(self, ctx: commands.Context[commands.Bot], query: str | None = None):
        await ctx.defer(ephemeral=False)

        try:
            embed, view = await generate_pokemon_profile(self.bot, ctx.guild, ctx.author, query, keep_shiny=False)
            if not embed:
                await ctx.send("❌ Pokémon introuvable. Vérifie l'orthographe exacte.", reference=ctx.message)
                return

            if ctx.interaction:
                msg = await ctx.interaction.followup.send(embed=embed, view=view, wait=True)
            else:
                msg = await ctx.send(embed=embed, view=view, reference=ctx.message, mention_author=True)

            view.message = msg

        except Exception:
            print("[ERROR - PokemonCommand] Une erreur est survenue:")
            traceback.print_exc()
            error_msg = "❌ Une erreur de communication avec l'API Pokémon est survenue."
            if ctx.interaction:
                await ctx.interaction.followup.send(error_msg, ephemeral=True)
            else:
                await ctx.send(error_msg, reference=ctx.message)


async def setup(bot: commands.Bot):
    if bot.get_command("pokemon"):
        bot.remove_command("pokemon")
    await bot.add_cog(PokemonCommand(bot))
