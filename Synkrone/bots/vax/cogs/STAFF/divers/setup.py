from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import discord
from discord import ui
from discord.ext import commands

from utils.config_perm import ensure_command_permission, perm_command
from utils.config_prefix import get_global_prefix, prefix_config_manager
from utils.config_theme import config_manager


DEV_TEAM_TEXT = "du fondateur `@ð‘½ð’†ð’™` et de `@à¼º ð•ºð–“ð–žð– à¼»`"


@dataclass(slots=True)
class SetupInfo:
    prefix: str
    bot_name: str
    guild_count: int
    team_text: str


@dataclass(slots=True)
class JoinDMInfo:
    guild_name: str
    guild_link: str
    prefix: str
    bot_name: str


class SetupLayoutView(ui.LayoutView):
    def __init__(self, cog: "SetupCommand", ctx: commands.Context, info: SetupInfo):
        super().__init__(timeout=300)
        self.cog = cog
        self.ctx = ctx
        self.info = info
        self.author = ctx.author
        self.current_section = "presentation"
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        return True

    def _section_options(self) -> list[discord.SelectOption]:
        sections = [
            ("presentation", "Présentation de base", "Bot, préfixe, équipe, aide", "ðŸ¤–"),
            ("prioritaire", "Configuration prioritaire", "Accès, permissions, thème, sécurité", "âš ï¸"),
            ("communaute", "Configuration communauté", "Accueil, rôles, annonces, confessions", "ðŸ˜ï¸"),
            ("activite", "Configuration activité", "Support, stats, automatisations, rewards", "ðŸ“Š"),
        ]

        out: list[discord.SelectOption] = []
        for value, label, desc, emoji in sections:
            out.append(
                discord.SelectOption(
                    label=label,
                    value=value,
                    description=desc,
                    emoji=emoji,
                    default=(self.current_section == value),
                )
            )
        return out

    def _render_section_text(self) -> str:
        pfx = self.info.prefix
        if self.current_section == "presentation":
            return (
                f"Je suis **{self.info.bot_name}**.\n"
                f"Je suis présent sur **{self.info.guild_count}** serveurs.\n"
                f"Mon préfixe principal est `{pfx}`.\n"
                f"Mon équipe de développement est composée de {self.info.team_text}.\n\n"
                "Je possede une option IA pour discuter avec les utilisateurs.\n"
                f"La commande `{pfx}help` est disponible pour voir l'étendue de mes commandes.\n"
                "Le menu setup sert a vous proposer les outils de configuration de base."
            )

        if self.current_section == "prioritaire":
            return (
                "âš ï¸ Ces configurations sont très recommandées pour gérer entièrement le bot, "
                "la sécurité du serveur et garder le calme avant la tempête.\n\n"
                "Configuration prioritaire\n"
                f"- `{pfx}acces` : Définit qui peut utiliser le bot et dans quels salons.\n"
                f"- `{pfx}perm` : Organise les niveaux d'accès et associe chaque commande au bon niveau.\n"
                f"- `{pfx}theme` : Personnalise l'identité visuelle du bot sur votre serveur.\n"
                f"- `{pfx}secur` : Active les protections automatiques contre les abus et raids.\n"
                f"- `{pfx}antiscam` : Bloque les liens et contenus suspects avant qu'ils se propagent.\n"
                f"- `{pfx}logs` : Enregistre les actions importantes pour un suivi clair."
            )

        if self.current_section == "communaute":
            return (
                "Configuration communaute :\n"
                f"- `{pfx}bienvenue` : Configure les messages d'accueil pour les nouveaux membres.\n"
                f"- `{pfx}aurevoir` : Configure les messages de depart et le salon de sortie.\n"
                f"- `{pfx}autorole` : Attribue automatiquement des roles selon vos regles.\n"
                f"- `{pfx}rolemenu` : Permet aux membres de choisir leurs roles via menus.\n"
                f"- `{pfx}boost` : Parametre les avantages et annonces lies aux boosts.\n"
                f"- `{pfx}anniversaire` : Gere les rappels et celebrations d'anniversaires.\n"
                f"- `{pfx}confessions` : Active un canal de confessions anonymes moderees.\n"
                f"- `{pfx}infinite` : Active vos animations communautaires en continu."
            )

        if self.current_section == "activite":
            return (
                "Configuration activite et support :\n"
                f"- `{pfx}ticket` : Met en place un systeme de tickets pour l'assistance.\n"
                f"- `{pfx}statsserver` : Affiche et configure les statistiques globales du serveur.\n"
                f"- `{pfx}autostats` : Automatise la mise a jour de salons statistiques.\n"
                f"- `{pfx}voice` : Configure les salons vocaux dynamiques et leurs options.\n"
                f"- `{pfx}autoping` : Automatise des notifications selon des declencheurs definis.\n"
                f"- `{pfx}rewards` : Configure les recompenses automatiques basees sur l'activite.\n"
                f"- `{pfx}update` : Gere les annonces de mises a jour et changelogs du bot."
            )

        return (
            "Configuration activité et support :\n"
            f"- `{pfx}ticket` : Met en place un systeme de tickets pour l'assistance.\n"
            f"- `{pfx}statsserver` : Affiche et configure les statistiques globales du serveur.\n"
            f"- `{pfx}autostats` : Automatise la mise a jour de salons statistiques.\n"
            f"- `{pfx}voice` : Configure les salons vocaux dynamiques et leurs options.\n"
            f"- `{pfx}autoping` : Automatise des notifications selon des declencheurs definis.\n"
            f"- `{pfx}rewards` : Configure les recompenses automatiques basees sur l'activite.\n"
            f"- `{pfx}update` : Gere les annonces de mises a jour et changelogs du bot."
        )

    def _build(self) -> None:
        self.clear_items()

        guild = self.ctx.guild
        guild_id = guild.id if guild else None
        theme = config_manager.get_layout_v2_theme(
            guild_id,
            guild,
            self.author,
            self.ctx.bot,
            force_global=(guild_id is None),
        )

        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text") or f"{self.info.bot_name} - Setup"

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay("# Centre de configuration"))
        container.add_item(ui.TextDisplay("Selectionnez une rubrique du setup pour voir les bases."))
        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

        row = ui.ActionRow()
        selector = ui.Select(
            placeholder="Choisir une rubrique",
            min_values=1,
            max_values=1,
            options=self._section_options(),
        )
        selector.callback = self.change_section_callback
        row.add_item(selector)
        container.add_item(row)

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
        container.add_item(ui.TextDisplay(self._render_section_text()))

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    async def change_section_callback(self, interaction: discord.Interaction):
        self.current_section = interaction.data.get("values", [self.current_section])[0]
        self._build()
        await interaction.response.edit_message(view=self)


