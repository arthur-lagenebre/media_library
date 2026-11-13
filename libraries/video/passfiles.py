"""Les fichiers qui accompagnent un passage de Movies/Metadata.py : le journal et les fichiers de décisions.

- metadata.log : le lien TMDB de chaque film trouvé, et en fin de fichier ceux qui n'en ont pas ;
- metadata.ok : les films dont l'utilisateur a vérifié l'association, dont les doutes ne sont plus signalés ;
- metadata.collections : les titres de collection arrêtés avec lui ;
- metadata.titles : la casse des titres de film arrêtée avec lui (voir casing.py).

Le journal n'est écrit qu'avec --log FICHIER. Les trois autres se rangent à côté de lui, ou à la racine de --dir sans --log.
"""

import re
from datetime import datetime
from pathlib import Path

from libraries.common import cli, textfile

from .tmdb import movie_url


def log_path(root_dir, args):
    """Le journal : le fichier donné par --log, sinon metadata.log à la racine de --dir (qui n'est alors pas écrit).

    metadata.ok, metadata.collections et metadata.titles sont rangés à côté : ils suivent donc --log (utile quand la médiathèque est en lecture seule).
    """
    log = getattr(args, "log", None)
    return Path(log) if log else Path(root_dir) / "metadata.log"


APPROVED_NAME = "metadata.ok"
MOVIE_ID_RE = re.compile(r"/movie/(\d+)")
LEADING_ID_RE = re.compile(r"\s*(\d+)\b")


def approved_path(root_dir, args):
    """Le fichier des films validés, rangé avec le journal."""
    return log_path(root_dir, args).with_name(APPROVED_NAME)


def read_approved(path):
    """Identifiants TMDB des films dont tu as vérifié l'association : {id, ...}.

    Une ligne par film, '#' commence un commentaire. L'identifiant s'écrit seul ("1437733") ou en lien TMDB, tel que le journal le donne : on peut y recopier la ligne d'un film, ou son seul lien. Un fichier absent ou illisible ne valide rien.

    C'est ce qui permet de faire taire un doute sans épingler l'identifiant dans le NOM du fichier : le nom reste propre, et le fichier survit aux renommages.
    """
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return set()
    approved = set()
    for line in text.splitlines():
        line = line.split("#", 1)[0]
        found = MOVIE_ID_RE.search(line) or LEADING_ID_RE.match(line)
        if found:
            approved.add(int(found.group(1)))
    return approved


COLLECTIONS_NAME = "metadata.collections"
COLLECTIONS_HEADER = ("# Titres de collection arrêtés avec toi : 'nom TMDB => titre inscrit dans le film'.\n"
                      "# Une ligne par collection ; '#' en début de ligne = commentaire. Modifie le titre à ta guise,\n"
                      "# ou supprime la ligne pour que la question soit reposée.\n")


def collections_path(root_dir, args):
    """Le fichier des titres de collection, rangé avec le journal."""
    return log_path(root_dir, args).with_name(COLLECTIONS_NAME)


def read_collections(path):
    """{nom TMDB de collection: titre à inscrire} lu dans metadata.collections ; un fichier absent ou illisible ne décide rien."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    titles = {}
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        name, sep, title = line.partition("=>")
        if sep and name.strip() and title.strip():
            titles[name.strip()] = title.strip()
    return titles


def _remember(path, name, title, header, label):
    """Consigne une réponse tout de suite : une interruption plus loin ne doit pas la perdre."""
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        new = not Path(path).exists()
        with open(path, "a", encoding="utf-8", newline="") as f:
            f.write((header if new else "") + f"{name} => {title}\n")
    except OSError as e:
        print(f"      [{label}] non écrit : {e}")


def remember_collection(path, name, title):
    _remember(path, name, title, COLLECTIONS_HEADER, COLLECTIONS_NAME)


TITLES_NAME = "metadata.titles"
TITLES_HEADER = ("# Casse des titres arrêtée avec toi : 'titre TMDB => titre inscrit dans le film'.\n"
                 "# Une ligne par titre ; '#' en début de ligne = commentaire. Modifie le titre à ta guise,\n"
                 "# ou supprime la ligne pour que la question soit reposée.\n")


def titles_path(root_dir, args):
    """Le fichier de la casse des titres, rangé avec le journal."""
    return log_path(root_dir, args).with_name(TITLES_NAME)


def read_titles(path):
    """{titre TMDB: titre à inscrire} lu dans metadata.titles : le même format que metadata.collections."""
    return read_collections(path)


def remember_title(path, name, title):
    _remember(path, name, title, TITLES_HEADER, TITLES_NAME)


def write_log(root_dir, journal, args, report):
    """Écrit le journal du passage : un lien TMDB par film, les vides à la fin.

    Le terminal defile et se perd ; ce fichier reste. Les films sans lien sont groupés en fin de fichier : ce sont eux qui demandent quelque chose. Comme la fiche, il n'est pas réécrit quand seul son horodatage changerait. Sans --log, rien n'est écrit.
    """
    if not getattr(args, "log", None):
        return
    out = log_path(root_dir, args)
    trouves = [(nom, mid, st) for nom, mid, st in journal if mid]
    vides = [(nom, st) for nom, mid, st in journal if not mid]
    largeur = min(max((len(nom) for nom, _, _ in journal), default=0), 70)

    lignes = [f"# Metadata.py - {Path(root_dir).resolve()}", f"# {datetime.now():%Y-%m-%d %H:%M} - {cli.mode_label(args)}", f"# {report.matched}/{report.total} film(s) associé(s)", ""]
    for nom, movie_id, statut in trouves:
        lignes.append(f"{nom:<{largeur}}  {movie_url(movie_id)}" + (f"  {statut}" if statut else ""))
    if vides:
        lignes += ["", f"# --- sans lien ({len(vides)}) ---"]
        lignes += [f"{nom:<{largeur}}  {statut}" for nom, statut in vides]

    text = "\n".join(lignes) + "\n"
    if textfile.same(out, text, skip_lines=2):
        print(f"[log] {out.name} inchangé")
        return
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        textfile.write(out, text)
    except OSError as e:
        print(f"[log] {out.name} non écrit : {e}")
        return
    print(f"[log] {out.name} écrit ({len(trouves)} lien(s), {len(vides)} sans lien)")
