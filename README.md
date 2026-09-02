# Synkrone

**synkrone.app** héberge et facilite la création de projets, et les présente.

Tout le site se teste **en local**, un seul processus Node. Pas de Docker, pas de Postgres/Mongo/Redis, pas de VPS.

Les données restent sur le disque :

- médiathèque → `apps/ui/data.json` + `apps/ui/uploads/`
- catalogue → fichiers de `templates/discord/`

## Lancer (local)

Il faut **Node.js** (v22 va). Puis, à la racine du dépôt :

```bash
npm install --prefix apps/www
npm start
```

→ [http://127.0.0.1:3668/hub](http://127.0.0.1:3668/hub)  
→ [http://127.0.0.1:3668/ui/](http://127.0.0.1:3668/ui/)  
→ [http://127.0.0.1:3668/sharing/](http://127.0.0.1:3668/sharing/)

Mots de passe ui / sharing : `PASSWORD` dans `apps/ui/.env`, `MDP` dans `apps/sharing/.env` (sinon les remplir dans `apps/www/.env`, voir `.env.example`).

Le hub charge Tailwind / Font Awesome depuis internet (CSS uniquement). Le reste ne sort pas de la machine.

Tuiles PM2 / Code / dashbot / etc. : pas branchées en local.

## Bot Discord (optionnel, pas besoin pour tester le site)

Le catalogue se parcourt dans `/sharing/` sans lancer Python.

Pour faire tourner le bot, il parle **à Discord** (inévitable) : `templates/discord/.env` avec `DISCORD_TOKEN`, puis `pip install -r requirements.txt && python main.py`.
