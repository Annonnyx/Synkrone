import json
import os
import re
import time
import uuid
from typing import Any

import aiohttp
import discord
from discord.ext import commands

from .utils import EconomyService

try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

POKEDOLLAR_EMOJI = "₽"
POKEDEX_OWNED_EMOJI = "<:pokedex:1523703818603335821>"
SHINY_EMOJI = "<:shiny:1522947934969270312>"
MARKET_DIR = os.path.join("data", "economie")
MARKET_FILE = os.path.join(MARKET_DIR, "commerce_market.json")


def format_price(amount: int) -> str:
    return f"{amount:,}".replace(",", " ")


def parse_pokemon_input(raw: str) -> tuple[int, bool] | None:
    match = re.match(r"^(s?)(\d+)$", raw.strip().lower())
    if not match:
        return None
    return int(match.group(2)), bool(match.group(1))


class CommerceManager:
    def __init__(self):
        os.makedirs(MARKET_DIR, exist_ok=True)
        if not os.path.exists(MARKET_FILE):
            with open(MARKET_FILE, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2, ensure_ascii=False)

    def load(self) -> list[dict[str, Any]]:
        try:
            with open(MARKET_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                return []
        except Exception:
            return []

    def save(self, listings: list[dict[str, Any]]):
        with open(MARKET_FILE, "w", encoding="utf-8") as f:
            json.dump(listings, f, indent=2, ensure_ascii=False)

    def add_listing(self, listing: dict[str, Any]):
        data = self.load()
        data.append(listing)
        self.save(data)

    def remove_listing(self, listing_id: str) -> tuple[bool, dict[str, Any] | None]:
        data = self.load()
        listing = next((x for x in data if x.get("listing_id") == listing_id), None)
        if not listing:
            return False, None
        data.remove(listing)
        self.save(data)
        return True, listing

    def user_listings(self, user_id: int) -> list[dict[str, Any]]:
        return [x for x in self.load() if int(x.get("seller_id", 0)) == user_id]

    def listed_inventory_ids(self) -> set[int]:
        return {int(x.get("inventory_id", 0)) for x in self.load() if x.get("inventory_id") is not None}


class SellPokemonModal(discord.ui.Modal, title="Mettre un Pokemon en vente"):
    pokemon_input = discord.ui.TextInput(
        label="Pokemon (ID ou sID)",
        placeholder="Ex: 150 ou s150",
        required=True,
        max_length=20,
    )
    price_input = discord.ui.TextInput(
        label="Prix en Pokedollars",
        placeholder="Ex: 25000",
        required=True,
        max_length=12,
    )

    def __init__(self, view: "CommerceMainView"):
        super().__init__()
        self.view_ref = view

    async def on_submit(self, interaction: discord.Interaction):
        parsed = parse_pokemon_input(self.pokemon_input.value)
        if parsed is None:
            await interaction.response.send_message("❌ Format invalide. Utilisez 150 ou s150.", ephemeral=True)
            return

        try:
            price = int(self.price_input.value.replace(" ", ""))
        except ValueError:
            await interaction.response.send_message("❌ Prix invalide.", ephemeral=True)
            return

        if price <= 0:
            await interaction.response.send_message("❌ Le prix doit etre superieur a 0.", ephemeral=True)
            return

        pokemon_id, is_shiny = parsed
        ok, msg = await self.view_ref.cog.create_listing(interaction.user.id, pokemon_id, is_shiny, price)
        await interaction.response.send_message(msg, ephemeral=True)
        if ok:
            await self.view_ref.refresh_after_action(interaction)


class RemoveListingSelect(discord.ui.Select[Any]):
    def __init__(self, view: "CommerceRemoveView", listings: list[dict[str, Any]]):
        self.view_ref = view
        options: list[discord.SelectOption] = []
        for item in listings[:25]:
            shiny = f"{SHINY_EMOJI} " if item.get("is_shiny") else ""
            name = item.get("name_fr") or f"Pokemon #{item.get('pokemon_id')}"
            options.append(
                discord.SelectOption(
                    label=f"{shiny}#{item.get('pokemon_id')} - {name}"[:100],
                    description=f"Prix: {format_price(int(item.get('price', 0)))} {POKEDOLLAR_EMOJI}"[:100],
                    value=str(item.get("listing_id")),
                )
            )
        super().__init__(
            placeholder="Choisissez une offre a retirer...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        listing_id = self.values[0]
        ok, msg = self.view_ref.cog.cancel_listing(interaction.user.id, listing_id)
        await interaction.response.send_message(msg, ephemeral=True)
        await self.view_ref.back_to_main(interaction)


class MarketListingSelect(discord.ui.Select[Any]):
    def __init__(self, view: "CommerceMarketView", listings: list[dict[str, Any]]):
        self.view_ref = view
        options: list[discord.SelectOption] = []

        for item in listings[:25]:
            seller = self.view_ref.cog.bot.get_user(int(item.get("seller_id", 0)))
            seller_name = getattr(seller, "display_name", f"Utilisateur {item.get('seller_id')}")
            shiny = f"{SHINY_EMOJI} " if item.get("is_shiny") else ""
            name = item.get("name_fr") or f"Pokemon #{item.get('pokemon_id')}"
            options.append(
                discord.SelectOption(
                    label=f"{shiny}#{item.get('pokemon_id')} - {name}"[:100],
                    description=f"{seller_name} | {format_price(int(item.get('price', 0)))} {POKEDOLLAR_EMOJI}"[:100],
                    value=str(item.get("listing_id")),
                )
            )

        super().__init__(
            placeholder="Choisissez un Pokémon à acheter...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        listing_id = self.values[0]
        listing = next((x for x in self.view_ref.listings if str(x.get("listing_id")) == listing_id), None)
        if not listing:
            await interaction.response.send_message("❌ Cette offre n'existe plus.", ephemeral=True)
            return

        shiny = f"{SHINY_EMOJI} " if listing.get("is_shiny") else ""
        pokemon_id = int(listing.get("pokemon_id", 0))
        name_fr = listing.get("name_fr") or f"Pokémon #{pokemon_id}"
        price = int(listing.get("price", 0))

        confirm_text = (
            "Confirmer cet achat ?\n"
            f"- Pokémon: {shiny}#{pokemon_id} {name_fr}\n"
            f"- Prix: {format_price(price)} {POKEDOLLAR_EMOJI}"
        )
        view = BuyConfirmView(self.view_ref, listing_id)
        await interaction.response.send_message(confirm_text, ephemeral=True, view=view)


class BuyConfirmView(discord.ui.View):
    def __init__(self, market_view: "CommerceMarketView", listing_id: str):
        super().__init__(timeout=60)
        self.market_view = market_view
        self.listing_id = listing_id

    @discord.ui.button(label="Confirmer", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, _: discord.ui.Button[Any]):
        ok, msg = await self.market_view.cog.buy_listing(interaction.user.id, self.listing_id)
        await interaction.response.edit_message(content=msg, view=None)
        if ok:
            await self.market_view.refresh_market()

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, _: discord.ui.Button[Any]):
        await interaction.response.edit_message(content="❌ Achat annulé.", view=None)


class CommerceMainView(discord.ui.View):
    def __init__(self, cog: "CommerceCog", author: discord.Member | discord.User, guild: discord.Guild | None):
        super().__init__(timeout=300)
        self.cog = cog
        self.author = author
        self.guild = guild
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        return True

    def build_embed(self) -> discord.Embed:
        listings = self.cog.manager.user_listings(self.author.id)
        desc = "Bienvenue dans le commerce joueur à joueur.\n"
        desc += "Vente et achat de Pokémon au prix fixé par le vendeur.\n\n"
        desc += "⚠️ Vente autorisée uniquement pour les doublons.\n"
        desc += "Utilisez ²doublon pour les voir.\n\n"
        desc += "**Vos offres actives :**\n"

        if not listings:
            desc += "> *Aucune offre active.*"
        else:
            for item in listings[:20]:
                shiny = f"{SHINY_EMOJI} " if item.get("is_shiny") else ""
                name = item.get("name_fr") or f"Pokémon #{item.get('pokemon_id')}"
                desc += (
                    f"- {shiny}**#{item.get('pokemon_id')} {name}**"
                    f" | {format_price(int(item.get('price', 0)))} {POKEDOLLAR_EMOJI}\n"
                )

        embed = self.cog.make_embed(
            guild=self.guild,
            user=self.author,
            title="🛒 Commerce Pokémon",
            description=desc,
            target_id=self.guild.id if self.guild else None,
            force_global=not bool(self.guild),
        )
        if self.cog.bot.user and self.cog.bot.user.display_avatar:
            embed.set_thumbnail(url=self.cog.bot.user.display_avatar.url)
        return embed

    async def refresh_after_action(self, interaction: discord.Interaction):
        if self.message:
            await self.message.edit(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Mettre en vente", style=discord.ButtonStyle.success, emoji="📈")
    async def sell_btn(self, interaction: discord.Interaction, _: discord.ui.Button[Any]):
        await interaction.response.send_modal(SellPokemonModal(self))

    @discord.ui.button(label="Retirer une vente", style=discord.ButtonStyle.danger, emoji="📉")
    async def remove_btn(self, interaction: discord.Interaction, _: discord.ui.Button[Any]):
        user_listings = self.cog.manager.user_listings(self.author.id)
        if not user_listings:
            await interaction.response.send_message("❌ Vous n'avez aucune offre active.", ephemeral=True)
            return
        view = CommerceRemoveView(self.cog, self.author, self.guild, user_listings)
        await interaction.response.edit_message(embed=view.build_embed(), view=view)

    @discord.ui.button(label="Voir le marche", style=discord.ButtonStyle.primary, emoji="🛒")
    async def market_btn(self, interaction: discord.Interaction, _: discord.ui.Button[Any]):
        all_listings = self.cog.manager.load()
        if not all_listings:
            await interaction.response.send_message("❌ Le marché est vide.", ephemeral=True)
            return
        view = CommerceMarketView(self.cog, self.author, self.guild, all_listings)
        view.message = interaction.message
        await interaction.response.edit_message(embed=view.build_embed(), view=view)


class CommerceRemoveView(discord.ui.View):
    def __init__(self, cog: "CommerceCog", author: discord.Member | discord.User, guild: discord.Guild | None, listings: list[dict[str, Any]]):
        super().__init__(timeout=300)
        self.cog = cog
        self.author = author
        self.guild = guild
        self.listings = listings
        self.add_item(RemoveListingSelect(self, listings))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        return True

    def build_embed(self) -> discord.Embed:
        return self.cog.make_embed(
            guild=self.guild,
            user=self.author,
            title="📉 Retirer une vente",
            description="Sélectionnez l'offre à retirer du marché.",
            target_id=self.guild.id if self.guild else None,
            force_global=not bool(self.guild),
        )

    @discord.ui.button(label="Retour", style=discord.ButtonStyle.secondary, emoji="🔙")
    async def back_btn(self, interaction: discord.Interaction, _: discord.ui.Button[Any]):
        await self.back_to_main(interaction)

    async def back_to_main(self, interaction: discord.Interaction):
        view = CommerceMainView(self.cog, self.author, self.guild)
        if interaction.message:
            await interaction.message.edit(embed=view.build_embed(), view=view)


class CommerceMarketView(discord.ui.View):
    def __init__(self, cog: "CommerceCog", author: discord.Member | discord.User, guild: discord.Guild | None, listings: list[dict[str, Any]]):
        super().__init__(timeout=300)
        self.cog = cog
        self.author = author
        self.guild = guild
        self.page = 0
        self.per_page = 15
        self.listings = self.cog.sort_market_listings(listings)
        self.non_owned_only = False
        self.owned_species = self.cog.get_owned_species(self.author.id)
        self.message: discord.Message | None = None
        self.rebuild()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        return True

    def filtered_listings(self) -> list[dict[str, Any]]:
        if not self.non_owned_only:
            return self.listings
        return [x for x in self.listings if int(x.get("pokemon_id", 0)) not in self.owned_species]

    def current_page_data(self) -> list[dict[str, Any]]:
        source = self.filtered_listings()
        start = self.page * self.per_page
        end = start + self.per_page
        return source[start:end]

    def rebuild(self):
        self.clear_items()
        page_data = self.current_page_data()

        filter_btn = discord.ui.Button(
            label="Non possede only",
            style=discord.ButtonStyle.success if self.non_owned_only else discord.ButtonStyle.secondary,
        )
        filter_btn.callback = self.toggle_non_owned_only
        self.add_item(filter_btn)

        if page_data:
            self.add_item(MarketListingSelect(self, page_data))

        if self.page > 0:
            prev_btn = discord.ui.Button(label="◀", style=discord.ButtonStyle.secondary)
            prev_btn.callback = self.prev_page
            self.add_item(prev_btn)

        if (self.page + 1) * self.per_page < len(self.filtered_listings()):
            next_btn = discord.ui.Button(label="▶", style=discord.ButtonStyle.secondary)
            next_btn.callback = self.next_page
            self.add_item(next_btn)

        back_btn = discord.ui.Button(label="Retour", style=discord.ButtonStyle.danger, emoji="🔙")
        back_btn.callback = self.back_btn
        self.add_item(back_btn)

    def build_embed(self) -> discord.Embed:
        page_data = self.current_page_data()
        if not page_data:
            desc = "Aucune offre sur cette page."
        else:
            lines = []
            for item in page_data:
                shiny = f"{SHINY_EMOJI} " if item.get("is_shiny") else ""
                name = item.get("name_fr") or f"Pokémon #{item.get('pokemon_id')}"
                seller = self.cog.bot.get_user(int(item.get("seller_id", 0)))
                seller_name = getattr(seller, "display_name", f"Utilisateur {item.get('seller_id')}")
                owned_marker = POKEDEX_OWNED_EMOJI if int(item.get("pokemon_id", 0)) in self.owned_species else ""
                lines.append(
                    f"- {owned_marker} {shiny}**#{item.get('pokemon_id')} {name}**"
                    f" | {format_price(int(item.get('price', 0)))} {POKEDOLLAR_EMOJI}"
                    f" | vendeur: {seller_name}"
                )
            desc = "\n".join(lines)

        embed = self.cog.make_embed(
            guild=self.guild,
            user=self.author,
            title="🛒 Marché global",
            description=desc,
            target_id=self.guild.id if self.guild else None,
            force_global=not bool(self.guild),
        )
        total_pages = max(1, (len(self.filtered_listings()) + self.per_page - 1) // self.per_page)
        base_footer = embed.footer.text if embed.footer and embed.footer.text else ""
        page_text = f"Page {self.page + 1}/{total_pages}"
        embed.set_footer(text=f"{page_text} | {base_footer}" if base_footer else page_text)
        return embed

    async def refresh_market(self):
        self.listings = self.cog.sort_market_listings(self.cog.manager.load())
        self.owned_species = self.cog.get_owned_species(self.author.id)
        max_page = max(0, (len(self.filtered_listings()) - 1) // self.per_page)
        self.page = min(self.page, max_page)
        self.rebuild()
        if self.message:
            await self.message.edit(embed=self.build_embed(), view=self)

    async def toggle_non_owned_only(self, interaction: discord.Interaction):
        self.non_owned_only = not self.non_owned_only
        self.page = 0
        self.rebuild()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def prev_page(self, interaction: discord.Interaction):
        self.page = max(0, self.page - 1)
        self.rebuild()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.page += 1
        self.rebuild()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def back_btn(self, interaction: discord.Interaction):
        view = CommerceMainView(self.cog, self.author, self.guild)
        await interaction.response.edit_message(embed=view.build_embed(), view=view)


class CommerceCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.eco = EconomyService(bot)
        self.manager = CommerceManager()

    def make_embed(
        self,
        guild: discord.Guild | None,
        user: discord.abc.User,
        title: str,
        description: str,
        target_id: int | None,
        force_global: bool,
    ) -> discord.Embed:
        if config_manager:
            try:
                return config_manager.get_formatted_embed(
                    guild=guild,
                    user=user,
                    bot=self.bot,
                    title=title,
                    description=description,
                    target_id=target_id,
                    force_global=force_global,
                )
            except Exception:
                pass
        return discord.Embed(title=title, description=description, color=0x2B2D31)

    @staticmethod
    def sort_market_listings(listings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # Tri principal par numero de Pokemon (croissant), puis non-shiny avant shiny, puis anciennete.
        return sorted(
            listings,
            key=lambda x: (
                int(x.get("pokemon_id", 0)),
                int(bool(x.get("is_shiny", False))),
                int(x.get("created_at", 0)),
            ),
        )

    def get_owned_species(self, user_id: int) -> set[int]:
        with self.eco._get_conn() as conn:
            rows = conn.execute(
                "SELECT DISTINCT pokemon_id FROM inventory WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        return {int(r["pokemon_id"]) for r in rows}

    async def create_listing(self, seller_id: int, pokemon_id: int, is_shiny: bool, price: int) -> tuple[bool, str]:
        self.eco.ensure_user(seller_id)
        listed_ids = self.manager.listed_inventory_ids()

        with self.eco._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT id, level
                FROM inventory
                WHERE user_id = ? AND pokemon_id = ? AND is_shiny = ?
                  AND id NOT IN (SELECT inventory_id FROM teams WHERE user_id = ?)
                  AND id NOT IN (SELECT pokemon_inv_id FROM daycare WHERE user_id = ?)
                ORDER BY level ASC, id ASC
                """,
                (seller_id, pokemon_id, int(is_shiny), seller_id, seller_id),
            ).fetchall()

        free_ids = [int(row["id"]) for row in rows if int(row["id"]) not in listed_ids]
        if len(free_ids) < 2:
            return False, "❌ Vente refusée: doublon requis. Vérifie avec ²doublon."

        inventory_id = free_ids[0]
        level = next((int(r["level"]) for r in rows if int(r["id"]) == inventory_id), 1)

        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            name_fr = await self.eco.get_species_name_fr(session, pokemon_id)

        listing = {
            "listing_id": str(uuid.uuid4()),
            "seller_id": seller_id,
            "inventory_id": inventory_id,
            "pokemon_id": pokemon_id,
            "is_shiny": bool(is_shiny),
            "level": level,
            "name_fr": name_fr,
            "price": int(price),
            "created_at": int(time.time()),
        }
        self.manager.add_listing(listing)

        shiny = f"{SHINY_EMOJI} " if is_shiny else ""
        return True, (
            f"✅ Offre créée: {shiny}#{pokemon_id} {name_fr}"
            f" pour {format_price(price)} {POKEDOLLAR_EMOJI}."
        )

    def cancel_listing(self, seller_id: int, listing_id: str) -> tuple[bool, str]:
        listings = self.manager.load()
        listing = next((x for x in listings if x.get("listing_id") == listing_id), None)
        if not listing:
            return False, "❌ Offre introuvable."
        if int(listing.get("seller_id", 0)) != seller_id:
            return False, "❌ Cette offre ne vous appartient pas."

        ok, _ = self.manager.remove_listing(listing_id)
        if not ok:
            return False, "❌ Impossible de retirer cette offre."
        return True, "✅ Offre retirée du marché."

    async def buy_listing(self, buyer_id: int, listing_id: str) -> tuple[bool, str]:
        listings = self.manager.load()
        listing = next((x for x in listings if x.get("listing_id") == listing_id), None)
        if not listing:
            return False, "❌ Cette offre n'existe plus."

        seller_id = int(listing.get("seller_id", 0))
        if seller_id == buyer_id:
            return False, "❌ Vous ne pouvez pas acheter votre propre Pokémon."

        price = int(listing.get("price", 0))
        inventory_id = int(listing.get("inventory_id", 0))
        pokemon_id = int(listing.get("pokemon_id", 0))
        is_shiny = int(bool(listing.get("is_shiny", False)))

        self.eco.ensure_user(buyer_id)
        self.eco.ensure_user(seller_id)

        try:
            with self.eco._get_conn() as conn:
                buyer = conn.execute("SELECT balance FROM users WHERE user_id = ?", (buyer_id,)).fetchone()
                if not buyer or int(buyer["balance"]) < price:
                    bal = int(buyer["balance"]) if buyer else 0
                    return False, (
                        f"❌ Fonds insuffisants: {format_price(bal)}/"
                        f"{format_price(price)} {POKEDOLLAR_EMOJI}."
                    )

                inv = conn.execute(
                    """
                    SELECT id
                    FROM inventory
                    WHERE id = ? AND user_id = ? AND pokemon_id = ? AND is_shiny = ?
                      AND id NOT IN (SELECT inventory_id FROM teams WHERE user_id = ?)
                      AND id NOT IN (SELECT pokemon_inv_id FROM daycare WHERE user_id = ?)
                    """,
                    (inventory_id, seller_id, pokemon_id, is_shiny, seller_id, seller_id),
                ).fetchone()
                if not inv:
                    self.manager.remove_listing(listing_id)
                    return False, "❌ Offre expirée: Pokémon indisponible."

                conn.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (price, buyer_id))
                conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (price, seller_id))
                conn.execute("UPDATE inventory SET user_id = ? WHERE id = ?", (buyer_id, inventory_id))

            self.manager.remove_listing(listing_id)
            shiny = f"{SHINY_EMOJI} " if is_shiny else ""
            name = listing.get("name_fr") or f"Pokémon #{pokemon_id}"
            await self.notify_seller_sale(seller_id, buyer_id, pokemon_id, name, bool(is_shiny), price)
            return True, (
                f"✅ Achat confirmé: {shiny}#{pokemon_id} {name}"
                f" pour {format_price(price)} {POKEDOLLAR_EMOJI}."
            )
        except Exception as exc:
            return False, f"❌ Erreur système: {exc}"

    async def notify_seller_sale(
        self,
        seller_id: int,
        buyer_id: int,
        pokemon_id: int,
        name_fr: str,
        is_shiny: bool,
        price: int,
    ):
        seller = self.bot.get_user(seller_id)
        if seller is None:
            try:
                seller = await self.bot.fetch_user(seller_id)
            except Exception:
                return

        buyer = self.bot.get_user(buyer_id)
        buyer_name = getattr(buyer, "display_name", f"Utilisateur {buyer_id}")
        shiny = f"{SHINY_EMOJI} " if is_shiny else ""
        dm_text = (
            "💸 Votre Pokémon a été vendu sur le marché !\n"
            f"- Pokémon: {shiny}#{pokemon_id} {name_fr}\n"
            f"- Prix: {format_price(price)} {POKEDOLLAR_EMOJI}\n"
            f"- Acheteur: {buyer_name}"
        )
        try:
            await seller.send(dm_text)
        except Exception:
            return

    @commands.hybrid_command(name="commerce", description="Marché joueur à joueur pour Pokémon.")
    async def commerce(self, ctx: commands.Context[commands.Bot]):
        self.eco.ensure_user(ctx.author.id)

        view = CommerceMainView(self, ctx.author, ctx.guild)
        embed = view.build_embed()
        if ctx.message:
            message = await ctx.send(embed=embed, view=view, reference=ctx.message)
        else:
            message = await ctx.send(embed=embed, view=view)
        view.message = message


async def setup(bot: commands.Bot):
    if bot.get_cog("CommerceCog"):
        await bot.remove_cog("CommerceCog")
    await bot.add_cog(CommerceCog(bot))
