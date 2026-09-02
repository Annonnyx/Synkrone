import discord
from discord.ext import commands
from discord import app_commands
from discord import ui
import asyncio
import random
import datetime
import traceback
import json
from pathlib import Path
from typing import List, Dict, Any

# Importations de l'architecture interne
from utils.config_theme import config_manager
from utils.config_emoji import Emoji
from utils.config_data import DataManager

# ==============================================================================
# -------------------- CONFIGURATION & VARIABLES GLOBALES ----------------------
# ==============================================================================

# Contrôle des logs système
DEBUG_LOGS = True
ERROR_LOGS_ONLY = True

# Emojis centralisés (Appel dynamique pour garantir la compatibilité)
E_HACK = "🔓"
E_PROGRESS = "🚀"
E_SUCCESS = getattr(Emoji, "VALIDER", "✅")
E_ERROR = getattr(Emoji, "REFUSER", "❌")
E_TARGET = getattr(Emoji, "CIBLE", "🎯")
E_SYS = getattr(Emoji, "BOUCLIER", "🛡️")
E_NET = getattr(Emoji, "MONDE", "🌐")
E_WARN = getattr(Emoji, "ATTENTION", "⚠️")
E_ID = getattr(Emoji, "IDENTIFIANT", "🆔")

# ==============================================================================
# --------------------------- SYSTÈME DE LOGS ----------------------------------
# ==============================================================================
def log_sys(msg: str, is_error: bool = False):
    """Gestionnaire de logs interne avec coloration de la console."""
    if is_error:
        print(f"\033[91m[MODULE HACK - ERREUR] {msg}\033[0m")
    elif not ERROR_LOGS_ONLY and DEBUG_LOGS:
        print(f"\033[94m[MODULE HACK - INFO] {msg}\033[0m")

# ==============================================================================
# ---------------------------- UI LAYOUT V2 ------------------------------------
# ==============================================================================
class HackTerminalLayout(ui.LayoutView):
    """Layout V2 simulant un terminal de hack dynamique."""
    def __init__(self, target: discord.Member, hacker: discord.Member, bot: commands.Bot, guild: discord.Guild):
        super().__init__(timeout=180)
        self.target = target
        self.hacker = hacker
        self.bot = bot
        self.guild = guild
        
        # Récupération du thème serveur
        self.theme = config_manager.get_layout_v2_theme(self.guild.id, self.guild, self.hacker, self.bot)
        
        self.content_header = f"# {E_HACK} Initialisation du piratage..."
        self.content_target_info = f"Acquisition des données sur {self.target.mention}..."
        self.content_progress = ""
        self.content_network = ""
        self.content_image_url: str | None = None
        
        self._build_layout()

    def update_state(self, header=None, target_info=None, progress=None, network=None, image_url=None):
        if header is not None: self.content_header = header
        if target_info is not None: self.content_target_info = target_info
        if progress is not None: self.content_progress = progress
        if network is not None: self.content_network = network
        if image_url is not None: self.content_image_url = image_url
        self._build_layout()

    def _build_layout(self):
        self.clear_items()
        
        container = ui.Container(accent_color=discord.Color(self.theme.get("color", config_manager.DEFAULT_COLOR)), spoiler=False)
        container.add_item(ui.TextDisplay(self.content_header))
        container.add_item(ui.TextDisplay(self.content_target_info))

        if self.content_image_url:
            try:
                gallery = ui.MediaGallery()
                gallery.add_item(media=self.content_image_url, description="Flux visuel")
                container.add_item(gallery)
            except Exception:
                container.add_item(ui.TextDisplay(f"{E_WARN} Flux visuel indisponible."))
        
        if self.content_progress:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
            container.add_item(ui.TextDisplay(f"## {E_PROGRESS} Progression système"))
            container.add_item(ui.TextDisplay(self.content_progress))
            
        if self.content_network:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.small, visible=True))
            container.add_item(ui.TextDisplay(f"## {E_NET} Trafic Réseau"))
            container.add_item(ui.TextDisplay(self.content_network))
            
        footer_text = self.theme.get("footer_text")
        if footer_text:
            container.add_item(ui.Separator(spacing=discord.SeparatorSpacing.large, visible=True))
            container.add_item(ui.TextDisplay(footer_text))
            
        self.add_item(container)

