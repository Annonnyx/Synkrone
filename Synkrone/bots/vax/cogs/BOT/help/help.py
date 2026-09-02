from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
from typing import Dict, List, Optional

import discord
from discord import ui
from discord.ext import commands

from utils.config_balise import resolve_balises
from utils.config_emoji import Emoji as E
from utils.config_prefix import get_global_prefix, prefix_config_manager
from utils.config_theme import config_manager


DEFAULT_PREFIX_FALLBACK = "!"


@dataclass(slots=True)
class HelpAccess:
    is_owner: bool
    is_admin: bool


class DevlogDMView(ui.LayoutView):
    """Layout envoyé en MP contenant une partie du devlog."""
    def __init__(self, content: str, part: int, total_parts: int, theme: dict, bot_name: str):
        super().__init__(timeout=None)
        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text") or f"{bot_name} - Devlog"

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        
        header_title = f"# {E.HISTOIRE} Devlog ({part}/{total_parts})" if total_parts > 1 else f"# {E.HISTOIRE} Devlog"
        container.add_item(ui.TextDisplay(header_title))
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
        container.add_item(ui.TextDisplay(content))
        
        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)


class HelpLayoutView(ui.LayoutView):
    def __init__(self, cog: "HelpCommand", ctx: commands.Context, access: HelpAccess):
        super().__init__(timeout=300)
        self.cog = cog
        self.ctx = ctx
        self.bot = ctx.bot
        self.author = ctx.author
        self.access = access
        self.current_category = self._default_category()
        self.current_subcategory: Optional[str] = None
        self._build()

    def _default_category(self) -> str:
        return "last_update"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(f"{E.ERREUR} Cette interface ne t'appartient pas.", ephemeral=True)
            return False
        return True

    def _visible_categories(self) -> List[str]:
        categories = ["last_update", "public", "bot", "discover"]
        if self.access.is_admin:
            categories.insert(1, "staff")
        if self.access.is_owner:
            categories.insert(1, "owner")
        return categories

    def _labels(self) -> Dict[str, str]:
        return {
            "last_update": self.cog.get_last_update_selector_label(self.ctx),
            "owner": "Owner",
            "staff": "Staff",
            "public": "Public",
            "bot": "Bot",
            "discover": self.cog.get_dynamic_category_name("discover", "Découvrez aussi"),
        }

    def _emojis(self) -> Dict[str, str]:
        return {
            "last_update": E.ANNONCE,
            "owner": E.OWNER,
            "staff": E.BOUCLIER,
            "public": E.MONDE,
            "bot": E.VAX,
            "discover": self.cog.get_dynamic_category_emoji("discover", E.CREATE),
        }

    def _subcategory_labels(self) -> Dict[str, str]:
        return {
            "configuration": "Configuration",
            "moderation": "Modération",
            "divers": "Divers",
            "divertissement": "Divertissement",
            "utilitaires": "Utilitaires",
            "statistiques": "Statistiques",
        }

    def _subcategory_emojis(self) -> Dict[str, str]:
        return {
            "configuration": E.MODIFIER,
            "moderation": E.BOUCLIER,
            "divers": E.LISTE,
            "divertissement": E.JEU,
            "utilitaires": E.LAMPE,
            "statistiques": E.GRAPHIQUE,
        }

    def _subcategories_for(self, category: str) -> List[str]:
        if category == "staff":
            return ["configuration", "moderation", "divers"]
        if category == "public":
            return ["divertissement", "utilitaires", "statistiques"]
        return []

    def _split_text_chunks(self, text: str, max_length: int = 1800) -> List[str]:
        """Découpe un texte long en plusieurs blocs sans couper les lignes."""
        chunks: List[str] = []
        lines = text.split("\n")
        current_chunk: List[str] = []
        current_length = 0

        for line in lines:
            if len(line) > max_length:
                if current_chunk:
                    chunks.append("\n".join(current_chunk))
                    current_chunk = []
                    current_length = 0
                for i in range(0, len(line), max_length):
                    chunks.append(line[i:i + max_length])
                continue

            if current_length + len(line) + 1 > max_length:
                chunks.append("\n".join(current_chunk))
                current_chunk = [line]
                current_length = len(line)
            else:
                current_chunk.append(line)
                current_length += len(line) + 1

        if current_chunk:
            chunks.append("\n".join(current_chunk))

        return chunks

    def _build(self):
        self.clear_items()

        guild = self.ctx.guild
        guild_id = guild.id if guild else None
        theme = config_manager.get_layout_v2_theme(
            guild_id,
            guild,
            self.author,
            self.bot,
            force_global=(guild_id is None),
        )

        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text") or f"{self.bot.user.name} - Help"

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {E.INFO} Centre d'aide"))
        container.add_item(ui.TextDisplay("Sélectionne une catégorie pour afficher les commandes disponibles."))
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

        labels = self._labels()
        emojis = self._emojis()
        visible = self._visible_categories()

        if self.current_category not in visible:
            self.current_category = visible[0]

        row = ui.ActionRow()
        options: List[discord.SelectOption] = []
        for key in visible:
            options.append(
                discord.SelectOption(
                    label=labels[key],
                    value=key,
                    emoji=emojis[key],
                    default=(self.current_category == key),
                )
            )

        select = ui.Select(
            placeholder="Choisir une catégorie",
            min_values=1,
            max_values=1,
            options=options,
        )
        select.callback = self.change_category_callback
        row.add_item(select)
        container.add_item(row)

        subcategories = self._subcategories_for(self.current_category)
        if subcategories:
            if self.current_subcategory not in subcategories:
                self.current_subcategory = subcategories[0]

            sub_labels = self._subcategory_labels()
            sub_emojis = self._subcategory_emojis()
            sub_options: List[discord.SelectOption] = []
            for key in subcategories:
                sub_options.append(
                    discord.SelectOption(
                        label=sub_labels[key],
                        value=key,
                        emoji=sub_emojis.get(key),
                        default=(self.current_subcategory == key),
                    )
                )

            sub_row = ui.ActionRow()
            sub_select = ui.Select(
                placeholder="Choisir une sous-catégorie",
                min_values=1,
                max_values=1,
                options=sub_options,
            )
            sub_select.callback = self.change_subcategory_callback
            sub_row.add_item(sub_select)
            container.add_item(sub_row)
        else:
            self.current_subcategory = None

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

        # Affichage spécifique si l'accueil / dernière mise à jour est sélectionné
        if self.current_category == "last_update":
            version = self.cog.get_last_update_version()
            teaser_text = f"{E.ANNONCE} **Le devlog de la mise à jour `{version}` est disponible !**\n\nClique sur le bouton ci-dessous pour recevoir le devlog complet en message privé."
            container.add_item(ui.TextDisplay(teaser_text))

            btn_row = ui.ActionRow()
            btn_devlog = ui.Button(
                label="Cliques ici pour recevoir le devlog",
                style=discord.ButtonStyle.primary,
                emoji=E.HISTOIRE,
            )
            btn_devlog.callback = self.send_devlog_dm_callback
            btn_row.add_item(btn_devlog)
            container.add_item(btn_row)
        else:
            commands_text = self.cog.render_commands_for_category(self.ctx, self.current_category, self.current_subcategory)
            container.add_item(ui.TextDisplay(commands_text))

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    async def change_category_callback(self, interaction: discord.Interaction):
        self.current_category = interaction.data.get("values", [self.current_category])[0]
        self.current_subcategory = None
        self._build()
        await interaction.response.edit_message(view=self)

    async def change_subcategory_callback(self, interaction: discord.Interaction):
        self.current_subcategory = interaction.data.get("values", [self.current_subcategory])[0]
        self._build()
        await interaction.response.edit_message(view=self)

    async def send_devlog_dm_callback(self, interaction: discord.Interaction):
        devlog_content = self.cog._render_dynamic_category("last_update", self.ctx)
        chunks = self._split_text_chunks(devlog_content, max_length=1800)

        guild = self.ctx.guild
        guild_id = guild.id if guild else None
        theme = config_manager.get_layout_v2_theme(
            guild_id,
            guild,
            self.author,
            self.bot,
            force_global=(guild_id is None),
        )

        try:
            total_parts = len(chunks)
            for index, chunk in enumerate(chunks, 1):
                dm_view = DevlogDMView(chunk, index, total_parts, theme, self.bot.user.name)
                await interaction.user.send(view=dm_view)

            await interaction.response.send_message(
                f"{E.VALIDER} Le devlog t'a été envoyé en message privé !", ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                f"{E.ERREUR} Impossible de t'envoyer un message privé. Vérifie que tes MP sont bien ouverts !",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"{E.ERREUR} Une erreur s'est produite lors de l'envoi : {e}",
                ephemeral=True
            )


