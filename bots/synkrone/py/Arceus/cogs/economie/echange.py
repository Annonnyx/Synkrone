import asyncio
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import aiohttp
import discord
from discord.ext import commands

from .utils import (
    BALL_EMOJIS,
    BALL_LABELS,
    CHARM_EMOJIS,
    CHARM_LABELS,
    SUPERBONBON_EMOJI,
    EconomyService,
)

try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None


def _display_user_name(user: discord.abc.User) -> str:
    return getattr(user, "display_name", user.name)


POKEDOLLAR_EMOJI = "₽"


def format_price(amount: int) -> str:
    return f"{amount:,}".replace(",", " ")


ITEM_ALIASES = {
    "pokeball": "pokeball", "poke ball": "pokeball",
    "superball": "superball", "super ball": "superball",
    "hyperball": "hyperball", "hyper ball": "hyperball",
    "masterball": "masterball", "master ball": "masterball",
    "superbonbon": "superbonbon", "bonbon": "superbonbon",
    "charme stabilite": "charme_stabilite", "stabilite": "charme_stabilite", "charme_stabilite": "charme_stabilite",
    "charme chroma": "charme_chroma", "chroma": "charme_chroma", "charme_chroma": "charme_chroma",
    "charme insigne": "charme_insigne", "insigne": "charme_insigne", "charme_insigne": "charme_insigne",
    "charme xp": "charme_xp", "xp": "charme_xp", "charme_xp": "charme_xp",
}

SHOP_LABELS = {**BALL_LABELS, "superbonbon": "Superbonbon", **CHARM_LABELS}
SHOP_EMOJIS = {**BALL_EMOJIS, "superbonbon": SUPERBONBON_EMOJI, **CHARM_EMOJIS}


@dataclass
class TradeOfferState:
    money: int = 0
    items: dict[str, int] = field(default_factory=dict)
    pokemons: dict[str, dict[str, Any]] = field(default_factory=dict)
    elements_confirmed: bool = False
    final_confirmed: bool = False

    def has_elements(self) -> bool:
        return self.money > 0 or bool(self.items) or bool(self.pokemons)


@dataclass
class TradeSession:
    session_id: str
    requester: discord.abc.User
    target: discord.abc.User
    offers: dict[int, TradeOfferState]
    message_by_user: dict[int, discord.Message | None] = field(default_factory=dict)
    view_by_user: dict[int, "TradeUserView"] = field(default_factory=dict)
    closed: bool = False
    closing_reason: str | None = None
    countdown_started: bool = False
    last_activity: float = field(default_factory=time.monotonic)
    inactivity_task: asyncio.Task[Any] | None = None

    def other_id(self, user_id: int) -> int:
        return self.target.id if user_id == self.requester.id else self.requester.id

    def both_elements_confirmed(self) -> bool:
        return self.offers[self.requester.id].elements_confirmed and self.offers[self.target.id].elements_confirmed

    def both_final_confirmed(self) -> bool:
        return self.offers[self.requester.id].final_confirmed and self.offers[self.target.id].final_confirmed


class TargetModal(discord.ui.Modal, title="Choisir le destinataire"):
    target_input = discord.ui.TextInput(
        label="ID Discord",
        placeholder="Ex: 123456789012345678",
        required=True,
        max_length=30,
    )

    def __init__(self, view: "TradeStartView"):
        super().__init__()
        self.view_ref = view

    async def on_submit(self, interaction: discord.Interaction):
        raw_id = self.target_input.value.strip()
        match = re.search(r"\d+", raw_id)
        if not match:
            await interaction.response.send_message("❌ ID invalide.", ephemeral=True)
            return

        target_id = int(match.group(0))
        if target_id == self.view_ref.author.id:
            await interaction.response.send_message("❌ Tu ne peux pas t'échanger avec toi-même.", ephemeral=True)
            return

        user = self.view_ref.cog.bot.get_user(target_id)
        if user is None:
            try:
                user = await self.view_ref.cog.bot.fetch_user(target_id)
            except Exception:
                user = None

        self.view_ref.target_id = target_id
        self.view_ref.target_user = user
        await self.view_ref.refresh(interaction)


