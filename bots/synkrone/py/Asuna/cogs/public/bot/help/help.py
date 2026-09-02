# Version : 8.0.0 - Full Integration with Config Manager
import discord
from discord.ext import commands
from discord import ui
from pathlib import Path
import json
import traceback

# ===================== IMPORTATION CONFIG MANAGER ====================
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# ===================== RÉSOLUTION DU PRÉFIXE ========================
def _get_help_prefix(bot, guild_id: int) -> str:
    """
    Retourne le préfixe à afficher dans le help, par priorité :
      1. 1er préfixe personnalisé du serveur (module prefix.py)
      2. Préfixe du cog BotAdmin en mémoire (panelbot)
      3. bot_config.json (panelbot)
      4. Fallback '!'
    """
    import os, json as _json

    try:
        prefix_file = os.path.join(
            'cogs', 'addons', 'prefix', 'data', f'{guild_id}.json'
        )
        if os.path.exists(prefix_file):
            with open(prefix_file, 'r', encoding='utf-8') as f:
                data = _json.load(f)
            server_prefixes = data.get('prefixes', [])
            if server_prefixes:
                return server_prefixes[0]
    except Exception:
        pass

    try:
        cog = bot.cogs.get('BotAdmin')
        if cog and hasattr(cog, 'default_prefix'):
            return cog.default_prefix
    except Exception:
        pass

    try:
        cfg = os.path.join('cogs', 'owner', 'commands', 'panelbot', 'bot_config.json')
        if os.path.exists(cfg):
            with open(cfg, 'r', encoding='utf-8') as f:
                prefix = _json.load(f).get('prefix')
            if prefix:
                return prefix
    except Exception:
        pass

    return '!'

async def _is_bot_owner(bot, user) -> bool:
    """Retourne True si l'utilisateur est owner du bot."""
    try:
        if await bot.is_owner(user):
            return True
    except Exception:
        pass

    try:
        from cogs.addons.owner.owner import load_allowed, CREATOR_ID
        allowed = load_allowed()
        return user.id == CREATOR_ID or user.id in allowed
    except Exception:
        return False


def _is_guild_admin(user) -> bool:
    """Retourne True si l'utilisateur est administrateur du serveur."""
    perms = getattr(user, 'guild_permissions', None)
    return bool(perms and perms.administrator)

# Variable pour activer/désactiver la génération automatique des JSON
AUTO_GENERATE_JSON = False

# ==============================================================================
# --------------------------- COMPONENTS ---------------------------------------
# ==============================================================================

class HelpSelect(ui.Select):
    def __init__(self, author, bot, categories_data):
        options = []
        keys = list(categories_data.keys())

        # new en premier si présent
        if "new" in keys:
            data = categories_data["new"]
            label = data.get("category_name", "Nouveauté")
            emoji = data.get("emoji", "✨")
            options.append(discord.SelectOption(label=label, value="new", emoji=emoji))
            keys.remove("new")

        # decouvrez_aussi en dernier si présent
        has_decouvrez = False
        if "decouvrez_aussi" in keys:
            has_decouvrez = True
            keys.remove("decouvrez_aussi")

        # Ajout des autres catégories dans l'ordre d'apparition
        for file_id in keys:
            data = categories_data[file_id]
            label = data.get("category_name", file_id.capitalize())
            emoji = data.get("emoji", "📂")
            options.append(discord.SelectOption(label=label, value=file_id, emoji=emoji))

        if has_decouvrez:
            data = categories_data["decouvrez_aussi"]
            label = data.get("category_name", "Découvrez aussi")
            emoji = data.get("emoji", "🌐")
            options.append(discord.SelectOption(label=label, value="decouvrez_aussi", emoji=emoji))

        super().__init__(placeholder="📍 Choisissez une catégorie...", options=options)
        self.author = author
        self.bot = bot
        self.categories_data = categories_data

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author.id:
            return await interaction.response.send_message("❌ Ce menu ne vous appartient pas.", ephemeral=True)
            
        file_id = self.values[0]
        embed = self.view.create_category_embed(file_id, self.author, interaction.guild)
        await interaction.response.edit_message(embed=embed, view=self.view)

