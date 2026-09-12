import discord
from discord.ext import commands
from discord.ui import Button, View, Select
import json
import os
import random
import asyncio
from datetime import datetime
import typing

# Import des modules de collection
try:
    from cogs.collection.commands.collect import COLLECTION_DB_PATH, USER_DATA_PATH, FAMILLE_DIR, emojis
    from LBD import DEVMOD
except ImportError:
    COLLECTION_DB_PATH = None
    USER_DATA_PATH = None
    FAMILIE_DIR = None
    emojis = {"cartes": "🎴", "check": "✅", "cross": "❌", "star": "⭐", "tirage": "🎴"}
    DEVMOD = False

class PVPView(discord.ui.View):
    def __init__(self, ctx, cog, user_cards):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.cog = cog
        self.user_cards = user_cards
        self.selected_cards = []
        self.current_index = 0
        self.max_selection = 3  # Maximum 3 cartes pour 3v3
        self.update_buttons()

    def update_buttons(self):
        # Désactiver le bouton précédent si on est au début
        self.prev_btn.disabled = self.current_index == 0
        # Désactiver le bouton suivant si on est à la fin
        self.next_btn.disabled = self.current_index >= len(self.user_cards) - 1
        
        # Mettre à jour le bouton de sélection
        if self.current_index < len(self.user_cards):
            current_card = self.user_cards[self.current_index]
            card_id = current_card.get('id', '')
            
            if card_id in self.selected_cards:
                self.select_btn.label = "✅ Sélectionné"
                self.select_btn.style = discord.ButtonStyle.success
            elif len(self.selected_cards) >= self.max_selection:
                self.select_btn.label = "❌ Maximum atteint"
                self.select_btn.style = discord.ButtonStyle.danger
                self.select_btn.disabled = True
            else:
                self.select_btn.label = "🎯 Sélectionner"
                self.select_btn.style = discord.ButtonStyle.primary
                self.select_btn.disabled = False
        
        # Mettre à jour le bouton de confirmation
        self.confirm_btn.disabled = len(self.selected_cards) == 0
        self.confirm_btn.label = f"⚔️ Combattre ({len(self.selected_cards)}/{self.max_selection})"

    @discord.ui.button(label="Précédent", emoji="<:gauche:1480718835010240613>", style=discord.ButtonStyle.secondary, row=0)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Ce n'est pas votre sélection !", ephemeral=True)
        
        self.current_index -= 1
        await self.update_view(interaction)

    @discord.ui.button(label="Suivant", emoji="<:droite:1480718813816164403>", style=discord.ButtonStyle.secondary, row=0)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Ce n'est pas votre sélection !", ephemeral=True)
        
        self.current_index += 1
        await self.update_view(interaction)

    @discord.ui.button(label="Sélectionner", emoji="<:star:1480719517465313281>", style=discord.ButtonStyle.primary, row=1)
    async def select_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Ce n'est pas votre sélection !", ephemeral=True)
        
        if self.current_index >= len(self.user_cards):
            return
        
        current_card = self.user_cards[self.current_index]
        card_id = current_card.get('id', '')
        
        if card_id in self.selected_cards:
            self.selected_cards.remove(card_id)
        elif len(self.selected_cards) < self.max_selection:
            self.selected_cards.append(card_id)
        
        self.update_buttons()
        await self.update_view(interaction)

    @discord.ui.button(label="Combattre", emoji="<:pvp:1480717291007246396>", style=discord.ButtonStyle.success, row=1)
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Ce n'est pas votre sélection !", ephemeral=True)
        
        if len(self.selected_cards) == 0:
            return await interaction.response.send_message("Veuillez sélectionner au moins une carte !", ephemeral=True)
        
        # Récupérer les cartes sélectionnées
        selected_card_data = []
        for card_id in self.selected_cards:
            for card in self.user_cards:
                if card.get('id') == card_id:
                    selected_card_data.append(card)
                    break
        
        await interaction.response.send_message(
            f"✅ Équipe sélectionnée ! {len(self.selected_cards)} carte(s) prête(s) au combat.",
            ephemeral=True
        )
        
        # Démarrer le matchmaking
        await self.cog.start_matchmaking(self.ctx.author, selected_card_data)

    async def update_view(self, interaction: discord.Interaction):
        self.update_buttons()
        
        if self.current_index < len(self.user_cards):
            current_card = self.user_cards[self.current_index]
            embed = self.cog.create_pvp_card_embed(current_card, self.current_index + 1, len(self.user_cards))
        else:
            embed = discord.Embed(title="Erreur", description="Carte non trouvée", color=discord.Color.red())
        
        await interaction.response.edit_message(embed=embed, view=self)

