import re
from typing import Any

import aiohttp
import discord
from discord.ext import commands

from .utils import (
    BALL_EMOJIS,
    BALL_FIELDS,
    BALL_LABELS,
    CHARM_EMOJIS,
    CHARM_FIELDS,
    CHARM_LABELS,
    SUPERBONBON_EMOJI,
    EconomyService,
)

try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

POKEDOLLAR_EMOJI = "₽"

def format_price(amount: int) -> str:
    return f"{amount:,}".replace(",", " ")

# Map pour retrouver facilement la clé en base de données à partir de ce que l'utilisateur tape
ITEM_ALIASES = {
    "pokeball": "pokeball", "poke ball": "pokeball",
    "superball": "superball", "super ball": "superball",
    "hyperball": "hyperball", "hyper ball": "hyperball",
    "masterball": "masterball", "master ball": "masterball",
    "superbonbon": "superbonbon", "bonbon": "superbonbon",
    "charme stabilite": "charme_stabilite", "stabilite": "charme_stabilite", "charme_stabilite": "charme_stabilite",
    "charme chroma": "charme_chroma", "chroma": "charme_chroma", "charme_chroma": "charme_chroma",
    "charme insigne": "charme_insigne", "insigne": "charme_insigne", "charme_insigne": "charme_insigne",
}

# Utilitaires pour mapper les noms propres (déclarés en haut pour éviter les NameError)
SHOP_LABELS = {**BALL_LABELS, "superbonbon": "Superbonbon", **CHARM_LABELS}
SHOP_EMOJIS = {**BALL_EMOJIS, "superbonbon": SUPERBONBON_EMOJI, **CHARM_EMOJIS}

class DonationState:
    """Stocke l'état du don en cours pour un utilisateur."""
    def __init__(self):
        self.target_id: int | None = None
        self.money: int = 0
        self.items: dict[str, int] = {}
        self.pokemons: dict[str, dict[str, Any]] = {} # Clé: "id_isShiny", Valeur: {id, is_shiny, qty, name_fr}

class TargetModal(discord.ui.Modal, title="Choisir le destinataire"):
    target_input = discord.ui.TextInput(
        label="ID Discord de l'utilisateur",
        placeholder="Ex: 123456789012345678",
        required=True,
        max_length=30
    )

    def __init__(self, view: "DonationView"):
        super().__init__()
        self.view_ref = view

    async def on_submit(self, interaction: discord.Interaction):
        raw_id = self.target_input.value.strip()
        match = re.search(r'\d+', raw_id)
        if not match:
            await interaction.response.send_message("❌ Format d'ID invalide. Veuillez entrer un nombre.", ephemeral=True)
            return

        target_id = int(match.group(0))
        if target_id == interaction.user.id:
            await interaction.response.send_message("❌ Vous ne pouvez pas vous faire un don à vous-même.", ephemeral=True)
            return

        self.view_ref.state.target_id = target_id
        await self.view_ref.update_ui(interaction)

