import discord
from discord.ext import commands
import json
import os
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
import pytz
import logging

# ==============================================================================
# --------------------------- IMPORTATION UTILS --------------------------------
# ==============================================================================
try:
    from cogs.developpeur.commands.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# ==============================================================================
# --------------------------- CONFIGURATION ------------------------------------
# ==============================================================================
logger = logging.getLogger('backup_cog')
logger.setLevel(logging.WARNING)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('[BACKUP] %(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)

FRANCE_TZ = pytz.timezone('Europe/Paris')


def _resolve_author_id(inter_or_ctx):
    if isinstance(inter_or_ctx, discord.Interaction):
        return inter_or_ctx.user.id
    return inter_or_ctx.author.id


class AuthorOnlyView(discord.ui.View):
    def __init__(self, author_id, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Seule la personne qui a execute cette commande peut utiliser ces boutons.",
                ephemeral=True,
            )
            return False
        return True

# ==============================================================================
# --------------------------- VIEWS D'ÉDITION ----------------------------------
# ==============================================================================

class BackupEditRenameModal(discord.ui.Modal):
    """Modal pour renommer un rôle, une catégorie ou un salon dans la backup"""
    def __init__(self, cog, backup_id, backup_name, inter_or_ctx, edit_type, item_val, item_name, page, category_idx=None):
        super().__init__(title="Renommer l'élément")
        self.cog = cog
        self.backup_id = backup_id
        self.backup_name = backup_name
        self.inter_or_ctx = inter_or_ctx
        self.edit_type = edit_type
        self.item_val = item_val
        self.page = page
        self.category_idx = category_idx

        self.name_input = discord.ui.TextInput(
            label="Nouveau nom",
            default=item_name,
            max_length=100,
            required=True
        )
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction):
        new_name = self.name_input.value.strip()
        data = self.cog._get_json(self.backup_id)

        if self.edit_type == "roles":
            data["roles"][int(self.item_val)]["name"] = new_name
        elif self.edit_type == "categories":
            data["categories"][int(self.item_val)]["name"] = new_name
        elif self.edit_type == "channels":
            if self.item_val.startswith("orphan_"):
                idx = int(self.item_val.split("_")[1])
                data["orphan_channels"][idx]["name"] = new_name
            else:
                c_idx, ch_idx = map(int, self.item_val.split("_"))
                data["categories"][c_idx]["channels"][ch_idx]["name"] = new_name

        self.cog._save_json(self.backup_id, data)

        view = BackupEditSelectView(self.cog, self.backup_id, self.backup_name, self.inter_or_ctx, self.edit_type, self.page, self.category_idx)
        type_fr = {"roles": "Rôles", "categories": "Catégories", "channels": "Salons"}[self.edit_type]
        embed = self.cog.get_custom_embed(interaction, f"🛠️ Modification - {type_fr}", f"✅ Élément renommé en **{new_name}**.\nSélectionnez un autre élément à modifier.")
        await interaction.response.edit_message(embed=embed, view=view)


