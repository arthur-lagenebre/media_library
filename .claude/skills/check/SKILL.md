---
name: check
description: >
  Vérifie le dépôt avant un commit ou une PR : toute la suite de tests, le
  découpage de libraries/, la compatibilité Python 3.14 et l'absence de secret.
  Use when the user runs /check or asks to verify the repo before pushing.
---

# check

Ce que la CI fera à la poussée (Windows + Linux, Python 3.14 + 3.15), fait avant, en local.

## 1. Les tests

```powershell
python -m unittest discover -s tests -t .
```

Rapporte le résultat **exact** (nombre de tests, échecs, erreurs, sautés). Un `OK (skipped=N)` se dit tel quel. En cas d'échec, lis le test avant de conclure : la cause est dans le code ou dans le test, et tu ne modifies jamais un test pour le faire passer sans l'avoir dit.

`tests/test_architecture.py` est dans la suite : il échoue dès qu'un import remonte entre `common`, `video`, `music` et `books`.

## 2. Python 3.14

Le minimum est Python 3.14 : la syntaxe et les API récentes sont permises. La CI teste aussi la 3.15 ; une API retirée ou dépréciée en 3.15 (avertissement `DeprecationWarning` dans la sortie des tests) se signale `fichier:ligne`.

## 3. Aucun secret, aucune dépendance

- `git status` : le `.env` ne doit pas apparaître ; aucune clé TMDB en clair dans le diff.
- Aucun `import` hors bibliothèque standard et hors `libraries.*`.

## 4. Documentation

Une option, un script ou un comportement nouveau doit se retrouver dans le `README.md` (tableau des scripts, section d'utilisation) et dans le docstring d'en-tête du script.

## Rapport

Une ligne par point (1 à 4) : OK, ou le problème avec `fichier:ligne`. Termine par « prêt à pousser » ou la liste de ce qui bloque. Ne corrige rien de ton propre chef : rapporte.
