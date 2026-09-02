import discord
from discord.ext import commands
from discord import ui
import random, os, json, asyncio, time
from datetime import datetime, timedelta
from pathlib import Path

# ===================== CONFIG MANAGER ========================
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

from cogs.casino.autres.achievements import add_xp, get_hourly_limit, get_max_bet, XP_PER_GAME_COMMAND
from cogs.casino.admin.adminlimit import apply_admin_gain_limit, get_admin_hourly_limit

# --- GESTION DES DONNÉES ---
def get_user_file_path(guild_id: int, user_id: int):
    base_dir = os.path.join('cogs', 'casino', 'data', str(guild_id))
    if not os.path.exists(base_dir): os.makedirs(base_dir)
    return os.path.join(base_dir, f"{user_id}.json")

def load_user_data(guild_id: int, user_id: int):
    path = get_user_file_path(guild_id, user_id)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        data.setdefault("Cols", 1000)
        data.setdefault("xp", 0)
        return data
    return {"Cols": 1000, "xp": 0}

def save_user_data(guild_id: int, user_id: int, data: dict):
    path = get_user_file_path(guild_id, user_id)
    with open(path, 'w', encoding='utf-8') as f: json.dump(data, f, indent=4)

def format_Cols(value: int) -> str:
    return f"{value:,}".replace(',', ' ')

VOTE_DATA_FILE = Path.cwd() / "data" / "public" / "data_vote" / "users.json"
PREMIUM_EMOJI = "<:premium:1528794484295467170>"

def get_vote_bonus_status(user_id: int):
    if not VOTE_DATA_FILE.exists():
        return False, 0
    try:
        with open(VOTE_DATA_FILE, 'r', encoding='utf-8') as f:
            vote_data = json.load(f)
    except Exception:
        return False, 0

    user_entry = vote_data.get(str(user_id), {})
    bonus_end = user_entry.get("bonus_end_timestamp")
    if not bonus_end:
        return False, 0

    now = time.time()
    remaining = int(bonus_end - now)
    if remaining > 0:
        return True, remaining
    return False, 0


def format_title(title: str, user_id: int) -> str:
    premium_active, _ = get_vote_bonus_status(user_id)
    return f"{PREMIUM_EMOJI} {title}" if premium_active else title

# --- GESTION DES LIMITES ---
MAX_MISE = 10_000_000
MAX_PARTIES_HEURE = 20
GAIN_MULTIPLIER = 1.5

def check_limites_heure(guild_id: int, user_id: int) -> dict:
    data = load_user_data(guild_id, user_id)
    now = datetime.now()
    
    if "blackjack_stats" not in data:
        data["blackjack_stats"] = {"parties_heure": [], "derniere_reset": now.isoformat()}
    
    stats = data["blackjack_stats"]
    try:
        derniere_reset = datetime.fromisoformat(stats["derniere_reset"])
    except ValueError:
        derniere_reset = now

    if now - derniere_reset > timedelta(hours=1):
        stats["parties_heure"] = []
        stats["derniere_reset"] = now.isoformat()
        derniere_reset = now
    
    stats["parties_heure"] = [
        p for p in stats["parties_heure"] 
        if datetime.fromisoformat(p) > now - timedelta(hours=1)
    ]

    default_limit = get_hourly_limit(data)
    limite = get_admin_hourly_limit(guild_id, "blackjack", default_limit)
    parties_count = len(stats["parties_heure"])
    parties_restantes = float('inf') if limite is None else limite - parties_count
    
    # Calcul du temps restant avant reset
    temps_restant = derniere_reset + timedelta(hours=1) - now
    minutes_restantes = int(temps_restant.total_seconds() / 60)
    
    return {
        "parties_jouees": parties_count,
        "parties_restantes": max(0, parties_restantes),
        "peut_jouer": parties_restantes > 0,
        "stats": stats,
        "temps_restant_minutes": minutes_restantes,
        "prochain_reset": derniere_reset + timedelta(hours=1),
        "limit": limite,
    }

def ajouter_partie_heure(stats: dict):
    stats["parties_heure"].append(datetime.now().isoformat())

# --- LOGIQUE DES CARTES ---
CARDS_VALUES = {
    '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '10': 10,
    'J': 10, 'Q': 10, 'K': 10, 'A': 11
}
SUITS = ['♠️', '♥️', '♦️', '♣️']

