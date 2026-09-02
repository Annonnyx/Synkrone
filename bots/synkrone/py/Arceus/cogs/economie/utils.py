import os
import random
import sqlite3
import time
import asyncio
from dataclasses import dataclass
from typing import Any

import aiohttp
import discord
from discord.ext import commands

try:
    from cogs.pokémon.pokemon import get_species_fr_name
except ImportError:
    get_species_fr_name = None

DB_PATH = os.path.join("data", "economie", "economy.db")

BALL_FIELDS = ["pokeball", "superball", "hyperball", "masterball"]
BALL_LABELS = {
    "pokeball": "Pokeball",
    "superball": "Superball",
    "hyperball": "Hyperball",
    "masterball": "Masterball",
}
BALL_EMOJIS = {
    "pokeball": "<:pokeball:1522952715846684782>",
    "superball": "<:superball:1522998967124623550>",
    "hyperball": "<:hyperball:1522998975739859084>",
    "masterball": "<:masterball:1522999190714585318>",
}
SUPERBONBON_EMOJI = "<:superbonbon:1522998956055990342>"

# --- AJOUT DES CHARMES (INCLUANT LE CHARME XP) ---
CHARM_FIELDS = ["charme_stabilite", "charme_chroma", "charme_insigne", "charme_xp"]
CHARM_LABELS = {
    "charme_stabilite": "Charme Stabilité",
    "charme_chroma": "Charme Chroma",
    "charme_insigne": "Charme Insigne",
    "charme_xp": "Charme XP",
}
CHARM_EMOJIS = {
    "charme_stabilite": "<:Stabilite:1523328083556302918>",
    "charme_chroma": "<:chroma:1523327967172755617>",
    "charme_insigne": "<:Insigne:1523328005882122280>",
    "charme_xp": "<:Exp:1523328037351854080>", # À remplacer par l'émoji de votre choix
}
# -------------------------

BALL_REWARD_TABLE = [
    ("pokeball", 0.60),
    ("superball", 0.25),
    ("hyperball", 0.12),
    ("masterball", 0.03),
]

TYPE_EFFECTIVENESS = {
    "fire": {"grass": 2.0, "ice": 2.0, "bug": 2.0, "steel": 2.0, "water": 0.5, "rock": 0.5, "dragon": 0.5},
    "water": {"fire": 2.0, "ground": 2.0, "rock": 2.0, "water": 0.5, "grass": 0.5, "dragon": 0.5},
    "grass": {"water": 2.0, "ground": 2.0, "rock": 2.0, "fire": 0.5, "grass": 0.5, "poison": 0.5, "flying": 0.5, "bug": 0.5, "dragon": 0.5, "steel": 0.5},
    "electric": {"water": 2.0, "flying": 2.0, "electric": 0.5, "grass": 0.5, "dragon": 0.5, "ground": 0.0},
    "fighting": {"normal": 2.0, "ice": 2.0, "rock": 2.0, "dark": 2.0, "steel": 2.0, "poison": 0.5, "flying": 0.5, "psychic": 0.5, "bug": 0.5, "fairy": 0.5, "ghost": 0.0},
    "ground": {"fire": 2.0, "electric": 2.0, "poison": 2.0, "rock": 2.0, "steel": 2.0, "grass": 0.5, "bug": 0.5, "flying": 0.0},
    "psychic": {"fighting": 2.0, "poison": 2.0, "psychic": 0.5, "steel": 0.5, "dark": 0.0},
    "ice": {"grass": 2.0, "ground": 2.0, "flying": 2.0, "dragon": 2.0, "fire": 0.5, "water": 0.5, "ice": 0.5, "steel": 0.5},
    "dragon": {"dragon": 2.0, "steel": 0.5, "fairy": 0.0},
    "dark": {"psychic": 2.0, "ghost": 2.0, "fighting": 0.5, "dark": 0.5, "fairy": 0.5},
    "fairy": {"fighting": 2.0, "dragon": 2.0, "dark": 2.0, "fire": 0.5, "poison": 0.5, "steel": 0.5},
}


@dataclass
class TeamMon:
    slot: int
    inventory_id: int
    pokemon_id: int
    name: str
    is_shiny: bool
    legendary: bool
    mythical: bool
    sexe: str
    ball: str
    level: int


