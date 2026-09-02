import discord
from discord.ext import commands, tasks
from datetime import datetime, timezone, timedelta
from utils.config_data import DataManager
from utils.config_theme import config_manager

# Active/desactive les logs debug du cog snipe
SNIPE_DEBUG = False


def debug_log(message: str):
    if SNIPE_DEBUG:
        print(f"[SNIPE DEBUG] {message}", flush=True)


class Snipe(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Initialisation du gestionnaire de données pour Snipe
        # Il créera automatiquement data/public/utilitaires/data_snipe
        self.db = DataManager("public/utilitaires/data_snipe")
        debug_log(f"Cog charge. Dossier de sauvegarde: {self.db.data_dir}")
        self.cleanup_task.start()

    def cog_unload(self):
        self.cleanup_task.cancel()

    # --- Boucle de Nettoyage (24h) ---
    @tasks.loop(hours=1)
    async def cleanup_task(self):
        now = datetime.now(timezone.utc)
        # Utilisation de la nouvelle méthode get_all_files de config_data
        for gid in self.db.get_all_files():
            data = self.db.load(gid)
            to_delete = []
            
            for cid, msg in data.items():
                ts = datetime.fromisoformat(msg['timestamp'])
                if now - ts >= timedelta(hours=24):
                    to_delete.append(cid)
                    
            for cid in to_delete:
                del data[cid]
                
            # Si data est vide, db.save supprimera automatiquement le fichier du serveur
            self.db.save(gid, data)

    # --- Nettoyage si le bot quitte un serveur ---
    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        self.db.delete(guild.id)

    # --- Capture des événements ---
    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author.bot or not message.guild:
            return

        debug_log(
            f"Message supprime de {message.author.id} sur le serveur {message.guild.id} "
            f"dans le salon {message.channel.id}"
        )

        await self._save_event(message, {"type": "del", "content": message.content})

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent):
        # Permet de diagnostiquer les suppressions non cachees
        if not payload.guild_id:
            return

        debug_log(
            f"Suppression detectee (raw) serveur={payload.guild_id} salon={payload.channel_id} message={payload.message_id}"
        )
        if payload.cached_message is None:
            debug_log("Message non en cache: contenu indisponible, impossible de le sauvegarder pour snipe.")

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.author.bot or not before.guild or before.content == after.content:
            return
        await self._save_event(before, {"type": "edit", "old": before.content, "new": after.content})

    async def _save_event(self, msg, extra):
        gid, cid = msg.guild.id, str(msg.channel.id)
        data = self.db.load(gid)

        # On écrase/sauvegarde le dernier événement du salon
        data[cid] = {
            "author_id": msg.author.id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **extra
        }
        self.db.save(gid, data)

        if extra.get("type") == "del":
            saved_path = self.db._get_path(gid)
            debug_log(f"Message sauvegarde dans {saved_path}")
            debug_log("en faisant la commande ²snipe vous pourrez voir le message supprime dans le salon")

    # --- Commande Snipe ---
    @commands.hybrid_command(name="snipe", description="Affiche la dernière activité (suppression/edit) du salon.")
    async def snipe(self, ctx):
        gid = ctx.guild.id
        cid = str(ctx.channel.id)
        data = self.db.load(gid)
        
        # Vérification si un message est enregistré pour ce salon
        if cid not in data:
            debug_log(f"Aucune donnee snipe pour serveur={gid} salon={cid}")
            if ctx.interaction:
                await ctx.send("❌ Aucun message récent trouvé dans ce salon.", ephemeral=True)
            else:
                await ctx.send("❌ Aucun message récent trouvé dans ce salon.")
            return

        msg_data = data[cid]
        is_del = msg_data['type'] == "del"
        
        # Horodatage et informations auteurs
        ts = int(datetime.fromisoformat(msg_data['timestamp']).timestamp())
        time_relative = f"<t:{ts}:R>"
        author_mention = f"<@{msg_data['author_id']}>"
        requester_name = ctx.author.display_name
        requester_avatar = ctx.author.display_avatar.url

        if is_del:
            description = (
                f"Message supprimé de {author_mention}. "
                f"Le message avait été écrit {time_relative}.\n\n"
                f"**Message :**\n{msg_data['content'] or '*Message vide*'}"
            )
            title = "🗑️ Message Supprimé"
        else:
            description = (
                f"Message modifié par {author_mention}. "
                f"Le message avait été écrit {time_relative}.\n\n"
                f"**Ancien :**\n```\n{msg_data['old'] or 'Vide'}\n```\n"
                f"**Nouveau :**\n```\n{msg_data['new'] or 'Vide'}\n```"
            )
            title = "✏️ Message Modifié"

        # --- Utilisation du Manager Embed ---
        if config_manager:
            embed = config_manager.get_formatted_embed(
                guild=ctx.guild,
                user=ctx.author,
                bot=self.bot,
                title=title,
                description=description,
                target_id=gid
            )
            if is_del:
                embed.set_author(name=f"Supprimé par {requester_name}", icon_url=requester_avatar)
        else:
            embed = discord.Embed(title=title, description=description, color=0x2b2d31)
            if is_del:
                embed.set_author(name=f"Supprimé par {requester_name}", icon_url=requester_avatar)
            embed.set_footer(text=f"Demandé par {ctx.author.name}")

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Snipe(bot))