class AddElementModal(discord.ui.Modal, title="Ajouter un élément au don"):
    element_input = discord.ui.TextInput(
        label="Élément (argent, objet, ou ID Pokémon)",
        placeholder="Ex: argent, hyperball, 150, s150",
        required=True,
        max_length=30
    )
    qty_input = discord.ui.TextInput(
        label="Quantité",
        placeholder="Laissez vide pour 1",
        required=False,
        max_length=10,
        default="1"
    )

    def __init__(self, view: "DonationView"):
        super().__init__()
        self.view_ref = view

    async def on_submit(self, interaction: discord.Interaction):
        element = self.element_input.value.strip().lower()
        try:
            qty = int(self.qty_input.value.strip() or "1")
        except ValueError:
            await interaction.response.send_message("❌ La quantité doit être un nombre valide.", ephemeral=True)
            return

        if qty <= 0:
            await interaction.response.send_message("❌ La quantité doit être supérieure à 0.", ephemeral=True)
            return

        cog = self.view_ref.cog
        state = self.view_ref.state
        author_id = interaction.user.id

        # 1. Gestion de l'Argent
        if element in ["argent", "money", "pokedollar", "pokédollar", "pokedollars", "₽"]:
            current_pending = state.money
            with cog.eco._get_conn() as conn:
                row = conn.execute("SELECT balance FROM users WHERE user_id = ?", (author_id,)).fetchone()
            balance = row["balance"] if row else 0

            if current_pending + qty > balance:
                await interaction.response.send_message(f"❌ Solde insuffisant. (Possédé: {format_price(balance)} {POKEDOLLAR_EMOJI})", ephemeral=True)
                return
            state.money += qty
            await self.view_ref.update_ui(interaction)
            return

        # 2. Gestion des Objets
        if element in ITEM_ALIASES:
            item_key = ITEM_ALIASES[element]
            current_pending = state.items.get(item_key, 0)
            
            with cog.eco._get_conn() as conn:
                row = conn.execute(f"SELECT {item_key} FROM users WHERE user_id = ?", (author_id,)).fetchone()
            owned = row[item_key] if row else 0

            if current_pending + qty > owned:
                await interaction.response.send_message(f"❌ Pas assez de {SHOP_LABELS.get(item_key, item_key)}. (Possédé: {format_price(owned)})", ephemeral=True)
                return
            
            state.items[item_key] = current_pending + qty
            await self.view_ref.update_ui(interaction)
            return

        # 3. Gestion des Pokémon (ID normal ou shiny "s150")
        match = re.match(r'^(s?)(\d+)$', element)
        if match:
            is_shiny = bool(match.group(1))
            poke_id = int(match.group(2))
            
            with cog.eco._get_conn() as conn:
                count_row = conn.execute(
                    """
                    SELECT COUNT(id) as c FROM inventory
                    WHERE user_id = ? AND pokemon_id = ? AND is_shiny = ?
                      AND id NOT IN (SELECT inventory_id FROM teams WHERE user_id = ?)
                      AND id NOT IN (SELECT pokemon_inv_id FROM daycare WHERE user_id = ?)
                    """,
                    (author_id, poke_id, int(is_shiny), author_id, author_id)
                ).fetchone()
            owned_free = count_row["c"] if count_row else 0
            
            dict_key = f"{poke_id}_{int(is_shiny)}"
            current_pending = state.pokemons.get(dict_key, {}).get("qty", 0)

            if current_pending + qty > owned_free:
                status = "✨ Shiny " if is_shiny else ""
                msg = f"❌ Tu ne possèdes pas assez de Pokémon #{poke_id} {status}libres (pas en équipe/garderie)."
                await interaction.response.send_message(f"{msg}\nPossédé et libre: {owned_free}", ephemeral=True)
                return

            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                name_fr = await cog.eco.get_species_name_fr(session, poke_id)

            if dict_key not in state.pokemons:
                state.pokemons[dict_key] = {"id": poke_id, "is_shiny": is_shiny, "qty": 0, "name_fr": name_fr}
            state.pokemons[dict_key]["qty"] += qty
            
            await self.view_ref.update_ui(interaction)
            return

        await interaction.response.send_message("❌ Élément non reconnu. Exemples valides : `argent`, `hyperball`, `150`, `s150`.", ephemeral=True)