class Card:
    def __init__(self, name, suit):
        self.name = name
        self.suit = suit
        self.value = CARDS_VALUES[name]
    def __str__(self):
        return f"`{self.name}{self.suit}`"

def calculate_hand(hand):
    val = sum(card.value for card in hand)
    aces = sum(1 for card in hand if card.name == 'A')
    while val > 21 and aces:
        val -= 10
        aces -= 1
    return val

# --- VUE DU JEU ---
class BlackjackView(ui.View):
    def __init__(self, author, bot):
        super().__init__(timeout=180)
        self.author = author
        self.bot = bot
        self.mise = 0
        self.player_hand = []
        self.dealer_hand = []
        self.deck = []
        self.ended = False

    def get_emb(self, title, desc, guild=None, user=None):
        target_guild = guild if guild else getattr(self, 'guild', None)
        target_user = user if user else getattr(self, 'author', None)
        target_id = target_guild.id if target_guild else None
        title_prefix = title if title.startswith(PREMIUM_EMOJI) else format_title(title, self.author.id)

        if config_manager:
            return config_manager.get_formatted_embed(
                guild=target_guild,
                user=target_user,
                bot=self.bot,
                title=title_prefix,
                description=desc,
                target_id=target_id,
            )

        if hasattr(self.bot, 'config') and hasattr(self.bot.config, 'get_formatted_embed'):
            emb = self.bot.config.get_formatted_embed(
                title=title_prefix,
                description=desc,
                bot_user=self.bot.user,
                guild=target_guild,
                user=target_user,
                target_id=target_id,
            )
            return emb

        emb = discord.Embed(title=title_prefix, description=desc, color=0x2b2d31)
        emb.set_footer(text=f"Joueur : {self.author.display_name}")
        return emb

    def update_view_buttons(self, step):
        """Met à jour les boutons selon l'état du jeu et le score"""
        self.clear_items()
        
        if step == "initial":
            btn = ui.Button(label="Placer une mise", style=discord.ButtonStyle.secondary, emoji="💰")
            btn.callback = self.ouvrir_modal_mise
            self.add_item(btn)
            
        elif step == "confirm":
            btn_start = ui.Button(label="Commencer", style=discord.ButtonStyle.success, emoji="🃏")
            btn_start.callback = self.demarrer_partie
            btn_back = ui.Button(label="Annuler", style=discord.ButtonStyle.danger)
            btn_back.callback = self.retour_accueil
            self.add_item(btn_start)
            self.add_item(btn_back)
            
        elif step == "play":
            p_score = calculate_hand(self.player_hand)
            d_score = calculate_hand(self.dealer_hand)
            
            # Bouton TIRER (Toujours là tant qu'on n'a pas sauté)
            btn_hit = ui.Button(label="Tirer une carte", style=discord.ButtonStyle.primary, emoji="➕")
            btn_hit.callback = self.hit_callback
            self.add_item(btn_hit)
            
            # Bouton S'ARRÊTER (Seulement si on bat ou égalise le croupier)
            # LOGIQUE DEMANDÉE : Si croupier > moi, je ne peux pas m'arrêter (car je perds).
            if p_score >= d_score:
                btn_stand = ui.Button(label="S'arrêter", style=discord.ButtonStyle.danger, emoji="🛑")
                btn_stand.callback = self.stand_callback
                self.add_item(btn_stand)
            
        elif step == "resultat":
            btn_re = ui.Button(label="Changer mise", style=discord.ButtonStyle.secondary, emoji="🔄")
            btn_re.callback = self.ouvrir_modal_mise
            self.add_item(btn_re)
            if self.mise > 0:
                btn_meme = ui.Button(label=f"Rejouer ({format_Cols(self.mise)})", style=discord.ButtonStyle.success, emoji="💰")
                btn_meme.callback = self.rejouer_meme_mise
                self.add_item(btn_meme)

    async def ouvrir_modal_mise(self, i: discord.Interaction):
        if i.user != self.author: return await i.response.send_message("❌ Pas ta session.", ephemeral=True)
        await i.response.send_modal(MiseBlackjackModal(self))

    async def rejouer_meme_mise(self, i: discord.Interaction):
        if i.user != self.author: return await i.response.send_message("❌ Pas ta session.", ephemeral=True)
        data = load_user_data(i.guild.id, self.author.id)
        limites = check_limites_heure(i.guild.id, self.author.id)
        
        if data["Cols"] < self.mise: return await i.response.send_message("❌ Fonds insuffisants.", ephemeral=True)
        if not limites["peut_jouer"]: return await i.response.send_message("❌ Limite atteinte.", ephemeral=True)
            
        # Ajouter la mise aux statistiques totales
        from cogs.casino.autres.achievements import increment_counter
        data = increment_counter(data, "Cols_spent", self.mise)
        data = add_xp(data, XP_PER_GAME_COMMAND, False)
            
        ajouter_partie_heure(limites["stats"])
        data["blackjack_stats"] = limites["stats"]
        save_user_data(i.guild.id, self.author.id, data)
        from cogs.casino.autres.achievements import check_and_unlock
        check_and_unlock(i.guild.id, self.author.id, "blackjack", data)
        
        self.update_view_buttons("confirm")
        gain_pot = int(self.mise * GAIN_MULTIPLIER)
        desc = f"💰 Mise : **{format_Cols(self.mise)} Cols**\n🏆 Gain potentiel : **{format_Cols(gain_pot)} Cols**\n"
        desc += f"💳 Solde actuel : **{format_Cols(data['Cols'])} Cols**\n"
        desc += f"🎮 Parties restantes : **{limites['parties_restantes']}/{limites['limit']}**"
        await i.response.edit_message(embed=self.get_emb("✅ CONFIRMATION", desc), view=self)

    async def retour_accueil(self, i: discord.Interaction):
        if i.user != self.author: return await i.response.send_message("❌ Pas ta session.", ephemeral=True)
        self.update_view_buttons("initial")
        data = load_user_data(i.guild.id, self.author.id)
        limites = check_limites_heure(i.guild.id, self.author.id)
        
        desc = f"💰 Solde : **{format_Cols(data['Cols'])} Cols**\n"
        desc += f"🎮 Parties restantes : **{limites['parties_restantes']}/{limites['limit']}**\n"
        
        if not limites["peut_jouer"]:
            desc += f"⏰ Prochain reset dans **{limites['temps_restant_minutes']}** minutes"
        
        await i.response.edit_message(embed=self.get_emb("🃏 BLACKJACK", desc), view=self)

    async def demarrer_partie(self, i: discord.Interaction):
        if i.user != self.author: return await i.response.send_message("❌ Pas ta session.", ephemeral=True)
        self.ended = False
        self.deck = [Card(n, s) for n in CARDS_VALUES for s in SUITS]
        random.shuffle(self.deck)
        
        # Distribution initiale : 2 pour joueur, 1 pour croupier (visible)
        self.player_hand = [self.deck.pop(), self.deck.pop()]
        self.dealer_hand = [self.deck.pop()] 
        
        self.update_view_buttons("play")
        await i.response.edit_message(embed=self.creer_embed_jeu(), view=self)

    def creer_embed_jeu(self, title="🃏 BLACKJACK"):
        p_val = calculate_hand(self.player_hand)
        d_val = calculate_hand(self.dealer_hand)
        limites = check_limites_heure(self.author.guild.id, self.author.id)
        user_data = load_user_data(self.author.guild.id, self.author.id)
        
        # Calcul du gain potentiel
        gain_pot = int(self.mise * GAIN_MULTIPLIER)

        desc = f"💰 Mise : **{format_Cols(self.mise)} Cols**\n"
        desc += f"🏆 Gain en cas de victoire : **{format_Cols(gain_pot)} Cols**\n"
        desc += f"💳 Solde actuel : **{format_Cols(user_data['Cols'])} Cols**\n"
        desc += f"🎮 Parties restantes : **{limites['parties_restantes']}**\n\n"
        
        desc += f"👤 **Votre main** : {' '.join(str(c) for c in self.player_hand)} (Score: `{p_val}`)\n"
        desc += f"🤵 **Croupier** : {' '.join(str(c) for c in self.dealer_hand)} (Score: `{d_val}`)\n"
        
        if not self.ended:
            if p_val < d_val:
                desc += "\n⚠️ **ATTENTION** : Le croupier mène ! Vous devez tirer pour espérer gagner."
            else:
                desc += "\n*Vous menez ou égalité. Si vous vous arrêtez, le croupier tentera de vous battre.*"
            
        return self.get_emb(title, desc)

    async def hit_callback(self, i: discord.Interaction):
        if i.user != self.author: return await i.response.send_message("❌ Pas ta session.", ephemeral=True)
        
        # Le joueur tire une carte
        self.player_hand.append(self.deck.pop())
        p_score = calculate_hand(self.player_hand)
        
        # Vérification si le joueur saute
        if p_score > 21:
            return await self.finir_jeu(i, "💥 BUST ! Vous avez dépassé 21.", 0)
        
        # Le croupier tire UNE SEULE carte en réponse
        self.dealer_hand.append(self.deck.pop())
        d_score = calculate_hand(self.dealer_hand)
        
        # Vérification si le croupier saute
        if d_score > 21:
            return await self.finir_jeu(i, "🎉 Le croupier a sauté!", GAIN_MULTIPLIER)
        
        # Mettre à jour les boutons et l'affichage
        self.update_view_buttons("play")
        await i.response.edit_message(embed=self.creer_embed_jeu(), view=self)

    async def stand_callback(self, i: discord.Interaction):
        if i.user != self.author: return await i.response.send_message("❌ Pas ta session.", ephemeral=True)
        
        p_score = calculate_hand(self.player_hand)
        
        # LOGIQUE DU CROUPIER :
        # Le croupier tire TANT QU'il a un score inférieur ou égal au joueur
        # ET qu'il n'a pas encore sauté (moins de 21)
        while True:
            d_score = calculate_hand(self.dealer_hand)
            if d_score > 21:
                return await self.finir_jeu(i, "🎉 Le croupier a sauté !", GAIN_MULTIPLIER)
            
            if d_score > p_score:
                # Le croupier a dépassé le joueur sans sauter -> Croupier gagne
                return await self.finir_jeu(i, f"❌ Le croupier vous a battu ({d_score} vs {p_score}).", 0)
            
            # Si le croupier a moins ou égal, il DOIT tirer pour essayer de gagner
            # (Sauf s'il est déjà à 21 et qu'il y a égalité, c'est un push technique, mais ici on tire)
            self.dealer_hand.append(self.deck.pop())
            # Petite pause pour le suspense si tu veux (optionnel)
            # await asyncio.sleep(0.5) 

    async def finir_jeu(self, i: discord.Interaction, raison, multiplicateur):
        self.ended = True
        user_data = load_user_data(i.guild.id, self.author.id)
        
        if multiplicateur == 0:
            user_data["Cols"] -= self.mise
            bilan = f"📉 Perte : **-{format_Cols(self.mise)} Cols**"
            color_t = "💀 PERDU"
        elif multiplicateur == 1:
            # Égalité parfaite (rare avec cette logique forcée)
            bilan = "🔄 Remboursé."
            color_t = "🤝 ÉGALITÉ"
        else:
            # Gain selon la règle : Mise * 1.5 
            total_retour = int(self.mise * multiplicateur)
            premium_active, _ = get_vote_bonus_status(self.author.id)
            if premium_active:
                total_retour *= 2
            profit = total_retour - self.mise
            profit = apply_admin_gain_limit(i.guild.id, "blackjack", profit)
            user_data["Cols"] += profit
            bilan = f"🎁 Gain : **+{format_Cols(profit)} Cols**"
            color_t = "🎉 GAGNÉ"
        
        save_user_data(i.guild.id, self.author.id, user_data)
        
        self.update_view_buttons("resultat")
        embed = self.creer_embed_jeu(title=f"{color_t} : {raison}")
        embed.add_field(name="Bilan", value=f"{bilan}\n💳 Solde : **{format_Cols(user_data['Cols'])} Cols**", inline=False)
        
        await i.response.edit_message(embed=embed, view=self)

