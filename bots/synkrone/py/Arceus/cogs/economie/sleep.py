import time
import math
from typing import Any

import aiohttp
import discord
from discord.ext import commands

from .utils import EconomyService

try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

POKEDOLLAR_EMOJI = "₽"
SHINY_EMOJI = "<:shiny:1522947934969270312>"

def format_number(num):
    """Formatage des nombres avec espaces (1000 -> 1 000)"""
    try:
        return f"{int(num):,}".replace(',', ' ')
    except:
        return "0"

class SleepDepositModal(discord.ui.Modal):
    def __init__(self, view: "SleepMainView", max_slots: int):
        super().__init__(title="Stocker un Pokémon")
        self.sleep_view = view
        self.cog = view.cog

        self.inv_id = discord.ui.TextInput(
            label="ID d'Inventaire du Pokémon",
            style=discord.TextStyle.short,
            placeholder="Ex: 42",
            required=True
        )
        self.add_item(self.inv_id)

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        try:
            target_id = int(self.inv_id.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ L'ID doit être un nombre entier valide.", ephemeral=True)
            return

        with self.cog.eco._get_conn() as conn:
            # 1. Vérifier si la garderie n'est pas pleine
            current_slots = conn.execute("SELECT COUNT(*) as c FROM daycare WHERE user_id = ?", (user_id,)).fetchone()["c"]
            if current_slots >= self.sleep_view.max_slots:
                await interaction.response.send_message("❌ Ta garderie est déjà pleine !", ephemeral=True)
                return

            # 2. Vérifier la possession
            inv_pokemon = conn.execute("SELECT pokemon_id, name, is_shiny, legendary, mythical FROM inventory WHERE id = ? AND user_id = ?", (target_id, user_id)).fetchone()
            if not inv_pokemon:
                await interaction.response.send_message("❌ Ce Pokémon ne t'appartient pas ou n'existe pas.", ephemeral=True)
                return

            # 3. Vérifier s'il est déjà en garderie
            in_daycare = conn.execute("SELECT 1 FROM daycare WHERE pokemon_inv_id = ?", (target_id,)).fetchone()
            if in_daycare:
                await interaction.response.send_message("❌ Ce Pokémon est déjà à la garderie.", ephemeral=True)
                return

            # 4. Vérifier s'il est dans l'équipe
            in_team = conn.execute("SELECT 1 FROM teams WHERE inventory_id = ?", (target_id,)).fetchone()
            if in_team:
                await interaction.response.send_message("❌ Ce Pokémon est actuellement dans ton équipe active. Retire-le d'abord.", ephemeral=True)
                return

        await interaction.response.defer(ephemeral=True)

        # 5. Calculer le taux horaire (Requête PokeAPI pour les stats)
        async with aiohttp.ClientSession() as session:
            stats = await self.cog.eco.fetch_pokemon_stats(session, inv_pokemon["pokemon_id"])
            
            if not stats:
                await interaction.followup.send("❌ Impossible de récupérer les statistiques du Pokémon via l'API.", ephemeral=True)
                return
                
            total_stats = stats.get("hp", 1) + stats.get("attack", 1) + stats.get("defense", 1) + stats.get("speed", 1)
            
        multiplier = 1.0
        if inv_pokemon["legendary"] or inv_pokemon["mythical"]:
            multiplier *= 1.5
        if inv_pokemon["is_shiny"]:
            multiplier *= 2.0
            
        hourly_rate = int(total_stats * multiplier)

        # 6. Insertion dans la garderie
        with self.cog.eco._get_conn() as conn:
            conn.execute(
                "INSERT INTO daycare (user_id, pokemon_inv_id, start_time, hourly_rate) VALUES (?, ?, ?, ?)",
                (user_id, target_id, int(time.time()), hourly_rate)
            )

        shiny_prefix = f"{SHINY_EMOJI} " if inv_pokemon["is_shiny"] else ""
        await interaction.followup.send(f"✅ **{shiny_prefix}{inv_pokemon['name']}** se repose maintenant à la garderie ! (Taux: `{format_number(hourly_rate)}` {POKEDOLLAR_EMOJI}/h)", ephemeral=True)
        
        # Rafraichir la vue
        await self.sleep_view.refresh_view(interaction)


class SleepMainView(discord.ui.View):
    def __init__(self, cog: "SleepCog", author_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.author_id = author_id
        self.message: discord.Message | None = None
        self.level = 1
        self.max_slots = 1
        self.slots_data = []

    async def init_data(self):
        """Récupère toutes les données nécessaires pour l'affichage de la vue."""
        with self.cog.eco._get_conn() as conn:
            row = conn.execute("SELECT level FROM users WHERE user_id = ?", (self.author_id,)).fetchone()
            self.level = row["level"] if row else 1
            # 1 slot par tranche de 10 niveaux (Niv 1 = 1, Niv 10 = 2 ... Niv 100 = 11)
            self.max_slots = min(11, 1 + (self.level // 10))
            
            self.slots_data = conn.execute(
                """
                SELECT d.id as daycare_id, d.pokemon_inv_id, d.start_time, d.hourly_rate,
                       i.pokemon_id, i.name, i.is_shiny, i.legendary, i.mythical
                FROM daycare d
                JOIN inventory i ON i.id = d.pokemon_inv_id
                WHERE d.user_id = ?
                """,
                (self.author_id,)
            ).fetchall()

        self.clear_items()

        # Bouton Récupérer Tout
        btn_claim = discord.ui.Button(label="Récupérer Tout", emoji="🎁", style=discord.ButtonStyle.success)
        btn_claim.callback = self.claim_rewards
        self.add_item(btn_claim)

        # Bouton Stocker (si non plein)
        if len(self.slots_data) < self.max_slots:
            btn_store = discord.ui.Button(label="Stocker", emoji="📥", style=discord.ButtonStyle.primary)
            btn_store.callback = self.store_pokemon
            self.add_item(btn_store)

        # Bouton Aide & Suggestions
        btn_help = discord.ui.Button(label="Aide & Suggestions", emoji="💡", style=discord.ButtonStyle.secondary)
        btn_help.callback = self.show_help
        self.add_item(btn_help)

        # Menu déroulant pour Retirer (si des Pokémon sont présents)
        if self.slots_data:
            options = []
            for slot in self.slots_data:
                shiny_icon = "✨ " if slot["is_shiny"] else ""
                options.append(discord.SelectOption(
                    label=f"ID: {slot['pokemon_inv_id']} | {shiny_icon}{slot['name']}",
                    value=str(slot['daycare_id']),
                    description="Retirer ce Pokémon et récolter ses gains",
                    emoji="📤"
                ))
            
            sel = discord.ui.Select(placeholder="Sélectionnez un Pokémon à retirer...", options=options, row=1)
            sel.callback = self.remove_pokemon
            self.add_item(sel)

    def create_embed(self, user: discord.abc.User) -> discord.Embed:
        desc = (
            "Bienvenue dans la Garderie !\nVos Pokémon se reposent et génèrent des Pokédollars passifs en fonction de leurs statistiques.\n\n"
            f"📈 **Niveau actuel :** {self.level}\n"
            f"📦 **Places disponibles :** {len(self.slots_data)} / {self.max_slots}\n\n"
        )

        now = int(time.time())
        if not self.slots_data:
            desc += "> *Aucun Pokémon en garderie actuellement.*\n> *Cliquez sur **Stocker** pour commencer.*"
        else:
            for idx, slot in enumerate(self.slots_data, start=1):
                elapsed_hours = (now - slot["start_time"]) / 3600
                pending_col = int(elapsed_hours * slot["hourly_rate"])
                
                shiny_prefix = f"{SHINY_EMOJI} " if slot["is_shiny"] else ""
                
                desc += f"**{idx}.** {shiny_prefix}**{slot['name']}** (ID: `{slot['pokemon_inv_id']}`)\n"
                desc += f"└ ⏳ `{elapsed_hours:.1f}h` écoulées • Taux: `{format_number(slot['hourly_rate'])}/h` • Gain act.: `+{format_number(pending_col)}` {POKEDOLLAR_EMOJI}\n\n"

        if config_manager and hasattr(user, "guild"):
            embed = config_manager.get_formatted_embed(
                guild=user.guild, 
                user=user, 
                bot=self.cog.bot, 
                title="⛺ Garderie Pokémon", 
                description=desc
            )
        else:
            embed = discord.Embed(title="⛺ Garderie Pokémon", description=desc, color=0x2b2d31)
            
        if hasattr(user, 'display_avatar') and user.display_avatar:
            embed.set_thumbnail(url=user.display_avatar.url)
            
        return embed

    async def claim_rewards(self, interaction: discord.Interaction):
        now = int(time.time())
        total_gained = 0
        
        with self.cog.eco._get_conn() as conn:
            for slot in self.slots_data:
                elapsed_hours = (now - slot["start_time"]) / 3600
                gain = int(elapsed_hours * slot["hourly_rate"])
                if gain > 0:
                    total_gained += gain
                    conn.execute("UPDATE daycare SET start_time = ? WHERE id = ?", (now, slot["daycare_id"]))
            
            if total_gained > 0:
                conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (total_gained, self.author_id))

        if total_gained == 0:
            await interaction.response.send_message("❌ Trop tôt pour récolter, tu n'as généré aucun Pokédollar.", ephemeral=True)
            return

        await interaction.response.send_message(f"✅ **Récompenses récupérées !**\n`+{format_number(total_gained)}` {POKEDOLLAR_EMOJI}", ephemeral=True)
        await self.refresh_view(interaction, defer=False)

    async def store_pokemon(self, interaction: discord.Interaction):
        modal = SleepDepositModal(self, self.max_slots)
        await interaction.response.send_modal(modal)

    async def remove_pokemon(self, interaction: discord.Interaction):
        target_daycare_id = int(interaction.data["values"][0])
        now = int(time.time())
        gained = 0
        pokemon_name = "Ton Pokémon"
        
        with self.cog.eco._get_conn() as conn:
            slot = conn.execute("SELECT start_time, hourly_rate, pokemon_inv_id FROM daycare WHERE id = ? AND user_id = ?", (target_daycare_id, self.author_id)).fetchone()
            
            if slot:
                inv = conn.execute("SELECT name, is_shiny FROM inventory WHERE id = ?", (slot["pokemon_inv_id"],)).fetchone()
                if inv:
                    shiny_prefix = f"{SHINY_EMOJI} " if inv["is_shiny"] else ""
                    pokemon_name = f"{shiny_prefix}{inv['name']}"
                
                elapsed_hours = (now - slot["start_time"]) / 3600
                gained = int(elapsed_hours * slot["hourly_rate"])
                
                conn.execute("DELETE FROM daycare WHERE id = ?", (target_daycare_id,))
                
                if gained > 0:
                    conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (gained, self.author_id))

        msg = f"✅ **{pokemon_name}** a été retiré de la garderie !"
        if gained > 0:
            msg += f"\n`+{format_number(gained)}` {POKEDOLLAR_EMOJI} ont été récupérés avant son départ."
            
        await interaction.response.send_message(msg, ephemeral=True)
        await self.refresh_view(interaction, defer=False)

    async def show_help(self, interaction: discord.Interaction):
        # Récupère les meilleurs Pokémon dispos (non dans l'équipe, non dans la garderie)
        # On trie intelligemment par ceux qui ont les plus gros multiplicateurs naturels.
        with self.cog.eco._get_conn() as conn:
            suggestions = conn.execute(
                """
                SELECT id, pokemon_id, name, is_shiny, legendary, mythical, level 
                FROM inventory 
                WHERE user_id = ? 
                  AND id NOT IN (SELECT inventory_id FROM teams WHERE user_id = ?)
                  AND id NOT IN (SELECT pokemon_inv_id FROM daycare)
                ORDER BY mythical DESC, legendary DESC, is_shiny DESC, level DESC
                LIMIT ?
                """,
                (self.author_id, self.author_id, self.max_slots)
            ).fetchall()

        desc = (
            "**Comment fonctionne la Garderie ?**\n"
            "1️⃣ La capacité de ta garderie dépend de ton niveau (1 place Niv.1, 2 places Niv.10... Max 11 places Niv.100).\n"
            "2️⃣ Le gain horaire dépend du total des stats de base du Pokémon déposé.\n"
            "3️⃣ **Bonus Multiplicateurs** :\n"
            "└ Légendaire / Fabuleux = **x1.5**\n"
            f"└ Shiny = **x2** {SHINY_EMOJI}\n\n"
            "**💡 Suggestions pour vous :**\n"
            "*Voici les Pokémon disponibles les plus rentables de votre inventaire :*\n"
        )
        
        if not suggestions:
            desc += "> *Vous n'avez aucun Pokémon éligible disponible.*"
        else:
            for s in suggestions:
                shiny_icon = f"{SHINY_EMOJI} " if s["is_shiny"] else ""
                leg_myth = ""
                if s["mythical"]: leg_myth = " [Fabuleux 🌟]"
                elif s["legendary"]: leg_myth = " [Légendaire 👑]"
                
                desc += f"ID: `{s['id']}` - {shiny_icon}**{s['name']}** (Niv. {s['level']}){leg_myth}\n"

        embed = discord.Embed(title="Aide & Suggestions Garderie", description=desc, color=0x3498db)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def refresh_view(self, interaction: discord.Interaction, defer: bool = False):
        await self.init_data()
        embed = self.create_embed(interaction.user)
        try:
            if not interaction.response.is_done() and not defer:
                await interaction.response.edit_message(embed=embed, view=self)
            else:
                await interaction.message.edit(embed=embed, view=self)
        except discord.HTTPException:
            pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ Cette garderie ne vous appartient pas.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class SleepCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.eco = EconomyService(bot)
        self.ensure_daycare_schema()

    def ensure_daycare_schema(self):
        """Met à jour la structure de la table daycare pour supporter de multiples slots et le taux horaire."""
        with self.eco._get_conn() as conn:
            cursor = conn.execute("PRAGMA table_info(daycare)")
            columns = {row["name"]: row["type"] for row in cursor.fetchall()}
            
            if "id" not in columns:
                try:
                    conn.execute("ALTER TABLE daycare RENAME TO daycare_old")
                    conn.execute("""
                        CREATE TABLE daycare (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            user_id INTEGER NOT NULL,
                            pokemon_inv_id INTEGER NOT NULL,
                            start_time INTEGER NOT NULL,
                            hourly_rate INTEGER NOT NULL DEFAULT 100
                        )
                    """)
                    conn.execute("""
                        INSERT INTO daycare (user_id, pokemon_inv_id, start_time) 
                        SELECT user_id, pokemon_inv_id, start_time FROM daycare_old
                    """)
                    conn.execute("DROP TABLE daycare_old")
                except Exception as e:
                    print(f"[Daycare Migration] Erreur: {e}")
            elif "hourly_rate" not in columns:
                conn.execute("ALTER TABLE daycare ADD COLUMN hourly_rate INTEGER NOT NULL DEFAULT 100")

    @commands.hybrid_command(name="sleep", description="Ouvre ta garderie pour gagner des Pokédollars passifs.")
    async def sleep_cmd(self, ctx: commands.Context[commands.Bot]):
        self.eco.ensure_user(ctx.author.id)
        
        view = SleepMainView(self, ctx.author.id)
        await view.init_data()
        
        embed = view.create_embed(ctx.author)
        msg = await ctx.send(embed=embed, view=view, reference=ctx.message)
        view.message = msg


async def setup(bot: commands.Bot):
    if bot.get_cog("SleepCog"):
        await bot.remove_cog("SleepCog")
    await bot.add_cog(SleepCog(bot))