class AddTradeElementModal(discord.ui.Modal, title="Ajouter un élément"):
    element_input = discord.ui.TextInput(
        label="Élément (argent, objet, Pokémon)",
        placeholder="Ex: argent, hyperball, charme chroma, 150, s150",
        required=True,
        max_length=40,
    )
    qty_input = discord.ui.TextInput(
        label="Quantité",
        placeholder="Laissez vide pour 1",
        required=False,
        default="1",
        max_length=10,
    )

    def __init__(self, view: "TradeUserView"):
        super().__init__()
        self.view_ref = view

    async def on_submit(self, interaction: discord.Interaction):
        session = self.view_ref.session
        self.view_ref.cog.touch_session(session)
        if session.closed:
            await interaction.response.send_message("❌ Cet échange est déjà fermé.", ephemeral=True)
            return

        offer = session.offers[self.view_ref.user_id]
        if offer.elements_confirmed:
            await interaction.response.send_message("❌ Tu as déjà validé tes éléments.", ephemeral=True)
            return

        element = self.element_input.value.strip().lower()
        try:
            qty = int(self.qty_input.value.strip() or "1")
        except ValueError:
            await interaction.response.send_message("❌ Quantité invalide.", ephemeral=True)
            return
        if qty <= 0:
            await interaction.response.send_message("❌ La quantité doit être > 0.", ephemeral=True)
            return

        if element in ["argent", "money", "pokedollar", "pokédollar", "pokedollars", "₽"]:
            with self.view_ref.cog.eco._get_conn() as conn:
                row = conn.execute("SELECT balance FROM users WHERE user_id = ?", (self.view_ref.user_id,)).fetchone()
            balance = int(row["balance"]) if row else 0
            if offer.money + qty > balance:
                await interaction.response.send_message(
                    f"❌ Solde insuffisant. Possédé: {format_price(balance)} {POKEDOLLAR_EMOJI}.",
                    ephemeral=True,
                )
                return
            offer.money += qty
        elif element in ITEM_ALIASES:
            item_key = ITEM_ALIASES[element]
            pending = offer.items.get(item_key, 0)
            with self.view_ref.cog.eco._get_conn() as conn:
                row = conn.execute(f"SELECT {item_key} FROM users WHERE user_id = ?", (self.view_ref.user_id,)).fetchone()
            owned = int(row[item_key]) if row else 0
            if pending + qty > owned:
                await interaction.response.send_message(
                    f"❌ Pas assez de {SHOP_LABELS.get(item_key, item_key)}. Possédé: {format_price(owned)}.",
                    ephemeral=True,
                )
                return
            offer.items[item_key] = pending + qty
        else:
            match = re.match(r"^(s?)(\d+)$", element)
            if not match:
                await interaction.response.send_message(
                    "❌ Élément invalide. Exemples: argent, hyperball, charme chroma, 150, s150.",
                    ephemeral=True,
                )
                return

            is_shiny = bool(match.group(1))
            pokemon_id = int(match.group(2))
            key = f"{pokemon_id}_{int(is_shiny)}"
            pending = offer.pokemons.get(key, {}).get("qty", 0)

            owned_free = self.view_ref.cog.count_free_pokemon(self.view_ref.user_id, pokemon_id, is_shiny)
            if pending + qty > owned_free:
                shiny_str = "✨ " if is_shiny else ""
                await interaction.response.send_message(
                    f"❌ Pas assez de Pokémon {shiny_str}#{pokemon_id} libres. Possédé libre: {owned_free}.",
                    ephemeral=True,
                )
                return

            timeout = aiohttp.ClientTimeout(total=12)
            async with aiohttp.ClientSession(timeout=timeout) as http_session:
                name_fr = await self.view_ref.cog.eco.get_species_name_fr(http_session, pokemon_id)

            if key not in offer.pokemons:
                offer.pokemons[key] = {
                    "id": pokemon_id,
                    "is_shiny": is_shiny,
                    "qty": 0,
                    "name_fr": name_fr,
                }
            offer.pokemons[key]["qty"] += qty

        offer.elements_confirmed = False
        offer.final_confirmed = False
        session.offers[session.other_id(self.view_ref.user_id)].final_confirmed = False

        await interaction.response.send_message("✅ Élément ajouté.", ephemeral=True)
        await self.view_ref.cog.refresh_session_ui(session)


