# TODO

Suivi de l'analyse du code (novembre 2026). État au 2 novembre : tous les points sont faits (PR #46 à #52), le fichier en garde la trace. Une prochaine passe d'analyse s'y ajoute ici ; cocher une case dans la PR qui règle le point.

## À corriger

- [x] **1. Réponse HTTP coupée en route** — `http.client.IncompleteRead` n'est pas un `OSError` : elle échappait à `Tmdb._request` et `MusicBrainz._request`, donc à tous les `except TmdbError` / `except MusicBrainzError` des scripts, et arrêtait le passage avec une trace. Maintenant réessayée, puis levée en erreur du client. (`libraries/video/tmdb.py`, `libraries/music/musicbrainz.py`)

## À améliorer

- [x] **2. Duplication** — `Avi_To_Mkv.py` et `Mp4_To_Mkv.py` partageaient 253 lignes sur ~300 : chemin commun dans `libraries/video/remux.py`. `Tmdb` et `MusicBrainz` recopiaient `_request` / `_retry_after` : boucle commune dans `libraries/common/http.py`. `display_command`, qui existait aussi dans `Wav_To_Flac.py`, vit dans `libraries/common/tools.py`.
- [x] **3. `process_album` trop complexe** (complexité 42 → 12) — découpé en `plan_track`, `describe_track`, `verify_track`, `write_track` dans `scripts/Music/Metadata.py`. `match_tracks` (33 → 14) et `target_tags` (32 → 6) dans `libraries/music/album.py` : une fonction par étape (numéro, places douteuses, titres ; crédits, piste, édition, identifiants).
- [x] **4. Renommage « casse seule » interrompu** — si la 2e étape de `rename_path` (`libraries/common/rename.py`) échouait, le fichier restait sous `X.tmpN.ext` sans que le message le dise. Il reprend maintenant son nom d'origine, et si même ce retour échoue, l'erreur nomme le fichier provisoire.

## Détails

- [x] `textfile.write` n'était pas atomique (`libraries/common/textfile.py`) : écrit maintenant sous un nom provisoire puis remplace, comme `flac.write` et `mp3.write`.
- [x] `libraries/books/` n'est utilisé par aucun script du dépôt (media_hub le lit) : la garde de `tests/test_architecture.py` sur `scripts/Books` dit désormais pourquoi elle passe à vide.
- [x] Coquille `diffs =albums…` (`scripts/Music/Metadata.py:156`) : disparue avec le découpage de `process_album`.

# Deuxième passe (2 novembre 2026)

Rien d'alarmant : la syntaxe est compatible 3.8, aucun `shell=True`, `eval` ou défaut mutable, tous les `urlopen` ont un délai, toutes les ouvertures de texte précisent l'encodage, chaque module et chaque script est nommé par un test, et ni l'arbre ni l'historique ne contiennent de clé. Ce qui reste, par ordre d'importance :

## À corriger

