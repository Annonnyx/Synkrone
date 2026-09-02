import discord

from discord.ext import commands

import time

import asyncio

import traceback

from . import logserver



class VocalLog(commands.Cog):

    def __init__(self, bot):

        self.bot = bot

        self.tracking = {}



    # ──────────────────────────────────────────────

    # Utils

    # ──────────────────────────────────────────────



    def get_log_channel(self, guild):
        # Récupère le canal de logs vocaux depuis la configuration
        main_cog = self.bot.get_cog("LogSystem")
        if not main_cog:
            return None
            
        config = main_cog.get_config(guild.id)
        channel_id = config.get("log_vocal")
        
        if not channel_id:
            return None
            
        channel = guild.get_channel(channel_id)
        if not channel:
            return channel
            
        return channel



    def get_duration(self, member_id, key):

        start_time = self.tracking.get(member_id, {}).pop(key, None)

        if not start_time:

            return "Indisponible"



        delta = int(time.time() - start_time)

        h, r = divmod(delta, 3600)

        m, s = divmod(r, 60)

        return f"{h}h {m}m {s}s" if h > 0 else f"{m}m {s}s"



    async def get_voice_responsable(self, guild, member_id, was_kick=False):

        """Recherche le responsable pour les déplacements et expulsions"""

        try:

            async for entry in guild.audit_logs(limit=10, action=discord.AuditLogAction.member_move):

                diff = (discord.utils.utcnow() - entry.created_at).total_seconds()

                if diff > 15: continue

                if not entry.extra: continue

               

                members = getattr(entry.extra, "members", [])

                channel_id = getattr(entry.extra, "channel_id", None)

                if member_id not in [m.id for m in members]: continue



                if was_kick and channel_id is None: return entry.user

                if not was_kick and channel_id is not None: return entry.user

        except Exception: pass

        return None



    async def get_generic_responsable(self, guild, member_id, action_type):

        """Recherche le responsable pour les Mutes et Sourdines Serveur"""

        try:

            async for entry in guild.audit_logs(limit=10, action=action_type):

                if entry.target and entry.target.id == member_id:

                    diff = (discord.utils.utcnow() - entry.created_at).total_seconds()

                    if diff < 15:

                        return entry.user

        except Exception: pass

        return None



    # ──────────────────────────────────────────────

    # Envoi des logs

    # ──────────────────────────────────────────────



    async def send_vax_log(self, guild, member, title, details, color, performer=None):
        try:
            channel = self.get_log_channel(guild)
            if not channel: 
                return

            is_mod_action = performer is not None
            if is_mod_action:
                title = f"Modération - {title}"
                display_user = performer
                thumb = guild.icon.url if guild and guild.icon else None
            else:
                display_user = member
                thumb = member.display_avatar.url if member and hasattr(member, 'display_avatar') and member.display_avatar else None

            # Utilisation de la fonction create_embed de logserver
            from .logserver import create_embed
            
            # Construction de la description complète
            full_description = f"{title}\n{details}"
            
            # Création de l'embed avec la fonction centralisée
            embed = await create_embed(
                guild=guild,
                user=display_user,
                bot=self.bot,
                title=title,
                description=details,
                color=color
            )

            # Configuration de la miniature
            if thumb:
                try:
                    embed.set_thumbnail(url=thumb)
                except Exception as e:
                    print(f"❌ Erreur lors de l'ajout de la miniature: {str(e)}")

            # Ajout des champs additionnels pour les actions de modération (Move/Kick)
            if is_mod_action:
                try:
                    v_mod = "`Aucun`"
                    if performer and hasattr(performer, 'voice') and performer.voice and performer.voice.channel:
                        v_mod = performer.voice.channel.mention
                    
                    v_target = "`Déconnecté`"
                    if member and hasattr(member, 'voice') and member.voice and member.voice.channel:
                        v_target = member.voice.channel.mention
                    
                    embed.add_field(name="👮 Responsable", value=f"{performer.mention if performer else 'Inconnu'}\nSalon : {v_mod}", inline=True)
                    embed.add_field(name="👤 Cible", value=f"{member.mention if member else 'Inconnu'}\nSalon : {v_target}", inline=True)
                except Exception as e:
                    print(f"❌ Erreur lors de l'ajout des champs de modération: {str(e)}")

            # Envoi du message
            try:
                await channel.send(embed=embed)
            except Exception as e:
                print(f"❌ Erreur lors de l'envoi du message de log vocal: {str(e)}")
                
        except Exception as e:
            print(f"❌ Erreur critique dans send_vax_log: {str(e)}\n{traceback.format_exc()}")

    # ──────────────────────────────────────────────

    # Listener principal

    # ──────────────────────────────────────────────



    @commands.Cog.listener()

    async def on_voice_state_update(self, member, before, after):

        guild = member.guild

        self.tracking.setdefault(member.id, {})



        # ────── MOUVEMENTS VOCAUX ──────

        if before.channel != after.channel:

            if before.channel is None:

                self.tracking[member.id]["join"] = time.time()

                await self.send_vax_log(guild, member, "Connexion Vocal", f"**{member.mention}** a rejoint {after.channel.mention}", 0x43b581)



            elif after.channel is None:

                duration = self.get_duration(member.id, "join")

                await asyncio.sleep(0.8)

                performer = await self.get_voice_responsable(guild, member.id, was_kick=True)

                await self.send_vax_log(guild, member, "Expulsion" if performer else "Déconnexion",

                    f"**{member.mention}** a {'été déconnecté' if performer else 'quitté'} {before.channel.mention}\n> ⏱️ Temps resté : `{duration}`",

                    0xff4757 if performer else 0x95a5a6, performer)



            else:

                duration = self.get_duration(member.id, "join")

                self.tracking[member.id]["join"] = time.time()

                await asyncio.sleep(0.8)

                performer = await self.get_voice_responsable(guild, member.id, was_kick=False)

                await self.send_vax_log(guild, member, "Déplacement" if performer else "Changement de salon",

                    f"**{member.mention}** a {'été déplacé' if performer else 'changé de salon'}.\n> ⬅️ De : {before.channel.mention}\n> ➡️ Vers : {after.channel.mention}",

                    0x7289da if performer else 0x3498db, performer)



        # ────── MUTE / SOURDINE SERVEUR (RECHERCHE DU MODÉRATEUR) ──────

        if before.deaf != after.deaf:

            await asyncio.sleep(0.8)

            performer = await self.get_generic_responsable(guild, member.id, discord.AuditLogAction.member_update)

            act = 'activée' if after.deaf else 'retirée'

            await self.send_vax_log(guild, member, "🔇 Sourdine Serveur", f"La sourdine serveur de **{member.mention}** a été {act}.", 0xe67e22, performer)



        elif before.mute != after.mute:

            await asyncio.sleep(0.8)

            performer = await self.get_generic_responsable(guild, member.id, discord.AuditLogAction.member_update)

            act = 'coupé' if after.mute else 'rétabli'

            await self.send_vax_log(guild, member, "🤐 Mute Serveur", f"Le micro serveur de **{member.mention}** a été {act}.", 0xe67e22, performer)

       

        # ────── CAMÉRA ──────

        if before.self_video != after.self_video:

            if after.self_video:

                # On stocke l'heure de début pour calculer la durée plus tard

                self.tracking[member.id]["camera"] = time.time()

                await self.send_vax_log(guild, member, "📹 Caméra", f"**{member.mention}** a allumé sa caméra.", 0x9b59b6)

            else:

                # On récupère la durée via la fonction get_duration

                dur = self.get_duration(member.id, "camera")

                await self.send_vax_log(guild, member, "📹 Caméra", f"**{member.mention}** a éteint sa caméra.\n> ⏱️ Durée : `{dur}`", 0x8e44ad)



        # ────── STREAM (Partage d'écran) ──────

        if before.self_stream != after.self_stream:

            if after.self_stream:

                self.tracking[member.id]["stream"] = time.time()

                await self.send_vax_log(guild, member, "🖥️ Stream", f"**{member.mention}** a lancé un partage d'écran.", 0x34495e)

            else:

                dur = self.get_duration(member.id, "stream")

                await self.send_vax_log(guild, member, "🖥️ Stream", f"**{member.mention}** a arrêté son stream.\n> ⏱️ Durée : `{dur}`", 0x2c3e50)



        # ────── ÉTATS PERSONNELS (INSTANTANÉ) ──────

        elif before.self_deaf != after.self_deaf:

            act = 'activé' if after.self_deaf else 'retiré'

            await self.send_vax_log(guild, member, "👂 Sourdine", f"**{member.mention}** a {act} sa sourdine.", 0x7f8c8d)



        elif before.self_mute != after.self_mute:

            act = 'coupé' if after.self_mute else 'activé'

            await self.send_vax_log(guild, member, "🎙️ Micro", f"**{member.mention}** a {act} son micro.", 0x7f8c8d)



async def setup(bot):
    try:
        cog = VocalLog(bot)
        await bot.add_cog(cog)
        # VocalLog chargé silencieusement
        return True
    except Exception as e:
        print(f"❌ Erreur lors du chargement de VocalLog: {str(e)}")
        import traceback
        traceback.print_exc()
        return False