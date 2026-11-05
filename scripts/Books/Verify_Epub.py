#!/usr/bin/env python3
r"""
Verify_Epub.py - Contrôle les .epub d'un dossier, en lecture seule.

Un .epub est un zip qui obéit à quelques règles que beaucoup de lecteurs font semblant d'ignorer et qu'un seul refuse un jour : "mimetype" en première entrée, stocké sans compression ; un conteneur qui désigne un .opf ; un manifeste dont chaque fichier existe ; un ordre de lecture qui ne cite que le manifeste ; du XHTML bien formé. Un livre qui s'ouvre sur l'ordinateur peut ne pas s'ouvrir sur la liseuse : ce contrôle le dit avant.

Sans outil externe : ce n'est pas EpubCheck (ni schéma EPUB 3, ni CSS, ni accessibilité), seulement ce qui fait qu'un livre s'ouvre ou non. Ce qu'il contrôle :
  - l'archive : zip lisible, somme de contrôle (CRC) de chaque entrée, entrées en double, noms dangereux ("/", "..") ;
  - mimetype : présent, première entrée, stocké, sans champ "extra", contenu exact ;
  - le conteneur et l'.opf : titre, langue, identifiant unique, version, manifeste (fichiers présents, ids uniques), spine, navigation (EPUB 3 : document "nav" et dcterms:modified ; EPUB 2 : toc) ;
  - chaque XHTML et chaque NCX du manifeste : XML bien formé ;
  - les résidus (__MACOSX, .DS_Store, Thumbs.db, calibre_bookmarks.txt...), la date « zéro » de Calibre (0101-01-01) et les éléments Dublin Core vides.

Rien n'est réparé : le script nomme chaque livre en défaut, et sort en code 1. Clean_Epub.py répare ce qui se répare sans rien perdre (résidus, mimetype, doublons, fiche de l'.opf) ; un livre dont des fichiers manquent ou dont le XML est cassé se remplace.

Usage :
  python Verify_Epub.py --dir "D:\Livres"                       # contrôle de tous les .epub
  python Verify_Epub.py --dir "D:\Livres\Romans" --no-recursive # cet étage seul

Options : --no-recursive --log (défaut : verification_epub.log à la racine de --dir)

Aucune dépendance externe, aucune dépendance pip, aucun accès réseau : ce script ne parle qu'aux fichiers.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # pour importer libraries
from libraries.books import epubhealth  # noqa: E402
from libraries.common import cli, verify  # noqa: E402
from libraries.common.report import Report  # noqa: E402

EXTENSIONS = (".epub",)
RAPIDE = "archive, mimetype, conteneur, .opf et XHTML de chaque livre"
REMEDE = "Clean_Epub.py répare les résidus, le mimetype, les doublons et la fiche de l'.opf ; le reste (fichiers manquants, XML cassé, archive abîmée) se remplace : nouveau téléchargement, sauvegarde."
NOTE = "Ce contrôle n'est pas EpubCheck : il ne valide ni le schéma EPUB 3, ni le CSS, ni l'accessibilité."
SEPARATEUR = "\n" + " " * 11      # les défauts d'un même livre s'alignent sous le premier


def parse_args():
    p = argparse.ArgumentParser(description="Contrôle les .epub d'un dossier, en lecture seule (récursivement par défaut).")
    p.add_argument("--dir", required=True, help="dossier à contrôler")
    p.add_argument("--no-recursive", action="store_true", help="ne contrôle que les livres posés directement dans --dir, sans descendre dans les sous-dossiers")
    p.add_argument("--log", default=None, help="fichier journal (défaut : verification_epub.log à la racine de --dir)")
    args = p.parse_args()
    args.full = False                      # un seul niveau de contrôle ; verify.* le demande
    return args


def check(chemin, _complet):
    """Ce qui cloche dans le livre, un défaut par ligne, ou "" s'il est sain."""
    return SEPARATEUR.join(d.message for d in epubhealth.audit(chemin))


def main():
    cli.setup_console()
    args = parse_args()
    racine, fichiers = verify.locate(args, EXTENSIONS)
    verify.announce(racine, fichiers, args, "livre", RAPIDE, RAPIDE)

    debut = time.time()
    defauts = verify.check_all(fichiers, racine, check, False)
    rapport = Report(total=len(fichiers), diffs=len(defauts))

    verify.summarize(rapport, time.time() - debut, args, "livre", REMEDE, NOTE)
    verify.write_log(Path(args.log) if args.log else racine / "verification_epub.log", racine, len(fichiers), defauts, "livre",
                     RAPIDE, RAPIDE, not args.no_recursive, False)
    return rapport.exit_code


if __name__ == "__main__":
    sys.exit(main())
