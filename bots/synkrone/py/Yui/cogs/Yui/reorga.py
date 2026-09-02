import discord
from discord.ext import commands
from discord import app_commands, ui
import asyncio
import math
import traceback
from typing import List, Any

# ===================== IMPORTATION CONFIG MANAGER ====================
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# ==============================================================================
# --------------------------- MODAL DE POSITION DIRECTE ------------------------
# ==============================================================================

class PositionModal(ui.Modal):
    def __init__(self, view: ui.View, max_rank: int):
        super().__init__(title="🔢 Modifier la position", timeout=300)
        self.reorga_view = view
        self.max_rank = max_rank

        self.pos_input = ui.TextInput(
            label=f"Nouveau rang souhaité (1 à {max_rank})",
            style=discord.TextStyle.short,
            placeholder=f"Exemple: {max_rank}",
            required=True,
            min_length=1,
            max_length=3
        )
        self.add_item(self.pos_input)

    async def on_submit(self, interaction: discord.Interaction):
        val = self.pos_input.value.strip()
        if not val.isdigit():
            return await interaction.response.send_message("❌ Veuillez entrer un nombre valide.", ephemeral=True)
        
        target_rank = int(val)
        if target_rank < 1 or target_rank > self.max_rank:
            return await interaction.response.send_message(f"❌ Le rang doit être compris entre 1 et {self.max_rank}.", ephemeral=True)

        # On déclenche le déplacement
        await self.reorga_view.move_to_rank(target_rank, interaction)


# ==============================================================================
# --------------------------- MACHINE À ÉTATS UI -------------------------------
# ==============================================================================

