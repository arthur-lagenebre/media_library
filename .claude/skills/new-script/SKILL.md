---
name: new-script
description: >
  Crée un nouveau script de media_library dans le respect des conventions du
  dépôt (simulation par défaut, --apply, bilan et code de sortie, journal,
  console Windows, tests, README). Use when the user runs /new-script or asks
  to add a script to scripts/.
---

# new-script

Argument : ce que le script doit faire et le domaine (`Video/Movies`, `Video/TV_Shows`, `Video` à plat pour les conversions et les contrôles, `Music`). **Un dossier par domaine, pas de dossier par type d'action** : jamais de `Converters/` ni de `Maintenance/` ; un sous-dossier n'existe que lorsque deux scripts de même nom y cohabitent (`Video/Movies/Metadata.py` et `Video/TV_Shows/Metadata.py`). `tests/test_architecture.py` le vérifie.

## Avant d'écrire

1. Lis le script voisin le plus proche (`scripts/<Domaine>/…`) et `libraries/common/` (`cli.py`, `report.py`, `rename.py`, `filenames.py`, `textfile.py`, `tools.py`) : **réutilise, n'invente pas**. Ce qui sert à deux domaines va dans `libraries/common/`, ce qui est propre à un domaine dans `libraries/<domaine>/` ; le script ne garde que la ligne de commande et l'enchaînement.
2. Si la logique est réutilisable ou testable seule (association, analyse de noms, calcul), elle va dans `libraries/`, pas dans le script.

## Conventions à reprendre

- Nom en `Majuscule_Underscore.py` (`Avi_To_Mkv.py`), rangé dans le bon dossier de `scripts/`.
- En-tête : shebang `#!/usr/bin/env python3`, docstring `r"""` qui dit *pourquoi* le script existe, ce qu'il garantit, `Usage :` (simulation, `--apply`, variantes), `Options :`, `Dépendances EXTERNES :`. En français.
- `sys.path.insert(0, str(Path(__file__).resolve().parents[N]))` pour importer `libraries`, puis imports `# noqa: E402`.
- `argparse` : `--dir` requis ; `--apply` pour écrire (**défaut : simulation**) ; `--no-recursive` si le dossier se parcourt ; `--log FICHIER` pour garder le journal du passage : `journal.add_option(parser)` et `with journal.record(args.log):` autour du passage (`libraries/common/journal.py` recopie ce qui s'affiche ; sans `--log`, rien n'est écrit). Les scripts TMDB prennent la clé par `cli.resolve_tmdb_key()` (`.env` seulement) et passent par le cache.
- `cli.setup_console()` au démarrage de `main()`.
- Le bilan est un `Report` (`libraries/common/report.py`) : `sys.exit(report.exit_code)` et la ligne `report.epilogue()` quand quelque chose reste à corriger. Une erreur réseau ou un élément sans fiche **ne passe jamais pour un succès**.
- Rien n'est perdu en route : renommages via `libraries/common/rename.py`, écritures sous un nom provisoire (`partial_path`) puis contrôle avant de remplacer, outils externes via `run_tool` (liste d'arguments, jamais `shell=True`).
- Python 3.8 minimum, bibliothèque standard seule.

## Finir

1. Un fichier `tests/test_<sujet>.py` (unittest, sans réseau ni outil externe, dossier temporaire, noms de tests en français) : une simulation n'écrit rien, `--apply` écrit, un second passage ne change rien, le code de sortie est le bon.
2. Une ligne dans le tableau des scripts du `README.md` et une section d'utilisation si le script en mérite une.
3. `python -m unittest discover -s tests -t .` doit passer ; lance ensuite `/check`.
4. Ne commite pas : `/ship` s'en charge, quand on le demande.