# --- MODAL ---
class MiseBlackjackModal(ui.Modal, title="💰 MISE"):
    m = ui.TextInput(label="Montant", placeholder="max selon votre niveau", min_length=1)
    def __init__(self, v):
        super().__init__()
        self.v = v
        max_bet = get_max_bet(load_user_data(v.author.guild.id, v.author.id), MAX_MISE)
        self.m.placeholder = f"Max {format_Cols(max_bet)} Cols"
        
    async def on_submit(self, i: discord.Interaction):
        if not self.m.value.isdigit(): return await i.response.send_message("❌ Chiffres uniquement.", ephemeral=True)
        montant = int(self.m.value)
        data = load_user_data(i.guild.id, self.v.author.id)
        limites = check_limites_heure(i.guild.id, self.v.author.id)

        max_bet = get_max_bet(data, MAX_MISE)
        if montant <= 0 or montant > data["Cols"]: return await i.response.send_message("❌ Montant invalide.", ephemeral=True)
        if montant > max_bet: return await i.response.send_message(f"❌ Max **{format_Cols(max_bet)} Cols** selon votre niveau.", ephemeral=True)
        if not limites["peut_jouer"]: 
            return await i.response.send_message(
                f"❌ Limite horaire atteinte !\n"
                f"Parties jouées : {limites['parties_jouees']}/{limites['limit']}\n"
                f"⏰ Prochain reset dans **{limites['temps_restant_minutes']}** minutes",
                ephemeral=True
            )
        
        # Ajouter la mise aux statistiques totales
        from cogs.casino.autres.achievements import increment_counter
        data = increment_counter(data, "Cols_spent", montant)
        data = add_xp(data, XP_PER_GAME_COMMAND, False)
        
        ajouter_partie_heure(limites["stats"])
        data["blackjack_stats"] = limites["stats"]
        save_user_data(i.guild.id, self.v.author.id, data)
        
        self.v.mise = montant
        self.v.update_view_buttons("confirm")
        
        # Affichage du gain potentiel dès la confirmation
        gain_pot = int(montant * GAIN_MULTIPLIER)
        desc = f"💰 Mise : **{format_Cols(montant)} Cols**\n🏆 Gain potentiel : **{format_Cols(gain_pot)} Cols**\n"
        desc += f"💳 Solde actuel : **{format_Cols(data['Cols'])} Cols**\n"
        desc += f"🎮 Parties restantes : **{limites['parties_restantes']}/{limites['limit']}**"
        
        await i.response.edit_message(embed=self.v.get_emb("✅ CONFIRMATION", desc), view=self.v)

