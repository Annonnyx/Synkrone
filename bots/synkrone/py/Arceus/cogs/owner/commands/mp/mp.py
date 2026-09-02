import discord
from discord.ext import commands, tasks
from pathlib import Path
import re
from datetime import datetime
import os

# ==============================================================================
# --------------------------- IMPORTATION UTILS --------------------------------
# ==============================================================================
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# Rôles autorisés à utiliser la commande /mp
ALLOWED_ROLES = [
    1368719335534887023,  # Rôle 1 (ex: Staff)
    1369430431212114002,  # Rôle 2 (ex: Modérateur)
    1368620965403299890,  # Rôle 3 (ex: Admin)
    1457021902047674560   # Rôle 4 (ex: Gérant)
]
LOG_CHANNEL_ID = 1492280022302720041           # ID du canal de logs pour les messages MPs/threads
ROLE_NOTIF_ID = 1465825778771034236            # ID du rôle à mentionner pour les notifications help

# IDs des serveurs et canaux Discord
GUILD_ID = int(os.getenv("GUILD_ID", "0"))       # ID du serveur principal depuis .env /mp        
ID_FONDATEUR = int(os.getenv("CREATED_BY") or "0")  # ID Discord du créateur depuis .env



# Ajout automatique du créateur comme rôle autorisé
def get_allowed_roles():
    """Retourne la liste des rôles autorisés en ajoutant automatiquement le créateur"""
    roles = ALLOWED_ROLES.copy()
    if ID_FONDATEUR not in roles:
        roles.append(ID_FONDATEUR)
    return roles

BASE_PATH = Path(__file__).parent
DATA_FOLDER = BASE_PATH / "data" / "users"
SUPPORT_FILE = BASE_PATH / "data" / "support.json"

# ==============================================================================
# --------------------------- GESTION DES FICHIERS -----------------------------
# ==============================================================================

def save_to_json(user, content, speaker_type="Utilisateur"):
    pass


# ==============================================================================
# --------------------------- COG PRINCIPAL ------------------------------------
# ==============================================================================

