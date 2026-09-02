import discord
from discord.ext import commands
import json
import os
import sys
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime

# ==========================================
# CONFIGURATION & CHEMINS
# ==========================================
BASE_DIR = os.path.dirname(__file__)
DATA_DEV_DIR = os.path.normpath(os.path.join(BASE_DIR, '..', 'data', 'dev'))
FAMILLE_DIR = os.path.join(DATA_DEV_DIR, 'famille')

# Importer depuis collect.py pour les paths
try:
    from .collect import COLLECTION_DB_PATH, USER_DATA_PATH
except ImportError as e:
    print(f"\033[91m[SELL] Erreur import collect.py: {e}\033[0m")
    COLLECTION_DB_PATH = None
    USER_DATA_PATH = None

# Fallback pour USER_DATA_PATH
if USER_DATA_PATH is None:
    try:
        current_dir = os.path.dirname(__file__)
        user_data_path = os.path.normpath(os.path.join(current_dir, '..', 'data', 'interserver'))
        if os.path.exists(user_data_path):
            USER_DATA_PATH = user_data_path
            print(f"[SELL] USER_DATA_PATH fallback trouvé: {USER_DATA_PATH}")
        else:
            print(f"[SELL] USER_DATA_PATH fallback non trouvé")
    except Exception as e:
        print(f"\033[91m[SELL] Erreur fallback USER_DATA_PATH: {e}\033[0m")
        USER_DATA_PATH = None

# ==============================================================================
# --------------------------- IMPORTATION UTILS --------------------------------
# ==============================================================================
try:
    from cogs.developpeur.commands.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# Importation Emojis
EMOJI_FILE = os.path.join(BASE_DIR, '..', 'emoji.json')
EMOJIS = {}
if os.path.exists(EMOJI_FILE):
    try:
        with open(EMOJI_FILE, 'r', encoding='utf-8') as f:
            EMOJIS = json.load(f)
    except:
        pass

# Importer MPManager pour les notifications
try:
    from cogs.collection.commands.mp import MPManager
except ImportError:
    MPManager = None

