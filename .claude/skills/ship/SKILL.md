---
name: ship
description: >
  Livre le travail en cours : vérifications, branche, commits, push et pull
  request au format du dépôt. Use only when the user runs /ship or explicitly
  asks to commit, push or open a PR.
disable-model-invocation: true
---

# ship

Le dépôt avance par **branches thématiques** (`movies-log-dir`, `music-discography`…) fusionnées par pull request sur `main` (`Merge pull request #43 from arthur-lagenebre/movies-collection-title`). La CI tourne à chaque push, sur toutes les branches.

## Étapes

1. **Vérifier** : `/check`. Ne continue pas si un point bloque.
2. **Branche** : si on est sur `main`, crée d'abord une branche courte en kebab-case qui nomme le sujet (`<domaine>-<sujet>` : `music-discography`, `movies-collection-title`). Jamais de commit direct sur `main`.
3. **Commits** : petits, ordonnés, un sujet chacun. Message **en anglais**, forme `<Script ou module> <option éventuelle>: <ce qui change, à l'impératif ou au présent>` — par exemple `Movies/Metadata.py --log-dir: choose where metadata.log is written`, `Discography.py: complete an artist's folder with its missing albums from MusicBrainz`. Le corps dit pourquoi, ce qui a changé, et comment c'est prouvé (tests ajoutés). Ajoute les lignes d'attribution demandées par l'environnement.
4. **Ne commite jamais** `.env`, un cache, un `metadata.log` ou un fichier de la médiathèque. Relis `git status` avant `git add` et ajoute les fichiers un par un, pas `git add -A`.
5. **Push** de la branche (`git push -u origin <branche>`), puis **PR** vers `main` avec `gh pr create` : titre court dans la même forme que les commits, description qui dit le *pourquoi*, ce qui change pour l'utilisateur, et la preuve (tests). Termine la description avec la ligne d'attribution demandée par l'environnement.
6. Donne le lien de la PR. Ne fusionne pas : c'est à l'utilisateur de le faire une fois la CI verte.

## Garde-fous

- Pas de `--force`, pas de `--no-verify`, pas de réécriture d'un historique déjà poussé.
- Si la CI échoue après le push, rapporte l'échec et sa cause (`gh run view --log-failed`) au lieu de pousser un correctif à l'aveugle.
