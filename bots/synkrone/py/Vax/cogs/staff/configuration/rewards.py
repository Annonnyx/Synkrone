import discord
from discord.ext import commands
from discord import app_commands, ui
import json
import uuid
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

# ==============================================================================
# --------------------------- CONFIGURATION & CHEMINS --------------------------
# ==============================================================================
EMBED_COLOR = 0x3498db

# Chemin strict demandé : Racine du bot -> data -> staff -> configuration -> data_reward
BASE_DIR = Path.cwd()
DATA_DIR = BASE_DIR / "data" / "staff" / "configuration" / "data_reward"

# Tentative d'importation du config_manager global (Fallback assuré)
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# ==============================================================================
# --------------------------- INTERFACES UTILISATEUR ---------------------------
# ==============================================================================

class RewardModal(ui.Modal):
    """Modal dynamique utilisé pour Ajouter ou Modifier un reward."""
    name = ui.TextInput(label="Nom de l'événement", placeholder="Ex: Noël 2025", style=discord.TextStyle.short, required=True, max_length=50)
    date_str = ui.TextInput(label="Date requise (JJ/MM/AAAA)", placeholder="Ex: 25/12/2025", style=discord.TextStyle.short, required=True, min_length=10, max_length=10)
    title_str = ui.TextInput(label="Titre à obtenir (Optionnel)", placeholder="Ex: Lutin de Noël", style=discord.TextStyle.short, required=False, max_length=100)
    role_id = ui.TextInput(label="ID du rôle (Optionnel)", placeholder="Ex: 123456789101112131", style=discord.TextStyle.short, required=False, max_length=20)

    def __init__(self, cog, guild: discord.Guild, action: str = "add", reward_id: str = None, default_data: dict = None):
        super().__init__(title="Créer un Reward" if action == "add" else "Modifier le Reward")
        self.cog = cog
        self.guild = guild
        self.action = action
        self.reward_id = reward_id or str(uuid.uuid4())[:8]

        # Pré-remplissage en cas de modification
        if default_data:
            self.name.default = default_data.get("name", "")
            self.date_str.default = datetime.fromtimestamp(default_data.get("date_timestamp")).strftime("%d/%m/%Y")
            self.title_str.default = default_data.get("title", "")
            self.role_id.default = str(default_data.get("role_id", "")) if default_data.get("role_id") else ""

    async def on_submit(self, interaction: discord.Interaction):
        # 1. Validation de la date
        try:
            req_date = datetime.strptime(self.date_str.value.strip(), "%d/%m/%Y")
        except ValueError:
            return await interaction.response.send_message("❌ Le format de la date doit être exactement `JJ/MM/AAAA`.", ephemeral=True)

        # 2. Validation d'au moins une récompense
        if not self.title_str.value.strip() and not self.role_id.value.strip():
            return await interaction.response.send_message("❌ Vous devez définir au moins un Titre ou un ID de Rôle.", ephemeral=True)

        # 3. Validation de l'ID du rôle
        r_id = None
        if self.role_id.value.strip():
            if not self.role_id.value.isdigit():
                return await interaction.response.send_message("❌ L'ID du rôle doit être uniquement numérique.", ephemeral=True)
            r_id = int(self.role_id.value.strip())
            if not self.guild.get_role(r_id):
                return await interaction.response.send_message(f"❌ Impossible de trouver le rôle `{r_id}` sur ce serveur.", ephemeral=True)

        # 4. Sauvegarde
        config = self.cog.load_data(self.guild.id)
        config["rewards"][self.reward_id] = {
            "name": self.name.value.strip(),
            "date_timestamp": req_date.timestamp(),
            "title": self.title_str.value.strip() if self.title_str.value.strip() else None,
            "role_id": r_id
        }
        self.cog.save_data(self.guild.id, config)
        
        action_text = "créé" if self.action == "add" else "modifié"
        await interaction.response.send_message(f"✅ Le reward **{self.name.value}** a été {action_text} avec succès !", ephemeral=True)