- [x] **5. Un titre qui ne laisse rien après nettoyage faisait planter `Rename_Movies.py`** — `safe_name` retire maintenant aussi les caractères de contrôle. `Rename_Movies.py` écarte le film (`[IGNORÉ] le titre TMDB … ne laisse aucun nom de fichier utilisable`, compté « à corriger », code de sortie 1) au lieu de lever `ValueError` ou de produire `" (2010).mkv"`. `Discography.py` refuse un `--only` sans nom utilisable et garde le dossier demandé quand MusicBrainz donne un nom vide. Les épisodes et les pistes à titre vide gardent `01 - .ext`, un nom valide.
- [x] **6. `Discography.py` prenait un dossier illisible pour un album manquant** — `find_albums` et `files_with_ext` prennent un dossier qu'ils ne peuvent pas lister pour un dossier vide, et l'inventaire avalait ses propres `OSError` : un album illisible (NAS qui rame, droits) passait pour manquant et recevait un fichier « manquant ». `discography.inventory` vérifie maintenant que tout le dossier de l'artiste se lit (hors dossiers cachés et de rangement système) et lève `OSError` sinon ; `Discography.py` le rapporte (`[ÉCHEC] inventaire impossible, rien n'est posé pour cet artiste`, code de sortie 1) au lieu de poser des fichiers. Le reste de l'application, `find_albums` en tête, garde sa tolérance : seul ce script écrit à partir de ce qu'il ne trouve pas.

## À améliorer

- [x] **7. Aucun délai sur les outils externes** — `mkvmerge -J`, `ffprobe` et `mkvextract` (lectures) reçoivent 120 s quand le fichier est sur un partage réseau (`tools.read_timeout`) ; une lecture suspendue est rapportée comme illisible (`sans réponse après 120 s (partage réseau injoignable ?)`) au lieu de figer le passage. Le réseau est reconnu par `libraries/common/volumes.py` : chemin UNC ou lecteur mappé (`GetDriveTypeW`) sous Windows, montage NFS / SMB / sshfs… d'après `/proc/mounts` sous Linux ; en cas de doute (macOS) le volume est tenu pour local, donc sans délai. Disque local et conversions : aucun délai. `Wav_To_Flac.py` n'est pas concerné (son `ffprobe` n'attrape déjà aucune panne d'outil).
- [x] **8. Complexité restante** — découpées par étape, chaque fois avec une comparaison avant/après (#60 à #66) : `remux.convert` (31 → 14), `mp3._comments` (30 → 18 au plus dans `mp3.py`), `mkv.write` (27 → 11) et `mkv.verify` (25 → 3), `ebml._rapide` (22 → 9), `epub.parse_opf` (23 → 10), `shelf.scan` (24 → 3), `Verify_Files.py main` (24 → 7), `Movies/Metadata.py main` (24 → 9). La comparaison de `_rapide` a aussi révélé un `TypeError` sur un Segment ou un SeekHead de taille illisible, corrigé à part (#64).
- [x] **9. `Movies/Metadata.py` faisait 748 lignes** — 388 lignes aujourd'hui (#67 à #70) : la logique pure du film est dans `libraries/video/movietags.py` et `doubts.py`, les fichiers du passage dans `passfiles.py`, l'association à TMDB et le replacement par saga dans `resolve.py`. Le script garde la ligne de commande, le traitement d'un film et l'enchaînement.
- [x] **11. Les fonctions restantes à 20 ou plus** — découpées (#73 à #76), chacune avec une comparaison avant/après : `Wav_To_Flac.convert` (21 → 12), `Discography.complete` (22 → moins de 9), `Rename_Tracks.main` (21 → 9), `TV_Shows/Metadata.process_season` (21 → 8). Les tags et la cible d'un épisode ont ensuite rejoint `libraries/video/episodetags.py`, comme ceux des films (#78).

## À décider

- [x] **10. `Verify_Mkv.py --repair` remplaçait l'original sans le garder** — sur un fichier abîmé, `mkvmerge` peut ne récupérer qu'une partie du film. L'original est maintenant gardé à côté (`Film.mkv.orig`, puis `.orig2`… sans jamais en écraser un), remis en place si le remux ne peut pas prendre sa place, et le journal dit où il est. Décision prise : on garde (le traitement se fait sur le PC avant transfert au NAS, la place n'est pas en jeu). Les `.orig` se suppriment à la main une fois les films vérifiés ; une option pour ne pas les garder reste possible si le script tourne un jour sur le NAS.

## Détails

- [x] `apply_renames` : le déblocage d'un cycle passe par `X.tmpN.ext` ; si le renommage suivant échouait, le fichier y restait. `put_back` lui rend maintenant son nom d'origine quand celui-ci est libre (`[REMIS]`) et, quand un autre fichier l'a pris (cycle presque terminé), dit sous quel nom provisoire il est resté. (`libraries/common/rename.py`)
- [x] `libraries/common/http.py` : l'`HTTPError` retenue entre deux essais gardait sa connexion ouverte ; elle est fermée dès qu'elle est reçue.
- [x] Les contrôles `Content-Length` de `Tmdb.image` et `MusicBrainz._image` ne se déclenchent plus en pratique (`http.client` lève `IncompleteRead` avant) : décision de les garder comme ceinture, avec un commentaire qui le dit, plutôt que de retirer du code et des tests sans gain.

# Troisième passe (novembre 2026) : arrêtée là

Un seul angle a été exploré : les lecteurs de fichiers confrontés à des fichiers abîmés au hasard, comme `ebml` l'avait été pour la seconde passe. 24 000 fichiers (4000 par lecteur : `flac.read`, `mp3.read`, `epub.read_info` et `cover`, `cbz.read_info` et `cover`) : aucun plantage hors erreur métier (`FlacError`, `Mp3Error`, `BookError`), aucun blocage. Rien à corriger de ce côté.

Ce qui n'a pas été fait, à reprendre si l'envie vient (rendement attendu plus faible que pour les deux premières passes) :

- [ ] Relire à froid le code écrit pendant les points 5 à 11 : `libraries/common/volumes.py` (détection d'un partage réseau, jamais essayée sur un vrai NAS), `tools.read_timeout`, `rename.put_back`, `textfile.write` atomique, l'inventaire de `Discography`.
- [ ] Mesurer la couverture réelle des tests sur les fichiers touchés (module `trace` de la bibliothèque standard) pour repérer les branches qu'aucun test n'exerce.
- [ ] Vérifier à la lecture les API utilisées par rapport à Python 3.8, faute d'un interpréteur 3.8 en local : la CI en a déjà pris un en défaut (`HTTPError.close()`, #72).
- [ ] Essayer sur de vrais fichiers ce que tout le travail a seulement simulé : `Music/Verify_Flac.py` et `Verify_Mp3.py` sur la vraie médiathèque (temps du contrôle rapide d'un `.mp3` sur le NAS, `--full`, faux positifs sur des fichiers anciens), `Verify_Mkv.py --repair` avec ses `.orig`, le délai de lecture sur le NAS, un renommage de casse sous Windows avec un fichier verrouillé.
