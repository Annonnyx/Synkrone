"""
COGNIFY MODULE - MARRY & PROFILE MANAGEMENT (VAX V3)
====================================================
Module unifié pour la gestion des unions, demandes en mariage et profils sentimentaux.
"""

from __future__ import annotations

import math
import time
from datetime import datetime

import discord
from discord import app_commands, ui
from discord.ext import commands

from utils.config_data import DataManager
from utils.config_emoji import Emoji as E
from utils.config_id import IdModal
from utils.config_theme import config_manager

# ==============================================================================
# --------------------------- CONFIGURATION & LOGS -----------------------------
# ==============================================================================

# Variables globales de débogage (Directive 1a & 1b)
DEBUG_MODE = True
ERROR_LOG_ONLY = False

# Centralisation des emojis (Directive 1c)
class MarryEmoji:
    HEART = getattr(E, "HEART", "❤️")
    BROKEN_HEART = "💔"
    RING = "💍"
    PROFILE = getattr(E, "PROFIL", "👤")
    HISTORY = "📜"
    SUCCESS = getattr(E, "SUCCESS", "✅")
    ERROR = getattr(E, "ERROR", "❌")
    WARNING = "⚠️"
    CUPID = "💘"
    WEDDING = "🎉"
    DIVORCE = "🪓"

# Gestionnaire de données standardisé via DataManager du projet
db = DataManager("public/divertissement/data_marry")


# ==============================================================================
# ------------------------------ VUES INTERACTIVES -----------------------------
# ==============================================================================

