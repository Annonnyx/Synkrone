import discord
from discord import ui
from discord.ext import commands
from discord import app_commands
import traceback
from typing import Optional, Union

# ==========================================
# GESTION DES CONFIGURATIONS VAX V3[cite: 5]
# ==========================================
from utils.config_theme import config_manager
from utils.config_perm import ensure_command_permission, perm_command
from utils.config_emoji import Emoji as E

# ==========================================
# CONFIGURATION GLOBALE & DÉBOGAGE
# ==========================================
DEBUG_LOGS = True
ERROR_LOGS = True

# ==========================================
# CENTRALISATION DES EMOJIS UI
# ==========================================
EMOJI_SUCCESS = getattr(E, 'VALIDE', "âœ…")
EMOJI_ERROR = getattr(E, 'ERREUR', "âŒ")
EMOJI_WARN = getattr(E, 'ATTENTION', "âš ï¸")
EMOJI_INFO = getattr(E, 'INFO', "â„¹ï¸")
EMOJI_ROLE = getattr(E, 'ROLE', "ðŸŽ­")
EMOJI_MEMBER = getattr(E, 'PROFIL', "ðŸ‘¤")
EMOJI_ADD = getattr(E, 'AJOUTER', "âž•")
EMOJI_REMOVE = getattr(E, 'SUPPRIMER', "âž–")
EMOJI_SEARCH = getattr(E, 'RECHERCHE', "ðŸ”")
EMOJI_BULLET = "ðŸ”¹"
EMOJI_IDEA = getattr(E, 'LAMPE', "ðŸ’¡")

# ==========================================
# UTILITAIRES DE LOGS (COLORIMÉTRIE)
# ==========================================
def log_info(message: str):
    """Affiche un log d'information en bleu profond pour le suivi d'exécution."""
    if DEBUG_LOGS:
        print(f"\033[94m[INFO]\033[0m {message}")

def log_success(message: str):
    """Affiche un log de succès en vert éclatant."""
    if DEBUG_LOGS:
        print(f"\033[92m[SUCCESS]\033[0m {message}")

def log_error(message: str):
    """Affiche un log d'erreur en rouge vif. Critique pour le débogage."""
    if ERROR_LOGS:
        print(f"\033[91m[ERROR]\033[0m {message}")

# ==========================================
# VUES INTERACTIVES (LAYOUT V2)[cite: 5]
# ==========================================
class RoleCreationView(ui.LayoutView):
    """Menu interactif de création de rôle (LayoutV2)[cite: 5]."""
    def __init__(self, ctx: commands.Context, role_name: str, target_member: discord.Member, color_hex: int, footer_text: str):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.role_name = role_name
        self.target_member = target_member
        self.color_hex = color_hex
        self.footer_text = footer_text
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Sécurité d'interaction : seul l'auteur de la commande peut interagir[cite: 5, 7]."""
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message(f"{EMOJI_ERROR} Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        return True

    def _build_layout(self, title: str, description: str) -> ui.Container:
        """Génère le conteneur standardisé pour les mises à jour de vue."""
        container = ui.Container(accent_color=discord.Color(self.color_hex), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {title}"))
        container.add_item(ui.TextDisplay(description))
        
        if self.footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(self.footer_text))
            
        return container

    def _build(self):
        """Construction initiale de la vue de proposition de création."""
        self.clear_items()
        container = self._build_layout(
            title=f"{EMOJI_SEARCH} Rôle introuvable",
            description=f"Le rôle `{self.role_name}` n'existe pas sur ce serveur.\nSouhaitez-vous le créer et l'attribuer immédiatement à {self.target_member.mention} ?"
        )
        
        action_row = ui.ActionRow()
        
        btn_create = ui.Button(label="Créer le rôle", style=discord.ButtonStyle.success, emoji=EMOJI_SUCCESS)
        btn_create.callback = self.create_role
        action_row.add_item(btn_create)
        
        btn_cancel = ui.Button(label="Annuler", style=discord.ButtonStyle.danger, emoji=EMOJI_ERROR)
        btn_cancel.callback = self.cancel
        action_row.add_item(btn_cancel)
        
        container.add_item(action_row)
        self.add_item(container)

    async def create_role(self, interaction: discord.Interaction):
        """Création et attribution du rôle suite à validation."""
        try:
            new_role = await self.ctx.guild.create_role(name=self.role_name, reason=f"Auto-création par {self.ctx.author}")
            await self.target_member.add_roles(new_role, reason=f"Auto-attribution par {self.ctx.author}")
            
            log_success(f"Rôle '{self.role_name}' créé et attribué à {self.target_member.name} par {self.ctx.author}.")
            
            self.clear_items()
            # Utilisation stricte des backticks pour éviter le ping visuel
            container = self._build_layout(
                title=f"{EMOJI_SUCCESS} Création et Attribution Réussies",
                description=f"Le rôle `@{new_role.name}` a été généré et assigné avec succès à {self.target_member.mention}."
            )
            self.add_item(container)
            await interaction.response.edit_message(view=self)
            
        except discord.Forbidden:
            log_error(f"Permissions insuffisantes pour créer le rôle {self.role_name}.")
            self.clear_items()
            container = self._build_layout(f"{EMOJI_ERROR} Échec de création", "Je ne possède pas les permissions nécessaires pour créer des rôles.")
            self.add_item(container)
            await interaction.response.edit_message(view=self)
        except Exception as e:
            log_error(f"Erreur lors de la création de rôle : {e}")
            self.clear_items()
            container = self._build_layout(f"{EMOJI_ERROR} Erreur système", f"Une anomalie est survenue : `{e}`")
            self.add_item(container)
            await interaction.response.edit_message(view=self)

    async def cancel(self, interaction: discord.Interaction):
        """Annulation de l'opération."""
        self.clear_items()
        container = self._build_layout(f"{EMOJI_WARN} Opération Annulée", "La création du rôle a été abandonnée.")
        self.add_item(container)
        await interaction.response.edit_message(view=self)


