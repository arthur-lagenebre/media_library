---
name: tech-debt-audit
description: >
  Audit de dette technique de tout le dépôt, lancé par l'utilisateur : produit
  TECH_DEBT_AUDIT.md avec des constats sourcés (fichier:ligne), une gravité,
  un coût, et une section obligatoire « semble mauvais mais volontaire ».
  Use only when the user runs /tech-debt-audit or asks for a debt audit, a
  codebase health check or an architecture review of the whole repo.
disable-model-invocation: true
---

# tech-debt-audit

Un audit délibéré et franc de **tout** le dépôt. Il cherche ce qui est réellement défaillant, pas une liste de bonnes pratiques génériques : pas de « dans l'ensemble le code est bien structuré », pas de flatterie. Adapté du skill `tech-debt-audit` de ksimback, resserré sur ce dépôt (Python pur, scripts + `libraries/`, tags lus par `media_hub`).

Tu ne modifies aucun fichier du dépôt sauf `TECH_DEBT_AUDIT.md`, et tu ne le commites pas sans demande : il se relit d'abord.

## Principes

- **`fichier:ligne` pour tout constat concret.** « Le code a tendance à… » ne compte pas. Un constat sans citation est une impression.
- **Lis avant de juger** : ce qui paraît faux isolément porte parfois la charge (fichiers Windows, partages réseau, NAS en Python 3.8).
- **Ce qui est tranché ne se rouvre pas.** `docs/TODO.md` consigne ce qui a été corrigé ou décidé, et pourquoi (par exemple les `.orig` gardés par `--repair`). Un point qui y est tranché va dans « semble mauvais mais volontaire », pas dans les constats, sauf fait nouveau.
- **Pas de refonte.** Des changements précis et bornés, jamais « réécrire X ».
- **Pas de remplissage.** Une catégorie sans rien de notable : « Rien de notable ».

## Phase 1 : s'orienter (obligatoire)

1. Lis `README.md`, `docs/TODO.md`, `docs/agents.md`, `.github/workflows/tests.yml`.
2. Cartographie : `scripts/<Domaine>/` (points d'entrée), `libraries/common|video|music|books/`, `tests/`.
3. `git log --oneline -100` et `git log --since="6 months ago" --name-only --pretty=format:` pour voir où ça bouge.
4. Mesure : les 20 plus gros fichiers et les 20 les plus modifiés ; leur intersection est là où la dette se cache. Complexité des fonctions avec `crapper` (`D:\Projets\ub-tools\bin`, lancé depuis la racine), doublons avec `dryer`. S'ils manquent, dis-le et continue.
5. Écris un modèle mental de l'architecture en un ou deux paragraphes avant de continuer. S'il contredit le README, c'est déjà un constat.

## Phase 2 : auditer

Cherche avec `Grep` et des commandes de lecture. Dimensions, avec ce qui compte ici :

1. **Décomposition** : fichiers et fonctions trop gros, logique testable restée dans un script au lieu de `libraries/`, duplication entre scripts ou entre `video` et `music` (ce qui sert aux deux descend dans `common`), code mort.
2. **Cohérence** : plusieurs façons de faire la même chose (écriture de fichier, client HTTP, lecture d'un tag, bilan et code de sortie). Un script qui court-circuite `rename.py`, `report.py`, `tools.py` ou `textfile`.
3. **Invariants** : écriture possible en simulation ; renommage sans `apply_renames` ; original effacé avant le contrôle du résultat ; `except` qui avale une erreur sans la compter dans le bilan ; `shell=True` ; clé TMDB hors `.env`.
4. **Contrat avec `media_hub`** : noms et formats de tags (`MUSICBRAINZ_ALBUMID`, tag `TMDB`…), signatures des lecteurs. Vérifie dans `../media_hub` ce qui est réellement lu (s'il n'est pas là, dis-le).
5. **Tests** : fonctions critiques non testées, tests qui vérifient l'implémentation et non le comportement, tests sautés, tests qui dorment pour de vrai, fabriques dupliquées.
6. **Portabilité** : syntaxe ou API postérieure à Python 3.8 ; chemins ou fins de ligne propres à Windows ; casse des noms de fichiers ; console Windows sans `cli.setup_console()`.
7. **Réseau et ressources** : délais d'attente absents, nouvelles tentatives sans borne, intervalle MusicBrainz et User-Agent, caches hors de la médiathèque, fichiers provisoires laissés derrière une exception.
8. **Gestion d'erreurs** : exceptions avalées ou trop larges, erreurs affichées mais non comptées, messages qui ne disent pas quel fichier est en cause.
9. **Documentation** : README ou docstring d'en-tête qui ne disent plus ce que fait le script, options absentes, commentaires qui contredisent le code voisin.

Dépôt de plus de 50 000 lignes ou plus de cinq modules : confie un module par sous-agent en parallèle (dimensions, citation obligatoire) et fusionne. Ici (~12 000 lignes), lis toi-même.

## Phase 3 : livrable

Écris `TECH_DEBT_AUDIT.md` à la racine :

- **Résumé** : 10 puces au plus, classées par impact.
- **Modèle mental** de l'architecture telle qu'elle est.
- **Tableau des constats** : `ID | Catégorie | Fichier:ligne | Gravité (critique / haute / moyenne / basse) | Coût (S/M/L) | Description | Recommandation`. Vise 15 à 40 constats ; au-delà, c'est du bruit.
- **Les 5 à corriger si on n'en corrige qu'un petit nombre**, avec un plan de PR (chacune livrable et verte seule) et la preuve attendue : suite intacte, et comparaison ancien / nouveau pour un refactor.
- **Gains rapides** : coût S × gravité moyenne ou plus, en cases à cocher.
- **Semble mauvais mais volontaire** : ce que tu as envisagé de signaler et écarté, avec la raison. **Section obligatoire** : vide, c'est que tu n'as pas assez regardé.
- **Questions au mainteneur** : ce que tu ne peux pas classer entre dette et choix.

Si `TECH_DEBT_AUDIT.md` existe déjà, lis-le d'abord : marque les constats corrigés `RÉSOLU`, mets à jour les autres, étiquette les nouveaux `NOUVEAU`.

## Compte rendu

En quelques lignes : nombre de constats par gravité, les trois qui comptent le plus, ce que tu n'as pas pu vérifier (vrais fichiers, NAS, `media_hub` absent, Python 3.8 seulement jugé par la CI). Ne corrige rien de ton propre chef : chaque correction se propose en PR séparée.
