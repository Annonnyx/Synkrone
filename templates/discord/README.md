# templates/discord

Catalogue de commandes Discord (modération, fun, configuration, etc.). Base pour un builder plus tard, pas un bot « Guillaume ».

- Lancer depuis ce dossier : `pip install -r requirements.txt` puis `python main.py`.
- Clés `.env` : voir `.env.example` (`DISCORD_TOKEN`, `PREFIX`, clés Twitch/YouTube, `VERSION`).
- Préfixe global : panelbot (`cogs/DEV/panelbot/bot_config.json`) puis `PREFIX` du `.env`.
- Catégories d’aide : `cogs/help.py` (Propriétaire, Configuration, ADMIN, Modération, Public).

Dépendances pip : uniquement `discord.py`, `python-dotenv`, `aiohttp`, `Pillow`.

Retour : [README racine](../../README.md).
