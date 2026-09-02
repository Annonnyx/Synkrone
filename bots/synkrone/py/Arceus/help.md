# Aide Commandes Economie

Ce document resume les commandes du systeme economie/collection situe dans `cogs/economie`.

## Fichiers et commandes

- `cogs/economie/profil.py`
  - `/profil [membre]`
  - Affiche balance, xp, niveau, total de captures, balls, superbonbons.

- `cogs/economie/pokedex.py`
  - `/pokedex`
  - Affiche les Pokemon possedes en pagination, sections Classique et Shiny.

- `cogs/economie/doublon.py`
  - `/doublon liste`
  - `/doublon relacher <pokemon_id> <shiny:true|false> <quantite>`
  - `/doublon combiner <pokemon_id> <shiny:true|false> <quantite_sets>`
  - Liste les doublons, permet de relacher contre des balls, ou de combiner 3 memes + superbonbon.

- `cogs/economie/sleep.py`
  - `/sleep deposer <inventory_id>`
  - `/sleep recuperer`
  - `/sleep statut`
  - Gestion de la garderie avec gain d'argent selon la duree.

- `cogs/economie/teams.py`
  - `/teams voir`
  - `/teams set <slot:1-3> <inventory_id>`
  - `/teams clear [slot]`
  - Configure la team de combat (max 3 Pokemon, Pokemon possedes uniquement).

- `cogs/economie/fight.py`
  - `/fight [adversaire]`
  - Combat simplifie avec vitesse, attaque/defense, critiques et efficacite des types.

- `cogs/economie/capture.py`
  - `!capture` (prefixe) ou `/capture`
  - Genere 1 Pokemon sauvage a capturer.
  - Boutons de balls sur une seule ligne: pokeball, superball, hyperball, masterball.
  - Chaque bouton affiche uniquement l'emoji et la quantite possedee, et est desactive si quantite = 0.
  - Limite anti-spam: 10 tentatives de capture par minute et par joueur.
  - Masterball = 100% de capture, autres balls ont un taux selon rarete/shiny/evolution.

- `cogs/economie/shop.py`
  - `!shop` ou `/shop`
  - Ouvre la boutique avec les prix et boutons d'achat rapide.
  - Achat direct possible: `!shop <ball> <quantite>` (ex: `!shop pokeball 10`).

- `cogs/economie/echange.py`
  - `/echange <utilisateur>`
  - Echange via Select menus + confirmation Accepter/Refuser.

- `cogs/economie/ecoadd.py`
  - `/ecoadd <cible> [balance] [pokeball] [superball] [hyperball] [masterball] [superbonbon] [pokemon_id] [shiny] [level] [quantite]`
  - Commande admin pour tests: ajoute ressources et/ou Pokemon.

- `cogs/economie/utils.py`
  - Fichier commun (non charge comme extension): DB SQLite, schema, helpers de service.

## Base de donnees

- Fichier SQLite: `data/economie/economy.db`
- Tables:
  - `users`
  - `inventory`
  - `daycare`
  - `teams`

## Comment tester rapidement

1. Lancer le bot:
   - `py main.py`

2. Alimenter un compte de test (admin):
   - `/ecoadd @Moi 1000 20 10 5 1 3 133 false 5 3`
   - Exemple ci-dessus: +1000 balance, balls, +3 superbonbons, 3 Evoli niveau 5.

3. Verifier l'etat du profil:
   - `/profil`

4. Verifier l'inventaire:
   - `/pokedex`
   - `/doublon liste`

5. Tester doublons:
   - `/doublon relacher 133 false 1`
   - `/doublon combiner 133 false 1`

6. Tester garderie:
   - `/sleep deposer <inventory_id>`
   - attendre un peu
   - `/sleep statut`
   - `/sleep recuperer`

7. Configurer team et combattre:
   - `/teams set 1 <inventory_id>`
   - `/teams set 2 <inventory_id>`
   - `/teams voir`
   - `/fight`

8. Tester echange:
   - `/echange @AutreJoueur`
   - selection des 2 Pokemon
   - confirmation via boutons Accepter/Refuser

9. Tester capture:
  - verifier que tu as des balls avec `/profil` ou ajouter avec `/ecoadd`
  - lancer `!capture`
  - cliquer une ball pour tenter la capture
  - verifier que l'inventaire change via `/pokedex`

10. Tester shop:
  - ajouter de l'argent: `/ecoadd @Moi 5000`
  - ouvrir la boutique: `!shop`
  - acheter en direct: `!shop pokeball 10`
  - verifier le stock et le solde: `/profil`

## Notes

- Les emojis des balls/superbonbon sont dans `cogs/economie/utils.py` (`BALL_EMOJIS`, `SUPERBONBON_EMOJI`).
- Pour les tests, commence par `/ecoadd` afin d'avoir des ressources et des Pokemon.
