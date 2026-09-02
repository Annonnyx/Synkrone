import aiohttp
import os
import discord
from discord import ui
from discord.ext import commands
import json
import time
from datetime import datetime
from pathlib import Path
import traceback

BASE_DIR = Path.cwd()
DATA_DIR = BASE_DIR / "data" / "public" / "data_vote"

# Import du gestionnaire d'embeds personnalisé
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# ==============================================================================
# --------------------------- INTERFACE UTILISATEUR ----------------------------
# ==============================================================================
class VoteView(ui.View):
    def __init__(self, bot_id: int):
        super().__init__(timeout=300)
        topgg_link = f"https://top.gg/bot/{bot_id}/vote"
        self.add_item(
            ui.Button(
                label="Voter sur Top.gg",
                style=discord.ButtonStyle.link,
                url=topgg_link,
                emoji=discord.PartialEmoji(name="top", id=1528770071445373109)
            )
        )

# ==============================================================================
# -------------------------------- COG VOTE ------------------------------------
# ==============================================================================
class Vote(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.data_file = DATA_DIR / "users.json"
        self._ensure_file()

        self.topgg_token = os.getenv("TOPGG_TOKEN")
        self.topgg = None
        if not self.topgg_token:
            print("[VOTE] TOPGG_TOKEN non défini. La vérification Top.gg via API est désactivée.")
        else:
            self.topgg = True

    def _ensure_file(self):
        if not self.data_file.exists():
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump({}, f, indent=4)

    def load_data(self) -> dict:
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def save_data(self, data: dict):
        try:
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"[ERREUR - Vote] Sauvegarde JSON : {e}")

    def create_custom_embed(self, guild, user, title, description):
        """Génère l'embed via le config_manager ou le fallback natif."""
        safe_title = title or "Vote"
        if config_manager:
            return config_manager.get_formatted_embed(
                guild=guild, 
                user=user, 
                bot=self.bot, 
                title=safe_title, 
                description=description,
                target_id=guild.id if guild else None
            )
        embed = discord.Embed(title=safe_title, description=description, color=0x3498db)
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        return embed

    async def _has_topgg_vote(self, user_id: int) -> bool:
        if not self.topgg:
            return False

        url = f"https://top.gg/api/bots/{self.bot.user.id}/check"
        headers = {
            "Authorization": self.topgg_token,
            "Content-Type": "application/json",
            "User-Agent": "VoteChecker/1.0"
        }
        params = {"userId": user_id}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return bool(data.get("voted", False))
                    if resp.status == 401:
                        print("[VOTE] Token Top.gg invalide ou non autorisé. Désactivation de la vérification API.")
                        self.topgg = None
                    elif resp.status == 404:
                        return False
                    else:
                        data = await resp.text()
                        print(f"[VOTE] Erreur Top.gg API get_user_vote : {resp.status} {data}")
        except Exception as e:
            print(f"[VOTE] Erreur Top.gg API get_user_vote : {e}")
        return False

    @commands.hybrid_command(name="vote", description="Votez pour soutenir le bot.")
    async def vote(self, ctx: commands.Context):
        try:
            await ctx.defer(ephemeral=False)
            
            data = self.load_data()
            user_key = str(ctx.author.id)
            user_data = data.get(user_key, {})
            voted = await self._has_topgg_vote(ctx.author.id)
            now = time.time()

            if voted:
                vote_time = user_data.get("vote_check_timestamp")
                if not vote_time or now - vote_time > 43200:
                    vote_time = now
                    user_data["vote_check_timestamp"] = vote_time
                    user_data["bonus_end_timestamp"] = vote_time + 7200
                if not user_data.get("bonus_end_timestamp"):
                    user_data["bonus_end_timestamp"] = vote_time + 7200

                data[user_key] = user_data
                self.save_data(data)

                bonus_remaining = max(0, int(user_data["bonus_end_timestamp"] - now))
                next_vote_ts = int(vote_time + 43200)
                if bonus_remaining > 0:
                    bonus_text = f"Gains doublés pendant encore <t:{int(now + bonus_remaining)}:R>"
                else:
                    bonus_text = "Aucun gain doublé"

                desc = (
                    "✅ Tu as déjà voté pour le bot !\n\n"
                    f"⏳ Gains de jeux doublés prendra fin <t:{int(now + bonus_remaining)}:R>.\n\n"
                    f"⏳ Prochain vote : <t:{next_vote_ts}:R>"
                )
                embed = self.create_custom_embed(ctx.guild, ctx.author, "Vote validé", desc)
                if isinstance(embed, discord.Embed):
                    if self.bot.user and self.bot.user.display_avatar:
                        embed.set_author(name=f"Merci de soutenir {self.bot.user.name}", icon_url=self.bot.user.display_avatar.url)
                    else:
                        embed.set_author(name=f"Merci de soutenir {self.bot.user.name}")
                view = None
            else:
                if not self.topgg:
                    desc = (
                        "⚠️ La vérification Top.gg n'est pas disponible pour le moment.\n"
                        "Clique sur le bouton ci-dessous pour voter et soutenir le bot."
                    )
                else:
                    desc = (
                        "🗳️ Tu n'as pas encore voté pour le bot.\n"
                    )
                embed = self.create_custom_embed(ctx.guild, ctx.author, "Voter pour le bot", desc)
                if isinstance(embed, discord.Embed):
                    embed.add_field(name="🎁 Bonus", value="Gains de jeux doublés pendant 2h", inline=False)
                    if not self.topgg:
                        embed.add_field(name="🔎 Vérification", value="Indisponible pour le moment", inline=False)
                    else:
                        embed.add_field(name="📝 Info", value="Prochain vote disponible 12h après ton vote.", inline=False)
                    if self.bot.user and self.bot.user.display_avatar:
                        embed.set_author(name=f"Soutenir {self.bot.user.name}", icon_url=self.bot.user.display_avatar.url)
                    else:
                        embed.set_author(name=f"Soutenir {self.bot.user.name}")
                view = VoteView(self.bot.user.id)

            send_kwargs = {"embed": embed}
            if view is not None:
                send_kwargs["view"] = view

            if ctx.interaction:
                await ctx.interaction.followup.send(**send_kwargs)
            else:
                await ctx.send(reference=ctx.message, **send_kwargs)
            
        except Exception as e:
            print(f"[ERROR - Vote] {e}")
            traceback.print_exc()
            error_msg = "❌ Une erreur est survenue lors de l'exécution de la commande."
            if ctx.interaction:
                await ctx.interaction.followup.send(error_msg, ephemeral=True)
            else:
                await ctx.send(error_msg)

async def setup(bot: commands.Bot):
    await bot.add_cog(Vote(bot))