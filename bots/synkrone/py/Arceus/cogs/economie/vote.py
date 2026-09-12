import aiohttp
import os
import discord
from discord import ui
from discord.ext import commands
import json
import random
import time
from pathlib import Path
import traceback

from .utils import EconomyService, CHARM_FIELDS, CHARM_LABELS, CHARM_EMOJIS
try:
    from cogs.pokémon.pokemon import get_species_fr_name
except ImportError:
    get_species_fr_name = None

BASE_DIR = Path.cwd()
DATA_DIR = BASE_DIR / "data" / "public" / "data_vote"
ENABLE_TESTVOTE = True  # Définir sur False pour désactiver complètement la commande testvote
MAX_POKEMON_ID = 1025
VOTE_COOLDOWN_SECONDS = 12 * 3600
SHINY_EMOJI = "<:shiny:1522947934969270312>"

# Import du gestionnaire d'embeds personnalisé
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# ===============================================================================
# --------------------------- INTERFACE UTILISATEUR -----------------------------
# ===============================================================================
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

# ===============================================================================
# -------------------------------- COG VOTE -------------------------------------
# ===============================================================================
class Vote(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.data_file = DATA_DIR / "users.json"
        self._ensure_file()
        self.eco = EconomyService(bot)

        self.topgg_token = os.getenv("TOPGG_TOKEN")
        self.topgg = bool(self.topgg_token)
        if not self.topgg_token:
            print("[VOTE] TOPGG_TOKEN non défini. La vérification Top.gg via API est désactivée.")
        print(f"[VOTE] Cog Vote initialisé. Top.gg actif: {self.topgg}")

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

    def create_custom_embed(self, guild, user, title, description, color=0x3498db):
        """Génère l'embed via le config_manager ou le fallback natif."""
        if config_manager:
            try:
                embed = config_manager.get_formatted_embed(
                    guild=guild,
                    user=user,
                    bot=self.bot,
                    title=title,
                    description=description,
                    target_id=guild.id if guild else None,
                    force_global=not bool(guild)
                )
                if color is not None:
                    embed.color = color
                return embed
            except Exception as e:
                print(f"[VOTE] Erreur config_manager: {e}")

        embed = discord.Embed(title=title, description=description, color=color)
        if self.bot.user and self.bot.user.display_avatar:
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
            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return bool(data.get("voted", False))
                    if resp.status == 401:
                        print("[VOTE] Token Top.gg invalide ou non autorisé. Désactivation de la vérification API.")
                        self.topgg = False
                    elif resp.status == 404:
                        return False
                    else:
                        data = await resp.text()
                        print(f"[VOTE] Erreur Top.gg API get_user_vote : {resp.status} {data}")
        except Exception as e:
            print(f"[VOTE] Erreur Top.gg API get_user_vote : {e}")
        return False

    async def _fetch_pokemon_name(self, pokemon_id: int) -> str:
        if get_species_fr_name is None:
            return f"Pokémon #{pokemon_id}"
        try:
            async with aiohttp.ClientSession() as session:
                return await get_species_fr_name(session, str(pokemon_id))
        except Exception as e:
            print(f"[VOTE] Erreur récupération nom Pokémon : {e}")
            return f"Pokémon #{pokemon_id}"

    def _choose_random_charm(self) -> str:
        return random.choice(CHARM_FIELDS)

    async def _grant_vote_reward(self, user_id: int) -> tuple[int, str, str]:
        pokemon_id = random.randint(1, MAX_POKEMON_ID)
        pokemon_name = await self._fetch_pokemon_name(pokemon_id)
        charm_key = self._choose_random_charm()

        print(f"[VOTE] Attribution récompense pour {user_id} : #{pokemon_id} {pokemon_name}, charme {charm_key}")

        self.eco.add_inventory_item(
            user_id=user_id,
            pokemon_id=pokemon_id,
            name=pokemon_name,
            is_shiny=True,
            level=1,
            ball="vote"
        )

        self.eco.ensure_user(user_id)
        with self.eco._get_conn() as conn:
            conn.execute(
                f"UPDATE users SET {charm_key} = {charm_key} + 1 WHERE user_id = ?",
                (user_id,)
            )

        return pokemon_id, pokemon_name, charm_key

    async def _send_reward_dm(self, user: discord.User, pokemon_id: int, pokemon_name: str, charm_key: str) -> bool:
        title = "🎉 Récompense de vote reçue !"
        description = (
            f"Tu as obtenu un Pokémon shiny gratuit ! {SHINY_EMOJI}\n\n"
            f"**Pokémon :** #{pokemon_id} {pokemon_name} {SHINY_EMOJI}\n"
            f"**Charme gagné :** {CHARM_EMOJIS.get(charm_key, charm_key)} {CHARM_LABELS.get(charm_key, charm_key)}"
        )
        embed = self.create_custom_embed(None, user, title, description)
        embed.set_image(url=f"https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon/shiny/{pokemon_id}.png")

        try:
            await user.send(embed=embed)
            print(f"[VOTE] DM envoyé à {user.id}")
            return True
        except Exception as e:
            print(f"[VOTE] Impossible d'envoyer le DM à {user.id} : {e}")
            return False

    def _build_vote_embed(self, voted: bool, can_claim: bool, guild: discord.Guild | None, user: discord.abc.User | None, next_vote_ts: int | None = None) -> tuple[discord.Embed, VoteView | None]:
        if voted and can_claim:
            desc = "✅ Vote détecté ! Tu vas recevoir ta récompense en message privé."
            embed = self.create_custom_embed(guild, user, "Vote détecté", desc)
            embed.add_field(name="Info", value="Un message privé arrive avec ton Pokémon shiny et ton charme.", inline=False)
            return embed, None

        if voted and not can_claim:
            desc = "✅ Tu as déjà reçu ta récompense de vote récente."
            embed = self.create_custom_embed(guild, user, "Déjà récompensé", desc)
            if next_vote_ts:
                embed.add_field(name="Prochain vote", value=f"<t:{next_vote_ts}:R>", inline=False)
            return embed, None

        desc = "🗳️ Tu n'as pas encore voté pour le bot."
        if not self.topgg:
            desc = "⚠️ La vérification Top.gg n'est pas disponible pour le moment. Clique sur le bouton ci-dessous pour voter."

        embed = self.create_custom_embed(guild, user, "Vote requis", desc)
        embed.add_field(name="Récompense", value="Un Pokémon shiny gratuit + un charme aléatoire", inline=False)
        if self.topgg:
            embed.add_field(name="Info", value="Tu peux revoter toutes les 12 heures.", inline=False)
        else:
            embed.add_field(name="Info", value="La vérification est désactivée, utilise testvote pour tester.", inline=False)

        view = VoteView(self.bot.user.id)
        return embed, view

    async def _send_vote_response(
        self,
        ctx: commands.Context,
        *,
        content: str | None = None,
        embed: discord.Embed | None = None,
        view: ui.View | None = None,
        ephemeral: bool = False,
    ):
        if ctx.interaction:
            try:
                if ctx.interaction.response.is_done():
                    return await ctx.interaction.followup.send(
                        content=content,
                        embed=embed,
                        view=view,
                        ephemeral=ephemeral,
                    )
                return await ctx.interaction.response.send_message(
                    content=content,
                    embed=embed,
                    view=view,
                    ephemeral=ephemeral,
                )
            except discord.NotFound:
                pass

        return await ctx.send(
            content=content,
            embed=embed,
            view=view,
            reference=ctx.message if getattr(ctx, "message", None) else None,
        )

    async def _can_claim_vote_reward(self, user_data: dict, now: float) -> bool:
        last_reward = user_data.get("vote_reward_timestamp", 0)
        return (not last_reward) or (now - last_reward >= VOTE_COOLDOWN_SECONDS)

    async def _record_vote_reward(self, user_data: dict, now: float) -> None:
        user_data["vote_reward_timestamp"] = now
        user_data["vote_check_timestamp"] = now

    @commands.hybrid_command(name="vote", description="Vérifie si tu as voté sur Top.gg et te récompense si c'est le cas.")
    async def vote(self, ctx: commands.Context):
        try:
            if ctx.interaction and not ctx.interaction.response.is_done():
                try:
                    await ctx.interaction.response.defer(thinking=True)
                except discord.NotFound:
                    pass

            print(f"[VOTE] Commande vote appelée par {ctx.author} ({ctx.author.id})")

            data = self.load_data()
            user_key = str(ctx.author.id)
            user_data = data.get(user_key, {})
            voted = await self._has_topgg_vote(ctx.author.id)
            now = time.time()
            can_claim = await self._can_claim_vote_reward(user_data, now)
            next_vote_ts = int(user_data.get("vote_reward_timestamp", 0) + VOTE_COOLDOWN_SECONDS) if user_data.get("vote_reward_timestamp") else None
            embed, view = self._build_vote_embed(voted, can_claim, ctx.guild, ctx.author, next_vote_ts)

            if voted and can_claim:
                pokemon_id, pokemon_name, charm_key = await self._grant_vote_reward(ctx.author.id)
                await self._record_vote_reward(user_data, now)
                data[user_key] = user_data
                self.save_data(data)
                dm_sent = await self._send_reward_dm(ctx.author, pokemon_id, pokemon_name, charm_key)
                if not dm_sent:
                    fallback_title = "🎉 Récompense de vote attribuée !"
                    fallback_desc = (
                        f"Ton vote a été détecté et ta récompense a bien été ajoutée à ton profil.\n\n"
                        f"**Pokémon :** #{pokemon_id} {pokemon_name} {SHINY_EMOJI}\n"
                        f"**Charme gagné :** {CHARM_EMOJIS.get(charm_key, charm_key)} {CHARM_LABELS.get(charm_key, charm_key)}\n\n"
                        "Je n'ai pas pu t'envoyer le message privé. Vérifie que tu peux recevoir des DM du bot."
                    )
                    fallback_embed = self.create_custom_embed(ctx.guild, ctx.author, fallback_title, fallback_desc)
                    await self._send_vote_response(ctx, embed=fallback_embed)
                    return

                await self._send_vote_response(ctx, embed=embed)
                return

            data[user_key] = user_data
            self.save_data(data)
            await self._send_vote_response(ctx, embed=embed, view=view)

        except Exception as e:
            print(f"[ERROR - Vote] {e}")
            traceback.print_exc()
            error_msg = "❌ Une erreur est survenue lors de l'exécution de la commande."
            await self._send_vote_response(ctx, content=error_msg, ephemeral=True)

    @commands.hybrid_command(name="testvote", description="Teste la récompense de vote.")
    async def testvote(self, ctx: commands.Context):
        try:
            if not await self.bot.is_owner(ctx.author):
                return await ctx.send("❌ Seul le propriétaire du bot peut utiliser testvote.", reference=ctx.message)

            if not ENABLE_TESTVOTE:
                return await ctx.send("❌ La commande testvote est désactivée.", reference=ctx.message)

            print(f"[VOTE] Commande testvote appelée par {ctx.author} ({ctx.author.id})")
            if ctx.interaction:
                await ctx.defer(ephemeral=False)

            data = self.load_data()
            user_key = str(ctx.author.id)
            user_data = data.get(user_key, {})
            now = time.time()

            pokemon_id, pokemon_name, charm_key = await self._grant_vote_reward(ctx.author.id)
            await self._record_vote_reward(user_data, now)
            data[user_key] = user_data
            self.save_data(data)
            await self._send_reward_dm(ctx.author, pokemon_id, pokemon_name, charm_key)

            embed = self.create_custom_embed(ctx.guild, ctx.author, "Test de vote", "✅ Récompense de test envoyée en message privé.")
            if ctx.interaction:
                await ctx.interaction.followup.send(embed=embed)
            else:
                await ctx.send(embed=embed, reference=ctx.message)

        except Exception as e:
            print(f"[ERROR - TestVote] {e}")
            traceback.print_exc()
            error_msg = "❌ Une erreur est survenue lors de l'exécution de la commande testvote."
            if ctx.interaction:
                await ctx.interaction.followup.send(error_msg, ephemeral=True)
            else:
                await ctx.send(error_msg)


async def setup(bot: commands.Bot):
    await bot.add_cog(Vote(bot))
