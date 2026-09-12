
import os
from dotenv import load_dotenv
load_dotenv()
import logging
import sys
sys.dont_write_bytecode = True
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import datetime
import json
import subprocess
import importlib.util
import asyncio
from typing import List, Optional

# ==============================================================================
# 1. GESTION DES DÉPENDANCES (REQUIREMENTS)
# ==============================================================================

def is_package_installed(package_name: str) -> bool:
    """Vérifie si un package est installé"""
    return importlib.util.find_spec(package_name) is not None

def get_requirements() -> List[str]:
    """Récupère la liste des dépendances depuis requirements.txt"""
    try:
        with open('requirements.txt', 'r') as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except FileNotFoundError:
        return []

def install_requirements() -> bool:
    """Installe les dépendances manquantes"""
    requirements = get_requirements()
    if not requirements:
        return True
    
    missing_deps = [dep for dep in requirements if not is_package_installed(dep.split('>=')[0].split('==')[0].strip())]
    
    if not missing_deps:
        return True
    
    print(f"\033[94m[ℹ] Installation de {len(missing_deps)} dépendance(s) manquante(s)...\033[0m")
    
    import time
    import threading
    
    progress_data = {'current': 0, 'total': len(missing_deps), 'running': True}
    
    def update_progress():
        while progress_data['running']:
            curr, tot = progress_data['current'], progress_data['total']
            if tot > 0:
                percent = (curr / tot) * 100
                sys.stdout.write(f"\r\033[94m[ℹ] Progression : [{curr}/{tot}] {percent:.1f}%\033[0m")
                sys.stdout.flush()
            if curr >= tot: break
            time.sleep(0.5)

    thread = threading.Thread(target=update_progress, daemon=True)
    thread.start()

    success_count = 0
    for i, dep in enumerate(missing_deps, 1):
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", dep], capture_output=True, check=True)
            success_count += 1
        except: pass
        progress_data['current'] = i
    
    progress_data['running'] = False
    thread.join(timeout=1)
    print("\n")
    return success_count == len(missing_deps)

# Exécution de l'installation avant d'importer Discord
if not install_requirements():
    sys.exit(1)

# ==============================================================================
# 2. CONFIGURATION DU LOGGER ET DE DISCORD
# ==============================================================================


import discord
from discord.ext import commands
# Importe la fonction d'init owner (chemin relatif au projet)
try:
    from cogs.addons.owner.owner import ensure_owner_file_exists
except ImportError:
    ensure_owner_file_exists = None

class CustomFormatter(logging.Formatter):
    def format(self, record):
        now = datetime.datetime.now()
        BLUE, YELLOW, GRAY, RESET = '\033[94m', '\033[93m', '\033[90m', '\033[0m'
        timestamp = now.strftime(f'{GRAY}[%d/%m/%y]{RESET} {YELLOW}%H:%M:%S{RESET}')
        record.msg = f"{timestamp} {BLUE}[MAIN]{RESET} {record.msg}"
        return super().format(record)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(CustomFormatter('%(message)s'))
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(handler)

def custom_print(*args, **kwargs):
    logging.info(' '.join(str(arg) for arg in args), **kwargs)

print = custom_print

# Silence les logs inutiles
logging.getLogger('discord').setLevel(logging.CRITICAL)
logging.getLogger('asyncio').setLevel(logging.CRITICAL)

# Configuration initiale
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
DEFAULT_PREFIX = os.getenv("PREFIX", "!")

intents = discord.Intents.all()  # Active tous les intents pour le développement

# ==============================================================================
# 3. CHARGEMENT DES COGS (FILTRE MODIFIÉ)
# ==============================================================================

COGS_ERRORS = []  # Liste globale pour stocker les erreurs de cogs