# --- COG ---
class BlackjackMiyazaki(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="blackjack", aliases=["bj"], description="Jouez au blackjack contre le casino.")
    async def blackjack(self, ctx):
        data = load_user_data(ctx.guild.id, ctx.author.id)
        limites = check_limites_heure(ctx.guild.id, ctx.author.id)

        def build_embed(title: str, description: str, color: discord.Color = discord.Color.red()):
            title = format_title(title, ctx.author.id)
            if config_manager:
                return config_manager.get_formatted_embed(
                    guild=ctx.guild,
                    user=ctx.author,
                    bot=self.bot,
                    title=title,
                    description=description,
                    target_id=ctx.guild.id if ctx.guild else None,
                )

            emb = discord.Embed(title=title, description=description, color=color)
            emb.set_footer(text=f"Joueur : {ctx.author.display_name}")
            return emb
        
        # Si limite atteinte, afficher directement le message d'erreur
        if not limites["peut_jouer"]:
            title = format_title("❌ Limite horaire atteinte", ctx.author.id)
            embed = build_embed(
                title=title,
                description=(
                    f"🎮 Parties jouées : **{limites['parties_jouees']}/{limites['limit']}**\n"
                    f"⏰ Prochain reset dans **{limites['temps_restant_minutes']}** minutes\n\n"
                    f"💰 Solde actuel : **{format_Cols(data['Cols'])} Cols**"
                ),
            )
            return await ctx.send(embed=embed, ephemeral=True)
        
        # Sinon, afficher le jeu normal
        limit_display = "∞" if limites["limit"] is None else limites["limit"]
        view = BlackjackView(ctx.author, self.bot)
        view.update_view_buttons("initial")
        
        desc = f"💰 Solde : **{format_Cols(data['Cols'])} Cols**\n"
        desc += f"🎮 Parties restantes : **{limites['parties_restantes']}/{limit_display}** \n"
        
        embed = view.get_emb("🃏 BLACKJACK", desc)
        await ctx.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(BlackjackMiyazaki(bot))