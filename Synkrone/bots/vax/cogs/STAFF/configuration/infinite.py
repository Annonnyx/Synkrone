import discord
from discord import ui
from discord.ext import commands
import asyncio
import re
import aiohttp
import traceback
from pathlib import Path
from typing import Optional, Dict, Any

# ==============================================================================
# --- IMPORTS MÉTIER VAX ---
# Utilisation stricte de l'écosystème pour garantir l'homogénéité globale.
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
E_TRASH = getattr(E, 'SUPPRIMER', "🗑️") if HAS_VAX_CORE else "🗑️"
E_CHAN = getattr(E, 'LIEN', "📍") if HAS_VAX_CORE else "📍"
E_DOC = getattr(E, 'DOCUMENT', "📄") if HAS_VAX_CORE else "📄"
E_ID = getattr(E, 'IDENTIFIANT', "🆔") if HAS_VAX_CORE else "🆔"
E_NUM = getattr(E, 'LISTE', "🔢") if HAS_VAX_CORE else "🔢"

# ==============================================================================
# --- UTILITAIRES DE LOGS ---
# ==============================================================================
def log_sys(action: str, message: str, is_error: bool = False):
    if ERROR_LOGS_ONLY and not is_error: return
    if not DEBUG_LOGS and not is_error: return
    color = "\033[91m" if is_error else "\033[96m"
    prefix = "[ERREUR Infinite]" if is_error else "[INFO Infinite]"
    print(f"{color}{prefix} [{action}] {message}\033[0m")

# ==============================================================================
# --- GESTIONNAIRE DE DONNÉES (DataManager) ---
# ==============================================================================
class InfiniteManager:
    """Interface de sauvegarde s'appuyant sur l'infrastructure standard."""
    def __init__(self):
        if HAS_VAX_CORE:
            self.data = DataManager("staff/configuration/data_infinite")
        else:
            log_sys("INIT", "DataManager introuvable. Échec système.", is_error=True)

    def get_default_config(self):
        return {
            "channel_id": None,
            "current_number": 0,
            "last_user_id": None,
            "reaction_emoji": "✅",
            "hardcore_mode": False
        }

    def load(self, guild_id: int) -> dict:
        try:
            raw = self.data.load(guild_id) or {}
            return {**self.get_default_config(), **raw}
        except Exception as e:
            log_sys("DB_LOAD", f"Erreur de lecture DB pour {guild_id}: {e}", is_error=True)
            return self.get_default_config()

    def save(self, guild_id: int, config: dict):
        try:
            self.data.save(guild_id, config)
        except Exception as e:
            log_sys("DB_SAVE", f"Erreur d'écriture DB pour {guild_id}: {e}", is_error=True)

infinite_db = InfiniteManager()

