import discord
from discord.ext import commands
import random
import json
import traceback
import re
import asyncio
import time
import math
from pathlib import Path

# ==============================================================================
# --------------------------- IMPORTATION UTILS --------------------------------
# ==============================================================================
try:
    from cogs.addons.embed_type.utils import config_manager
    HAS_CUSTOM_EMBED = True
except ImportError:
    try:
        from .utils import config_manager # type: ignore
        HAS_CUSTOM_EMBED = True
    except ImportError:
        config_manager = None
        HAS_CUSTOM_EMBED = False

########################################
# Modals
########################################

class FlagAnswerModal(discord.ui.Modal, title="🌍 Ta Réponse"):
    answer_input = discord.ui.TextInput(
        label="Quel est ce pays ?",
        placeholder="Écris le nom ici...",
        style=discord.TextStyle.short,
        required=True
    )

    def __init__(self, view):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        user_raw = self.answer_input.value
        user_clean = self.view.parent_cog.normalize_answer(user_raw)
        target_clean = self.view.parent_cog.normalize_answer(self.view.flag_data["nom"])

        if user_clean == target_clean:
            self.view.is_won = True
            self.view.winner = interaction.user
            self.view.parent_cog.save_progression(interaction.user.id, self.view.flag_index)
            await interaction.response.defer()
            # Mettre à jour le message avec la bonne réponse
            await self.view.update_message(final=True)
        else:
            entry = f"❌ **{interaction.user.display_name}** : `{user_raw}`"
            self.view.history.append(entry)
            if len(self.view.history) > 5: self.view.history.pop(0)
            await interaction.response.send_message("Ce n'est pas le bon pays !", ephemeral=True)

########################################
# Views (Pagination & Jeu)
########################################

class FlagPaginationView(discord.ui.View):
    def __init__(self, parent_cog, data, author, total_max=0, is_lb=True):
        super().__init__(timeout=60)
        self.parent_cog, self.data, self.author = parent_cog, data, author
        self.total_max, self.is_lb = total_max, is_lb
        self.current_page = 0
        self.per_page = 10 if is_lb else 50
        self.max_pages = math.ceil(len(data) / self.per_page) if data else 1
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        btn_prev = discord.ui.Button(emoji="⬅️", disabled=(self.current_page <= 0))
        btn_prev.callback = self.prev_page
        self.add_item(btn_prev)

        btn_next = discord.ui.Button(emoji="➡️", disabled=(self.current_page >= self.max_pages - 1))
        btn_next.callback = self.next_page
        self.add_item(btn_next)

    async def prev_page(self, interaction):
        self.current_page -= 1
        await self.update_view(interaction)

    async def next_page(self, interaction):
        self.current_page += 1
        await self.update_view(interaction)

    async def update_view(self, interaction):
        self.update_buttons()
        if self.is_lb:
            embed = await self.parent_cog.create_lb_embed(interaction.guild, self.data, self.total_max, self.current_page, self.author)
        else:
            embed = self.parent_cog.create_avancee_embed(interaction.guild, self.author, self.parent_cog.last_all_flags, self.data, "N/A", self.current_page)
        await interaction.response.edit_message(embed=embed, view=self)


