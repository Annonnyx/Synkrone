# Synkrone

**synkrone.app** — en local, un seul `npm start` : site public + panel d’hébergement. Le site est la porte d’entrée ; le panel est servi sur `/hebergement`.

Le site public stocke JSON + SQLite. Le panel a besoin de **Postgres** (déjà sur `:5432` en local) pour les comptes / services.

## Lancer

Il faut **Node.js** (v22 va). À la racine du dépôt :

```bash
npm install --prefix apps/www
npm install --prefix dashboard/Orbital-hebergeur
npm start
```

Écoute **127.0.0.1:3668** (le panel Next tourne en interne et est proxifié).

| URL | Rôle |
| --- | --- |
| [http://127.0.0.1:3668/](http://127.0.0.1:3668/) | **Site public** (Accueil, Discord/bots, Minecraft, Admin, Équipe, CGU, contact, roulette, bump, me, dashbot UI) |
| [http://127.0.0.1:3668/hebergement](http://127.0.0.1:3668/hebergement) | **Panel d’hébergement** (bots, Minecraft, web, Krônes) |
| [http://127.0.0.1:3668/vux/](http://127.0.0.1:3668/vux/) | Page Vux + téléchargement `Vux.exe` |
| [http://127.0.0.1:3668/hub](http://127.0.0.1:3668/hub) | Hub interne |
| [http://127.0.0.1:3668/ui/](http://127.0.0.1:3668/ui/) | Médiathèque interne |
| [http://127.0.0.1:3668/sharing/](http://127.0.0.1:3668/sharing/) | Explorateur template Discord |

Mots de passe ui / sharing : `PASSWORD` dans `apps/ui/.env`, `MDP` dans `apps/sharing/.env` (sinon les remplir dans `apps/www/.env`, voir `.env.example`).

OAuth Discord : optionnel. Copier `apps/www/.env.example` → `apps/www/.env` et remplir les clés seulement si tu veux tester le login. Sans clés, les pages restent consultables.

Le hub charge Tailwind / Font Awesome depuis internet (CSS uniquement). Le reste ne sort pas de la machine.

Tuiles PM2 / Code / status : pas branchées en local (VPS).

## Public vs interne

- **Public** : `Synkrone/test/synkrone_authdiscord` (HTML + APIs JSON dans `data/`).
- **Vux** : `Synkrone/html/vux` (page + `Vux.exe`, stats SQLite locales).
- **Interne** : `apps/www` (hub), `apps/ui`, `apps/sharing`. Ne pas les supprimer.

Les bots Python (`bots/`, `Synkrone/bots/vax`) ne sont pas lancés avec le site. Les fiches Discord du site suffisent.

## Bot Discord (optionnel, pas besoin pour tester le site)

Le catalogue se parcourt dans `/sharing/` sans lancer Python.

Pour faire tourner le bot, il parle **à Discord** (inévitable) : `templates/discord/.env` avec `DISCORD_TOKEN`, puis `pip install -r requirements.txt && python main.py`.
