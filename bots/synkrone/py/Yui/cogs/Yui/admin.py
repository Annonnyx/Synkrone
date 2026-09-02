import discord
from discord.ext import commands
from discord import app_commands, ui
import traceback
import asyncio

# ===================== IMPORTATION CONFIG MANAGER ====================
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# ==============================================================================
# --------------------------- FONCTIONS UTILITAIRES ----------------------------
# ==============================================================================

def is_channel_private(channel: discord.abc.GuildChannel, guild: discord.Guild) -> bool:
    """Vérifie si le rôle @everyone a l'interdiction de voir le salon."""
    everyone_role = guild.default_role
    overwrite = channel.overwrites_for(everyone_role)
    # Si view_channel est False, le salon est privé. Sinon (True ou None), il est public.
    return overwrite.view_channel is False

# ==============================================================================
# --------------------------- MODALS DE BLOCAGE --------------------------------
# ==============================================================================

class BlockModal(ui.Modal):
    def __init__(self, bot: commands.Bot, author: discord.Member, target_type: str):
        """
        target_type: 'category' ou 'channel'
        """
        self.bot = bot
        self.author = author
        self.target_type = target_type
        
        title = "🔒 Bloquer des Catégories" if target_type == 'category' else "🔒 Bloquer des Salons"
        super().__init__(title=title, timeout=300)

        self.ids_input = ui.TextInput(
            label="IDs (séparés par des virgules)",
            style=discord.TextStyle.paragraph,
            placeholder="Ex: 112233445566, 998877665544",
            required=True,
            max_length=2000
        )
        self.add_item(self.ids_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=False)
        guild = interaction.guild
        everyone_role = guild.default_role
        
        # Extraction et nettoyage des IDs
        raw_ids = self.ids_input.value.split(',')
        valid_ids = []
        for raw_id in raw_ids:
            clean_id = raw_id.strip()
            if clean_id.isdigit():
                valid_ids.append(int(clean_id))

        if not valid_ids:
            return await interaction.followup.send("❌ Aucun ID valide n'a été fourni.", ephemeral=True)

        msg = await interaction.followup.send(f"⏳ Traitement de {len(valid_ids)} ID(s) en cours...", wait=True)
        
        success_count = 0
        failed_count = 0

        for target_id in valid_ids:
            try:
                # Récupération de l'objet selon son type
                target = None
                if self.target_type == 'category':
                    target = guild.get_channel(target_id)
                    if not isinstance(target, discord.CategoryChannel):
                        target = None
                else:
                    target = guild.get_channel(target_id)
                    if isinstance(target, discord.CategoryChannel): # On ignore les catégories ici
                        target = None
                
                if target is None:
                    failed_count += 1
                    continue

                # Application de la restriction
                await target.set_permissions(
                    everyone_role, 
                    view_channel=False, 
                    reason=f"Bloqué via Modal Admin par {self.author}"
                )
                success_count += 1
                await asyncio.sleep(0.5) # Anti Rate-Limit

            except discord.Forbidden:
                failed_count += 1
            except Exception as e:
                failed_count += 1
                print(f"[ERROR BlockModal] ID {target_id} : {e}")

        # Bilan de l'opération
        desc = f"**Succès :** {success_count} élément(s) bloqué(s).\n**Échecs (Introuvable ou Permissions) :** {failed_count}."
        
        if config_manager:
            embed = config_manager.get_formatted_embed(
                guild=guild, user=self.author, bot=self.bot, 
                title="✅ Opération Terminée", description=desc
            )
        else:
            embed = discord.Embed(title="✅ Opération Terminée", description=desc, color=0x2ecc71)

        await msg.edit(content=None, embed=embed)


# ==============================================================================
# --------------------------- VUE DU MENU ADMIN --------------------------------
# ==============================================================================

