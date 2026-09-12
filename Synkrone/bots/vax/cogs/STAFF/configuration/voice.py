import discord
from discord import ui
from discord.ext import commands
import traceback
from typing import Optional

# ==============================================================================
# --- IMPORTS MÉTIER VAX ---
# Utilisation stricte de nos gestionnaires internes.
# ==============================================================================
try:
    from utils.config_data import DataManager
    from utils.config_theme import config_manager
    from utils.config_perm import ensure_command_permission, perm_command
    from utils.config_emoji import Emoji as E
    HAS_VAX_CORE = True
except ImportError as e:
    HAS_VAX_CORE = False
    print(f"\033[91m[ERREUR CRITIQUE] Impossible d'importer le noyau Vax : {e}\033[0m")

# ==============================================================================
# --- CONFIGURATION GLOBALE & DÉBOGAGE ---
# ==============================================================================
DEBUG_LOGS = True
ERROR_LOGS_ONLY = False

# ==============================================================================
# --- CENTRALISATION DES EMOJIS ---
# ==============================================================================
E_ON = getattr(E, 'VALIDER', "🟢") if HAS_VAX_CORE else "🟢"
E_OFF = getattr(E, 'REFUSER', "🔴") if HAS_VAX_CORE else "🔴"
E_WARN = getattr(E, 'ATTENTION', "⚠️") if HAS_VAX_CORE else "⚠️"
E_GEAR = getattr(E, 'MODIFIER', "⚙️") if HAS_VAX_CORE else "⚙️"
E_VOICE = getattr(E, 'VOCAL', "🔊") if HAS_VAX_CORE else "🔊"
E_CTRL = getattr(E, 'MODIFIER', "⚙️") if HAS_VAX_CORE else "⚙️"
E_VISIBILITY = getattr(E, 'RECHERCHE', "🔎") if HAS_VAX_CORE else "🔎"
E_LOCK = getattr(E, 'LOCK', "🔒") if HAS_VAX_CORE else "🔒"
E_UNLOCK = getattr(E, 'UNLOCK', "🔓") if HAS_VAX_CORE else "🔓"
E_USERS = getattr(E, 'ROLE', "👥") if HAS_VAX_CORE else "👥"
E_BAN = getattr(E, 'BOUCLIER', "🛡️") if HAS_VAX_CORE else "🛡️"
E_BACK = getattr(E, 'RETOUR', "↩️") if HAS_VAX_CORE else "↩️"
E_TRASH = getattr(E, 'SUPPRIMER', "🗑️") if HAS_VAX_CORE else "🗑️"
E_CHAN = getattr(E, 'LIEN', "📍") if HAS_VAX_CORE else "📍"
E_ID = getattr(E, 'IDENTIFIANT', "🆔") if HAS_VAX_CORE else "🆔"
E_ADD = getattr(E, 'AJOUTER', "➕") if HAS_VAX_CORE else "➕"
E_DOC = getattr(E, 'DOCUMENT', "📄") if HAS_VAX_CORE else "📄"

# ==============================================================================
# --- UTILITAIRES DE LOGS ---
# ==============================================================================
def log_sys(action: str, message: str, is_error: bool = False):
    """Système de logs dynamiques respectant les variables globales de débogage."""
    if ERROR_LOGS_ONLY and not is_error:
        return
    if not DEBUG_LOGS and not is_error:
        return

    COLOR_RESET = "\033[0m"
    COLOR_INFO = "\033[96m"   # Cyan
    COLOR_ERROR = "\033[91m"   # Rouge
    color = COLOR_ERROR if is_error else COLOR_INFO
    prefix = "[ERREUR Vocal]" if is_error else "[INFO Vocal]"
    
    print(f"{color}{prefix} [{action}] {message}{COLOR_RESET}")

# ==============================================================================
# --- GESTIONNAIRE DE DONNÉES (DataManager) ---
# ==============================================================================
class TempVoiceConfigManager:
    def __init__(self):
        if HAS_VAX_CORE:
            self.data = DataManager("staff/configuration/data_temp_voice")
        else:
            log_sys("INIT", "DataManager introuvable. Échec système.", is_error=True)

    def get_default_config(self):
        return {
            "root_id": None,
            "actives": {}
        }

    def load(self, guild_id: int) -> dict:
        try:
            raw = self.data.load(guild_id) or {}
            return {**self.get_default_config(), **raw}
        except Exception:
            return self.get_default_config()

    def save(self, guild_id: int, config: dict):
        self.data.save(guild_id, config)

