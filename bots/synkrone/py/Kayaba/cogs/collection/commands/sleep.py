import discord
from discord.ext import commands
import json
import os
import time
from typing import List
from datetime import datetime, timedelta

# ==========================================
# CONFIGURATION & CHEMINS
# ==========================================
BASE_DIR = os.path.dirname(__file__)

# ==========================================
# CONFIGURATION GARDERIE
# ==========================================
BASE_CONFIG = {
    'max_slots': 2,
    'max_farm_time': 480,  # 8h en minutes
    'price_multiplier': 0.005,  # 1 000 000 valeur = 5000 cols/min
    'xp_multiplier': 0.001   # 1 000 000 valeur = 1000 xp/min
}

PREMIUM_CONFIG = {
    'max_slots': 3,
    'max_farm_time': 720,  # 12h en minutes
    'price_multiplier': 0.005,
    'xp_multiplier': 0.001
}

DATA_DEV_DIR = os.path.normpath(os.path.join(BASE_DIR, '..', 'data', 'dev'))
FAMILLE_DIR = os.path.join(DATA_DEV_DIR, 'famille')
USER_DATA_PATH = os.path.normpath(os.path.join(BASE_DIR, '..', 'data', 'interserver'))
PREMIUM_PATH = os.path.normpath(os.path.join(BASE_DIR, '..', 'data', 'premium.json'))

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

def format_number(num):
    """Formatage des nombres avec espaces (1000 -> 1 000)"""
    try:
        return f"{num:,}".replace(',', ' ')
    except:
        return "0"

