import discord
from discord.ext import commands
import json
import os
import sys
import asyncio
import aiohttp
import re
from typing import Optional, Dict, Any, List
from datetime import datetime
import random
import string

# ==============================================================================
# --------------------------- CONFIGURATION & CHEMINS ---------------------------
# ==============================================================================
DEBUG_MODE = True

# Variables globales pour éviter les répétitions de chemins
BASE_DIR = os.path.dirname(__file__)
DATA_DEV_DIR = os.path.normpath(os.path.join(BASE_DIR, '..', '..', 'data', 'dev'))
FAMILLE_DIR = os.path.join(DATA_DEV_DIR, 'famille')

# Importation Config Manager
sys.path.append(os.path.join(BASE_DIR, '..', '..', '..', 'developpeur', 'commands', 'embed_type'))
try:
    from cogs.developpeur.commands.embed_type.utils import config_manager
    HAS_CONFIG_MANAGER = True
    HAS_CUSTOM_EMBED = True
except ImportError:
    config_manager = None
    HAS_CONFIG_MANAGER = False
    HAS_CUSTOM_EMBED = False


# ==============================================================================
# -------------------------------- MANAGERS ------------------------------------
# ==============================================================================

class FamilleManager:
    def __init__(self, bot):
        self.bot = bot
        self.famille_dir = FAMILLE_DIR
        
    def get_famille_dir(self) -> str:
        os.makedirs(self.famille_dir, exist_ok=True)
        return self.famille_dir
    
    def get_all_familles(self) -> List[str]:
        famille_dir = self.get_famille_dir()
        if not os.path.exists(famille_dir):
            return []
        
        familles = []
        for item in os.listdir(famille_dir):
            item_path = os.path.join(famille_dir, item)
            if os.path.isdir(item_path):
                familles.append(item)
        
        return sorted(familles, key=lambda x: x.lower())
    
    def create_famille_folder(self, nom_famille: str) -> bool:
        famille_dir = self.get_famille_dir()
        famille_path = os.path.join(famille_dir, nom_famille)
        if os.path.exists(famille_path):
            return False
        os.makedirs(famille_path, exist_ok=True)
        return True
    
    def get_famille_image(self, nom_famille: str) -> Optional[str]:
        config_path = os.path.join(self.famille_dir, nom_famille, 'config.json')
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('image_file')
            except: pass
        return None
    
    def get_famille_description(self, nom_famille: str) -> Optional[str]:
        config_path = os.path.join(self.famille_dir, nom_famille, 'config.json')
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get('description')
            except: pass
        return None
    
    def get_famille_embed(self, interaction, page: int = 1) -> discord.Embed:
        cog = self.bot.get_cog("Dev")
        familles = self.get_all_familles()
        
        items_per_page = 20
        total_pages = max(1, (len(familles) + items_per_page - 1) // items_per_page)
        page_start_idx = (page - 1) * items_per_page
        end_idx = page_start_idx + items_per_page
        page_familles = familles[page_start_idx:end_idx]
        
        embed = cog.get_custom_embed(
            interaction,
            "👨‍👩‍👧‍👦 Gestion des Familles",
            "" 
        )
        
        if page_familles:
            desc_lines = [f"**{page_start_idx + i + 1}.** {famille}" for i, famille in enumerate(page_familles)]
            embed.description = "\n".join(desc_lines)
        else:
            embed.description = "*Aucune famille n'existe encore*"
        
        embed.set_footer(text=f"Page {page}/{total_pages} - {len(familles)} {('famille' if len(familles) == 1 else 'familles')}")
        return embed

class PersonnageManager:
    def __init__(self, bot):
        self.bot = bot
    
    def get_famille_list(self, guild_id: int) -> List[str]:
        if os.path.exists(FAMILLE_DIR):
            return [d for d in os.listdir(FAMILLE_DIR) if os.path.isdir(os.path.join(FAMILLE_DIR, d))]
        return []
    
    def load_famille_personnages(self, guild_id: int, famille_name: str) -> Dict[str, Any]:
        path = self.get_famille_personnages_path(guild_id, famille_name)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"personnages": []}
    
    def save_famille_personnages(self, guild_id: int, famille_name: str, data: Dict[str, Any]) -> None:
        path = self.get_famille_personnages_path(guild_id, famille_name)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
    
    def get_famille_personnages_path(self, guild_id: int, famille_name: str) -> str:
        return os.path.join(FAMILLE_DIR, famille_name, 'personnages.json')
    
    def count_personnages_in_famille(self, famille_name: str) -> int:
        """Compte le nombre de personnages dans une famille"""
        personnages_data = self.load_famille_personnages(None, famille_name)
        personnages = personnages_data.get("personnages", [])
        return len(personnages)
    
    def get_personnage_embed(self, interaction, page: int = 1) -> discord.Embed:
        try:
            cog = self.bot.get_cog("Dev")
            familles = self.get_famille_list(interaction.guild.id)
            
            items_per_page = 20
            total_pages = max(1, (len(familles) + items_per_page - 1) // items_per_page)
            page_start_idx = (page - 1) * items_per_page
            end_idx = page_start_idx + items_per_page
            page_familles = familles[page_start_idx:end_idx]
            
            embed = cog.get_custom_embed(
                interaction,
                "🎭 Gestion des Personnages",
                "Bienvenue dans le panneau de gestion des personnages. Choisissez une famille ci-dessous."
            )
            
            if page_familles:
                desc_lines = [f"**{page_start_idx + i + 1}.** {famille} ({self.count_personnages_in_famille(famille)})" for i, famille in enumerate(page_familles)]
                embed.description = "\n".join(desc_lines)
            else:
                embed.description = "*Aucune famille n'existe encore*"
            
            embed.set_footer(text=f"Page {page}/{total_pages} - {len(familles)} {('famille' if len(familles) == 1 else 'familles')}")
            return embed
            
        except Exception as e:
            return discord.Embed(title="❌ Erreur", description=f"Erreur: {str(e)}", color=0xff0000)

    def _get_famille_description(self, famille_name: str) -> Optional[str]:
        config_path = os.path.join(FAMILLE_DIR, famille_name, 'config.json')
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f).get('description')
            except: pass
        return None

    def _get_famille_image(self, famille_name: str) -> Optional[str]:
        config_path = os.path.join(FAMILLE_DIR, famille_name, 'config.json')
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f).get('image_file')
            except: pass
        return None
    
    def _get_famille_image_path(self, famille_name: str, image_filename: str) -> str:
        return os.path.join(FAMILLE_DIR, famille_name, image_filename)

    async def show_famille_personnages(self, interaction: discord.Interaction, famille_name: str, page: int = 1):
        try:
            personnages_data = self.load_famille_personnages(interaction.guild.id, famille_name)
            personnages = personnages_data.get("personnages", [])
            
            items_per_page = 20
            total_pages = max(1, (len(personnages) + items_per_page - 1) // items_per_page)
            page_start_idx = (page - 1) * items_per_page
            end_idx = page_start_idx + items_per_page
            page_personnages = personnages[page_start_idx:end_idx]
            
            theme_color = 0x2b2d31
            if HAS_CONFIG_MANAGER and config_manager:
                vals = config_manager.get_resolved_values(interaction.guild.id if interaction.guild else None)
                theme_color = vals['color']
            
            embed = discord.Embed(
                title="Profil de famille",
                description=f"Famille sélectionnée : **{famille_name}** | **{len(personnages)} personnage{'s' if len(personnages) != 1 else ''}**",
                color=theme_color
            )
            
            famille_description = self._get_famille_description(famille_name)
            if famille_description:
                embed.add_field(name="📝 Description", value=famille_description, inline=False)
            
            if page_personnages:
                persos_text = []
                for i, perso in enumerate(page_personnages):
                    perso_info = f"**{page_start_idx + i + 1}.** {perso.get('nom', 'Sans nom')}"
                    if perso.get('image'): perso_info += " 🖼️"
                    persos_text.append(perso_info)
                
                persos_text = "\n".join(persos_text)
                if len(personnages) > items_per_page:
                    persos_text += f"\n... et {len(personnages) - end_idx} autres"
                
                embed.add_field(name=f"📜 Personnages de la famille (Page {page}/{total_pages})", value=persos_text, inline=False)
            else:
                embed.add_field(name="📜 Personnages de la famille", value="Aucun personnage dans cette famille.", inline=False)
            
            file = None
            try:
                img_name = self._get_famille_image(famille_name)
                if img_name:
                    image_path = self._get_famille_image_path(famille_name, img_name)
                    if os.path.exists(image_path):
                        file = discord.File(image_path, filename=img_name)
                        embed.set_thumbnail(url=f"attachment://{img_name}")
            except: pass
            
            embed.set_footer(text=f"Page {page}/{total_pages} • Utilisez les boutons pour naviguer")
            view = FamillePersonnageView(self, famille_name, page, personnages)
            
            if file: await interaction.followup.send(embed=embed, view=view, file=file)
            else: await interaction.followup.send(embed=embed, view=view)
            
        except Exception as e:
            try: await interaction.followup.send(f"❌ Erreur: {str(e)}", ephemeral=True)
            except: pass


# ==============================================================================
# ----------------------------- VUES & MODALS (FAMILLES) -----------------------
# ==============================================================================

class FamilleView(discord.ui.View):
    def __init__(self, manager: FamilleManager, current_page: int = 1):
        super().__init__(timeout=300)
        self.manager = manager
        self.current_page = current_page
        self.familles = manager.get_all_familles()
        self.items_per_page = 20
        self.total_pages = max(1, (len(self.familles) + self.items_per_page - 1) // self.items_per_page)
        self._build_view()
    
    def _build_view(self):
        self.clear_items()
        back_btn = discord.ui.Button(label="Retour", style=discord.ButtonStyle.secondary, emoji="🔙", row=0)
        back_btn.callback = self.back_to_main
        self.add_item(back_btn)
        
        add_btn = discord.ui.Button(label="Ajouter", style=discord.ButtonStyle.success, emoji="➕", row=0)
        add_btn.callback = self.create_famille
        self.add_item(add_btn)
        
        if self.current_page > 1:
            prev_btn = discord.ui.Button(label="⬅️", style=discord.ButtonStyle.secondary, row=0)
            prev_btn.callback = self.previous_page
            self.add_item(prev_btn)
        
        if self.current_page < self.total_pages:
            next_btn = discord.ui.Button(label="➡️", style=discord.ButtonStyle.secondary, row=0)
            next_btn.callback = self.next_page
            self.add_item(next_btn)
            
        start_idx = (self.current_page - 1) * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, len(self.familles))
        page_familles = self.familles[start_idx:end_idx]
        
        if page_familles:
            options = [discord.SelectOption(label=f"{start_idx + i + 1}. {f}", value=f) for i, f in enumerate(page_familles)]
            select = discord.ui.Select(placeholder="Choisissez une famille...", options=options, row=1)
            select.callback = self.select_famille
            self.add_item(select)

    async def select_famille_with_name(self, interaction: discord.Interaction, nom_famille: str):
        selected_famille = nom_famille
        famille_path = os.path.join(self.manager.famille_dir, selected_famille)
        if not os.path.exists(famille_path):
            await interaction.followup.send(f"❌ La famille **{selected_famille}** n'existe pas.", ephemeral=True)
            return
        
        theme_color = 0x2b2d31
        if HAS_CONFIG_MANAGER and config_manager:
            vals = config_manager.get_resolved_values(interaction.guild.id if interaction.guild else None)
            theme_color = vals['color']
        
        embed = discord.Embed(title=f"Profil de famille", description=f"Famille sélectionnée : **{selected_famille}**", color=theme_color)
        description = self.manager.get_famille_description(selected_famille)
        if description: embed.add_field(name="📝 Description", value=description, inline=False)
        
        view = discord.ui.View(timeout=300)
        back_btn = discord.ui.Button(label="Retour", style=discord.ButtonStyle.secondary, emoji="⬅️", row=0)
        back_btn.callback = self.back_to_list
        view.add_item(back_btn)
        
        delete_btn = discord.ui.Button(label="Supprimer", style=discord.ButtonStyle.danger, emoji="🗑", row=0)
        delete_btn.callback = lambda inter: self.delete_famille(inter, selected_famille)
        view.add_item(delete_btn)
        
        modify_btn = discord.ui.Button(label="Renommer", style=discord.ButtonStyle.primary, emoji="✏", row=1)
        modify_btn.callback = lambda inter: self.modify_famille_name(inter, selected_famille)
        view.add_item(modify_btn)
        
        desc_btn = discord.ui.Button(label="Description", style=discord.ButtonStyle.secondary, emoji="📝", row=1)
        desc_btn.callback = lambda inter: self.manage_famille_description(inter, selected_famille)
        view.add_item(desc_btn)
        
        image_btn = discord.ui.Button(label="Image", style=discord.ButtonStyle.success, emoji="🖼", row=1)
        image_btn.callback = lambda inter: self.manage_famille_image(inter, selected_famille)
        view.add_item(image_btn)
        
        kwargs = {'embed': embed, 'view': view}
        try:
            image_file = self.manager.get_famille_image(selected_famille)
            if image_file:
                file_path = os.path.join(self.manager.famille_dir, selected_famille, image_file)
                if os.path.exists(file_path):
                    file = discord.File(file_path, filename=image_file)
                    embed.set_thumbnail(url=f"attachment://{image_file}")
                    kwargs['attachments'] = [file]
        except: kwargs['attachments'] = []
        
        await interaction.message.edit(**kwargs)

    async def create_famille(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CreateFamilleModal(self.manager, self))
    
    async def select_famille(self, interaction: discord.Interaction):
        await interaction.response.defer()
        selected_famille = interaction.data['values'][0]
        await self.select_famille_with_name(interaction, selected_famille)
    
    async def manage_famille_image(self, interaction: discord.Interaction, nom_famille: str):
        await interaction.response.defer()
        await interaction.followup.send(f"📸 Envoyez une **image/GIF/lien** dans le chat pour la famille **{nom_famille}** (60s).", ephemeral=True)

        def check(m): return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id
        try: msg = await self.manager.bot.wait_for('message', check=check, timeout=60.0)
        except asyncio.TimeoutError:
            return await interaction.followup.send("⏳ Temps écoulé.", ephemeral=True)

        image_url, is_attachment = None, False
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"image_{timestamp}.png"

        if msg.attachments:
            image_url = msg.attachments[0].url
            is_attachment = True
        elif "http" in msg.content:
            urls = re.findall(r'(https?://[^\s]+)', msg.content)
            if urls: image_url = urls[0]

        if not image_url: return await interaction.followup.send("❌ Aucun fichier/lien valide.", ephemeral=True)

        famille_path = os.path.join(self.manager.famille_dir, nom_famille)
        file_path = os.path.join(famille_path, filename)
        os.makedirs(famille_path, exist_ok=True)

        try:
            if is_attachment: await msg.attachments[0].save(file_path)
            else:
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_url) as resp:
                        if resp.status == 200:
                            with open(file_path, 'wb') as f: f.write(await resp.read())
                        else: return await interaction.followup.send("❌ Impossible de télécharger.", ephemeral=True)
        except Exception as e: return await interaction.followup.send(f"❌ Erreur: {str(e)}", ephemeral=True)

        config_path = os.path.join(famille_path, 'config.json')
        config_data = {"nom": nom_famille}
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f: config_data = json.load(f)

        old_img = config_data.get('image_file')
        if old_img and old_img != filename:
            old_path = os.path.join(famille_path, old_img)
            if os.path.exists(old_path): os.remove(old_path)

        config_data['image_file'] = filename
        with open(config_path, 'w', encoding='utf-8') as f: json.dump(config_data, f, indent=4, ensure_ascii=False)

        try: await msg.delete()
        except: pass

        await interaction.followup.send(f"✅ Image mise à jour pour **{nom_famille}** !", ephemeral=True)
        
        # Rafraichir la vue
        interaction.message = await interaction.channel.fetch_message(interaction.message.id)
        await self.select_famille_with_name(interaction, nom_famille)
    
    async def modify_famille_name(self, interaction: discord.Interaction, nom_famille: str):
        await interaction.response.send_modal(ModifyFamilleModal(self.manager, self, nom_famille))
    
    async def manage_famille_description(self, interaction: discord.Interaction, nom_famille: str):
        await interaction.response.send_modal(DescriptionFamilleModal(self.manager, self, nom_famille))
    
    async def delete_famille(self, interaction: discord.Interaction, nom_famille: str):
        view = discord.ui.View()
        
        async def confirm_callback(inter: discord.Interaction):
            import shutil
            famille_path = os.path.join(self.manager.famille_dir, nom_famille)
            try:
                if os.path.exists(famille_path):
                    shutil.rmtree(famille_path)
                    await inter.response.edit_message(content=f"✅ Famille **{nom_famille}** supprimée.", view=None, attachments=[])
                    await asyncio.sleep(1)
                    self.familles = self.manager.get_all_familles()
                    self._build_view()
                    embed = self.manager.get_famille_embed(inter, self.current_page)
                    await inter.followup.send(embed=embed, view=self)
            except Exception as e:
                await inter.response.edit_message(content=f"❌ Erreur: {str(e)}", view=None)
        
        async def cancel_callback(inter: discord.Interaction):
            await inter.response.edit_message(content="❌ Annulé.", view=None)
        
        confirm_btn = discord.ui.Button(label="Confirmer", style=discord.ButtonStyle.danger)
        confirm_btn.callback = confirm_callback
        view.add_item(confirm_btn)
        
        cancel_btn = discord.ui.Button(label="Annuler", style=discord.ButtonStyle.secondary)
        cancel_btn.callback = cancel_callback
        view.add_item(cancel_btn)
        
        await interaction.response.send_message(f"⚠️ Sûr de vouloir supprimer **{nom_famille}** ?", view=view, ephemeral=True)
    
    async def previous_page(self, interaction: discord.Interaction):
        self.current_page -= 1
        self._build_view()
        await interaction.response.edit_message(embed=self.manager.get_famille_embed(interaction, self.current_page), view=self, attachments=[])
    
    async def next_page(self, interaction: discord.Interaction):
        self.current_page += 1
        self._build_view()
        await interaction.response.edit_message(embed=self.manager.get_famille_embed(interaction, self.current_page), view=self, attachments=[])
    
    async def back_to_list(self, interaction: discord.Interaction):
        self.familles = self.manager.get_all_familles()
        self._build_view()
        await interaction.response.edit_message(embed=self.manager.get_famille_embed(interaction, self.current_page), view=self, attachments=[])
    
    async def back_to_main(self, interaction: discord.Interaction):
        cog = self.manager.bot.get_cog("Dev")
        embed = cog.get_custom_embed(interaction, f"🔧 Menu Dev", f"Menu de gestion de l'économie.")
        embed.add_field(name="🎯 Options", value="**👨‍👩‍👧‍👦 Familles**\n**🎭 Personnages**", inline=False)
        await interaction.response.edit_message(embed=embed, view=DevView(cog), attachments=[])