voice_db = TempVoiceConfigManager()

# ==============================================================================
# --- MODALS UTILISATEUR ---
# ==============================================================================
class VoiceChannelModal(ui.Modal, title="Lier par ID de Salon"):
    id_input = ui.TextInput(label="ID du Salon", placeholder="Collez l'ID ici...", min_length=15, max_length=25)
    
    def __init__(self, view: "SetupLayoutView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        raw_id = self.id_input.value.strip()
        if not raw_id.isdigit():
            return await interaction.response.send_message(f"{E_OFF} L'ID fourni n'est pas un nombre valide.", ephemeral=True)
            
        target = interaction.guild.get_channel(int(raw_id))
        if not target or target.type != discord.ChannelType.voice:
            return await interaction.response.send_message(f"{E_OFF} Vous devez spécifier l'ID d'un salon **vocal** valide.", ephemeral=True)

        conf = voice_db.load(self.view.guild.id)
        conf['root_id'] = target.id
        voice_db.save(self.view.guild.id, conf)
        
        self.view.status_message = f"{E_ON} Salon vocal générateur lié avec succès."
        self.view.active_sub_menu = None
        await self.view._refresh(interaction)

class LimitModal(ui.Modal, title="Modifier la limite du vocal"):
    limit = ui.TextInput(label="Nombre de places (0 = illimité)", placeholder="Ex: 5", max_length=2, required=True)
    
    def __init__(self, channel: discord.VoiceChannel, view: "VoiceControlLayoutView"):
        super().__init__()
        self.channel = channel
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.limit.value)
            if 0 <= val <= 99:
                await self.channel.edit(user_limit=val)
                log_sys("LIMIT_EDIT", f"Limite modifiée à {val} pour le salon {self.channel.id}")
                
                self.view.status_message = f"{E_ON} Limite du salon mise à jour à **{val if val > 0 else 'Illimité'}** places."
                await self.view._refresh(interaction)
            else:
                await interaction.response.send_message(f"{E_OFF} {interaction.user.mention}, le nombre doit être compris entre 0 et 99.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message(f"{E_OFF} {interaction.user.mention}, veuillez entrer un nombre valide.", ephemeral=True)
        except Exception as e:
            log_sys("MODAL_LIMIT", f"Erreur critique: {e}", is_error=True)
            await interaction.response.send_message(f"{E_OFF} Une erreur inattendue est survenue.", ephemeral=True)

class BanModal(ui.Modal, title="Bannir un utilisateur"):
    user_id = ui.TextInput(label="ID de l'utilisateur", placeholder="Collez l'ID Discord ici...", min_length=15, required=True)
    
    def __init__(self, channel: discord.VoiceChannel, view: "VoiceControlLayoutView"):
        super().__init__()
        self.channel = channel
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        guild = self.channel.guild
        try:
            target_id = int(self.user_id.value.strip())
            target = guild.get_member(target_id)
            
            if not target:
                await interaction.response.send_message(f"{E_WARN} {interaction.user.mention}, cet utilisateur est introuvable sur le serveur.", ephemeral=True)
                return
            
            await self.channel.set_permissions(target, connect=False, view_channel=False)
            if target in self.channel.members:
                await target.move_to(None)
            
            log_sys("VOICE_BAN", f"{target.name} banni du salon {self.channel.id}")
            
            self.view.status_message = f"{E_BAN} L'utilisateur **{target.display_name}** a été banni du vocal."
            await self.view._refresh(interaction)
            
        except ValueError:
            await interaction.response.send_message(f"{E_OFF} {interaction.user.mention}, l'ID fourni n'est pas un nombre valide.", ephemeral=True)
        except Exception as e:
            log_sys("MODAL_BAN", f"Erreur critique: {e}", is_error=True)
            await interaction.response.send_message(f"{E_OFF} Impossible d'appliquer le bannissement.", ephemeral=True)

# ==============================================================================
# --- SELECTEURS D'OPTIONS (Layout V2) ---
# ==============================================================================
class VoiceOptionsSelect(ui.Select):
    def __init__(self, parent_view: "SetupLayoutView", is_default: bool):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(label="Configurer le salon", value="channel", emoji=E_CHAN, description="Sélectionner, lier ou auto-générer le salon racine"),
        ]
        if not is_default:
            options.append(discord.SelectOption(label="Réinitialiser", value="reset", emoji=E_TRASH, description="Désactiver et remettre à zéro le système"))
            
        super().__init__(placeholder="Options de configuration...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val == "channel":
            self.parent_view.active_sub_menu = "channel"
            await self.parent_view._refresh(interaction)
        elif val == "reset":
            await self.parent_view._on_reset(interaction)


# ==============================================================================
# --- INTERFACE D'ADMINISTRATION (Layout V2) ---
# ==============================================================================
class SetupLayoutView(ui.LayoutView):
    """LayoutV2 d'administration pour la gestion du salon racine."""
    def __init__(self, cog: "TemporaryVoice", guild: discord.Guild, author: discord.Member):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild = guild
        self.author = author
        self.status_message = ""
        self.active_sub_menu: str | None = None
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            if not interaction.response.is_done(): await interaction.response.defer()
            await interaction.channel.send(f"{E_OFF} Cette interface d'administration ne vous appartient pas.", ephemeral=True)
            return False
        return True

    def _build(self):
        self.clear_items()
        config = voice_db.load(self.guild.id)
        
        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.author, self.cog.bot)
        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text", "")
        
        is_enabled = bool(config.get('root_id')) and self.guild.get_channel(config['root_id']) is not None
        state_text = f"{E_ON} `Activé`" if is_enabled else f"{E_OFF} `Désactivé`"
        chan_txt = f"<#{config['root_id']}>" if is_enabled else "`Non configuré`"

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {E_VOICE} Déploiement Vocal Temporaire"))
        
        if self.status_message:
            container.add_item(ui.TextDisplay(f"> {self.status_message}"))
            self.status_message = ""

        container.add_item(ui.TextDisplay(
            f"**État du système :** {state_text}\n"
            f"**Salon racine :** {chan_txt}\n\n"
            f"Sélectionnez une option ci-dessous pour configurer le générateur de salons vocaux."
        ))

        # Sélecteur principal
        row_main = ui.ActionRow()
        is_default = not config.get('root_id')
        opt_select = VoiceOptionsSelect(self, is_default)
        row_main.add_item(opt_select)
        container.add_item(row_main)

        # Sous-menus dynamiques
        if self.active_sub_menu == "channel":
            row_chan = ui.ActionRow()
            chan_select = ui.ChannelSelect(
                placeholder="Sélectionner un salon vocal d'origine...",
                min_values=1, max_values=1,
                channel_types=[discord.ChannelType.voice]
            )
            chan_select.callback = self._on_chan_selected
            row_chan.add_item(chan_select)
            container.add_item(row_chan)

            row_id = ui.ActionRow()
            btn_id = ui.Button(label="Lier par ID", style=discord.ButtonStyle.secondary, emoji=E_ID)
            btn_id.callback = self._on_chan_id_manual
            row_id.add_item(btn_id)
            
            btn_auto = ui.Button(label="Générer", style=discord.ButtonStyle.primary, emoji=E_ADD)
            btn_auto.callback = self._on_chan_auto_create
            row_id.add_item(btn_auto)
            
            container.add_item(row_id)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    async def _refresh(self, interaction: discord.Interaction):
        self._build()
        if interaction.response.is_done():
            await interaction.edit_original_response(view=self)
        else:
            await interaction.response.edit_message(view=self)

    # --- CALLBACKS SOUS-MENUS ---
    async def _on_chan_selected(self, interaction: discord.Interaction):
        chan_id = int(interaction.data['values'][0])
        conf = voice_db.load(self.guild.id)
        conf['root_id'] = chan_id
        voice_db.save(self.guild.id, conf)
        self.status_message = f"{E_ON} Salon vocal générateur sélectionné avec succès."
        self.active_sub_menu = None
        await self._refresh(interaction)

    async def _on_chan_id_manual(self, interaction: discord.Interaction):
        self.active_sub_menu = None
        await interaction.response.send_modal(VoiceChannelModal(self))

    async def _on_chan_auto_create(self, interaction: discord.Interaction):
        if not interaction.response.is_done():
            await interaction.response.defer()
        
        try:
            channel = await interaction.guild.create_voice_channel(f"➕│Créer vocal", category=interaction.channel.category, user_limit=1)
            conf = voice_db.load(self.guild.id)
            conf['root_id'] = channel.id
            voice_db.save(self.guild.id, conf)
            
            self.status_message = f"{E_ON} Salon racine généré automatiquement avec succès."
        except Exception as e:
            self.status_message = f"{E_OFF} Impossible de créer le salon : {e}"
            
        self.active_sub_menu = None
        await self._refresh(interaction)

    async def _on_reset(self, interaction: discord.Interaction):
        self.active_sub_menu = None
        config = voice_db.load(self.guild.id)
        
        # Suppression du salon si existant
        if config.get("root_id"):
            chan = self.guild.get_channel(config["root_id"])
            if chan:
                try: await chan.delete()
                except: pass
                
        voice_db.save(self.guild.id, voice_db.get_default_config())
        self.status_message = f"{E_TRASH} Configuration réinitialisée, le salon racine a été supprimé."
        await self._refresh(interaction)


