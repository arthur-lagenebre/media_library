# TODO

Ce qui reste à faire, et ce qui a été tranché (à ne pas rouvrir sans fait nouveau). Le détail du travail fini est dans les PR citées. Une prochaine passe d'analyse s'ajoute ici ; cocher une case dans la PR qui règle le point.

## À faire

Reste de la troisième passe d'analyse (novembre 2026), arrêtée là : rendement attendu plus faible que pour les deux premières.

- [ ] Relire à froid le code écrit pendant la deuxième passe : `libraries/common/volumes.py` (détection d'un partage réseau, jamais essayée sur un vrai NAS), `tools.read_timeout`, `rename.put_back`, `textfile.write` atomique, `discography.inventory`.
- [ ] Mesurer la couverture réelle des tests sur ces fichiers (module `trace` de la bibliothèque standard) pour repérer les branches qu'aucun test n'exerce.
- [ ] Vérifier à la lecture les API utilisées par rapport à Python 3.8, faute d'un interpréteur 3.8 en local : la CI en a déjà pris un en défaut (`HTTPError.close()`, #72).
- [ ] Essayer sur de vrais fichiers ce que tout le travail a seulement simulé :
  - `Music/Verify_Flac.py` et `Verify_Mp3.py` sur la vraie médiathèque (temps du contrôle rapide d'un `.mp3` sur le NAS, `--full`, faux positifs sur des fichiers anciens) ;
  - `Verify_Mkv.py --repair` avec ses `.orig` ;
  - le délai de lecture sur le NAS ;
  - un renommage de casse sous Windows avec un fichier verrouillé ;
  - `--log` dans une vraie console Windows, sur un script qui pose des questions (`Discography.py` sans `--no-ask`).

## Décisions prises

- **`Verify_Mkv.py --repair` garde l'original** à côté (`Film.mkv.orig`, puis `.orig2`… sans jamais en écraser un). Sur un fichier abîmé, `mkvmerge` peut ne récupérer qu'une partie du film. Le traitement se fait sur le PC avant transfert au NAS, la place n'est pas en jeu ; les `.orig` se suppriment à la main. Une option pour ne pas les garder reste possible si le script tourne un jour sur le NAS.
- **Les contrôles `Content-Length`** de `Tmdb.image` et `MusicBrainz._image` sont gardés comme ceinture, avec un commentaire qui le dit, bien que `http.client` lève `IncompleteRead` avant eux en pratique.
- **Seul `Discography.py` est strict sur un dossier illisible** : `discography.inventory` lève `OSError` plutôt que de prendre un album illisible pour un album manquant, parce que ce script écrit à partir de ce qu'il ne trouve pas. Le reste de l'application, `find_albums` en tête, garde sa tolérance.
- **Aucun journal sans `--log FICHIER`**, pour tous les scripts (#105, #106) ; `--log-dir` a disparu. Les fichiers de décision de `Movies/Metadata.py` (`metadata.ok`, `.collections`, `.titles`) restent à la racine de `--dir` sans `--log`, à côté du journal avec.

## Fait

- **Première passe** (#46 à #52) : réponse HTTP coupée en route réessayée puis levée en erreur du client ; duplications retirées (`remux.py`, `common/http.py`, `tools.display_command`) ; `process_album`, `match_tracks` et `target_tags` découpés ; renommage « casse seule » interrompu qui reprend son nom ; `textfile.write` atomique.
- **Deuxième passe** (#56 à #78) : titres vides qui faisaient planter `Rename_Movies.py` ; dossier illisible pris pour un album manquant par `Discography.py` ; délai de 120 s sur les lectures d'outils externes sur un partage réseau ; toutes les fonctions de complexité 20 ou plus découpées, chacune avec une comparaison avant/après ; `Movies/Metadata.py` ramené de 748 à 388 lignes ; `put_back` après un cycle de renommages interrompu ; connexion d'une `HTTPError` fermée.
- **Troisième passe** : 24 000 fichiers abîmés au hasard donnés aux lecteurs (`flac`, `mp3`, `epub`, `cbz`, pochettes) ; aucun plantage hors erreur métier, aucun blocage.