class FlagView(discord.ui.View):
    def __init__(self, parent_cog, ctx, flag_data, flag_index):
        super().__init__(timeout=600)
        self.parent_cog, self.ctx, self.flag_data, self.flag_index = parent_cog, ctx, flag_data, flag_index
        self.start_time, self.duration, self.is_won, self.winner = time.time(), 300, False, None
        self.message, self.history, self.revealed_hints = None, [], []
        self.indices_config = {270: 0, 240: 1, 210: 2}

    async def update_message(self, final=False):
        elapsed = time.time() - self.start_time
        remaining = max(0, self.duration - int(elapsed))
        indices = self.flag_data.get("indices", [])
        
        for t_limit, idx in self.indices_config.items():
            if remaining <= t_limit and idx < len(indices):
                hint_str = f"💡 {indices[idx]}"
                if hint_str not in self.revealed_hints: 
                    self.revealed_hints.append(hint_str)

        flag_emoji = f"# {self.flag_data['emoji']}"
        time_elapsed = int(elapsed)
        time_remaining = max(0, self.duration - time_elapsed)
        next_hint_time = next((t for t in sorted(self.indices_config.keys(), reverse=True) 
                             if t > time_remaining), 0)
        
        if next_hint_time > 0 and time_remaining > 0:
            time_until_next = max(0, next_hint_time - time_remaining)
            minutes = time_until_next // 60
            seconds = time_until_next % 60
            time_str = f"{minutes}min {seconds}sec" if minutes > 0 else f"{seconds} secondes"
            hints_text = "\n".join(self.revealed_hints) if self.revealed_hints else f"*Prochain indice dans {time_str}*"
        else:
            hints_text = "\n".join(self.revealed_hints) if self.revealed_hints else "*Plus d'indices disponibles*"
            
        desc = f"**Drapeau #{self.flag_index + 1}**\n**{flag_emoji}**\n\n🔎 **Indices culturels :**\n{hints_text}\n"
        
        if not final:
            hist_text = "\n".join(self.history) if self.history else "*Aucun essai*"
            desc += f"\n⏳ Temps restant : **{remaining}s**\n📝 **Derniers essais :**\n{hist_text}"
            title = "🌍 Quel est ce pays ?"
        else:
            res = f"🏆 **Gagné par {self.winner.mention} !**" if self.is_won else "⏱️ **Temps écoulé !**"
            desc += f"\n{res}\nC'était : **{self.flag_data['nom']}** {self.flag_data['emoji']}"
            title = "🌍 Fin du tour"
            
        if config_manager:
            embed = config_manager.get_formatted_embed(guild=self.ctx.guild, user=self.ctx.author, bot=self.parent_cog.bot, title=title, description=desc, target_id=self.ctx.guild.id if self.ctx.guild else None)
        else:
            embed = discord.Embed(title=title, description=desc, color=0x2b2d31)
            
        if self.message:
            if final:
                for item in self.children:
                    if hasattr(item, 'emoji') and str(getattr(item, 'emoji', '')) == "🏆":
                        item.disabled = False
                    else:
                        item.disabled = True
            try: await self.message.edit(embed=embed, view=self)
            except: pass
        return embed

    async def run_loop(self):
        while not self.is_won and (time.time() - self.start_time) < self.duration:
            await self.update_message()
            await asyncio.sleep(8)
        await self.update_message(final=True)

    @discord.ui.button(label="Répondre", style=discord.ButtonStyle.success, emoji="✍️")
    async def answer_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(FlagAnswerModal(self))

    @discord.ui.button(label=None, style=discord.ButtonStyle.secondary, emoji="🏆")
    async def lb_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        lb_view = FlagsLeaderboardView(self.parent_cog, interaction)
        await interaction.response.send_message(embed=lb_view.get_embed(interaction), view=lb_view, ephemeral=True)


# Menu avancé de classement inspiré de master.py
class FlagsLeaderboardView(discord.ui.View):
    def __init__(self, parent_cog, interaction, mode="server"):
        super().__init__(timeout=600)
        self.parent_cog = parent_cog
        self.interaction = interaction
        self.mode = mode
        self.update_buttons()

    def update_buttons(self):
        self.clear_items()
        self.add_item(discord.ui.Button(label="Serveur", style=discord.ButtonStyle.primary if self.mode=="server" else discord.ButtonStyle.secondary, custom_id="lb_server", emoji="🏢"))
        self.add_item(discord.ui.Button(label="Global", style=discord.ButtonStyle.primary if self.mode=="global" else discord.ButtonStyle.secondary, custom_id="lb_global", emoji="🌍"))

    def get_embed(self, interaction):
        with open(self.parent_cog.json_path, "r", encoding="utf-8") as f:
            all_flags = json.load(f)
        all_stats = []
        for file in self.parent_cog.data_dir.glob("*.json"):
            try:
                uid = int(file.stem)
                with open(file, "r", encoding="utf-8") as f2:
                    data = json.load(f2)
                    count = len(data.get("found_ids", []))
                    if count > 0:
                        all_stats.append({"uid": uid, "count": count})
            except Exception:
                pass
        if self.mode == "server" and interaction.guild:
            member_ids = [m.id for m in interaction.guild.members]
            all_stats = [s for s in all_stats if s["uid"] in member_ids]
            
        all_stats.sort(key=lambda x: x["count"], reverse=True)
        user_id = interaction.user.id
        user_rank = next((i for i, s in enumerate(all_stats) if s["uid"] == user_id), -1)
        desc = "### 👤 Ton Profil\n"
        if user_rank != -1:
            u_data = all_stats[user_rank]
            desc += f"> **Position :** `#{user_rank + 1}`\n"
            desc += f"> **Score :** `{u_data['count']}/{len(all_flags)}`\n\n"
        else:
            desc += "> *Tu n'as encore terminé aucun drapeau.*\n\n"
            
        desc += "### 🏆 Top 10\n"
        if not all_stats:
            desc += "*Aucun joueur classé pour le moment.*"
        else:
            for i, s in enumerate(all_stats[:10]):
                medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"`#{i+1:02d}`"
                desc += f"{medal} <@{s['uid']}> — `{s['count']}/{len(all_flags)}` pays\n"
                
        title = "🌍 Classement Interserveur" if self.mode == "global" else f"🏢 Classement {interaction.guild.name if interaction.guild else 'Serveur'}"
        if config_manager:
            return config_manager.get_formatted_embed(guild=interaction.guild, user=interaction.user, bot=self.parent_cog.bot, title=title, description=desc, target_id=interaction.guild.id if interaction.guild else None)
        return discord.Embed(title=title, description=desc, color=0xffd700)

    async def interaction_check(self, interaction):
        cid = interaction.data.get('custom_id')
        if cid == "lb_server":
            self.mode = "server"
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(interaction), view=self)
        elif cid == "lb_global":
            self.mode = "global"
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(interaction), view=self)
        return False

