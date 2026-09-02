import time
import math
import asyncio
from typing import Any

import aiohttp
import discord
from discord.ext import commands

from .utils import EconomyService, SUPERBONBON_EMOJI, BALL_EMOJIS

try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

POKEDOLLAR_EMOJI = "₽"
SHINY_EMOJI = "<:shiny:1522947934969270312>"
STAR_EMOJI = "🌟"
POKEBALL_EMOJI = BALL_EMOJIS.get("pokeball", "🔴")

# Listes statiques pour les Ultra-Chimères et Paradoxes
UB_IDS = [793, 794, 795, 796, 797, 798, 799, 800, 801, 802, 803, 804, 805, 806]
PARADOX_IDS = [984, 985, 986, 987, 988, 989, 990, 991, 992, 993, 994, 995, 996, 
               997, 998, 999, 1000, 1001, 1002, 1003, 1004, 1005, 1006, 1007, 
               1008, 1009, 1010, 1020, 1021, 1022, 1023]


def format_number(num):
    return f"{int(num):,}".replace(',', ' ')

def calculate_release_price(total_stats):
    """
    Formule non-linéaire (Stats² / 12) :
    - 300 stats = ~7 500 ₽
    - 500 stats = ~20 833 ₽
    - 600 stats = ~30 000 ₽ (Ex: Dracolosse, très rentable !)
    - 680 stats = ~38 533 ₽
    """
    return int((total_stats ** 2) / 12)

def is_special_pokemon(pokemon_id: int, is_legendary: bool, is_mythical: bool) -> bool:
    return is_legendary or is_mythical or (pokemon_id in UB_IDS) or (pokemon_id in PARADOX_IDS)


# ==========================================
# GESTIONNAIRE DE CACHE API
# ==========================================
class PokemonMetaCache:
    def __init__(self):
        self.cache = {}

    async def get_meta(self, session: aiohttp.ClientSession, pokemon_id: int):
        if pokemon_id in self.cache:
            return self.cache[pokemon_id]

        total_stats = 300
        stage = 1
        is_final = True
        next_evo_id = None
        name_fr = f"Pokémon #{pokemon_id}"

        # 1. Fetch Stats & Name
        try:
            async with session.get(f"https://pokeapi.co/api/v2/pokemon/{pokemon_id}") as r:
                if r.status == 200:
                    data = await r.json()
                    total_stats = sum(s["base_stat"] for s in data["stats"])
        except: pass

        # 2. Fetch Species & Evolution Chain
        try:
            async with session.get(f"https://pokeapi.co/api/v2/pokemon-species/{pokemon_id}") as r:
                if r.status == 200:
                    s_data = await r.json()
                    # Find French name
                    for n in s_data.get("names", []):
                        if n["language"]["name"] == "fr":
                            name_fr = n["name"]
                            break
                            
                    evo_url = s_data.get("evolution_chain", {}).get("url")
                    if evo_url:
                        async with session.get(evo_url) as er:
                            if er.status == 200:
                                e_data = await er.json()
                                chain = e_data["chain"]
                                
                                def find_node(node, target_name, curr_stage=1):
                                    if node["species"]["name"] == target_name:
                                        return node, curr_stage
                                    for child in node.get("evolves_to", []):
                                        res, st = find_node(child, target_name, curr_stage + 1)
                                        if res: return res, st
                                    return None, 1

                                node, stage = find_node(chain, s_data["name"])
                                if node and node.get("evolves_to"):
                                    is_final = False
                                    next_url = node["evolves_to"][0]["species"]["url"]
                                    next_evo_id = int(next_url.rstrip('/').split('/')[-1])
        except: pass

        self.cache[pokemon_id] = {
            "total_stats": total_stats,
            "stage": stage,
            "is_final": is_final,
            "next_evo_id": next_evo_id,
            "name": name_fr
        }
        return self.cache[pokemon_id]

meta_cache = PokemonMetaCache()


