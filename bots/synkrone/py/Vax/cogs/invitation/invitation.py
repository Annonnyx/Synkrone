import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import discord
from discord.ext import commands

# ==============================================================================
# --------------------------- IMPORTATION UTILS --------------------------------
# ==============================================================================
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None


DATA_DIR = Path(__file__).parents[2] / "data" / "invitation"
DB_PATH = DATA_DIR / "invitation.sqlite3"
DEFAULT_TEMPLATE = "**{inviter_name}** a invité {@invited} & comptabilise **{inviter_count} invitations**."


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


def format_presence_duration(since: datetime, now: Optional[datetime] = None) -> str:
    now = now or utcnow()
    delta = now - since
    total_seconds = max(0, int(delta.total_seconds()))

    minute = 60
    hour = 3600
    day = 86400

    if total_seconds < hour:
        mins = max(1, total_seconds // minute)
        return f"depuis {mins} minute" + ("s" if mins > 1 else "")
    if total_seconds < day:
        hours = total_seconds // hour
        return f"depuis {hours} heure" + ("s" if hours > 1 else "")

    days = total_seconds // day
    months = days // 30
    rem_days = days % 30

    if months <= 0:
        return f"depuis {days} jour" + ("s" if days > 1 else "")
    if rem_days <= 0:
        return f"depuis {months} mois"
    return f"depuis {months} mois et {rem_days} jour" + ("s" if rem_days > 1 else "")


def default_guild_data() -> Dict[str, Any]:
    return {
        "config": {
            "channel_id": None,
            "message_template": DEFAULT_TEMPLATE,
            "use_embed": False,
        },
        "role_rewards": [],
        "inviters": {},
        "invited_users": {},
    }


class ProfileLookupModal(discord.ui.Modal):
    def __init__(self, cog: "Invitation", user_id: int, guild_id: int, channel_id: int, message_id: int):
        super().__init__(title="Profil invitation")
        self.cog = cog
        self.user_id = user_id
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.message_id = message_id

        self.target_id = discord.ui.TextInput(
            label="ID utilisateur",
            placeholder="Entrez l'ID de l'utilisateur à afficher",
            required=True,
            min_length=17,
            max_length=20,
        )
        self.add_item(self.target_id)

    async def on_submit(self, interaction: discord.Interaction):
        raw = str(self.target_id.value).strip()
        if not raw.isdigit() or len(raw) < 17:
            return await interaction.response.send_message("ID invalide.", ephemeral=True)

        target_id = int(raw)
        guild = interaction.client.get_guild(self.guild_id)
        if not guild:
            return await interaction.response.send_message("Serveur introuvable.", ephemeral=True)

        show_presence_details, show_history_details = self.cog.get_profile_prefs(self.guild_id, self.user_id)
        embed = await self.cog.build_profile_embed(
            guild,
            interaction.user,
            target_id,
            show_presence_details=show_presence_details,
            show_history_details=show_history_details,
        )
        view = InvitationPanelView(
            cog=self.cog,
            requester_id=self.user_id,
            guild_id=self.guild_id,
            selected_user_id=target_id,
            mode="profile",
            show_presence_details=show_presence_details,
            show_history_details=show_history_details,
        )

        ok = await self.cog.edit_panel_message(self.channel_id, self.message_id, embed, view)
        if not ok:
            return await interaction.response.send_message("Impossible de mettre à jour le panneau.", ephemeral=True)

        await interaction.response.send_message("Profil mis à jour.", ephemeral=True)


class ConfigModal(discord.ui.Modal):
    def __init__(self, cog: "Invitation", guild_id: int, requester_id: int, channel_id: int, message_id: int):
        super().__init__(title="Configuration des invitations")
        self.cog = cog
        self.guild_id = guild_id
        self.requester_id = requester_id
        self.channel_id = channel_id
        self.message_id = message_id

        data = self.cog.load_data(guild_id)
        cfg = data["config"]

        self.channel_input = discord.ui.TextInput(
            label="Salon de logs invitations (ID)",
            placeholder="Ex: 123456789012345678",
            required=False,
            max_length=20,
            default=str(cfg.get("channel_id") or ""),
        )
        self.template_input = discord.ui.TextInput(
            label="Message personnalise",
            placeholder=DEFAULT_TEMPLATE,
            required=False,
            style=discord.TextStyle.long,
            max_length=300,
            default=cfg.get("message_template") or DEFAULT_TEMPLATE,
        )

        self.add_item(self.channel_input)
        self.add_item(self.template_input)

    async def on_submit(self, interaction: discord.Interaction):
        data = self.cog.load_data(self.guild_id)
        cfg = data["config"]

        raw_channel = str(self.channel_input.value or "").strip()
        if raw_channel:
            if not raw_channel.isdigit():
                return await interaction.response.send_message("Le salon doit etre un ID numerique.", ephemeral=True)
            cfg["channel_id"] = int(raw_channel)
        else:
            cfg["channel_id"] = None

        template = str(self.template_input.value or "").strip()
        cfg["message_template"] = template if template else DEFAULT_TEMPLATE

        self.cog.save_data(self.guild_id, data)

        guild = interaction.client.get_guild(self.guild_id)
        if not guild:
            return await interaction.response.send_message("Serveur introuvable.", ephemeral=True)

        embed = self.cog.build_config_embed(guild, interaction.user)
        view = InvitationPanelView(
            cog=self.cog,
            requester_id=self.requester_id,
            guild_id=self.guild_id,
            selected_user_id=self.requester_id,
            mode="config",
        )
        ok = await self.cog.edit_panel_message(self.channel_id, self.message_id, embed, view)
        if not ok:
            return await interaction.response.send_message("Configuration enregistrée, mais panneau non mis à jour.", ephemeral=True)

        await interaction.response.send_message("Configuration mise à jour.", ephemeral=True)


class RewardAddModal(discord.ui.Modal):
    def __init__(self, cog: "Invitation", guild_id: int, requester_id: int):
        super().__init__(title="Ajouter une récompense")
        self.cog = cog
        self.guild_id = guild_id
        self.requester_id = requester_id

        self.role_id_input = discord.ui.TextInput(
            label="ID du rôle",
            placeholder="Ex: 123456789012345678",
            required=True,
            max_length=20,
        )
        self.required_input = discord.ui.TextInput(
            label="Invités actifs requis",
            placeholder="Ex: 5",
            required=True,
            max_length=4,
        )
        self.add_item(self.role_id_input)
        self.add_item(self.required_input)

    async def on_submit(self, interaction: discord.Interaction):
        data = self.cog.load_data(self.guild_id)
        rewards = data.get("role_rewards", [])
        if len(rewards) >= 25:
            return await interaction.response.send_message("Maximum 25 récompenses atteint.", ephemeral=True)

        raw_role = str(self.role_id_input.value).strip()
        raw_required = str(self.required_input.value).strip()
        if not raw_role.isdigit():
            return await interaction.response.send_message("ID de rôle invalide.", ephemeral=True)
        if not raw_required.isdigit() or int(raw_required) < 1:
            return await interaction.response.send_message("Le seuil doit être >= 1.", ephemeral=True)

        used_slots = {int(r.get("slot", 0)) for r in rewards}
        slot = next((i for i in range(1, 26) if i not in used_slots), None)
        if slot is None:
            return await interaction.response.send_message("Aucun slot disponible.", ephemeral=True)

        rewards.append(
            {
                "slot": slot,
                "enabled": True,
                "role_id": int(raw_role),
                "required_invites": int(raw_required),
            }
        )
        data["role_rewards"] = sorted(rewards, key=lambda x: int(x.get("slot", 0)))
        self.cog.save_data(self.guild_id, data)

        guild = interaction.client.get_guild(self.guild_id)
        if guild:
            await self.cog.refresh_role_rewards(guild)
            embed = self.cog.build_rewards_embed(guild, interaction.user, selected_slot=slot)
            view = RewardsManagementView(self.cog, self.requester_id, self.guild_id, selected_slot=slot)
            await interaction.response.edit_message(embed=embed, view=view)
            return

        await interaction.response.send_message("Récompense ajoutée.", ephemeral=True)


class RewardEditModal(discord.ui.Modal):
    def __init__(self, cog: "Invitation", guild_id: int, requester_id: int, slot: int):
        super().__init__(title=f"Modifier récompense #{slot}")
        self.cog = cog
        self.guild_id = guild_id
        self.requester_id = requester_id
        self.slot = slot

        data = self.cog.load_data(guild_id)
        reward = next((r for r in data.get("role_rewards", []) if int(r.get("slot", 0)) == slot), None)

        self.role_id_input = discord.ui.TextInput(
            label="ID du rôle",
            placeholder="Ex: 123456789012345678",
            required=True,
            max_length=20,
            default=str(reward.get("role_id")) if reward else "",
        )
        self.required_input = discord.ui.TextInput(
            label="Invités actifs requis",
            placeholder="Ex: 5",
            required=True,
            max_length=4,
            default=str(reward.get("required_invites", 1)) if reward else "1",
        )
        self.enabled_input = discord.ui.TextInput(
            label="Actif ? (oui/non)",
            placeholder="oui",
            required=True,
            max_length=3,
            default="oui" if (reward and reward.get("enabled", True)) else "non",
        )

        self.add_item(self.role_id_input)
        self.add_item(self.required_input)
        self.add_item(self.enabled_input)

    async def on_submit(self, interaction: discord.Interaction):
        data = self.cog.load_data(self.guild_id)
        rewards = data.get("role_rewards", [])
        idx = next((i for i, r in enumerate(rewards) if int(r.get("slot", 0)) == self.slot), None)
        if idx is None:
            return await interaction.response.send_message("Récompense introuvable.", ephemeral=True)

        raw_role = str(self.role_id_input.value).strip()
        raw_required = str(self.required_input.value).strip()
        raw_enabled = str(self.enabled_input.value).strip().lower()

        if not raw_role.isdigit():
            return await interaction.response.send_message("ID de rôle invalide.", ephemeral=True)
        if not raw_required.isdigit() or int(raw_required) < 1:
            return await interaction.response.send_message("Le seuil doit être >= 1.", ephemeral=True)

        rewards[idx]["role_id"] = int(raw_role)
        rewards[idx]["required_invites"] = int(raw_required)
        rewards[idx]["enabled"] = raw_enabled in ("oui", "o", "yes", "y", "1", "on")
        data["role_rewards"] = rewards
        self.cog.save_data(self.guild_id, data)

        guild = interaction.client.get_guild(self.guild_id)
        if guild:
            await self.cog.refresh_role_rewards(guild)
            embed = self.cog.build_rewards_embed(guild, interaction.user, selected_slot=self.slot)
            view = RewardsManagementView(self.cog, self.requester_id, self.guild_id, selected_slot=self.slot)
            await interaction.response.edit_message(embed=embed, view=view)
            return

        await interaction.response.send_message("Récompense modifiée.", ephemeral=True)


class RewardSelect(discord.ui.Select):
    def __init__(self, view: "RewardsManagementView"):
        self._owner_view = view
        guild = view.cog.bot.get_guild(view.guild_id)
        data = view.cog.load_data(view.guild_id)
        rewards = sorted(data.get("role_rewards", []), key=lambda x: int(x.get("slot", 0)))

        options = []
        for r in rewards[:25]:
            slot = int(r.get("slot", 0))
            role_id = r.get("role_id")
            role = guild.get_role(int(role_id)) if (guild and role_id) else None
            role_name = role.name if role else f"Role {role_id}"
            req = int(r.get("required_invites", 1))
            state = "Actif" if r.get("enabled", True) else "Inactif"
            options.append(
                discord.SelectOption(
                    label=f"#{slot} - {role_name}",
                    description=f"Seuil: {req} | {state}",
                    value=str(slot),
                    default=(view.selected_slot == slot),
                )
            )

        if not options:
            options.append(discord.SelectOption(label="Aucune récompense", value="none", description="Ajoutez votre première récompense"))

        super().__init__(
            placeholder="Choisir une récompense",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        if selected == "none":
            self._owner_view.selected_slot = None
        else:
            self._owner_view.selected_slot = int(selected)

        guild = interaction.client.get_guild(self._owner_view.guild_id)
        if not guild:
            return await interaction.response.send_message("Serveur introuvable.", ephemeral=True)

        embed = self._owner_view.cog.build_rewards_embed(guild, interaction.user, selected_slot=self._owner_view.selected_slot)
        new_view = RewardsManagementView(
            cog=self._owner_view.cog,
            requester_id=self._owner_view.requester_id,
            guild_id=self._owner_view.guild_id,
            selected_slot=self._owner_view.selected_slot,
        )
        await interaction.response.edit_message(embed=embed, view=new_view)


class RewardsManagementView(discord.ui.View):
    def __init__(self, cog: "Invitation", requester_id: int, guild_id: int, selected_slot: Optional[int] = None):
        super().__init__(timeout=300)
        self.cog = cog
        self.requester_id = requester_id
        self.guild_id = guild_id
        self.selected_slot = selected_slot

        self.add_item(RewardSelect(self))
        self.add_item(self._btn_add())
        self.add_item(self._btn_edit())
        self.add_item(self._btn_delete())
        self.add_item(self._btn_back_config())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message("Ce panneau ne vous appartient pas.", ephemeral=True)
            return False
        return True

    def _btn_add(self):
        btn = discord.ui.Button(label="Ajouter", emoji="➕", style=discord.ButtonStyle.success, row=1)

        async def callback(interaction: discord.Interaction):
            data = self.cog.load_data(self.guild_id)
            if len(data.get("role_rewards", [])) >= 25:
                return await interaction.response.send_message("Maximum 25 récompenses atteint.", ephemeral=True)
            await interaction.response.send_modal(RewardAddModal(self.cog, self.guild_id, self.requester_id))

        btn.callback = callback
        return btn

    def _btn_edit(self):
        btn = discord.ui.Button(label="Modifier", emoji="✏️", style=discord.ButtonStyle.primary, row=1)

        async def callback(interaction: discord.Interaction):
            if not self.selected_slot:
                return await interaction.response.send_message("Sélectionnez d'abord une récompense.", ephemeral=True)
            await interaction.response.send_modal(RewardEditModal(self.cog, self.guild_id, self.requester_id, self.selected_slot))

        btn.callback = callback
        return btn

    def _btn_delete(self):
        btn = discord.ui.Button(label="Supprimer", emoji="🗑️", style=discord.ButtonStyle.danger, row=1)

        async def callback(interaction: discord.Interaction):
            if not self.selected_slot:
                return await interaction.response.send_message("Sélectionnez d'abord une récompense.", ephemeral=True)

            data = self.cog.load_data(self.guild_id)
            rewards = data.get("role_rewards", [])
            data["role_rewards"] = [r for r in rewards if int(r.get("slot", 0)) != int(self.selected_slot)]
            self.cog.save_data(self.guild_id, data)

            guild = interaction.client.get_guild(self.guild_id)
            if guild:
                await self.cog.refresh_role_rewards(guild)
                embed = self.cog.build_rewards_embed(guild, interaction.user, selected_slot=None)
                view = RewardsManagementView(self.cog, self.requester_id, self.guild_id, selected_slot=None)
                await interaction.response.edit_message(embed=embed, view=view)
                return

            await interaction.response.send_message("Récompense supprimée.", ephemeral=True)

        btn.callback = callback
        return btn

    def _btn_back_config(self):
        btn = discord.ui.Button(label="Retour Config", emoji="↩️", style=discord.ButtonStyle.secondary, row=1)

        async def callback(interaction: discord.Interaction):
            guild = interaction.client.get_guild(self.guild_id)
            if not guild:
                return await interaction.response.send_message("Serveur introuvable.", ephemeral=True)
            embed = self.cog.build_config_embed(guild, interaction.user)
            view = InvitationPanelView(
                cog=self.cog,
                requester_id=self.requester_id,
                guild_id=self.guild_id,
                selected_user_id=self.requester_id,
                mode="config",
            )
            await interaction.response.edit_message(embed=embed, view=view)

        btn.callback = callback
        return btn

class VariablesHelpView(discord.ui.View):
    def __init__(self, cog: "Invitation", requester_id: int, guild_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.requester_id = requester_id
        self.guild_id = guild_id

    def build_summary_embed(self, guild: discord.Guild, user: discord.abc.User) -> discord.Embed:
        template = self.cog.load_data(guild.id)["config"].get("message_template") or DEFAULT_TEMPLATE
        lines = [
            "🗂️ **Sommaire des variables disponibles**",
            "",
            "👤 **Variables de l'invité (celui qui rejoint)**",
            "• `{invited}` / `{@invited}` : mention de l'invité",
            "• `{invited_name}` : pseudo de l'invité",
            "• `<@invitedname>` : alias legacy de mention invité",
            "",
            "🧑 **Variables de l'invitant (celui qui invite)**",
            "• `{inviter}` / `{@inviter}` : mention de l'invitant",
            "• `{inviter_name}` : pseudo de l'invitant",
            "• `<@invitername>` : alias legacy de mention invitant",
            "• `<@invtername>` : alias typo legacy (compatibilité)",
            "",
            "📊 **Variables de statistiques**",
            "• `{inviter_count}` : invitations actives de l'invitant",
            "• `{invite_total}` : invitations actives totales du serveur",
            "• `{invite_code}` : code d'invitation utilisé",
            "",
            "✨ **Exemple final** : **{inviter_name}** a invité <@invitedname> & comptabilise **{inviter_count} invitations**.",
            "",
            "💬 **Template actuel** :",
            f"```{template}```",
            "✅ Ce sommaire est la vue principale des variables.",
        ]
        return self.cog.create_embed(guild, user, "🧩 Variables disponibles", "\n".join(lines))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message("Ce panneau ne vous appartient pas.", ephemeral=True)
            return False
        return True


class ConfigActionSelect(discord.ui.Select):
    def __init__(self, owner_view: "InvitationPanelView"):
        self.owner_view = owner_view
        options = [
            discord.SelectOption(label="Modifier Salon + Message", value="edit_config", emoji="📝"),
            discord.SelectOption(label="Basculer mode simple/embed", value="toggle_mode", emoji="🎨"),
            discord.SelectOption(label="Aperçu du message", value="preview", emoji="👁️"),
            discord.SelectOption(label="Gérer récompenses", value="rewards", emoji="🎖️"),
        ]
        super().__init__(
            placeholder="Choisir une action",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        action = self.values[0]
        guild = interaction.client.get_guild(self.owner_view.guild_id)
        if not guild:
            return await interaction.response.send_message("Serveur introuvable.", ephemeral=True)

        if action == "edit_config":
            modal = ConfigModal(
                cog=self.owner_view.cog,
                guild_id=self.owner_view.guild_id,
                requester_id=self.owner_view.requester_id,
                channel_id=interaction.channel_id,
                message_id=interaction.message.id,
            )
            return await interaction.response.send_modal(modal)

        if action == "toggle_mode":
            data = self.owner_view.cog.load_data(self.owner_view.guild_id)
            data["config"]["use_embed"] = not bool(data["config"].get("use_embed"))
            self.owner_view.cog.save_data(self.owner_view.guild_id, data)
            embed = self.owner_view.cog.build_config_embed(guild, interaction.user)
            view = InvitationPanelView(
                cog=self.owner_view.cog,
                requester_id=self.owner_view.requester_id,
                guild_id=self.owner_view.guild_id,
                selected_user_id=self.owner_view.selected_user_id,
                mode="config",
            )
            return await interaction.response.edit_message(embed=embed, view=view)

        if action == "rewards":
            embed = self.owner_view.cog.build_rewards_embed(guild, interaction.user, selected_slot=None)
            view = RewardsManagementView(self.owner_view.cog, self.owner_view.requester_id, self.owner_view.guild_id, selected_slot=None)
            return await interaction.response.edit_message(embed=embed, view=view)

        if action == "preview":
            preview_text = self.owner_view.cog.render_template(
                guild=guild,
                inviter=interaction.user,
                invited=interaction.user,
                invite_code="mon-code",
            )
            use_embed = self.owner_view.cog.load_data(guild.id)["config"].get("use_embed", False)
            await interaction.response.defer(ephemeral=True)
            if use_embed:
                embed = self.owner_view.cog.create_embed(guild, interaction.user, "🎉 Nouvelle invitation", preview_text)
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(preview_text, ephemeral=True)
            reset_view = InvitationPanelView(
                cog=self.owner_view.cog,
                requester_id=self.owner_view.requester_id,
                guild_id=self.owner_view.guild_id,
                selected_user_id=self.owner_view.selected_user_id,
                mode="config",
            )
            await interaction.message.edit(view=reset_view)
            return


class ProfileDisplaySelect(discord.ui.Select):
    def __init__(self, owner_view: "InvitationPanelView"):
        self.owner_view = owner_view
        presence_label = "Détail de présence"
        history_label = "Détail ancien/récent"
        options = [
            discord.SelectOption(label=presence_label, value="presence", emoji="🕒", default=owner_view.show_presence_details),
            discord.SelectOption(label=history_label, value="history", emoji="📚", default=owner_view.show_history_details),
        ]
        super().__init__(
            placeholder="Afficher / Masquer des valeurs",
            min_values=0,
            max_values=2,
            options=options,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction):
        selected = set(self.values)
        self.owner_view.show_presence_details = "presence" in selected
        self.owner_view.show_history_details = "history" in selected

        self.owner_view.cog.set_profile_prefs(
            guild_id=self.owner_view.guild_id,
            user_id=self.owner_view.requester_id,
            show_presence_details=self.owner_view.show_presence_details,
            show_history_details=self.owner_view.show_history_details,
        )

        guild = interaction.client.get_guild(self.owner_view.guild_id)
        if not guild:
            return await interaction.response.send_message("Serveur introuvable.", ephemeral=True)

        embed = await self.owner_view.cog.build_profile_embed(
            guild=guild,
            viewer=interaction.user,
            target_id=self.owner_view.selected_user_id,
            show_presence_details=self.owner_view.show_presence_details,
            show_history_details=self.owner_view.show_history_details,
        )
        view = InvitationPanelView(
            cog=self.owner_view.cog,
            requester_id=self.owner_view.requester_id,
            guild_id=self.owner_view.guild_id,
            selected_user_id=self.owner_view.selected_user_id,
            mode="profile",
            show_presence_details=self.owner_view.show_presence_details,
            show_history_details=self.owner_view.show_history_details,
        )
        await interaction.response.edit_message(embed=embed, view=view)


class InvitationPanelView(discord.ui.View):
    def __init__(
        self,
        cog: "Invitation",
        requester_id: int,
        guild_id: int,
        selected_user_id: int,
        mode: str = "profile",
        show_presence_details: bool = True,
        show_history_details: bool = True,
        leaderboard_page: int = 1,
    ):
        super().__init__(timeout=300)
        self.cog = cog
        self.requester_id = requester_id
        self.guild_id = guild_id
        self.selected_user_id = selected_user_id
        self.mode = mode
        self.show_presence_details = show_presence_details
        self.show_history_details = show_history_details
        self.leaderboard_page = max(1, leaderboard_page)

        if mode == "home":
            return

        if mode == "config":
            self.add_item(ConfigActionSelect(self))
            self.add_item(self._btn_variables())
            self.add_item(self._btn_back())
            return

        self.add_item(self._btn_profile_modal())
        self.add_item(self._btn_leaderboard())

        guild = self.cog.bot.get_guild(self.guild_id)
        member = guild.get_member(self.requester_id) if guild else None
        if member and member.guild_permissions.administrator:
            self.add_item(self._btn_config())

        if mode == "leaderboard" or (mode == "profile" and self.selected_user_id != self.requester_id):
            self.add_item(self._btn_back())

        if mode == "leaderboard":
            self.add_item(self._btn_lb_prev())
            self.add_item(self._btn_lb_next())

        if mode == "profile":
            self.add_item(ProfileDisplaySelect(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.requester_id:
            await interaction.response.send_message("Ce panneau ne vous appartient pas.", ephemeral=True)
            return False
        return True

    def _btn_profile_modal(self):
        btn = discord.ui.Button(label="Profil", emoji="👤", style=discord.ButtonStyle.primary)

        async def callback(interaction: discord.Interaction):
            modal = ProfileLookupModal(
                cog=self.cog,
                user_id=self.requester_id,
                guild_id=self.guild_id,
                channel_id=interaction.channel_id,
                message_id=interaction.message.id,
            )
            await interaction.response.send_modal(modal)

        btn.callback = callback
        return btn

    def _btn_leaderboard(self):
        btn = discord.ui.Button(label="Classement", emoji="🏆", style=discord.ButtonStyle.secondary)

        async def callback(interaction: discord.Interaction):
            guild = interaction.client.get_guild(self.guild_id)
            if not guild:
                return await interaction.response.send_message("Serveur introuvable.", ephemeral=True)

            embed = self.cog.build_leaderboard_embed(guild, interaction.user, page=1)
            view = InvitationPanelView(
                cog=self.cog,
                requester_id=self.requester_id,
                guild_id=self.guild_id,
                selected_user_id=self.selected_user_id,
                mode="leaderboard",
                show_presence_details=self.show_presence_details,
                show_history_details=self.show_history_details,
                leaderboard_page=1,
            )
            await interaction.response.edit_message(embed=embed, view=view)

        btn.callback = callback
        return btn

    def _btn_lb_prev(self):
        btn = discord.ui.Button(label="Page précédente", emoji="⬅️", style=discord.ButtonStyle.secondary, row=2)
        btn.disabled = self.leaderboard_page <= 1

        async def callback(interaction: discord.Interaction):
            guild = interaction.client.get_guild(self.guild_id)
            if not guild:
                return await interaction.response.send_message("Serveur introuvable.", ephemeral=True)

            new_page = max(1, self.leaderboard_page - 1)
            embed = self.cog.build_leaderboard_embed(guild, interaction.user, page=new_page)
            view = InvitationPanelView(
                cog=self.cog,
                requester_id=self.requester_id,
                guild_id=self.guild_id,
                selected_user_id=self.selected_user_id,
                mode="leaderboard",
                show_presence_details=self.show_presence_details,
                show_history_details=self.show_history_details,
                leaderboard_page=new_page,
            )
            await interaction.response.edit_message(embed=embed, view=view)

        btn.callback = callback
        return btn

    def _btn_lb_next(self):
        btn = discord.ui.Button(label="Page suivante", emoji="➡️", style=discord.ButtonStyle.secondary, row=2)

        async def callback(interaction: discord.Interaction):
            guild = interaction.client.get_guild(self.guild_id)
            if not guild:
                return await interaction.response.send_message("Serveur introuvable.", ephemeral=True)

            max_page = self.cog.get_leaderboard_max_page(guild)
            new_page = min(max_page, self.leaderboard_page + 1)
            embed = self.cog.build_leaderboard_embed(guild, interaction.user, page=new_page)
            view = InvitationPanelView(
                cog=self.cog,
                requester_id=self.requester_id,
                guild_id=self.guild_id,
                selected_user_id=self.selected_user_id,
                mode="leaderboard",
                show_presence_details=self.show_presence_details,
                show_history_details=self.show_history_details,
                leaderboard_page=new_page,
            )
            await interaction.response.edit_message(embed=embed, view=view)

        btn.callback = callback
        return btn

    def _btn_config(self):
        btn = discord.ui.Button(label="Configuration", emoji="⚙️", style=discord.ButtonStyle.success)

        async def callback(interaction: discord.Interaction):
            guild = interaction.client.get_guild(self.guild_id)
            if not guild:
                return await interaction.response.send_message("Serveur introuvable.", ephemeral=True)

            member = guild.get_member(interaction.user.id)
            if not member or not member.guild_permissions.administrator:
                return await interaction.response.send_message("Accès réservé aux administrateurs.", ephemeral=True)

            embed = self.cog.build_config_embed(guild, interaction.user)
            view = InvitationPanelView(
                cog=self.cog,
                requester_id=self.requester_id,
                guild_id=self.guild_id,
                selected_user_id=self.selected_user_id,
                mode="config",
            )
            await interaction.response.edit_message(embed=embed, view=view)

        btn.callback = callback
        return btn

    def _btn_set_config(self):
        btn = discord.ui.Button(label="Salon + Message", emoji="📝", style=discord.ButtonStyle.primary)

        async def callback(interaction: discord.Interaction):
            modal = ConfigModal(
                cog=self.cog,
                guild_id=self.guild_id,
                requester_id=self.requester_id,
                channel_id=interaction.channel_id,
                message_id=interaction.message.id,
            )
            await interaction.response.send_modal(modal)

        btn.callback = callback
        return btn

    def _btn_toggle_mode(self):
        btn = discord.ui.Button(label="Mode simple/embed", emoji="🎨", style=discord.ButtonStyle.secondary)

        async def callback(interaction: discord.Interaction):
            data = self.cog.load_data(self.guild_id)
            data["config"]["use_embed"] = not bool(data["config"].get("use_embed"))
            self.cog.save_data(self.guild_id, data)

            guild = interaction.client.get_guild(self.guild_id)
            if not guild:
                return await interaction.response.send_message("Serveur introuvable.", ephemeral=True)

            embed = self.cog.build_config_embed(guild, interaction.user)
            view = InvitationPanelView(
                cog=self.cog,
                requester_id=self.requester_id,
                guild_id=self.guild_id,
                selected_user_id=self.selected_user_id,
                mode="config",
            )
            await interaction.response.edit_message(embed=embed, view=view)

        btn.callback = callback
        return btn

    def _btn_variables(self):
        btn = discord.ui.Button(label="Variables", emoji="🧩", style=discord.ButtonStyle.secondary)

        async def callback(interaction: discord.Interaction):
            guild = interaction.client.get_guild(self.guild_id)
            if not guild:
                return await interaction.response.send_message("Serveur introuvable.", ephemeral=True)

            view = VariablesHelpView(self.cog, self.requester_id, self.guild_id)
            embed = view.build_summary_embed(guild, interaction.user)
            await interaction.response.send_message(embed=embed, ephemeral=True)

        btn.callback = callback
        return btn

    def _btn_preview(self):
        btn = discord.ui.Button(label="Aperçu", emoji="👁️", style=discord.ButtonStyle.secondary)

        async def callback(interaction: discord.Interaction):
            guild = interaction.client.get_guild(self.guild_id)
            if not guild:
                return await interaction.response.send_message("Serveur introuvable.", ephemeral=True)

            preview_text = self.cog.render_template(
                guild=guild,
                inviter=interaction.user,
                invited=interaction.user,
                invite_code="mon-code",
            )
            use_embed = self.cog.load_data(guild.id)["config"].get("use_embed", False)

            if use_embed:
                embed = self.cog.create_embed(guild, interaction.user, "🎉 Nouvelle invitation", preview_text)
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(preview_text, ephemeral=True)

        btn.callback = callback
        return btn

    def _btn_rewards_menu(self):
        btn = discord.ui.Button(label="Récompenses", emoji="🎖️", style=discord.ButtonStyle.success)

        async def callback(interaction: discord.Interaction):
            guild = interaction.client.get_guild(self.guild_id)
            if not guild:
                return await interaction.response.send_message("Serveur introuvable.", ephemeral=True)
            embed = self.cog.build_rewards_embed(guild, interaction.user, selected_slot=None)
            view = RewardsManagementView(self.cog, self.requester_id, self.guild_id, selected_slot=None)
            await interaction.response.edit_message(embed=embed, view=view)

        btn.callback = callback
        return btn

    def _btn_back(self):
        btn = discord.ui.Button(label="Retour", emoji="↩️", style=discord.ButtonStyle.danger)

        async def callback(interaction: discord.Interaction):
            guild = interaction.client.get_guild(self.guild_id)
            if not guild:
                return await interaction.response.send_message("Serveur introuvable.", ephemeral=True)

            embed = await self.cog.build_profile_embed(
                guild,
                interaction.user,
                self.requester_id,
                show_presence_details=self.show_presence_details,
                show_history_details=self.show_history_details,
            )
            view = InvitationPanelView(
                cog=self.cog,
                requester_id=self.requester_id,
                guild_id=self.guild_id,
                selected_user_id=self.requester_id,
                mode="profile",
                show_presence_details=self.show_presence_details,
                show_history_details=self.show_history_details,
            )
            await interaction.response.edit_message(embed=embed, view=view)

        btn.callback = callback
        return btn


class Invitation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.invites_cache: Dict[int, Dict[str, int]] = {}
        self.invites_meta_cache: Dict[int, Dict[str, Dict[str, Any]]] = {}
        self.recently_deleted_invites: Dict[int, Dict[str, Dict[str, Any]]] = {}
        self.vanity_cache: Dict[int, int] = {}
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(DB_PATH)

    def _init_db(self):
        with self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS configs (
                    guild_id INTEGER PRIMARY KEY,
                    channel_id INTEGER,
                    message_template TEXT,
                    use_embed INTEGER DEFAULT 0
                )
                """
            )
            cols = [row[1] for row in con.execute("PRAGMA table_info(role_rewards)").fetchall()]
            if cols and "slot" not in cols:
                old_rows = con.execute("SELECT guild_id, enabled, role_id, required_invites FROM role_rewards").fetchall()
                con.execute("DROP TABLE role_rewards")
                con.commit()
                con.execute(
                    """
                    CREATE TABLE role_rewards (
                        guild_id INTEGER,
                        slot INTEGER,
                        enabled INTEGER DEFAULT 1,
                        role_id INTEGER,
                        required_invites INTEGER DEFAULT 1,
                        PRIMARY KEY (guild_id, slot)
                    )
                    """
                )
                for guild_id, enabled, role_id, required_invites in old_rows:
                    if role_id:
                        con.execute(
                            "INSERT OR REPLACE INTO role_rewards(guild_id, slot, enabled, role_id, required_invites) VALUES(?, 1, ?, ?, ?)",
                            (guild_id, int(enabled or 0), role_id, int(required_invites or 1)),
                        )
            else:
                con.execute(
                    """
                    CREATE TABLE IF NOT EXISTS role_rewards (
                        guild_id INTEGER,
                        slot INTEGER,
                        enabled INTEGER DEFAULT 1,
                        role_id INTEGER,
                        required_invites INTEGER DEFAULT 1,
                        PRIMARY KEY (guild_id, slot)
                    )
                    """
                )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS inviters (
                    guild_id INTEGER,
                    inviter_id INTEGER,
                    joined_total INTEGER DEFAULT 0,
                    bots_total INTEGER DEFAULT 0,
                    PRIMARY KEY (guild_id, inviter_id)
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS invited_users (
                    guild_id INTEGER,
                    user_id INTEGER,
                    inviter_id INTEGER,
                    invite_code TEXT,
                    joined_at TEXT,
                    is_bot INTEGER DEFAULT 0,
                    is_present INTEGER DEFAULT 1,
                    invited_name TEXT,
                    inviter_name TEXT,
                    PRIMARY KEY (guild_id, user_id)
                )
                """
            )
            invited_cols = [row[1] for row in con.execute("PRAGMA table_info(invited_users)").fetchall()]
            if invited_cols and "is_present" not in invited_cols:
                con.execute("ALTER TABLE invited_users ADD COLUMN is_present INTEGER DEFAULT 1")
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS profile_prefs (
                    guild_id INTEGER,
                    user_id INTEGER,
                    show_presence_details INTEGER DEFAULT 1,
                    show_history_details INTEGER DEFAULT 1,
                    PRIMARY KEY (guild_id, user_id)
                )
                """
            )
            con.commit()

    def get_profile_prefs(self, guild_id: int, user_id: int) -> tuple[bool, bool]:
        with self._connect() as con:
            row = con.execute(
                "SELECT show_presence_details, show_history_details FROM profile_prefs WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ).fetchone()
            if row is None:
                return True, True
            return bool(row[0]), bool(row[1])

    def set_profile_prefs(self, guild_id: int, user_id: int, show_presence_details: bool, show_history_details: bool):
        with self._connect() as con:
            con.execute(
                """
                INSERT INTO profile_prefs(guild_id, user_id, show_presence_details, show_history_details)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    show_presence_details = excluded.show_presence_details,
                    show_history_details = excluded.show_history_details
                """,
                (guild_id, user_id, 1 if show_presence_details else 0, 1 if show_history_details else 0),
            )
            con.commit()

    # ----------------------------- DATA -------------------------------------
    def load_data(self, guild_id: int) -> Dict[str, Any]:
        data = default_guild_data()
        with self._connect() as con:
            cfg = con.execute(
                "SELECT channel_id, message_template, use_embed FROM configs WHERE guild_id = ?",
                (guild_id,),
            ).fetchone()
            if cfg:
                data["config"]["channel_id"] = cfg[0]
                data["config"]["message_template"] = cfg[1] or DEFAULT_TEMPLATE
                data["config"]["use_embed"] = bool(cfg[2])

            rw = con.execute(
                "SELECT slot, enabled, role_id, required_invites FROM role_rewards WHERE guild_id = ? ORDER BY slot ASC",
                (guild_id,),
            ).fetchall()
            data["role_rewards"] = []
            for slot, enabled, role_id, required_invites in rw:
                data["role_rewards"].append(
                    {
                        "slot": int(slot),
                        "enabled": bool(enabled),
                        "role_id": role_id,
                        "required_invites": int(required_invites or 1),
                    }
                )

            inviter_rows = con.execute(
                "SELECT inviter_id, joined_total, bots_total FROM inviters WHERE guild_id = ?",
                (guild_id,),
            ).fetchall()
            for inviter_id, joined_total, bots_total in inviter_rows:
                data["inviters"][str(inviter_id)] = {
                    "joined_total": int(joined_total or 0),
                    "bots_total": int(bots_total or 0),
                }

            invited_rows = con.execute(
                "SELECT user_id, inviter_id, invite_code, joined_at, is_bot, is_present, invited_name, inviter_name FROM invited_users WHERE guild_id = ?",
                (guild_id,),
            ).fetchall()
            for user_id, inviter_id, invite_code, joined_at, is_bot, is_present, invited_name, inviter_name in invited_rows:
                data["invited_users"][str(user_id)] = {
                    "inviter_id": inviter_id,
                    "invite_code": invite_code,
                    "joined_at": joined_at,
                    "is_bot": bool(is_bot),
                    "is_present": bool(is_present) if is_present is not None else True,
                    "invited_name": invited_name,
                    "inviter_name": inviter_name,
                }

        return data

    def save_data(self, guild_id: int, data: Dict[str, Any]):
        cfg = data.get("config", {})
        rewards = data.get("role_rewards", [])
        inviters = data.get("inviters", {})
        invited_users = data.get("invited_users", {})

        with self._connect() as con:
            con.execute(
                """
                INSERT INTO configs(guild_id, channel_id, message_template, use_embed)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    channel_id = excluded.channel_id,
                    message_template = excluded.message_template,
                    use_embed = excluded.use_embed
                """,
                (
                    guild_id,
                    cfg.get("channel_id"),
                    cfg.get("message_template") or DEFAULT_TEMPLATE,
                    1 if cfg.get("use_embed") else 0,
                ),
            )
            con.execute("DELETE FROM role_rewards WHERE guild_id = ?", (guild_id,))
            for r in rewards[:25]:
                if not r.get("role_id"):
                    continue
                con.execute(
                    "INSERT INTO role_rewards(guild_id, slot, enabled, role_id, required_invites) VALUES(?, ?, ?, ?, ?)",
                    (
                        guild_id,
                        int(r.get("slot", 0)),
                        1 if r.get("enabled", True) else 0,
                        int(r.get("role_id")),
                        int(r.get("required_invites") or 1),
                    ),
                )

            con.execute("DELETE FROM inviters WHERE guild_id = ?", (guild_id,))
            for inviter_id, stats in inviters.items():
                con.execute(
                    "INSERT INTO inviters(guild_id, inviter_id, joined_total, bots_total) VALUES(?, ?, ?, ?)",
                    (
                        guild_id,
                        int(inviter_id),
                        int(stats.get("joined_total", 0)),
                        int(stats.get("bots_total", 0)),
                    ),
                )

            con.execute("DELETE FROM invited_users WHERE guild_id = ?", (guild_id,))
            for user_id, rec in invited_users.items():
                con.execute(
                    """
                    INSERT INTO invited_users(guild_id, user_id, inviter_id, invite_code, joined_at, is_bot, is_present, invited_name, inviter_name)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        guild_id,
                        int(user_id),
                        rec.get("inviter_id"),
                        rec.get("invite_code"),
                        rec.get("joined_at"),
                        1 if rec.get("is_bot") else 0,
                        1 if rec.get("is_present", True) else 0,
                        rec.get("invited_name"),
                        rec.get("inviter_name"),
                    ),
                )

            con.commit()

    # ----------------------------- EMBEDS -----------------------------------
    def create_embed(self, guild: Optional[discord.Guild], user: discord.abc.User, title: str, description: str) -> discord.Embed:
        if config_manager:
            return config_manager.get_formatted_embed(
                guild=guild,
                user=user,
                bot=self.bot,
                title=title,
                description=description,
                target_id=guild.id if guild else None,
                force_global=guild is None,
            )

        embed = discord.Embed(title=title, description=description, color=0x2B2D31)
        if self.bot.user:
            embed.set_footer(text=f"{self.bot.user.name} - /help pour decouvrir mes commandes.")
        return embed

    async def build_profile_embed(
        self,
        guild: discord.Guild,
        viewer: discord.abc.User,
        target_id: int,
        show_presence_details: bool = True,
        show_history_details: bool = True,
    ) -> discord.Embed:
        data = self.load_data(guild.id)
        target_member = guild.get_member(target_id)
        target_user = target_member or await self._safe_fetch_user(target_id)

        display_name = target_user.display_name if hasattr(target_user, "display_name") else str(target_id)
        avatar_url = target_user.display_avatar.url if hasattr(target_user, "display_avatar") else None

        invited_users = data.get("invited_users", {})
        inviters = data.get("inviters", {})

        invited_by_rec = invited_users.get(str(target_id), {})
        invited_by = invited_by_rec.get("inviter_id")
        invited_by_name = invited_by_rec.get("inviter_name")
        invited_by_member = guild.get_member(int(invited_by)) if invited_by else None
        if invited_by_member:
            invited_by_text = invited_by_member.mention
        elif invited_by:
            invited_by_text = f"<@{int(invited_by)}>"
        elif invited_by_name:
            invited_by_text = f"`{invited_by_name}`"
        else:
            invited_by_text = "Inconnu"

        invited_records = [
            (uid, rec)
            for uid, rec in invited_users.items()
            if str(rec.get("inviter_id")) == str(target_id)
        ]

        bots_invited = sum(1 for _, rec in invited_records if rec.get("is_bot"))
        human_total_joined = sum(1 for _, rec in invited_records if not rec.get("is_bot"))

        present_humans = []
        for uid, rec in invited_records:
            if rec.get("is_bot"):
                continue
            is_present = rec.get("is_present")
            if is_present is None:
                is_present = bool(guild.get_member(int(uid)))
            if bool(is_present):
                member = guild.get_member(int(uid))
                mention = member.mention if member else f"<@{int(uid)}>"
                present_humans.append((mention, rec))

        present_count = len(present_humans)
        now = utcnow()

        def older_than_days(rec: Dict[str, Any], days: int) -> bool:
            joined = parse_dt(rec.get("joined_at"))
            return bool(joined and (now - joined).days >= days)

        d7 = sum(1 for _, rec in present_humans if older_than_days(rec, 7))
        d1 = sum(1 for _, rec in present_humans if older_than_days(rec, 1))
        d30 = sum(1 for _, rec in present_humans if older_than_days(rec, 30))
        d90 = sum(1 for _, rec in present_humans if older_than_days(rec, 90))
        d180 = sum(1 for _, rec in present_humans if older_than_days(rec, 180))
        d270 = sum(1 for _, rec in present_humans if older_than_days(rec, 270))
        d365 = sum(1 for _, rec in present_humans if older_than_days(rec, 365))

        newest_present = sorted(
            present_humans,
            key=lambda x: parse_dt(x[1].get("joined_at")) or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )[:3]
        oldest_present = sorted(
            present_humans,
            key=lambda x: parse_dt(x[1].get("joined_at")) or datetime.max.replace(tzinfo=timezone.utc),
        )[:3]

        newest_txt = (
            "\n".join(
                f"• {mention} - {format_presence_duration(parse_dt(rec.get('joined_at')) or utcnow(), now)}"
                for mention, rec in newest_present
            )
            if newest_present
            else "Aucun"
        )
        oldest_txt = (
            "\n".join(
                f"• {mention} - {format_presence_duration(parse_dt(rec.get('joined_at')) or utcnow(), now)}"
                for mention, rec in oldest_present
            )
            if oldest_present
            else "Aucun"
        )

        inviter_stats = inviters.get(str(target_id), {})
        total_recorded = inviter_stats.get("joined_total", human_total_joined)

        invite_link = await self.get_best_invite_link_for_user(guild, target_id)
        invite_link_text = invite_link if invite_link else "Aucun lien actif"

        lines = []
        if invited_by_text != "Inconnu":
            lines.append(f"👥 **J'ai été invité par** : {invited_by_text}")
        if invite_link_text != "Aucun lien actif":
            lines.append(f"🔗 **Mon lien d'invitation** : {invite_link_text}")

        if lines:
            lines.append("")

        lines.extend(
            [
                f"🤖 **Bots invités** : `{bots_invited}`",
                f"📥 **Ayant rejoint** : `{total_recorded}`",
                f"✅ **Ayant rejoint & encore sur le discord** : `{present_count}`",
            ]
        )

        if show_presence_details:
            lines.extend(
                [
                    f"🗓️ **Présents depuis +24h** : `{d1}`",
                    f"🗓️ **Présents depuis +7j** : `{d7}`",
                    f"🗓️ **Présents depuis +1 mois** : `{d30}`",
                    f"🗓️ **Présents depuis +3 mois** : `{d90}`",
                    f"🗓️ **Présents depuis +6 mois** : `{d180}`",
                    f"🗓️ **Présents depuis +9 mois** : `{d270}`",
                    f"🗓️ **Présents depuis +12 mois** : `{d365}`",
                ]
            )

        if show_history_details:
            lines.extend(
                [
                    "",
                    f"🆕 **3 derniers ayant rejoint** :\n{newest_txt}",
                    "",
                    f"🏛️ **3 plus anciens** :\n{oldest_txt}",
                ]
            )

        description = "\n".join(lines)

        embed = self.create_embed(guild, viewer, None, description)
        if avatar_url:
            embed.set_author(name=f"Profil invitation de {display_name}", icon_url=avatar_url)
            embed.set_thumbnail(url=avatar_url)
        return embed

    def build_leaderboard_embed(self, guild: discord.Guild, viewer: discord.abc.User, page: int = 1) -> discord.Embed:
        data = self.load_data(guild.id)
        rows = self._get_leaderboard_rows(guild, data)

        max_page = self._get_leaderboard_max_page_from_total(len(rows))
        page = min(max(1, page), max_page)
        start, end = self._get_leaderboard_bounds(page)
        chunk = rows[start:end]

        viewer_count = self.active_invites_count(guild, data, viewer.id)
        viewer_position = next((idx + 1 for idx, (uid, _count) in enumerate(rows) if uid == viewer.id), None)
        if viewer_position:
            header = f"🙋 **Vous êtes position #{viewer_position} avec {viewer_count} invité{'s' if viewer_count != 1 else ''}.**"
        else:
            header = f"🙋 **Vous êtes position non classée avec {viewer_count} invité{'s' if viewer_count != 1 else ''}.**"

        if not rows:
            desc = header + "\n\n📭 Aucune donnée d'invitation disponible pour le moment."
        else:
            lines = [header, "", f"📄 **Page {page}/{max_page}**"]
            for i, (uid, count) in enumerate(chunk, start=start + 1):
                member = guild.get_member(uid)
                mention = member.mention if member else f"<@{uid}>"
                medal = "🥇" if i == 1 else ("🥈" if i == 2 else ("🥉" if i == 3 else "🔹"))
                suffix = "invité" if count == 1 else "invités"
                lines.append(f"{medal} #{i} {mention} - {count} {suffix}")
            desc = "\n".join(lines)

        embed = self.create_embed(guild, viewer, "🏆 Classement des invitations", desc)
        if rows:
            top_member = guild.get_member(rows[0][0])
            if top_member:
                embed.set_thumbnail(url=top_member.display_avatar.url)
        return embed

    def build_config_embed(self, guild: discord.Guild, viewer: discord.abc.User) -> discord.Embed:
        data = self.load_data(guild.id)
        cfg = data["config"]
        rewards = data.get("role_rewards", [])

        channel_txt = f"<#{cfg.get('channel_id')}>" if cfg.get("channel_id") else "Non configuré"
        mode_txt = "Embed" if cfg.get("use_embed") else "Message simple"
        active_count = sum(1 for r in rewards if r.get("enabled"))

        desc = (
            f"📣 **Salon de notification** : {channel_txt}\n"
            f"🎛️ **Type d'envoi** : `{mode_txt}`\n"
            f"💬 **Message personnalisé** :\n"
            f"```{cfg.get('message_template') or DEFAULT_TEMPLATE}```\n"
            f"🎖️ **Récompenses configurées** : `{len(rewards)}/25`\n"
            f"✅ **Récompenses actives** : `{active_count}`"
        )

        return self.create_embed(guild, viewer, "⚙️ Configuration des invitations", desc)

    def build_rewards_embed(self, guild: discord.Guild, viewer: discord.abc.User, selected_slot: Optional[int]) -> discord.Embed:
        data = self.load_data(guild.id)
        rewards = sorted(data.get("role_rewards", []), key=lambda x: int(x.get("slot", 0)))

        lines = []
        for r in rewards:
            slot = int(r.get("slot", 0))
            role_id = r.get("role_id")
            role = guild.get_role(int(role_id)) if role_id else None
            role_txt = role.mention if role else f"Role {role_id}"
            req = int(r.get("required_invites", 1))
            state = "✅" if r.get("enabled", True) else "⛔"
            marker = "👉" if selected_slot == slot else "•"
            lines.append(f"{marker} #{slot} {state} {role_txt} - `{req}` invité(s)")

        desc = (
            f"🎁 **Gestion des récompenses d'invitation**\n"
            f"`{len(rewards)}/25` récompenses configurées\n\n"
            + ("\n".join(lines) if lines else "Aucune récompense configurée pour le moment.")
            + "\n\nSélectionnez une récompense, puis choisissez **Modifier** ou **Supprimer**."
        )
        return self.create_embed(guild, viewer, "🎖️ Récompenses d'invitation", desc)

    async def get_best_invite_link_for_user(self, guild: discord.Guild, user_id: int) -> Optional[str]:
        try:
            invites = await guild.invites()
        except Exception:
            return None

        mine = [i for i in invites if i.inviter and i.inviter.id == user_id]
        if not mine:
            return None

        best = max(mine, key=lambda i: (i.uses or 0, i.created_at or datetime.min.replace(tzinfo=timezone.utc)))
        return best.url

    # ----------------------------- HELPERS ----------------------------------
    async def edit_panel_message(self, channel_id: int, message_id: int, embed: discord.Embed, view: discord.ui.View) -> bool:
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return False
        try:
            msg = await channel.fetch_message(message_id)
            await msg.edit(embed=embed, view=view)
            return True
        except Exception:
            return False

    async def _safe_fetch_user(self, user_id: int):
        try:
            return await self.bot.fetch_user(user_id)
        except Exception:
            return None

    def active_invites_count(self, guild: discord.Guild, data: Dict[str, Any], inviter_id: int) -> int:
        total = 0
        for uid, rec in data.get("invited_users", {}).items():
            if str(rec.get("inviter_id")) != str(inviter_id):
                continue
            if rec.get("is_bot"):
                continue
            is_present = rec.get("is_present")
            if is_present is None:
                is_present = bool(guild.get_member(int(uid)))
            if bool(is_present):
                total += 1
        return total

    def _get_leaderboard_rows(self, guild: discord.Guild, data: Dict[str, Any]) -> list[tuple[int, int]]:
        inviters = data.get("inviters", {})
        invited_users = data.get("invited_users", {})

        rows = []
        for inviter_id_str in inviters.keys():
            inviter_id = int(inviter_id_str)
            active = self.active_invites_count(guild, data, inviter_id)
            rows.append((inviter_id, active))

        for rec in invited_users.values():
            inviter_id = rec.get("inviter_id")
            if not inviter_id:
                continue
            if all(int(inviter_id) != rid for rid, _ in rows):
                rows.append((int(inviter_id), self.active_invites_count(guild, data, int(inviter_id))))

        rows.sort(key=lambda x: x[1], reverse=True)
        return rows

    @staticmethod
    def _get_leaderboard_bounds(page: int) -> tuple[int, int]:
        if page <= 1:
            return 0, 10
        if page == 2:
            return 10, 50
        start = 50 + (page - 3) * 50
        return start, start + 50

    @staticmethod
    def _get_leaderboard_max_page_from_total(total: int) -> int:
        if total <= 10:
            return 1
        if total <= 50:
            return 2
        return 2 + ((total - 50 + 49) // 50)

    def get_leaderboard_max_page(self, guild: discord.Guild) -> int:
        data = self.load_data(guild.id)
        rows = self._get_leaderboard_rows(guild, data)
        return self._get_leaderboard_max_page_from_total(len(rows))

    def total_active_invited_in_guild(self, guild: discord.Guild, data: Dict[str, Any]) -> int:
        return sum(
            1
            for uid, rec in data.get("invited_users", {}).items()
            if not rec.get("is_bot") and guild.get_member(int(uid))
        )

    def render_template(
        self,
        guild: discord.Guild,
        inviter: Optional[discord.abc.User],
        invited: discord.abc.User,
        invite_code: str,
        custom_template: Optional[str] = None,
        inviter_id: Optional[int] = None,
        inviter_name_override: Optional[str] = None,
    ) -> str:
        data = self.load_data(guild.id)
        template = custom_template if custom_template is not None else (data["config"].get("message_template") or DEFAULT_TEMPLATE)

        effective_inviter_id = inviter.id if inviter else inviter_id
        inviter_mention = inviter.mention if inviter else (f"<@{effective_inviter_id}>" if effective_inviter_id else "Inconnu")
        inviter_name = inviter.display_name if inviter else (inviter_name_override or (f"Utilisateur {effective_inviter_id}" if effective_inviter_id else "Inconnu"))

        values = {
            "{inviter}": inviter_mention,
            "{@inviter}": inviter_mention,
            "{inviter_name}": inviter_name,
            "{invited}": invited.mention,
            "{@invited}": invited.mention,
            "{invited_name}": invited.display_name,
            "{invite_total}": str(self.total_active_invited_in_guild(guild, data)),
            "{inviter_count}": str(self.active_invites_count(guild, data, effective_inviter_id)) if effective_inviter_id else "0",
            "{invite_code}": invite_code or "inconnu",
            "<@invitedname>": invited.mention,
            "<@invitername>": inviter_mention,
            "<@invtername>": inviter_mention,
        }

        text = template
        for key, value in values.items():
            text = text.replace(key, value)
        return text

    async def refresh_role_rewards(self, guild: discord.Guild):
        data = self.load_data(guild.id)
        rewards = data.get("role_rewards", [])
        if not rewards:
            return
        candidate_ids = set(int(x) for x in data.get("inviters", {}).keys())
        managed_roles = []
        for r in rewards:
            role_id = r.get("role_id")
            if not role_id:
                continue
            role = guild.get_role(int(role_id))
            if role:
                managed_roles.append((role, r))
                for m in role.members:
                    candidate_ids.add(m.id)

        for uid in candidate_ids:
            member = guild.get_member(uid)
            if not member:
                continue
            current = self.active_invites_count(guild, data, uid)
            for role, r in managed_roles:
                enabled = bool(r.get("enabled", True))
                required = int(r.get("required_invites") or 1)
                should_have = enabled and current >= required
                has_role = role in member.roles
                try:
                    if should_have and not has_role:
                        await member.add_roles(role, reason="Invitation reward threshold reached")
                    elif not should_have and has_role:
                        await member.remove_roles(role, reason="Invitation reward threshold not met")
                except Exception:
                    continue

    # ----------------------------- INVITE CACHE -----------------------------
    async def cache_guild_invites(self, guild: discord.Guild):
        try:
            invites = await guild.invites()
        except Exception:
            self.invites_cache[guild.id] = {}
            self.invites_meta_cache[guild.id] = {}
        else:
            self.invites_cache[guild.id] = {i.code: i.uses for i in invites}
            self.invites_meta_cache[guild.id] = {i.code: self._invite_meta(i) for i in invites}

        self.vanity_cache[guild.id] = await self._get_vanity_uses(guild)

    async def _get_vanity_uses(self, guild: discord.Guild) -> int:
        code = getattr(guild, "vanity_url_code", None)
        if not code:
            return 0
        try:
            vanity = await guild.vanity_invite()
            return int(getattr(vanity, "uses", 0) or 0)
        except Exception:
            return 0

    def _invite_meta(self, invite: discord.Invite) -> Dict[str, Any]:
        created_at = getattr(invite, "created_at", None)
        created_ts = created_at.timestamp() if created_at else 0.0
        return {
            "inviter_id": invite.inviter.id if invite.inviter else None,
            "uses": int(invite.uses or 0),
            "max_uses": invite.max_uses,
            "created_ts": created_ts,
        }

    async def detect_used_invite(self, guild: discord.Guild) -> tuple[Optional[str], Optional[int]]:
        old = self.invites_cache.get(guild.id, {})
        old_meta = self.invites_meta_cache.get(guild.id, {})
        old_vanity_uses = self.vanity_cache.get(guild.id, 0)
        try:
            new_invites = await guild.invites()
        except Exception:
            new_invites = []

        new_map = {i.code: i.uses for i in new_invites}
        new_meta = {i.code: self._invite_meta(i) for i in new_invites}
        self.invites_cache[guild.id] = new_map
        self.invites_meta_cache[guild.id] = new_meta

        for inv in new_invites:
            prev_uses = old.get(inv.code, 0)
            if inv.uses > prev_uses:
                inviter_id = inv.inviter.id if inv.inviter else None
                return inv.code, inviter_id

        removed_candidates = []
        for code, prev_uses in old.items():
            if code in new_map:
                continue
            meta = old_meta.get(code, {})
            max_uses = meta.get("max_uses")
            if max_uses == 1 and int(prev_uses or 0) == 0:
                removed_candidates.append((code, meta))

        if removed_candidates:
            removed_candidates.sort(key=lambda x: float(x[1].get("created_ts") or 0.0), reverse=True)
            best_code, best_meta = removed_candidates[0]
            return best_code, best_meta.get("inviter_id")

        now_ts = utcnow().timestamp()
        deleted_map = self.recently_deleted_invites.get(guild.id, {})
        deleted_candidates = []
        for code, meta in list(deleted_map.items()):
            deleted_ts = float(meta.get("deleted_ts") or 0.0)
            if (now_ts - deleted_ts) > 60:
                deleted_map.pop(code, None)
                continue
            if int(meta.get("max_uses") or 0) == 1:
                deleted_candidates.append((code, meta))

        if deleted_candidates:
            deleted_candidates.sort(key=lambda x: float(x[1].get("deleted_ts") or 0.0), reverse=True)
            best_code, best_meta = deleted_candidates[0]
            deleted_map.pop(best_code, None)
            return best_code, best_meta.get("inviter_id")

        vanity_code = getattr(guild, "vanity_url_code", None)
        if vanity_code:
            new_vanity_uses = await self._get_vanity_uses(guild)
            self.vanity_cache[guild.id] = new_vanity_uses
            if new_vanity_uses > old_vanity_uses:
                return vanity_code, None

        return None, None

    # ----------------------------- EVENTS -----------------------------------
    @commands.Cog.listener()
    async def on_ready(self):
        for guild in self.bot.guilds:
            await self.cache_guild_invites(guild)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        await self.cache_guild_invites(guild)

    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        guild = invite.guild
        if guild:
            self.invites_cache.setdefault(guild.id, {})[invite.code] = int(invite.uses or 0)
            self.invites_meta_cache.setdefault(guild.id, {})[invite.code] = self._invite_meta(invite)
            await self.cache_guild_invites(guild)

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        guild = invite.guild
        if guild:
            meta = self._invite_meta(invite)
            meta["deleted_ts"] = utcnow().timestamp()
            self.recently_deleted_invites.setdefault(guild.id, {})[invite.code] = meta
            await self.cache_guild_invites(guild)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        code, inviter_id = await self.detect_used_invite(guild)
        inviter = guild.get_member(inviter_id) if inviter_id else None
        inviter_user = inviter
        if inviter_id and inviter_user is None:
            inviter_user = await self._safe_fetch_user(inviter_id)

        data = self.load_data(guild.id)

        if inviter_id:
            inv = data["inviters"].setdefault(str(inviter_id), {"joined_total": 0, "bots_total": 0})
            if member.bot:
                inv["bots_total"] = int(inv.get("bots_total", 0)) + 1
            else:
                inv["joined_total"] = int(inv.get("joined_total", 0)) + 1

        data["invited_users"][str(member.id)] = {
            "inviter_id": inviter_id,
            "invite_code": code or "inconnu",
            "joined_at": utcnow().isoformat(),
            "is_bot": bool(member.bot),
            "is_present": True,
            "invited_name": member.display_name,
            "inviter_name": inviter_user.display_name if inviter_user else None,
        }
        self.save_data(guild.id, data)

        await self.send_join_log(guild, inviter_user, member, code or "inconnu", inviter_id=inviter_id)
        await self.refresh_role_rewards(guild)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        data = self.load_data(member.guild.id)
        rec = data.get("invited_users", {}).get(str(member.id))
        if rec is not None:
            rec["is_present"] = False
            data["invited_users"][str(member.id)] = rec
            self.save_data(member.guild.id, data)
        await self.refresh_role_rewards(member.guild)

    async def send_join_log(
        self,
        guild: discord.Guild,
        inviter: Optional[discord.abc.User],
        invited: discord.Member,
        code: str,
        inviter_id: Optional[int] = None,
    ):
        data = self.load_data(guild.id)
        cfg = data.get("config", {})
        channel_id = cfg.get("channel_id")
        if not channel_id:
            return

        channel = guild.get_channel(int(channel_id))
        if not channel:
            return

        vanity_code = getattr(guild, "vanity_url_code", None)
        if vanity_code and code == vanity_code and inviter is None:
            text = f"**{invited.display_name}** est arrivé en utilisant l'invitation personnalisée **{vanity_code}**"
        else:
            text = self.render_template(
                guild,
                inviter,
                invited,
                code,
                inviter_id=inviter_id,
                inviter_name_override=(inviter.display_name if inviter else None),
            )
        use_embed = bool(cfg.get("use_embed"))

        try:
            if use_embed:
                embed = self.create_embed(guild, invited, "🎉 Nouvelle invitation", text)
                await channel.send(embed=embed)
            else:
                await channel.send(text)
        except Exception:
            pass

    # ----------------------------- COMMAND ----------------------------------
    @commands.hybrid_command(name="invitation", description="Panneau invitations: profil, classement et configuration.")
    async def invitation(self, ctx: commands.Context):
        if not ctx.guild:
            return await ctx.send("Cette commande est disponible uniquement sur un serveur.")

        await ctx.defer(ephemeral=False)

        show_presence_details, show_history_details = self.get_profile_prefs(ctx.guild.id, ctx.author.id)
        embed = await self.build_profile_embed(
            ctx.guild,
            ctx.author,
            ctx.author.id,
            show_presence_details=show_presence_details,
            show_history_details=show_history_details,
        )
        view = InvitationPanelView(
            cog=self,
            requester_id=ctx.author.id,
            guild_id=ctx.guild.id,
            selected_user_id=ctx.author.id,
            mode="profile",
            show_presence_details=show_presence_details,
            show_history_details=show_history_details,
        )
        await ctx.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    if bot.get_command("invitation"):
        bot.remove_command("invitation")
    await bot.add_cog(Invitation(bot))