########################################
# Cog Flags
########################################

class Flags(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.base_path = Path(__file__).parent
        self.json_path = self.base_path / "flags.json"
        self.data_dir = Path("data/public/jeux/data_flags")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.last_all_flags = []
        
        # Vérification du gestionnaire d'embed
        if not HAS_CUSTOM_EMBED:
            print("⚠️ Attention: Le gestionnaire d'embed personnalisé n'a pas pu être chargé. Les embeds utiliseront le style par défaut.")
        elif config_manager is None:
            print("⚠️ Attention: Le gestionnaire d'embed est défini comme disponible mais n'a pas pu être importé correctement.")

    def get_random_flag(self, user_id: int):
        with open(self.json_path, 'r', encoding='utf-8') as f:
            flags = json.load(f)
        
        user_data = self.get_user_data(user_id)
        found_ids = set(user_data.get('found_ids', []))
        
        # Si tous les drapeaux ont été trouvés
        if len(found_ids) >= len(flags):
            return None, None, True  # Ajout d'un flag pour indiquer que tout est terminé
            
        # Filtrer les drapeaux non trouvés
        available_flags = [f for f in flags if f['id'] not in found_ids]
        flag = random.choice(available_flags)
        return flag, flags.index(flag), False  # Ajout du flag de fin à False par défaut

    def normalize_answer(self, text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r"^(le |la |les |un |une |du |des |l'|d'|en )", "", text)
        return text.translate(str.maketrans('', '', '?.!,;')).strip()

    def get_user_data(self, user_id: int):
        path = self.data_dir / f"{user_id}.json"
        d = {"found_ids": []}
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    d.update(json.load(f))
            except: pass
        return d

    def save_progression(self, user_id: int, flag_index: int):
        data = self.get_user_data(user_id)
        if flag_index not in data["found_ids"]:
            data["found_ids"].append(flag_index)
            with open(self.data_dir / f"{user_id}.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)

    def get_leaderboard_data(self):
        scores = []
        for file in self.data_dir.glob("*.json"):
            try:
                user_id = int(file.stem)
                with open(file, "r", encoding="utf-8") as f:
                    count = len(json.load(f).get("found_ids", []))
                if count > 0:
                    scores.append((user_id, count))
            except: continue
        return sorted(scores, key=lambda x: x[1], reverse=True)

    # --- EMBEDS ---

    def create_avancee_embed(self, guild, user, all_flags, found_ids, rank, page):
        total, found_count = len(all_flags), len(found_ids)
        percent = (found_count / total) * 100 if total > 0 else 0
        not_found = [i + 1 for i in range(total) if i not in found_ids]
        not_found_str = ", ".join([f"`#{idx}`" for idx in not_found]) if not_found else "Aventure terminée ! 🎉"
        
        title = f"📊 Progression : {user.display_name}"
        desc = (f"**🏆 Rang :** `#{rank}`\n**📈 Score :** `{found_count}/{total}` (**{percent:.1f}%**)\n\n"
                f"**🚩 Pays restants :**\n{not_found_str}")
        
        if config_manager:
            embed = config_manager.get_formatted_embed(
                guild=guild, 
                user=user, 
                bot=self.bot, 
                title=title, 
                description=desc, 
                target_id=guild.id if guild else None
            )
        else:
            embed = discord.Embed(title=title, description=desc, color=0x3498db)
            
        # Ajout de l'avatar de l'utilisateur en tant que thumbnail
        if hasattr(user, 'avatar') and user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
            
        return embed

    async def create_lb_embed(self, guild, scores, total_max, page, author):
        start, end = page * 10, (page * 10) + 10
        slice_data = scores[start:end]
        lines = []
        for i, (uid, count) in enumerate(slice_data, start=start + 1):
            user = self.bot.get_user(uid)
            name = user.display_name if user else f"ID: {uid}"
            prefix = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"`#{i}`"
            bold = "**" if uid == author.id else ""
            lines.append(f"{prefix} {bold}{name}{bold} — `{count}/{total_max}` pays")
        
        desc = "\n".join(lines) if lines else "Aucun joueur."
        title = "🏆 Top Explorateurs Vax"
        if config_manager:
            return config_manager.get_formatted_embed(guild=guild, user=author, bot=self.bot, title=title, description=desc, target_id=guild.id if guild else None)
        return discord.Embed(title=title, description=desc, color=0xffd700)

    # --- SENDS ---

    async def send_leaderboard(self, source):
        author = source.user if isinstance(source, discord.Interaction) else source.author
        try:
            with open(self.json_path, "r", encoding="utf-8") as f: total_max = len(json.load(f))
            data = self.get_leaderboard_data()
            view = FlagPaginationView(self, data, author, total_max, True)
            embed = await self.create_lb_embed(source.guild, data, total_max, 0, author)
            if isinstance(source, discord.Interaction): await source.response.send_message(embed=embed, view=view, ephemeral=True)
            else: await source.send(embed=embed, view=view)
        except: traceback.print_exc()

    async def send_profile_embed(self, source, user):
        try:
            with open(self.json_path, "r", encoding="utf-8") as f: 
                self.last_all_flags = json.load(f)
            user_data = self.get_user_data(user.id)
            all_scores = self.get_leaderboard_data()
            rank = next((i for i, (uid, _) in enumerate(all_scores, 1) if uid == user.id), "N/A")
            embed = self.create_avancee_embed(
                source.guild, 
                user, 
                self.last_all_flags, 
                user_data["found_ids"], 
                rank, 
                0
            )
            if isinstance(source, discord.Interaction): 
                await source.response.send_message(embed=embed, ephemeral=True)
            else: 
                await source.send(embed=embed)
        except Exception as e:
            traceback.print_exc()

    # --- COMMANDS ---

    @commands.hybrid_command(name="flags", description="Lancer un quiz sur les drapeaux du monde !")
    async def flags(self, ctx: commands.Context):
        try:
            await ctx.defer(ephemeral=False)
            
            flag, idx, all_found = self.get_random_flag(ctx.author.id)
            
            if flag is None and all_found:
                # Tous les drapeaux ont été trouvés
                if config_manager:
                    embed = config_manager.get_formatted_embed(
                        guild=ctx.guild,
                        user=ctx.author,
                        bot=self.bot,
                        title="🎉 Félicitations !",
                        description="**Vous avez trouvé tous les drapeaux disponibles !** 🏆\n\nRevenez plus tard pour de nouveaux défis !",
                        target_id=ctx.guild.id if ctx.guild else None
                    )
                else:
                    embed = discord.Embed(
                        title="🎉 Félicitations !",
                        description="**Vous avez trouvé tous les drapeaux disponibles !** 🏆\n\nRevenez plus tard pour de nouveaux défis !",
                        color=0x2b2d31
                    )
                return await ctx.send(embed=embed)
            elif flag is None:
                return await ctx.send("Aucun drapeau disponible pour le moment.", ephemeral=True)
            
            view = FlagView(self, ctx, flag, idx)
            if ctx.interaction:
                view.message = await ctx.send(embed=await view.update_message(), view=view)
            else:
                view.message = await ctx.send(embed=await view.update_message(), view=view, reference=ctx.message)
            
            asyncio.create_task(view.run_loop())
        except Exception:
            traceback.print_exc()
            await ctx.send("❌ Une erreur est survenue.", ephemeral=True)

async def setup(bot: commands.Bot):
    # Suppression de l'ancienne commande si elle existe pour éviter les conflits
    if bot.get_command("flags"):
        bot.remove_command("flags")
    await bot.add_cog(Flags(bot))