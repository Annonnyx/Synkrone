import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

import discord
from discord import ui
from discord.ext import commands

try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

MAIL_DB = Path.cwd() / "data" / "economie" / "mail.db"
READ_PAGE_SIZE = 25
MESSAGE_RETENTION_SECONDS = 7 * 24 * 3600


def create_embed(guild: discord.Guild | None, user: discord.abc.User | None, bot: commands.Bot, title: str, description: str) -> discord.Embed:
    if config_manager:
        try:
            return config_manager.get_formatted_embed(
                guild=guild,
                user=user,
                bot=bot,
                title=title,
                description=description,
                target_id=guild.id if guild else None,
                force_global=not bool(guild),
            )
        except Exception:
            pass
    embed = discord.Embed(title=title, description=description, color=0x2B2D31)
    return embed


class MailService:
    def __init__(self):
        os.makedirs(MAIL_DB.parent, exist_ok=True)
        self.ensure_schema()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(MAIL_DB)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_schema(self) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS modmail_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_id INTEGER NOT NULL,
                    recipient_id INTEGER NOT NULL,
                    subject TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    is_read INTEGER NOT NULL DEFAULT 0,
                    read_at INTEGER
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS modmail_preferences (
                    user_id INTEGER PRIMARY KEY,
                    dm_notifications INTEGER NOT NULL DEFAULT 1
                )
                """
            )

    def cleanup_old_messages(self) -> None:
        threshold = int(time.time()) - MESSAGE_RETENTION_SECONDS
        with self._get_conn() as conn:
            conn.execute(
                "DELETE FROM modmail_messages WHERE is_read = 1 AND read_at <= ?",
                (threshold,),
            )

    def create_message(self, sender_id: int, recipient_id: int, subject: str, content: str) -> int:
        now = int(time.time())
        with self._get_conn() as conn:
            cursor = conn.execute(
                "INSERT INTO modmail_messages (sender_id, recipient_id, subject, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (sender_id, recipient_id, subject[:100], content[:4000], now),
            )
            return cursor.lastrowid

    def get_unread_messages(self, recipient_id: int) -> list[dict[str, Any]]:
        self.cleanup_old_messages()
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM modmail_messages WHERE recipient_id = ? AND is_read = 0 ORDER BY created_at DESC",
                (recipient_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_read_messages(self, recipient_id: int, page: int) -> list[dict[str, Any]]:
        self.cleanup_old_messages()
        offset = page * READ_PAGE_SIZE
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM modmail_messages WHERE recipient_id = ? AND is_read = 1 ORDER BY read_at DESC LIMIT ? OFFSET ?",
                (recipient_id, READ_PAGE_SIZE, offset),
            ).fetchall()
        return [dict(row) for row in rows]

    def count_read_messages(self, recipient_id: int) -> int:
        self.cleanup_old_messages()
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total FROM modmail_messages WHERE recipient_id = ? AND is_read = 1",
                (recipient_id,),
            ).fetchone()
        return int(row["total"] if row else 0)

    def get_message(self, message_id: int, recipient_id: int) -> Optional[dict[str, Any]]:
        self.cleanup_old_messages()
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM modmail_messages WHERE id = ? AND recipient_id = ?",
                (message_id, recipient_id),
            ).fetchone()
        return dict(row) if row else None

    def mark_as_read(self, message_id: int) -> None:
        now = int(time.time())
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE modmail_messages SET is_read = 1, read_at = ? WHERE id = ?",
                (now, message_id),
            )

    def get_notification_setting(self, user_id: int) -> bool:
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT dm_notifications FROM modmail_preferences WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            self.set_notification_setting(user_id, True)
            return True
        return bool(row["dm_notifications"])

    def set_notification_setting(self, user_id: int, enabled: bool) -> None:
        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO modmail_preferences (user_id, dm_notifications) VALUES (?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET dm_notifications = excluded.dm_notifications",
                (user_id, 1 if enabled else 0),
            )


class SendMailModal(ui.Modal, title="Envoyer un message"):
    recipient_id = ui.TextInput(
        label="ID Discord du destinataire",
        placeholder="123456789012345678",
        required=True,
        max_length=30,
    )
    subject = ui.TextInput(
        label="Objet",
        placeholder="Titre du message",
        required=True,
        max_length=100,
    )
    content = ui.TextInput(
        label="Contenu du message",
        style=discord.TextStyle.paragraph,
        placeholder="Écris ton message ici...",
        required=True,
        max_length=4000,
    )

    def __init__(self, view: "MailMainView"):
        super().__init__()
        self.view_ref = view

    async def on_submit(self, interaction: discord.Interaction):
        recipient_raw = self.recipient_id.value.strip()
        if not recipient_raw.isdigit():
            await interaction.response.send_message("❌ L'ID doit être un nombre valide.", ephemeral=True)
            return

        recipient_id = int(recipient_raw)
        if recipient_id == interaction.user.id:
            await interaction.response.send_message("❌ Tu ne peux pas t'envoyer un message à toi-même.", ephemeral=True)
            return

        message_id = self.view_ref.cog.mail_service.create_message(
            sender_id=interaction.user.id,
            recipient_id=recipient_id,
            subject=self.subject.value.strip(),
            content=self.content.value.strip(),
        )

        dm_sent = await self.view_ref.cog.notify_recipient(
            recipient_id=recipient_id,
            sender_name=interaction.user.display_name,
            subject=self.subject.value.strip(),
            message_id=message_id,
        )

        if dm_sent:
            await interaction.response.send_message(
                f"✅ Message envoyé à `{recipient_id}` et notification privée envoyée.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"✅ Message envoyé à `{recipient_id}`. La notification privée n'a pas pu être envoyée.",
                ephemeral=True,
            )


class ReplyMailModal(ui.Modal, title="Répondre au message"):
    content = ui.TextInput(
        label="Contenu de votre réponse",
        style=discord.TextStyle.paragraph,
        placeholder="Écris ta réponse ici...",
        required=True,
        max_length=4000,
    )

    def __init__(self, view: "MailDetailView", original_message: dict[str, Any]):
        super().__init__()
        self.view_ref = view
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        sender_id = self.original_message["sender_id"]
        subject = f"RE: {self.original_message['subject']}"
        message_id = self.view_ref.cog.mail_service.create_message(
            sender_id=interaction.user.id,
            recipient_id=sender_id,
            subject=subject,
            content=self.content.value.strip(),
        )
        dm_sent = await self.view_ref.cog.notify_recipient(
            recipient_id=sender_id,
            sender_name=interaction.user.display_name,
            subject=subject,
            message_id=message_id,
        )
        if dm_sent:
            await interaction.response.send_message(
                f"✅ Réponse envoyée à `{sender_id}` et notification privée envoyée.",
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                f"✅ Réponse envoyée à `{sender_id}`. La notification privée n'a pas pu être envoyée.",
                ephemeral=True,
            )


class UnreadMailSelect(ui.Select):
    def __init__(self, view: "MailMainView", choices: list[discord.SelectOption]):
        super().__init__(placeholder="Sélectionne un message non lu...", min_values=1, max_values=1, options=choices)
        self.view_ref = view

    async def callback(self, interaction: discord.Interaction):
        message_id = int(self.values[0])
        message = self.view_ref.cog.mail_service.get_message(message_id, self.view_ref.user.id)
        if not message:
            await interaction.response.send_message("❌ Message introuvable.", ephemeral=True)
            return
        if not message["is_read"]:
            self.view_ref.cog.mail_service.mark_as_read(message_id)
        embed = await self.view_ref.cog.build_message_embed(interaction.guild, interaction.user, message)
        view = MailDetailView(self.view_ref.cog, interaction.user, message)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class MailMainView(ui.View):
    def __init__(self, cog: "MailCog", ctx: commands.Context, unread: list[dict[str, Any]]):
        super().__init__(timeout=300)
        self.cog = cog
        self.ctx = ctx
        self.user = ctx.author
        self.unread = unread
        self._build_view()

    def _build_view(self):
        if self.unread:
            options = []
            for item in self.unread:
                label = item["subject"][:100]
                sender_name = f"{item['sender_id']}"
                options.append(
                    discord.SelectOption(
                        label=label,
                        value=str(item["id"]),
                        description=f"Envoyé par {sender_name}"
                    )
                )
            self.add_item(UnreadMailSelect(self, options))

        is_enabled = self.cog.mail_service.get_notification_setting(self.user.id)
        self.notification_button.label = f"Notifications DM : {'ON' if is_enabled else 'OFF'}"
        self.notification_button.style = discord.ButtonStyle.success if is_enabled else discord.ButtonStyle.secondary

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Ce menu ne t'appartient pas.", ephemeral=True)
            return False
        return True

    @ui.button(label="Voir messages lus", style=discord.ButtonStyle.secondary, row=1)
    async def view_read(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        await self.cog.show_read_messages(interaction, 0)

    @ui.button(label="Envoyer un message", style=discord.ButtonStyle.primary, row=1)
    async def send_message(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(SendMailModal(self))

    @ui.button(label="Notifications DM", style=discord.ButtonStyle.secondary, row=1)
    async def notification_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Ce menu ne t'appartient pas.", ephemeral=True)
            return
        enabled = self.cog.mail_service.get_notification_setting(self.user.id)
        self.cog.mail_service.set_notification_setting(self.user.id, not enabled)
        if enabled:
            button.label = "Notifications DM : OFF"
            button.style = discord.ButtonStyle.secondary
            await interaction.response.send_message("✅ Notifications privées désactivées.", ephemeral=True)
        else:
            button.label = "Notifications DM : ON"
            button.style = discord.ButtonStyle.success
            await interaction.response.send_message("✅ Notifications privées activées.", ephemeral=True)


class ReadMessagesView(ui.View):
    def __init__(self, cog: "MailCog", ctx: commands.Context, page: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.ctx = ctx
        self.page = page
        self.user = ctx.author
        self._build_view()

    def _build_view(self):
        messages = self.cog.mail_service.get_read_messages(self.user.id, self.page)
        if messages:
            options = []
            for item in messages:
                label = item["subject"][:100]
                options.append(
                    discord.SelectOption(
                        label=label,
                        value=str(item["id"]),
                        description=f"Lu le {time.strftime('%d/%m/%Y', time.localtime(item['read_at']))}"
                    )
                )
            self.read_select.options = options
            self.read_select.disabled = False
            self.read_select.placeholder = "Choisis un message lu..."
        else:
            self.read_select.options = []
            self.read_select.disabled = True
            self.read_select.placeholder = "Aucun message lu"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Ce menu ne t'appartient pas.", ephemeral=True)
            return False
        return True

    @ui.button(label="Retour", style=discord.ButtonStyle.secondary, custom_id="back_main", row=1)
    async def back_main(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        await self.cog.show_mail_main(interaction)

    @ui.button(label="◀", style=discord.ButtonStyle.secondary, custom_id="prev_page", row=2)
    async def prev_page(self, interaction: discord.Interaction, button: ui.Button):
        if self.page > 0:
            await interaction.response.defer()
            await self.cog.show_read_messages(interaction, self.page - 1)

    @ui.button(label="▶", style=discord.ButtonStyle.secondary, custom_id="next_page", row=2)
    async def next_page(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        await self.cog.show_read_messages(interaction, self.page + 1)

    @ui.select(placeholder="Choisis un message lu...", min_values=1, max_values=1, custom_id="read_select")
    async def read_select(self, interaction: discord.Interaction, select: ui.Select):
        message_id = int(select.values[0])
        message = self.cog.mail_service.get_message(message_id, self.user.id)
        if not message:
            await interaction.response.send_message("❌ Message introuvable.", ephemeral=True)
            return
        embed = await self.cog.build_message_embed(interaction.guild, self.user, message)
        view = MailDetailView(self.cog, self.user, message)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class MailDetailView(ui.View):
    def __init__(self, cog: "MailCog", user: discord.abc.User, message: dict[str, Any]):
        super().__init__(timeout=300)
        self.cog = cog
        self.user = user
        self.message = message

    @ui.button(label="Répondre", style=discord.ButtonStyle.primary, row=0)
    async def reply_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Ce menu ne t'appartient pas.", ephemeral=True)
            return
        await interaction.response.send_modal(ReplyMailModal(self, self.message))

    @ui.button(label="Retour au menu", style=discord.ButtonStyle.secondary, row=0)
    async def back_button(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Ce menu ne t'appartient pas.", ephemeral=True)
            return
        await self.cog.show_mail_main(interaction)


class MailCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.mail_service = MailService()

    def create_embed(self, guild: discord.Guild | None, user: discord.abc.User | None, title: str, description: str) -> discord.Embed:
        return create_embed(guild, user, self.bot, title, description)

    async def get_user_display(self, user_id: int) -> str:
        user = self.bot.get_user(user_id)
        if user:
            return user.display_name
        try:
            user = await self.bot.fetch_user(user_id)
            return user.display_name
        except Exception:
            return str(user_id)

    async def notify_recipient(self, recipient_id: int, sender_name: str, subject: str, message_id: int) -> bool:
        if not self.mail_service.get_notification_setting(recipient_id):
            return False
        try:
            recipient = self.bot.get_user(recipient_id)
            if recipient is None:
                recipient = await self.bot.fetch_user(recipient_id)
            if recipient is None:
                return False
            embed = self.create_embed(
                None,
                recipient,
                "📩 Nouveau message privé",
                f"Tu as reçu un nouveau message de `{sender_name}`."
            )
            embed.add_field(name="Objet", value=subject, inline=False)
            embed.add_field(name="ID interne", value=str(message_id), inline=False)
            embed.set_footer(text="Utilise /mail pour le lire et répondre.")
            await recipient.send(embed=embed)
            return True
        except Exception:
            return False

    async def build_message_embed(self, guild: discord.Guild | None, user: discord.abc.User, message: dict[str, Any]) -> discord.Embed:
        sender_name = await self.get_user_display(message["sender_id"])
        sender = self.bot.get_user(message["sender_id"])
        title = message["subject"]
        description = f"Message reçu de `{sender_name}` — `ID : {message['sender_id']}`"
        embed = self.create_embed(guild, user, title, description)
        if sender and getattr(sender, "display_avatar", None):
            embed.set_author(name=sender_name, icon_url=sender.display_avatar.url)
        embed.add_field(name="Objet", value=message["subject"], inline=False)
        embed.add_field(name="Contenu", value=message["content"], inline=False)
        embed.set_footer(text=f"Envoyé le {time.strftime('%d/%m/%Y %H:%M', time.localtime(message['created_at']))}")
        return embed

    async def show_mail_main(self, interaction: discord.Interaction) -> None:
        unread = self.mail_service.get_unread_messages(interaction.user.id)
        embed = self.create_embed(
            interaction.guild,
            interaction.user,
            "📬 Modmail",
            f"Tu as **{len(unread)} message(s) non lu(s)**. Sélectionne un message pour le lire ou utilise les boutons ci-dessous.",
        )
        if unread:
            preview = "\n".join([f"• `{item['subject']}`" for item in unread[:5]])
            embed.add_field(name="Non lus", value=preview, inline=False)
        else:
            embed.add_field(name="Non lus", value="Aucun message non lu.", inline=False)
        await interaction.response.edit_message(embed=embed, view=MailMainView(self, interaction, unread))

    async def show_read_messages(self, interaction: discord.Interaction, page: int) -> None:
        messages = self.mail_service.get_read_messages(interaction.user.id, page)
        total = self.mail_service.count_read_messages(interaction.user.id)
        embed = self.create_embed(
            interaction.guild,
            interaction.user,
            "📨 Messages lus",
            f"Page {page + 1} / {max(1, (total + READ_PAGE_SIZE - 1) // READ_PAGE_SIZE)}",
        )
        if messages:
            preview = "\n".join([
                f"• `{item['subject']}` — lu le {time.strftime('%d/%m/%Y', time.localtime(item['read_at']))}" for item in messages
            ])
            embed.add_field(name="Messages lus", value=preview, inline=False)
        else:
            embed.add_field(name="Messages lus", value="Aucun message lu sur cette page.", inline=False)
        await interaction.response.edit_message(embed=embed, view=ReadMessagesView(self, interaction, page))

    @commands.hybrid_command(name="mail", description="Ouvre l'interface de Modmail.")
    async def mail(self, ctx: commands.Context):
        self.mail_service.cleanup_old_messages()
        unread = self.mail_service.get_unread_messages(ctx.author.id)
        embed = self.create_embed(
            ctx.guild,
            ctx.author,
            "📬 Modmail",
            f"Tu as **{len(unread)} message(s) non lu(s)**. Sélectionne un message pour le lire ou utilise les boutons ci-dessous.",
        )
        if unread:
            preview = "\n".join([f"• `{item['subject']}`" for item in unread[:5]])
            embed.add_field(name="Non lus", value=preview, inline=False)
        else:
            embed.add_field(name="Non lus", value="Aucun message non lu.", inline=False)
        await ctx.send(embed=embed, view=MailMainView(self, ctx, unread))


async def setup(bot: commands.Bot):
    await bot.add_cog(MailCog(bot))
