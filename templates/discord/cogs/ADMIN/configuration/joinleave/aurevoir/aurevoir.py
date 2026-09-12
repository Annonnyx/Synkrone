import discord
from discord.ext import commands
from discord import ui, app_commands
import io
import json
import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageOps
from pathlib import Path

# ==============================================================================
# --------------------------- IMPORTATION UTILS --------------------------------
# ==============================================================================
try:
    from cogs.config_manager.utils import config_manager
except ImportError:
    config_manager = None

# ==============================================================================
# --------------------------- GESTIONNAIRE DE DONNÉES --------------------------
# ==============================================================================

class LeaveDataManager:
    def __init__(self):
        self.base_path = Path(__file__).parent / "data_leave"
        self.assets_path = Path(__file__).parent / "assets"
        self.default_font = self.assets_path / "arial.ttf"
        self.help_json = self.assets_path / "aide_aurevoir.json"
        if not self.base_path.exists(): self.base_path.mkdir(parents=True)

    def get_guild_folder(self, guild_id: int) -> Path:
        folder = self.base_path / str(guild_id)
        if not folder.exists(): folder.mkdir(parents=True)
        return folder

    def get_default_config(self):
        return {
            "channel_id": None,
            "is_private": True,
            "embed_title": "Départ de {user}",
            "embed_description": "Triste de te voir partir...",
            "content_message": "{user.mention} nous a quitté.\nNous sommes désormais {guild.count}.",
            "background_mode": "default",
            "background_url": "",
            "bg_color_1": "#2c2f33",
            "bg_color_2": "",
            "banner_user": "author",
            "banner_fallback_enabled": False,
            "banner_fallback_mode": "default"
        }

    def get_config(self, guild_id: int) -> dict:
        folder = self.get_guild_folder(guild_id)
        config_file = folder / "config.json"
        if not config_file.exists(): return self.get_default_config()
        with open(config_file, 'r', encoding='utf-8') as f:
            return {**self.get_default_config(), **json.load(f)}

    def save_config(self, guild_id: int, data: dict):
        folder = self.get_guild_folder(guild_id)
        with open(folder / "config.json", 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

# ==============================================================================
# --------------------------- MODALS -------------------------------------------
# ==============================================================================

class LeaveChannelModal(ui.Modal, title="📍 Salon de Départ"):
    id_input = ui.TextInput(label="ID du Salon", placeholder="Collez l'ID ici...", min_length=15, max_length=25)
    def __init__(self, cog, view):
        super().__init__()
        self.cog, self.view = cog, view

    async def on_submit(self, it: discord.Interaction):
        try:
            conf = self.cog.data_manager.get_config(it.guild.id)
            conf['channel_id'] = int(self.id_input.value)
            self.cog.data_manager.save_config(it.guild.id, conf)
            await self.view.refresh(it)
        except:
            await it.response.send_message("❌ ID invalide.", ephemeral=True)

class LeaveTextModal(ui.Modal, title="📝 Textes de Départ"):
    t = ui.TextInput(label="Titre Embed", max_length=250)
    d = ui.TextInput(label="Description Embed", style=discord.TextStyle.paragraph)
    m = ui.TextInput(label="Message Hors Embed", style=discord.TextStyle.paragraph)
    
    def __init__(self, cog, view):
        super().__init__()
        self.cog, self.view = cog, view
        conf = self.cog.data_manager.get_config(view.guild_id)
        self.t.default, self.d.default, self.m.default = conf['embed_title'], conf['embed_description'], conf['content_message']

    async def on_submit(self, it: discord.Interaction):
        conf = self.cog.data_manager.get_config(self.view.guild_id)
        conf.update({"embed_title": self.t.value, "embed_description": self.d.value, "content_message": self.m.value})
        self.cog.data_manager.save_config(self.view.guild_id, conf)
        await self.view.refresh(it)


class LeaveBackgroundUrlModal(ui.Modal, title="🌐 Fond par URL"):
    url_input = ui.TextInput(
        label="URL d'image",
        placeholder="https://exemple.com/image.png",
        style=discord.TextStyle.short,
        max_length=1000,
    )

    def __init__(self, cog, view, banner_fallback=False):
        super().__init__()
        self.cog, self.view = cog, view
        self.banner_fallback = banner_fallback
        conf = self.cog.data_manager.get_config(view.guild_id)
        self.url_input.default = conf.get("background_url", "")

    async def on_submit(self, it: discord.Interaction):
        conf = self.cog.data_manager.get_config(self.view.guild_id)
        if self.banner_fallback:
            conf["background_mode"] = "banner"
            conf["banner_fallback_enabled"] = True
            conf["banner_fallback_mode"] = "url"
        else:
            conf["background_mode"] = "url"
        conf["banner_fallback_mode"] = "url"
        conf["background_url"] = self.url_input.value.strip()
        self.cog.data_manager.save_config(self.view.guild_id, conf)
        await self.view.refresh(it)


class LeaveBackgroundHexModal(ui.Modal, title="🎨 Fond par Couleurs HEX"):
    c1 = ui.TextInput(label="Couleur HEX 1", placeholder="#2c2f33", max_length=7)
    c2 = ui.TextInput(label="Couleur HEX 2 (optionnelle)", placeholder="#23272a", required=False, max_length=7)

    def __init__(self, cog, view, banner_fallback=False):
        super().__init__()
        self.cog, self.view = cog, view
        self.banner_fallback = banner_fallback
        conf = self.cog.data_manager.get_config(view.guild_id)
        self.c1.default = conf.get("bg_color_1", "#2c2f33")
        self.c2.default = conf.get("bg_color_2", "")

    @staticmethod
    def _normalize_hex(value: str):
        value = (value or "").strip()
        if not value:
            return ""
        if not value.startswith("#"):
            value = f"#{value}"
        if len(value) != 7:
            return None
        try:
            int(value[1:], 16)
        except ValueError:
            return None
        return value.lower()

    async def on_submit(self, it: discord.Interaction):
        c1 = self._normalize_hex(self.c1.value)
        c2 = self._normalize_hex(self.c2.value)
        if c1 is None or c2 is None:
            return await it.response.send_message("❌ Code HEX invalide. Exemple: #2c2f33", ephemeral=True)

        conf = self.cog.data_manager.get_config(self.view.guild_id)
        if self.banner_fallback:
            conf["background_mode"] = "banner"
            conf["banner_fallback_enabled"] = True
            conf["banner_fallback_mode"] = "hex"
        else:
            conf["background_mode"] = "hex"
        conf["banner_fallback_mode"] = "hex"
        conf["bg_color_1"] = c1 or "#2c2f33"
        conf["bg_color_2"] = c2
        self.cog.data_manager.save_config(self.view.guild_id, conf)
        await self.view.refresh(it)


class LeaveBannerFallbackModeSelect(ui.Select):
    def __init__(self, cog, parent_view):
        self.cog = cog
        self.parent_view = parent_view
        options = [
            discord.SelectOption(label="Fallback image", value="upload", description="Envoyer une image de secours"),
            discord.SelectOption(label="Fallback URL image", value="url", description="Définir une URL de secours"),
            discord.SelectOption(label="Fallback code HEX", value="hex", description="Définir une couleur de secours"),
        ]
        super().__init__(placeholder="Choisissez le fallback bannière...", min_values=1, max_values=1, options=options)

    async def callback(self, it: discord.Interaction):
        conf = self.cog.data_manager.get_config(self.parent_view.guild_id)
        conf["background_mode"] = "banner"
        conf["banner_fallback_enabled"] = True
        self.cog.data_manager.save_config(self.parent_view.guild_id, conf)

        choice = self.values[0]
        if choice == "upload":
            await it.response.send_message("📤 Envoyez l'image de fallback (PNG/JPG) dans les 10 minutes.", ephemeral=True)

            def check(m):
                return m.author.id == it.user.id and m.channel.id == it.channel.id and m.attachments

            try:
                msg = await self.cog.bot.wait_for("message", check=check, timeout=600)
                conf = self.cog.data_manager.get_config(self.parent_view.guild_id)
                conf["background_mode"] = "banner"
                conf["banner_fallback_enabled"] = True
                conf["banner_fallback_mode"] = "upload"
                self.cog.data_manager.save_config(self.parent_view.guild_id, conf)
                await msg.attachments[0].save(self.cog.data_manager.get_guild_folder(self.parent_view.guild_id) / "background.png")
                try:
                    await msg.delete()
                except:
                    pass
                await self.parent_view.refresh(it)
            except:
                await it.followup.send("⌛ Temps dépassé (10 minutes).", ephemeral=True)
            return

        if choice == "url":
            return await it.response.send_modal(LeaveBackgroundUrlModal(self.cog, self.parent_view, banner_fallback=True))

        return await it.response.send_modal(LeaveBackgroundHexModal(self.cog, self.parent_view, banner_fallback=True))


class LeaveBannerFallbackView(ui.View):
    def __init__(self, cog, parent_view):
        super().__init__(timeout=180)
        self.cog = cog
        self.parent_view = parent_view
        self.add_item(LeaveBannerFallbackModeSelect(cog, parent_view))

    @ui.button(label="Fallback ON", style=discord.ButtonStyle.success)
    async def fallback_on(self, it: discord.Interaction, btn: ui.Button):
        conf = self.cog.data_manager.get_config(self.parent_view.guild_id)
        conf["background_mode"] = "banner"
        conf["banner_fallback_enabled"] = True
        self.cog.data_manager.save_config(self.parent_view.guild_id, conf)
        await it.response.send_message("✅ Bannière activée avec fallback ON.", ephemeral=True)
        await self.parent_view.refresh(it)

    @ui.button(label="Fallback OFF", style=discord.ButtonStyle.secondary)
    async def fallback_off(self, it: discord.Interaction, btn: ui.Button):
        conf = self.cog.data_manager.get_config(self.parent_view.guild_id)
        conf["background_mode"] = "banner"
        conf["banner_fallback_enabled"] = False
        self.cog.data_manager.save_config(self.parent_view.guild_id, conf)
        await it.response.send_message("✅ Bannière activée avec fallback OFF.", ephemeral=True)
        await self.parent_view.refresh(it)


class LeaveBackgroundModeSelect(ui.Select):
    def __init__(self, cog, view):
        self.cog = cog
        self.parent_view = view
        options = [
            discord.SelectOption(label="Envoyer une image", value="upload", description="Importer un fond PNG/JPG"),
            discord.SelectOption(label="URL d'image", value="url", description="Définir une image depuis une URL"),
            discord.SelectOption(label="Couleur HEX", value="hex", description="1 couleur: uni, 2 couleurs: dégradé"),
            discord.SelectOption(label="Bannière de l'utilisateur", value="banner", description="Utilise la bannière du membre ciblé"),
        ]
        super().__init__(placeholder="Choisissez le type de fond...", min_values=1, max_values=1, options=options)

    async def callback(self, it: discord.Interaction):
        choice = self.values[0]
        if choice == "upload":
            await it.response.send_message("📤 Envoyez l'image (PNG/JPG) dans les 10 minutes.", ephemeral=True)

            def check(m):
                return m.author.id == it.user.id and m.channel.id == it.channel.id and m.attachments

            try:
                msg = await self.cog.bot.wait_for("message", check=check, timeout=600)
                conf = self.cog.data_manager.get_config(self.parent_view.guild_id)
                conf["background_mode"] = "upload"
                conf["banner_fallback_mode"] = "upload"
                self.cog.data_manager.save_config(self.parent_view.guild_id, conf)
                await msg.attachments[0].save(self.cog.data_manager.get_guild_folder(self.parent_view.guild_id) / "background.png")
                try:
                    await msg.delete()
                except:
                    pass
                await self.parent_view.refresh(it)
            except:
                await it.followup.send("⌛ Temps dépassé (10 minutes).", ephemeral=True)
            return

        if choice == "url":
            return await it.response.send_modal(LeaveBackgroundUrlModal(self.cog, self.parent_view))

        if choice == "banner":
            conf = self.cog.data_manager.get_config(self.parent_view.guild_id)
            conf["background_mode"] = "banner"
            self.cog.data_manager.save_config(self.parent_view.guild_id, conf)
            await it.response.send_message(
                "Bannière sélectionnée. Choisissez le fallback si l'utilisateur n'a pas de bannière :",
                ephemeral=True,
                view=LeaveBannerFallbackView(self.cog, self.parent_view),
            )
            await self.parent_view.refresh(it)
            return

        return await it.response.send_modal(LeaveBackgroundHexModal(self.cog, self.parent_view))


class LeaveBackgroundSelectView(ui.View):
    def __init__(self, cog, parent_view):
        super().__init__(timeout=180)
        self.add_item(LeaveBackgroundModeSelect(cog, parent_view))


class LeaveChannelSelect(ui.ChannelSelect):
    def __init__(self, cog, view):
        self.cog = cog
        self.parent_view = view
        super().__init__(
            placeholder="Choisissez le salon d'envoi...",
            min_values=1,
            max_values=1,
            channel_types=[discord.ChannelType.text],
            row=0,
        )

    async def callback(self, it: discord.Interaction):
        channel = self.values[0]
        conf = self.cog.data_manager.get_config(self.parent_view.guild_id)
        conf["channel_id"] = channel.id
        self.cog.data_manager.save_config(self.parent_view.guild_id, conf)
        await self.parent_view.refresh(it)

# ==============================================================================
# --------------------------- VIEW CONFIGURATION -------------------------------
# ==============================================================================

class LeaveView(ui.View):
    def __init__(self, cog, guild_id, user_preview):
        super().__init__(timeout=600)
        self.cog, self.guild_id, self.user_preview = cog, guild_id, user_preview
        self.message = None
        self.add_item(LeaveChannelSelect(cog, self))
        self.sync_buttons()

    def sync_buttons(self):
        conf = self.cog.data_manager.get_config(self.guild_id)

        bg_exists = (self.cog.data_manager.get_guild_folder(self.guild_id) / "background.png").exists()
        is_default = (conf == self.cog.data_manager.get_default_config()) and not bg_exists
        if is_default and self.reset_btn in self.children:
            self.remove_item(self.reset_btn)
        if not is_default and self.reset_btn not in self.children:
            self.add_item(self.reset_btn)

    async def refresh(self, it: discord.Interaction = None):
        if it and getattr(it, "message", None) and getattr(it.message, "id", None) and self.message is None:
            self.message = it.message
        if it and not it.response.is_done():
            await it.response.defer()
            
        self.sync_buttons()
        img = await self.cog.create_leave_image(self.user_preview, self.guild_id)
        
        conf = self.cog.data_manager.get_config(self.guild_id)
        chan = f"<#{conf['channel_id']}>" if conf['channel_id'] else "❌"
        bg_text = self.cog.get_background_status_text(conf)
        fallback_text = self.cog.get_banner_fallback_text(conf)
        fallback_line = f"\n*Si aucune bannière :* {fallback_text}" if conf.get("background_mode") == "banner" else ""
        
        desc = (
            f"📍 **Salon :** {chan}\n"
            f"🖼️ **Fond :** {bg_text}{fallback_line}\n\n"
            f"**Titre :** {self.cog.parse(conf['embed_title'], self.user_preview)}\n"
            f"**Desc :** {self.cog.parse(conf['embed_description'], self.user_preview)}\n"
            f"**Msg :** {self.cog.parse(conf['content_message'], self.user_preview)}"
        )
        
        if config_manager:
            embed = config_manager.get_formatted_embed(it.guild, self.user_preview, self.cog.bot, "⚙️ Config Au Revoir", desc, it.guild.id)
        else:
            embed = discord.Embed(title="⚙️ Config Au Revoir", description=desc, color=0xe74c3c)
        
        embed.set_image(url="attachment://preview.png")
        file = discord.File(img, "preview.png")

        if self.message:
            await self.message.edit(embed=embed, attachments=[file], view=self)
            return
        if it:
            await it.edit_original_response(embed=embed, attachments=[file], view=self)

    @ui.button(label="Texte", emoji="📝", style=discord.ButtonStyle.secondary, row=1)
    async def text_btn(self, it: discord.Interaction, btn: ui.Button):
        await it.response.send_modal(LeaveTextModal(self.cog, self))

    @ui.button(label="Fond", emoji="🖼️", style=discord.ButtonStyle.secondary, row=1)
    async def bg_btn(self, it: discord.Interaction, btn: ui.Button):
        await it.response.send_message("Choisissez le mode de fond :", ephemeral=True, view=LeaveBackgroundSelectView(self.cog, self))

    @ui.button(label="Aperçu", emoji="👁️", style=discord.ButtonStyle.primary, row=1)
    async def preview_btn(self, it: discord.Interaction, btn: ui.Button):
        conf = self.cog.data_manager.get_config(self.guild_id)
        img = await self.cog.create_leave_image(self.user_preview, self.guild_id)
        title = self.cog.parse(conf['embed_title'], self.user_preview)
        desc = self.cog.parse(conf['embed_description'], self.user_preview)
        if config_manager:
            embed = config_manager.get_formatted_embed(it.guild, it.user, self.cog.bot, title, desc, it.guild.id)
        else:
            embed = discord.Embed(title=title, description=desc, color=0xe74c3c)
        embed.set_image(url="attachment://leave.png")
        await it.response.send_message(
            content=self.cog.parse(conf['content_message'], self.user_preview),
            embed=embed,
            file=discord.File(img, "leave.png"),
            ephemeral=True,
        )

    @ui.button(label="Aide", emoji="❓", style=discord.ButtonStyle.secondary, row=1)
    async def help_btn(self, it: discord.Interaction, btn: ui.Button):
        path = self.cog.data_manager.help_json
        if not path.exists(): return await it.response.send_message("❌ JSON manquant.", ephemeral=True)
        with open(path, 'r', encoding='utf-8') as f: data = json.load(f)['help_embed']
        if config_manager: 
            embed = config_manager.get_formatted_embed(it.guild, it.user, self.cog.bot, data['title'], data['description'], it.guild.id)
        else: 
            embed = discord.Embed(title=data['title'], description=data['description'], color=data['color'])
        for f in data['fields']: embed.add_field(name=f['name'], value=f['value'], inline=False)
        await it.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Reset", emoji="♻️", style=discord.ButtonStyle.danger, row=1)
    async def reset_btn(self, it: discord.Interaction, btn: ui.Button):
        self.cog.data_manager.save_config(self.guild_id, self.cog.data_manager.get_default_config())
        bg = self.cog.data_manager.get_guild_folder(self.guild_id) / "background.png"
        if bg.exists(): bg.unlink()
        await self.refresh(it)

# ==============================================================================
# ---------------------------------- COG ---------------------------------------
# ==============================================================================

class AuRevoir(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_manager = LeaveDataManager()

    async def create_leave_image(self, member, g_id):
        color = (231, 76, 60) # Rouge par défaut
        if config_manager:
            e = config_manager.get_formatted_embed(member.guild, member, self.bot, "t", "d", member.guild.id)
            if e.color: color = (e.color.r, e.color.g, e.color.b)

        W, H = 800, 300
        conf = self.data_manager.get_config(g_id)
        image = await self.build_background_image(conf, g_id, member)

        async with aiohttp.ClientSession() as s:
            async with s.get(str(member.display_avatar.url)) as r: av_d = await r.read()
        av = ImageOps.fit(Image.open(io.BytesIO(av_d)).convert("RGBA"), (160,160))
        mask = Image.new('L', (160,160), 0)
        ImageDraw.Draw(mask).ellipse((0,0,160,160), fill=255)
        av.putalpha(mask)

        draw = ImageDraw.Draw(image)
        draw.ellipse((54, 64, 226, 236), fill=color) 
        image.paste(av, (60, 70), av)

        overlay = Image.new('RGBA', (W,H), (0,0,0,0))
        ImageDraw.Draw(overlay).rectangle([250, 80, 750, 220], fill=(0,0,0,235))
        image = Image.alpha_composite(image, overlay)
        
        draw = ImageDraw.Draw(image)
        try:
            from synkrone_custom import card_font
            font = card_font(g_id, 45, fallback=self.data_manager.default_font)
        except Exception:
            try:
                font = ImageFont.truetype(str(self.data_manager.default_font), 45)
            except Exception:
                font = ImageFont.load_default()
        draw.text((270, 100), "AU REVOIR", fill=(255,255,255), font=font)
        
        # Nom avec majuscule
        name_text = str(member.name)[:15].capitalize()
        draw.text((270, 160), name_text, fill=color, font=font)

        buf = io.BytesIO()
        image.save(buf, format='PNG')
        buf.seek(0)
        return buf

    @staticmethod
    def _hex_to_rgb(hex_color: str):
        hex_color = (hex_color or "#2c2f33").lstrip("#")
        if len(hex_color) != 6:
            return (44, 47, 51)
        try:
            return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            return (44, 47, 51)

    def get_background_status_text(self, conf):
        bg_mode = conf.get("background_mode", "default")
        if bg_mode == "upload":
            return "Image upload"
        if bg_mode == "url":
            return f"URL: {conf.get('background_url', '')[:60]}"
        if bg_mode == "hex":
            c1 = conf.get("bg_color_1", "#2c2f33")
            c2 = conf.get("bg_color_2", "")
            return f"HEX: {c1}" + (f" -> {c2}" if c2 else "")
        if bg_mode == "banner":
            return "Bannière utilisateur"
        return "Par défaut"

    def get_banner_fallback_text(self, conf):
        if conf.get("background_mode") != "banner":
            return ""
        if not conf.get("banner_fallback_enabled", False):
            return "Désactivé"
        fb_mode = conf.get("banner_fallback_mode", "default")
        if fb_mode == "upload":
            return "Image upload"
        if fb_mode == "url":
            return f"URL: {conf.get('background_url', '')[:60]}"
        if fb_mode == "hex":
            c1 = conf.get("bg_color_1", "#2c2f33")
            c2 = conf.get("bg_color_2", "")
            return f"HEX: {c1}" + (f" -> {c2}" if c2 else "")
        return "Par défaut"

    async def build_background_image(self, conf, g_id, member):
        W, H = 800, 300
        mode = conf.get("background_mode", "default")
        bg_p = self.data_manager.get_guild_folder(g_id) / "background.png"

        async def build_for_mode(selected_mode: str):
            if selected_mode == "upload" and bg_p.exists():
                return ImageOps.fit(Image.open(bg_p).convert("RGBA"), (W, H), method=Image.Resampling.LANCZOS)

            if selected_mode == "url" and conf.get("background_url"):
                try:
                    async with aiohttp.ClientSession() as s:
                        async with s.get(conf["background_url"]) as r:
                            if r.status == 200:
                                raw = await r.read()
                                return ImageOps.fit(Image.open(io.BytesIO(raw)).convert("RGBA"), (W, H), method=Image.Resampling.LANCZOS)
                except:
                    pass

            if selected_mode == "hex":
                c1 = self._hex_to_rgb(conf.get("bg_color_1", "#2c2f33"))
                c2_hex = conf.get("bg_color_2", "")
                if c2_hex:
                    c2 = self._hex_to_rgb(c2_hex)
                    image = Image.new("RGBA", (W, H))
                    draw = ImageDraw.Draw(image)
                    for y in range(H):
                        ratio = y / max(H - 1, 1)
                        r = int(c1[0] + (c2[0] - c1[0]) * ratio)
                        g = int(c1[1] + (c2[1] - c1[1]) * ratio)
                        b = int(c1[2] + (c2[2] - c1[2]) * ratio)
                        draw.line([(0, y), (W, y)], fill=(r, g, b, 255))
                    return image
                return Image.new("RGBA", (W, H), color=(*c1, 255))

            if bg_p.exists():
                return ImageOps.fit(Image.open(bg_p).convert("RGBA"), (W, H), method=Image.Resampling.LANCZOS)
            return Image.new("RGBA", (W, H), color=(44, 47, 51, 255))

        if mode == "banner":
            banner_url = None
            if getattr(member, "banner", None):
                banner_url = str(member.banner.url)
            if not banner_url:
                try:
                    fetched = await self.bot.fetch_user(member.id)
                    if fetched.banner:
                        banner_url = str(fetched.banner.url)
                except:
                    pass

            if banner_url:
                try:
                    async with aiohttp.ClientSession() as s:
                        async with s.get(banner_url) as r:
                            if r.status == 200:
                                raw = await r.read()
                                return ImageOps.fit(Image.open(io.BytesIO(raw)).convert("RGBA"), (W, H), method=Image.Resampling.LANCZOS)
                except:
                    pass
            fallback_mode = "default"
            if conf.get("banner_fallback_enabled", False):
                fallback_mode = conf.get("banner_fallback_mode", "default")
            return await build_for_mode(fallback_mode)

        return await build_for_mode(mode)

    def parse(self, text, member):
        m = {"{user}": member.name, "{user.mention}": member.mention, "{guild}": member.guild.name, "{guild.count}": str(member.guild.member_count)}
        for k, v in m.items(): text = text.replace(k, v)
        return text

    async def get_config_embed(self, guild, user):
        conf = self.data_manager.get_config(guild.id)
        chan = f"<#{conf['channel_id']}>" if conf['channel_id'] else "❌"
        bg_text = self.get_background_status_text(conf)
        fallback_text = self.get_banner_fallback_text(conf)
        fallback_line = f"\n*Si aucune bannière :* {fallback_text}" if conf.get("background_mode") == "banner" else ""
        desc = f"📍 **Salon :** {chan}\n🖼️ **Fond :** {bg_text}{fallback_line}\n\n**Titre :** {self.parse(conf['embed_title'], user)}\n**Desc :** {self.parse(conf['embed_description'], user)}\n**Msg :** {self.parse(conf['content_message'], user)}"
        if config_manager:
            e = config_manager.get_formatted_embed(guild, user, self.bot, "⚙️ Config Au Revoir", desc, guild.id)
        else: e = discord.Embed(title="⚙️ Config Au Revoir", description=desc, color=0xe74c3c)
        e.set_image(url="attachment://preview.png")
        return e

    @commands.hybrid_command(name="aurevoir", description="Configure le système de départ des membres.")
    @app_commands.default_permissions(administrator=True)
    @commands.has_permissions(administrator=True)
    async def aurevoir(self, ctx):
        await ctx.defer()
        img = await self.create_leave_image(ctx.author, ctx.guild.id)
        embed = await self.get_config_embed(ctx.guild, ctx.author)
        view = LeaveView(self, ctx.guild.id, ctx.author)
        msg = await ctx.send(embed=embed, file=discord.File(img, "preview.png"), view=view)
        view.message = msg

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        conf = self.data_manager.get_config(member.guild.id)
        if not conf['channel_id']: return
        chan = member.guild.get_channel(conf['channel_id'])
        if chan:
            img = await self.create_leave_image(member, member.guild.id)
            title = self.parse(conf['embed_title'], member)
            desc = self.parse(conf['embed_description'], member)
            if config_manager:
                e = config_manager.get_formatted_embed(member.guild, member, self.bot, title, desc, member.guild.id)
            else: e = discord.Embed(title=title, description=desc, color=0xe74c3c)
            e.set_image(url="attachment://leave.png")
            await chan.send(content=self.parse(conf['content_message'], member), embed=e, file=discord.File(img, "leave.png"))

async def setup(bot): await bot.add_cog(AuRevoir(bot))