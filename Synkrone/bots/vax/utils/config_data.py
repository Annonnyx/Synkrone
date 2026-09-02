"""
GESTIONNAIRE DE DONNÉES CENTRALISÉ
==================================
Gère la création, lecture, écriture et suppression des fichiers JSON
sous le dossier racine /data.

Utilisation :
    from utils.config_data import DataManager
    db = DataManager("public/utilitaires/data_snipe")
    data = db.load(guild_id)
"""

import os
import json
import shutil
from pathlib import Path

class DataManager:
    def __init__(self, relative_path: str):
        """
        Initialise le gestionnaire de données sur un dossier cible sous /data.
        :param relative_path: Chemin sous le dossier /data (ex: "public/utilitaires/data_snipe")
        """
        self.project_root = self._find_project_root()
        self.data_dir = os.path.join(self.project_root, "data", relative_path)
        self.path = self.data_dir
        self._ensure_dir_exists()

    def _find_project_root(self):
        """Trouve la racine du projet en remontant depuis ce fichier."""
        current = os.path.dirname(os.path.abspath(__file__))
        # Remonte 1 niveau depuis utils/ pour atteindre la racine
        return os.path.dirname(current)

    def _ensure_dir_exists(self):
        """S'assure que le dossier cible dans /data existe, sinon le crée."""
        os.makedirs(self.data_dir, exist_ok=True)

    def _get_path(self, target_id: int | str):
        """Retourne le chemin complet du fichier JSON pour une cible donnée."""
        return os.path.join(self.data_dir, f"{target_id}.json")

    def load(self, target_id: int | str) -> dict:
        """
        Charge les données d'un fichier (ex: guild_id ou user_id).
        Retourne un dictionnaire vide si le fichier n'existe pas.
        """
        path = self._get_path(target_id)
        if not os.path.exists(path):
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            # Compatibilite: certains fichiers migrés peuvent contenir un BOM UTF-8.
            try:
                with open(path, "r", encoding="utf-8-sig") as f:
                    return json.load(f)
            except Exception:
                return {}

    def save(self, target_id: int | str, data: dict):
        """
        Sauvegarde les données dans le fichier cible.
        Si le dictionnaire est vide, supprime automatiquement le fichier.
        """
        path = self._get_path(target_id)
        if not data:
            self.delete(target_id)
            return

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def delete(self, target_id: int | str):
        """Supprime le fichier lié à l'ID (ex: quand le bot quitte un serveur)."""
        path = self._get_path(target_id)
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception as e:
                print(f"[DataManager] Erreur lors de la suppression de {path}: {e}")

    def get_all_files(self):
        """Retourne la liste de tous les IDs ayant un fichier JSON dans ce dossier."""
        if not os.path.exists(self.data_dir):
            return []
        return [
            file.replace(".json", "")
            for file in os.listdir(self.data_dir)
            if file.endswith(".json")
        ]

    def delete_all(self):
        """Supprime entièrement le dossier géré (attention danger !)."""
        if os.path.exists(self.data_dir):
            shutil.rmtree(self.data_dir)