class EconomyService:
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.ensure_schema()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_schema(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    balance INTEGER NOT NULL DEFAULT 0,
                    xp INTEGER NOT NULL DEFAULT 0,
                    level INTEGER NOT NULL DEFAULT 1,
                    pokeball INTEGER NOT NULL DEFAULT 20,
                    superball INTEGER NOT NULL DEFAULT 0,
                    hyperball INTEGER NOT NULL DEFAULT 0,
                    masterball INTEGER NOT NULL DEFAULT 0,
                    superbonbon INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            
            cursor = conn.execute("PRAGMA table_info(users)")
            user_columns = [row["name"] for row in cursor.fetchall()]
            
            for charm in CHARM_FIELDS:
                if charm not in user_columns:
                    conn.execute(f"ALTER TABLE users ADD COLUMN {charm} INTEGER NOT NULL DEFAULT 0")
                if f"{charm}_expire" not in user_columns:
                    conn.execute(f"ALTER TABLE users ADD COLUMN {charm}_expire REAL NOT NULL DEFAULT 0")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS inventory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    pokemon_id INTEGER NOT NULL,
                    is_shiny INTEGER NOT NULL DEFAULT 0,
                    level INTEGER NOT NULL DEFAULT 1,
                    created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
                )
                """
            )
            
            cursor = conn.execute("PRAGMA table_info(inventory)")
            columns = [row["name"] for row in cursor.fetchall()]

            if "name" not in columns:
                conn.execute("ALTER TABLE inventory ADD COLUMN name TEXT DEFAULT 'Inconnu'")
            if "legendary" not in columns:
                conn.execute("ALTER TABLE inventory ADD COLUMN legendary INTEGER NOT NULL DEFAULT 0")
            if "mythical" not in columns:
                conn.execute("ALTER TABLE inventory ADD COLUMN mythical INTEGER NOT NULL DEFAULT 0")
            if "sexe" not in columns:
                conn.execute("ALTER TABLE inventory ADD COLUMN sexe TEXT DEFAULT 'Inconnu'")
            if "ball" not in columns:
                conn.execute("ALTER TABLE inventory ADD COLUMN ball TEXT DEFAULT 'pokeball'")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS daycare (
                    user_id INTEGER PRIMARY KEY,
                    pokemon_inv_id INTEGER NOT NULL,
                    start_time INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS teams (
                    user_id INTEGER NOT NULL,
                    slot INTEGER NOT NULL,
                    inventory_id INTEGER NOT NULL,
                    PRIMARY KEY(user_id, slot)
                )
                """
            )

    def ensure_user(self, user_id: int):
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO users (
                    user_id, balance, xp, level, pokeball, superball, hyperball, masterball, superbonbon
                ) VALUES (?, 0, 0, 1, 20, 0, 0, 0, 0)
                """,
                (user_id,),
            )

    def get_active_charms(self, user_id: int) -> dict[str, float]:
        self.ensure_user(user_id)
        now = time.time()
        active = {}
        with self._get_conn() as conn:
            query_fields = ", ".join([f"{charm}_expire" for charm in CHARM_FIELDS])
            row = conn.execute(
                f"SELECT {query_fields} FROM users WHERE user_id = ?",
                (user_id,)
            ).fetchone()
            if row:
                for charm in CHARM_FIELDS:
                    expire_time = row[f"{charm}_expire"]
                    if expire_time > now:
                        active[charm] = expire_time
        return active

    def use_charm(self, user_id: int, charm_key: str) -> tuple[bool, str]:
        self.ensure_user(user_id)
        now = time.time()
        with self._get_conn() as conn:
            row = conn.execute(f"SELECT {charm_key}, {charm_key}_expire FROM users WHERE user_id = ?", (user_id,)).fetchone()
            if not row or row[charm_key] <= 0:
                return False, "Vous ne possédez pas ce charme."
            
            current_expire = row[f"{charm_key}_expire"]
            new_expire = max(now, current_expire) + 3600
            
            conn.execute(
                f"UPDATE users SET {charm_key} = {charm_key} - 1, {charm_key}_expire = ? WHERE user_id = ?",
                (new_expire, user_id)
            )
        return True, "Charme activé avec succès !"

    @staticmethod
    def is_staff(member: discord.Member | discord.User) -> bool:
        if isinstance(member, discord.Member):
            return member.guild_permissions.administrator
        return False

    @staticmethod
    def type_multiplier(attacker_types: list[str], defender_types: list[str]) -> float:
        if not attacker_types or not defender_types:
            return 1.0
        atk_type = attacker_types[0]
        chart = TYPE_EFFECTIVENESS.get(atk_type, {})
        mult = 1.0
        for d in defender_types:
            mult *= chart.get(d, 1.0)
        return max(0.0, mult)

    async def get_species_name_fr(self, session: aiohttp.ClientSession, pokemon_id: int) -> str:
        if get_species_fr_name is None:
            return f"Pokémon #{pokemon_id}"
        return await get_species_fr_name(session, str(pokemon_id))

    async def fetch_pokemon_stats(self, session: aiohttp.ClientSession, pokemon_id: int) -> dict[str, Any] | None:
        async with session.get(f"https://pokeapi.co/api/v2/pokemon/{pokemon_id}") as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

        stats = {s["stat"]["name"]: s["base_stat"] for s in data["stats"]}
        
        # Récupération de 4 compétences aléatoires (avec dégâts)
        all_moves = data.get("moves", [])
        selected_moves = []
        if all_moves:
            random.shuffle(all_moves)
            tasks = []
            for m in all_moves:
                tasks.append(session.get(m["move"]["url"]))
                if len(tasks) >= 8: # Prendre un échantillon
                    break
            
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            for m_resp in responses:
                if not isinstance(m_resp, Exception) and m_resp.status == 200:
                    m_data = await m_resp.json()
                    if m_data.get("power"):
                        selected_moves.append({
                            "name": m_data["name"].capitalize(),
                            "power": m_data["power"],
                            "type": m_data["type"]["name"]
                        })
                    if len(selected_moves) >= 4:
                        break

        # Fallback si aucune compétence trouvée
        if not selected_moves:
            selected_moves = [{"name": "Charge", "power": 40, "type": "normal"}]

        return {
            "id": data["id"],
            "name": data["name"].capitalize(),
            "types": [t["type"]["name"] for t in data.get("types", [])],
            "hp": stats.get("hp", 1),
            "attack": stats.get("attack", 1),
            "defense": stats.get("defense", 1),
            "speed": stats.get("speed", 1),
            "moves": selected_moves
        }

    def add_inventory_item(self, user_id: int, pokemon_id: int, name: str = "Inconnu", is_shiny: bool = False, legendary: bool = False, mythical: bool = False, sexe: str = "Inconnu", ball: str = "pokeball", level: int = 1):
        self.ensure_user(user_id)
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO inventory (user_id, pokemon_id, name, is_shiny, legendary, mythical, sexe, ball, level) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, pokemon_id, name, int(is_shiny), int(legendary), int(mythical), sexe, ball, level),
            )

    def get_user_team(self, user_id: int) -> list[TeamMon]:
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT t.slot, i.id AS inventory_id, i.pokemon_id, i.name, i.is_shiny, i.legendary, i.mythical, i.sexe, i.ball, i.level
                FROM teams t
                JOIN inventory i ON i.id = t.inventory_id
                WHERE t.user_id = ?
                ORDER BY t.slot ASC
                """,
                (user_id,),
            ).fetchall()

            if not rows:
                defaults = conn.execute(
                    """
                    SELECT i.id AS inventory_id
                    FROM inventory i
                    LEFT JOIN daycare d ON d.user_id = i.user_id AND d.pokemon_inv_id = i.id
                    WHERE i.user_id = ? AND d.pokemon_inv_id IS NULL
                    ORDER BY i.id ASC
                    LIMIT 3
                    """,
                    (user_id,),
                ).fetchall()

                for slot, row in enumerate(defaults, start=1):
                    conn.execute(
                        "INSERT OR REPLACE INTO teams (user_id, slot, inventory_id) VALUES (?, ?, ?)",
                        (user_id, slot, row["inventory_id"]),
                    )

                rows = conn.execute(
                    """
                    SELECT t.slot, i.id AS inventory_id, i.pokemon_id, i.name, i.is_shiny, i.legendary, i.mythical, i.sexe, i.ball, i.level
                    FROM teams t
                    JOIN inventory i ON i.id = t.inventory_id
                    WHERE t.user_id = ?
                    ORDER BY t.slot ASC
                    """,
                    (user_id,),
                ).fetchall()
                
        return [
            TeamMon(
                slot=row["slot"],
                inventory_id=row["inventory_id"],
                pokemon_id=row["pokemon_id"],
                name=row["name"],
                is_shiny=bool(row["is_shiny"]),
                legendary=bool(row["legendary"]),
                mythical=bool(row["mythical"]),
                sexe=row["sexe"],
                ball=row["ball"],
                level=row["level"],
            )
            for row in rows
        ]

    def gain_xp(self, user_id: int, xp_gain: int) -> int:
        self.ensure_user(user_id)
        now = time.time()
        actual_gain = xp_gain
        with self._get_conn() as conn:
            row = conn.execute("SELECT xp, level, charme_xp_expire FROM users WHERE user_id = ?", (user_id,)).fetchone()
            
            # --- APPLICATION DU CHARME XP ---
            if row["charme_xp_expire"] > now:
                actual_gain = xp_gain * 2

            xp = row["xp"] + actual_gain
            level = row["level"]
            while xp >= level * 100:
                xp -= level * 100
                level += 1
            conn.execute("UPDATE users SET xp = ?, level = ? WHERE user_id = ?", (xp, level, user_id))
            
        return actual_gain