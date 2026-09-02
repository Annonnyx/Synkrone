# ===============================================================================
# ------------------------- BLACKLIST CONFIGURATION ------------------------------
# ===============================================================================
# Liste des IDs de serveurs à blacklister
BLACKLISTED_GUILDS = [
    1124304256518848543,
    # Exemple : 123456789012345678,
]
# Liste des IDs de membres à blacklister
BLACKLISTED_MEMBERS = [
    # Exemple : 987654321098765432,
]
import discord
from discord.ext import commands, tasks
import json
import random
import traceback
from datetime import datetime
import pytz
from pathlib import Path

# ==============================================================================
# --------------------------- IMPORTATION UTILS --------------------------------
# ==============================================================================
try:
    from utils.config_theme import config_manager
except ImportError:
    config_manager = None

# ==============================================================================
# ------------------------- CONFIGURATION GLOBALE ------------------------------
# ==============================================================================
SUPPORT_GUILD_ID = 1368235294192570520
ANNOUNCE_CHANNEL_ID = 1462547904035291219
TEST_USER_ID = 1366780122891419784
SUPPORT_LINK = "https://discord.gg/6UHYn6KYMf"

TARGET_DAY_NAME = "Samedi"
TARGET_HOUR = 20
TARGET_MINUTE = 0

DAYS_MAPPING = {
    "Lundi": 0, "Mardi": 1, "Mercredi": 2, "Jeudi": 3,
    "Vendredi": 4, "Samedi": 5, "Dimanche": 6
}

PRIZE_BASIC = "Nitro Basic `3,03€` *1 mois*"
PRIZE_PREMIUM = "Nitro Boost `10,13€` *1 mois*"

# Chemin absolu des datas à la racine
DATA_DIR = Path.cwd() / "data" / "staff" / "configuration" / "data_aincradGA"

# ==============================================================================
# ----------------------------- INTERFACES (UI) --------------------------------
# ==============================================================================
class ClaimRewardView(discord.ui.View):
    """Vue contenant le bouton pour réclamer la récompense en MP."""
    def __init__(self):
        super().__init__(timeout=None) # Pas de timeout pour un bouton lien
        self.add_item(discord.ui.Button(
            label="Réclamer ma récompense",
            style=discord.ButtonStyle.link,
            url=SUPPORT_LINK,
            emoji="🎁"
        ))