class HelpView(ui.View):
    def __init__(self, author, bot, categories_data):
        super().__init__(timeout=180)
        self.author = author
        self.bot = bot
        self.categories_data = categories_data
        if categories_data:
            self.add_item(HelpSelect(author, bot, categories_data))

    def create_category_embed(self, file_id, author, guild):
        data = self.categories_data.get(file_id, {})
        emoji = data.get("emoji", "📂")
        cat_name = data.get("category_name", file_id.capitalize())
        cat_desc = data.get("category_description", "")
        sections = data.get("sections", {})

        # Résolution du préfixe actif pour ce serveur
        prefix = _get_help_prefix(self.bot, guild.id if guild else 0)

        # Construction de la description
        content = f"*{cat_desc}*\n" if cat_desc else ""

        # Ligne des préfixes configurés (si plusieurs)
        try:
            import os as _os, json as _json
            prefix_file = _os.path.join('cogs', 'addons', 'prefix', 'data', f'{guild.id}.json')
            if guild and _os.path.exists(prefix_file):
                with open(prefix_file, 'r', encoding='utf-8') as _f:
                    _data = _json.load(_f)
                server_prefixes = _data.get('prefixes', [])
                if len(server_prefixes) >= 1:
                    prefixes_str = " ".join(f"`{p}`" for p in server_prefixes)
                    content += f"-# *Préfixes configurés : {prefixes_str}*\n"
        except Exception:
            pass
        
        if not sections:
            content += "\n*Aucune section trouvée dans cette catégorie.*"
        else:
            for section_title, commands_list in sections.items():
                content += f"\n**─── {section_title.upper()} ───**\n"
                for cmd_custom, desc in commands_list.items():
                    cmd_display = cmd_custom.replace("{prefix}", prefix)
                    desc_display = desc.replace("{prefix}", prefix) if desc else desc
                    content += f"› {cmd_display} : *{desc_display}*\n"

        title = f"{emoji} Aide : {cat_name}"
        
        # --- UTILISATION DU CONFIG MANAGER (Comme dans pingpong.py) ---
        if config_manager:
            embed = config_manager.get_formatted_embed(
                guild=guild,
                user=author,
                bot=self.bot,
                title=title,
                description=content,
                target_id=guild.id if guild else None
            )
        else:
            embed = discord.Embed(title=title, description=content, color=0x2b2d31)
            embed.set_author(name=f"Demandé par {author.display_name}", icon_url=author.display_avatar.url)
            
        return embed

# ==============================================================================
# --------------------------- COG HELP -----------------------------------------
# ==============================================================================

