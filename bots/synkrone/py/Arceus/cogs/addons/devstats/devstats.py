import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
from pathlib import Path
from datetime import datetime
import asyncio

# ==============================================================================
# --------------------------- CONFIGURATION ------------------------------------
# ==============================================================================
DB_PATH = Path(__file__).parent / "dev_stats.db"

try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# ==============================================================================
# --------------------------- INTERFACE UI (VIEW) ------------------------------
# ==============================================================================

class DevStatsView(discord.ui.View):
    def __init__(self, cog, ctx: commands.Context):
        super().__init__(timeout=180)
        self.cog = cog
        self.ctx = ctx
        self.current_tab = "servers"
        self.current_page = 0
        self.pages_cache = []
        self.author_id = ctx.author.id
        self.show_ids = False

    async def get_content(self):
        if self.current_tab == "servers":
            self.pages_cache = await self.cog.get_server_list_pages()
        elif self.current_tab == "user_stats":
            self.pages_cache = await self.cog.get_user_stats_pages()
        elif self.current_tab == "guild_stats":
            self.pages_cache = await self.cog.get_guild_stats_pages()
        elif self.current_tab == "global_stats":
            # Affiche la page globale seule
            self.pages_cache = [await self.cog.get_global_stats_page()]
        else: # global_commands
            self.pages_cache = await self.cog.get_global_commands_pages()
        return self.pages_cache

    def update_components(self):
        self.clear_items()

        # 1. Pagination boutons (au-dessus)
        if len(self.pages_cache) > 1:
            prev_btn = discord.ui.Button(emoji="⬅️", style=discord.ButtonStyle.primary, disabled=(self.current_page == 0))
            next_btn = discord.ui.Button(emoji="➡️", style=discord.ButtonStyle.primary, disabled=(self.current_page == len(self.pages_cache)-1))
            prev_btn.callback = self.page_prev
            next_btn.callback = self.page_next
            self.add_item(prev_btn)
            self.add_item(next_btn)

        # Bouton Afficher/Masquer les ID (onglet serveurs)
        if self.current_tab == "servers":
            toggle_id_btn = discord.ui.Button(
                label=("Masquer les ID" if self.show_ids else "Afficher les ID"),
                style=discord.ButtonStyle.secondary
            )
            toggle_id_btn.callback = self.toggle_ids
            self.add_item(toggle_id_btn)

        # 2. Sélecteur de CATÉGORIE
        cat_options = [
            discord.SelectOption(label="Liste des Serveurs", emoji="🌐", value="servers", default=(self.current_tab == "servers")),
            discord.SelectOption(label="Utilisation des Commandes", emoji="🛠️", value="global_commands", default=(self.current_tab == "global_commands")),
            discord.SelectOption(label="Statistiques Utilisateurs", emoji="👤", value="user_stats", default=(self.current_tab == "user_stats")),
            discord.SelectOption(label="Statistiques Serveurs", emoji="📊", value="guild_stats", default=(self.current_tab == "guild_stats")),
            discord.SelectOption(label="Statistiques Globales", emoji="📈", value="global_stats", default=(self.current_tab == "global_stats")),
        ]
        select_cat = discord.ui.Select(placeholder="📁 Choisir une catégorie...", options=cat_options)
        select_cat.callback = self.change_category
        self.add_item(select_cat)

        # 3. Sélecteur d'INSPECTION (Onglet serveurs)
        if self.current_tab == "servers" and self.pages_cache:
            current_guilds = self.cog.last_guild_chunks.get(self.current_page, [])
            if current_guilds:
                options_srv = [
                    discord.SelectOption(label=f"{i+1}. {g.name[:90]}", description=f"{self.cog.get_human_count(g)} membres", value=str(g.id))
                    for i, g in enumerate(current_guilds)
                ]
                select_srv = discord.ui.Select(placeholder="🔍 Inspecter un serveur de cette page...", options=options_srv)
                select_srv.callback = self.inspect_server
                self.add_item(select_srv)

    async def toggle_ids(self, interaction: discord.Interaction):
        if not self._can_interact(interaction):
            await interaction.response.send_message("❌ Seul l'auteur de la commande peut interagir.", ephemeral=True)
            return
        self.show_ids = not self.show_ids
        await self.refresh(interaction)

    async def page_prev(self, it: discord.Interaction):
        if not self._can_interact(it):
            await it.response.send_message("❌ Seul l'auteur de la commande peut interagir.", ephemeral=True)
            return
        if self.current_page > 0:
            self.current_page -= 1
            await self.refresh(it)

    async def page_next(self, it: discord.Interaction):
        if not self._can_interact(it):
            await it.response.send_message("❌ Seul l'auteur de la commande peut interagir.", ephemeral=True)
            return
        if self.current_page < len(self.pages_cache)-1:
            self.current_page += 1
            await self.refresh(it)

    def _can_interact(self, it: discord.Interaction):
        return it.user.id == self.author_id

    async def refresh(self, interaction: discord.Interaction):
        await self.get_content()
        if self.current_page >= len(self.pages_cache): self.current_page = 0
        self.update_components()
        await interaction.response.edit_message(embed=self.pages_cache[self.current_page], view=self)

    async def change_category(self, it: discord.Interaction):
        if not self._can_interact(it):
            await it.response.send_message("❌ Seul l'auteur de la commande peut interagir.", ephemeral=True)
            return
        self.current_tab = it.data["values"][0]
        self.current_page = 0
        await self.refresh(it)

    # Pagination par boutons, plus de select_page

    async def inspect_server(self, it: discord.Interaction):
        if not self._can_interact(it):
            await it.response.send_message("❌ Seul l'auteur de la commande peut interagir.", ephemeral=True)
            return
        guild_id = int(it.data["values"][0])
        embed = await self.cog.get_detailed_guild_embed(guild_id)
        await it.response.send_message(embed=embed, ephemeral=True)