# ==========================================
# MANAGER DE VENTE
# ==========================================
class SellManager:
    def __init__(self):
        self.famille_dir = FAMILLE_DIR
    
    def update_exemplaires_restant(self, famille_name: str, personnage_id: str, increment: int):
        """Augmente exemplaires_restant dans personnages.json lors de la vente"""
        personnages_file = os.path.join(FAMILLE_DIR, famille_name, 'personnages.json')
        if not os.path.exists(personnages_file):
            return False
        
        try:
            with open(personnages_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Trouver le personnage et mettre à jour
            for personnage in data.get('personnages', []):
                if personnage.get('id') == personnage_id:
                    current_restant = personnage.get('exemplaires_restant', 0)
                    personnage['exemplaires_restant'] = current_restant + increment
                    print(f"[SELL] exemplaires_restant mis à jour pour {personnage_id}: {current_restant} -> {personnage['exemplaires_restant']}")
                    break
            
            # Sauvegarder
            with open(personnages_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            
            return True
        except Exception as e:
            print(f"\033[91m[SELL] Erreur mise à jour exemplaires_restant: {e}\033[0m")
            return False
    
    def get_user_collection(self, user_id: int):
        """Récupère la collection de l'utilisateur"""
        if not USER_DATA_PATH:
            print(f"[SELL] USER_DATA_PATH est None")
            return {}
        
        user_file = USER_DATA_PATH / f"{user_id}.json"
        print(f"[SELL] Recherche du fichier: {user_file}")
        
        if not user_file.exists():
            print(f"[SELL] Fichier non trouvé pour l'utilisateur {user_id}")
            return {}
        
        try:
            with open(user_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                collection = data.get('collection', {})
                print(f"[SELL] Collection chargée pour {user_id}: {len(collection)} cartes")
                return collection
        except Exception as e:
            print(f"\033[91m[SELL] Erreur lecture fichier utilisateur: {e}\033[0m")
            return {}
    
    def get_user_families(self, user_id: int):
        """Récupère les familles que l'utilisateur possède (au moins 1 carte)"""
        collection = self.get_user_collection(user_id)
        user_families = {}
        
        if not os.path.exists(FAMILLE_DIR):
            return user_families
        
        # Parcourir toutes les familles pour trouver celles que l'utilisateur possède
        for famille_name in os.listdir(FAMILLE_DIR):
            famille_path = os.path.join(FAMILLE_DIR, famille_name)
            if not os.path.isdir(famille_path):
                continue
            
            personnages_file = os.path.join(famille_path, 'personnages.json')
            if not os.path.exists(personnages_file):
                continue
            
            try:
                with open(personnages_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    personnages = data.get('personnages', [])
                    
                    # Vérifier si l'utilisateur possède au moins une carte de cette famille
                    user_cards_in_family = []
                    for personnage in personnages:
                        card_id = personnage.get('id')
                        if card_id in collection and collection[card_id] > 0:
                            user_cards_in_family.append(personnage)
                    
                    if user_cards_in_family:
                        # Récupérer le nom d'affichage de la famille
                        config_file = os.path.join(famille_path, 'config.json')
                        display_name = famille_name
                        if os.path.exists(config_file):
                            with open(config_file, 'r', encoding='utf-8') as f2:
                                config_data = json.load(f2)
                                display_name = config_data.get('nom', famille_name)
                        
                        user_families[famille_name] = {
                            'display_name': display_name,
                            'personnages': user_cards_in_family
                        }
            except Exception as e:
                print(f"\033[91m[SELL] Erreur lecture famille {famille_name}: {e}\033[0m")
                continue
        
        print(f"[SELL] Familles possédées par {user_id}: {list(user_families.keys())}")
        return user_families
    
    def get_user_cards_in_family(self, user_id: int, famille_name: str):
        """Récupère les cartes de l'utilisateur dans une famille spécifique"""
        collection = self.get_user_collection(user_id)
        user_cards = []
        
        personnages_file = os.path.join(FAMILLE_DIR, famille_name, 'personnages.json')
        if not os.path.exists(personnages_file):
            return user_cards
        
        try:
            with open(personnages_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                personnages = data.get('personnages', [])
                
                for personnage in personnages:
                    card_id = personnage.get('id')
                    if card_id in collection and collection[card_id] > 0:
                        user_cards.append({
                            **personnage,
                            'quantity': collection[card_id]
                        })
        except Exception as e:
            print(f"\033[91m[SELL] Erreur lecture cartes famille {famille_name}: {e}\033[0m")
        
        # Trier par quantité (plus grand en premier)
        user_cards.sort(key=lambda x: x['quantity'], reverse=True)
        return user_cards
    
    def format_number(self, number: int) -> str:
        """Formate un nombre avec des espaces au lieu de virgules"""
        return f"{number:,}".replace(",", " ")
    
    def get_plural_form(self, word: str, quantity: int):
        """Retourne la forme singulier/pluriel correcte d'un mot"""
        if quantity == 1:
            return word
        # Cas particuliers pour le français
        if word == "carte":
            return "cartes"
        elif word == "exemplaire":
            return "exemplaires"
        elif word.endswith("al"):
            return word[:-2] + "aux"  # exemple: "cardinal" -> "cardinaux"
        elif word.endswith("ail"):
            return word[:-3] + "ails"  # exemple: "travail" -> "travaux"
        else:
            return word + "s"
    
    def add_col_to_user(self, user_id: int, amount: int):
        """Ajoute des Col au solde de l'utilisateur"""
        if not USER_DATA_PATH:
            print(f"[SELL] USER_DATA_PATH est None")
            return False
        
        user_file = USER_DATA_PATH / f"{user_id}.json"
        if not user_file.exists():
            print(f"[SELL] Fichier non trouvé pour l'utilisateur {user_id}")
            return False
        
        try:
            with open(user_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Ajouter les Col
            current_col = data.get('col', 0)
            data['col'] = current_col + amount
            
            # Sauvegarder
            with open(user_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            
            print(f"[SELL] {amount:,} Col ajoutés à l'utilisateur {user_id} (solde: {current_col:,} -> {data['col']:,})")
            return True
        except Exception as e:
            print(f"\033[91m[SELL] Erreur ajout Col: {e}\033[0m")
            return False
    
    def remove_cards_from_collection(self, user_id: int, card_id: str, quantity: int):
        """Retire des cartes de la collection de l'utilisateur"""
        if not USER_DATA_PATH:
            return False
        
        user_file = USER_DATA_PATH / f"{user_id}.json"
        if not user_file.exists():
            return False
        
        try:
            with open(user_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            collection = data.get('collection', {})
            current_quantity = collection.get(card_id, 0)
            
            if current_quantity < quantity:
                return False
            
            # Retirer les cartes
            new_quantity = current_quantity - quantity
            if new_quantity <= 0:
                del collection[card_id]
            else:
                collection[card_id] = new_quantity
            
            data['collection'] = collection
            
            # Sauvegarder
            with open(user_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            
            print(f"[SELL] {quantity} cartes {card_id} retirées de la collection de {user_id}")
            return True
        except Exception as e:
            print(f"\033[91m[SELL] Erreur retrait cartes: {e}\033[0m")
            return False

# ==========================================
# VUES INTERACTIVES
# ==========================================
class FamilySellView(discord.ui.View):
    def __init__(self, ctx, sell_manager: SellManager):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.sell_manager = sell_manager
        self.current_page = 1
        self.items_per_page = 25
        self.families = []
        self._build_view()
    
    def _build_view(self):
        self.clear_items()
        
        # Récupérer les familles de l'utilisateur
        self.families = list(self.sell_manager.get_user_families(self.ctx.author.id).items())
        
        # Pagination
        start_idx = (self.current_page - 1) * self.items_per_page
        end_idx = start_idx + self.items_per_page
        page_families = self.families[start_idx:end_idx]
        
        # Sélecteur de familles
        family_options = []
        for famille_name, family_data in page_families:
            family_options.append(discord.SelectOption(
                label=family_data['display_name'],
                value=famille_name,
                description=f"{len(family_data['personnages'])} cartes possédées"
            ))
        
        if family_options:
            family_select = discord.ui.Select(
                placeholder="Choisissez une famille à vendre...",
                options=family_options,
                row=0
            )
            family_select.callback = self.select_family
            self.add_item(family_select)
        
        # Boutons de pagination
        if self.current_page > 1:
            prev_btn = discord.ui.Button(label="◀", style=discord.ButtonStyle.secondary, row=1)
            prev_btn.callback = self.previous_page
            self.add_item(prev_btn)
        
        if len(self.families) > self.current_page * self.items_per_page:
            next_btn = discord.ui.Button(label="▶", style=discord.ButtonStyle.secondary, row=1)
            next_btn.callback = self.next_page
            self.add_item(next_btn)
    
    def create_embed(self):
        # Calculer la valeur totale de toute la collection de l'utilisateur
        total_collection_value = 0
        user_collection = self.sell_manager.get_user_collection(self.ctx.author.id)
        
        print(f"[SELL DEBUG] USER_DATA_PATH: {USER_DATA_PATH}")
        print(f"[SELL DEBUG] FAMILLE_DIR: {FAMILLE_DIR}")
        print(f"[SELL DEBUG] Collection utilisateur: {user_collection}")
        
        if user_collection:
            # Parcourir toutes les familles pour calculer la valeur totale
            import os
            if os.path.exists(FAMILLE_DIR):
                print(f"[SELL DEBUG] FAMILLE_DIR existe, contenu: {os.listdir(FAMILLE_DIR)}")
                for family_name in os.listdir(FAMILLE_DIR):
                    family_path = os.path.join(FAMILLE_DIR, family_name)
                    print(f"[SELL DEBUG] Vérification famille: {family_name} -> {family_path}")
                    if os.path.isdir(family_path):
                        personnages_file = os.path.join(family_path, 'personnages.json')
                        print(f"[SELL DEBUG] Fichier personnages: {personnages_file}")
                        if os.path.exists(personnages_file):
                            try:
                                with open(personnages_file, 'r', encoding='utf-8') as f:
                                    personnages = json.load(f)
                                
                                print(f"[SELL DEBUG] Famille {family_name}: {len(personnages)} personnages")
                                for personnage in personnages:
                                    card_id = personnage.get('id')
                                    if card_id in user_collection and user_collection[card_id] > 0:
                                        value = personnage.get('valeur', 0)
                                        quantity = user_collection[card_id]
                                        total_collection_value += value * quantity
                                        print(f"[SELL DEBUG] Carte {card_id}: {value} x {quantity} = {value * quantity}")
                            except Exception as e:
                                print(f"\033[91m[SELL DEBUG] Erreur lecture famille {family_name}: {e}\033[0m")
                                continue
                        else:
                            print(f"[SELL DEBUG] Fichier personnages n'existe pas: {personnages_file}")
                    else:
                        print(f"[SELL DEBUG] {family_path} n'est pas un dossier")
            else:
                print(f"[SELL DEBUG] FAMILLE_DIR n'existe pas: {FAMILLE_DIR}")
        else:
            print(f"[SELL DEBUG] Collection utilisateur vide ou None")
        
        print(f"[SELL DEBUG] Valeur totale calculée: {total_collection_value}")
        
        # Utiliser config_manager si disponible
        if config_manager:
            try:
                embed = config_manager.get_formatted_embed(
                    self.ctx.guild, self.ctx.author, self.ctx.bot,
                    title=f"{EMOJIS.get('col', '💰')} Vente de Cartes - {self.ctx.author.display_name}",
                    description="Choisissez une famille pour voir les cartes que vous pouvez vendre.",
                    target_id=self.ctx.guild.id if self.ctx.guild else None
                )
                
                if self.families:
                    families_text = ""
                    for family_name, family_data in self.families:
                        card_count = len(family_data['personnages'])
                        carte_word = "carte" if card_count == 1 else "cartes"
                        families_text += f"📁 **{family_data['display_name']}** ({card_count} {carte_word})\n"
                    
                    embed.add_field(
                        name="📊 Vos familles disponibles",
                        value=families_text,
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="❌ Aucune carte disponible",
                        value="Vous ne possédez aucune carte à vendre.",
                        inline=False
                    )
                
                # Ajouter l'image du bot en thumbnail
                if self.ctx.bot and self.ctx.bot.user.avatar:
                    embed.set_thumbnail(url=self.ctx.bot.user.avatar.url)
                    
            except Exception as e:
                print(f"\033[91m[SELL] Erreur config_manager: {e}\033[0m")
                embed = discord.Embed(
                    title=f"{EMOJIS.get('col', '💰')} Vente de Cartes - {self.ctx.author.display_name}",
                    description="Choisissez une famille pour voir les cartes que vous pouvez vendre.",
                    color=discord.Color.gold()
                )
                
                if self.families:
                    families_text = ""
                    for family_name, family_data in self.families:
                        card_count = len(family_data['personnages'])
                        carte_word = "carte" if card_count == 1 else "cartes"
                        families_text += f"📁 **{family_data['display_name']}** ({card_count} {carte_word})\n"
                    
                    embed.add_field(
                        name="📊 Vos familles disponibles",
                        value=families_text,
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="❌ Aucune carte disponible",
                        value="Vous ne possédez aucune carte à vendre.",
                        inline=False
                    )
                
                # Ajouter l'image du bot en thumbnail et footer
                if self.ctx.bot and self.ctx.bot.user.avatar:
                    embed.set_thumbnail(url=self.ctx.bot.user.avatar.url)
                    embed.set_footer(
                        text="Système Kayaba Collection",
                        icon_url=self.ctx.bot.user.avatar.url
                    )
                else:
                    embed.set_footer(text="Système Kayaba Collection")
                
                embed.add_field(
                    name="Valeur totale de votre collection",
                    value=f"**{self.sell_manager.format_number(total_collection_value)}** {EMOJIS.get('col', '💰')}",
                    inline=False
                )
        else:
            embed = discord.Embed(
                title=f"{EMOJIS.get('col', '💰')} Vente de Cartes - {self.ctx.author.display_name}",
                description="Choisissez une famille pour voir les cartes que vous pouvez vendre.",
                color=discord.Color.gold()
            )
            
            if self.families:
                families_text = ""
                for family_name, family_data in self.families:
                    card_count = len(family_data['personnages'])
                    carte_word = "carte" if card_count == 1 else "cartes"
                    families_text += f"📁 **{family_data['display_name']}** ({card_count} {carte_word})\n"
                
                embed.add_field(
                    name="📊 Vos familles disponibles",
                    value=families_text,
                    inline=False
                )
                
                embed.add_field(
                    name="Valeur totale de votre collection",
                    value=f"**{self.sell_manager.format_number(total_collection_value)}** {EMOJIS.get('col', '💰')}",
                    inline=False
                )
            else:
                embed.add_field(
                    name="❌ Aucune carte disponible",
                    value="Vous ne possédez aucune carte à vendre.",
                    inline=False
                )
            
            # Ajouter l'image du bot en thumbnail et footer
            if self.ctx.bot and self.ctx.bot.user.avatar:
                embed.set_thumbnail(url=self.ctx.bot.user.avatar.url)
                embed.set_footer(
                    text="Système Kayaba Collection",
                    icon_url=self.ctx.bot.user.avatar.url
                )
            else:
                embed.set_footer(text="Système Kayaba Collection")
        
        # Footer
        footer_text = "Sélectionnez une famille"
        if config_manager:
            try:
                footer_text += f" • {config_manager.get_embed_footer(self.ctx.author)}"
                embed.set_footer(text=footer_text)
            except:
                embed.set_footer(text=footer_text)
        else:
            embed.set_footer(text=footer_text + " • Système Kayaba Collection")
        
        return embed
    
    async def previous_page(self, interaction: discord.Interaction):
        self.current_page -= 1
        self._build_view()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)
    
    async def next_page(self, interaction: discord.Interaction):
        self.current_page += 1
        self._build_view()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)
    
    async def select_family(self, interaction: discord.Interaction):
        family_name = interaction.data['values'][0]
        cards = self.sell_manager.get_user_cards_in_family(self.ctx.author.id, family_name)
        
        if not cards:
            await interaction.response.send_message("❌ Aucune carte trouvée dans cette famille.", ephemeral=True)
            return
        
        # Passer à la vue des cartes
        card_view = CardSellView(self.ctx, self.sell_manager, family_name, cards)
        await interaction.response.edit_message(embed=card_view.create_embed(), view=card_view)

class CardSellView(discord.ui.View):
    def __init__(self, ctx, sell_manager: SellManager, family_name: str, cards: List[dict]):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.sell_manager = sell_manager
        self.family_name = family_name
        self.cards = cards
        self.current_page = 1
        self.items_per_page = 25
        self._build_view()
    
    def _build_view(self):
        self.clear_items()
        
        # Pagination
        start_idx = (self.current_page - 1) * self.items_per_page
        end_idx = start_idx + self.items_per_page
        page_cards = self.cards[start_idx:end_idx]
        
        # Sélecteur de cartes
        card_options = []
        for card in page_cards:
            quantity = card['quantity']
            value = card.get('valeur', 0)
            card_options.append(discord.SelectOption(
                label=f"{card['nom']} ({quantity}x)",
                value=card['id'],
                description=f"ID: {card['id']} • Valeur: {self.sell_manager.format_number(value)} • Total: {self.sell_manager.format_number(value * quantity)}"
            ))
        
        if card_options:
            card_select = discord.ui.Select(
                placeholder="Choisissez une carte à vendre...",
                options=card_options,
                row=0
            )
            card_select.callback = self.select_card
            self.add_item(card_select)
        
        # Boutons de navigation
        if self.current_page > 1:
            prev_btn = discord.ui.Button(label="◀", style=discord.ButtonStyle.secondary, row=1)
            prev_btn.callback = self.previous_page
            self.add_item(prev_btn)
        
        if len(self.cards) > self.current_page * self.items_per_page:
            next_btn = discord.ui.Button(label="▶", style=discord.ButtonStyle.secondary, row=1)
            next_btn.callback = self.next_page
            self.add_item(next_btn)
        
        # Bouton retour
        back_btn = discord.ui.Button(label="🔙 Retour aux familles", style=discord.ButtonStyle.red, row=2)
        back_btn.callback = self.back_to_families
        self.add_item(back_btn)
    
    def create_embed(self):
        # Récupérer le nom d'affichage de la famille
        config_file = os.path.join(FAMILLE_DIR, self.family_name, 'config.json')
        family_display_name = self.family_name
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                    family_display_name = config_data.get('nom', self.family_name)
            except:
                pass
        
        # Utiliser config_manager si disponible
        if config_manager:
            try:
                embed = config_manager.get_formatted_embed(
                    self.ctx.guild, self.ctx.author, self.ctx.bot,
                    title=f"{EMOJIS.get('col', '💰')} Vente - {family_display_name}",
                    description="Choisissez une carte à vendre.",
                    target_id=self.ctx.guild.id if self.ctx.guild else None
                )
                
                # Calculer la valeur totale de toutes les cartes
                total_value = sum(card.get('valeur', 0) * card['quantity'] for card in self.cards)
                
                embed.add_field(
                    name="📊 Statistiques de la famille",
                    value=f"**{len(self.cards)}** cartes différentes\n**{sum(card['quantity'] for card in self.cards)}** cartes au total\n**{self.sell_manager.format_number(total_value)}** {EMOJIS.get('col', '💰')} de valeur totale",
                    inline=False
                )
                
                # Ajouter l'image du bot en thumbnail
                if self.ctx.bot and self.ctx.bot.user.avatar:
                    embed.set_thumbnail(url=self.ctx.bot.user.avatar.url)
                    
            except Exception as e:
                print(f"\033[91m[SELL] Erreur config_manager: {e}\033[0m")
                embed = discord.Embed(
                    title=f"{EMOJIS.get('col', '💰')} Vente - {family_display_name}",
                    description="Choisissez une carte à vendre.",
                    color=discord.Color.gold()
                )
                
                # Calculer la valeur totale de toutes les cartes
                total_value = sum(card.get('valeur', 0) * card['quantity'] for card in self.cards)
                
                embed.add_field(
                    name="📊 Statistiques de la famille",
                    value=f"**{len(self.cards)}** cartes différentes\n**{sum(card['quantity'] for card in self.cards)}** cartes au total\n**{self.sell_manager.format_number(total_value)}** {EMOJIS.get('col', '💰')} de valeur totale",
                    inline=False
                )
                
                # Ajouter l'image du bot en thumbnail et footer
                if self.ctx.bot and self.ctx.bot.user.avatar:
                    embed.set_thumbnail(url=self.ctx.bot.user.avatar.url)
                    embed.set_footer(
                        text="Système Kayaba Collection",
                        icon_url=self.ctx.bot.user.avatar.url
                    )
                else:
                    embed.set_footer(text="Système Kayaba Collection")
        else:
            embed = discord.Embed(
                title=f"{EMOJIS.get('col', '💰')} Vente - {family_display_name}",
                description="Choisissez une carte à vendre.",
                color=discord.Color.gold()
            )
            
            # Calculer la valeur totale de toutes les cartes
            total_value = sum(card.get('valeur', 0) * card['quantity'] for card in self.cards)
            
            embed.add_field(
                name="📊 Statistiques de la famille",
                value=f"**{len(self.cards)}** cartes différentes\n**{sum(card['quantity'] for card in self.cards)}** cartes au total\n**{self.sell_manager.format_number(total_value)}** {EMOJIS.get('col', '💰')} de valeur totale",
                inline=False
            )
            
            # Ajouter l'image du bot en thumbnail et footer
            if self.ctx.bot and self.ctx.bot.user.avatar:
                embed.set_thumbnail(url=self.ctx.bot.user.avatar.url)
                embed.set_footer(
                    text="Système Kayaba Collection",
                    icon_url=self.ctx.bot.user.avatar.url
                )
            else:
                embed.set_footer(text="Système Kayaba Collection")
        
        # Afficher les cartes de la page actuelle
        start_idx = (self.current_page - 1) * self.items_per_page
        end_idx = start_idx + self.items_per_page
        page_cards = self.cards[start_idx:end_idx]
        
        if page_cards:
            cards_text = ""
            for i, card in enumerate(page_cards, start=start_idx + 1):
                rarity_emoji = {"Légendaire": "🟡", "Epique": "🟣", "Rare": "🔵", "Commun": "🟢"}.get(card.get('rarete', 'Commun'), "🟢")
                quantity = card['quantity']
                value = card.get('valeur', 0)
                cards_text += f"**x{quantity}** • {rarity_emoji} **{card['nom']}** • `{card['id']}` • **{self.sell_manager.format_number(value)}** {EMOJIS.get('col', '💰')}\n"
            
            embed.add_field(
                name=f"{EMOJIS.get('cartes', '🎴')} Cartes (Page {self.current_page})",
                value=cards_text,
                inline=False
            )
        
        # Footer avec pagination
        footer_text = f"Page {self.current_page}"
        if config_manager:
            try:
                footer_text += f" • {config_manager.get_embed_footer(self.ctx.author)}"
                embed.set_footer(text=footer_text)
            except:
                embed.set_footer(text=footer_text)
        else:
            embed.set_footer(text=footer_text + " • Système Kayaba Collection")
        
        return embed
    
    async def previous_page(self, interaction: discord.Interaction):
        self.current_page -= 1
        self._build_view()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)
    
    async def next_page(self, interaction: discord.Interaction):
        self.current_page += 1
        self._build_view()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)
    
    async def back_to_families(self, interaction: discord.Interaction):
        family_view = FamilySellView(self.ctx, self.sell_manager)
        await interaction.response.edit_message(embed=family_view.create_embed(), view=family_view)
    
    async def select_card(self, interaction: discord.Interaction):
        card_id = interaction.data['values'][0]
        
        # Trouver la carte sélectionnée
        selected_card = None
        for card in self.cards:
            if card['id'] == card_id:
                selected_card = card
                break
        
        if not selected_card:
            await interaction.response.send_message("❌ Carte non trouvée.", ephemeral=True)
            return
        
        # Créer la vue de confirmation
        confirm_view = SellConfirmView(self.ctx, self.sell_manager, self.family_name, selected_card)
        embed, image_file = confirm_view.create_embed()
        
        # Envoyer avec le fichier image si disponible
        if image_file:
            # D'abord répondre à l'interaction pour éviter le timeout
            await interaction.response.edit_message(
                content="📋 **Chargement de la confirmation...**", 
                view=None
            )
            # Envoyer le nouveau message avec l'image
            await interaction.followup.send(embed=embed, view=confirm_view, file=image_file)
        else:
            await interaction.response.edit_message(embed=embed, view=confirm_view)

class SellConfirmView(discord.ui.View):
    def __init__(self, ctx, sell_manager: SellManager, family_name: str, card: dict):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.sell_manager = sell_manager
        self.family_name = family_name
        self.card = card
        self.quantity = 1
        self._build_view()
    
    def get_character_image(self):
        """Récupère l'image du personnage depuis le dossier du personnage"""
        try:
            # Construire le chemin vers le dossier du personnage
            character_name = self.card.get('nom', '').lower().replace(' ', '_')
            character_dir = os.path.join(FAMILLE_DIR, self.family_name, character_name)
            
            print(f"[SELL] Recherche image dans: {character_dir}")
            
            if not os.path.exists(character_dir):
                print(f"[SELL] Dossier personnage non trouvé: {character_dir}")
                return None
            
            # Chercher config.json pour obtenir le nom de l'image
            config_file = os.path.join(character_dir, 'config.json')
            if os.path.exists(config_file):
                try:
                    with open(config_file, 'r', encoding='utf-8') as f:
                        config_data = json.load(f)
                        image_name = config_data.get('image', '')
                        
                        if image_name:
                            image_path = os.path.join(character_dir, image_name)
                            if os.path.exists(image_path):
                                print(f"[SELL] Image trouvée via config.json: {image_path}")
                                # Vérifier la taille du fichier (limite 8MB pour Discord)
                                file_size = os.path.getsize(image_path)
                                if file_size > 8 * 1024 * 1024:  # 8MB
                                    print(f"[SELL] Image trop volumineuse: {file_size} bytes")
                                    return None
                                
                                # Créer un fichier Discord avec un nom unique
                                file_key = f"character_{self.card['id']}_{os.path.basename(image_path)}"
                                discord_file = discord.File(image_path, filename=file_key)
                                attachment_url = f"attachment://{file_key}"
                                return discord_file, attachment_url
                except json.JSONDecodeError as e:
                    print(f"\033[91m[SELL] Erreur JSON config.json: {e}\033[0m")
                except Exception as e:
                    print(f"\033[91m[SELL] Erreur lecture config.json: {e}\033[0m")
            
            # Chercher automatiquement les images courantes
            image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.webp']
            for ext in image_extensions:
                image_path = os.path.join(character_dir, f"{character_name}{ext}")
                if os.path.exists(image_path):
                    print(f"[SELL] Image auto-trouvée: {image_path}")
                    
                    # Vérifier la taille du fichier (limite 8MB pour Discord)
                    file_size = os.path.getsize(image_path)
                    if file_size > 8 * 1024 * 1024:  # 8MB
                        print(f"[SELL] Image trop volumineuse: {file_size} bytes")
                        continue
                    
                    try:
                        # Créer un fichier Discord avec un nom unique
                        file_key = f"character_{self.card['id']}{ext}"
                        discord_file = discord.File(image_path, filename=file_key)
                        attachment_url = f"attachment://{file_key}"
                        return discord_file, attachment_url
                    except Exception as e:
                        print(f"\033[91m[SELL] Erreur création fichier Discord: {e}\033[0m")
                        continue
            
            print(f"[SELL] Aucune image trouvée pour {character_name}")
            return None
            
        except Exception as e:
            print(f"\033[91m[SELL] Erreur générale récupération image: {e}\033[0m")
            return None
    
    def _build_view(self):
        self.clear_items()
        
        if self.card['quantity'] == 1:
            # Une seule carte : bouton simple
            sell_btn = discord.ui.Button(label="Vendre la carte", style=discord.ButtonStyle.success, row=0)
            sell_btn.callback = self.sell_single
            self.add_item(sell_btn)
        else:
            # Plusieurs cartes : options multiples
            sell_one_btn = discord.ui.Button(label="Vendre 1 carte", style=discord.ButtonStyle.success, row=0)
            sell_one_btn.callback = self.sell_single
            self.add_item(sell_one_btn)
            
            sell_multiple_btn = discord.ui.Button(label="Vendre plusieurs cartes", style=discord.ButtonStyle.primary, row=0)
            sell_multiple_btn.callback = self.sell_multiple
            self.add_item(sell_multiple_btn)
        
        # Bouton annulation
        cancel_btn = discord.ui.Button(label="❌ Annuler", style=discord.ButtonStyle.red, row=1)
        cancel_btn.callback = self.cancel
        self.add_item(cancel_btn)
    
    def create_embed(self):
        rarity_emoji = {"Légendaire": "🟡", "Epique": "🟣", "Rare": "🔵", "Commun": "🟢"}.get(self.card.get('rarete', 'Commun'), "🟢")
        value = self.card.get('valeur', 0)
        
        # Récupérer l'image du personnage
        image_data = self.get_character_image()
        image_file = None
        image_url = None
        
        if image_data:
            image_file, image_url = image_data
            print(f"[SELL] Image utilisée: {image_url}")
        
        # Vérifier si c'est l'unique carte de l'utilisateur
        is_unique_card = self.card['quantity'] == 1
        
        # Utiliser config_manager si disponible
        if config_manager:
            try:
                embed = config_manager.get_formatted_embed(
                    self.ctx.guild, self.ctx.author, self.ctx.bot,
                    title=f"{EMOJIS.get('col', '💰')} Confirmation de Vente",
                    description=rarity_emoji + f" **{self.card['nom']}**",
                    target_id=self.ctx.guild.id if self.ctx.guild else None
                )
                
                # Ajouter l'image du bot en thumbnail
                if self.ctx.bot and self.ctx.bot.user.avatar:
                    embed.set_thumbnail(url=self.ctx.bot.user.avatar.url)
                    
                    embed.add_field(
                        name="Vente proposée",
                        value=f"**Quantité:** {self.quantity}\n**Valeur totale:** {self.sell_manager.format_number(total_value)} {EMOJIS.get('col', '💰')}",
                        inline=False
                    )
                
                # Message d'alerte si c'est l'unique carte
                if is_unique_card:
                    embed.add_field(
                        name="⚠️ ALERTE - CARTE UNIQUE",
                        value="**Ceci est votre seul exemplaire de cette carte !**\nUne fois vendue, vous ne la posséderez plus du tout.",
                        inline=False
                    )
                
                embed.add_field(
                    name="🚫 Attention",
                    value="Cette action est **irréversible**. Les cartes vendues seront retirées de votre collection et remises en circulation.",
                    inline=False
                )
                
            except Exception as e:
                print(f"\033[91m[SELL] Erreur config_manager: {e}\033[0m")
                embed = discord.Embed(
                    title=f"{EMOJIS.get('col', '💰')} Confirmation de Vente",
                    description=rarity_emoji + f" **{self.card['nom']}**",
                    color=discord.Color.gold()
                )
                
                # Ajouter l'image en thumbnail si disponible
                if image_url:
                    embed.set_thumbnail(url=image_url)
                
                embed.add_field(
                    name="📋 Détails de la carte",
                    value=f"**ID:** `{self.card['id']}`\n**Rareté:** {self.card.get('rarete', 'Commun')}\n**Valeur unitaire:** {self.sell_manager.format_number(value)} {EMOJIS.get('col', '💰')}\n**En votre possession:** {self.card['quantity']} exemplaire(s)",
                    inline=False
                )
                
                if self.quantity > 1:
                    total_value = value * self.quantity
                    embed.add_field(
                        name="Vente proposée",
                        value=f"**Quantité:** {self.quantity}\n**Valeur totale:** {self.sell_manager.format_number(total_value)} {EMOJIS.get('col', '💰')}",
                        inline=False
                    )
                
                # Message d'alerte si c'est l'unique carte
                if is_unique_card:
                    embed.add_field(
                        name="⚠️ ALERTE - CARTE UNIQUE",
                        value="**Ceci est votre seul exemplaire de cette carte !**\nUne fois vendue, vous ne la posséderez plus du tout.",
                        inline=False
                    )
                
                embed.add_field(
                    name="🚫 Attention",
                    value="Cette action est **irréversible**. Les cartes vendues seront retirées de votre collection et remises en circulation.",
                    inline=False
                )
        else:
            embed = discord.Embed(
                title=f"{EMOJIS.get('col', '💰')} Confirmation de Vente",
                description=rarity_emoji + f" **{self.card['nom']}**",
                color=discord.Color.gold()
            )
            
            # Ajouter l'image en thumbnail si disponible
            if image_url:
                embed.set_thumbnail(url=image_url)
            
            embed.add_field(
                name="📋 Détails de la carte",
                value=f"**ID:** `{self.card['id']}`\n**Rareté:** {self.card.get('rarete', 'Commun')}\n**Valeur unitaire:** {self.sell_manager.format_number(value)} {EMOJIS.get('col', '💰')}\n**En votre possession:** {self.card['quantity']} exemplaire(s)",
                inline=False
            )
            
            if self.quantity > 1:
                total_value = value * self.quantity
                embed.add_field(
                    name="Vente proposée",
                    value=f"**Quantité:** {self.quantity}\n**Valeur totale:** {self.sell_manager.format_number(total_value)} {EMOJIS.get('col', '💰')}",
                    inline=False
                )
            
            # Message d'alerte si c'est l'unique carte
            if is_unique_card:
                embed.add_field(
                    name="⚠️ ALERTE - CARTE UNIQUE",
                    value="**Ceci est votre seul exemplaire de cette carte !**\nUne fois vendue, vous ne la posséderez plus du tout.",
                    inline=False
                )
            
            embed.add_field(
                name="🚫 Attention",
                value="Cette action est **irréversible**. Les cartes vendues seront retirées de votre collection et remises en circulation.",
                inline=False
            )
        
        # Footer
        footer_text = "Confirmez la vente"
        if config_manager:
            try:
                footer_text += f" • {config_manager.get_embed_footer(self.ctx.author)}"
                embed.set_footer(text=footer_text)
            except:
                embed.set_footer(text=footer_text)
        else:
            embed.set_footer(text=footer_text + " • Système Kayaba Collection")
        
        return embed, image_file
    
    async def sell_single(self, interaction: discord.Interaction):
        self.quantity = 1
        await self.execute_sell(interaction)
    
    async def sell_multiple(self, interaction: discord.Interaction):
        # Ouvrir un modal pour demander la quantité
        modal = QuantityModal(self)
        await interaction.response.send_modal(modal)
    
    async def execute_sell(self, interaction: discord.Interaction):
        # Vérifier la quantité actuelle de l'utilisateur
        current_collection = self.sell_manager.get_user_collection(self.ctx.author.id)
        current_quantity = current_collection.get(self.card['id'], 0)
        
        if self.quantity > current_quantity:
            exemplaire_word = self.sell_manager.get_plural_form("exemplaire", current_quantity)
            await interaction.response.send_message(f"❌ Vous ne possédez que {current_quantity} {exemplaire_word} de cette carte.", ephemeral=True)
            return
        
        if self.quantity <= 0:
            await interaction.response.send_message("❌ Quantité invalide.", ephemeral=True)
            return
        
        # Effectuer la vente
        success = self.sell_manager.remove_cards_from_collection(self.ctx.author.id, self.card['id'], self.quantity)
        
        if not success:
            await interaction.response.send_message("❌ Erreur lors de la vente.", ephemeral=True)
            return
        
        # Remettre les cartes en circulation
        self.sell_manager.update_exemplaires_restant(self.family_name, self.card['id'], self.quantity)
        
        # Calculer la valeur totale
        value = self.card.get('valeur', 0)
        total_value = value * self.quantity
        
        # Ajouter les Col à l'utilisateur
        col_success = self.sell_manager.add_col_to_user(self.ctx.author.id, total_value)
        
        # Envoyer le message privé
        rarity_emoji = {"Légendaire": "🟡", "Epique": "🟣", "Rare": "🔵", "Commun": "🟢"}.get(self.card.get('rarete', 'Commun'), "🟢")
        mp_message = f"**[SELL]** Vous avez vendu `{self.quantity}` **{self.card['nom']}** {EMOJIS.get('cartes', '🎴')} à {self.ctx.bot.user.name} pour une valeur de `{self.sell_manager.format_number(total_value)}` **Col** {EMOJIS.get('col', '💰')}"
        
        if MPManager:
            await MPManager.send_mp_if_enabled(self.ctx.bot, self.ctx.author.id, mp_message)
        else:
            try:
                await self.ctx.author.send(mp_message)
            except discord.Forbidden:
                pass
        
        # Afficher la confirmation
        embed = discord.Embed(
            title="✅ Vente effectuée",
            description=f"{rarity_emoji} **{self.card['nom']}** vendue avec succès !",
            color=discord.Color.green()
        )
        
        embed.add_field(
            name="Détails de la vente",
            value=f"**Quantité:** {self.quantity}\n**Valeur unitaire:** {self.sell_manager.format_number(value)} {EMOJIS.get('col', '💰')}\n**Valeur totale:**{self.sell_manager.format_number(total_value)} {EMOJIS.get('col', '💰')}",
            inline=False
        )
        
        if col_success:
            embed.add_field(
                name="💳 Col ajoutés",
                value=f"**+{self.sell_manager.format_number(total_value)} {EMOJIS.get('col', '💰')}** ont été ajoutés à votre solde.",
                inline=False
            )
        else:
            embed.add_field(
                name="⚠️ Attention",
                value="Les Col n'ont pas pu être ajoutés à votre solde. Contactez un administrateur.",
                inline=False
            )
        
        # Bouton pour revenir aux cartes
        back_btn = discord.ui.Button(label="🔙 Retour aux cartes", style=discord.ButtonStyle.secondary)
        back_btn.callback = self.back_to_cards
        view = discord.ui.View()
        view.add_item(back_btn)
        
        await interaction.response.edit_message(embed=embed, view=view)
    
    async def cancel(self, interaction: discord.Interaction):
        # Revenir à la vue des cartes
        cards = self.sell_manager.get_user_cards_in_family(self.ctx.author.id, self.family_name)
        card_view = CardSellView(self.ctx, self.sell_manager, self.family_name, cards)
        await interaction.response.edit_message(embed=card_view.create_embed(), view=card_view)
    
    async def back_to_cards(self, interaction: discord.Interaction):
        cards = self.sell_manager.get_user_cards_in_family(self.ctx.author.id, self.family_name)
        card_view = CardSellView(self.ctx, self.sell_manager, self.family_name, cards)
        await interaction.response.edit_message(embed=card_view.create_embed(), view=card_view)

class QuantityModal(discord.ui.Modal):
    def __init__(self, confirm_view: SellConfirmView):
        super().__init__(title="Quantité à vendre")
        self.confirm_view = confirm_view
        
        # Récupérer la quantité actuelle de l'utilisateur
        current_collection = confirm_view.sell_manager.get_user_collection(confirm_view.ctx.author.id)
        current_quantity = current_collection.get(confirm_view.card['id'], 0)
        
        self.quantity_input = discord.ui.TextInput(
            label="Quantité",
            placeholder=f"Entrez un nombre entre 1 et {current_quantity}",
            style=discord.TextStyle.short,
            required=True,
            min_length=1,
            max_length=10
        )
        self.add_item(self.quantity_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            quantity = int(self.quantity_input.value)
            
            # Récupérer la quantité actuelle (au cas où elle aurait changé)
            current_collection = self.confirm_view.sell_manager.get_user_collection(self.confirm_view.ctx.author.id)
            current_quantity = current_collection.get(self.confirm_view.card['id'], 0)
            
            if quantity < 1 or quantity > current_quantity:
                await interaction.response.send_message(f"❌ Quantité invalide. Veuillez entrer un nombre entre 1 et {current_quantity}.", ephemeral=True)
                return
            
            self.confirm_view.quantity = quantity
            
            # Recréer les boutons de confirmation
            self.confirm_view.clear_items()
            
            # Bouton de confirmation
            confirm_btn = discord.ui.Button(label="✅ Confirmer", style=discord.ButtonStyle.success, row=0)
            confirm_btn.callback = self.confirm_view.execute_sell
            self.confirm_view.add_item(confirm_btn)
            
            # Bouton d'annulation
            cancel_btn = discord.ui.Button(label="❌ Annuler", style=discord.ButtonStyle.red, row=0)
            cancel_btn.callback = self.confirm_view.cancel
            self.confirm_view.add_item(cancel_btn)
            
            await interaction.response.edit_message(embed=self.confirm_view.create_embed(), view=self.confirm_view)
            
        except ValueError:
            await interaction.response.send_message("❌ Veuillez entrer un nombre valide.", ephemeral=True)

# ==========================================
# COG PRINCIPAL
# ==========================================
class Sell(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sell_manager = SellManager()
    
    @commands.hybrid_command(name="sell", description="Vendez vos cartes contre des Col")
    async def sell(self, ctx: commands.Context):
        """Commande hybride pour vendre des cartes"""
        print(f"[SELL] Commande sell exécutée par {ctx.author.name} (ID: {ctx.author.id})")
        
        try:
            await ctx.defer()
            print(f"[SELL] Défer exécuté")
            
            # Créer et afficher la vue des familles
            view = FamilySellView(ctx, self.sell_manager)
            embed = view.create_embed()
            
            print(f"[SELL] Embed créé, envoi en cours...")
            await ctx.send(embed=embed, view=view)
            print(f"[SELL] Message envoyé avec succès")
            
        except Exception as e:
            print(f"\033[91m[SELL] ERREUR: {e}\033[0m")
            await ctx.send(f"{EMOJIS.get('cross', '❌')} Une erreur est survenue lors de l'affichage du menu de vente.")
            import traceback
            traceback.print_exc()

# Fonction setup obligatoire pour charger le Cog
async def setup(bot):
    await bot.add_cog(Sell(bot))
