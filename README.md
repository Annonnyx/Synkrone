# Synkrone

**synkrone.app** héberge et facilite la création de projets, et les présente.

Premier chantier prévu ensuite : des bots Discord. **Le builder n’est pas dans ce dépôt pour l’instant.**

Un seul processus Node sert le hub, la médiathèque et l’explorateur du catalogue.

## Carte

| Chemin | Rôle |
|---|---|
| [apps/www](apps/www/) | Processus unique (`npm start`, port **3668**) — hub `/hub` |
| `/ui/` | Médiathèque |
| `/sharing/` | Explorateur du catalogue Discord |
| [templates/discord](templates/discord/) | Catalogue de commandes (Python, à part) |

Tuiles `dashbot` / `me` / `bump` / `app` / `cloud` / `status` : toujours placeholders.

## Lancer

Les `.env` de `apps/www`, `apps/ui` et `apps/sharing` sont lus au démarrage (www ne remplace pas `PORT` s’il est déjà défini). Voir [apps/www/.env.example](apps/www/.env.example).

```bash
cd apps/www && npm install && npm start
# http://localhost:3668/hub
# http://localhost:3668/ui/
# http://localhost:3668/sharing/

cd templates/discord && pip install -r requirements.txt && python main.py
```

Les secrets déjà poussés dans d’anciens commits git sont à considérer comme exposés.
