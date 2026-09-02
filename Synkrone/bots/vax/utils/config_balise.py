import discord
from datetime import datetime
from zoneinfo import ZoneInfo


WEEKDAYS_FR = [
    "Lundi",
    "Mardi",
    "Mercredi",
    "Jeudi",
    "Vendredi",
    "Samedi",
    "Dimanche",
]

MONTHS_FR = [
    "Janvier",
    "Fevrier",
    "Mars",
    "Avril",
    "Mai",
    "Juin",
    "Juillet",
    "Aout",
    "Septembre",
    "Octobre",
    "Novembre",
    "Decembre",
]


def _safe_name(obj, fallback="Inconnu"):
    return getattr(obj, "display_name", None) or getattr(obj, "name", None) or fallback


def _safe_mention(obj):
    return getattr(obj, "mention", None) or "@inconnu"


def _safe_id(obj):
    obj_id = getattr(obj, "id", None)
    return str(obj_id) if obj_id is not None else "0"


def _resolve_bot_owner(bot: discord.Client):
    """Retourne l'owner du bot. Si le bot appartient a une equipe, retourne le fondateur."""
    # 1) Owner explicite connu par le client (classique)
    owner_id = getattr(bot, "owner_id", None)
    if owner_id:
        owner = bot.get_user(owner_id)
        if owner:
            return owner

    # 2) Application info si disponible dans le client
    app = getattr(bot, "application", None)
    if app:
        team = getattr(app, "team", None)
        if team is not None:
            founder = getattr(team, "owner", None)
            if founder:
                return founder
            founder_id = getattr(team, "owner_id", None)
            if founder_id:
                owner = bot.get_user(founder_id)
                if owner:
                    return owner

        app_owner = getattr(app, "owner", None)
        if app_owner:
            return app_owner

    return None


def _latest_joined_member(guild: discord.Guild | None):
    if guild is None:
        return None
    candidates = [m for m in guild.members if getattr(m, "joined_at", None) is not None]
    if not candidates:
        return None
    return max(candidates, key=lambda m: m.joined_at)


def _member_stats(guild: discord.Guild | None) -> dict[str, int]:
    if guild is None:
        return {
            "members_total": 0,
            "members_humans": 0,
            "members_bots": 0,
            "members_online": 0,
            "members_humans_online": 0,
            "members_bots_online": 0,
        }

    members = list(guild.members)
    humans = [m for m in members if not m.bot]
    bots = [m for m in members if m.bot]

    def _is_online(member: discord.Member) -> bool:
        return member.status != discord.Status.offline

    return {
        "members_total": len(members),
        "members_humans": len(humans),
        "members_bots": len(bots),
        "members_online": sum(1 for m in members if _is_online(m)),
        "members_humans_online": sum(1 for m in humans if _is_online(m)),
        "members_bots_online": sum(1 for m in bots if _is_online(m)),
    }


