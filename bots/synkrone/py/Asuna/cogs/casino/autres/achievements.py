# ============================================================
#  SYSTÈME DE SUCCÈS — GRAND CASINO D'AINCRAD
#  Paliers : I II III IV V VI VII VIII IX X
#  Récompense : Points d'Honneur (honneur)
# ============================================================
import os
import json
import math
from datetime import datetime

# ── SYSTÈME DE NIVEAU / XP ───────────────────────────────────
XP_PER_GAME_COMMAND = 60
XP_PER_MESSAGE = 1
XP_PER_VOICE_MINUTE = 60

# Ce système base tous les seuils sur le niveau 20 = 10 000 XP.
# La progression est continue de 1 à 100+.
# Le niveau 100 reste proche de 100 000 XP.

_BETA = math.log(100000 / 10000) / math.log(99 / 19)


def xp_for_level(level: int) -> int:
    if level <= 1:
        return 0
    n = level - 1
    return int(round(10000 * (n / 19) ** _BETA))


def level_from_xp(xp: int) -> int:
    if xp <= 0:
        return 1
    n = (xp / 10000) ** (1 / _BETA) * 19
    level = max(1, int(math.floor(n)) + 1)
    while xp_for_level(level) > xp:
        level -= 1
    while xp_for_level(level + 1) <= xp:
        level += 1
    return level


def get_xp(data: dict) -> int:
    return data.get("xp", 0)


def get_level(data: dict) -> int:
    return level_from_xp(get_xp(data))


def get_xp_progress(data: dict) -> tuple[int, int, int]:
    xp = get_xp(data)
    level = level_from_xp(xp)
    xp_in_level = xp - xp_for_level(level)
    xp_to_next = xp_for_level(level + 1) - xp_for_level(level)
    return level, xp_in_level, xp_to_next


def add_xp(data: dict, amount: int, premium: bool = False) -> dict:
    if amount <= 0:
        return data
    if premium:
        amount *= 2
    data["xp"] = data.get("xp", 0) + amount
    return data


def get_hourly_limit(data: dict) -> int:
    return max(1, get_level(data))


_MAX_BET_BY_LEVEL = [
    1000, 3250, 5500, 7750, 10000,
    18000, 26000, 34000, 42000, 50000,
    60000, 70000, 80000, 90000, 100000,
    110000, 120000, 130000, 140000, 150000,
    273125, 396250, 519375, 642500, 765625,
    888750, 1011875, 1135000, 1258125, 1381250,
    1504375, 1627500, 1750625, 1873750, 1996875,
    2120000, 2243125, 2366250, 2489375, 2612500,
    2735625, 2858750, 2981875, 3105000, 3228125,
    3351250, 3474375, 3597500, 3720625, 3843750,
    3966875, 4090000, 4213125, 4336250, 4459375,
    4582500, 4705625, 4828750, 4951875, 5075000,
    5198125, 5321250, 5444375, 5567500, 5690625,
    5813750, 5936875, 6060000, 6183125, 6306250,
    6429375, 6552500, 6675625, 6798750, 6921875,
    7045000, 7168125, 7291250, 7414375, 7537500,
    7660625, 7783750, 7906875, 8030000, 8153125,
    8276250, 8399375, 8522500, 8645625, 8768750,
    8891875, 9015000, 9138125, 9261250, 9384375,
    9507500, 9630625, 9753750, 9876875, 10000000,
]


def get_max_bet(data: dict, base: int) -> int:
    level = max(1, get_level(data))
    if level > len(_MAX_BET_BY_LEVEL):
        level = len(_MAX_BET_BY_LEVEL)
    return min(base, _MAX_BET_BY_LEVEL[level - 1])


# ── PALIERS ──────────────────────────────────────────────────
TIER_NAMES = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X"]

def tier_label(tier: int) -> str:
    return TIER_NAMES[tier - 1] if 1 <= tier <= 10 else str(tier)