# ==============================================================================
# ---------------------------------- COG ---------------------------------------
# ==============================================================================
class aincradGA(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.timezone = pytz.timezone("Europe/Paris")
        
        # Initialisation Data
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.config_file = DATA_DIR / "config.json"
        self._init_data()

        # Lancement Cron
        self.giveaway_task.start()

    def cog_unload(self):
        self.giveaway_task.cancel()

    # --- GESTION DES DONNÉES ---
    def _init_data(self):
        if not self.config_file.exists():
            try:
                with open(self.config_file, "w", encoding="utf-8") as f:
                    json.dump({"last_run": ""}, f, indent=4)
            except Exception as e:
                print(f"[AincradGA ❌] Impossible de créer la data : {e}")

    def get_last_run(self) -> str:
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                return json.load(f).get("last_run", "")
        except:
            return ""

    def set_last_run(self, date_str: str):
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump({"last_run": date_str}, f, indent=4)
        except Exception as e:
            print(f"[AincradGA ❌] Erreur sauvegarde JSON : {e}")

    # --- LOGIQUE MÉTIER ---
    def is_premium_eligible(self, user: discord.User) -> bool:
        # Vérif Owner
        for guild in self.bot.guilds:
            if guild.owner_id == user.id:
                return True
        # Vérif Booster Support
        support_guild = self.bot.get_guild(SUPPORT_GUILD_ID)
        if support_guild:
            member = support_guild.get_member(user.id)
            if member and member.premium_since is not None:
                return True
        return False

    async def execute_giveaway(self, test_mode: bool = False, force_user_id: int = None):
        support_guild = self.bot.get_guild(SUPPORT_GUILD_ID)
        announce_channel = self.bot.get_channel(ANNOUNCE_CHANNEL_ID)

        if not support_guild or not announce_channel:
            print("[AincradGA ❌] Serveur de support ou salon d'annonce introuvable.")
            return

        target_user = None

        if test_mode and force_user_id:
            target_user = self.bot.get_user(force_user_id) or await self.bot.fetch_user(force_user_id)
            if not target_user:
                return
        else:
            # Filtrage blacklist serveurs et membres
            all_members = {}
            for g in self.bot.guilds:
                if g.id in BLACKLISTED_GUILDS:
                    continue
                for m in g.members:
                    if m.bot or m.id in BLACKLISTED_MEMBERS:
                        continue
                    all_members[m.id] = m
            unique_members = list(all_members.values())
            random.shuffle(unique_members)
            if not unique_members:
                return

        # --- Envoi du MP avec Embed et Bouton ---
        dm_sent = False
        candidates = [target_user] if test_mode else unique_members

        # Calcul stats pour MP
        all_members_stats = {}
        for g in self.bot.guilds:
            if g.id in BLACKLISTED_GUILDS:
                continue
            for m in g.members:
                if m.bot or m.id in BLACKLISTED_MEMBERS:
                    continue
                all_members_stats[m.id] = m
        unique_count = len(all_members_stats)
        if unique_count > 0:
            chance = round(100 / unique_count, 4)
            # Affichage sans zéros inutiles, mais toujours 4 décimales
            chance_str = f"{chance:.4f}"
        else:
            chance_str = "0.0000"
        server_count = len([g for g in self.bot.guilds if g.id not in BLACKLISTED_GUILDS])
        support_guild_name = support_guild.name if support_guild else "le serveur support"
        gains = (
            f"🔹<:owner:1508179195036045372> Owner de serveur — **Nitro Boost**\n"
            f"🔹<a:boost:1508178804093354004> Booster {support_guild_name} — **Nitro Boost**\n"
            f"🔹<:Synkrone:1506414460091240458> Simple utilisateur — **Nitro Basic**"
        )
        comment_str = (
            f"📝 **Comment ça marche ?**\n"
            f"🔹 Je choisis un joueur au hasard parmi tous mes ``{server_count} serveurs``. Ceci représente ``{unique_count} membres``, tu as donc ``{chance_str}%`` de chance de gagner la prochaine fois.\n\n"
            f"🎁 **Quels sont les gains ?**\n"
            f"{gains}\n"
        )

        for potential_winner in candidates:
            is_premium = self.is_premium_eligible(potential_winner)
            prize = PRIZE_PREMIUM if is_premium else PRIZE_BASIC

            # Création de l'Embed de Message Privé (NOUVEAU FORMAT)
            if prize == PRIZE_PREMIUM:
                lot_str = "🎁 **Lot Remporté : Nitro Boost** `1 mois`  `10,13€`"
            else:
                lot_str = "🎁 **Lot Remporté : Nitro Basic** `1 mois`  `3,03€`"
            dm_embed = config_manager.get_formatted_embed(
                guild=None,
                user=potential_winner,
                bot=self.bot,
                title="🎉 Félicitations ! Vous avez gagné !",
                description=(
                    f"> Incroyable ! Le destin vous a souri lors du tirage au sort hebdomadaire de l'Aincrad. 🏆\n\n"
                    f"{lot_str}\n\n"
                    f"{comment_str}"
                )
            )

            if not is_premium:
                dm_embed.add_field(
                    name="💎 Envie d'une meilleure récompense ?",
                    value=f"Devenez **Booster** du serveur support ou invitez-moi sur votre propre serveur pour gagner un **{PRIZE_PREMIUM}** au prochain tirage !",
                    inline=False
                )

            dm_embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            # Footer  déjà géré par config_manager.get_formatted_embed

            try:
                await potential_winner.send(embed=dm_embed, view=ClaimRewardView())
                target_user = potential_winner
                dm_sent = True
                break
            except discord.Forbidden:
                if test_mode:
                    print(f"[AincradGA ⚠️] DMs bloqués pour le testeur {potential_winner.name}.")
                continue

        if not dm_sent:
            print("[AincradGA ❌] Impossible de trouver un gagnant avec DMs ouverts.")
            return

        # --- Annonce Publique avec Embed ---
        member_in_support = support_guild.get_member(target_user.id)
        winner_tag = f"<@{target_user.id}>" if member_in_support else f"`@{target_user.name}`"

        # Calcul du nombre d'utilisateurs uniques et de la chance de gagner (hors blacklist)
        all_members = {}
        for g in self.bot.guilds:
            if g.id in BLACKLISTED_GUILDS:
                continue
            for m in g.members:
                if m.bot or m.id in BLACKLISTED_MEMBERS:
                    continue
                all_members[m.id] = m
        unique_count = len(all_members)
        if unique_count > 0:
            chance = round(100 / unique_count, 4)
            chance_str = f"{chance:.4f}"
        else:
            chance_str = "0.0000"
        server_count = len([g for g in self.bot.guilds if g.id not in BLACKLISTED_GUILDS])
        support_guild_name = support_guild.name if support_guild else "le serveur support"

        # Formatage du lot pour l'annonce (même visuel que DM)
        if prize == PRIZE_PREMIUM:
            lot_str = "🎁 **Lot Remporté : Nitro Boost** `1 mois`  `10,13€`"
        else:
            lot_str = "🎁 **Lot Remporté : Nitro Basic** `1 mois`  `3,03€`"

        # Visuel des gains avec variables
        gains = (
            f"🔹<:owner:1508179195036045372> Owner de serveur — **Nitro Boost**\n"
            f"🔹<a:boost:1508178804093354004> Booster {support_guild_name} — **Nitro Boost**\n"
            f"🔹<:Synkrone:1506414460091240458> Simple utilisateur — **Nitro Basic**"
        )

        # Visuel principal
        description = (
            f"> Bravo à {winner_tag} qui vient de remporter notre tirage au sort hebdomadaire !\n\n"
            f"{lot_str}\n\n"
            f"📝 **Comment ça marche ?**\n"
            f"🔹 Je choisis un joueur au hasard parmi tous mes ``{server_count} serveurs``. Ceci représente ``{unique_count} membres``, tu as donc ``{chance_str}%`` de chance de gagner la prochaine fois.\n\n"
            f"**🎁 Quels sont les gains ?**\n"
            f"{gains}\n"
            f"-# *:warning: Il faut que je puisse bien t'envoyer un message pour gagner.*"
        )

        announce_embed = config_manager.get_formatted_embed(
            guild=None,
            user=target_user,
            bot=self.bot,
            title="🎊 Tirage de l'Aincrad 🎊",
            description=description
        )
        announce_embed.set_thumbnail(url=target_user.display_avatar.url if target_user.avatar else self.bot.user.display_avatar.url)

        try:
            await announce_channel.send(embed=announce_embed)
            print(f"[AincradGA ✅] Gagnant : {target_user.name} | Lot : {prize}")
        except Exception as e:
            print(f"[AincradGA ❌] Erreur annonce publique : {e}")

    # --- TÂCHES AUTOMATIQUES ---
    @tasks.loop(minutes=1)
    async def giveaway_task(self):
        now = datetime.now(self.timezone)
        current_day_index = now.weekday()
        target_day_index = DAYS_MAPPING.get(TARGET_DAY_NAME, 5)
        
        if current_day_index == target_day_index and now.hour == TARGET_HOUR and now.minute == TARGET_MINUTE:
            date_str = now.strftime("%Y-%m-%d")
            if self.get_last_run() != date_str:
                print(f"[AincradGA ⚙️] Lancement automatique du {date_str}.")
                await self.execute_giveaway()
                self.set_last_run(date_str)

    @giveaway_task.before_loop
    async def before_giveaway_task(self):
        await self.bot.wait_until_ready()

    # --- COMMANDES PREFIX ---
    @commands.command(name="faga", aliases=["forcega"], description="Fait gagner un utilisateur aléatoire ou ciblé (Owner uniquement).\nUtilisation : !faga [id/tag]")
    @commands.is_owner()
    async def faga_cmd(self, ctx: commands.Context, user: discord.User = None):
        """Force le tirage pour un utilisateur aléatoire ou ciblé."""
        processing_msg = await ctx.send("⏳ *Traitement du tirage en cours...*")
        try:
            if user is not None:
                await self.execute_giveaway(test_mode=True, force_user_id=user.id)
                embed = discord.Embed(
                    title="⚙️ Tirage Forcé : Utilisateur Sélectionné",
                    description=f"✅ Le système a tenté de récompenser l'utilisateur {user.mention}.\n*Vérifiez la console et les salons pour confirmer le résultat.*",
                    color=0x2ecc71
                )
                embed.set_footer(text=f"Tirage par {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
                await processing_msg.edit(content=None, embed=embed)
            else:
                await self.execute_giveaway(test_mode=False)
                embed = discord.Embed(
                    title="⚙️ Tirage Forcé : Utilisateur Aléatoire",
                    description=f"✅ Le système a tenté de récompenser un utilisateur aléatoire.\n*Vérifiez la console et les salons pour confirmer le résultat.*",
                    color=0x2ecc71
                )
                embed.set_footer(text=f"Tirage par {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
                await processing_msg.edit(content=None, embed=embed)
        except Exception as e:
            traceback.print_exc()
            await processing_msg.edit(content=f"❌ **Erreur critique lors du tirage :**\n```py\n{e}\n```")

async def setup(bot: commands.Bot):
    await bot.add_cog(aincradGA(bot))
