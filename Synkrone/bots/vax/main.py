# Non
import os
import logging
import sys
import datetime
import subprocess
import importlib.util
import asyncio
from typing import List, Optional
from dotenv import load_dotenv

sys.dont_write_bytecode = True

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

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
    return any(importlib.util.find_spec(name) is not None for name in _requirement_to_import_candidates(requirement))

def get_requirements() -> List[str]:
    try:
        with open('requirements.txt', 'r', encoding='utf-8') as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except FileNotFoundError:
        return []

def install_requirements() -> bool:
    requirements = get_requirements()
    if not requirements:
        return True
    
    missing_deps = [dep for dep in requirements if not is_package_installed(dep)]
    if not missing_deps:
        return True
        
    print(f"\033[94m[?] Installation de {len(missing_deps)} dépendance(s) manquante(s)...\033[0m")
    import time
    import threading
    
    progress_data = {'current': 0, 'total': len(missing_deps), 'running': True}
    
    def update_progress():
        while progress_data['running']:
            curr, tot = progress_data['current'], progress_data['total']
            if tot > 0:
                percent = (curr / tot) * 100
                sys.stdout.write(f"\r\033[94m[?] Progression : [{curr}/{tot}] {percent:.1f}%\033[0m")
                sys.stdout.flush()
            if curr >= tot:
                break
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
        print("\033[91m[?] Installation incomplète des dépendances :\033[0m")
        for dep, err in failed_deps:
            print(f"\033[91m - {dep}: {err}\033[0m")
        if any("externally-managed-environment" in err for _, err in failed_deps):
            print("\033[93m[!] Lancez le bot avec un environnement virtuel, ex: venv/bin/python main.py\033[0m")
            
    return success_count == len(missing_deps)

if not install_requirements():
    sys.exit(1)

# ==============================================================================
# 2. CONFIGURATION DU LOGGER ET DE DISCORD
# ==============================================================================

import discord
from discord.ext import commands
from utils.config_prefix import get_global_prefix as _resolve_global_prefix, prefix_config_manager

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

logging.getLogger('discord').setLevel(logging.CRITICAL)
logging.getLogger('asyncio').setLevel(logging.CRITICAL)

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
DEFAULT_PREFIX = os.getenv("PREFIX", "!")
intents = discord.Intents.all()

# ==============================================================================
# 3. CHARGEMENT DES COGS
# ==============================================================================

COGS_ERRORS = []
COGS_TOTAL = 0
COGS_LOADED = 0
COGS_ERRORS_COUNT = 0

async def load_cogs():
    global COGS_TOTAL, COGS_LOADED, COGS_ERRORS_COUNT, COGS_ERRORS
    total_cogs = 0
    loaded_cogs = 0
    error_cogs = 0
    
    ignored_exact_files = [
        '__init__.py', 'utils.py', 'util_embed.py',
        'embed_private.py', 'config_util.py', 'embed_launcher.py', 'embed_admin.py'
    ]
    
    YELLOW, GREEN, RED, BLUE, RESET = '\033[93m', '\033[92m', '\033[91m', '\033[94m', '\033[0m'
    print(f"{BLUE}[?] Analyse et chargement des cogs...{RESET}")
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
                    print(f"{GREEN}[?] Cog chargé : {cog_path}{RESET}")
                except Exception as e:
                    error_cogs += 1
                    print(f"{YELLOW}[!] Erreur lors du chargement de {cog_path}: {e}{RESET}")
                    COGS_ERRORS.append((cog_path, str(e)))
                    
    print(f"\n{BLUE}=== Résumé du chargement ==={RESET}")
    print(f"{GREEN}✓ {loaded_cogs} chargé(s){RESET} | {RED}✗ {error_cogs} erreur(s){RESET}")
    print(f"{BLUE}============================{RESET}\n")
    
    COGS_TOTAL = total_cogs
    COGS_LOADED = loaded_cogs
    COGS_ERRORS_COUNT = error_cogs

# ==============================================================================
# 4. SYSTÈME DE PRÉFIXES
# ==============================================================================

def _get_global_prefix() -> str:
    return _resolve_global_prefix(bot, fallback=DEFAULT_PREFIX)

def get_prefix(bot, message):
    if message.guild:
        try:
            return prefix_config_manager.get_effective_prefixes(
                bot=bot,
                guild_id=message.guild.id,
                default_prefix=DEFAULT_PREFIX,
            )
        except Exception:
            pass
    return [_get_global_prefix()]

# ==============================================================================
# 5. LANCEMENT DU BOT
# ==============================================================================

class ReplyBot(commands.Bot):
    async def get_context(self, message, *, cls=commands.Context):
        ctx = await super().get_context(message, cls=cls)
        if ctx.command:
            original_send = ctx.send
            async def reply_send(content=None, **kwargs):
                if 'reference' not in kwargs and 'mention' not in kwargs:
                    if hasattr(message, "reply") and callable(getattr(message, "reply", None)):
                        try:
                            return await message.reply(content, **kwargs)
                        except discord.HTTPException:
                            return await original_send(content, **kwargs)
                        except Exception:
                            return await original_send(content, **kwargs)
                    else:
                        return await original_send(content, **kwargs)
                else:
                    return await original_send(content, **kwargs)
            ctx.send = reply_send
        return ctx