# ==========================================
# MANAGER DE LA GARDERIE
# ==========================================
class SleepManager:
    def __init__(self):
        self.user_data_path = USER_DATA_PATH

    def is_premium(self, user_id: int) -> bool:
        """Vérifie si l'utilisateur est premium via premium.json"""
        if not os.path.exists(PREMIUM_PATH):
            return False
        
        try:
            with open(PREMIUM_PATH, 'r', encoding='utf-8') as f:
                premium_data = json.load(f)
                premium_users = premium_data.get('premium_users', [])
                return user_id in premium_users
        except Exception as e:
            print(f"\033[91m[DEBUG] Erreur vérification premium sleep: {e}\033[0m")
            return False

    def get_max_slots(self, user_id: int) -> int:
        return 3 if self.is_premium(user_id) else 2

    def get_max_farm_time(self, user_id: int) -> int:
        # Retourne la limite de farm en minutes (12h = 720, 8h = 480)
        return 720 if self.is_premium(user_id) else 480

    def get_user_data(self, user_id: int):
        if not self.user_data_path: 
            return None
        user_file = os.path.join(self.user_data_path, f"{user_id}.json")
        if not os.path.exists(user_file): 
            return None
        
        try:
            with open(user_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return None

    def save_user_data(self, user_id: int, data: dict):
        if not self.user_data_path: 
            return False
        user_file = os.path.join(self.user_data_path, f"{user_id}.json")
        os.makedirs(os.path.dirname(user_file), exist_ok=True)
        try:
            with open(user_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            return True
        except:
            return False

    def calculate_pending_rewards(self, slot: dict, user_id: int):
        now = int(time.time())
        last_claim = slot.get('last_claim', now)
        valeur = slot.get('valeur', 0)
        
        minutes_elapsed = (now - last_claim) // 60
        max_minutes = self.get_max_farm_time(user_id)
        
        farm_minutes = min(minutes_elapsed, max_minutes)
        
        if farm_minutes <= 0:
            return 0, 0, 0
            
        # 1 000 000 valeur = 5000 cols/min -> multiplier par 0.005
        # 1 000 000 valeur = 1000 xp/min -> multiplier par 0.001
        col_reward = int(valeur * 0.005 * farm_minutes)
        xp_reward = int(valeur * 0.001 * farm_minutes)
        
        return col_reward, xp_reward, farm_minutes

    def claim_all_rewards(self, user_id: int):
        data = self.get_user_data(user_id)
        if not data or 'sleep_slots' not in data or not data['sleep_slots']:
            return 0, 0
            
        total_col = 0
        total_xp = 0
        now = int(time.time())
        
        for slot in data['sleep_slots']:
            col, xp, mins = self.calculate_pending_rewards(slot, user_id)
            total_col += col
            total_xp += xp
            slot['last_claim'] = now  # Reset du timer
            
        data['col'] = data.get('col', 0) + total_col
        data['xp'] = data.get('xp', 0) + total_xp
        
        self.save_user_data(user_id, data)
        return total_col, total_xp

    def store_character(self, user_id: int, card: dict):
        data = self.get_user_data(user_id)
        if not data: return False
        
        if 'sleep_slots' not in data:
            data['sleep_slots'] = []
            
        if len(data['sleep_slots']) >= self.get_max_slots(user_id):
            return False
            
        now = int(time.time())
        data['sleep_slots'].append({
            'id': card['id'],
            'nom': card['nom'],
            'rarete': card.get('rarete', 'Commun'),
            'valeur': card.get('valeur', 0),
            'start_time': now,
            'last_claim': now
        })
        
        return self.save_user_data(user_id, data)

    def remove_character(self, user_id: int, slot_index: int):
        data = self.get_user_data(user_id)
        if not data or 'sleep_slots' not in data: return False
        
        if 0 <= slot_index < len(data['sleep_slots']):
            data['sleep_slots'].pop(slot_index)
            return self.save_user_data(user_id, data)
        return False

    def get_user_families(self, user_id: int):
        # MÊME LOGIQUE QUE SELL.PY
        data = self.get_user_data(user_id)
        collection = data.get('collection', {}) if data else {}
        sleep_slots = data.get('sleep_slots', []) if data else []
        
        # Soustraire les cartes déjà en train de dormir pour éviter les doublons
        sleeping_counts = {}
        for s in sleep_slots:
            sleeping_counts[s['id']] = sleeping_counts.get(s['id'], 0) + 1

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
                    
                    user_cards = []
                    for p in fam_data.get('personnages', []):
                        cid = p.get('id')
                        owned = collection.get(cid, 0)
                        sleeping = sleeping_counts.get(cid, 0)
                        dispo = owned - sleeping
                        
                        if dispo > 0:
                            p['quantity_dispo'] = dispo
                            user_cards.append(p)
                    
                    if user_cards:
                        config_file = os.path.join(famille_path, 'config.json')
                        display_name = famille_name
                        if os.path.exists(config_file):
                            with open(config_file, 'r', encoding='utf-8') as f2:
                                config_data = json.load(f2)
                                display_name = config_data.get('nom', famille_name)
                        
                        user_families[famille_name] = {
                            'display_name': display_name,
                            'personnages': user_cards
                        }
            except:
                continue
        return user_families

# ==========================================
# VUES INTERACTIVES
# ==========================================
class SleepMainView(discord.ui.View):
    def __init__(self, ctx, sleep_manager: SleepManager):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.manager = sleep_manager
        self._build_view()

    def _build_view(self):
        self.clear_items()
        
        user_data = self.manager.get_user_data(self.ctx.author.id)
        slots = user_data.get('sleep_slots', []) if user_data else []
        max_slots = self.manager.get_max_slots(self.ctx.author.id)
        is_full = len(slots) >= max_slots
        
        btn_claim = discord.ui.Button(label="Récupérer", emoji="🎁", style=discord.ButtonStyle.success)
        btn_claim.callback = self.claim_rewards
        self.add_item(btn_claim)

        # Ajouter le bouton "Stocker" seulement si la garderie n'est pas pleine
        if not is_full:
            btn_store = discord.ui.Button(label="Stocker", emoji="📥", style=discord.ButtonStyle.primary)
            btn_store.callback = self.store_character
            self.add_item(btn_store)
        
        # Ajouter le sélecteur "Réveiller" seulement s'il y a des personnages
        if slots:
            options = []
            for i, slot in enumerate(slots):
                rarity_emoji = {"Légendaire": "🟡", "Epique": "🟣", "Rare": "🔵", "Commun": "🟢"}.get(slot.get('rarete', 'Commun'), "🟢")
                options.append(discord.SelectOption(
                    label=f"{rarity_emoji} {slot['nom']}",
                    value=str(i),
                    description=f"Retirer ce personnage de la garderie"
                ))
                
            sel = discord.ui.Select(placeholder="Choisissez qui réveiller...", options=options, row=1)
            sel.callback = self.remove_character_direct
            self.add_item(sel)

    def create_embed(self):
        user_data = self.manager.get_user_data(self.ctx.author.id)
        slots = user_data.get('sleep_slots', []) if user_data else []
        is_premium = self.manager.is_premium(self.ctx.author.id)
        max_slots = self.manager.get_max_slots(self.ctx.author.id)
        max_time = self.manager.get_max_farm_time(self.ctx.author.id)
        
        guild = getattr(self.ctx, 'guild', None)
        user = getattr(self.ctx, 'user', None)
        bot = getattr(self.ctx, 'bot', None)
        
        desc = f"Bienvenue dans la Garderie !\nVos personnages se reposent et génèrent des récompenses avec le temps.\n\n"
        desc += f"🌟 **Statut :** {'Premium (12h max)' if is_premium else 'Base (8h max)'}\n"
        desc += f"📦 **Places :** {len(slots)} / {max_slots}\n\n"

        if not slots:
            desc += "> *Aucun personnage en garderie actuellement.*\n> *Cliquez sur **Stocker** pour commencer.*"
        else:
            for i, slot in enumerate(slots):
                col, xp, mins = self.manager.calculate_pending_rewards(slot, self.ctx.author.id)
                rarity_emoji = {"Légendaire": "🟡", "Epique": "🟣", "Rare": "🔵", "Commun": "🟢"}.get(slot.get('rarete', 'Commun'), "🟢")
                
                desc += f"**{i+1}.** {rarity_emoji} **{slot['nom']}**\n"
                desc += f"└ ⏳ `{mins} / {max_time} min` • `+{format_number(col)}` <:col:1482462727468486738> • 🌟 `+{format_number(xp)} XP`\n\n"

        # Utiliser config_manager pour l'embed (comme devstats.py)
        if config_manager:
            try:
                embed = config_manager.get_formatted_embed(
                    guild, self.ctx.author, self.ctx.bot,
                    title="⛺ Garderie des Personnages", 
                    description=desc,
                    target_id=guild.id if guild else None
                )
                # Ajouter le thumbnail de l'utilisateur
                if hasattr(self.ctx.author, 'display_avatar') and self.ctx.author.display_avatar:
                    embed.set_thumbnail(url=self.ctx.author.display_avatar.url)
            except Exception as e:
                print(f"\033[91m[DEBUG] Erreur config_manager sleep: {e}\033[0m")
                embed = discord.Embed(title="⛺ Garderie des Personnages", description=desc, color=0x2b2d31)
                if hasattr(self.ctx.author, 'display_avatar') and self.ctx.author.display_avatar:
                    embed.set_thumbnail(url=self.ctx.author.display_avatar.url)
                embed.set_footer(text="Système Kayaba Collection")
        else:
            embed = discord.Embed(title="⛺ Garderie des Personnages", description=desc, color=0x2b2d31)
            if hasattr(self.ctx.author, 'display_avatar') and self.ctx.author.display_avatar:
                embed.set_thumbnail(url=self.ctx.author.display_avatar.url)
            embed.set_footer(text="Système Kayaba Collection")
            
        return embed

    async def claim_rewards(self, interaction: discord.Interaction):
        col, xp = self.manager.claim_all_rewards(self.ctx.author.id)
        if col == 0 and xp == 0:
            await interaction.response.send_message("❌ Aucune récompense à récupérer pour le moment.", ephemeral=True)
            return
        
        # Message MP pour la récompense
        try:
            await self.ctx.author.send(
                f"**[SLEEP]** Votre session vous a rapporté `+{format_number(col)}` <:col:1482462727468486738> & `{format_number(xp)}` d'exp."
            )
        except: pass
            
        await interaction.response.send_message(f"✅ **Récompenses récupérées !**\n`+{format_number(col)}` <:col:1482462727468486738>\n🌟 `+{format_number(xp)} XP`", ephemeral=True)
        self._build_view()
        await interaction.message.edit(embed=self.create_embed(), view=self)

    async def store_character(self, interaction: discord.Interaction):
        data = self.manager.get_user_data(self.ctx.author.id)
        slots = data.get('sleep_slots', []) if data else []
        if len(slots) >= self.manager.get_max_slots(self.ctx.author.id):
            await interaction.response.send_message("❌ Vous n'avez plus de place disponible dans la garderie.", ephemeral=True)
            return
            
        view = SleepFamilySelectView(self.ctx, self.manager)
        await interaction.response.edit_message(embed=view.create_embed(), view=view)

    async def remove_character_direct(self, interaction: discord.Interaction):
        """Retire directement un personnage depuis le sélecteur principal"""
        slot_idx = int(interaction.data['values'][0])
        user_data = self.manager.get_user_data(self.ctx.author.id)
        slots = user_data.get('sleep_slots', []) if user_data else []
        
        if 0 <= slot_idx < len(slots):
            slot = slots[slot_idx]
            
            # Récolter individuellement avant de supprimer
            col, xp, mins = self.manager.calculate_pending_rewards(slot, self.ctx.author.id)
            
            if col > 0 or xp > 0:
                data = self.manager.get_user_data(self.ctx.author.id)
                data['col'] = data.get('col', 0) + col
                data['xp'] = data.get('xp', 0) + xp
                self.manager.save_user_data(self.ctx.author.id, data)
            
            success = self.manager.remove_character(self.ctx.author.id, slot_idx)
            
            if success:
                # Message MP pour le retrait
                try:
                    if col > 0 or xp > 0:
                        await self.ctx.author.send(
                            f"**[SLEEP]** Vous avez retiré **{slot['nom']}** à la garderie. Il vous a rapporté `+{format_number(col)}` <:col:1482462727468486738> & `{format_number(xp)}` d'exp."
                        )
                    else:
                        await self.ctx.author.send(
                            f"**[SLEEP]** Vous avez retiré **{slot['nom']}** à la garderie."
                        )
                except: pass
                
                msg = f"✅ **{slot['nom']}** a été retiré de la garderie !"
                if col > 0 or xp > 0:
                    msg += f"\n`+{format_number(col)}` <:col:1482462727468486738> et 🌟 `+{format_number(xp)} XP` ont été récupérés avant son départ."
                await interaction.response.send_message(msg, ephemeral=True)
                
                # Mettre à jour la vue principale
                self._build_view()
                await interaction.message.edit(embed=self.create_embed(), view=self)

    async def remove_character(self, interaction: discord.Interaction):
        """Fonction conservée pour compatibilité mais non utilisée"""
        data = self.manager.get_user_data(self.ctx.author.id)
        slots = data.get('sleep_slots', []) if data else []
        if not slots:
            await interaction.response.send_message("❌ Vous n'avez aucun personnage en garderie.", ephemeral=True)
            return

        view = SleepRemoveView(self.ctx, self.manager, slots)
        await interaction.response.edit_message(embed=view.create_embed(), view=view)


class SleepFamilySelectView(discord.ui.View):
    def __init__(self, ctx, manager: SleepManager):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.manager = manager
        self.current_page = 1
        self.items_per_page = 25
        self.families = list(self.manager.get_user_families(self.ctx.author.id).items())
        self._build_view()

    def _build_view(self):
        self.clear_items()
        
        start_idx = (self.current_page - 1) * self.items_per_page
        end_idx = start_idx + self.items_per_page
        page_families = self.families[start_idx:end_idx]
        
        options = []
        for fam_name, fam_data in page_families:
            options.append(discord.SelectOption(
                label=fam_data['display_name'],
                value=fam_name,
                description=f"{len(fam_data['personnages'])} cartes disponibles"
            ))
            
        if options:
            sel = discord.ui.Select(placeholder="Sélectionnez une famille...", options=options, row=0)
            sel.callback = self.select_family
            self.add_item(sel)

        if self.current_page > 1:
            btn = discord.ui.Button(label="◀", style=discord.ButtonStyle.secondary, row=1)
            btn.callback = self.prev_page
            self.add_item(btn)
            
        if len(self.families) > self.current_page * self.items_per_page:
            btn = discord.ui.Button(label="▶", style=discord.ButtonStyle.secondary, row=1)
            btn.callback = self.next_page
            self.add_item(btn)

        back = discord.ui.Button(label="Retour à la garderie", emoji="🔙", style=discord.ButtonStyle.danger, row=2)
        back.callback = self.go_back
        self.add_item(back)

    def create_embed(self):
        guild = getattr(self.ctx, 'guild', None)
        user = getattr(self.ctx, 'author', getattr(self.ctx, 'user', None))
        bot = getattr(self.ctx, 'bot', getattr(self.ctx, 'client', None))
        
        # Utiliser config_manager pour l'embed
        if config_manager:
            try:
                embed = config_manager.get_formatted_embed(
                    guild, user, bot,
                    title="📥 Garderie - Choix de la famille",
                    description="Sélectionnez la famille du personnage que vous souhaitez envoyer se reposer.",
                    target_id=guild.id if guild else None
                )
                if not self.families:
                    embed.add_field(name="Vide", value="Vous n'avez aucune carte disponible à stocker.")
            except Exception as e:
                print(f"\033[91m[DEBUG] Erreur config_manager sleep: {e}\033[0m")
                embed = discord.Embed(
                    title="📥 Garderie - Choix de la famille",
                    description="Sélectionnez la famille du personnage que vous souhaitez envoyer se reposer.",
                    color=0x2b2d31
                )
                if not self.families:
                    embed.add_field(name="Vide", value="Vous n'avez aucune carte disponible à stocker.")
                embed.set_footer(text="Système Kayaba Collection")
        else:
            embed = discord.Embed(
                title="📥 Garderie - Choix de la famille",
                description="Sélectionnez la famille du personnage que vous souhaitez envoyer se reposer.",
                color=0x2b2d31
            )
            if not self.families:
                embed.add_field(name="Vide", value="Vous n'avez aucune carte disponible à stocker.")
            embed.set_footer(text="Système Kayaba Collection")
        return embed

    async def select_family(self, interaction: discord.Interaction):
        fam_name = interaction.data['values'][0]
        fam_data = dict(self.families).get(fam_name)
        
        view = SleepCardSelectView(self.ctx, self.manager, fam_name, fam_data['personnages'])
        await interaction.response.edit_message(embed=view.create_embed(), view=view)

    async def prev_page(self, interaction: discord.Interaction):
        self.current_page -= 1
        self._build_view()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page += 1
        self._build_view()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def go_back(self, interaction: discord.Interaction):
        view = SleepMainView(self.ctx, self.manager)
        await interaction.response.edit_message(embed=view.create_embed(), view=view)


class SleepCardSelectView(discord.ui.View):
    def __init__(self, ctx, manager: SleepManager, fam_name: str, cards: list):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.manager = manager
        self.fam_name = fam_name
        self.cards = cards
        self.current_page = 1
        self.items_per_page = 25
        self._build_view()

    def _build_view(self):
        self.clear_items()
        
        start_idx = (self.current_page - 1) * self.items_per_page
        end_idx = start_idx + self.items_per_page
        page_cards = self.cards[start_idx:end_idx]
        
        options = []
        for c in page_cards:
            valeur = c.get('valeur', 0)
            options.append(discord.SelectOption(
                label=f"{c['nom']}",
                value=c['id'],
                description=f"Gain: {int(valeur*0.005)} Col/m | {int(valeur*0.001)} XP/m"
            ))
            
        if options:
            sel = discord.ui.Select(placeholder="Choisissez un personnage...", options=options, row=0)
            sel.callback = self.select_card
            self.add_item(sel)

        if self.current_page > 1:
            btn = discord.ui.Button(label="◀", style=discord.ButtonStyle.secondary, row=1)
            btn.callback = self.prev_page
            self.add_item(btn)
            
        if len(self.cards) > self.current_page * self.items_per_page:
            btn = discord.ui.Button(label="▶", style=discord.ButtonStyle.secondary, row=1)
            btn.callback = self.next_page
            self.add_item(btn)

        back = discord.ui.Button(label="Retour", emoji="🔙", style=discord.ButtonStyle.danger, row=2)
        back.callback = self.go_back
        self.add_item(back)

    def create_embed(self):
        guild = getattr(self.ctx, 'guild', None)
        user = getattr(self.ctx, 'author', getattr(self.ctx, 'user', None))
        bot = getattr(self.ctx, 'bot', getattr(self.ctx, 'client', None))
        
        # Utiliser config_manager pour l'embed (comme devstats.py)
        if config_manager:
            try:
                embed = config_manager.get_formatted_embed(
                    guild, self.ctx.author, self.ctx.bot,
                    title=f"📥 Garderie - Famille {self.fam_name}",
                    description="Sélectionnez le personnage que vous souhaitez envoyer à la garderie.",
                    target_id=guild.id if guild else None
                )
            except Exception as e:
                print(f"\033[91m[DEBUG] Erreur config_manager sleep: {e}\033[0m")
                embed = discord.Embed(
                    title=f"📥 Garderie - Famille {self.fam_name}",
                    description="Sélectionnez le personnage que vous souhaitez envoyer à la garderie.",
                    color=0x2b2d31
                )
                embed.set_footer(text="Système Kayaba Collection")
        else:
            embed = discord.Embed(
                title=f"📥 Garderie - Famille {self.fam_name}",
                description="Sélectionnez le personnage que vous souhaitez envoyer à la garderie.",
                color=0x2b2d31
            )
            embed.set_footer(text="Système Kayaba Collection")
        return embed

    async def select_card(self, interaction: discord.Interaction):
        card_id = interaction.data['values'][0]
        card = next((c for c in self.cards if c['id'] == card_id), None)
        
        if card:
            success = self.manager.store_character(self.ctx.author.id, card)
            if success:
                # Message MP pour le stockage
                try:
                    await self.ctx.author.send(
                        f"**[SLEEP]** Vous avez stocké **{card['nom']}** à la garderie."
                    )
                except: pass
                await interaction.response.send_message(f"✅ **{card['nom']}** se repose maintenant à la garderie !", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Erreur lors de l'ajout (garderie pleine ?).", ephemeral=True)
                
        view = SleepMainView(self.ctx, self.manager)
        await interaction.message.edit(embed=view.create_embed(), view=view)

    async def prev_page(self, interaction: discord.Interaction):
        self.current_page -= 1
        self._build_view()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page += 1
        self._build_view()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def go_back(self, interaction: discord.Interaction):
        view = SleepFamilySelectView(self.ctx, self.manager)
        await interaction.response.edit_message(embed=view.create_embed(), view=view)


class SleepRemoveView(discord.ui.View):
    def __init__(self, ctx, manager: SleepManager, slots: list):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.manager = manager
        self.slots = slots
        self._build_view()

    def _build_view(self):
        self.clear_items()
        
        options = []
        for i, slot in enumerate(self.slots):
            options.append(discord.SelectOption(
                label=f"{slot['nom']}",
                value=str(i),
                description=f"Retirer ce personnage de la garderie."
            ))
            
        sel = discord.ui.Select(placeholder="Choisissez qui réveiller...", options=options, row=0)
        sel.callback = self.remove_slot
        self.add_item(sel)

        back = discord.ui.Button(label="Retour", emoji="🔙", style=discord.ButtonStyle.danger, row=1)
        back.callback = self.go_back
        self.add_item(back)

    def create_embed(self):
        guild = getattr(self.ctx, 'guild', None)
        user = getattr(self.ctx, 'author', getattr(self.ctx, 'user', None))
        bot = getattr(self.ctx, 'bot', getattr(self.ctx, 'client', None))
        
        # Utiliser config_manager pour l'embed (comme devstats.py)
        if config_manager:
            try:
                embed = config_manager.get_formatted_embed(
                    guild, self.ctx.author, self.ctx.bot,
                    title="📤 Garderie - Retirer",
                    description="⚠️ **Attention :** Retirer un personnage récoltera automatiquement ses récompenses en attente et libérera l'emplacement.",
                    target_id=guild.id if guild else None
                )
            except Exception as e:
                print(f"\033[91m[DEBUG] Erreur config_manager sleep: {e}\033[0m")
                embed = discord.Embed(
                    title="📤 Garderie - Retirer",
                    description="⚠️ **Attention :** Retirer un personnage récoltera automatiquement ses récompenses en attente et libérera l'emplacement.",
                    color=0x2b2d31
                )
                embed.set_footer(text="Système Kayaba Collection")
        else:
            embed = discord.Embed(
                title="📤 Garderie - Retirer",
                description="⚠️ **Attention :** Retirer un personnage récoltera automatiquement ses récompenses en attente et libérera l'emplacement.",
                color=0x2b2d31
            )
            embed.set_footer(text="Système Kayaba Collection")
        return embed

    async def remove_slot(self, interaction: discord.Interaction):
        slot_idx = int(interaction.data['values'][0])
        slot = self.slots[slot_idx]
        
        # Récolter individuellement avant de supprimer
        col, xp, mins = self.manager.calculate_pending_rewards(slot, self.ctx.author.id)
        
        if col > 0 or xp > 0:
            data = self.manager.get_user_data(self.ctx.author.id)
            data['col'] = data.get('col', 0) + col
            data['xp'] = data.get('xp', 0) + xp
            self.manager.save_user_data(self.ctx.author.id, data)
        
        success = self.manager.remove_character(self.ctx.author.id, slot_idx)
        
        if success:
            # Message MP pour le retrait
            try:
                if col > 0 or xp > 0:
                    await self.ctx.author.send(
                        f"**[SLEEP]** Vous avez retiré **{slot['nom']}** à la garderie. Il vous a rapporté `+{format_number(col)}` <:col:1482462727468486738> & `{format_number(xp)}` d'exp."
                    )
                else:
                    await self.ctx.author.send(
                        f"**[SLEEP]** Vous avez retiré **{slot['nom']}** à la garderie."
                    )
            except: pass
            
            msg = f"✅ **{slot['nom']}** a été retiré de la garderie !"
            if col > 0 or xp > 0:
                msg += f"\n`+{format_number(col)}` <:col:1482462727468486738> et 🌟 `+{format_number(xp)} XP` ont été récupérés avant son départ."
            await interaction.response.send_message(msg, ephemeral=True)
            
        view = SleepMainView(self.ctx, self.manager)
        await interaction.message.edit(embed=view.create_embed(), view=view)

    async def go_back(self, interaction: discord.Interaction):
        view = SleepMainView(self.ctx, self.manager)
        await interaction.response.edit_message(embed=view.create_embed(), view=view)


# ==========================================
# COG PRINCIPAL
# ==========================================
class Sleep(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.manager = SleepManager()

    @commands.hybrid_command(name="sleep", description="Gérez votre garderie pour gagner de l'XP et des Col passifs")
    async def sleep_cmd(self, ctx: commands.Context):
        await ctx.defer()
        
        try:
            view = SleepMainView(ctx, self.manager)
            embed = view.create_embed()
            await ctx.send(embed=embed, view=view)
        except Exception as e:
            print(f"[SLEEP] ERREUR: {e}")
            await ctx.send("❌ Une erreur est survenue lors de l'ouverture de la garderie.")


async def setup(bot):
    await bot.add_cog(Sleep(bot))