def resolve_balises(
    guild: discord.Guild | None,
    user: discord.abc.User,
    bot: discord.Client | None,
    *,
    version: str = "",
    prefix: str = "",
) -> dict[str, str]:
    now = datetime.now(ZoneInfo("Europe/Paris"))

    bot_user = getattr(bot, "user", None) if bot is not None else None
    bot_owner = _resolve_bot_owner(bot) if bot is not None else None
    guild_owner = guild.owner if guild else None
    stats = _member_stats(guild)
    latest_joined = _latest_joined_member(guild)

    guild_count = len(getattr(bot, "guilds", []) or []) if bot is not None else 0
    unique_user_ids = set()
    if bot is not None:
        for g in getattr(bot, "guilds", []) or []:
            for m in getattr(g, "members", []):
                if getattr(m, "bot", False):
                    continue
                member_id = getattr(m, "id", None)
                if member_id is not None:
                    unique_user_ids.add(member_id)
    users_unique = len(unique_user_ids)
    ping_ms = int(getattr(bot, "latency", 0.0) * 1000) if bot is not None else 0

    weekday_name = WEEKDAYS_FR[now.weekday()]
    month_name = MONTHS_FR[now.month - 1]

    values = {
        "{serveur_nom}": guild.name if guild else "",
        "{serveur_id}": _safe_id(guild),
        "{bot_nom}": _safe_name(bot_user, "Bot"),
        "{bot_id}": _safe_id(bot_user),
        "{version}": version,
        "{prefix}": prefix,
        "{owner_bot_pseudo}": _safe_name(bot_owner),
        "{owner_bot_tag}": _safe_mention(bot_owner),
        "{owner_bot_id}": _safe_id(bot_owner),
        "{owner_serveur_pseudo}": _safe_name(guild_owner),
        "{owner_serveur_tag}": _safe_mention(guild_owner),
        "{owner_serveur_id}": _safe_id(guild_owner),
        "{viewer_pseudo}": _safe_name(user),
        "{viewer_tag}": _safe_mention(user),
        "{viewer_id}": _safe_id(user),
        "{membres_total}": str(stats["members_total"]),
        "{membres_humains}": str(stats["members_humans"]),
        "{membres_bots}": str(stats["members_bots"]),
        "{membres_en_ligne}": str(stats["members_online"]),
        "{membres_humains_en_ligne}": str(stats["members_humans_online"]),
        "{membres_bots_en_ligne}": str(stats["members_bots_online"]),
        "{dernier_arrive_pseudo}": _safe_name(latest_joined),
        "{dernier_arrive_tag}": _safe_mention(latest_joined),
        "{dernier_arrive_id}": _safe_id(latest_joined),
        "{date_ddmmyyyy}": now.strftime("%d/%m/%Y"),
        "{date_ddmmyy}": now.strftime("%d/%m/%y"),
        "{date_longue}": f"{weekday_name} {now.day} {month_name} {now.year}",
        "{date_jour_nom}": weekday_name,
        "{date_jour_num}": str(now.day),
        "{date_mois_nom}": month_name,
        "{date_mois_num}": now.strftime("%m"),
        "{date_annee}": str(now.year),
        "{date_annee_courte}": now.strftime("%y"),
        "{heure}": now.strftime("%H"),
        "{minute}": now.strftime("%M"),
        "{seconde}": now.strftime("%S"),
        "{heure_hhmm}": now.strftime("%H:%M"),
        "{heure_hhmmss}": now.strftime("%H:%M:%S"),
    }

    # Aliases pour compatibilite avec les anciens templates
    values["{serveur}"] = values["{serveur_nom}"]
    values["{membres}"] = values["{membres_total}"]
    values["{pseudo}"] = values["{viewer_pseudo}"]
    values["{date}"] = values["{date_ddmmyyyy}"]
    values["{heure_ancienne}"] = values["{heure_hhmm}"]

    # Balises courantes des presets de presence
    values["{name}"] = values["{bot_nom}"]
    values["{ping}"] = str(ping_ms)
    values["{users}"] = str(users_unique)
    values["{servers}"] = str(guild_count)

    return values


def apply_balises(text: str, guild: discord.Guild | None, user: discord.abc.User, bot: discord.Client, *, version: str = "", prefix: str = "") -> str:
    if not text:
        return ""

    result = text
    values = resolve_balises(guild, user, bot, version=version, prefix=prefix)
    for key, value in values.items():
        result = result.replace(key, value)

    if guild is None:
        result = result.rstrip(" -")
    return result