# ==========================================
# MODAUX D'ACTION
# ==========================================
class ActionModal(discord.ui.Modal):
    def __init__(self, view, action: str, pokemon: dict, max_qty: int, meta: dict):
        titre = {"relacher": "Relâcher", "evoluer": "Évoluer", "recycler": "Recycler"}[action]
        super().__init__(title=f"{titre} - {meta['name']}")
        self.action_view = view
        self.action = action
        self.pokemon = pokemon
        self.max_qty = max_qty
        self.meta = meta

        self.quantity = discord.ui.TextInput(
            label=f"Quantité (Max: {max_qty})",
            style=discord.TextStyle.short,
            placeholder=str(max_qty),
            required=True
        )
        self.add_item(self.quantity)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            qty = int(self.quantity.value.strip())
            if qty <= 0 or qty > self.max_qty:
                raise ValueError
        except ValueError:
            await interaction.response.send_message(f"❌ Quantité invalide. (Max: {self.max_qty})", ephemeral=True)
            return

        cog = self.action_view.cog
        pid = self.pokemon["pokemon_id"]
        shiny = self.pokemon["is_shiny"]
        uid = interaction.user.id
        
        with cog.eco._get_conn() as conn:
            inv_rows = conn.execute(
                "SELECT id, level FROM inventory WHERE user_id = ? AND pokemon_id = ? AND is_shiny = ? ORDER BY level ASC",
                (uid, pid, int(shiny))
            ).fetchall()

            if self.action == "relacher":
                ids_to_delete = [r["id"] for r in inv_rows[:qty]]
                reward = qty * calculate_release_price(self.meta["total_stats"])
                
                conn.executemany("DELETE FROM inventory WHERE id = ?", [(i,) for i in ids_to_delete])
                conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (reward, uid))
                
                msg = f"✅ Tu as relâché **{qty}x {self.meta['name']}** pour `+{format_number(reward)}` {POKEDOLLAR_EMOJI}."

            elif self.action == "evoluer":
                sb_cost = 1 if self.meta["stage"] == 1 else 3
                total_sb_cost = qty * sb_cost
                copies_needed = qty * 3
                
                user_sb = conn.execute("SELECT superbonbon FROM users WHERE user_id = ?", (uid,)).fetchone()["superbonbon"]
                if user_sb < total_sb_cost:
                    await interaction.response.send_message(f"❌ Tu n'as pas assez de Superbonbons. (Requis: {total_sb_cost})", ephemeral=True)
                    return
                    
                ids_to_delete = [r["id"] for r in inv_rows[:copies_needed]]
                conn.executemany("DELETE FROM inventory WHERE id = ?", [(i,) for i in ids_to_delete])
                conn.execute("UPDATE users SET superbonbon = superbonbon - ? WHERE user_id = ?", (total_sb_cost, uid))
                
                for _ in range(qty):
                    conn.execute(
                        "INSERT INTO inventory (user_id, pokemon_id, is_shiny, level, legendary, mythical) VALUES (?, ?, ?, ?, ?, ?)",
                        (uid, self.meta["next_evo_id"], int(shiny), inv_rows[copies_needed-1]["level"] + 1, self.pokemon["legendary"], self.pokemon["mythical"])
                    )
                
                msg = f"✅ Tu as évolué **{qty}x {self.meta['name']}**. (Coût: `{total_sb_cost}` {SUPERBONBON_EMOJI})"

            elif self.action == "recycler":
                base_sb = self.meta["stage"]
                bonus = 0
                if shiny: bonus += 2
                if self.pokemon["legendary"]: bonus += 3
                if self.pokemon["mythical"]: bonus += 5
                if pid in UB_IDS: bonus += 3
                if pid in PARADOX_IDS: bonus += 1
                
                sb_reward_per_item = base_sb + bonus
                total_sb_reward = qty * sb_reward_per_item
                
                ids_to_delete = [r["id"] for r in inv_rows[:qty]]
                conn.executemany("DELETE FROM inventory WHERE id = ?", [(i,) for i in ids_to_delete])
                conn.execute("UPDATE users SET superbonbon = superbonbon + ? WHERE user_id = ?", (total_sb_reward, uid))
                
                msg = f"✅ Tu as recyclé **{qty}x {self.meta['name']}** et obtenu `+{total_sb_reward}` {SUPERBONBON_EMOJI}."

            # Mise à jour des Superbonbons de la vue pour l'affichage en direct
            new_sb = conn.execute("SELECT superbonbon FROM users WHERE user_id = ?", (uid,)).fetchone()
            if new_sb: self.action_view.user_sb = new_sb["superbonbon"]

        await interaction.response.send_message(msg, ephemeral=True)
        
        # Rafraichir la vue d'action sans changer de menu
        await self.action_view.parent_view.fetch_data()
        self.action_view.data = await self.action_view.parent_view.get_filtered_data(self.action)
        max_p = max(0, math.ceil(len(self.action_view.data) / self.action_view.per_page) - 1)
        self.action_view.page = min(self.action_view.page, max_p)
        self.action_view._build_view()
        await interaction.message.edit(embed=self.action_view.create_embed(), view=self.action_view)


