# TODO

Suivi de l'analyse du code (novembre 2026). Cocher une case dans la PR qui règle le point.

## À corriger

- [x] **1. Réponse HTTP coupée en route** — `http.client.IncompleteRead` n'est pas un `OSError` : elle échappait à `Tmdb._request` et `MusicBrainz._request`, donc à tous les `except TmdbError` / `except MusicBrainzError` des scripts, et arrêtait le passage avec une trace. Maintenant réessayée, puis levée en erreur du client. (`libraries/video/tmdb.py`, `libraries/music/musicbrainz.py`)

## À améliorer

- [x] **2. Duplication** — `Avi_To_Mkv.py` et `Mp4_To_Mkv.py` partageaient 253 lignes sur ~300 : chemin commun dans `libraries/video/remux.py`. `Tmdb` et `MusicBrainz` recopiaient `_request` / `_retry_after` : boucle commune dans `libraries/common/http.py`. Reste `display_command`, aussi défini dans `Wav_To_Flac.py`.
- [x] **3. `process_album` trop complexe** (complexité 42 → 12) — découpé en `plan_track`, `describe_track`, `verify_track`, `write_track` dans `scripts/Music/Metadata.py`. `match_tracks` (33 → 14) et `target_tags` (32 → 6) dans `libraries/music/album.py` : une fonction par étape (numéro, places douteuses, titres ; crédits, piste, édition, identifiants).
- [ ] **4. Renommage « casse seule » interrompu** — si la 2e étape de `rename_path` échoue (`libraries/common/rename.py:29`), le fichier reste sous `X.tmpN.ext` et le message ne le dit pas. Remettre le nom d'origine.

## Détails

- [ ] `textfile.write` n'est pas atomique (`libraries/common/textfile.py:23`), contrairement à `flac.write` et `mp3.write`.
- [ ] `libraries/books/` n'est utilisé par aucun script du dépôt (seulement media_hub et les tests) ; le test d'architecture vise un `scripts/Books` qui n'existe pas (`tests/test_architecture.py:56`). Le dire en commentaire, ou nettoyer.
- [x] Coquille `diffs =albums…` (`scripts/Music/Metadata.py:156`) : disparue avec le découpage de `process_album`.