class DevMessaging(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_unload(self):
        self.clean_thread_starter_messages.cancel()

    @tasks.loop(minutes=5)
    async def clean_thread_starter_messages(self):
        await self.delete_thread_starter_messages()

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.clean_thread_starter_messages.is_running():
            self.clean_thread_starter_messages.start()
        await self.delete_thread_starter_messages()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot and not message.is_system(): 
            return

        # Suppression immédiate des messages système "a commencé un fil :"
        if message.channel.id == LOG_CHANNEL_ID and (
            message.type == discord.MessageType.thread_starter_message
            or message.is_system()
            or (message.content and "a commencé un fil :" in message.content)
        ):
            try:
                await message.delete()
            except Exception:
                pass
            return

        # RÉCEPTION DM (L'utilisateur parle au bot)
        if isinstance(message.channel, discord.DMChannel) and not message.author.bot:
            # Réponse automatique avec embed vers le support
            if config_manager:
                embed = config_manager.get_formatted_embed(None, message.author, self.bot, None, "*Message envoyé à l'équipe [𝑺𝒚𝒏𝒌𝒓𝒐𝒏𝒆 𝑺𝒖𝒑𝒑𝒐𝒓𝒕](https://discord.gg/p768u2Pgp3).*", None)
            else:
                embed = discord.Embed(
                    description="*Message envoyé à l'équipe [𝑺𝒚𝒏𝒌𝒓𝒐𝒏𝒆 𝑺𝒖𝒑𝒑𝒐𝒓𝒕](https://discord.gg/p768u2Pgp3).*",
                    color=discord.Color.blue()
                )
            await message.reply(embed=embed, mention_author=False)
            save_to_json(message.author, message.content, "Utilisateur")

            thread = await self.get_or_create_thread(message.author)
            log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
            
            if not thread:
                print(f"[ERREUR] Impossible d'envoyer le message dans le fil pour {message.author}.")
                return
                
            thread_url = thread.jump_url

            # Récupère le pseudo serveur (display_name) avec majuscule
            try:
                guild = self.bot.get_guild(GUILD_ID)
                member = await guild.fetch_member(message.author.id) if guild else None
                display_name = member.display_name if member else message.author.name
            except Exception:
                display_name = message.author.name
                
            display_name = display_name[:1].upper() + display_name[1:]

            # Envoi du log avec l'ID bien visible pour faciliter la mise à jour (🔴 -> 🟢)
            embed_color = 0xED4245  # Rouge par défaut
            embed = discord.Embed(color=embed_color)
            embed.description = f"🔴 Message de [{display_name}]({thread_url})"
            now = datetime.now().strftime("%d/%m/%Y %H:%M")
            embed.set_footer(text=f"{now} - {message.author.id}")
            
            await log_channel.send(embed=embed)

            # Traitement du message à envoyer dans le fil
            files = [await a.to_file() for a in message.attachments]
            tag = f"<@&{ROLE_NOTIF_ID}> " if message.content and re.search(r"\bhelp\b", message.content, re.IGNORECASE) else ""
            content_str = message.content.strip() if message.content else ""
            
            final_content = f"{tag}{content_str}".strip()

            # Si le contenu est vide mais qu'il y a des fichiers
            sent_msg = None
            if not final_content and files:
                sent_msg = await thread.send(files=files)
            elif final_content:
                sent_msg = await thread.send(content=final_content, files=files)

            # S'assure que seule le dernier message du bot a la réaction 🟢
            if sent_msg:
                # Retire la réaction 🟢 de tous les autres messages du bot dans le thread
                async for msg in thread.history(limit=50):
                    if msg.id == sent_msg.id:
                        continue
                    if msg.author.id == self.bot.user.id:
                        try:
                            for react in msg.reactions:
                                if str(react.emoji) == "✅":
                                    async for u in react.users():
                                        await msg.remove_reaction("✅", u)
                        except Exception:
                            pass
                # Ajoute la réaction 🟢 sur le dernier message
                try:
                    await sent_msg.add_reaction("✅")
                except Exception:
                    pass

        # RÉPONSE DANS LE FIL (Le staff répond à l'utilisateur)
        elif isinstance(message.channel, discord.Thread) and message.channel.parent_id == LOG_CHANNEL_ID:
            try:
                match = re.search(r'\d+', message.channel.name)
                if not match:
                    return
                
                u_id = int(match.group())
                user = await self.bot.fetch_user(u_id)
                
                if user and await self.send_global_logic(message.author, user, message.content, message.attachments, message.channel, mirror_in_thread=False):
                    await message.add_reaction("✅")

                    # Met à jour les anciens messages de log (🔴 -> 🟢)
                    log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
                    async for log_msg in log_channel.history(limit=100):
                        if log_msg.embeds:
                            embed = log_msg.embeds[0]
                            # On cherche l'ID dans le footer, pas dans la description
                            footer = embed.footer.text if embed.footer else ""
                            if (
                                embed.description and 
                                embed.description.startswith("🔴 Message de ") and 
                                f"{u_id}" in footer
                            ):
                                new_embed = embed.copy()
                                new_embed.description = new_embed.description.replace("🔴", "🟢", 1)
                                new_embed.color = 0x57F287  # Vert Discord
                                await log_msg.edit(embed=new_embed)
            except Exception:
                pass


    async def delete_thread_starter_messages(self):
        log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if not log_channel:
            return
        async for msg in log_channel.history(limit=100):
            if (
                msg.type == discord.MessageType.thread_starter_message
                or msg.is_system()
                or (msg.content and "a commencé un fil :" in msg.content)
            ):
                try:
                    await msg.delete()
                except Exception:
                    pass

    async def get_or_create_thread(self, user):
        await self.delete_thread_starter_messages()
        channel = self.bot.get_channel(LOG_CHANNEL_ID)
        if not channel:
            return None
            
        thread_name = str(user.id)
        thread = discord.utils.get(channel.threads, name=thread_name)
        try:
            if not thread:
                thread = await channel.create_thread(name=thread_name, type=discord.ChannelType.public_thread)
            if thread.archived:
                await thread.edit(archived=False)
            return thread
        except Exception:
            return None

    async def send_global_logic(self, staff, target, content, files_raw, thread=None, mirror_in_thread=True):
        rank = "Fondateur" if staff.id == ID_FONDATEUR else "Équipe Staff"
        desc = (
            f"{content if content else '*Fichier multimédia*'}\n\n"
            f"-# *Si vous souhaitez notifier [𝑺𝒚𝒏𝒌𝒓𝒐𝒏𝒆 𝑺𝒖𝒑𝒑𝒐𝒓𝒕](https://discord.gg/p768u2Pgp3), utilisez le mot clé : `help`*"
        )
        
        if config_manager:
            embed = config_manager.get_formatted_embed(None, staff, self.bot, None, desc, None)
        else:
            embed = discord.Embed(description=desc, color=discord.Color.blue())
        
        staff_display = staff.name[:1].upper() + staff.name[1:]
        embed.set_author(name=f"Message de {rank} - {staff_display}", icon_url=staff.display_avatar.url)
                
        if files_raw:
            for a in files_raw:
                if any(ext in a.filename.lower() for ext in ['png', 'jpg', 'jpeg', 'gif', 'webp']):
                    embed.set_image(url=f"attachment://{a.filename}")
                    break

        try:
            f_user = [await a.to_file() for a in files_raw]
            await target.send(embed=embed, files=f_user)
            save_to_json(target, content, "Équipe")
            
            if thread and mirror_in_thread:
                f_staff = [await a.to_file() for a in files_raw]
                await thread.send(embed=embed, files=f_staff)
                
            return True
        except Exception: 
            return False

    @commands.command(name="mp")
    async def mp(self, ctx: commands.Context, user: discord.User, *, message: str = ""):
        if hasattr(ctx.author, "roles"):
            has_role = any(r.id in get_allowed_roles() for r in ctx.author.roles)
        else:
            has_role = False
            
        if not has_role and ctx.author.id != ID_FONDATEUR:
            return await ctx.send("Permissions insuffisantes.", ephemeral=True)

        thread = await self.get_or_create_thread(user)
        sent = await self.send_global_logic(ctx.author, user, message, ctx.message.attachments, thread, mirror_in_thread=True)

        if sent:
            log_channel = self.bot.get_channel(LOG_CHANNEL_ID)

            try:
                guild = self.bot.get_guild(GUILD_ID)
                staff_member = await guild.fetch_member(ctx.author.id) if guild else None
                staff_display = staff_member.display_name if staff_member else ctx.author.name
                # Toujours essayer d'obtenir le display_name serveur pour la cible
                user_member = await guild.fetch_member(user.id) if guild else None
                if user_member:
                    user_display = user_member.display_name
                else:
                    user_display = user.name
            except Exception:
                staff_display = ctx.author.name
                user_display = user.name

            staff_display = staff_display[:1].upper() + staff_display[1:]
            user_display = user_display[:1].upper() + user_display[1:]
            thread_url = thread.jump_url if thread else ""

            embed_color = 0x9B59B6  # Violet Discord
            embed = discord.Embed(color=embed_color)
            embed.description = f" {staff_display} a contacté [{user_display}]({thread_url}) avec la commande mp"
            now = datetime.now().strftime("%d/%m/%Y %H:%M")
            embed.set_footer(text=f"{now} - {user.id}")

            await log_channel.send(embed=embed)
            await ctx.send("", ephemeral=True)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        # Ignore les réactions du bot lui-même
        if user.bot:
            return
        # On ne traite que la réaction 🟢 dans un thread du log
        if str(reaction.emoji) != "✅":
            return
        message = reaction.message
        thread = message.channel
        # Vérifie que c'est bien un thread lié au log
        if not isinstance(thread, discord.Thread) or thread.parent_id != LOG_CHANNEL_ID:
            return
        # Récupère l'ID utilisateur cible à partir du nom du thread
        match = re.search(r'\d+', thread.name)
        if not match:
            return
        u_id = int(match.group())
        # Passe tous les logs "🔴 Message de ..." pour cet utilisateur en vert (ID dans le footer, format: date - ID)
        log_channel = self.bot.get_channel(LOG_CHANNEL_ID)
        async for log_msg in log_channel.history(limit=100):
            if log_msg.embeds:
                embed = log_msg.embeds[0]
                footer = embed.footer.text if embed.footer else ""
                # On extrait l'ID à la fin du footer (format: date - ID)
                id_in_footer = footer.split('-')[-1].strip() if '-' in footer else footer.strip()
                if (
                    embed.description and 
                    embed.description.startswith("🔴 Message de ") and 
                    id_in_footer == str(u_id)
                ):
                    new_embed = embed.copy()
                    new_embed.description = new_embed.description.replace("🔴", "🟢", 1)
                    new_embed.color = 0x57F287  # Vert Discord
                    await log_msg.edit(embed=new_embed)
        # Supprime toutes les réactions 🟢 sur les messages du bot et de l'équipe modération dans le thread
        async for msg in thread.history(limit=100):
            if msg.author.bot or any(r.id in ALLOWED_ROLES for r in getattr(msg.author, 'roles', [])):
                try:
                    for react in msg.reactions:
                        if str(react.emoji) == "✅":
                            async for u in react.users():
                                await msg.remove_reaction("✅", u)
                except Exception:
                    pass

async def setup(bot: commands.Bot):
    await bot.add_cog(DevMessaging(bot))