# ==============================================================================
# --- MODALS UTILISATEUR ---
# ==============================================================================
class InfiniteChannelModal(ui.Modal, title="Lier par ID de Salon"):
    id_input = ui.TextInput(label="ID du Salon", placeholder="Collez l'ID ici...", min_length=15, max_length=25)
    
    def __init__(self, view: "InfiniteLayoutView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        raw_id = self.id_input.value.strip()
        if not raw_id.isdigit():
            return await interaction.response.send_message(f"{E_OFF} L'ID fourni n'est pas un nombre valide.", ephemeral=True)
            
        target = interaction.guild.get_channel(int(raw_id))
        if not target or target.type not in {discord.ChannelType.text, discord.ChannelType.news}:
            return await interaction.response.send_message(f"{E_OFF} Salon textuel introuvable.", ephemeral=True)

        conf = infinite_db.load(self.view.guild.id)
        conf['channel_id'] = target.id
        infinite_db.save(self.view.guild.id, conf)
        
        self.view.status_message = f"{E_ON} Salon du jeu de comptage lié avec succès."
        self.view.active_sub_menu = None
        await self.view._refresh(interaction)

class InfiniteNumberModal(ui.Modal, title="Modifier le nombre actuel"):
    num_input = ui.TextInput(label="Nouveau nombre", placeholder="0", max_length=10, required=True)

    def __init__(self, view: "InfiniteLayoutView"):
        super().__init__()
        self.view = view
        config = infinite_db.load(self.view.guild.id)
        self.num_input.default = str(config.get('current_number', 0))

    async def on_submit(self, interaction: discord.Interaction):
        val = self.num_input.value.strip()
        if not val.isdigit():
            return await interaction.response.send_message(f"{E_OFF} Vous devez entrer un nombre valide.", ephemeral=True)

        config = infinite_db.load(self.view.guild.id)
        config['current_number'] = int(val)
        config['last_user_id'] = None # Permet à n'importe qui de reprendre
        infinite_db.save(self.view.guild.id, config)
        
        self.view.status_message = f"{E_ON} Le nombre actuel a été défini sur **{val}**."
        self.view.active_sub_menu = None
        await self.view._refresh(interaction)


# ==============================================================================
# --- SELECTEURS D'OPTIONS (Layout V2) ---
# ==============================================================================
class InfiniteOptionsSelect(ui.Select):
    def __init__(self, parent_view: "InfiniteLayoutView", is_default: bool):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(label="Configurer le salon", value="channel", emoji=E_CHAN, description="Définir le salon du jeu"),
            discord.SelectOption(label="Modifier le nombre", value="number", emoji=E_NUM, description="Reprendre à partir d'un chiffre précis"),
            discord.SelectOption(label="Emoji de validation", value="emoji", emoji=E_ON, description="Modifier l'émoji de succès"),
            discord.SelectOption(label="Mode Hardcore", value="hardcore", emoji=E_WARN, description="Retour à zéro à la moindre erreur"),
        ]
        if not is_default:
            options.append(discord.SelectOption(label="Réinitialiser", value="reset", emoji=E_TRASH, description="Désactiver et remettre à zéro le jeu"))
            
        super().__init__(placeholder="Options de configuration...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val == "channel":
            self.parent_view.active_sub_menu = "channel"
            await self.parent_view._refresh(interaction)
        elif val == "number":
            await self.parent_view._on_number_config(interaction)
        elif val == "emoji":
            await self.parent_view._on_emoji_config(interaction)
        elif val == "hardcore":
            await self.parent_view._on_hardcore_toggle(interaction)
        elif val == "reset":
            await self.parent_view._on_reset(interaction)

# ==============================================================================
# --- INTERFACE D'ADMINISTRATION (Layout V2) ---
# ==============================================================================
class InfiniteLayoutView(ui.LayoutView):
    """Panneau de contrôle de l'administration du jeu de comptage infini."""
    def __init__(self, cog: "InfiniteCog", guild: discord.Guild, user: discord.Member):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild = guild
        self.user = user
        self.status_message = ""
        self.active_sub_menu: str | None = None
        self.wait_task: Optional[asyncio.Task] = None
        self.waiting_for_emoji = False
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            if not interaction.response.is_done(): await interaction.response.defer()
            await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, cette interface est verrouillée.", delete_after=6)
            return False
        return True

    def _build(self):
        self.clear_items()
        config = infinite_db.load(self.guild.id)
        
        theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.cog.bot)
        accent_color = int(theme.get("color", discord.Color.blurple().value))
        footer_text = theme.get("footer_text", "")

        container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
        
        # Gestion du mode attente d'émoji via le chat
        if self.waiting_for_emoji:
            container.add_item(ui.TextDisplay(f"# {getattr(E, 'TEMPS', '⏳')} En attente d'un émoji..."))
            container.add_item(ui.TextDisplay(
                f"Veuillez envoyer un **émoji** (basique ou custom) directement dans ce salon.\n\n"
                "-# S'il s'agit d'un émoji personnalisé inaccessible, le bot le téléchargera et le copiera sur votre serveur pour l'utiliser.\n"
                "-# Vous avez 2 minutes. Le message sera automatiquement intercepté."
            ))
            
            wait_row = ui.ActionRow()
            btn_cancel = ui.Button(label="Annuler", style=discord.ButtonStyle.secondary, emoji=getattr(E, "RETOUR", "↩️"))
            btn_cancel.callback = self.cancel_wait_callback
            wait_row.add_item(btn_cancel)
            container.add_item(wait_row)
            self.add_item(container)
            return

        is_enabled = bool(config.get('channel_id')) and self.guild.get_channel(config['channel_id']) is not None
        statut_txt = f"{E_ON} `Activé`" if is_enabled else f"{E_OFF} `Désactivé`"
        salon_txt = f"<#{config['channel_id']}>" if config.get('channel_id') else "`Non configuré`"
        hardcore_txt = f"{E_ON} `Activé`" if config.get('hardcore_mode') else f"{E_OFF} `Désactivé`"
        last_user = f"<@{config.get('last_user_id')}>" if config.get('last_user_id') else "`Aucun`"
        
        container.add_item(ui.TextDisplay(f"# {E_DOC} Jeu du Compteur Infini"))
        
        if self.status_message:
            container.add_item(ui.TextDisplay(f"> {self.status_message}"))
            self.status_message = ""

        container.add_item(ui.TextDisplay(
            f"**État du système :** {statut_txt}\n"
            f"**Salon d'ancrage :** {salon_txt}\n"
            f"**Mode Hardcore :** {hardcore_txt}\n\n"
            f"### {E_NUM} Données en cours\n"
            f"- **Nombre actuel :** `{config.get('current_number', 0)}`\n"
            f"- **Dernier joueur :** {last_user}\n"
            f"- **Emoji de succès :** {config.get('reaction_emoji', '✅')}"
        ))

        # Sélecteur principal
        row_main = ui.ActionRow()
        is_default = not config.get('channel_id') and config.get('current_number') == 0 and not config.get('hardcore_mode')
        opt_select = InfiniteOptionsSelect(self, is_default)
        row_main.add_item(opt_select)
        container.add_item(row_main)

        # Sous-menus dynamiques
        if self.active_sub_menu == "channel":
            row_chan = ui.ActionRow()
            chan_select = ui.ChannelSelect(
                placeholder="Sélectionner le salon du jeu...",
                min_values=1, max_values=1,
                channel_types=[discord.ChannelType.text, discord.ChannelType.news]
            )
            chan_select.callback = self._on_chan_selected
            row_chan.add_item(chan_select)
            container.add_item(row_chan)

            row_id = ui.ActionRow()
            btn_id = ui.Button(label="Lier par ID", style=discord.ButtonStyle.secondary, emoji=E_ID)
            btn_id.callback = self._on_chan_id_manual
            row_id.add_item(btn_id)
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
        conf = infinite_db.load(self.guild.id)
        conf['channel_id'] = chan_id
        infinite_db.save(self.guild.id, conf)
        self.status_message = f"{E_ON} Salon du jeu de comptage sélectionné avec succès."
        self.active_sub_menu = None
        await self._refresh(interaction)

    async def _on_chan_id_manual(self, interaction: discord.Interaction):
        self.active_sub_menu = None
        await interaction.response.send_modal(InfiniteChannelModal(self))

    async def _on_number_config(self, interaction: discord.Interaction):
        self.active_sub_menu = None
        await interaction.response.send_modal(InfiniteNumberModal(self))

    async def _on_emoji_config(self, interaction: discord.Interaction):
        self.active_sub_menu = None
        self.waiting_for_emoji = True
        self._build()
        await interaction.response.edit_message(view=self)
        self.wait_task = asyncio.create_task(self.wait_for_emoji_task(interaction))

    async def _on_hardcore_toggle(self, interaction: discord.Interaction):
        self.active_sub_menu = None
        conf = infinite_db.load(self.guild.id)
        conf['hardcore_mode'] = not conf.get('hardcore_mode', False)
        infinite_db.save(self.guild.id, conf)
        self.status_message = f"{E_ON} Mode Hardcore {'activé' if conf['hardcore_mode'] else 'désactivé'}."
        await self._refresh(interaction)

    async def _on_reset(self, interaction: discord.Interaction):
        self.active_sub_menu = None
        infinite_db.save(self.guild.id, infinite_db.get_default_config())
        self.status_message = f"{E_TRASH} Jeu réinitialisé et module désactivé."
        await self._refresh(interaction)

    async def cancel_wait_callback(self, interaction: discord.Interaction):
        if self.wait_task:
            self.wait_task.cancel()
        self.waiting_for_emoji = False
        self.active_sub_menu = None
        await self._refresh(interaction)

    async def wait_for_emoji_task(self, interaction: discord.Interaction):
        """Attente d'un emoji via le chat et copie automatique si inaccessible."""
        def check(m):
            return m.author.id == self.user.id and m.channel.id == interaction.channel.id

        try:
            msg = await self.cog.bot.wait_for('message', check=check, timeout=120.0)
            
            final_emoji = None
            match = re.search(r'<(a?):([a-zA-Z0-9_]+):([0-9]+)>', msg.content)
            
            if match:
                is_animated = bool(match.group(1))
                name = match.group(2)
                emoji_id = int(match.group(3))
                
                emoji_obj = self.cog.bot.get_emoji(emoji_id)
                if emoji_obj and emoji_obj.is_usable():
                    final_emoji = str(emoji_obj)
                    self.status_message = f"{E_ON} L'émoji de validation a été mis à jour."
                else:
                    # Copier l'emoji localement sur le serveur actuel
                    ext = "gif" if is_animated else "png"
                    url = f"https://cdn.discordapp.com/emojis/{emoji_id}.{ext}"
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url) as resp:
                            if resp.status == 200:
                                image_bytes = await resp.read()
                                try:
                                    new_emoji = await self.guild.create_custom_emoji(name=name, image=image_bytes)
                                    final_emoji = str(new_emoji)
                                    self.status_message = f"{E_ON} L'émoji a été importé sur ce serveur et défini avec succès."
                                except discord.Forbidden:
                                    self.status_message = f"{E_OFF} Je n'ai pas la permission de créer un émoji sur ce serveur."
                                except Exception as e:
                                    self.status_message = f"{E_OFF} Erreur lors de la création de l'émoji : limite de slots atteinte ou erreur API."
                            else:
                                self.status_message = f"{E_OFF} Impossible de télécharger l'émoji source."
            else:
                # Emojis standards Unicode
                final_emoji = msg.content.strip()
                self.status_message = f"{E_ON} L'émoji de validation a été mis à jour."
                
            try: await msg.delete()
            except: pass

            if final_emoji:
                conf = infinite_db.load(self.guild.id)
                conf['reaction_emoji'] = final_emoji
                infinite_db.save(self.guild.id, conf)

                # Test dans le chat
                try:
                    await interaction.channel.send(f"Test de l'émoji de validation : {final_emoji}", delete_after=5)
                except Exception:
                    pass

        except asyncio.TimeoutError:
            self.status_message = f"{E_WARN} Délai d'attente expiré."
        except asyncio.CancelledError:
            return

        self.waiting_for_emoji = False
        try:
            self._build()
            await interaction.edit_original_response(view=self)
        except Exception as e:
            log_sys("UI_ERR", f"Erreur update UI emoji: {e}", is_error=True)


