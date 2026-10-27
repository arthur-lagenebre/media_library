# media_library

[![Tests](https://github.com/arthur-lagenebre/media_library/actions/workflows/tests.yml/badge.svg)](https://github.com/arthur-lagenebre/media_library/actions/workflows/tests.yml)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![Généré par Claude Code](https://img.shields.io/badge/G%C3%A9n%C3%A9r%C3%A9%20par-Claude%20Code-D97757?logo=claude&logoColor=white)](https://claude.com/claude-code)

Outils personnels pour étiqueter une médiathèque à partir de [TMDB](https://www.themoviedb.org) pour les films et les séries, en français, et de [MusicBrainz](https://musicbrainz.org) pour la musique : les métadonnées sont écrites **directement dans les fichiers** — `.mkv`, `.flac`, `.mp3` — (sans ré-encodage ni remux, c'est quasi instantané), pour que chaque fichier reste autonome. Les livres, BD, comics et mangas portent déjà leur fiche (`ComicInfo.xml`, `.opf`) : ils sont seulement **lus**, pour en tirer une fiche de la bibliothèque.

| Script | Rôle |
| --- | --- |
| [scripts/Movies/Metadata.py](scripts/Movies/Metadata.py) | Étiquette des films : titre, date de sortie **française**, synopsis, casting, genres, jaquette, noms de pistes ; fiche récap de la médiathèque |
| [scripts/TV_Shows/Metadata.py](scripts/TV_Shows/Metadata.py) | Idem pour une série, saison par saison, plus une fiche récap HTML |
| [scripts/Music/Metadata.py](scripts/Music/Metadata.py) | Étiquette des albums `.flac` et `.mp3` depuis MusicBrainz : tags à la Picard, identifiants, pochette ; ReplayGain et paroles restent en place |
| [scripts/Music/Cover.py](scripts/Music/Cover.py) | Embarque dans les pistes le fichier `cover.jpg` / `cover.png` du dossier de chaque album — les pochettes seules, aucun tag touché, sans Internet |
| [scripts/Music/Recap.py](scripts/Music/Recap.py) | Fiche HTML d'une médiathèque musicale, lue dans les tags des `.flac` et `.mp3` : un mur de pochettes par artiste, une fiche par album avec ses pistes et celles qui manquent, une fiche par artiste (membres, liens, résumé Wikipédia, via MusicBrainz) ; rien n'est écrit dans les fichiers |
| [scripts/TV_Shows/Recap_All.py](scripts/TV_Shows/Recap_All.py) | Régénère la fiche récap de toutes les séries d'une médiathèque, sans toucher aux épisodes |
| [scripts/TV_Shows/Index.py](scripts/TV_Shows/Index.py) | Sommaire de toutes les séries (dans `__Data__`, sous le nom de `--title`), chacune menant à sa fiche récap ; fait pour une tâche planifiée sur le NAS |
| [scripts/TV_Shows/Rename_Episodes.py](scripts/TV_Shows/Rename_Episodes.py) | Renomme les épisodes en `{numéro} - {titre TMDB}.ext`, sous-titres compris |
| [scripts/Movies/Rename_Movies.py](scripts/Movies/Rename_Movies.py) | Renomme les dossiers de films en `Titre (Année)`, avec épinglage de l'id TMDB |
| [scripts/Music/Rename_Tracks.py](scripts/Music/Rename_Tracks.py) | Renomme les pistes des albums `.flac` et `.mp3` en `{numéro} - {titre MusicBrainz}.flac` (ou `.mp3`), paroles `.lrc` comprises |
| [scripts/Books/Recap.py](scripts/Books/Recap.py) | Fiche HTML d'une bibliothèque de livres, BD, comics et mangas, lue dans les fiches intégrées aux `.cbz` et `.epub` : une page par série, couvertures, auteurs, tomes manquants ; rien n'est écrit dans les livres |
| [scripts/Maintenance/Verify_Files.py](scripts/Maintenance/Verify_Files.py) | Contrôle la structure Matroska des `.mkv` d'un dossier, et remultiplexe ceux qui sont abîmés |
| [scripts/Converters/Video/Avi_To_Mkv.py](scripts/Converters/Video/Avi_To_Mkv.py) | Remultiplexe les `.avi` en `.mkv` sans réencodage, sous-titres adjacents compris |
| [scripts/Converters/Video/Mp4_To_Mkv.py](scripts/Converters/Video/Mp4_To_Mkv.py) | Idem pour les `.mp4`, en gardant les langues de pistes que le fichier déclare déjà |
| [scripts/Converters/Music/Wav_To_Flac.py](scripts/Converters/Music/Wav_To_Flac.py) | Encode les `.wav` en `.flac`, sans perte et vérifié : le son décodé des deux fichiers doit avoir la même empreinte |

Les scripts qu'on lance vivent sous [scripts/](scripts/), rangés par domaine ; le reste est interne :

```text
scripts/Movies/        étiquetage et renommage des films
scripts/TV_Shows/      la même chose pour les séries
scripts/Music/         étiquetage et renommage des albums, depuis MusicBrainz, et leur fiche HTML
scripts/Books/         fiche HTML des livres, BD, comics et mangas
scripts/Maintenance/   contrôle et réparation des fichiers, sans rapport avec TMDB
scripts/Converters/    conversions qui précèdent l'étiquetage : Video/ (conteneur .mkv) et Music/ (.wav en .flac)
libraries/common/      ce qui ne dépend d'aucun domaine : cache, ligne de commande, bilan d'un passage, noms de fichiers, renommage
libraries/video/       tout ce qui touche aux films et aux séries
libraries/music/       tout ce qui touche à la musique
libraries/books/       tout ce qui touche aux livres : lecture des `.cbz` et `.epub`, étagère, pages HTML
tests/                 les tests
```

[libraries/common/](libraries/common/) porte ce qui ne dépend d'aucun domaine : cache disque, ligne de commande, bilan d'un passage, noms de fichiers, renommage sans perte, miniatures d'images, mise en page des fiches. [libraries/video/](libraries/video/) porte l'accès TMDB, la lecture/écriture des `.mkv`, l'analyse des noms de fichiers et les fiches HTML. [libraries/music/](libraries/music/) porte l'accès MusicBrainz, la lecture/écriture des `.flac` et des `.mp3`, la reconnaissance des albums et leur fiche HTML. `video` et `music` ne se connaissent pas : chacun n'emprunte qu'à `common` (un test le vérifie). Aucune dépendance pip : uniquement la bibliothèque standard.

## Prérequis

- Python 3.8 ou plus récent — de quoi tourner aussi sur un NAS, avec le Python qu'il fournit
- [MKVToolNix](https://mkvtoolnix.download) (`mkvpropedit`, `mkvmerge`, `mkvextract`) — obligatoire pour écrire
- [FFmpeg](https://ffmpeg.org) (`ffprobe`) — facultatif : débit audio dans le nom des pistes, détection des fichiers dont la durée ne correspond pas à l'épisode, et contrôle de la durée après conversion d'un `.avi` ou d'un `.mp4` ; **requis** (avec `ffprobe`) pour `Wav_To_Flac.py`, qui encode et compare le son
- [Pillow](https://pypi.org/project/pillow/) (`pip install pillow`) — facultatif : réduit les couvertures de `Books/Recap.py` et les pochettes de `Music/Recap.py`. Sans lui, les pages montrent un monogramme à la place (une note de musique grise pour la musique).

```powershell
winget install MoritzBunkus.MKVToolNix
winget install Gyan.FFmpeg
```

`Rename_Episodes.py` et `Rename_Tracks.py` n'ont besoin d'aucun de ces outils : ils ne touchent qu'aux noms de fichiers. `Music/Metadata.py` non plus : il lit et écrit les `.flac` et les `.mp3` lui-même, et MusicBrainz ne demande aucune clé. `Books/Recap.py` ne demande ni outil, ni clé, ni réseau ; `Music/Recap.py` non plus pour ses pages d'albums, et n'interroge MusicBrainz et Wikipédia (sans clé) que pour enrichir les fiches d'artiste — `--no-artist-info` l'en empêche.

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
python scripts\Movies\Metadata.py --dir "D:\Films" --no-tag --recap --apply   # fiche seule
```

L'identifiant TMDB retenu est **inscrit dans le film** (tag Matroska `TMDB`, au format `movie/1234`) : au passage suivant il est relu, plus rien n'est cherché, et l'association survit au renommage. La relecture ne coûte un sous-processus de plus que sur les fichiers qui déclarent des tags — une médiathèque jamais étiquetée ne paie rien. Priorité : `--tmdb-id`, puis l'identifiant épinglé dans le **nom**, puis celui lu dans le **fichier**, puis la recherche.

Chaque association est aussi **contrôlée** : un film dont la durée sur le disque sort de 75 % à 135 % de celle que TMDB annonce (à 10 min près), ou dont la fiche n'a presque aucun vote, est signalé sous `/!\`, repris en fin de passage sous `A VERIFIER` et marqué dans `metadata.log`. Les versions longues et l'accélération PAL passent ; un court métrage homonyme pris pour le film, ou un fichier tronqué, ne passent pas. Un identifiant épinglé dans le nom n'est jamais remis en cause. Pour faire taire un doute **sans toucher au nom du fichier**, ajoute le film à `metadata.ok`, rangé avec `metadata.log` : une ligne par film, l'identifiant seul ou son lien TMDB recopié du journal, `#` pour un commentaire (`https://www.themoviedb.org/movie/1437733  # Bref. De bons amis, ok`). Ses doutes ne sont plus signalés ; rien d'autre ne change.

Comme toute la reconnaissance repose sur les noms, [Rename_Movies.py](scripts/Movies/Rename_Movies.py) le remet d'aplomb depuis TMDB — et `--pin-id` y écrit l'identifiant, après quoi plus rien n'est cherché ni ne peut se tromper :

```powershell
python scripts\Movies\Rename_Movies.py --dir "D:\Films"                    # simulation
python scripts\Movies\Rename_Movies.py --dir "D:\Films" --apply --pin-id   # renomme et épingle
```

Un préfixe d'ordre de saga est conservé (`1 - Iron Man` → `1 - Iron Man (2008)`), les sous-titres suivent leur film en mode « `.mkv` à plat », et un identifiant déjà épinglé n'est jamais retiré.

`--recap` écrit `movies.html` dans le dossier `__Data__` de `--dir` (créé au besoin : la médiathèque elle-même n'est pas touchée), avec le dossier `Fiches` de ses fiches de film à côté, intitulé « Films », ou ce que `--title` lui donne (le titre choisi est repris aux passages suivants) : un mur d'affiches groupé par saga, avec **les films qui manquent à chaque saga** — TMDB connaît la composition des collections, donc une trilogie possédée aux deux tiers se voit. Seuls les films déjà sortis peuvent manquer : une suite annoncée (*Avatar 4*, 2029) ou sans date n'apparaît qu'une fois sa date passée. Comme pour les séries, la page est un fichier unique (affiches encodées dedans) et la précédente sert de cache. `--no-tag` produit les annexes sans rien modifier dans les `.mkv`. Les versions précédentes écrivaient `index.html` et `Fiches/` à la racine de `--dir` (ou ailleurs, avec `--recap-out`, qui n'existe plus) : ils ne sont **pas effacés**, mais `movies.html` reprend leur titre et leurs affiches au premier passage, et on peut les supprimer. Le journal `metadata.log` reste à la racine.

Une **zone de recherche** filtre les films par titre (sans accents ni casse) et masque les sagas qui n'ont plus rien à montrer. Un **index A–Z** dans l'en-tête fixe mène à la saga ou au film seul qui commence par la lettre (`#` pour un chiffre) ; pressée de nouveau, la lettre passe à l'occurrence suivante, et les lettres sans film sont grisées. Un bouton bascule entre **7 affiches par ligne** (par défaut) et la **pleine largeur** de l'écran ; le choix est gardé par le navigateur. Les sagas portent leur seul nom (`Iron Man`, pas `Iron Man - Saga`). Chaque film possédé mène à **sa propre fiche** — affiche, résumé, réalisateur et casting avec portraits —, un fichier par film rangé dans un dossier `Fiches` à côté de `movies.html` (`__Data__/Fiches/<id TMDB>.html`) : l'index reste léger, et la fiche n'est ouverte que pour le film qu'on clique, et « ← Films » ramène à sa vignette, pas en haut de la liste. Elle ne coûte aucune requête TMDB de plus (le casting est déjà dans la réponse du film), seulement des images, téléchargées une seule fois : la fiche précédente en sert de cache, et une fiche inchangée n'est pas réécrite. `--profile-size` (`w185`) règle la taille des portraits du casting. Les films manquants d'une saga n'ont pas de fiche, et celle d'un film sorti de la médiathèque reste sur le disque, sans plus de lien pour y mener.

Sous `--no-tag`, les films ne sont lus que pour leurs tags et leur durée, en Python pur : **ni MKVToolNix ni FFmpeg** ne sont nécessaires, et l'identifiant TMDB inscrit dans chaque film est repris sans recherche. La fiche n'est réécrite que si son contenu change, et le journal `metadata.log` reste à la racine de `--dir`. De quoi la tenir à jour en tâche planifiée sur le NAS qui héberge les films.

### Séries

Un sous-dossier `Saison N` par saison, les `.mkv` dedans, préfixés par leur numéro d'épisode. `--dir` peut aussi pointer directement sur un dossier de saison.

```powershell
python scripts\TV_Shows\Rename_Episodes.py --dir "D:\Series\Ma Serie" --apply
python scripts\TV_Shows\Metadata.py --dir "D:\Series\Ma Serie" --apply --recap
```

Les sous-titres posés à côté d'une vidéo (`.srt`, `.ass`, `.idx`/`.sub`…) sont renommés avec elle, en conservant ce qui suit le nom : `S01E02.fr.forced.srt` → `02 - Titre.fr.forced.srt`.

La série est identifiée par une recherche TMDB sur le nom du dossier (celui du parent si `--dir` pointe sur une saison) : le résultat retenu est affiché, et les cas douteux — reboot portant le même nom, titre éloigné de la recherche — sont signalés. `--tmdb-id 1234` force l'identifiant quand la recherche se trompe ou ne trouve rien — et pour que ce soit **durable**, écris-le dans le nom du dossier : `Ma Serie [tmdbid-1396]` (ou `{tmdb-1396}`). Même chose côté films : `Dune (2021) [tmdbid-438631]`.

`--recap` produit un `index.html` unique (onglets par saison, vignettes encodées dans la page : rien à conserver à côté). Les épisodes dont TMDB n'a pas de vignette reprennent l'affiche de leur saison (à défaut, celle de la série), encodée une seule fois pour toute la page. Les épisodes absents du disque y sont grisés et étiquetés, avec un compteur par saison — l'inventaire se lit dans les noms de fichiers, tous formats vidéo confondus, donc il reste juste même avec `--no-tag`. Un dernier onglet **Casting** rassemble les acteurs vus dans plusieurs saisons, puis, saison par saison, ceux qui n'appartiennent qu'à elle — ce qui rend lisible une série longue dont la distribution change (aucun acteur n'est écarté ; une saison en crédite facilement une centaine). `--artwork` écrit les `folder.jpg` (affiche anglaise) de la série et de chaque saison. `--no-tag` génère ces annexes sans toucher aux épisodes, pour une série qui n'est pas en `.mkv`.

Un dossier `Specials` (ou `Hors-serie`) est traité comme la saison 0 de TMDB, où vivent les épisodes spéciaux.

Quand la fiche évolue, [Recap_All.py](scripts/TV_Shows/Recap_All.py) remet toute la médiathèque à niveau d'une seule commande : il lance `Metadata.py --no-tag --recap` sur chaque série — les épisodes ne sont **jamais** modifiés. L'identifiant TMDB inscrit dans la fiche existante est repris (sauf s'il est épinglé dans le nom du dossier), si bien qu'une série identifiée autrefois avec `--tmdb-id` ne retombe pas sur un homonyme. Les images déjà dans une fiche sont reprises, une série en échec n'arrête pas les suivantes et figure au bilan, et un sommaire `index.html` présent est réécrit à la fin. `--only` restreint aux séries dont le nom contient un texte ; toute autre option (`--no-cache`, `--profile-size`, `--artwork`…) est transmise à `Metadata.py`.

```powershell
python scripts\TV_Shows\Recap_All.py --dir "D:\Series"            # simulation
python scripts\TV_Shows\Recap_All.py --dir "D:\Series" --apply    # régénère toutes les fiches
```

Pour passer d'une fiche à l'autre, [Index.py](scripts/TV_Shows/Index.py) écrit un sommaire dans le dossier `__Data__` de la médiathèque (créé au besoin) : un mur d'affiches, une par série, chacune menant à sa fiche — son `index.html`, dans le dossier de la série, ou l'ancien `recap.html` tant que la fiche n'a pas été régénérée (elle est alors renommée). **Le fichier porte le nom du titre** : `--title "Anime"` écrit `__Data__/Anime.html`, intitulé « Anime » (onglet et titre de la page) ; sans `--title`, c'est `__Data__/tv_shows.html`, intitulé « Séries » ou comme le sommaire déjà écrit. L'`index.html` que les versions précédentes écrivaient à la racine n'est ni réécrit ni effacé : on en reprend le titre, et on peut le supprimer. [Recap_All.py](scripts/TV_Shows/Recap_All.py) réécrit à la fin tous les sommaires qu'Index.py a écrits dans `__Data__`, ou seulement celui d'un `--title`. Tout est lu dans l'en-tête des fiches, qui portent titre, année, saisons (`2/5 saisons` quand il en manque), affiche et résumé — trois lignes sous l'affiche : ni TMDB, ni clé, ni réseau, ni outil externe — seulement Python 3 et `libraries/`. Il est donc fait pour tourner **en tâche planifiée sur le NAS** : les fiches s'écrivent sur un disque local puis sont transférées, et seul le NAS voit toutes les séries. Le sommaire n'est réécrit que si son contenu change, une page qu'il n'a pas écrite n'est jamais remplacée, et les dossiers cachés (`.recycle`…) sont ignorés. Une fiche antérieure à cette version figure sans affiche jusqu'à sa régénération. Chaque fiche porte un lien de retour dans son en-tête fixe (« ← Séries », ou « ← Anime » pour `--title "Anime"`), qui ramène à **sa vignette** dans le sommaire, pas en haut de la liste : le lien de chaque vignette dit à la fiche quel sommaire l'a ouverte (son fichier et son titre), et venu de lui c'est un vrai retour en arrière, qui garde aussi la recherche en cours. Une fiche ouverte directement, ou écrite avant cette version, mène à `__Data__/tv_shows.html`. Classement alphabétique sur le titre tel qu'il s'écrit, article compris (*The Expanse* à T, *Les Motards de l'espace* à L), filtre de recherche en tête, liens relatifs (le sommaire est dans `__Data__` : ils remontent d'un cran jusqu'aux fiches) : la médiathèque peut être déplacée sans rien casser. Chaque fiche porte une icône d'onglet à ses initiales, sur une couleur propre à la série (*BB* pour *Breaking Bad*), et le sommaire un petit téléviseur : des SVG écrits dans la page, sans fichier à côté — Safari, qui gère mal les icônes SVG, affiche la sienne par défaut.

```powershell
python scripts\TV_Shows\Index.py --dir "D:\Series" --apply
```

#### Mettre le sommaire à jour sur TrueNAS SCALE

Dans ce qui suit, `<pool>` est le pool de stockage, `<outils>` le dataset où ranger le script, `<series>` celui de la médiathèque, `<utilisateur>` le compte propriétaire du partage et `<nas>` / `<partage>` le nom réseau du NAS et du partage SMB. Les chemins réels se lisent dans *Datasets* (champ *Mountpoint*) et dans *Shares*.

1. **Copier les fichiers** sur un dataset, depuis l'Explorateur Windows par le partage SMB par exemple — jamais sur le pool système (`boot-pool`), qui est effacé aux mises à jour. Le dépôt entier convient ; à défaut, ces deux éléments suffisent, à condition de garder l'arborescence :

   ```text
   /mnt/<pool>/<outils>/media_library/
   ├── libraries/                     (le dossier entier)
   └── scripts/TV_Shows/Index.py
   ```

2. **Vérifier Python**, dans *System → Shell* : `python3 --version` doit répondre (Python est fourni avec le système, rien à installer).

3. **Essayer en simulation**, toujours dans le shell — rien n'est écrit, la liste des séries trouvées s'affiche :

   ```sh
   python3 /mnt/<pool>/<outils>/media_library/scripts/TV_Shows/Index.py --dir /mnt/<pool>/<series>
   ```

   `Aucune fiche` signifie que `--dir` ne pointe pas sur le dossier qui contient un sous-dossier par série, ou qu'aucune série n'a encore de fiche.

4. **Créer la tâche**, dans *System → Advanced Settings → Cron Jobs → Add* :

   | Champ | Valeur |
   | --- | --- |
   | Description | `Sommaire des séries` |
   | Command | `python3 /mnt/<pool>/<outils>/media_library/scripts/TV_Shows/Index.py --dir /mnt/<pool>/<series> --apply` |
   | Run As User | `<utilisateur>` — pas `root` : un dossier `__Data__` créé par `root` pourrait ne plus être modifiable ni supprimable depuis le partage |
   | Schedule | *Hourly* (toutes les heures) |
   | Hide Standard Output | coché — sans quoi chaque passage enverrait un courriel |
   | Hide Standard Error | décoché — une erreur, elle, mérite d'être signalée |
   | Enabled | coché |

5. **Lancer la tâche une première fois** depuis la liste des Cron Jobs (*Run Now*), puis ouvrir `\<nas>\<partage>\__Data__\tv_shows.html` (ou `<titre>.html`, avec `--title`) depuis Windows.

Ensuite, plus rien à faire : une série traitée sur le disque local puis copiée sur le NAS apparaît dans le sommaire au passage suivant, au plus tard une heure après. Le fichier n'est réécrit que si la liste a changé. `Permission denied` dans le courriel d'erreur veut dire que `<utilisateur>` ne peut pas écrire à la racine de `<series>` ; une série sans affiche, que sa fiche date d'avant cette version — la régénérer avec `--recap` suffit.

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

Le chemin pour corriger les mauvaises pochettes (recto-verso, mal cadrées) : extraire, ouvrir les `cover.jpg`, remplacer à la main ceux qui ne vont pas, puis embarquer avec `Cover.py --apply` et régénérer la fiche avec `Recap.py --apply`.

Une piste qui porte déjà exactement cette image n'est pas réécrite ; une autre image de face est remplacée, les images d'un autre type (dos, livret) sont gardées. Les albums sans fichier cover sont listés à la fin, pour savoir où en poser un. Seuls le JPEG et le PNG s'embarquent dans une piste : un `.webp`, `.gif` ou `.bmp` sert à la fiche mais pas aux fichiers audio (signalé). Une image de plus de 4 Mio est signalée, car l'Explorateur de Windows ne lit plus rien d'un `.flac` dont l'en-tête la dépasse. Pour que la fiche montre les nouvelles pochettes, relancer `Recap.py --apply`.

L'identifiant de l'édition (`MUSICBRAINZ_ALBUMID`) est inscrit dans chaque fichier et relu au passage suivant. Priorité : `--mbid`, puis l'identifiant épinglé dans le nom du dossier (`2013 - Outrun [mbid-4e5d9f0c-09b6-42bf-b495-e2d7cc288bf6]`), puis celui que **tous** les fichiers déclarent, puis la recherche.

Aucun outil externe : le script lit et écrit lui-même les blocs du `.flac`. Tant que les tags tiennent dans le padding du fichier, seul l'en-tête est réécrit ; sinon — une pochette ajoutée, typiquement — le fichier est recopié à côté puis substitué, et le son ne bouge pas. La place laissée vide sur place est plafonnée à 64 Ko : l'Explorateur de Windows ne lit plus rien, ni tags ni miniature, d'un `.flac` dont le son commence au-delà de 4 Mio (mesuré à l'octet près), et c'est ainsi que les pistes de *Synthesis* avaient perdu leur pochette à l'affichage. Un fichier que son padding a fait passer au-delà est signalé par `--verify` et recopié par `--apply` ; une image embarquée assez lourde pour franchir seule la limite est signalée. Mesuré sur une médiathèque de 194 pistes : 167 écritures sur place, 27 recopies (les deux albums sans pochette), le son intact à l'octet près, et un `--verify` qui ne trouve plus rien ensuite ; sur un album recopié en entier, l'empreinte MD5 du son décodé par ffmpeg reste la même. Un fichier déjà conforme n'est jamais réécrit, d'où l'absence de `--skip-done`. MusicBrainz n'accepte qu'une requête par seconde : un premier passage coûte environ trois requêtes par album, les suivants sont servis par le cache. Un `.mp3` se traite de la même façon, avec les mêmes options : les tags vont dans son étiquette ID3v2, sous les noms de trames de Picard (`TXXX` « MusicBrainz Album Id »…, `UFID` pour l'enregistrement), les valeurs multiples — genres, labels, artistes — séparées par un octet nul, la pochette dans une trame `APIC`. Une étiquette ID3v2.3 est relue puis réécrite en 2.4, UTF-8 (l'Explorateur de Windows en lit titre, artiste, album, année, numéro de piste, genre et pochette) ; ses trames que le script ne gère pas — ReplayGain, paroles `USLT`, commentaires, notes — sont recopiées telles quelles. Un ID3v2.2, antérieur à 1999, est converti trame par trame en 2.4 (ce qui n'a pas d'équivalent est abandonné), et l'étiquette ID3v1 de fin de fichier n'est pas touchée. Tant que l'étiquette tient dans son padding, seule elle est réécrite ; sinon, ou si le fichier n'en avait pas, il est recopié à côté puis substitué, et le son reste identique à l'octet près. La durée d'un `.mp3` (lue dans l'en-tête Xing, sinon estimée sur le débit) sert, comme celle d'un `.flac`, à signaler une piste qui ne colle pas. Seuls les `.flac` et les `.mp3` sont écrits : un dossier de `.m4a`, `.ogg`… est signalé et laissé tel quel. Le journal `metadata.log` donne le lien MusicBrainz de chaque album.

Pour les noms de fichiers, [Rename_Tracks.py](scripts/Music/Rename_Tracks.py) est le pendant de `Rename_Episodes.py` : chaque piste prend le nom `{numéro} - {titre}.flac` que donne MusicBrainz, le numéro sur autant de chiffres dans tout l'album.

```powershell
python scripts\Music\Rename_Tracks.py --dir "D:\Musique"                 # simulation
python scripts\Music\Rename_Tracks.py --dir "D:\Musique" --apply         # renomme
```

L'album est reconnu exactement comme par `Metadata.py` — mêmes éditions, même placement des fichiers, mêmes questions en fin de passage — et un album dont un seul fichier ne trouve pas sa piste n'est pas renommé du tout. Passé après `Metadata.py`, il ne cherche plus rien : l'identifiant est dans les fichiers. Un album en plusieurs disques rangés à plat préfixe le disque (`2-01 - Alive 1997.flac`) ; rangés dans `CD1`, `CD2`…, chaque dossier repart de `01`. Un `/` dans un titre devient `-` (`Robot Rock - Oh Yeah`), et les paroles `.lrc` posées à côté suivent leur piste. Les dossiers ne bougent pas : leur nom reste celui qu'on leur a donné.

#### Fiche de la médiathèque

Les albums passés par `Metadata.py` portent déjà tout ce qu'une fiche montre : titre, artiste, année, genres, label, numéros de piste et leurs totaux, identifiant MusicBrainz, pochette. Il n'y a donc **rien à chercher en ligne** pour les albums : [Recap.py](scripts/Music/Recap.py) lit ces tags — sans clé, sans rien écrire dans les fichiers — et en fait une fiche de la médiathèque, dans le style de celle des films. Elle marche aussi sur des albums qui n'ont pas été étiquetés (le nom du dossier remplace alors les tags), et le journal dit lesquels sont à passer par `Metadata.py`.

```powershell
python scripts\Music\Recap.py --dir "D:\Musique"            # simulation : lit les fichiers, ne montre que le bilan
python scripts\Music\Recap.py --dir "D:\Musique" --apply    # écrit la fiche dans D:\Musique\__Data__
```

Tout est écrit dans `__Data__` à la racine de `--dir` (ou dans `--out`) :

| Fichier | Contenu |
| --- | --- |
| `music.html` | Le sommaire **et le lecteur**, en un seul fichier : un mur de pochettes **groupé par artiste** — chaque artiste a sa section, même avec un seul album, classée sans tenir compte des accents ni de la casse —, avec une **zone de recherche** (album, artiste, label, genre), un **filtre de genre**, le bouton *7 par ligne* / *Pleine largeur* et un **index A–Z** dans l'en-tête fixe, au-dessus d'une **barre de lecture** (voir plus bas) |
| `Albums/` | Une fiche par album : pochette, artiste, année, label et numéro de catalogue, genres, durée, format, lien vers la fiche MusicBrainz, pistes avec leur durée (une section par disque), **les pistes qui manquent**, et un **lecteur** (voir plus bas) |
| `Artistes/` | Une fiche par artiste ou groupe, où mène son nom — dans le sommaire comme sur la fiche d'un album : ses albums, ses genres, et ce que MusicBrainz et Wikipédia en disent (voir plus bas) |
| `artists.json` | Ce que MusicBrainz et Wikipédia ont dit des artistes (voir plus bas) : redemandé au bout d'un mois seulement |
| `catalog.json` | Ce qu'on a lu dans chaque fichier, avec sa taille et sa date : aux passages suivants, seules les pistes **nouvelles ou modifiées** sont rouvertes |
| `recap.log` | Le journal : les albums pas encore étiquetés, les pistes qui manquent, les fichiers illisibles et ceux d'un format non pris en charge |

Les **pistes manquantes** viennent du total que les tags annoncent (`TRACKTOTAL`, `DISCTOTAL`) comparé aux numéros possédés : `Manque : pistes 3, 5–7 (sur 13)`, et chaque piste absente est grisée à sa place dans la liste. Rien n'est dit d'un disque dont une piste n'a pas de numéro — c'est peut-être elle qui manque. Sur le sommaire, la pochette d'un album incomplet affiche `11/13 pistes` en orange.

Un album est reconnu comme par `Metadata.py` — un dossier qui contient de l'audio, lui ou ses dossiers de disque —, et les mêmes règles tranchent quand les tags manquent : le disque et le numéro viennent des tags, puis du dossier de disque, puis du nom du fichier. Les dossiers dont le nom commence par `__`, `#` ou `@` (`__Data__`, `#recycle`, `@eaDir`) sont ignorés. Les artistes se regroupent sans tenir compte des accents ni de la casse, et les albums d'un artiste se rangent par année. Le lien MusicBrainz d'un artiste vient du tag `MUSICBRAINZ_ALBUMARTISTID`, écrit par `Metadata.py` : il manque aux albums pas encore étiquetés, et à ceux dont l'artiste en porte plusieurs (`Kavinsky feat. Havoc`), où aucun ne dit seul qui est l'artiste. Les albums d'« Artiste inconnu » n'ont pas de fiche commune.

**Ce que dit la fiche d'un artiste.** Pour chaque artiste dont les tags portent l'identifiant MusicBrainz, `Recap.py --apply` demande à MusicBrainz son **type** (groupe, artiste solo, orchestre…), son **pays**, ses **dates** (`depuis 1993`, `1950 – 2016`, `né en 1970`), sa description courte, ses **membres** — les actuels, puis les anciens, en deux listes **repliées par défaut** (un clic les déplie ; la liste des albums, elle, est dépliée et se replie de même), avec leurs rôles et leur période, chacun lié à sa fiche MusicBrainz — et ses **liens officiels** (site, Bandcamp, YouTube, réseaux sociaux, plateformes ; les bases de données et les boutiques sont écartées). Le **résumé** vient de Wikipédia, que MusicBrainz désigne par un identifiant Wikidata : l'article en français, à défaut en anglais, coupé à la fin d'une phrase et suivi de sa source. Les noms de pays, les rôles des membres et la description courte restent ceux de MusicBrainz, donc en anglais.

**Les albums qui manquent.** Pour qu'une fiche d'artiste montre sa discographie complète, on le dit dans son dossier par un fichier vide nommé comme un album rangé : `1997 - OK Computer.txt` à côté de `1995 - The Bends/`. Seul le nom du fichier est lu. La fiche range ces albums parmi les autres, par année, en vignettes grisées marquées « manquant » (sans lien ni lecture), compte `Albums 8/12` et ajoute « 4 manquants » à ses chiffres ; le journal `recap.log` les liste (`[ABSENT]`). Un `.txt` dont l'album a été rangé depuis (même titre, même année) est ignoré : il peut rester sans fausser la fiche. Les signes qu'un nom de fichier ne peut pas porter (`?`, `:`) ne comptent pas dans la comparaison, et un `.txt` dans un dossier sans aucun album n'affiche rien — l'artiste n'a pas de fiche.

C'est le seul endroit où le script sort sur le réseau, à raison d'**une requête par seconde** pour MusicBrainz — comptez un quart d'heure pour 500 artistes au premier passage. Les réponses sont gardées dans `artists.json`, à côté des pages, et redemandées au bout d'un mois : aux passages suivants, seuls les **nouveaux artistes** coûtent une requête, et un artiste sans fiche MusicBrainz (supprimée ou fusionnée) n'est pas redemandé. Sans réseau, le script abandonne après **trois échecs d'affilée** et garde ce qu'il avait ; le reste est repris au passage suivant. La simulation n'interroge personne et annonce combien d'artistes elle interrogerait. `--no-artist-info` n'interroge jamais, et les fiches gardent alors ce qu'on savait déjà ; `--no-cache` redemande tous les artistes.

**Écouter depuis la fiche.** Chaque piste d'une fiche d'album a un bouton ▶ qui joue le fichier lui-même, dans un lecteur fixé en bas de page. **Tout lire**, en tête de fiche, lit l'album du début à la fin, disques à la suite (le même bouton met en pause, puis reprend) ; une piste finie lance la suivante, la barre porte ⏮ et ⏭ et la position (`3/12`), ⏮ relance la piste si elle a plus de 3 secondes ou si c'est la première, recliquer sur la piste en cours la met en pause, et un fichier introuvable le dit dans la barre. **`music.html` est aussi le lecteur** : le sommaire porte sa barre de lecture, à la manière de Qobuz, fixée en bas de la fenêtre : à gauche la **pochette**, le **titre** et « artiste – album » de la piste en cours (un clic y ouvre la fiche de l'album) ; au centre le temps écoulé et la durée (`00:30 - 03:17`), **aléatoire**, **précédent**, **lecture/pause**, **suivant** et **répéter** (rien, l'album, la piste) ; à droite le **volume** et la coupure du son ; et en travers de son bord haut la **barre de progression**, qu'on clique ou qu'on tire (flèches du clavier : ±5 s). La file de lecture est l'album : l'aléatoire le mélange en gardant la piste choisie en tête, et il reste actif d'un album à l'autre. La barre est là **dès l'arrivée**, au repos (« Aucune lecture », lecture, précédent et suivant grisés) : le bouton du volet reste actif, ce qui permet de lancer une playlist avant d'avoir joué quoi que ce soit. Un bouton ▶ au milieu de chaque pochette lit l'album (le même bouton met en pause). Le bouton ☰♪ de la barre ouvre la **file d'attente**, un volet à droite : le titre en cours, puis **ce qui suit dans l'ordre de lecture** — celui de l'album, ou le tirage de l'aléatoire, qui s'y reflète. Un clic sur un titre saute dessus, un clic sur le titre en cours le met en pause, la croix au bout d'un titre à venir le **retire** de la file, « Vider » retire tout ce qui suit, `Échap` ou la croix du haut referment le volet. Ouvert, le volet **pousse la page** (et la fiche ouverte) au lieu de la recouvrir : les durées et les menus ⋯ du bord droit restent à portée ; sur un écran étroit, il passe par-dessus.

**Les playlists** vivent dans le deuxième onglet du volet, *Playlists*. On y crée une playlist (**＋ Nouvelle playlist**), on voit la liste, et un clic en ouvre le contenu : **▶ Lire** en fait la file, **À la file** l'ajoute à la fin de la file en cours, **Renommer** et **Supprimer** font ce qu'ils disent, un clic sur un titre lit la playlist à partir de lui, et la croix d'un titre le retire. Pour y ranger des titres, le menu ⋯ d'un titre (ou celui de l'album, à côté de « Tout lire ») propose **Ajouter à une playlist…** : une fenêtre liste vos playlists et « Nouvelle playlist » ; un titre déjà présent n'est pas doublé, et un message le dit. Dans l'onglet de la file, **Enregistrer en playlist** garde toute la file, dans l'ordre de lecture.

**Réordonner.** Dans une playlist, chaque titre porte une poignée **⋮⋮** à gauche : on l'attrape (à la souris ou au doigt) et on la dépose à sa place, un trait bleu montrant où elle tombera, et la liste défile quand on approche de son bord. Au clavier, la poignée prend le focus avec Tab, et **↑** / **↓** déplacent le titre d'un cran. Réordonner une playlist ne touche pas à la file en cours : celle-ci est une copie.

**Exporter et importer.** Dans la liste des playlists, **Exporter** télécharge toutes les playlists dans un fichier `playlists.json` (le format de l'export, versionné, ne contient que des noms, des chemins relatifs et des titres), et **Importer** en lit un. L'import **ajoute sans rien écraser** : une playlist identique (même nom, mêmes titres) n'est pas doublée, un nom déjà pris reçoit un numéro (« Ma liste (2) »), et un message dit ce qui a été fait ; un fichier qui n'est pas du JSON, ou sans playlist valable, est refusé. C'est le moyen de sauvegarder ses playlists, de les passer d'un navigateur à l'autre, ou de les retrouver entre `file://` et `https://`, qui ne partagent pas leur stockage.

Les playlists sont gardées **dans le navigateur** (`localStorage`), pas sur le NAS : elles ne se partagent pas d'un navigateur à l'autre, ni entre `file://` et `https://` — qui sont deux « sites » pour lui. Chaque titre y est enregistré par son **chemin relatif à `music.html`** (`../Daft%20Punk/Discovery/01.flac`) plus son titre, jamais par une adresse complète : la même playlist marche donc par le partage réseau comme par le serveur web. La pochette, l'artiste et la fiche d'un titre sont retrouvés dans la page ; un fichier déplacé ou supprimé reste dans la playlist, barré et marqué *Introuvable*, et n'est pas lu. Si le navigateur refuse le stockage (navigation privée), la page le dit et marche sans playlists. Chaque titre de la file porte son propre artiste, album, pochette et fiche : la file n'est plus liée à un seul album. Cliquer un nom d'artiste ou une pochette ouvre la fiche **par-dessus** le sommaire, dans une iframe, au-dessus de la barre : la musique ne s'arrête jamais. La fiche n'y joue plus elle-même, elle envoie ses pistes à la barre et marque celle qui joue ; « ← Musique » la ferme et ramène au groupe qu'on a quitté, le sommaire n'ayant pas bougé ; cliquer le nom de l'album dans la barre rouvre sa fiche. Un clic avec Ctrl ou Maj, ou un clic du milieu, ouvre la fiche dans un onglet comme d'habitude. L'adresse du navigateur reste celle de `music.html` pendant qu'on navigue, donc un favori ou un rechargement ramène au sommaire. Ouvertes seules (depuis l'Explorateur ou un lien direct), les fiches jouent comme avant, avec leur barre simple (⏮ ⏭ et le lecteur du navigateur), et la musique s'arrête quand on change de page. Rien n'est copié ni encodé dans la page : le bouton pointe vers le fichier par un **lien relatif** (`../../Daft%20Punk/Discovery/01.flac`), donc la fiche ne lit que là où les fichiers sont joignables depuis elle — ouverte depuis le disque ou le partage réseau (`file://`), ou servie avec la musique par un serveur web du NAS. Écrite ailleurs avec `--out`, le lien est recalculé vers la médiathèque ; **copiée sans la musique**, elle ne lit rien, et `--no-player` retire alors les boutons et la barre : `music.html` n'est plus qu'un sommaire, dont les liens se suivent dans l'onglet. Les `.flac` et `.mp3` se lisent dans les navigateurs récents, et dans l'ordre de la fiche : les pistes manquantes ou illisibles n'ont pas de bouton. Un menu **⋯** en bout de chaque piste (visible au survol, toujours au doigt) propose **Lire ce titre seul** : la file ne contient alors que lui, la lecture s'arrête à sa fin, et « suivant » est grisé. Dans `music.html` la fiche l'envoie à la barre comme une file d'un seul titre, que le panneau de la file d'attente montre ; sur une fiche ouverte seule, c'est sa propre barre qui s'arrête. Dans `music.html`, le même menu propose aussi **Lire ensuite** (juste après le titre en cours, derrière ceux déjà ajoutés ainsi : ils passent dans l'ordre où on les a demandés) et **Ajouter à la fin** ; un menu **⋯** à côté de « Tout lire » fait de même pour **l'album entier**. Un message le confirme au-dessus de la barre, et quand rien ne joue encore, l'ajout lance la lecture. Les titres ajoutés restent à leur place si on coupe puis remet l'aléatoire. Une fiche ouverte seule n'a pas de file : elle ne propose que « Lire ce titre seul ».

**Le retour sur le sommaire** (quand une fiche est ouverte seule, ou avec `--no-player`) se cale sur le **nom du groupe** de l'album qu'on quitte, juste sous l'en-tête fixe, plutôt que de remettre la page là où elle était — presque toujours en travers d'une rangée de pochettes coupée par l'en-tête. Ça vaut pour le retour du navigateur comme pour le lien « Musique ».

Les pochettes sont celles que portent les fichiers, réduites et encodées dans la page, qui reste un fichier unique : il faut [Pillow](https://pypi.org/project/pillow/) pour les réduire, et sans lui les pages montrent une image générique à la place — une note de musique grise, la même pour tous les albums sans pochette. Une page déjà écrite sert de cache — rien n'est rouvert pour une pochette déjà dedans, et une page qui n'a pas changé n'est pas réécrite —, de quoi la tenir à jour chaque nuit sur le NAS sans réveiller les disques pour rien. Le script sort en **code 1** s'il y a des fichiers illisibles. `--no-cache` rouvre toutes les pistes, `--no-player` retire les boutons de lecture, `--title` donne son titre à la fiche (« Musique » par défaut, et le choix est repris aux passages suivants), `--cover-width` règle la taille des pochettes des fiches et `--workers` le nombre de fichiers lus en parallèle (8 par défaut).

Les versions précédentes écrivaient `index.html` (le sommaire) et `lecteur.html` (la coque qui l'affichait dans une iframe), puis `musique.html` : `music.html` les remplace tous. Ils ne sont **pas effacés** — ce script n'efface jamais rien dans `__Data__` — mais plus rien n'y mène ; le titre choisi avec `--title` y est repris la première fois. Les supprimer à la main est sans conséquence.

Pour la mettre à jour sur un NAS, la tâche planifiée est celle de [la fiche des livres](#mettre-la-fiche-à-jour-sur-truenas-scale), avec `Music/Recap.py` et le dossier de la musique : `XDG_CACHE_HOME=/mnt/<pool>/<outils>/cache python3 /mnt/<pool>/<outils>/media_library/scripts/Music/Recap.py --dir /mnt/<pool>/<musique> --apply`. Ouvrir ensuite `\<nas>\<partage>\__Data__\music.html`.

### Livres, BD, comics et mangas

La bibliothèque est rangée **par section** — un dossier `Manga`, `BD`, `Comics`, `Artbook`, `Romans`… — et chaque section par **série** : un dossier par série (par auteur pour les romans) qui contient ses volumes, `.cbz` pour les bandes dessinées, `.epub` pour le reste. Un fichier posé seul dans une section (`Manuels/Un guide.epub`) est sa propre série, ceux de la racine forment la section « Autres », et les sous-dossiers d'une série (cycles, intégrales) en groupent les volumes à l'affichage.

Ces livres portent déjà leur fiche : `ComicInfo.xml` dans un `.cbz` (série, numéro, résumé, auteurs, éditeur, date, genres…), le `.opf` d'un `.epub` quand Calibre est passé par là. Il n'y a donc **rien à chercher en ligne** : [Recap.py](scripts/Books/Recap.py) lit ces fiches — sans réseau, sans clé, sans rien écrire dans les livres — et en fait une fiche de la bibliothèque, dans le style de celle des films.

```powershell
python scripts\Books\Recap.py --dir "\\TRUENAS\Livres"            # simulation : lit les livres, ne montre que le bilan
python scripts\Books\Recap.py --dir "\\TRUENAS\Livres" --apply    # écrit la fiche dans \\TRUENAS\Livres\__Data__
```

Tout est écrit dans `__Data__` à la racine de `--dir` (ou dans `--out`) :

| Fichier | Contenu |
| --- | --- |
| `books.html` | Le sommaire : une vignette par série, groupées par section, avec une **zone de recherche** (titre, auteur, éditeur, genre) et le bouton *7 par ligne* / *Pleine largeur* des films, un **index A–Z** (la même lettre, pressée de nouveau, passe à la série suivante) et un raccourci par section (*Manga*, *BD*…) dans l'en-tête fixe |
| `Series/` | Une page par série : couverture, auteurs, éditeur, années, genres, résumé, une carte par volume avec sa couverture, et **les tomes qui manquent** |
| `catalog.json` | Ce qu'on a lu dans chaque livre, avec sa taille et sa date : aux passages suivants, seuls les livres **nouveaux ou modifiés** sont rouverts |
| `recap.log` | Le journal : par section, les livres **sans fiche** et les fichiers illisibles |

Les **tomes manquants** viennent du champ `Count` des fiches (« la série compte 37 tomes ») comparé aux numéros possédés : `Manque : 3, 5–7, 12`. Rien n'est dit d'une série dont un volume n'a pas de numéro, car c'est peut-être lui qui manque. Un dossier qui réunit plusieurs cycles se compte cycle par cycle. Quand il en manque, la vignette affiche `12/22 tomes` en orange.

Un dossier dont le nom commence par `__` — `__Data__`, `__En cours` — n'est pas encore rangé : il est ignoré, comme `#recycle`, `@eaDir` et les dossiers cachés. Tout ce qui n'est pas un livre (`.txt`, `.db`, `.jpg`, `.opf` voisin d'un livre, tableur) l'est aussi, et **les `.pdf` le sont par défaut** : ils n'ont ni fiche ni couverture à lire. `--include-pdf` les compte, avec un monogramme.

Les couvertures sont celles que la fiche désigne (`FrontCover`), sinon la première page, réduites à 240 pixels et encodées dans la page, qui reste un fichier unique. Il faut [Pillow](https://pypi.org/project/pillow/) pour les réduire ; sans lui, les pages montrent un monogramme à la place. Une page déjà écrite sert de cache : rien n'est rouvert pour une couverture déjà dedans, et une page qui n'a pas changé n'est pas réécrite — la fiche ne change pas de date tant que la bibliothèque ne bouge pas.

Le script sort en **code 1** s'il y a des fichiers illisibles (un `.cbz` tronqué par un transfert interrompu, typiquement), signalés dans `recap.log` et sur la page de leur série. `--no-cache` rouvre tous les livres, `--cover-width` règle la taille des couvertures et `--workers` le nombre de livres lus en parallèle (8 par défaut : sur un partage réseau, chaque archive paie son aller-retour).

#### Mettre la fiche à jour sur TrueNAS SCALE

Le premier passage ouvre chaque archive, ce qui prend un moment ; les suivants ne rouvrent que ce qui a changé. C'est fait pour une tâche planifiée, comme [le sommaire des séries](#mettre-le-sommaire-à-jour-sur-truenas-scale) — mêmes étapes, avec ces valeurs :

| Champ | Valeur |
| --- | --- |
| Description | `Fiche des livres` |
| Command | `XDG_CACHE_HOME=/mnt/<pool>/<outils>/cache python3 /mnt/<pool>/<outils>/media_library/scripts/Books/Recap.py --dir /mnt/<pool>/<livres> --apply` |
| Run As User | `<utilisateur>`, pas `root` |
| Schedule | *Daily* (la nuit) |

Le dépôt entier doit être copié sur le NAS (`libraries/` et `scripts/Books/Recap.py` suffisent). Pillow n'y est en général pas installé : sans lui la fiche s'écrit quand même, avec des monogrammes. Ouvrir ensuite `\\<nas>\<partage>\__Data__\books.html`. Les versions précédentes écrivaient `index.html` : il n'est pas effacé, mais `books.html` en reprend le titre.

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

## Pistes à explorer

Rien de tout ça n'est fait ; c'est ce qu'on a retenu en y réfléchissant.

### Lire films et séries depuis leurs fiches

La musique se lit déjà depuis ses fiches (voir [Musique](#musique)), parce que `<audio>` lit le FLAC et le MP3 tels quels. Pour la vidéo le blocage est le **format**, pas la page :

- le `.mkv` n'est lu que par Chrome et Edge, et pas toujours ; Firefox et Safari ne le lisent pas ;
- l'audio AC-3, E-AC-3 et DTS ne passe pas dans `<video>`, le HEVC est aléatoire, les sous-titres PGS ne s'affichent pas.

Seul un **transcodage à la volée** (ffmpeg, HLS) lirait tout dans le navigateur. Il demande un serveur qui tourne en permanence, ce qui sort du principe actuel — pages statiques écrites par une tâche planifiée, sans dépendance — et ffmpeg est aujourd'hui facultatif. Trois voies, de la plus simple à la plus lourde :

1. **Un bouton « Lire » qui sort du navigateur** : un `.m3u` à télécharger, ou un lien `vlc://`. Ça lit tout, et ça se fait avec les mêmes liens relatifs que la musique (`music.html` pourrait aussi porter un `<video>`, mais le format reste le blocage) (`libraries/video/filmpage.py` connaît déjà les chemins des fichiers, `paths=`). C'est la voie recommandée pour commencer.
2. **Un lien vers Jellyfin, Plex ou Video Station** si le NAS en héberge un : la fiche pointerait vers le titre correspondant, et le transcodage est déjà fait par eux. À voir : retrouver un titre par son identifiant TMDB, que les fiches portent déjà.
3. **Un `<video>` direct, sans transcodage** : à écarter, il ne marcherait que pour les rares fichiers compatibles, sans dire pourquoi aux autres.

À décider avant : où les fiches sont servies (`file://`, partage réseau, serveur web du NAS) et s'il y a déjà un serveur de médias.

## Tests

```powershell
python -m unittest discover -s tests -t .
```

Ils tournent aussi sur chaque push et chaque PR (Windows et Linux, Python 3.8 et 3.13) via [GitHub Actions](.github/workflows/tests.yml).

Ils couvrent la partie qui casse en silence — analyse des noms, tags produits, comparaison à l'état visé, erreurs TMDB, cas tordus du renommage — sans réseau ni outil externe.

## Licence et données

Le code est publié sous licence [MIT](LICENSE).

Les données qu'il écrit dans les fichiers et dans les fiches HTML ont leurs propres conditions :

- This product uses the TMDB API but is not endorsed or certified by [TMDB](https://www.themoviedb.org). Les titres, synopsis, affiches et portraits des films et des séries viennent de TMDB.
- Les métadonnées musicales viennent de [MusicBrainz](https://musicbrainz.org), les pochettes de [Cover Art Archive](https://coverartarchive.org) (chacune garde la licence que son auteur lui a donnée).
- Les résumés d'artistes viennent de Wikipédia, sous licence CC BY-SA ; chaque fiche en cite la source.
- MKVToolNix et FFmpeg sont lancés comme programmes séparés, jamais intégrés au code : leurs licences ne s'appliquent pas à ce dépôt.
