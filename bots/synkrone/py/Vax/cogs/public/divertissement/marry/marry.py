import discord
from discord.ext import commands
from discord import app_commands, ui
import json
import time
from datetime import datetime, timezone
from pathlib import Path
import traceback
import math

# ==============================================================================
# --------------------------- CONFIGURATION & CHEMINS --------------------------
# ==============================================================================
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

BASE_DIR = Path.cwd()
DATA_DIR = BASE_DIR / "data" / "public" / "divertissement" / "data_marry"

# ==============================================================================
# ----------------------------- GESTION DES DONNÉES ----------------------------
# ==============================================================================
class MarryDataManager:
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    def get_file_path(self, user_id: int) -> Path:
        return DATA_DIR / f"{user_id}.json"

    def load_user(self, user_id: int, user_name: str) -> dict:
        """Charge ou crée les données d'un utilisateur."""
        path = self.get_file_path(user_id)
        if not path.exists():
            return {
                "user_name": user_name,
                "points": 0,
                "marriages_count": 0,
                "refusals_received": 0,
                "refusals_given": 0,
                "current_marriages": [],
                "history": []
            }
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Assure la rétrocompatibilité des clés manquantes
                if "points" not in data: data["points"] = 0
                return data
        except Exception as e:
            print(f"[ERROR] Chargement data_marry pour {user_id} : {e}")
            return {"user_name": user_name, "points": 0, "marriages_count": 0, "refusals_received": 0, "refusals_given": 0, "current_marriages": [], "history": []}

    def save_user(self, user_id: int, data: dict):
        path = self.get_file_path(user_id)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"[ERROR] Sauvegarde data_marry pour {user_id} : {e}")

    def add_history(self, user_id: int, user_name: str, entry: str):
        data = self.load_user(user_id, user_name)
        now_str = datetime.now().strftime("[%d/%m/%y][%H:%M]")
        data["history"].insert(0, f"{now_str} {entry}")
        self.save_user(user_id, data)

db = MarryDataManager()

# ==============================================================================
# ------------------------------ VUES INTERACTIVES -----------------------------
# ==============================================================================