class MatchmakingView(discord.ui.View):
    def __init__(self, ctx, cog, player, team):
        super().__init__(timeout=300)  # 5 minutes max
        self.ctx = ctx
        self.cog = cog
        self.player = player
        self.team = team
        self.cancelled = False

    @discord.ui.button(label="Annuler", emoji="<:croix:1480718030127235103>", style=discord.ButtonStyle.danger)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.player.id:
            return await interaction.response.send_message("Ce n'est pas votre recherche !", ephemeral=True)
        
        self.cancelled = True
        await self.cog.cancel_matchmaking(self.player)
        await interaction.response.edit_message(
            content="❌ Recherche de combat annulée",
            view=None
        )

class CombatView(discord.ui.View):
    def __init__(self, ctx, cog, combat_data):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.cog = cog
        self.combat_data = combat_data
        self.current_turn = 0
        self.combat_log = []

    @discord.ui.button(label="Relancer", emoji="<:add:1480718405689671742>", style=discord.ButtonStyle.secondary)
    async def reroll_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Pour les futures fonctionnalités
        await interaction.response.send_message("Fonctionnalité bientôt disponible !", ephemeral=True)

class PVP(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.matchmaking_queue = []  # File d'attente du matchmaking
        self.active_combats = {}  # Combats en cours
        self.pvp_stats_path = USER_DATA_PATH.parent / "pvp_stats.json" if USER_DATA_PATH else None
        self.load_pvp_stats()

    def load_pvp_stats(self):
        """Charge les statistiques PvP"""
        if not self.pvp_stats_path or not self.pvp_stats_path.exists():
            self.pvp_stats = {}
            return
        
        try:
            with open(self.pvp_stats_path, 'r', encoding='utf-8') as f:
                self.pvp_stats = json.load(f)
        except Exception as e:
            print(f"\033[91m[PVP] Erreur chargement stats: {e}\033[0m")
            self.pvp_stats = {}

    def save_pvp_stats(self):
        """Sauvegarde les statistiques PvP"""
        if not self.pvp_stats_path:
            return
        
        try:
            with open(self.pvp_stats_path, 'w', encoding='utf-8') as f:
                json.dump(self.pvp_stats, f, indent=4)
        except Exception as e:
            print(f"\033[91m[PVP] Erreur sauvegarde stats: {e}\033[0m")

    def get_user_pvp_stats(self, user_id: int):
        """Récupère les stats PvP d'un utilisateur"""
        user_id_str = str(user_id)
        
        # Vérifier d'abord dans le JSON utilisateur
        user_data = self.get_user_data_from_json(user_id)
        if user_data and 'pvp_stats' in user_data:
            return user_data['pvp_stats']
        
        # Sinon, vérifier dans le fichier de stats PvP séparé
        if user_id_str not in self.pvp_stats:
            self.pvp_stats[user_id_str] = {
                "elo": 1000,  # ELO de départ
                "victories": 0,
                "defeats": 0,
                "draws": 0,
                "total_combats": 0,
                "win_rate": 0.0
            }
            
            # Sauvegarder dans le JSON utilisateur
            self.save_pvp_stats_to_user_json(user_id, self.pvp_stats[user_id_str])
        
        return self.pvp_stats[user_id_str]

    def get_user_data_from_json(self, user_id: int):
        """Récupère les données utilisateur depuis le JSON principal"""
        if not USER_DATA_PATH:
            return None
        
        user_file = USER_DATA_PATH / f"{user_id}.json"
        if not user_file.exists():
            return None
        
        try:
            with open(user_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"\033[91m[PVP] Erreur lecture fichier utilisateur: {e}\033[0m")
            return None

    def save_pvp_stats_to_user_json(self, user_id: int, pvp_stats: dict):
        """Sauvegarde les stats PvP dans le JSON utilisateur"""
        if not USER_DATA_PATH:
            return
        
        user_file = USER_DATA_PATH / f"{user_id}.json"
        try:
            # Lire le fichier existant
            user_data = {}
            if user_file.exists():
                with open(user_file, 'r', encoding='utf-8') as f:
                    user_data = json.load(f)
            
            # Ajouter/mettre à jour les stats PvP
            user_data['pvp_stats'] = pvp_stats
            
            # Sauvegarder
            with open(user_file, 'w', encoding='utf-8') as f:
                json.dump(user_data, f, indent=4)
                
            print(f"[PVP] Stats PvP sauvegardées pour l'utilisateur {user_id}")
            
        except Exception as e:
            print(f"\033[91m[PVP] Erreur sauvegarde stats dans JSON utilisateur: {e}\033[0m")

    def update_pvp_stats(self, user_id: int, victory: bool, opponent_elo: int):
        """Met à jour les stats PvP après un combat"""
        user_stats = self.get_user_pvp_stats(user_id)
        user_stats["total_combats"] += 1
        
        if victory:
            user_stats["victories"] += 1
            # Calcul ELO (système simple)
            elo_gain = max(20, min(40, int((opponent_elo - user_stats["elo"]) / 50 + 30)))
            user_stats["elo"] += elo_gain
        else:
            user_stats["defeats"] += 1
            # Calcul ELO (système simple)
            elo_loss = max(20, min(40, int((user_stats["elo"] - opponent_elo) / 50 + 20)))
            user_stats["elo"] = max(0, user_stats["elo"] - elo_loss)
        
        user_stats["win_rate"] = (user_stats["victories"] / user_stats["total_combats"]) * 100
        
        # Sauvegarder dans les deux endroits
        self.save_pvp_stats()
        self.save_pvp_stats_to_user_json(user_id, user_stats)

    def get_user_collection(self, user_id: int):
        """Récupère la collection de cartes d'un utilisateur"""
        if not USER_DATA_PATH:
            return []
        
        user_file = USER_DATA_PATH / f"{user_id}.json"
        if not user_file.exists():
            return []
        
        try:
            with open(user_file, 'r', encoding='utf-8') as f:
                user_data = json.load(f)
                collection = user_data.get('collection', {})
                
                # Récupérer les cartes détaillées
                cards = []
                for card_id, count in collection.items():
                    if count > 0:  # Seulement les cartes que l'utilisateur possède
                        card_data = self.get_card_data(card_id)
                        if card_data:
                            card_data['count'] = count
                            cards.append(card_data)
                        else:
                            print(f"[PVP] Carte {card_id} non trouvée dans les données de personnage")
                
                print(f"[PVP] Collection pour {user_id}: {len(cards)} cartes trouvées")
                return cards
        except Exception as e:
            print(f"[PVP] Erreur récupération collection: {e}")
            return []

    def get_card_data(self, card_id: str):
        """Récupère les données complètes d'une carte"""
        try:
            for famille in os.listdir(FAMILLE_DIR):
                famille_path = os.path.join(FAMILLE_DIR, famille)
                if os.path.isdir(famille_path):
                    personnages_file = os.path.join(famille_path, 'personnages.json')
                    if os.path.exists(personnages_file):
                        with open(personnages_file, 'r', encoding='utf-8') as f:
                            personnages_data = json.load(f)
                        
                        for personnage in personnages_data.get('personnages', []):
                            if personnage.get('id') == card_id:
                                personnage['famille_nom'] = famille
                                return personnage
        except Exception as e:
            print(f"[PVP] Erreur récupération carte {card_id}: {e}")
        return None

    def create_pvp_card_embed(self, card, page: int, total_pages: int):
        """Crée un embed pour une carte dans le menu PvP"""
        embed = discord.Embed(
            title=f"🎴 {card['nom']}",
            description=f"**{card.get('description', 'Pas de description')}**",
            color=card.get('couleur', discord.Color.blue().value)
        )
        
        # Stats principales
        stats_text = f"⚡ **Vitesse:** {card.get('vitesse', 0)}\n"
        stats_text += f"🎯 **Précision:** {card.get('precision', 0)}%\n"
        stats_text += f"❤️ **Vie:** {card.get('vie', 0)}\n"
        stats_text += f"💪 **Puissance:** {card.get('puissance', 0)}"
        
        embed.add_field(name="📊 Statistiques", value=stats_text, inline=True)
        
        # Informations
        info_text = f"🏷️ **ID:** {card.get('id', 'N/A')}\n"
        info_text += f"⭐ **Rareté:** {card.get('rarete', 'Inconnue')}\n"
        info_text += f"💰 **Valeur:** {card.get('valeur', 0):,} 💎\n"
        info_text += f"📚 **Famille:** {card.get('famille_nom', 'Inconnue')}"
        
        embed.add_field(name="ℹ️ Informations", value=info_text, inline=True)
        
        embed.set_footer(text=f"Page {page}/{total_pages} • Sélectionnez votre équipe de combat")
        
        # Image si disponible
        if 'image' in card:
            image_path = os.path.join(FAMILLE_DIR, card['famille_nom'], 
                                     card['nom'].lower().replace(" ", "_"), card['image'])
            if os.path.exists(image_path):
                file = discord.File(image_path, filename="image.png")
                embed.set_thumbnail(url="attachment://image.png")
                return embed, file
        
        return embed, None

    @commands.hybrid_command(name="pvp")
    async def pvp(self, ctx, user: discord.Member = None):
        """Commande principale PvP"""
        
        # Créer automatiquement les stats PvP dans le JSON utilisateur si elles n'existent pas
        self.get_user_pvp_stats(ctx.author.id)
        
        # Afficher l'embed principal avec l'équipe du joueur
        await self.show_main_pvp_embed(ctx)
        
        if user:
            # Créer aussi les stats pour l'adversaire s'il n'en a pas
            self.get_user_pvp_stats(user.id)
            
            # Défier un joueur spécifique
            if user.id == ctx.author.id:
                return await ctx.send("❌ Vous ne pouvez pas vous défier vous-même !")
            
            if user.bot:
                return await ctx.send("❌ Vous ne pouvez pas défier un bot !")
            
            await self.challenge_player(ctx, user)
        else:
            # S'inscrire au matchmaking
            await self.show_team_selection(ctx)

    async def show_main_pvp_embed(self, ctx):
        """Affiche l'embed principal PvP avec l'équipe du joueur"""
        user_stats = self.get_user_pvp_stats(ctx.author.id)
        
        # Récupérer l'équipe configurée du joueur (si elle existe)
        configured_team = self.get_user_configured_team(ctx.author.id)
        
        if configured_team:
            # Le joueur a une équipe configurée
            embed = discord.Embed(
                title="⚔️ Système PvP",
                description=f"**Joueur:** {ctx.author.mention}\n"
                           f"**ELO:** {user_stats['elo']}\n"
                           f"**Win Rate:** {user_stats['win_rate']:.1f}%",
                color=discord.Color.blue()
            )
            
            # Afficher l'équipe configurée
            team_text = ""
            for i, card in enumerate(configured_team, 1):
                team_text += f"🎴 **{card['nom']}** (ID: {card['id']})\n"
                team_text += f"   ⚡ Vitesse: {card.get('vitesse', 0)} | "
                team_text += f"🎯 Précision: {card.get('precision', 0)}% | "
                team_text += f"❤️ Vie: {card.get('vie', 0)} | "
                team_text += f"💪 Puissance: {card.get('puissance', 0)}\n\n"
            
            embed.add_field(
                name=f"🛡️ Équipe configurée ({len(configured_team)} carte(s))",
                value=team_text,
                inline=False
            )
            
            embed.add_field(
                name="🎮 Actions disponibles",
                value="• Utilisez les boutons ci-dessous\n"
                      "• `.pvp @joueur` - Défier un joueur",
                inline=False
            )
            
            embed.set_footer(text="Utilisez les boutons pour accéder aux fonctionnalités PvP")
            
        else:
            # Le joueur n'a pas d'équipe configurée
            embed = discord.Embed(
                title="⚔️ Système PvP",
                description=f"**Joueur:** {ctx.author.mention}\n"
                           f"**ELO:** {user_stats['elo']}\n"
                           f"**Win Rate:** {user_stats['win_rate']:.1f}%",
                color=discord.Color.red()
            )
            
            embed.add_field(
                name="❌ Aucune équipe configurée",
                value="Vous devez configurer une équipe avant de pouvoir combattre !\n\n"
                      "**Actions disponibles:**\n"
                      "• Cliquez sur 'Configurer l'équipe' pour commencer\n"
                      "• `.pvp @joueur` - Défier un joueur (si équipe configurée)\n"
                      "• Consultez le classement et vos stats",
                inline=False
            )
            
            embed.add_field(
                name="📋 Comment configurer une équipe ?",
                value="1. Cliquez sur 'Configurer l'équipe'\n"
                      "2. Sélectionnez 1 à 3 cartes de votre collection\n"
                      "3. Validez votre équipe\n"
                      "4. Commencez à combattre !",
                inline=False
            )
            
            embed.set_footer(text="Configurez votre équipe avec le bouton 'Configurer l'équipe'")
        
        # Créer la vue avec les boutons
        view = PVPMainView(ctx, self)
        await ctx.send(embed=embed, view=view)

class PVPMainView(discord.ui.View):
    def __init__(self, ctx, cog):
        super().__init__(timeout=180)
        self.ctx = ctx
        self.cog = cog

    @discord.ui.button(label="Recherche de combat", emoji="<:pvp:1480717291007246396>", style=discord.ButtonStyle.primary)
    async def matchmaking_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Ce n'est pas votre commande !", ephemeral=True)
        
        await self.cog.show_team_selection(self.ctx)

    @discord.ui.button(label="Configurer l'équipe", emoji="<:membre:1480719320567906376>", style=discord.ButtonStyle.success)
    async def team_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Ce n'est pas votre commande !", ephemeral=True)
        
        await self.cog.show_team_selection(self.ctx)

    @discord.ui.button(label="Classement", emoji="<:trophy:1480719996509356203>", style=discord.ButtonStyle.secondary)
    async def rank_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Ce n'est pas votre commande !", ephemeral=True)
        
        await self.cog.pvprank(self.ctx)

    @discord.ui.button(label="Mes stats", emoji="<:stats:1480716514863878164>", style=discord.ButtonStyle.secondary)
    async def stats_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message("Ce n'est pas votre commande !", ephemeral=True)
        
        await self.cog.pvpstats(self.ctx)

    def get_user_configured_team(self, user_id: int):
        """Récupère l'équipe configurée d'un utilisateur"""
        # Pour l'instant, retourne None (pas d'équipe sauvegardée)
        # Cette fonction pourra être étendue pour sauvegarder les équipes
        return None

    async def show_team_selection(self, ctx):
        """Affiche le menu de sélection d'équipe"""
        user_cards = self.get_user_collection(ctx.author.id)
        
        if not user_cards:
            return await ctx.send("❌ Vous ne possédez aucune carte ! Utilisez `.collect` pour obtenir des cartes.")
        
        # Trier par rareté puis par nom
        rarity_order = {"Légendaire": 0, "Epique": 1, "Rare": 2, "Commun": 3}
        user_cards.sort(key=lambda x: (rarity_order.get(x.get('rarete', 'Commun'), 4), x.get('nom', '')))
        
        # Créer la vue de sélection
        view = PVPView(ctx, self, user_cards)
        
        # Message d'en-tête pour la sélection
        embed_header = discord.Embed(
            title="🛡️ Configuration de l'équipe PvP",
            description="Sélectionnez 1 à 3 cartes pour votre équipe de combat.\n"
                       "Les cartes seront utilisées dans l'ordre de vitesse (du plus rapide au plus lent).",
            color=discord.Color.gold()
        )
        
        # Afficher la première carte
        if user_cards:
            embed, file = self.create_pvp_card_embed(user_cards[0], 1, len(user_cards))
            await ctx.send(embed=embed_header)
            await ctx.send(embed=embed, view=view, file=file)
        else:
            await ctx.send("❌ Aucune carte disponible")

    async def challenge_player(self, ctx, opponent: discord.Member):
        """Défie un joueur spécifique"""
        embed = discord.Embed(
            title="⚔️ Défi PvP",
            description=f"{ctx.author.mention} défi {opponent.mention} en combat !",
            color=discord.Color.red()
        )
        
        view = discord.ui.View(timeout=60)
        
        async def accept_callback(interaction: discord.Interaction):
            if interaction.user.id != opponent.id:
                return await interaction.response.send_message("Ce n'est pas votre défi !", ephemeral=True)
            
            await interaction.response.edit_message(
                content="✅ Défi accepté ! Préparation du combat...",
                view=None
            )
            
            # Lancer la sélection d'équipe pour les deux joueurs
            await self.setup_duel(ctx, opponent)
        
        async def decline_callback(interaction: discord.Interaction):
            if interaction.user.id != opponent.id:
                return await interaction.response.send_message("Ce n'est pas votre défi !", ephemeral=True)
            
            await interaction.response.edit_message(
                content="❌ Défi décliné",
                view=None
            )
        
        accept_btn = discord.ui.Button(label="✅ Accepter", style=discord.ButtonStyle.success)
        accept_btn.callback = accept_callback
        view.add_item(accept_btn)
        
        decline_btn = discord.ui.Button(label="❌ Décliner", style=discord.ButtonStyle.danger)
        decline_btn.callback = decline_callback
        view.add_item(decline_btn)
        
        await ctx.send(embed=embed, view=view)

    async def setup_duel(self, ctx, opponent: discord.Member):
        """Configure un duel entre deux joueurs"""
        # Pour l'instant, on utilise le système de matchmaking simplifié
        await ctx.send(f"📋 {ctx.author.mention} et {opponent.mention}, sélectionnez vos équipes respectivement...")
        
        # Demander au premier joueur de sélectionner son équipe
        await self.show_team_selection(ctx)

    async def start_matchmaking(self, player: discord.Member, team: list):
        """Démarre le matchmaking pour un joueur"""
        # Vérifier si le joueur n'est pas déjà dans la file
        for entry in self.matchmaking_queue:
            if entry['player'].id == player.id:
                return await player.send("❌ Vous êtes déjà dans la file d'attente !")
        
        # Ajouter à la file d'attente
        queue_entry = {
            'player': player,
            'team': team,
            'timestamp': datetime.now()
        }
        self.matchmaking_queue.append(queue_entry)
        
        # Envoyer le message de recherche
        embed = discord.Embed(
            title="🔍 Recherche d'adversaire...",
            description=f"Recherche d'un adversaire avec {len(team)} carte(s)...\n\n"
                       f"⏱️ Temps d'attente estimé: 1-3 minutes",
            color=discord.Color.blue()
        )
        
        view = MatchmakingView(player._get_context(), self, player, team)
        message = await player.send(embed=embed, view=view)
        
        # Tenter de trouver un match
        await self.find_match(queue_entry, message, view)

    async def find_match(self, queue_entry, message, view):
        """Trouve un match dans la file d'attente"""
        max_attempts = 30  # 30 tentatives maximum (environ 30 secondes)
        
        for attempt in range(max_attempts):
            if view.cancelled:
                return
            
            # Chercher un adversaire compatible
            opponent_entry = None
            for entry in self.matchmaking_queue:
                if (entry != queue_entry and 
                    len(entry['team']) == len(queue_entry['team']) and
                    not view.cancelled):
                    opponent_entry = entry
                    break
            
            if opponent_entry:
                # Match trouvé !
                await self.start_combat(queue_entry, opponent_entry)
                return
            
            await asyncio.sleep(1)  # Attendre 1 seconde avant la prochaine tentative
        
        # Aucun match trouvé
        if not view.cancelled:
            await message.edit(
                content="❌ Aucun adversaire trouvé. Veuillez réessayer plus tard.",
                embed=None,
                view=None
            )
            self.matchmaking_queue.remove(queue_entry)

    async def start_combat(self, player1_entry, player2_entry):
        """Démarre un combat entre deux joueurs"""
        player1 = player1_entry['player']
        player2 = player2_entry['player']
        team1 = player1_entry['team']
        team2 = player2_entry['team']
        
        # Retirer de la file d'attente
        if player1_entry in self.matchmaking_queue:
            self.matchmaking_queue.remove(player1_entry)
        if player2_entry in self.matchmaking_queue:
            self.matchmaking_queue.remove(player2_entry)
        
        # Créer les données de combat
        combat_id = f"{player1.id}_{player2.id}_{datetime.now().timestamp()}"
        combat_data = {
            'id': combat_id,
            'player1': {
                'user': player1,
                'team': team1,
                'active_cards': team1.copy()  # Copie pour le combat
            },
            'player2': {
                'user': player2,
                'team': team2,
                'active_cards': team2.copy()
            },
            'current_turn': 0,
            'turn_order': [],
            'log': []
        }
        
        self.active_combats[combat_id] = combat_data
        
        # Envoyer les messages de début de combat
        await self.send_combat_start_messages(combat_data)
        
        # Démarrer le combat
        await self.execute_combat_turn(combat_data)

    async def send_combat_start_messages(self, combat_data):
        """Envoie les messages de début de combat"""
        player1 = combat_data['player1']['user']
        player2 = combat_data['player2']['user']
        team1 = combat_data['player1']['team']
        team2 = combat_data['player2']['team']
        
        # Message pour le joueur 1
        embed1 = discord.Embed(
            title="⚔️ Combat PvP !",
            description=f"**Adversaire:** {player2.mention}\n"
                       f"**Mode:** {len(team1)}v{len(team2)}\n\n"
                       f"**Votre équipe:**\n" + 
                       "\n".join([f"🎴 {card['nom']}" for card in team1]),
            color=discord.Color.red()
        )
        embed1.add_field(name="Équipe adverse", 
                        value="\n".join([f"🎴 {card['nom']}" for card in team2]),
                        inline=False)
        
        # Message pour le joueur 2
        embed2 = discord.Embed(
            title="⚔️ Combat PvP !",
            description=f"**Adversaire:** {player1.mention}\n"
                       f"**Mode:** {len(team2)}v{len(team2)}\n\n"
                       f"**Votre équipe:**\n" + 
                       "\n".join([f"🎴 {card['nom']}" for card in team2]),
            color=discord.Color.blue()
        )
        embed2.add_field(name="Équipe adverse", 
                        value="\n".join([f"🎴 {card['nom']}" for card in team1]),
                        inline=False)
        
        view = CombatView(player1._get_context(), self, combat_data)
        
        await player1.send(embed=embed1, view=view)
        await player2.send(embed=embed2, view=view)

    async def execute_combat_turn(self, combat_data):
        """Exécute un tour de combat"""
        player1_cards = combat_data['player1']['active_cards']
        player2_cards = combat_data['player2']['active_cards']
        
        # Déterminer l'ordre de tour (vitesse)
        all_cards = []
        for card in player1_cards:
            all_cards.append(('player1', card))
        for card in player2_cards:
            all_cards.append(('player2', card))
        
        # Trier par vitesse
        all_cards.sort(key=lambda x: x[1].get('vitesse', 0), reverse=True)
        
        # Exécuter les actions
        combat_log = []
        
        for player, card in all_cards:
            if not player2_cards or not player1_cards:
                break  # Combat terminé
            
            opponent_cards = player2_cards if player == 'player1' else player1_cards
            opponent = 'player2' if player == 'player1' else 'player1'
            
            # Choisir une cible aléatoire
            if opponent_cards:
                target = random.choice(opponent_cards)
                
                # Calcul de précision
                precision = card.get('precision', 50)
                roll = random.randint(1, 100)
                
                if roll <= precision:
                    # L'attaque réussit
                    damage_multiplier = self.calculate_damage_multiplier(precision, roll)
                    base_damage = card.get('puissance', 50) * damage_multiplier
                    
                    # Appliquer les dégâts
                    target_hp = target.get('vie', 100) - base_damage
                    
                    combat_log.append(
                        f"⚔️ {card['nom']} attaque {target['nom']} et inflige {base_damage:.1f} dégâts !"
                    )
                    
                    if target_hp <= 0:
                        # La carte est KO
                        combat_log.append(f"💀 {target['nom']} est K.O !")
                        opponent_cards.remove(target)
                    else:
                        target['vie'] = target_hp
                else:
                    # L'attaque échoue
                    combat_log.append(f"❌ {card['nom']} rate son attaque sur {target['nom']} !")
        
        # Vérifier si le combat est terminé
        if not player1_cards:
            winner = 'player2'
        elif not player2_cards:
            winner = 'player1'
        else:
            winner = None
        
        if winner:
            await self.end_combat(combat_data, winner)
        else:
            # Continuer le combat
            combat_data['current_turn'] += 1
            await self.send_combat_update(combat_data, combat_log)
            await asyncio.sleep(3)  # Pause entre les tours
            await self.execute_combat_turn(combat_data)

    def calculate_damage_multiplier(self, precision: int, roll: int):
        """Calcule le multiplicateur de dégâts selon la précision"""
        if roll <= precision * 0.5:  # 50% de la précision
            return 0.25  # 25% des dégâts
        elif roll <= precision * 0.85:  # 85% de la précision
            return 0.5  # 50% des dégâts
        elif roll <= precision * 0.955:  # 95.5% de la précision
            return 0.75  # 75% des dégâts
        else:
            return 1.0  # 100% des dégâts

    async def send_combat_update(self, combat_data, combat_log):
        """Envoie une mise à jour du combat"""
        player1 = combat_data['player1']['user']
        player2 = combat_data['player2']['user']
        
        embed = discord.Embed(
            title=f"⚔️ Tour {combat_data['current_turn'] + 1}",
            description="\n".join(combat_log[-5:]),  # Dernières 5 actions
            color=discord.Color.orange()
        )
        
        # Statut des équipes
        p1_status = f"**Équipe {player1.display_name}:**\n"
        for card in combat_data['player1']['active_cards']:
            hp_percent = (card.get('vie', 100) / card.get('max_vie', card.get('vie', 100))) * 100
            p1_status += f"🎴 {card['nom']} - {hp_percent:.1f}% HP\n"
        
        p2_status = f"**Équipe {player2.display_name}:**\n"
        for card in combat_data['player2']['active_cards']:
            hp_percent = (card.get('vie', 100) / card.get('max_vie', card.get('vie', 100))) * 100
            p2_status += f"🎴 {card['nom']} - {hp_percent:.1f}% HP\n"
        
        embed.add_field(name="🔴 Vos cartes", value=p1_status, inline=True)
        embed.add_field(name="🔵 Cartes adverses", value=p2_status, inline=True)
        
        await player1.send(embed=embed)
        await player2.send(embed=embed)

    async def end_combat(self, combat_data, winner):
        """Termine un combat"""
        player1 = combat_data['player1']['user']
        player2 = combat_data['player2']['user']
        
        # Stats des joueurs
        p1_stats = self.get_user_pvp_stats(player1.id)
        p2_stats = self.get_user_pvp_stats(player2.id)
        
        # Mettre à jour les stats
        if winner == 'player1':
            self.update_pvp_stats(player1.id, True, p2_stats['elo'])
            self.update_pvp_stats(player2.id, False, p1_stats['elo'])
            winner_user = player1
            loser_user = player2
        else:
            self.update_pvp_stats(player2.id, True, p1_stats['elo'])
            self.update_pvp_stats(player1.id, False, p2_stats['elo'])
            winner_user = player2
            loser_user = player1
        
        # Message de fin de combat
        embed = discord.Embed(
            title="🏆 Combat terminé !",
            description=f"**Vainqueur:** {winner_user.mention}\n"
                       f"**Perdant:** {loser_user.mention}\n\n"
                       f"**Nouveaux ELO:**\n"
                       f"🔴 {player1.display_name}: {self.get_user_pvp_stats(player1.id)['elo']}\n"
                       f"🔵 {player2.display_name}: {self.get_user_pvp_stats(player2.id)['elo']}",
            color=discord.Color.gold()
        )
        
        await player1.send(embed=embed)
        await player2.send(embed=embed)
        
        # Nettoyer
        combat_id = combat_data['id']
        if combat_id in self.active_combats:
            del self.active_combats[combat_id]

    async def cancel_matchmaking(self, player: discord.Member):
        """Annule le matchmaking d'un joueur"""
        for entry in self.matchmaking_queue:
            if entry['player'].id == player.id:
                self.matchmaking_queue.remove(entry)
                break

async def setup(bot):
    await bot.add_cog(PVP(bot))