BALISE_GROUPS = [
    {
        "key": "serveur",
        "emoji": "🏰",
        "title": "Serveur",
        "subtitle": "Informations d'identité du serveur",
        "items": [
            ("{serveur_nom}", "Nom du serveur"),
            ("{serveur_id}", "ID du serveur"),
            ("{owner_serveur_pseudo}", "Pseudo de l'owner du serveur"),
            ("{owner_serveur_tag}", "Mention de l'owner du serveur"),
            ("{owner_serveur_id}", "ID de l'owner du serveur"),
        ],
    },
    {
        "key": "bot",
        "emoji": "🤖",
        "title": "Bot",
        "subtitle": "Informations d'identité du bot",
        "items": [
            ("{bot_nom}", "Nom du bot"),
            ("{name}", "Alias de {bot_nom} (presences)"),
            ("{bot_id}", "ID du bot"),
            ("{version}", "Version du bot"),
            ("{prefix}", "Préfixe global"),
            ("{ping}", "Latence du bot en millisecondes"),
            ("{owner_bot_pseudo}", "Pseudo de l'owner du bot"),
            ("{owner_bot_tag}", "Mention de l'owner du bot"),
            ("{owner_bot_id}", "ID de l'owner du bot"),
        ],
    },
    {
        "key": "viewer",
        "emoji": "🧑",
        "title": "Utilisateur",
        "subtitle": "Personne qui exécute/voit la commande",
        "items": [
            ("{viewer_pseudo}", "Pseudo de l'utilisateur"),
            ("{viewer_tag}", "Mention de l'utilisateur"),
            ("{viewer_id}", "ID de l'utilisateur"),
        ],
    },
    {
        "key": "stats",
        "emoji": "📊",
        "title": "Statistiques",
        "subtitle": "Membres et présence",
        "items": [
            ("{users}", "Nombre de membres humains uniques sur tous les serveurs"),
            ("{servers}", "Nombre de serveurs où le bot est present"),
            ("{membres_total}", "Nombre total de membres"),
            ("{membres_humains}", "Nombre de membres humains"),
            ("{membres_bots}", "Nombre de bots"),
            ("{membres_en_ligne}", "Membres en ligne"),
            ("{membres_humains_en_ligne}", "Humains en ligne"),
            ("{membres_bots_en_ligne}", "Bots en ligne"),
            ("{dernier_arrive_pseudo}", "Pseudo du dernier membre arrivé"),
            ("{dernier_arrive_tag}", "Mention du dernier membre arrivé"),
            ("{dernier_arrive_id}", "ID du dernier membre arrivé"),
        ],
    },
    {
        "key": "date_heure",
        "emoji": "📅",
        "title": "Date & Heure",
        "subtitle": "Formats courts, longs et détaillés",
        "items": [
            ("{date_ddmmyyyy}", "Date complète"),
            ("{date_ddmmyy}", "Date courte"),
            ("{date_longue}", "Date longue"),
            ("{date_jour_nom}", "Nom du jour"),
            ("{date_jour_num}", "Numéro du jour"),
            ("{date_mois_nom}", "Nom du mois"),
            ("{date_mois_num}", "Numéro du mois"),
            ("{date_annee}", "Année"),
            ("{date_annee_courte}", "Année courte"),
            ("{heure}", "Heure (HH)"),
            ("{minute}", "Minute (MM)"),
            ("{seconde}", "Seconde (SS)"),
            ("{heure_hhmm}", "Heure (HH:MM)"),
            ("{heure_hhmmss}", "Heure (HH:MM:SS)"),
        ],
    },
]


def get_balise_groups() -> list[dict]:
    return BALISE_GROUPS


def get_filter_options() -> list[tuple[str, str, str]]:
    return [(group["key"], f"{group['emoji']} {group['title']}", group["subtitle"]) for group in BALISE_GROUPS]


def get_balise_catalog() -> list[tuple[str, str]]:
    flat: list[tuple[str, str]] = []
    for group in BALISE_GROUPS:
        for token, label in group["items"]:
            flat.append((token, label))
    return flat


def build_balise_help_text() -> str:
    sections: list[str] = []
    for group in BALISE_GROUPS:
        lines = [f"`{token}` : {label}" for token, label in group["items"]]
        block = f"{group['emoji']} **{group['title']}**\n" + "\n".join(lines)
        sections.append(block)
    return "\n\n".join(sections)


def format_balise_line(token: str, label: str, value: str) -> str:
    value = value or ""
    # Les mentions (@tag) ne doivent pas etre dans un bloc code.
    if token.endswith("_tag}"):
        return f"- `{token}` : {label} {value}"
    return f"- `{token}` : {label} `{value}`"