class DonationRemoveSelect(discord.ui.Select):
    def __init__(self, view: "DonationView"):
        self.view_ref = view
        options = []
        state = view.state

        if state.money > 0:
            options.append(discord.SelectOption(label=f"Argent: {format_price(state.money)} {POKEDOLLAR_EMOJI}", value="money", emoji="💰"))
        
        for k, v in state.items.items():
            label = SHOP_LABELS.get(k, k.capitalize())
            options.append(discord.SelectOption(label=f"{label} x{format_price(v)}", value=f"item_{k}", emoji="🎒"))
            
        for k, data in state.pokemons.items():
            shiny_str = "✨" if data["is_shiny"] else "🐾"
            options.append(discord.SelectOption(label=f"#{data['id']} {data['name_fr']} x{data['qty']}", value=f"poke_{k}", emoji=shiny_str))

        if not options:
            options.append(discord.SelectOption(label="Aucun élément", value="none", description="La liste est vide"))

        super().__init__(placeholder="Retirer un élément de la liste...", min_values=1, max_values=1, options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        state = self.view_ref.state
        
        if val == "none":
            await interaction.response.defer()
            return
        elif val == "money":
            state.money = 0
        elif val.startswith("item_"):
            item_key = val[5:]
            if item_key in state.items:
                del state.items[item_key]
        elif val.startswith("poke_"):
            poke_key = val[5:]
            if poke_key in state.pokemons:
                del state.pokemons[poke_key]

        await self.view_ref.update_ui(interaction)


class DonationConfirmView(discord.ui.View):
    def __init__(self, cog: "DonCog", parent_view: "DonationView", author: discord.Member | discord.User):
        super().__init__(timeout=60)
        self.cog = cog
        self.parent_view = parent_view
        self.author = author

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Vous ne pouvez pas confirmer ce don.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Oui, confirmer le don", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        success, msg = await self.cog.execute_donation(self.author.id, self.parent_view.state)
        
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
                
        embed = interaction.message.embeds[0]
        embed.color = 0x2ECC71 if success else 0xE74C3C
        embed.add_field(name="Résultat", value=msg, inline=False)
        
        await interaction.edit_original_response(embed=embed, view=self)

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        
        embed = interaction.message.embeds[0]
        embed.color = 0xE74C3C
        embed.add_field(name="Résultat", value="❌ Don annulé.", inline=False)
        
        await interaction.response.edit_message(embed=embed, view=self)


class DonationView(discord.ui.View):
    def __init__(self, cog: "DonCog", author: discord.Member | discord.User):
        super().__init__(timeout=300)
        self.cog = cog
        self.author = author
        self.state = DonationState()
        self.message: discord.Message | None = None
        self._sync_components()

    def _sync_components(self):
        self.clear_items()
        
        # Bouton 1 : Choisir destinataire
        btn_target = discord.ui.Button(label="Choisir le destinataire", style=discord.ButtonStyle.primary, emoji="🎯", row=0)
        btn_target.callback = self.target_callback
        self.add_item(btn_target)

        # Bouton 2 : Ajouter élément
        btn_add = discord.ui.Button(label="Ajouter un élément", style=discord.ButtonStyle.secondary, emoji="➕", row=0)
        btn_add.callback = self.add_callback
        self.add_item(btn_add)

        # Sélecteur pour supprimer
        has_elements = self.state.money > 0 or bool(self.state.items) or bool(self.state.pokemons)
        if has_elements:
            select = DonationRemoveSelect(self)
            self.add_item(select)

        # Bouton 3 : Valider
        can_donate = self.state.target_id is not None and has_elements
        btn_confirm = discord.ui.Button(label="Donner", style=discord.ButtonStyle.success if can_donate else discord.ButtonStyle.secondary, emoji="🎁", disabled=not can_donate, row=2)
        btn_confirm.callback = self.confirm_callback
        self.add_item(btn_confirm)

    async def target_callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TargetModal(self))

    async def add_callback(self, interaction: discord.Interaction):
        total_types = (1 if self.state.money > 0 else 0) + len(self.state.items) + len(self.state.pokemons)
        if total_types >= 24:
            await interaction.response.send_message("❌ La liste contient trop d'éléments différents. Validez ou retirez-en.", ephemeral=True)
            return
        await interaction.response.send_modal(AddElementModal(self))

    async def confirm_callback(self, interaction: discord.Interaction):
        target_id = self.state.target_id
        if not target_id:
            await interaction.response.send_message("❌ Vous n'avez pas choisi de destinataire.", ephemeral=True)
            return
        
        confirm_view = DonationConfirmView(self.cog, self, self.author)
        embed = self.build_embed()
        embed.color = 0xE67E22
        embed.title = "⚠️ Confirmation du don"
        embed.description = "Veuillez vérifier les éléments ci-dessous avant de confirmer définitivement."
        
        await interaction.response.edit_message(embed=embed, view=confirm_view)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        return True

    def build_embed(self) -> discord.Embed:
        target_str = f"<@{self.state.target_id}>" if self.state.target_id else "`Non défini`"
        
        embed = discord.Embed(title="🎁 Menu de Don", color=0x2B2D31)
        embed.description = f"**Destinataire :** {target_str}\n\n**Contenu du don :**\n"
        
        lines = []
        if self.state.money > 0:
            lines.append(f"> 💰 **Argent :** {format_price(self.state.money)} {POKEDOLLAR_EMOJI}")
            
        for k, v in self.state.items.items():
            label = SHOP_LABELS.get(k, k.capitalize())
            emoji = SHOP_EMOJIS.get(k, "🎒")
            lines.append(f"> {emoji} **{label} :** x{format_price(v)}")
            
        for data in self.state.pokemons.values():
            shiny_str = "✨ Shiny" if data["is_shiny"] else "Classique"
            lines.append(f"> 🐾 **{data['name_fr']}** (#{data['id']} - {shiny_str}) : x{data['qty']}")

        if not lines:
            embed.description += "> *La liste est vide.*"
        else:
            embed.description += "\n".join(lines)
            
        embed.set_footer(text="Utilisez les boutons ci-dessous pour configurer votre don.")
        return embed

    async def update_ui(self, interaction: discord.Interaction):
        self._sync_components()
        embed = self.build_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        for item in self.children:
            if hasattr(item, 'disabled'):
                item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class DonCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.eco = EconomyService(bot)

    async def execute_donation(self, author_id: int, state: DonationState) -> tuple[bool, str]:
        """Exécute la transaction sécurisée de bout en bout."""
        target_id = state.target_id
        if not target_id:
            return False, "❌ Aucun destinataire."

        self.eco.ensure_user(author_id)
        self.eco.ensure_user(target_id)

        try:
            with self.eco._get_conn() as conn:
                row = conn.execute("SELECT * FROM users WHERE user_id = ?", (author_id,)).fetchone()
                if not row:
                    return False, "❌ Votre profil est introuvable."

                if state.money > 0 and row["balance"] < state.money:
                    return False, "❌ Vous n'avez plus assez d'argent pour ce don."

                for item_key, qty in state.items.items():
                    if row[item_key] < qty:
                        return False, f"❌ Vous n'avez plus assez de {SHOP_LABELS.get(item_key, item_key)}."

                inventory_ids_to_transfer = []
                for data in state.pokemons.values():
                    poke_id = data["id"]
                    is_shiny = int(data["is_shiny"])
                    qty = data["qty"]

                    rows = conn.execute(
                        """
                        SELECT id FROM inventory
                        WHERE user_id = ? AND pokemon_id = ? AND is_shiny = ?
                          AND id NOT IN (SELECT inventory_id FROM teams WHERE user_id = ?)
                          AND id NOT IN (SELECT pokemon_inv_id FROM daycare WHERE user_id = ?)
                        ORDER BY level ASC, id ASC
                        LIMIT ?
                        """,
                        (author_id, poke_id, is_shiny, author_id, author_id, qty)
                    ).fetchall()

                    if len(rows) < qty:
                        return False, f"❌ Vous n'avez plus assez de Pokémon #{poke_id} libres."
                    
                    inventory_ids_to_transfer.extend([r["id"] for r in rows])

                # EXÉCUTION
                if state.money > 0:
                    conn.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (state.money, author_id))
                    conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (state.money, target_id))
                
                for item_key, qty in state.items.items():
                    conn.execute(f"UPDATE users SET {item_key} = {item_key} - ? WHERE user_id = ?", (qty, author_id))
                    conn.execute(f"UPDATE users SET {item_key} = {item_key} + ? WHERE user_id = ?", (qty, target_id))

                if inventory_ids_to_transfer:
                    conn.executemany(
                        "UPDATE inventory SET user_id = ? WHERE id = ?",
                        [(target_id, inv_id) for inv_id in inventory_ids_to_transfer]
                    )

            return True, f"✅ Le don à <@{target_id}> a été effectué avec succès !"

        except Exception as e:
            return False, f"❌ Une erreur système est survenue : {e}"

    @commands.hybrid_command(name="don", description="Fais un don à un autre joueur.")
    async def don(self, ctx: commands.Context[commands.Bot]):
        self.eco.ensure_user(ctx.author.id)
        
        view = DonationView(self, ctx.author)
        embed = view.build_embed()
        
        msg = await ctx.send(embed=embed, view=view, reference=ctx.message if ctx.message else None)
        view.message = msg


async def setup(bot: commands.Bot):
    if bot.get_cog("DonCog"):
        await bot.remove_cog("DonCog")
    await bot.add_cog(DonCog(bot))