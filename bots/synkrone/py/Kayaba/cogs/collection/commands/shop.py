import discord
from discord.ext import commands
import json
import os
import uuid
from typing import List

# ==========================================
# CONFIGURATION & CHEMINS
# ==========================================
BASE_DIR = os.path.dirname(__file__)
DATA_DEV_DIR = os.path.normpath(os.path.join(BASE_DIR, '..', 'data', 'dev'))
FAMILLE_DIR = os.path.join(DATA_DEV_DIR, 'famille')

try:
    from .collect import USER_DATA_PATH
except ImportError:
    USER_DATA_PATH = None

if USER_DATA_PATH is None:
    current_dir = os.path.dirname(__file__)
    user_data_path = os.path.normpath(os.path.join(current_dir, '..', 'data', 'interserver'))
    if os.path.exists(user_data_path):
        USER_DATA_PATH = user_data_path

try:
    from cogs.developpeur.commands.embed_type.utils import config_manager
except ImportError:
    config_manager = None

EMOJI_FILE = os.path.join(BASE_DIR, '..', 'emoji.json')
EMOJIS = {}
if os.path.exists(EMOJI_FILE):
    try:
        with open(EMOJI_FILE, 'r', encoding='utf-8') as f:
            EMOJIS = json.load(f)
    except:
        pass

try:
    from cogs.collection.commands.mp import MPManager
except ImportError:
    MPManager = None