class MarryLayoutView(ui.LayoutView):
    """Vue principale unifiée gérant le profil, la recherche d'ID, l'historique et les interactions d'union."""
    def __init__(self, cog: Marry, guild: discord.Guild, author: discord.Member, target_user: discord.Member):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.author = author
        self.target = target_user
        self.current_page = 0
        self.mode = "profile"  # "profile", "history", "divorce_confirm"
        self._build()

    def _build(self):
        self.clear_items()

        # Récupération du thème global/serveur
        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.author, self.cog.bot) if config_manager else {}
        accent_color = int(theme.get("color", 0xFF69B4))
        footer_text = theme.get("footer_text", "")

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        is_owner = self.author.id == self.target.id

        # Section d'en-tête avec bouton ID en haut à droite (accessory)
        header_section = ui.Section(
            ui.TextDisplay(f"# {MarryEmoji.CUPID} Registre Sentimental : {self.target.display_name}"),
            accessory=ui.Button(
                label="ID",
                style=discord.ButtonStyle.secondary,
                emoji="🆔",
                custom_id="marry:id_search"
            )
        )
        container.add_item(header_section)

        if self.target.display_avatar:
            try:
                container.add_item(
                    ui.Section(
                        ui.TextDisplay(f"### {MarryEmoji.PROFILE} Profil de {self.target.mention}"),
                        accessory=ui.Thumbnail(self.target.display_avatar.url, description=f"Avatar de {self.target.display_name}")
                    )
                )
            except Exception:
                # Fallback silencieux si Discord refuse temporairement l'URL de l'avatar.
                pass

        if self.mode == "profile":
            raw_data = db.load(self.target.id) or {}
            data = {
                "user_name": self.target.display_name,
                "points": raw_data.get("points", 0),
                "marriages_count": raw_data.get("marriages_count", 0),
                "refusals_received": raw_data.get("refusals_received", 0),
                "refusals_given": raw_data.get("refusals_given", 0),
                "current_marriages": raw_data.get("current_marriages", []),
                "history": raw_data.get("history", [])
            }
            
            stats_text = ""
            if data['refusals_received'] != 0:
                stats_text += f"- **Râteaux Reçus :** `{data['refusals_received']}`\n"
            if data['refusals_given'] != 0:
                stats_text += f"- **Râteaux Donnés :** `{data['refusals_given']}`\n"
            if data['marriages_count'] != 0:
                stats_text += f"- **Unions totales :** `{data['marriages_count']}`\n"

            if stats_text:
                container.add_item(ui.TextDisplay(stats_text))

            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

            if data["current_marriages"]:
                marriages_desc = "### 💞 Unions Actuelles\n"
                for m in data["current_marriages"]:
                    partner_mention = self.cog.format_mention(self.guild, m['partner_id'], m['partner_name'])
                    time_str = f"<t:{m['timestamp']}:R>"
                    if m['proposer_id'] == self.target.id:
                        marriages_desc += f"› A demandé en mariage {partner_mention} {time_str}\n"
                    else:
                        marriages_desc += f"› Demandé(e) en mariage par {partner_mention} {time_str}\n"
                container.add_item(ui.TextDisplay(marriages_desc))
            else:
                container.add_item(ui.TextDisplay("### 🕊️ Célibataire\n*Aucune union en cours.*"))

            nav_row = ui.ActionRow()
            
            btn_hist = ui.Button(label="Historique Sentimental", style=discord.ButtonStyle.primary, emoji=MarryEmoji.HISTORY)
            btn_hist.callback = self.show_history_callback
            nav_row.add_item(btn_hist)

            if is_owner:
                # Si c'est notre propre profil, on peut voir la liste des mariages pour gérer les divorces si nécessaire
                if data["current_marriages"]:
                    btn_divorce = ui.Button(label="Gérer mes divorces", style=discord.ButtonStyle.secondary, emoji=MarryEmoji.DIVORCE)
                    btn_divorce.callback = self.show_divorce_select_callback
                    nav_row.add_item(btn_divorce)
            else:
                # Si on visite le profil d'un autre utilisateur : vérifier si on est  déjà marié avec lui
                author_raw = db.load(self.author.id) or {}
                author_marriages = author_raw.get("current_marriages", [])
                is_married_with_target = any(m["partner_id"] == self.target.id for m in author_marriages)

                if is_married_with_target:
                    btn_action = ui.Button(label=f"Divorcer de {self.target.display_name}", style=discord.ButtonStyle.danger, emoji=MarryEmoji.DIVORCE)
                    btn_action.callback = self.trigger_divorce_target_callback
                else:
                    btn_action = ui.Button(label=f"Épouser {self.target.display_name}", style=discord.ButtonStyle.success, emoji=MarryEmoji.RING)
                    btn_action.callback = self.trigger_proposal_target_callback
                nav_row.add_item(btn_action)

            container.add_item(nav_row)

        elif self.mode == "history":
            raw_data = db.load(self.target.id) or {}
            history = raw_data.get("history", [])
            
            if not history:
                desc = "L'historique sentimental est désespérément vide."
            else:
                start = self.current_page * 10
                end = start + 10
                desc = "\n".join(history[start:end])
                
            max_pages = max(1, math.ceil(len(history) / 10))
            container.add_item(ui.TextDisplay(f"## {MarryEmoji.HISTORY} Historique (Page {self.current_page + 1}/{max_pages})\n\n{desc}"))

            nav_row = ui.ActionRow()
            btn_back = ui.Button(label="Retour au profil", style=discord.ButtonStyle.secondary, emoji="🔙")
            btn_back.callback = self.show_profile_callback
            nav_row.add_item(btn_back)

            btn_prev = ui.Button(label="◀ Précédent", style=discord.ButtonStyle.primary, disabled=(self.current_page == 0))
            btn_prev.callback = self.prev_page_callback
            nav_row.add_item(btn_prev)

            btn_next = ui.Button(label="Suivant ▶", style=discord.ButtonStyle.primary, disabled=(self.current_page >= max_pages - 1))
            btn_next.callback = self.next_page_callback
            nav_row.add_item(btn_next)

            container.add_item(nav_row)

        elif self.mode == "divorce_select":
            raw_data = db.load(self.author.id) or {}
            marriages = raw_data.get("current_marriages", [])

            container.add_item(ui.TextDisplay(f"## {MarryEmoji.BROKEN_HEART} Procédure de Divorce\nSélectionnez l'union que vous souhaitez rompre :"))

            options = [
                discord.SelectOption(
                    label=f"Divorcer de {m['partner_name']}",
                    value=f"{m['partner_id']}|{m['partner_name']}",
                    emoji=MarryEmoji.DIVORCE
                ) for m in marriages[:25]
            ]
            select = ui.Select(placeholder="Choisissez un partenaire...", options=options)
            select.callback = self.select_divorce_callback
            
            select_row = ui.ActionRow()
            select_row.add_item(select)
            container.add_item(select_row)

            back_row = ui.ActionRow()
            btn_back = ui.Button(label="Retour au profil", style=discord.ButtonStyle.secondary, emoji="🔙")
            btn_back.callback = self.show_profile_callback
            back_row.add_item(btn_back)
            container.add_item(back_row)

        elif self.mode == "divorce_confirm":
            container.add_item(ui.TextDisplay(f"## {MarryEmoji.WARNING} Confirmation de Divorce\nÊtes-vous sûr de vouloir divorcer de **{self.selected_partner_name}** ? Cette action est définitive."))

            confirm_row = ui.ActionRow()
            btn_confirm = ui.Button(label="Confirmer le divorce", style=discord.ButtonStyle.danger, emoji=MarryEmoji.DIVORCE)
            btn_confirm.callback = self.execute_divorce_callback
            confirm_row.add_item(btn_confirm)

            btn_cancel = ui.Button(label="Annuler", style=discord.ButtonStyle.secondary)
            btn_cancel.callback = self.show_profile_callback
            confirm_row.add_item(btn_cancel)

            container.add_item(confirm_row)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            if DEBUG_MODE:
                print(f"\033[93m[WARNING] Utilisateur non autorisé {interaction.user.id} sur la vue de {self.author.id}\033[0m")
            await interaction.response.send_message(f"{MarryEmoji.ERROR} Ce menu ne vous appartient pas.", ephemeral=False)
            return False

        # Gestion du bouton ID custom injecté en accessory de la section d'en-tête
        custom_id = interaction.data.get("custom_id") if interaction.data else None
        if custom_id == "marry:id_search":
            await interaction.response.send_modal(IdModal("user", self._on_user_id_submit))
            return False

        return True

    async def _on_user_id_submit(self, interaction: discord.Interaction, target):
        member = target if isinstance(target, discord.Member) else None
        if member is None:
            await interaction.followup.send(f"{MarryEmoji.ERROR} Utilisateur introuvable.", ephemeral=False)
            return

        self.target = member
        self.mode = "profile"
        db.load(self.target.id)
        self._build()
        if interaction.message:
            await interaction.message.edit(view=self)

    async def show_profile_callback(self, interaction: discord.Interaction):
        self.mode = "profile"
        self._build()
        await interaction.response.edit_message(view=self)

    async def show_history_callback(self, interaction: discord.Interaction):
        self.mode = "history"
        self.current_page = 0
        self._build()
        await interaction.response.edit_message(view=self)

    async def prev_page_callback(self, interaction: discord.Interaction):
        self.current_page = max(0, self.current_page - 1)
        self._build()
        await interaction.response.edit_message(view=self)

    async def next_page_callback(self, interaction: discord.Interaction):
        self.current_page += 1
        self._build()
        await interaction.response.edit_message(view=self)

    async def show_divorce_select_callback(self, interaction: discord.Interaction):
        self.mode = "divorce_select"
        self._build()
        await interaction.response.edit_message(view=self)

    async def select_divorce_callback(self, interaction: discord.Interaction):
        values = interaction.data.get("values", [])
        if values:
            partner_id_str, partner_name = values[0].split('|')
            self.selected_partner_id = int(partner_id_str)
            self.selected_partner_name = partner_name
            self.mode = "divorce_confirm"
            self._build()
            await interaction.response.edit_message(view=self)

    async def execute_divorce_callback(self, interaction: discord.Interaction):
        author_raw = db.load(self.author.id) or {"current_marriages": [], "history": []}
        partner_raw = db.load(self.selected_partner_id) or {"current_marriages": [], "history": []}
        
        author_raw["current_marriages"] = [m for m in author_raw.get("current_marriages", []) if m["partner_id"] != self.selected_partner_id]
        partner_raw["current_marriages"] = [m for m in partner_raw.get("current_marriages", []) if m["partner_id"] != self.author.id]
        
        db.save(self.author.id, author_raw)
        db.save(self.selected_partner_id, partner_raw)
        
        self.cog.add_history_entry(self.author.id, self.author.display_name, f"Vous avez divorcé de {self.cog.format_mention(self.guild, self.selected_partner_id, self.selected_partner_name)}.")
        self.cog.add_history_entry(self.selected_partner_id, self.selected_partner_name, f"{self.cog.format_mention(self.guild, self.author.id, self.author.display_name)} a rompu l'union.")

        self.mode = "profile"
        self._build()
        await interaction.response.edit_message(view=self)

    async def trigger_proposal_target_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.cog.send_proposal_flow(interaction, self.target)

    async def trigger_divorce_target_callback(self, interaction: discord.Interaction):
        self.selected_partner_id = self.target.id
        self.selected_partner_name = self.target.display_name
        self.mode = "divorce_confirm"
        self._build()
        await interaction.response.edit_message(view=self)


