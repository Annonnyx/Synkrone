# ==============================================================================
# utils/config_play.py - CONFIGURATION DU MODULE MUSICAL (VAX V3)
# ==============================================================================
DEBUG_MODE = False  # <-- Bascule globale pour les logs console

import os
import shutil
import time
from utils.config_data import DataManager

def debug_config(message: str, level: str = "INFO"):
    if not DEBUG_MODE: return
    colors = {"INFO": "\033[94m", "SUCCESS": "\033[92m", "ERROR": "\033[91m", "WARNING": "\033[93m"}
    reset = "\033[0m"
    print(f"{colors.get(level.upper(), '\033[97m')}[DEBUG - ConfigPlay] [{level.upper()}] {message}{reset}")

# --- 1. DÉTECTION ROBUSTE DE FFMPEG ---
_ENV_FFMPEG = os.getenv("FFMPEG_PATH", "ffmpeg")
if shutil.which(_ENV_FFMPEG):
    FFMPEG_EXECUTABLE = _ENV_FFMPEG
    debug_config(f"Exécutable FFmpeg détecté via PATH : {FFMPEG_EXECUTABLE}", "SUCCESS")
elif os.name == "nt" and os.path.exists(r"C:\ffmpeg\bin\ffmpeg.exe"):
    FFMPEG_EXECUTABLE = r"C:\ffmpeg\bin\ffmpeg.exe"
    debug_config(f"FFmpeg trouvé via fallback local Windows : {FFMPEG_EXECUTABLE}", "SUCCESS")
else:
    FFMPEG_EXECUTABLE = "ffmpeg"
    debug_config("ATTENTION : FFmpeg introuvable dans le PATH ou le dossier local !", "ERROR")

# --- 2. OPTIONS YOUTUBE-DLP ---
YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
    'nocheckcertificate': True,
    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

# --- 3. OPTIONS FFMPEG ---
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -filter:a "volume=0.5"'
}

# --- 4. GESTIONNAIRE DE DONNÉES (Historique) ---
try:
    music_db = DataManager("public/divertissement/data_music_history")
    debug_config("DataManager 'data_music_history' initialisé.", "SUCCESS")
except Exception as e:
    music_db = None
    debug_config(f"Erreur d'initialisation du DataManager : {e}", "ERROR")

def save_to_history(guild_id: int, query: str, user_id: int, track_title: str):
    if not music_db: return
    data = music_db.load(guild_id)
    if "history" not in data:
        data["history"] = []
    
    data["history"].insert(0, {
        "query": query,
        "title": track_title,
        "user_id": user_id,
        "timestamp": int(time.time())
    })
    data["history"] = data["history"][:50]
    music_db.save(guild_id, data)
