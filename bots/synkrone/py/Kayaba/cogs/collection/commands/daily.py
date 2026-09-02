import discord
from discord.ext import commands
import json
import os
import random
from pathlib import Path
from datetime import datetime, timedelta

# ==========================================
# CONFIGURATION DAILY
# ==========================================

# Avantages classiques (utilisateur normal)
DAILY_SLOTS_MIN = 1
DAILY_SLOTS_MAX = 5
DAILY_COL_MIN = 1
DAILY_COL_MAX = 50000

# Avantages premium (multiplicateurs)
PREMIUM_MULTIPLIER = 3
PREMIUM_SLOTS_MIN = 3
PREMIUM_SLOTS_MAX = 20
PREMIUM_COL_MIN = 10000
PREMIUM_COL_MAX = 150000

# Importer config_manager
try:
    from cogs.developpeur.commands.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# Importer premium pour vérifier le statut
try:
    from cogs.collection.commands.premium import premium_manager
except ImportError:
    premium_manager = None

# Importer MPManager pour les notifications
try:
    from cogs.collection.commands.mp import MPManager
except ImportError:
    MPManager = None


class Daily(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_dir = Path("cogs/collection/data/interserver")
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def get_user_data(self, user_id: int):
        """Récupère les données utilisateur depuis le JSON"""
        file_path = self.data_dir / f"{user_id}.json"
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None
    
    def update_user_data(self, user_id: int, data: dict):
        """Met à jour les données utilisateur dans le JSON"""
        file_path = self.data_dir / f"{user_id}.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
    
    def get_daily_multiplier(self, user_id: int) -> int:
        """Retourne le multiplicateur daily selon le statut premium"""
        if premium_manager and premium_manager.is_premium(user_id):
            return 3  # Premium : x3
        return 1  # Normal : x1
    
    @commands.hybrid_command(name="daily", description="Récupère votre récompense quotidienne")
    async def daily(self, ctx: commands.Context):
        """Récupère votre récompense quotidienne de slots et de Col"""
        user_id = ctx.author.id
        user_data = self.get_user_data(user_id)
        
        if not user_data:
            await ctx.send("Profil créé, vous pouvez refaire `.daily` !")
            return
        
        # 1. Vérifier si 24h se sont écoulées
        last_daily = user_data.get('last_daily')
        now = datetime.now()
        
        if last_daily:
            try:
                last_daily_date = datetime.fromisoformat(last_daily)
                time_elapsed = now - last_daily_date
                
                # Si moins de 24h se sont écoulées
                if time_elapsed < timedelta(hours=24):
                    time_remaining = timedelta(hours=24) - time_elapsed
                    hours = int(time_remaining.total_seconds() // 3600)
                    minutes = int((time_remaining.total_seconds() % 3600) // 60)
                    
                    description = f"Vous devez attendre **24h** entre chaque récompense !\n\n**Prochaine récompense dans :** `{hours}h {minutes}min`"
                    
                    if config_manager:
                        try:
                            embed = config_manager.get_formatted_embed(
                                ctx.guild, ctx.author, self.bot,
                                title="Récompense Quotidienne",
                                target_id=ctx.guild.id if ctx.guild else None
                            )
                            embed.description = description
                            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
                        except Exception:
                            embed = discord.Embed(title="Récompense Quotidienne", description=description, color=0x2b2d31)
                            embed.set_footer(text="Système Kayaba Collection")
                    else:
                        embed = discord.Embed(title="Récompense Quotidienne", description=description, color=0xf1c40f)
                        embed.set_footer(text="Cooldown quotidien")
                    
                    await ctx.send(embed=embed, ephemeral=True)
                    return
            except (ValueError, TypeError):
                pass
        
        # 2. Charger les Emojis (Déplacé ICI pour éviter le NameError)
        try:
            emoji_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'emoji.json')
            with open(emoji_path, 'r', encoding='utf-8') as f:
                emojis = json.load(f)
        except Exception:
            emojis = {
                'tirage': '�',
                'col': '💰',
                'star': '⭐'
            }

        # 3. Obtenir le multiplicateur et générer les récompenses
        multiplier = self.get_daily_multiplier(user_id)
        is_premium = multiplier > 1
        
        if multiplier == PREMIUM_MULTIPLIER:
            slots_gained = random.randint(PREMIUM_SLOTS_MIN, PREMIUM_SLOTS_MAX)
            col_gained = random.randint(PREMIUM_COL_MIN, PREMIUM_COL_MAX)
        else:
            slots_gained = random.randint(DAILY_SLOTS_MIN, DAILY_SLOTS_MAX)
            col_gained = random.randint(DAILY_COL_MIN, DAILY_COL_MAX)
        
        # 4. Mettre à jour les données utilisateur
        user_data['slots'] = user_data.get('slots', 0) + slots_gained
        user_data['col'] = user_data.get('col', 0) + col_gained
        user_data['last_daily'] = now.isoformat()
        
        self.update_user_data(user_id, user_data)
        
        # 5. Créer l'embed de récompense
        formatted_col = f"{col_gained:,}".replace(",", " ")
        description = f"**+ `{slots_gained}` tirages** {emojis['tirage']}\n"
        description += f"**+ `{formatted_col}` Col** {emojis['col']}"

        if config_manager:
            try:
                embed = config_manager.get_formatted_embed(
                    ctx.guild, ctx.author, self.bot,
                    title="Récompense Quotidienne",
                    target_id=ctx.guild.id if ctx.guild else None
                )
                embed.description = description
                embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            except Exception:
                embed = discord.Embed(title="Récompense Quotidienne", description=description, color=0x2b2d31)
                embed.set_thumbnail(url=self.bot.user.display_avatar.url)
                embed.set_footer(text="Système Kayaba Collection")
        else:
            embed = discord.Embed(title="Récompense Quotidienne", description=description, color=0x2ecc71)
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            embed.set_footer(text="Système Kayaba Collection")
            
        if is_premium:
            embed.set_author(name="Membre Premium", icon_url=ctx.author.display_avatar.url)
        
        # 6. Envoyer la récompense
        await ctx.send(embed=embed)
        
        # 7. Envoyer une notification MP si activé
        if MPManager and MPManager.get_mp_preference(user_id):
            try:
                message = f"**[DAILY]** Vous avez gagné `{slots_gained}` **tirages** {emojis['tirage']} & `{formatted_col}` **Col** {emojis['col']}"
                await ctx.author.send(message)
            except discord.Forbidden:
                pass
            except Exception:
                pass

async def setup(bot):
    await bot.add_cog(Daily(bot))