class BackupEditActionView(AuthorOnlyView):
    """Vue des actions (Renommer/Supprimer) pour un élément spécifique"""
    def __init__(self, cog, backup_id, backup_name, inter_or_ctx, edit_type, item_val, item_name, page, category_idx=None):
        super().__init__(_resolve_author_id(inter_or_ctx), timeout=120)
        self.cog = cog
        self.backup_id = backup_id
        self.backup_name = backup_name
        self.inter_or_ctx = inter_or_ctx
        self.edit_type = edit_type
        self.item_val = item_val
        self.item_name = item_name
        self.page = page
        self.category_idx = category_idx

    @discord.ui.button(label="Renommer", style=discord.ButtonStyle.primary, emoji="✏️")
    async def rename_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BackupEditRenameModal(
            self.cog, self.backup_id, self.backup_name, self.inter_or_ctx, 
            self.edit_type, self.item_val, self.item_name, self.page, self.category_idx
        ))

    @discord.ui.button(label="Supprimer", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = self.cog._get_json(self.backup_id)
        
        if self.edit_type == "roles":
            del data["roles"][int(self.item_val)]
        elif self.edit_type == "categories":
            del data["categories"][int(self.item_val)]
        elif self.edit_type == "channels":
            if self.item_val.startswith("orphan_"):
                idx = int(self.item_val.split("_")[1])
                del data["orphan_channels"][idx]
            else:
                c_idx, ch_idx = map(int, self.item_val.split("_"))
                del data["categories"][c_idx]["channels"][ch_idx]

        self.cog._save_json(self.backup_id, data)

        view = BackupEditSelectView(self.cog, self.backup_id, self.backup_name, self.inter_or_ctx, self.edit_type, self.page, self.category_idx)
        type_fr = {"roles": "Rôles", "categories": "Catégories", "channels": "Salons"}[self.edit_type]
        embed = self.cog.get_custom_embed(interaction, f"🛠️ Modification - {type_fr}", f"✅ L'élément **{self.item_name}** a été supprimé.\nSélectionnez un autre élément.")
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Retour", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def back_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = BackupEditSelectView(self.cog, self.backup_id, self.backup_name, self.inter_or_ctx, self.edit_type, self.page, self.category_idx)
        type_fr = {"roles": "Rôles", "categories": "Catégories", "channels": "Salons"}[self.edit_type]
        embed = self.cog.get_custom_embed(interaction, f"🛠️ Modification - {type_fr}", "Sélectionnez un élément à modifier.")
        await interaction.response.edit_message(embed=embed, view=view)


class BackupEditSelect(discord.ui.Select):
    """Menu déroulant pour choisir l'élément à éditer"""
    def __init__(self, cog, backup_id, edit_type, page, backup_name, inter_or_ctx, category_idx=None):
        self.cog = cog
        self.backup_id = backup_id
        self.edit_type = edit_type
        self.page = page
        self.backup_name = backup_name
        self.inter_or_ctx = inter_or_ctx
        self.category_idx = str(category_idx).replace('cat_', '') if category_idx else None

        data = self.cog._get_json(self.backup_id)
        options = []
        items_list = []

        if edit_type == "roles":
            for i, r in enumerate(data.get("roles", [])):
                items_list.append({"value": str(i), "label": r["name"][:100], "emoji": "🎭"})
        elif edit_type == "categories":
            for i, c in enumerate(data.get("categories", [])):
                items_list.append({"value": str(i), "label": c["name"][:100], "emoji": "📁"})
        elif edit_type == "channel_category":
            for i, c in enumerate(data.get("categories", [])):
                items_list.append({"value": f"cat_{i}", "label": c["name"][:100], "emoji": "📁"})
            if data.get("orphan_channels"):
                items_list.append({"value": "orphan", "label": "Sans catégorie", "emoji": "📝"})
        elif edit_type == "channels":
            if self.category_idx == "orphan":
                for i, ch in enumerate(data.get("orphan_channels", [])):
                    items_list.append({"value": f"orphan_{i}", "label": ch["name"][:100], "emoji": "💬"})
            else:
                c_idx = int(self.category_idx)
                cat_name = data["categories"][c_idx]["name"]
                for i, ch in enumerate(data["categories"][c_idx].get("channels", [])):
                    items_list.append({
                        "value": f"{c_idx}_{i}", 
                        "label": ch["name"][:100], 
                        "description": f"Cat: {cat_name[:50]}", 
                        "emoji": "💬"
                    })

        start = (page - 1) * 25
        page_items = items_list[start:start+25]

        for item in page_items:
            options.append(discord.SelectOption(
                label=item["label"], 
                description=item.get("description"), 
                value=item["value"], 
                emoji=item["emoji"]
            ))

        if not options:
            options.append(discord.SelectOption(label="Aucun élément", value="none"))

        super().__init__(placeholder="Sélectionnez un élément...", options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.defer()
            return
        
        val = self.values[0]

        if self.edit_type == "channel_category":
            view = BackupEditSelectView(self.cog, self.backup_id, self.backup_name, self.inter_or_ctx, "channels", 1, val)
            embed = self.cog.get_custom_embed(interaction, "🛠️ Modification - Salons", "Sélectionnez un salon à modifier dans cette catégorie.")
            await interaction.response.edit_message(embed=embed, view=view)
            return

        data = self.cog._get_json(self.backup_id)
        item_name = ""
        
        if self.edit_type == "roles": 
            item_name = data["roles"][int(val)]["name"]
        elif self.edit_type == "categories": 
            item_name = data["categories"][int(val)]["name"]
        elif self.edit_type == "channels":
            if val.startswith("orphan_"):
                idx = int(val.split("_")[1])
                item_name = data["orphan_channels"][idx]["name"]
            else:
                c_idx, ch_idx = map(int, val.split("_"))
                item_name = data["categories"][c_idx]["channels"][ch_idx]["name"]

        view = BackupEditActionView(self.cog, self.backup_id, self.backup_name, self.inter_or_ctx, self.edit_type, val, item_name, self.page, self.category_idx)
        embed = self.cog.get_custom_embed(interaction, "🛠️ Action", f"Que voulez-vous faire avec l'élément **{item_name}** ?")
        await interaction.response.edit_message(embed=embed, view=view)


class BackupEditSelectView(AuthorOnlyView):
    """Vue contenant le Select paginé pour l'édition"""
    def __init__(self, cog, backup_id, backup_name, inter_or_ctx, edit_type, page=1, category_idx=None):
        super().__init__(_resolve_author_id(inter_or_ctx), timeout=120)
        self.cog = cog
        self.backup_id = backup_id
        self.backup_name = backup_name
        self.inter_or_ctx = inter_or_ctx
        self.edit_type = edit_type
        self.page = page
        self.category_idx = category_idx

        data = self.cog._get_json(self.backup_id)
        total = 0
        if edit_type == "roles": 
            total = len(data.get("roles", []))
        elif edit_type == "categories": 
            total = len(data.get("categories", []))
        elif edit_type == "channel_category":
            total = len(data.get("categories", [])) + (1 if data.get("orphan_channels") else 0)
        elif edit_type == "channels":
            if str(self.category_idx).replace('cat_', '') == "orphan":
                total = len(data.get("orphan_channels", []))
            else:
                c_idx = int(str(self.category_idx).replace('cat_', ''))
                total = len(data["categories"][c_idx]["channels"])

        self.max_pages = max(1, (total - 1) // 25 + 1)

        self.add_item(BackupEditSelect(self.cog, self.backup_id, self.edit_type, self.page, self.backup_name, self.inter_or_ctx, self.category_idx))

        self.prev_btn = discord.ui.Button(label="⬅️", style=discord.ButtonStyle.secondary, disabled=(page <= 1), row=1)
        self.prev_btn.callback = self.prev_page
        self.next_btn = discord.ui.Button(label="➡️", style=discord.ButtonStyle.secondary, disabled=(page >= self.max_pages), row=1)
        self.next_btn.callback = self.next_page
        self.back_btn = discord.ui.Button(label="Retour", style=discord.ButtonStyle.danger, row=1)
        self.back_btn.callback = self.go_back

        self.add_item(self.prev_btn)
        self.add_item(self.back_btn)
        self.add_item(self.next_btn)

    async def prev_page(self, interaction: discord.Interaction):
        view = BackupEditSelectView(self.cog, self.backup_id, self.backup_name, self.inter_or_ctx, self.edit_type, self.page - 1, self.category_idx)
        await interaction.response.edit_message(view=view)

    async def next_page(self, interaction: discord.Interaction):
        view = BackupEditSelectView(self.cog, self.backup_id, self.backup_name, self.inter_or_ctx, self.edit_type, self.page + 1, self.category_idx)
        await interaction.response.edit_message(view=view)

    async def go_back(self, interaction: discord.Interaction):
        if self.edit_type == "channels" and self.category_idx is not None:
            view = BackupEditSelectView(self.cog, self.backup_id, self.backup_name, self.inter_or_ctx, "channel_category")
            embed = self.cog.get_custom_embed(interaction, "🛠️ Modification - Catégorie", "Sélectionnez la catégorie du salon à modifier.")
            await interaction.response.edit_message(embed=embed, view=view)
            return

        view = BackupEditMenuView(self.cog, self.backup_id, self.backup_name, self.inter_or_ctx)
        embed = self.cog.get_custom_embed(interaction, "🛠️ Modification de la Backup", f"Choisissez le type d'élément que vous souhaitez modifier dans la backup **{self.backup_name}**.")
        await interaction.response.edit_message(embed=embed, view=view)


class BackupEditMenuView(AuthorOnlyView):
    """Menu de base pour choisir quoi éditer (Rôles, Catégories, Salons)"""
    def __init__(self, cog, backup_id, backup_name, inter_or_ctx):
        super().__init__(_resolve_author_id(inter_or_ctx), timeout=120)
        self.cog = cog
        self.backup_id = backup_id
        self.backup_name = backup_name
        self.inter_or_ctx = inter_or_ctx

    @discord.ui.button(label="Rôles", style=discord.ButtonStyle.primary, emoji="🎭")
    async def edit_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._goto_select(interaction, "roles")

    @discord.ui.button(label="Catégories", style=discord.ButtonStyle.primary, emoji="📁")
    async def edit_cats(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._goto_select(interaction, "categories")

    @discord.ui.button(label="Salons", style=discord.ButtonStyle.primary, emoji="💬")
    async def edit_channels(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._goto_select(interaction, "channel_category")

    @discord.ui.button(label="Retour", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = BackupDetailView(self.cog, self.backup_id, self.backup_name, self.inter_or_ctx)
        embed = self.cog.get_custom_embed(interaction, "⚙️ Gestion de la Backup", f"Options pour la backup **{self.backup_name}** (`{self.backup_id}`)")
        await interaction.response.edit_message(embed=embed, view=view)

    async def _goto_select(self, interaction, edit_type):
        view = BackupEditSelectView(self.cog, self.backup_id, self.backup_name, self.inter_or_ctx, edit_type)
        type_fr = {"roles": "Rôles", "categories": "Catégories", "channel_category": "Catégories de salons"}[edit_type]
        embed = self.cog.get_custom_embed(interaction, f"🛠️ Modification - {type_fr}", "Sélectionnez un élément dans la liste ci-dessous.")
        await interaction.response.edit_message(embed=embed, view=view)

# ==============================================================================
# --------------------------- VIEWS DE GESTION ---------------------------------
# ==============================================================================

class ConfirmLoadView(AuthorOnlyView):
    """Vue pour confirmer le chargement d'une backup"""
    def __init__(self, cog, backup_id, backup_name, inter_or_ctx, clean_first):
        super().__init__(_resolve_author_id(inter_or_ctx), timeout=60)
        self.cog = cog
        self.backup_id = backup_id
        self.backup_name = backup_name
        self.inter_or_ctx = inter_or_ctx
        self.clean_first = clean_first

    @discord.ui.button(label="Confirmer", style=discord.ButtonStyle.danger, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed, _ = self.cog.generate_main_embed(self.inter_or_ctx)
        await interaction.response.edit_message(embed=embed, view=BackupView(self.cog, self.inter_or_ctx))
        asyncio.create_task(self.cog.logic_load_backup_process(interaction, self.backup_id, self.clean_first))

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = UseChoiceView(self.cog, self.backup_id, self.backup_name, self.inter_or_ctx)
        embed = self.cog.get_custom_embed(interaction, "⚙️ Configuration de la restauration", f"Choisissez le mode de restauration pour la backup **{self.backup_name}** (`{self.backup_id}`)")
        await interaction.response.edit_message(embed=embed, view=view)


class UseChoiceView(AuthorOnlyView):
    """Vue pour choisir le mode d'utilisation (Restaurer vs Ajouter)"""
    def __init__(self, cog, backup_id, backup_name, inter_or_ctx):
        super().__init__(_resolve_author_id(inter_or_ctx), timeout=120)
        self.cog = cog
        self.backup_id = backup_id
        self.backup_name = backup_name
        self.inter_or_ctx = inter_or_ctx

    @discord.ui.button(label="Restaurer", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def restore_clean(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = self.cog.get_custom_embed(interaction, "⚠️ Confirmation", f"Êtes-vous sûr de vouloir **restaurer** la backup **{self.backup_name}** ?\n\n**⚠️ Attention :** Cette action va **supprimer tous les salons et rôles actuels** avant de restaurer la backup.\n\nCette action est **irréversible**.")
        await interaction.response.edit_message(embed=embed, view=ConfirmLoadView(self.cog, self.backup_id, self.backup_name, self.inter_or_ctx, clean_first=True))

    @discord.ui.button(label="Ajouter", style=discord.ButtonStyle.success, emoji="➕")
    async def restore_add(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = self.cog.get_custom_embed(interaction, "⚠️ Confirmation", f"Êtes-vous sûr de vouloir **ajouter** la backup **{self.backup_name}** ?\n\n**ℹ️ Information :** Cette action va **conserver les salons et rôles actuels** et ajouter ceux de la backup.\n\nCette action est **partiellement réversible** (les nouveaux éléments devront être supprimés manuellement).")
        await interaction.response.edit_message(embed=embed, view=ConfirmLoadView(self.cog, self.backup_id, self.backup_name, self.inter_or_ctx, clean_first=False))

    @discord.ui.button(label="Retour", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = BackupDetailView(self.cog, self.backup_id, self.backup_name, self.inter_or_ctx)
        embed = self.cog.get_custom_embed(interaction, "⚙️ Gestion de la Backup", f"Options pour la backup **{self.backup_name}** (`{self.backup_id}`)")
        await interaction.response.edit_message(embed=embed, view=view)


class ConfirmDeleteView(AuthorOnlyView):
    """Vue pour confirmer la suppression d'une backup"""
    def __init__(self, cog, backup_id, inter_or_ctx):
        super().__init__(_resolve_author_id(inter_or_ctx), timeout=60)
        self.cog = cog
        self.backup_id = backup_id
        self.inter_or_ctx = inter_or_ctx

    @discord.ui.button(label="Confirmer", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        path = self.cog.folder / f"{self.backup_id}.json"
        if path.exists():
            os.remove(path)
        
        embed, _ = self.cog.generate_main_embed(self.inter_or_ctx)
        await interaction.response.edit_message(content=None, embed=embed, view=BackupView(self.cog, self.inter_or_ctx))

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        path = self.cog.folder / f"{self.backup_id}.json"
        if not path.exists():
            await interaction.response.send_message("❌ Cette backup n'existe plus.", ephemeral=True)
            return

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        view = BackupDetailView(self.cog, self.backup_id, data["info"]["name"], self.inter_or_ctx)
        embed = self.cog.get_custom_embed(interaction, "⚙️ Gestion de la Backup", f"Options pour la backup **{data['info']['name']}** (`{self.backup_id}`)")
        await interaction.response.edit_message(embed=embed, view=view)


class RenameBackupModal(discord.ui.Modal, title="Renommer la Backup"):
    """Modal pour renommer une backup"""
    def __init__(self, cog, backup_id, backup_name, inter_or_ctx):
        super().__init__()
        self.cog = cog
        self.backup_id = backup_id
        self.backup_name = backup_name
        self.inter_or_ctx = inter_or_ctx
        
        self.name_input = discord.ui.TextInput(
            label="Nouveau nom de la backup",
            placeholder="Entrez le nouveau nom...",
            default=backup_name,
            max_length=50,
            required=True
        )
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction):
        new_name = self.name_input.value.strip()
        
        if not new_name:
            await interaction.response.send_message("❌ Le nom ne peut pas être vide.", ephemeral=True)
            return
        
        try:
            data = self.cog._get_json(self.backup_id)
            if not data: return
            
            old_name = data["info"]["name"]
            data["info"]["name"] = new_name
            self.cog._save_json(self.backup_id, data)
            
            view = BackupDetailView(self.cog, self.backup_id, new_name, self.inter_or_ctx)
            embed = self.cog.get_custom_embed(
                interaction, 
                "✅ Backup renommée", 
                f"La backup **{old_name}** a été renommée en **{new_name}** (`{self.backup_id}`)"
            )
            await interaction.response.edit_message(embed=embed, view=view)
            
        except Exception as e:
            await interaction.response.send_message(f"❌ Erreur lors du renommage: {e}", ephemeral=True)


class BackupDetailView(AuthorOnlyView):
    """Vue affichée lorsqu'on sélectionne une backup spécifique"""
    def __init__(self, cog, backup_id, backup_name, inter_or_ctx):
        super().__init__(_resolve_author_id(inter_or_ctx), timeout=120)
        self.cog = cog
        self.backup_id = backup_id
        self.backup_name = backup_name
        self.inter_or_ctx = inter_or_ctx

    @discord.ui.button(label="Utiliser", style=discord.ButtonStyle.success, emoji="🚀")
    async def use_backup(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = UseChoiceView(self.cog, self.backup_id, self.backup_name, self.inter_or_ctx)
        embed = self.cog.get_custom_embed(
            interaction, 
            "⚙️ Configuration de la restauration", 
            f"Choisissez le mode de restauration pour la backup **{self.backup_name}** (`{self.backup_id}`)"
        )
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Modifier", style=discord.ButtonStyle.primary, emoji="🛠️")
    async def edit_content(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = BackupEditMenuView(self.cog, self.backup_id, self.backup_name, self.inter_or_ctx)
        embed = self.cog.get_custom_embed(
            interaction, 
            "🛠️ Modification de la Backup", 
            f"Choisissez le type d'élément que vous souhaitez modifier dans la backup **{self.backup_name}**."
        )
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Renommer", style=discord.ButtonStyle.primary, emoji="✏️")
    async def rename_backup(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RenameBackupModal(self.cog, self.backup_id, self.backup_name, self.inter_or_ctx))

    @discord.ui.button(label="Supprimer", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_request(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = self.cog.get_custom_embed(interaction, "⚠️ Confirmation", f"Êtes-vous sûr de vouloir supprimer la backup **{self.backup_name}** ?\nCette action est irréversible.")
        await interaction.response.edit_message(embed=embed, view=ConfirmDeleteView(self.cog, self.backup_id, self.inter_or_ctx))

    @discord.ui.button(label="Retour", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed, _ = self.cog.generate_main_embed(self.inter_or_ctx)
        await interaction.response.edit_message(embed=embed, view=BackupView(self.cog, self.inter_or_ctx))

# ==============================================================================
# --------------------------- MENU PRINCIPAL -----------------------------------
# ==============================================================================

class BackupSelectMenu(discord.ui.Select):
    def __init__(self, cog, inter_or_ctx, page=1, per_page=10):
        self.cog = cog
        self.inter_or_ctx = inter_or_ctx
        self.user = inter_or_ctx.user if isinstance(inter_or_ctx, discord.Interaction) else inter_or_ctx.author
        self.page = page
        self.per_page = per_page
        
        user_backups = self.cog.get_user_backups(self.user.id)
        start = (page - 1) * per_page
        page_backups = user_backups[start : start + per_page]
        
        options = []
        for i, info in enumerate(page_backups, start + 1):
            options.append(discord.SelectOption(
                label=f"{i}. {info['name'][:25]}", 
                description=f"ID: {info['id']} - {info['date']}", 
                emoji="📁",
                value=info['id']
            ))
        
        if not options:
            options.append(discord.SelectOption(label="Aucune backup", value="none"))
            
        super().__init__(placeholder="Sélectionnez une backup...", min_values=1, max_values=1, options=options)
    
    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.defer()
            return
        
        b_id = self.values[0]
        data = self.cog._get_json(b_id)
        if not data:
            await interaction.response.send_message("❌ Cette backup est introuvable.", ephemeral=True)
            return
        
        b_name = data["info"]["name"]
        view = BackupDetailView(self.cog, b_id, b_name, self.inter_or_ctx)
        
        embed = self.cog.get_custom_embed(
            interaction, 
            "⚙️ Gestion de la Backup", 
            f"Options pour la backup **{b_name}** (`{b_id}`)"
        )
        await interaction.response.edit_message(embed=embed, view=view)


class BackupView(AuthorOnlyView):
    def __init__(self, cog, inter_or_ctx, page=1):
        super().__init__(_resolve_author_id(inter_or_ctx), timeout=None)
        self.cog = cog
        self.inter_or_ctx = inter_or_ctx
        self.user = inter_or_ctx.user if isinstance(inter_or_ctx, discord.Interaction) else inter_or_ctx.author
        self.page = page
        
        embed, self.total_pages = self.cog.generate_main_embed(inter_or_ctx, page)
        
        self.add_item(BackupSelectMenu(cog, inter_or_ctx, page, 10))
        
        self.prev_btn = discord.ui.Button(label="⬅️", style=discord.ButtonStyle.secondary, custom_id="prev", row=1, disabled=(page <= 1))
        self.copy_btn = discord.ui.Button(label="Copier", style=discord.ButtonStyle.success, emoji="💾", row=1)
        self.next_btn = discord.ui.Button(label="➡️", style=discord.ButtonStyle.secondary, custom_id="next", row=1, disabled=(page >= self.total_pages))
        
        self.prev_btn.callback = self.prev_page
        self.next_btn.callback = self.next_page
        self.copy_btn.callback = self.copy_server
        
        self.add_item(self.prev_btn)
        self.add_item(self.copy_btn)
        self.add_item(self.next_btn)

    async def prev_page(self, interaction: discord.Interaction):
        self.page -= 1
        embed, _ = self.cog.generate_main_embed(self.inter_or_ctx, self.page)
        await interaction.response.edit_message(embed=embed, view=BackupView(self.cog, self.inter_or_ctx, self.page))

    async def next_page(self, interaction: discord.Interaction):
        self.page += 1
        embed, _ = self.cog.generate_main_embed(self.inter_or_ctx, self.page)
        await interaction.response.edit_message(embed=embed, view=BackupView(self.cog, self.inter_or_ctx, self.page))

    async def copy_server(self, interaction: discord.Interaction):
        await self.cog.logic_create_backup(interaction, self.user.id, self.inter_or_ctx)

# ==============================================================================
# --------------------------- COG PRINCIPAL ------------------------------------
# ==============================================================================

class BackupCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.folder = Path(__file__).parent / "backups"
        self.folder.mkdir(parents=True, exist_ok=True)

    def _get_json(self, backup_id: str):
        path = self.folder / f"{backup_id}.json"
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_json(self, backup_id: str, data: dict):
        path = self.folder / f"{backup_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def _normalize_channel_type(self, raw_type: str) -> str:
        """Normalise le type de salon sauvegarde vers une valeur simple."""
        if not raw_type:
            return "text"
        t = str(raw_type).lower().strip()
        if "." in t:
            t = t.split(".")[-1]
        aliases = {
            "news": "text",
            "category": "category",
            "stage_voice": "voice",
            "public_thread": "text",
            "private_thread": "text",
            "news_thread": "text",
        }
        return aliases.get(t, t)

    def get_now(self):
        return datetime.now(FRANCE_TZ).strftime("%d/%m/%y - %H:%M")

    def get_custom_embed(self, inter, title, description):
        user = inter.user if isinstance(inter, discord.Interaction) else inter.author
        guild = inter.guild if hasattr(inter, 'guild') else None
        
        if config_manager:
            embed = config_manager.get_formatted_embed(
                guild=guild, user=user, bot=self.bot,
                title=title, description=description,
                target_id=guild.id if guild else None
            )
        else:
            embed = discord.Embed(title=title, description=description, color=0x2b2d31)
        
        if self.bot.user.display_avatar:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            
        embed.remove_author()
        return embed

    def get_user_backups(self, user_id):
        user_id_str = str(user_id)
        backups = []
        for f in [file for file in os.listdir(self.folder) if file.endswith('.json')]:
            try:
                path = self.folder / f
                with open(path, "r", encoding="utf-8") as file:
                    data = json.load(file)
                    info = data.get("info", {})
                    if info.get("creator_id") == user_id_str:
                        info['timestamp'] = os.path.getmtime(path)
                        backups.append(info)
            except: 
                continue
        
        backups.sort(key=lambda x: x['timestamp'], reverse=True)
        return backups

    def generate_main_embed(self, inter_or_ctx, page=1, per_page=10):
        user = inter_or_ctx.user if isinstance(inter_or_ctx, discord.Interaction) else inter_or_ctx.author
        user_backups = self.get_user_backups(user.id)
        
        total_pages = max(1, (len(user_backups) - 1) // per_page + 1)
        page = max(1, min(page, total_pages))
        start = (page - 1) * per_page
        
        page_backups = user_backups[start : start + per_page]
        
        if not user_backups:
            description = ">>> 📉 **Aucune sauvegarde trouvée.**\nCliquez sur `💾 Copier` pour commencer."
        else:
            list_txt = []
            for i, info in enumerate(page_backups, start + 1):
                list_txt.append(f"**{i}.** 🛡️ **{info['name']}** `{info['id']}` *{info['date']}*")
            description = "\n\n".join(list_txt) + f"\n\n*Page {page}/{total_pages} — Total : {len(user_backups)}*"
        
        return self.get_custom_embed(inter_or_ctx, "📂 Gestionnaire de Backups", description), total_pages

    # --- ACTIONS ---
    async def logic_create_backup(self, interaction: discord.Interaction, author_id: int, inter_or_ctx):
        loading = self.get_custom_embed(interaction, "🔄 Analyse...", "Scan du serveur en cours...")
        await interaction.response.edit_message(embed=loading, view=None)
        
        guild = interaction.guild
        try:
            b_id = str(uuid.uuid4())[:8]
            data = {
                "info": {"name": guild.name, "icon_url": str(guild.icon.url) if guild.icon else None, "date": self.get_now(), "id": b_id, "creator_id": str(author_id)},
                "roles": [{"name": r.name, "color": r.color.value, "permissions": r.permissions.value, "hoist": r.hoist, "mentionable": r.mentionable} 
                          for r in sorted(guild.roles, key=lambda r: r.position) if not r.is_default() and not r.managed],
                "categories": [],
                "orphan_channels": []
            }

            # Sauvegarde des catégories et de leurs salons
            for cat in sorted(guild.categories, key=lambda c: c.position):
                channels = []
                for ch in sorted(cat.channels, key=lambda c: c.position):
                    ch_type = self._normalize_channel_type(str(ch.type))
                    channels.append({
                        "name": ch.name, "type": ch_type, "topic": getattr(ch, 'topic', None),
                        "overwrites": [{"id": t.id, "name": t.name, "is_role": isinstance(t, discord.Role), "allow": ov.pair()[0].value, "deny": ov.pair()[1].value} for t, ov in ch.overwrites.items()],
                        "nsfw": getattr(ch, 'nsfw', False), "user_limit": getattr(ch, 'user_limit', 0)
                    })
                data["categories"].append({
                    "name": cat.name, 
                    "overwrites": [{"id": t.id, "name": t.name, "is_role": isinstance(t, discord.Role), "allow": ov.pair()[0].value, "deny": ov.pair()[1].value} for t, ov in cat.overwrites.items()],
                    "channels": channels
                })
            
            # Sauvegarde des salons "Sans catégorie"
            for ch in sorted([c for c in guild.channels if c.category is None and not isinstance(c, discord.CategoryChannel)], key=lambda c: c.position):
                ch_type = self._normalize_channel_type(str(ch.type))
                data["orphan_channels"].append({
                    "name": ch.name, "type": ch_type, "topic": getattr(ch, 'topic', None),
                    "overwrites": [{"id": t.id, "name": t.name, "is_role": isinstance(t, discord.Role), "allow": ov.pair()[0].value, "deny": ov.pair()[1].value} for t, ov in ch.overwrites.items()],
                    "nsfw": getattr(ch, 'nsfw', False), "user_limit": getattr(ch, 'user_limit', 0)
                })

            self._save_json(b_id, data)

            embed, _ = self.generate_main_embed(inter_or_ctx)
            await interaction.message.edit(embed=embed, view=BackupView(self, inter_or_ctx))
        except Exception as e:
            await interaction.message.edit(content=f"❌ Erreur: {e}")

    async def logic_load_backup_process(self, interaction: discord.Interaction, backup_id: str, clean_first: bool):
        log_ch = None
        try:
            data = self._get_json(backup_id)
            if not data: return
            guild = interaction.guild
            
            log_ch = await guild.create_text_channel(name=f"🤖│{self.bot.user.name}")
            await log_ch.send(f"🚀 Restauration lancée par {interaction.user.mention}")
            
            bot_member = guild.me
            await log_ch.send(f"🔍 Vérification des permissions du bot...")
            
            if not bot_member.guild_permissions.manage_roles:
                await log_ch.send("❌ Le bot n'a pas la permission 'Gérer les rôles'!")
                return
            if not bot_member.guild_permissions.manage_channels:
                await log_ch.send("❌ Le bot n'a pas la permission 'Gérer les salons'!")
                return
            
            if clean_first:
                channels = [c for c in guild.channels if c.id != log_ch.id]
                for c in channels:
                    try: 
                        await c.delete(reason="Backup restoration")
                        await asyncio.sleep(0.2)
                    except: pass
                
                roles = [r for r in guild.roles if not r.managed and not r.is_default() and r < guild.me.top_role]
                for r in roles:
                    try: 
                        await r.delete(reason="Backup restoration")
                        await asyncio.sleep(0.2)
                    except: pass

            role_map = {}
            await log_ch.send("🔄 Création des rôles (Les rôles qui bloquent seront créés sans permissions dangereuses)...")
            roles_data = data.get("roles", [])
            
            for i, r_data in enumerate(reversed(roles_data)):
                try:
                    try:
                        role = await guild.create_role(
                            name=r_data["name"], 
                            color=discord.Color(r_data["color"]), 
                            permissions=discord.Permissions(r_data["permissions"]), 
                            hoist=r_data.get("hoist", False),
                            mentionable=r_data.get("mentionable", False),
                            reason="Backup restoration"
                        )
                    except discord.Forbidden:
                        # Si le bot n'a pas la permission de donner ces droits, on l'esquive
                        role = await guild.create_role(
                            name=r_data["name"], 
                            color=discord.Color(r_data["color"]), 
                            hoist=r_data.get("hoist", False),
                            mentionable=r_data.get("mentionable", False),
                            reason="Backup restoration (Perms réduites)"
                        )
                        await log_ch.send(f"⚠️ Rôle `{r_data['name']}` créé sans permissions (droits du bot insuffisants).")
                    
                    role_map[r_data["name"]] = role
                    await asyncio.sleep(0.3)
                except Exception as e:
                    await log_ch.send(f"❌ Erreur en créant le rôle `{r_data['name']}`: {e}")
                    continue

            await log_ch.send("🔄 Création des catégories et salons...")
            
            for c_data in data.get("categories", []):
                try:
                    cat = await guild.create_category(name=c_data["name"], reason="Backup restoration")
                    await asyncio.sleep(0.2)
                    
                    for ch in c_data.get("channels", []):
                        try:
                            ch_type = self._normalize_channel_type(ch.get("type", "text"))
                            if ch_type in ("text", "forum"):
                                await cat.create_text_channel(
                                    name=ch["name"],
                                    topic=ch.get("topic", "") or "",
                                    nsfw=ch.get("nsfw", False),
                                    reason="Backup"
                                )
                            elif ch_type == "voice":
                                await cat.create_voice_channel(
                                    name=ch["name"],
                                    user_limit=ch.get("user_limit", 0),
                                    reason="Backup"
                                )
                            else:
                                # Fallback securise: creer en textuel si type non gere
                                await cat.create_text_channel(name=ch["name"], topic=ch.get("topic", "") or "", reason="Backup")
                            await asyncio.sleep(0.1)
                        except Exception as e:
                            await log_ch.send(f"❌ Erreur salon `{ch['name']}`: {e}")
                except Exception as e:
                    await log_ch.send(f"❌ Erreur catégorie `{c_data['name']}`: {e}")
                    
            await log_ch.send("🔄 Création des salons sans catégorie...")
            for ch in data.get("orphan_channels", []):
                try:
                    ch_type = self._normalize_channel_type(ch.get("type", "text"))
                    if ch_type in ("text", "forum"):
                        await guild.create_text_channel(
                            name=ch["name"],
                            topic=ch.get("topic", "") or "",
                            nsfw=ch.get("nsfw", False),
                            reason="Backup"
                        )
                    elif ch_type == "voice":
                        await guild.create_voice_channel(
                            name=ch["name"],
                            user_limit=ch.get("user_limit", 0),
                            reason="Backup"
                        )
                    else:
                        await guild.create_text_channel(name=ch["name"], topic=ch.get("topic", "") or "", reason="Backup")
                    await asyncio.sleep(0.1)
                except Exception as e:
                    await log_ch.send(f"❌ Erreur salon orphelin `{ch['name']}`: {e}")
            
            await log_ch.send("✅ Restauration terminée avec succès!")
            
        except Exception as e:
            if log_ch:
                try: await log_ch.send(f"❌ Erreur critique: {e}")
                except: pass

    @commands.hybrid_command(name="backup", description="Ouvre le gestionnaire de backups (creer, restaurer, modifier, supprimer).")
    @commands.has_permissions(administrator=True)
    async def backup_cmd(self, ctx):
        embed, _ = self.generate_main_embed(ctx)
        await ctx.send(embed=embed, view=BackupView(self, ctx))

async def setup(bot):
    await bot.add_cog(BackupCog(bot))