class SetupCommand(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _resolve_prefix_for_guild(self, guild: discord.Guild) -> str:
        try:
            prefixes = prefix_config_manager.get_effective_prefixes(self.bot, guild.id, default_prefix="!")
            if prefixes:
                return str(prefixes[0])
        except Exception:
            pass
        return get_global_prefix(self.bot, fallback="!")

    async def _resolve_team_text(self) -> str:
        return DEV_TEAM_TEXT

    async def _build_setup_info(self, ctx: commands.Context) -> SetupInfo:
        guild = ctx.guild
        if guild is not None:
            prefix = self._resolve_prefix_for_guild(guild)
        else:
            prefix = get_global_prefix(self.bot, fallback="!")

        bot_name = getattr(self.bot.user, "display_name", None) or getattr(self.bot.user, "name", "Bot")
        team_text = await self._resolve_team_text()

        return SetupInfo(
            prefix=prefix,
            bot_name=bot_name,
            guild_count=len(self.bot.guilds),
            team_text=team_text,
        )

    async def _iter_admin_members(self, guild: discord.Guild) -> list[discord.Member]:
        admins: dict[int, discord.Member] = {}

        for member in guild.members:
            if member.bot:
                continue
            if member.guild_permissions.administrator:
                admins[member.id] = member

        if admins:
            return list(admins.values())

        try:
            async for member in guild.fetch_members(limit=None):
                if member.bot:
                    continue
                if member.guild_permissions.administrator and member.id not in admins:
                    admins[member.id] = member
        except Exception:
            pass

        return list(admins.values())

    async def _resolve_guild_direct_link(self, guild: discord.Guild) -> str:
        vanity_url = getattr(guild, "vanity_url", None)
        if vanity_url:
            return vanity_url
        return f"https://discord.com/channels/{guild.id}"

    async def _build_join_dm_info(self, guild: discord.Guild) -> JoinDMInfo:
        prefix = self._resolve_prefix_for_guild(guild)
        bot_name = getattr(self.bot.user, "display_name", None) or getattr(self.bot.user, "name", "Bot")
        guild_link = await self._resolve_guild_direct_link(guild)

        return JoinDMInfo(
            guild_name=guild.name,
            guild_link=guild_link,
            prefix=prefix,
            bot_name=bot_name,
        )

    def _build_join_dm_view(self, guild: discord.Guild, member: discord.abc.User, info: JoinDMInfo) -> ui.LayoutView:
        theme = config_manager.get_layout_v2_theme(
            guild.id,
            guild,
            member,
            self.bot,
            force_global=False,
        )

        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text") or f"{info.bot_name} - Setup"

        view = ui.LayoutView(timeout=None)
        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)

        container.add_item(ui.TextDisplay("## âœ… Je viens de rejoindre votre serveur"))
        container.add_item(ui.TextDisplay(f"**ðŸ° Serveur :** `{info.guild_name}`"))
        container.add_item(
            ui.TextDisplay(
                "ðŸ” Vous recevez ce message car vous avez la permission administrateur.\n"
                f"ðŸ› ï¸ Commencez avec `{info.prefix}setup` pour configurer la base du bot.\n"
                f"ðŸ“š Utilisez `{info.prefix}help` pour parcourir toutes les commandes disponibles."
            )
        )

        row = ui.ActionRow()
        row.add_item(
            ui.Button(
                label="Ouvrir le serveur",
                style=discord.ButtonStyle.link,
                url=info.guild_link,
                emoji="ðŸ”—",
            )
        )
        container.add_item(row)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        view.add_item(container)
        return view

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        info = await self._build_join_dm_info(guild)

        admins = await self._iter_admin_members(guild)
        for admin in admins:
            try:
                dm_view = self._build_join_dm_view(guild, admin, info)
                await admin.send(view=dm_view)
            except (discord.Forbidden, discord.HTTPException):
                continue

    @perm_command(level=1)
    @commands.hybrid_command(name="setup", description="Affiche le menu de configuration de base du bot")
    async def setup_command(self, ctx: commands.Context):
        if not await ensure_command_permission(ctx, command_name="setup"):
            return

        info = await self._build_setup_info(ctx)
        view = SetupLayoutView(self, ctx, info)
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(SetupCommand(bot))