class HelpCommand(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.path = Path(__file__).parent
        self.json_folder = self.path / "catégorie"
        self.json_folder.mkdir(exist_ok=True)
        
        # Supprime l'aide par défaut pour éviter le conflit initial
        if self.bot.get_command('help'):
            self.bot.remove_command('help')

    @commands.Cog.listener()
    async def on_ready(self):
        if AUTO_GENERATE_JSON:
            self.sync_json_categories()

    def sync_json_categories(self):
        """Scanne les commandes et génère les JSON de base."""
        try:
            found_data = {}
            for command in self.bot.walk_commands():
                if command.hidden or isinstance(command, commands.Group) or not command.cog:
                    continue
                
                module_parts = command.cog.__module__.split('.')
                if len(module_parts) >= 2:
                    folder_name = module_parts[1]
                    if folder_name not in found_data:
                        found_data[folder_name] = {}
                    
                    # Format par défaut pour la génération
                    cmd_key = f"`/{command.name}`"
                    found_data[folder_name][cmd_key] = command.description or "Aucune description."

            for folder, cmds in found_data.items():
                file_path = self.json_folder / f"{folder}.json"
                
                if file_path.exists():
                    with open(file_path, "r", encoding="utf-8") as f:
                        current_json = json.load(f)
                else:
                    current_json = {
                        "emoji": "📂",
                        "category_name": folder.capitalize(),
                        "category_description": f"Commandes de la catégorie {folder}.",
                        "sections": { "Général": {} }
                    }

                # Vérification de l'existence des commandes dans les sections
                updated = False
                for cmd_name, cmd_desc in cmds.items():
                    exists = False
                    for section in current_json.get("sections", {}).values():
                        if cmd_name in section:
                            exists = True
                            break
                    
                    if not exists:
                        if "sections" not in current_json: current_json["sections"] = {"Général": {}}
                        first_section = list(current_json["sections"].keys())[0]
                        current_json["sections"][first_section][cmd_name] = cmd_desc
                        updated = True

                if updated or not file_path.exists():
                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(current_json, f, indent=4, ensure_ascii=False)

        except Exception as e:
            print(f"[HELP ERROR] Sync JSON : {e}")

    def load_json_data(self):
        """Charge les JSON pour le menu en priorisant new et decouvrez_aussi."""
        data = {}
        files = sorted(self.json_folder.glob("*.json"), key=lambda p: p.name)

        # Charger new.json d'abord si présent
        new_path = self.json_folder / "new.json"
        if new_path.exists():
            try:
                with open(new_path, "r", encoding="utf-8") as f:
                    new_data = json.load(f)
                special_new = {
                    "emoji": "✨",
                    "category_name": new_data.get("category_name", "Nouveauté"),
                    "category_description": new_data.get("category_description", f"Version : {new_data.get('version', 'N/A')}"),
                    "sections": {}
                }
                for key, label in [
                    ("ajout", "Ajouts"),
                    ("amelioration", "Améliorations"),
                    ("modification", "Modifications"),
                    ("correction", "Corrections"),
                    ("nerf", "Nerfs"),
                    ("suppression", "Suppressions")
                ]:
                    items = new_data.get(key, [])
                    if items:
                        special_new["sections"][label] = {item: "" for item in items}
                data["new"] = special_new
            except Exception:
                pass

        for file in files:
            if file.name == "new.json":
                continue
            try:
                with open(file, "r", encoding="utf-8") as f:
                    item = json.load(f)
                data[file.stem] = item
            except Exception:
                pass
        return data

    def filter_categories(self, categories_data, is_owner: bool, is_admin: bool):
        """Filtre les catégories d'aide selon les droits de l'utilisateur."""
        filtered = {}
        for file_id, data in categories_data.items():
            if data.get("requires_owner") and not is_owner:
                continue
            if data.get("requires_admin") and not is_admin:
                continue
            filtered[file_id] = data
        return filtered

    @commands.hybrid_command(name="help", description="Affiche le centre d'aide interactif.")
    async def help(self, ctx: commands.Context):
        try:
            # Pour le help, on peut aussi faire un defer si on a beaucoup de JSON
            if ctx.interaction:
                await ctx.defer(ephemeral=False)

            categories_data = self.load_json_data()
            if not categories_data:
                return await ctx.send("❌ Aucun module d'aide trouvé.")

            is_owner = await _is_bot_owner(self.bot, ctx.author)
            is_admin = bool(ctx.guild and _is_guild_admin(ctx.author))
            categories_data = self.filter_categories(categories_data, is_owner, is_admin)

            if not categories_data:
                return await ctx.send("❌ Vous n'avez pas accès aux catégories d'aide disponibles.")

            view = HelpView(ctx.author, self.bot, categories_data)
            
            if "new" in categories_data:
                embed = view.create_category_embed("new", ctx.author, ctx.guild)
            else:
                # Recherche du module par défaut (Casino)
                default_cat = None
                for file_id, data in categories_data.items():
                    if data.get("category_name", "").lower().startswith("casino") or file_id.lower() == "casino":
                        default_cat = file_id
                        break
                if not default_cat:
                    default_cat = list(categories_data.keys())[0]
                embed = view.create_category_embed(default_cat, ctx.author, ctx.guild)
            
            if ctx.interaction:
                await ctx.send(embed=embed, view=view)
            else:
                await ctx.send(embed=embed, view=view, reference=ctx.message, mention_author=True)

        except Exception:
            traceback.print_exc()
            await ctx.send("❌ Une erreur est survenue lors de l'ouverture du menu d'aide.")

async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCommand(bot))