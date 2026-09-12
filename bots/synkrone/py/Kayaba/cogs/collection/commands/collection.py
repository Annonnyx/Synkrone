import discord
from discord.ext import commands
import json
import os
import sys
import asyncio
from typing import Optional, Dict, Any, List

# ==========================================
# CONFIGURATION & CHEMINS
# ==========================================
BASE_DIR = os.path.dirname(__file__)
DATA_DEV_DIR = os.path.normpath(os.path.join(BASE_DIR, '..', 'data', 'dev'))
FAMILLE_DIR = os.path.join(DATA_DEV_DIR, 'famille')

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
# MANAGER DE CARTES
# ==========================================
class CardManager:
    def __init__(self):
        self.famille_dir = FAMILLE_DIR
    
    def update_exemplaires_restant(self, famille_name: str, personnage_name: str, new_value: int):
        """Met à jour exemplaires_restant dans personnages.json"""
        personnages_file = os.path.join(FAMILLE_DIR, famille_name, 'personnages.json')
        if not os.path.exists(personnages_file):
            return False
        
        try:
            with open(personnages_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Trouver le personnage et mettre à jour
            for personnage in data.get('personnages', []):
                if personnage.get('nom') == personnage_name:
                    personnage['exemplaires_restant'] = new_value
                    break
            
            # Sauvegarder
            with open(personnages_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            
            print(f"[COLLECTION] exemplaires_restant mis à jour pour {personnage_name}: {new_value}")
            return True
        except Exception as e:
            print(f"[COLLECTION] Erreur mise à jour exemplaires_restant: {e}")
            return False
    
    def get_all_cards(self):
        """Récupère toutes les cartes de toutes les familles"""
        print("[DEBUG] DÉBUT get_all_cards()")
        all_cards = []
        
        if not os.path.exists(FAMILLE_DIR):
            print(f"[DEBUG] FAMILLE_DIR n'existe pas: {FAMILLE_DIR}")
            return all_cards
        
        print(f"[DEBUG] Parcours des familles dans: {FAMILLE_DIR}")
        for famille_name in os.listdir(FAMILLE_DIR):
            famille_path = os.path.join(FAMILLE_DIR, famille_name)
            print(f"[DEBUG] Famille trouvée: {famille_name}")
            
            if not os.path.isdir(famille_path):
                print(f"[DEBUG] {famille_name} n'est pas un dossier")
                continue
            
            personnages_file = os.path.join(famille_path, 'personnages.json')
            print(f"[DEBUG] Fichier personnages.json: {personnages_file}")
            
            if not os.path.exists(personnages_file):
                print(f"[DEBUG] Fichier personnages.json non trouvé pour {famille_name}")
                continue
            
            try:
                with open(personnages_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    personnages = data.get('personnages', [])
                    print(f"[DEBUG] Personnages trouvés dans {famille_name}: {len(personnages)}")
                    
                config_file = os.path.join(famille_path, 'config.json')
                famille_config = {}
                if os.path.exists(config_file):
                    with open(config_file, 'r', encoding='utf-8') as f:
                        famille_config = json.load(f)
                
                for personnage in personnages:
                    personnage_name = personnage.get('nom', 'Inconnu')
                    print(f"[DEBUG] Personnage trouvé: '{personnage_name}'")
                    
                    # Utiliser directement les données de personnages.json
                    exemplaires_value = personnage.get('exemplaires', 0)
                    exemplaires_restant_value = personnage.get('exemplaires_restant', exemplaires_value)
                    
                    print(f"[DEBUG] {personnage_name}: exemplaires={exemplaires_value}, exemplaires_restant={exemplaires_restant_value}")
                    
                    # Ne pas inclure les cartes avec 0 exemplaires restants
                    if exemplaires_restant_value <= 0:
                        print(f"[DEBUG] Carte {personnage_name} exclue (0 exemplaires restants)")
                        continue
                    
                    card_info = {
                        'id': personnage.get('id', ''),
                        'config_id': self.get_config_id(famille_name, personnage_name),
                        'nom': personnage.get('nom', 'Inconnu'),
                        'famille': famille_name,
                        'famille_nom': famille_config.get('nom', famille_name),
                        'description': personnage.get('description', ''),
                        'rarete': personnage.get('rarete', 'Commun'),
                        'valeur': personnage.get('valeur', 0),
                        'exemplaires': exemplaires_value,
                        'exemplaires_restant': exemplaires_restant_value,
                        'vitesse': personnage.get('vitesse', 0),
                        'precision': personnage.get('precision', 0),
                        'vie': personnage.get('vie', 0),
                        'puissance': personnage.get('puissance', 0),
                        'image': personnage.get('image', ''),
                        'creation_date': personnage.get('creation_date', ''),
                        'creator_id': personnage.get('creator_id', 0)
                    }
                    all_cards.append(card_info)
                    print(f"[DEBUG] Ajout de {personnage_name} à la liste des cartes")
                    
            except Exception as e:
                print(f"[DEBUG] Erreur générale pour {famille_name}: {e}")
                continue
        
        print(f"[DEBUG] FIN get_all_cards() - {len(all_cards)} cartes chargées (filtrées)")
        return all_cards
    
    def get_config_id(self, famille_name: str, personnage_name: str):
        personnage_dir = os.path.join(FAMILLE_DIR, famille_name, personnage_name.lower().replace(" ", "_"))
        config_file = os.path.join(personnage_dir, 'config.json')
        
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                    return config_data.get('id', '')
            except Exception:
                pass
        return ''
    
    def get_card_by_id(self, card_id: str):
        print(f"[DEBUG] get_card_by_id appelé avec: {card_id}")
        all_cards = self.get_all_cards()
        print(f"[DEBUG] get_card_by_id: {len(all_cards)} cartes trouvées")
        for card in all_cards:
            if card['id'] == card_id or card['config_id'] == card_id:
                print(f"[DEBUG] get_card_by_id: carte trouvée - exemplaires_restant = {card.get('exemplaires_restant', 'NON_TROUVE')}")
                return card
        return None

# ==========================================
# VUES POUR LA COLLECTION
# ==========================================
class FamilySelectView(discord.ui.View):
    def __init__(self, card_manager):
        super().__init__(timeout=300)
        self.card_manager = card_manager
        self.families = self.get_families()
        self.current_page = 1
        self.families_per_page = 15
        self.total_pages = max(1, (len(self.families) + self.families_per_page - 1) // self.families_per_page)
        self._build_view()
    
    def _build_view(self):
        self.clear_items()
        
        if not self.families:
            return
        
        # Pagination : utiliser les familles de la page actuelle
        start_idx = (self.current_page - 1) * self.families_per_page
        end_idx = min(start_idx + self.families_per_page, len(self.families))
        page_families = self.families[start_idx:end_idx]
        
        family_options = []
        for i, family in enumerate(page_families):
            family_options.append(discord.SelectOption(
                label=family['name'],
                value=family['value'],
                description=f"{family['count']} personnages"
            ))
        
        family_select = discord.ui.Select(
            placeholder="👨‍👩‍👧‍👦 Choisissez une famille...",
            options=family_options,
            row=0
        )
        family_select.callback = self.select_family
        self.add_item(family_select)
        
        # Boutons de pagination
        if self.current_page > 1:
            prev_btn = discord.ui.Button(label="◀", style=discord.ButtonStyle.secondary, row=1)
            prev_btn.callback = self.previous_families_page
            self.add_item(prev_btn)
        
        if self.current_page < self.total_pages:
            next_btn = discord.ui.Button(label="▶", style=discord.ButtonStyle.secondary, row=1)
            next_btn.callback = self.next_families_page
            self.add_item(next_btn)
    
    def get_families(self):
        families = []
        if not os.path.exists(FAMILLE_DIR):
            return families
        
        # Récupérer toutes les familles avec leurs personnages
        for famille_name in os.listdir(FAMILLE_DIR):
            famille_path = os.path.join(FAMILLE_DIR, famille_name)
            if not os.path.isdir(famille_path): continue
            
            personnages_file = os.path.join(famille_path, 'personnages.json')
            if os.path.exists(personnages_file):
                try:
                    with open(personnages_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        personnages = data.get('personnages', [])
                        
                        config_file = os.path.join(famille_path, 'config.json')
                        display_name = famille_name
                        if os.path.exists(config_file):
                            with open(config_file, 'r', encoding='utf-8') as f2:
                                config_data = json.load(f2)
                                display_name = config_data.get('nom', famille_name)
                        
                        # Calculer le score de rareté de la famille
                        rarity_score = self.calculate_family_rarity_score(personnages)
                        
                        families.append({
                            'name': display_name,
                            'value': famille_name,
                            'count': len(personnages),
                            'rarity_score': rarity_score
                        })
                except:
                    continue
        
        # Trier par score de rareté (plus rares en premier)
        families.sort(key=lambda x: x['rarity_score'])
        return families
    
    def calculate_family_rarity_score(self, personnages):
        """Calcule un score de rareté pour une famille"""
        rarity_values = {'Légendaire': 4, 'Epique': 3, 'Rare': 2, 'Commun': 1}
        total_score = 0
        
        for personnage in personnages:
            rarete = personnage.get('rarete', 'Commun')
            total_score += rarity_values.get(rarete, 1)
        
        return total_score / len(personnages) if personnages else 0
    
    async def previous_families_page(self, interaction: discord.Interaction):
        self.current_page -= 1
        await self.update_families_view(interaction)
    
    async def next_families_page(self, interaction: discord.Interaction):
        self.current_page += 1
        await self.update_families_view(interaction)
    
    async def update_families_view(self, interaction: discord.Interaction):
        self._build_view()
        embed = self.create_family_embed(interaction)
        await interaction.response.edit_message(embed=embed, view=self)
    
    async def select_family(self, interaction: discord.Interaction):
        family_value = interaction.data['values'][0]
        personnages = self.get_family_characters(family_value)
        
        if not personnages:
            await interaction.response.send_message("❌ Aucun personnage trouvé dans cette famille.", ephemeral=True)
            return
        
        view = CharacterSelectView(self.card_manager, family_value, personnages)
        embed, files = view.create_character_select_embed(family_value, personnages, interaction)
        
        await interaction.response.edit_message(embed=embed, view=view, attachments=files)
    
    def get_family_characters(self, family_value):
        family_path = os.path.join(FAMILLE_DIR, family_value)
        personnages_file = os.path.join(family_path, 'personnages.json')
        if not os.path.exists(personnages_file): return []
        
        try:
            with open(personnages_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('personnages', [])
        except:
            return []
    
    def create_family_embed(self, ctx_or_interaction=None):
        cartes_emoji = EMOJIS.get('cartes', '📚')
        
        guild = getattr(ctx_or_interaction, 'guild', None)
        user = getattr(ctx_or_interaction, 'author', getattr(ctx_or_interaction, 'user', None))
        bot = getattr(ctx_or_interaction, 'bot', getattr(ctx_or_interaction, 'client', None))
        target_id = guild.id if guild else None

        # Pagination : 15 familles par page
        start_idx = (self.current_page - 1) * self.families_per_page
        end_idx = min(start_idx + self.families_per_page, len(self.families))
        page_families = self.families[start_idx:end_idx]

        family_list = []
        for i, family in enumerate(page_families, start_idx + 1):
            family_list.append(f"**{i}.** {family['name']} • {family['count']} cartes")
        
        if len(self.families) > end_idx:
            family_list.append(f"\n... et {len(self.families) - end_idx} autres familles")
            
        desc = f"**{len(self.families)} familles disponibles**\n\nChoisissez une famille pour explorer la collection :\n\n" + "\n".join(family_list)

        # Créer l'embed avec config_manager (identique à Kayaba Collection)
        if config_manager and ctx_or_interaction:
            embed = config_manager.get_formatted_embed(
                guild=guild, user=user, bot=bot,
                title=f"{cartes_emoji} Kayaba Collection",
                description=desc, target_id=target_id
            )
            # Ajouter l'image du bot en thumbnail
            if bot and bot.user.avatar:
                embed.set_thumbnail(url=bot.user.avatar.url)
            # Ajouter la pagination au footer existant sans écraser le footer de config_manager
            current_footer = embed.footer.text if embed.footer.text else ""
            current_icon = embed.footer.icon_url if embed.footer.icon_url else (bot.user.avatar.url if bot and bot.user.avatar else None)
            
            embed.set_footer(
                text=f"Page {self.current_page}/{self.total_pages} • {current_footer}",
                icon_url=current_icon
            )
        else:
            embed = discord.Embed(
                title=f"{cartes_emoji} Kayaba Collection",
                description=desc,
                color=0x2b2d31
            )
            # Ajouter l'image du bot en thumbnail et footer
            if bot and bot.user.avatar:
                embed.set_thumbnail(url=bot.user.avatar.url)
                embed.set_footer(
                    text=f"Page {self.current_page}/{self.total_pages} • Système Kayaba Collection",
                    icon_url=bot.user.avatar.url
                )
            else:
                embed.set_footer(text=f"Page {self.current_page}/{self.total_pages} • Système Kayaba Collection")
        
        return embed


class CharacterSelectView(discord.ui.View):
    def __init__(self, card_manager, family_value, personnages):
        super().__init__(timeout=300)
        self.card_manager = card_manager
        self.family_value = family_value
        self.personnages = personnages
        self.current_page = 1
        self.characters_per_page = 15
        self.total_pages = max(1, (len(personnages) + self.characters_per_page - 1) // self.characters_per_page)
        self._build_view()
    
    def _build_view(self):
        self.clear_items()
        
        start_idx = (self.current_page - 1) * self.characters_per_page
        end_idx = min(start_idx + self.characters_per_page, len(self.personnages))
        page_personnages = self.personnages[start_idx:end_idx]
        
        # Trier par rareté (plus rares en premier)
        rarity_order = {'Légendaire': 0, 'Epique': 1, 'Rare': 2, 'Commun': 3}
        page_personnages.sort(key=lambda x: rarity_order.get(x.get('rarete', 'Commun'), 3))
        
        character_options = []
        for personnage in page_personnages:
            rarity_emoji = {'Commun': '⚪', 'Rare': '🔵', 'Epique': '🟣', 'Légendaire': '🟡'}
            emoji = rarity_emoji.get(personnage.get('rarete', 'Commun'), '⚪')
            character_options.append(discord.SelectOption(
                label=f"{emoji} {personnage.get('nom', 'Inconnu')}",
                value=personnage.get('id', ''),
                description=f"ID: {personnage.get('id', '')} • {personnage.get('rarete', 'Commun')}"
            ))
        
        character_select = discord.ui.Select(
            placeholder="👤 Choisissez un personnage...",
            options=character_options,
            row=0
        )
        character_select.callback = self.select_character
        self.add_item(character_select)
        
        # Bouton Retour en premier (avec emoji flèche)
        back_btn = discord.ui.Button(label="Retour", emoji="🔙", style=discord.ButtonStyle.primary, row=1)
        back_btn.callback = self.back_to_families
        self.add_item(back_btn)
        
        if self.current_page > 1:
            prev_btn = discord.ui.Button(label="◀", style=discord.ButtonStyle.secondary, row=1)
            prev_btn.callback = self.previous_page
            self.add_item(prev_btn)
        
        if self.current_page < self.total_pages:
            next_btn = discord.ui.Button(label="▶", style=discord.ButtonStyle.secondary, row=1)
            next_btn.callback = self.next_page
            self.add_item(next_btn)

    async def select_character(self, interaction: discord.Interaction):
        character_id = interaction.data['values'][0]
        
        character = next((p for p in self.personnages if p.get('id') == character_id), None)
        if not character:
            await interaction.response.send_message("❌ Personnage non trouvé.", ephemeral=True)
            return
        
        self.clear_items()
        # Bouton Retour Liste des Personnages (avec emoji flèche)
        back_char_btn = discord.ui.Button(label="Retour", emoji="🔙", style=discord.ButtonStyle.primary)
        back_char_btn.callback = self.back_to_character_list
        self.add_item(back_char_btn)

        embed, files = self.create_character_embed(character, interaction)
        await interaction.response.edit_message(embed=embed, view=self, attachments=files)
    
    async def back_to_character_list(self, interaction: discord.Interaction):
        self._build_view()
        embed, files = self.create_character_select_embed(self.family_value, self.personnages, interaction)
        await interaction.response.edit_message(embed=embed, view=self, attachments=files)

    def create_character_embed(self, character, interaction):
        print(f"[DEBUG EMBED] DÉBUT create_character_embed()")
        print(f"[DEBUG EMBED] character reçu: {character}")
        print(f"[DEBUG EMBED] type de character: {type(character)}")
        
        guild = getattr(interaction, 'guild', None)
        user = getattr(interaction, 'user', None)
        bot = getattr(interaction, 'client', None)

        char_name = character.get('nom', 'Inconnu')
        print(f"[DEBUG EMBED] nom extrait: {char_name}")
        
        # Couleur selon la rareté
        rarity_colors = {
            'Commun': 0x95a5a6,      # Gris
            'Rare': 0x3498db,         # Bleu
            'Epique': 0x9b59b6,       # Violet
            'Légendaire': 0xf1c40f    # Or
        }
        embed_color = rarity_colors.get(character.get('rarete', 'Commun'), 0x95a5a6)
        
        # Formatage avec des espaces pour tous les chiffres (sauf IDs)
        def format_number(num):
            return f"{num:,}".replace(',', ' ')
        
        valeur_str = format_number(character.get('valeur', 0))
        exemplaires_str = format_number(character.get('exemplaires', 0))
        exemplaires_restant_str = format_number(character.get('exemplaires_restant', 0))
        
        # Debug pour vérifier les valeurs brutes
        print(f"[DEBUG EMBED] personnage: {character.get('nom', 'Inconnu')}")
        print(f"[DEBUG EMBED] exemplaires_brut: {character.get('exemplaires', 'NON_TROUVE')}")
        print(f"[DEBUG EMBED] exemplaires_restant_brut: {character.get('exemplaires_restant', 'NON_TROUVE')}")
        print(f"[DEBUG EMBED] exemplaires_str: {exemplaires_str}")
        print(f"[DEBUG EMBED] exemplaires_restant_str: {exemplaires_restant_str}")
        
        vitesse_str = format_number(character.get('vitesse', 0))
        precision_str = format_number(character.get('precision', 0))
        vie_str = format_number(character.get('vie', 0))
        puissance_str = format_number(character.get('puissance', 0))

        # Description avec rareté, famille et ID sur une seule ligne (ID entre backticks)
        rarity_emoji = {'Commun': '⚪', 'Rare': '🔵', 'Epique': '🟣', 'Légendaire': '🟡'}
        rarity_emoji_display = rarity_emoji.get(character.get('rarete', 'Commun'), '⚪')
        
        # Formatage du titre dans la description
        cartes_emoji = EMOJIS.get('cartes', '🃏')
        kronos_emoji = EMOJIS.get('kronos', '💰')
        desc = f"**# {cartes_emoji} {char_name}** __{valeur_str} {kronos_emoji}__\n-# *{rarity_emoji_display} {character.get('rarete', 'Commun')} - {self.family_value} - `#{character.get('id', '')}`*\n{cartes_emoji} `{exemplaires_str}` exemplaires dont `{exemplaires_restant_str}` en circulation"
        
        # Ajouter la description du personnage si elle existe (entre ``)
        if character.get('description'):
            desc += f"\n```\n{character.get('description', '')}\n```"

        # Créer l'embed avec config_manager pour avoir le même footer que Kayaba Collection (sans titre)
        if config_manager:
            try:
                embed = config_manager.get_formatted_embed(
                    guild=guild, user=user, bot=bot,
                    title="", description=desc, target_id=guild.id if guild else None
                )
                # Conserver la couleur de rareté
                embed.color = embed_color
            except Exception as e:
                embed = discord.Embed(description=desc, color=embed_color)
                embed.set_footer(text="Système Kayaba Collection")
        else:
            embed = discord.Embed(description=desc, color=embed_color)
            embed.set_footer(text="Système Kayaba Collection")
        
        # Stats en 2 colonnes (avec emojis et valeurs entre ``)
        embed.add_field(name=f"⚡ **Vitesse:** `{vitesse_str}`", value=f"🎯 **Précision:** `{precision_str}%`", inline=True)
        embed.add_field(name=f"❤️ **Vie:** `{vie_str}`", value=f"⚔️ **Puissance:** `{puissance_str}`", inline=True)

        files = []
        
        # Thumbnail : Image de la famille (première image trouvée dans le dossier)
        fam_file, fam_url = self.get_family_image(self.family_value)
        if fam_file:
            files.append(fam_file)
            embed.set_thumbnail(url=fam_url)

        # Image principale : Personnage
        char_file, char_url = self.get_local_file_data(self.family_value, character.get('nom', ''))
        if char_file:
            files.append(char_file)
            embed.set_image(url=char_url)
        elif character.get('image', '').startswith('http'):
            embed.set_image(url=character.get('image'))

        return embed, files
    
    def get_family_image(self, family_value):
        """Récupère la première image trouvée dans le dossier de la famille"""
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
    
    async def previous_page(self, interaction: discord.Interaction):
        self.current_page -= 1
        await self.update_view(interaction)
    
    async def next_page(self, interaction: discord.Interaction):
        self.current_page += 1
        await self.update_view(interaction)
    
    async def back_to_families(self, interaction: discord.Interaction):
        view = FamilySelectView(self.card_manager)
        embed = view.create_family_embed(interaction)
        await interaction.response.edit_message(embed=embed, view=view, attachments=[])
    
    async def update_view(self, interaction: discord.Interaction):
        self._build_view()
        embed, files = self.create_character_select_embed(self.family_value, self.personnages, interaction)
        await interaction.response.edit_message(embed=embed, view=self, attachments=files)
    
    def create_character_select_embed(self, family_value, personnages, interaction):
        cartes_emoji = EMOJIS.get('cartes', '📚')
        
        start_idx = (self.current_page - 1) * self.characters_per_page
        end_idx = min(start_idx + self.characters_per_page, len(personnages))
        page_personnages = personnages[start_idx:end_idx]
        
        # Trier par rareté (plus rares en premier)
        rarity_order = {'Légendaire': 0, 'Epique': 1, 'Rare': 2, 'Commun': 3}
        page_personnages.sort(key=lambda x: rarity_order.get(x.get('rarete', 'Commun'), 3))
        
        character_list = []
        for i, personnage in enumerate(page_personnages, start_idx + 1):
            rarity_emoji = {'Commun': '⚪', 'Rare': '🔵', 'Epique': '🟣', 'Légendaire': '🟡'}
            emoji = rarity_emoji.get(personnage.get('rarete', 'Commun'), '⚪')
            character_list.append(f"**{i}.** {emoji} {personnage.get('nom', 'Inconnu')} (ID: `{personnage.get('id', '')}`)")
        
        desc = f"**{len(personnages)} personnages**\n\nChoisissez un personnage:\n\n" + "\n".join(character_list)
        
        guild = getattr(interaction, 'guild', None)
        user = getattr(interaction, 'user', None)
        bot = getattr(interaction, 'client', None)

        embed = None
        if config_manager:
            embed = config_manager.get_formatted_embed(
                guild=guild, user=user, bot=bot,
                title=f"{cartes_emoji} Famille {family_value}",
                description=desc, target_id=guild.id if guild else None
            )
        else:
            embed = discord.Embed(
                title=f"{cartes_emoji} Famille {family_value}",
                description=desc, color=0x2b2d31
            )
            embed.set_footer(text="Système Kayaba Collection")

        # Footer dynamique avec pages et image du bot
        current_footer = embed.footer.text if embed.footer.text else ""
        current_icon = embed.footer.icon_url if embed.footer.icon_url else (bot.user.avatar.url if bot and bot.user.avatar else None)
        
        embed.set_footer(
            text=f"Page {self.current_page}/{self.total_pages} • {current_footer}",
            icon_url=current_icon
        )

        files = []
        # Thumbnail : Famille
        fam_file, fam_url = self.get_family_image(family_value)
        if fam_file:
            files.append(fam_file)
            embed.set_thumbnail(url=fam_url)

        return embed, files

    def get_local_file_data(self, family_value, character_name=None):
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

# ==========================================
# RECHERCHE GLOBALE ET MODALES
# ==========================================
class CollectionView(discord.ui.View):
    def __init__(self, cards: List[Dict], current_page: int = 1, cards_per_page: int = 20):
        super().__init__(timeout=300)
        self.cards = cards
        self.current_page = current_page
        self.cards_per_page = cards_per_page
        self.total_pages = max(1, (len(cards) + cards_per_page - 1) // cards_per_page)
        self._build_view()
    
    def _build_view(self):
        self.clear_items()
        
        if self.current_page > 1:
            prev_btn = discord.ui.Button(label="◀", style=discord.ButtonStyle.secondary, row=0)
            prev_btn.callback = self.previous_page
            self.add_item(prev_btn)
        
        if self.current_page < self.total_pages:
            next_btn = discord.ui.Button(label="▶", style=discord.ButtonStyle.secondary, row=0)
            next_btn.callback = self.next_page
            self.add_item(next_btn)
        
        search_select = discord.ui.Select(
            placeholder="🔍 Rechercher une carte...",
            options=[
                discord.SelectOption(label="Par ID", value="id", emoji="🆔"),
                discord.SelectOption(label="Par nom", value="name", emoji="📝"),
                discord.SelectOption(label="Par famille", value="famille", emoji="👨‍👩‍👧‍👦"),
                discord.SelectOption(label="Par rareté", value="rarete", emoji="⭐")
            ],
            row=1
        )
        search_select.callback = self.search_cards
        self.add_item(search_select)
    
    async def previous_page(self, interaction: discord.Interaction):
        self.current_page -= 1
        await self.update_view(interaction)
    
    async def next_page(self, interaction: discord.Interaction):
        self.current_page += 1
        await self.update_view(interaction)
    
    async def search_cards(self, interaction: discord.Interaction):
        search_type = interaction.data['values'][0]
        search_modal = SearchModal(search_type)
        await interaction.response.send_modal(search_modal)
    
    async def update_view(self, interaction: discord.Interaction):
        start_idx = (self.current_page - 1) * self.cards_per_page
        end_idx = min(start_idx + self.cards_per_page, len(self.cards))
        page_cards = self.cards[start_idx:end_idx]
        
        embed = self.create_collection_embed(self.cards, interaction)
        
        await interaction.response.edit_message(embed=embed, view=self)
    
    def create_collection_embed(self, cards: List[Dict], interaction=None) -> discord.Embed:
        if not cards:
            return discord.Embed(
                title="📚 Collection Vide",
                description="Aucune carte trouvée dans la base de données.",
                color=discord.Color.red()
            )
        
        cards_sorted = sorted(cards, key=lambda x: x['nom'])
        limited_cards = cards_sorted[:20]
        card_list = []
        for i, card in enumerate(limited_cards, 1):
            rarity_emoji = {'Commun': '⚪', 'Rare': '🔵', 'Epique': '🟣', 'Légendaire': '🟡'}
            emoji = rarity_emoji.get(card['rarete'], '⚪')
            card_text = f"**{i}. {emoji} {card['nom']}** (ID: `{card['id'][:8]}...`)"
            card_list.append(card_text)
        
        if len(cards) > 20:
            card_list.append(f"\n... et {len(cards) - 20} autres résultats")
        
        embed = discord.Embed(
            title="📚 Résultats de Recherche",
            description="\n".join(card_list),
            color=discord.Color.blue()
        )
        
        if config_manager:
            try:
                embed.set_footer(
                    text="📚 Collection • Système Kayaba Collection",
                    icon_url=config_manager.get_embed_icon(interaction.user)
                )
            except Exception:
                embed.set_footer(text="📚 Collection • Système Kayaba Collection")
        else:
            embed.set_footer(text="📚 Collection • Système Kayaba Collection")
        
        return embed


class SearchModal(discord.ui.Modal):
    def __init__(self, search_type: str):
        title = f"Recherche par {search_type}"
        placeholder = {
            "id": "Entrez l'ID de la carte...",
            "name": "Entrez le nom du personnage...",
            "famille": "Entrez le nom de la famille...",
            "rarete": "Entrez la rareté (Commun/Rare/Epique/Légendaire)..."
        }
        
        super().__init__(title=title)
        
        self.search_type = search_type
        self.search_input = discord.ui.TextInput(
            label=f"Recherche par {search_type}",
            placeholder=placeholder.get(search_type, "Entrez votre recherche..."),
            required=True,
            style=discord.TextStyle.short,
            max_length=100
        )
        self.add_item(self.search_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        query = self.search_input.value.strip()
        
        if self.search_type == "id":
            card_manager = CardManager()
            card = card_manager.get_card_by_id(query)
            if card:
                await self.show_card_result(interaction, card)
            else:
                await interaction.response.send_message(f"❌ Aucune carte trouvée avec l'ID `{query}`", ephemeral=True)
        
        elif self.search_type == "name":
            card_manager = CardManager()
            cards = [card for card in card_manager.get_all_cards() if query.lower() in card['nom'].lower()]
            if cards:
                await self.show_search_results(interaction, cards, f"Résultats pour '{query}'")
            else:
                await interaction.response.send_message(f"❌ Aucune carte trouvée avec le nom '{query}'", ephemeral=True)
        
        elif self.search_type == "famille":
            card_manager = CardManager()
            cards = [card for card in card_manager.get_all_cards() if query.lower() in card['famille'].lower()]
            if cards:
                await self.show_search_results(interaction, cards, f"Famille '{query}'")
            else:
                await interaction.response.send_message(f"❌ Aucune carte trouvée dans la famille '{query}'", ephemeral=True)
        
        elif self.search_type == "rarete":
            valid_rarities = ["commun", "rare", "epique", "legendaire"]
            if query.lower() not in valid_rarities:
                await interaction.response.send_message("❌ Rareté invalide. Utilisez: Commun, Rare, Epique ou Légendaire", ephemeral=True)
                return
            
            card_manager = CardManager()
            cards = [card for card in card_manager.get_all_cards() if card['rarete'].lower() == query.lower()]
            if cards:
                await self.show_search_results(interaction, cards, f"Cartes {query.title()}")
            else:
                await interaction.response.send_message(f"❌ Aucune carte trouvée avec la rareté '{query}'", ephemeral=True)
    
    async def show_card_result(self, interaction, card):
        # Créer une vue avec le bouton récupérer
        view = CardRecoverView(card, self)
        
        # Créer l'embed du personnage
        character_select_view = CharacterSelectView(CardManager(), card['famille'], [card])
        embed, files = character_select_view.create_character_embed(card, interaction)
        
        # Envoyer le message principal
        await interaction.response.send_message(embed=embed, view=view, files=files, ephemeral=True)
        
        # Envoyer une notification MP si activé
        if MPManager:
            try:
                plus_emoji = EMOJIS.get('plus', '➕')
                message = f"{plus_emoji} Vous avez consulté **{card['nom']}** via la collection. Cette carte appartient à la famille **{card['famille']}**."
                bot = getattr(interaction, 'client', None) or getattr(interaction, 'bot', None)
                if bot:
                    await MPManager.send_mp_if_enabled(bot, interaction.user.id, message)
                    print(f"[COLLECTION] Notification MP envoyée à l'utilisateur {interaction.user.id} pour la consultation de {card['nom']}")
            except Exception as e:
                print(f"[COLLECTION] Erreur lors de l'envoi de la notification MP: {e}")

class CardRecoverView(discord.ui.View):
    def __init__(self, card, collection_cog):
        super().__init__(timeout=300)
        self.card = card
        self.collection_cog = collection_cog
        self.card_manager = CardManager()
        
        # Vérifier s'il reste des exemplaires
        exemplaires_restant = card.get('exemplaires_restant', 0)
        if exemplaires_restant > 0:
            recover_btn = discord.ui.Button(label="🎁 Récupérer", style=discord.ButtonStyle.success, row=0)
            recover_btn.callback = self.recover_card
            self.add_item(recover_btn)
        else:
            # Bouton désactivé si plus d'exemplaires
            disabled_btn = discord.ui.Button(label="❌ Indisponible", style=discord.ButtonStyle.secondary, row=0, disabled=True)
            self.add_item(disabled_btn)
    
    async def recover_card(self, interaction: discord.Interaction):
        exemplaires_restant = self.card.get('exemplaires_restant', 0)
        
        if exemplaires_restant <= 0:
            await interaction.response.send_message("❌ Cette carte n'est plus disponible.", ephemeral=True)
            return
        
        # Mettre à jour exemplaires_restant (-1)
        new_value = exemplaires_restant - 1
        success = self.card_manager.update_exemplaires_restant(self.card['famille'], self.card['nom'], new_value)
        
        if success:
            # Envoyer la notification MP
            if MPManager:
                try:
                    plus_emoji = EMOJIS.get('plus', '➕')
                    message = f"{plus_emoji} Vous avez récupéré **{self.card['nom']}** !\n\n"
                    message += f"📊 **Détails de la carte :**\n"
                    message += f"• **Nom :** {self.card['nom']}\n"
                    message += f"• **Famille :** {self.card['famille']}\n"
                    message += f"• **Rareté :** {self.card['rarete']}\n"
                    message += f"• **Valeur :** {self.card.get('valeur', 0):,} 💰\n"
                    message += f"• **ID :** {self.card.get('id', '')}\n"
                    message += f"\n🎉 **Plus que {new_value} exemplaires disponibles !**"
                    
                    bot = getattr(interaction, 'client', None) or getattr(interaction, 'bot', None)
                    if bot:
                        await MPManager.send_mp_if_enabled(bot, interaction.user.id, message)
                        print(f"[COLLECTION] MP récupération envoyé pour {self.card['nom']}")
                except Exception as e:
                    print(f"[COLLECTION] Erreur MP récupération: {e}")
            
            # Mettre à jour la vue (désactiver le bouton)
            self.clear_items()
            disabled_btn = discord.ui.Button(label="✅ Récupéré", style=discord.ButtonStyle.secondary, row=0, disabled=True)
            self.add_item(disabled_btn)
            
            # Mettre à jour l'embed pour montrer la nouvelle valeur
            updated_card = self.card.copy()
            updated_card['exemplaires_restant'] = new_value
            
            character_select_view = CharacterSelectView(CardManager(), self.card['famille'], [updated_card])
            embed, files = character_select_view.create_character_embed(updated_card, interaction)
            
            # Naviguer vers la page suivante ou précédente
            await interaction.response.edit_message(embed=embed, view=self, attachments=files if files else [])
            
            # Naviguer automatiquement
            await self.navigate_to_next_page(interaction)
        else:
            await interaction.response.send_message("❌ Erreur lors de la mise à jour.", ephemeral=True)
    
    async def navigate_to_next_page(self, interaction):
        """Navigue vers la page suivante ou précédente automatiquement"""
        try:
            # Attendre un peu pour que l'utilisateur voie le message
            await asyncio.sleep(1)
            
            # Simuler une navigation vers la "page suivante" 
            # (cette logique dépend de comment est implémentée la pagination)
            await interaction.followup.send("📄 Navigation automatique vers la page suivante...", ephemeral=True)
        except:
            pass
    
    async def show_search_results(self, interaction, cards, title):
        view = CollectionView(cards)
        embed = view.create_collection_embed(cards, interaction)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
        
        # Envoyer une notification MP si activé
        if MPManager and cards:
            try:
                plus_emoji = EMOJIS.get('plus', '➕')
                card_names = [f"**{card['nom']}**" for card in cards[:3]]  # Limiter à 3 cartes pour éviter les messages trop longs
                if len(cards) > 3:
                    card_names.append(f"...et {len(cards) - 3} autres")
                message = f"{plus_emoji} Vous avez recherché **{title}** dans la collection. Cartes trouvées : {', '.join(card_names)}."
                bot = getattr(interaction, 'client', None) or getattr(interaction, 'bot', None)
                if bot:
                    await MPManager.send_mp_if_enabled(bot, interaction.user.id, message)
                    print(f"[COLLECTION] Notification MP envoyée à l'utilisateur {interaction.user.id} pour la recherche '{title}'")
            except Exception as e:
                print(f"[COLLECTION] Erreur lors de l'envoi de la notification MP de recherche: {e}")

# ==========================================
# COMMANDE COLLECTION
# ==========================================
class Collection(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.card_manager = CardManager()
    
    @commands.hybrid_command(name="collection", description="Consultez la collection de cartes")
    async def collection_command(self, ctx: commands.Context, *, id: str = None, personnage: str = None):
        """Affiche la collection de cartes disponibles"""
        await ctx.defer()
        
        if id:
            card = self.card_manager.get_card_by_id(id)
            if card:
                # Créer une vue factice et appeler la méthode de recherche
                modal = SearchModal("id")
                await modal.show_card_result(ctx, card)
            else:
                return await ctx.send(f"❌ Aucune carte trouvée avec l'ID `{id}`")
        
        elif personnage:
            cards = [card for card in self.card_manager.get_all_cards() if personnage.lower() in card['nom'].lower()]
            if cards:
                modal = SearchModal("name")
                await modal.show_search_results(ctx, cards, f"Résultats pour '{personnage}'")
            else:
                return await ctx.send(f"❌ Aucune carte trouvée avec le nom '{personnage}'")
        
        else:
            view = FamilySelectView(self.card_manager)
            embed = view.create_family_embed(ctx)
            
            await ctx.send(embed=embed, view=view)

# ==========================================
# SETUP
# ==========================================
async def setup(bot):
    await bot.add_cog(Collection(bot))