class AdminMenuView(ui.View):
    def __init__(self, bot: commands.Bot, ctx: commands.Context):
        super().__init__(timeout=600)
        self.bot = bot
        self.ctx = ctx
        self.channel = ctx.channel
        self.guild = ctx.guild
        self.author = ctx.author

        self.update_buttons()

    # ================= [SÉCURITÉ] =================
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message("❌ Ce menu ne vous est pas destiné.", ephemeral=True)
            return False
        return True

    def update_buttons(self):
        """Met à jour le label et la couleur du premier bouton selon l'état actuel."""
        self.clear_items()
        
        is_private = is_channel_private(self.channel, self.guild)

        # Bouton 1 : Toggle (Dynamique)
        if is_private:
            btn_toggle = ui.Button(label="Rendre ce salon Public", style=discord.ButtonStyle.success, emoji="🔓", custom_id="btn_toggle")
        else:
            btn_toggle = ui.Button(label="Rendre ce salon Privé", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="btn_toggle")
        
        btn_toggle.callback = self.toggle_callback

        # Boutons de blocage (Fixes)
        btn_block_cat = ui.Button(label="Bloquer une Catégorie", style=discord.ButtonStyle.secondary, emoji="📂", custom_id="btn_bcat")
        btn_block_cat.callback = self.block_cat_callback

        btn_block_chan = ui.Button(label="Bloquer des Salons", style=discord.ButtonStyle.secondary, emoji="💬", custom_id="btn_bchan")
        btn_block_chan.callback = self.block_chan_callback

        self.add_item(btn_toggle)
        self.add_item(btn_block_cat)
        self.add_item(btn_block_chan)

    def generate_embed(self) -> discord.Embed:
        is_private = is_channel_private(self.channel, self.guild)
        etat = "🔴 **PRIVÉ** (Invisible pour les membres)" if is_private else "🟢 **PUBLIC** (Visible par défaut)"

        desc = (
            f"**Salon actuel :** {self.channel.mention}\n"
            f"**État du salon :** {etat}\n\n"
            f"Utilisez les boutons ci-dessous pour gérer l'accessibilité de vos salons.\n"
            f"*(Note : Bloquer via ID modifie les permissions du rôle @everyone)*"
        )

        if config_manager:
            return config_manager.get_formatted_embed(
                guild=self.guild, user=self.author, bot=self.bot, 
                title="🛡️ Panel d'Administration Rapide", description=desc
            )
        else:
            color = 0xe74c3c if is_private else 0x2ecc71
            return discord.Embed(title="🛡️ Panel d'Administration Rapide", description=desc, color=color)

    # --- CALLBACKS ---
    async def toggle_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        everyone_role = self.guild.default_role
        is_private = is_channel_private(self.channel, self.guild)

        try:
            if is_private:
                # Si c'était privé, on le rend public (On met None pour réinitialiser et suivre la catégorie)
                await self.channel.set_permissions(everyone_role, view_channel=None, reason=f"Salon rendu public par {self.author}")
            else:
                # Si c'était public, on le rend privé
                await self.channel.set_permissions(everyone_role, view_channel=False, reason=f"Salon rendu privé par {self.author}")
            
            # Mise à jour de l'interface graphique (Embed + Boutons)
            self.update_buttons()
            await interaction.edit_original_response(embed=self.generate_embed(), view=self)

        except discord.Forbidden:
            await interaction.followup.send("❌ Je n'ai pas les permissions nécessaires pour modifier ce salon.", ephemeral=True)

    async def block_cat_callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(BlockModal(self.bot, self.author, 'category'))

    async def block_chan_callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(BlockModal(self.bot, self.author, 'channel'))


# ==============================================================================
# ----------------------------- COG ADMIN --------------------------------------
# ==============================================================================

class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(
        name="admin", 
        description="Ouvre le panel d'administration pour gérer la visibilité des salons."
    )
    @commands.has_permissions(administrator=True)
    @app_commands.default_permissions(administrator=True)
    async def admin_cmd(self, ctx: commands.Context):
        """Ouvre le menu interactif de gestion des permissions basiques."""
        view = AdminMenuView(self.bot, ctx)
        embed = view.generate_embed()

        if ctx.interaction:
            await ctx.send(embed=embed, view=view)
            view.message = await ctx.interaction.original_response()
        else:
            msg = await ctx.send(embed=embed, view=view, reference=ctx.message)
            view.message = msg

    @admin_cmd.error
    async def admin_cmd_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingPermissions):
            error_msg = "❌ Vous devez être **Administrateur** pour utiliser cette commande."
            if ctx.interaction:
                await ctx.interaction.response.send_message(error_msg, ephemeral=True)
            else:
                await ctx.send(error_msg, delete_after=5)

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))