# ==========================================
# VUES SECONDAIRES (PAGINATION DES ACTIONS)
# ==========================================
class DoublonActionView(discord.ui.View):
    def __init__(self, parent_view, action: str, data: list, user_sb: int = 0):
        super().__init__(timeout=180)
        self.parent_view = parent_view
        self.cog = parent_view.cog
        self.user = parent_view.user
        self.action = action
        self.data = data
        self.user_sb = user_sb
        self.page = 0
        self.per_page = 15
        self._build_view()

    def _apply_footer(self, embed: discord.Embed, current_page: int, total_pages: int):
        base_footer = embed.footer.text if embed.footer and embed.footer.text else ""
        base_icon = embed.footer.icon_url if embed.footer and embed.footer.icon_url else None
        
        page_text = f"Page {current_page + 1}/{total_pages}"
        new_footer = f"{base_footer} | {page_text}" if base_footer else page_text
        
        if base_icon:
            embed.set_footer(text=new_footer, icon_url=base_icon)
        else:
            embed.set_footer(text=new_footer)

    def _build_view(self):
        self.clear_items()
        
        start = self.page * self.per_page
        end = start + self.per_page
        current_data = self.data[start:end]

        if not current_data:
            btn_back = discord.ui.Button(label="Retour", style=discord.ButtonStyle.danger, emoji="🔙", row=0)
            btn_back.callback = self.go_back
            self.add_item(btn_back)
            return

        options = []
        for d in current_data:
            meta = d["meta"]
            
            # Utilisation de texte pur pour éviter le bug de l'emoji custom dans le menu déroulant
            shiny_label = "[Shiny] " if d["is_shiny"] else ""
            star_icon = f"{STAR_EMOJI} " if is_special_pokemon(d["pokemon_id"], d["legendary"], d["mythical"]) else ""
            
            desc = ""
            if self.action == "relacher":
                price = calculate_release_price(meta["total_stats"])
                desc = f"Qté dispo: {d['c'] - 1} | Gain: {format_number(price)} ₽/u"
            elif self.action == "evoluer":
                combos = d["c"] // 3
                sb_cost = 1 if meta["stage"] == 1 else 3
                desc = f"Combos: {combos} | Coût: {sb_cost} 🍬/combo"
            elif self.action == "recycler":
                desc = f"Qté dispo: {d['c'] - 4} | Détruire 1 copie pour des 🍬"
                
            options.append(discord.SelectOption(
                label=f"{shiny_label}{star_icon}{meta['name']} (x{d['c']})",
                value=f"{d['pokemon_id']}_{int(d['is_shiny'])}",
                description=desc
            ))

        placeholder = {
            "relacher": "Sélectionnez un Pokémon à relâcher...",
            "evoluer": "Sélectionnez un Pokémon à évoluer...",
            "recycler": "Sélectionnez un Pokémon à recycler..."
        }[self.action]

        sel = discord.ui.Select(placeholder=placeholder, options=options, row=0)
        sel.callback = self.on_select
        self.add_item(sel)

        if self.page > 0:
            btn_prev = discord.ui.Button(label="◀", style=discord.ButtonStyle.secondary, row=1)
            btn_prev.callback = self.prev_page
            self.add_item(btn_prev)

        if len(self.data) > end:
            btn_next = discord.ui.Button(label="▶", style=discord.ButtonStyle.secondary, row=1)
            btn_next.callback = self.next_page
            self.add_item(btn_next)

        btn_back = discord.ui.Button(label="Retour", style=discord.ButtonStyle.danger, emoji="🔙", row=1)
        btn_back.callback = self.go_back
        self.add_item(btn_back)

    async def on_select(self, interaction: discord.Interaction):
        pid_str, shiny_str = interaction.data["values"][0].split("_")
        pid, shiny = int(pid_str), bool(int(shiny_str))
        
        selected = next(d for d in self.data if d["pokemon_id"] == pid and d["is_shiny"] == shiny)
        
        max_qty = 1
        if self.action == "relacher":
            max_qty = selected["c"] - 1
        elif self.action == "evoluer":
            max_qty = selected["c"] // 3
        elif self.action == "recycler":
            max_qty = selected["c"] - 4

        modal = ActionModal(self, self.action, selected, max_qty, selected["meta"])
        await interaction.response.send_modal(modal)

    async def prev_page(self, interaction: discord.Interaction):
        self.page -= 1
        self._build_view()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.page += 1
        self._build_view()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    async def go_back(self, interaction: discord.Interaction):
        await self.parent_view.refresh_view(interaction, defer=False)

    def create_embed(self) -> discord.Embed:
        titres = {"relacher": "Relâcher", "evoluer": "Évoluer", "recycler": "Recycler"}
        descs = {
            "relacher": "Seuls les Pokémon en évolution finale sont affichés.\nRelâcher rapporte des Pokédollars selon la puissance de base.",
            "evoluer": f"{SUPERBONBON_EMOJI} **Superbonbons possédés :** `{self.user_sb}`\nNécessite 3 exemplaires identiques. Coûte des Superbonbons selon le stade.",
            "recycler": f"{SUPERBONBON_EMOJI} **Superbonbons possédés :** `{self.user_sb}`\nNécessite de posséder au moins 5 exemplaires. Détruit 1 exemplaire contre de nombreux Superbonbons."
        }
        
        if config_manager and hasattr(self.user, "guild"):
            embed = config_manager.get_formatted_embed(
                guild=self.user.guild, 
                user=self.user, 
                bot=self.cog.bot, 
                title="", 
                description=descs[self.action]
            )
        else:
            embed = discord.Embed(title="", description=descs[self.action], color=0x2B2D31)

        embed.set_author(name=f"Action : {titres[self.action]}", icon_url=self.user.display_avatar.url)

        if not self.data:
            embed.add_field(name="Vide", value="Aucun Pokémon ne correspond aux critères de cette action.")
            max_p = 1
            self._apply_footer(embed, self.page, max_p)
            return embed
            
        start = self.page * self.per_page
        end = start + self.per_page
        current_data = self.data[start:end]

        col1, col2, col3 = [], [], []
        
        for d in current_data:
            meta = d["meta"]
            shiny_icon = f"{SHINY_EMOJI} " if d["is_shiny"] else ""
            star_icon = f"{STAR_EMOJI} " if is_special_pokemon(d["pokemon_id"], d["legendary"], d["mythical"]) else ""
            
            col1.append(f"`#{d['pokemon_id']:04d}` {shiny_icon}{meta['name']} {star_icon}")
            col2.append(f"x{d['c']}")
            
            if self.action == "relacher":
                price = calculate_release_price(meta["total_stats"])
                col3.append(f"+{format_number(price)} {POKEDOLLAR_EMOJI}")
            elif self.action == "evoluer":
                next_id = meta.get("next_evo_id", 0)
                next_name = d.get("next_evo_name", "Inconnu")
                owned = "🔴" if not d.get("next_evo_owned") else POKEBALL_EMOJI
                col3.append(f"{owned} `#{next_id:04d}` {next_name}")
            elif self.action == "recycler":
                base_sb = meta["stage"]
                bonus = 0
                if d["is_shiny"]: bonus += 2
                if d["legendary"]: bonus += 3
                if d["mythical"]: bonus += 5
                if d["pokemon_id"] in UB_IDS: bonus += 3
                if d["pokemon_id"] in PARADOX_IDS: bonus += 1
                sb_reward = base_sb + bonus
                col3.append(f"+{sb_reward} {SUPERBONBON_EMOJI}")

        embed.add_field(name="Pokémon", value="\n".join(col1) or "-", inline=True)
        embed.add_field(name="Possédé", value="\n".join(col2) or "-", inline=True)
        
        if self.action == "relacher":
            embed.add_field(name="Gain/u", value="\n".join(col3) or "-", inline=True)
        elif self.action == "evoluer":
            embed.add_field(name="Évolution", value="\n".join(col3) or "-", inline=True)
        elif self.action == "recycler":
            embed.add_field(name="Gain/u", value="\n".join(col3) or "-", inline=True)

        max_p = max(1, math.ceil(len(self.data) / self.per_page))
        self._apply_footer(embed, self.page, max_p)
        return embed