async def load_cogs():
    """Charge les cogs en ignorant les scripts util_*.py mais pas les dossiers utilitaires"""
    global COGS_TOTAL, COGS_LOADED, COGS_ERRORS_COUNT
    total_cogs = 0
    loaded_cogs = 0
    error_cogs = 0

    # Fichiers à ignorer strictement
    ignored_exact_files = ['__init__.py', 'utils.py', 'util_embed.py']

    YELLOW, GREEN, RED, BLUE, RESET = '\033[93m', '\033[92m', '\033[91m', '\033[94m', '\033[0m'

    print(f"{BLUE}[ℹ] Analyse et chargement des cogs...{RESET}")

    global COGS_ERRORS
    COGS_ERRORS.clear()

    for root, dirs, files in os.walk('./cogs'):
        dirs[:] = [d for d in dirs if not d.startswith('__')]
        for filename in files:
            if (
                filename.endswith('.py')
                and not filename.startswith('__')
                and not filename.startswith('util_')
                and filename not in ignored_exact_files
            ):
                rel_path = os.path.relpath(os.path.join(root, filename), './cogs')
                cog_path = 'cogs.' + rel_path.replace('\\', '.').replace('/', '.')[:-3]
                total_cogs += 1
                try:
                    await bot.load_extension(cog_path)
                    loaded_cogs += 1
                    print(f"{GREEN}[✓] Cog chargé : {cog_path}{RESET}")
                except Exception as e:
                    error_cogs += 1
                    print(f"{YELLOW}[!] Erreur lors du chargement de {cog_path}: {e}{RESET}")
                    # Ajoute l'erreur formatée pour l'embed
                    COGS_ERRORS.append((cog_path, str(e)))

    print(f"\n{BLUE}=== Résumé du chargement ==={RESET}")
    print(f"{GREEN}✓ {loaded_cogs} chargé(s){RESET} | {RED}⚠ {error_cogs} erreur(s){RESET}")
    print(f"{BLUE}============================{RESET}\n")

    # Stocke les stats globales pour l'embed
    COGS_TOTAL = total_cogs
    COGS_LOADED = loaded_cogs
    COGS_ERRORS_COUNT = error_cogs

# ==============================================================================
# 4. SYSTÈME DE PRÉFIXES
# ==============================================================================
# Priorité de résolution du préfixe pour chaque commande :
#   1. Préfixes du serveur (module prefix.py) :
#        - disable_global=True  → seuls les préfixes du serveur sont actifs
#        - disable_global=False → préfixes du serveur + préfixe global
#   2. Préfixe global si aucun préfixe de serveur :
#        a. Cog BotAdmin en mémoire (panelbot, mis à jour sans redémarrage)
#        b. bot_config.json (panelbot, valeur persistée)
#        c. PREFIX dans .env (valeur par défaut au démarrage)

# Chemins utilisés par le système de préfixes
_PREFIX_DATA_DIR    = os.path.join('cogs', 'addons', 'prefix', 'data')
_PANELBOT_CFG_PATH  = os.path.join('cogs', 'owner', 'commands', 'panelbot', 'bot_config.json')

def _get_global_prefix() -> str:
    """Retourne le préfixe global actif : BotAdmin en mémoire → bot_config.json → .env"""
    # 1. Préfixe en mémoire du Cog BotAdmin (changé via panelbot sans redémarrage)
    try:
        cog = bot.cogs.get('BotAdmin')
        if cog and hasattr(cog, 'default_prefix'):
            return cog.default_prefix
    except Exception:
        pass
    # 2. Fichier de configuration panelbot
    if os.path.exists(_PANELBOT_CFG_PATH):
        try:
            with open(_PANELBOT_CFG_PATH, 'r', encoding='utf-8') as f:
                prefix = json.load(f).get('prefix')
                if prefix:
                    return prefix
        except Exception:
            pass
    # 3. Valeur par défaut (.env)
    return DEFAULT_PREFIX