class ProposalLayoutView(ui.LayoutView):
    """Vue interactive pour répondre à une demande en mariage via Layout V2."""
    def __init__(self, cog: Marry, guild: discord.Guild, proposer: discord.Member, target: discord.Member):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.proposer = proposer
        self.target = target
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target.id:
            await interaction.response.send_message(
                f"{MarryEmoji.ERROR} Cette demande en mariage ne vous est pas destinée.", ephemeral=False
            )
            return False
        return True

    def _build(self):
        self.clear_items()
        container = ui.Container(accent_color=discord.Color.from_rgb(255, 105, 180), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {MarryEmoji.RING} Demande en mariage !"))
        container.add_item(ui.TextDisplay(f"💌 **{self.target.mention}, consentez-vous à épouser {self.proposer.mention} ?**\n\n*Prenez votre temps, ce choix est engageant !*"))

        row = ui.ActionRow()
        btn_accept = ui.Button(label="Oui je le veux", style=discord.ButtonStyle.success, emoji=MarryEmoji.HEART)
        btn_accept.callback = self.accept_callback
        row.add_item(btn_accept)

        btn_deny = ui.Button(label="Refuser", style=discord.ButtonStyle.secondary, emoji=MarryEmoji.BROKEN_HEART)
        btn_deny.callback = self.deny_callback
        row.add_item(btn_deny)

        container.add_item(row)
        self.add_item(container)

    async def accept_callback(self, interaction: discord.Interaction):
        if self.target.bot:
            if self.guild is not None and self.proposer.id != self.guild.owner_id:
                container = ui.Container(accent_color=discord.Color.red())
                container.add_item(ui.TextDisplay(f"# {MarryEmoji.ERROR} Refus automatique\nSeul le propriétaire du serveur peut épouser le bot."))
                self.clear_items()
                self.add_item(container)
                return await interaction.response.edit_message(view=self)

        now_ts = int(time.time())
        proposer_raw = db.load(self.proposer.id) or {"marriages_count": 0, "current_marriages": [], "history": []}
        target_raw = db.load(self.target.id) or {"marriages_count": 0, "current_marriages": [], "history": []}

        proposer_raw["marriages_count"] = proposer_raw.get("marriages_count", 0) + 1
        target_raw["marriages_count"] = target_raw.get("marriages_count", 0) + 1

        if "current_marriages" not in proposer_raw: proposer_raw["current_marriages"] = []
        if "current_marriages" not in target_raw: target_raw["current_marriages"] = []

        proposer_raw["current_marriages"].append({
            "partner_id": self.target.id, "partner_name": self.target.display_name, "timestamp": now_ts, "proposer_id": self.proposer.id
        })
        target_raw["current_marriages"].append({
            "partner_id": self.proposer.id, "partner_name": self.proposer.display_name, "timestamp": now_ts, "proposer_id": self.proposer.id
        })

        db.save(self.proposer.id, proposer_raw)
        db.save(self.target.id, target_raw)

        self.cog.add_history_entry(self.proposer.id, self.proposer.display_name, f"Vous vous êtes marié(e) avec {self.cog.format_mention(self.guild, self.target.id, self.target.display_name)}.")
        self.cog.add_history_entry(self.target.id, self.target.display_name, f"Vous avez accepté la demande en mariage de {self.cog.format_mention(self.guild, self.proposer.id, self.proposer.display_name)}.")

        container = ui.Container(accent_color=discord.Color.from_rgb(255, 105, 180))
        container.add_item(ui.TextDisplay(f"# {MarryEmoji.WEDDING} Vive les Mariés ! {MarryEmoji.WEDDING}\n{self.target.mention} a dit **OUI** à {self.proposer.mention} ! Que votre union soit éternelle."))
        
        self.clear_items()
        self.add_item(container)
        await interaction.response.edit_message(view=self)

    async def deny_callback(self, interaction: discord.Interaction):
        proposer_raw = db.load(self.proposer.id) or {"refusals_received": 0, "history": []}
        target_raw = db.load(self.target.id) or {"refusals_given": 0, "history": []}

        proposer_raw["refusals_received"] = proposer_raw.get("refusals_received", 0) + 1
        target_raw["refusals_given"] = target_raw.get("refusals_given", 0) + 1

        db.save(self.proposer.id, proposer_raw)
        db.save(self.target.id, target_raw)

        self.cog.add_history_entry(self.proposer.id, self.proposer.display_name, f"{self.cog.format_mention(self.guild, self.target.id, self.target.display_name)} a refusé votre demande.")
        self.cog.add_history_entry(self.target.id, self.target.display_name, f"Vous avez refusé la demande de {self.cog.format_mention(self.guild, self.proposer.id, self.proposer.display_name)}.")

        container = ui.Container(accent_color=discord.Color.dark_gray())
        container.add_item(ui.TextDisplay(f"# {MarryEmoji.BROKEN_HEART} Aïe... Coup dur.\n{self.target.mention} a gentiment repoussé la demande de {self.proposer.mention}."))

        self.clear_items()
        self.add_item(container)
        await interaction.response.edit_message(view=self)


# ==============================================================================
# ------------------------------- COG MARRY ------------------------------------
# ==============================================================================

class Marry(commands.Cog):
    """Gestion unifiée des mariages, profils et recherches via interfaces Layout V2."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        if DEBUG_MODE and not ERROR_LOG_ONLY:
            print(f"\033[94m[INFO] Cog Marry initialisé avec succès.\033[0m")

    def format_mention(self, guild: discord.Guild, user_id: int, user_name: str) -> str:
        member = guild.get_member(user_id)
        if member:
            return member.mention
        return f"`@{user_name}`"

    def add_history_entry(self, user_id: int, user_name: str, entry: str):
        raw = db.load(user_id) or {"user_name": user_name, "points": 0, "marriages_count": 0, "refusals_received": 0, "refusals_given": 0, "current_marriages": [], "history": []}
        now_str = datetime.now().strftime("[%d/%m/%y][%H:%M]")
        if "history" not in raw:
            raw["history"] = []
        raw["history"].insert(0, f"{now_str} {entry}")
        db.save(user_id, raw)
        if DEBUG_MODE and not ERROR_LOG_ONLY:
            print(f"\033[92m[SUCCESS] Historique mis à jour pour {user_id}\033[0m")

    async def send_proposal_flow(self, interaction: discord.Interaction, membre: discord.Member):
        guild = interaction.guild
        author = interaction.user

        if membre.id == author.id:
            return await interaction.followup.send(f"{MarryEmoji.ERROR} Vous ne pouvez pas vous marier avec vous-même !", ephemeral=False)

        author_raw = db.load(author.id) or {"current_marriages": []}
        if any(m["partner_id"] == membre.id for m in author_raw.get("current_marriages", [])):
            return await interaction.followup.send(f"{MarryEmoji.ERROR} Vous êtes  déjà marié(e) avec cette personne !", ephemeral=False)

        if membre.bot:
            if guild is not None and author.id == guild.owner_id:
                bot_raw = db.load(membre.id) or {"marriages_count": 0, "current_marriages": [], "history": []}
                now_ts = int(time.time())

                author_raw["marriages_count"] = author_raw.get("marriages_count", 0) + 1
                bot_raw["marriages_count"] = bot_raw.get("marriages_count", 0) + 1

                if "current_marriages" not in author_raw: author_raw["current_marriages"] = []
                if "current_marriages" not in bot_raw: bot_raw["current_marriages"] = []

                author_raw["current_marriages"].append({"partner_id": membre.id, "partner_name": membre.display_name, "timestamp": now_ts, "proposer_id": author.id})
                bot_raw["current_marriages"].append({"partner_id": author.id, "partner_name": author.display_name, "timestamp": now_ts, "proposer_id": author.id})
                
                db.save(author.id, author_raw)
                db.save(membre.id, bot_raw)
                
                self.add_history_entry(author.id, author.display_name, f"Vous vous êtes marié(e) avec {self.format_mention(guild, membre.id, membre.display_name)}.")
                self.add_history_entry(membre.id, membre.display_name, f"Vous avez accepté la demande de {self.format_mention(guild, author.id, author.display_name)}.")

                container = ui.Container(accent_color=discord.Color.from_rgb(255, 105, 180))
                container.add_item(ui.TextDisplay(f"# {MarryEmoji.WEDDING} Union Divine\n{membre.mention} a dit **OUI** à {author.mention} !"))
                view = ui.LayoutView()
                view.add_item(container)
                return await interaction.edit_original_response(view=view)
            else:
                return await interaction.followup.send(f"{MarryEmoji.ERROR} Seul le propriétaire du serveur peut épouser le bot.", ephemeral=False)

        proposal_view = ProposalLayoutView(self, guild, author, membre)

        # Résolution robuste du salon pour garantir un envoi dans le même salon que le bouton.
        channel = interaction.channel
        if channel is None and guild and interaction.channel_id:
            channel = guild.get_channel(interaction.channel_id)
            if channel is None:
                try:
                    channel = await guild.fetch_channel(interaction.channel_id)
                except Exception:
                    channel = None

        if channel is None or not hasattr(channel, "send"):
            await interaction.followup.send(
                f"{MarryEmoji.ERROR} Salon introuvable pour envoyer la demande en mariage.",
                ephemeral=True,
            )
            return

        try:
            await channel.send(
                view=proposal_view,
            )
            await interaction.followup.send(
                f"{MarryEmoji.SUCCESS} Demande envoyée à {membre.mention} dans ce salon.",
                ephemeral=True,
                allowed_mentions=discord.AllowedMentions(users=False, roles=False, everyone=False),
            )
        except discord.Forbidden:
            await interaction.followup.send(
                f"{MarryEmoji.ERROR} Permissions insuffisantes pour envoyer la demande ici.",
                ephemeral=True,
            )
        except discord.HTTPException as e:
            if DEBUG_MODE:
                print(f"\033[91m[ERROR] Envoi demande mariage impossible: {e}\033[0m")
            await interaction.followup.send(
                f"{MarryEmoji.ERROR} Envoi de la demande impossible (erreur API Discord).",
                ephemeral=True,
            )

    @commands.hybrid_command(name="marry", description="Affiche votre profil de mariage ou celui d'un membre spécifié.")
    @app_commands.describe(membre="L'utilisateur dont vous souhaitez afficher le profil (optionnel)")
    async def marry(self, ctx: commands.Context, membre: discord.Member = None):
        if not ctx.guild:
            if DEBUG_MODE:
                print(f"\033[91m[ERROR] Tentative d'exécution de /marry en DM par {ctx.author.id}\033[0m")
            return await ctx.send(f"{MarryEmoji.ERROR} Cette commande ne peut être exécutée que sur un serveur.")

        # ²marry @tag : envoi direct d'une demande en mariage dans le salon courant.
        if membre is not None:
            proposal_view = ProposalLayoutView(self, ctx.guild, ctx.author, membre)

            if membre.id == ctx.author.id:
                return await ctx.send(f"{MarryEmoji.ERROR} Vous ne pouvez pas vous marier avec vous-même !")

            author_raw = db.load(ctx.author.id) or {"current_marriages": []}
            if any(m["partner_id"] == membre.id for m in author_raw.get("current_marriages", [])):
                return await ctx.send(f"{MarryEmoji.ERROR} Vous êtes  déjà marié(e) avec cette personne !")

            if membre.bot and ctx.author.id != ctx.guild.owner_id:
                return await ctx.send(f"{MarryEmoji.ERROR} Seul le propriétaire du serveur peut épouser le bot.")

            try:
                await ctx.channel.send(
                    view=proposal_view,
                    allowed_mentions=discord.AllowedMentions(users=False, roles=False, everyone=False),
                )
                return await ctx.send(f"{MarryEmoji.SUCCESS} Demande envoyée à {membre.mention} dans ce salon.")
            except discord.Forbidden:
                return await ctx.send(f"{MarryEmoji.ERROR} Permissions insuffisantes pour envoyer la demande ici.")
            except discord.HTTPException as e:
                if DEBUG_MODE:
                    print(f"\033[91m[ERROR] Envoi demande mariage impossible via commande: {e}\033[0m")
                return await ctx.send(f"{MarryEmoji.ERROR} Envoi de la demande impossible (erreur API Discord).")

        target = ctx.author
        db.load(target.id)

        view = MarryLayoutView(self, ctx.guild, ctx.author, target)
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    if DEBUG_MODE and not ERROR_LOG_ONLY:
        print(f"\033[94m[INFO] Chargement du module cogs.PUBLIQUE.divertissement.marry...\033[0m")
    await bot.add_cog(Marry(bot))