# ==============================================================================
# Nom du fichier : auto_pin_ticket.py
# Description : Épingle le 1er message généré par un Cog dans la catégorie Ticket
# ==============================================================================

import discord
import asyncio
from discord.ext import commands

# ==============================================================================
# ----------------------- CONFIGURATION DES IDs --------------------------------
# ==============================================================================
GUILD_TARGET_ID = 1518305648918401184 
CATEGORY_TICKETS_ID = 1518311378966937651

class AutoPinTicketCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # 1. Ignorer les messages privés (DMs)
        if not message.guild:
            return

        # 2. Sécurité : Vérifier le serveur
        if message.guild.id != GUILD_TARGET_ID:
            return

        # 3. Vérifier qu'on est dans un salon textuel et dans la bonne catégorie
        if not isinstance(message.channel, discord.TextChannel):
            return
            
        if message.channel.category_id != CATEGORY_TICKETS_ID:
            return

        # 4. Ignorer les messages systèmes natifs (pour éviter une boucle)
        if message.is_system():
            return

        # 5. Détecter si c'est le 1er message du salon (celui généré par ton autre Cog)
        # On charge les 2 derniers messages. S'il n'y en a qu'un, c'est le tout premier.
        history = [msg async for msg in message.channel.history(limit=2)]
        
        if len(history) == 1:
            try:
                # Épingler le message
                await message.pin(reason="Système Auto-Pin : Premier message du ticket")
                
                # Attendre 1 seconde pour laisser le temps à Discord de générer 
                # la notification "Un tel a épinglé un message."
                await asyncio.sleep(1)
                
                # Chercher et supprimer le message système disgracieux
                async for msg in message.channel.history(limit=5):
                    if msg.type == discord.MessageType.pins_add:
                        await msg.delete()
                        break
                        
            except discord.Forbidden:
                print(f"[ERREUR Auto-Pin] Permissions manquantes ('Gérer les messages') dans le salon : {message.channel.name}")
            except discord.HTTPException as e:
                print(f"[ERREUR Auto-Pin] Erreur de l'API Discord : {e}")
            except Exception as e:
                print(f"[ERREUR Auto-Pin] Erreur inattendue : {e}")

async def setup(bot: commands.Bot):
    await bot.add_cog(AutoPinTicketCog(bot))