# ==============================================================================
# --- COG PRINCIPAL ---
# ==============================================================================
class InfiniteCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log_sys("INIT", "Module Jeu de Comptage Infini déployé.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        config = infinite_db.load(message.guild.id)
        chan_id = config.get("channel_id")

        if not chan_id or message.channel.id != chan_id:
            return

        content = message.content.strip().split()
        
        # Filtre strict : on supprime s'il y a une image/pièce jointe ou si le message ne commence pas par un nombre
        is_valid_number = bool(content and content[0].isdigit())
        
        if message.attachments or not is_valid_number:
            try:
                await message.delete()
            except:
                pass
            return

        number = int(content[0])
        expected = config.get("current_number", 0) + 1
        last_user = config.get("last_user_id")

        # Cas 1 : Réussite parfaite
        if number == expected and message.author.id != last_user:
            try:
                await message.add_reaction(config.get("reaction_emoji", "✅"))
            except discord.HTTPException:
                # Fallback si l'emoji custom fourni est introuvable ou invalide
                try: await message.add_reaction("✅")
                except: pass

            config["current_number"] = expected
            config["last_user_id"] = message.author.id
            infinite_db.save(message.guild.id, config)

        # Cas 2 : Erreur (mauvais nombre ou même utilisateur)
        else:
            try:
                await message.add_reaction("❌")
            except:
                pass

            # Punition Hardcore ou Message Normal
            if config.get("hardcore_mode", False):
                reason = "le système anti-solo a bloqué ta requête" if message.author.id == last_user else f"a ruiné le compteur à **{expected - 1}**"
                await message.channel.send(f"{E_WARN} **Série brisée !** {message.author.mention} {reason}. On recommence à **0** !")
                
                config["current_number"] = 0
                config["last_user_id"] = None
                infinite_db.save(message.guild.id, config)
            else:
                # Mode normal : On supprime le message erroné après quelques secondes pour garder la chaîne propre
                if message.author.id == last_user:
                    warn_msg = await message.channel.send(f"{E_WARN} {message.author.mention}, le système anti-solo bloque ta requête. Attends ton tour !")
                else:
                    warn_msg = await message.channel.send(f"{E_WARN} {message.author.mention}, le prochain nombre était **{expected}** !")
                
                await asyncio.sleep(4)
                try:
                    await message.delete()
                    await warn_msg.delete()
                except:
                    pass

    @perm_command(level=2)
    @commands.hybrid_command(name="infinite", description="Configuration du jeu de comptage infini.")
    async def infinite_cmd(self, ctx: commands.Context):
        if not ctx.guild:
            await ctx.send(f"{E_OFF} Cette commande exige un contexte de serveur.")
            return

        if HAS_VAX_CORE and not await ensure_command_permission(ctx, command_name="infinite"):
            return

        log_sys("CMD_INVOKE", f"Interface /infinite déployée par {ctx.author.name}")
        view = InfiniteLayoutView(self, ctx.guild, ctx.author)
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    # Retirer les éventuelles anciennes commandes "compteur" et "infinite" pour éviter les conflits
    if bot.get_command("compteur"):
        bot.remove_command("compteur")
    if bot.get_command("infinite"):
        bot.remove_command("infinite")
        
    await bot.add_cog(InfiniteCog(bot))