# ── DÉFINITION DES SUCCÈS ────────────────────────────────────
# Format : id -> { "nom", "desc", "tiers": [ {seuil, honneur} x10 ] }
# seuil  = valeur du compteur pour débloquer ce palier
# honneur = points d'honneur accordés au déblocage de CE palier
ACHIEVEMENTS = {
    # ─── DAILY ───────────────────────────────────────────────
    "daily_count": {
        "nom": "Habitué du Daily",
        "desc": "Réclamez votre bonus quotidien chaque jour pour accumuler des Cols.",
        "unite": "fois",
        "tiers": [
            {"seuil": 1,    "honneur": 1},
            {"seuil": 5,    "honneur": 1},
            {"seuil": 10,   "honneur": 2},
            {"seuil": 25,   "honneur": 3},
            {"seuil": 50,   "honneur": 5},
            {"seuil": 100,  "honneur": 8},
            {"seuil": 200,  "honneur": 12},
            {"seuil": 365,  "honneur": 20},
            {"seuil": 500,  "honneur": 30},
            {"seuil": 1000, "honneur": 50},
        ]
    },
    "daily_streak": {
        "nom": "Assidu",
        "desc": "Réclamez votre daily sans interruption pendant plusieurs jours consécutifs.",
        "unite": "jours",
        "tiers": [
            {"seuil": 3,   "honneur": 1},
            {"seuil": 7,   "honneur": 2},
            {"seuil": 14,  "honneur": 4},
            {"seuil": 21,  "honneur": 6},
            {"seuil": 30,  "honneur": 10},
            {"seuil": 60,  "honneur": 15},
            {"seuil": 90,  "honneur": 25},
            {"seuil": 120, "honneur": 40},
            {"seuil": 180, "honneur": 60},
            {"seuil": 365, "honneur": 100},
        ]
    },
    # ─── BLACKJACK ───────────────────────────────────────────
    "blackjack_games": {
        "nom": "Amateur de 21",
        "desc": "Affrontez le croupier au Blackjack et visez 21 sans dépasser.",
        "unite": "parties",
        "tiers": [
            {"seuil": 1,   "honneur": 1},
            {"seuil": 10,  "honneur": 1},
            {"seuil": 25,  "honneur": 2},
            {"seuil": 50,  "honneur": 3},
            {"seuil": 100, "honneur": 5},
            {"seuil": 250, "honneur": 8},
            {"seuil": 500, "honneur": 12},
            {"seuil": 750, "honneur": 18},
            {"seuil": 1000,"honneur": 25},
            {"seuil": 2000,"honneur": 40},
        ]
    },
    "blackjack_wins": {
        "nom": "Roi du 21",
        "desc": "Remportez des parties de Blackjack contre le croupier.",
        "unite": "victoires",
        "tiers": [
            {"seuil": 1,   "honneur": 1},
            {"seuil": 5,   "honneur": 2},
            {"seuil": 15,  "honneur": 4},
            {"seuil": 30,  "honneur": 6},
            {"seuil": 60,  "honneur": 10},
            {"seuil": 100, "honneur": 15},
            {"seuil": 200, "honneur": 25},
            {"seuil": 350, "honneur": 40},
            {"seuil": 500, "honneur": 60},
            {"seuil": 1000,"honneur": 100},
        ]
    },
    # ─── ROULETTE ────────────────────────────────────────────
    "roulette_games": {
        "nom": "Rouleur",
        "desc": "Misez sur les numéros ou couleurs et regardez la bille tourner à la Roulette.",
        "unite": "parties",
        "tiers": [
            {"seuil": 1,   "honneur": 1},
            {"seuil": 10,  "honneur": 1},
            {"seuil": 25,  "honneur": 2},
            {"seuil": 50,  "honneur": 3},
            {"seuil": 100, "honneur": 5},
            {"seuil": 250, "honneur": 8},
            {"seuil": 500, "honneur": 12},
            {"seuil": 750, "honneur": 18},
            {"seuil": 1000,"honneur": 25},
            {"seuil": 2000,"honneur": 40},
        ]
    },
    "roulette_wins": {
        "nom": "Chanceux de la Roulette",
        "desc": "Pariez et remportez des victoires à la Roulette grâce à votre instinct.",
        "unite": "victoires",
        "tiers": [
            {"seuil": 1,   "honneur": 1},
            {"seuil": 5,   "honneur": 2},
            {"seuil": 15,  "honneur": 4},
            {"seuil": 30,  "honneur": 6},
            {"seuil": 60,  "honneur": 10},
            {"seuil": 100, "honneur": 15},
            {"seuil": 200, "honneur": 25},
            {"seuil": 350, "honneur": 40},
            {"seuil": 500, "honneur": 60},
            {"seuil": 1000,"honneur": 100},
        ]
    },
    # ─── SLOTS ───────────────────────────────────────────────
    "slots_games": {
        "nom": "Bras Mécanique",
        "desc": "Tirez le levier des machines à sous et tentez d'aligner les symboles gagnants.",
        "unite": "parties",
        "tiers": [
            {"seuil": 1,   "honneur": 1},
            {"seuil": 10,  "honneur": 1},
            {"seuil": 50,  "honneur": 2},
            {"seuil": 100, "honneur": 3},
            {"seuil": 250, "honneur": 5},
            {"seuil": 500, "honneur": 8},
            {"seuil": 1000,"honneur": 12},
            {"seuil": 2000,"honneur": 18},
            {"seuil": 3500,"honneur": 25},
            {"seuil": 5000,"honneur": 40},
        ]
    },
    "slots_jackpot": {
        "nom": "Légende du Jackpot",
        "desc": "Décrochez le Jackpot aux Slots — la combinaison ultime qui fait trembler le casino.",
        "unite": "jackpots",
        "tiers": [
            {"seuil": 1,  "honneur": 5},
            {"seuil": 2,  "honneur": 8},
            {"seuil": 3,  "honneur": 12},
            {"seuil": 5,  "honneur": 20},
            {"seuil": 7,  "honneur": 35},
            {"seuil": 10, "honneur": 60},
            {"seuil": 15, "honneur": 100},
            {"seuil": 20, "honneur": 150},
            {"seuil": 30, "honneur": 250},
            {"seuil": 50, "honneur": 500},
        ]
    },
    # ─── MINES ───────────────────────────────────────────────
    "mines_games": {
        "nom": "Démineur",
        "desc": "Naviguez sur la grille piégée des Mines sans faire exploser une bombe.",
        "unite": "parties",
        "tiers": [
            {"seuil": 1,   "honneur": 1},
            {"seuil": 10,  "honneur": 1},
            {"seuil": 25,  "honneur": 2},
            {"seuil": 50,  "honneur": 3},
            {"seuil": 100, "honneur": 5},
            {"seuil": 200, "honneur": 8},
            {"seuil": 350, "honneur": 12},
            {"seuil": 500, "honneur": 18},
            {"seuil": 750, "honneur": 25},
            {"seuil": 1000,"honneur": 40},
        ]
    },
    "mines_survived": {
        "nom": "Survivant des Mines",
        "desc": "Encaissez vos gains avant l'explosion — la sagesse du démineur expérimenté.",
        "unite": "cash-outs",
        "tiers": [
            {"seuil": 1,   "honneur": 1},
            {"seuil": 5,   "honneur": 2},
            {"seuil": 15,  "honneur": 4},
            {"seuil": 30,  "honneur": 6},
            {"seuil": 60,  "honneur": 10},
            {"seuil": 100, "honneur": 15},
            {"seuil": 200, "honneur": 25},
            {"seuil": 350, "honneur": 40},
            {"seuil": 500, "honneur": 60},
            {"seuil": 1000,"honneur": 120},
        ]
    },
    # ─── COINFLIP ────────────────────────────────────────────
    "coinflip_games": {
        "nom": "Pile ou Face",
        "desc": "Lancez le jeton et pariez sur le bon côté pour doubler votre mise.",
        "unite": "parties",
        "tiers": [
            {"seuil": 1,   "honneur": 1},
            {"seuil": 10,  "honneur": 1},
            {"seuil": 25,  "honneur": 2},
            {"seuil": 50,  "honneur": 3},
            {"seuil": 100, "honneur": 5},
            {"seuil": 200, "honneur": 8},
            {"seuil": 350, "honneur": 12},
            {"seuil": 500, "honneur": 18},
            {"seuil": 750, "honneur": 25},
            {"seuil": 1500,"honneur": 45},
        ]
    },
    "coinflip_wins": {
        "nom": "Maître de la Pièce",
        "desc": "Remportez des victoires au Coinflip — la chance seule ne suffit pas.",
        "unite": "victoires",
        "tiers": [
            {"seuil": 1,   "honneur": 1},
            {"seuil": 5,   "honneur": 2},
            {"seuil": 15,  "honneur": 4},
            {"seuil": 30,  "honneur": 6},
            {"seuil": 60,  "honneur": 10},
            {"seuil": 100, "honneur": 15},
            {"seuil": 200, "honneur": 25},
            {"seuil": 350, "honneur": 40},
            {"seuil": 500, "honneur": 60},
            {"seuil": 1000,"honneur": 120},
        ]
    },
    # ─── LANTERNFALL ─────────────────────────────────────────
    "lantern_games": {
        "nom": "Gardien de la Lanterne",
        "desc": "Suivez la chute des lanternes et misez sur le bon multiplicateur.",
        "unite": "parties",
        "tiers": [
            {"seuil": 1,   "honneur": 1},
            {"seuil": 10,  "honneur": 1},
            {"seuil": 25,  "honneur": 2},
            {"seuil": 50,  "honneur": 3},
            {"seuil": 100, "honneur": 5},
            {"seuil": 200, "honneur": 8},
            {"seuil": 350, "honneur": 12},
            {"seuil": 500, "honneur": 18},
            {"seuil": 750, "honneur": 28},
            {"seuil": 1000,"honneur": 45},
        ]
    },
    # ─── YAKUZABOX ───────────────────────────────────────────
    "yakuza_opened": {
        "nom": "Briseur de Sceaux",
        "desc": "Brisez les sceaux des coffres pour en extraire le butin.",
        "unite": "coffres",
        "tiers": [
            {"seuil": 1,  "honneur": 3},
            {"seuil": 3,  "honneur": 6},
            {"seuil": 5,  "honneur": 10},
            {"seuil": 10, "honneur": 18},
            {"seuil": 20, "honneur": 30},
            {"seuil": 35, "honneur": 50},
            {"seuil": 50, "honneur": 80},
            {"seuil": 75, "honneur": 120},
            {"seuil": 100,"honneur": 200},
            {"seuil": 200,"honneur": 400},
        ]
    },
    # ─── FORTUNE ─────────────────────────────────────────────
    "Cols_total": {
        "nom": "Fortune d'Aincrad",
        "desc": "Accumulez un solde massif de Cols — la richesse absolue du Grand Casino.",
        "unite": "Cols",
        "tiers": [
            {"seuil": 10_000,      "honneur": 1},
            {"seuil": 50_000,      "honneur": 2},
            {"seuil": 100_000,     "honneur": 3},
            {"seuil": 250_000,     "honneur": 5},
            {"seuil": 500_000,     "honneur": 10},
            {"seuil": 1_000_000,   "honneur": 20},
            {"seuil": 2_500_000,   "honneur": 40},
            {"seuil": 5_000_000,   "honneur": 80},
            {"seuil": 10_000_000,  "honneur": 150},
            {"seuil": 50_000_000,  "honneur": 400},
        ]
    },
    "Cols_spent": {
        "nom": "Grand Flambeur",
        "desc": "Misez des sommes colossales — seul un vrai flambeur ose tout risquer.",
        "unite": "Cols misés",
        "tiers": [
            {"seuil": 10_000,      "honneur": 1},
            {"seuil": 50_000,      "honneur": 1},
            {"seuil": 200_000,     "honneur": 2},
            {"seuil": 500_000,     "honneur": 4},
            {"seuil": 1_000_000,   "honneur": 8},
            {"seuil": 5_000_000,   "honneur": 15},
            {"seuil": 10_000_000,  "honneur": 30},
            {"seuil": 25_000_000,  "honneur": 60},
            {"seuil": 50_000_000,  "honneur": 120},
            {"seuil": 100_000_000, "honneur": 250},
        ]
    },
    # ─── HONNEUR ─────────────────────────────────────────────
    "honneur_total": {
        "nom": "Guerrier Honorable",
        "desc": "Accumulez des Points d'Honneur — la marque des plus grands guerriers d'Aincrad.",
        "unite": "pts",
        "tiers": [
            {"seuil": 10,    "honneur": 1},
            {"seuil": 50,    "honneur": 2},
            {"seuil": 100,   "honneur": 3},
            {"seuil": 250,   "honneur": 5},
            {"seuil": 500,   "honneur": 10},
            {"seuil": 1000,  "honneur": 20},
            {"seuil": 2500,  "honneur": 40},
            {"seuil": 5000,  "honneur": 80},
            {"seuil": 10000, "honneur": 150},
            {"seuil": 25000, "honneur": 300},
        ]
    },
    # ─── ROB ─────────────────────────────────────────────────
    "rob_success": {
        "nom": "Pickpocket",
        "desc": "Volez des Cols à d'autres joueurs sans vous faire attraper.",
        "unite": "vols réussis",
        "tiers": [
            {"seuil": 1,   "honneur": 1},
            {"seuil": 5,   "honneur": 2},
            {"seuil": 15,  "honneur": 4},
            {"seuil": 30,  "honneur": 6},
            {"seuil": 60,  "honneur": 10},
            {"seuil": 100, "honneur": 15},
            {"seuil": 200, "honneur": 25},
            {"seuil": 350, "honneur": 40},
            {"seuil": 500, "honneur": 70},
            {"seuil": 1000,"honneur": 130},
        ]
    },
    "rob_backfire": {
        "nom": "Maladroit",
        "desc": "Tentez un vol sur une cible protégée et payez les conséquences.",
        "unite": "fois pris",
        "tiers": [
            {"seuil": 1,  "honneur": 1},
            {"seuil": 3,  "honneur": 1},
            {"seuil": 5,  "honneur": 2},
            {"seuil": 10, "honneur": 3},
            {"seuil": 20, "honneur": 5},
            {"seuil": 30, "honneur": 8},
            {"seuil": 50, "honneur": 12},
            {"seuil": 75, "honneur": 18},
            {"seuil": 100,"honneur": 28},
            {"seuil": 200,"honneur": 50},
        ]
    },
    # ─── VICTOIRES GLOBALES ───────────────────────────────────
    "total_wins": {
        "nom": "Invincible",
        "desc": "Remportez des victoires dans tous les jeux du casino — devenez une légende.",
        "unite": "victoires",
        "tiers": [
            {"seuil": 5,    "honneur": 1},
            {"seuil": 20,   "honneur": 2},
            {"seuil": 50,   "honneur": 4},
            {"seuil": 100,  "honneur": 8},
            {"seuil": 250,  "honneur": 15},
            {"seuil": 500,  "honneur": 30},
            {"seuil": 1000, "honneur": 60},
            {"seuil": 2000, "honneur": 120},
            {"seuil": 3500, "honneur": 200},
            {"seuil": 5000, "honneur": 350},
        ]
    },
}