class VoiceControlLayoutView(ui.LayoutView):
    """LayoutV2 gérant le panneau de contrôle dans le salon vocal temp de l'utilisateur."""
    def __init__(self, bot: commands.Bot, guild: discord.Guild, owner: discord.Member, channel_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild = guild
        self.owner = owner
        self.channel_id = channel_id
        self.status_message = ""
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message(f"{E_OFF} Action refusée : ce panneau appartient exclusivement à {self.owner.mention}.", ephemeral=True)
            return False
        return True

    def _build(self):
        self.clear_items()
        
        channel = self.guild.get_channel(self.channel_id)
        if not channel:
            return 
            
        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.owner, self.bot)
        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text", "")

        everyone_role = self.guild.default_role
        overwrites = channel.overwrites_for(everyone_role)
        
        vis_state = f"{E_ON} Visible" if overwrites.view_channel is not False else f"{E_OFF} Masqué"
        acc_state = f"{E_ON} Ouvert" if overwrites.connect is not False else f"{E_LOCK} Verrouillé"
        lim_state = f"{channel.user_limit} places" if channel.user_limit > 0 else "∞ Illimitée"
        
        member_list = "\n".join([f"- {m.display_name}" for m in channel.members]) or "- *Vocal vide*"
        bans = [f"- {obj.display_name}" for obj, ow in channel.overwrites.items() if isinstance(obj, discord.Member) and ow.connect is False]
        banlist_str = "\n".join(bans) or "- *Aucun banni*"

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        container.add_item(ui.TextDisplay(f"# {E_CTRL} Centre de contrôle de {self.owner.mention}"))
        
        if self.status_message:
            container.add_item(ui.TextDisplay(f"> {self.status_message}"))
            self.status_message = ""
            
        container.add_item(ui.TextDisplay(
            f"### {E_GEAR} Sécurité et Accès\n"
            f"- **Visibilité** : {vis_state}\n"
            f"- **Accès** : {acc_state}\n"
            f"- **Capacité** : {lim_state}\n\n"
            f"### {E_USERS} Connectés actuels\n{member_list}\n\n"
            f"### {E_BAN} Liste noire\n{banlist_str}"
        ))

        action_row = ui.ActionRow()

        vis_btn = ui.Button(label="Visibilité", style=discord.ButtonStyle.secondary, emoji=E_VISIBILITY)
        vis_btn.callback = self.toggle_visibility
        action_row.add_item(vis_btn)

        lock_btn = ui.Button(label="Verrouillage", style=discord.ButtonStyle.secondary, emoji=E_LOCK)
        lock_btn.callback = self.toggle_lock
        action_row.add_item(lock_btn)

        limit_btn = ui.Button(label="Places", style=discord.ButtonStyle.secondary, emoji=E_USERS)
        limit_btn.callback = self.set_limit
        action_row.add_item(limit_btn)

        ban_btn = ui.Button(label="Bannir", style=discord.ButtonStyle.danger, emoji=E_BAN)
        ban_btn.callback = self.ban_user
        action_row.add_item(ban_btn)

        container.add_item(action_row)

        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))

        self.add_item(container)

    async def _refresh(self, interaction: discord.Interaction):
        self._build()
        if interaction.response.is_done():
            await interaction.edit_original_response(view=self)
        else:
            await interaction.response.edit_message(view=self)

    async def toggle_visibility(self, interaction: discord.Interaction):
        channel = self.guild.get_channel(self.channel_id)
        if not channel: return
        everyone = self.guild.default_role
        is_visible = channel.overwrites_for(everyone).view_channel
        
        await channel.set_permissions(everyone, view_channel=False if is_visible is not False else True)
        self.status_message = f"{E_ON} La visibilité de ton salon a été modifiée."
        await self._refresh(interaction)

    async def toggle_lock(self, interaction: discord.Interaction):
        channel = self.guild.get_channel(self.channel_id)
        if not channel: return
        everyone = self.guild.default_role
        can_join = channel.overwrites_for(everyone).connect
        
        await channel.set_permissions(everyone, connect=False if can_join is not False else True)
        self.status_message = f"{E_ON} L'accès à ton salon a été modifié."
        await self._refresh(interaction)

    async def set_limit(self, interaction: discord.Interaction):
        channel = self.guild.get_channel(self.channel_id)
        if channel:
            await interaction.response.send_modal(LimitModal(channel, self))

    async def ban_user(self, interaction: discord.Interaction):
        channel = self.guild.get_channel(self.channel_id)
        if channel:
            await interaction.response.send_modal(BanModal(channel, self))