# ==============================================================================
# --------------------------------- COG ----------------------------------------
# ==============================================================================
class Hack(commands.Cog):
    """Module Divertissement — Système avancé de pénétration de sécurité."""

    def __init__(self, bot):
        self.bot = bot
        # Initialisation du DataManager pointant sur le fichier JSON ciblé
        self.data_mgr = DataManager("public/divertissement/assets")
        self.assets_dir = Path(__file__).resolve().parent / "assets"
        log_sys("Module chargé et opérationnel. Connecté au DataManager.")

    def _load_asset_hack_data(self) -> Dict[str, Any]:
        """Charge hack_data.json depuis les assets du module (source principale)."""
        asset_file = self.assets_dir / "hack_data.json"
        if not asset_file.exists():
            log_sys(f"Fichier asset introuvable: {asset_file}", is_error=True)
            return {}
        try:
            with asset_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
            log_sys("hack_data.json invalide: racine non objet.", is_error=True)
            return {}
        except Exception as exc:
            log_sys(f"Erreur lecture hack_data.json: {exc}", is_error=True)
            return {}

    def _get_hack_data(self) -> Dict[str, Any]:
        """Charge et sécurise les données dynamiques depuis hack_data.json."""
        # Source principale: cogs/public/divertissement/assets/hack_data.json
        # Source secondaire: data/public/divertissement/assets/hack_data.json pour surcharges runtime.
        data = self._load_asset_hack_data()
        override_data = self.data_mgr.load("hack_data")
        if isinstance(override_data, dict) and override_data:
            data.update(override_data)

        raw_steps = data.get("hacking_steps") or data.get("steps") or []
        normalized_steps: List[Dict[str, Any]] = []
        if isinstance(raw_steps, list):
            for step in raw_steps:
                if not isinstance(step, dict):
                    continue
                action = str(step.get("action", "Scan initial du système")).strip()
                emoji = str(step.get("emoji", "")).strip()
                success = float(step.get("success", 0.9))
                delay = float(step.get("time", 1.0))
                normalized_steps.append(
                    {
                        "action": action,
                        "emoji": emoji,
                        "success": min(1.0, max(0.0, success)),
                        "time": max(0.4, min(6.0, delay)),
                    }
                )
        
        # Données de secours (fallbacks) au cas où le JSON est vide ou mal formaté
        return {
            "aliases": data.get("hacker_aliases") or data.get("aliases", ["Cypher", "Neo", "Vex", "Zero", "Glitch", "Phantom", "Root", "Spectre"]),
            "os_list": data.get("operating_systems") or data.get("os_list", ["Linux (Kali)", "Windows 11 Pro", "iOS 18", "macOS Ventura", "Android 15"]),
            "images": data.get("images", [
                "https://i.gifer.com/Xqg8.gif", 
                "https://i.gifer.com/2iiJ.gif",
                "https://i.gifer.com/1F1I.gif"
            ]),
            "steps": normalized_steps or [
                {"action": "Scan initial du système", "success": 0.98},
                {"action": "Contournement du pare-feu", "success": 0.90},
                {"action": "Brute force des identifiants", "success": 0.85},
                {"action": "Injection de charge utile", "success": 0.92},
                {"action": "Extraction des données sensibles", "success": 0.88},
                {"action": "Effacement des traces (Ghost Protocol)", "success": 0.95}
            ],
            "status_messages": data.get("status_messages", []),
            "system_messages": data.get("system_messages", []),
            "emails_corpus": data.get("emails_corpus", ["{username}.darkweb@proton.mail", "contact_{year}@secure.net"]),
            "files_corpus": data.get("files_corpus", ["Photos/Selfies_Genants_{year}", "Backup/Clés_SSH.bak"]),
            "passwords_corpus": data.get("passwords_corpus", ["Pa$$w0rdS3cur3{rand}", "azerty{rand}123"])
        }

    def _generate_ip(self):
        return f"{random.randint(10,255)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"

    def _generate_mac(self):
        return ":".join([f"{random.randint(0, 255):02x}" for _ in range(6)])

    @commands.hybrid_command(name="hack", description="Simule un hack rapide et animé sur un utilisateur")
    @app_commands.describe(cible="La personne à hacker")
    async def hack(self, ctx: commands.Context, cible: discord.Member):

        log_sys(f"Séquence rapide initiée par {ctx.author.id} sur {cible.id}")
        await ctx.defer(ephemeral=False)
        
        if cible.bot:
            log_sys("Rejet : Ciblage d'une IA détecté.")
            return await ctx.send(f"{E_ERROR} **Alerte Système** : Action impossible sur une intelligence artificielle tierce.")
            
        if cible == ctx.author:
            log_sys("Rejet : Auto-ciblage détecté.")
            return await ctx.send(f"{E_WARN} **Alerte Système** : Auto-ciblage détecté. Annulation par sécurité.")

        try:
            # 1. Chargement des données fraîches
            hack_data = self._get_hack_data()
            hacker_name = f"{random.choice(hack_data['aliases'])}_{random.randint(100, 999)}"
            target_ip = self._generate_ip()
            target_os = random.choice(hack_data['os_list'])
            images = hack_data['images']
            steps = hack_data['steps']
            status_messages = hack_data.get('status_messages', [])
            system_messages = hack_data.get('system_messages', [])
            
            # 2. Initialisation de l'interface Components V2 (sans embed).
            terminal_view = HackTerminalLayout(cible, ctx.author, self.bot, ctx.guild)

            first_image = images[0] if images else None
            if first_image:
                terminal_view.update_state(image_url=first_image)

            message = await ctx.send(view=terminal_view)
            await asyncio.sleep(1.0)
            
            # 3. Informations d'accroche
            target_info = (
                f"{E_TARGET} Cible: {cible.mention}\n"
                f"```ansi\n"
                f"\u001b[31m• Alias: {cible.display_name}\n"
                f"\u001b[34m• ID: {cible.id}\n"
                f"\u001b[35m• IPv4: {target_ip}\n"
                f"\u001b[32m• Kernel: {target_os}\n"
                f"\u001b[33m• MAC: {self._generate_mac()}\n"
                f"```"
            )
            terminal_view.update_state(header=f"# {E_SYS} Terminal Actif", target_info=target_info)
            await message.edit(view=terminal_view)

            total_steps = len(steps)
            
            # 4. Boucle d'exécution pilotée par les étapes JSON
            for i, step in enumerate(steps, 1):
                progress_percent = min(100, int((i / total_steps) * 100))
                bar_len = 20
                filled = int(bar_len * i // total_steps)
                bar = '█' * filled + '░' * (bar_len - filled)
                
                color_code = '31' if progress_percent < 35 else '33' if progress_percent < 75 else '32'
                
                status_line = random.choice(status_messages) if status_messages else step['action']
                step_label = f"{step.get('emoji', '').strip()} {step['action']}".strip()
                prog_text = (
                    f"```ansi\n"
                    f"\033[1;{color_code}m{bar} [{progress_percent}%]\033[0m\n\n"
                    f"\033[1;36m>> {step_label}...\033[0m\n"
                    f"\033[0;37m{status_line}\033[0m\n"
                    f"```"
                )
                
                # Réseau aléatoire
                if system_messages and random.random() < 0.7:
                    net_text = f"```\n{random.choice(system_messages)}\n```"
                else:
                    net_text = f"```\n[PORT] Redirection du flux sur le port {random.randint(1000, 9999)}...\n```" if random.random() < 0.5 else ""
                
                # Mise à jour de l'image (Animation)
                if images:
                    terminal_view.update_state(image_url=images[i % len(images)])
                    
                terminal_view.update_state(progress=prog_text, network=net_text)
                await message.edit(view=terminal_view)
                
                # Rythme défini par les étapes du JSON
                await asyncio.sleep(float(step.get('time', 1.0)))
                
                # Gestion réaliste d'erreur
                if random.random() > step['success']:
                    log_sys(f"Échec partiel sur étape {i}", is_error=True)
                    terminal_view.update_state(progress=f"```diff\n- ERREUR: {step['action']}\n- Re-routage...\n```")
                    await message.edit(view=terminal_view)
                    await asyncio.sleep(1.0)
            
            # 5. Extraction finale
            username = cible.name.lower().replace(' ', '_')
            year = datetime.datetime.now().year
            
            def fmt(corpus): 
                return random.choice(corpus).format(username=username, year=year, rand=random.randint(10, 999))
                
            report = (
                f"```ansi\n"
                f"\033[1;34m📧 EMAIL\033[0m: {fmt(hack_data['emails_corpus'])}\n"
                f"\033[1;33m📂 FICHIER\033[0m: {fmt(hack_data['files_corpus'])}\n"
                f"\033[1;31m🔑 CREDENTIALS\033[0m: {fmt(hack_data['passwords_corpus'])}\n\n"
                f"\033[1;32m[VAX-SYS] Accès Root Permanent.\033[0m\n"
                f"```"
            )
            
            # Validation visuelle
            final_image = images[-1] if images else None
            
            terminal_view.update_state(
                header=f"# {E_SUCCESS} OPÉRATION COMPLÈTE",
                target_info=f"{E_TARGET} Cible: {cible.mention}",
                progress=report,
                network="",
                image_url=final_image,
            )
            await message.edit(view=terminal_view)
            log_sys("Séquence rapide terminée avec succès.")
            
        except Exception as e:
            log_sys(f"Exception lors de l'exécution: {str(e)}", is_error=True)
            traceback.print_exc()
            await ctx.send(f"{E_ERROR} Erreur critique d'exécution. Les logs ont été capturés.")

async def setup(bot: commands.Bot):
    if bot.get_command("hack"):
        bot.remove_command("hack")
    await bot.add_cog(Hack(bot))