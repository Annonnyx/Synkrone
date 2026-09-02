import os
import re
import json
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Tuple, List, Optional

import discord
from discord.ext import commands, tasks
from discord import ui, app_commands

# --- INTERFACE DE COHÉRENCE VISUELLE ---
try:
    from cogs.addons.embed_type.utils import config_manager
except ImportError:
    config_manager = None

# --- CONSTANTES ET CONFIGURATION DES CHEMINS ---
ROOT_DATA_DIR = Path.cwd() / "data"
COGS_DIR = Path.cwd() / "cogs"
FEATURE_DATA_DIR = ROOT_DATA_DIR / "owner" / "data_control"
LOGS = logging.getLogger("bot")

def format_bytes(b: int) -> str:
    """Formatte les octets de manière lisible pour les rapports quantitatifs."""
    for unit in ['octets', 'Ko', 'Mo', 'Go']:
        if b < 1024.0:
            return f"**{b:.2f}** {unit}"
        b /= 1024.0
    return f"**{b:.2f}** To"

# ==============================================================================
# ------------------------ INTERFACE DE CONTRÔLE OWNER -------------------------
# ==============================================================================

class DataControlView(ui.View):
    def __init__(self, cog, author: discord.User):
        super().__init__(timeout=300.0)
        self.cog = cog
        self.author = author
        self.mask_ids = True  # Masquage activé par défaut pour la sécurité visuelle
        self.update_buttons()

    def update_buttons(self):
        """Met à jour dynamiquement l'état visuel des boutons de contrôle."""
        # Bouton de boucle automatique
        if self.cog.loop_enabled:
            self.toggle_loop_btn.label = "Boucle Auto : ON"
            self.toggle_loop_btn.style = discord.ButtonStyle.green
            self.toggle_loop_btn.emoji = "🟢"
        else:
            self.toggle_loop_btn.label = "Boucle Auto : OFF"
            self.toggle_loop_btn.style = discord.ButtonStyle.danger
            self.toggle_loop_btn.emoji = "🔴"

        # Bouton de masquage des identifiants (IDs)
        if self.mask_ids:
            self.toggle_id_btn.label = "IDs : Masqués"
            self.toggle_id_btn.style = discord.ButtonStyle.secondary
            self.toggle_id_btn.emoji = "🔒"
        else:
            self.toggle_id_btn.label = "IDs : Visibles"
            self.toggle_id_btn.style = discord.ButtonStyle.success
            self.toggle_id_btn.emoji = "🔓"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Sécurité : Restriction exclusive au propriétaire d'origine."""
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("⛔ Ce panneau d'administration est verrouillé.", ephemeral=True)
            return False
        return True

    @ui.button(label="Boucle Auto", row=0)
    async def toggle_loop_btn(self, interaction: discord.Interaction, button: ui.Button):
        self.cog.loop_enabled = not self.cog.loop_enabled
        self.cog.save_loop_state()
        self.update_buttons()
        embed = self.cog.generate_main_embed(interaction.guild, self.author, self.mask_ids)
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="IDs : Masqués", row=0)
    async def toggle_id_btn(self, interaction: discord.Interaction, button: ui.Button):
        """Permet de basculer entre le masquage anonymisé et l'affichage brut des Snowflake Discord."""
        self.mask_ids = not self.mask_ids
        self.update_buttons()
        embed = self.cog.generate_main_embed(interaction.guild, self.author, self.mask_ids)
        await interaction.response.edit_message(embed=embed, view=self)

    @ui.button(label="Purger Inutiles", style=discord.ButtonStyle.primary, emoji="🧹", row=0)
    async def clean_orphans_btn(self, interaction: discord.Interaction, button: ui.Button):
        """Purge ciblée des serveurs quittés et utilisateurs introuvables."""
        await interaction.response.defer(ephemeral=True)
        files_purged, size_recovered = self.cog.execute_global_cleanup()
        
        embed = self.cog.create_custom_embed(
            interaction.guild, self.author,
            "🧹 Nettoyage multi-répertoires finalisé",
            f"L'analyse a traité la racine `/data/` et les sous-dossiers `/cogs/`.\n\n"
            f"• Éléments orphelins supprimés : `{files_purged}`\n"
            f"• Espace disque total récupéré : {format_bytes(size_recovered)}"
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @ui.button(label="Rafraîchir", style=discord.ButtonStyle.blurple, emoji="🔄", row=1)
    async def refresh_btn(self, interaction: discord.Interaction, button: ui.Button):
        embed = self.cog.generate_main_embed(interaction.guild, self.author, self.mask_ids)
        await interaction.response.edit_message(embed=embed, view=self)

# ==============================================================================
# -------------------------------- COG PRINCIPAL -------------------------------
# ==============================================================================

class DataControlCog(commands.Cog, name="Owner Data Control"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.loop_enabled = False
        FEATURE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.load_loop_state()
        self.cleanup_task.start()

    def cog_unload(self):
        self.cleanup_task.cancel()

    def load_loop_state(self):
        """Charge l'état du cycle de nettoyage depuis son fichier de configuration dédié."""
        config_file = FEATURE_DATA_DIR / "config.json"
        if config_file.exists():
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    self.loop_enabled = json.load(f).get("loop_enabled", False)
            except Exception as e:
                LOGS.error(f"[DATA CONTROL] Erreur chargement config : {e}")

    def save_loop_state(self):
        """Sauvegarde l'état du cycle de nettoyage dans son fichier de configuration dédié."""
        config_file = FEATURE_DATA_DIR / "config.json"
        try:
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump({"loop_enabled": self.loop_enabled}, f, indent=4)
        except Exception as e:
            LOGS.error(f"[DATA CONTROL] Erreur sauvegarde config : {e}")

    def create_custom_embed(self, guild, user, title, description) -> discord.Embed:
        """Assure la cohérence visuelle via le gestionnaire d'embed global ou fallback standard."""
        if config_manager:
            return config_manager.get_formatted_embed(
                guild=guild, user=user, bot=self.bot, title=title, description=description
            )
        embed = discord.Embed(title=title, description=description, color=0x2b2d31)
        embed.set_footer(text=f"Système de Stockage • {datetime.now().strftime('%H:%M')}")
        return embed

    def obfuscate_text(self, text: str, active: bool) -> str:
        """Applique un masquage de type Spoiler Discord sur tous les IDs (Snowflakes) détectés."""
        if not active:
            return text
        # Aligne et capture toutes les suites numériques correspondant à des IDs Discord (17 à 20 chiffres)
        return re.sub(r'\b\d{17,20}\b', r'||\g<0>||', text)

    # --- ENGIN D'ANALYSE ET CARTOGRAPHIE MULTI-DOSSIERS ---

    def scan_all_storage_locations(self) -> Dict[str, Any]:
        """
        Scanne de manière exhaustive :
        1. La racine /data/ (en suivant la structure miroir des cogs)
        2. Les répertoires internes /cogs/**/data/ et /cogs/**/DB/
        """
        report = {
            "root_total": 0,
            "cogs_total": 0,
            "guild_mapping": {},  # guild_id -> size_in_bytes
            "root_breakdown": {}, # feature_path -> size_in_bytes
            "cogs_breakdown": {}  # cog_internal_path -> size_in_bytes
        }

        # 1. Scan complet de la racine `/data/`
        if ROOT_DATA_DIR.exists():
            for root, _, files in os.walk(ROOT_DATA_DIR):
                root_path = Path(root)
                for file in files:
                    file_path = root_path / file
                    try:
                        size = file_path.stat().st_size
                        report["root_total"] += size

                        # Calcul par catégorie relative (ex: staff/configuration/data_mute)
                        try:
                            rel_path = file_path.relative_to(ROOT_DATA_DIR).parent
                            path_str = str(rel_path).replace("\\", "/")
                            if path_str and path_str != ".":
                                report["root_breakdown"][path_str] = report["root_breakdown"].get(path_str, 0) + size
                        except ValueError:
                            pass

                        # Extraction des IDs de serveurs pour métriques quantitatives
                        self._apply_guild_mapping(file_path, size, report["guild_mapping"])
                    except Exception:
                        continue

        # 2. Scan complet des dossiers `data` & `DB` internes dans `/cogs/`
        if COGS_DIR.exists():
            for root, dirs, files in os.walk(COGS_DIR):
                root_path = Path(root)
                if root_path.name.lower() in ["data", "db"]:
                    for file in files:
                        file_path = root_path / file
                        try:
                            size = file_path.stat().st_size
                            report["cogs_total"] += size

                            # Identification du module conteneur
                            try:
                                rel_cog = file_path.relative_to(COGS_DIR).parent
                                cog_str = str(rel_cog).replace("\\", "/")
                                report["cogs_breakdown"][cog_str] = report["cogs_breakdown"].get(cog_str, 0) + size
                            except ValueError:
                                pass

                            # Extraction ID
                            self._apply_guild_mapping(file_path, size, report["guild_mapping"])
                        except Exception:
                            continue

        return report

    def _apply_guild_mapping(self, file_path: Path, size: int, mapping: Dict[int, int]):
        """Analyse le nom du fichier ou de ses parents pour lier la taille à un ID de Guilde."""
        stem_clean = file_path.stem.split('_')[0]
        if stem_clean.isdigit() and 17 <= len(stem_clean) <= 20:
            g_id = int(stem_clean)
            mapping[g_id] = mapping.get(g_id, 0) + size
            return

        for part in file_path.parts:
            if part.isdigit() and 17 <= len(part) <= 20:
                g_id = int(part)
                mapping[g_id] = mapping.get(g_id, 0) + size
                break

    def analyze_single_guild(self, guild_id: int) -> Tuple[int, int]:
        """Calcule l'impact quantitatif exact d'une guilde sur l'ensemble des espaces de stockage."""
        file_count = 0
        total_size = 0
        guild_str = str(guild_id)

        for target_dir in [ROOT_DATA_DIR, COGS_DIR]:
            if not target_dir.exists():
                continue
            for root, _, files in os.walk(target_dir):
                root_path = Path(root)
                for f in files:
                    fp = root_path / f
                    if guild_str in root_path.parts or fp.stem == guild_str or fp.stem.startswith(f"{guild_str}_"):
                        file_count += 1
                        try:
                            total_size += fp.stat().st_size
                        except Exception:
                            pass
        return file_count, total_size

    def execute_global_cleanup(self) -> Tuple[int, int]:
        """Exécute une purge chirurgicale des fichiers associés à des serveurs ou utilisateurs introuvables."""
        files_purged = 0
        size_recovered = 0

        # Liste des dossiers cibles pour la recherche d'éléments orphelins
        search_targets = [ROOT_DATA_DIR, COGS_DIR]

        for target_dir in search_targets:
            if not target_dir.exists():
                continue
            
            for root, dirs, files in os.walk(target_dir, topdown=False):
                root_path = Path(root)
                
                # 1. Suppression des sous-dossiers nommés par un ID de serveur orphelin
                for d in dirs:
                    if d.isdigit() and 17 <= len(d) <= 20:
                        g_id = int(d)
                        if self.bot.get_guild(g_id) is None:
                            dir_path = root_path / d
                            try:
                                internal_files = list(dir_path.glob("**/*"))
                                for item in internal_files:
                                    if item.is_file():
                                        size_recovered += item.stat().st_size
                                        files_purged += 1
                                shutil.rmtree(dir_path)
                            except Exception:
                                pass

                # 2. Suppression des fichiers isolés (SÉCURITÉ : Ne supprime AUCUNE image sans ID explicite)
                for f in files:
                    file_path = root_path / f
                    stem_clean = file_path.stem.split('_')[0]
                    
                    if stem_clean.isdigit() and 17 <= len(stem_clean) <= 20:
                        target_id = int(stem_clean)
                        
                        is_orphan_guild = self.bot.get_guild(target_id) is None
                        is_orphan_user = self.bot.get_user(target_id) is None if is_orphan_guild else False
                        
                        if is_orphan_guild and is_orphan_user:
                            try:
                                size = file_path.stat().st_size
                                os.remove(file_path)
                                files_purged += 1
                                size_recovered += size
                            except Exception:
                                continue

        return files_purged, size_recovered

    # --- PANNEAU DE BORD GÉNÉRAL ---


    def generate_main_embed(self, guild, author, mask_ids: bool) -> discord.Embed:
        report = self.scan_all_storage_locations()

        # --- TOP 10 SERVEURS CONSOMMATEURS ---
        guild_sizes = []
        for g_id, size in report["guild_mapping"].items():
            guild_obj = self.bot.get_guild(g_id)
            if guild_obj:
                name = guild_obj.name
            else:
                name = f"❌ Serveur Quitté ({g_id})"
            guild_sizes.append((name, size, g_id, guild_obj is not None))

        # Trie par taille décroissante, puis serveurs actifs avant les quittés
        guild_sizes.sort(key=lambda x: (-x[1], not x[3], x[0]))
        top10 = guild_sizes[:10]
        top10_lines = []
        for idx, (name, size, g_id, is_active) in enumerate(top10, 1):
            display_name = self.obfuscate_text(name, mask_ids)
            id_str = f" `{g_id}`" if not mask_ids else ""
            top10_lines.append(f"#{idx} {display_name}{id_str} — {format_bytes(size)}")
        top10_text = "\n".join(top10_lines) if top10_lines else "*Aucune donnée serveur détectée.*"

        # --- TOP 5 DOSSIERS LES PLUS LOURDS (tous dossiers confondus) ---
        folder_sizes = {}
        # Ajoute les dossiers racine
        for path_str, size in report["root_breakdown"].items():
            folder_sizes[f"/data/{path_str}"] = size
        # Ajoute les dossiers internes cogs
        for path_str, size in report["cogs_breakdown"].items():
            folder_sizes[f"/cogs/{path_str}"] = size
        top5_folders = sorted(folder_sizes.items(), key=lambda x: x[1], reverse=True)[:5]
        # Le masquage d'ID ne s'applique pas aux chemins de fichiers/dossiers
        top5_lines = [f"{i+1}. `{path}` — {format_bytes(size)}" for i, (path, size) in enumerate(top5_folders)]
        top5_text = "\n".join(top5_lines) if top5_lines else "*Aucun dossier volumineux détecté.*"

        # Formatage de la répartition de la racine /data/ (top 5)
        root_lines = []
        for path_str, size in sorted(report["root_breakdown"].items(), key=lambda x: x[1], reverse=True)[:5]:
            root_lines.append(f"📁 `/{path_str}` — {format_bytes(size)}")
        root_text = "\n".join(root_lines) if root_lines else "*Aucune structure miroir détectée.*"

        # Formatage de la répartition interne /cogs/ (top 5)
        cogs_lines = []
        for path_str, size in sorted(report["cogs_breakdown"].items(), key=lambda x: x[1], reverse=True)[:5]:
            cogs_lines.append(f"📦 `/{path_str}` — {format_bytes(size)}")
        cogs_text = "\n".join(cogs_lines) if cogs_lines else "*Aucun stockage local interne détecté.*"

        # Calcul des volumes orphelins cumulés
        orphan_count = 0
        orphan_size = 0
        for g_id, size in report["guild_mapping"].items():
            guild = self.bot.get_guild(g_id)
            if guild is not None:
                continue  # Serveur encore présent
            # Vérifie si l'ID correspond à un utilisateur encore présent
            user = self.bot.get_user(g_id)
            if user is not None:
                continue  # Utilisateur encore présent
            # Ignore les fichiers/dossiers images ou .json nécessaires
            # (On ne peut pas savoir ici, mais on peut ignorer les .json standards)
            # Pour un calcul plus précis, il faudrait scanner les fichiers, mais ici on ne compte que les guilds/users vraiment orphelins
            orphan_count += 1
            orphan_size += size

        total_combined = report["root_total"] + report["cogs_total"]

        description = (
            f"### 🏆 Top 10 Serveurs Consommateurs\n{top10_text}\n\n"
            f"### 📦 Top 5 Dossiers les plus lourds\n{top5_text}\n\n"
            f"### 📊 Métriques Consolides du Stockage\n"
            f"• Empreinte disque totale : {format_bytes(total_combined)}\n"
            f"• Volume Racine `/data/` : {format_bytes(report['root_total'])}\n"
            f"• Volume Interne `/cogs/` : {format_bytes(report['cogs_total'])}\n"
            f"• Statut Nettoyage Auto : {f'🟢 **Actif (15m)**' if self.loop_enabled else '🔴 **Désactivé**'}\n"
            f"• Visibilité des Données : {f'🔒 **Masquage ID (Spoiler)**' if mask_ids else '🔓 **Affichage Complet**'}\n\n"
            f"### 📂 Analyse Racine (Top /data/)\n{root_text}\n\n"
            f"### 🧬 Stockages Internes détectés (Top /cogs/)\n{cogs_text}\n\n"
            f"### 👻 Analyse Résiduelle\n"
            f"• Entités orphelines identifiées : `{orphan_count}`\n"
            f"• Espace mort nettoyable : {format_bytes(orphan_size)}\n\n"
            f"💡 _Analysez un contexte spécifique sans afficher de fichiers bruts avec :_ `/data id_serveur:<id>`."
        )
        return self.create_custom_embed(guild, author, "🛡️ Super-Administration & Analyse de l'Écosystème Stockage", description)

    # ==============================================================================
    # --------------------------- HYBRID COMMAND DEFINITION ------------------------
    # ==============================================================================

    @commands.hybrid_command(name="data", description="[Owner] Analyse quantitative, cartographie et purge de l'arborescence des données.")
    @app_commands.describe(id_serveur="Optionnel : ID d'un serveur précis pour calculer son poids (Dossiers/Fichiers) global.")
    @commands.is_owner()
    async def data_command(self, ctx: commands.Context, id_serveur: Optional[str] = None):
        await ctx.defer(ephemeral=True)

        if not ctx.interaction:
            try:
                await ctx.message.delete()
            except Exception:
                pass

        # Mode Contextuel : Analyse quantitative focalisée sur une entité

        if id_serveur:
            if not id_serveur.isdigit():
                return await ctx.send("❌ L'identifiant fourni doit être strictement numérique (Snowflake Discord).", ephemeral=True)

            g_id = int(id_serveur)
            g_obj = self.bot.get_guild(g_id)
            file_count, total_size = self.analyze_single_guild(g_id)

            # Recherche des fichiers/dossiers les plus lourds pour ce serveur
            file_list = []
            for target_dir in [ROOT_DATA_DIR, COGS_DIR]:
                if not target_dir.exists():
                    continue
                for root, _, files in os.walk(target_dir):
                    root_path = Path(root)
                    for f in files:
                        fp = root_path / f
                        if str(g_id) in root_path.parts or fp.stem == str(g_id) or fp.stem.startswith(f"{g_id}_"):
                            try:
                                size = fp.stat().st_size
                                file_list.append((str(fp), size))
                            except Exception:
                                pass
            # Trie et sélectionne les 5 plus lourds
            top5_files = sorted(file_list, key=lambda x: x[1], reverse=True)[:5]
            top5_lines = [f"{i+1}. `{path}` — {format_bytes(size)}" for i, (path, size) in enumerate(top5_files)]
            top5_text = "\n".join(top5_lines) if top5_lines else "*Aucun fichier/dossier volumineux détecté.*"

            desc_detailed = (
                f"**Nom de la structure :** {g_obj.name if g_obj else 'Serveur Externe / Historique'}\n"
                f"**Identifiant unique :** `{g_id}`\n"
                f"**Présence du Bot :** {'✅ Connecté' if g_obj else '❌ Absent (Données Résiduelles)'}\n\n"
                f"### 📦 Empreinte Cumulée (Racine + Internes)\n"
                f"• Nombre de fichiers assignés : `{file_count}`\n"
                f"• Volume total consommé : {format_bytes(total_size)}\n\n"
                f"### 🗂️ Top 5 fichiers/dossiers les plus lourds\n{top5_text}"
            )
            embed_detail = self.create_custom_embed(ctx.guild, ctx.author, f"🔍 Analyse Quantitative — ID {id_serveur}", desc_detailed)
            return await ctx.send(embed=embed_detail, ephemeral=True)

        # Mode Général : Tableau de bord de l'architecture de stockage globale
        view = DataControlView(self, ctx.author)
        embed = self.generate_main_embed(ctx.guild, ctx.author, view.mask_ids)
        await ctx.send(embed=embed, view=view, ephemeral=True)

    # ==============================================================================
    # ----------------------- BOUCLE AUTOMATIQUE DE NETTOYAGE ----------------------
    # ==============================================================================

    @tasks.loop(minutes=15.0)
    async def cleanup_task(self):
        """Cycle périodique de nettoyage si l'option est configurée sur actif."""
        if not self.loop_enabled:
            return
        await self.bot.wait_until_ready()
        self.execute_global_cleanup()

    @cleanup_task.before_loop
    async def before_cleanup_task(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(DataControlCog(bot))