class CreateFamilleModal(discord.ui.Modal, title="Créer une famille"):
    nom_famille = discord.ui.TextInput(label="Nom de la famille", min_length=2, max_length=50)
    
    def __init__(self, manager: FamilleManager, view: FamilleView):
        super().__init__()
        self.manager = manager
        self.view = view
    
    async def on_submit(self, interaction: discord.Interaction):
        if not self.manager.create_famille_folder(self.nom_famille.value):
            return await interaction.response.send_message(f"❌ La famille **{self.nom_famille.value}** existe déjà.", ephemeral=True)
        await interaction.response.send_message(f"✅ Famille **{self.nom_famille.value}** créée !", ephemeral=True)
        
        interaction.message = await interaction.channel.fetch_message(interaction.message.id)
        await self.view.select_famille_with_name(interaction, self.nom_famille.value)

class ModifyFamilleModal(discord.ui.Modal, title="Renommer la famille"):
    nouveau_nom = discord.ui.TextInput(label="Nouveau nom", min_length=2, max_length=50)
    
    def __init__(self, manager: FamilleManager, view: FamilleView, ancien_nom: str):
        super().__init__()
        self.manager = manager
        self.view = view
        self.ancien_nom = ancien_nom
        self.nouveau_nom.default = ancien_nom
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        import shutil
        ancien_chemin = os.path.join(self.manager.famille_dir, self.ancien_nom)
        nouveau_chemin = os.path.join(self.manager.famille_dir, self.nouveau_nom.value)
        
        if os.path.exists(nouveau_chemin):
            return await interaction.followup.send(f"❌ Le nom **{self.nouveau_nom.value}** est déjà pris.", ephemeral=True)
        
        try:
            shutil.move(ancien_chemin, nouveau_chemin)
            config_path = os.path.join(nouveau_chemin, 'config.json')
            config_data = {"nom": self.nouveau_nom.value}
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f: config_data = json.load(f)
            config_data['nom'] = self.nouveau_nom.value
            with open(config_path, 'w', encoding='utf-8') as f: json.dump(config_data, f, indent=4, ensure_ascii=False)
            
            await interaction.followup.send(f"✅ Renommé en **{self.nouveau_nom.value}** !", ephemeral=True)
            
            # Rafraichir le profil
            interaction.message = await interaction.channel.fetch_message(interaction.message.id)
            await self.view.select_famille_with_name(interaction, self.nouveau_nom.value)
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur: {str(e)}", ephemeral=True)