# ==========================================
# VUE PRINCIPALE
# ==========================================
class DoublonMainView(discord.ui.View):
    def __init__(self, cog: "DoublonCog", user: discord.Member | discord.User, is_owner: bool):
        super().__init__(timeout=300)
        self.cog = cog
        self.user = user
        self.is_owner = is_owner
        self.duplicates = []
        self.page = 0
        self.per_page = 15

    def _apply_footer(self, embed: discord.Embed, current_page: int, total_pages: int):
        base_footer = embed.footer.text if embed.footer and embed.footer.text else ""
        base_icon = embed.footer.icon_url if embed.footer and embed.footer.icon_url else None
        
        page_text = f"Page {current_page + 1}/{total_pages}"
        new_footer = f"{base_footer} | {page_text}" if base_footer else page_text
        
        if base_icon:
            embed.set_footer(text=new_footer, icon_url=base_icon)
        else:
            embed.set_footer(text=new_footer)

    async def fetch_data(self):
        with self.cog.eco._get_conn() as conn:
            self.duplicates = conn.execute(
                """
                SELECT pokemon_id, is_shiny, legendary, mythical, COUNT(*) AS c
                FROM inventory
                WHERE user_id = ?
                GROUP BY pokemon_id, is_shiny
                HAVING COUNT(*) > 1
                ORDER BY pokemon_id ASC
                """,
                (self.user.id,)
            ).fetchall()
            self.duplicates = [dict(r) for r in self.duplicates]

    async def get_filtered_data(self, action: str):
        filtered = []
        async with aiohttp.ClientSession() as session:
            for d in self.duplicates:
                meta = await meta_cache.get_meta(session, d["pokemon_id"])
                
                if action == "relacher" and meta["is_final"] and d["c"] > 1:
                    d_copy = dict(d); d_copy["meta"] = meta
                    filtered.append(d_copy)
                elif action == "evoluer" and not meta["is_final"] and d["c"] >= 3:
                    d_copy = dict(d); d_copy["meta"] = meta
                    if meta.get("next_evo_id"):
                        d_copy["next_evo_name"] = await self.cog.eco.get_species_name_fr(session, meta["next_evo_id"])
                        d_copy["next_evo_owned"] = bool(self.cog.eco._get_conn().execute("SELECT 1 FROM inventory WHERE user_id = ? AND pokemon_id = ?", (self.user.id, meta["next_evo_id"])).fetchone())
                    filtered.append(d_copy)
                elif action == "recycler" and d["c"] >= 5:
                    d_copy = dict(d); d_copy["meta"] = meta
                    filtered.append(d_copy)
        return filtered

    def build_buttons(self):
        self.clear_items()
        
        if self.is_owner:
            btn_relacher = discord.ui.Button(label="Relâcher", style=discord.ButtonStyle.primary, emoji="📤", row=0)
            btn_relacher.callback = self.open_relacher
            self.add_item(btn_relacher)

            btn_evoluer = discord.ui.Button(label="Évoluer", style=discord.ButtonStyle.success, emoji="🧬", row=0)
            btn_evoluer.callback = self.open_evoluer
            self.add_item(btn_evoluer)

            btn_recycler = discord.ui.Button(label="Recycler", style=discord.ButtonStyle.danger, emoji="♻️", row=0)
            btn_recycler.callback = self.open_recycler
            self.add_item(btn_recycler)

        if self.page > 0:
            btn_prev = discord.ui.Button(label="◀", style=discord.ButtonStyle.secondary, row=1)
            btn_prev.callback = self.prev_page
            self.add_item(btn_prev)

        if len(self.duplicates) > (self.page + 1) * self.per_page:
            btn_next = discord.ui.Button(label="▶", style=discord.ButtonStyle.secondary, row=1)
            btn_next.callback = self.next_page
            self.add_item(btn_next)

    async def create_embed(self) -> discord.Embed:
        start = self.page * self.per_page
        end = start + self.per_page
        page_data = self.duplicates[start:end]

        desc = f"Voici la liste des Pokémon en double de {self.user.display_name}."

        if config_manager and hasattr(self.user, "guild"):
            embed = config_manager.get_formatted_embed(
                guild=self.user.guild, 
                user=self.user, 
                bot=self.cog.bot, 
                title="", 
                description=desc
            )
        else:
            embed = discord.Embed(title="", description=desc, color=0x2B2D31)

        embed.set_author(name=f"Doublons de {self.user.display_name}", icon_url=self.user.display_avatar.url)

        if not page_data:
            embed.add_field(name="Vide", value="*Aucun doublon trouvé.*", inline=False)
        else:
            async with aiohttp.ClientSession() as session:
                tasks = [meta_cache.get_meta(session, d["pokemon_id"]) for d in page_data]
                metas = await asyncio.gather(*tasks)

            col1, col2 = [], []
            for d, meta in zip(page_data, metas):
                shiny_icon = f"{SHINY_EMOJI} " if d["is_shiny"] else ""
                star_icon = f"{STAR_EMOJI} " if is_special_pokemon(d["pokemon_id"], d["legendary"], d["mythical"]) else ""
                
                col1.append(f"`#{d['pokemon_id']:04d}` | {shiny_icon}{meta['name']} {star_icon}")
                col2.append(f"**x{d['c']}**")

            embed.add_field(name="Pokémon", value="\n".join(col1) or "-", inline=True)
            embed.add_field(name="Possédé", value="\n".join(col2) or "-", inline=True)

        max_p = max(1, math.ceil(len(self.duplicates) / self.per_page))
        self._apply_footer(embed, self.page, max_p)
        
        return embed

    def _get_user_sb(self):
        user_sb = 0
        with self.cog.eco._get_conn() as conn:
            row = conn.execute("SELECT superbonbon FROM users WHERE user_id = ?", (self.user.id,)).fetchone()
            if row: user_sb = row["superbonbon"]
        return user_sb

    async def open_relacher(self, interaction: discord.Interaction):
        await interaction.response.defer()
        filtered = await self.get_filtered_data("relacher")
        view = DoublonActionView(self, "relacher", filtered)
        await interaction.edit_original_response(embed=view.create_embed(), view=view)

    async def open_evoluer(self, interaction: discord.Interaction):
        await interaction.response.defer()
        filtered = await self.get_filtered_data("evoluer")
        user_sb = self._get_user_sb()
        view = DoublonActionView(self, "evoluer", filtered, user_sb)
        await interaction.edit_original_response(embed=view.create_embed(), view=view)

    async def open_recycler(self, interaction: discord.Interaction):
        await interaction.response.defer()
        filtered = await self.get_filtered_data("recycler")
        user_sb = self._get_user_sb()
        view = DoublonActionView(self, "recycler", filtered, user_sb)
        await interaction.edit_original_response(embed=view.create_embed(), view=view)

    async def prev_page(self, interaction: discord.Interaction):
        self.page -= 1
        self.build_buttons()
        await interaction.response.edit_message(embed=await self.create_embed(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        self.page += 1
        self.build_buttons()
        await interaction.response.edit_message(embed=await self.create_embed(), view=self)

    async def refresh_view(self, interaction: discord.Interaction, defer: bool = False):
        await self.fetch_data()
        self.page = 0
        self.build_buttons()
        embed = await self.create_embed()
        
        if not interaction.response.is_done() and not defer:
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.message.edit(embed=embed, view=self)


class DoublonCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.eco = EconomyService(bot)

    @commands.hybrid_command(name="doublon", description="Gère tes doublons Pokémon.")
    async def doublon_cmd(self, ctx: commands.Context[commands.Bot], membre: discord.Member | discord.User | None = None):
        target = membre or ctx.author
        self.eco.ensure_user(target.id)
        is_owner = (target.id == ctx.author.id)

        view = DoublonMainView(self, target, is_owner)
        await view.fetch_data()
        view.build_buttons()
        
        embed = await view.create_embed()
        await ctx.send(embed=embed, view=view, reference=ctx.message)


async def setup(bot: commands.Bot):
    if bot.get_cog("DoublonCog"):
        await bot.remove_cog("DoublonCog")
    await bot.add_cog(DoublonCog(bot))