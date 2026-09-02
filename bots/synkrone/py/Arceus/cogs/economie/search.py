import aiohttp
import asyncio
import discord
import json
import math
import random
import time
from pathlib import Path
from typing import Any
from discord.ext import commands

from .utils import EconomyService

try:
    from cogs.pokémon.pokemon import get_species_fr_name
except ImportError:
    get_species_fr_name = None

try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

SEARCH_PER_PAGE = 10
CLASSIC_EMOJI = "<:pokeball:1522952715846684782>"
SHINY_EMOJI = "<:shiny:1522947934969270312>"
VOTE_DATA_FILE = Path.cwd() / "data" / "public" / "data_vote" / "users.json"


def format_number(num: int) -> str:
    return f"{int(num):,}".replace(",", " ")


def create_embed(guild: discord.Guild | None, user: discord.abc.User | None, bot: commands.Bot, title: str, description: str) -> discord.Embed:
    if config_manager:
        try:
            embed = config_manager.get_formatted_embed(
                guild=guild,
                user=user,
                bot=bot,
                title=title,
                description=description,
                target_id=guild.id if guild else None,
                force_global=not bool(guild)
            )
            return embed
        except Exception:
            pass
    embed = discord.Embed(title=title, description=description, color=0x2B2D31)
    return embed


class SearchDetailView(discord.ui.View):
    def __init__(self, cog: "SearchCog", guild: discord.Guild | None, author: discord.abc.User, pokemon_id: int, is_shiny: bool, results: dict[str, Any], show_toggle: bool = True):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.author = author
        self.pokemon_id = pokemon_id
        self.is_shiny = is_shiny
        self.results = results
        self.show_toggle = show_toggle
        self._build_buttons()

    def _build_buttons(self):
        self.clear_items()
        if not self.show_toggle:
            return
        if self.is_shiny:
            if self.results.get("classic_available"):
                btn = discord.ui.Button(label="Mode classique", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji(name="pokeball", id=1522952715846684782), custom_id="classic")
                btn.callback = self.on_classic
                self.add_item(btn)
        else:
            if self.results.get("shiny_available"):
                btn = discord.ui.Button(label="Mode shiny", style=discord.ButtonStyle.secondary, emoji=discord.PartialEmoji(name="shiny", id=1522947934969270312), custom_id="shiny")
                btn.callback = self.on_shiny
                self.add_item(btn)

    async def on_classic(self, interaction: discord.Interaction):
        await self._update(interaction, False)

    async def on_shiny(self, interaction: discord.Interaction):
        await self._update(interaction, True)

    async def _update(self, interaction: discord.Interaction, is_shiny: bool):
        self.is_shiny = is_shiny
        embed = await self.cog.build_detail_embed(self.guild, self.author, self.pokemon_id, self.is_shiny)
        await interaction.response.edit_message(embed=embed, view=self)


