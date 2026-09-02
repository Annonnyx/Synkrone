import discord
from discord.ext import commands
from discord import app_commands, ui
import asyncio
import math
import traceback
from typing import List, Optional

# ===================== IMPORTATION CONFIG MANAGER ====================
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# ==============================================================================
# --------------------------- SYSTÈME UI AVANCÉ --------------------------------
# ==============================================================================

class AdvancedUnbuildView(ui.View):
    def __init__(self, bot: commands.Bot, author: discord.Member, ctx_guild: discord.Guild, original_message: discord.Message = None):
        super().__init__(timeout=600) # Timeout de 10 minutes (600s)
        self.bot = bot
        self.author = author
        self.guild = ctx_guild
        self.message = original_message
        
        # État de la State Machine
        self.state = 'menu' # 'menu', 'selection', ou 'done'
        self.current_type = None 
        
        # Données de pagination
        self.items: List = []
        self.current_page = 0
        self.max_pages = 1
        self.selections = {} # Stockage des sélections par page
        
        # Variables de résultat final
        self.result_desc = ""

        self.build_ui()

    # ================= [SÉCURITÉ] =================
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message("❌ Ce menu ne vous est pas destiné.", ephemeral=True)
            return False
        return True
    # ==============================================

    async def on_timeout(self):
        self.clear_items()
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass

    def get_filtered_items(self, item_type: str) -> List:
        """Filtre les éléments pour ne retourner QUE ceux que le bot a le droit de supprimer."""
        me = self.guild.me
        items = []
        
        if item_type == 'role':
            for r in self.guild.roles:
                if not r.is_default() and not r.managed and me.top_role > r:
                    items.append(r)
        else:
            # Si le type est category_pack, on liste les catégories (comme pour category normal)
            fetch_type = 'category' if item_type == 'category_pack' else item_type
            
            channels = {
                'category': self.guild.categories,
                'text': self.guild.text_channels,
                'forum': self.guild.forums,
                'voice': self.guild.voice_channels
            }.get(fetch_type, [])
            
            for c in channels:
                if c.permissions_for(me).manage_channels:
                    items.append(c)
                    
        return items

    def build_ui(self):
        """Construit l'interface dynamique selon l'état actuel de la machine."""
        self.clear_items()

        if self.state == 'menu':
            # --- ÉTAT 1 : MENU PRINCIPAL (SÉLECTEUR) ---
            options = [
                discord.SelectOption(label="Pack : Catégorie + TOUT son contenu", value="category_pack", emoji="🧨", description="Détruit la catégorie et tous ses salons"),
                discord.SelectOption(label="Supprimer des Catégories (Vides ou non)", value="category", emoji="📂", description="Détruit juste la catégorie (les salons restent)"),
                discord.SelectOption(label="Supprimer des Salons Textuels", value="text", emoji="💬"),
                discord.SelectOption(label="Supprimer des Salons Vocaux", value="voice", emoji="🔊"),
                discord.SelectOption(label="Supprimer des Salons Forums", value="forum", emoji="📝"),
                discord.SelectOption(label="Supprimer des Rôles", value="role", emoji="🎭"),
            ]
            
            select = ui.Select(placeholder="Que souhaitez-vous nettoyer ?", min_values=1, max_values=1, options=options, row=0)
            select.callback = self.menu_select_callback
            self.add_item(select)

        elif self.state == 'selection':
            # --- ÉTAT 2 : PAGINATION ET SÉLECTION ---
            if not self.items:
                btn_back = ui.Button(label="Retour", style=discord.ButtonStyle.danger, emoji="🔙", row=0)
                btn_back.callback = self.go_back_callback
                self.add_item(btn_back)
                return

            start_idx = self.current_page * 25
            end_idx = start_idx + 25
            page_items = self.items[start_idx:end_idx]

            select = ui.Select(
                placeholder=f"Sélectionnez (Page {self.current_page + 1}/{self.max_pages})...",
                min_values=0, max_values=len(page_items), row=0
            )

            current_page_selections = self.selections.get(self.current_page, [])

            for item in page_items:
                is_selected = str(item.id) in current_page_selections
                emoji = "🎭" if self.current_type == 'role' else "📁"
                if self.current_type == 'category_pack': emoji = "🧨"
                
                # Pour les packs, on affiche le nombre de salons qu'elle contient
                desc = f"ID: {item.id}"
                if self.current_type == 'category_pack' and isinstance(item, discord.CategoryChannel):
                    desc = f"Contient {len(item.channels)} salon(s) | ID: {item.id}"

                select.add_option(
                    label=item.name[:100], value=str(item.id), 
                    description=desc, emoji=emoji, default=is_selected
                )

            select.callback = self.pagination_select_callback
            self.add_item(select)

            # Boutons de navigation et confirmation
            btn_prev = ui.Button(label="◀️", style=discord.ButtonStyle.secondary, disabled=(self.current_page == 0), row=1)
            btn_prev.callback = self.prev_page_callback
            
            btn_next = ui.Button(label="▶️", style=discord.ButtonStyle.secondary, disabled=(self.current_page == self.max_pages - 1), row=1)
            btn_next.callback = self.next_page_callback
            
            btn_back = ui.Button(label="Retour au Menu", style=discord.ButtonStyle.danger, emoji="🔙", row=1)
            btn_back.callback = self.go_back_callback

            total_selected = sum(len(ids) for ids in self.selections.values())
            btn_confirm = ui.Button(
                label=f"🗑️ Exécuter la suppression ({total_selected})", 
                style=discord.ButtonStyle.danger if total_selected > 0 else discord.ButtonStyle.secondary,
                disabled=(total_selected == 0), row=2
            )
            btn_confirm.callback = self.confirm_callback

            self.add_item(btn_prev)
            self.add_item(btn_next)
            self.add_item(btn_back)
            self.add_item(btn_confirm)

        elif self.state == 'done':
            # --- ÉTAT 3 : RÉSULTAT ET RETOUR ---
            btn_return = ui.Button(label="Retour au Menu Principal", style=discord.ButtonStyle.primary, emoji="🔙")
            btn_return.callback = self.go_back_callback
            self.add_item(btn_return)

    def generate_embed(self) -> discord.Embed:
        """Génère l'embed en fonction de l'état actuel."""
        if self.state == 'menu':
            title = "🧨 Unbuilder - Menu Principal"
            desc = (
                "Bienvenue dans l'outil de suppression avancée (Timeout : 10 minutes).\n"
                "Sélectionnez le type d'éléments à détruire ci-dessous.\n\n"
                "⚠️ Le mode `Pack` détruit une catégorie **et tous les salons à l'intérieur** simultanément."
            )
        elif self.state == 'done':
            title = "✅ Nettoyage Terminé"
            desc = self.result_desc
        else:
            types_fr = {
                'category_pack': 'Packs Complets (Catégorie + Contenu)', 'category': 'Catégories (Isolées)', 
                'text': 'Salons Textuels', 'forum': 'Salons Forums', 
                'voice': 'Salons Vocaux', 'role': 'Rôles'
            }
            title = f"🗑️ Cible : {types_fr.get(self.current_type)}"
            
            if not self.items:
                desc = f"⚠️ Aucun élément de type **{types_fr.get(self.current_type)}** ne peut être supprimé par le bot actuellement."
            else:
                total_selected = sum(len(ids) for ids in self.selections.values())
                desc = (
                    f"Éléments trouvés : **{len(self.items)}**\n"
                    f"Page **{self.current_page + 1}/{self.max_pages}**\n\n"
                    f"Sélectionnez les éléments à détruire. Vous en avez sélectionné **{total_selected}** au total."
                )

        if config_manager:
            return config_manager.get_formatted_embed(
                guild=self.guild, user=self.author, bot=self.bot, title=title, description=desc
            )
        color = 0x2ecc71 if self.state == 'done' else 0xe74c3c
        return discord.Embed(title=title, description=desc, color=color)

    # ==============================================================================
    # --------------------------- CALLBACKS D'INTERACTIONS -------------------------
    # ==============================================================================

    async def menu_select_callback(self, interaction: discord.Interaction):
        """Quand on choisit une option dans le menu principal."""
        self.state = 'selection'
        self.current_type = interaction.data['values'][0]
        self.items = self.get_filtered_items(self.current_type)
        self.max_pages = max(1, math.ceil(len(self.items) / 25))
        self.current_page = 0
        self.selections = {}
        
        self.build_ui()
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    async def pagination_select_callback(self, interaction: discord.Interaction):
        """Quand on coche/décoche des cases dans la page courante."""
        self.selections[self.current_page] = interaction.data.get('values', [])
        self.build_ui()
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    async def prev_page_callback(self, interaction: discord.Interaction):
        self.current_page -= 1
        self.build_ui()
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    async def next_page_callback(self, interaction: discord.Interaction):
        self.current_page += 1
        self.build_ui()
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    async def go_back_callback(self, interaction: discord.Interaction):
        """Bouton universel pour réinitialiser la vue et retourner au menu."""
        self.state = 'menu'
        self.current_type = None
        self.build_ui()
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    async def confirm_callback(self, interaction: discord.Interaction):
        """Le cœur de la suppression avec gestion du Pack Complet."""
        await interaction.response.defer()
        
        # Récupération de tous les IDs
        all_selected_ids = []
        for page_ids in self.selections.values():
            all_selected_ids.extend(page_ids)

        # 1. État de chargement UI
        loading_embed = discord.Embed(
            title="⏳ Destruction en cours...", 
            description=f"Veuillez patienter pendant la suppression de {len(all_selected_ids)} cible(s)...", 
            color=0xf39c12
        )
        await interaction.edit_original_response(embed=loading_embed, view=None)

        # 2. Logique de suppression
        deleted_main = 0
        deleted_children = 0
        objects_to_delete = [item for item in self.items if str(item.id) in all_selected_ids]

        for obj in objects_to_delete:
            try:
                # GESTION SPÉCIFIQUE : PACK COMPLET (Détruit les enfants avant le parent)
                if self.current_type == 'category_pack' and isinstance(obj, discord.CategoryChannel):
                    for channel in obj.channels:
                        try:
                            await channel.delete(reason=f"Mass unbuild PACK demandé par {self.author}")
                            deleted_children += 1
                            await asyncio.sleep(0.5)
                        except Exception:
                            pass # On ignore si on ne peut pas delete un salon précis

                # GESTION CLASSIQUE : Détruit l'objet ciblé (Rôle, Salon, ou Catégorie)
                await obj.delete(reason=f"Mass unbuild demandé par {self.author}")
                deleted_main += 1
                await asyncio.sleep(0.5) # Anti Rate-Limit
            except Exception as e:
                print(f"[ERROR Unbuild] Échec sur {obj.name} : {e}")

        # 3. Préparation du résultat
        if self.current_type == 'category_pack':
            self.result_desc = f"**Succès :** {deleted_main} catégorie(s) et {deleted_children} salon(s) interne(s) supprimé(s)."
        else:
            self.result_desc = f"**Succès :** {deleted_main}/{len(all_selected_ids)} élément(s) supprimé(s)."

        # 4. Fin de la State Machine (État Done)
        self.state = 'done'
        self.build_ui()
        await interaction.edit_original_response(embed=self.generate_embed(), view=self)


# ==============================================================================
# --------------------------- COG UNBUILDER ------------------------------------
# ==============================================================================

class MassUnbuilderCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name="unbuild", 
        description="Menu avancé pour nettoyer proprement rôles, salons ou catégories entières."
    )
    @commands.has_permissions(administrator=True)
    @app_commands.default_permissions(administrator=True)
    async def unbuild(self, ctx: commands.Context):
        # Initialisation de la View
        view = AdvancedUnbuildView(self.bot, ctx.author, ctx.guild)
        embed = view.generate_embed()

        if ctx.interaction:
            await ctx.send(embed=embed, view=view)
            view.message = await ctx.interaction.original_response()
        else:
            msg = await ctx.send(embed=embed, view=view, reference=ctx.message)
            view.message = msg

    @unbuild.error
    async def unbuild_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            error_msg = "❌ Vous devez être **Administrateur** pour utiliser cette commande."
            if ctx.interaction:
                await ctx.interaction.response.send_message(error_msg, ephemeral=True)
            else:
                await ctx.send(error_msg, delete_after=5)

async def setup(bot: commands.Bot):
    await bot.add_cog(MassUnbuilderCog(bot))