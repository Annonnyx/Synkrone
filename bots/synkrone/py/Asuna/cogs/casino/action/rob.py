import discord
from discord.ext import commands
import random
import os
import json
from datetime import datetime, timedelta

# ===================== CONFIG MANAGER ========================
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

from cogs.casino.autres.achievements import (
    load_user_data, save_user_data,
    increment_counter, check_and_unlock
)

# ── HELPERS ──────────────────────────────────────────────────

def format_Cols(value: int) -> str:
    return f"{value:,}".replace(',', ' ')

def _get_embed(bot, guild, member, title, description):
    return bot.config.get_formatted_embed(
        title=title, description=description,
        bot_user=bot.user, guild=guild, user=member,
        target_id=guild.id if guild else None
    )

# ── LIMITES ──────────────────────────────────────────────────
# - 5 vols par heure (global, toutes cibles confondues)
# - 1 vol par cible par jour
# - Une cible peut être volée max 2 fois par jour
# - Si la cible est déjà volée 2x, le voleur perd 0.1–10% de ses Cols

ROB_MAX_PER_HOUR = 5
ROB_MAX_PER_TARGET_PER_DAY = 1   # le voleur ne peut cibler qqn qu'1x/jour
ROB_MAX_RECEIVED_PER_DAY = 2     # une cible peut être volée max 2x/jour
ROB_PCT_MIN = 0.001              # 0.1 %
ROB_PCT_MAX = 0.10               # 10 %


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# ── ROB : données du voleur ──────────────────────────────────
def _get_rob_info(data: dict) -> dict:
    """Renvoie le sous-dict rob_data, initialisé si absent."""
    return data.setdefault("rob_data", {
        "rob_date": "",
        "targets_today": [],
        "hourly_robs": [],
    })


def _get_hourly_robs(rob_info: dict) -> list:
    """Renvoie la liste filtrée des timestamps de la dernière heure."""
    now = datetime.now()
    cutoff = now - timedelta(hours=1)
    raw = rob_info.get("hourly_robs", [])
    return [t for t in raw if datetime.fromisoformat(t) > cutoff]


def _get_targets_today(rob_info: dict) -> list:
    """Renvoie la liste des cibles du jour (reset si date différente)."""
    today = _today()
    if rob_info.get("rob_date") != today:
        rob_info["rob_date"] = today
        rob_info["targets_today"] = []
    return rob_info["targets_today"]


# ── ROB : données de la victime ──────────────────────────────
def _get_victim_received(data: dict) -> dict:
    """Retourne le sous-dict rob_received de la victime, réinitialisé si nouveau jour."""
    received = data.setdefault("rob_received", {"date": "", "count": 0})
    today = _today()
    if received.get("date") != today:
        received["date"] = today
        received["count"] = 0
    return received


# ─────────────────────────────────────────────────────────────

class RobCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="rob", description="🦹 Tentez de voler des Cols à un autre joueur !")
    async def rob(self, ctx: commands.Context, cible: discord.Member):
        # ── Validations de base ──
        if cible.id == ctx.author.id:
            return await ctx.send("❌ Vous ne pouvez pas vous voler vous-même.", ephemeral=True)
        if cible.bot:
            return await ctx.send("❌ Vous ne pouvez pas voler un bot.", ephemeral=True)

        guild_id = ctx.guild.id
        robber_data = load_user_data(guild_id, ctx.author.id)
        victim_data = load_user_data(guild_id, cible.id)

        rob_info = _get_rob_info(robber_data)

        # ── Limite 1 : 5 vols par heure ──
        hourly = _get_hourly_robs(rob_info)
        if len(hourly) >= ROB_MAX_PER_HOUR:
            oldest = min(datetime.fromisoformat(t) for t in hourly)
            rem_s = int((oldest + timedelta(hours=1) - datetime.now()).total_seconds())
            m, s = divmod(max(0, rem_s), 60)
            return await ctx.send(
                f"⏳ Vous avez déjà effectué **{ROB_MAX_PER_HOUR} vols** cette heure.\n"
                f"Patientez encore `{m}m {s:02d}s` avant de pouvoir en faire un nouveau.",
                ephemeral=True
            )

        # ── Limite 2 : 1 vol par cible par jour ──
        targets_today = _get_targets_today(rob_info)
        if str(cible.id) in targets_today:
            return await ctx.send(
                f"❌ Vous avez déjà tenté de voler **{cible.display_name}** aujourd'hui.\n"
                f"Attendez demain pour vous en prendre à nouveau à cette cible.",
                ephemeral=True
            )

        # ── Limite 3 : cible volée max 2x par jour → backfire ──
        victim_received = _get_victim_received(victim_data)

        if victim_received.get("count", 0) >= ROB_MAX_RECEIVED_PER_DAY:
            # Backfire : le voleur perd des Cols au profit de la cible
            robber_cols = robber_data.get("Cols", 0)
            pct = random.uniform(ROB_PCT_MIN, ROB_PCT_MAX)
            amount = max(1, int(robber_cols * pct))
            amount = min(amount, robber_cols)

            robber_data["Cols"] = max(0, robber_cols - amount)
            victim_data["Cols"] = victim_data.get("Cols", 0) + amount

            # Stats backfire
            robber_data = increment_counter(robber_data, "rob_backfire")
            new_ach = check_and_unlock(guild_id, ctx.author.id, "rob_backfire", robber_data)

            save_user_data(guild_id, ctx.author.id, robber_data)
            save_user_data(guild_id, cible.id, victim_data)

            embed = _get_embed(
                self.bot, ctx.guild, ctx.author,
                "🚨 Vol retourné !",
                f"**{cible.display_name}** a déjà été volé·e **2 fois** aujourd'hui et était sur ses gardes !\n\n"
                f"Vous avez été pris·e en flagrant délit et avez remis "
                f"**{format_Cols(amount)} Cols** à {cible.mention}.\n\n"
                f"💳 Votre solde : **{format_Cols(robber_data['Cols'])} Cols**"
            )
            msg = await ctx.send(embed=embed)
            if new_ach:
                notif = "\n".join(
                    f"🔓 Succès **{a['nom']}** — Palier {a['tier_label']} (+{a['honneur']} honneur)"
                    for a in new_ach
                )
                await msg.reply(f"🏆 Nouveau(x) succès !\n{notif}")
            return

        # ── Vol réussi ──
        victim_cols = victim_data.get("Cols", 0)
        pct = random.uniform(ROB_PCT_MIN, ROB_PCT_MAX)
        amount = max(1, int(victim_cols * pct))

        robber_data["Cols"] = robber_data.get("Cols", 0) + amount
        victim_data["Cols"] = max(0, victim_cols - amount)

        # Mise à jour tracking
        targets_today.append(str(cible.id))
        rob_info["targets_today"] = targets_today
        hourly.append(datetime.now().isoformat())
        rob_info["hourly_robs"] = hourly
        robber_data["rob_data"] = rob_info

        victim_received["count"] = victim_received.get("count", 0) + 1
        victim_data["rob_received"] = victim_received

        # Stats + achievements voleur
        robber_data = increment_counter(robber_data, "rob_success")
        new_ach = check_and_unlock(guild_id, ctx.author.id, "rob_success", robber_data)

        save_user_data(guild_id, ctx.author.id, robber_data)
        save_user_data(guild_id, cible.id, victim_data)

        embed = _get_embed(
            self.bot, ctx.guild, ctx.author,
            "🦹 Vol réussi !",
            f"Vous avez dérobé **{format_Cols(amount)} Cols** à {cible.mention} "
            f"*(soit {pct*100:.1f}% de son solde)*.\n\n"
            f"💳 Votre solde : **{format_Cols(robber_data['Cols'])} Cols**\n"
            f"💳 Solde de {cible.display_name} : **{format_Cols(victim_data['Cols'])} Cols**"
        )
        msg = await ctx.send(embed=embed)
        if new_ach:
            notif = "\n".join(
                f"🔓 Succès **{a['nom']}** — Palier {a['tier_label']} (+{a['honneur']} honneur)"
                for a in new_ach
            )
            await msg.reply(f"🏆 Nouveau(x) succès !\n{notif}")


async def setup(bot):
    await bot.add_cog(RobCog(bot))
