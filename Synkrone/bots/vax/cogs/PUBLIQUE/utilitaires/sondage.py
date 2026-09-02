"""
MODULE SONDAGE - VAX V3
=======================
Gestionnaire de sondages interactifs utilisant l'architecture Layout V2,
la commande hybride `/sondage`, la configuration par thèmes,
des retours persistants (sans messages éphémères), les variables globales de log,
les emojis centralisés et le respect strict des standards Vax v3.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
import traceback
from typing import Any, Optional

import discord
from discord import app_commands, ui
from discord.ext import commands, tasks

from utils.config_emoji import Emoji as E
from utils.config_perm import ensure_command_permission, perm_command, perm_config_manager

try:
    from utils.config_theme import config_manager
except ImportError:
    config_manager = None

# ==============================================================================
# ------------------------------ DÉBOGAGE GLOBAL -------------------------------
# ==============================================================================
DEBUG_MODE = True
DEBUG_ERRORS_ONLY = True


def debug_log(message: str, level: str = "INFO") -> None:
    """Affiche des logs formatés dans la console selon le niveau de sévérité."""
    if DEBUG_ERRORS_ONLY and level.upper() != "ERROR":
        return
    if not DEBUG_MODE and not DEBUG_ERRORS_ONLY:
        return

    colors = {
        "INFO": "\033[94m",
        "SUCCESS": "\033[92m",
        "ERROR": "\033[91m",
        "WARNING": "\033[93m",
    }
    reset = "\033[0m"
    color = colors.get(level.upper(), "\033[97m")
    print(f"{color}[DEBUG - Sondage] [{level.upper()}] {message}{reset}")


# ==============================================================================
# --------------------------- CONFIGURATION DU THÈME ---------------------------
# ==============================================================================
def get_theme_values(guild: Optional[discord.Guild], user: discord.abc.User, bot: commands.Bot) -> tuple[int, str]:
    if config_manager:
        try:
            theme = config_manager.get_layout_v2_theme(
                guild.id if guild else None,
                guild,
                user,
                bot,
            )
            return int(theme.get("color", discord.Color.blurple().value)), str(theme.get("footer_text") or "")
        except Exception as e:
            debug_log(f"Erreur get_theme_values: {e}", "ERROR")
            traceback.print_exc()
    return discord.Color.blurple().value, "Module Sondage"


# ==============================================================================
# ----------------------------- CLASSE DE DONNÉES ------------------------------
# ==============================================================================
class Survey:
    def __init__(self, **kwargs):
        self.title = kwargs.get("title", "Nouveau Sondage")
        self.options = kwargs.get("options", [])
        self.description = kwargs.get("description", "")
        self.channel_id = kwargs.get("channel_id")
        self.author_id = kwargs.get("author_id")
        self.guild_id = kwargs.get("guild_id")
        self.is_multiple = kwargs.get("is_multiple", False)
        self.duration_value = kwargs.get("duration_value", 1)
        self.duration_unit = kwargs.get("duration_unit", "h")  # 'm' (minutes), 'h' (heures), 'j' (jours)
        self.votes = kwargs.get("votes", {})
        self.message_id = kwargs.get("message_id")
        self.created_at = kwargs.get("created_at", datetime.now(timezone.utc).timestamp())
        self.ended_at = kwargs.get("ended_at")

    def get_duration_in_seconds(self) -> int:
        if self.duration_unit == "m":
            return self.duration_value * 60
        elif self.duration_unit == "h":
            return self.duration_value * 3600
        elif self.duration_unit == "j":
            return self.duration_value * 86400
        return self.duration_value * 3600

    def to_dict(self):
        return self.__dict__


# ==============================================================================
# -------------------------- MODALES DE CONFIGURATION --------------------------
# ==============================================================================
class SurveyConfigModal(ui.Modal, title="Contenu du Sondage"):
    def __init__(self, setup_view: "SurveySetupView"):
        super().__init__()
        self.setup_view = setup_view
        self.survey_title = ui.TextInput(label="Titre", default=setup_view.survey.title, max_length=100)
        self.survey_desc = ui.TextInput(label="Description", default=setup_view.survey.description, style=discord.TextStyle.paragraph, required=False, max_length=1000)
        self.add_item(self.survey_title)
        self.add_item(self.survey_desc)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            self.setup_view.survey.title = self.survey_title.value
            self.setup_view.survey.description = self.survey_desc.value
            await self.setup_view.refresh(interaction)
        except Exception as e:
            debug_log(f"Erreur SurveyConfigModal: {e}", "ERROR")
            traceback.print_exc()


class SurveyOptionModal(ui.Modal, title="Ajouter des Options"):
    def __init__(self, setup_view: "SurveySetupView"):
        super().__init__()
        self.setup_view = setup_view
        remaining = 25 - len(setup_view.survey.options)
        count = min(5, remaining)
        self.inputs = [ui.TextInput(label=f"Option {len(setup_view.survey.options)+i+1}", required=False) for i in range(count)]
        for item in self.inputs:
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            for item in self.inputs:
                if item.value and item.value.strip():
                    if len(self.setup_view.survey.options) < 25:
                        self.setup_view.survey.options.append(item.value.strip())
            await self.setup_view.refresh(interaction)
        except Exception as e:
            debug_log(f"Erreur SurveyOptionModal: {e}", "ERROR")
            traceback.print_exc()


class SurveyDurationModal(ui.Modal, title="Durée du Sondage"):
    def __init__(self, setup_view: "SurveySetupView"):
        super().__init__()
        self.setup_view = setup_view
        self.duration_input = ui.TextInput(
            label="Durée (ex: 30m, 1h, 7j — max 90j)",
            default=f"{setup_view.survey.duration_value}{setup_view.survey.duration_unit}",
            required=True,
            max_length=5
        )
        self.add_item(self.duration_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            raw = self.duration_input.value.strip().lower()
            if not raw:
                return
            unit = raw[-1]
            if unit not in {"m", "h", "j"}:
                await interaction.response.send_message(f"{E.ERREUR} Unité invalide. Utilisez 'm' (minutes), 'h' (heures) ou 'j' (jours).", ephemeral=False)
                return
            val_str = raw[:-1]
            if not val_str.isdigit():
                await interaction.response.send_message(f"{E.ERREUR} Valeur numérique invalide.", ephemeral=False)
                return
            val = int(val_str)
            if val < 1:
                val = 1
            if unit == "j" and val > 90:
                val = 90

            self.setup_view.survey.duration_value = val
            self.setup_view.survey.duration_unit = unit
            await self.setup_view.refresh(interaction)
        except Exception as e:
            debug_log(f"Erreur SurveyDurationModal: {e}", "ERROR")
            await interaction.response.send_message(f"{E.ERREUR} Format de durée incorrect.", ephemeral=False)


# ==============================================================================
# ------------------------- VUE LAYOUT V2 DE PRÉPARATION -----------------------
# ==============================================================================
class SurveySetupView(ui.LayoutView):
    def __init__(self, cog: "Sondage", survey: Survey, author: discord.Member, ctx: commands.Context):
        super().__init__(timeout=600)
        self.cog = cog
        self.survey = survey
        self.author = author
        self.ctx = ctx
        self._build_layout()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(f"{E.ERREUR} Ce menu ne vous appartient pas.", ephemeral=False)
            return False
        return True

    def _build_layout(self) -> None:
        try:
            self.clear_items()

            guild = self.author.guild if hasattr(self.author, "guild") else None
            color, footer = get_theme_values(guild, self.author, self.cog.bot)

            container = ui.Container(accent_color=discord.Color(color), spoiler=False)

            title = "⚙️ Préparation du Sondage"
            opts_text = "\n".join([f"`{i+1}`. {o}" for i, o in enumerate(self.survey.options)]) or "*Aucune option*"
            desc = (
                f"**Titre :** {self.survey.title}\n"
                f"**Description :** {self.survey.description or '*Aucune*'}\n"
                f"**Durée :** {self.survey.duration_value}{self.survey.duration_unit}\n\n"
                f"**Options ({len(self.survey.options)}/25) :**\n{opts_text}"
            )

            container.add_item(ui.TextDisplay(f"## {title}"))
            container.add_item(ui.TextDisplay(desc))
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

            config_select = ui.Select(
                placeholder="⚙️ Configurer le sondage...",
                options=[
                    discord.SelectOption(label="Modifier le Titre / Description", value="config_main", emoji="📝"),
                    discord.SelectOption(label="Ajouter des options", value="config_opts", emoji="➕", description="Max 25 options"),
                    discord.SelectOption(label=f"Changer le mode (Actuel: {'Multiple' if self.survey.is_multiple else 'Unique'})", value="config_mode", emoji="🔄"),
                    discord.SelectOption(label=f"Définir la durée (Actuel: {self.survey.duration_value}{self.survey.duration_unit})", value="config_duration", emoji="⏳"),
                ]
            )

            async def config_select_callback(interaction: discord.Interaction) -> None:
                try:
                    choice = config_select.values[0]
                    if choice == "config_main":
                        await interaction.response.send_modal(SurveyConfigModal(self))
                    elif choice == "config_opts":
                        if len(self.survey.options) >= 25:
                            await interaction.response.send_message(f"{E.ERREUR} Limite de 25 options atteinte.", ephemeral=False)
                            return
                        await interaction.response.send_modal(SurveyOptionModal(self))
                    elif choice == "config_mode":
                        self.survey.is_multiple = not self.survey.is_multiple
                        await self.refresh(interaction)
                    elif choice == "config_duration":
                        await interaction.response.send_modal(SurveyDurationModal(self))
                except Exception as e:
                    debug_log(f"Erreur config_select_callback: {e}", "ERROR")

            config_select.callback = config_select_callback
            row_config = ui.ActionRow()
            row_config.add_item(config_select)
            container.add_item(row_config)

            if self.survey.options:
                select_remove = ui.Select(
                    placeholder="🗑️ Supprimer une option...",
                    options=[discord.SelectOption(label=f"{i+1}. {o[:50]}", value=str(i)) for i, o in enumerate(self.survey.options)],
                )
                async def remove_option_callback(interaction: discord.Interaction) -> None:
                    try:
                        idx = int(select_remove.values[0])
                        if 0 <= idx < len(self.survey.options):
                            self.survey.options.pop(idx)
                            await self.refresh(interaction)
                    except Exception as e:
                        debug_log(f"Erreur remove_option_callback: {e}", "ERROR")
                select_remove.callback = remove_option_callback
                
                row_select = ui.ActionRow()
                row_select.add_item(select_remove)
                container.add_item(row_select)

            if len(self.survey.options) >= 2:
                row_launch = ui.ActionRow()
                btn_launch = ui.Button(label="Lancer le Sondage", style=discord.ButtonStyle.primary, emoji="🚀")
                async def launch_callback(interaction: discord.Interaction) -> None:
                    try:
                        self.survey.channel_id = interaction.channel_id
                        
                        msg = await interaction.channel.send("Chargement du sondage...")
                        self.survey.message_id = msg.id

                        public_view = SurveyPublicView(self.survey, self.cog)
                        await msg.edit(content=None, view=public_view)

                        self.cog.save_survey_data(self.survey)
                        debug_log(f"Sondage lancé avec succès par {interaction.user}", "SUCCESS")
                        
                        try:
                            await interaction.message.delete()
                        except Exception:
                            pass

                        if self.ctx.message:
                            try:
                                await self.ctx.message.delete()
                            except Exception:
                                pass

                    except Exception as e:
                        debug_log(f"Erreur launch_callback: {e}", "ERROR")
                        traceback.print_exc()

                btn_launch.callback = launch_callback
                row_launch.add_item(btn_launch)
                container.add_item(row_launch)

            if footer:
                container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
                container.add_item(ui.TextDisplay(footer))

            self.add_item(container)
        except Exception as e:
            debug_log(f"Erreur critique _build_layout SurveySetupView: {e}", "ERROR")
            traceback.print_exc()

    async def refresh(self, interaction: discord.Interaction) -> None:
        try:
            self._build_layout()
            if interaction.response.is_done():
                await interaction.edit_original_response(view=self)
            else:
                await interaction.response.edit_message(view=self)
        except Exception as e:
            debug_log(f"Erreur refresh SurveySetupView: {e}", "ERROR")
            traceback.print_exc()


# ==============================================================================
# ----------------------- VUE PUBLIQUE (VOTE ET CLÔTURE) -----------------------
# ==============================================================================
class SurveyPublicView(ui.LayoutView):
    def __init__(self, survey: Survey, cog: "Sondage"):
        super().__init__(timeout=None)
        self.survey = survey
        self.cog = cog
        self._build_layout()

    def _build_layout(self) -> None:
        try:
            self.clear_items()
            guild = self.cog.bot.get_guild(self.survey.guild_id)
            color, footer = get_theme_values(guild, None, self.cog.bot)

            container = ui.Container(accent_color=discord.Color(color), spoiler=False)

            if not self.survey.ended_at:
                elapsed = datetime.now(timezone.utc).timestamp() - self.survey.created_at
                if elapsed >= self.survey.get_duration_in_seconds():
                    self.survey.ended_at = datetime.now(timezone.utc).timestamp()

            status_info = f"🔴 **Clôturé**" if self.survey.ended_at else "🟢 **En cours**"
            total_voters = len(self.survey.votes)

            header_text = f"## 📊 {self.survey.title}"
            if self.survey.description:
                header_text += f"\n{self.survey.description}"

            header_text += f"\n\nMode : `{'Multiple' if self.survey.is_multiple else 'Unique'}` | Statut : {status_info} | {total_voters} votant(s)"

            if not self.survey.ended_at:
                end_btn = ui.Button(
                    label="Terminer",
                    style=discord.ButtonStyle.danger,
                    emoji="🏁",
                    custom_id=f"sv_end_{self.survey.message_id}"
                )

                async def end_callback(interaction: discord.Interaction):
                    if not interaction.guild:
                        await interaction.response.send_message(f"{E.ERREUR} Commande réservée à un serveur.", ephemeral=True)
                        return
                    
                    is_author = interaction.user.id == self.survey.author_id
                    is_admin = interaction.user.guild_permissions.administrator

                    # Vérification permissions via config_perm si non-auteur et non-admin
                    has_perm_bypass = False
                    if not (is_author or is_admin):
                        if isinstance(interaction.user, discord.Member):
                            has_perm_bypass = perm_config_manager.user_has_access(interaction.guild.id, interaction.user, level=2)

                    if not (is_author or is_admin or has_perm_bypass):
                        await interaction.response.send_message(f"{E.ERREUR} Seul l'auteur du sondage, un administrateur ou un utilisateur autorisé peut le clôturer.", ephemeral=True)
                        return

                    await self.cog.close_survey(self.survey)
                    await interaction.response.send_message(f"{E.VALIDE} Le sondage a été clôturé manuellement.", ephemeral=True)

                end_btn.callback = end_callback

                container.add_item(
                    ui.Section(
                        ui.TextDisplay(header_text),
                        accessory=end_btn
                    )
                )
            else:
                container.add_item(ui.TextDisplay(header_text))

            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

            stats = {i: 0 for i in range(len(self.survey.options))}
            for user_votes in self.survey.votes.values():
                for v in user_votes:
                    if v < len(self.survey.options):
                        stats[v] += 1

            for i, opt in enumerate(self.survey.options):
                cnt = stats[i]
                pct = (cnt / total_voters * 100) if total_voters > 0 else 0
                bar = "🟦" * int(pct/10) + "⬜" * (10 - int(pct/10))
                
                choice_text = f"`{i+1}.` **{opt}**\n{bar} `{pct:.1f}%` ({cnt})"

                vote_btn = ui.Button(
                    label=f"Voter #{i+1}",
                    style=discord.ButtonStyle.secondary,
                    emoji="🗳️",
                    custom_id=f"sv_vote_{self.survey.message_id}_{i}",
                    disabled=bool(self.survey.ended_at)
                )

                def create_vote_callback(opt_idx: int):
                    async def vote_callback(interaction: discord.Interaction):
                        try:
                            user_id_str = str(interaction.user.id)
                            current_user_votes = self.survey.votes.get(user_id_str, [])

                            if self.survey.is_multiple:
                                if opt_idx in current_user_votes:
                                    current_user_votes.remove(opt_idx)
                                    msg = f"{E.VALIDE} Vous avez retiré votre vote pour l'option {opt_idx + 1}."
                                else:
                                    current_user_votes.append(opt_idx)
                                    msg = f"{E.VALIDE} Votre vote pour l'option {opt_idx + 1} a été enregistré."
                            else:
                                if current_user_votes == [opt_idx]:
                                    current_user_votes = []
                                    msg = f"{E.VALIDE} Vous avez retiré votre vote."
                                else:
                                    current_user_votes = [opt_idx]
                                    msg = f"{E.VALIDE} Votre vote a été enregistré pour l'option {opt_idx + 1}."

                            if current_user_votes:
                                self.survey.votes[user_id_str] = current_user_votes
                            else:
                                self.survey.votes.pop(user_id_str, None)

                            self.cog.save_survey_data(self.survey)
                            await self.cog.update_survey_message(self.survey)
                            await interaction.response.send_message(msg, ephemeral=True, delete_after=5)
                        except Exception as e:
                            debug_log(f"Erreur vote callback: {e}", "ERROR")
                    return vote_callback

                vote_btn.callback = create_vote_callback(i)

                container.add_item(
                    ui.Section(
                        ui.TextDisplay(choice_text),
                        accessory=vote_btn
                    )
                )

            if footer:
                container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
                container.add_item(ui.TextDisplay(footer))

            self.add_item(container)
        except Exception as e:
            debug_log(f"Erreur critique _build_layout SurveyPublicView: {e}", "ERROR")
            traceback.print_exc()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return True


# ==============================================================================
# ------------------------------ COG PRINCIPAL ---------------------------------
# ==============================================================================
class Sondage(commands.Cog):
    """📊 Module Sondage — Gestion des sondages interactifs (Layout V2)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../../data/public/utilitaires/data_sondage"))
        os.makedirs(self.base_dir, exist_ok=True)
        self.cleanup_loop.start()
        debug_log("Cog Sondage initialisé avec succès.", "SUCCESS")

    def cog_unload(self) -> None:
        self.cleanup_loop.cancel()
        debug_log("Cog Sondage déchargé.", "WARNING")

    def save_survey_data(self, survey: Survey) -> None:
        try:
            path = os.path.join(self.base_dir, f"{survey.message_id}.json")
            with open(path, "w", encoding='utf-8') as f:
                json.dump(survey.to_dict(), f, indent=4, ensure_ascii=False)
        except Exception as e:
            debug_log(f"Erreur save_survey_data: {e}", "ERROR")
            traceback.print_exc()

    @tasks.loop(minutes=1)
    async def cleanup_loop(self) -> None:
        """Vérifie l'expiration des sondages selon leur durée configurée."""
        now = datetime.now(timezone.utc).timestamp()
        if not os.path.exists(self.base_dir):
            return
        for file in os.listdir(self.base_dir):
            if file.endswith(".json"):
                try:
                    p = os.path.join(self.base_dir, file)
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    s = Survey(**data)
                    duration_sec = s.get_duration_in_seconds()
                    if not s.ended_at and (now - s.created_at >= duration_sec):
                        await self.close_survey(s)
                except Exception as e:
                    debug_log(f"Erreur cleanup_loop sur {file}: {e}", "ERROR")

    async def close_survey(self, survey: Survey) -> None:
        """Met à jour l'affichage final, actualise la vue et supprime le fichier JSON de suivi actif."""
        survey.ended_at = datetime.now(timezone.utc).timestamp()
        chan = self.bot.get_channel(survey.channel_id)
        if chan:
            try:
                msg = await chan.fetch_message(survey.message_id)
                public_view = SurveyPublicView(survey, self)
                await msg.edit(view=public_view)
            except Exception:
                pass

        path = os.path.join(self.base_dir, f"{survey.message_id}.json")
        if os.path.exists(path):
            os.remove(path)

    async def update_survey_message(self, survey: Survey) -> None:
        chan = self.bot.get_channel(survey.channel_id)
        if not chan:
            return
        try:
            msg = await chan.fetch_message(survey.message_id)
            public_view = SurveyPublicView(survey, self)
            await msg.edit(view=public_view)
        except Exception as e:
            debug_log(f"Erreur update_survey_message: {e}", "ERROR")

    @commands.hybrid_command(name="sondage", description="Permet de créer un sondage public.")
    async def sondage(self, ctx: commands.Context) -> None:
        debug_log(f"Commande /sondage invoquée par {ctx.author} ({ctx.author.id})", "INFO")
        
        if not ctx.guild:
            await ctx.send(f"{E.ERREUR} Cette commande ne peut être exécutée que dans un serveur.")
            return

        try:
            survey = Survey(guild_id=ctx.guild.id if ctx.guild else None, author_id=ctx.author.id)
            view = SurveySetupView(self, survey, ctx.author, ctx)

            if ctx.interaction:
                await ctx.send(view=view, ephemeral=False)
            else:
                await ctx.reply(view=view, mention_author=False)
        except Exception as exc:
            debug_log(f"Erreur lors de l'exécution de la commande /sondage : {exc}", "ERROR")
            traceback.print_exc()
            await ctx.send(f"{E.ERREUR} Une erreur est survenue lors de l'ouverture du gestionnaire de sondages.")


async def setup(bot: commands.Bot) -> None:
    cog = Sondage(bot)
    await bot.add_cog(cog)
    debug_log("Cog Sondage enregistré et chargé avec succès.", "SUCCESS")

    # Restauration des vues persistantes au redémarrage
    if os.path.exists(cog.base_dir):
        for file in os.listdir(cog.base_dir):
            if file.endswith(".json"):
                try:
                    with open(os.path.join(cog.base_dir, file), "r", encoding='utf-8') as f:
                        data = json.load(f)
                    s = Survey(**data)
                    bot.add_view(SurveyPublicView(s, cog))
                except Exception as e:
                    debug_log(f"Erreur restauration vue sondage {file}: {e}", "ERROR")