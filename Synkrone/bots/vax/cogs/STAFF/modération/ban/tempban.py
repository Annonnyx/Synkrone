"""
COGNITIVE MODULE - TempBan (Bannissement temporaire)
====================================================
Gestionnaire interactif et exécution rapide directe (ex: Â²tempban 723720252134785057 1h) avec notification MP et fallbacks UI.
"""

from __future__ import annotations

import re

import discord
from discord import app_commands, ui
from discord.ext import commands

from utils.config_data import DataManager
from utils.config_emoji import Emoji as E
from utils.config_perm import ensure_command_permission, perm_command
from utils.config_theme import config_manager

# --- CONFIGURATION DES LOGS ---
DEBUG_MODE = True
ERROR_LOGS_ONLY = False
ALERT_EMOJI = getattr(E, "ATTENTION", "âš ï¸")
EMOJI_ERROR = getattr(E, "REFUS", getattr(E, "REFUSER", "âŒ"))
EMOJI_SUCCESS = getattr(E, "VALIDE", getattr(E, "VALIDER", "âœ…"))


class TempBanView(ui.LayoutView):
    def __init__(self, ctx: commands.Context, members: list[discord.User]):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.members = members
        self.duration = "24h"
        self.duration_seconds = 86400
        self.reason = "Aucune raison spécifiée"
        self.db = DataManager("staff/moderation/banlist_serveur")
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(f"{getattr(E, 'ERREUR', 'âŒ')} Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        return True

    def _build(self):
        self.clear_items()
        theme = config_manager.get_layout_v2_theme(self.ctx.guild.id, self.ctx.guild, self.ctx.author, self.ctx.bot)
        color = int(theme.get("color", 0xFAA61A))
        footer_text = theme.get("footer_text", "")

        members_text = "\n".join([f"**{i+1}.** {m} (`{m.id}`)" for i, m in enumerate(self.members)]) if self.members else "`Aucun membre sélectionné`"

        container = ui.Container(accent_color=discord.Color(color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {ALERT_EMOJI} Menu de Bannissement Temporaire"))
        container.add_item(
            ui.TextDisplay(
                f"**Membres ciblés :**\n{members_text}\n\n"
                f"{getattr(E, 'HORLOGE', 'â±ï¸')} **Durée :** `{self.duration}`\n"
                f"{getattr(E, 'MEMO', 'ðŸ“')} **Raison :** `{self.reason}`"
            )
        )

        row = ui.ActionRow()
        ban_btn = ui.Button(label="Exécuter TempBan", style=discord.ButtonStyle.danger, emoji=getattr(E, 'MODIFIER', 'ðŸ”¨'), disabled=not bool(self.members))
        ban_btn.callback = self.execute_tempban
        row.add_item(ban_btn)
        container.add_item(row)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    async def execute_tempban(self, interaction: discord.Interaction):
        bans = self.db.load(self.ctx.guild.id) or {}
        success_count = 0
        already_banned_count = 0
        failed_count = 0

        for user in self.members:
            try:
                try:
                    await self.ctx.guild.fetch_ban(user)
                    already_banned_count += 1
                    continue
                except discord.NotFound:
                    pass

                member = self.ctx.guild.get_member(user.id)
                me_member = self.ctx.guild.me
                if member and me_member and member.top_role >= me_member.top_role:
                    failed_count += 1
                    continue

                try:
                    dm_view = ui.LayoutView(timeout=10)
                    dm_container = ui.Container(accent_color=discord.Color(0xFAA61A), spoiler=False)
                    dm_container.add_item(ui.TextDisplay(f"# {EMOJI_ERROR} Notification de Bannissement Temporaire"))
                    dm_container.add_item(ui.TextDisplay(f"Vous avez été temporairement banni de **{self.ctx.guild.name}** pour **{self.duration}**.\n**Raison :** {self.reason}"))
                    dm_view.add_item(dm_container)
                    await user.send(view=dm_view)
                except Exception:
                    pass

                await self.ctx.guild.ban(user, reason=f"TempBan par {self.ctx.author}: {self.reason}")
                bans[str(user.id)] = {
                    "Nom complet": str(user),
                    "Raison": self.reason,
                    "Date": discord.utils.utcnow().strftime("%d/%m/%Y"),
                    "Heure": discord.utils.utcnow().strftime("%H:%M"),
                    "Modérateur": str(self.ctx.author),
                    "Type": f"TEMPBAN ({self.duration})",
                    "ExpiresAt": discord.utils.utcnow().timestamp() + self.duration_seconds
                }
                success_count += 1
            except discord.Forbidden:
                failed_count += 1
            except Exception as e:
                failed_count += 1
                if DEBUG_MODE:
                    print(f"\033[31m[ERREUR TEMPBAN] Échec pour {user}: {e}\033[0m")

        self.db.save(self.ctx.guild.id, bans)
        summary = (
            f"{EMOJI_SUCCESS} {success_count} membre(s) temporairement banni(s) pour {self.duration}.\n"
            f"{ALERT_EMOJI} Deja banni(s): {already_banned_count}.\n"
            f"{EMOJI_ERROR} Echec(s) permissions/hierarchie: {failed_count}."
        )
        await interaction.response.edit_message(content=summary, view=None)


class TempBan(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = DataManager("staff/moderation/banlist_serveur")

    async def _send_fallback(self, ctx: commands.Context, title: str, description: str, color: int = 0xED4245):
        guild = ctx.guild
        guild_id = guild.id if guild else None
        theme = config_manager.get_layout_v2_theme(guild_id, guild, ctx.author, self.bot, force_global=(guild is None))
        footer_text = theme.get("footer_text", "")
        view = ui.LayoutView(timeout=15)
        container = ui.Container(accent_color=discord.Color(color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {EMOJI_ERROR} {title}"))
        container.add_item(ui.TextDisplay(description))
        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))
        view.add_item(container)
        await ctx.send(view=view)

    @perm_command(level=2)
    @commands.hybrid_command(name="tempban", description="Bannir temporairement un utilisateur via menu ou commande rapide.")
    @app_commands.describe(cible="Membre ou ID cible", duree="Durée (ex: 24h, 1h)", raison="Motif optionnel")
    async def tempban(self, ctx: commands.Context, cible: str = None, duree: str = "24h", *, raison: str = "Aucune raison fournie"):
        if not ctx.guild:
            return await self._send_fallback(ctx, "Action impossible", "Cette commande doit être utilisée sur un serveur.")

        if not await ensure_command_permission(ctx, command_name="tempban"):
            return

        if cible:
            match_id = re.search(r'(\d{17,19})', cible)
            if match_id:
                uid = int(match_id.group(1))
                target_user = self.bot.get_user(uid)
                if not target_user:
                    try:
                        target_user = await self.bot.fetch_user(uid)
                    except Exception:
                        target_user = None

                if target_user:
                    units = {'a': 31536000, 'M': 2592000, 'S': 604800, 'j': 86400, 'h': 3600, 'm': 60, 's': 1}
                    sec_match = re.findall(r"(\d+)([aSMjhms])", duree.lower())
                    total_seconds = sum(int(val) * units[unit] for val, unit in sec_match) if sec_match else 86400

                    try:
                        try:
                            await ctx.guild.fetch_ban(target_user)
                            try:
                                dm_view = ui.LayoutView(timeout=10)
                                dm_container = ui.Container(accent_color=discord.Color(0xFAA61A), spoiler=False)
                                dm_container.add_item(ui.TextDisplay(f"# {ALERT_EMOJI} Statut du compte"))
                                dm_container.add_item(ui.TextDisplay(f"Vous etes deja banni du serveur **{ctx.guild.name}**."))
                                dm_view.add_item(dm_container)
                                await target_user.send(view=dm_view)
                            except Exception:
                                pass
                            return await self._send_fallback(
                                ctx,
                                "Utilisateur deja banni",
                                f"{ALERT_EMOJI} {target_user} est deja banni. Un message prive a ete envoye.",
                                color=0xFAA61A,
                            )
                        except discord.NotFound:
                            pass

                        member = ctx.guild.get_member(uid)
                        me_member = ctx.guild.me
                        if member and me_member and member.top_role >= me_member.top_role:
                            return await self._send_fallback(
                                ctx,
                                "Action refusee",
                                "Je ne peux pas bannir cet utilisateur: role superieur ou egal au mien.",
                            )

                        # Envoi du message privé d'avertissement avant le ban direct
                        try:
                            theme = config_manager.get_layout_v2_theme(ctx.guild.id, ctx.guild, ctx.author, self.bot)
                            color = int(theme.get("color", 0xFAA61A))
                            dm_view = ui.LayoutView(timeout=10)
                            dm_container = ui.Container(accent_color=discord.Color(color), spoiler=False)
                            dm_container.add_item(ui.TextDisplay(f"# {EMOJI_ERROR} Notification de Bannissement Temporaire"))
                            dm_container.add_item(ui.TextDisplay(f"Vous avez été temporairement banni de **{ctx.guild.name}** pour **{duree}**.\n**Raison :** {raison}"))
                            dm_view.add_item(dm_container)
                            await target_user.send(view=dm_view)
                        except Exception:
                            pass

                        await ctx.guild.ban(target_user, reason=f"TempBan direct par {ctx.author}: {raison}")
                        
                        bans = self.db.load(ctx.guild.id) or {}
                        bans[str(target_user.id)] = {
                            "Nom complet": str(target_user),
                            "Raison": raison,
                            "Date": discord.utils.utcnow().strftime("%d/%m/%Y"),
                            "Heure": discord.utils.utcnow().strftime("%H:%M"),
                            "Modérateur": str(ctx.author),
                            "Type": f"TEMPBAN ({duree})",
                            "ExpiresAt": discord.utils.utcnow().timestamp() + total_seconds
                        }
                        self.db.save(ctx.guild.id, bans)

                        if DEBUG_MODE and not ERROR_LOGS_ONLY:
                            print(f"\033[32m[SUCCÈS TEMPBAN DIRECT] {target_user} banni pour {duree} par {ctx.author}\033[0m")

                        # Affichage du layout de confirmation persistant et visible dans le salon
                        theme = config_manager.get_layout_v2_theme(ctx.guild.id, ctx.guild, ctx.author, self.bot)
                        color = int(theme.get("color", 0xFAA61A))
                        footer_text = theme.get("footer_text", "")

                        success_view = ui.LayoutView(timeout=10)
                        success_container = ui.Container(accent_color=discord.Color(color), spoiler=False)
                        success_container.add_item(ui.TextDisplay(f"# {EMOJI_SUCCESS} Bannissement Temporaire Effectue"))
                        success_container.add_item(ui.TextDisplay(f"ðŸ”¨ **{target_user}** (`{target_user.id}`) a été temporairement banni pour **{duree}**.\n**Raison :** {raison}"))
                        if footer_text:
                            success_container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
                            success_container.add_item(ui.TextDisplay(footer_text))
                        success_view.add_item(success_container)
                        return await ctx.send(view=success_view)
                    except discord.Forbidden:
                        return await self._send_fallback(
                            ctx,
                            "Permissions insuffisantes",
                            "Je ne peux pas bannir cet utilisateur (permissions manquantes ou role superieur).",
                        )
                    except Exception as e:
                        return await self._send_fallback(ctx, "Erreur d'exécution", f"Échec du bannissement direct : `{e}`")

        users_list = []
        if cible:
            pattern = r'<@!?(\d+)>|(\d{17,19})'
            matches = re.findall(pattern, cible)
            for match in matches:
                uid = int(match[0] if match[0] else match[1])
                u = self.bot.get_user(uid)
                if not u:
                    try:
                        u = await self.bot.fetch_user(uid)
                    except Exception:
                        u = None
                if u and u.id != ctx.author.id:
                    users_list.append(u)

        view = TempBanView(ctx, users_list)
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(TempBan(bot))
