# media_library

[![Tests](https://github.com/arthur-lagenebre/media_library/actions/workflows/tests.yml/badge.svg)](https://github.com/arthur-lagenebre/media_library/actions/workflows/tests.yml)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![Généré par Claude Code](https://img.shields.io/badge/G%C3%A9n%C3%A9r%C3%A9%20par-Claude%20Code-D97757?logo=claude&logoColor=white)](https://claude.com/claude-code)

Outils personnels pour étiqueter une médiathèque à partir de [TMDB](https://www.themoviedb.org) pour les films et les séries, en français, et de [MusicBrainz](https://musicbrainz.org) pour la musique : les métadonnées sont écrites **directement dans les fichiers** — `.mkv`, `.flac`, `.mp3` — (sans ré-encodage ni remux, c'est quasi instantané), pour que chaque fichier reste autonome. Les livres, BD, comics et mangas portent déjà leur fiche (`ComicInfo.xml`, `.opf`) : ils ne sont pas modifiés.

**media_library est l'atelier** : il nettoie, renomme, convertit et étiquette, mais ne produit **aucune page**. La médiathèque se *lit* depuis [media_hub](../media_hub), le serveur du NAS, qui réutilise les lecteurs de tags de `libraries/` (MKV, FLAC, MP3, CBZ, EPUB) sans rien écrire dans les fichiers.

| Script | Rôle |
| --- | --- |
| [scripts/Movies/Metadata.py](scripts/Movies/Metadata.py) | Étiquette des films : titre, date de sortie **française**, synopsis, casting, genres, jaquette, noms de pistes  |
| [scripts/TV_Shows/Metadata.py](scripts/TV_Shows/Metadata.py) | Idem pour une série, saison par saison, |
| [scripts/Music/Metadata.py](scripts/Music/Metadata.py) | Étiquette des albums `.flac` et `.mp3` depuis MusicBrainz : tags à la Picard, identifiants, pochette ; ReplayGain et paroles restent en place |
| [scripts/Music/Cover.py](scripts/Music/Cover.py) | Embarque dans les pistes le fichier `cover.jpg` / `cover.png` du dossier de chaque album — les pochettes seules, aucun tag touché, sans Internet ; `--candidates` (avec Internet) dépose dans `_covers/` les pochettes entre lesquelles choisir |
| [scripts/Music/Discography.py](scripts/Music/Discography.py) | Pose dans le dossier de chaque artiste la pochette `1997 - OK Computer.jpg` (ou un fichier vide `1997 - OK Computer` sans pochette) de chaque album qu'il a sorti d'après MusicBrainz et que la médiathèque n'a pas ; les albums possédés ne sont jamais touchés |
| [scripts/TV_Shows/Rename_Episodes.py](scripts/TV_Shows/Rename_Episodes.py) | Renomme les épisodes en `{numéro} - {titre TMDB}.ext`, sous-titres compris |
| [scripts/Movies/Rename_Movies.py](scripts/Movies/Rename_Movies.py) | Renomme les dossiers de films en `Titre (Année)`, avec épinglage de l'id TMDB |
| [scripts/Music/Rename_Tracks.py](scripts/Music/Rename_Tracks.py) | Renomme les pistes des albums `.flac` et `.mp3` en `{numéro} - {titre MusicBrainz}.flac` (ou `.mp3`), paroles `.lrc` comprises |
| [scripts/Maintenance/Verify_Files.py](scripts/Maintenance/Verify_Files.py) | Contrôle la structure Matroska des `.mkv` d'un dossier, et remultiplexe ceux qui sont abîmés |
| [scripts/Converters/Video/Avi_To_Mkv.py](scripts/Converters/Video/Avi_To_Mkv.py) | Remultiplexe les `.avi` en `.mkv` sans réencodage, sous-titres adjacents compris |
| [scripts/Converters/Video/Mp4_To_Mkv.py](scripts/Converters/Video/Mp4_To_Mkv.py) | Idem pour les `.mp4`, en gardant les langues de pistes que le fichier déclare déjà |
| [scripts/Converters/Music/Wav_To_Flac.py](scripts/Converters/Music/Wav_To_Flac.py) | Encode les `.wav` en `.flac`, sans perte et vérifié : le son décodé des deux fichiers doit avoir la même empreinte |

Les scripts qu'on lance vivent sous [scripts/](scripts/), rangés par domaine ; le reste est interne :

```text
scripts/Movies/        étiquetage et renommage des films
scripts/TV_Shows/      la même chose pour les séries
scripts/Music/         étiquetage et renommage des albums, depuis MusicBrainz, pochettes, albums manquants
scripts/Maintenance/   contrôle et réparation des fichiers, sans rapport avec TMDB
scripts/Converters/    conversions qui précèdent l'étiquetage : Video/ (conteneur .mkv) et Music/ (.wav en .flac)
libraries/common/      ce qui ne dépend d'aucun domaine : cache, ligne de commande, bilan d'un passage, noms de fichiers, renommage
libraries/video/       tout ce qui touche aux films et aux séries
libraries/music/       tout ce qui touche à la musique
libraries/books/       tout ce qui touche aux livres : lecture des `.cbz` et `.epub`, étagère
tests/                 les tests
```

[libraries/common/](libraries/common/) porte ce qui ne dépend d'aucun domaine : cache disque, ligne de commande, bilan d'un passage, noms de fichiers, renommage sans perte, tri des titres. [libraries/video/](libraries/video/) porte l'accès TMDB, la lecture/écriture des `.mkv`, l'analyse des noms de fichiers. [libraries/music/](libraries/music/) porte l'accès MusicBrainz, la lecture/écriture des `.flac` et des `.mp3`, la reconnaissance des albums, le catalogue et les albums manquants. `video` et `music` ne se connaissent pas : chacun n'emprunte qu'à `common` (un test le vérifie). Aucune dépendance pip : uniquement la bibliothèque standard.

## Prérequis

- Python 3.8 ou plus récent — de quoi tourner aussi sur un NAS, avec le Python qu'il fournit
- [MKVToolNix](https://mkvtoolnix.download) (`mkvpropedit`, `mkvmerge`, `mkvextract`) — obligatoire pour écrire
- [FFmpeg](https://ffmpeg.org) (`ffprobe`) — facultatif : débit audio dans le nom des pistes, détection des fichiers dont la durée ne correspond pas à l'épisode, et contrôle de la durée après conversion d'un `.avi` ou d'un `.mp4` ; **requis** (avec `ffprobe`) pour `Wav_To_Flac.py`, qui encode et compare le son

```powershell
winget install MoritzBunkus.MKVToolNix
winget install Gyan.FFmpeg
```

`Rename_Episodes.py` et `Rename_Tracks.py` n'ont besoin d'aucun de ces outils : ils ne touchent qu'aux noms de fichiers. `Music/Metadata.py` non plus : il lit et écrit les `.flac` et les `.mp3` lui-même, et MusicBrainz ne demande aucune clé.

## Clé TMDB

Copier `.env.example` en `.env` à la racine et y renseigner la clé (themoviedb.org → Paramètres → API). Le `.env` n'est jamais commité, et sert à tous les scripts du dépôt.

```text
TMDB_KEY=votre_cle
```

C'est la **seule** source : ni variable d'environnement, ni constante dans les scripts. Le fichier est cherché en remontant depuis le dossier du script, donc tous s'en servent sans qu'on ait rien à exporter. La clé v3 (hexadécimale) comme le token de lecture v4 (JWT) fonctionnent.

## Utilisation

**Tous les scripts démarrent en simulation** : rien n'est écrit tant que `--apply` n'est pas passé. `--verify` (les `Metadata.py`) compare l'état des fichiers à TMDB sans rien modifier.

### Films

`--dir` est parcouru **récursivement**, aussi profond qu'il y a des dossiers : films à plat, dossiers de saga (`DCEU/01 - Man of Steel.mkv`) et étages intermédiaires (`Batman/Nolan Trilogy/…`) cohabitent. Un **dossier n'est jamais un film** : il ne compte ni ne se traite, il range. Il prête seulement son nom au film qu'il contient quand il n'en contient qu'un — c'est là que vit le titre dans `Inception (2010)/film.mkv`. Partout ailleurs c'est le nom du **fichier** qui parle, et les dossiers au-dessus viennent en **renfort** — du plus proche au plus lointain : `Resident Evil/Animation/3 - Vendetta.mkv` cherche `Vendetta` (qui donne *V pour Vendetta*…), puis `Resident Evil Vendetta`. Le renfort ne l'emporte que si le titre trouvé contient à la fois le dossier et ce qu'on cherchait. À titre égal, TMDB classant par popularité, une fiche portant **exactement** le titre cherché passe devant (`Blade` doit rendre *Blade*, pas *Blade II*).

Un sous-titre dont le **nom** dit « forcé » alors que le drapeau manque se voit poser le drapeau — sinon le renommer d'après ses drapeaux effacerait l'information. Et quand une piste reste **ambiguë** (un « forcé » non transposable parce qu'une autre piste porte déjà le drapeau, ou deux pistes de même langue qui porteraient le même nom), le film n'est **pas traité du tout** : rien n'est modifié, la raison s'affiche sous `[NON TRAITE]`, et le bilan les compte.

Une piste audio qui se déclare **audiodescription** (drapeau malvoyant) ou **commentaire** le dit dans son nom — `E-AC-3 5.1 640 kb/s AD`, `AC-3 2.0 Commentary` — et n'est jamais choisie comme piste par défaut. Une audiodescription est souvent encodée exactement comme la piste qu'elle double : sans l'étiquette, les deux porteraient le même nom.

Quand plusieurs fiches TMDB écrivent le **même titre autrement** (« Les Quatre Fantastiques » et « Les 4 Fantastiques »), ou quand plusieurs portent le **même titre** (« Dracula » en rend trois), le film est mis de côté et la question est posée **à la fin du passage**, dans le terminal : candidats numérotés, `Entrée` garde le premier, `i` laisse le film de côté, `q` arrête les questions. Une suite (« Iron Man 2 ») n'est pas une variante et ne demande rien. Hors terminal (sortie redirigée, CI) les films restent de côté au lieu de bloquer ; `--no-ask` reprend l'ancien comportement.

Le titre et l'année sont lus dans le nom — `Inception (2010)`. Un film coupé en plusieurs fichiers (`CD1`/`CD2`) est étiqueté en entier. Bandes-annonces, making-of et dossiers de bonus (`Extras`, `Featurettes`…) sont reconnus à leur **nom** : le poids ne décide de rien, un dessin animé de 1 Go est un film autant qu'un remux de 28 Go. Un préfixe d'ordre de saga (`1 - Iron Man`, demi-numéros compris : `1.5 - Dark Fury`) est reconnu et inscrit comme numéro dans la collection.

Un dossier de saga n'est pas une réunion de fichiers indépendants : c'est une **collection** TMDB. Les dossiers à plusieurs films sont donc réexaminés de l'intérieur — la saga est cherchée par le nom du dossier, puis parmi celles vers lesquelles plusieurs films pointent déjà, et les fichiers lui sont appariés un à un (numéro d'ordre d'abord, ressemblance ensuite ; chaque film ne servant qu'une fois, les titres muets héritent de ce qui reste). Un homonyme qui existe dans 900 000 films n'existe pas dans une saga de 26. `--no-saga` s'en passe.

À chaque passage, un **journal** est écrit à la racine de `--dir` : `metadata.log` donne le lien TMDB de chaque film trouvé, et groupe en fin de fichier ceux qui n'en ont pas — non associés, ou laissés en attente d'une réponse.

```powershell
python scripts\Movies\Metadata.py --dir "D:\Films"                    # simulation
python scripts\Movies\Metadata.py --dir "D:\Films" --apply            # applique
python scripts\Movies\Metadata.py --dir "D:\Films\Dune (2021)" --tmdb-id 438631 --apply   # force l'id
python scripts\Movies\Metadata.py --dir "D:\Films" --no-tag --artwork --apply   # folder.jpg seul, sans toucher aux .mkv
```

L'identifiant TMDB retenu est **inscrit dans le film** (tag Matroska `TMDB`, au format `movie/1234`) : au passage suivant il est relu, plus rien n'est cherché, et l'association survit au renommage. La relecture ne coûte un sous-processus de plus que sur les fichiers qui déclarent des tags — une médiathèque jamais étiquetée ne paie rien. Priorité : `--tmdb-id`, puis l'identifiant épinglé dans le **nom**, puis celui lu dans le **fichier**, puis la recherche.

Chaque association est aussi **contrôlée** : un film dont la durée sur le disque sort de 75 % à 135 % de celle que TMDB annonce (à 10 min près), ou dont la fiche n'a presque aucun vote, est signalé sous `/!\`, repris en fin de passage sous `A VERIFIER` et marqué dans `metadata.log`. Les versions longues et l'accélération PAL passent ; un court métrage homonyme pris pour le film, ou un fichier tronqué, ne passent pas. Un identifiant épinglé dans le nom n'est jamais remis en cause. Pour faire taire un doute **sans toucher au nom du fichier**, ajoute le film à `metadata.ok`, rangé avec `metadata.log` : une ligne par film, l'identifiant seul ou son lien TMDB recopié du journal, `#` pour un commentaire (`https://www.themoviedb.org/movie/1437733  # Bref. De bons amis, ok`). Ses doutes ne sont plus signalés ; rien d'autre ne change.

Comme toute la reconnaissance repose sur les noms, [Rename_Movies.py](scripts/Movies/Rename_Movies.py) le remet d'aplomb depuis TMDB — et `--pin-id` y écrit l'identifiant, après quoi plus rien n'est cherché ni ne peut se tromper :

```powershell
python scripts\Movies\Rename_Movies.py --dir "D:\Films"                    # simulation
python scripts\Movies\Rename_Movies.py --dir "D:\Films" --apply --pin-id   # renomme et épingle
```

Un préfixe d'ordre de saga est conservé (`1 - Iron Man` → `1 - Iron Man (2008)`), les sous-titres suivent leur film en mode « `.mkv` à plat », et un identifiant déjà épinglé n'est jamais retiré.

Sous `--no-tag`, les films ne sont lus que pour leurs tags et leur durée, en Python pur : **ni MKVToolNix ni FFmpeg** ne sont nécessaires, et l'identifiant TMDB inscrit dans chaque film est repris sans recherche. La fiche n'est réécrite que si son contenu change, et le journal `metadata.log` reste à la racine de `--dir`. De quoi la tenir à jour en tâche planifiée sur le NAS qui héberge les films.

### Séries

Un sous-dossier `Saison N` par saison, les `.mkv` dedans, préfixés par leur numéro d'épisode. `--dir` peut aussi pointer directement sur un dossier de saison.

```powershell
python scripts\TV_Shows\Rename_Episodes.py --dir "D:\Series\Ma Serie" --apply
python scripts\TV_Shows\Metadata.py --dir "D:\Series\Ma Serie" --apply
```

Les sous-titres posés à côté d'une vidéo (`.srt`, `.ass`, `.idx`/`.sub`…) sont renommés avec elle, en conservant ce qui suit le nom : `S01E02.fr.forced.srt` → `02 - Titre.fr.forced.srt`.

La série est identifiée par une recherche TMDB sur le nom du dossier (celui du parent si `--dir` pointe sur une saison) : le résultat retenu est affiché, et les cas douteux — reboot portant le même nom, titre éloigné de la recherche — sont signalés. `--tmdb-id 1234` force l'identifiant quand la recherche se trompe ou ne trouve rien — et pour que ce soit **durable**, écris-le dans le nom du dossier : `Ma Serie [tmdbid-1396]` (ou `{tmdb-1396}`). Même chose côté films : `Dune (2021) [tmdbid-438631]`.

Un dossier `Specials` (ou `Hors-serie`) est traité comme la saison 0 de TMDB, où vivent les épisodes spéciaux.

### Musique

Un album est un dossier qui contient des `.flac` ou des `.mp3` — lui ou ses dossiers de disque (`CD1`, `CD2`…, `Disc 2 - Bonus`, ou nommés d'après le disque, `1 - La fête est finie` / `2 - Épilogue`, tant qu'ils se suivent de 1 à n) ; les dossiers d'artiste au-dessus ne font que ranger. La référence est [MusicBrainz](https://musicbrainz.org), ouvert et **sans clé**, et les pochettes viennent de [Cover Art Archive](https://coverartarchive.org).

```powershell
python scripts\Music\Metadata.py --dir "D:\Musique"                  # simulation
python scripts\Music\Metadata.py --dir "D:\Musique" --apply          # applique
python scripts\Music\Metadata.py --dir "D:\Musique" --verify         # vérifie seulement
```

L'album est cherché d'après les tags `ALBUM` et `ALBUMARTIST` de ses fichiers, puis d'après le nom du dossier (`1994 - Born Dead`, `Daft Punk - Discovery (2001) FLAC [...]`). Un album existe en autant d'**éditions** qu'il a connu de pressages, et seules comptent celles qui ont **exactement autant de pistes** que le dossier a de fichiers : c'est ce qui départage l'album du single de même nom, le CD de 17 pistes du pressage de 16. Parmi elles, l'édition officielle, en autant de disques que le dossier en range, sur CD ou en numérique plutôt qu'en vinyle — celui de *Human After All* a bien dix pistes, mais en deux faces de cinq —, de l'année annoncée, du pays `--country` (défaut `FR`), à défaut européenne puis mondiale. Deux albums **différents** du même titre qui tiennent tous les deux font l'objet d'une question en fin de passage, comme pour les films.

Chaque fichier est placé sur sa piste par son numéro (tags, dossier de disque, nom de fichier), puis par son titre ; un titre ou une durée qui ne collent pas sont signalés. Un seul fichier sans piste et l'album n'est **pas traité** : à moitié étiqueté, il aurait l'air fait.

Les tags s'écrivent sous les noms qu'emploie [Picard](https://picard.musicbrainz.org) : titre, artistes crédités et noms de tri, numéros et totaux, dates, genres votés, label, catalogue, code-barres, identifiants MusicBrainz. Un album déjà passé par Picard ne diffère en général que par ses genres. **Tout ce qui ne vient pas de MusicBrainz reste en place** : ReplayGain, paroles, notes, ISRC. Une clé n'est gérée que si la base lui donne une valeur — un genre écrit à la main survit à un album sans genre, et `--no-genres` les laisse tous —, sauf celles qui décrivent l'édition (label, code-barres, identifiants), qui mentiraient si elles restaient d'une autre.

**Imposer le nom d'un artiste.** MusicBrainz écrit parfois le même artiste de plusieurs façons d'un album à l'autre (`H.F. Thiéfaine`, `Thiéfaine`, `Hubert Félix Thiéfaine`), et la fiche de la médiathèque en fait alors plusieurs artistes. Un fichier `artist.txt` dans le dossier d'artiste, dont la première ligne est le nom voulu, le fixe pour tous les albums qu'il range (le plus proche de l'album l'emporte) ; `--artist "Hubert-Félix Thiéfaine"` fait de même pour tout `--dir`. Seul le crédit qui désigne cet artiste est réécrit, dans `ARTIST` et `ALBUMARTIST` : `Thiéfaine / Mairet` devient `Hubert-Félix Thiéfaine / Mairet`. Quand MusicBrainz crédite cet artiste « feat. » des invités de tout l'album (`Ultra Vomit feat. A, B, C`), ces invités disparaissent des tags : `Ultra Vomit`, comme sur les autres albums ; l'invité d'une seule piste reste. Les noms de tri restent ceux de MusicBrainz, et un album dont aucun crédit ne ressemble au nom le signale et garde ceux de MusicBrainz.

La pochette est ajoutée aux fichiers qui n'en ont pas : celle de l'édition, à défaut celle du release group. Une pochette déjà embarquée est gardée ; `--replace-cover` la remplace, `--no-cover` n'en ajoute aucune, `--image-size` choisit `250`, `500`, `1200` (défaut) ou `original`. `--verify` n'exige que la pochette que l'édition déclare : celle du release group peut ne pas exister.

**La pochette téléchargée devient un fichier.** Quand `Metadata.py` télécharge une pochette (aux pistes qui n'en ont pas, ou toutes avec `--replace-cover`), il l'enregistre aussi en `cover.jpg` — ou `cover.png`, selon l'image — dans le dossier de l'album, une seule fois par album et sans jamais écraser un fichier. C'est ce fichier que lira la fiche, et que l'on peut remplacer à la main ; au passage suivant il l'emporte sur toute autre pochette et plus rien n'est téléchargé. `--no-cover-file` s'en abstient. Le passage habituel suffit donc :

```powershell
python scripts\Music\Rename_Tracks.py --dir "D:\_Music" --apply
python scripts\Music\Metadata.py --dir "D:\_Music" --replace-cover --apply
```

Les albums qui portent déjà une pochette que `Metadata.py` n'a pas besoin de remplacer n'ont pas de fichier : `Cover.py --extract` (plus bas) leur en écrit un.

**Choisir soi-même la pochette.** Un fichier `cover.jpg` (ou `.jpeg`, `.png` ; aussi `folder`, `front`, `album`, `albumart`, casse libre) posé dans le dossier de l'album — à côté de `CD1`, `CD2`… pour un album en plusieurs disques — est **la** pochette de l'album : elle l'emporte sur celle que portent déjà les pistes (un scan recto-verso, une image mal cadrée) comme sur celle de Cover Art Archive. La fiche de la médiathèque la lit directement, et `Metadata.py` l'embarque à la place de tout téléchargement. Pour n'appliquer **que** les pochettes, sans toucher à un tag ni interroger MusicBrainz :

```powershell
python scripts\Music\Cover.py --dir "D:\Musique"                  # simulation
python scripts\Music\Cover.py --dir "D:\Musique" --apply          # embarque cover.jpg dans chaque piste
python scripts\Music\Cover.py --dir "D:\Musique" --verify         # vérifie seulement (code 1 s'il reste un écart)
python scripts\Music\Cover.py --dir "D:\Musique\Eminem\1996 - Infinite" --apply   # un seul album
```

**Récupérer les pochettes des albums déjà traités.** Leurs pistes portent une pochette, mais leur dossier n'a pas de fichier : `--extract` l'écrit en `cover.jpg` (ou `cover.png`, selon l'image) dans le dossier de chaque album qui n'en a pas. Un fichier cover existant n'est jamais remplacé, et les pistes ne sont pas touchées. Les albums sans pochette exploitable sont listés à la fin ; une image qui n'est pas typée « face » (un dos, un livret) est signalée.

```powershell
python scripts\Music\Cover.py --dir "D:\Musique" --extract            # simulation
python scripts\Music\Cover.py --dir "D:\Musique" --extract --apply    # écrit les cover.jpg manquants
```

Le chemin pour corriger les mauvaises pochettes (recto-verso, mal cadrées) : extraire, ouvrir les `cover.jpg`, remplacer à la main ceux qui ne vont pas, puis embarquer avec `Cover.py --apply`.

**Choisir entre plusieurs pochettes.** `--candidates` retrouve l'édition de chaque album sur MusicBrainz (comme `Metadata.py` : l'identifiant déjà dans les pistes ou le nom du dossier, sinon la recherche) et télécharge dans un sous-dossier `_covers/` de l'album les pochettes de face que Cover Art Archive garde pour cette édition **et pour les autres éditions du même album** (12 au plus). Chaque nom dit d'où vient l'image : `01_FR-2013-CD_1200x1200.jpg` — le `01` est l'édition retenue, puis viennent les autres, les plus anciennes d'abord. Les images identiques entre elles ou au `cover.jpg` déjà là ne sont déposées qu'une fois ; rien n'est touché ailleurs (ni `cover.jpg`, ni les pistes), et un fichier déjà déposé n'est jamais écrasé. `--image-size`, `--country` et `--no-cache` se comportent comme pour `Metadata.py`.

```powershell
python scripts\Music\Cover.py --dir "D:\Musique\Eminem\1996 - Infinite" --candidates --apply   # dépose les pochettes dans _covers\
# ouvrir _covers\ dans l'Explorateur, copier la bonne image en cover.jpg dans le dossier de l'album
python scripts\Music\Cover.py --dir "D:\Musique\Eminem\1996 - Infinite" --apply                # l'embarque dans les pistes
python scripts\Music\Cover.py --dir "D:\Musique" --clean-candidates --apply                    # supprime les dossiers _covers
```

Un `cover.jpg` l'emporte sur un `cover.png` : si l'image choisie change de format, supprimer l'ancien fichier. Embarquer ne supprime jamais `_covers/` — un passage sur toute la médiathèque n'efface ainsi pas des candidates que l'on n'a pas encore regardées ; c'est `--clean-candidates` qui le fait (simulation sans `--apply`).

Une piste qui porte déjà exactement cette image n'est pas réécrite ; une autre image de face est remplacée, les images d'un autre type (dos, livret) sont gardées. Les albums sans fichier cover sont listés à la fin, pour savoir où en poser un. Seuls le JPEG et le PNG s'embarquent dans une piste : un `.webp`, `.gif` ou `.bmp` ne s'embarque pas dans un fichier audio (signalé). Une image de plus de 4 Mio est signalée, car l'Explorateur de Windows ne lit plus rien d'un `.flac` dont l'en-tête la dépasse.

L'identifiant de l'édition (`MUSICBRAINZ_ALBUMID`) est inscrit dans chaque fichier et relu au passage suivant. Priorité : `--mbid`, puis l'identifiant épinglé dans le nom du dossier (`2013 - Outrun [mbid-4e5d9f0c-09b6-42bf-b495-e2d7cc288bf6]`), puis celui que **tous** les fichiers déclarent, puis la recherche.

Aucun outil externe : le script lit et écrit lui-même les blocs du `.flac`. Tant que les tags tiennent dans le padding du fichier, seul l'en-tête est réécrit ; sinon — une pochette ajoutée, typiquement — le fichier est recopié à côté puis substitué, et le son ne bouge pas. La place laissée vide sur place est plafonnée à 64 Ko : l'Explorateur de Windows ne lit plus rien, ni tags ni miniature, d'un `.flac` dont le son commence au-delà de 4 Mio (mesuré à l'octet près), et c'est ainsi que les pistes de *Synthesis* avaient perdu leur pochette à l'affichage. Un fichier que son padding a fait passer au-delà est signalé par `--verify` et recopié par `--apply` ; une image embarquée assez lourde pour franchir seule la limite est signalée. Mesuré sur une médiathèque de 194 pistes : 167 écritures sur place, 27 recopies (les deux albums sans pochette), le son intact à l'octet près, et un `--verify` qui ne trouve plus rien ensuite ; sur un album recopié en entier, l'empreinte MD5 du son décodé par ffmpeg reste la même. Un fichier déjà conforme n'est jamais réécrit, d'où l'absence de `--skip-done`. MusicBrainz n'accepte qu'une requête par seconde : un premier passage coûte environ trois requêtes par album, les suivants sont servis par le cache. Un `.mp3` se traite de la même façon, avec les mêmes options : les tags vont dans son étiquette ID3v2, sous les noms de trames de Picard (`TXXX` « MusicBrainz Album Id »…, `UFID` pour l'enregistrement), les valeurs multiples — genres, labels, artistes — séparées par un octet nul, la pochette dans une trame `APIC`. Une étiquette ID3v2.3 est relue puis réécrite en 2.4, UTF-8 (l'Explorateur de Windows en lit titre, artiste, album, année, numéro de piste, genre et pochette) ; ses trames que le script ne gère pas — ReplayGain, paroles `USLT`, commentaires, notes — sont recopiées telles quelles. Un ID3v2.2, antérieur à 1999, est converti trame par trame en 2.4 (ce qui n'a pas d'équivalent est abandonné), et l'étiquette ID3v1 de fin de fichier n'est pas touchée. Tant que l'étiquette tient dans son padding, seule elle est réécrite ; sinon, ou si le fichier n'en avait pas, il est recopié à côté puis substitué, et le son reste identique à l'octet près. La durée d'un `.mp3` (lue dans l'en-tête Xing, sinon estimée sur le débit) sert, comme celle d'un `.flac`, à signaler une piste qui ne colle pas. Seuls les `.flac` et les `.mp3` sont écrits : un dossier de `.m4a`, `.ogg`… est signalé et laissé tel quel. Le journal `metadata.log` donne le lien MusicBrainz de chaque album.

Pour les noms de fichiers, [Rename_Tracks.py](scripts/Music/Rename_Tracks.py) est le pendant de `Rename_Episodes.py` : chaque piste prend le nom `{numéro} - {titre}.flac` que donne MusicBrainz, le numéro sur autant de chiffres dans tout l'album.

```powershell
python scripts\Music\Rename_Tracks.py --dir "D:\Musique"                 # simulation
python scripts\Music\Rename_Tracks.py --dir "D:\Musique" --apply         # renomme
```

L'album est reconnu exactement comme par `Metadata.py` — mêmes éditions, même placement des fichiers, mêmes questions en fin de passage — et un album dont un seul fichier ne trouve pas sa piste n'est pas renommé du tout. Passé après `Metadata.py`, il ne cherche plus rien : l'identifiant est dans les fichiers. Un album en plusieurs disques rangés à plat préfixe le disque (`2-01 - Alive 1997.flac`) ; rangés dans `CD1`, `CD2`…, chaque dossier repart de `01`. Un `/` dans un titre devient `-` (`Robot Rock - Oh Yeah`), et les paroles `.lrc` posées à côté suivent leur piste. Les dossiers ne bougent pas : leur nom reste celui qu'on leur a donné.

**Compléter la discographie.** [Discography.py](scripts/Music/Discography.py) compare chaque dossier d'artiste à ce que MusicBrainz sait de lui et pose, pour chaque album qui manque, un fichier `{année} - {titre}` à côté des albums rangés — là où l'artiste range les siens : son dossier, ou `Albums/` s'il y met les siens. C'est ce nom que lit la fiche de l'artiste pour montrer les albums à acquérir, avec leur pochette.

```text
Radiohead/
    1995 - The Bends/            <- un album possédé : jamais touché
    1997 - OK Computer.jpg       <- un album qui manque, avec sa pochette
    2000 - Kid A                 <- un album qui manque, sans pochette (fichier vide, sans extension)
```

**La pochette** est celle que Cover Art Archive garde pour l'album (l'édition que MusicBrainz juge représentative), en JPEG ou PNG, à la taille `--image-size` — 1200 px par défaut : assez pour la fiche, sans les scans d'origine de plusieurs Mo (`original` les prend). Faute de pochette, ou si le service ne répond pas, l'album est un fichier vide sans extension ; au passage suivant, ce fichier vide est **remplacé par la pochette** si elle existe alors. Une image ou un fichier non vide déjà là n'est jamais remplacé. `--no-covers` ne télécharge rien et ne pose que des fichiers vides ; la simulation ne télécharge rien non plus.

L'artiste est reconnu par l'identifiant MusicBrainz que portent les fichiers de ses albums (`Metadata.py` l'y a inscrit), sinon par recherche sur le nom du dossier — ou la première ligne de son `artist.txt`. Plusieurs artistes de ce nom sont une **question** de fin de passage (`--no-ask` garde le premier). Un album compte pour possédé qu'il soit un dossier, un fichier (vide, avec ou sans `.txt`) ou une image `AAAA - Titre` : seul le titre est comparé, l'année d'une réédition ou d'un autre format n'y change rien. Les sorties sans année sur MusicBrainz ne peuvent pas se nommer `AAAA - Titre` : elles sont comptées et laissées de côté.

Seuls les **albums** sont complétés par défaut ; `--cats` ajoute les `ep`, `single`, `live`, `compilation`, `soundtrack`, `remix`, `demo`, `other` (ou `all`), dont les fichiers vont dans un sous-dossier à leur nom (`EP/`, `Singles/`…) — celui où l'artiste range déjà les siens s'il existe. `--only "Radiohead"` ne complète que cet artiste, et crée son dossier s'il n'existe pas encore, sous le nom que lui donne MusicBrainz.

```powershell
python scripts\Music\Discography.py --dir "D:\Musique"                             # simulation
python scripts\Music\Discography.py --dir "D:\Musique" --apply                     # pose pochettes et fichiers vides
python scripts\Music\Discography.py --dir "D:\Musique" --only "Radiohead" --apply  # un artiste, créé au besoin
python scripts\Music\Discography.py --dir "D:\Musique" --cats album,ep --apply     # albums et EP
python scripts\Music\Discography.py --dir "D:\Musique" --no-covers --apply         # fichiers vides seulement
```

Un titre qui finit comme une extension (`Vol.2`) garde un `.txt` quand il n'a pas de pochette (`1999 - Vol.2.txt`) : sans lui, le nom serait lu comme `Vol` + `.2`. Les anciens `.txt` restent lus comme avant. Repasser le script ne pose que ce qui a manqué depuis, et il sort en **code 1** s'il reste un artiste sans fiche (introuvable, à confirmer, MusicBrainz injoignable) ou une écriture en échec.

### Livres, BD, comics et mangas

La bibliothèque est rangée **par section** — un dossier `Manga`, `BD`, `Comics`, `Artbook`, `Romans`… — et chaque section par **série** : un dossier par série (par auteur pour les romans) qui contient ses volumes, `.cbz` pour les bandes dessinées, `.epub` pour le reste. Un fichier posé seul dans une section (`Manuels/Un guide.epub`) est sa propre série, ceux de la racine forment la section « Autres », et les sous-dossiers d'une série (cycles, intégrales) en groupent les volumes à l'affichage.

Ces livres portent déjà leur fiche : `ComicInfo.xml` dans un `.cbz` (série, numéro, résumé, auteurs, éditeur, date, genres…), le `.opf` d'un `.epub` quand Calibre est passé par là. Il n'y a donc **rien à étiqueter** ici : media_library ne les modifie pas, et [media_hub](../media_hub) les lit (`libraries/books/`).

### Convertir les AVI

Un `.avi` ne sait rien porter : ni jaquette, ni synopsis, ni identifiant TMDB. Tant qu'un film reste dans ce conteneur, `Metadata.py` n'a nulle part où écrire — [Avi_To_Mkv.py](scripts/Converters/Video/Avi_To_Mkv.py) fait donc la passe qui précède l'étiquetage. Rien n'est réencodé : les pistes sont recopiées telles quelles, à la vitesse du disque, et l'image comme le son ressortent identiques.

```powershell
python scripts\Converters\Video\Avi_To_Mkv.py --dir "D:\Films"                          # simulation
python scripts\Converters\Video\Avi_To_Mkv.py --dir "D:\Films" --apply                  # convertit
python scripts\Converters\Video\Avi_To_Mkv.py --dir "D:\Films" --apply --delete-source  # + efface l'.avi vérifié
```

Les sous-titres posés à côté sont embarqués au passage, et leur **encodage est mesuré fichier par fichier** : `mkvmerge` suppose de l'UTF-8, alors qu'un `.srt` d'époque est en général en `windows-1252` — et le malentendu ne se voit qu'aux accents cassés, souvent une fois l'original effacé. La langue est lue dans le suffixe du nom (`Film.fr.srt` → `fre`), `--sub-lang` tranche pour ceux qui n'en ont pas, et un `.sub` est laissé à son `.idx`, qui l'embarque déjà. `--subs none` les ignore, `--subs require` ne convertit que les films qui en ont.

La **durée** du `.mkv` produit est comparée à celle de la source (`--tolerance`, 2 s par défaut) : c'est ce qui attrape un index AVI qui ment ou un flux mal recopié, que `mkvmerge` ne signale pas toujours. `--delete-source` n'efface l'original qu'après ce contrôle — et réclame donc `ffprobe`. Le `.mkv` s'écrit d'abord sous un nom provisoire (`Film.mkv.part`) et ne prend son nom qu'une fois ce contrôle passé : un échec de `mkvmerge`, un écart de durée ou un Ctrl-C ne laissent aucun `.mkv` tronqué, que le passage suivant aurait pris pour un film déjà converti — et `--overwrite` ne détruit l'ancien qu'au moment de le remplacer. Un `conversion.log` est écrit à la racine de `--dir`, et le script sort en **code 1** s'il reste un fichier non converti.

`--lang` donne la langue des pistes audio (`fre` par défaut, code ISO 639-2 à trois lettres), `--default-audio` et `--default-sub` posent les drapeaux « piste par défaut », `--title` inscrit le nom du fichier comme titre du segment, et `--output-dir` écrit ailleurs qu'à côté de la source. `--overwrite` remplace un `.mkv` déjà présent (sans lui, le fichier est passé), `--sub-charset` fixe l'encodage de repli des sous-titres qui ne sont pas en UTF-8 (`windows-1252` par défaut) et `--log` place le journal ailleurs qu'à la racine de `--dir`. Le `.mkv` obtenu est prêt pour [Metadata.py](scripts/Movies/Metadata.py), qui y écrira le reste.

### Convertir les MP4

Même passe pour les `.mp4`, avec [Mp4_To_Mkv.py](scripts/Converters/Video/Mp4_To_Mkv.py). Un `.mp4` sait porter une jaquette et quelques tags, mais à la mode iTunes : `Metadata.py` écrit des tags **Matroska**, et n'a donc nulle part où les poser tant que le film reste dans ce conteneur. Rien n'est réencodé non plus — les chapitres suivent, la jaquette et les tags iTunes sont laissés derrière, puisque `Metadata.py` les réécrit ensuite depuis TMDB.

```powershell
python scripts\Converters\Video\Mp4_To_Mkv.py --dir "D:\Films"                          # simulation
python scripts\Converters\Video\Mp4_To_Mkv.py --dir "D:\Films" --apply                  # convertit
python scripts\Converters\Video\Mp4_To_Mkv.py --dir "D:\Films" --apply --delete-source  # + efface le .mp4 vérifié
```

Une différence de fond avec les `.avi` : un `.mp4` **déclare souvent la langue de ses pistes**, là où un `.avi` n'en dit jamais rien. Elle est donc gardée telle quelle, et `--lang` ne sert qu'aux pistes qui n'en ont pas (`und`) — sans quoi un rip anglais correctement étiqueté ressortirait en français. `--force-lang` réétiquette tout, pour un fichier qui se trompe, et le bilan de chaque conversion dit quelles langues ont été conservées.

Les sous-titres **déjà dans le `.mp4`** (tx3g) sont recopiés par `mkvmerge` sans qu'on ait rien à demander, et comptent pour `--subs require` ; ceux posés à côté sont traités exactement comme pour un `.avi`, encodage mesuré fichier par fichier. Le reste est identique — contrôle de durée (`--tolerance`), `--delete-source` après vérification, code de sortie **1** s'il reste un fichier non converti — et le journal s'appelle `conversion_mp4.log`, pour ne pas écraser celui des `.avi` quand les deux passes visent le même dossier. Seule l'extension `.mp4` est prise : un `.m4v` est le même conteneur sous un autre nom, mais le renommer se voit, alors que l'embarquer en silence ne se verrait pas.

### Convertir les WAV en FLAC

Un `.wav` ne sait presque rien porter : ni pochette, ni identifiant MusicBrainz, des tags que la plupart des lecteurs ignorent — et il pèse en général près du double du même son en FLAC. [Music/Metadata.py](scripts/Music/Metadata.py) n'a donc nulle part où écrire tant qu'une piste reste dans ce conteneur : [Wav_To_Flac.py](scripts/Converters/Music/Wav_To_Flac.py) fait la passe qui précède l'étiquetage.

```powershell
python scripts\Converters\Music\Wav_To_Flac.py --dir "D:\Musique"                          # simulation
python scripts\Converters\Music\Wav_To_Flac.py --dir "D:\Musique" --apply                  # convertit
python scripts\Converters\Music\Wav_To_Flac.py --dir "D:\Musique" --apply --delete-source  # + efface le .wav vérifié
```

**FLAC plutôt que MP3** : c'est le seul des deux qui rende exactement le son d'origine. Un `.wav` sort d'un CD ou d'une captation, et il n'en existe souvent plus qu'une copie : l'encoder en MP3 jetterait pour toujours ce que l'oreille ne remarque pas aujourd'hui, alors qu'un `.flac` se transcode en MP3 le jour où il en faut un. `Metadata.py`, `Rename_Tracks.py` et `Recap.py` lisent les deux de la même façon.

« Sans perte » est **vérifié, pas supposé** : le son décodé du `.wav` et celui du `.flac` produit sont comparés par empreinte (MD5 des échantillons), et le `.flac` n'existe qu'à cette condition. `--delete-source` n'efface l'original qu'ensuite. Seuls les `.wav` en **entiers 16 ou 24 bits** sont pris : `ffmpeg` arrondirait en silence un `.wav` en virgule flottante ou en 32 bits, qui est donc laissé tel quel avec la raison au bilan. Comme pour les films, le `.flac` s'écrit d'abord sous un nom provisoire (`Piste.flac.part`) : un échec, une empreinte différente ou un Ctrl-C ne laissent aucun `.flac` tronqué, que le passage suivant aurait pris pour une conversion déjà faite.

Les tags du `.wav` (titre, artiste, album, année, numéro de piste…) suivent quand il en a ; `Metadata.py` les remplace ensuite depuis MusicBrainz, et ajoute la pochette. `--compression` (de 0 à 12, 8 par défaut) ne change que la taille et le temps de calcul, jamais le son. `--output-dir`, `--overwrite`, `--no-recursive` et `--log` fonctionnent comme pour les films. Un `conversion_flac.log` est écrit à la racine de `--dir`, et le script sort en **code 1** s'il reste un fichier non converti.

### Vérifier les fichiers

Un `.mkv` peut se lire du début à la fin et avoir le conteneur abîmé — une fin de fichier écrite à moitié après une coupure, par exemple. `mkvpropedit` s'en plaint alors à chaque passage (« erreur dans la structure du fichier Matroska à la position … ») et **rien d'autre ne le dit** : mesuré sur des fichiers volontairement cassés, `mkvmerge` (même en démultiplexant tout vers `NUL`) et `mkvinfo` se resynchronisent en silence et sortent en code 0.

```powershell
python scripts\Maintenance\Verify_Files.py --dir "D:\Films"                # contrôle rapide
python scripts\Maintenance\Verify_Files.py --dir "D:\Films\Ghibli" --full  # toute la chaîne, clusters compris
python scripts\Maintenance\Verify_Files.py --dir "D:\Films" --repair       # contrôle puis remultiplexe
python scripts\Maintenance\Verify_Files.py --dir "D:\Films" --no-recursive # cet étage seul
```

[Verify_Files.py](scripts/Maintenance/Verify_Files.py) suit lui-même la chaîne des éléments EBML, en lecture seule. Par défaut il s'en tient aux points de repère — l'index, la table Cues, la queue du fichier — dont le prix **ne dépend pas de la taille du film** : mesuré sur un partage réseau, 489 films et 4,49 To en 15 minutes (dont les deux tiers passés dans la lecture d'en-tête par `mkvmerge`). `--full` descend dans les clusters, mais lit chaque fichier en entier (compter ~10 s par Go sur un partage réseau) ; il voit alors tout ce que voit `mkvpropedit`, plus la troncature.

`--dir` est parcouru **récursivement**, comme partout ailleurs. `--no-recursive` s'en tient aux `.mkv` posés directement dedans : de quoi contrôler l'étage d'une médiathèque — les films rangés à plat — sans relire les dossiers de films qu'elle contient, ni les repasser après coup un par un.

`--repair` remultiplexe les fichiers en défaut : `mkvmerge` réécrit le film proprement à côté (sous le nom provisoire `Film.mkv.part`, effacé quoi qu'il arrive), le résultat est contrôlé à son tour, et l'original n'est remplacé que s'il ressort sain — identifiant TMDB, jaquette, titre du segment, noms de pistes et statistiques sont conservés. Au moindre échec l'original reste en place. Un `verification.log` est écrit à la racine de `--dir` (ou là où `--log` le place), et le script sort en **code 1** s'il reste un fichier abîmé.

### Options communes

`--verify` et `--skip-done` comparent aussi **les tags écrits** (synopsis, casting, genres, dates) à ce que TMDB donne aujourd'hui : un fichier étiqueté par une version plus ancienne, ou dont les tags ont été perdus, est signalé au lieu d'être déclaré conforme. Cette relecture coûte un appel à `mkvextract` par fichier, donc elle n'a lieu qu'avec ces deux options.

Les `Metadata.py` sortent en **code 1** s'il reste quelque chose à corriger — fichiers non conformes en `--verify`, écritures en échec en `--apply` — et le résument en dernière ligne, de quoi les enchaîner dans un script. Il en va de même pour ce qui reste **sans fiche** : un film ou un album que le script n'a pas pu associer, une saison ou un film pour lesquels TMDB n'a pas répondu, un album pour lequel MusicBrainz n'a pas répondu — `Movies/Metadata.py`, `Movies/Rename_Movies.py`, `TV_Shows/Metadata.py`, `TV_Shows/Rename_Episodes.py`, `Music/Metadata.py` et `Music/Rename_Tracks.py` sortent alors en code 1 et le disent sur une ligne `À CORRIGER`. Sans cela, une panne réseau pendant la tâche planifiée du NAS passerait pour un succès. Des fichiers qu'il reste à renommer, en simulation, n'en sont pas.

Les réponses de TMDB et de MusicBrainz sont gardées **7 jours** dans `%LOCALAPPDATA%\media_library\tmdb` et `…\musicbrainz` (`~/.cache/media_library/…` ailleurs) — jamais à côté de la médiathèque. Repasser sur une grosse collection ne refait donc pas tous les appels : mesuré sur 8 requêtes, 416 ms contre 56 ms. `--no-cache` ignore ce qui est en cache et le rafraîchit ; supprimer le dossier est sans conséquence, il se reconstruit tout seul.

`--skip-done` saute ce qui est déjà conforme, `--language` change la langue TMDB (défaut `fr-FR` ; c'est elle qui détermine le pays de la date de sortie retenue pour les films), et les `--no-*` (`--no-cover`, `--no-date`, `--no-audio-names`, `--no-sub-names`, `--no-flags`, `--no-stats`) désactivent chacun une catégorie d'écriture. Pour les séries, `--match-threshold` (de 0 à 1, `0.55` par défaut) règle le score minimal d'une association par titre — `Metadata.py` comme `Rename_Episodes.py` — et `--series-name` impose le nom de la série. La taille des images TMDB se règle par `--image-size` (jaquette), `--still-size` (vignettes d'épisodes), `--profile-size` (portraits du casting) et, pour les films, `--poster-size` (affiches du récap). `--help` liste le reste.

## Lire la médiathèque

media_library ne génère plus de pages. La lecture (web, TV, lecteur audio et visionneuse de livres) est le travail de **media_hub**, un serveur qui tourne sur le NAS : il indexe les dossiers en lisant les tags que ces scripts ont écrits (identifiant TMDB, synopsis, casting, jaquette, `MUSICBRAINZ_ALBUMID`, `ComicInfo.xml`…) et sert films, séries, animations, musique et livres. Le contrat entre les deux est donc **les fichiers eux-mêmes** : un fichier bien étiqueté ici se présente bien là-bas.

## Tests

```powershell
python -m unittest discover -s tests -t .
```

Ils tournent aussi sur chaque push et chaque PR (Windows et Linux, Python 3.8 et 3.13) via [GitHub Actions](.github/workflows/tests.yml).

Ils couvrent la partie qui casse en silence — analyse des noms, tags produits, comparaison à l'état visé, erreurs TMDB, cas tordus du renommage — sans réseau ni outil externe.

## Licence et données

Le code est publié sous licence [MIT](LICENSE).

Les données qu'il écrit dans les fichiers ont leurs propres conditions :

- This product uses the TMDB API but is not endorsed or certified by [TMDB](https://www.themoviedb.org). Les titres, synopsis, affiches et portraits des films et des séries viennent de TMDB.
- Les métadonnées musicales viennent de [MusicBrainz](https://musicbrainz.org), les pochettes de [Cover Art Archive](https://coverartarchive.org) (chacune garde la licence que son auteur lui a donnée).
- Les résumés d'artistes (`libraries/music/artistinfo.py`) viennent de Wikipédia, sous licence CC BY-SA.
- MKVToolNix et FFmpeg sont lancés comme programmes séparés, jamais intégrés au code : leurs licences ne s'appliquent pas à ce dépôt.
