import discord
from discord.ext import commands
from discord import ui
import random, os, json, math, asyncio, time
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
    if not os.path.exists(base_dir): 
        os.makedirs(base_dir)
    return os.path.join(base_dir, f"{user_id}.json")

def load_user_data(guild_id: int, user_id: int):
    path = get_user_file_path(guild_id, user_id)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f: 
            data = json.load(f)
            if "mines_stats" not in data: 
                data["mines_stats"] = {"parties_heure": [], "derniere_reset": datetime.now().isoformat()}
            return data
    return {"Cols": 1000, "mines_stats": {"parties_heure": [], "derniere_reset": datetime.now().isoformat()}}

def check_limites_heure(guild_id: int, user_id: int) -> dict:
    data = load_user_data(guild_id, user_id)
    now = datetime.now()
    
    stats = data["mines_stats"]
    try:
        derniere_reset = datetime.fromisoformat(stats["derniere_reset"])
    except (ValueError, KeyError):
        derniere_reset = now

    if now - derniere_reset > timedelta(hours=1):
        stats["parties_heure"] = []
        stats["derniere_reset"] = now.isoformat()
    
    stats["parties_heure"] = [
        p for p in stats["parties_heure"] 
        if datetime.fromisoformat(p) > now - timedelta(hours=1)
    ]

    parties_count = len(stats["parties_heure"])
    default_limit = get_hourly_limit(data)
    limite = get_admin_hourly_limit(guild_id, "mines", default_limit)
    parties_restantes = float('inf') if limite is None else max(0, limite - parties_count)
    
    temps_restant = derniere_reset + timedelta(hours=1) - now
    minutes_restantes = max(0, int(temps_restant.total_seconds() / 60))
    
    return {
        "peut_jouer": True if limite is None else parties_restantes > 0,
        "parties_jouees": parties_count,
        "parties_restantes": parties_restantes,
        "temps_restant_minutes": minutes_restantes,
        "stats": stats,
        "limit": limite
    }

def save_user_data(guild_id: int, user_id: int, data: dict):
    path = get_user_file_path(guild_id, user_id)
    with open(path, 'w', encoding='utf-8') as f: 
        json.dump(data, f, indent=4)

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

# --- LOGIQUE DU JEU ---
def get_multiplier(mines, diamonds):
    """Calcul purement informatif du multiplicateur total"""
    if diamonds <= 0: return 1.0
    
    if mines == 1:
        mult = 1.01 + (0.02 * (diamonds - 1))
    elif mines == 3:
        mult = 1.05 + (0.08 * (diamonds - 1))
    elif mines == 5:
        mult = 1.10 + (0.15 * (diamonds - 1))
    elif mines == 10:
        mult = 1.25 + (0.40 * (diamonds - 1))
    elif mines == 15:
        mult = 1.80 + (1.20 * (diamonds - 1))
    elif mines == 20:
        mult = 4.00 + (5.00 * (diamonds - 1))
    elif mines == 24:
        mult = 25.00
        
    return round(mult, 2)

def calculate_gain(mise, mines, diamonds_found):
    if diamonds_found <= 0:
        return 0
    
    gain_total = mise
    
    # Courbe de récompense exponentielle selon la prise de risque
    if mines == 1:
        gain_total += mise * 0.01 + (mise * 0.02 * (diamonds_found - 1))
    elif mines == 3:
        gain_total += mise * 0.05 + (mise * 0.08 * (diamonds_found - 1))
    elif mines == 5:
        gain_total += mise * 0.10 + (mise * 0.15 * (diamonds_found - 1))
    elif mines == 10:
        gain_total += mise * 0.25 + (mise * 0.40 * (diamonds_found - 1))
    elif mines == 15:
        gain_total += mise * 0.80 + (mise * 1.20 * (diamonds_found - 1))
    elif mines == 20:
        gain_total += mise * 3.00 + (mise * 5.00 * (diamonds_found - 1))
    elif mines == 24:
        # Il n'y a qu'une seule case valide sur 25, le gain doit être massif
        gain_total += mise * 24.00 
    
    return int(gain_total)