class TradeRemoveSelect(discord.ui.Select[Any]):
    def __init__(self, view: "TradeUserView"):
        self.view_ref = view
        offer = view.session.offers[view.user_id]

        options: list[discord.SelectOption] = []
        if offer.money > 0:
            options.append(
                discord.SelectOption(
                    label=f"Argent: {format_price(offer.money)} {POKEDOLLAR_EMOJI}",
                    value="money",
                    emoji="💰",
                )
            )

        for key, qty in offer.items.items():
            options.append(
                discord.SelectOption(
                    label=f"{SHOP_LABELS.get(key, key)} x{format_price(qty)}",
                    value=f"item_{key}",
                    emoji=SHOP_EMOJIS.get(key, "🎒"),
                )
            )

        for key, data in offer.pokemons.items():
            shiny = "✨" if data["is_shiny"] else "🐾"
            options.append(
                discord.SelectOption(
                    label=f"#{data['id']} {data['name_fr']} x{data['qty']}",
                    value=f"poke_{key}",
                    emoji=shiny,
                )
            )

        if not options:
            options.append(discord.SelectOption(label="Aucun élément", value="none"))

        super().__init__(
            placeholder="Supprimer un élément proposé...",
            min_values=1,
            max_values=1,
            options=options[:25],
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view_ref.user_id:
            await interaction.response.send_message("❌ Ce menu ne t'appartient pas.", ephemeral=True)
            return

        val = self.values[0]
        offer = self.view_ref.session.offers[self.view_ref.user_id]
        if val == "none":
            await interaction.response.defer()
            return

        if val == "money":
            offer.money = 0
        elif val.startswith("item_"):
            item_key = val[5:]
            offer.items.pop(item_key, None)
        elif val.startswith("poke_"):
            poke_key = val[5:]
            offer.pokemons.pop(poke_key, None)
        else:
            await interaction.response.send_message("❌ Élément introuvable.", ephemeral=True)
            return

        offer.elements_confirmed = False
        offer.final_confirmed = False
        self.view_ref.session.offers[self.view_ref.session.other_id(self.view_ref.user_id)].final_confirmed = False
        await interaction.response.send_message("✅ Élément retiré.", ephemeral=True)
        await self.view_ref.cog.refresh_session_ui(self.view_ref.session)
        return


class TradeActionSelect(discord.ui.Select[Any]):
    def __init__(self, view: "TradeUserView"):
        self.view_ref = view
        options = [
            discord.SelectOption(label="Valider mes éléments", value="confirm_elements", emoji="✅"),
            discord.SelectOption(label="Fermer l'échange", value="close", emoji="🛑"),
        ]
        super().__init__(
            placeholder="Choisis une action...",
            min_values=1,
            max_values=1,
            options=options,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view_ref.user_id:
            await interaction.response.send_message("❌ Ce menu ne t'appartient pas.", ephemeral=True)
            return

        choice = self.values[0]
        if choice == "close":
            view = ConfirmActionView(self.view_ref, action="close")
            await interaction.response.send_message(
                "⚠️ Confirmer la fermeture de l'échange ?",
                view=view,
                ephemeral=True,
            )
            return

        view = ConfirmActionView(self.view_ref, action="confirm_elements")
        await interaction.response.send_message(
            "⚠️ Confirmer la validation de tes éléments ?",
            view=view,
            ephemeral=True,
        )


class ConfirmActionView(discord.ui.View):
    def __init__(self, parent: "TradeUserView", action: str):
        super().__init__(timeout=60)
        self.parent = parent
        self.action = action

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.parent.user_id:
            await interaction.response.send_message("❌ Action non autorisée.", ephemeral=True)
            return False
        self.parent.cog.touch_session(self.parent.session)
        return True

    @discord.ui.button(label="Oui", style=discord.ButtonStyle.success, emoji="✅")
    async def yes_btn(self, interaction: discord.Interaction, _: discord.ui.Button[Any]):
        session = self.parent.session
        if session.closed:
            await interaction.response.edit_message(content="❌ Échange déjà fermé.", view=None)
            return

        if self.action == "close":
            await interaction.response.edit_message(content="✅ Fermeture confirmée.", view=None)
            by = _display_user_name(interaction.user)
            await self.parent.cog.close_session(session, f"🛑 Échange fermé par {by}.")
            return

        offer = session.offers[self.parent.user_id]
        if not offer.has_elements():
            await interaction.response.edit_message(content="❌ Tu dois proposer au moins un élément.", view=None)
            return

        offer.elements_confirmed = True
        offer.final_confirmed = False
        await interaction.response.edit_message(content="✅ Tes éléments sont validés.", view=None)

        other_id = session.other_id(self.parent.user_id)
        await self.parent.cog.safe_send_dm(
            other_id,
            f"✅ {_display_user_name(interaction.user)} a validé ses éléments.",
        )
        await self.parent.cog.refresh_session_ui(session)

    @discord.ui.button(label="Non", style=discord.ButtonStyle.danger, emoji="❌")
    async def no_btn(self, interaction: discord.Interaction, _: discord.ui.Button[Any]):
        await interaction.response.edit_message(content="❌ Action annulée.", view=None)


class ConfirmFinalTradeView(discord.ui.View):
    def __init__(self, parent: "TradeUserView"):
        super().__init__(timeout=60)
        self.parent = parent

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.parent.user_id:
            await interaction.response.send_message("❌ Action non autorisée.", ephemeral=True)
            return False
        self.parent.cog.touch_session(self.parent.session)
        return True

    @discord.ui.button(label="Oui, valider l'échange", style=discord.ButtonStyle.success, emoji="🤝")
    async def yes_btn(self, interaction: discord.Interaction, _: discord.ui.Button[Any]):
        session = self.parent.session
        if session.closed:
            await interaction.response.edit_message(content="❌ Échange déjà fermé.", view=None)
            return
        if not session.both_elements_confirmed():
            await interaction.response.edit_message(content="❌ Les deux joueurs doivent d'abord valider leurs éléments.", view=None)
            return

        session.offers[self.parent.user_id].final_confirmed = True
        await interaction.response.edit_message(content="✅ Ta validation finale est enregistrée.", view=None)
        await self.parent.cog.refresh_session_ui(session)

        if session.both_final_confirmed() and not session.countdown_started:
            session.countdown_started = True
            asyncio.create_task(self.parent.cog.finalize_trade_with_countdown(session))

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.danger, emoji="❌")
    async def no_btn(self, interaction: discord.Interaction, _: discord.ui.Button[Any]):
        await interaction.response.edit_message(content="❌ Validation finale annulée.", view=None)


class TradeInviteResponseView(discord.ui.View):
    def __init__(self, cog: "EchangeCog", requester: discord.abc.User, target: discord.abc.User):
        super().__init__(timeout=300)
        self.cog = cog
        self.requester = requester
        self.target = target

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target.id:
            await interaction.response.send_message("❌ Cette invitation ne t'est pas destinée.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Oui", style=discord.ButtonStyle.success, emoji="✅")
    async def yes_btn(self, interaction: discord.Interaction, _: discord.ui.Button[Any]):
        self.cog.release_pending_pair(self.requester.id, self.target.id)

        if self.requester.id in self.cog.user_to_session or self.target.id in self.cog.user_to_session:
            await interaction.response.edit_message(content="❌ L'un des joueurs est déjà en échange.", view=None)
            await self.cog.safe_send_dm(self.requester.id, f"❌ {_display_user_name(self.target)} est déjà en échange.")
            return

        session = await self.cog.start_trade_session(self.requester, self.target)
        if session is None:
            await interaction.response.edit_message(content="❌ Impossible de démarrer l'échange.", view=None)
            return

        await interaction.response.edit_message(content="✅ Échange accepté. Vérifie tes messages privés.", view=None)
        await self.cog.safe_send_dm(self.requester.id, f"✅ {_display_user_name(self.target)} a accepté l'échange.")
        await self.cog.refresh_session_ui(session)

    @discord.ui.button(label="Non", style=discord.ButtonStyle.danger, emoji="❌")
    async def no_btn(self, interaction: discord.Interaction, _: discord.ui.Button[Any]):
        await interaction.response.edit_message(content="❌ Échange refusé.", view=None)
        await self.cog.safe_send_dm(
            self.requester.id,
            f"❌ {_display_user_name(self.target)} a refusé votre demande d'échange.",
        )
        self.cog.release_pending_pair(self.requester.id, self.target.id)

    async def on_timeout(self):
        self.cog.release_pending_pair(self.requester.id, self.target.id)


class TradeStartView(discord.ui.View):
    def __init__(self, cog: "EchangeCog", author: discord.Member | discord.User, guild: discord.Guild | None):
        super().__init__(timeout=600)
        self.cog = cog
        self.author = author
        self.guild = guild
        self.target_id: int | None = None
        self.target_user: discord.abc.User | None = None
        self.message: discord.Message | None = None
        self.invitation_sent = False
        self.sync_items()

    def sync_items(self):
        self.clear_items()

        if not self.invitation_sent:
            choose_btn = discord.ui.Button(label="Choisir le destinataire", style=discord.ButtonStyle.primary, emoji="🎯", row=0)
            choose_btn.callback = self.choose_target_callback
            self.add_item(choose_btn)

        can_validate = self.target_id is not None and self.target_user is not None and not self.invitation_sent
        validate_btn = discord.ui.Button(
            label="Valider le destinataire",
            style=discord.ButtonStyle.success if can_validate else discord.ButtonStyle.secondary,
            disabled=not can_validate,
            emoji="✅",
            row=0,
        )
        validate_btn.callback = self.validate_target_callback
        self.add_item(validate_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Ce menu ne t'appartient pas.", ephemeral=True)
            return False
        return True

    def build_embed(self) -> discord.Embed:
        if self.target_user:
            target_text = f"**{_display_user_name(self.target_user)}** - {self.target_user.id}"
        elif self.target_id:
            target_text = f"ID trouvé mais utilisateur introuvable - {self.target_id}"
        else:
            target_text = "Non défini"

        desc = (
            "__Choisir le destinataire__\n"
            "Clique sur le bouton puis saisis un ID Discord.\n\n"
            f"**Destinataire actuel :** {target_text}"
        )
        embed = self.cog.make_embed(
            guild=self.guild,
            user=self.author,
            title="🤝 Menu d'échange",
            description=desc,
            target_id=self.guild.id if self.guild else None,
            force_global=not bool(self.guild),
        )
        if self.target_user:
            embed.set_thumbnail(url=self.target_user.display_avatar.url)
        return embed

    async def choose_target_callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TargetModal(self))

    async def validate_target_callback(self, interaction: discord.Interaction):
        if self.target_id is None or self.target_user is None:
            await interaction.response.send_message("❌ Destinataire invalide.", ephemeral=True)
            return

        if self.cog.is_user_busy(self.author.id):
            await interaction.response.send_message("❌ Vous êtes déjà en échange.", ephemeral=True)
            return
        if self.cog.is_user_busy(self.target_id):
            await interaction.response.send_message(f"❌ {_display_user_name(self.target_user)} est déjà en échange.", ephemeral=True)
            return

        if not self.cog.reserve_pending_pair(self.author.id, self.target_id):
            await interaction.response.send_message("❌ Impossible de réserver cet échange pour le moment.", ephemeral=True)
            return

        invite_embed = self.cog.make_embed(
            guild=None,
            user=self.author,
            title="📩 Proposition d'échange",
            description=f"{_display_user_name(self.author)} souhaite vous faire un échange.",
            target_id=None,
            force_global=True,
        )
        invite_embed.set_thumbnail(url=self.author.display_avatar.url)
        view = TradeInviteResponseView(self.cog, self.author, self.target_user)

        try:
            await self.target_user.send(embed=invite_embed, view=view)
        except Exception:
            self.cog.release_pending_pair(self.author.id, self.target_id)
            await interaction.response.send_message("❌ Impossible d'envoyer le DM au destinataire.", ephemeral=True)
            return

        self.invitation_sent = True
        self.sync_items()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def refresh(self, interaction: discord.Interaction):
        self.invitation_sent = False
        self.sync_items()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    async def on_timeout(self):
        for child in self.children:
            if hasattr(child, "disabled"):
                child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class TradeUserView(discord.ui.View):
    def __init__(self, cog: "EchangeCog", session: TradeSession, user_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.session = session
        self.user_id = user_id
        self.sync_items()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Cette vue ne t'appartient pas.", ephemeral=True)
            return False
        self.cog.touch_session(self.session)
        return True

    def sync_items(self):
        self.clear_items()
        if self.session.closed:
            return

        offer = self.session.offers[self.user_id]

        can_edit = not offer.elements_confirmed
        add_btn = discord.ui.Button(
            label="Ajouter un élément",
            style=discord.ButtonStyle.secondary if can_edit else discord.ButtonStyle.gray,
            emoji="➕",
            disabled=not can_edit,
            row=3,
        )
        add_btn.callback = self.add_callback

        tip_btn = discord.ui.Button(
            label="Astuce",
            style=discord.ButtonStyle.primary,
            emoji="💡",
            row=3,
        )
        tip_btn.callback = self.tip_callback

        if can_edit and offer.has_elements():
            self.add_item(TradeRemoveSelect(self))

        if self.session.both_elements_confirmed():
            final_btn = discord.ui.Button(label="Valider l'échange", style=discord.ButtonStyle.success, emoji="🤝", row=2)
            final_btn.callback = self.final_validate_callback
            self.add_item(final_btn)

            close_btn = discord.ui.Button(label="Fermer l'échange", style=discord.ButtonStyle.danger, emoji="🛑", row=2)
            close_btn.callback = self.close_button_callback
            self.add_item(close_btn)
        else:
            self.add_item(TradeActionSelect(self))

        self.add_item(add_btn)
        self.add_item(tip_btn)

    async def add_callback(self, interaction: discord.Interaction):
        offer = self.session.offers[self.user_id]
        total_types = (1 if offer.money > 0 else 0) + len(offer.items) + len(offer.pokemons)
        if total_types >= 24:
            await interaction.response.send_message(
                "❌ Trop d'éléments différents. Retire des éléments avant d'en ajouter.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(AddTradeElementModal(self))

    async def tip_callback(self, interaction: discord.Interaction):
        embed = self.cog.make_embed(
            guild=interaction.guild,
            user=interaction.user,
            title="💡 Astuce - Ajout d'élément",
            description="Guide rapide pour remplir ton offre d'échange.",
            target_id=interaction.guild.id if interaction.guild else None,
            force_global=not bool(interaction.guild),
        )
        embed.add_field(
            name="Format",
            value="- élément + quantité\n- Quantité vide = 1",
            inline=False,
        )
        embed.add_field(
            name="Argent",
            value="- argent, money, ₽\n- Exemple: élément=argent, quantité=5000",
            inline=False,
        )
        embed.add_field(
            name="Objets (Balls / Charmes)",
            value=(
                "- Balls: pokeball, superball, hyperball, masterball\n"
                "- Charmes: charme stabilite, charme chroma, charme insigne, charme xp\n"
                "- Exemple: élément=hyperball, quantité=10"
            ),
            inline=False,
        )
        embed.add_field(
            name="Pokémon",
            value="- Classique: 150\n- Shiny: s150\n- Exemple: élément=s25, quantité=2",
            inline=False,
        )
        embed.add_field(
            name="Rappel",
            value="Seuls les Pokémon libres (hors équipe/garderie) sont échangeables.",
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def final_validate_callback(self, interaction: discord.Interaction):
        confirm_view = ConfirmFinalTradeView(self)
        await interaction.response.send_message(
            "⚠️ Confirmez la validation finale de l'échange ?",
            view=confirm_view,
            ephemeral=True,
        )

    async def close_button_callback(self, interaction: discord.Interaction):
        view = ConfirmActionView(self, action="close")
        await interaction.response.send_message("⚠️ Confirmer la fermeture de l'échange ?", view=view, ephemeral=True)

    async def on_timeout(self):
        if not self.session.closed:
            await self.cog.close_session(self.session, "⏱️ Échange fermé: délai expiré.")


class EchangeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.eco = EconomyService(bot)
        self.active_sessions: dict[str, TradeSession] = {}
        self.user_to_session: dict[int, str] = {}
        self.pending_users: set[int] = set()

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

    def is_user_busy(self, user_id: int) -> bool:
        return user_id in self.user_to_session or user_id in self.pending_users

    def reserve_pending_pair(self, user_a: int, user_b: int) -> bool:
        if user_a in self.pending_users or user_b in self.pending_users:
            return False
        if user_a in self.user_to_session or user_b in self.user_to_session:
            return False
        self.pending_users.add(user_a)
        self.pending_users.add(user_b)
        return True

    def release_pending_pair(self, user_a: int, user_b: int):
        self.pending_users.discard(user_a)
        self.pending_users.discard(user_b)

    def touch_session(self, session: TradeSession):
        session.last_activity = time.monotonic()

    async def watch_session_inactivity(self, session_id: str):
        while True:
            await asyncio.sleep(5)
            session = self.active_sessions.get(session_id)
            if session is None or session.closed:
                return
            if time.monotonic() - session.last_activity >= 300:
                await self.close_session(session, "⏱️ Échange fermé automatiquement après 5 minutes d'inactivité.")
                return

    async def safe_send_dm(self, user_id: int, text: str):
        user = self.bot.get_user(user_id)
        if user is None:
            try:
                user = await self.bot.fetch_user(user_id)
            except Exception:
                return
        try:
            await user.send(text)
        except Exception:
            return

    def count_free_pokemon(self, user_id: int, pokemon_id: int, is_shiny: bool) -> int:
        with self.eco._get_conn() as conn:
            row = conn.execute(
                """
                SELECT COUNT(id) AS c
                FROM inventory
                WHERE user_id = ? AND pokemon_id = ? AND is_shiny = ?
                  AND id NOT IN (SELECT inventory_id FROM teams WHERE user_id = ?)
                  AND id NOT IN (SELECT pokemon_inv_id FROM daycare WHERE user_id = ?)
                """,
                (user_id, pokemon_id, int(is_shiny), user_id, user_id),
            ).fetchone()
        return int(row["c"]) if row else 0

    async def start_trade_session(self, requester: discord.abc.User, target: discord.abc.User) -> TradeSession | None:
        if self.is_user_busy(requester.id) or self.is_user_busy(target.id):
            return None

        session_id = str(uuid.uuid4())
        session = TradeSession(
            session_id=session_id,
            requester=requester,
            target=target,
            offers={
                requester.id: TradeOfferState(),
                target.id: TradeOfferState(),
            },
        )

        self.active_sessions[session_id] = session
        self.user_to_session[requester.id] = session_id
        self.user_to_session[target.id] = session_id
        self.touch_session(session)
        session.inactivity_task = asyncio.create_task(self.watch_session_inactivity(session_id))

        requester_view = TradeUserView(self, session, requester.id)
        target_view = TradeUserView(self, session, target.id)
        session.view_by_user[requester.id] = requester_view
        session.view_by_user[target.id] = target_view

        try:
            requester_msg = await requester.send(
                embed=self.build_session_embed(session, requester.id),
                view=requester_view,
            )
            target_msg = await target.send(
                embed=self.build_session_embed(session, target.id),
                view=target_view,
            )
        except Exception:
            self.cleanup_session(session)
            await self.safe_send_dm(requester.id, "❌ Impossible d'ouvrir le salon DM d'échange.")
            await self.safe_send_dm(target.id, "❌ Impossible d'ouvrir le salon DM d'échange.")
            return None

        session.message_by_user[requester.id] = requester_msg
        session.message_by_user[target.id] = target_msg
        return session

    def build_offer_lines(self, offer: TradeOfferState) -> list[str]:
        lines: list[str] = []
        if offer.money > 0:
            lines.append(f"- 💰 Argent: {format_price(offer.money)} {POKEDOLLAR_EMOJI}")

        for key, qty in offer.items.items():
            emoji = SHOP_EMOJIS.get(key, "🎒")
            label = SHOP_LABELS.get(key, key)
            lines.append(f"- {emoji} {label}: x{format_price(qty)}")

        for data in offer.pokemons.values():
            shiny_str = "✨ Shiny" if data["is_shiny"] else "Classique"
            lines.append(f"- #{data['id']} {data['name_fr']} ({shiny_str}) x{data['qty']}")
        return lines

    def build_session_embed(self, session: TradeSession, viewer_id: int) -> discord.Embed:
        me = session.requester if viewer_id == session.requester.id else session.target
        other = session.target if viewer_id == session.requester.id else session.requester

        my_offer = session.offers[viewer_id]
        other_offer = session.offers[other.id]

        my_lines = self.build_offer_lines(my_offer)
        other_lines = self.build_offer_lines(other_offer)

        my_status = "✅ Validé" if my_offer.elements_confirmed else "⌛ En préparation"
        other_status = "✅ Validé" if other_offer.elements_confirmed else "⌛ En préparation"

        desc = (
            f"**Toi :** {_display_user_name(me)}\n"
            f"**Partenaire :** {_display_user_name(other)}\n\n"
            f"**Mes éléments ({my_status})**\n"
            + ("\n".join(my_lines) if my_lines else "- Aucun")
            + "\n\n"
            + f"**Éléments du partenaire ({other_status})**\n"
            + ("\n".join(other_lines) if other_lines else "- Aucun")
        )

        if session.both_elements_confirmed():
            my_final = "✅" if my_offer.final_confirmed else "⌛"
            other_final = "✅" if other_offer.final_confirmed else "⌛"
            desc += (
                "\n\n**Validation finale**\n"
                f"- Toi: {my_final}\n"
                f"- Partenaire: {other_final}"
            )

        title = "🤝 Échange en cours"
        if session.closed:
            title = "🛑 Échange fermé"
            if session.closing_reason:
                desc += f"\n\n{session.closing_reason}"

        embed = self.make_embed(
            guild=None,
            user=me,
            title=title,
            description=desc,
            target_id=None,
            force_global=True,
        )
        embed.set_thumbnail(url=other.display_avatar.url)
        return embed

    async def refresh_session_ui(self, session: TradeSession):
        if session.closed:
            return
        for user_id, view in session.view_by_user.items():
            view.sync_items()
            message = session.message_by_user.get(user_id)
            if message is None:
                continue
            try:
                await message.edit(embed=self.build_session_embed(session, user_id), view=view)
            except Exception:
                continue

    async def close_session(self, session: TradeSession, reason: str):
        if session.closed:
            return
        session.closed = True
        session.closing_reason = reason

        for user_id, view in session.view_by_user.items():
            for child in view.children:
                if hasattr(child, "disabled"):
                    child.disabled = True
            message = session.message_by_user.get(user_id)
            if message is None:
                continue
            try:
                await message.edit(embed=self.build_session_embed(session, user_id), view=view)
            except Exception:
                continue

        other_notice = f"ℹ️ {reason}"
        await self.safe_send_dm(session.requester.id, other_notice)
        await self.safe_send_dm(session.target.id, other_notice)
        self.cleanup_session(session)

    def cleanup_session(self, session: TradeSession):
        if session.inactivity_task and not session.inactivity_task.done():
            session.inactivity_task.cancel()
        self.user_to_session.pop(session.requester.id, None)
        self.user_to_session.pop(session.target.id, None)
        self.active_sessions.pop(session.session_id, None)

    def _select_inventory_ids_for_offer(self, conn: Any, user_id: int, offer: TradeOfferState) -> tuple[bool, str, list[int]]:
        selected: list[int] = []
        for data in offer.pokemons.values():
            pokemon_id = int(data["id"])
            is_shiny = int(data["is_shiny"])
            qty = int(data["qty"])
            rows = conn.execute(
                """
                SELECT id
                FROM inventory
                WHERE user_id = ? AND pokemon_id = ? AND is_shiny = ?
                  AND id NOT IN (SELECT inventory_id FROM teams WHERE user_id = ?)
                  AND id NOT IN (SELECT pokemon_inv_id FROM daycare WHERE user_id = ?)
                ORDER BY level ASC, id ASC
                LIMIT ?
                """,
                (user_id, pokemon_id, is_shiny, user_id, user_id, qty),
            ).fetchall()

            if len(rows) < qty:
                return False, f"❌ {user_id} n'a plus assez de Pokémon #{pokemon_id} libres.", []
            selected.extend([r["id"] for r in rows])

        return True, "", selected

    def execute_trade(self, session: TradeSession) -> tuple[bool, str]:
        requester_id = session.requester.id
        target_id = session.target.id
        request_offer = session.offers[requester_id]
        target_offer = session.offers[target_id]

        try:
            with self.eco._get_conn() as conn:
                req_user_row = conn.execute("SELECT * FROM users WHERE user_id = ?", (requester_id,)).fetchone()
                tgt_user_row = conn.execute("SELECT * FROM users WHERE user_id = ?", (target_id,)).fetchone()
                if not req_user_row or not tgt_user_row:
                    return False, "❌ Profil introuvable pour l'un des joueurs."

                if int(req_user_row["balance"]) < request_offer.money:
                    return False, "❌ L'initiateur n'a plus assez d'argent."
                if int(tgt_user_row["balance"]) < target_offer.money:
                    return False, "❌ Le destinataire n'a plus assez d'argent."

                for item_key, qty in request_offer.items.items():
                    if int(req_user_row[item_key]) < qty:
                        return False, f"❌ L'initiateur n'a plus assez de {SHOP_LABELS.get(item_key, item_key)}."

                for item_key, qty in target_offer.items.items():
                    if int(tgt_user_row[item_key]) < qty:
                        return False, f"❌ Le destinataire n'a plus assez de {SHOP_LABELS.get(item_key, item_key)}."

                ok, err, req_ids = self._select_inventory_ids_for_offer(conn, requester_id, request_offer)
                if not ok:
                    return False, err
                ok, err, tgt_ids = self._select_inventory_ids_for_offer(conn, target_id, target_offer)
                if not ok:
                    return False, err

                if request_offer.money > 0:
                    conn.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (request_offer.money, requester_id))
                    conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (request_offer.money, target_id))
                if target_offer.money > 0:
                    conn.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (target_offer.money, target_id))
                    conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (target_offer.money, requester_id))

                for item_key, qty in request_offer.items.items():
                    conn.execute(f"UPDATE users SET {item_key} = {item_key} - ? WHERE user_id = ?", (qty, requester_id))
                    conn.execute(f"UPDATE users SET {item_key} = {item_key} + ? WHERE user_id = ?", (qty, target_id))

                for item_key, qty in target_offer.items.items():
                    conn.execute(f"UPDATE users SET {item_key} = {item_key} - ? WHERE user_id = ?", (qty, target_id))
                    conn.execute(f"UPDATE users SET {item_key} = {item_key} + ? WHERE user_id = ?", (qty, requester_id))

                if req_ids:
                    conn.executemany(
                        "UPDATE inventory SET user_id = ? WHERE id = ?",
                        [(target_id, inv_id) for inv_id in req_ids],
                    )
                if tgt_ids:
                    conn.executemany(
                        "UPDATE inventory SET user_id = ? WHERE id = ?",
                        [(requester_id, inv_id) for inv_id in tgt_ids],
                    )

            return True, "✅ Échange effectué avec succès."
        except Exception as exc:
            return False, f"❌ Erreur système: {exc}"

    async def finalize_trade_with_countdown(self, session: TradeSession):
        for second in range(5, 0, -1):
            if session.closed:
                return
            await self.safe_send_dm(session.requester.id, f"⏳ Validation finale dans {second}...")
            await self.safe_send_dm(session.target.id, f"⏳ Validation finale dans {second}...")
            await asyncio.sleep(1)

        if session.closed:
            return

        ok, msg = self.execute_trade(session)
        if ok:
            await self.close_session(session, f"🎉 {msg}")
        else:
            await self.close_session(session, msg)

    @commands.hybrid_command(name="echange", description="Ouvre le menu d'échange Pokémon en message privé.")
    async def echange(self, ctx: commands.Context[commands.Bot]):
        self.eco.ensure_user(ctx.author.id)

        view = TradeStartView(self, ctx.author, ctx.guild)
        embed = view.build_embed()
        message = await ctx.send(embed=embed, view=view, reference=ctx.message if ctx.message else None)
        view.message = message


async def setup(bot: commands.Bot):
    if bot.get_cog("EchangeCog"):
        await bot.remove_cog("EchangeCog")
    await bot.add_cog(EchangeCog(bot))