# ==============================================================================
# --- COG PRINCIPAL ---
# ==============================================================================
class TemporaryVoice(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log_sys("INIT", "Module Vocaux Temporaires en ligne et arrimé.")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot: return
        
        config = voice_db.load(member.guild.id)
        root_id = config.get("root_id")
        
        # 1. GÉNÉRATION DU SALON
        if after.channel and after.channel.id == root_id:
            log_sys("EVENT_JOIN", f"{member.name} déclenche la création d'un salon.")
            
            user_str_id = str(member.id)
            if user_str_id in config["actives"]:
                existing_chan = member.guild.get_channel(config["actives"][user_str_id])
                if existing_chan:
                    log_sys("EVENT_REDIRECT", f"Redirection de {member.name} vers son instance existante.")
                    return await member.move_to(existing_chan)

            try:
                overwrites = {
                    member.guild.default_role: discord.PermissionOverwrite(view_channel=True, connect=True),
                    member: discord.PermissionOverwrite(manage_channels=True, connect=True, view_channel=True, move_members=True)
                }
                new_channel = await member.guild.create_voice_channel(
                    name=f"🔊 {member.display_name}", 
                    category=after.channel.category, 
                    overwrites=overwrites
                )
                
                config["actives"][user_str_id] = new_channel.id
                voice_db.save(member.guild.id, config)
                await member.move_to(new_channel)
                
                log_sys("CHANNEL_UP", f"Instance {new_channel.id} déployée pour {member.name}")

                view = VoiceControlLayoutView(self.bot, member.guild, member, new_channel.id)
                # Envoi EXCLUSIF de la view pour respecter la norme IS_COMPONENTS_V2. 
                await new_channel.send(view=view)
                
            except Exception as e:
                log_sys("CHANNEL_ERROR", f"Crash au déploiement pour {member.name}: {e}", is_error=True)
                traceback.print_exc()

        # 2. NETTOYAGE DU SALON
        if before.channel:
            owner_id_str = next((k for k, v in config["actives"].items() if v == before.channel.id), None)
            
            if owner_id_str and len(before.channel.members) == 0:
                try:
                    await before.channel.delete()
                    log_sys("CHANNEL_DOWN", f"Instance {before.channel.id} détruite (vidée).")
                    
                    del config["actives"][owner_id_str]
                    voice_db.save(member.guild.id, config)
                except Exception as e:
                    log_sys("CHANNEL_CLEANUP_ERR", f"Échec de suppression {before.channel.id}: {e}", is_error=True)

    @perm_command(level=2)
    @commands.hybrid_command(name="voice", description="Menu d'administration des salons vocaux temporaires.")
    async def voice_cmd(self, ctx: commands.Context):
        if not ctx.guild:
            await ctx.send(f"{E_OFF} Cette commande exige un contexte serveur.")
            return

        if HAS_VAX_CORE and not await ensure_command_permission(ctx, command_name="voice"):
            return
            
        log_sys("COMMAND", f"Lancement de /voice par {ctx.author}")
        view = SetupLayoutView(self, ctx.guild, ctx.author)
        await ctx.send(view=view)

async def setup(bot: commands.Bot):
    if bot.get_command("voice"):
        bot.remove_command("voice")
    await bot.add_cog(TemporaryVoice(bot))