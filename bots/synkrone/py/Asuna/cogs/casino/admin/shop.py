import json
import os
from typing import Dict, List, Optional, Tuple

import discord
from discord import ui
from discord.ext import commands

try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None


DEFAULT_CUSTOM_PRICE = 1_000_000_000
SHOP_FILE_NAME = "shop_config.json"
CUSTOM_OWNERS_FILE = "custom_roles.json"


def format_cols(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def get_guild_data_dir(guild_id: int) -> str:
    base_dir = os.path.join("cogs", "casino", "data", str(guild_id))
    os.makedirs(base_dir, exist_ok=True)
    return base_dir


def get_user_file_path(guild_id: int, user_id: int) -> str:
    return os.path.join(get_guild_data_dir(guild_id), f"{user_id}.json")


def load_user_data(guild_id: int, user_id: int) -> Dict:
    path = get_user_file_path(guild_id, user_id)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"Cols": 1000}


def save_user_data(guild_id: int, user_id: int, data: Dict) -> None:
    path = get_user_file_path(guild_id, user_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def get_shop_path(guild_id: int) -> str:
    return os.path.join(get_guild_data_dir(guild_id), SHOP_FILE_NAME)


def get_custom_owner_path(guild_id: int) -> str:
    return os.path.join(get_guild_data_dir(guild_id), CUSTOM_OWNERS_FILE)


def default_shop_config() -> Dict:
    return {
        "items": [],
        "custom": {
            "enabled": False,
            "base_price": DEFAULT_CUSTOM_PRICE,
            "anchor_role_id": None,
            "position": "bottom",  # bottom | above | below
            "max_per_user": 1,
            "max_total": 20,
            "option_prices": {
                "color": {"enabled": True, "pct": 10},
                "hoist": {"enabled": True, "pct": 10},
                "mention": {"enabled": True, "pct": 10},
            },
        },
    }


def load_shop_config(guild_id: int) -> Dict:
    path = get_shop_path(guild_id)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = default_shop_config()

    if "items" not in data or not isinstance(data["items"], list):
        data["items"] = []
    if "custom" not in data or not isinstance(data["custom"], dict):
        data["custom"] = default_shop_config()["custom"]

    custom = data["custom"]
    custom.setdefault("enabled", False)
    custom.setdefault("base_price", DEFAULT_CUSTOM_PRICE)
    custom.setdefault("anchor_role_id", None)
    custom.setdefault("position", "bottom")
    custom.setdefault("max_per_user", 1)
    custom.setdefault("max_total", 20)
    custom.setdefault("option_prices", {})
    option_prices = custom["option_prices"]
    option_prices.setdefault("color", {"enabled": True, "pct": 10})
    option_prices.setdefault("hoist", {"enabled": True, "pct": 10})
    option_prices.setdefault("mention", {"enabled": True, "pct": 10})

    for key in ["color", "hoist", "mention"]:
        option_prices[key].setdefault("enabled", True)
        option_prices[key].setdefault("pct", 10)

    return data


def save_shop_config(guild_id: int, data: Dict) -> None:
    path = get_shop_path(guild_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def load_custom_owners(guild_id: int) -> Dict[str, List[int]]:
    path = get_custom_owner_path(guild_id)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = {"owners": {}}

    if "owners" not in data or not isinstance(data["owners"], dict):
        data["owners"] = {}
    if "role_options" not in data or not isinstance(data["role_options"], dict):
        data["role_options"] = {}

    normalized_owners = {}
    for uid, role_ids in data["owners"].items():
        uid_txt = str(uid)
        if not isinstance(role_ids, list):
            continue
        normalized_roles = []
        for rid in role_ids:
            try:
                normalized_roles.append(int(rid))
            except (TypeError, ValueError):
                continue
        normalized_owners[uid_txt] = normalized_roles
    data["owners"] = normalized_owners

    normalized_opts = {}
    for rid, opt in data["role_options"].items():
        rid_txt = str(rid)
        if not isinstance(opt, dict):
            opt = {}
        normalized_opts[rid_txt] = {
            "color": bool(opt.get("color", False)),
            "hoist": bool(opt.get("hoist", False)),
            "mention": bool(opt.get("mention", False)),
        }
    data["role_options"] = normalized_opts

    return data


def save_custom_owners(guild_id: int, data: Dict[str, List[int]]) -> None:
    path = get_custom_owner_path(guild_id)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def parse_on_off(value: str) -> Optional[bool]:
    v = value.strip().lower()
    if v in {"on", "oui", "true", "1", "activer", "enabled"}:
        return True
    if v in {"off", "non", "false", "0", "desactiver", "disabled"}:
        return False
    return None


def parse_yes_no(value: str) -> Optional[bool]:
    v = value.strip().lower()
    if v in {"oui", "yes", "y", "true", "1", "on"}:
        return True
    if v in {"non", "no", "n", "false", "0", "off"}:
        return False
    return None


def parse_hex_color(value: str) -> Optional[discord.Colour]:
    txt = value.strip().lstrip("#")
    if len(txt) != 6:
        return None
    try:
        return discord.Colour(int(txt, 16))
    except ValueError:
        return None


def parse_custom_input(raw: str) -> Tuple[Optional[str], Optional[str], Optional[bool], Optional[bool], Optional[str]]:
    # Format attendu: nom;coul_hex;notifier(oui/non);epingle(oui/non)
    parts = [p.strip() for p in raw.split(";")]
    if not parts or not parts[0]:
        return None, None, None, None, "Nom du role manquant."

    name = parts[0]
    color_raw = parts[1] if len(parts) > 1 and parts[1] else None
    notify = parse_yes_no(parts[2]) if len(parts) > 2 and parts[2] else False
    pinned = parse_yes_no(parts[3]) if len(parts) > 3 and parts[3] else False

    if len(name) > 100:
        return None, None, None, None, "Le nom du role ne peut pas depasser 100 caracteres."
    if notify is None:
        return None, None, None, None, "Valeur notifier invalide (oui/non)."
    if pinned is None:
        return None, None, None, None, "Valeur epingle invalide (oui/non)."
    if color_raw and parse_hex_color(color_raw) is None:
        return None, None, None, None, "Couleur invalide. Utilisez un code hex, ex: #ff8800"

    return name, color_raw, notify, pinned, None


class ShopCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def make_embed(self, ctx: commands.Context, title: str, description: str) -> discord.Embed:
        if config_manager:
            return config_manager.get_formatted_embed(
                guild=ctx.guild,
                user=ctx.author,
                bot=self.bot,
                title=title,
                description=description,
                target_id=ctx.guild.id if ctx.guild else None,
            )
        return discord.Embed(title=title, description=description)

    def make_embed_for_user(
        self,
        guild: discord.Guild,
        user: Optional[discord.abc.User],
        title: str,
        description: str,
    ) -> discord.Embed:
        if config_manager:
            return config_manager.get_formatted_embed(
                guild=guild,
                user=user,
                bot=self.bot,
                title=title,
                description=description,
                target_id=guild.id if guild else None,
            )
        return discord.Embed(title=title, description=description)

    def get_shop_items_sorted(self, guild_id: int) -> List[Dict]:
        data = load_shop_config(guild_id)
        items = data.get("items", [])
        return sorted(items, key=lambda x: int(x.get("price", 0)), reverse=True)

    def get_buyable_shop_items(self, member: discord.Member) -> List[Dict]:
        buyable = []
        for item in self.get_shop_items_sorted(member.guild.id):
            role = member.guild.get_role(int(item["role_id"]))
            if role is None:
                continue
            if role in member.roles:
                continue
            buyable.append(item)
        return buyable

    def prune_owner_roles(self, guild: discord.Guild, owners_data: Dict) -> Dict:
        changed = False
        owners = owners_data.get("owners", {})
        role_options = owners_data.get("role_options", {})

        for uid, role_ids in list(owners.items()):
            kept = []
            for rid in role_ids:
                if guild.get_role(int(rid)) is not None:
                    kept.append(int(rid))
            if kept != role_ids:
                owners[uid] = kept
                changed = True
            if not owners[uid]:
                owners.pop(uid, None)
                changed = True

        used_role_ids = {str(rid) for role_ids in owners.values() for rid in role_ids}
        for rid_txt in list(role_options.keys()):
            if rid_txt not in used_role_ids:
                role_options.pop(rid_txt, None)
                changed = True

        if changed:
            owners_data["owners"] = owners
            owners_data["role_options"] = role_options
        return owners_data

    def clean_missing_custom_roles(self, guild: discord.Guild) -> Dict:
        owners_data = load_custom_owners(guild.id)
        owners_data = self.prune_owner_roles(guild, owners_data)
        save_custom_owners(guild.id, owners_data)
        return owners_data

    def get_custom_roles_count(self, guild: discord.Guild) -> int:
        owners_data = self.clean_missing_custom_roles(guild)
        owners = owners_data.get("owners", {})
        return sum(len(role_ids) for role_ids in owners.values())

    def get_user_custom_roles(self, guild: discord.Guild, user_id: int) -> List[int]:
        owners_data = self.clean_missing_custom_roles(guild)
        return [int(rid) for rid in owners_data.get("owners", {}).get(str(user_id), [])]

    def get_role_options_state(self, owners_data: Dict, role_id: int) -> Dict[str, bool]:
        role_options = owners_data.get("role_options", {})
        raw = role_options.get(str(role_id), {})
        return {
            "color": bool(raw.get("color", False)),
            "hoist": bool(raw.get("hoist", False)),
            "mention": bool(raw.get("mention", False)),
        }

    def set_role_options_state(self, owners_data: Dict, role_id: int, state: Dict[str, bool]) -> None:
        role_options = owners_data.setdefault("role_options", {})
        role_options[str(role_id)] = {
            "color": bool(state.get("color", False)),
            "hoist": bool(state.get("hoist", False)),
            "mention": bool(state.get("mention", False)),
        }

    async def move_role_if_needed(self, guild: discord.Guild, role: discord.Role, custom_cfg: Dict) -> None:
        position_mode = str(custom_cfg.get("position", "bottom")).lower()
        anchor_role_id = custom_cfg.get("anchor_role_id")

        if position_mode == "bottom" or not anchor_role_id:
            return

        anchor = guild.get_role(int(anchor_role_id))
        if anchor is None:
            return

        if position_mode == "above":
            target_pos = anchor.position + 1
        elif position_mode == "below":
            target_pos = max(1, anchor.position - 1)
        else:
            return

        await role.edit(position=target_pos, reason="Positionnement role custom shop")

    def build_admin_roles_description(self, guild: discord.Guild) -> str:
        data = load_shop_config(guild.id)
        items = data.get("items", [])

        lines = []
        if not items:
            lines.append("Aucun rôle en vente.")
        else:
            for idx, item in enumerate(items, start=1):
                role = guild.get_role(int(item["role_id"]))
                role_txt = role.mention if role else f"Role supprime ({item['role_id']})"
                lines.append(f"{idx}. {role_txt} - {format_cols(int(item['price']))} Cols")

        lines.append("")
        lines.append("Actions disponibles:")
        lines.append("- ➕ Ajouter un rôle")
        lines.append("- ✏️ Modifier une entrée")
        lines.append("- 🗑️ Supprimer une entrée")

        return "\n".join(lines)

    def build_admin_custom_description(self, guild: discord.Guild) -> str:
        data = load_shop_config(guild.id)
        custom = data.get("custom", {})
        option_prices = custom.get("option_prices", {})
        color_cfg = option_prices.get("color", {"enabled": True, "pct": 10})
        hoist_cfg = option_prices.get("hoist", {"enabled": True, "pct": 10})
        mention_cfg = option_prices.get("mention", {"enabled": True, "pct": 10})
        anchor_txt = "Aucun"
        if custom.get("anchor_role_id"):
            role = guild.get_role(int(custom["anchor_role_id"]))
            anchor_txt = role.mention if role else f"ID {custom['anchor_role_id']}"

        lines = []
        lines.append("Option custom:")
        lines.append(f"- État: {'🟢 Active' if custom.get('enabled') else '🔴 Désactivée'}")
        lines.append(f"- Prix de base: 💰 {format_cols(int(custom.get('base_price', DEFAULT_CUSTOM_PRICE)))} Cols")
        lines.append(f"- Max par joueur: 👤 {int(custom.get('max_per_user', 1))}")
        lines.append(f"- Max global: 🌍 {int(custom.get('max_total', 20))}")
        lines.append(f"- Rôles custom actuels: 🧩 {self.get_custom_roles_count(guild)}")

        lines.append("")
        lines.append("Options facturées:")
        lines.append(
            f"- 🎨 Couleur: {'🟢 Activée' if color_cfg.get('enabled', True) else '🔴 Désactivée'}"
            f" | +{int(color_cfg.get('pct', 10))}%"
        )
        lines.append(
            f"- 📌 Épinglé: {'🟢 Activée' if hoist_cfg.get('enabled', True) else '🔴 Désactivée'}"
            f" | +{int(hoist_cfg.get('pct', 10))}%"
        )
        lines.append(
            f"- 📣 Mentionnable: {'🟢 Activée' if mention_cfg.get('enabled', True) else '🔴 Désactivée'}"
            f" | +{int(mention_cfg.get('pct', 10))}%"
        )

        lines.append("")
        lines.append("Système d'ancrage:")
        lines.append(f"- 📍 Position: {custom.get('position', 'bottom')}")
        lines.append(f"- ⚓ Rôle ancre: {anchor_txt}")

        return "\n".join(lines)

    def build_admin_anchor_description(self, guild: discord.Guild) -> str:
        data = load_shop_config(guild.id)
        custom = data.get("custom", {})

        anchor_txt = "Aucun"
        if custom.get("anchor_role_id"):
            role = guild.get_role(int(custom["anchor_role_id"]))
            anchor_txt = role.mention if role else f"ID {custom['anchor_role_id']}"

        lines = []
        lines.append("Système d'ancrage")
        lines.append(f"- Position actuelle: 📍 {custom.get('position', 'bottom')}")
        lines.append(f"- Rôle ancre: ⚓ {anchor_txt}")
        lines.append("")
        lines.append("Comportement:")
        lines.append("- above: le rôle custom est placé juste au-dessus du rôle ancre.")
        lines.append("- below: le rôle custom est placé juste en-dessous du rôle ancre.")
        lines.append("- bottom: l'ancre est ignorée et le rôle reste en bas.")
        lines.append("")
        lines.append("Action disponible:")
        lines.append("- 📍 Définir position/ancre")
        return "\n".join(lines)

    def build_adminshop_description(self, guild: discord.Guild) -> str:
        # Compatibilite: vue globale legacy
        return self.build_admin_roles_description(guild) + "\n\n" + self.build_admin_custom_description(guild)

    def build_shop_description(self, guild: discord.Guild, user_id: Optional[int] = None) -> str:
        data = load_shop_config(guild.id)
        items = self.get_shop_items_sorted(guild.id)
        member = guild.get_member(user_id) if user_id is not None else None

        lines = []
        if user_id is not None:
            user_data = load_user_data(guild.id, user_id)
            lines.append(f"💳 Votre solde actuel: **{format_cols(int(user_data.get('Cols', 0)))} Cols**")
            lines.append("")

        if not items:
            lines.append("📭 Aucun rôle n'est en vente pour le moment.")
        else:
            lines.append("🛍️ Roles disponibles:")
            for idx, item in enumerate(items, start=1):
                role = guild.get_role(int(item["role_id"]))
                if role is None:
                    continue
                line = f"{idx}. {role.mention} - {format_cols(int(item['price']))} Cols"
                if member is not None and role in member.roles:
                    line = f"~~{line}~~"
                lines.append(line)

        return "\n".join(lines)

    def build_custom_shop_details(self, guild: discord.Guild) -> str:
        data = load_shop_config(guild.id)
        custom = data.get("custom", {})
        option_prices = custom.get("option_prices", {})
        color_cfg = option_prices.get("color", {"enabled": True, "pct": 10})
        hoist_cfg = option_prices.get("hoist", {"enabled": True, "pct": 10})
        mention_cfg = option_prices.get("mention", {"enabled": True, "pct": 10})

        def format_option(cfg: Dict, enabled_word: str = "désactivée") -> str:
            if cfg.get("enabled", True):
                return f"+{int(cfg.get('pct', 10))}%"
            return enabled_word

        lines = []
        lines.append("🧩 Custom actif:")
        lines.append("")
        lines.append(f"- Prix de base: 💰 {format_cols(int(custom.get('base_price', DEFAULT_CUSTOM_PRICE)))} Cols")
        lines.append(f"- Couleur: 🎨 {format_option(color_cfg, 'désactivée')}")
        lines.append(f"- Épinglé: 📌 {format_option(hoist_cfg, 'désactivé')}")
        lines.append(f"- Mentionnable: 📣 {format_option(mention_cfg, 'désactivé')}")
        lines.append(f"- Max roles custom par joueur: 👤 {int(custom.get('max_per_user', 1))}")
        lines.append(f"- Max roles custom globaux: 🌍 {int(custom.get('max_total', 20))}")
        lines.append(f"- Roles custom deja crees: 🧩 {self.get_custom_roles_count(guild)}")
        return "\n".join(lines)

    def perform_add_item(self, guild: discord.Guild, role: discord.Role, prix: int) -> str:
        if prix <= 0:
            return "❌ Le prix doit etre superieur a 0."

        data = load_shop_config(guild.id)
        items = data.get("items", [])

        if len(items) >= 25:
            return "❌ Limite atteinte: maximum 25 roles vendables dans le shop."

        if any(int(i["role_id"]) == role.id for i in items):
            return "❌ Ce role est deja dans le shop."

        owners_data = self.clean_missing_custom_roles(guild)
        owned_custom_ids = {
            int(rid)
            for role_ids in owners_data.get("owners", {}).values()
            for rid in role_ids
        }
        if role.id in owned_custom_ids:
            return "❌ Impossible: un rôle custom acheté ne peut pas être vendu dans le shop serveur."

        items.append({"role_id": role.id, "price": int(prix)})
        data["items"] = items
        save_shop_config(guild.id, data)
        return f"✅ Role {role.mention} ajoute au shop pour **{format_cols(prix)} Cols**."

    def perform_modify_item(self, guild: discord.Guild, index: int, prix: int, role: Optional[discord.Role]) -> str:
        data = load_shop_config(guild.id)
        items = data.get("items", [])

        if index < 1 or index > len(items):
            return "❌ Index invalide."
        if prix <= 0:
            return "❌ Le prix doit etre superieur a 0."

        item = items[index - 1]
        item["price"] = int(prix)
        if role is not None:
            item["role_id"] = role.id

        save_shop_config(guild.id, data)
        return "✅ Entree shop modifiee."

    def perform_delete_item(self, guild: discord.Guild, index: int) -> str:
        data = load_shop_config(guild.id)
        items = data.get("items", [])
        if index < 1 or index > len(items):
            return "❌ Index invalide."

        removed = items.pop(index - 1)
        save_shop_config(guild.id, data)
        removed_role = guild.get_role(int(removed["role_id"]))
        role_txt = removed_role.mention if removed_role else str(removed["role_id"])
        return f"✅ Entree retiree: {role_txt}."

    def perform_custom_toggle(self, guild: discord.Guild, mode: bool) -> str:
        data = load_shop_config(guild.id)
        data["custom"]["enabled"] = mode
        save_shop_config(guild.id, data)
        return f"✅ Option custom {'activee' if mode else 'desactivee'}."

    def perform_custom_price(self, guild: discord.Guild, prix: int) -> str:
        if prix <= 0:
            return "❌ Le prix doit etre superieur a 0."
        data = load_shop_config(guild.id)
        data["custom"]["base_price"] = int(prix)
        save_shop_config(guild.id, data)
        return f"✅ Prix custom defini a **{format_cols(prix)} Cols**."

    def perform_custom_anchor(self, guild: discord.Guild, position: str, role: Optional[discord.Role]) -> str:
        pos = position.strip().lower()
        aliases = {
            "bottom": "bottom",
            "dessous": "below",
            "below": "below",
            "dessus": "above",
            "above": "above",
        }
        if pos not in aliases:
            return "❌ Position invalide. Utilisez bottom, above/dessus ou below/dessous."

        mapped = aliases[pos]
        data = load_shop_config(guild.id)
        data["custom"]["position"] = mapped

        if mapped == "bottom":
            data["custom"]["anchor_role_id"] = None
            save_shop_config(guild.id, data)
            return "✅ Position custom definie tout en dessous."

        if role is None:
            return "❌ Vous devez fournir un rôle ancre pour above/below."

        data["custom"]["anchor_role_id"] = role.id
        save_shop_config(guild.id, data)
        return f"✅ Position custom: **{mapped}** {role.mention}."

    def perform_custom_max(self, guild: discord.Guild, maximum: int) -> str:
        if maximum < 1:
            return "❌ Le maximum doit etre au moins 1."
        data = load_shop_config(guild.id)
        data["custom"]["max_per_user"] = int(maximum)
        save_shop_config(guild.id, data)
        return f"✅ Maximum de roles custom par joueur: **{maximum}**."

    def perform_custom_max_total(self, guild: discord.Guild, maximum: int) -> str:
        if maximum < 1:
            return "❌ Le maximum global doit etre au moins 1."
        data = load_shop_config(guild.id)
        data["custom"]["max_total"] = int(maximum)
        save_shop_config(guild.id, data)
        return f"✅ Maximum global de roles custom: **{maximum}**."

    def perform_custom_feature(self, guild: discord.Guild, feature: str, enabled: bool, pct: int) -> str:
        if feature not in {"color", "hoist", "mention"}:
            return "❌ Option inconnue."
        if pct < 0:
            return "❌ Le pourcentage doit etre superieur ou egal a 0."

        labels = {
            "color": "couleur",
            "hoist": "épinglé",
            "mention": "mentionnable",
        }

        data = load_shop_config(guild.id)
        custom = data.setdefault("custom", {})
        option_prices = custom.setdefault("option_prices", {})
        cfg = option_prices.setdefault(feature, {"enabled": True, "pct": 10})
        cfg["enabled"] = bool(enabled)
        cfg["pct"] = int(pct)
        save_shop_config(guild.id, data)

        state = "activée" if enabled else "désactivée"
        return f"✅ Option {labels[feature]} {state} (surcoût: +{pct}%)."

    def get_custom_feature_cfg(self, custom_cfg: Dict, feature: str) -> Dict:
        option_prices = custom_cfg.get("option_prices", {})
        return option_prices.get(feature, {"enabled": True, "pct": 10})

    def compute_custom_price(self, base_price: int, custom_cfg: Dict, selected_features: List[str]) -> int:
        total = int(base_price)
        for feature in selected_features:
            cfg = self.get_custom_feature_cfg(custom_cfg, feature)
            if not cfg.get("enabled", True):
                continue
            pct = int(cfg.get("pct", 10))
            total += int(base_price * pct / 100)
        return total

        base_price = int(custom.get('base_price', DEFAULT_CUSTOM_PRICE))
        color_cost = int(base_price * int(color_cfg.get('pct', 10)) / 100)
        hoist_cost = int(base_price * int(hoist_cfg.get('pct', 10)) / 100)
        mention_cost = int(base_price * int(mention_cfg.get('pct', 10)) / 100)
        max_per_user = min(int(custom.get('max_per_user', 1)), 24)
        lines.append(f"💰 **Prix de base** : {format_cols(base_price)} Cols")
        lines.append(f"🎨 **Couleur** : {format_option(color_cfg)} • coût {format_cols(color_cost)} Cols")
        lines.append(f"📌 **Épinglé** : {format_option(hoist_cfg, 'désactivé')} • coût {format_cols(hoist_cost)} Cols")
        lines.append(f"📣 **Mentionnable** : {format_option(mention_cfg, 'désactivé')} • coût {format_cols(mention_cost)} Cols")
        lines.append(f"👤 **Max rôles custom par joueur** : {max_per_user}")
        lines.append(f"🌍 **Max rôles custom globaux** : {int(custom.get('max_total', 20))}")
        lines.append(f"🧩 **Rôles custom déjà créés** : {self.get_custom_roles_count(guild)}")
    async def perform_custom_create(
        self,
        member: discord.Member,
        role_name: str,
        selected_features: List[str],
        color_hex: Optional[str],
    ) -> str:
        guild = member.guild
        data = load_shop_config(guild.id)
        custom = data.get("custom", {})
        if not custom.get("enabled", False):
            return "❌ L'option custom est désactivée sur ce serveur."

        role_name = role_name.strip()
        if not role_name:
            return "❌ Le nom du rôle est obligatoire."
        if len(role_name) > 100:
            return "❌ Le nom du rôle ne peut pas dépasser 100 caractères."

        owners_data = self.clean_missing_custom_roles(guild)
        owners = owners_data.get("owners", {})
        user_key = str(member.id)
        user_roles = [int(rid) for rid in owners.get(user_key, []) if guild.get_role(int(rid))]
        max_per_user = min(int(custom.get("max_per_user", 1)), 24)
        if len(user_roles) >= max_per_user:
            return "❌ Vous avez atteint le maximum de rôles custom autorisés."

        total_current = self.get_custom_roles_count(guild)
        max_total = int(custom.get("max_total", 20))
        if total_current >= max_total:
            return "❌ Limite globale atteinte: aucun nouveau rôle custom ne peut être créé."

        normalized_features = []
        for feature in selected_features:
            if feature in {"color", "hoist", "mention"} and feature not in normalized_features:
                cfg = self.get_custom_feature_cfg(custom, feature)
                if not cfg.get("enabled", True):
                    return f"❌ L'option {feature} est désactivée sur ce serveur."
                normalized_features.append(feature)

        color_obj = None
        if "color" in normalized_features:
            if color_hex:
                color_obj = parse_hex_color(color_hex)
                if color_obj is None:
                    return "❌ Couleur invalide. Utilisez un format HEX #RRGGBB."
            else:
                color_obj = discord.Colour.default()

        base_price = int(custom.get("base_price", DEFAULT_CUSTOM_PRICE))
        final_price = self.compute_custom_price(base_price, custom, normalized_features)

        user_data = load_user_data(guild.id, member.id)
        current_cols = int(user_data.get("Cols", 0))
        if current_cols < final_price:
            return f"❌ Il vous faut **{format_cols(final_price)} Cols** (vous avez {format_cols(current_cols)})."

        try:
            new_role = await guild.create_role(
                name=role_name,
                colour=color_obj if color_obj else discord.Colour.default(),
                mentionable="mention" in normalized_features,
                hoist="hoist" in normalized_features,
                reason=f"Role custom acheté par {member}",
            )
        except discord.Forbidden:
            return "❌ Je ne peux pas créer de rôle (permissions manquantes)."

        try:
            await self.move_role_if_needed(guild, new_role, custom)
            await member.add_roles(new_role, reason="Achat rôle custom")
        except discord.Forbidden:
            try:
                await new_role.delete(reason="Rollback achat custom")
            except discord.HTTPException:
                pass
            return "❌ Je ne peux pas attribuer/positionner ce rôle (hiérarchie/perms)."

        user_data["Cols"] = current_cols - final_price
        save_user_data(guild.id, member.id, user_data)

        owners.setdefault(user_key, [])
        owners[user_key].append(new_role.id)
        owners_data["owners"] = owners
        self.set_role_options_state(
            owners_data,
            new_role.id,
            {
                "color": "color" in normalized_features,
                "hoist": "hoist" in normalized_features,
                "mention": "mention" in normalized_features,
            },
        )
        save_custom_owners(guild.id, owners_data)

        return (
            f"✅ 🧩 Rôle custom créé: {new_role.mention}\n"
            f"- 💰 Prix payé: **{format_cols(final_price)} Cols**\n"
            f"- 🪙 Nouveau solde: **{format_cols(user_data['Cols'])} Cols**"
        )

    async def perform_custom_upgrade(
        self,
        member: discord.Member,
        role_id: int,
        selected_features: List[str],
        color_hex: Optional[str],
    ) -> str:
        guild = member.guild
        role = guild.get_role(int(role_id))
        if role is None:
            return "❌ Rôle introuvable."

        data = load_shop_config(guild.id)
        custom = data.get("custom", {})
        if not custom.get("enabled", False):
            return "❌ L'option custom est désactivée sur ce serveur."

        owners_data = self.clean_missing_custom_roles(guild)
        owners = owners_data.get("owners", {})
        user_roles = [int(rid) for rid in owners.get(str(member.id), [])]
        if role.id not in user_roles:
            return "❌ Ce rôle custom ne vous appartient pas."

        current_state = self.get_role_options_state(owners_data, role.id)
        to_apply = []
        for feature in selected_features:
            if feature not in {"color", "hoist", "mention"}:
                continue
            if current_state.get(feature, False):
                continue
            cfg = self.get_custom_feature_cfg(custom, feature)
            if not cfg.get("enabled", True):
                return f"❌ L'option {feature} est désactivée sur ce serveur."
            to_apply.append(feature)

        if not to_apply:
            return "❌ Aucune nouvelle option à acheter."

        new_color = role.colour
        if "color" in to_apply:
            if not color_hex:
                return "❌ Vous devez fournir une couleur HEX pour l'option couleur."
            parsed = parse_hex_color(color_hex)
            if parsed is None:
                return "❌ Couleur invalide. Utilisez un format HEX #RRGGBB."
            new_color = parsed

        base_price = int(custom.get("base_price", DEFAULT_CUSTOM_PRICE))
        upgrade_price = self.compute_custom_price(base_price, custom, to_apply) - base_price

        user_data = load_user_data(guild.id, member.id)
        current_cols = int(user_data.get("Cols", 0))
        if current_cols < upgrade_price:
            return f"❌ Il vous faut **{format_cols(upgrade_price)} Cols** (vous avez {format_cols(current_cols)})."

        try:
            await role.edit(
                colour=new_color,
                mentionable=role.mentionable or ("mention" in to_apply),
                hoist=role.hoist or ("hoist" in to_apply),
                reason=f"Upgrade rôle custom par {member}",
            )
        except discord.Forbidden:
            return "❌ Je ne peux pas modifier ce rôle (hiérarchie/perms)."

        user_data["Cols"] = current_cols - upgrade_price
        save_user_data(guild.id, member.id, user_data)

        current_state["color"] = current_state["color"] or ("color" in to_apply)
        current_state["hoist"] = current_state["hoist"] or ("hoist" in to_apply)
        current_state["mention"] = current_state["mention"] or ("mention" in to_apply)
        self.set_role_options_state(owners_data, role.id, current_state)
        save_custom_owners(guild.id, owners_data)

        return (
            f"✅ ✨ Options achetées pour {role.mention}: {', '.join(to_apply)}\n"
            f"- 💰 Prix payé: **{format_cols(upgrade_price)} Cols**\n"
            f"- 🪙 Nouveau solde: **{format_cols(user_data['Cols'])} Cols**"
        )

    async def perform_shop_buy(self, member: discord.Member, index: int) -> str:
        guild = member.guild
        items = self.get_shop_items_sorted(guild.id)

        if index < 1 or index > len(items):
            return "❌ Index invalide."

        item = items[index - 1]
        role = guild.get_role(int(item["role_id"]))
        if role is None:
            return "❌ Ce role n'existe plus, demandez une mise a jour du shop."

        if role in member.roles:
            return "❌ Vous possedez deja ce role."

        user_data = load_user_data(guild.id, member.id)
        price = int(item["price"])
        current_cols = int(user_data.get("Cols", 0))
        if current_cols < price:
            return f"❌ Il vous faut **{format_cols(price)} Cols** (vous avez {format_cols(current_cols)})."

        try:
            await member.add_roles(role, reason="Achat shop")
        except discord.Forbidden:
            return "❌ Je ne peux pas attribuer ce role (hierarchie/perms)."

        user_data["Cols"] = current_cols - price
        save_user_data(guild.id, member.id, user_data)
        return (
            f"✅ Achat valide: {role.mention} pour **{format_cols(price)} Cols**. "
            f"Nouveau solde: **{format_cols(user_data['Cols'])} Cols**."
        )

    async def perform_shop_buy_by_role(self, member: discord.Member, role_id: int) -> str:
        guild = member.guild
        role = guild.get_role(role_id)
        if role is None:
            return "❌ Ce role n'existe plus, demandez une mise a jour du shop."

        item = next((i for i in self.get_shop_items_sorted(guild.id) if int(i.get("role_id", 0)) == role_id), None)
        if item is None:
            return "❌ Ce role n'est pas en vente."
        if role in member.roles:
            return "❌ Vous possedez deja ce role."

        user_data = load_user_data(guild.id, member.id)
        price = int(item["price"])
        current_cols = int(user_data.get("Cols", 0))
        if current_cols < price:
            return f"❌ Il vous faut **{format_cols(price)} Cols** (vous avez {format_cols(current_cols)})."

        try:
            await member.add_roles(role, reason="Achat shop")
        except discord.Forbidden:
            return "❌ Je ne peux pas attribuer ce role (hierarchie/perms)."

        user_data["Cols"] = current_cols - price
        save_user_data(guild.id, member.id, user_data)
        return (
            f"✅ Achat valide: {role.mention} pour **{format_cols(price)} Cols**. "
            f"Nouveau solde: **{format_cols(user_data['Cols'])} Cols**."
        )

    async def perform_custom_buy(self, member: discord.Member, options: str) -> str:
        name, color_raw, notify, pinned, error = parse_custom_input(options)
        if error:
            return (
                "❌ "
                + error
                + "\nFormat: `Nom du rôle;#ff8800;oui;non` (couleur/notifier/épinglé optionnels)."
            )

        selected_features = []
        if color_raw:
            selected_features.append("color")
        if pinned:
            selected_features.append("hoist")
        if notify:
            selected_features.append("mention")

        return await self.perform_custom_create(member, name, selected_features, color_raw)

    async def perform_custom_rename(self, member: discord.Member, role_id: int, new_name: str) -> str:
        if len(new_name) > 100:
            return "❌ Le nom du role ne peut pas depasser 100 caracteres."

        guild = member.guild
        role = guild.get_role(role_id)
        if role is None:
            return "❌ Role introuvable."

        owners_data = load_custom_owners(guild.id)
        owners_data = self.prune_owner_roles(guild, owners_data)
        owners = owners_data.get("owners", {})
        user_roles = [int(rid) for rid in owners.get(str(member.id), [])]

        if role.id not in user_roles:
            return "❌ Ce role custom ne vous appartient pas."

        try:
            await role.edit(name=new_name, reason=f"Renommage par {member}")
        except discord.Forbidden:
            return "❌ Je ne peux pas renommer ce role (hierarchie/perms)."

        save_custom_owners(guild.id, owners_data)
        return f"✅ 📝 Votre rôle custom a été renommé en **{new_name}**."

    async def perform_custom_set_color(self, member: discord.Member, role_id: int, color_hex: str) -> str:
        guild = member.guild
        role = guild.get_role(int(role_id))
        if role is None:
            return "❌ Rôle introuvable."

        owners_data = self.clean_missing_custom_roles(guild)
        owners = owners_data.get("owners", {})
        user_roles = [int(rid) for rid in owners.get(str(member.id), [])]
        if role.id not in user_roles:
            return "❌ Ce rôle custom ne vous appartient pas."

        state = self.get_role_options_state(owners_data, role.id)
        if not state.get("color", False):
            return "❌ Vous devez d'abord acheter l'option 🎨 Couleur."

        parsed = parse_hex_color(color_hex)
        if parsed is None:
            return "❌ Couleur invalide. Utilisez un format HEX #RRGGBB."

        try:
            await role.edit(colour=parsed, reason=f"Changement couleur par {member}")
        except discord.Forbidden:
            return "❌ Je ne peux pas modifier ce rôle (hiérarchie/perms)."

        return f"✅ 🎨 Couleur mise à jour pour {role.mention}."

    async def perform_custom_toggle_setting(self, member: discord.Member, role_id: int, feature: str) -> str:
        if feature not in {"hoist", "mention"}:
            return "❌ Option de gestion invalide."

        labels = {
            "hoist": "📌 Épinglé",
            "mention": "📣 Mentionnable",
        }

        guild = member.guild
        role = guild.get_role(int(role_id))
        if role is None:
            return "❌ Rôle introuvable."

        owners_data = self.clean_missing_custom_roles(guild)
        owners = owners_data.get("owners", {})
        user_roles = [int(rid) for rid in owners.get(str(member.id), [])]
        if role.id not in user_roles:
            return "❌ Ce rôle custom ne vous appartient pas."

        state = self.get_role_options_state(owners_data, role.id)
        if not state.get(feature, False):
            return f"❌ Vous devez d'abord acheter l'option {labels[feature]}."

        try:
            if feature == "hoist":
                new_value = not role.hoist
                await role.edit(hoist=new_value, reason=f"Mise à jour épinglé par {member}")
            else:
                new_value = not role.mentionable
                await role.edit(mentionable=new_value, reason=f"Mise à jour mention par {member}")
        except discord.Forbidden:
            return "❌ Je ne peux pas modifier ce rôle (hiérarchie/perms)."

        return f"✅ {labels[feature]} {'activé' if new_value else 'désactivé'} pour {role.mention}."

    @commands.command(name="adminshop", help="Gérer la boutique administrateur du serveur.")
    @commands.has_permissions(administrator=True)
    async def adminshop(self, ctx: commands.Context):
        view = AdminShopView(self, ctx.author.id, ctx.guild)
        embed = view.get_current_embed()
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    async def adminshop_add(self, ctx: commands.Context, role: discord.Role, prix: int):
        await ctx.send(self.perform_add_item(ctx.guild, role, prix))

    async def adminshop_modify(self, ctx: commands.Context, index: int, prix: int, role: Optional[discord.Role] = None):
        await ctx.send(self.perform_modify_item(ctx.guild, index, prix, role))

    async def adminshop_delete(self, ctx: commands.Context, index: int):
        await ctx.send(self.perform_delete_item(ctx.guild, index))

    async def adminshop_customtoggle(self, ctx: commands.Context, mode: str):
        parsed = parse_on_off(mode)
        if parsed is None:
            return await ctx.send("❌ Utilisez on/off (ou oui/non).")
        await ctx.send(self.perform_custom_toggle(ctx.guild, parsed))

    async def adminshop_customprice(self, ctx: commands.Context, prix: int):
        await ctx.send(self.perform_custom_price(ctx.guild, prix))

    async def adminshop_customanchor(self, ctx: commands.Context, position: str, role: Optional[discord.Role] = None):
        await ctx.send(self.perform_custom_anchor(ctx.guild, position, role))

    async def adminshop_custommax(self, ctx: commands.Context, maximum: int):
        await ctx.send(self.perform_custom_max(ctx.guild, maximum))

    async def adminshop_custommaxtotal(self, ctx: commands.Context, maximum: int):
        await ctx.send(self.perform_custom_max_total(ctx.guild, maximum))

    @commands.hybrid_command(name="shop", description="Consulter la boutique du serveur.")
    async def shop(self, ctx: commands.Context):
        self.clean_missing_custom_roles(ctx.guild)
        view = ShopUserView(self, ctx.author.id, ctx.guild)
        embed = self.make_embed(ctx, "🛒 Shop du serveur", self.build_shop_description(ctx.guild, ctx.author.id))
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    async def shop_buy(self, ctx: commands.Context, index: int):
        await ctx.send(await self.perform_shop_buy(ctx.author, index))

    async def shop_custom(self, ctx: commands.Context, *, options: str):
        await ctx.send(await self.perform_custom_buy(ctx.author, options))

    async def shop_rename_role(self, ctx: commands.Context, role_id: int, *, new_name: str):
        await ctx.send(await self.perform_custom_rename(ctx.author, role_id, new_name))


class BaseShopView(ui.View):
    def __init__(self, cog: ShopCog, owner_id: int, guild: discord.Guild):
        super().__init__(timeout=300)
        self.cog = cog
        self.owner_id = owner_id
        self.guild = guild
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("❌ Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass


class AdminShopAddModal(ui.Modal, title="Ajouter un rôle au shop"):
    role_id = ui.TextInput(label="Role ID", placeholder="ID du role a vendre", required=True)
    price = ui.TextInput(label="Prix", placeholder="Ex: 250000", required=True)

    def __init__(self, view: "AdminShopView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        if not self.role_id.value.isdigit() or not self.price.value.isdigit():
            return await interaction.response.send_message("❌ Role ID ou prix invalide.", ephemeral=True)
        role = interaction.guild.get_role(int(self.role_id.value))
        if role is None:
            return await interaction.response.send_message("❌ Role introuvable.", ephemeral=True)
        result = self.view.cog.perform_add_item(interaction.guild, role, int(self.price.value))
        await interaction.response.send_message(result, ephemeral=True)
        await self.view.refresh_message()


class AdminShopModifyModal(ui.Modal, title="Modifier une entrée shop"):
    index = ui.TextInput(label="Index", placeholder="Ex: 1", required=True)
    price = ui.TextInput(label="Nouveau prix", placeholder="Ex: 500000", required=True)
    role_id = ui.TextInput(label="Nouveau role ID (optionnel)", required=False)

    def __init__(self, view: "AdminShopView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        if not self.index.value.isdigit() or not self.price.value.isdigit():
            return await interaction.response.send_message("❌ Index/prix invalide.", ephemeral=True)

        role_obj = None
        role_id_txt = self.role_id.value.strip()
        if role_id_txt:
            if not role_id_txt.isdigit():
                return await interaction.response.send_message("❌ Role ID invalide.", ephemeral=True)
            role_obj = interaction.guild.get_role(int(role_id_txt))
            if role_obj is None:
                return await interaction.response.send_message("❌ Role introuvable.", ephemeral=True)

        result = self.view.cog.perform_modify_item(
            interaction.guild,
            int(self.index.value),
            int(self.price.value),
            role_obj,
        )
        await interaction.response.send_message(result, ephemeral=True)
        await self.view.refresh_message()


class AdminShopDeleteModal(ui.Modal, title="Supprimer une entrée shop"):
    index = ui.TextInput(label="Index", placeholder="Ex: 1", required=True)

    def __init__(self, view: "AdminShopView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        if not self.index.value.isdigit():
            return await interaction.response.send_message("❌ Index invalide.", ephemeral=True)
        result = self.view.cog.perform_delete_item(interaction.guild, int(self.index.value))
        await interaction.response.send_message(result, ephemeral=True)
        await self.view.refresh_message()


class AdminCustomPriceModal(ui.Modal, title="Prix custom"):
    price = ui.TextInput(label="Prix de base", placeholder="Ex: 1000000000", required=True)

    def __init__(self, view: "AdminShopView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        if not self.price.value.isdigit():
            return await interaction.response.send_message("❌ Prix invalide.", ephemeral=True)
        result = self.view.cog.perform_custom_price(interaction.guild, int(self.price.value))
        await interaction.response.send_message(result, ephemeral=True)
        await self.view.refresh_message()


class AdminCustomFeatureModal(ui.Modal):
    enabled = ui.TextInput(label="Activer ? (oui/non)", placeholder="oui", required=True)
    percent = ui.TextInput(label="Surcoût en %", placeholder="Ex: 10", required=True)

    def __init__(self, view: "AdminShopView", feature: str, title_txt: str):
        super().__init__(title=title_txt)
        self.view = view
        self.feature = feature

    async def on_submit(self, interaction: discord.Interaction):
        parsed_enabled = parse_yes_no(self.enabled.value)
        if parsed_enabled is None:
            return await interaction.response.send_message("❌ Valeur invalide pour l'état (oui/non).", ephemeral=True)
        if not self.percent.value.isdigit():
            return await interaction.response.send_message("❌ Pourcentage invalide.", ephemeral=True)

        result = self.view.cog.perform_custom_feature(
            interaction.guild,
            self.feature,
            parsed_enabled,
            int(self.percent.value),
        )
        await interaction.response.send_message(result, ephemeral=True)
        await self.view.refresh_message()


class AdminCustomMaxModal(ui.Modal, title="Max custom par joueur"):
    max_count = ui.TextInput(label="Maximum", placeholder="Ex: 1", required=True)

    def __init__(self, view: "AdminShopView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        if not self.max_count.value.isdigit():
            return await interaction.response.send_message("❌ Valeur invalide.", ephemeral=True)
        result = self.view.cog.perform_custom_max(interaction.guild, int(self.max_count.value))
        await interaction.response.send_message(result, ephemeral=True)
        await self.view.refresh_message()


class AdminCustomMaxTotalModal(ui.Modal, title="Max custom global"):
    max_count = ui.TextInput(label="Maximum global", placeholder="Ex: 20", required=True)

    def __init__(self, view: "AdminShopView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        if not self.max_count.value.isdigit():
            return await interaction.response.send_message("❌ Valeur invalide.", ephemeral=True)
        result = self.view.cog.perform_custom_max_total(interaction.guild, int(self.max_count.value))
        await interaction.response.send_message(result, ephemeral=True)
        await self.view.refresh_message()


class AdminCustomAnchorModal(ui.Modal, title="Position role custom"):
    position = ui.TextInput(label="Position", placeholder="bottom / above / below", required=True)
    role_id = ui.TextInput(label="Role ID ancre (si above/below)", required=False)

    def __init__(self, view: "AdminShopView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        role_obj = None
        role_id_txt = self.role_id.value.strip()
        if role_id_txt:
            if not role_id_txt.isdigit():
                return await interaction.response.send_message("❌ Role ID invalide.", ephemeral=True)
            role_obj = interaction.guild.get_role(int(role_id_txt))
            if role_obj is None:
                return await interaction.response.send_message("❌ Role ancre introuvable.", ephemeral=True)

        result = self.view.cog.perform_custom_anchor(interaction.guild, self.position.value, role_obj)
        await interaction.response.send_message(result, ephemeral=True)
        await self.view.refresh_message()


class AdminRoleConfigSelect(ui.Select):
    def __init__(self, view: "AdminShopView"):
        self.admin_view = view
        options = [
            discord.SelectOption(
                label="Ajouter un rôle",
                value="add",
                emoji="➕",
                description="Ajoute un rôle configuré au shop",
            ),
            discord.SelectOption(
                label="Modifier une entrée",
                value="modify",
                emoji="✏️",
                description="Change le prix ou le rôle d'une entrée",
            ),
            discord.SelectOption(
                label="Supprimer une entrée",
                value="delete",
                emoji="🗑️",
                description="Retire une entrée de la liste des rôles",
            ),
        ]
        super().__init__(
            placeholder="🎭 Menu rôles configurés",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        action = self.values[0]
        if action == "add":
            return await interaction.response.send_modal(AdminShopAddModal(self.admin_view))
        if action == "modify":
            return await interaction.response.send_modal(AdminShopModifyModal(self.admin_view))
        return await interaction.response.send_modal(AdminShopDeleteModal(self.admin_view))


class AdminCustomConfigSelect(ui.Select):
    def __init__(self, view: "AdminShopView"):
        self.admin_view = view
        options = [
            discord.SelectOption(
                label="Activer/Désactiver custom",
                value="toggle",
                emoji="⚙️",
                description="Bascule l'etat de la fonctionnalite custom",
            ),
            discord.SelectOption(
                label="Prix custom",
                value="custom_price",
                emoji="💰",
                description="Definit le prix de base des roles custom",
            ),
            discord.SelectOption(
                label="Option couleur",
                value="opt_color",
                emoji="🎨",
                description="Active/désactive et définit le surcoût couleur",
            ),
            discord.SelectOption(
                label="Option épinglé",
                value="opt_hoist",
                emoji="📌",
                description="Active/désactive et définit le surcoût épinglé",
            ),
            discord.SelectOption(
                label="Option mentionnable",
                value="opt_mention",
                emoji="📣",
                description="Active/désactive et définit le surcoût mentionnable",
            ),
            discord.SelectOption(
                label="Max par joueur",
                value="custom_max",
                emoji="👤",
                description="Nombre max de roles custom pour un joueur",
            ),
            discord.SelectOption(
                label="Max global",
                value="custom_max_total",
                emoji="🌍",
                description="Nombre max total de roles custom serveur",
            ),
        ]
        super().__init__(
            placeholder="🧩 Menu options custom",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        action = self.values[0]
        if action == "toggle":
            cfg = load_shop_config(interaction.guild.id)
            now_enabled = bool(cfg.get("custom", {}).get("enabled", False))
            result = self.admin_view.cog.perform_custom_toggle(interaction.guild, not now_enabled)
            await interaction.response.send_message(result, ephemeral=True)
            return await self.admin_view.refresh_message()
        if action == "custom_price":
            return await interaction.response.send_modal(AdminCustomPriceModal(self.admin_view))
        if action == "opt_color":
            return await interaction.response.send_modal(AdminCustomFeatureModal(self.admin_view, "color", "Option couleur"))
        if action == "opt_hoist":
            return await interaction.response.send_modal(AdminCustomFeatureModal(self.admin_view, "hoist", "Option épinglé"))
        if action == "opt_mention":
            return await interaction.response.send_modal(AdminCustomFeatureModal(self.admin_view, "mention", "Option mentionnable"))
        if action == "custom_max":
            return await interaction.response.send_modal(AdminCustomMaxModal(self.admin_view))
        return await interaction.response.send_modal(AdminCustomMaxTotalModal(self.admin_view))


class AdminAnchorConfigSelect(ui.Select):
    def __init__(self, view: "AdminShopView"):
        self.admin_view = view
        options = [
            discord.SelectOption(
                label="Définir position/ancre",
                value="custom_anchor",
                emoji="📍",
                description="Règle bottom/above/below et le rôle ancre",
            ),
        ]
        super().__init__(
            placeholder="📍 Menu système d'ancrage",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        return await interaction.response.send_modal(AdminCustomAnchorModal(self.admin_view))


class AdminMainSectionSelect(ui.Select):
    def __init__(self, view: "AdminShopView", current_section: str):
        self.admin_view = view
        options = [
            discord.SelectOption(
                label="Système d'encrage",
                value="anchor_system",
                emoji="📍",
                description="Configuration de la position et du rôle ancre",
                default=current_section == "anchor_system",
            ),
            discord.SelectOption(
                label="Configuration rôles serveur",
                value="server_roles",
                emoji="🎭",
                description="Gestion des roles en vente: ajouter/modifier/supprimer",
                default=current_section == "server_roles",
            ),
            discord.SelectOption(
                label="Configuration rôles custom",
                value="custom_roles",
                emoji="🧩",
                description="Gestion de l'option custom: état, prix, limites, options",
                default=current_section == "custom_roles",
            ),
        ]
        super().__init__(
            placeholder="🗂️ Menu principal configuration",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        self.admin_view.current_section = self.values[0]
        await self.admin_view.refresh_message(interaction)


class AdminShopView(BaseShopView):
    def __init__(self, cog: ShopCog, owner_id: int, guild: discord.Guild):
        super().__init__(cog, owner_id, guild)
        self.current_section = "anchor_system"
        self.rebuild_items()

    def get_current_embed(self) -> discord.Embed:
        member = self.guild.get_member(self.owner_id)
        if self.current_section == "anchor_system":
            title = "📍 Système d'ancrage"
            description = self.cog.build_admin_anchor_description(self.guild)
        elif self.current_section == "custom_roles":
            title = "🧩 Configuration rôles custom"
            description = self.cog.build_admin_custom_description(self.guild)
        else:
            title = "🎭 Configuration rôles serveur"
            description = self.cog.build_admin_roles_description(self.guild)
        return self.cog.make_embed_for_user(self.guild, member, title, description)

    def rebuild_items(self):
        self.clear_items()
        self.add_item(AdminMainSectionSelect(self, self.current_section))
        if self.current_section == "anchor_system":
            self.add_item(AdminAnchorConfigSelect(self))
        elif self.current_section == "custom_roles":
            self.add_item(AdminCustomConfigSelect(self))
        else:
            self.add_item(AdminRoleConfigSelect(self))

    async def refresh_message(self, interaction: Optional[discord.Interaction] = None):
        if not self.message:
            return
        self.rebuild_items()
        embed = self.get_current_embed()
        try:
            if interaction and not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=self)
            else:
                await self.message.edit(embed=embed, view=self)
        except discord.HTTPException:
            pass


class ShopBuySelect(ui.Select):
    def __init__(self, view: "ShopUserView"):
        self.shop_view = view
        member = view.guild.get_member(view.owner_id)
        items = view.cog.get_buyable_shop_items(member) if member else []
        options = []
        for item in items:
            role = view.guild.get_role(int(item["role_id"]))
            if role is None:
                continue
            options.append(
                discord.SelectOption(
                    label=role.name,
                    description=f"{format_cols(int(item['price']))} Cols",
                    emoji="🛒",
                    value=str(role.id),
                )
            )
            if len(options) >= 25:
                break

        super().__init__(placeholder="🛍️ Acheter un rôle...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        result = await self.shop_view.cog.perform_shop_buy_by_role(interaction.user, int(self.values[0]))
        await interaction.response.send_message(result, ephemeral=True)
        await self.shop_view.refresh_message()


class ShopCustomCreateModal(ui.Modal, title="Créer un rôle custom"):
    role_name = ui.TextInput(label="Nom du rôle", placeholder="Ex: Elite Rouge", required=True)

    def __init__(self, view: "CustomRoleManageView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            result = await self.view.cog.perform_custom_create(
                interaction.user,
                self.role_name.value,
                self.view.selected_features,
                None,
            )
        except Exception as exc:
            await interaction.followup.send(
                f"❌ La création du rôle custom a échoué: `{type(exc).__name__}` - {exc}",
                ephemeral=True,
            )
            return

        await interaction.followup.send(result, ephemeral=True)

        try:
            await self.view.refresh_message()
        except Exception as exc:
            await interaction.followup.send(
                f"⚠️ Le rôle a été créé, mais le menu n'a pas pu se rafraîchir: `{type(exc).__name__}` - {exc}",
                ephemeral=True,
            )


class ShopCustomUpgradeColorModal(ui.Modal, title="Couleur option custom"):
    color = ui.TextInput(label="Couleur HEX", placeholder="#ff8800", required=True, min_length=7, max_length=7)

    def __init__(self, view: "CustomRoleManageView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        result = await self.view.cog.perform_custom_upgrade(
            interaction.user,
            int(self.view.selected_role_id),
            self.view.selected_features,
            self.color.value.strip(),
        )
        await interaction.followup.send(result, ephemeral=True)
        await self.view.refresh_message()


class ShopCustomRenameModal(ui.Modal, title="Renommer le rôle custom"):
    new_name = ui.TextInput(label="Nouveau nom", placeholder="Ex: Rouge Elite", required=True, max_length=100)

    def __init__(self, view: "CustomRoleManageView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if self.view.selected_role_id is None:
            return await interaction.followup.send("❌ Sélectionnez un rôle custom.", ephemeral=True)
        result = await self.view.cog.perform_custom_rename(
            interaction.user,
            int(self.view.selected_role_id),
            self.new_name.value,
        )
        await interaction.followup.send(result, ephemeral=True)
        await self.view.refresh_message()


class ShopCustomSetColorModal(ui.Modal, title="Changer la couleur"):
    color = ui.TextInput(label="Couleur HEX", placeholder="#ff8800", required=True, min_length=7, max_length=7)

    def __init__(self, view: "CustomRoleManageView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if self.view.selected_role_id is None:
            return await interaction.followup.send("❌ Sélectionnez un rôle custom.", ephemeral=True)
        result = await self.view.cog.perform_custom_set_color(
            interaction.user,
            int(self.view.selected_role_id),
            self.color.value.strip(),
        )
        await interaction.followup.send(result, ephemeral=True)
        await self.view.refresh_message()


class CustomRoleTargetSelect(ui.Select):
    def __init__(self, view: "CustomRoleManageView", roles: List[discord.Role], allow_create: bool):
        self.custom_view = view
        data = load_shop_config(view.guild.id)
        custom_cfg = data.get("custom", {})
        base_price = int(custom_cfg.get("base_price", DEFAULT_CUSTOM_PRICE))

        options = []
        if allow_create:
            options.append(
                discord.SelectOption(
                    label="Créer / acheter un rôle custom",
                    value="create_custom",
                    emoji="🛒",
                    description=f"Prix de base : {format_cols(base_price)} Cols",
                )
            )

        options.extend(
            discord.SelectOption(
                label=role.name[:100],
                value=str(role.id),
                emoji="🧩",
                description=f"ID {role.id}",
                default=view.selected_role_id == role.id,
            )
            for role in roles
        )
        super().__init__(
            placeholder="🧩 Choisir un rôle custom à gérer",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "create_custom":
            self.custom_view.selected_role_id = None
            return await interaction.response.send_modal(ShopCustomCreateModal(self.custom_view))

        self.custom_view.selected_role_id = int(self.values[0])
        self.custom_view.selected_features = []
        await self.custom_view.refresh_message(interaction)


class CustomFeatureSelect(ui.Select):
    def __init__(self, view: "CustomRoleManageView", available_features: List[str]):
        self.custom_view = view
        data = load_shop_config(view.guild.id)
        custom_cfg = data.get("custom", {})
        base_price = int(custom_cfg.get("base_price", DEFAULT_CUSTOM_PRICE))
        option_prices = custom_cfg.get("option_prices", {})
        color_pct = int(option_prices.get("color", {"pct": 10}).get("pct", 10))
        hoist_pct = int(option_prices.get("hoist", {"pct": 10}).get("pct", 10))
        mention_pct = int(option_prices.get("mention", {"pct": 10}).get("pct", 10))
        labels = {
            "color": (
                "Couleur",
                "🎨",
                f"Choisir une couleur personnalisée • {format_cols(int(base_price * color_pct / 100))} Cols",
            ),
            "hoist": (
                "Épinglé",
                "📌",
                f"Afficher le rôle séparé • {format_cols(int(base_price * hoist_pct / 100))} Cols",
            ),
            "mention": (
                "Mentionnable",
                "📣",
                f"Autoriser tout le monde à le taguer • {format_cols(int(base_price * mention_pct / 100))} Cols",
            ),
        }
        options = []
        for feature in available_features:
            label, emoji, desc = labels[feature]
            options.append(
                discord.SelectOption(
                    label=label,
                    value=feature,
                    emoji=emoji,
                    description=desc,
                    default=feature in view.selected_features,
                )
            )

        super().__init__(
            placeholder="🧾 Choisir les options à acheter",
            min_values=0,
            max_values=len(options),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        self.custom_view.selected_features = list(self.values)
        await self.custom_view.refresh_message(interaction)


class CustomRoleActionSelect(ui.Select):
    def __init__(self, view: "CustomRoleManageView", available_features: List[str]):
        self.custom_view = view

        options = [
            discord.SelectOption(
                label="Renommer",
                value="rename",
                emoji="📝",
                description="Changer le nom du rôle",
            ),
        ]

        if "color" in available_features:
            options.append(
                discord.SelectOption(
                    label="Changer couleur",
                    value="color",
                    emoji="🎨",
                    description="Modifier la couleur du rôle",
                )
            )
        if "hoist" in available_features:
            options.append(
                discord.SelectOption(
                    label="Activer/Désactiver l'épinglé",
                    value="hoist",
                    emoji="📌",
                    description="Basculer l'affichage séparé du rôle",
                )
            )
        if "mention" in available_features:
            options.append(
                discord.SelectOption(
                    label="Activer/Désactiver mention",
                    value="mention",
                    emoji="📣",
                    description="Basculer la possibilité de taguer le rôle",
                )
            )

        super().__init__(
            placeholder="🛠️ Gérer le rôle sélectionné",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        action = self.values[0]
        if action == "rename":
            return await interaction.response.send_modal(ShopCustomRenameModal(self.custom_view))
        if action == "color":
            return await interaction.response.send_modal(ShopCustomSetColorModal(self.custom_view))
        if action == "hoist":
            result = await self.custom_view.cog.perform_custom_toggle_setting(
                interaction.user,
                int(self.custom_view.selected_role_id),
                "hoist",
            )
        else:
            result = await self.custom_view.cog.perform_custom_toggle_setting(
                interaction.user,
                int(self.custom_view.selected_role_id),
                "mention",
            )
        await interaction.response.send_message(result, ephemeral=True)
        await self.custom_view.refresh_message()


class CustomRoleManageView(BaseShopView):
    def __init__(self, cog: ShopCog, owner_id: int, guild: discord.Guild, parent_view: "ShopUserView"):
        super().__init__(cog, owner_id, guild)
        self.parent_view = parent_view
        self.selected_role_id: Optional[int] = None
        self.selected_features: List[str] = []
        self.rebuild_items()

    def get_embed(self) -> discord.Embed:
        member = self.guild.get_member(self.owner_id)
        details = self.cog.build_custom_shop_details(self.guild)
        owners_data = self.cog.clean_missing_custom_roles(self.guild)
        role_line = "Aucun"
        role_details = []
        if self.selected_role_id:
            role = self.guild.get_role(self.selected_role_id)
            if role:
                role_line = role.mention
                current_state = self.cog.get_role_options_state(owners_data, self.selected_role_id)
                role_color_hex = f"#{role.colour.value:06X}"
                role_details.append(f"- 🎨 Couleur: {role_color_hex}")
                role_details.append(f"- 📌 Épinglé: {'activé' if role.hoist else 'désactivé'}")
                role_details.append(f"- 📣 Mentionnable: {'activé' if role.mentionable else 'désactivé'}")
        desc = details + "\n\n" + f"🎯 Rôle sélectionné: {role_line}"
        if role_details:
            desc += "\n" + "\n".join(role_details)
        if self.selected_features:
            desc += "\n" + f"🧾 Options choisies: {', '.join(self.selected_features)}"
        desc += "\n\n🚫 Un rôle custom acheté ne peut pas être vendu dans le shop serveur."
        desc += "\n💡 Vous pouvez renommer, recolorer et activer/désactiver vos options à tout moment."

        embed = self.cog.make_embed_for_user(self.guild, member, "🧩 Gestion des rôles custom", desc)
        if self.selected_role_id:
            role = self.guild.get_role(self.selected_role_id)
            if role is not None:
                embed.colour = role.colour
        return embed

    def rebuild_items(self):
        self.clear_items()
        member = self.guild.get_member(self.owner_id)
        if member is None:
            return

        data = load_shop_config(self.guild.id)
        custom_cfg = data.get("custom", {})
        custom_enabled = bool(custom_cfg.get("enabled", False))
        owners_data = self.cog.clean_missing_custom_roles(self.guild)
        owned_ids = [int(rid) for rid in owners_data.get("owners", {}).get(str(member.id), [])]
        owned_roles = [r for r in [self.guild.get_role(rid) for rid in owned_ids] if r is not None]

        if self.selected_role_id is None and owned_roles:
            self.selected_role_id = owned_roles[0].id

        if custom_enabled:
            feature_order = ["color", "hoist", "mention"]
            total_current = self.cog.get_custom_roles_count(self.guild)
            max_total = int(custom_cfg.get("max_total", 20))
            total_reached = total_current >= max_total
            effective_max_per_user = min(int(custom_cfg.get("max_per_user", 1)), 24)
            user_reached = len(owned_roles) >= effective_max_per_user
            allow_create = (not total_reached) and (not user_reached)

            target_select = CustomRoleTargetSelect(self, owned_roles[:25], allow_create=allow_create)
            if target_select.options:
                self.add_item(target_select)

            owned_features: List[str] = []
            missing_features: List[str] = []
            if self.selected_role_id is not None:
                current_state = self.cog.get_role_options_state(owners_data, self.selected_role_id)
                for feature in feature_order:
                    cfg = self.cog.get_custom_feature_cfg(custom_cfg, feature)
                    if not cfg.get("enabled", True):
                        continue
                    if current_state.get(feature, False):
                        owned_features.append(feature)
                    else:
                        missing_features.append(feature)

            self.selected_features = [f for f in self.selected_features if f in missing_features]
            if missing_features:
                self.add_item(CustomFeatureSelect(self, missing_features))

            if self.selected_role_id is not None and missing_features:
                upgrade_btn = ui.Button(label="Acheter options", style=discord.ButtonStyle.primary, emoji="✨")

                async def upgrade_btn_cb(interaction: discord.Interaction):
                    if not self.selected_features:
                        return await interaction.response.send_message("❌ Sélectionnez au moins une option.", ephemeral=True)
                    if "color" in self.selected_features:
                        return await interaction.response.send_modal(ShopCustomUpgradeColorModal(self))
                    result = await self.cog.perform_custom_upgrade(
                        interaction.user,
                        int(self.selected_role_id),
                        self.selected_features,
                        None,
                    )
                    await interaction.response.send_message(result, ephemeral=True)
                    await self.refresh_message()

                upgrade_btn.callback = upgrade_btn_cb
                self.add_item(upgrade_btn)

            if self.selected_role_id is not None:
                action_features = [feature for feature in feature_order if feature in owned_features]
                if action_features:
                    self.add_item(CustomRoleActionSelect(self, action_features))

        back_btn = ui.Button(label="Retour", style=discord.ButtonStyle.secondary, emoji="↩️")

        async def back_btn_cb(interaction: discord.Interaction):
            self.parent_view.message = self.message
            await self.parent_view.refresh_message(interaction)

        back_btn.callback = back_btn_cb
        self.add_item(back_btn)

    async def refresh_message(self, interaction: Optional[discord.Interaction] = None):
        if not self.message:
            return
        self.rebuild_items()
        embed = self.get_embed()
        try:
            if interaction and not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=self)
            else:
                await self.message.edit(embed=embed, view=self)
        except discord.HTTPException:
            pass


class ShopUserView(BaseShopView):
    def __init__(self, cog: ShopCog, owner_id: int, guild: discord.Guild):
        super().__init__(cog, owner_id, guild)
        self.rebuild_items()

    def rebuild_items(self):
        self.clear_items()
        member = self.guild.get_member(self.owner_id)
        if member is not None:
            self.cog.clean_missing_custom_roles(self.guild)
            buyable_items = self.cog.get_buyable_shop_items(member)
            if buyable_items:
                self.add_item(ShopBuySelect(self))

            data = load_shop_config(self.guild.id)
            custom_cfg = data.get("custom", {})
            custom_enabled = bool(custom_cfg.get("enabled", False))
            if custom_enabled:
                custom_btn = ui.Button(label="Gérer custom", style=discord.ButtonStyle.success, emoji="🧩")

                async def custom_btn_cb(interaction: discord.Interaction):
                    custom_view = CustomRoleManageView(self.cog, self.owner_id, self.guild, self)
                    custom_view.message = self.message
                    await custom_view.refresh_message(interaction)

                custom_btn.callback = custom_btn_cb
                self.add_item(custom_btn)

    async def refresh_message(self, interaction: Optional[discord.Interaction] = None):
        if not self.message:
            return
        self.rebuild_items()

        member = self.guild.get_member(self.owner_id)
        embed = self.cog.make_embed_for_user(
            self.guild,
            member,
            "🛒 Shop du serveur",
            self.cog.build_shop_description(self.guild, self.owner_id),
        )
        try:
            if interaction and not interaction.response.is_done():
                await interaction.response.edit_message(embed=embed, view=self)
            else:
                await self.message.edit(embed=embed, view=self)
        except discord.HTTPException:
            pass


async def setup(bot):
    await bot.add_cog(ShopCog(bot))
