"""Configuration des sélecteurs d'identifiants Discord.

Permet de choisir un salon, un membre ou un rôle via un menu natif,
ou d'entrer un ID manuellement via une modale.
"""

from __future__ import annotations

from typing import Any, Callable

import discord
from discord import ui

from utils.config_emoji import Emoji as E


class IdModal(ui.Modal):
    def __init__(self, mode: str, callback_fn: Callable[[discord.Interaction, Any], None]):
        title_map = {
            "channel": "Insérer un ID de salon",
            "user": "Insérer un ID utilisateur",
            "role": "Insérer un ID de rôle",
        }
        super().__init__(title=title_map.get(mode, "Insérer un ID"))
        self.mode = mode
        self.callback_fn = callback_fn
        self.id_input = ui.TextInput(
            label="Identifiant",
            placeholder="Ex: 123456789101112345",
            max_length=25,
            required=True,
        )
        self.add_item(self.id_input)

    async def on_submit(self, interaction: discord.Interaction):
        raw_id = self.id_input.value.strip()
        if not raw_id.isdigit():
            return await interaction.response.send_message(
                "L'ID fourni n'est pas un nombre valide.",
                ephemeral=True,
            )

        await interaction.response.defer()
        obj_id = int(raw_id)
        guild = interaction.guild
        if guild is None:
            return await interaction.followup.send("Cette action nécessite un serveur.", ephemeral=True)

        target: Any = None
        if self.mode == "channel":
            target = guild.get_channel(obj_id)
            if not target:
                return await interaction.followup.send("Salon introuvable sur ce serveur.", ephemeral=True)
            if target.type not in {
                discord.ChannelType.text,
                discord.ChannelType.news,
                discord.ChannelType.voice,
                discord.ChannelType.stage_voice,
                discord.ChannelType.forum,
                discord.ChannelType.category,
            }:
                return await interaction.followup.send(
                    "Le salon doit être textuel, vocal, forum, catégorie ou d'annonce.",
                    ephemeral=True,
                )
        elif self.mode == "user":
            target = guild.get_member(obj_id)
            if target is None:
                try:
                    target = await guild.fetch_member(obj_id)
                except (discord.NotFound, discord.HTTPException, discord.Forbidden):
                    target = None
            if not target:
                return await interaction.followup.send("Utilisateur introuvable sur ce serveur.", ephemeral=True)
        elif self.mode == "role":
            target = guild.get_role(obj_id)
            if not target:
                return await interaction.followup.send("Rôle introuvable sur ce serveur.", ephemeral=True)
        else:
            return await interaction.followup.send("Mode inconnu.", ephemeral=True)

        await self.callback_fn(interaction, target)


class IdSelectView(ui.View):
    def __init__(
        self,
        mode: str,
        on_select: Callable[[discord.Interaction, Any], None],
        on_back: Callable[[discord.Interaction], None] | None,
        author_id: int | None = None,
        timeout: float | None = 900,
    ):
        super().__init__(timeout=timeout)
        self.mode = mode
        self.on_select = on_select
        self.on_back = on_back
        self.author_id = author_id

        if self.mode == "channel":
            select = ui.ChannelSelect(
                placeholder="Choisir un salon dans la liste",
                channel_types=[
                    discord.ChannelType.text,
                    discord.ChannelType.news,
                    discord.ChannelType.voice,
                    discord.ChannelType.stage_voice,
                    discord.ChannelType.forum,
                    discord.ChannelType.category,
                ],
                row=0,
            )
        elif self.mode == "user":
            select = ui.UserSelect(
                placeholder="Choisir un membre dans la liste",
                row=0,
            )
        elif self.mode == "role":
            select = ui.RoleSelect(
                placeholder="Choisir un rôle dans la liste",
                row=0,
            )
        else:
            raise ValueError(f"Mode inconnu: {self.mode}")

        select.callback = self.select_callback
        self.add_item(select)

        if self.mode == "role":
            mention_select = ui.Select(
                placeholder="Ou choisir @everyone / @here / Aucun",
                options=[
                    discord.SelectOption(label="Aucun (Réinitialiser)", value="none"),
                    discord.SelectOption(label="@everyone", value="everyone"),
                    discord.SelectOption(label="@here", value="here"),
                ],
                row=1,
            )
            mention_select.callback = self.mention_callback
            self.add_item(mention_select)

        insert_btn = ui.Button(
            label="Insérer un ID direct",
            style=discord.ButtonStyle.primary,
            emoji=getattr(E, "IDENTIFIANT", None),
            row=2,
        )
        insert_btn.callback = self.insert_id_callback
        self.add_item(insert_btn)

        back_btn = ui.Button(
            label="Retour",
            style=discord.ButtonStyle.secondary,
            emoji=getattr(E, "RETOUR", None),
            row=2,
        )
        back_btn.callback = self.back_callback
        self.add_item(back_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.author_id is not None and interaction.user.id != self.author_id:
            await interaction.response.send_message("Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        return True

    async def select_callback(self, interaction: discord.Interaction):
        values = list(getattr(interaction, "values", []) or interaction.data.get("values", []))
        if not values:
            return await interaction.response.send_message("Aucun choix sélectionné.", ephemeral=True)

        value = values[0]
        target: Any = None
        if self.mode == "channel":
            target = interaction.guild.get_channel(int(value)) if interaction.guild else None
        elif self.mode == "user":
            if interaction.guild:
                target = interaction.guild.get_member(int(value))
                if target is None:
                    try:
                        target = await interaction.guild.fetch_member(int(value))
                    except (discord.NotFound, discord.HTTPException, discord.Forbidden):
                        target = None
        elif self.mode == "role":
            target = interaction.guild.get_role(int(value)) if interaction.guild else None

        if target is None:
            return await interaction.response.send_message("Aucun choix valide n'a été trouvé.", ephemeral=True)

        await self.on_select(interaction, target)

    async def mention_callback(self, interaction: discord.Interaction):
        choice = (interaction.data.get("values", ["none"])[0] if interaction.data else "none")
        value = "" if choice == "none" else choice
        await self.on_select(interaction, value)

    async def insert_id_callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(IdModal(self.mode, self.on_select))

    async def back_callback(self, interaction: discord.Interaction):
        if self.on_back is None:
            await interaction.response.defer()
            return
        await self.on_back(interaction)


async def open_id_selector(
    interaction: discord.Interaction,
    mode: str,
    on_select: Callable[[discord.Interaction, Any], None],
    on_back: Callable[[discord.Interaction], None] | None = None,
    author_id: int | None = None,
    timeout: float | None = 900,
):
    """Affiche la vue de sélection d'ID adaptée au mode demandé."""
    view = IdSelectView(mode=mode, on_select=on_select, on_back=on_back, author_id=author_id, timeout=timeout)

    if interaction.response.is_done():
        await interaction.edit_original_response(view=view)
    else:
        await interaction.response.edit_message(view=view)

    return view


__all__ = ["IdModal", "IdSelectView", "open_id_selector"]
