# ==============================================================================
# cogs/public/divertissement/everyone.py - RAPPORT DES PINGS (LAYOUT V2)
# ==============================================================================
DEBUG_MODE = True  # <-- Bascule globale pour activer/désactiver tous les logs console

from datetime import datetime, timedelta, timezone
from collections import Counter
import discord
from discord import app_commands, ui
from discord.ext import commands

# Intégration de l'écosystème Vax v3
from utils.config_theme import config_manager
from utils.config_data import DataManager
from utils.config_emoji import Emoji as E


EMOJI_TOP = getattr(E, "CLASSEMENT", "🏆")
EMOJI_PREV = getattr(E, "FLECHE_GAUCHE", "⬅️")
EMOJI_NEXT = getattr(E, "FLECHE_DROITE", "➡️")


def debug_log(message: str, level: str = "INFO"):
    """Affiche un log esthétique dans la console si le mode debug est actif."""
    if not DEBUG_MODE:
        return
    
    colors = {
        "INFO": "\033[94m",     # Bleu
        "SUCCESS": "\033[92m",  # Vert
        "ERROR": "\033[91m",    # Rouge
        "WARNING": "\033[93m"   # Jaune
    }
    reset = "\033[0m"
    color = colors.get(level.upper(), "\033[97m")
    print(f"{color}[DEBUG - PingStats] [{level.upper()}] {message}{reset}")


# ==============================================================================
# CALCULATEUR DE STATISTIQUES DE PINGS
# ==============================================================================
async def fetch_ping_data(guild: discord.Guild, hours: int):
    """Parcourt l'historique des salons textuels pour collecter les pings et leurs métadonnées."""
    time_limit = datetime.now(timezone.utc) - timedelta(hours=hours)
    total_pings = 0
    user_pings = Counter()
    ping_details = []  # Stocke chaque occurrence de ping : {"user": member, "channel": channel, "timestamp": timestamp, "content": snippet}

    for channel in guild.text_channels:
        try:
            if not channel.permissions_for(guild.me).read_message_history:
                continue

            async for message in channel.history(after=time_limit, limit=None):
                if message.mention_everyone:
                    total_pings += 1
                    user_pings[message.author] += 1
                    
                    # Enregistrement des détails pour l'exploration interactive (sans mention brute dans le texte)
                    clean_content = message.content.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")
                    ping_details.append({
                        "user": message.author,
                        "channel": channel,
                        "timestamp": int(message.created_at.timestamp()),
                        "content": clean_content[:100] if clean_content else "*Message vide/média*"
                    })
        except Exception as e:
            debug_log(f"Erreur de lecture sur le salon {channel.name}: {e}", "WARNING")
            continue

    return total_pings, user_pings, ping_details