# --- VUES DE L'INTERFACE SAO ---
class MinesGameView(ui.View):
    def __init__(self, author, bot, mise, num_mines):
        super().__init__(timeout=600)
        self.author, self.bot, self.mise, self.num_mines = author, bot, mise, num_mines
        self.guild = author.guild if hasattr(author, 'guild') else None
        self.diamonds_found = 0
        self.revealed_cells = set()
        self.mines_pos = random.sample([(r, c) for r in range(5) for c in range(5)], min(num_mines, 24))
        self.temp_row = None
        self.temp_col = None
        self.update_buttons()

    def draw_emoji_grid(self, reveal=False, boom_pos=None):
        l_em = [":regional_indicator_a:", ":regional_indicator_b:", ":regional_indicator_c:", ":regional_indicator_d:", ":regional_indicator_e:"]
        n_em = ["⬛", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
        grid = "".join(n_em) + "\n"
        for r in range(5):
            line = l_em[r]
            for c in range(5):
                pos = (r, c)
                if reveal:
                    if pos == boom_pos: line += "💥"
                    elif pos in self.mines_pos: line += "💣"
                    elif pos in self.revealed_cells: line += "💎"
                    else: line += "⬜"
                else:
                    if pos in self.revealed_cells: line += "💎"
                    elif self.temp_row == r and self.temp_col == c: line += "🟪"
                    elif self.temp_row == r and self.temp_col is None: line += "🟪"
                    else: line += "⬜"
            grid += line + "\n"
        return grid

    def update_buttons(self):
        self.clear_items()
        
        if self.temp_row is None:
            select = ui.Select(placeholder="📍 Sélectionner une Ligne (A-E)")
            for r in range(5):
                ligne_pleine = True
                for c in range(5):
                    if (r, c) not in self.revealed_cells:
                        ligne_pleine = False
                        break
                if not ligne_pleine:
                    select.add_option(label=f"Ligne {chr(65+r)}", value=str(r))
            select.callback = self.row_selected
            self.add_item(select)
            
            if self.diamonds_found == 0:
                btn_back = ui.Button(label="⚙️ Modifier les Pièges", style=discord.ButtonStyle.secondary, row=1)
                btn_back.callback = self.back_to_mines
                self.add_item(btn_back)
            
        elif self.temp_col is None:
            select = ui.Select(placeholder="🔢 Sélectionner une Colonne (1-5)")
            for c in range(5):
                if (self.temp_row, c) not in self.revealed_cells:
                    select.add_option(label=f"Colonne {c+1}", value=str(c))
            select.callback = self.col_selected
            self.add_item(select)
            btn_back = ui.Button(label="Retour", style=discord.ButtonStyle.secondary)
            btn_back.callback = self.reset_selection
            self.add_item(btn_back)
        else:
            btn_confirm = ui.Button(label=f"⚔️ Ouvrir la zone {chr(65+self.temp_row)}{self.temp_col+1}", style=discord.ButtonStyle.success)
            btn_confirm.callback = self.confirm_action
            self.add_item(btn_confirm)
            btn_back = ui.Button(label="Changer Colonne", style=discord.ButtonStyle.secondary)
            btn_back.callback = self.back_to_col
            self.add_item(btn_back)

        if self.diamonds_found > 0:
            btn_cash = ui.Button(label="💰 Encaisser les Cols", style=discord.ButtonStyle.primary, row=2)
            btn_cash.callback = self.cashout_callback
            self.add_item(btn_cash)

    def get_emb(self, title, status, reveal=False, boom=None):
        gain_pot = calculate_gain(self.mise, self.num_mines, self.diamonds_found)
        desc = (
            f"⚔️ **Donjon d'Aincrad**\n"
            f"💀 **Pièges (Mines) : {self.num_mines}** | 💰 Cristal misé : **{format_Cols(self.mise)} Cols**\n"
            f"💎 Butin potentiel : **{format_Cols(gain_pot)} Cols**\n\n"
            f"{self.draw_emoji_grid(reveal, boom)}\n\n"
            f"🌐 **Statut de l'interface :** {status}"
        )
        # Gestion du cas où le config_manager serait absent
        title_prefix = format_title(f"🎮 {title}", self.author.id)
        if hasattr(self.bot, "config") and hasattr(self.bot.config, "get_formatted_embed"):
            return self.bot.config.get_formatted_embed(
                title=title_prefix, 
                description=desc, 
                bot_user=self.bot.user, 
                guild=self.guild, 
                user=self.author, 
                target_id=self.guild.id if self.guild else None
            )
        else:
            return discord.Embed(title=title_prefix, description=desc, color=discord.Color.blue())

    async def check_author(self, i: discord.Interaction) -> bool:
        if i.user.id != self.author.id:
            await i.response.send_message("❌ Cette interface de jeu appartient à un autre joueur.", ephemeral=True)
            return False
        return True

    async def row_selected(self, i: discord.Interaction):
        if not await self.check_author(i): return
        self.temp_row = int(i.data['values'][0])
        self.update_buttons()
        await i.response.edit_message(embed=self.get_emb("SAO - EXPLORATION", "Coordonnée de ligne enregistrée. Sélectionnez la colonne."), view=self)

    async def col_selected(self, i: discord.Interaction):
        if not await self.check_author(i): return
        self.temp_col = int(i.data['values'][0])
        self.update_buttons()
        await i.response.edit_message(embed=self.get_emb("SAO - CONFIRMATION", "Prêt à envoyer l'ordre d'ouverture ?"), view=self)

    async def reset_selection(self, i: discord.Interaction):
        if not await self.check_author(i): return
        self.temp_row = None
        self.update_buttons()
        await i.response.edit_message(embed=self.get_emb("SAO - MINES", "Sélectionnez une coordonnée de ligne."), view=self)

    async def back_to_col(self, i: discord.Interaction):
        if not await self.check_author(i): return
        self.temp_col = None
        self.update_buttons()
        await i.response.edit_message(embed=self.get_emb("SAO - EXPLORATION", "Choisissez une nouvelle colonne."), view=self)

    async def confirm_action(self, i: discord.Interaction):
        if not await self.check_author(i): return
        r, c = self.temp_row, self.temp_col
        self.temp_row, self.temp_col = None, None
        
        if (r, c) in self.revealed_cells:
            self.update_buttons()
            return await i.response.edit_message(content="⚠️ Cette zone a déjà été inspectée !", view=self)
            
        if (r, c) in self.mines_pos:
            await self.game_over(i, r, c)
        else:
            self.revealed_cells.add((r, c))
            self.diamonds_found += 1
            if len(self.revealed_cells) + self.num_mines == 25:
                await self.cashout_callback(i)
            else:
                self.update_buttons()
                await i.response.edit_message(embed=self.get_emb("SAO - COFFRE SÉCURISÉ", f"✨ Zone {chr(65+r)}{c+1} saine ! Pas de monstre."), view=self)

    async def cashout_callback(self, i: discord.Interaction):
        if not await self.check_author(i): return
        gain = calculate_gain(self.mise, self.num_mines, self.diamonds_found)
        premium_active, _ = get_vote_bonus_status(self.author.id)
        if premium_active and gain > 0:
            gain *= 2
        gain = apply_admin_gain_limit(i.guild.id, "mines", gain)
        data = load_user_data(i.guild.id, self.author.id)
        
        try:
            from cogs.casino.autres.achievements import increment_counter
            data = increment_counter(data, "Cols_spent", self.mise)
        except ImportError:
            pass
            
        data["Cols"] += (gain - self.mise)
        
        stats = data["mines_stats"]
        stats["parties_heure"].append(datetime.now().isoformat())
        
        data = add_xp(data, XP_PER_GAME_COMMAND, False)
        save_user_data(i.guild.id, self.author.id, data)
        
        try:
            from cogs.casino.autres.achievements import check_and_unlock
            check_and_unlock(i.guild.id, self.author.id, "mines", data)
        except ImportError:
            pass
            
        await self.end_game(i, f"🎉 **VICTOIRE DE L'ÉTAGE** : Transfert réussi ! Vous avez sécurisé **{format_Cols(gain)} Cols** !")

    async def game_over(self, i: discord.Interaction, r, c):
        data = load_user_data(i.guild.id, self.author.id)
        
        try:
            from cogs.casino.autres.achievements import increment_counter
            data = increment_counter(data, "Cols_spent", self.mise)
        except ImportError:
            pass
            
        data["Cols"] -= self.mise
        
        data = add_xp(data, XP_PER_GAME_COMMAND, False)
        save_user_data(i.guild.id, self.author.id, data)
        await self.end_game(i, f"💥 **PIÈGE DÉCLENCHÉ** : Un monstre de zone a détruit votre cristal de mise ! Vous perdez vos Cols.", boom_pos=(r, c))

    async def end_game(self, i: discord.Interaction, status, boom_pos=None):
        self.clear_items()
        
        btn_change = ui.Button(label="Modifier la mise", style=discord.ButtonStyle.secondary, emoji="🔄", row=0)
        btn_change.callback = self.changer_mise_callback
        self.add_item(btn_change)
        
        btn_same = ui.Button(label=f"Relancer ({format_Cols(self.mise)} Cols)", style=discord.ButtonStyle.success, row=0)
        btn_same.callback = self.rejouer_same_mise
        self.add_item(btn_same)
        
        limites = check_limites_heure(i.guild.id, self.author.id)
        limit_display = "∞" if limites['limit'] is None else limites['limit']
        desc = f"{status}\n\n🎮 Énergie de l'avatar : **{limites['parties_restantes']}/{limit_display}**."
        
        await i.response.edit_message(embed=self.get_emb("RÉSULTAT DE L'EXPLORATION", desc, reveal=True, boom=boom_pos), view=self)

    async def rejouer_same_mise(self, i: discord.Interaction):
        if not await self.check_author(i): return
        data = load_user_data(i.guild.id, self.author.id)
        if data["Cols"] < self.mise:
            return await i.response.send_message("❌ Solde de Cols insuffisant dans votre inventaire principal.", ephemeral=True)
        
        view = MinesSelectView(self.author, self.bot, self.mise)
        await i.response.edit_message(embed=view.get_select_emb(), view=view)

    async def changer_mise_callback(self, i: discord.Interaction):
        if not await self.check_author(i): return
        await i.response.send_modal(MinesMiseModal(self.bot, self.author))

    async def back_to_mines(self, i: discord.Interaction):
        if not await self.check_author(i): return
        view = MinesSelectView(self.author, self.bot, self.mise)
        await i.response.edit_message(embed=view.get_select_emb(), view=view)


class MinesSelectView(ui.View):
    def __init__(self, author, bot, mise):
        super().__init__(timeout=120)
        # C'est ici que l'erreur se trouvait, la variable "mise" manquait dans l'assignation !
        self.author, self.bot, self.mise = author, bot, mise 
        self.guild = author.guild if hasattr(author, 'guild') else None
        
        select = ui.Select(placeholder="⚔️ Sélectionner la dangerosité du coffre...")
        difficulties = [
            (1, "+1% (1er), +2% (autres)"),
            (3, "+5% (1er), +8% (autres)"),
            (5, "+10% (1er), +15% (autres)"),
            (10, "+25% (1er), +40% (autres)"),
            (15, "+80% (1er), +120% (autres)"),
            (20, "+300% (1er), +500% (autres)"),
            (24, "+2400% (Jackpot Critique)")
        ]
        for n, desc in difficulties:
            select.add_option(label=f"{n} {'Piège' if n==1 else 'Pièges'}", value=str(n), description=desc)
            
        select.callback = self.select_callback
        self.add_item(select)
        
        btn_mise = ui.Button(label="💰 Réajuster la mise", style=discord.ButtonStyle.secondary, row=1)
        btn_mise.callback = self.change_mise
        self.add_item(btn_mise)

    def get_select_emb(self):
        desc = f"💰 Cristal préparé : **{format_Cols(self.mise)} Cols**\n\nSélectionnez le nombre de pièges dissimulés dans le coffre d'Aincrad."
        title = format_title("⚙️ CONFIGURATION DU SYSTÈME", self.author.id)
        if hasattr(self.bot, "config") and hasattr(self.bot.config, "get_formatted_embed"):
            return self.bot.config.get_formatted_embed(
                title=title, 
                description=desc, 
                guild=self.guild, 
                user=self.author, 
                target_id=self.guild.id if self.guild else None
            )
        else:
            return discord.Embed(title=title, description=desc, color=discord.Color.blue())

    async def select_callback(self, i: discord.Interaction):
        if i.user.id != self.author.id:
            return await i.response.send_message("❌ Cette configuration ne vous appartient pas.", ephemeral=True)
        mines = int(i.data['values'][0])
        game = MinesGameView(self.author, self.bot, self.mise, mines)
        await i.response.edit_message(embed=game.get_emb("SAO - SYSTÈME INITIALISÉ", "🎯 Sélectionnez une première ligne de coordonnées."), view=game)

    async def change_mise(self, i: discord.Interaction):
        if i.user.id != self.author.id:
            return await i.response.send_message("❌ Action impossible.", ephemeral=True)
        await i.response.send_modal(MinesMiseModal(self.bot, self.author))


class MinesLobbyView(ui.View):
    def __init__(self, author, bot):
        super().__init__()
        self.author, self.bot = author, bot
        self.guild = author.guild if hasattr(author, 'guild') else None
        
    def get_lobby_emb(self, data, guild_id=None):
        if guild_id is None:
            guild_id = self.guild.id if self.guild else 0
        limites = check_limites_heure(guild_id, self.author.id)
        limit_display = "∞" if limites['limit'] is None else limites['limit']
        desc = (
            f"🎒 **Inventaire d'Aincrad**\n"
            f"💳 Solde disponible : **{format_Cols(data['Cols'])} Cols**\n"
            f"🎮 Sessions d'exploration : **{limites['parties_restantes']}/{limit_display}**"
        )
        title = format_title("⚔️ SWORD ART ONLINE : EXPÉDITION DE COFFRES", self.author.id)
        if hasattr(self.bot, "config") and hasattr(self.bot.config, "get_formatted_embed"):
            return self.bot.config.get_formatted_embed(
                title=title, 
                description=desc, 
                bot_user=self.bot.user, 
                guild=self.guild, 
                user=self.author, 
                target_id=guild_id if guild_id else None
            )
        else:
            return discord.Embed(title=title, description=desc, color=discord.Color.blue())

    @ui.button(label="⚔️ Ouvrir un coffre", style=discord.ButtonStyle.primary)
    async def bet(self, i: discord.Interaction, btn: ui.Button):
        if i.user.id != self.author.id: 
            return await i.response.send_message("❌ Vous devez initialiser votre propre interface avec /mines.", ephemeral=True)
        await i.response.send_modal(MinesMiseModal(self.bot, self.author))


class MinesMiseModal(ui.Modal, title="💰 MONTANT DE LA MISE"):
    m = ui.TextInput(label="Somme de Cols à charger", placeholder="Ex: 1000 (max selon votre niveau)", min_length=1)
    
    def __init__(self, bot, author):
        super().__init__()
        self.bot, self.author = bot, author
        user_data = load_user_data(author.guild.id, author.id)
        max_bet = get_max_bet(user_data, 10_000_000)
        self.m.placeholder = f"Max {format_Cols(max_bet)} Cols"
        
    async def on_submit(self, i: discord.Interaction):
        try: 
            mise = int(self.m.value)
        except ValueError: 
            return await i.response.send_message("❌ Donnée invalide. Veuillez entrer un nombre entier.", ephemeral=True)
            
        data = load_user_data(i.guild.id, self.author.id)
        max_bet = get_max_bet(data, 10_000_000)
        if mise <= 0 or mise > data["Cols"] or mise > max_bet: 
            return await i.response.send_message(f"❌ Solde insuffisant, mise négative ou limite de {format_Cols(max_bet)} Cols selon votre niveau dépassée.", ephemeral=True)

        limites = check_limites_heure(i.guild.id, self.author.id)
        if not limites["peut_jouer"]:
            limit_display = "∞" if limites['limit'] is None else limites['limit']
            return await i.response.send_message(
                f"❌ Limite horaire atteinte !\n"
                f"🎮 Parties jouées : **{limites['parties_jouees']}/{limit_display}**\n"
                f"⏰ Prochain reset dans **{limites['temps_restant_minutes']}** minutes",
                ephemeral=True
            )

        # Consommer la session dès la confirmation de la mise
        stats = limites["stats"]
        stats["parties_heure"].append(datetime.now().isoformat())
        data["mines_stats"] = stats
        save_user_data(i.guild.id, self.author.id, data)

        view = MinesSelectView(self.author, self.bot, mise)
        await i.response.edit_message(embed=view.get_select_emb(), view=view)


class MinesSAO(commands.Cog):
    def __init__(self, bot): 
        self.bot = bot
        
    @commands.hybrid_command(name="mines", description="Explorez une zone piégée et tentez d'en repartir indemne.")
    async def mines(self, ctx):
        data = load_user_data(ctx.guild.id, ctx.author.id)
        limites = check_limites_heure(ctx.guild.id, ctx.author.id)
        
        if not limites["peut_jouer"]:
            limit_display = "∞" if limites['limit'] is None else limites['limit']
            embed = discord.Embed(
                title="❌ Énergie de l'avatar épuisée",
                description=(
                    f"🎮 Sessions complétées : **{limites['parties_jouees']}/{limit_display}**\n"
                    f"⏰ Régénération du système dans : **{limites['temps_restant_minutes']}** minutes\n\n"
                    f"💰 Banque de Cols actuelle : **{format_Cols(data['Cols'])} Cols**"
                ),
                color=discord.Color.red()
            )
            return await ctx.send(embed=embed, ephemeral=True)
        
        view = MinesLobbyView(ctx.author, self.bot)
        await ctx.send(embed=view.get_lobby_emb(data, ctx.guild.id), view=view)

async def setup(bot): 
    await bot.add_cog(MinesSAO(bot))