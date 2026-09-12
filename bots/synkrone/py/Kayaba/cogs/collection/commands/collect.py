import discord
from discord.ext import commands
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta
from discord import Color

# Importer MPManager pour les notifications MP
try:
    from .mp import MPManager
except ImportError:
    try:
        from cogs.collection.commands.mp import MPManager
    except ImportError:
        MPManager = None

# ==========================================
# CONFIGURATION COLLECT
# ==========================================

# Cooldown selon le statut (en heures)
COOLDOWN_BASE = 1
COOLDOWN_PREMIUM = 0.5

# Nombre de cartes selon le statut
CARTE_BASE = 5
CARTE_PREMIUM = 8

# Taux de drop de base (en pourcentage)
RATE_COMMUN_BASE = 60.0
RATE_RARE_BASE = 25.0
RATE_EPIQUE_BASE = 10.0
RATE_LEGENDAIRE_BASE = 5.0

# Bonus premium pour les taux de drop (multiplicateurs)
BONUS_RARE_PREMIUM = 1.15       # +15%
BONUS_EPIQUE_PREMIUM = 1.20     # +20%
BONUS_LEGENDAIRE_PREMIUM = 1.25 # +25%
MALUS_COMMUN_PREMIUM = 0.85     # -15%

# Mode développeur (si True, le cooldown est désactivé)
DEVMOD = False

# Importer les classes depuis collection.py
try:
    from .collection import CharacterSelectView, CardManager
except ImportError as e1:
    try:
        # Essayer avec le chemin relatif
        from collection import CharacterSelectView, CardManager
    except ImportError as e2:
        # En dernier recours, utiliser l'ancien embed de collect.py
        CharacterSelectView = None
        CardManager = None

# Importer config_manager pour le footer
try:
    from cogs.developpeur.commands.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# Importer les modules pour la vérification de collection
try:
    import sqlite3
    import os
    from pathlib import Path
    COLLECTION_DB_PATH = Path("racine/cogs/collection/data/collection.db")
    USER_DATA_PATH = Path("cogs/collection/data/interserver")
    PREMIUM_PATH = Path("cogs/collection/data/premium.json")
except ImportError:
    COLLECTION_DB_PATH = None
    USER_DATA_PATH = None
    PREMIUM_PATH = None

# Chargement des emojis avec fallback intégré
def load_emojis():
    """Charge les emojis personnalisés avec fallback sur emojis standards"""
    emoji_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'emoji.json')
    
    # Emojis standards de fallback
    fallback_emojis = {
        "cartes": "🎴",
        "kronos": "💰", 
        "star": "⭐",
        "trophy": "🏆",
        "sword": "⚔️",
        "check": "✅",
        "handshake": "🤝",
        "cross": "❌",
        "gem": "💎",
        "chart": "📊",
        "user": "👤",
        "home": "🏠",
        "left_arrow": "⬅️",
        "right_arrow": "➡️",
        "plus": "➕",
        "info": "ℹ️",
        "tirage": "🎰"
    }
    
    try:
        with open(emoji_path, 'r', encoding='utf-8') as f:
            custom_emojis = json.load(f)
            
        # Fusionner avec fallback : garder les emojis personnalisés, utiliser fallback pour les manquants
        final_emojis = {}
        for key, fallback_value in fallback_emojis.items():
            final_emojis[key] = custom_emojis.get(key, fallback_value)
            
        return final_emojis
        
    except (FileNotFoundError, json.JSONDecodeError):
        # Si le fichier n'existe pas ou est invalide, utiliser uniquement les fallbacks
        return fallback_emojis

emojis = load_emojis()

# ==============================================================================
# --------------------------- CONFIGURATION DU TIRAGE ---------------------------
# ==============================================================================

# Nombre de cartes affichées/piochées par défaut
CARDS_TO_DRAW = 10

# Probabilités de drop selon la rareté (en pourcentage)
RARITY_WEIGHTS_BASE = {
    "Commun": RATE_COMMUN_BASE,
    "Rare": RATE_RARE_BASE,
    "Epique": RATE_EPIQUE_BASE,
    "Légendaire": RATE_LEGENDAIRE_BASE
}

# Chemins (cohérents avec ta structure)
BASE_DIR = os.path.dirname(__file__)
FAMILLE_DIR = os.path.normpath(os.path.join(BASE_DIR, '..', 'data', 'dev', 'famille'))

# ==============================================================================