# ==============================================================================
# INTERFACE UTILISATEUR (LAYOUT V2 & SÉLECTEUR DE DÉTAIL AVEC PAGINATION)
# ==============================================================================
class PingStatsLayoutView(ui.LayoutView):
    ITEMS_PER_PAGE = 5  # Nombre de détails de pings affichés par page

    def __init__(self, bot, guild, user, hours, time_text, total_pings, user_pings, ping_details):
        super().__init__(timeout=600)
        self.bot = bot
        self.guild = guild
        self.author = user
        self.hours = hours
        self.time_text = time_text
        self.total_pings = total_pings
        self.user_pings = user_pings
        self.ping_details = ping_details
        self.selected_target_id = None
        self.current_page = 0
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(f"{E.ERREUR} Ce panneau ne vous appartient pas.", ephemeral=True)
            return False
        return True

    def _build(self):
        self.clear_items()

        # Récupération du thème V2 du serveur
        try:
            theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.author, self.bot)
            accent_color = int(theme.get("color", discord.Color.blurple().value))
            footer_text = theme.get("footer_text", "Rapport des Pings - Vax v3")
        except Exception as e:
            debug_log(f"Erreur de thème V2 : {e}", "ERROR")
            accent_color = discord.Color.blurple().value
            footer_text = "Rapport des Pings - Vax v3"

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)

        # En-tête (Dépourvu de toute mention @everyone ou @here pour éviter les pings intempestifs)
        container.add_item(ui.TextDisplay(f"## {E.ANNONCE} Rapport des Pings (everyone / here) - {self.time_text}"))

        # Résumé textuel sécurisé (noms d'utilisateurs sans pings directs dans l'affichage texte de base)
        top_5_text = ""
        if self.user_pings:
            for i, (user, count) in enumerate(self.user_pings.most_common(5), 1):
                safe_username = user.name.replace("@", "@\u200b")
                top_5_text += f"{i}. **{safe_username}** : `{count}` pings\n"
        else:
            top_5_text = "*Aucun ping détecté sur cette période.*"

        description = (
            f"**Quantité totale**\n"
            f"**{self.total_pings}** pings globaux\n\n"
            f"**{EMOJI_TOP} Top 5 des tagueurs**\n"
            f"{top_5_text}"
        )

        # Thumbnail du serveur ou de l'utilisateur ciblé si sélectionné
        target_member = self.guild.get_member(self.selected_target_id) if self.selected_target_id else None
        thumb_url = None
        if target_member and target_member.display_avatar:
            thumb_url = target_member.display_avatar.url
        elif self.guild.icon:
            thumb_url = self.guild.icon.url
        elif self.bot.user:
            thumb_url = self.bot.user.display_avatar.url

        if thumb_url:
            container.add_item(
                ui.Section(
                    description,
                    accessory=ui.Thumbnail(thumb_url, description="Avatar / Logo")
                )
            )
        else:
            container.add_item(ui.TextDisplay(description))

        container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

        # --- PAGE D'ACCUEIL OU AFFICHAGE DES DÉTAILS AVEC PAGINATION ---
        if self.selected_target_id:
            target_name = target_member.display_name if target_member else "Utilisateur inconnu"
            user_logs = [d for d in self.ping_details if d["user"].id == self.selected_target_id]
            
            total_logs = len(user_logs)
            total_pages = max(1, (total_logs + self.ITEMS_PER_PAGE - 1) // self.ITEMS_PER_PAGE) if total_logs > 0 else 1
            self.current_page = max(0, min(self.current_page, total_pages - 1))
            
            start_idx = self.current_page * self.ITEMS_PER_PAGE
            end_idx = start_idx + self.ITEMS_PER_PAGE
            page_logs = user_logs[start_idx:end_idx]

            logs_text = ""
            if page_logs:
                for log in page_logs:
                    logs_text += f"• Salon {log['channel'].mention} — <t:{log['timestamp']}:R>\n  `{log['content']}`\n"
            else:
                logs_text = "Aucun détail d'historique récent."

            container.add_item(ui.TextDisplay(f"### {E.RECHERCHE} Historique de {target_name} (Page {self.current_page + 1}/{total_pages})"))
            container.add_item(ui.TextDisplay(logs_text))

            # Boutons de pagination gauche / droite
            if total_pages > 1:
                nav_row = ui.ActionRow()
                btn_prev = ui.Button(
                    label="Précédent",
                    style=discord.ButtonStyle.secondary,
                    emoji=EMOJI_PREV,
                    disabled=(self.current_page == 0)
                )
                btn_prev.callback = self._cb_prev_page
                nav_row.add_item(btn_prev)

                btn_next = ui.Button(
                    label="Suivant",
                    style=discord.ButtonStyle.secondary,
                    emoji=EMOJI_NEXT,
                    disabled=(self.current_page >= total_pages - 1)
                )
                btn_next.callback = self._cb_next_page
                nav_row.add_item(btn_next)
                container.add_item(nav_row)

            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
        else:
            container.add_item(ui.TextDisplay(f"{E.INFO} *Astuce : Sélectionnez un tagueur dans le menu ci-dessous pour inspecter ses salons et horaires de pings.*"))
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))

        # --- SÉLECTEUR DE PÉRIODE ---
        period_options = [
            discord.SelectOption(label="1 heure", value="1", description="Dernière heure", emoji=E.TEMPS, default=(self.hours == 1)),
            discord.SelectOption(label="3 heures", value="3", description="Dernières 3 heures", emoji=E.TEMPS, default=(self.hours == 3)),
            discord.SelectOption(label="6 heures", value="6", description="Dernières 6 heures", emoji=E.TEMPS, default=(self.hours == 6)),
            discord.SelectOption(label="12 heures", value="12", description="Dernières 12 heures", emoji=E.TEMPS, default=(self.hours == 12)),
            discord.SelectOption(label="24 heures", value="24", description="Dernières 24 heures", emoji=E.TEMPS, default=(self.hours == 24)),
            discord.SelectOption(label="48 heures", value="48", description="Derniers 2 jours", emoji=E.TEMPS, default=(self.hours == 48)),
            discord.SelectOption(label="7 jours", value="168", description="Dernière semaine", emoji=E.TEMPS, default=(self.hours == 168)),
        ]
        row_period = ui.ActionRow()
        period_select = ui.Select(
            placeholder="Changer la période d'analyse...",
            min_values=1,
            max_values=1,
            options=period_options
        )
        period_select.callback = self._cb_period_select
        row_period.add_item(period_select)
        container.add_item(row_period)

        # --- SÉLECTEUR DE MEMBRE POUR VOIR LES SALONS ET HEURES DE PING ---
        if self.user_pings:
            user_options = [
                discord.SelectOption(
                    label=f"{user.name}"[:100],
                    value=str(user.id),
                    description=f"{count} pings enregistrés",
                    emoji=E.PROFIL,
                    default=(self.selected_target_id == user.id)
                )
                for user, count in self.user_pings.most_common(25)
            ]
            
            # Option de retour à l'accueil si un utilisateur est sélectionné
            if self.selected_target_id is not None:
                user_options.insert(0, discord.SelectOption(
                    label="Retour à l'accueil global",
                    value="home",
                    description="Fermer les détails de l'utilisateur",
                    emoji=E.HOME
                ))

            row_user = ui.ActionRow()
            user_select = ui.Select(
                placeholder="Sélectionner un tagueur pour voir où/quand...",
                min_values=1,
                max_values=1,
                options=user_options
            )
            user_select.callback = self._cb_user_select
            row_user.add_item(user_select)
            container.add_item(row_user)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    async def _cb_prev_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if self.current_page > 0:
            self.current_page -= 1
        self._build()
        await interaction.edit_original_response(view=self, allowed_mentions=discord.AllowedMentions.none())

    async def _cb_next_page(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.current_page += 1
        self._build()
        await interaction.edit_original_response(view=self, allowed_mentions=discord.AllowedMentions.none())

    async def _cb_period_select(self, interaction: discord.Interaction):
        # 1) Affichage immédiat du conteneur de chargement avec l'émoji personnalisé E.LOAD
        loading_container = ui.Container(spoiler=False)
        loading_container.add_item(ui.TextDisplay(f"## {E.LOAD} Analyse et recalcul des pings en cours..."))
        loading_view = ui.LayoutView()
        loading_view.add_item(loading_container)
        
        await interaction.response.edit_message(view=loading_view, allowed_mentions=discord.AllowedMentions.none())

        # 2) Récupération de la nouvelle valeur de période
        selected_value = int(interaction.data.get("values", ["24"])[0])
        
        mapping = {
            1: "Dernière heure",
            3: "Dernières 3 heures",
            6: "Dernières 6 heures",
            12: "Dernières 12 heures",
            24: "Dernières 24 heures",
            48: "Derniers 2 jours",
            168: "Dernière semaine"
        }
        new_time_text = mapping.get(selected_value, "cette période")

        debug_log(f"Recalcul des pings demandé pour {new_time_text} par {interaction.user}", "INFO")
        
        # 3) Calcul effectif des données
        total, pings, details = await fetch_ping_data(self.guild, selected_value)
        
        self.hours = selected_value
        self.time_text = new_time_text
        self.total_pings = total
        self.user_pings = pings
        self.ping_details = details
        self.selected_target_id = None
        self.current_page = 0

        # 4) Reconstruction de la vue finale et mise à jour du message
        self._build()
        await interaction.edit_original_response(view=self, allowed_mentions=discord.AllowedMentions.none())

    async def _cb_user_select(self, interaction: discord.Interaction):
        await interaction.response.defer()
        picked_val = interaction.data.get("values", [0])[0]
        
        if picked_val == "home":
            self.selected_target_id = None
        else:
            picked_id = int(picked_val)
            if self.selected_target_id != picked_id:
                self.selected_target_id = picked_id
                self.current_page = 0  # Reset de la pagination lors du changement de membre
            else:
                self.selected_target_id = None
        
        debug_log(f"Sélection utilisateur modifiée : {picked_val}", "INFO")
        self._build()
        await interaction.edit_original_response(view=self, allowed_mentions=discord.AllowedMentions.none())


# ==============================================================================
# COG PRINCIPAL : PING STATS
# ==============================================================================
class PingStats(commands.Cog):
    """Module avancé d'analyse des pings @everyone et @here."""

    def __init__(self, bot):
        self.bot = bot
        debug_log("Cog PingStats initialisé avec succès.", "SUCCESS")

    @commands.hybrid_command(name="everyone", description="Affiche les statistiques détaillées des pings everyone/here")
    @app_commands.describe(hours="Nombre d'heures à analyser (défaut 24)")
    async def everyone_command(self, ctx: commands.Context, hours: int = 24):
        if not ctx.guild:
            return await ctx.send(f"{E.ERREUR} Cette commande doit être utilisée sur un serveur.")

        debug_log(f"Commande /everyone invoquée par {ctx.author} pour {hours}h", "INFO")
        
        time_text_map = {
            1: "Dernière heure",
            3: "Dernières 3 heures",
            6: "Dernières 6 heures",
            12: "Dernières 12 heures",
            24: "Dernières 24 heures",
            48: "Derniers 2 jours",
            168: "Dernière semaine"
        }
        time_text = time_text_map.get(hours, f"Dernières {hours} heures")

        # Affichage immédiat du message de chargement avec l'émoji animé E.LOAD
        loading_container = ui.Container(spoiler=False)
        loading_container.add_item(ui.TextDisplay(f"## {E.LOAD} Analyse des pings en cours..."))
        loading_view = ui.LayoutView()
        loading_view.add_item(loading_container)

        if ctx.interaction:
            await ctx.interaction.response.defer(ephemeral=False)
            sent_msg = await ctx.interaction.followup.send(view=loading_view, wait=True, allowed_mentions=discord.AllowedMentions.none())
        else:
            sent_msg = await ctx.send(view=loading_view, allowed_mentions=discord.AllowedMentions.none())

        total_pings, user_pings, ping_details = await fetch_ping_data(ctx.guild, hours)

        view = PingStatsLayoutView(
            bot=self.bot,
            guild=ctx.guild,
            user=ctx.author,
            hours=hours,
            time_text=time_text,
            total_pings=total_pings,
            user_pings=user_pings,
            ping_details=ping_details
        )
        view.message = sent_msg

        await sent_msg.edit(view=view, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot):
    await bot.add_cog(PingStats(bot))
    debug_log("Cog PingStats enregistré dans le bot.", "SUCCESS")