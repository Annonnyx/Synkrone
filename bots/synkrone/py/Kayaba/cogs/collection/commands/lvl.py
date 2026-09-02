import json
import discord
from discord.ext import commands

class LevelSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.level_data = self.load_level_system()
        self.user_data = self.load_user_data()
        self.last_checked_levels = {}  # Stocker les derniers niveaux vérifiés
        
        # Démarrer la tâche de vérification périodique
        self.bot.loop.create_task(self.check_level_changes_periodically())
    
    def load_level_system(self):
        """Charge le système de niveaux depuis level_system.json"""
        try:
            with open('cogs/collection/data/level_system.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print("Erreur: level_system.json introuvable")
            return {}
        except json.JSONDecodeError:
            print("Erreur: level_system.json mal formaté")
            return {}
    
    def load_user_data(self):
        """Charge les données utilisateurs depuis les fichiers dans interserver"""
        import os
        user_data = {}
        interserver_dir = 'cogs/collection/data/interserver'
        
        try:
            if os.path.exists(interserver_dir):
                for filename in os.listdir(interserver_dir):
                    if filename.endswith('.json') and filename != 'shop.json':
                        user_id = filename.replace('.json', '')
                        try:
                            with open(os.path.join(interserver_dir, filename), 'r', encoding='utf-8') as f:
                                content = f.read()
                                if not content.strip():  # Vérifier si le fichier n'est pas vide
                                    print(f"Fichier vide pour l'utilisateur {user_id}")
                                    continue
                                
                                data = json.loads(content)
                                if isinstance(data, dict):
                                    user_data[user_id] = data
                                else:
                                    print(f"Format invalide dans le fichier {filename}")
                        except json.JSONDecodeError as e:
                            print(f"Erreur JSON dans le fichier {filename}: {e}")
                        except Exception as e:
                            print(f"Erreur lors du chargement du fichier {filename}: {e}")
                            import traceback
                            traceback.print_exc()
            else:
                print(f"Dossier {interserver_dir} introuvable")
            return user_data
        except Exception as e:
            print(f"Erreur lors du chargement des données utilisateur: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    def save_user_data(self):
        """Sauvegarde les données utilisateurs dans les fichiers individuels"""
        import os
        interserver_dir = 'cogs/collection/data/interserver'
        
        try:
            # Créer le dossier s'il n'existe pas
            if not os.path.exists(interserver_dir):
                os.makedirs(interserver_dir)
            
            # Sauvegarder chaque utilisateur dans son fichier
            for user_id, data in self.user_data.items():
                filename = f"{user_id}.json"
                filepath = os.path.join(interserver_dir, filename)
                
                try:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                except Exception as e:
                    print(f"Erreur lors de la sauvegarde du fichier {filename}: {e}")
                    
        except Exception as e:
            print(f"Erreur lors de la sauvegarde des données utilisateur: {e}")
    
    def save_single_user(self, user_id_str):
        """Sauvegarde les données d'un seul utilisateur"""
        import os
        interserver_dir = 'cogs/collection/data/interserver'
        
        try:
            # Créer le dossier s'il n'existe pas
            if not os.path.exists(interserver_dir):
                os.makedirs(interserver_dir)
            
            # Sauvegarder uniquement cet utilisateur
            filename = f"{user_id_str}.json"
            filepath = os.path.join(interserver_dir, filename)
            
            # Validation des données avant sauvegarde
            if user_id_str not in self.user_data:
                print(f"Erreur: utilisateur {user_id_str} non trouvé dans user_data")
                return
            
            data_to_save = self.user_data[user_id_str]
            if not isinstance(data_to_save, dict):
                print(f"Erreur: données invalides pour l'utilisateur {user_id_str}")
                return
            
            # Sauvegarde avec encodage UTF-8
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=2, ensure_ascii=False)
                
            print(f"Sauvegarde réussie pour l'utilisateur {user_id_str}")
                
        except Exception as e:
            print(f"Erreur lors de la sauvegarde du fichier {filename}: {e}")
            import traceback
            traceback.print_exc()
    
    def get_user_level(self, user_id):
        """Récupère le niveau actuel d'un utilisateur"""
        user_id_str = str(user_id)
        if user_id_str not in self.user_data:
            return 1
        
        xp = self.user_data[user_id_str].get('xp', 0)
        return self.calculate_level_from_xp(xp)
    
    def calculate_level_from_xp(self, xp):
        """Calcule le niveau à partir de l'XP"""
        levels = self.level_data.get('levels', {})
        if not levels:
            return 1
        
        # Trouver le niveau le plus élevé avec XP requis <= XP actuel
        current_level = 1
        for level_str, required_xp in levels.items():
            level = int(level_str)
            if xp >= required_xp and level > current_level:
                current_level = level
        
        return current_level
    
    async def check_level_up(self, user_id, new_xp):
        """Vérifie si l'utilisateur a passé un niveau et envoie un message"""
        user_id_str = str(user_id)
        
        # Récupérer l'ancien niveau
        old_xp = self.user_data.get(user_id_str, {}).get('xp', 0)
        old_level = self.calculate_level_from_xp(old_xp)
        
        # Mettre à jour uniquement l'XP sans écraser les autres données
        if user_id_str not in self.user_data:
            self.user_data[user_id_str] = {}
        
        # Préserver toutes les données existantes et ne mettre à jour que l'XP
        existing_data = self.user_data[user_id_str]
        existing_data['xp'] = new_xp
        self.user_data[user_id_str] = existing_data
        
        # Calculer le nouveau niveau
        new_level = self.calculate_level_from_xp(new_xp)
        
        # Debug : afficher les informations de level up
        print(f"[DEBUG] Level up check - User: {user_id_str}, Old XP: {old_xp}, New XP: {new_xp}, Old Level: {old_level}, New Level: {new_level}")
        
        # Vérifier si level up
        if new_level > old_level:
            print(f"[DEBUG] LEVEL UP DETECTED! User {user_id_str} passed from level {old_level} to {new_level}")
            await self.send_level_up_message(user_id, old_level, new_level)
        else:
            print(f"[DEBUG] No level up - User {user_id_str} stays at level {new_level}")
        
        # Sauvegarder uniquement cet utilisateur
        self.save_single_user(user_id_str)
        
        return new_level
    
    async def send_level_up_message(self, user_id, old_level, new_level):
        """Envoie un message privé de level up"""
        try:
            user = await self.bot.fetch_user(user_id)
            if user:
                message = f"**[LEVELUP]** Vous venez de passer niveau `{new_level}` !"
                await user.send(message)
                print(f"Message de level up envoyé à l'utilisateur {user_id} (Level {old_level} → {new_level})")
            else:
                print(f"Impossible de trouver l'utilisateur {user_id}")
        except discord.Forbidden:
            print(f"L'utilisateur {user_id} a désactivé les messages privés")
        except Exception as e:
            print(f"Erreur lors de l'envoi du message de level up: {e}")
    
    async def check_level_changes_periodically(self):
        """Vérifie périodiquement les changements de niveau dans les fichiers JSON"""
        import asyncio
        
        while True:
            try:
                # Recharger les données utilisateur depuis les fichiers
                await self.reload_user_data()
                
                # Vérifier chaque utilisateur pour les changements de niveau
                for user_id_str, user_data in self.user_data.items():
                    if 'xp' in user_data:
                        current_xp = user_data['xp']
                        current_level = self.calculate_level_from_xp(current_xp)
                        
                        # Vérifier si c'est un nouvel utilisateur ou si le niveau a changé
                        if user_id_str not in self.last_checked_levels:
                            self.last_checked_levels[user_id_str] = current_level
                        elif self.last_checked_levels[user_id_str] != current_level:
                            old_level = self.last_checked_levels[user_id_str]
                            self.last_checked_levels[user_id_str] = current_level
                            
                            # Envoyer le message de level up
                            print(f"[AUTO-LEVELUP] User {user_id_str}: {old_level} → {current_level}")
                            await self.send_level_up_message(int(user_id_str), old_level, current_level)
                
                # Attendre 30 secondes avant la prochaine vérification
                await asyncio.sleep(30)
                
            except Exception as e:
                print(f"Erreur dans la vérification périodique: {e}")
                await asyncio.sleep(60)  # Attendre 1 minute en cas d'erreur
    
    async def reload_user_data(self):
        """Recharge les données utilisateur depuis les fichiers"""
        self.user_data = self.load_user_data()

async def setup(bot):
    await bot.add_cog(LevelSystem(bot))
