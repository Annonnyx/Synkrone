import json
import os
import re
import unicodedata
from typing import Optional

import discord
from discord import app_commands, ui
from discord.ext import commands
import pyfiglet

from utils.config_emoji import Emoji as E

try:
    from utils.config_theme import config_manager
except ImportError:
    config_manager = None


def _escape_codeblock(value: str) -> str:
    return value.replace("```", "`\u200b`\u200b`")


class FontEditModal(ui.Modal, title="Modifier la phrase"):
    def __init__(self, parent_view: "FontView"):
        super().__init__()
        self.parent_view = parent_view

        default_text = parent_view.source_text or ""
        if len(default_text) > 1000:
            default_text = default_text[:1000]

        self.text_input = ui.TextInput(
            label="Texte",
            placeholder="Ecris ta phrase ici...",
            required=True,
            style=discord.TextStyle.paragraph,
            default=default_text,
            max_length=1000,
        )
        self.add_item(self.text_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True)
        self.parent_view.source_text = str(self.text_input.value)
        await self.parent_view.refresh_message()
        await interaction.followup.send("Texte mis a jour.", ephemeral=True)


class FontModeSelect(ui.Select):
    def __init__(self, parent_view: "FontView"):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(
                label="Font",
                value="font",
                description="Applique la police stylisee",
                default=(parent_view.mode == "font"),
                emoji="🔤",
            ),
            discord.SelectOption(
                label="Standard",
                value="standard",
                description="Reverse avec miroir de caracteres",
                default=(parent_view.mode == "standard"),
                emoji="↔️",
            ),
            discord.SelectOption(
                label="Upside",
                value="upside",
                description="Retourne les caracteres",
                default=(parent_view.mode == "upside"),
                emoji="🙃",
            ),
            discord.SelectOption(
                label="Binary",
                value="binary",
                description="Convertit en binaire puis reverse",
                default=(parent_view.mode == "binary"),
                emoji=E.NUM_0,
            ),
            discord.SelectOption(
                label="ASCII",
                value="ascii",
                description="Genere un ASCII art (pyfiglet)",
                default=(parent_view.mode == "ascii"),
                emoji="🧱",
            ),
        ]
        super().__init__(
            placeholder="Choisir un mode...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        picked = self.values[0] if self.values else None
        if not picked and interaction.data:
            raw_values = interaction.data.get("values", [])
            picked = raw_values[0] if raw_values else None
        if not picked:
            await interaction.response.send_message("Aucun mode selectionne.", ephemeral=True)
            return

        self.parent_view.mode = picked
        await self.parent_view.refresh_interaction(interaction)


class FontView(ui.View):
    def __init__(self, cog: "Font", author_id: int, source_text: str, mode: str):
        super().__init__(timeout=600)
        self.cog = cog
        self.author_id = author_id
        self.source_text = source_text
        self.mode = mode
        self.message: Optional[discord.Message] = None
        self._build_components()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        return True

    async def _on_edit_text(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(FontEditModal(self))

    def _build_components(self) -> None:
        self.clear_items()
        self.add_item(FontModeSelect(self))

        edit_btn = ui.Button(
            label="Modifier la phrase",
            style=discord.ButtonStyle.primary,
            emoji=E.MODIFIER,
            row=1,
        )
        edit_btn.callback = self._on_edit_text
        self.add_item(edit_btn)

    def _resolve_user_for_embed(self) -> Optional[discord.abc.User]:
        if self.message is None:
            return None
        if self.message.guild is None:
            return self.message.author
        member = self.message.guild.get_member(self.author_id)
        return member or self.message.author

    async def refresh_message(self) -> None:
        if self.message is None:
            return

        self._build_components()
        target_user = self._resolve_user_for_embed() or self.message.author
        embed = self.cog.build_embed(
            guild=self.message.guild,
            user=target_user,
            mode=self.mode,
            source_text=self.source_text,
        )
        await self.message.edit(embed=embed, view=self)

    async def refresh_interaction(self, interaction: discord.Interaction) -> None:
        self._build_components()
        embed = self.cog.build_embed(
            guild=interaction.guild,
            user=interaction.user,
            mode=self.mode,
            source_text=self.source_text,
        )
        await interaction.response.edit_message(embed=embed, view=self)


class Font(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        base_path = os.path.dirname(__file__)
        assets_json_path = os.path.join(base_path, "assets", "font.json")
        legacy_json_path = os.path.join(base_path, "font.json")
        json_path = assets_json_path if os.path.isfile(assets_json_path) else legacy_json_path

        with open(json_path, "r", encoding="utf-8") as file:
            self.font_map = json.load(file)

        self.ascii_allowed_chars = re.compile(r"^[a-zA-Z0-9\s]*$")
        self.ascii_max_length = 10

    def stylize(self, text: str) -> str:
        decomposed = unicodedata.normalize("NFD", text)
        styled_parts: list[str] = []

        for char in decomposed:
            if unicodedata.combining(char):
                styled_parts.append(char)
                continue
            styled_parts.append(self.font_map.get(char, char))

        return "".join(styled_parts)

    def reverse_text(self, text: str) -> str:
        mirrored = ""
        special_chars = {
            "(": ")",
            ")": "(",
            "[": "]",
            "]": "[",
            "{": "}",
            "}": "{",
            "<": ">",
            ">": "<",
            "/": "\\",
            "\\": "/",
        }

        for char in text[::-1]:
            mirrored += special_chars.get(char, char)
        return mirrored

    def upside_text(self, text: str) -> str:
        normal = r"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890!?.,;:()[]{}\\"
        flipped = r"ɐqɔpǝɟƃɥᴉɾʞןɯuodbɹsʇnʌʍxʎz∀𐐒ƆᗡƎℲ⅁HIſʞ˥WNOԀΌᴚS⊥∩ΛMX⅄Z⇂ᄅƐㄣϛ9ㄥ860¡¿'˙'؛:)(][}{/\\"
        flip_table = {ord(src): dst for src, dst in zip(normal, flipped)}
        return text.translate(flip_table)[::-1]

    def binary_text(self, text: str) -> str:
        return " ".join(format(ord(char), "08b") for char in text)[::-1]

    def ascii_text(self, text: str) -> str:
        raw = (text or "").strip()
        if not raw:
            return "Entrez du texte pour le mode ASCII."
        if len(raw) > self.ascii_max_length:
            return f"Maximum {self.ascii_max_length} caracteres pour le mode ASCII."
        if not self.ascii_allowed_chars.fullmatch(raw):
            return "ASCII accepte uniquement lettres, chiffres et espaces."

        art = pyfiglet.figlet_format(raw, font="small", width=100)
        clean = "\n".join(line.rstrip() for line in art.split("\n") if line.strip())
        return clean or "Impossible de generer l'ASCII."

    def transform_text(self, text: str, mode: str) -> str:
        if mode == "standard":
            return self.reverse_text(text)
        if mode == "upside":
            return self.upside_text(text)
        if mode == "binary":
            return self.binary_text(text)
        if mode == "ascii":
            return self.ascii_text(text)
        return self.stylize(text)

    def build_embed(
        self,
        guild: Optional[discord.Guild],
        user: discord.abc.User,
        mode: str,
        source_text: str,
    ) -> discord.Embed:
        output = self.transform_text(source_text, mode)
        mode_names = {
            "font": "Font",
            "standard": "Reverse Standard",
            "upside": "Reverse Upside",
            "binary": "Reverse Binary",
            "ascii": "ASCII Art",
        }
        mode_name = mode_names.get(mode, "Font")

        description = "Resultat pret a copier/coller:"
        if config_manager:
            embed = config_manager.get_formatted_embed(
                guild=guild,
                user=user,
                bot=self.bot,
                title="Font Studio",
                description=description,
                target_id=guild.id if guild else None,
            )
        else:
            embed = discord.Embed(
                title="Font Studio",
                description=description,
                color=discord.Color.blurple(),
            )

        if self.bot.user:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        embed.add_field(name="Mode actif", value=f"`{mode_name}`", inline=True)
        embed.add_field(name="Longueur", value=str(len(source_text)), inline=True)
        embed.add_field(name="Sortie", value=f"```\n{_escape_codeblock(output)}\n```", inline=False)

        if source_text:
            embed.add_field(name="Source", value=f"```\n{_escape_codeblock(source_text)}\n```", inline=False)

        return embed

    @commands.hybrid_command(name="font", description="Stylise un texte ou applique un mode reverse.")
    @app_commands.describe(message="Phrase a transformer")
    async def font(self, ctx: commands.Context, *, message: Optional[str] = None) -> None:
        source_text = (message or "").strip()
        if not source_text:
            source_text = "Tape sur Modifier la phrase pour commencer."

        view = FontView(self, ctx.author.id, source_text, "font")
        embed = self.build_embed(ctx.guild, ctx.author, "font", source_text)
        sent = await ctx.send(embed=embed, view=view)
        view.message = sent


async def setup(bot: commands.Bot) -> None:
    if bot.get_command("reverse"):
        bot.remove_command("reverse")
    if bot.get_command("font"):
        bot.remove_command("font")
    await bot.add_cog(Font(bot))