# ==============================================================================
# --------------------------- COG PRINCIPAL ------------------------------------
# ==============================================================================

class DevStats(commands.Cog):

    @commands.hybrid_command(name="resetdevstats", description="Réinitialise toutes les statistiques de développement (owner seulement)")
    async def resetdevstats(self, ctx: commands.Context):
        is_owner = await self.bot.is_owner(ctx.author)
        if not is_owner:
            return await ctx.send("❌ Seul l'owner du bot peut utiliser cette commande.", ephemeral=True)
        try:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute("DELETE FROM user_stats")
                conn.execute("DELETE FROM global_guild_stats")
                conn.execute("DELETE FROM command_stats")
                conn.execute("DELETE FROM command_usage_log")
            await ctx.send("✅ Toutes les statistiques de développement ont été remises à zéro !")
        except Exception as e:
            await ctx.send(f"❌ Erreur lors de la remise à zéro : {e}")
    def get_human_count(self, guild):
        return len([m for m in getattr(guild, 'members', []) if not m.bot])

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_guild_chunks = {}
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS user_stats (
                user_id INTEGER, guild_id INTEGER, username TEXT, 
                slash_count INTEGER DEFAULT 0, prefix_count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, guild_id))""")
            conn.execute("""CREATE TABLE IF NOT EXISTS global_guild_stats (
                guild_id INTEGER PRIMARY KEY, guild_name TEXT,
                slash_count INTEGER DEFAULT 0, prefix_count INTEGER DEFAULT 0)""")
            conn.execute("""CREATE TABLE IF NOT EXISTS command_stats (
                command_name TEXT, guild_id INTEGER,
                slash_count INTEGER DEFAULT 0, prefix_count INTEGER DEFAULT 0,
                PRIMARY KEY (command_name, guild_id))""")
            conn.execute("""CREATE TABLE IF NOT EXISTS command_usage_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                guild_id INTEGER,
                command_name TEXT,
                is_slash INTEGER,
                timestamp INTEGER
            )""")

    def _update_stats(self, user, guild, command_name, is_slash):
        col = "slash_count" if is_slash else "prefix_count"
        g_id = guild.id if guild else 0
        g_name = guild.name if guild else "DMs"
        now_ts = int(datetime.utcnow().timestamp())
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(f"""INSERT INTO user_stats (user_id, guild_id, username, {col}) VALUES (?, ?, ?, 1)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET {col} = {col} + 1, username = ?""", (user.id, g_id, str(user), str(user)))
            conn.execute(f"""INSERT INTO command_stats (command_name, guild_id, {col}) VALUES (?, ?, 1)
                ON CONFLICT(command_name, guild_id) DO UPDATE SET {col} = {col} + 1""", (command_name, g_id))
            if guild:
                conn.execute(f"""INSERT INTO global_guild_stats (guild_id, guild_name, {col}) VALUES (?, ?, 1)
                    ON CONFLICT(guild_id) DO UPDATE SET {col} = {col} + 1, guild_name = ?""", (g_id, g_name, g_name))
            # Log chaque utilisation
            conn.execute("""INSERT INTO command_usage_log (user_id, guild_id, command_name, is_slash, timestamp) VALUES (?, ?, ?, ?, ?)""",
                         (user.id, g_id, command_name, int(is_slash), now_ts))

    @commands.Cog.listener()
    async def on_app_command_completion(self, interaction: discord.Interaction, command):
        self._update_stats(interaction.user, interaction.guild, command.name, True)

    @commands.Cog.listener()
    async def on_command_completion(self, ctx):
        self._update_stats(ctx.author, ctx.guild, ctx.command.name, False)

    def create_embed(self, title, description, thumbnail=None):
        if config_manager:
            return config_manager.get_formatted_embed(None, self.bot.user, self.bot, title, description, thumbnail)
        emb = discord.Embed(title=title, description=description, color=0x3498db)
        if thumbnail: emb.set_thumbnail(url=thumbnail)
        return emb

    async def _get_best_invite(self, guild: discord.Guild):
        """Force la récupération d'une invitation par tous les moyens possibles"""
        # 1. Tenter de trouver une invitation existante
        try:
            invites = await guild.invites()
            for inv in invites:
                if inv.max_age == 0 or not inv.expired: return inv.url
        except: pass

        # 2. Tenter de créer une invitation sur le premier salon disponible
        # On trie pour essayer les salons textuels d'abord
        channels = sorted(guild.channels, key=lambda x: isinstance(x, discord.TextChannel), reverse=True)
        for channel in channels:
            try:
                if channel.permissions_for(guild.me).create_instant_invite:
                    new_inv = await channel.create_invite(max_age=3600, max_uses=1, reason="DevStats Inspection")
                    return new_inv.url
            except: continue
        
        # 3. Vanité URL si disponible
        if guild.vanity_url_code:
            return f"https://discord.gg/{guild.vanity_url_code}"
            
        return "⚠️ Impossible de créer une invitation (Permissions manquantes)"


    async def get_detailed_guild_embed(self, guild_id: int):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return self.create_embed("Erreur", "Serveur introuvable.")

        invite_url = await self._get_best_invite(guild)
        # Si le lien d'invitation n'est pas valide, afficher un message d'avertissement mais continuer l'affichage
        if invite_url.startswith("⚠️"):
            invite_display = f"{guild.name} *(invitation indisponible)*"
        else:
            invite_display = f"[{guild.name}]({invite_url})"

        with sqlite3.connect(DB_PATH) as conn:
            g_data = conn.execute("SELECT slash_count, prefix_count FROM global_guild_stats WHERE guild_id = ?", (guild_id,)).fetchone()
            top_users = conn.execute("SELECT username, slash_count, prefix_count FROM user_stats WHERE guild_id = ? ORDER BY (slash_count + prefix_count) DESC LIMIT 10", (guild_id,)).fetchall()
            top_cmds = conn.execute("SELECT command_name, slash_count, prefix_count FROM command_stats WHERE guild_id = ? ORDER BY (slash_count + prefix_count) DESC LIMIT 10", (guild_id,)).fetchall()

        s_cnt, p_cnt = (g_data[0], g_data[1]) if g_data else (0, 0)
        humans = self.get_human_count(guild)
        bots = guild.member_count - humans

        desc = (
            f"### 🌐 Informations Serveur\n"
            f"**Nom :** {invite_display}\n"
            f"**ID :** `{guild.id}`\n"
            f"**Création :** <t:{int(guild.created_at.timestamp())}:D>\n**Boosts :** `{guild.premium_subscription_count}`\n\n"
            f"### 👥 Membres\n└ Humains : `{humans}` | Bots : `{bots}`\n\n"
            f"### 📈 Utilisation\n└ Total : `{s_cnt + p_cnt}` | `Slash: {s_cnt}` | `Prefix: {p_cnt}`\n\n"
            f"### 🏆 Top 10 utilisateurs\n"
        )
        desc += "\n".join([f"`{i+1}.` **{n}** : `{s+p}` `[S:{s}|P:{p}]`" for i, (n, s, p) in enumerate(top_users)])
        desc += "\n\n### 🛠️ Top 10 commandes\n"
        desc += "\n".join([f"`{i+1}.` **{c}** : `{s+p}` `[S:{s}|P:{p}]`" for i, (c, s, p) in enumerate(top_cmds)])

        return self.create_embed(None, desc, guild.icon.url if guild.icon else None)

    async def get_server_list_pages(self):
        # Nettoyage automatique des serveurs non présents
        await self.clean_guilds_db()
        guilds = sorted(self.bot.guilds, key=lambda g: g.member_count, reverse=True)
        per_page, pages = 20, []
        self.last_guild_chunks = {}
        # Trouver la vue appelante pour savoir si show_ids est actif
        import inspect
        show_ids = False
        # On cherche dans la pile d'appels une instance de DevStatsView
        for frame in inspect.stack():
            local_self = frame.frame.f_locals.get('self')
            if isinstance(local_self, DevStatsView):
                show_ids = getattr(local_self, 'show_ids', False)
                break
        for p in range(0, len(guilds), per_page):
            chunk = guilds[p:p+per_page]
            self.last_guild_chunks[p//per_page] = chunk
            desc = "### 🌐 Liste des serveurs\n" + "\n".join(
                f"`{i+1:02d}.` **{g.name}** (`{g.id}`) • 👥 `{self.get_human_count(g)}" if show_ids else f"`{i+1:02d}.` **{g.name}** • 👥 `{self.get_human_count(g)}"
                for i, g in enumerate(chunk, p)
            )
            pages.append(self.create_embed(None, desc))
        return pages
    async def clean_guilds_db(self):
        """Supprime de la DB les serveurs où le bot n'est plus présent"""
        current_ids = {g.id for g in self.bot.guilds}
        with sqlite3.connect(DB_PATH) as conn:
            # user_stats
            conn.execute(f"DELETE FROM user_stats WHERE guild_id NOT IN ({','.join(['?']*len(current_ids))})", tuple(current_ids) if current_ids else (0,))
            # command_stats
            conn.execute(f"DELETE FROM command_stats WHERE guild_id NOT IN ({','.join(['?']*len(current_ids))})", tuple(current_ids) if current_ids else (0,))
            # global_guild_stats
            conn.execute(f"DELETE FROM global_guild_stats WHERE guild_id NOT IN ({','.join(['?']*len(current_ids))})", tuple(current_ids) if current_ids else (0,))

    async def get_global_commands_pages(self):
        # Récupère la liste des commandes existantes
        all_commands = set()
        for cmd in self.bot.commands:
            all_commands.add(cmd.name)
        # Pour les app_commands (slash)
        if hasattr(self.bot, 'tree'):
            for appcmd in getattr(self.bot, 'tree').walk_commands():
                all_commands.add(appcmd.name)
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute("SELECT command_name, SUM(slash_count), SUM(prefix_count) FROM command_stats GROUP BY command_name ORDER BY (SUM(slash_count) + SUM(prefix_count)) DESC").fetchall()
        # Filtre les commandes qui existent encore
        filtered = [(c, s, pr) for (c, s, pr) in rows if c in all_commands]
        per_page, pages = 20, []
        for p in range(0, len(filtered), per_page):
            chunk = filtered[p:p+per_page]
            desc = "### 🛠️ Utilisation globale des commandes\n" + "\n".join([f"`{i+1:02d}.` **{c}** : `{s+pr}` `[S:{s}|P:{pr}]`" for i, (c, s, pr) in enumerate(chunk, p)])
            pages.append(self.create_embed(None, desc))
        return pages if pages else [self.create_embed(None, "Aucune donnée.")]

    async def get_global_stats_page(self):
        """Page 5 : stats globales (total, mois, semaine, jour)"""
        now = datetime.utcnow()
        today_start = datetime(now.year, now.month, now.day)
        week_start = today_start
        # ISO weekday: Monday=1, Sunday=7
        week_start = today_start.replace(day=today_start.day - (today_start.isoweekday() - 1))
        month_start = today_start.replace(day=1)
        ts_today = int(today_start.timestamp())
        ts_week = int(week_start.timestamp())
        ts_month = int(month_start.timestamp())
        with sqlite3.connect(DB_PATH) as conn:
            # Total = somme slash + prefix
            total = conn.execute("SELECT SUM(slash_count)+SUM(prefix_count) FROM command_stats").fetchone()[0] or 0
            month_count = conn.execute("SELECT COUNT(*) FROM command_usage_log WHERE timestamp >= ?", (ts_month,)).fetchone()[0]
            week_count = conn.execute("SELECT COUNT(*) FROM command_usage_log WHERE timestamp >= ?", (ts_week,)).fetchone()[0]
            today_count = conn.execute("SELECT COUNT(*) FROM command_usage_log WHERE timestamp >= ?", (ts_today,)).fetchone()[0]
        desc = (
            f"### 📈 Statistiques globales\n"
            f"- Nombre de commandes totale utilisée : **{total}**\n"
            f"- Ce mois-ci : **{month_count}**\n"
            f"- Cette semaine : **{week_count}**\n"
            f"- Aujourd'hui : **{today_count}**\n"
        )
        return self.create_embed(None, desc)

    async def get_user_stats_pages(self):
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute("SELECT username, SUM(slash_count), SUM(prefix_count) FROM user_stats GROUP BY user_id ORDER BY (SUM(slash_count) + SUM(prefix_count)) DESC LIMIT 100").fetchall()
        pages = []
        per_page = 10
        for p in range(0, len(rows), per_page):
            chunk = rows[p:p+per_page]
            desc = "### 👤 Classement des utilisateurs\n" + "\n".join([
                f"`#{p+i+1:02d}` **{n}**\n└ Total : `{s+pnt}` `[S:{s}|P:{pnt}]`"
                for i, (n, s, pnt) in enumerate(chunk)
            ])
            pages.append(self.create_embed(None, desc))
        return pages if pages else [self.create_embed(None, "Aucune donnée.")]

    async def get_guild_stats_pages(self):
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute("SELECT guild_name, slash_count, prefix_count FROM global_guild_stats ORDER BY (slash_count + prefix_count) DESC LIMIT 100").fetchall()
        pages = []
        per_page = 10
        for p in range(0, len(rows), per_page):
            chunk = rows[p:p+per_page]
            desc = "### 📊 Classement des serveurs\n" + "\n".join([
                f"`#{p+i+1:02d}` **{n}**\n└ Total : `{s+pnt}` `[S:{s}|P:{pnt}]`"
                for i, (n, s, pnt) in enumerate(chunk)
            ])
            pages.append(self.create_embed(None, desc))
        return pages if pages else [self.create_embed(None, "Aucune donnée.")]

    @commands.hybrid_command(name="devstats", description="Menu statistiques de développement")
    async def devstats(self, ctx: commands.Context):
        is_owner = await self.bot.is_owner(ctx.author)
        if not is_owner:
            return await ctx.send("❌ Seul l'owner du bot peut utiliser cette commande.", ephemeral=True)
        try:
            if hasattr(ctx, 'interaction') and ctx.interaction:
                await ctx.defer(ephemeral=True)
            view = DevStatsView(self, ctx)
            # Prépare toutes les pages
            await view.get_content()
            # Ajoute la page globale
            global_stats_page = await self.get_global_stats_page()
            view.pages_cache.append(global_stats_page)
            view.update_components()
            if hasattr(ctx, 'interaction') and ctx.interaction:
                await ctx.send(embed=view.pages_cache[0], view=view, ephemeral=True)
            else:
                await ctx.send(embed=view.pages_cache[0], view=view)
        except Exception as e:
            raise

async def setup(bot: commands.Bot):
    await bot.add_cog(DevStats(bot))