class DescriptionFamilleModal(discord.ui.Modal, title="Modifier description"):
    description = discord.ui.TextInput(label="Description", style=discord.TextStyle.paragraph, max_length=1000, required=False)
    
    def __init__(self, manager: FamilleManager, view: FamilleView, nom_famille: str):
        super().__init__()
        self.manager = manager
        self.view = view
        self.nom_famille = nom_famille
        existing = manager.get_famille_description(nom_famille)
        if existing: self.description.default = existing
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        config_path = os.path.join(self.manager.famille_dir, self.nom_famille, 'config.json')
        config_data = {"nom": self.nom_famille}
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f: config_data = json.load(f)
        
        if self.description.value.strip(): config_data['description'] = self.description.value.strip()
        elif 'description' in config_data: del config_data['description']
        
        with open(config_path, 'w', encoding='utf-8') as f: json.dump(config_data, f, indent=4, ensure_ascii=False)
        await interaction.followup.send(f"✅ Description mise à jour !", ephemeral=True)
        
        interaction.message = await interaction.channel.fetch_message(interaction.message.id)
        await self.view.select_famille_with_name(interaction, self.nom_famille)


# ==============================================================================
# ----------------------------- VUES & MODALS (PERSONNAGES) --------------------
# ==============================================================================

class PersonnageView(discord.ui.View):
    def __init__(self, manager: PersonnageManager, guild_id: int = None, current_page: int = 1):
        super().__init__(timeout=300)
        self.manager = manager
        self.guild_id = guild_id
        self.current_page = current_page
        self.familles = manager.get_famille_list(guild_id) if guild_id else []
        self.items_per_page = 20
        self.total_pages = max(1, (len(self.familles) + self.items_per_page - 1) // self.items_per_page)
        self._build_view()
    
    def _build_view(self):
        self.clear_items()
        back_btn = discord.ui.Button(label="Retour", style=discord.ButtonStyle.secondary, emoji="🔙", row=0)
        back_btn.callback = self.back_to_dev_menu
        self.add_item(back_btn)
        
        if self.current_page > 1:
            prev_btn = discord.ui.Button(label="⬅️", style=discord.ButtonStyle.secondary, row=0)
            prev_btn.callback = self.previous_page
            self.add_item(prev_btn)
        
        if self.current_page < self.total_pages:
            next_btn = discord.ui.Button(label="➡️", style=discord.ButtonStyle.secondary, row=0)
            next_btn.callback = self.next_page
            self.add_item(next_btn)
            
        start_idx = (self.current_page - 1) * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, len(self.familles))
        page_familles = self.familles[start_idx:end_idx]
        
        if page_familles:
            options = [discord.SelectOption(label=f"{start_idx + i + 1}. {f}", value=f) for i, f in enumerate(page_familles)]
            select = discord.ui.Select(placeholder="Choisissez une famille...", options=options, row=1)
            select.callback = self.select_famille
            self.add_item(select)
    
    async def select_famille(self, interaction: discord.Interaction):
        await interaction.response.defer()
        selected_famille = interaction.data['values'][0]
        await self.manager.show_famille_personnages(interaction, selected_famille)
    
    async def previous_page(self, interaction: discord.Interaction):
        self.current_page -= 1
        self._build_view()
        await interaction.response.edit_message(embed=self.manager.get_personnage_embed(interaction, self.current_page), view=self, attachments=[])
    
    async def next_page(self, interaction: discord.Interaction):
        self.current_page += 1
        self._build_view()
        await interaction.response.edit_message(embed=self.manager.get_personnage_embed(interaction, self.current_page), view=self, attachments=[])
    
    async def back_to_dev_menu(self, interaction: discord.Interaction):
        cog = self.manager.bot.get_cog("Dev")
        embed = cog.get_custom_embed(interaction, f"🔧 Menu Dev", f"Menu de gestion de l'économie.")
        embed.add_field(name="🎯 Options", value="**👨‍👩‍👧‍👦 Familles**\n**🎭 Personnages**", inline=False)
        await interaction.response.edit_message(embed=embed, view=DevView(cog), attachments=[])