class CardPaginationView(discord.ui.View):
    def __init__(self, ctx, cards, cog):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.cards = cards
        self.cog = cog
        self.current_index = 0
        self.retrieved_cards = set()  # Suivre les cartes déjà récupérées dans cette session
        self.update_buttons()

    def update_buttons(self):
        self.prev_btn.disabled = self.current_index == 0
        self.next_btn.disabled = self.current_index == len(self.cards) - 1
        
        # Récupérer les données utilisateur
        user_data = self.cog.get_user_data(self.ctx.author.id)
        slots = user_data.get('slots', 0) if user_data else 0
        
        # Mettre à jour le bouton de statut de collection
        current_card = self.cards[self.current_index]
        card_id = current_card.get('id', '')
        has_card, card_count = self.cog.check_user_collection(self.ctx.author.id, card_id)
        
        if has_card is None:
            self.collection_btn.label = "🔍 Statut inconnu"
            self.collection_btn.style = discord.ButtonStyle.secondary
        elif has_card:
            self.collection_btn.label = f"✅ Possédé ({card_count})"
            self.collection_btn.style = discord.ButtonStyle.success
        else:
            self.collection_btn.label = "❌ Manquant"
            self.collection_btn.style = discord.ButtonStyle.danger
        
        # Mettre à jour le bouton de slots
        self.tirages_btn.label = f"{emojis.get('tirage', '🎰')} Slots : {slots}"
        
        # Mettre à jour le bouton de récupération
        personnage_data = self.cog.get_character_data(card_id)
        exemplaires_restant = personnage_data.get('exemplaires_restant', 0) if personnage_data else 0
        
        # BLOCAGE UNIQUEMENT SI : 
        # 1. Plus de slots 
        # 2. Carte déjà récupérée dans cette session
        # 3. Épuisée
        if slots <= 0:
            self.recover_btn.label = "❌ Récupérer"
            self.recover_btn.style = discord.ButtonStyle.danger
            self.recover_btn.disabled = True
        elif card_id in self.retrieved_cards:
            self.recover_btn.label = "✅ Récupéré"
            self.recover_btn.style = discord.ButtonStyle.success
            self.recover_btn.disabled = True
        elif exemplaires_restant <= 0:
            self.recover_btn.label = "❌ Épuisée"
            self.recover_btn.style = discord.ButtonStyle.danger
            self.recover_btn.disabled = True
        else:
            # Même si on possède déjà la carte, on peut la récupérer
            self.recover_btn.label = "✅ Récupérer"
            self.recover_btn.style = discord.ButtonStyle.success
            self.recover_btn.disabled = False

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, row=0)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message(f"{emojis['cross']} Ce n'est pas votre tirage !", ephemeral=True)
        self.current_index -= 1
        await self.update_view(interaction)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, row=0)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message(f"{emojis['cross']} Ce n'est pas votre tirage !", ephemeral=True)
        self.current_index += 1
        await self.update_view(interaction)

    @discord.ui.button(label="❌ Manquant", style=discord.ButtonStyle.danger, row=0, custom_id="collection_status", disabled=True)
    async def collection_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Bouton désactivé - ne fait rien
        pass

    @discord.ui.button(label="🎴 Slots : 10", style=discord.ButtonStyle.secondary, row=0, disabled=True)
    async def tirages_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message(f"{emojis['cross']} Ce n'est pas votre tirage !", ephemeral=True)
        
        user_data = self.cog.get_user_data(interaction.user.id)
        if user_data:
            slots = user_data.get('slots', 0)
            await interaction.response.send_message(
                f"📊 **Vos statistiques :**\n"
                f"🎯 **Chances de capture :** {slots}\n"
                f"📦 **Slots disponibles :** {slots}",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(f"{emojis['cross']} Impossible de récupérer vos données.", ephemeral=True)

    @discord.ui.button(label="✅ Récupérer", style=discord.ButtonStyle.success, row=1)
    async def recover_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message(f"{emojis['cross']} Ce n'est pas votre tirage !", ephemeral=True)
        
        print(f"[COLLECT DEBUG] Bouton récupéré cliqué par {interaction.user.id}")
        
        current_card = self.cards[self.current_index]
        card_id = current_card.get('id', '')
        
        print(f"[COLLECT DEBUG] Carte à récupérer: {card_id} - {current_card.get('nom', 'Inconnu')}")

        # 1. Vérification Anti-spam immédiate 
        if card_id in self.retrieved_cards:
            return await interaction.response.send_message(f"{emojis['cross']} Vous avez déjà récupéré cette carte lors de ce tirage !", ephemeral=True)
        
        # 2. Vérifier les slots
        user_data = self.cog.get_user_data(interaction.user.id)
        if not user_data:
            return await interaction.response.send_message(f"{emojis['cross']} Impossible de récupérer vos données.", ephemeral=True)
        
        slots = user_data.get('slots', 0)
        if slots <= 0:
            return await interaction.response.send_message(
                f"{emojis['cross']} Vous n'avez aucune chance de capture !\n"
                f"*Veuillez obtenir des chances de capture pour pouvoir récupérer des cartes.*",
                ephemeral=True
            )

        # MARQUER IMMEDIATEMENT COMME RECUPEREE POUR EVITER LE SPAM
        self.retrieved_cards.add(card_id)
        
        # 3. Récupérer la carte via base de données
        print(f"[COLLECT DEBUG] Appel de add_card_to_collection...")
        if self.cog.add_card_to_collection(interaction.user.id, card_id):
            print(f"[COLLECT DEBUG] add_card_to_collection a retourné True, exécution du bloc MP")
            has_card, card_count = self.cog.check_user_collection(interaction.user.id, card_id)
            print(f"[COLLECT DEBUG] check_user_collection: has_card={has_card}, card_count={card_count}")
            
            # Mettre à jour les boutons (désactiver la récup de cette carte pour cette session)
            self.update_buttons()
            print(f"[COLLECT DEBUG] Boutons mis à jour")
            
            # Message public avec réponse initiale (ce qui permet d'utiliser edit_message via followup pour les boutons)
            await interaction.response.send_message(
                f"{emojis['check']} **{current_card['nom']}** a été récupéré avec succès !\n"
                f"📦 **Slots restants :** {slots - 1}",
                delete_after=1200.0  # 20 minutes = 1200 secondes
            )
            print(f"[COLLECT DEBUG] Message public envoyé")

            # Mise à jour UNIQUEMENT de la vue (View) de l'interaction originale pour éviter les conflits d'attachments
            print(f"[COLLECT DEBUG] Tentative de mise à jour de la vue...")
            try:
                # Utilisation de interaction.message.edit beaucoup plus stable que followup
                await interaction.message.edit(view=self)
                print(f"[COLLECT DEBUG] Vue mise à jour avec succès")
            except Exception as e:
                print(f"\033[91m[COLLECT DEBUG] Erreur lors de la mise à jour de la vue: {e}\033[0m")
                # Continuer quand même pour envoyer le MP
            
            # Message en MP structuré exactement comme demandé
            mp_message = f"**[COLLECT]** Vous avez récupéré **{current_card['nom']}**. Vous en avez désormais `{card_count}` {emojis['cartes']}"
            
            print(f"[COLLECT DEBUG] Message MP à envoyer: {mp_message}")
            
            try:
                # Importer MPManager pour les notifications
                from cogs.collection.commands.mp import MPManager
                if MPManager:
                    print(f"[COLLECT DEBUG] MPManager importé avec succès")
                    
                    # Debug : vérifier la préférence MP
                    mp_pref = MPManager.get_mp_preference(interaction.user.id)
                    print(f"[COLLECT DEBUG] Préférence MP pour {interaction.user.id}: {mp_pref}")
                    
                    result = await MPManager.send_mp_if_enabled(self.cog.bot, interaction.user.id, mp_message)
                    print(f"[COLLECT DEBUG] Résultat envoi MP: {result}")
                    
                    if result:
                        print(f"[COLLECT DEBUG] MP envoyé avec succès à {interaction.user.id}")
                    else:
                        print(f"\033[91m[COLLECT DEBUG] MP non envoyé (préférence désactivée ou erreur)\033[0m")
                else:
                    raise ImportError("MPManager is None")
                
            except Exception as e:
                print(f"\033[91m[COLLECT] MPManager non trouvé ou erreur: {e}. Tentative d'envoi direct...\033[0m")
                # Fallback : essayer d'envoyer directement si MPManager plante ou n'est pas dispo
                try:
                    print(f"[COLLECT DEBUG] Tentative d'envoi direct à {interaction.user.id}")
                    await interaction.user.send(mp_message)
                    print(f"[COLLECT DEBUG] Envoi direct réussi")
                except discord.Forbidden:
                    print(f"[COLLECT DEBUG] L'utilisateur a désactivé les MP")
                except Exception as e2:
                    print(f"\033[91m[COLLECT DEBUG] Erreur lors de l'envoi direct: {e2}\033[0m")
        else:
            # En cas d'erreur de BDD, on retire la carte de l'anti-spam pour permettre de réessayer
            self.retrieved_cards.remove(card_id)
            await interaction.response.send_message(
                f"{emojis['cross']} Une erreur est survenue lors de la récupération.",
                ephemeral=True
            )

    async def update_view(self, interaction: discord.Interaction):
        self.update_buttons()
        embed, files = self.cog.create_card_embed(
            self.cards[self.current_index], 
            self.current_index + 1,  # Page actuelle (1-based)
            len(self.cards),
            self.ctx
        )
        await interaction.response.edit_message(embed=embed, view=self, attachments=files)


class Collect(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def get_famille_image(self, famille_name):
        """Récupère le nom du fichier image de la famille"""
        config_path = os.path.join(FAMILLE_DIR, famille_name, 'config.json')
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f).get('image_file')
            except: pass
        return None

    def draw_cards(self, characters_by_rarity, amount, user_id: int):
        """Tire un nombre aléatoire de cartes uniques selon les probabilités"""
        drawn_cards = []
        used_characters = set()  # Pour éviter les doublons
        
        # On ne garde que les raretés qui possèdent au moins 1 personnage
        available_rarities = [r for r in characters_by_rarity.keys() if len(characters_by_rarity[r]) > 0]
        
        if not available_rarities:
            return [] # Aucun personnage dans la base de données
            
        # Utiliser les poids ajustés selon le statut premium
        weights = self.get_adjusted_rarity_weights(user_id)
        adjusted_weights = [weights[r] for r in available_rarities]

        for _ in range(amount):
            # On filtre les personnages pas encore utilisés
            available_chars = []
            available_weights = []
            
            for i, rarity in enumerate(available_rarities):
                unused_chars = [char for char in characters_by_rarity[rarity] 
                               if char['nom'] not in used_characters]
                if unused_chars:
                    available_chars.extend(unused_chars)
                    # On ajoute le poids pour chaque personnage disponible
                    available_weights.extend([adjusted_weights[i]] * len(unused_chars))
            
            if not available_chars:
                break  # Plus de personnages uniques disponibles
                
            # On choisit un personnage au hasard parmi les personnages uniques
            chosen_character = random.choices(available_chars, weights=available_weights, k=1)[0]
            used_characters.add(chosen_character['nom'])
            drawn_cards.append(chosen_character)
            
        return drawn_cards

    def get_collect_cooldown_remaining(self, user_id: int):
        """Retourne le temps restant avant de pouvoir utiliser .collect"""
        print(f"[DEBUG_COLLECT] get_collect_cooldown_remaining appelé pour user_id={user_id}")
        if DEVMOD:
            print(f"[DEBUG_COLLECT] DEVMOD=True, pas de cooldown")
            return 0  # Pas de cooldown en mode dev
        
        user_data = self.get_user_data(user_id)
        if not user_data or 'collect_cooldown_end' not in user_data:
            print(f"[DEBUG_COLLECT] Pas de cooldown enregistré pour cet utilisateur")
            return 0  # Pas de cooldown enregistré
        
        try:
            cooldown_end = datetime.fromisoformat(user_data['collect_cooldown_end'])
            current_time = datetime.now()
            print(f"[DEBUG_COLLECT] Cooldown end: {cooldown_end}, Current time: {current_time}")
            
            if current_time >= cooldown_end:
                print(f"[DEBUG_COLLECT] Cooldown terminé")
                return 0  # Cooldown terminé
            
            remaining_time = cooldown_end - current_time
            total_seconds = int(remaining_time.total_seconds())
            print(f"[DEBUG_COLLECT] Temps restant: {total_seconds} secondes")
            
            if total_seconds <= 0:
                return 0
            
            return total_seconds
        except Exception as e:
            print(f"[DEBUG_COLLECT] Erreur calcul cooldown: {e}")
            return 0

    def is_premium_user(self, user_id: int):
        """Vérifie si l'utilisateur est premium"""
        if not PREMIUM_PATH:
            return False
        
        try:
            with open(PREMIUM_PATH, 'r', encoding='utf-8') as f:
                premium_data = json.load(f)
                premium_users = premium_data.get('premium_users', [])
                return user_id in premium_users
        except Exception as e:
            print(f"\033[91m[DEBUG] Erreur vérification premium: {e}\033[0m")
            return False

    def get_adjusted_rarity_weights(self, user_id: int):
        """Retourne les poids de rareté ajustés selon le statut premium"""
        base_weights = RARITY_WEIGHTS_BASE.copy()
        
        if self.is_premium_user(user_id):
            # Bonus pour les utilisateurs premium
            base_weights["Rare"] *= BONUS_RARE_PREMIUM
            base_weights["Epique"] *= BONUS_EPIQUE_PREMIUM
            base_weights["Légendaire"] *= BONUS_LEGENDAIRE_PREMIUM
            # Réduire les communs pour compenser
            base_weights["Commun"] *= MALUS_COMMUN_PREMIUM
        
        return base_weights

    def get_cards_to_draw(self, user_id: int):
        """Retourne le nombre de cartes à tirer selon le statut premium"""
        return CARTE_PREMIUM if self.is_premium_user(user_id) else CARTE_BASE

    def get_cooldown_hours(self, user_id: int):
        """Retourne le cooldown en heures selon le statut premium"""
        return COOLDOWN_PREMIUM if self.is_premium_user(user_id) else COOLDOWN_BASE

    def get_user_data(self, user_id: int):
        """Récupère les données utilisateur depuis le JSON"""
        print(f"[DEBUG_COLLECT] get_user_data appelé pour user_id={user_id}")
        if not USER_DATA_PATH:
            print(f"[DEBUG_COLLECT] USER_DATA_PATH est None")
            return None
        
        user_file = USER_DATA_PATH / f"{user_id}.json"
        print(f"[DEBUG_COLLECT] Fichier utilisateur: {user_file}")
        
        if not user_file.exists():
            print(f"[DEBUG_COLLECT] Fichier utilisateur n'existe pas")
            return None
        
        try:
            with open(user_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                print(f"[DEBUG_COLLECT] Données utilisateur chargées: slots={data.get('slots', 0)}")
                return data
        except Exception as e:
            print(f"[DEBUG_COLLECT] Erreur lecture fichier utilisateur: {e}")
            return None

    def get_character_data(self, card_id: str):
        """Récupère les données du personnage depuis son config.json"""
        try:
            # Parcourir toutes les familles pour trouver le personnage
            for famille in os.listdir(FAMILLE_DIR):
                famille_path = os.path.join(FAMILLE_DIR, famille)
                if os.path.isdir(famille_path):
                    # Chercher dans personnages.json pour obtenir le nom du personnage
                    personnages_file = os.path.join(famille_path, 'personnages.json')
                    if os.path.exists(personnages_file):
                        with open(personnages_file, 'r', encoding='utf-8') as f:
                            personnages_data = json.load(f)
                        
                        # Chercher le personnage par ID pour obtenir son nom
                        personnage_nom = None
                        personnage_found = False
                        personnages_list = personnages_data.get('personnages', [])
                        
                        for i, personnage in enumerate(personnages_list):
                            if personnage.get('id') == card_id:
                                personnage_nom = personnage.get('nom')
                                personnage_found = True
                                break
                        
                        if personnage_found and personnage_nom:
                            # Mettre à jour le config.json du personnage
                            personnage_folder = personnage_nom.lower().replace(" ", "_")
                            config_file = os.path.join(famille_path, personnage_folder, 'config.json')
                           
                            if os.path.exists(config_file):
                                with open(config_file, 'r', encoding='utf-8') as f:
                                    return json.load(f)
        except Exception as e:
            print(f"\033[91m[DEBUG] Erreur récupération données personnage: {e}\033[0m")
            return {}

    def update_user_data(self, user_id: int, data: dict):
        """Met à jour les données utilisateur dans le JSON"""
        if not USER_DATA_PATH:
            return False
        
        # Création du dossier au cas où
        os.makedirs(USER_DATA_PATH, exist_ok=True)
        user_file = USER_DATA_PATH / f"{user_id}.json"
        try:
            with open(user_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            return True
        except Exception as e:
            print(f"\033[91m[DEBUG] Erreur écriture fichier utilisateur: {e}\033[0m")
            return False

    def check_user_collection_json(self, user_id: int, card_id: str):
        """Vérifie si l'utilisateur possède la carte dans son JSON"""
        user_data = self.get_user_data(user_id)
        if not user_data or 'collection' not in user_data:
            return False, 0
        
        collection = user_data['collection']
        if card_id in collection:
            return True, collection[card_id]
        return False, 0

    def add_card_to_collection(self, user_id: int, card_id: str):
        """Ajoute une carte à la collection de l'utilisateur"""
        print(f"[COLLECT DEBUG] add_card_to_collection appelé pour user_id={user_id}, card_id={card_id}")
        
        user_data = self.get_user_data(user_id)
        if not user_data:
            print(f"\033[91m[COLLECT DEBUG] ERREUR: user_data est None pour user_id={user_id}\033[0m")
            return False
        
        print(f"[COLLECT DEBUG] user_data récupéré avec succès, slots={user_data.get('slots', 0)}")
        
        # Ajouter la carte à la collection
        if 'collection' not in user_data:
            user_data['collection'] = {}
        
        if card_id in user_data['collection']:
            user_data['collection'][card_id] += 1
            print(f"[COLLECT DEBUG] Carte {card_id} incrémentée à {user_data['collection'][card_id]}")
        else:
            user_data['collection'][card_id] = 1
            print(f"[COLLECT DEBUG] Carte {card_id} ajoutée à la collection")
        
        # Retirer un slot
        if user_data.get('slots', 0) > 0:
            user_data['slots'] -= 1
            print(f"[COLLECT DEBUG] Slot retiré, nouveau solde: {user_data['slots']}")
        
        # Mettre à jour exemplaires_restant dans le config.json du personnage
        print(f"[COLLECT DEBUG] Mise à jour des exemplaires_restant pour {card_id}")
        self.update_character_exemplaires_restant(card_id)
        
        result = self.update_user_data(user_id, user_data)
        print(f"[COLLECT DEBUG] update_user_data retourne: {result}")
        
        return result
    
    def update_character_exemplaires_restant(self, card_id: str):
        """Met à jour exemplaires_restant dans le config.json ET personnages.json du personnage"""
        try:
            # Parcourir toutes les familles pour trouver le personnage
            for famille in os.listdir(FAMILLE_DIR):
                famille_path = os.path.join(FAMILLE_DIR, famille)
                if os.path.isdir(famille_path):
                    # Chercher dans personnages.json pour obtenir le nom du personnage
                    personnages_file = os.path.join(famille_path, 'personnages.json')
                    if os.path.exists(personnages_file):
                        with open(personnages_file, 'r', encoding='utf-8') as f:
                            personnages_data = json.load(f)
                        
                        # Chercher le personnage par ID pour obtenir son nom
                        personnage_nom = None
                        personnage_found = False
                        personnages_list = personnages_data.get('personnages', [])
                        
                        for i, personnage in enumerate(personnages_list):
                            if personnage.get('id') == card_id:
                                personnage_nom = personnage.get('nom')
                                personnage_found = True
                                break
                        
                        if personnage_nom and personnage_found:
                            # Mettre à jour le config.json du personnage
                            personnage_folder = personnage_nom.lower().replace(" ", "_")
                            config_file = os.path.join(famille_path, personnage_folder, 'config.json')
                           
                            if os.path.exists(config_file):
                                with open(config_file, 'r', encoding='utf-8') as f:
                                    config_data = json.load(f)
                                
                                # Mettre à jour exemplaires_restant
                                current_restant = config_data.get('exemplaires_restant', 0)
                                if current_restant > 0:
                                    new_restant = current_restant - 1
                                    config_data['exemplaires_restant'] = new_restant
                                    
                                    # Sauvegarder le config.json
                                    with open(config_file, 'w', encoding='utf-8') as f:
                                        json.dump(config_data, f, indent=4)
                                    
                                    # Mettre à jour aussi le personnages.json
                                    for personnage in personnages_data.get('personnages', []):
                                        if personnage.get('id') == card_id:
                                            personnage['exemplaires_restant'] = new_restant
                                            break
                                    
                                    # Sauvegarder le personnages.json
                                    with open(personnages_file, 'w', encoding='utf-8') as f:
                                        json.dump(personnages_data, f, indent=4)
                                    
                                    return True
        except Exception as e:
            pass
        
        return False

    def check_user_collection(self, user_id: int, card_id: str):
        """Vérifie si l'utilisateur possède la carte et combien d'exemplaires (via JSON)"""
        return self.check_user_collection_json(user_id, card_id)

    def get_all_characters_by_rarity(self):
        characters_by_rarity = {"Commun": [], "Rare": [], "Epique": [], "Légendaire": []}
        if not os.path.exists(FAMILLE_DIR): return characters_by_rarity

        for famille in os.listdir(FAMILLE_DIR):
            perso_file = os.path.join(FAMILLE_DIR, famille, 'personnages.json')
            if os.path.exists(perso_file):
                try:
                    with open(perso_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        for p in data.get("personnages", []):
                            rarete = p.get('rarete', 'Commun')
                            p['famille_nom'] = famille # On stocke le nom pour l'image plus tard
                            if rarete not in characters_by_rarity: rarete = "Commun"
                            
                            # Ne pas inclure les cartes avec 0 exemplaires restants
                            exemplaires_restant = p.get('exemplaires_restant', p.get('exemplaires', 0))
                            if exemplaires_restant <= 0:
                                continue
                            
                            characters_by_rarity[rarete].append(p)
                except: continue
        return characters_by_rarity

    def create_card_embed(self, personnage, current_page, total_pages, ctx=None):
        """Utilise la même méthode d'embed que collection.py ou fallback"""
        if CharacterSelectView and CardManager:
            try:
                # Créer une instance de CharacterSelectView pour utiliser sa méthode create_character_embed
                card_manager = CardManager()
                family_value = personnage.get('famille_nom', '')
                
                # Créer une vue factice pour utiliser la méthode d'embed
                view = CharacterSelectView(card_manager, family_value, [personnage])
                
                # Créer un objet interaction factice pour la compatibilité
                class MockInteraction:
                    def __init__(self, bot, ctx):
                        self.guild = ctx.guild if ctx else None
                        self.user = ctx.author if ctx else None
                        self.client = self.bot
                        self.bot = self.bot
                
                mock_interaction = MockInteraction(self.bot, ctx)
                
                # Utiliser la méthode create_character_embed de collection.py
                result = view.create_character_embed(personnage, mock_interaction)
                embed, files = result if isinstance(result, tuple) else (result, [])
                
                # Ajouter le footer spécifique au tirage
                current_footer = embed.footer.text if embed.footer.text else ""
                embed.set_footer(text=f"Carte {current_page}/{total_pages} • Tirage de {self.get_cards_to_draw(ctx.author.id) if ctx else CARTE_BASE} cartes • {current_footer}")
                
                return embed, files
            except Exception as e:
                pass
        
        # Fallback : utiliser l'ancien embed de collect.py avec config_manager
        rarete = personnage.get('rarete', 'Commun')
        famille_name = personnage.get('famille_nom', '')
        
        couleurs = {"Commun": 0x00ff00, "Rare": 0x00bfff, "Epique": 0x9932cc, "Légendaire": 0xffd700}
        color = couleurs.get(rarete, 0x2b2d31)

        # Utiliser config_manager si disponible
        if config_manager and ctx:
            try:
                # Vérifier si l'utilisateur est premium pour l'afficher dans l'auteur
                is_premium = self.is_premium_user(ctx.author.id)
                
                embed = config_manager.get_formatted_embed(
                    guild=ctx.guild, user=ctx.author, bot=self.bot,
                    title=f"{emojis['cartes']} {personnage.get('nom', 'Inconnu')}",
                    target_id=ctx.guild.id if ctx.guild else None
                )
                embed.description = f"Famille : **{famille_name}**"
                embed.color = color
                
                # Ajouter l'indicateur premium dans l'auteur si applicable
                if is_premium and hasattr(embed, 'set_author'):
                    # Si l'auteur n'existe pas, le créer
                    if not embed.author:
                        embed.set_author(
                            name=f"Membre premium ",
                            icon_url=ctx.author.display_avatar.url if ctx.author else None
                        )
                    else:
                        # Modifier l'auteur existant pour ajouter l'indicateur premium
                        embed.set_author(
                            name=f"{embed.author.name} Premium",
                            icon_url=embed.author.icon_url
                        )
            except Exception as e:
                embed = discord.Embed(
                    title=f"{emojis['cartes']} {personnage.get('nom', 'Inconnu')}",
                    description=f"Famille : **{famille_name}**",
                    color=color
                )
                # Ajouter l'image du bot en thumbnail et footer
                if self.bot and self.bot.user.avatar:
                    embed.set_thumbnail(url=self.bot.user.avatar.url)
                    embed.set_footer(
                        text="Système Kayaba Collection",
                        icon_url=self.bot.user.avatar.url
                    )
                else:
                    embed.set_footer(text="Système Kayaba Collection")
        else:
            embed = discord.Embed(
                title=f"{emojis['cartes']} {personnage.get('nom', 'Inconnu')}",
                description=f"Famille : **{famille_name}**",
                color=color
            )
        
        # Stats & Infos
        stats_text = []
        for s, n in [('vitesse', 'Vitesse'), ('precision', 'Précision'), ('vie', 'PV'), ('puissance', 'Puissance')]:
            if s in personnage: 
                stats_text.append(f"**{n}:** {personnage[s]}{'%' if s=='precision' else ''}")
        
        if stats_text: embed.add_field(name=f"{emojis['chart']} Statistiques", value="\n".join(stats_text), inline=True)

        info_text = [f"**Rareté:** {rarete} {emojis['star']}"]
        if 'valeur' in personnage: info_text.append(f"**Valeur:** {personnage['valeur']} {emojis['kronos']}")
        embed.add_field(name=f"{emojis['info']} Informations", value="\n".join(info_text), inline=True)

        # Footer avec config_manager et image du bot
        if config_manager and ctx:
            current_footer = embed.footer.text if embed.footer.text else ""
            # Ajouter l'image du bot dans le footer
            if self.bot and self.bot.user.avatar:
                # Vérifier si l'utilisateur est premium pour le message de tirage
                is_premium = self.is_premium_user(ctx.author.id)
                tirage_type = "Tirage premium" if is_premium else "Tirage standard"
                
                embed.set_footer(
                    text=f"Carte {current_page}/{total_pages} • {tirage_type} • {self.get_cards_to_draw(ctx.author.id) if ctx else CARTE_BASE} cartes • {current_footer}",
                    icon_url=self.bot.user.avatar.url
                )
            else:
                is_premium = self.is_premium_user(ctx.author.id) if ctx else False
                tirage_type = "Tirage premium" if is_premium else "Tirage standard"
                
                embed.set_footer(text=f"Carte {current_page}/{total_pages} • {tirage_type} • {self.get_cards_to_draw(ctx.author.id) if ctx else CARTE_BASE} cartes • {current_footer}")
        else:
            is_premium = self.is_premium_user(ctx.author.id) if ctx else False
            tirage_type = "Tirage premium" if is_premium else "Tirage standard"
            
            embed.set_footer(text=f"Carte {current_page}/{total_pages} • {tirage_type} • {self.get_cards_to_draw(ctx.author.id) if ctx else CARTE_BASE} cartes")

        attachments = []

        # 1. IMAGE DU PERSONNAGE (Image principale)
        if personnage.get('image'):
            perso_folder = personnage.get('nom', '').lower().replace(" ", "_")
            perso_img_path = os.path.join(FAMILLE_DIR, famille_name, perso_folder, personnage['image'])
            if os.path.exists(perso_img_path):
                img_perso = discord.File(perso_img_path, filename="card_main.png")
                attachments.append(img_perso)
                embed.set_image(url="attachment://card_main.png")

        # 2. IMAGE DE LA FAMILLE (Thumbnail)
        famille_img_name = self.get_famille_image(famille_name)
        if famille_img_name:
            famille_img_path = os.path.join(FAMILLE_DIR, famille_name, famille_img_name)
            if os.path.exists(famille_img_path):
                img_famille = discord.File(famille_img_path, filename="family_thumb.png")
                attachments.append(img_famille)
                embed.set_thumbnail(url="attachment://family_thumb.png")

        return embed, attachments

    @commands.hybrid_command(name="collect")
    async def collect(self, ctx: commands.Context):
        # Vérifier le cooldown personnalisé avant d'exécuter
        if not DEVMOD:
            cooldown_remaining = self.get_collect_cooldown_remaining(ctx.author.id)
            if cooldown_remaining > 0:
                # Calculer le temps restant
                hours = cooldown_remaining // 3600
                minutes = (cooldown_remaining % 3600) // 60
                seconds = cooldown_remaining % 60
                
                # Créer l'embed de cooldown
                if config_manager:
                    try:
                        embed = config_manager.get_formatted_embed(
                            guild=ctx.guild, user=ctx.author, bot=self.bot,
                            title=" Cooldown de Collect",
                            target_id=ctx.guild.id if ctx.guild else None
                        )
                        if embed is None:
                            raise ValueError("Embed retourné est None")
                            
                        description = f"Vous devez attendre avant de pouvoir faire un nouveau tirage !\n\n"
                        description += f"**Prochain tirage disponible dans :** `{hours}h {minutes}min {seconds}s`"
                        
                        embed.description = description
                    except Exception as e:
                        embed = discord.Embed(
                            title=" Cooldown de Collect",
                            description=f"Vous devez attendre avant de pouvoir faire un nouveau tirage !\n\n"
                                        f"**Prochain tirage disponible dans :** `{hours}h {minutes}min {seconds}s`",
                            color=discord.Color.orange()
                        )
                        # Ajouter l'image du bot en thumbnail et footer
                        if self.bot and self.bot.user.avatar:
                            embed.set_thumbnail(url=self.bot.user.avatar.url)
                            embed.set_footer(
                                text="Système Kayaba Collection",
                                icon_url=self.bot.user.avatar.url
                            )
                        else:
                            embed.set_footer(text="Système Kayaba Collection")
                else:
                    embed = discord.Embed(
                        title=" Cooldown de Collect",
                        description=f"Vous devez attendre avant de pouvoir faire un nouveau tirage !\n\n"
                                    f"**Prochain tirage disponible dans :** `{hours}h {minutes}min {seconds}s`",
                        color=discord.Color.orange()
                    )
                    # Ajouter l'image du bot en thumbnail et footer
                    if self.bot and self.bot.user.avatar:
                        embed.set_thumbnail(url=self.bot.user.avatar.url)
                        embed.set_footer(
                            text="Système Kayaba Collection",
                            icon_url=self.bot.user.avatar.url
                        )
                    else:
                        embed.set_footer(text="Système Kayaba Collection")
                
                return await ctx.send(embed=embed, ephemeral=True)
        
        chars = self.get_all_characters_by_rarity()
        
        if not any(chars.values()):
            return await ctx.send(f"{emojis['cross']} Aucun personnage trouvé dans la base de données.")

        # Vérifier si l'utilisateur est premium
        is_premium = self.is_premium_user(ctx.author.id)
        cards_to_draw = self.get_cards_to_draw(ctx.author.id)
        cooldown_hours = self.get_cooldown_hours(ctx.author.id)
        
        # Mettre à jour le cooldown dans le profil
        if not DEVMOD:
            # Récupération sécurisée : si l'utilisateur n'existe pas, on initialise ses données
            user_data = self.get_user_data(ctx.author.id) or {'slots': 0, 'collection': {}}
            current_time = datetime.now()
            user_data['collect_cooldown'] = current_time.isoformat()
            user_data['collect_cooldown_end'] = (current_time + timedelta(hours=cooldown_hours)).isoformat()
            
            # AJOUT D'UN SLOT GRATUIT À CHAQUE COLLECT
            current_slots = user_data.get('slots', 0)
            user_data['slots'] = current_slots + 1
            print(f"[DEBUG_COLLECT] Slot gratuit ajouté: {current_slots} → {user_data['slots']}")
            
            self.update_user_data(ctx.author.id, user_data)
        
        # Tirage sans doublons avec poids ajustés
        drawn_cards = self.draw_cards(chars, cards_to_draw, ctx.author.id)
        
        # Protection supplémentaire : s'il n'y a plus du tout de carte disponible
        if not drawn_cards:
            return await ctx.send(f"{emojis['cross']} Impossible de générer un tirage : toutes les cartes sont épuisées ou manquantes.")

        view = CardPaginationView(ctx, drawn_cards, self)
        embed, files = self.create_card_embed(drawn_cards[0], 1, len(drawn_cards), ctx)

        await ctx.send(embed=embed, view=view, files=files)

async def setup(bot):
    await bot.add_cog(Collect(bot))