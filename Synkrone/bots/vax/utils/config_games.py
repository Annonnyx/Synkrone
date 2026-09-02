import importlib
from pathlib import Path
from typing import Any

import discord

try:
    from utils.config_theme import config_manager
except ImportError:
    config_manager = None


MODULE_IMPORTS = [
    "cogs.public.jeux.module.2048",
    "cogs.public.jeux.module.anagram",
    "cogs.public.jeux.module.enigme",
    "cogs.public.jeux.module.flags",
    "cogs.public.jeux.module.master",
    "cogs.public.jeux.module.morpion",
    "cogs.public.jeux.module.nombre",
    "cogs.public.jeux.module.pfc",
    "cogs.public.jeux.module.puissance4",
]


def load_games_catalog() -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    for module_path in MODULE_IMPORTS:
        module = importlib.import_module(module_path)
        meta = getattr(module, "GAME_META", None)
        if isinstance(meta, dict):
            catalog.append(meta.copy())
    return catalog


def load_games_registry() -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {}
    for module_path in MODULE_IMPORTS:
        module = importlib.import_module(module_path)
        meta = getattr(module, "GAME_META", None)
        if isinstance(meta, dict) and meta.get("id"):
            game_id = str(meta["id"])
            registry[game_id] = {
                "meta": meta.copy(),
                "module": module,
                "module_path": module_path,
            }
    return registry


def layout_theme(guild, user, bot):
    if config_manager:
        try:
            theme = config_manager.get_layout_v2_theme(
                guild.id if guild else None,
                guild,
                user,
                bot,
            )
            return {
                "accent_color": discord.Color(int(theme.get("color", 0x2B2D31))),
                "footer_text": theme.get("footer_text") or "",
            }
        except Exception:
            pass
    return {"accent_color": discord.Color(0x2B2D31), "footer_text": ""}


def default_rating_data() -> dict:
    return {"wins": 0, "losses": 0, "draws": 0, "elo": 1000}


def format_rating_field(data: dict) -> str:
    return (
        f"Elo: `{int(data.get('elo', 1000))}`\n"
        f"V: `{int(data.get('wins', 0))}` | N: `{int(data.get('draws', 0))}` | D: `{int(data.get('losses', 0))}`"
    )


def apply_elo_result(data_a: dict, data_b: dict, score_a: float, k_factor: int = 32) -> tuple[dict, dict]:
    elo_a = int(data_a.get("elo", 1000))
    elo_b = int(data_b.get("elo", 1000))

    expected_a = 1 / (1 + 10 ** ((elo_b - elo_a) / 400))
    expected_b = 1 / (1 + 10 ** ((elo_a - elo_b) / 400))

    data_a["elo"] = int(round(elo_a + k_factor * (score_a - expected_a)))
    data_b["elo"] = int(round(elo_b + k_factor * ((1 - score_a) - expected_b)))

    if score_a == 1:
        data_a["wins"] = int(data_a.get("wins", 0)) + 1
        data_b["losses"] = int(data_b.get("losses", 0)) + 1
    elif score_a == 0:
        data_a["losses"] = int(data_a.get("losses", 0)) + 1
        data_b["wins"] = int(data_b.get("wins", 0)) + 1
    else:
        data_a["draws"] = int(data_a.get("draws", 0)) + 1
        data_b["draws"] = int(data_b.get("draws", 0)) + 1

    return data_a, data_b


def load_leaderboard_rows(data_dir: Path, data_loader) -> list[tuple[int, int]]:
    rows: list[tuple[int, int]] = []
    for file in data_dir.glob("*.json"):
        try:
            uid = int(file.stem)
            payload = data_loader(uid)
            score = int(payload.get("elo", 1000))
            if int(payload.get("wins", 0)) + int(payload.get("losses", 0)) + int(payload.get("draws", 0)) > 0:
                rows.append((uid, score))
        except Exception:
            continue
    rows.sort(key=lambda x: x[1], reverse=True)
    return rows


def split_server_global_rows(
    rows: list[tuple[int, int]], guild: discord.Guild | None
) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    global_rows = sorted(rows, key=lambda x: x[1], reverse=True)
    if guild is None:
        return [], global_rows
    server_rows = [(uid, score) for uid, score in global_rows if guild.get_member(int(uid)) is not None]
    return server_rows, global_rows


def top_three_line(rows: list[tuple[int, int]]) -> str:
    if not rows:
        return "Aucun"
    out = []
    for idx, (uid, score) in enumerate(rows[:3], start=1):
        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉"
        out.append(f"{medal} <@{uid}> {score}")
    return " ".join(out)


async def safe_back_to_games(view, interaction: discord.Interaction, game_key: str):
    try:
        from cogs.public.jeux.jeux import MiniGamesLayout

        jeux_cog = view.ctx.bot.get_cog("Jeux")
        if jeux_cog is None:
            view.status_text = "Menu principal introuvable."
            view.rebuild()
            if interaction.response.is_done():
                await interaction.message.edit(view=view)
            else:
                await interaction.response.edit_message(view=view)
            return

        menu_view = MiniGamesLayout(jeux_cog, view.ctx)
        menu_view.mode = "multi"
        menu_view.screen = "games"
        menu_view.selected_game_key = game_key
        menu_view.status_text = "Retour au menu principal."
        menu_view._rebuild()

        view.stop()
        if interaction.response.is_done():
            await interaction.message.edit(view=menu_view)
        else:
            await interaction.response.edit_message(view=menu_view)
    except Exception:
        view.status_text = "Impossible de revenir au menu principal."
        view.rebuild()
        if interaction.response.is_done():
            await interaction.message.edit(view=view)
        else:
            await interaction.response.edit_message(view=view)