class FamillePersonnageView(discord.ui.View):
    def __init__(self, manager: PersonnageManager, famille_name: str, page: int = 1, personnages: List[Dict] = None):
        super().__init__(timeout=300)
        self.manager = manager
        self.famille_name = famille_name
        self.page = page
        self.items_per_page = 20
        self.personnages = personnages or []
        self.total_pages = max(1, (len(self.personnages) + self.items_per_page - 1) // self.items_per_page)
        self._build_view()
    
    def _build_view(self):
        self.clear_items()
        back_btn = discord.ui.Button(label="Retour", style=discord.ButtonStyle.secondary, emoji="🔙", row=0)
        back_btn.callback = self.back_to_dev_menu
        self.add_item(back_btn)
        
        add_btn = discord.ui.Button(label="Ajouter", style=discord.ButtonStyle.success, emoji="➕", row=0)
        add_btn.callback = self.create_personnage
        self.add_item(add_btn)
        
        if self.page > 1:
            prev_btn = discord.ui.Button(label="⬅️", style=discord.ButtonStyle.secondary, row=0)
            prev_btn.callback = self.previous_page
            self.add_item(prev_btn)
        if self.page < self.total_pages:
            next_btn = discord.ui.Button(label="➡️", style=discord.ButtonStyle.secondary, row=0)
            next_btn.callback = self.next_page
            self.add_item(next_btn)
            
        start_idx = (self.page - 1) * self.items_per_page
        end_idx = min(start_idx + self.items_per_page, len(self.personnages))
        page_personnages = self.personnages[start_idx:end_idx]
        
        if page_personnages:
            options = [discord.SelectOption(label=f"{start_idx + i + 1}. {p.get('nom', 'Sans nom')}", value=str(start_idx + i)) for i, p in enumerate(page_personnages)]
            select = discord.ui.Select(placeholder="Choisissez un personnage...", options=options, row=1)
            select.callback = self.select_personnage
            self.add_item(select)
    
    async def select_personnage(self, interaction: discord.Interaction):
        await interaction.response.defer()
        personnage_index = int(interaction.data['values'][0])
        personnage_data = self.personnages[personnage_index]
        personnage_name = personnage_data.get('nom', 'Sans nom')
        
        # On instancie la vue complète du profil
        view = PersonnageProfileView(self.manager, self.famille_name, personnage_name, personnage_data)
        await view.render_profile(interaction)
    
    async def previous_page(self, interaction: discord.Interaction):
        self.page -= 1
        self._build_view()
        await interaction.response.edit_message(view=self) # (Simplifié pour la pagination)
    
    async def next_page(self, interaction: discord.Interaction):
        self.page += 1
        self._build_view()
        await interaction.response.edit_message(view=self)
    
    async def create_personnage(self, interaction: discord.Interaction):
        await interaction.response.send_modal(CreatePersonnageModal(self.manager, self.famille_name))
    
    async def back_to_dev_menu(self, interaction: discord.Interaction):
        cog = self.manager.bot.get_cog("Dev")
        view = PersonnageView(self.manager, interaction.guild.id)
        embed = self.manager.get_personnage_embed(interaction, 1)
        await interaction.response.edit_message(embed=embed, view=view, attachments=[])

class PersonnageProfileView(discord.ui.View):
    """Vue unique et complète pour le profil d'un personnage avec tous les outils."""
    def __init__(self, manager: PersonnageManager, famille_name: str, personnage_name: str, personnage_data: Dict):
        super().__init__(timeout=300)
        self.manager = manager
        self.famille_name = famille_name
        self.personnage_name = personnage_name
        self.personnage_data = personnage_data
        self._build_view()
    
    def _build_view(self):
        self.clear_items()
        
        # Ligne 0 : Retour, Info, Stats, Programme
        back_btn = discord.ui.Button(label="Retour", style=discord.ButtonStyle.secondary, emoji="🔙", row=0)
        back_btn.callback = self.back_to_family
        self.add_item(back_btn)
        
        info_btn = discord.ui.Button(label="Informations", style=discord.ButtonStyle.primary, emoji="📝", row=0)
        info_btn.callback = self.modify_info
        self.add_item(info_btn)
        
        stats_btn = discord.ui.Button(label="Stats", style=discord.ButtonStyle.primary, emoji="⚔️", row=0)
        stats_btn.callback = self.modify_stats
        self.add_item(stats_btn)
        
        program_btn = discord.ui.Button(label="Programmer", style=discord.ButtonStyle.primary, emoji="💰", row=0)
        program_btn.callback = self.program_personnage
        self.add_item(program_btn)
        
        # Ligne 1 : Image, Supprimer
        image_btn = discord.ui.Button(label="Modifier l'image", style=discord.ButtonStyle.success, emoji="🖼️", row=1)
        image_btn.callback = self.modify_image
        self.add_item(image_btn)
        
        delete_btn = discord.ui.Button(label="Supprimer", style=discord.ButtonStyle.danger, emoji="🗑️", row=1)
        delete_btn.callback = self.delete_personnage
        self.add_item(delete_btn)
        
        # Ligne 2 : Rareté
        rarete_select = discord.ui.Select(
            placeholder=f"Rareté: {self.personnage_data.get('rarete', 'Non définie')}",
            options=[
                discord.SelectOption(label="Commun", value="Commun"),
                discord.SelectOption(label="Rare", value="Rare"),
                discord.SelectOption(label="Epique", value="Epique"),
                discord.SelectOption(label="Légendaire", value="Légendaire")
            ],
            row=2
        )
        rarete_select.callback = self.change_rarete
        self.add_item(rarete_select)

    async def render_profile(self, interaction: discord.Interaction, is_edit=False):
        """Génère et envoie l'embed complet du profil du personnage."""
        theme_color = self.personnage_data.get('couleur', 0x2b2d31)
        
        embed = discord.Embed(
            title=f"👤 {self.personnage_name}",
            description=f"*Personnage de la famille **{self.famille_name}***",
            color=theme_color
        )
        
        if self.personnage_data.get('description'):
            embed.add_field(name="📝 Description", value=self.personnage_data['description'], inline=False)
        
        # Stats
        stats = []
        if 'vitesse' in self.personnage_data: stats.append(f"**Vitesse:** {self.personnage_data['vitesse']}")
        if 'precision' in self.personnage_data: stats.append(f"**Précision:** {self.personnage_data['precision']}%")
        if 'vie' in self.personnage_data: stats.append(f"**PV:** {self.personnage_data['vie']}")
        if 'puissance' in self.personnage_data: stats.append(f"**Puissance:** {self.personnage_data['puissance']}")
        if stats: embed.add_field(name="📊 Statistiques", value="\n".join(stats), inline=False)
        
        # Infos générales
        infos = []
        if 'valeur' in self.personnage_data: infos.append(f"**Valeur:** {self.personnage_data['valeur']} 💰")
        if 'exemplaires' in self.personnage_data: infos.append(f"**Exemplaires:** {self.personnage_data['exemplaires']} 📦")
        if 'rarete' in self.personnage_data: infos.append(f"**Rareté:** {self.personnage_data['rarete']} ⭐")
        if infos: embed.add_field(name="ℹ️ Economie & Rareté", value="\n".join(infos), inline=False)
        
        file = None
        if self.personnage_data.get('image'):
            personnage_dir = os.path.join(FAMILLE_DIR, self.famille_name, self.personnage_name.lower().replace(" ", "_"))
            image_path = os.path.join(personnage_dir, self.personnage_data['image'])
            if os.path.exists(image_path):
                file = discord.File(image_path, filename=self.personnage_data['image'])
                embed.set_thumbnail(url=f"attachment://{self.personnage_data['image']}")
        
        kwargs = {'embed': embed, 'view': self}
        if file: kwargs['file' if not is_edit else 'attachments'] = [file] if is_edit else file
        else:
            if is_edit: kwargs['attachments'] = []

        if is_edit:
            await interaction.message.edit(**kwargs)
        else:
            # S'il vient d'un defer, il faut utiliser followup.
            try:
                await interaction.followup.send(**kwargs)
            except discord.errors.InteractionResponded:
                # Si non différé ou déjà répondu classiquement
                await interaction.response.send_message(**kwargs)

    async def back_to_family(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.manager.show_famille_personnages(interaction, self.famille_name)
    
    async def modify_info(self, interaction: discord.Interaction):
        # Pas de defer() pour pouvoir envoyer un modal
        await interaction.response.send_modal(PersonnageInfoModal(self.manager, self.famille_name, self.personnage_name, self.personnage_data))
    
    async def modify_stats(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PersonnageStatsModal(self.manager, self.famille_name, self.personnage_name, self.personnage_data))
        
    async def program_personnage(self, interaction: discord.Interaction):
        await interaction.response.send_modal(PersonnageProgramModal(self.manager, self.famille_name, self.personnage_name, self.personnage_data))

    async def change_rarete(self, interaction: discord.Interaction):
        await interaction.response.defer()
        nouvelle_rarete = interaction.data['values'][0]
        
        couleurs = {"Commun": 0x00ff00, "Rare": 0x00bfff, "Epique": 0x9932cc, "Légendaire": 0xffd700}
        
        personnages_data = self.manager.load_famille_personnages(interaction.guild.id, self.famille_name)
        for i, perso in enumerate(personnages_data["personnages"]):
            if perso.get('nom') == self.personnage_name:
                personnages_data["personnages"][i]['rarete'] = nouvelle_rarete
                personnages_data["personnages"][i]['couleur'] = couleurs[nouvelle_rarete]
                self.personnage_data = personnages_data["personnages"][i] # update locale
                break
        
        self.manager.save_famille_personnages(interaction.guild.id, self.famille_name, personnages_data)
        
        # Mettre à jour le JSON local du personnage aussi
        perso_dir = os.path.join(FAMILLE_DIR, self.famille_name, self.personnage_name.lower().replace(" ", "_"))
        config_path = os.path.join(perso_dir, "config.json")
        if os.path.exists(config_path):
            with open(config_path, 'w', encoding='utf-8') as f: json.dump(self.personnage_data, f, indent=4, ensure_ascii=False)
            
        await interaction.followup.send(f"✅ Rareté changée en **{nouvelle_rarete}** !", ephemeral=True)
        self._build_view() # Reconstruire pour MAJ le placeholder
        interaction.message = await interaction.channel.fetch_message(interaction.message.id)
        await self.render_profile(interaction, is_edit=True)

    async def modify_image(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await interaction.followup.send(f"📸 Envoyez une image/GIF/lien pour **{self.personnage_name}** (60s).", ephemeral=True)

        def check(m): return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id
        try: msg = await self.manager.bot.wait_for('message', check=check, timeout=60.0)
        except asyncio.TimeoutError: return await interaction.followup.send("⏳ Temps écoulé.", ephemeral=True)

        image_url, is_attachment = None, False
        filename = f"image_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

        if msg.attachments:
            image_url = msg.attachments[0].url
            is_attachment = True
        elif "http" in msg.content:
            urls = re.findall(r'(https?://[^\s]+)', msg.content)
            if urls: image_url = urls[0]

        if not image_url: return await interaction.followup.send("❌ Aucun fichier/lien valide.", ephemeral=True)

        perso_dir = os.path.join(FAMILLE_DIR, self.famille_name, self.personnage_name.lower().replace(" ", "_"))
        file_path = os.path.join(perso_dir, filename)
        os.makedirs(perso_dir, exist_ok=True)

        try:
            if is_attachment: await msg.attachments[0].save(file_path)
            else:
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_url) as resp:
                        if resp.status == 200:
                            with open(file_path, 'wb') as f: f.write(await resp.read())
        except Exception as e: return await interaction.followup.send(f"❌ Erreur: {str(e)}", ephemeral=True)

        # MAJ Data globale
        personnages_data = self.manager.load_famille_personnages(interaction.guild.id, self.famille_name)
        for i, perso in enumerate(personnages_data["personnages"]):
            if perso.get('nom') == self.personnage_name:
                # Supprimer l'ancienne image
                old_img = perso.get('image')
                if old_img:
                    old_path = os.path.join(perso_dir, old_img)
                    if os.path.exists(old_path): os.remove(old_path)
                    
                personnages_data["personnages"][i]['image'] = filename
                self.personnage_data = personnages_data["personnages"][i]
                break
                
        self.manager.save_famille_personnages(interaction.guild.id, self.famille_name, personnages_data)
        
        # MAJ config locale
        config_path = os.path.join(perso_dir, "config.json")
        if os.path.exists(config_path):
            with open(config_path, 'w', encoding='utf-8') as f: json.dump(self.personnage_data, f, indent=4, ensure_ascii=False)

        try: await msg.delete()
        except: pass

        await interaction.followup.send(f"✅ Image mise à jour !", ephemeral=True)
        interaction.message = await interaction.channel.fetch_message(interaction.message.id)
        await self.render_profile(interaction, is_edit=True)

    async def delete_personnage(self, interaction: discord.Interaction):
        await interaction.response.defer()
        import shutil
        personnage_dir = os.path.join(FAMILLE_DIR, self.famille_name, self.personnage_name.lower().replace(" ", "_"))
        try:
            if os.path.exists(personnage_dir): shutil.rmtree(personnage_dir)
            
            personnages_data = self.manager.load_famille_personnages(interaction.guild.id, self.famille_name)
            personnages_data["personnages"] = [p for p in personnages_data["personnages"] if p.get("nom") != self.personnage_name]
            self.manager.save_famille_personnages(interaction.guild.id, self.famille_name, personnages_data)
            
            await interaction.followup.send(f"✅ Personnage **{self.personnage_name}** supprimé !", ephemeral=True)
            await self.manager.show_famille_personnages(interaction, self.famille_name)
        except Exception as e:
            await interaction.followup.send(f"❌ Erreur: {str(e)}", ephemeral=True)


def generate_unique_id():
    """Génère un ID aléatoire de 5 caractères (lettres + chiffres)"""
    characters = string.ascii_uppercase + string.digits
    return ''.join(random.choices(characters, k=5))

def get_existing_ids():
    """Récupère tous les IDs existants pour éviter les doublons"""
    existing_ids = set()
    
    if not os.path.exists(FAMILLE_DIR):
        return existing_ids
    
    for famille_name in os.listdir(FAMILLE_DIR):
        famille_path = os.path.join(FAMILLE_DIR, famille_name)
        
        if not os.path.isdir(famille_path):
            continue
        
        # Parcourir tous les personnages dans la famille
        personnages_file = os.path.join(famille_path, 'personnages.json')
        if os.path.exists(personnages_file):
            try:
                with open(personnages_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for personnage in data.get('personnages', []):
                        if 'id' in personnage:
                            existing_ids.add(personnage['id'])
            except:
                continue
        
        # Parcourir tous les config.json des personnages
        for personnage_name in os.listdir(famille_path):
            personnage_dir = os.path.join(famille_path, personnage_name)
            if os.path.isdir(personnage_dir):
                config_file = os.path.join(personnage_dir, 'config.json')
                if os.path.exists(config_file):
                    try:
                        with open(config_file, 'r', encoding='utf-8') as f:
                            config_data = json.load(f)
                            if 'id' in config_data:
                                existing_ids.add(config_data['id'])
                    except:
                        continue
    
    return existing_ids

class CreatePersonnageModal(discord.ui.Modal):
    def __init__(self, manager: PersonnageManager, famille_name: str):
        super().__init__(title=f"Créer un personnage", timeout=300)
        self.manager = manager
        self.famille_name = famille_name
        self.nom = discord.ui.TextInput(label="Nom du personnage", required=True, max_length=50)
        self.add_item(self.nom)
    
    async def on_submit(self, interaction: discord.Interaction):
        nom = self.nom.value.strip()
        personnage_dir = os.path.join(FAMILLE_DIR, self.famille_name, nom.lower().replace(" ", "_"))
        os.makedirs(personnage_dir, exist_ok=True)
        
        # Générer un ID aléatoire non utilisé
        existing_ids = get_existing_ids()
        new_id = generate_unique_id()
        while new_id in existing_ids:
            new_id = generate_unique_id()
        
        personnage_data = {
            "nom": nom,
            "creation_date": discord.utils.utcnow().isoformat(),
            "creator_id": interaction.user.id,
            "image": None,
            "id": new_id,  # Ajouter l'ID unique
            "exemplaires": 1,  # Ajouter le nombre d'exemplaires par défaut
            "exemplaires_restant": 1  # Ajouter exemplaires_restant = exemplaires
        }
        
        config_path = os.path.join(personnage_dir, "config.json")
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(personnage_data, f, indent=4, ensure_ascii=False)
        
        personnages_data = self.manager.load_famille_personnages(interaction.guild.id, self.famille_name)
        personnages_data["personnages"].append(personnage_data)
        self.manager.save_famille_personnages(interaction.guild.id, self.famille_name, personnages_data)
        
        # Ouvre le profil auto via defer + followup
        await interaction.response.defer()
        await interaction.followup.send(f"✅ Personnage **{nom}** créé avec l'ID **{new_id}** !", ephemeral=True)
        
        view = PersonnageProfileView(self.manager, self.famille_name, nom, personnage_data)
        await view.render_profile(interaction)

class PersonnageInfoModal(discord.ui.Modal):
    def __init__(self, manager: PersonnageManager, famille_name: str, personnage_name: str, personnage_data: Dict):
        super().__init__(title=f"Infos - {personnage_name}", timeout=300)
        self.manager = manager
        self.famille_name = famille_name
        self.personnage_name = personnage_name
        self.personnage_data = personnage_data
        
        self.nom = discord.ui.TextInput(label="Nom", required=True, max_length=50, default=personnage_data.get('nom', ''))
        self.add_item(self.nom)
        self.description = discord.ui.TextInput(label="Description", style=discord.TextStyle.paragraph, required=False, max_length=1000, default=personnage_data.get('description', ''))
        self.add_item(self.description)
    
    async def on_submit(self, interaction: discord.Interaction):
        new_name = self.nom.value.strip()
        new_desc = self.description.value.strip() if self.description.value else None
        
        personnages_data = self.manager.load_famille_personnages(interaction.guild.id, self.famille_name)
        for i, perso in enumerate(personnages_data["personnages"]):
            if perso.get('nom') == self.personnage_name:
                personnages_data["personnages"][i]['nom'] = new_name
                if new_desc is not None: personnages_data["personnages"][i]['description'] = new_desc
                self.personnage_data = personnages_data["personnages"][i]
                break
                
        self.manager.save_famille_personnages(interaction.guild.id, self.famille_name, personnages_data)
        
        # Gestion du renommage du dossier
        if new_name != self.personnage_name:
            old_dir = os.path.join(FAMILLE_DIR, self.famille_name, self.personnage_name.lower().replace(" ", "_"))
            new_dir = os.path.join(FAMILLE_DIR, self.famille_name, new_name.lower().replace(" ", "_"))
            if os.path.exists(old_dir):
                import shutil
                shutil.move(old_dir, new_dir)
            
        config_path = os.path.join(FAMILLE_DIR, self.famille_name, new_name.lower().replace(" ", "_"), "config.json")
        if os.path.exists(config_path):
            with open(config_path, 'w', encoding='utf-8') as f: json.dump(self.personnage_data, f, indent=4, ensure_ascii=False)
            
        await interaction.response.defer()
        interaction.message = await interaction.channel.fetch_message(interaction.message.id)
        
        view = PersonnageProfileView(self.manager, self.famille_name, new_name, self.personnage_data)
        await view.render_profile(interaction, is_edit=True)

class PersonnageStatsModal(discord.ui.Modal):
    def __init__(self, manager: PersonnageManager, famille_name: str, personnage_name: str, personnage_data: Dict):
        super().__init__(title=f"Stats - {personnage_name}", timeout=300)
        self.manager = manager
        self.famille_name = famille_name
        self.personnage_name = personnage_name
        self.personnage_data = personnage_data
        
        self.vitesse = discord.ui.TextInput(label="Vitesse (1-100)", required=True, max_length=3, default=str(personnage_data.get('vitesse', 50)))
        self.add_item(self.vitesse)
        self.precision = discord.ui.TextInput(label="Précision (1-100)", required=True, max_length=3, default=str(personnage_data.get('precision', 75)))
        self.add_item(self.precision)
        self.vie = discord.ui.TextInput(label="Points de Vie", required=True, max_length=4, default=str(personnage_data.get('vie', 100)))
        self.add_item(self.vie)
        self.puissance = discord.ui.TextInput(label="Puissance", required=True, max_length=3, default=str(personnage_data.get('puissance', 60)))
        self.add_item(self.puissance)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            v = int(self.vitesse.value)
            p = int(self.precision.value)
            vie = int(self.vie.value)
            pui = int(self.puissance.value)
        except ValueError:
            return await interaction.response.send_message("❌ Valeurs numériques invalides.", ephemeral=True)
            
        personnages_data = self.manager.load_famille_personnages(interaction.guild.id, self.famille_name)
        for i, perso in enumerate(personnages_data["personnages"]):
            if perso.get('nom') == self.personnage_name:
                personnages_data["personnages"][i].update({'vitesse': v, 'precision': p, 'vie': vie, 'puissance': pui})
                self.personnage_data = personnages_data["personnages"][i]
                break
                
        self.manager.save_famille_personnages(interaction.guild.id, self.famille_name, personnages_data)
        
        perso_dir = os.path.join(FAMILLE_DIR, self.famille_name, self.personnage_name.lower().replace(" ", "_"))
        config_path = os.path.join(perso_dir, "config.json")
        if os.path.exists(config_path):
            with open(config_path, 'w', encoding='utf-8') as f: json.dump(self.personnage_data, f, indent=4, ensure_ascii=False)
            
        await interaction.response.defer()
        interaction.message = await interaction.channel.fetch_message(interaction.message.id)
        view = PersonnageProfileView(self.manager, self.famille_name, self.personnage_name, self.personnage_data)
        await view.render_profile(interaction, is_edit=True)

class PersonnageProgramModal(discord.ui.Modal):
    def __init__(self, manager: PersonnageManager, famille_name: str, personnage_name: str, personnage_data: Dict):
        super().__init__(title=f"Eco - {personnage_name}", timeout=300)
        self.manager = manager
        self.famille_name = famille_name
        self.personnage_name = personnage_name
        self.personnage_data = personnage_data
        
        self.valeur = discord.ui.TextInput(label="Valeur monétaire", required=True, max_length=10, default=str(personnage_data.get('valeur', '0')))
        self.add_item(self.valeur)
        self.exemplaires = discord.ui.TextInput(label="Nombre d'exemplaires", required=True, max_length=5, default=str(personnage_data.get('exemplaires', '1')))
        self.add_item(self.exemplaires)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.valeur.value)
            ex = int(self.exemplaires.value)
        except ValueError:
            return await interaction.response.send_message("❌ Valeurs numériques invalides.", ephemeral=True)
            
        personnages_data = self.manager.load_famille_personnages(interaction.guild.id, self.famille_name)
        for i, perso in enumerate(personnages_data["personnages"]):
            if perso.get('nom') == self.personnage_name:
                personnages_data["personnages"][i].update({'valeur': val, 'exemplaires': ex, 'exemplaires_restant': ex})
                self.personnage_data = personnages_data["personnages"][i]
                break
                
        self.manager.save_famille_personnages(interaction.guild.id, self.famille_name, personnages_data)
        
        perso_dir = os.path.join(FAMILLE_DIR, self.famille_name, self.personnage_name.lower().replace(" ", "_"))
        config_path = os.path.join(perso_dir, "config.json")
        if os.path.exists(config_path):
            with open(config_path, 'w', encoding='utf-8') as f: json.dump(self.personnage_data, f, indent=4, ensure_ascii=False)
            
        await interaction.response.defer()
        interaction.message = await interaction.channel.fetch_message(interaction.message.id)
        view = PersonnageProfileView(self.manager, self.famille_name, self.personnage_name, self.personnage_data)
        await view.render_profile(interaction, is_edit=True)


# ==============================================================================
# ----------------------------- VUE PRINCIPALE DEV -----------------------------
# ==============================================================================

class DevView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog
        select = discord.ui.Select(
            placeholder="Choisissez une option...",
            options=[
                discord.SelectOption(label="Famille", value="famille", emoji="👨‍👩‍👧‍👦"),
                discord.SelectOption(label="Personnage", value="personnage", emoji="🎭")
            ]
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        selected = interaction.data['values'][0]
        
        if selected == "famille":
            try:
                manager = FamilleManager(self.cog.bot)
                embed = manager.get_famille_embed(interaction)
                view = FamilleView(manager)
                await interaction.response.edit_message(embed=embed, view=view)
            except Exception as e:
                await interaction.response.send_message(f"❌ Erreur: {str(e)}", ephemeral=True)
            
        elif selected == "personnage":
            try:
                manager = PersonnageManager(self.cog.bot)
                embed = manager.get_personnage_embed(interaction)
                view = PersonnageView(manager, interaction.guild.id, 1)
                await interaction.response.edit_message(embed=embed, view=view)
            except Exception as e:
                await interaction.response.send_message(f"❌ Erreur: {str(e)}", ephemeral=True)


# ==============================================================================
# -------------------------------- COG DEV -------------------------------------
# ==============================================================================

class Dev(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.owner_ids = self._load_owners()
        
    def _load_owners(self):
        try:
            # Chemin absolu vers owner.json
            path = os.path.normpath(os.path.join(os.getcwd(), 'cogs', 'developpeur', 'commands', 'profil', 'owner', 'owner.json'))
            if os.path.exists(path):
                with open(path, 'r') as f:
                    d = json.load(f)
                    return [int(x) for x in d] if isinstance(d, list) else [int(d)]
            return []
        except: return []

    def get_custom_embed(self, inter, title, description):
        user = inter.user if isinstance(inter, discord.Interaction) else inter.author
        guild = inter.guild if hasattr(inter, 'guild') else None
        
        if HAS_CUSTOM_EMBED and config_manager:
            embed = config_manager.get_formatted_embed(
                guild=guild, user=user, bot=self.bot,
                title=title, description=description,
                target_id=guild.id if guild else None
            )
        else:
            embed = discord.Embed(title=title, description=description, color=0x2b2d31)
        
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        return embed
    
    async def get_prefix(self, ctx):
        # Import de la fonction centralisée depuis main.py
        import sys
        import os
        sys.path.append(os.path.join(os.getcwd()))
        from main import get_prefixes_with_priority
        
        prefixes = get_prefixes_with_priority(ctx.guild.id)
        return prefixes[0] if prefixes else "."  # Retourne le premier préfixe
        
    @commands.command(name="dev", description="Commande de développement réservée aux owners.")
    async def dev(self, ctx: commands.Context):
        if not await ctx.bot.is_owner(ctx.author) and ctx.author.id not in self.owner_ids:
            return await ctx.send("❌ Accès restreint aux owners du bot.", ephemeral=True)
        
        if ctx.interaction: 
            await ctx.defer(ephemeral=True)
        
        embed = self.get_custom_embed(
            ctx, 
            f"🔧 Menu de développement de {self.bot.user.name}", 
            f"Bienvenue sur le menu de développement de **{self.bot.user.name}**\n\nCe menu permet aux développeurs de la liste owner `{await self.get_prefix(ctx)}owner` de gérer l'économie du bot."
        )
        
        embed.add_field(
            name="🎯 Options disponibles",
            value="**👨‍👩‍👧‍👦 Familles** : Créer / Modifier / Supprimer des familles\n\n"
                  "**🎭 Personnages** : Créer / Modifier / Supprimer des personnages",
            inline=False
        )
        
        try:
            await ctx.send(embed=embed, view=DevView(self), ephemeral=True)
        except Exception as e:
            await ctx.send(f"❌ Erreur lors de l'envoi: {str(e)}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Dev(bot))