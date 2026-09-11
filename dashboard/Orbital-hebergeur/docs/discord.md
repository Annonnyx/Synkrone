# Discord runtime

Wizard: General → Discord → Modules → Commands → Intents → Resources → Review.

The builder writes a **real discord.js v14 project** into the service volume:

```
package.json  index.js  config/bot.json  commands/<name>.js  .orbital/boot.sh
```

* Modules drive the generated command set and the computed gateway intents.
* `Enable slash commands` makes the bot register its commands with Discord via
  `REST.put(Routes.applicationCommands(...))` at boot.
* The token is injected as `BOT_TOKEN` only into that bot's container; the file
  system copy never contains it.
* Console commands are executed with `docker exec` inside the bot container.