# ==========================================
# COG PRINCIPAL : ADDDELROLE
# ==========================================
class AddDelRole(commands.Cog):
    """
    Système centralisé pour l'ajout et le retrait de rôles.
    Conçu avec l'architecture Vax v3 (LayoutV2, Permissions).
    """
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log_info("Initialisation du module AddDelRole (LayoutV2 strict)...")

    # --- UTILITAIRES DE RECHERCHE ---
    async def _find_member(self, ctx: commands.Context, member_input: str) -> Optional[discord.Member]:
        """Recherche algorithmique d'un membre (Mention, ID, Nom)."""
        if member_input.startswith('<@') and member_input.endswith('>'):
            try:
                member_id = int(member_input.strip('<@!>'))
                return ctx.guild.get_member(member_id)
            except ValueError:
                pass
        
        if member_input.isdigit():
            return ctx.guild.get_member(int(member_input))
        
        for member in ctx.guild.members:
            if member.name.lower() == member_input.lower() or member.display_name.lower() == member_input.lower():
                return member
        return None
    
    async def _find_role(self, ctx: commands.Context, role_input: str) -> Optional[discord.Role]:
        """Recherche algorithmique d'un rôle (Mention, ID, Nom exact ou partiel)."""
        if role_input.startswith('<@&') and role_input.endswith('>'):
            try:
                role_id = int(role_input.strip('<@&>'))
                return ctx.guild.get_role(role_id)
            except ValueError:
                pass
        
        if role_input.isdigit():
            return ctx.guild.get_role(int(role_input))
        
        for role in ctx.guild.roles:
            if role.name.lower() == role_input.lower():
                return role
        
        matching_roles = [r for r in ctx.guild.roles if role_input.lower() in r.name.lower()]
        if len(matching_roles) == 1:
            return matching_roles[0]
            
        return None

    def _build_layout_view(self, ctx: commands.Context, title: str, description: str, color_hex: int, footer_text: str) -> ui.LayoutView:
        """Générateur de vues standardisées persistantes pour les réponses[cite: 5]."""
        view = ui.LayoutView(timeout=1)
        container = ui.Container(accent_color=discord.Color(color_hex), spoiler=False)
        
        container.add_item(ui.TextDisplay(f"# {title}"))
        container.add_item(ui.TextDisplay(description))
        
        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))
            
        view.add_item(container)
        return view

    def _get_theme_data(self, ctx: commands.Context, default_color: int) -> tuple[int, str]:
        """Extrait la couleur et le footer dynamiques du serveur via config_manager[cite: 5]."""
        theme = config_manager.get_layout_v2_theme(ctx.guild.id, ctx.guild, ctx.author, self.bot)
        color = int(theme.get("color", default_color))
        footer = theme.get("footer_text", "")
        return color, footer

    # --- COMMANDE ADDROLE ---
    @perm_command(level=3)
    @commands.hybrid_command(name="addrole", description="Ajoute un rôle spécifique à un membre.")
    @app_commands.describe(member="Mention, ID ou nom du membre", role="Mention, ID ou nom du rôle")
    async def addrole(self, ctx: commands.Context, member: Optional[str] = None, *, role: Optional[str] = None):
        """Commande d'ajout de rôle (Persistante, LayoutV2)."""
        log_info(f"Exécution de addrole par {ctx.author} pour {member} -> {role}")

        if not await ensure_command_permission(ctx, command_name="addrole"):
            return

        await ctx.defer(ephemeral=False)
        
        color_err, footer = self._get_theme_data(ctx, 0xED4245)
        color_suc, _ = self._get_theme_data(ctx, 0x57F287)

        if member is None or role is None:
            view = self._build_layout_view(ctx, f"{EMOJI_ERROR} Argument manquant", f"L'usage attendu est : `{ctx.prefix}addrole [membre] [rôle]`", color_err, footer)
            return await ctx.send(view=view)

        target_member = await self._find_member(ctx, member)
        if target_member is None:
            view = self._build_layout_view(ctx, f"{EMOJI_ERROR} Membre introuvable", f"Impossible d'identifier l'utilisateur `{member}` sur le serveur.", color_err, footer)
            return await ctx.send(view=view)

        target_role = await self._find_role(ctx, role)
        
        if target_role is None:
            if role.isdigit():
                view = self._build_layout_view(ctx, f"{EMOJI_ERROR} ID introuvable", f"Aucun rôle existant avec l'ID `{role}`.", color_err, footer)
                return await ctx.send(view=view)
            
            creation_view = RoleCreationView(ctx, role, target_member, color_suc, footer)
            return await ctx.send(view=creation_view)

        if target_role.position >= ctx.author.top_role.position and ctx.author.id != ctx.guild.owner_id:
            view = self._build_layout_view(ctx, f"{EMOJI_WARN} Conflit hiérarchique", "Vous ne possédez pas les privilèges pour attribuer un rôle supérieur ou égal au vôtre.", color_err, footer)
            return await ctx.send(view=view)
            
        if target_role.position >= ctx.guild.me.top_role.position:
            view = self._build_layout_view(ctx, f"{EMOJI_WARN} Limitation système", "Ce rôle est techniquement supérieur au rôle le plus haut que je possède.", color_err, footer)
            return await ctx.send(view=view)

        try:
            if target_role in target_member.roles:
                view = self._build_layout_view(ctx, f"{EMOJI_INFO} Action inutile", f"{target_member.mention} possède déjà le rôle `@{target_role.name}`.", color_err, footer)
                return await ctx.send(view=view)
            
            await target_member.add_roles(target_role, reason=f"Attribué par {ctx.author}")
            log_success(f"Addrole : {target_role.name} ajouté à {target_member.name}.")
            
            desc = f"{EMOJI_BULLET} **Membre :** {target_member.mention}\n{EMOJI_BULLET} **Rôle ajouté :** `@{target_role.name}`"
            view = self._build_layout_view(ctx, f"{EMOJI_ADD} Rôle Attribué", desc, color_suc, footer)
            await ctx.send(view=view)
            
        except discord.Forbidden:
            view = self._build_layout_view(ctx, f"{EMOJI_ERROR} Privilèges insuffisants", "Je n'ai pas les permissions Discord natives pour gérer ce rôle.", color_err, footer)
            await ctx.send(view=view)
        except Exception as e:
            log_error(f"Crash inattendu dans addrole : {e}")
            traceback.print_exc()
            view = self._build_layout_view(ctx, f"{EMOJI_ERROR} Erreur critique", f"Une exception non gérée est survenue : `{str(e)}`", color_err, footer)
            await ctx.send(view=view)

    # --- COMMANDE DELROLE ---
    @perm_command(level=3)
    @commands.hybrid_command(name="delrole", description="Retire un rôle spécifique d'un membre.")
    @app_commands.describe(member="Mention, ID ou nom du membre", role="Mention, ID ou nom du rôle")
    async def delrole(self, ctx: commands.Context, member: Optional[str] = None, *, role: Optional[str] = None):
        """Commande de révocation de rôle (Persistante, LayoutV2)."""
        log_info(f"Exécution de delrole par {ctx.author} pour {member} -> {role}")

        if not await ensure_command_permission(ctx, command_name="delrole"):
            return

        await ctx.defer(ephemeral=False)
        
        color_err, footer = self._get_theme_data(ctx, 0xED4245)
        color_suc, _ = self._get_theme_data(ctx, 0x57F287)

        if member is None or role is None:
            view = self._build_layout_view(ctx, f"{EMOJI_ERROR} Argument manquant", f"L'usage attendu est : `{ctx.prefix}delrole [membre] [rôle]`", color_err, footer)
            return await ctx.send(view=view)

        target_member = await self._find_member(ctx, member)
        if target_member is None:
            view = self._build_layout_view(ctx, f"{EMOJI_ERROR} Membre introuvable", f"Impossible d'identifier l'utilisateur `{member}` sur le serveur.", color_err, footer)
            return await ctx.send(view=view)

        target_role = await self._find_role(ctx, role)
        
        if target_role is None:
            similar_roles = [r.name for r in ctx.guild.roles if role.lower() in r.name.lower()][:5]
            suggestions = f"\n\n{EMOJI_IDEA} **Suggestions :**\n" + "\n".join([f"{EMOJI_BULLET} `{r}`" for r in similar_roles]) if similar_roles else ""
            
            view = self._build_layout_view(ctx, f"{EMOJI_SEARCH} Rôle introuvable", f"Le rôle `{role}` n'existe pas.{suggestions}", color_err, footer)
            return await ctx.send(view=view)

        if target_role.position >= ctx.author.top_role.position and ctx.author.id != ctx.guild.owner_id:
            view = self._build_layout_view(ctx, f"{EMOJI_WARN} Conflit hiérarchique", "Vous ne possédez pas les privilèges pour retirer un rôle supérieur ou égal au vôtre.", color_err, footer)
            return await ctx.send(view=view)
            
        if target_role.position >= ctx.guild.me.top_role.position:
            view = self._build_layout_view(ctx, f"{EMOJI_WARN} Limitation système", "Ce rôle est techniquement supérieur au rôle le plus haut que je possède.", color_err, footer)
            return await ctx.send(view=view)

        try:
            if target_role not in target_member.roles:
                view = self._build_layout_view(ctx, f"{EMOJI_INFO} Action impossible", f"{target_member.mention} ne possède actuellement pas le rôle `@{target_role.name}`.", color_err, footer)
                return await ctx.send(view=view)
            
            await target_member.remove_roles(target_role, reason=f"Révoqué par {ctx.author}")
            log_success(f"Delrole : {target_role.name} retiré à {target_member.name}.")
            
            desc = f"{EMOJI_BULLET} **Membre :** {target_member.mention}\n{EMOJI_BULLET} **Rôle retiré :** `@{target_role.name}`"
            view = self._build_layout_view(ctx, f"{EMOJI_REMOVE} Rôle Révoqué", desc, color_suc, footer)
            await ctx.send(view=view)
            
        except discord.Forbidden:
            view = self._build_layout_view(ctx, f"{EMOJI_ERROR} Privilèges insuffisants", "Je n'ai pas les permissions Discord natives pour modifier ce rôle.", color_err, footer)
            await ctx.send(view=view)
        except Exception as e:
            log_error(f"Crash inattendu dans delrole : {e}")
            traceback.print_exc()
            view = self._build_layout_view(ctx, f"{EMOJI_ERROR} Erreur critique", f"Une exception non gérée est survenue : `{str(e)}`", color_err, footer)
            await ctx.send(view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(AddDelRole(bot))
    log_success("Module 'AddDelRole' compilé et chargé, mentions désactivées.")