class SearchListView(discord.ui.View):
    def __init__(self, cog: "SearchCog", guild: discord.Guild | None, author: discord.abc.User, data: list[dict[str, Any]], mode: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.author = author
        self.data = data
        self.page = 0
        self.mode = mode
        self._build_view()

    def _filtered_data(self) -> list[dict[str, Any]]:
        if self.mode == "Shiny":
            return [item for item in self.data if item["is_shiny"]]
        return [item for item in self.data if not item["is_shiny"]]

    def _build_view(self):
        self.clear_items()
        filtered = self._filtered_data()
        start = self.page * SEARCH_PER_PAGE
        end = start + SEARCH_PER_PAGE
        page_data = filtered[start:end]

        if page_data:
            options = []
            for item in page_data:
                label = f"`#{item['pokemon_id']:04d}` {item['name']} — {item['global_users']}"
                desc = f"Disponible chez {item['global_users']} joueur(s)"
                options.append(discord.SelectOption(label=label, value=f"{item['pokemon_id']}_{int(item['is_shiny'])}", description=desc))

            sel = discord.ui.Select(placeholder="Sélectionne un Pokémon pour voir la liste des doublons.", options=options, row=0)
            sel.callback = self.on_select
            self.add_item(sel)

        has_shiny = any(item["is_shiny"] for item in self.data)
        has_classic = any(not item["is_shiny"] for item in self.data)
        alternate_available = (self.mode == "Classique" and has_shiny) or (self.mode == "Shiny" and has_classic)
        if alternate_available:
            btn_mode = discord.ui.Button(
                label="Mode shiny" if self.mode == "Classique" else "Mode classique",
                style=discord.ButtonStyle.secondary,
                emoji=discord.PartialEmoji(name="shiny", id=1522947934969270312) if self.mode == "Classique" else discord.PartialEmoji(name="pokeball", id=1522952715846684782),
                row=1
            )
            btn_mode.callback = self.toggle_mode
            self.add_item(btn_mode)

        if self.page > 0:
            btn_prev = discord.ui.Button(label="◀", style=discord.ButtonStyle.secondary, row=2)
            btn_prev.callback = self.prev_page
            self.add_item(btn_prev)
        if len(filtered) > end:
            btn_next = discord.ui.Button(label="▶", style=discord.ButtonStyle.secondary, row=2)
            btn_next.callback = self.next_page
            self.add_item(btn_next)

    async def on_select(self, interaction: discord.Interaction):
        value = interaction.data["values"][0]
        pokemon_id, shiny_flag = value.split("_")
        pokemon_id = int(pokemon_id)
        is_shiny = bool(int(shiny_flag))
        embed = await self.cog.build_detail_embed(self.guild, self.author, pokemon_id, is_shiny)
        result = await self.cog.get_pokemon_availability(pokemon_id)
        view = SearchDetailView(self.cog, self.guild, self.author, pokemon_id, is_shiny, result, show_toggle=False)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def toggle_mode(self, interaction: discord.Interaction):
        self.mode = "Shiny" if self.mode == "Classique" else "Classique"
        self.page = 0
        self._build_view()
        embed = await self.cog.build_main_embed(self.guild, self.author, self.data, self.page, self.mode)
        await interaction.response.edit_message(embed=embed, view=self)

    async def prev_page(self, interaction: discord.Interaction):
        self.page -= 1
        self._build_view()
        embed = await self.cog.build_main_embed(self.guild, self.author, self.data, self.page, self.mode)
        await interaction.response.edit_message(embed=embed, view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.page += 1
        self._build_view()
        embed = await self.cog.build_main_embed(self.guild, self.author, self.data, self.page, self.mode)
        await interaction.response.edit_message(embed=embed, view=self)


class SearchUserView(discord.ui.View):
    def __init__(self, cog: "SearchCog", guild: discord.Guild | None, author: discord.abc.User, target: discord.abc.User, data: list[dict[str, Any]]):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.author = author
        self.target = target
        self.data = data
        self.page = 0
        self.mode = "Classique"
        self._build_view()

    def _filtered_data(self) -> list[dict[str, Any]]:
        if self.mode == "Shiny":
            return [item for item in self.data if item["is_shiny"]]
        return [item for item in self.data if not item["is_shiny"]]

    def _build_view(self):
        self.clear_items()
        has_shiny = any(item["is_shiny"] for item in self.data)
        has_classic = any(not item["is_shiny"] for item in self.data)
        alternate_available = (self.mode == "Classique" and has_shiny) or (self.mode == "Shiny" and has_classic)
        if alternate_available:
            btn_mode = discord.ui.Button(
                label="Mode shiny" if self.mode == "Classique" else "Mode classique",
                style=discord.ButtonStyle.secondary,
                emoji=discord.PartialEmoji(name="shiny", id=1522947934969270312) if self.mode == "Classique" else discord.PartialEmoji(name="pokeball", id=1522952715846684782),
                row=0
            )
            btn_mode.callback = self.toggle_mode
            self.add_item(btn_mode)
        if self.page > 0:
            btn_prev = discord.ui.Button(label="◀", style=discord.ButtonStyle.secondary, row=1)
            btn_prev.callback = self.prev_page
            self.add_item(btn_prev)
        if len(self._filtered_data()) > (self.page + 1) * SEARCH_PER_PAGE:
            btn_next = discord.ui.Button(label="▶", style=discord.ButtonStyle.secondary, row=1)
            btn_next.callback = self.next_page
            self.add_item(btn_next)

    async def toggle_mode(self, interaction: discord.Interaction):
        self.mode = "Shiny" if self.mode == "Classique" else "Classique"
        self.page = 0
        self._build_view()
        await interaction.response.edit_message(embed=self.cog.build_user_embed(self.guild, self.author, self.target, self.data, self.page, self.mode), view=self)

    async def prev_page(self, interaction: discord.Interaction):
        self.page -= 1
        self._build_view()
        await interaction.response.edit_message(embed=self.cog.build_user_embed(self.guild, self.author, self.target, self.data, self.page, self.mode), view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.page += 1
        self._build_view()
        await interaction.response.edit_message(embed=self.cog.build_user_embed(self.guild, self.author, self.target, self.data, self.page, self.mode), view=self)


class SearchCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.eco = EconomyService(bot)

    def _load_vote_data(self) -> dict[str, dict[str, Any]]:
        if not VOTE_DATA_FILE.exists():
            return {}
        try:
            with open(VOTE_DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _format_pokemon_label(self, pokemon_id: int, name: str, is_shiny: bool) -> str:
        prefix = SHINY_EMOJI if is_shiny else ""
        return f"#{pokemon_id:04d} {name} {prefix}".strip()

    async def _get_species_name(self, pokemon_id: int) -> str:
        if get_species_fr_name is None:
            return f"Pokémon #{pokemon_id}"
        try:
            async with aiohttp.ClientSession() as session:
                return await get_species_fr_name(session, str(pokemon_id))
        except Exception:
            return f"Pokémon #{pokemon_id}"

    def _get_user_owned(self, user_id: int) -> set[tuple[int, int]]:
        with self.eco._get_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT pokemon_id, is_shiny FROM inventory WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            return {(row["pokemon_id"], row["is_shiny"]) for row in rows}

    def _guild_member_ids(self, guild: discord.Guild | None) -> set[int]:
        if not guild:
            return set()
        return {m.id for m in guild.members}

    async def _find_user_by_id(self, user_id: int) -> discord.abc.User | None:
        user = self.bot.get_user(user_id)
        if user:
            return user
        try:
            return await self.bot.fetch_user(user_id)
        except Exception:
            return None

    def _is_member_or_user_mention(self, arg: str) -> int | None:
        if arg.startswith("<@") and arg.endswith(">"):
            arg = arg.strip("<@!>")
        if arg.isdigit():
            return int(arg)
        return None

    def _parse_pokemon_query(self, query: str) -> int | None:
        if query.startswith("#"):
            query = query[1:]
        if query.isdigit():
            return int(query)
        return None

    async def _resolve_user_or_pokemon_query(self, query: str) -> tuple[str, int | discord.abc.User | None]:
        member_id = self._is_member_or_user_mention(query)

        if query.startswith("#"):
            pokemon_id = self._parse_pokemon_query(query)
            if pokemon_id is not None:
                return "pokemon", pokemon_id
            return "pokemon_name", None

        if query.isdigit():
            if len(query) >= 17:
                target = await self._find_user_by_id(int(query))
                if target:
                    return "user", target
            return "pokemon", int(query)

        if member_id is not None:
            target = await self._find_user_by_id(member_id)
            if target:
                return "user", target

        return "pokemon_name", None

    async def _find_pokemon_id_by_name(self, query: str) -> int | None:
        if query.isdigit():
            return int(query)
        try:
            async with aiohttp.ClientSession() as session:
                search = query.lower().replace(" ", "-")
                async with session.get(f"https://pokeapi.co/api/v2/pokemon/{search}") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return int(data["id"])
        except Exception:
            pass
        return None

    def _get_global_duplicates(self, exclude_owned: set[tuple[int, int]]) -> list[dict[str, Any]]:
        with self.eco._get_conn() as conn:
            rows = conn.execute(
                "SELECT pokemon_id, is_shiny, user_id, COUNT(*) AS qty FROM inventory GROUP BY user_id, pokemon_id, is_shiny HAVING qty > 1"
            ).fetchall()
        candidates: dict[tuple[int, int], dict[str, Any]] = {}
        for row in rows:
            key = (row["pokemon_id"], row["is_shiny"])
            if key in exclude_owned:
                continue
            if key not in candidates:
                candidates[key] = {
                    "pokemon_id": row["pokemon_id"],
                    "is_shiny": bool(row["is_shiny"]),
                    "global_users": set(),
                    "guild_users": set(),
                }
            candidates[key]["global_users"].add(row["user_id"])
        return [
            {"pokemon_id": k[0], "is_shiny": k[1], "global_users": len(v["global_users"]), "guild_users": 0}
            for k, v in candidates.items()
        ]

    def _count_guild_users(self, data: list[dict[str, Any]], guild_ids: set[int]) -> None:
        if not guild_ids:
            return
        with self.eco._get_conn() as conn:
            for item in data:
                rows = conn.execute(
                    "SELECT DISTINCT user_id FROM inventory WHERE pokemon_id = ? AND is_shiny = ? AND user_id IN ({})".format(
                        ",".join(["?"] * len(guild_ids))
                    ),
                    (item["pokemon_id"], int(item["is_shiny"]), *list(guild_ids)),
                ).fetchall()
                item["guild_users"] = len(rows)

    def _filter_user_duplicates(self, target_id: int, exclude_owned: set[tuple[int, int]]) -> list[dict[str, Any]]:
        with self.eco._get_conn() as conn:
            rows = conn.execute(
                "SELECT pokemon_id, is_shiny, COUNT(*) AS qty FROM inventory WHERE user_id = ? GROUP BY pokemon_id, is_shiny HAVING qty > 1",
                (target_id,),
            ).fetchall()
        result = []
        for row in rows:
            key = (row["pokemon_id"], row["is_shiny"])
            if key in exclude_owned:
                continue
            result.append({
                "pokemon_id": row["pokemon_id"],
                "is_shiny": bool(row["is_shiny"]),
                "qty": int(row["qty"]),
            })
        return result

    def _format_user_line(self, user_id: int, qty: int) -> str:
        user = self.bot.get_user(user_id)
        username = user.name if user else str(user_id)
        return f"`{username}` — `ID : {user_id}` — x{qty}"

    def _build_user_list(self, pokemon_id: int, is_shiny: bool, exclude_user: int, guild_ids: set[int]) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
        with self.eco._get_conn() as conn:
            rows = conn.execute(
                "SELECT user_id, COUNT(*) AS qty FROM inventory WHERE pokemon_id = ? AND is_shiny = ? GROUP BY user_id HAVING qty > 1",
                (pokemon_id, int(is_shiny)),
            ).fetchall()
        global_list = []
        guild_list = []
        for row in rows:
            uid = row["user_id"]
            if uid == exclude_user:
                continue
            qty = int(row["qty"])
            global_list.append((uid, qty))
            if uid in guild_ids:
                guild_list.append((uid, qty))
        global_list.sort(key=lambda x: x[1], reverse=True)
        guild_list.sort(key=lambda x: x[1], reverse=True)
        return guild_list, global_list

    def _filter_data_by_mode(self, data: list[dict[str, Any]], mode: str) -> list[dict[str, Any]]:
        if mode == "Shiny":
            return [item for item in data if item["is_shiny"]]
        return [item for item in data if not item["is_shiny"]]

    async def build_main_embed(self, guild: discord.Guild | None, author: discord.abc.User, data: list[dict[str, Any]], page: int, mode: str) -> discord.Embed:
        title = "Recherche de doublons disponibles"
        description = "Voici les Pokémon que tu n'as pas et que d'autres joueurs possèdent en double."
        embed = create_embed(guild, author, self.bot, title, description)

        filtered = self._filter_data_by_mode(data, mode)
        if not filtered:
            embed.add_field(name="Aucun résultat", value="Personne ne possède de doublon correspondant à tes critères.", inline=False)
            return embed

        start = page * SEARCH_PER_PAGE
        end = start + SEARCH_PER_PAGE
        page_data = filtered[start:end]

        lines = []
        for item in page_data:
            shiny_label = SHINY_EMOJI if item["is_shiny"] else CLASSIC_EMOJI
            lines.append(
                f"{shiny_label} `#{item['pokemon_id']:04d}` {item['name']} — {item['global_users']}"
            )
        embed.add_field(name="Pokémon disponibles", value="\n".join(lines), inline=False)

        total_pages = max(1, math.ceil(len(filtered) / SEARCH_PER_PAGE))
        if config_manager is None:
            embed.set_footer(text=f"Page {page+1}/{total_pages} | Utilise le menu pour afficher un Pokémon précis.")
        else:
            embed.add_field(name="Page", value=f"{page+1}/{total_pages}", inline=False)
        return embed

    def build_user_embed(self, guild: discord.Guild | None, author: discord.abc.User, target: discord.abc.User, data: list[dict[str, Any]], page: int, mode: str) -> discord.Embed:
        title = f"Doublons de {target.display_name}"
        description = f"`{target.display_name}` — `ID : {target.id}`\nListe des Pokémon en doublon possédés par cette personne."
        embed = create_embed(guild, author, self.bot, title, description)
        if hasattr(target, 'display_avatar'):
            embed.set_thumbnail(url=target.display_avatar.url)

        embed.add_field(name="Utilisateur", value=f"{target.mention} • `ID : {target.id}`", inline=False)

        filtered = self._filter_data_by_mode(data, mode)
        if not filtered:
            embed.add_field(name="Aucun résultat", value="Aucun doublon trouvé ou tu as déjà tous les Pokémon.", inline=False)
            return embed

        start = page * SEARCH_PER_PAGE
        end = start + SEARCH_PER_PAGE
        page_data = filtered[start:end]
        lines = []
        for item in page_data:
            shiny_label = SHINY_EMOJI if item["is_shiny"] else CLASSIC_EMOJI
            lines.append(f"{shiny_label} `#{item['pokemon_id']:04d}` {item['name']} — x{item['qty']}")

        embed.add_field(name="Pokémon", value="\n".join(lines), inline=False)
        total_pages = max(1, math.ceil(len(filtered) / SEARCH_PER_PAGE))
        if config_manager is None:
            embed.set_footer(text=f"Page {page+1}/{total_pages}")
        else:
            embed.add_field(name="Page", value=f"{page+1}/{total_pages}", inline=False)
        return embed

    async def build_detail_embed(self, guild: discord.Guild | None, author: discord.abc.User, pokemon_id: int, is_shiny: bool) -> discord.Embed:
        name = await self._get_species_name(pokemon_id)
        title = f"{name} {SHINY_EMOJI if is_shiny else ''}"
        description = f"Utilisateurs possédant ce Pokémon en doublon."
        embed = create_embed(guild, author, self.bot, title, description)
        embed.set_thumbnail(url=f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/{'shiny/' if is_shiny else ''}{pokemon_id}.png")

        guild_ids = self._guild_member_ids(guild)
        guild_users, global_users = self._build_user_list(pokemon_id, is_shiny, author.id, guild_ids)

        if not global_users:
            embed.add_field(name="Aucun doublon trouvé", value="Aucun utilisateur n'a ce Pokémon en doublon.", inline=False)
            return embed

        embed.add_field(name="En serveur", value="\n".join([self._format_user_line(uid, qty) for uid, qty in guild_users]) or "Aucun utilisateur sur ce serveur.", inline=False)
        embed.add_field(name="Global", value="\n".join([self._format_user_line(uid, qty) for uid, qty in global_users[:15]]) or "Aucun utilisateur." , inline=False)
        if config_manager is None:
            embed.set_footer(text=f"Affiche {len(global_users)} utilisateur(s) globalement, {len(guild_users)} sur ce serveur.")
        else:
            embed.add_field(name="Infos", value=f"{len(global_users)} utilisateur(s) globalement, {len(guild_users)} sur ce serveur.", inline=False)
        return embed

    async def get_pokemon_availability(self, pokemon_id: int) -> dict[str, Any]:
        with self.eco._get_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT is_shiny FROM inventory WHERE pokemon_id = ?",
                (pokemon_id,),
            ).fetchall()
        classic = any(row["is_shiny"] == 0 for row in rows)
        shiny = any(row["is_shiny"] == 1 for row in rows)
        return {"classic_available": classic, "shiny_available": shiny}

    async def _search_candidates(self, ctx: commands.Context[commands.Bot]) -> list[dict[str, Any]]:
        owned = self._get_user_owned(ctx.author.id)
        guild_ids = self._guild_member_ids(ctx.guild)
        data = self._get_global_duplicates(owned)
        self._count_guild_users(data, guild_ids)
        if not data:
            return []
        names = {}
        async with aiohttp.ClientSession() as session:
            tasks = [self._get_species_name(item["pokemon_id"]) for item in data]
            names_list = await asyncio.gather(*tasks)
        for item, name in zip(data, names_list):
            item["name"] = name
        data.sort(key=lambda x: (x["pokemon_id"], not x["is_shiny"], -x["global_users"]))
        return data

    @commands.hybrid_command(name="search", description="Cherche les doublons des autres joueurs que tu n'as pas.")
    async def search(self, ctx: commands.Context[commands.Bot], member: discord.Member | None = None, query: str | None = None):
        if member and query:
            return await ctx.send("❌ Utilise un seul paramètre à la fois : soit un utilisateur, soit un Pokémon.", reference=ctx.message)

        if member:
            owned = self._get_user_owned(ctx.author.id)
            target_data = self._filter_user_duplicates(member.id, owned)
            if not target_data:
                await ctx.send("❌ Aucun doublon trouvé chez cette personne que tu n'as pas.", reference=ctx.message)
                return
            async with aiohttp.ClientSession() as session:
                tasks = [self._get_species_name(item["pokemon_id"]) for item in target_data]
                names = await asyncio.gather(*tasks)
            for item, name in zip(target_data, names):
                item["name"] = name
            view = SearchUserView(self, ctx.guild, ctx.author, member, target_data)
            embed = self.build_user_embed(ctx.guild, ctx.author, member, target_data, 0, "Classique")
            await ctx.send(embed=embed, view=view, reference=ctx.message)
            return

        if query:
            query_type, target = await self._resolve_user_or_pokemon_query(query)
            if query_type == "user" and isinstance(target, discord.abc.User):
                owned = self._get_user_owned(ctx.author.id)
                target_data = self._filter_user_duplicates(target.id, owned)
                if not target_data:
                    await ctx.send("❌ Aucun doublon trouvé chez cette personne que tu n'as pas.", reference=ctx.message)
                    return
                async with aiohttp.ClientSession() as session:
                    tasks = [self._get_species_name(item["pokemon_id"]) for item in target_data]
                    names = await asyncio.gather(*tasks)
                for item, name in zip(target_data, names):
                    item["name"] = name
                view = SearchUserView(self, ctx.guild, ctx.author, target, target_data)
                embed = self.build_user_embed(ctx.guild, ctx.author, target, target_data, 0, "Classique")
                await ctx.send(embed=embed, view=view, reference=ctx.message)
                return
            if query_type == "pokemon":
                pokemon_id = target
            else:
                pokemon_id = await self._find_pokemon_id_by_name(query)
                if pokemon_id is None:
                    await ctx.send("❌ Pokémon introuvable.", reference=ctx.message)
                    return

            owned = self._get_user_owned(ctx.author.id)
            if (pokemon_id, 0) in owned or (pokemon_id, 1) in owned:
                await ctx.send("❌ Tu possèdes déjà ce Pokémon.", reference=ctx.message)
                return

            result = await self.get_pokemon_availability(pokemon_id)
            if not result["classic_available"] and not result["shiny_available"]:
                await ctx.send("❌ Aucun joueur ne possède ce Pokémon en doublon.", reference=ctx.message)
                return

            embed = await self.build_detail_embed(ctx.guild, ctx.author, pokemon_id, False)
            view = SearchDetailView(self, ctx.guild, ctx.author, pokemon_id, False, result)
            await ctx.send(embed=embed, view=view, reference=ctx.message)
            return

        data = await self._search_candidates(ctx)
        if not data:
            await ctx.send("❌ Aucun Pokémon en doublon disponible pour toi.", reference=ctx.message)
            return
        embed = await self.build_main_embed(ctx.guild, ctx.author, data, 0, "Classique")
        view = SearchListView(self, ctx.guild, ctx.author, data, "Classique")
        await ctx.send(embed=embed, view=view, reference=ctx.message)


async def setup(bot: commands.Bot):
    await bot.add_cog(SearchCog(bot))