# ========================== VUE CONFIRMATION DIVORCE =========================
class DivorceConfirmView(ui.View):
    def __init__(self, cog, guild, author, partner_id, partner_name):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.author = author
        self.partner_id = partner_id
        self.partner_name = partner_name

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Action non autorisée.", ephemeral=True)
            return False
        return True

    @ui.button(label="Confirmer le divorce", style=discord.ButtonStyle.danger, emoji="💔")
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        try:
            await interaction.response.defer()
        except discord.errors.InteractionResponded:
            pass

        author_data = db.load_user(self.author.id, self.author.display_name)
        partner_data = db.load_user(self.partner_id, self.partner_name)
        
        # Suppression de l'union
        author_data["current_marriages"] = [m for m in author_data["current_marriages"] if m["partner_id"] != self.partner_id]
        partner_data["current_marriages"] = [m for m in partner_data["current_marriages"] if m["partner_id"] != self.author.id]
        
        db.save_user(self.author.id, author_data)
        db.save_user(self.partner_id, partner_data)
        
        db.add_history(self.author.id, self.author.display_name, f"Vous avez divorcé de {self.cog.format_mention(self.guild, self.partner_id, self.partner_name)}.")
        db.add_history(self.partner_id, self.partner_name, f"{self.cog.format_mention(self.guild, self.author.id, self.author.display_name)} a demandé le divorce.")
        
        # Retour au profil
        profile_view = MarryProfileView(self.cog, self.guild, self.author, self.author)
        embed = profile_view.build_profile_embed()
        await interaction.edit_original_response(content="✅ Le divorce a été prononcé.", embed=embed, view=profile_view)

    @ui.button(label="Annuler", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        profile_view = MarryProfileView(self.cog, self.guild, self.author, self.author)
        embed = profile_view.build_profile_embed()
        await interaction.response.edit_message(content=None, embed=embed, view=profile_view)


# ========================== VUE DIVORCE SELECTEUR ============================
class DivorceSelectView(ui.View):
    def __init__(self, cog, guild, author, marriages):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.author = author
        options = [
            discord.SelectOption(
                label=f"Divorcer de {m['partner_name']}",
                value=f"{m['partner_id']}|{m['partner_name']}",
                emoji="💔"
            ) for m in marriages[:25]
        ]
        self.select = ui.Select(placeholder="Choisissez l'union à rompre...", options=options)
        self.select.callback = self.select_callback
        self.add_item(self.select)

        # Bouton retour au profil
        btn_back = ui.Button(label="Retour au profil", style=discord.ButtonStyle.secondary, emoji="🔙")
        btn_back.callback = self.go_back
        self.add_item(btn_back)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Action non autorisée.", ephemeral=True)
            return False
        return True

    async def select_callback(self, interaction: discord.Interaction):
        partner_id_str, partner_name = self.select.values[0].split('|')
        partner_id = int(partner_id_str)
        confirm_view = DivorceConfirmView(self.cog, self.guild, self.author, partner_id, partner_name)
        embed = self.cog.create_embed(
            self.guild, self.author,
            "⚖️ Procédure de Divorce",
            f"Êtes-vous sûr de vouloir divorcer de **{partner_name}** ? Cette action est définitive."
        )
        await interaction.response.edit_message(embed=embed, view=confirm_view)

    async def go_back(self, interaction: discord.Interaction):
        profile_view = MarryProfileView(self.cog, self.guild, self.author, self.author)
        embed = profile_view.build_profile_embed()
        await interaction.response.edit_message(embed=embed, view=profile_view)


# ========================== VUE PROFIL ============================
class MarryProfileView(ui.View):
    def __init__(self, cog, guild, author, target_user):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.author = author
        self.target = target_user
        self.current_page = 0
        self.mode = "profil" # "profil" ou "history"
        self.setup_buttons()

    def setup_buttons(self):
        self.clear_items()
        is_owner = self.author.id == self.target.id
        data = db.load_user(self.target.id, self.target.display_name)

        if self.mode == "profil":
            btn_hist = ui.Button(label="Historique Sentimental", style=discord.ButtonStyle.primary, emoji="📜")
            btn_hist.callback = self.show_history
            self.add_item(btn_hist)

            # Si c'est l'auteur et qu'il est marié, il peut divorcer
            if is_owner and data["current_marriages"]:
                btn_divorce = ui.Button(label="Gérer mes unions", style=discord.ButtonStyle.secondary, emoji="💔")
                btn_divorce.callback = self.show_divorce_menu
                self.add_item(btn_divorce)

        elif self.mode == "history":
            btn_profil = ui.Button(label="Retour au profil", style=discord.ButtonStyle.secondary, emoji="🔙")
            btn_profil.callback = self.show_profile
            self.add_item(btn_profil)

            max_pages = max(1, math.ceil(len(data["history"]) / 10))

            btn_prev = ui.Button(label="◀ Précédent", style=discord.ButtonStyle.primary, disabled=(self.current_page == 0))
            btn_prev.callback = self.prev_page
            self.add_item(btn_prev)

            btn_next = ui.Button(label="Suivant ▶", style=discord.ButtonStyle.primary, disabled=(self.current_page >= max_pages - 1))
            btn_next.callback = self.next_page
            self.add_item(btn_next)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Vous ne pouvez pas interagir avec ce menu.", ephemeral=True)
            return False
        return True

    def build_profile_embed(self) -> discord.Embed:
        data = db.load_user(self.target.id, self.target.display_name)

        desc = ""
        if data['refusals_received'] != 0:
            desc += f"🚫 **Râteaux Reçus :** `{data['refusals_received']}`\n"
        if data['refusals_given'] != 0:
            desc += f"🚫 **Râteaux Donnés :** `{data['refusals_given']}`\n"

        if data["current_marriages"]:
            if desc:
                desc += "\n"
            desc += "### 💞 Unions Actuelles\n"
            for m in data["current_marriages"]:
                partner_mention = self.cog.format_mention(self.guild, m['partner_id'], m['partner_name'])
                time_str = f"<t:{m['timestamp']}:R>"
                if m['proposer_id'] == self.target.id:
                    desc += f"› A demandé en mariage {partner_mention} {time_str}\n"
                else:
                    desc += f"› Demandé(e) en mariage par {partner_mention} {time_str}\n"
        else:
            if desc:
                desc += "\n"
            desc += "### 🕊️ Célibataire\n*Aucune union en cours.*"

        embed = self.cog.create_embed(self.guild, self.author, "", desc)
        embed.set_author(name=f"Union de {self.target.display_name}", icon_url=self.target.display_avatar.url)
        embed.set_thumbnail(url=self.target.display_avatar.url)
        return embed

    def build_history_embed(self) -> discord.Embed:
        data = db.load_user(self.target.id, self.target.display_name)
        history = data["history"]
        
        if not history:
            desc = "L'historique est vide."
        else:
            start = self.current_page * 10
            end = start + 10
            desc = "\n".join(history[start:end])
            
        max_pages = max(1, math.ceil(len(history) / 10))
        embed = self.cog.create_embed(self.guild, self.author, f"📖 Historique Sentimental - Page {self.current_page + 1}/{max_pages}", desc)
        embed.set_author(name=f"Historique de {self.target.display_name}", icon_url=self.target.display_avatar.url)
        return embed

    async def show_profile(self, interaction: discord.Interaction):
        self.mode = "profil"
        self.setup_buttons()
        await interaction.response.edit_message(embed=self.build_profile_embed(), view=self)

    async def show_history(self, interaction: discord.Interaction):
        self.mode = "history"
        self.current_page = 0
        self.setup_buttons()
        await interaction.response.edit_message(embed=self.build_history_embed(), view=self)

    async def prev_page(self, interaction: discord.Interaction):
        self.current_page -= 1
        self.setup_buttons()
        await interaction.response.edit_message(embed=self.build_history_embed(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.current_page += 1
        self.setup_buttons()
        await interaction.response.edit_message(embed=self.build_history_embed(), view=self)

    async def show_divorce_menu(self, interaction: discord.Interaction):
        data = db.load_user(self.author.id, self.author.display_name)
        select_view = DivorceSelectView(self.cog, self.guild, self.author, data["current_marriages"])
        embed = self.cog.create_embed(self.guild, self.author, "💔 Menu des divorces", "Sélectionnez l'union que vous souhaitez rompre :")
        await interaction.response.edit_message(embed=embed, view=select_view)


# ========================== VUE DEMANDE EN MARIAGE ===========================
class ProposalView(ui.View):
    def __init__(self, cog, guild, proposer, target):
        super().__init__(timeout=300)
        self.cog = cog
        self.guild = guild
        self.proposer = proposer
        self.target = target

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target.id:
            await interaction.response.send_message("❌ Cette demande ne vous est pas destinée.", ephemeral=True)
            return False
        return True

    @ui.button(label="Oui je le veux", style=discord.ButtonStyle.success, emoji="❤️")
    async def accept(self, interaction: discord.Interaction, button: ui.Button):
        if self.target.bot:
            if self.guild is not None and self.proposer.id != self.guild.owner_id:
                embed = self.cog.create_embed(
                    self.guild, self.proposer,
                    "Refus automatique",
                    "❌ Seul le propriétaire du serveur peut marier le bot."
                )
                for item in self.children: item.disabled = True
                await interaction.response.edit_message(embed=embed, view=self)
                return
                
        await interaction.response.defer()
        now_ts = int(time.time())

        proposer_data = db.load_user(self.proposer.id, self.proposer.display_name)
        target_data = db.load_user(self.target.id, self.target.display_name)

        proposer_data["marriages_count"] += 1
        target_data["marriages_count"] += 1

        marriage_record_proposer = {
            "partner_id": self.target.id,
            "partner_name": self.target.display_name,
            "timestamp": now_ts,
            "proposer_id": self.proposer.id
        }
        marriage_record_target = {
            "partner_id": self.proposer.id,
            "partner_name": self.proposer.display_name,
            "timestamp": now_ts,
            "proposer_id": self.proposer.id
        }

        proposer_data["current_marriages"].append(marriage_record_proposer)
        target_data["current_marriages"].append(marriage_record_target)

        db.save_user(self.proposer.id, proposer_data)
        db.save_user(self.target.id, target_data)

        db.add_history(self.proposer.id, self.proposer.display_name, f"Vous vous êtes marié(e) avec {self.cog.format_mention(self.guild, self.target.id, self.target.display_name)}.")
        db.add_history(self.target.id, self.target.display_name, f"Vous avez accepté la demande en mariage de {self.cog.format_mention(self.guild, self.proposer.id, self.proposer.display_name)}.")

        embed = self.cog.create_embed(
            self.guild, self.proposer,
            "🎉 Vive les Mariés ! 🎉",
            f"{self.target.mention} a dit **OUI** à {self.proposer.mention} ! Que votre union soit belle et durable."
        )
        embed.set_image(url="https://i.imgur.com/uFk1L9X.gif")
        
        for item in self.children: item.disabled = True
        await interaction.edit_original_response(embed=embed, view=self)

    @ui.button(label="Sorry", style=discord.ButtonStyle.secondary, emoji="💔")
    async def deny(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer()

        proposer_data = db.load_user(self.proposer.id, self.proposer.display_name)
        target_data = db.load_user(self.target.id, self.target.display_name)

        proposer_data["refusals_received"] += 1
        target_data["refusals_given"] += 1

        db.save_user(self.proposer.id, proposer_data)
        db.save_user(self.target.id, target_data)

        db.add_history(self.proposer.id, self.proposer.display_name, f"{self.cog.format_mention(self.guild, self.target.id, self.target.display_name)} a refusé votre demande en mariage.")
        db.add_history(self.target.id, self.target.display_name, f"Vous avez refusé la demande de {self.cog.format_mention(self.guild, self.proposer.id, self.proposer.display_name)}.")

        embed = self.cog.create_embed(
            self.guild, self.proposer,
            "🥀 Aïe... Coup dur.",
            f"{self.target.mention} a gentiment repoussé la demande de {self.proposer.mention}."
        )

        for item in self.children: item.disabled = True
        await interaction.edit_original_response(embed=embed, view=self)

# ==============================================================================
# ------------------------------- COG MARRY ------------------------------------
# ==============================================================================
class Marry(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def create_embed(self, guild, user, title, description):
        """Générateur d'embed stylisé avec fallback sur ConfigManager."""
        if config_manager:
            return config_manager.get_formatted_embed(
                guild=guild, user=user, bot=self.bot, 
                title=title, description=description, target_id=guild.id if guild else None
            )
        return discord.Embed(title=title, description=description, color=0xff69b4)

    def format_mention(self, guild: discord.Guild, user_id: int, user_name: str) -> str:
        """Formate la mention : @user si sur le serveur, `@nom` sinon."""
        member = guild.get_member(user_id)
        if member:
            return member.mention
        return f"`@{user_name}`"

    @commands.hybrid_command(name="marry", description="Affiche votre menu de mariage ou celui d'un autre utilisateur.")
    @app_commands.describe(membre="L'utilisateur dont vous souhaitez voir le profil (Optionnel)")
    async def marry(self, ctx: commands.Context, membre: discord.Member = None):
        target = membre or ctx.author
        db.load_user(target.id, target.display_name) # Initialisation garantie

        view = MarryProfileView(self, ctx.guild, ctx.author, target)
        embed = view.build_profile_embed()
        if ctx.interaction:
            await ctx.send(embed=embed, view=view)
        else:
            await ctx.send(embed=embed, view=view, reference=ctx.message)


    @commands.hybrid_command(name="marryme", description="Fait une demande en mariage à un autre membre.")
    @app_commands.describe(membre="L'élu(e) de votre cœur.")
    async def marryme(self, ctx: commands.Context, membre: discord.Member):
        if membre.id == ctx.author.id:
            return await ctx.send("❌ Vous ne pouvez pas vous marier avec vous-même. Essayez de trouver quelqu'un d'autre !", ephemeral=True)

        author_data = db.load_user(ctx.author.id, ctx.author.display_name)
        
        # Vérification si déjà marié avec cette personne (Humain ou Bot)
        if any(m["partner_id"] == membre.id for m in author_data["current_marriages"]):
            return await ctx.send("❌ Vous êtes déjà marié(e) avec cette personne !", ephemeral=True)

        # Cas spécial : cible = bot
        if membre.bot:
            if ctx.guild is not None and ctx.author.id == ctx.guild.owner_id:
                bot_data = db.load_user(membre.id, membre.display_name)
                now_ts = int(time.time())

                author_data["marriages_count"] += 1
                bot_data["marriages_count"] += 1

                marriage_record_author = {
                    "partner_id": membre.id,
                    "partner_name": membre.display_name,
                    "timestamp": now_ts,
                    "proposer_id": ctx.author.id
                }
                marriage_record_bot = {
                    "partner_id": ctx.author.id,
                    "partner_name": ctx.author.display_name,
                    "timestamp": now_ts,
                    "proposer_id": ctx.author.id
                }
                author_data["current_marriages"].append(marriage_record_author)
                bot_data["current_marriages"].append(marriage_record_bot)
                
                db.save_user(ctx.author.id, author_data)
                db.save_user(membre.id, bot_data)
                db.add_history(ctx.author.id, ctx.author.display_name, f"Vous vous êtes marié(e) avec {self.format_mention(ctx.guild, membre.id, membre.display_name)}.")
                db.add_history(membre.id, membre.display_name, f"Vous avez accepté la demande en mariage de {self.format_mention(ctx.guild, ctx.author.id, ctx.author.display_name)}.")

                embed = self.create_embed(
                    ctx.guild, ctx.author,
                    "🎉 Vive les Mariés ! 🎉",
                    f"{membre.mention} a dit **OUI** à {ctx.author.mention} ! Que votre union soit belle et durable."
                )
                return await ctx.send(embed=embed)
            else:
                return await ctx.send("❌ Les bots n'ont pas de sentiments (pour le moment). Seul le propriétaire du serveur peut marier le bot !", ephemeral=True)


        desc = f"💌 **{membre.mention}, consentez-vous à épouser {ctx.author.mention} ?**\n\n*Prenez votre temps, ce choix pourrait vous coûter des points de fidélité !*"
        embed = self.create_embed(ctx.guild, ctx.author, "", desc)
        embed.set_author(name=f"{ctx.author.display_name} vous demande en mariage", icon_url=ctx.author.display_avatar.url)

        view = ProposalView(self, ctx.guild, ctx.author, membre)

        if ctx.interaction:
            await ctx.send(content=membre.mention, embed=embed, view=view)
        else:
            await ctx.send(content=membre.mention, embed=embed, view=view, reference=ctx.message)

async def setup(bot: commands.Bot):
    await bot.add_cog(Marry(bot))