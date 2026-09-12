
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

IMPORT_NAME_OVERRIDES = {
    "discord.py": "discord",
    "python-dotenv": "dotenv",
    "pillow": "PIL",
    "pynacl": "nacl",
    "topggpy": "topgg",
}


def _requirement_to_import_candidates(requirement: str) -> List[str]:
    """Convertit une ligne requirements en noms de modules possibles."""
    base = requirement.split(";", 1)[0].strip()
    base = base.split("[", 1)[0].strip()
    for sep in ("==", ">=", "<=", "~=", "!=", ">", "<"):
        if sep in base:
            base = base.split(sep, 1)[0].strip()
            break

    key = base.lower()
    candidates = []

    if key in IMPORT_NAME_OVERRIDES:
        candidates.append(IMPORT_NAME_OVERRIDES[key])

    candidates.append(base)
    candidates.append(base.replace("-", "_"))

    unique = []
    for name in candidates:
        if name and name not in unique:
            unique.append(name)
    return unique


def is_package_installed(requirement: str) -> bool:
    """Vérifie si une dépendance requirements est déjà importable."""
    return any(importlib.util.find_spec(name) is not None for name in _requirement_to_import_candidates(requirement))

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
    
    missing_deps = [dep for dep in requirements if not is_package_installed(dep)]
    
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
    failed_deps = []
    for i, dep in enumerate(missing_deps, 1):
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", dep], capture_output=True, check=True)
            success_count += 1
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or b"").decode(errors="replace").strip()
            failed_deps.append((dep, stderr.splitlines()[-1] if stderr else "Erreur pip inconnue"))
        except Exception as e:
            failed_deps.append((dep, str(e)))
        progress_data['current'] = i
    
    progress_data['running'] = False
    thread.join(timeout=1)
    print("\n")
    if failed_deps:
        print("\033[91m[✗] Installation incomplète des dépendances :\033[0m")
        for dep, err in failed_deps:
            print(f"\033[91m - {dep}: {err}\033[0m")

        if any("externally-managed-environment" in err for _, err in failed_deps):
            print("\033[93m[!] Lancez le bot avec un environnement virtuel, ex: venv/bin/python main.py\033[0m")

    return success_count == len(missing_deps)

# Exécution de l'installation avant d'importer Discord
if not install_requirements():
    sys.exit(1)

# ==============================================================================
# 2. CONFIGURATION DU LOGGER ET DE DISCORD
# ==============================================================================


import discord
from discord.ext import commands
# Pas de module owner/addons dans ce dépôt.

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
DEFAULT_PREFIX = os.getenv("BOT_PREFIX") or os.getenv("PREFIX", "!")

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
    ignored_exact_files = [
        '__init__.py', 'utils.py', 'util_embed.py',
        'embed_private.py', 'config_util.py', 'embed_launcher.py', 'embed_admin.py'
    ]

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
# Préfixe global uniquement (ce dépôt n'inclut pas cogs/addons/prefix) :
#   a. config/bot.json (panneau Synkrone)
#   b. Cog BotAdmin en mémoire (panelbot, mis à jour sans redémarrage)
#   c. cogs/DEV/panelbot/bot_config.json
#   d. BOT_PREFIX / PREFIX dans l'environnement

_PANEL_CFG_PATH = os.path.join('config', 'bot.json')
_PANELBOT_CFG_PATH = os.path.join('cogs', 'DEV', 'panelbot', 'bot_config.json')

def _read_json_prefix(path: str) -> Optional[str]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            prefix = json.load(f).get('prefix')
            if prefix:
                return str(prefix)
    except Exception:
        pass
    return None

try:
    from synkrone_slash import slash_enabled as _slash_enabled, sync_app_commands
except ImportError:
    sync_app_commands = None

    def _slash_enabled() -> bool:
        if os.path.exists(_PANEL_CFG_PATH):
            try:
                with open(_PANEL_CFG_PATH, 'r', encoding='utf-8') as f:
                    flag = json.load(f).get('slashCommands')
                    if flag is not None:
                        return bool(flag)
            except Exception:
                pass
        raw = os.getenv('ENABLE_SLASH_COMMANDS', 'true')
        return str(raw).lower() in ('1', 'true', 'yes')

def _get_global_prefix() -> str:
    """Retourne le préfixe global actif : panneau → BotAdmin → bot_config.json → env"""
    panel_prefix = _read_json_prefix(_PANEL_CFG_PATH)
    if panel_prefix:
        return panel_prefix
    try:
        cog = bot.cogs.get('BotAdmin')
        if cog and hasattr(cog, 'default_prefix') and cog.default_prefix:
            return cog.default_prefix
    except Exception:
        pass
    return _read_json_prefix(_PANELBOT_CFG_PATH) or DEFAULT_PREFIX

def get_prefix(bot, message):
    """Préfixe global (panneau > BotAdmin en mémoire > bot_config.json > env)."""
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
    if getattr(bot, "start_time", None) is None:
        bot.start_time = datetime.datetime.now(datetime.timezone.utc)
    print(f'\033[92m🤖 Connecté en tant que {bot.user.name}\033[0m')
    print('\033[94m' + '─' * 60 + '\033[0m')
    if sync_app_commands:
        await sync_app_commands(bot, log_prefix="[bot]")
    else:
        try:
            if _slash_enabled():
                synced = await bot.tree.sync()
                print(f'\033[92m[✓] {len(synced)} commande(s) slash synchronisée(s)\033[0m')
            else:
                bot.tree.clear_commands(guild=None)
                await bot.tree.sync()
                print('\033[93m[!] Commandes slash désactivées\033[0m')
        except Exception as e:
            print(f'\033[93m[!] Erreur lors de la synchronisation des slash commands : {e}\033[0m')
    if COGS_ERRORS:
        print('\033[93m[!] Erreurs de chargement des cogs :\033[0m')
        for cog, msg in COGS_ERRORS:
            print(f'\033[93m - {cog}: {msg}\033[0m')

@bot.event
async def on_guild_join(guild):
    if sync_app_commands:
        await sync_app_commands(bot, guild=guild, log_prefix="[bot]")

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