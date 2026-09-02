import io
import json
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

try:
    from utils.config_theme import config_manager
except ImportError:
    config_manager = None


class CopyMessage(commands.Cog):
    """Recupere la source brute d'un message (texte, embeds, layout/components)."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        existing = self.bot.tree.get_command("Copier la source", type=discord.AppCommandType.message)
        if existing is not None:
            self.bot.tree.remove_command("Copier la source", type=discord.AppCommandType.message)

        self.ctx_menu = app_commands.ContextMenu(
            name="Copier la source",
            callback=self.copy_context_menu,
        )
        self.bot.tree.add_command(self.ctx_menu)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)

    def _message_to_source_text(self, message: discord.Message) -> str:
        sections: list[str] = []

        if message.content:
            safe_content = message.content.replace("```", "`\u200b`\u200b`")
            sections.append("=== TEXTE ===")
            sections.append(safe_content)

        if message.embeds:
            sections.append("=== EMBEDS ===")
            for index, embed in enumerate(message.embeds, start=1):
                sections.append(f"[Embed {index}]")
                try:
                    sections.append(json.dumps(embed.to_dict(), ensure_ascii=False, indent=2))
                except Exception:
                    sections.append(str(embed))

        if message.components:
            sections.append("=== LAYOUT / COMPONENTS ===")
            serialized = []
            for component in message.components:
                if hasattr(component, "to_dict"):
                    serialized.append(component.to_dict())
                else:
                    serialized.append(str(component))
            sections.append(json.dumps(serialized, ensure_ascii=False, indent=2))

        if message.attachments:
            sections.append("=== PIECES JOINTES ===")
            for att in message.attachments:
                sections.append(f"- {att.filename} -> {att.url}")

        if not sections:
            return ""

        raw = "\n\n".join(sections)
        return "```\n" + raw + "\n```"

    async def _send_error(self, ctx_or_interaction, description: str):
        is_interaction = isinstance(ctx_or_interaction, discord.Interaction)
        guild = ctx_or_interaction.guild
        user = ctx_or_interaction.user if is_interaction else ctx_or_interaction.author

        if config_manager:
            embed = config_manager.get_formatted_embed(
                guild=guild,
                user=user,
                bot=self.bot,
                title="Impossible de copier",
                description=description,
                target_id=guild.id if guild else None,
            )
        else:
            embed = discord.Embed(title="Impossible de copier", description=description, color=0xFF0000)

        if is_interaction:
            await ctx_or_interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await ctx_or_interaction.send(embed=embed, reference=ctx_or_interaction.message)

    async def _process_copy(self, ctx_or_interaction, message: discord.Message):
        source_text = self._message_to_source_text(message)
        if not source_text:
            return await self._send_error(
                ctx_or_interaction,
                "Ce message ne contient ni texte, ni embed, ni layout exploitable.",
            )

        if len(source_text) > 2000:
            content_for_file = source_text.removeprefix("```\n").removesuffix("\n```")
            file = discord.File(
                io.BytesIO(content_for_file.encode("utf-8")),
                filename="message_source.txt",
            )
            msg_text = "Le contenu est trop long pour Discord. Fichier source ci-joint."

            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.followup.send(content=msg_text, file=file, ephemeral=True)
            else:
                await ctx_or_interaction.send(content=msg_text, file=file, reference=ctx_or_interaction.message)
            return

        if isinstance(ctx_or_interaction, discord.Interaction):
            await ctx_or_interaction.followup.send(content=source_text, ephemeral=True)
        else:
            await ctx_or_interaction.send(content=source_text, reference=ctx_or_interaction.message)

    async def _resolve_message_from_id(self, ctx: commands.Context, message_id: int) -> Optional[discord.Message]:
        try:
            return await ctx.channel.fetch_message(message_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass

        if ctx.guild:
            for channel in ctx.guild.text_channels:
                if channel.id == ctx.channel.id:
                    continue
                try:
                    msg = await channel.fetch_message(message_id)
                    if msg:
                        return msg
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    continue

        for guild in self.bot.guilds:
            if ctx.guild and guild.id == ctx.guild.id:
                continue
            for channel in guild.text_channels:
                try:
                    msg = await channel.fetch_message(message_id)
                    if msg:
                        return msg
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    continue

        return None

    @app_commands.checks.cooldown(1, 3.0, key=lambda i: (i.guild_id, i.user.id))
    async def copy_context_menu(self, interaction: discord.Interaction, message: discord.Message):
        await interaction.response.defer(ephemeral=True)
        await self._process_copy(interaction, message)

    @commands.hybrid_command(name="copy", description="Copie la source d'un message (texte, embed, layout).")
    @app_commands.describe(message_id="ID du message (ou repondre au message puis lancer la commande)")
    async def copy_cmd(self, ctx: commands.Context, message_id: Optional[str] = None):
        target_message: Optional[discord.Message] = None

        if ctx.message.reference and ctx.message.reference.message_id:
            try:
                target_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return await self._send_error(ctx, "Le message cible en reponse est introuvable.")

        elif message_id and message_id.isdigit():
            target_message = await self._resolve_message_from_id(ctx, int(message_id))
            if target_message is None:
                return await self._send_error(
                    ctx,
                    f"Impossible de trouver un message avec l'ID {message_id} dans les salons accessibles.",
                )

        if target_message is None:
            return await self._send_error(
                ctx,
                "Vous devez repondre a un message ou fournir un ID valide.",
            )

        if ctx.interaction:
            try:
                await ctx.defer(ephemeral=True)
            except TypeError:
                await ctx.defer()

        await self._process_copy(ctx, target_message)


async def setup(bot: commands.Bot):
    await bot.add_cog(CopyMessage(bot))
