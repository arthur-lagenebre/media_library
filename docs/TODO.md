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

- [ ] **7. Aucun délai sur les outils externes** — `run_tool` (`libraries/common/tools.py:11`) n'a pas de `timeout` : un `ffprobe` ou un `mkvmerge -J` qui reste suspendu sur un partage réseau fige tout le passage. Un délai (une à deux minutes) pour les lectures (`identify`, `probe`, `ffprobe`), aucun pour les conversions, qui durent ce qu'elles durent.
- [ ] **8. Complexité restante** — `remux.convert` (31, le plus complexe du dépôt : plan, exécution, contrôle de durée, remplacement, effacement de la source), `mp3._comments` (30), `mkv.write` (27), `mkv.verify` (25), `shelf.scan` (24), `Movies/Metadata.py main` (24), `Verify_Files.py main` (24), `epub.parse_opf` (23), `ebml._rapide` (22). Même méthode que #49 : découper par étape, prouver l'identité avant/après.
- [ ] **9. `Movies/Metadata.py` fait 748 lignes** (`process_season` de `TV_Shows/Metadata.py`, 21) — la règle du dépôt veut que le script garde la ligne de commande et l'enchaînement, et que la logique réutilisable vive dans `libraries/`. À reprendre avec le point 8.

## À décider

- [ ] **10. `Verify_Files.py --apply` remplace l'original par le remux sans comparer** — contrairement aux conversions (qui contrôlent la durée), `repair` n'exige du remux que d'être structurellement sain. Sur un fichier abîmé, `mkvmerge` peut ne récupérer qu'une partie : l'original, même abîmé, est alors perdu pour de bon. Garder l'original à côté (`Film.mkv.orig`), ou exiger une durée proche, ou assumer ? (`scripts/Maintenance/Verify_Files.py:121-146`)

## Détails

- [ ] `apply_renames` : le déblocage d'un cycle passe par `X.tmpN.ext` ; si le renommage suivant échoue, le fichier y reste (le message `[ÉCHEC]` cite ce nom provisoire, mais rien ne le remet) — même famille que #50. (`libraries/common/rename.py:83`)
- [ ] `libraries/common/http.py` : l'`HTTPError` retenue entre deux essais garde sa connexion ouverte jusqu'à l'essai suivant ; appeler `close()` avant de dormir.
- [ ] Les contrôles `Content-Length` de `Tmdb.image` et `MusicBrainz._image` ne se déclenchent plus en pratique (`http.client` lève `IncompleteRead` avant, depuis #46) ; ils ne servent qu'aux tests. Les garder comme ceinture, ou les retirer avec leurs tests.