# ==========================================
# MANAGER DU SHOP
# ==========================================
class ShopManager:
    def __init__(self):
        # Stocker shop.json dans le dossier shop au lieu de interserver
        shop_dir = os.path.join(os.path.dirname(__file__), '..', 'data', 'shop')
        os.makedirs(shop_dir, exist_ok=True)
        self.shop_file = os.path.join(shop_dir, 'shop.json')
        if not os.path.exists(self.shop_file):
            with open(self.shop_file, 'w', encoding='utf-8') as f:
                json.dump([], f)

    def load_shop(self):
        try:
            with open(self.shop_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []

    def save_shop(self, data):
        with open(self.shop_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def get_user_data(self, user_id: int):
        if not USER_DATA_PATH: return {}
        user_file = USER_DATA_PATH / f"{user_id}.json"
        if not user_file.exists(): return {}
        with open(user_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_user_data(self, user_id: int, data):
        if not USER_DATA_PATH: return False
        user_file = USER_DATA_PATH / f"{user_id}.json"
        with open(user_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True

    def get_user_families(self, user_id: int):
        data = self.get_user_data(user_id)
        collection = data.get('collection', {})
        user_families = {}
        
        if not os.path.exists(FAMILLE_DIR): return user_families
        for famille_name in os.listdir(FAMILLE_DIR):
            famille_path = os.path.join(FAMILLE_DIR, famille_name)
            if not os.path.isdir(famille_path): continue
            
            personnages_file = os.path.join(famille_path, 'personnages.json')
            if not os.path.exists(personnages_file): continue
            
            try:
                with open(personnages_file, 'r', encoding='utf-8') as f:
                    fam_data = json.load(f)
                    user_cards = [p for p in fam_data.get('personnages', []) if p.get('id') in collection and collection[p['id']] > 0]
                    if user_cards:
                        user_families[famille_name] = {
                            'display_name': famille_name,
                            'personnages': user_cards
                        }
            except:
                continue
        return user_families

    def list_card(self, user_id: int, card: dict, price: int):
        data = self.get_user_data(user_id)
        if not data or 'collection' not in data or data['collection'].get(card['id'], 0) < 1:
            return False

        # Retirer de l'inventaire
        data['collection'][card['id']] -= 1
        if data['collection'][card['id']] == 0:
            del data['collection'][card['id']]
        self.save_user_data(user_id, data)

        # Ajouter au shop
        shop_data = self.load_shop()
        listing = {
            'listing_id': str(uuid.uuid4()),
            'seller_id': user_id,
            'card': card,
            'price': price
        }
        shop_data.append(listing)
        self.save_shop(shop_data)
        return True

    def cancel_listing(self, user_id: int, listing_id: str):
        shop_data = self.load_shop()
        listing = next((l for l in shop_data if l['listing_id'] == listing_id and l['seller_id'] == user_id), None)
        
        if not listing: return False
        
        # Rembourser la carte
        data = self.get_user_data(user_id)
        if 'collection' not in data: data['collection'] = {}
        data['collection'][listing['card']['id']] = data['collection'].get(listing['card']['id'], 0) + 1
        self.save_user_data(user_id, data)

        # Retirer du shop
        shop_data.remove(listing)
        self.save_shop(shop_data)
        return True

    def buy_listing(self, buyer_id: int, listing_id: str):
        shop_data = self.load_shop()
        listing = next((l for l in shop_data if l['listing_id'] == listing_id), None)
        
        if not listing: return False, "Cette offre n'existe plus."
        if listing['seller_id'] == buyer_id: return False, "Vous ne pouvez pas acheter votre propre carte."

        buyer_data = self.get_user_data(buyer_id)
        price = listing['price']

        if buyer_data.get('col', 0) < price:
            return False, "Fonds insuffisants."

        # Retirer Col à l'acheteur et donner la carte
        buyer_data['col'] -= price
        if 'collection' not in buyer_data: buyer_data['collection'] = {}
        buyer_data['collection'][listing['card']['id']] = buyer_data['collection'].get(listing['card']['id'], 0) + 1
        self.save_user_data(buyer_id, buyer_data)

        # Donner Col au vendeur
        seller_data = self.get_user_data(listing['seller_id'])
        seller_data['col'] = seller_data.get('col', 0) + price
        self.save_user_data(listing['seller_id'], seller_data)

        # Retirer l'offre
        shop_data.remove(listing)
        self.save_shop(shop_data)

        return True, listing

# ==========================================
# VUES INTERACTIVES
# ==========================================
class ShopMainView(discord.ui.View):
    def __init__(self, ctx, manager: ShopManager):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.manager = manager
        self._build_view()

    def _build_view(self):
        self.clear_items()
        
        btn_sell = discord.ui.Button(label="Mettre en vente", emoji="📈", style=discord.ButtonStyle.success)
        btn_sell.callback = self.open_sell_menu
        self.add_item(btn_sell)

        btn_remove = discord.ui.Button(label="Retirer une vente", emoji="📉", style=discord.ButtonStyle.danger)
        btn_remove.callback = self.open_remove_menu
        self.add_item(btn_remove)

        btn_shop = discord.ui.Button(label="Voir le shop", emoji="🛒", style=discord.ButtonStyle.primary)
        btn_shop.callback = self.open_global_shop
        self.add_item(btn_shop)

    def create_embed(self):
        shop_data = self.manager.load_shop()
        user_listings = [l for l in shop_data if l['seller_id'] == self.ctx.author.id][:25]
        
        desc = "Bienvenue dans le Marché des Joueurs !\n\n**Vos offres actuelles :**\n"
        if not user_listings:
            desc += "> *Vous n'avez aucune carte en vente actuellement.*"
        else:
            for l in user_listings:
                c = l['card']
                rarity_emoji = {"Légendaire": "🟡", "Epique": "🟣", "Rare": "🔵", "Commun": "🟢"}.get(c.get('rarete', 'Commun'), "🟢")
                desc += f"• {rarity_emoji} **{c['nom']}** - `#{c['id']}` - **{l['price']:,}** <:col:1482462727468486738>\n"

        # Utiliser config_manager
        if config_manager:
            try:
                embed = config_manager.get_formatted_embed(
                    self.ctx.guild, self.ctx.author, self.ctx.bot,
                    title="🛒 Marché des Joueurs",
                    description=desc,
                    target_id=self.ctx.guild.id if self.ctx.guild else None
                )
                # Ajouter l'image du bot en thumbnail
                if self.ctx.bot and self.ctx.bot.user.avatar:
                    embed.set_thumbnail(url=self.ctx.bot.user.avatar.url)
            except Exception as e:
                print(f"[DEBUG] Erreur config_manager shop: {e}")
                embed = discord.Embed(title="🛒 Marché des Joueurs", description=desc, color=0x2b2d31)
                if self.ctx.bot and self.ctx.bot.user.avatar:
                    embed.set_thumbnail(url=self.ctx.bot.user.avatar.url)
                    embed.set_footer(
                        text="Système Kayaba Collection",
                        icon_url=self.ctx.bot.user.avatar.url
                    )
                else:
                    embed.set_footer(text="Système Kayaba Collection")
        else:
            embed = discord.Embed(title="🛒 Marché des Joueurs", description=desc, color=0x2b2d31)
            if self.ctx.bot and self.ctx.bot.user.avatar:
                embed.set_thumbnail(url=self.ctx.bot.user.avatar.url)
                embed.set_footer(
                    text="Système Kayaba Collection",
                    icon_url=self.ctx.bot.user.avatar.url
                )
            else:
                embed.set_footer(text="Système Kayaba Collection")
        return embed

    async def open_sell_menu(self, interaction: discord.Interaction):
        view = ShopFamilySelectView(self.ctx, self.manager)
        await interaction.response.edit_message(embed=view.create_embed(), view=view)

    async def open_remove_menu(self, interaction: discord.Interaction):
        shop_data = self.manager.load_shop()
        user_listings = [l for l in shop_data if l['seller_id'] == self.ctx.author.id][:25]
        
        if not user_listings:
            await interaction.response.send_message("❌ Vous n'avez aucune offre active.", ephemeral=True)
            return
            
        view = ShopRemoveView(self.ctx, self.manager, user_listings)
        await interaction.response.edit_message(embed=view.create_embed(), view=view)

    async def open_global_shop(self, interaction: discord.Interaction):
        shop_data = self.manager.load_shop()
        if not shop_data:
            await interaction.response.send_message("❌ Le marché est actuellement vide.", ephemeral=True)
            return
            
        view = ShopGlobalView(self.ctx, self.manager, shop_data)
        await interaction.response.edit_message(embed=view.create_embed(), view=view)


class ShopFamilySelectView(discord.ui.View):
    def __init__(self, ctx, manager):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.manager = manager
        self.families = list(self.manager.get_user_families(self.ctx.author.id).items())
        self._build_view()

    def _build_view(self):
        options = [discord.SelectOption(label=f_data['display_name'], value=f_name) for f_name, f_data in self.families[:25]]
        if options:
            sel = discord.ui.Select(placeholder="Choisissez une famille...", options=options)
            sel.callback = self.select_family
            self.add_item(sel)

        back = discord.ui.Button(label="Retour", style=discord.ButtonStyle.secondary)
        back.callback = self.go_back
        self.add_item(back)

    def create_embed(self):
        # Utiliser config_manager
        if config_manager:
            try:
                embed = config_manager.get_formatted_embed(
                    self.ctx.guild, self.ctx.author, self.ctx.bot,
                    title="📈 Mettre en vente",
                    description="Choisissez la famille de la carte à vendre.",
                    target_id=self.ctx.guild.id if self.ctx.guild else None
                )
                # Ajouter l'image du bot en thumbnail
                if self.ctx.bot and self.ctx.bot.user.avatar:
                    embed.set_thumbnail(url=self.ctx.bot.user.avatar.url)
            except Exception as e:
                print(f"[DEBUG] Erreur config_manager shop family: {e}")
                embed = discord.Embed(title="📈 Mettre en vente", description="Choisissez la famille de la carte à vendre.", color=0x2b2d31)
                if self.ctx.bot and self.ctx.bot.user.avatar:
                    embed.set_thumbnail(url=self.ctx.bot.user.avatar.url)
                    embed.set_footer(
                        text="Système Kayaba Collection",
                        icon_url=self.ctx.bot.user.avatar.url
                    )
                else:
                    embed.set_footer(text="Système Kayaba Collection")
        else:
            embed = discord.Embed(title="📈 Mettre en vente", description="Choisissez la famille de la carte à vendre.", color=0x2b2d31)
            if self.ctx.bot and self.ctx.bot.user.avatar:
                embed.set_thumbnail(url=self.ctx.bot.user.avatar.url)
                embed.set_footer(
                    text="Système Kayaba Collection",
                    icon_url=self.ctx.bot.user.avatar.url
                )
            else:
                embed.set_footer(text="Système Kayaba Collection")
        return embed

    async def select_family(self, interaction: discord.Interaction):
        f_name = interaction.data['values'][0]
        cards = dict(self.families)[f_name]['personnages']
        view = ShopCardSelectView(self.ctx, self.manager, cards)
        await interaction.response.edit_message(embed=view.create_embed(), view=view)

    async def go_back(self, interaction: discord.Interaction):
        view = ShopMainView(self.ctx, self.manager)
        await interaction.response.edit_message(embed=view.create_embed(), view=view)


class ShopCardSelectView(discord.ui.View):
    def __init__(self, ctx, manager, cards):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.manager = manager
        self.cards = cards
        self._build_view()

    def _build_view(self):
        options = []
        for c in self.cards[:25]:
            options.append(discord.SelectOption(label=c['nom'], value=c['id'], description=f"ID: {c['id']}"))
            
        sel = discord.ui.Select(placeholder="Choisissez la carte...", options=options)
        sel.callback = self.select_card
        self.add_item(sel)

        back = discord.ui.Button(label="Retour", style=discord.ButtonStyle.secondary)
        back.callback = self.go_back
        self.add_item(back)

    def create_embed(self):
        # Utiliser config_manager
        if config_manager:
            try:
                embed = config_manager.get_formatted_embed(
                    self.ctx.guild, self.ctx.author, self.ctx.bot,
                    title="📈 Mettre en vente",
                    description="Choisissez la carte exacte que vous souhaitez lister sur le marché.",
                    target_id=self.ctx.guild.id if self.ctx.guild else None
                )
                # Ajouter l'image du bot en thumbnail
                if self.ctx.bot and self.ctx.bot.user.avatar:
                    embed.set_thumbnail(url=self.ctx.bot.user.avatar.url)
            except Exception as e:
                print(f"[DEBUG] Erreur config_manager shop card: {e}")
                embed = discord.Embed(title="📈 Mettre en vente", description="Choisissez la carte exacte que vous souhaitez lister sur le marché.", color=0x2b2d31)
                if self.ctx.bot and self.ctx.bot.user.avatar:
                    embed.set_thumbnail(url=self.ctx.bot.user.avatar.url)
                    embed.set_footer(
                        text="Système Kayaba Collection",
                        icon_url=self.ctx.bot.user.avatar.url
                    )
                else:
                    embed.set_footer(text="Système Kayaba Collection")
        else:
            embed = discord.Embed(title="📈 Mettre en vente", description="Choisissez la carte exacte que vous souhaitez lister sur le marché.", color=0x2b2d31)
            if self.ctx.bot and self.ctx.bot.user.avatar:
                embed.set_thumbnail(url=self.ctx.bot.user.avatar.url)
                embed.set_footer(
                    text="Système Kayaba Collection",
                    icon_url=self.ctx.bot.user.avatar.url
                )
            else:
                embed.set_footer(text="Système Kayaba Collection")
        return embed

    async def select_card(self, interaction: discord.Interaction):
        card_id = interaction.data['values'][0]
        card = next(c for c in self.cards if c['id'] == card_id)
        
        await interaction.response.send_modal(ListPriceModal(self.ctx, self.manager, card))

    async def go_back(self, interaction: discord.Interaction):
        view = ShopFamilySelectView(self.ctx, self.manager)
        await interaction.response.edit_message(embed=view.create_embed(), view=view)


class ListPriceModal(discord.ui.Modal, title="Prix de vente"):
    price = discord.ui.TextInput(label="Prix (en Col)", placeholder="Ex: 50000", required=True)

    def __init__(self, ctx, manager, card):
        super().__init__()
        self.ctx = ctx
        self.manager = manager
        self.card = card

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.price.value.replace(" ", ""))
            if val <= 0: raise ValueError
        except ValueError:
            await interaction.response.send_message("❌ Prix invalide.", ephemeral=True)
            return

        success = self.manager.list_card(self.ctx.author.id, self.card, val)
        if success:
            await interaction.response.send_message(f"✅ **{self.card['nom']}** est maintenant sur le marché pour **{val:,}** <:col:1482462727468486738> !", ephemeral=True)
            view = ShopMainView(self.ctx, self.manager)
            await interaction.message.edit(embed=view.create_embed(), view=view)
        else:
            await interaction.response.send_message("❌ Erreur lors de la mise en vente (carte manquante ?).", ephemeral=True)


class ShopRemoveView(discord.ui.View):
    def __init__(self, ctx, manager, listings):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.manager = manager
        self.listings = listings
        self._build_view()

    def _build_view(self):
        options = []
        for l in self.listings:
            options.append(discord.SelectOption(label=l['card']['nom'], value=l['listing_id'], description=f"Prix: {l['price']:,} Col"))
            
        sel = discord.ui.Select(placeholder="Choisissez l'offre à annuler...", options=options)
        sel.callback = self.cancel_listing
        self.add_item(sel)

        back = discord.ui.Button(label="Retour", style=discord.ButtonStyle.secondary)
        back.callback = self.go_back
        self.add_item(back)

    def create_embed(self):
        # Utiliser config_manager
        if config_manager:
            try:
                embed = config_manager.get_formatted_embed(
                    self.ctx.guild, self.ctx.author, self.ctx.bot,
                    title="📉 Retirer une vente",
                    description="Sélectionnez l'offre à retirer du marché. La carte retournera dans votre inventaire.",
                    target_id=self.ctx.guild.id if self.ctx.guild else None
                )
                # Ajouter l'image du bot en thumbnail
                if self.ctx.bot and self.ctx.bot.user.avatar:
                    embed.set_thumbnail(url=self.ctx.bot.user.avatar.url)
            except Exception as e:
                print(f"[DEBUG] Erreur config_manager shop remove: {e}")
                embed = discord.Embed(title="📉 Retirer une vente", description="Sélectionnez l'offre à retirer du marché. La carte retournera dans votre inventaire.", color=0x2b2d31)
                if self.ctx.bot and self.ctx.bot.user.avatar:
                    embed.set_thumbnail(url=self.ctx.bot.user.avatar.url)
                    embed.set_footer(
                        text="Système Kayaba Collection",
                        icon_url=self.ctx.bot.user.avatar.url
                    )
                else:
                    embed.set_footer(text="Système Kayaba Collection")
        else:
            embed = discord.Embed(title="📉 Retirer une vente", description="Sélectionnez l'offre à retirer du marché. La carte retournera dans votre inventaire.", color=0x2b2d31)
            if self.ctx.bot and self.ctx.bot.user.avatar:
                embed.set_thumbnail(url=self.ctx.bot.user.avatar.url)
                embed.set_footer(
                    text="Système Kayaba Collection",
                    icon_url=self.ctx.bot.user.avatar.url
                )
            else:
                embed.set_footer(text="Système Kayaba Collection")
        return embed

    async def cancel_listing(self, interaction: discord.Interaction):
        listing_id = interaction.data['values'][0]
        success = self.manager.cancel_listing(self.ctx.author.id, listing_id)
        
        if success:
            await interaction.response.send_message("✅ Offre retirée, la carte a été replacée dans votre inventaire.", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Erreur lors du retrait de l'offre.", ephemeral=True)
            
        view = ShopMainView(self.ctx, self.manager)
        await interaction.message.edit(embed=view.create_embed(), view=view)

    async def go_back(self, interaction: discord.Interaction):
        view = ShopMainView(self.ctx, self.manager)
        await interaction.response.edit_message(embed=view.create_embed(), view=view)


class ShopGlobalView(discord.ui.View):
    def __init__(self, ctx, manager, listings):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.manager = manager
        self.listings = listings
        self.current_page = 1
        self.items_per_page = 10
        self.user_collection = self.manager.get_user_data(self.ctx.author.id).get('collection', {})
        self.filter_missing = False
        self.filter_rarity = None
        self.filter_family = None
        self.filter_card_id = None
        self._build_view()

    def _build_view(self):
        self.clear_items()
        
        # Ajouter les filtres
        # Filtre manquants
        btn_missing = discord.ui.Button(label="Manquants", emoji="❌", style=discord.ButtonStyle.secondary if not self.filter_missing else discord.ButtonStyle.success)
        btn_missing.callback = self.toggle_missing
        self.add_item(btn_missing)
        
        # Filtre rareté
        rarity_options = [
            discord.SelectOption(label="Toutes", value="None"),
            discord.SelectOption(label="Commun 🟢", value="Commun"),
            discord.SelectOption(label="Rare 🔵", value="Rare"),
            discord.SelectOption(label="Epique 🟣", value="Epique"),
            discord.SelectOption(label="Légendaire 🟡", value="Légendaire")
        ]
        sel_rarity = discord.ui.Select(placeholder="Filtrer par rareté...", options=rarity_options, max_values=1)
        sel_rarity.callback = self.filter_by_rarity
        self.add_item(sel_rarity)
        
        # Filtre famille
        families = set()
        for l in self.listings:
            if 'famille' in l['card']:
                families.add(l['card']['famille'])
            elif 'famille_nom' in l['card']:
                families.add(l['card']['famille_nom'])
        
        family_options = [discord.SelectOption(label="Toutes", value="None")]
        for family in sorted(families):
            family_options.append(discord.SelectOption(label=family, value=family))
        
        sel_family = discord.ui.Select(placeholder="Filtrer par famille...", options=family_options, max_values=1)
        sel_family.callback = self.filter_by_family
        self.add_item(sel_family)
        
        # Filtre ID
        btn_id = discord.ui.Button(label="Filtrer par ID", emoji="🔍", style=discord.ButtonStyle.secondary)
        btn_id.callback = self.prompt_id_filter
        self.add_item(btn_id)
        
        # Séparateur
        self.add_item(discord.ui.Button(label="─", style=discord.ButtonStyle.secondary, disabled=True))
        
        # Navigation et sélection
        start_idx = (self.current_page - 1) * self.items_per_page
        page_listings = self.listings[start_idx:start_idx + self.items_per_page]
        
        options = []
        for l in page_listings:
            seller = self.ctx.bot.get_user(l['seller_id'])
            seller_name = seller.display_name if seller else f"Utilisateur #{l['seller_id']}"
            options.append(discord.SelectOption(
                label=f"{l['card']['nom']}",
                value=l['listing_id'],
                description=f"{seller_name} - {l['price']} <:col:1482462727468486738> - #{l['card']['id']}"
            ))
            
        if options:
            sel = discord.ui.Select(placeholder="Sélectionnez une carte à acheter...", options=options)
            sel.callback = self.buy_prompt
            self.add_item(sel)

        if self.current_page > 1:
            btn = discord.ui.Button(label="◀", style=discord.ButtonStyle.secondary)
            btn.callback = self.prev_page
            self.add_item(btn)
            
        if len(self.listings) > self.current_page * self.items_per_page:
            btn = discord.ui.Button(label="▶", style=discord.ButtonStyle.secondary)
            btn.callback = self.next_page
            self.add_item(btn)

        back = discord.ui.Button(label="Retour", emoji="🔙", style=discord.ButtonStyle.danger)
        back.callback = self.go_back
        self.add_item(back)

    def create_embed(self):
        # Appliquer les filtres
        filtered_listings = self.listings.copy()
        
        # Filtre manquants
        if self.filter_missing:
            filtered_listings = [l for l in filtered_listings if self.user_collection.get(l['card']['id'], 0) == 0]
        
        # Filtre rareté
        if self.filter_rarity:
            filtered_listings = [l for l in filtered_listings if l['card'].get('rarete') == self.filter_rarity]
        
        # Filtre famille
        if self.filter_family:
            filtered_listings = [l for l in filtered_listings if 
                                l['card'].get('famille') == self.filter_family or 
                                l['card'].get('famille_nom') == self.filter_family]
        
        # Filtre ID
        if self.filter_card_id:
            filtered_listings = [l for l in filtered_listings if l['card'].get('id') == self.filter_card_id]
        
        start_idx = (self.current_page - 1) * self.items_per_page
        page_listings = filtered_listings[start_idx:start_idx + self.items_per_page]
        
        desc = "**Offres actuelles des joueurs :**\n\n"
        for l in page_listings:
            c = l['card']
            seller = self.ctx.bot.get_user(l['seller_id'])
            seller_name = seller.display_name if seller else f"Utilisateur #{l['seller_id']}"
            owned = self.user_collection.get(c['id'], 0)
            status = f"Possédé : {owned}" if owned > 0 else "Manquant"
            rarity_emoji = {"Légendaire": "🟡", "Epique": "🟣", "Rare": "🔵", "Commun": "🟢"}.get(c.get('rarete', 'Commun'), "🟢")
            
            # Formater le prix avec des espaces
            formatted_price = f"{l['price']:,}".replace(',', ' ')
            
            desc += f"{rarity_emoji} **{c['nom']}** - `#{c['id']}` - **{formatted_price}** <:col:1482462727468486738> - *{seller_name}* - *{status}*\n"

        # Utiliser config_manager
        if config_manager:
            try:
                embed = config_manager.get_formatted_embed(
                    self.ctx.guild, self.ctx.author, self.ctx.bot,
                    title="🛒 Marché Global",
                    description=desc,
                    target_id=self.ctx.guild.id if self.ctx.guild else None
                )
                # Ajouter l'image du bot en thumbnail
                if self.ctx.bot and self.ctx.bot.user.avatar:
                    embed.set_thumbnail(url=self.ctx.bot.user.avatar.url)
                    
                # Footer avec pagination et filtres
                filter_text = ""
                if self.filter_missing:
                    filter_text += "Manquants "
                if self.filter_rarity:
                    filter_text += f"{self.filter_rarity} "
                if self.filter_family:
                    filter_text += f"{self.filter_family} "
                if self.filter_card_id:
                    filter_text += f"ID:{self.filter_card_id} "
                    
                current_footer = embed.footer.text if embed.footer.text else ""
                current_icon = embed.footer.icon_url if embed.footer.icon_url else (self.ctx.bot.user.avatar.url if self.ctx.bot and self.ctx.bot.user.avatar else None)
                
                footer_text = f"Page {self.current_page}/{len(filtered_listings) // self.items_per_page + 1 if len(filtered_listings) > 0 else 1}"
                if filter_text:
                    footer_text += f" • {filter_text.strip()}"
                footer_text += f" • {current_footer}"
                
                embed.set_footer(
                    text=footer_text,
                    icon_url=current_icon
                )
            except Exception as e:
                print(f"[DEBUG] Erreur config_manager shop global: {e}")
                embed = discord.Embed(title="🛒 Marché Global", description=desc, color=0x2b2d31)
                if self.ctx.bot and self.ctx.bot.user.avatar:
                    embed.set_thumbnail(url=self.ctx.bot.user.avatar.url)
                    embed.set_footer(
                        text=f"Page {self.current_page}/{len(filtered_listings) // self.items_per_page + 1 if len(filtered_listings) > 0 else 1} • Système Kayaba Collection",
                        icon_url=self.ctx.bot.user.avatar.url
                    )
                else:
                    embed.set_footer(text=f"Page {self.current_page}/{len(filtered_listings) // self.items_per_page + 1 if len(filtered_listings) > 0 else 1} • Système Kayaba Collection")
        else:
            embed = discord.Embed(title="🛒 Marché Global", description=desc, color=0x2b2d31)
            if self.ctx.bot and self.ctx.bot.user.avatar:
                embed.set_thumbnail(url=self.ctx.bot.user.avatar.url)
                embed.set_footer(
                    text=f"Page {self.current_page}/{len(filtered_listings) // self.items_per_page + 1 if len(filtered_listings) > 0 else 1} • Système Kayaba Collection",
                    icon_url=self.ctx.bot.user.avatar.url
                )
            else:
                embed.set_footer(text=f"Page {self.current_page}/{len(filtered_listings) // self.items_per_page + 1 if len(filtered_listings) > 0 else 1} • Système Kayaba Collection")
        return embed

    async def buy_prompt(self, interaction: discord.Interaction):
        listing_id = interaction.data['values'][0]
        listing = next((l for l in self.listings if l['listing_id'] == listing_id), None)
        
        if listing['seller_id'] == self.ctx.author.id:
            await interaction.response.send_message("❌ Vous ne pouvez pas acheter votre propre carte !", ephemeral=True)
            return

        view = discord.ui.View()
        btn = discord.ui.Button(label="Confirmer l'achat", style=discord.ButtonStyle.success)
        
        async def confirm_callback(inter):
            success, result = self.manager.buy_listing(self.ctx.author.id, listing_id)
            if success:
                await inter.response.send_message(f"✅ Vous avez acheté **{result['card']['nom']}** pour **{result['price']:,}** 💰 !", ephemeral=True)
                
                # Notification au vendeur
                if MPManager:
                    msg = f"🎉 Votre carte **{result['card']['nom']}** a été vendue pour **{result['price']:,}** 💰 !"
                    await MPManager.send_mp_if_enabled(self.ctx.bot, result['seller_id'], msg)
            else:
                await inter.response.send_message(f"❌ {result}", ephemeral=True)
            
            # Retour au menu
            main_view = ShopMainView(self.ctx, self.manager)
            await self.ctx.message.edit(embed=main_view.create_embed(), view=main_view)

        btn.callback = confirm_callback
        view.add_item(btn)
        
        await interaction.response.send_message(f"❓ Confirmez-vous l'achat de **{listing['card']['nom']}** pour **{listing['price']:,}** 💰 ?", view=view, ephemeral=True)

    async def prev_page(self, interaction: discord.Interaction):
        self.current_page -= 1
        self._build_view()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page += 1
        self._build_view()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def go_back(self, interaction: discord.Interaction):
        view = ShopMainView(self.ctx, self.manager)
        await interaction.response.edit_message(embed=view.create_embed(), view=view)

    async def toggle_missing(self, interaction: discord.Interaction):
        self.filter_missing = not self.filter_missing
        self.current_page = 1  # Reset to first page when filter changes
        self._build_view()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def filter_by_rarity(self, interaction: discord.Interaction):
        selected = interaction.data['values'][0]
        self.filter_rarity = None if selected == "None" else selected
        self.current_page = 1  # Reset to first page when filter changes
        self._build_view()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def filter_by_family(self, interaction: discord.Interaction):
        selected = interaction.data['values'][0]
        self.filter_family = None if selected == "None" else selected
        self.current_page = 1  # Reset to first page when filter changes
        self._build_view()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def prompt_id_filter(self, interaction: discord.Interaction):
        # Create a modal for ID input
        modal = discord.ui.Modal(title="Filtrer par ID de carte")
        id_input = discord.ui.TextInput(
            label="ID de la carte",
            placeholder="Ex: ABC123",
            required=True,
            max_length=10
        )
        modal.add_item(id_input)

        async def on_submit(modal_interaction: discord.Interaction):
            card_id = id_input.value.strip().upper()
            self.filter_card_id = card_id if card_id else None
            self.current_page = 1  # Reset to first page when filter changes
            self._build_view()
            await modal_interaction.response.edit_message(embed=self.create_embed(), view=self)

        modal.on_submit = on_submit
        await interaction.response.send_modal(modal)


# ==========================================
# COG PRINCIPAL
# ==========================================
class Shop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.manager = ShopManager()

    @commands.hybrid_command(name="shop", description="Accédez au marché des joueurs")
    async def shop_cmd(self, ctx: commands.Context):
        await ctx.defer()
        
        try:
            view = ShopMainView(ctx, self.manager)
            embed = view.create_embed()
            if config_manager:
                try:
                    embed = config_manager.get_formatted_embed(
                        ctx.guild, ctx.author, ctx.bot,
                        title="🛒 Marché des Joueurs",
                        description=embed.description,
                        target_id=ctx.guild.id if ctx.guild else None
                    )
                except:
                    pass
            await ctx.send(embed=embed, view=view)
        except Exception as e:
            print(f"[SHOP] ERREUR: {e}")
            await ctx.send("❌ Une erreur est survenue lors de l'ouverture du shop.")


async def setup(bot):
    await bot.add_cog(Shop(bot))