def get_prefix(bot, message):
    """
    Résout le ou les préfixes valides pour un message donné.

    Règles (par priorité) :
      1. Si le module prefix.py a configuré des préfixes sur ce serveur :
           - disable_global=True  → seuls les préfixes du serveur s'appliquent
                                    (le préfixe global est ignoré)
           - disable_global=False → préfixes du serveur + préfixe global
      2. Sinon → préfixe global (BotAdmin en mémoire > bot_config.json > .env)
    """
    if message.guild:
        prefix_file = os.path.join(_PREFIX_DATA_DIR, f'{message.guild.id}.json')
        if os.path.exists(prefix_file):
            try:
                with open(prefix_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                server_prefixes = data.get('prefixes', [])
                disable_global  = data.get('disable_global', False)

                if disable_global:
                    # Préfixe global désactivé → uniquement les préfixes du serveur
                    # '\x00' si aucun préfixe défini (aucune commande préfixée ne répond)
                    return server_prefixes if server_prefixes else ['\x00']

                if server_prefixes:
                    # Préfixes du serveur + préfixe global (sans doublon)
                    global_prefix = _get_global_prefix()
                    combined = list(server_prefixes)
                    if global_prefix not in combined:
                        combined.append(global_prefix)
                    return combined
            except Exception:
                pass

    # Aucun préfixe de serveur → préfixe global
    return [_get_global_prefix()]

# ==============================================================================
# 5. LANCEMENT DU BOT
# ==============================================================================

# Classe Bot personnalisée pour que toutes les commandes répondent par défaut avec reply()
class ReplyBot(commands.Bot):
    async def get_context(self, message, *, cls=commands.Context):
        # Récupérer le contexte normalement
        ctx = await super().get_context(message, cls=cls)
        
        # Si c'est une commande, surcharger la méthode send pour utiliser reply par défaut
        if ctx.command:
            original_send = ctx.send

            async def reply_send(content=None, **kwargs):
                # Si mention=True n'est pas spécifié et que ce n'est pas déjà une réponse, utiliser reply
                if 'reference' not in kwargs and 'mention' not in kwargs:
                    # Vérifie si message a bien la méthode reply (donc c'est un Message, pas une Interaction)
                    if hasattr(message, "reply") and callable(getattr(message, "reply", None)):
                        try:
                            return await message.reply(content, **kwargs)
                        except discord.HTTPException:
                            # Fallback vers send si reply échoue
                            return await original_send(content, **kwargs)
                        except Exception:
                            # Fallback général
                            return await original_send(content, **kwargs)
                    else:
                        # Si ce n'est pas un message classique, fallback direct
                        return await original_send(content, **kwargs)
                else:
                    return await original_send(content, **kwargs)

            ctx.send = reply_send
        
        return ctx

bot = ReplyBot(command_prefix=get_prefix, intents=intents)
bot.help_command = None  # Désactive l'aide par défaut



@bot.event
async def on_ready():
    if ensure_owner_file_exists:
        ensure_owner_file_exists()
    print(f'\033[92m🤖 Connecté en tant que {bot.user.name}\033[0m')
    print('\033[94m' + '─' * 60 + '\033[0m')

    try:
        synced = await bot.tree.sync()
        print(f'\033[92m[✓] {len(synced)} commande(s) slash synchronisée(s)\033[0m')
    except Exception as e:
        print(f'\033[93m[!] Erreur lors de la synchronisation des slash commands : {e}\033[0m')

    try:
        from synkrone_custom import apply_runtime
        await apply_runtime(bot)
    except Exception:
        pass

    # Envoi du MP à l'owner si erreurs de cogs
    if COGS_ERRORS:
        try:
            # Récupère l'ID owner depuis le fichier JSON
            import json
            owner_path = os.path.join('data', 'addons', 'data_owner', 'owner.json')
            with open(owner_path, 'r', encoding='utf-8') as f:
                owner_ids = json.load(f)
            owner_id = owner_ids[0] if owner_ids else None
            if owner_id:
                owner = await bot.fetch_user(owner_id)
                if owner:
                    # Formatage :
                    # - 📁 chemin (avec \)
                    #    - description sans rappel du chemin
                    error_lines = []
                    for cog, msg in COGS_ERRORS:
                        # Chemin avec backslash et .py, monospace
                        cog_path = cog.replace('.', '\\') + '.py'
                        # Nettoie le message d'erreur : retire le rappel du chemin si présent
                        desc = msg
                        cog_name = cog
                        if f"'{cog_name}'" in desc:
                            desc = desc.replace(f"'{cog_name}'", "").strip()
                        desc = desc.replace('Extension', '').strip()
                        desc = desc.lstrip(':').strip()
                        if desc.startswith("has no"):
                            desc = "Extension " + desc
                        # Format markdown demandé
                        error_lines.append(f"- 📁 `{cog_path}`\n❌   - *{desc}*")
                    error_text = '\n'.join(error_lines)
                    # Statistiques dans le footer avec emoji
                    try:
                        total = COGS_TOTAL
                        loaded = COGS_LOADED
                        errors = COGS_ERRORS_COUNT
                    except Exception:
                        total = loaded = errors = 'N/A'
                    stats = f"📦 Total : {total} | ✅ Chargés : {loaded} | ⚠️ Erreurs : {errors}"
                    embed = discord.Embed(title="⚠️ Erreurs de chargement des cogs", description=error_text, color=0xFFA500)
                    embed.set_footer(text=stats)
                    await owner.send(embed=embed)
        except Exception as e:
            print(f"[!] Impossible d'envoyer le MP d'erreurs à l'owner: {e}")


@bot.event
async def on_guild_join(guild):
    try:
        from synkrone_custom import apply_runtime
        await apply_runtime(bot, guild)
    except Exception:
        pass

async def main():
    async with bot:
        await load_cogs()
        await bot.start(TOKEN)

if __name__ == "__main__":
    if TOKEN:
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            print("\n\033[93m[!] Arrêt du bot par l'utilisateur...\033[0m")
        except Exception as e:
            print(f"\033[91m[!] Erreur fatale : {e}\033[0m")
    else:
        print("\033[91m[!] Erreur: DISCORD_TOKEN introuvable dans le .env\033[0m")