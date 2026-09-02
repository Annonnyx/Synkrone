import discord
from discord.ext import commands
import json
import os
import random
import asyncio
from datetime import datetime, timedelta

# ==========================================
# CONFIGURATION BOUTIQUE
# ==========================================

BASE_DIR = os.path.dirname(__file__)
DATA_DEV_DIR = os.path.normpath(os.path.join(BASE_DIR, '..', 'data', 'dev'))
FAMILLE_DIR = os.path.join(DATA_DEV_DIR, 'famille')
USER_DATA_PATH = os.path.normpath(os.path.join(BASE_DIR, '..', 'data', 'interserver'))
SHOP_DATA_PATH = os.path.normpath(os.path.join(BASE_DIR, '..', 'data', 'shop'))

# Configuration des stocks et prix
BASE_CONFIG = {
    "max_cards": 5,
    "price_multiplier": 1.2, 
    "min_rarity": ["Rare", "Epique", "Légendaire"]
}

PREMIUM_CONFIG = {
    "max_cards": 6,
    "price_multiplier": 1.0, # Prix normal pour les premiums
    "min_rarity": ["Rare", "Epique", "Légendaire"]
}

# Importer config_manager pour le style visuel
try:
    from cogs.developpeur.commands.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# Chargement des emojis
def load_emojis():
    emoji_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'emoji.json')
    fallback_emojis = {
        "cartes": "🎴", "kronos": "💰", "star": "⭐", "shop": "🛍️",
        "chart": "📊", "info": "ℹ️", "check": "✅", "cross": "❌"
    }
    try:
        with open(emoji_path, 'r', encoding='utf-8') as f:
            custom_emojis = json.load(f)
            return {k: custom_emojis.get(k, v) for k, v in fallback_emojis.items()}
    except:
        return fallback_emojis

emojis = load_emojis()

# ==========================================
# FONCTIONS UTILITAIRES (LOGIQUE)
# ==========================================

def format_number(n):
    return f"{n:,}".replace(",", " ")