class HelpCommand(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._json_dir = Path(__file__).resolve().parent

    def _load_json_config(self, name: str) -> dict:
        path = self._json_dir / name
        if not path.exists():
            return {}
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _dynamic_payload(self, category: str) -> dict:
        if category == "last_update":
            return self._load_json_config("last_update.json")
        if category == "discover":
            return self._load_json_config("discover.json")
        return {}

    def get_dynamic_category_name(self, category: str, fallback: str) -> str:
        payload = self._dynamic_payload(category)
        name = payload.get("category_name")
        return str(name).strip() if isinstance(name, str) and name.strip() else fallback

    def get_dynamic_category_emoji(self, category: str, fallback: str) -> str:
        payload = self._dynamic_payload(category)
        emoji = payload.get("emoji")
        return str(emoji).strip() if isinstance(emoji, str) and emoji.strip() else fallback

    def get_last_update_version(self) -> str:
        payload = self._dynamic_payload("last_update")
        version = payload.get("version")
        if isinstance(version, str) and version.strip():
            return version.strip()

        sections = payload.get("sections")
        if isinstance(sections, dict):
            info = sections.get("Informations")
            if isinstance(info, dict):
                fallback_version = info.get("Version")
                if isinstance(fallback_version, str) and fallback_version.strip():
                    return fallback_version.strip()

        return "Version inconnue"

    def get_last_update_selector_label(self, ctx: commands.Context) -> str:
        configured_version = config_manager.get_panelbot_version() or self.get_last_update_version()
        values = resolve_balises(
            ctx.guild,
            ctx.author,
            self.bot,
            version=configured_version,
            prefix=self._get_display_prefix(ctx),
        )
        bot_name = values.get("{bot_nom}", getattr(self.bot.user, "display_name", "Bot")).strip() or "Bot"
        version = values.get("{version}", "").strip() or "Version inconnue"
        label = f"{bot_name} {version}".strip()
        return label[:100]

    def _get_display_prefix(self, ctx: commands.Context) -> str:
        fallback_prefix = get_global_prefix(self.bot, fallback=DEFAULT_PREFIX_FALLBACK)
        guild = ctx.guild
        if guild is not None:
            try:
                server_cfg = prefix_config_manager.get_server_config(guild.id)
                server_prefixes = server_cfg.get("prefixes", []) if isinstance(server_cfg, dict) else []
                if server_prefixes:
                    first = str(server_prefixes[0]).strip()
                    if first:
                        return first
            except Exception:
                pass

            try:
                effective_prefixes = prefix_config_manager.get_effective_prefixes(
                    bot=self.bot,
                    guild_id=guild.id,
                    default_prefix=fallback_prefix,
                )
                if effective_prefixes:
                    first = str(effective_prefixes[0]).strip()
                    if first:
                        return first
            except Exception:
                pass
        return fallback_prefix

    def _apply_help_balises(self, text: str, ctx: commands.Context) -> str:
        configured_version = config_manager.get_panelbot_version() or self.get_last_update_version()
        values = resolve_balises(
            ctx.guild,
            ctx.author,
            self.bot,
            version=configured_version,
            prefix=self._get_display_prefix(ctx),
        )
        rendered = text
        for key, value in values.items():
            rendered = rendered.replace(key, value)
        return rendered

    def _render_dynamic_category(self, category: str, ctx: commands.Context) -> str:
        payload = self._dynamic_payload(category)
        if not payload:
            return "*Aucune donnée JSON trouvée pour cette rubrique.*"

        if category == "last_update":
            free_content = payload.get("content")
            if isinstance(free_content, str) and free_content.strip():
                return self._apply_help_balises(free_content.strip(), ctx)
            return "*Aucune information à afficher pour cette rubrique.*"

        lines: List[str] = []
        free_content = payload.get("content")
        if isinstance(free_content, str) and free_content.strip():
            lines.append(free_content.strip())

        description = payload.get("category_description")
        if isinstance(description, str) and description.strip():
            lines.append(description.strip())

        sections = payload.get("sections")
        if isinstance(sections, dict):
            for section_name, section_items in sections.items():
                if category != "discover" and str(section_name).strip():
                    lines.append(f"\n### {section_name}")
                if isinstance(section_items, dict):
                    for label, text in section_items.items():
                        lines.append(f"- {label}: {text}")
                elif isinstance(section_items, list):
                    for item in section_items:
                        lines.append(f"- {item}")
                else:
                    lines.append(f"- {section_items}")

        content = "\n".join(lines).strip() or "*Aucune information à afficher pour cette rubrique.*"
        return self._apply_help_balises(content, ctx)

    async def _build_access(self, ctx: commands.Context) -> HelpAccess:
        is_owner = await self.bot.is_owner(ctx.author)
        is_admin = bool(getattr(ctx.author.guild_permissions, "administrator", False)) if ctx.guild else False
        return HelpAccess(is_owner=is_owner, is_admin=is_admin)

    def _command_signature(self, cmd: commands.Command, prefix: str) -> str:
        description = (
            getattr(cmd, "description", None)
            or getattr(cmd, "help", None)
            or getattr(cmd, "brief", None)
            or "Aucune description"
        )
        description_text = str(description)
        # Nettoie les mentions techniques d'UI pour l'affichage utilisateur du help.
        description_text = re.sub(r"\(?\b(?:via\s+)?layout\s*v2\b\)?", "", description_text, flags=re.IGNORECASE)
        description_text = re.sub(r"\bavec\s+une\s+interface\b", "", description_text, flags=re.IGNORECASE)
        description_text = " ".join(description_text.split()).strip(" .")
        if not description_text:
            description_text = "Aucune description"
        return f"- `{prefix}{cmd.name}` : {description_text}"

    def _iter_commands_for_category(self, category: str, subcategory: Optional[str] = None) -> List[commands.Command]:
        selected: List[commands.Command] = []
        for cmd in self.bot.commands:
            if getattr(cmd, "hidden", False):
                continue

            if category == "owner" and cmd.name == "faga":
                selected.append(cmd)
                continue

            module = getattr(getattr(cmd, "callback", None), "__module__", "") or ""

            if category == "owner" and module.startswith("cogs.OWNER."):
                selected.append(cmd)
            elif category == "staff":
                if subcategory == "configuration" and module.startswith("cogs.STAFF.configuration."):
                    selected.append(cmd)
                elif subcategory == "moderation" and (
                    module.startswith("cogs.STAFF.moderation.")
                    or module.startswith("cogs.STAFF.modération.")
                ):
                    selected.append(cmd)
                elif subcategory == "divers" and module.startswith("cogs.STAFF.divers."):
                    selected.append(cmd)
            elif category == "public":
                if subcategory == "divertissement" and module.startswith("cogs.PUBLIQUE.divertissement."):
                    selected.append(cmd)
                elif subcategory == "utilitaires" and module.startswith("cogs.PUBLIQUE.utilitaires."):
                    selected.append(cmd)
                elif subcategory == "statistiques" and module.startswith("cogs.PUBLIQUE.statistiques."):
                    selected.append(cmd)
            elif category == "bot":
                if cmd.name == "faga":
                    continue
                if module.startswith("cogs.PUBLIQUE."):
                    continue
                if module.startswith("cogs.STAFF."):
                    continue
                if module.startswith("cogs.OWNER."):
                    continue
                if module.startswith("cogs.TEST."):
                    continue
                if module.startswith("cogs.test."):
                    continue
                if module.startswith("cogs.BOT.help."):
                    continue
                if module.startswith("cogs."):
                    selected.append(cmd)

        selected.sort(key=lambda c: c.name)
        return selected

    def get_category_description(self, category: str, subcategory: Optional[str] = None) -> str:
        mapping = {
            "last_update": "",
            "owner": "Commandes réservées au propriétaire du bot.",
            "staff": "Commandes staff, visibles uniquement aux administrateurs du serveur.",
            "public": "Commandes disponibles pour tous les utilisateurs.",
            "bot": "Commandes utilitaires globales du bot (également publiques).",
            "discover": "",
        }
        sub_mapping = {
            ("staff", "configuration"): "Paramétrage et gestion de la configuration du serveur.",
            ("staff", "moderation"): "Actions de modération et outils disciplinaires.",
            ("staff", "divers"): "Outils staff divers.",
            ("public", "divertissement"): "Commandes de jeu et de divertissement.",
            ("public", "utilitaires"): "Outils utiles pour les membres.",
            ("public", "statistiques"): "Statistiques utilisateur et serveur.",
        }
        if subcategory:
            return sub_mapping.get((category, subcategory), mapping.get(category, ""))
        return mapping.get(category, "")

    def render_commands_for_category(self, ctx: commands.Context, category: str, subcategory: Optional[str] = None) -> str:
        if category in {"last_update", "discover"}:
            return self._render_dynamic_category(category, ctx)

        commands_list = self._iter_commands_for_category(category, subcategory)
        if not commands_list:
            return "*Aucune commande disponible dans cette catégorie pour le moment.*"

        prefix = self._get_display_prefix(ctx)
        lines = [self._command_signature(cmd, prefix) for cmd in commands_list]
        return "\n".join(lines)

    @commands.hybrid_command(name="help", description="Affiche les commandes disponibles par catégorie")
    async def help_command(self, ctx: commands.Context):
        access = await self._build_access(ctx)
        view = HelpLayoutView(self, ctx, access)
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCommand(bot))