bot = ReplyBot(command_prefix=get_prefix, intents=intents)
bot.help_command = None

STARTUP_LOG_USER_ID = 1366780122891419784

async def _resolve_notification_owners() -> List[discord.User]:
    owners_by_id = {}
    async def _add_owner_by_id(user_id: Optional[int], source: str) -> None:
        if not user_id or user_id in owners_by_id:
            return
        try:
            user = await bot.fetch_user(user_id)
            owners_by_id[user.id] = user
        except Exception as e:
            print(f"[!] Impossible de fetch l'owner ({source}: {user_id}): {e}")
            
    try:
        app_info = await bot.application_info()
    except Exception as e:
        print(f"[!] Impossible de récupérer application_info: {e}")
        app_info = None
        
    if app_info:
        team = getattr(app_info, "team", None)
        if team:
            await _add_owner_by_id(getattr(team, "owner_id", None), "team.owner_id")
            team_owner_obj = getattr(team, "owner", None)
            await _add_owner_by_id(getattr(team_owner_obj, "id", None), "team.owner")
        else:
            app_owner = getattr(app_info, "owner", None)
            await _add_owner_by_id(getattr(app_owner, "id", None), "app.owner")
            
    fallback_owner_ids = []
    owner_id = getattr(bot, "owner_id", None)
    owner_ids = getattr(bot, "owner_ids", None)
    if owner_id:
        fallback_owner_ids.append(owner_id)
    if owner_ids:
        fallback_owner_ids.extend(list(owner_ids))
    for fallback_id in fallback_owner_ids:
        await _add_owner_by_id(fallback_id, "fallback")
    return list(owners_by_id.values())

def _build_startup_embeds() -> List[discord.Embed]:
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    has_errors = bool(COGS_ERRORS)
    color = 0xF39C12 if has_errors else 0x2ECC71
    title = "⚠️ Bot en ligne (avec erreurs de cogs)" if has_errors else "🟢 Bot en ligne"
    description = "Le bot est connecté et opérationnel."
    if has_errors:
        description = "Le bot est connecté, mais certains cogs n'ont pas pu être chargés."
    embed = discord.Embed(title=title, description=description, color=color, timestamp=now_utc)
    stats = f"📊 Total : {COGS_TOTAL} | ✅ Chargés : {COGS_LOADED} | ❌ Erreurs : {COGS_ERRORS_COUNT}"
    embed.add_field(name="État du chargement", value=stats, inline=False)
    embeds = [embed]
    
    if has_errors:
        def _build_error_entry(cog_path: str, description: str, limit: int = 900) -> str:
            # Keep code fences balanced by truncating only inner content.
            prefix = f"```\n{cog_path}\n\n"
            suffix = "\n```"
            max_desc_len = max(20, limit - len(prefix) - len(suffix))
            if len(description) > max_desc_len:
                description = description[: max_desc_len - 15].rstrip() + "... (tronqué)"
            return f"{prefix}{description}{suffix}"

        def _chunk_entries(entries: List[str], limit: int = 900) -> List[str]:
            chunks: List[str] = []
            current: List[str] = []
            current_len = 0

            for entry in entries:
                entry_len = len(entry)
                separator_len = 2 if current else 0

                if current and current_len + separator_len + entry_len > limit:
                    chunks.append('\n\n'.join(current))
                    current = [entry]
                    current_len = entry_len
                    continue

                current.append(entry)
                current_len += separator_len + entry_len

            if current:
                chunks.append('\n\n'.join(current))
            return chunks

        error_entries = []
        for cog, msg in COGS_ERRORS:
            cog_path = cog.replace('.', '\\') + '.py'
            desc = msg
            if f"'{cog}'" in desc:
                desc = desc.replace(f"'{cog}'", "").strip()
            desc = desc.replace('Extension', '').strip()
            desc = desc.lstrip(':').strip()
            if desc.startswith("has no"):
                desc = "Extension " + desc
            sanitized_desc = desc.replace("```", "'''")
            error_entries.append(_build_error_entry(cog_path, sanitized_desc))

        error_chunks = _chunk_entries(error_entries or ["Aucun détail disponible."])
        for index, chunk in enumerate(error_chunks, start=1):
            detail_embed = discord.Embed(
                title=f"Détails des erreurs ({index}/{len(error_chunks)})",
                description=chunk,
                color=color,
                timestamp=now_utc,
            )
            embeds.append(detail_embed)
    return embeds

@bot.event
async def on_ready():
    print(f'\033[92m🟢 Connecté en tant que {bot.user.name}\033[0m')
    print('\033[94m' + '-' * 60 + '\033[0m')
    try:
        synced = await bot.tree.sync()
        print(f"[?] Slash commands synchronisées: {len(synced)}")
    except Exception as e:
        print(f"[!] Échec de synchronisation des slash commands: {e}")
    try:
        target_user = await bot.fetch_user(STARTUP_LOG_USER_ID)
        startup_embeds = _build_startup_embeds()
        for startup_embed in startup_embeds:
            await target_user.send(embed=startup_embed)
        print(f"[?] MP de démarrage envoyé à {target_user} ({STARTUP_LOG_USER_ID}).")
    except Exception as e:
        print(f"[!] Impossible d'envoyer le MP de démarrage à {STARTUP_LOG_USER_ID}: {e}")
    print(f'\033[92m✅ Connecté avec succès\033[0m')

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