def get_user_data(user_id):
    user_file = os.path.join(USER_DATA_PATH, f"{user_id}.json")
    if os.path.exists(user_file):
        try:
            with open(user_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return None
    return None

def save_user_data(user_id, data):
    user_file = os.path.join(USER_DATA_PATH, f"{user_id}.json")
    os.makedirs(os.path.dirname(user_file), exist_ok=True)
    try:
        with open(user_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except: return False

def is_premium_user(user_id: int):
    """Vérifie si l'utilisateur est premium via premium.json"""
    premium_path = os.path.normpath(os.path.join(BASE_DIR, '..', 'data', 'premium.json'))
    if not os.path.exists(premium_path):
        return False
    
    try:
        with open(premium_path, 'r', encoding='utf-8') as f:
            premium_data = json.load(f)
            premium_users = premium_data.get('premium_users', [])
            return user_id in premium_users
    except Exception as e:
        print(f"\033[91m[DEBUG] Erreur vérification premium boutique: {e}\033[0m")
        return False

def get_all_cards():
    all_cards = []
    if not os.path.exists(FAMILLE_DIR): return all_cards
    for famille in os.listdir(FAMILLE_DIR):
        famille_path = os.path.join(FAMILLE_DIR, famille)
        if os.path.isdir(famille_path):
            perso_file = os.path.join(famille_path, 'personnages.json')
            if os.path.exists(perso_file):
                try:
                    with open(perso_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        for p in data.get('personnages', []):
                            p['famille_nom'] = famille
                            all_cards.append(p)
                except: continue
    return all_cards

def get_user_shop_data(user_id):
    """Récupère les données de boutique individuelle pour un utilisateur"""
    shop_file = os.path.join(SHOP_DATA_PATH, f"shop_{user_id}.json")
    try:
        with open(shop_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except: 
        return {"last_reset": "", "base_cards": [], "premium_cards": []}

def save_user_shop_data(user_id, data):
    """Sauvegarde les données de boutique individuelle pour un utilisateur"""
    shop_file = os.path.join(SHOP_DATA_PATH, f"shop_{user_id}.json")
    os.makedirs(os.path.dirname(shop_file), exist_ok=True)
    try:
        with open(shop_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except: return False

# ==========================================
# SYSTÈME DE VUE (PAGINATION STYLE COLLECT)
# ==========================================

class ShopPaginationView(discord.ui.View):
    def __init__(self, ctx, cards, is_premium, cog):
        super().__init__(timeout=600)  # 10 minutes au lieu de 5
        self.ctx = ctx
        self.cards = cards
        self.is_premium = is_premium
        self.cog = cog
        self.current_index = 0
        self.config = PREMIUM_CONFIG if is_premium else BASE_CONFIG
        self.update_buttons()

    async def on_timeout(self):
        """Appelé quand la vue expire"""
        try:
            # Désactiver tous les boutons
            for item in self.children:
                item.disabled = True
            # Mettre à jour le message pour montrer que la vue a expiré
            if hasattr(self, 'message'):
                await self.message.edit(view=self)
        except:
            pass  # Ignorer les erreurs lors du timeout

    def update_buttons(self):
        # Navigation
        self.prev_btn.disabled = self.current_index == 0
        self.next_btn.disabled = self.current_index == len(self.cards) - 1
        
        # Données utilisateur
        user_data = get_user_data(self.ctx.author.id)
        balance = user_data.get('col', 0) if user_data else 0
        self.balance_btn.label = f"{format_number(balance)}"
        
        # État d'achat du jour avec reset à 7h
        last_purchase = user_data.get('last_shop_purchase', "")
        now = datetime.now()
        
        # Si on est avant 7h, utiliser la date d'hier pour la vérification
        if now.hour < 7:
            yesterday = now - timedelta(days=1)
            check_date = yesterday.strftime("%Y-%m-%d")
        else:
            check_date = now.strftime("%Y-%m-%d")
        
        has_bought_today = last_purchase == check_date

        # Info Carte Actuelle
        current_card = self.cards[self.current_index]
        price = int(current_card.get('valeur', 0) * self.config["price_multiplier"])
        stock = current_card.get('exemplaires_restant', 0)

        if has_bought_today:
            self.buy_btn.label = "Quota atteint"
            self.buy_btn.style = discord.ButtonStyle.secondary
            self.buy_btn.disabled = True
        elif stock <= 0:
            self.buy_btn.label = "Rupture de stock"
            self.buy_btn.style = discord.ButtonStyle.danger
            self.buy_btn.disabled = True
        elif balance < price:
            self.buy_btn.label = "solde insuffisant"
            self.buy_btn.style = discord.ButtonStyle.danger
            self.buy_btn.disabled = True
        else:
            self.buy_btn.label = f"acheter pour {format_number(price)}"
            self.buy_btn.style = discord.ButtonStyle.success
            self.buy_btn.disabled = False

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, row=0)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id: return
        try:
            self.current_index -= 1
            await self.refresh_view(interaction)
        except Exception as e:
            print(f"\033[91m[DEBUG] Erreur prev_btn boutique: {e}\033[0m")

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, row=0)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id: return
        try:
            self.current_index += 1
            await self.refresh_view(interaction)
        except Exception as e:
            print(f"\033[91m[DEBUG] Erreur next_btn boutique: {e}\033[0m")

    @discord.ui.button(label="0", emoji="<:col:1482462727468486738>", style=discord.ButtonStyle.secondary, row=0, disabled=True)
    async def balance_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="Acheter", emoji="<:col:1482462727468486738>", style=discord.ButtonStyle.success, row=1)
    async def buy_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id: return
        
        user_data = get_user_data(self.ctx.author.id)
        current_card = self.cards[self.current_index]
        price = int(current_card.get('valeur', 0) * self.config["price_multiplier"])
        
        if user_data.get('col', 0) < price:
            return await interaction.response.send_message(f"{emojis['cross']} Solde insuffisant !", ephemeral=True)

        # Vérifier si l'utilisateur a déjà acheté aujourd'hui
        last_purchase = user_data.get('last_shop_purchase', "")
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Vérifier si on est après 7h du matin pour le reset quotidien
        now = datetime.now()
        reset_time = now.replace(hour=7, minute=0, second=0, microsecond=0)
        
        # Si on est avant 7h, utiliser la date d'hier pour la vérification
        if now.hour < 7:
            yesterday = now - timedelta(days=1)
            check_date = yesterday.strftime("%Y-%m-%d")
        else:
            check_date = today
        
        # Bloquer si déjà acheté aujourd'hui (après 7h)
        if last_purchase == check_date:
            return await interaction.response.send_message(f"{emojis['cross']} Vous avez déjà acheté une carte aujourd'hui ! Revenez demain après 7h.", ephemeral=True)

        # Vérifier si l'utilisateur possède déjà la carte
        collection = user_data.get('collection', {})
        card_id = current_card['id']
        if card_id in collection and collection[card_id] > 0:
            return await interaction.response.send_message(f"{emojis['cross']} Vous ne pouvez pas acheter cette carte car vous la possédez déjà !", ephemeral=True)

        # Procédure d'achat
        user_data['col'] -= price
        user_data['last_shop_purchase'] = datetime.now().strftime("%Y-%m-%d")
        
        collection[card_id] = collection.get(card_id, 0) + 1
        user_data['collection'] = collection
        
        # Sauvegarde
        if save_user_data(self.ctx.author.id, user_data):
            # Message MP (style Kayaba - identique à collection.py)
            try:
                await self.ctx.author.send(
                    f"**[BOUTIQUE]** Vous avez acheté **{current_card['nom']}** {emojis['cartes']} "
                    f"à **𝑲𝒂𝒚𝒂𝒃𝒂** pour `{format_number(price)}` **Col** {emojis['kronos']}.\n"
                    f"Vous en possédez désormais `{collection[card_id]}`."
                )
            except: pass
            
            await interaction.response.defer()  # Acknowledge l'interaction
            await self.ctx.send(f"{emojis['check']} Achat réussi ! La carte a été ajoutée à votre collection.", reference=self.ctx.message, delete_after=5)
            self.update_buttons()
            await interaction.edit_original_response(view=self)
            
            # Clear l'embed de la boutique après un court délai
            await asyncio.sleep(2)
            await self.ctx.message.delete()
            try:
                await self.ctx.channel.fetch_message(self.ctx.message.id)
            except:
                pass
        else:
            await interaction.response.send_message("❌ Erreur lors de la transaction.", ephemeral=True)

    async def refresh_view(self, interaction):
        try:
            self.update_buttons()
            embed, files = self.cog.create_shop_embed(
                self.cards[self.current_index], 
                self.current_index + 1, 
                len(self.cards), 
                self.ctx,
                self.is_premium
            )
            await interaction.response.edit_message(embed=embed, view=self, attachments=files)
        except discord.errors.InteractionResponded:
            # Si l'interaction a déjà été répondue
            try:
                await interaction.edit_original_response(embed=embed, view=self, attachments=files)
            except:
                pass  # Si même ça échoue, on ignore silencieusement
        except discord.errors.NotFound:
            # Si le message n'existe plus
            pass
        except Exception as e:
            print(f"\033[91m[DEBUG] Erreur refresh_view boutique: {e}\033[0m")

# ==========================================
# COG PRINCIPAL
# ==========================================

class Boutique(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def generate_daily_cards(self, is_premium):
        all_cards = get_all_cards()
        config = PREMIUM_CONFIG if is_premium else BASE_CONFIG
        
        # Filtrer par rareté et stock
        eligible = [c for c in all_cards if c.get('rarete') in config["min_rarity"] and c.get('exemplaires_restant', 0) > 0]
        
        if not eligible: return random.sample(all_cards, min(len(all_cards), config["max_cards"]))
        
        return random.sample(eligible, min(len(eligible), config["max_cards"]))

    def get_or_create_shop(self, user_id):
        today = datetime.now().strftime("%Y-%m-%d")
        shop_data = get_user_shop_data(user_id)
        
        # Reset à 07:00 du matin
        now = datetime.now()
        reset_time = now.replace(hour=7, minute=0, second=0, microsecond=0)
        
        # Si on est après 7h et que le shop date d'avant 7h aujourd'hui ou d'un autre jour
        if shop_data.get("date") != today:
            shop_data = {
                "date": today,
                "base_cards": self.generate_daily_cards(False),
                "premium_cards": self.generate_daily_cards(True)
            }
            save_user_shop_data(user_id, shop_data)
            
        return shop_data

    def create_shop_embed(self, personnage, current_page, total_pages, ctx, is_premium):
        try:
            guild = getattr(ctx, 'guild', None)
            user = getattr(ctx, 'user', None)
            bot = getattr(ctx, 'bot', None)

            char_name = personnage.get('nom', 'Inconnu')
            
            # Couleur selon la rareté (identique à collection.py)
            rarity_colors = {
                'Commun': 0x95a5a6,      # Gris
                'Rare': 0x3498db,         # Bleu
                'Epique': 0x9b59b6,       # Violet
                'Légendaire': 0xf1c40f    # Or
            }
            embed_color = rarity_colors.get(personnage.get('rarete', 'Commun'), 0x95a5a6)
            
            # Formatage avec des espaces pour tous les chiffres (sauf IDs)
            def format_number(num):
                try:
                    return f"{num:,}".replace(',', ' ')
                except:
                    return "0"
            
            valeur_str = format_number(personnage.get('valeur', 0))
            exemplaires_str = format_number(personnage.get('exemplaires', 0))
            exemplaires_restant_str = format_number(personnage.get('exemplaires_restant', 0))
            
            vitesse_str = format_number(personnage.get('vitesse', 0))
            precision_str = format_number(personnage.get('precision', 0))
            vie_str = format_number(personnage.get('vie', 0))
            puissance_str = format_number(personnage.get('puissance', 0))

            # Description avec rareté, famille et ID sur une seule ligne (ID entre backticks)
            rarity_emoji = {'Commun': '⚪', 'Rare': '🔵', 'Epique': '🟣', 'Légendaire': '🟡'}
            rarity_emoji_display = rarity_emoji.get(personnage.get('rarete', 'Commun'), '⚪')
            
            # Formatage du titre dans la description (identique à collection.py)
            cartes_emoji = emojis.get('cartes', '🃏')
            kronos_emoji = emojis.get('kronos', '💰')
            famille_name = personnage.get('famille_nom', 'Inconnue')
            
            # Calcul du prix selon le type de boutique
            config = PREMIUM_CONFIG if is_premium else BASE_CONFIG
            price = int(personnage.get('valeur', 0) * config["price_multiplier"])
            price_str = format_number(price)
            
            desc = f"**# {cartes_emoji} {char_name}** __{price_str} {kronos_emoji}__\n-# *{rarity_emoji_display} {personnage.get('rarete', 'Commun')} - {famille_name} - `#{personnage.get('id', 'N/A')}`*\n{cartes_emoji} `{exemplaires_str}` exemplaires dont `{exemplaires_restant_str}` en circulation"
            
            # Ajouter la description du personnage si elle existe (entre ``)
            if personnage.get('description'):
                desc += f"\n```\n{personnage.get('description', '')}\n```"

            # Créer l'embed avec config_manager pour avoir le même footer que Kayaba Collection (sans titre)
            if config_manager:
                try:
                    embed = config_manager.get_formatted_embed(
                        guild, user, bot,
                        title="", description=desc, target_id=guild.id if guild else None
                    )
                    # Conserver la couleur de rareté
                    embed.color = embed_color
                    
                    # Footer dynamique avec pagination selon le statut premium
                    shop_type = "Boutique Premium" if is_premium else ""
                    current_footer = embed.footer.text if embed.footer.text else ""
                    current_icon = embed.footer.icon_url if embed.footer.icon_url else (bot.user.avatar.url if bot and bot.user.avatar else None)
                    
                    footer_text = f"Page {current_page}/{total_pages}"
                    if shop_type:
                        footer_text += f" • {shop_type}"
                    if current_footer:
                        footer_text += f" • {current_footer}"
                    
                    embed.set_footer(text=footer_text, icon_url=current_icon)
                except Exception as e:
                    print(f"\033[91m[DEBUG] Erreur config_manager boutique: {e}\033[0m")
                    embed = discord.Embed(description=desc, color=embed_color)
                    shop_type = "Boutique Premium" if is_premium else ""
                    footer_text = f"Page {current_page}/{total_pages}"
                    if shop_type:
                        footer_text += f" • {shop_type}"
                    footer_text += " • Système Kayaba Collection"
                    embed.set_footer(text=footer_text)
            else:
                embed = discord.Embed(description=desc, color=embed_color)
                shop_type = "Boutique Premium" if is_premium else ""
                footer_text = f"Page {current_page}/{total_pages}"
                if shop_type:
                    footer_text += f" • {shop_type}"
                footer_text += " • Système Kayaba Collection"
                embed.set_footer(text=footer_text)
            
            # Stats en 2 colonnes (avec emojis et valeurs entre ``) - identique à collection.py
            embed.add_field(name=f"⚡ **Vitesse:** `{vitesse_str}`", value=f"🎯 **Précision:** `{precision_str}%`", inline=True)
            embed.add_field(name=f"❤️ **Vie:** `{vie_str}`", value=f"⚔️ **Puissance:** `{puissance_str}`", inline=True)

            files = []
            
            # Thumbnail : Image de la famille (première image trouvée dans le dossier)
            try:
                fam_file, fam_url = self.get_family_image(famille_name)
                if fam_file:
                    files.append(fam_file)
                    embed.set_thumbnail(url=fam_url)
            except Exception as e:
                print(f"\033[91m[DEBUG] Erreur image famille boutique: {e}\033[0m")

            # Image principale : Personnage
            try:
                char_file, char_url = self.get_local_file_data(famille_name, personnage.get('nom', ''))
                if char_file:
                    files.append(char_file)
                    embed.set_image(url=char_url)
                elif personnage.get('image', '').startswith('http'):
                    embed.set_image(url=personnage.get('image'))
            except Exception as e:
                print(f"\033[91m[DEBUG] Erreur image personnage boutique: {e}\033[0m")

            return embed, files
        except Exception as e:
            print(f"\033[91m[DEBUG] Erreur create_shop_embed: {e}\033[0m")
            # Embed de secours en cas d'erreur
            embed = discord.Embed(
                description=f"**# 🃏 {personnage.get('nom', 'Inconnu')}**\nImpossible d'afficher toutes les informations.",
                color=0x95a5a6
            )
            embed.set_footer(text=f"Page {current_page}/{total_pages} • Système Kayaba Collection")
            return embed, []
    
    def get_family_image(self, family_value):
        """Récupère la première image trouvée dans le dossier de la famille (identique à collection.py)"""
        family_path = os.path.join(FAMILLE_DIR, family_value)
        
        if not os.path.exists(family_path):
            return None, None
        
        # Chercher la première image dans le dossier de la famille
        for file in os.listdir(family_path):
            if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                img_path = os.path.join(family_path, file)
                file_key = f"fam_{file.replace(' ', '_')}"
                return discord.File(img_path, filename=file_key), f"attachment://{file_key}"
        
        return None, None
    
    def get_local_file_data(self, family_value, character_name=None):
        """Récupère les données de fichier local (identique à collection.py)"""
        base_path = os.path.join(FAMILLE_DIR, family_value)
        
        if character_name:
            char_folder = character_name.lower().replace(" ", "_")
            target_dir = os.path.join(base_path, char_folder)
        else:
            target_dir = base_path

        config_file = os.path.join(target_dir, 'config.json')
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    image_name = data.get('image', '')
                    if image_name and not image_name.startswith('http'):
                        img_path = os.path.join(target_dir, image_name)
                        if os.path.exists(img_path):
                            file_key = f"img_{image_name.replace(' ', '_')}"
                            return discord.File(img_path, filename=file_key), f"attachment://{file_key}"
            except:
                pass
        return None, None

    @commands.command(name="boutique")
    async def shop(self, ctx):
        """Ouvre la boutique quotidienne de Kayaba"""
        user_data = get_user_data(ctx.author.id)
        if not user_data:
            # Créer le profil utilisateur
            user_data = {
                "user_id": ctx.author.id,
                "first_seen": True,
                "created_at": datetime.now().isoformat(),
                "slots": 2,
                "collection": {},
                "mp_enabled": True
            }
            save_user_data(ctx.author.id, user_data)
            return await ctx.send("Vous venez de créer votre profil. Vous pouvez maintenant faire `.guide`")

        is_premium = is_premium_user(ctx.author.id)
        shop_data = self.get_or_create_shop(ctx.author.id)
        
        cards = shop_data["premium_cards"] if is_premium else shop_data["base_cards"]
        
        if not cards:
            return await ctx.send("🛒 La boutique est vide pour le moment. Revenez plus tard !")

        view = ShopPaginationView(ctx, cards, is_premium, self)
        embed, files = self.create_shop_embed(cards[0], 1, len(cards), ctx, is_premium)
        
        msg = await ctx.send(embed=embed, view=view, files=files)
        view.message = msg  # Stocker la référence pour le timeout

async def setup(bot):
    await bot.add_cog(Boutique(bot))
