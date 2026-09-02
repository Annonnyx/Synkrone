import discord
from discord import ui, app_commands
from discord.ext import commands
import io
import aiohttp
import asyncio
import re
from PIL import Image, ImageDraw, ImageFont, ImageOps
from pathlib import Path
import traceback
from typing import Any

# ==============================================================================
# --- IMPORTS MÉTIER VAX ---
# Utilisation stricte de l'écosystème pour garantir l'homogénéité globale.
# ==============================================================================
try:
    from utils.config_data import DataManager
    from utils.config_theme import config_manager, BaliseCatalogLayoutView
    from utils.config_perm import ensure_command_permission, perm_command
    from utils.config_emoji import Emoji as E
    from utils.config_id import IdModal
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
E_IMAGE = getattr(E, 'IMAGE', "🖼️") if HAS_VAX_CORE else "🖼️"
E_TEXT = getattr(E, 'MEMO', "📝") if HAS_VAX_CORE else "📝"
E_TRASH = getattr(E, 'SUPPRIMER', "🗑️") if HAS_VAX_CORE else "🗑️"
E_HELP = getattr(E, 'LISTE', "📋") if HAS_VAX_CORE else "📋"
E_CHAN = getattr(E, 'LIEN', "📍") if HAS_VAX_CORE else "📍"
E_LOCK = getattr(E, 'LOCK', "🔒") if HAS_VAX_CORE else "🔒"
E_UNLOCK = getattr(E, 'UNLOCK', "🔓") if HAS_VAX_CORE else "🔓"
E_DOC = getattr(E, 'DOCUMENT', "📄") if HAS_VAX_CORE else "📄"
E_ID = getattr(E, 'IDENTIFIANT', "🆔") if HAS_VAX_CORE else "🆔"

# ==============================================================================
# --- UTILITAIRES ---
# ==============================================================================
def log_sys(action: str, message: str, is_error: bool = False):
    if ERROR_LOGS_ONLY and not is_error: return
    if not DEBUG_LOGS and not is_error: return
    color = "\033[91m" if is_error else "\033[96m"
    prefix = "[ERREUR AuRevoir]" if is_error else "[INFO AuRevoir]"
    print(f"{color}{prefix} [{action}] {message}\033[0m")

def hex_to_rgb(hex_str: str, default=(44, 47, 51)):
    hex_str = hex_str.lstrip('#')
    if len(hex_str) == 6:
        try:
            return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))
        except:
            pass
    return default