class ReorgaView(ui.View):
    def __init__(self, bot: commands.Bot, author: discord.Member, ctx_guild: discord.Guild, original_message: discord.Message = None):
        super().__init__(timeout=600)
        self.bot = bot
        self.author = author
        self.guild = ctx_guild
        self.message = original_message

        # Variables de navigation
        self.state = 'menu'
        self.current_item: Any = None 
        self.current_category: Any = None 
        self.channel_filter_type: str = 'text' 
        
        self.page = 0
        self.max_pages = 1

        self.build_ui()

    # ================= [SÉCURITÉ ADMIN] =================
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message("❌ Ce panel est strictement réservé à la personne qui a lancé la commande.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        self.clear_items()
        try:
            if self.message: await self.message.edit(view=self)
        except Exception: pass

    # ================= [RÉCUPÉRATION ET TRIS] =================
    
    def get_roles_display(self) -> List[discord.Role]:
        bot_top = self.guild.me.top_role
        roles = [r for r in self.guild.roles if r.position > 0 and r < bot_top and not r.managed]
        roles.sort(key=lambda r: r.position, reverse=True)
        return roles

    def get_cats_display(self) -> List[Any]:
        cats = [c for c in self.guild.categories]
        cats.sort(key=lambda c: c.position)
        return ["uncat"] + cats

    def get_channels_display(self) -> List[discord.abc.GuildChannel]:
        if self.current_category == "uncat":
            channels = [c for c in self.guild.channels if c.category_id is None and not isinstance(c, discord.CategoryChannel)]
        else:
            channels = self.current_category.channels

        if self.channel_filter_type == 'text':
            filtered = [c for c in channels if isinstance(c, (discord.TextChannel, discord.ForumChannel))]
        else:
            filtered = [c for c in channels if isinstance(c, (discord.VoiceChannel, discord.StageChannel))]

        filtered.sort(key=lambda c: c.position)
        return filtered

    def get_current_items_list(self):
        if 'role' in self.state: return self.get_roles_display()
        if 'cat' in self.state or self.state == 'select_new_category': return self.get_cats_display()
        if 'channel' in self.state: return self.get_channels_display()
        return []

    # ================= [CONSTRUCTION DE L'INTERFACE] =================

    def build_ui(self):
        self.clear_items()

        # --- MENU PRINCIPAL ---
        if self.state == 'menu':
            btn_roles = ui.Button(label="Réorganiser les Rôles", style=discord.ButtonStyle.primary, emoji="🎭")
            btn_roles.callback = self.make_transition_callback('roles_list')
            
            btn_cats = ui.Button(label="Réorganiser Catégories & Salons", style=discord.ButtonStyle.primary, emoji="📂")
            btn_cats.callback = self.make_transition_callback('cats_list')

            btn_help = ui.Button(label="Aide & Tutoriel", style=discord.ButtonStyle.secondary, emoji="ℹ️")
            btn_help.callback = self.show_help_callback
            
            self.add_item(btn_roles)
            self.add_item(btn_cats)
            self.add_item(btn_help)

        # --- LISTES DÉROULANTES ---
        elif self.state in ['roles_list', 'cats_list', 'channels_list', 'select_new_category']:
            items = self.get_current_items_list()
            self.max_pages = max(1, math.ceil(len(items) / 25))
            
            if not items:
                btn_back = ui.Button(label="Retour", style=discord.ButtonStyle.danger, emoji="🔙")
                back_target = 'menu' if self.state in ['roles_list', 'cats_list'] else 'cat_selected'
                btn_back.callback = self.make_transition_callback(back_target)
                self.add_item(btn_back)
                return

            page_items = items[self.page * 25 : (self.page + 1) * 25]
            emoji = "🎭" if 'role' in self.state else ("📂" if 'cat' in self.state or self.state == 'select_new_category' else "💬")
            
            placeholder = f"Sélectionnez (Page {self.page + 1}/{self.max_pages})..."
            if self.state == 'select_new_category': placeholder = f"Où envoyer ce salon ? (Page {self.page + 1})..."
                
            select = ui.Select(placeholder=placeholder, min_values=1, max_values=1, row=0)

            for idx, item in enumerate(page_items):
                if item == "uncat":
                    label = "🌐 Salons Hors Catégorie"
                    desc = "Salons tout en haut du serveur" if self.state != 'select_new_category' else "Envoyer tout en haut du serveur"
                    select.add_option(label=label, value="uncat", description=desc, emoji="🌐")
                else:
                    global_rank = (self.page * 25) + idx + 1
                    if self.state == 'select_new_category':
                        select.add_option(label=item.name[:90], value=str(item.id), emoji=emoji)
                    else:
                        select.add_option(label=f"{global_rank}. {item.name[:90]}", value=str(item.id), emoji=emoji)

            select.callback = self.list_select_callback
            self.add_item(select)

            # Pagination & Retour
            if self.page > 0:
                btn_prev = ui.Button(label="◀️ Page Précédente", style=discord.ButtonStyle.secondary, row=1)
                btn_prev.callback = self.prev_page_callback
                self.add_item(btn_prev)
                
            if self.page < self.max_pages - 1:
                btn_next = ui.Button(label="Page Suivante ▶️", style=discord.ButtonStyle.secondary, row=1)
                btn_next.callback = self.next_page_callback
                self.add_item(btn_next)

            btn_back = ui.Button(label="Retour", style=discord.ButtonStyle.danger, emoji="🔙", row=1)
            if self.state == 'select_new_category':
                btn_back.callback = self.make_transition_callback('channel_selected')
            else:
                back_target = 'menu' if self.state in ['roles_list', 'cats_list'] else 'cat_selected'
                btn_back.callback = self.make_transition_callback(back_target)
                
            self.add_item(btn_back)

        # --- ÉLÉMENT SÉLECTIONNÉ ---
        elif self.state in ['role_selected', 'cat_selected', 'channel_selected']:
            is_virtual_cat = (self.state == 'cat_selected' and self.current_item == "uncat")

            # Boutons de déplacement (Cachés si c'est le groupe "Hors Catégorie")
            if not is_virtual_cat:
                btn_up = ui.Button(label="Monter", style=discord.ButtonStyle.success, emoji="⬆️", row=0)
                btn_up.callback = self.make_move_callback(-1)
                
                btn_down = ui.Button(label="Descendre", style=discord.ButtonStyle.danger, emoji="⬇️", row=0)
                btn_down.callback = self.make_move_callback(1)
                
                btn_pos = ui.Button(label="Taper le numéro final", style=discord.ButtonStyle.primary, emoji="🔢", row=0)
                btn_pos.callback = self.open_pos_modal_callback

                self.add_item(btn_up)
                self.add_item(btn_down)
                self.add_item(btn_pos)

            # Boutons supplémentaires selon le type
            if self.state == 'cat_selected':
                btn_txt = ui.Button(label="Ranger les Textuels/Forums", style=discord.ButtonStyle.secondary, emoji="💬", row=1)
                btn_txt.callback = self.manage_channels_callback('text')
                
                btn_voc = ui.Button(label="Ranger les Vocaux", style=discord.ButtonStyle.secondary, emoji="🔊", row=1)
                btn_voc.callback = self.manage_channels_callback('voice')
                
                self.add_item(btn_txt)
                self.add_item(btn_voc)
                
            elif self.state == 'channel_selected':
                btn_change_cat = ui.Button(label="Changer de Catégorie", style=discord.ButtonStyle.secondary, emoji="🔀", row=1)
                btn_change_cat.callback = self.make_transition_callback('select_new_category')
                self.add_item(btn_change_cat)

            # Retour
            back_targets = {'role_selected': 'roles_list', 'cat_selected': 'cats_list', 'channel_selected': 'channels_list'}
            btn_back = ui.Button(label="Retour à la liste", style=discord.ButtonStyle.danger, emoji="🔙", row=2)
            btn_back.callback = self.make_transition_callback(back_targets[self.state])
            self.add_item(btn_back)

    def generate_embed(self) -> discord.Embed:
        title = "🏗️ Panel de Réorganisation"
        desc = ""

        if self.state == 'menu':
            desc = "Bienvenue dans l'outil de gestion hiérarchique interactif.\nCliquez sur une option ci-dessous ou consultez l'aide."
            
        elif self.state in ['roles_list', 'cats_list', 'channels_list']:
            items = self.get_current_items_list()
            types = {'roles_list': 'Rôles', 'cats_list': 'Catégories', 'channels_list': 'Salons'}
            title = f"📋 Liste des {types[self.state]}"
            
            if not items:
                desc = "⚠️ Aucun élément trouvé."
            else:
                if self.state == 'channels_list':
                    cat_name = "🌐 Hors Catégorie" if self.current_category == "uncat" else self.current_category.name
                    desc += f"**Dossier ouvert :** {cat_name}\n"
                    desc += f"**Filtre :** {'💬 Salons Textuels' if self.channel_filter_type == 'text' else '🔊 Salons Vocaux'}\n\n"
                    
                desc += f"*(Total : {len(items)} éléments)*\nSélectionnez ce que vous souhaitez déplacer :"

        elif self.state == 'select_new_category':
            title = "🔀 Déplacement vers un autre dossier"
            desc = f"Où souhaitez-vous envoyer le salon **{self.current_item.name}** ?\nChoisissez sa nouvelle maison dans la liste."

        elif self.state in ['role_selected', 'cat_selected', 'channel_selected']:
            if self.state == 'cat_selected' and self.current_item == "uncat":
                title = "🌐 Salons Hors Catégorie"
                desc = "Ce groupe représente tous les salons tout en haut de votre serveur qui n'ont pas de catégorie.\n\nCliquez sur les boutons en dessous pour les ranger."
            else:
                items = self.get_current_items_list()
                current_rank = next((idx + 1 for idx, item in enumerate(items) if getattr(item, 'id', None) == self.current_item.id), 1)
                mention = self.current_item.mention if hasattr(self.current_item, 'mention') else self.current_item.name
                
                title = "⚙️ Que voulez-vous en faire ?"
                desc = (
                    f"**Cible :** {mention}\n"
                    f"**Position actuelle :** `N° {current_rank}` sur {len(items)}\n\n"
                    f"Appuyez sur `Monter`/`Descendre` pour le glisser d'un cran, ou cliquez sur `🔢` pour taper directement sa place finale."
                )

        if config_manager:
            return config_manager.get_formatted_embed(self.guild, self.author, self.bot, title, desc)
        return discord.Embed(title=title, description=desc, color=0xf1c40f)

    # ================= [LOGIQUE DE DÉPLACEMENT 100% FIABLE] =================

    async def move_to_rank(self, target_rank: int, interaction: discord.Interaction):
        await interaction.response.defer()
        
        items = self.get_current_items_list()
        
        # 1. On trouve où est l'élément actuellement
        current_idx = next((idx for idx, item in enumerate(items) if getattr(item, 'id', None) == self.current_item.id), -1)
        
        # 2. On calcule l'index visé (en protégeant des nombres trop grands ou petits)
        target_idx = target_rank - 1
        if target_idx < 0: target_idx = 0
        if target_idx >= len(items): target_idx = len(items) - 1

        # Si on demande à aller là où on est déjà, on ne fait rien
        if current_idx == target_idx or current_idx == -1:
            self.build_ui()
            return await interaction.edit_original_response(embed=self.generate_embed(), view=self)

        # 3. Écran de chargement pour rassurer l'utilisateur
        loading_embed = discord.Embed(title="⏳ Synchronisation Discord...", description="Application du changement...", color=0xf39c12)
        await interaction.edit_original_response(embed=loading_embed, view=None)

        # 4. LE SECRET DE LA FIABILITÉ : On copie la position API de l'élément qui occupe la place voulue
        target_pos = items[target_idx].position

        try:
            # On applique la modification. Discord s'occupe de repousser les autres éléments.
            if self.state == 'channel_selected' and isinstance(self.current_category, discord.CategoryChannel):
                await self.current_item.edit(position=target_pos, category=self.current_category, reason=f"Reorga par {self.author}")
            else:
                await self.current_item.edit(position=target_pos, reason=f"Reorga par {self.author}")
            
            # 5. On fige le bot pendant 1.5 secondes pour laisser à Discord le temps d'appliquer visuellement le changement
            await asyncio.sleep(1.5) 
            
        except Exception as e:
            print(f"[ERROR Reorga Position] {e}")

        # On rafraîchit les données avant de réafficher le menu
        items = self.get_current_items_list()
        self.current_item = next((i for i in items if getattr(i, 'id', None) == self.current_item.id), self.current_item)

        self.build_ui()
        await interaction.edit_original_response(embed=self.generate_embed(), view=self)


    # ================= [CALLBACKS & TRANSITIONS] =================

    async def show_help_callback(self, interaction: discord.Interaction):
        """Bouton d'Aide : Affiche un tutoriel clair à l'utilisateur."""
        help_desc = (
            "Bienvenue dans le tutoriel du panel de réorganisation.\n\n"
            "**1. Le système des numéros (🔢)**\n"
            "Si la liste affiche 20 éléments, tapez `20` pour mettre un élément tout en bas. Tapez `1` pour le mettre tout en haut.\n\n"
            "**2. Le comportement des Flèches (⬆️⬇️)**\n"
            "Elles échangent la place de l'élément avec son voisin direct. Si le menu met 2 secondes à répondre, c'est normal : c'est le temps que Discord prenne en compte le changement.\n\n"
            "**3. Le Bouton Changer de Catégorie (🔀)**\n"
            "Uniquement disponible sur les salons. Il permet d'expédier un salon dans un autre dossier instantanément.\n\n"
            "**4. Pourquoi Textuels et Vocaux sont séparés ?**\n"
            "Discord interdit de mélanger l'ordre des salons textuels et vocaux (les vocaux sont toujours en bas). L'outil vous demande donc de choisir quoi filtrer pour éviter que les salons ne buggent."
        )
        embed = discord.Embed(title="ℹ️ Comment ça marche ?", description=help_desc, color=0x3498db)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    def make_transition_callback(self, new_state: str):
        async def callback(interaction: discord.Interaction):
            self.state = new_state
            self.page = 0
            self.build_ui()
            await interaction.response.edit_message(embed=self.generate_embed(), view=self)
        return callback

    def make_move_callback(self, offset: int):
        async def callback(interaction: discord.Interaction):
            items = self.get_current_items_list()
            current_rank = next((idx + 1 for idx, item in enumerate(items) if getattr(item, 'id', None) == self.current_item.id), 1)
            target_rank = current_rank + offset
            await self.move_to_rank(target_rank, interaction)
        return callback

    async def open_pos_modal_callback(self, interaction: discord.Interaction):
        items = self.get_current_items_list()
        await interaction.response.send_modal(PositionModal(self, max_rank=len(items)))

    def manage_channels_callback(self, filter_type: str):
        async def callback(interaction: discord.Interaction):
            self.current_category = self.current_item
            self.channel_filter_type = filter_type
            self.state = 'channels_list'
            self.page = 0
            self.build_ui()
            await interaction.response.edit_message(embed=self.generate_embed(), view=self)
        return callback

    async def list_select_callback(self, interaction: discord.Interaction):
        selected_val = interaction.data['values'][0]
        
        # --- TRANSFERT DE CATÉGORIE ---
        if self.state == 'select_new_category':
            await interaction.response.defer()
            loading_embed = discord.Embed(title="⏳ Expédition en cours...", color=0xf39c12)
            await interaction.edit_original_response(embed=loading_embed, view=None)

            try:
                if selected_val == "uncat":
                    await self.current_item.edit(category=None, reason=f"Déplacé par {self.author}")
                    self.current_category = "uncat"
                else:
                    target_cat = self.guild.get_channel(int(selected_val))
                    await self.current_item.edit(category=target_cat, reason=f"Déplacé par {self.author}")
                    self.current_category = target_cat
                await asyncio.sleep(1.0)
            except Exception as e:
                print(f"[ERROR Reorga ChangeCat] {e}")

            self.state = 'channels_list'
            self.page = 0
            self.build_ui()
            return await interaction.edit_original_response(embed=self.generate_embed(), view=self)

        # --- SÉLECTION CLASSIQUE ---
        if selected_val == "uncat":
            self.current_item = "uncat"
            self.state = 'cat_selected'
        else:
            selected_id = int(selected_val)
            items = self.get_current_items_list()
            self.current_item = next((i for i in items if getattr(i, 'id', None) == selected_id), None)
            
            if not self.current_item:
                return await interaction.response.send_message("❌ Élément introuvable.", ephemeral=True)

            if self.state == 'roles_list': self.state = 'role_selected'
            elif self.state == 'cats_list': self.state = 'cat_selected'
            elif self.state == 'channels_list': self.state = 'channel_selected'

        self.build_ui()
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    async def prev_page_callback(self, interaction: discord.Interaction):
        self.page -= 1
        self.build_ui()
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    async def next_page_callback(self, interaction: discord.Interaction):
        self.page += 1
        self.build_ui()
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)


# ==============================================================================
# ----------------------------- COG REORGA -------------------------------------
# ==============================================================================

class ReorgaCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="reorga", description="Ouvre le panel interactif pour réorganiser votre serveur.")
    @commands.has_permissions(administrator=True)
    @app_commands.default_permissions(administrator=True)
    async def reorga_cmd(self, ctx: commands.Context):
        view = ReorgaView(self.bot, ctx.author, ctx.guild)
        embed = view.generate_embed()

        if ctx.interaction:
            await ctx.send(embed=embed, view=view)
            view.message = await ctx.interaction.original_response()
        else:
            msg = await ctx.send(embed=embed, view=view, reference=ctx.message)
            view.message = msg

    @reorga_cmd.error
    async def reorga_cmd_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            error_msg = "❌ Vous devez être **Administrateur** pour utiliser cette commande."
            if ctx.interaction:
                await ctx.interaction.response.send_message(error_msg, ephemeral=True)
            else:
                await ctx.send(error_msg, delete_after=5)

async def setup(bot: commands.Bot):
    await bot.add_cog(ReorgaCog(bot))