# ── CHEMINS ─────────────────────────────────────────────────

def _user_path(guild_id: int, user_id: int) -> str:
    base = os.path.join('cogs', 'casino', 'data', str(guild_id))
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, f"{user_id}.json")

def load_user_data(guild_id: int, user_id: int) -> dict:
    path = _user_path(guild_id, user_id)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        data.setdefault("Cols", 1000)
        data.setdefault("honneur", 0)
        data.setdefault("xp", 0)
        return data
    return {"Cols": 1000, "honneur": 0, "xp": 0}

def save_user_data(guild_id: int, user_id: int, data: dict):
    with open(_user_path(guild_id, user_id), 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# ── LOGIQUE PRINCIPALE ───────────────────────────────────────

def get_counter(data: dict, key: str) -> int:
    """Lit le compteur dans stats.{key}. Cas spéciaux: Cols/honneur lus directement."""
    if key == "Cols_total":
        return data.get("Cols", 0)
    if key == "honneur_total":
        return data.get("honneur", 0)
    return data.get("stats", {}).get(key, 0)

def increment_counter(data: dict, key: str, amount: int = 1) -> dict:
    """Incrémente stats.{key} de amount."""
    if "stats" not in data:
        data["stats"] = {}
    data["stats"][key] = data["stats"].get(key, 0) + amount
    return data

def get_unlocked(data: dict) -> dict:
    """Retourne le dict des succès débloqués : { ach_id: { tier: int, date: str } }"""
    return data.get("achievements", {})

def check_and_unlock(guild_id: int, user_id: int, key: str, data: dict = None) -> list:
    """
    Vérifie si de nouveaux paliers sont débloqués pour `key`.
    Retourne la liste des nouveaux paliers débloqués : [ {"nom", "tier_label", "honneur"} ]
    Met à jour et sauvegarde les données si nécessaire.
    """
    if key not in ACHIEVEMENTS:
        return []

    if data is None:
        data = load_user_data(guild_id, user_id)

    ach = ACHIEVEMENTS[key]
    counter = get_counter(data, key)
    unlocked = data.setdefault("achievements", {})
    ach_data = unlocked.setdefault(key, {})
    already_unlocked = ach_data.get("tier", 0)

    newly = []
    for i, tier in enumerate(ach["tiers"]):
        tier_num = i + 1
        if tier_num <= already_unlocked:
            continue
        if counter >= tier["seuil"]:
            # Débloque ce palier
            ach_data["tier"] = tier_num
            now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
            if "dates" not in ach_data:
                ach_data["dates"] = {}
            ach_data["dates"][str(tier_num)] = now_str
            # Donne les points d'honneur
            data["honneur"] = data.get("honneur", 0) + tier["honneur"]
            newly.append({
                "nom": ach["nom"],
                "tier_label": tier_label(tier_num),
                "honneur": tier["honneur"],
            })
        else:
            break  # Paliers ordonnés, inutile de continuer

    if newly:
        save_user_data(guild_id, user_id, data)

    return newly

def check_all(guild_id: int, user_id: int, data: dict = None) -> list:
    """Vérifie tous les succès d'un coup (utile après grosse opération)."""
    if data is None:
        data = load_user_data(guild_id, user_id)
    all_new = []
    for key in ACHIEVEMENTS:
        all_new.extend(check_and_unlock(guild_id, user_id, key, data))
    if all_new:
        save_user_data(guild_id, user_id, data)
    return all_new

# ── STATS RÉSUMÉES ───────────────────────────────────────────

def get_achievement_stats(data: dict) -> dict:
    """Retourne un résumé des succès pour l'affichage en-tête."""
    unlocked = data.get("achievements", {})
    total_paliers = sum(len(a["tiers"]) for a in ACHIEVEMENTS.values())
    unlocked_paliers = sum(u.get("tier", 0) for u in unlocked.values())
    total_honneur_from_ach = 0
    for key, u in unlocked.items():
        tier = u.get("tier", 0)
        for i in range(tier):
            total_honneur_from_ach += ACHIEVEMENTS[key]["tiers"][i]["honneur"]
    return {
        "unlocked_paliers": unlocked_paliers,
        "total_paliers": total_paliers,
        "total_achievements": len(ACHIEVEMENTS),
        "unlocked_achievements": sum(1 for u in unlocked.values() if u.get("tier", 0) > 0),
        "honneur_earned": total_honneur_from_ach,
    }

# ── PAGES POUR AFFICHAGE ─────────────────────────────────────
PER_PAGE = 5  # Succès par page (chacun peut avoir 10 paliers donc dense)

def build_achievement_pages(data: dict) -> list:
    """
    Construit la liste des pages à afficher.
    Chaque page est une liste de succès formatés.
    """
    unlocked = data.get("achievements", {})
    pages = []
    ach_list = list(ACHIEVEMENTS.items())
    for i in range(0, len(ach_list), PER_PAGE):
        chunk = ach_list[i:i + PER_PAGE]
        page_lines = []
        for key, ach in chunk:
            u = unlocked.get(key, {})
            current_tier = u.get("tier", 0)
            counter = get_counter(data, key)
            # Prochain palier
            next_seuil = None
            if current_tier < 10:
                next_seuil = ach["tiers"][current_tier]["seuil"]

            # Nom + palier actuel
            if current_tier == 0:
                header = f"🔒 **{ach['nom']}** — *Aucun palier*"
            elif current_tier == 10:
                header = f"🌟 **{ach['nom']}** — Palier **{tier_label(current_tier)}** *(MAX)*"
            else:
                header = f"🔓 **{ach['nom']}** — Palier **{tier_label(current_tier)}**"

            # Barre de progression
            bar = _progress_bar(current_tier)
            progress = f"`{bar}` {current_tier}/10"

            # Compteur + prochain seuil
            if next_seuil:
                fmt_c = f"{counter:,}".replace(",", " ")
                fmt_s = f"{next_seuil:,}".replace(",", " ")
                progress += f" · {fmt_c}/{fmt_s} {ach['unite']}"

            # Date du dernier palier
            date_line = ""
            if current_tier > 0 and "dates" in u:
                last_date = u["dates"].get(str(current_tier), "?")
                date_line = f"\n-# Palier {tier_label(current_tier)} débloqué le {last_date}"

            # Description de l'achievement
            desc_line = f"\n*{ach['desc']}*"

            page_lines.append(f"{header}{desc_line}\n{progress}{date_line}")

        pages.append("\n\n".join(page_lines))
    return pages

def _progress_bar(tier: int, length: int = 10) -> str:
    filled = "█" * tier
    empty = "░" * (length - tier)
    return filled + empty

# achievements.py est un module utilitaire — pas un cog autonome.
async def setup(bot):
    pass  # Chargé automatiquement comme module, pas comme cog