async def get_font_async(size: int):
    """Charge une police TTF pour Pillow, ou télécharge une font Roboto si aucune n'est dispo sur le système."""
    for f in ["arial.ttf", "tahoma.ttf", "verdana.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]:
        try:
            return ImageFont.truetype(f, size)
        except Exception:
            continue
            
    # Fallback asynchrone si aucune police système n'est trouvée (garantit que le texte est adaptatif)
    try:
        url = "https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Bold.ttf"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    font_bytes = await resp.read()
                    return ImageFont.truetype(io.BytesIO(font_bytes), size)
    except Exception:
        pass
        
    return ImageFont.load_default()

# ==============================================================================
# --- GESTIONNAIRE DE DONNÉES (DataManager) ---
# ==============================================================================
class LeaveManager:
    def __init__(self):
        if HAS_VAX_CORE:
            self.data = DataManager("staff/configuration/data_aurevoir")
            self.assets_dir = Path("data/staff/configuration/data_aurevoir/assets")
            try:
                self.assets_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                log_sys("MKDIR_ERR", f"Erreur de création du dossier assets: {e}", is_error=True)
        else:
            log_sys("INIT", "DataManager introuvable. Échec système.", is_error=True)

    def get_bg_path(self, guild_id: int) -> Path:
        return self.assets_dir / f"{guild_id}_bg.png"

    def get_default_config(self):
        return {
            "channel_id": None,
            "is_private": True,
            "embed_title": "Départ de {user}",
            "embed_description": "Triste de te voir partir...",
            "content_message": "{user.mention} nous a quitté.\nNous sommes désormais {guild.count}.",
            "bg_mode": "image",  # "image", "solid", "gradient"
            "bg_color1": "#2c3e50",
            "bg_color2": "#e74c3c"
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

leave_db = LeaveManager()

# ==============================================================================
# --- MODALS ---
# ==============================================================================
class LeaveChannelModal(ui.Modal, title="📍 Lier par ID de Salon"):
    id_input = ui.TextInput(label="ID du Salon", placeholder="Collez l'ID ici...", min_length=15, max_length=25)
    
    def __init__(self, view: "LeaveLayoutView"):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        raw_id = self.id_input.value.strip()
        if not raw_id.isdigit():
            return await interaction.response.send_message(f"{E_OFF} L'ID fourni n'est pas un nombre valide.", ephemeral=True)
            
        target = interaction.guild.get_channel(int(raw_id))
        if not target or target.type not in {discord.ChannelType.text, discord.ChannelType.news}:
            return await interaction.response.send_message(f"{E_OFF} Salon textuel introuvable.", ephemeral=True)

        conf = leave_db.load(self.view.guild.id)
        conf['channel_id'] = target.id
        leave_db.save(self.view.guild.id, conf)
        self.view.status_message = f"{E_ON} Salon cible mis à jour avec succès."
        await self.view._refresh(interaction)

class LeaveTextModal(ui.Modal, title="📝 Textes de Départ"):
    t = ui.TextInput(label="Titre (Layout)", max_length=250)
    d = ui.TextInput(label="Description (Layout)", style=discord.TextStyle.paragraph)
    m = ui.TextInput(label="Message Hors Composant", style=discord.TextStyle.paragraph)
    
    def __init__(self, view: "LeaveLayoutView"):
        super().__init__()
        self.view = view
        conf = leave_db.load(self.view.guild.id)
        self.t.default = conf['embed_title']
        self.d.default = conf['embed_description']
        self.m.default = conf['content_message']

    async def on_submit(self, interaction: discord.Interaction):
        conf = leave_db.load(self.view.guild.id)
        conf.update({"embed_title": self.t.value, "embed_description": self.d.value, "content_message": self.m.value})
        leave_db.save(self.view.guild.id, conf)
        self.view.status_message = f"{E_ON} Textes de départ mis à jour."
        await self.view._refresh(interaction)

class BgSolidModal(ui.Modal, title="Couleur unie"):
    c1 = ui.TextInput(label="Code Couleur (Hex)", placeholder="ex: #ff0000", max_length=7, min_length=6)
    
    def __init__(self, view: "LeaveLayoutView"):
        super().__init__()
        self.view = view
        conf = leave_db.load(self.view.guild.id)
        self.c1.default = conf.get('bg_color1', "#2c3e50")

    async def on_submit(self, interaction: discord.Interaction):
        conf = leave_db.load(self.view.guild.id)
        conf.update({"bg_mode": "solid", "bg_color1": self.c1.value.strip()})
        leave_db.save(self.view.guild.id, conf)
        self.view.status_message = f"{E_ON} Fond en couleur unie mis à jour."
        await self.view._refresh(interaction)

class BgGradientModal(ui.Modal, title="Couleurs en alternance (Dégradé)"):
    c1 = ui.TextInput(label="Couleur Gauche (Hex)", placeholder="ex: #2c3e50", max_length=7, min_length=6)
    c2 = ui.TextInput(label="Couleur Droite (Hex)", placeholder="ex: #e74c3c", max_length=7, min_length=6)
    
    def __init__(self, view: "LeaveLayoutView"):
        super().__init__()
        self.view = view
        conf = leave_db.load(self.view.guild.id)
        self.c1.default = conf.get('bg_color1', "#2c3e50")
        self.c2.default = conf.get('bg_color2', "#e74c3c")

    async def on_submit(self, interaction: discord.Interaction):
        conf = leave_db.load(self.view.guild.id)
        conf.update({"bg_mode": "gradient", "bg_color1": self.c1.value.strip(), "bg_color2": self.c2.value.strip()})
        leave_db.save(self.view.guild.id, conf)
        self.view.status_message = f"{E_ON} Fond dégradé mis à jour."
        await self.view._refresh(interaction)


# ==============================================================================
# --- SELECTEURS (Layout V2) ---
# ==============================================================================
class LeaveOptionsSelect(ui.Select):
    def __init__(self, parent_view: "LeaveLayoutView", is_default: bool):
        self.parent_view = parent_view
        
        options = [
            discord.SelectOption(label="Configurer le salon", value="channel", emoji=E_CHAN, description="Sélectionner ou lier par ID"),
            discord.SelectOption(label="Visibilité", value="vis", emoji=E_LOCK, description="Basculer Privé / Public"),
            discord.SelectOption(label="Textes", value="text", emoji=E_TEXT, description="Modifier les textes du message"),
            discord.SelectOption(label="Fond", value="bg", emoji=E_IMAGE, description="Modifier l'image de fond"),
            discord.SelectOption(label="Balises", value="balises", emoji=E_HELP, description="Afficher les balises utilisables"),
        ]
        if not is_default:
            options.append(discord.SelectOption(label="Réinitialiser", value="reset", emoji=E_TRASH, description="Désactiver et remettre à zéro"))
            
        super().__init__(placeholder="⚙️ Options de configuration...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val == "channel":
            self.parent_view.active_sub_menu = "channel"
            await self.parent_view._refresh(interaction)
        elif val == "bg":
            self.parent_view.active_sub_menu = "bg"
            await self.parent_view._refresh(interaction)
        elif val == "vis":
            await self.parent_view._on_visibility(interaction)
        elif val == "text":
            await self.parent_view._on_text_config(interaction)
        elif val == "balises":
            await self.parent_view._on_balises(interaction)
        elif val == "reset":
            await self.parent_view._on_reset(interaction)

# ==============================================================================
# --- INTERFACE UTILISATEUR PRINCIPALE ---
# ==============================================================================
class LeaveLayoutView(ui.LayoutView):
    def __init__(self, cog: "AurevoirCog", guild: discord.Guild, user: discord.Member):
        super().__init__(timeout=600)
        self.cog = cog
        self.guild = guild
        self.user = user
        self.status_message = ""
        self.active_sub_menu: str | None = None
        self._build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            if not interaction.response.is_done(): await interaction.response.defer()
            await interaction.channel.send(f"{E_OFF} {interaction.user.mention}, cette console est protégée.", delete_after=6)
            return False
        return True

    def _build(self):
        try:
            self.clear_items()
            conf = leave_db.load(self.guild.id)
            
            accent_color = 0xe74c3c # Rouge départ
            footer_text = ""
            if HAS_VAX_CORE and config_manager:
                try:
                    theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.user, self.cog.bot)
                    accent_color = int(theme.get("color", 0xe74c3c))
                    footer_text = theme.get("footer_text", "")
                except Exception: pass

            container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
            container.add_item(ui.TextDisplay(f"# {E_DOC} Configuration d'Au Revoir"))
            
            if self.status_message:
                container.add_item(ui.TextDisplay(f"> {self.status_message}"))
                self.status_message = ""

            chan_txt = f"<#{conf['channel_id']}>" if conf.get('channel_id') else "`Non configuré`"
            is_enabled = bool(conf.get('channel_id')) and self.guild.get_channel(conf['channel_id']) is not None
            state_txt = f"{E_ON} `Activé`" if is_enabled else f"{E_OFF} `Désactivé`"
            
            bg_mode = conf.get("bg_mode", "image")
            if bg_mode == "solid":
                bg_state = f"`Couleur Unie ({conf.get('bg_color1')})`"
            elif bg_mode == "gradient":
                bg_state = f"`Dégradé ({conf.get('bg_color1')} -> {conf.get('bg_color2')})`"
            else:
                bg_state = "`Image personnalisée`" if leave_db.get_bg_path(self.guild.id).exists() else "`Image par Défaut`"

            vis_txt = f"{E_LOCK} `Privé`" if conf.get('is_private', True) else f"{E_UNLOCK} `Public (Lecture seule)`"

            container.add_item(ui.TextDisplay(
                f"**État du système :** {state_txt}\n"
                f"**Salon d'ancrage :** {chan_txt}\n"
                f"**Visibilité :** {vis_txt}\n"
                f"**Style de fond :** {bg_state}\n\n"
                f"### {E_TEXT} Textes Configurés\n"
                f"- **Titre :** {self.cog.parse(conf['embed_title'], self.user)}\n"
                f"- **Desc :** {self.cog.parse(conf['embed_description'], self.user)}\n"
                f"- **Msg brut :** {self.cog.parse(conf['content_message'], self.user)}"
            ))

            try:
                gallery = ui.MediaGallery()
                gallery.add_item(media="attachment://preview.png", description="Aperçu du Départ")
                container.add_item(gallery)
            except Exception as e:
                log_sys("GALLERY_ERR", f"Erreur gallery: {e}", is_error=True)

            # Ligne Principale : Sélecteur d'options
            row_main = ui.ActionRow()
            is_default = not conf.get('channel_id') and conf.get('bg_mode', 'image') == 'image' and not leave_db.get_bg_path(self.guild.id).exists()
            opt_select = LeaveOptionsSelect(self, is_default)
            row_main.add_item(opt_select)
            container.add_item(row_main)

            # Sous-menus en fonction de l'option choisie
            if self.active_sub_menu == "channel":
                row_chan = ui.ActionRow()
                chan_select = ui.ChannelSelect(
                    placeholder="Sélectionner le salon d'au revoir...",
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

            elif self.active_sub_menu == "bg":
                row_bg = ui.ActionRow()
                bg_select = ui.Select(
                    placeholder="🎨 Choisir le style de fond...",
                    options=[
                        discord.SelectOption(label="Image personnalisée", value="image", emoji=E_IMAGE, description="Uploader une image ou une URL"),
                        discord.SelectOption(label="Couleur unie", value="solid", emoji="🖌️", description="Une seule couleur HEX"),
                        discord.SelectOption(label="Couleur en alternance", value="gradient", emoji="🌈", description="Dégradé de 2 couleurs HEX")
                    ]
                )
                bg_select.callback = self._on_bg_select
                row_bg.add_item(bg_select)
                container.add_item(row_bg)

            if footer_text:
                container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
                container.add_item(ui.TextDisplay(footer_text))

            self.add_item(container)
        except Exception as e:
            log_sys("BUILD_ERR", f"Erreur de construction UI:\n{traceback.format_exc()}", is_error=True)

    async def _refresh(self, interaction: discord.Interaction):
        try:
            self._build()
            img_buffer = await self.cog.create_leave_image(self.user, self.guild.id)
            file = discord.File(img_buffer, "preview.png")

            if interaction.response.is_done():
                await interaction.edit_original_response(attachments=[file], view=self)
            else:
                await interaction.response.edit_message(attachments=[file], view=self)
            log_sys("REFRESH", "Interface rafraîchie avec succès.")
        except Exception as e:
            log_sys("REFRESH_ERR", f"Erreur de rafraîchissement UI:\n{traceback.format_exc()}", is_error=True)

    async def _on_chan_selected(self, interaction: discord.Interaction):
        chan_id = int(interaction.data['values'][0])
        conf = leave_db.load(self.guild.id)
        conf['channel_id'] = chan_id
        leave_db.save(self.guild.id, conf)
        self.status_message = f"{E_ON} Salon d'au revoir sélectionné avec succès."
        self.active_sub_menu = None
        await self._refresh(interaction)

    async def _on_chan_id_manual(self, interaction: discord.Interaction):
        self.active_sub_menu = None
        await interaction.response.send_modal(LeaveChannelModal(self))

    async def _on_visibility(self, interaction: discord.Interaction):
        self.active_sub_menu = None
        conf = leave_db.load(self.guild.id)
        conf['is_private'] = not conf.get('is_private', True)
        leave_db.save(self.guild.id, conf)
        
        if conf.get('channel_id'):
            channel = self.guild.get_channel(conf['channel_id'])
            if channel:
                try:
                    if conf['is_private']:
                        await channel.set_permissions(self.guild.default_role, view_channel=False)
                    else:
                        await channel.set_permissions(self.guild.default_role, 
                            view_channel=True, send_messages=False, create_public_threads=False,
                            create_private_threads=False, send_messages_in_threads=False, add_reactions=False
                        )
                except discord.Forbidden:
                    log_sys("PERM_ERR", "Permissions insuffisantes pour modifier le salon de départ.")

        self.status_message = f"{E_ON} Visibilité du salon mise à jour."
        await self._refresh(interaction)

    async def _on_text_config(self, interaction: discord.Interaction):
        self.active_sub_menu = None
        await interaction.response.send_modal(LeaveTextModal(self))

    async def _on_bg_select(self, interaction: discord.Interaction):
        val = interaction.data['values'][0]
        self.active_sub_menu = None
        if val == "solid":
            await interaction.response.send_modal(BgSolidModal(self))
        elif val == "gradient":
            await interaction.response.send_modal(BgGradientModal(self))
        elif val == "image":
            await self._start_image_upload(interaction)

    async def _start_image_upload(self, interaction: discord.Interaction):
        if not interaction.response.is_done(): await interaction.response.defer()
        
        prompt = await interaction.channel.send(
            f"📥 {interaction.user.mention}, envoyez l'image (fichier joint) ou l'URL directe (PNG/JPG/WEBP) dans ce salon.\n"
            f"*Vous avez 5 minutes. Le message sera automatiquement intercepté et supprimé.*", 
            delete_after=300
        )
        
        def check(m): return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id

        try:
            msg = await self.cog.bot.wait_for('message', check=check, timeout=300)
            
            url = None
            if msg.attachments:
                for att in msg.attachments:
                    if att.content_type and att.content_type.startswith('image/'):
                        url = att.url
                        break
                if not url: url = msg.attachments[0].url
            else:
                match = re.search(r'(https?://\S+\.(?:png|jpe?g|webp|gif)(?:\?\S*)?)', msg.content, re.IGNORECASE)
                if match:
                    url = match.group(1)
                else:
                    match = re.search(r'(https?://\S+)', msg.content)
                    if match: url = match.group(1)

            if url:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            data = await resp.read()
                            with open(leave_db.get_bg_path(self.guild.id), "wb") as f:
                                f.write(data)
                            
                            conf = leave_db.load(self.guild.id)
                            conf['bg_mode'] = "image"
                            leave_db.save(self.guild.id, conf)
                            
                            self.status_message = f"{E_ON} Image de fond téléchargée et appliquée avec succès."
                        else:
                            await interaction.channel.send(f"{E_OFF} Erreur de téléchargement depuis l'URL.", delete_after=6)
            else:
                await interaction.channel.send(f"{E_OFF} Aucune image ou URL valide n'a été trouvée dans votre message.", delete_after=6)

            try: await msg.delete()
            except: pass
            try: await prompt.delete()
            except: pass
            
            await self._refresh(interaction)

        except asyncio.TimeoutError:
            await interaction.channel.send(f"{E_WARN} {interaction.user.mention}, délai écoulé pour l'image. Relancez la commande.", delete_after=6)

    async def _on_balises(self, interaction: discord.Interaction):
        self.active_sub_menu = None
        await self._refresh(interaction)
        
        base_text = (
            "✨ **Balises Spécifiques au Départ**\n"
            "- `{user}` : Nom d'utilisateur\n"
            "- `{user.mention}` : Mention (Ping)\n"
            "- `{guild}` : Nom du serveur\n"
            "- `{guild.count}` : Nombre total de membres restants\n"
        )
        
        try:
            # Envoi des balises de base
            await interaction.followup.send(content=base_text, ephemeral=True)
            # Envoi des balises globales Vax V3 via le Layout V2 dédié (2e message)
            if HAS_VAX_CORE:
                view = BaliseCatalogLayoutView(self.guild, interaction.user, self.cog.bot)
                await interaction.followup.send(view=view, ephemeral=True)
        except Exception as e:
            log_sys("BALISE_ERR", str(e), is_error=True)

    async def _on_reset(self, interaction: discord.Interaction):
        self.active_sub_menu = None
        leave_db.save(self.guild.id, leave_db.get_default_config())
        bg_path = leave_db.get_bg_path(self.guild.id)
        if bg_path.exists(): bg_path.unlink()
        self.status_message = f"{E_TRASH} Configuration réinitialisée et module désactivé."
        await self._refresh(interaction)

# ==============================================================================
# --- COG PRINCIPAL ---
# ==============================================================================
class AurevoirCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        log_sys("INIT", "Module Au Revoir V3 déployé.")

    def parse(self, text: str, member: discord.Member) -> str:
        if not text: return ""
        
        # Application des balises de base
        mapping = {
            "{user}": member.name, 
            "{user.mention}": member.mention, 
            "{guild}": member.guild.name, 
            "{guild.count}": str(member.guild.member_count)
        }
        for k, v in mapping.items(): 
            text = text.replace(k, v)
            
        # Application des balises globales du bot
        if HAS_VAX_CORE:
            try:
                from utils.config_balise import resolve_balises
                b_vals = resolve_balises(member.guild, member, self.bot)
                for k, v in b_vals.items():
                    text = text.replace(k, str(v))
            except Exception:
                pass
                
        return text

    async def create_leave_image(self, member: discord.Member, guild_id: int):
        conf = leave_db.load(guild_id)
        bg_mode = conf.get("bg_mode", "image")
        
        color = (231, 76, 60) # Rouge par défaut
        if HAS_VAX_CORE and config_manager:
            try:
                t = config_manager.get_resolved_values(guild_id)
                hex_c = t.get("color", 0xe74c3c)
                color = ((hex_c >> 16) & 255, (hex_c >> 8) & 255, hex_c & 255)
            except: pass

        bg_path = leave_db.get_bg_path(guild_id)
        W, H = 800, 300
        
        # --- GENERATION DU FOND ---
        if bg_mode == "solid":
            c1 = hex_to_rgb(conf.get('bg_color1', "#2c3e50"))
            image = Image.new('RGB', (W, H), color=c1).convert("RGBA")
        elif bg_mode == "gradient":
            image = Image.new('RGB', (W, H))
            draw = ImageDraw.Draw(image)
            c1 = hex_to_rgb(conf.get('bg_color1', "#2c3e50"))
            c2 = hex_to_rgb(conf.get('bg_color2', "#e74c3c"))
            for x in range(W):
                r = int(c1[0] + (c2[0] - c1[0]) * x / W)
                g = int(c1[1] + (c2[1] - c1[1]) * x / W)
                b = int(c1[2] + (c2[2] - c1[2]) * x / W)
                draw.line([(x, 0), (x, H)], fill=(r,g,b))
            image = image.convert("RGBA")
        else: # Mode Image
            if bg_path.exists():
                image = ImageOps.fit(Image.open(bg_path).convert("RGBA"), (W, H), method=Image.Resampling.LANCZOS)
            else:
                image = Image.new('RGB', (W, H), color=(44, 47, 51)).convert("RGBA")

        # Filtre sombre sur tout le fond pour faire ressortir le texte et l'avatar
        overlay = Image.new('RGBA', (W,H), (0, 0, 0, 140))
        image = Image.alpha_composite(image, overlay)

        # Extraction Avatar Asynchrone
        av_data = None
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(str(member.display_avatar.with_format("png").with_size(256).url)) as r:
                    av_data = await r.read()
        except: pass

        # Dessin de l'Avatar Centré Gauche
        if av_data:
            av = ImageOps.fit(Image.open(io.BytesIO(av_data)).convert("RGBA"), (180, 180))
            mask = Image.new('L', (180, 180), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, 180, 180), fill=255)
            av.putalpha(mask)

            draw = ImageDraw.Draw(image)
            draw.ellipse((45, 55, 235, 245), fill=color) 
            image.paste(av, (50, 60), av)
        
        draw = ImageDraw.Draw(image)
        
        # Chargement de la police agrandie (45 et 65) via le fallback sécurisé
        font_title = await get_font_async(45)
        font_name = await get_font_async(65)
            
        # Calcul de la position X pour bien centrer le texte dans l'espace vide à droite (entre 260 et 780)
        text_title = "AU REVOIR"
        bbox_t = draw.textbbox((0, 0), text_title, font=font_title)
        w_t = bbox_t[2] - bbox_t[0]
        x_t = 260 + (520 - w_t) // 2
        
        name_text = str(member.name)[:15].capitalize()
        bbox_n = draw.textbbox((0, 0), name_text, font=font_name)
        w_n = bbox_n[2] - bbox_n[0]
        x_n = 260 + (520 - w_n) // 2

        # Rendu centré verticalement (Y=90 et Y=150) avec contour noir (stroke) épais
        draw.text((x_t, 90), text_title, fill=(255, 255, 255), font=font_title, stroke_width=3, stroke_fill=(0,0,0))
        draw.text((x_n, 150), name_text, fill=color, font=font_name, stroke_width=4, stroke_fill=(0,0,0))

        buf = io.BytesIO()
        image.save(buf, format='PNG')
        buf.seek(0)
        return buf

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        try:
            conf = leave_db.load(member.guild.id)
            if not conf.get('channel_id'): return
            
            chan = member.guild.get_channel(conf['channel_id'])
            if not chan: return
            
            img_buffer = await self.create_leave_image(member, member.guild.id)
            file = discord.File(img_buffer, "leave.png")
            
            title = self.parse(conf['embed_title'], member)
            desc = self.parse(conf['embed_description'], member)
            msg_content = self.parse(conf['content_message'], member)

            view = ui.LayoutView(timeout=1)
            accent_color = 0xe74c3c
            if HAS_VAX_CORE and config_manager:
                try:
                    theme = config_manager.get_layout_v2_theme(member.guild.id, member.guild, self.bot.user, self.bot)
                    accent_color = int(theme.get("color", 0xe74c3c))
                except: pass

            container = ui.Container(accent_color=discord.Color(accent_color), spoiler=False)
            container.add_item(ui.TextDisplay(f"# {E_LEAVE} {title}\n{desc}"))
            
            try:
                gallery = ui.MediaGallery()
                gallery.add_item(media="attachment://leave.png", description="Image de Départ")
                container.add_item(gallery)
            except Exception as e:
                log_sys("GALLERY_ERR", f"Erreur gallery: {e}", is_error=True)

            view.add_item(container)

            # Séparation propre du contenu hors-composant pour compatibilité LayoutV2
            if msg_content:
                try:
                    await chan.send(content=msg_content)
                except discord.Forbidden:
                    log_sys("PERM_ERROR", f"Impossible d'écrire le message brut dans le salon {chan.id}", is_error=True)
                    return

            # Envoi LayoutV2 final
            await chan.send(files=[file], view=view)
            log_sys("SEND", f"Départ envoyé pour {member.name} sur {member.guild.id}")
            
        except Exception as e:
            log_sys("LEAVE_ERR", f"Erreur critique on_member_remove:\n{traceback.format_exc()}", is_error=True)

    @perm_command(level=2) # Verrouillage métier
    @commands.hybrid_command(name="aurevoir", description="Configure le système de départ des membres.")
    async def aurevoir_cmd(self, ctx: commands.Context):
        try:
            if not ctx.guild:
                await ctx.send(f"{E_OFF} Cette commande exige un contexte de serveur.", ephemeral=True)
                return

            if HAS_VAX_CORE and not await ensure_command_permission(ctx, command_name="aurevoir"):
                return
                
            log_sys("CMD_INVOKE", f"Console /aurevoir invoquée par {ctx.author.name}")
            await ctx.defer()
            
            view = LeaveLayoutView(self, ctx.guild, ctx.author)
            img_buffer = await self.create_leave_image(ctx.author, ctx.guild.id)
            file = discord.File(img_buffer, "preview.png")
            
            await ctx.send(files=[file], view=view)
        except Exception as e:
            log_sys("CMD_ERR", f"Erreur critique lancement commande:\n{traceback.format_exc()}", is_error=True)
            await ctx.send(f"{E_OFF} Une erreur s'est produite au lancement de la commande.", ephemeral=True)

async def setup(bot: commands.Bot):
    if bot.get_command("aurevoir"): bot.remove_command("aurevoir")
    await bot.add_cog(AurevoirCog(bot))