class RewardActionSelect(ui.Select):
    """Sélecteur pour choisir un reward à modifier ou supprimer."""
    def __init__(self, cog, guild: discord.Guild, action: str):
        self.cog = cog
        self.guild = guild
        self.action = action
        
        config = self.cog.load_data(guild.id)
        options = []
        # Limitation à 25 options (limite API Discord)
        for r_id, r_data in list(config.get("rewards", {}).items())[:25]:
            date_str = datetime.fromtimestamp(r_data["date_timestamp"]).strftime("%d/%m/%Y")
            options.append(discord.SelectOption(
                label=r_data["name"][:100], 
                description=f"Date: {date_str}", 
                value=r_id,
                emoji="✏️" if action == "edit" else "🗑️"
            ))
            
        if not options:
            options.append(discord.SelectOption(label="Aucun reward configuré", value="none"))
            
        super().__init__(
            placeholder="Sélectionnez un reward à modifier..." if action == "edit" else "Sélectionnez un reward à supprimer...",
            min_values=1, max_values=1, options=options
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            return await interaction.response.send_message("❌ Aucun reward disponible.", ephemeral=True)
            
        reward_id = self.values[0]
        config = self.cog.load_data(self.guild.id)
        reward_data = config["rewards"].get(reward_id)

        if self.action == "edit":
            await interaction.response.send_modal(RewardModal(self.cog, self.guild, action="edit", reward_id=reward_id, default_data=reward_data))
        elif self.action == "delete":
            del config["rewards"][reward_id]
            self.cog.save_data(self.guild.id, config)
            await interaction.response.send_message(f"✅ Le reward **{reward_data['name']}** a été supprimé.", ephemeral=True)

class RewardConfigView(ui.View):
    """Menu spécifique pour Ajouter/Modifier/Supprimer."""
    def __init__(self, cog, guild: discord.Guild, author: discord.Member):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.author = author

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Action refusée.", ephemeral=True)
            return False
        return True

    @ui.button(label="Ajouter", style=discord.ButtonStyle.success, emoji="➕", row=0)
    async def btn_add(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(RewardModal(self.cog, self.guild, action="add"))

    @ui.button(label="Modifier", style=discord.ButtonStyle.primary, emoji="✏️", row=0)
    async def btn_edit(self, interaction: discord.Interaction, button: ui.Button):
        view = ui.View(timeout=300)
        view.add_item(RewardActionSelect(self.cog, self.guild, "edit"))
        await interaction.response.send_message("Choisissez le reward à modifier :", view=view, ephemeral=True)

    @ui.button(label="Supprimer", style=discord.ButtonStyle.danger, emoji="🗑️", row=0)
    async def btn_delete(self, interaction: discord.Interaction, button: ui.Button):
        view = ui.View(timeout=300)
        view.add_item(RewardActionSelect(self.cog, self.guild, "delete"))
        await interaction.response.send_message("Choisissez le reward à supprimer :", view=view, ephemeral=True)

class RewardAdminView(ui.View):
    """Menu principal administrateur."""
    def __init__(self, cog, guild: discord.Guild, author: discord.Member):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.author = author

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Ce menu ne vous appartient pas.", ephemeral=True)
            return False
        return True

    @ui.button(label="Configurer les rewards", style=discord.ButtonStyle.primary, custom_id="admin_config_reward", emoji="⚙️")
    async def btn_config(self, interaction: discord.Interaction, button: ui.Button):
        embed = self.cog.create_custom_embed(self.guild, self.author, "⚙️ Configuration des Rewards", "Choisissez une action ci-dessous : Ajouter, Modifier ou Supprimer un reward.")
        await interaction.response.edit_message(embed=embed, view=RewardConfigView(self.cog, self.guild, self.author))

    @ui.button(label="Mes rewards", style=discord.ButtonStyle.secondary, custom_id="admin_view_profile", emoji="🏆")
    async def btn_profile(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()
        embed = await self.cog.generate_profile_embed(self.guild, interaction.user, interaction.user)
        await interaction.edit_original_response(embed=embed, view=None)

# ==============================================================================
# ----------------------------- COG PRINCIPAL ----------------------------------
# ==============================================================================

class Rewards(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.configs = {}

    async def cog_load(self):
        """Création de l'arborescence au lancement du cog."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    def load_data(self, guild_id: int) -> dict:
        """Charge la configuration depuis le fichier JSON propre au serveur."""
        if guild_id in self.configs:
            return self.configs[guild_id]

        path = DATA_DIR / f"{guild_id}.json"
        default = {
            "rewards": {},  # reward_id -> {name, date_timestamp, title, role_id}
            "users": {}     # user_id -> {obtained_rewards: {reward_id: timestamp_obtention}}
        }

        if not path.exists():
            self.configs[guild_id] = default
            self.save_data(guild_id, default)
            return default

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                final_config = {**default, **data}
                if "rewards" not in final_config: final_config["rewards"] = {}
                if "users" not in final_config: final_config["users"] = {}
                self.configs[guild_id] = final_config
                return final_config
        except Exception as e:
            print(f"[ERROR Reward] Lecture de {path} échouée : {e}")
            return default

    def save_data(self, guild_id: int, config: dict):
        """Sauvegarde les données dans le fichier JSON du serveur."""
        self.configs[guild_id] = config
        path = DATA_DIR / f"{guild_id}.json"
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[ERROR Reward] Sauvegarde de {path} échouée : {e}")

    def create_custom_embed(self, guild, user, title, description):
        """Création d'embeds homogénéisés."""
        if config_manager:
            return config_manager.get_formatted_embed(
                guild=guild, user=user, bot=self.bot, title=title, description=description
            )
        embed = discord.Embed(title=title, description=description, color=EMBED_COLOR)
        if self.bot.user.avatar:
            embed.set_footer(text=self.bot.user.name, icon_url=self.bot.user.display_avatar.url)
        return embed

    async def generate_profile_embed(self, guild: discord.Guild, target: discord.Member, requester: discord.Member) -> discord.Embed:
        """Calcule les récompenses de l'utilisateur de manière dynamique."""
        config = self.load_data(guild.id)
        user_str_id = str(target.id)
        current_ts = datetime.now().timestamp()
        
        if user_str_id not in config["users"]:
            config["users"][user_str_id] = {"obtained_rewards": {}}

        user_data = config["users"][user_str_id]["obtained_rewards"]
        updated = False
        roles_to_add = []

        # 1. Analyse d'éligibilité
        for r_id, r_data in config["rewards"].items():
            if r_id not in user_data:
                # Si la date de l'event est passée et que le membre était présent avant ou ce jour-là
                if current_ts >= r_data["date_timestamp"]:
                    if target.joined_at and target.joined_at.timestamp() <= r_data["date_timestamp"]:
                        user_data[r_id] = r_data["date_timestamp"] 
                        updated = True
                        
                        if r_data.get("role_id"):
                            role = guild.get_role(r_data["role_id"])
                            if role and role not in target.roles:
                                roles_to_add.append(role)

        # 2. Application silencieuse des rôles
        if updated:
            self.save_data(guild.id, config)
            if roles_to_add and guild.me.guild_permissions.manage_roles:
                try:
                    await target.add_roles(*roles_to_add, reason="Auto-claim Rewards")
                except Exception as e:
                    print(f"[ERROR Reward] Attribution des rôles échouée : {e}")

        # 3. Formatage de l'affichage
        titres_list = []
        roles_list = []

        for r_id, obt_ts in user_data.items():
            if r_id in config["rewards"]:
                r_data = config["rewards"][r_id]
                date_str = datetime.fromtimestamp(obt_ts).strftime('%d/%m/%Y')
                
                if r_data.get("title"):
                    titres_list.append(f"• **{r_data['title']}** *(Obtenu le {date_str})*")
                if r_data.get("role_id"):
                    role = guild.get_role(r_data["role_id"])
                    if role:
                        roles_list.append(role.mention)

        desc = ""
        if not titres_list and not roles_list:
            desc = "Cet utilisateur n'a débloqué aucune récompense d'ancienneté pour le moment."
        else:
            if titres_list: desc += "### 🏆 Titres obtenus\n" + "\n".join(titres_list) + "\n\n"
            if roles_list: desc += "### 🎭 Rôles obtenus\n" + " ".join(roles_list)

        title = f"Profil Rewards : {target.display_name}"
        embed = self.create_custom_embed(guild, requester, title, desc)

        # 4. Ajout des Assets Discord
        embed.set_thumbnail(url=target.display_avatar.url)
        full_user = await self.bot.fetch_user(target.id) # Requis pour fetch la bannière
        if full_user.banner:
            embed.set_image(url=full_user.banner.url)

        return embed

    @commands.hybrid_command(name="reward", description="Affiche votre profil Reward ou configure le système.")
    @app_commands.describe(cible="L'utilisateur dont vous souhaitez voir le profil (Optionnel)")
    async def reward_cmd(self, ctx: commands.Context, cible: Optional[discord.Member] = None):
        """Commande Hybride Principale."""
        
        # Si cible définie OU l'auteur n'est pas Admin -> Rendu direct du profil
        if cible is not None or not ctx.author.guild_permissions.administrator:
            target_user = cible if cible else ctx.author
            await ctx.defer(ephemeral=False)
            
            try:
                embed = await self.generate_profile_embed(ctx.guild, target_user, ctx.author)
                if ctx.interaction:
                    await ctx.interaction.followup.send(embed=embed)
                else:
                    await ctx.send(embed=embed, reference=ctx.message, mention_author=False)
            except Exception as e:
                traceback.print_exc()
                await ctx.send("❌ Erreur lors de la génération du profil.", ephemeral=True)
            return

        # Si Admin et aucune cible -> Panneau de gestion
        embed = self.create_custom_embed(
            ctx.guild, ctx.author, "⚙️ Gestion des Rewards", 
            "Vous êtes administrateur. Souhaitez-vous configurer les récompenses ou consulter votre propre profil ?"
        )
        view = RewardAdminView(self, ctx.guild, ctx.author)
        
        if ctx.interaction:
            await ctx.send(embed=embed, view=view, ephemeral=True)
        else:
            await ctx.send(embed=embed, view=view, reference=ctx.message, mention_author=False)


async def setup(bot: commands.Bot):
    if bot.get_command("reward"):
        bot.remove_command("reward")
    await bot.add_cog(Rewards(bot))