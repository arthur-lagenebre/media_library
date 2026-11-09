# Utiliser les agents et les skills Claude Code

Le dépôt contient cinq **sous-agents** dans [.claude/agents/](../.claude/agents/) et six **skills** dans [.claude/skills/](../.claude/skills/). Ces dossiers restent à la racine : c'est là que Claude Code les cherche.

Un sous-agent est un assistant spécialisé : Claude Code lui confie une tâche, il travaille dans son propre contexte avec ses propres outils, puis ne renvoie que son compte rendu. Un skill est une marche à suivre que Claude charge dans la conversation en cours, sans changer d'interlocuteur.

## Les agents : qui fait quoi

| Agent | À appeler pour… | Peut modifier des fichiers ? |
| --- | --- | --- |
| `video-expert` | `scripts/Video`, `libraries/video` : association aux fiches TMDB, noms de fichiers, tags et pistes Matroska, sagas, conversions AVI / MP4, vérification des `.mkv` | oui |
| `music-expert` | `scripts/Music`, `libraries/music` : association à MusicBrainz, tags FLAC et MP3 lus et écrits sans outil externe, pochettes, albums manquants, discographie, WAV vers FLAC, vérification des pistes | oui |
| `library-tester` | ajouter un test, reproduire un bug par un test qui échoue, comprendre un test qui échoue | oui (tests seulement, sauf demande explicite) |
| `library-reviewer` | relire un changement avant commit / PR | **non** (lecture seule) |
| `library-architect` | décider **avant** d'écrire : où va une fonctionnalité (`scripts/` ou `libraries/`, `common` ou un domaine), comment découper un module qui grossit, l'effet d'un changement de tag sur `media_hub`, le plan d'un refactor en PR | **non** (lecture seule) |

Règle de partage : `video` et `music` ne s'importent pas (un test le vérifie), et les deux experts non plus ne se marchent pas dessus. Une tâche qui touche `libraries/common/` ou les deux domaines se découpe : chaque expert décrit ce qu'il attend de l'autre.

## Comment les lancer

Trois façons, dans une conversation Claude Code (terminal ou extension VS Code) :

1. **Par la demande** : nomme l'agent.
   > Utilise l'agent library-reviewer pour relire ma branche.
2. **Par mention** : tape `@` puis choisis l'agent dans la liste (`@agent-library-reviewer`).
3. **Automatiquement** : sans les nommer, Claude peut déléguer de lui-même quand la demande correspond à la description d'un agent (« le matching d'album se trompe… » → `music-expert`). Nommer l'agent reste plus fiable.

La commande `/agents` liste les agents disponibles, permet de les consulter et de les modifier. Les agents sont chargés au démarrage de la session : après avoir créé ou changé un fichier de `.claude/agents/`, relance la session (ou passe par `/agents`) si l'agent n'apparaît pas.

## Exemples de demandes

Plus la demande est précise, meilleur est le résultat : un agent démarre **sans connaître la conversation**, il ne sait que ce que tu lui écris.

```text
Utilise video-expert : Movies/Metadata.py associe « Taken » à la mauvaise fiche quand le
dossier porte l'année. Trouve pourquoi, sans corriger.

Utilise music-expert : Discography.py doit sauter les singles. Ajoute l'option, ses
tests et sa ligne dans le README.

Utilise library-tester : écris un test qui reproduit « un renommage de casse seule
laisse X.tmp1.ext derrière lui », sans corriger le code.

Utilise library-reviewer : relis le diff de la branche courante contre main.

Utilise library-architect : je veux un script qui range les pochettes en double. Où
vit la logique, qu'est-ce qui peut descendre dans common, et en combien de PR ?
```

## Enchaînements utiles

**Nouveau script**
1. `library-architect` si le placement n'est pas évident (partage entre domaines, tag lu par `media_hub`) ; inutile pour un script qui ressemble à un voisin.
2. `/new-script` pour poser la structure et les conventions du dépôt.
3. L'expert du domaine écrit la logique dans `libraries/`.
4. `library-tester` complète les cas limites.
5. `library-reviewer` relit, puis `/check` et `/ship`.

**Bug**
1. `library-tester` écrit un test qui échoue pour la bonne raison.
2. `video-expert` ou `music-expert` corrige jusqu'à ce que le test passe.
3. `library-reviewer` vérifie qu'il n'y a pas de régression.

**Refactor** : `library-architect` propose le découpage et l'ordre des PR ; puis, pour chacune, prouver que rien ne change avant de la proposer (suite de tests intacte, et une comparaison ancien / nouveau code sur des scénarios identiques, comme pour les PR #47 et #49).

Plusieurs agents peuvent travailler en parallèle s'ils touchent des fichiers différents : demande-le explicitement.

## Les skills

| Skill | Pour… | Déclenchement |
| --- | --- | --- |
| `/check` | vérifier le dépôt avant un commit : toute la suite de tests, le découpage de `libraries/`, la compatibilité Python 3.8, l'absence de secret, le README | par toi, ou quand Claude le juge utile |
| `/new-script` | créer un script dans les conventions (simulation par défaut, `--apply`, bilan et code de sortie, journal, console Windows, tests, README) | par toi, ou quand tu demandes d'ajouter un script |
| `/ship` | livrer : vérifications, branche, commits, push et PR au format du dépôt | **par toi seulement** (`disable-model-invocation`) |
| `/merged` | ranger après une fusion : vérifier que GitHub a fusionné la PR, synchroniser `main`, supprimer la branche fusionnée (`git branch -d`, jamais `-D`), vérifier que sa copie distante a disparu | par toi (`/merged`), ou quand tu dis que la PR est fusionnée |
| `/ub-mode` | travailler selon les principes réduits : d'abord que ça marche, ensuite que ce soit juste, puis suivre la pratique | par toi |
| `/tech-debt-audit` | auditer toute la dette technique du dépôt : écrit `TECH_DEBT_AUDIT.md` (constats `fichier:ligne`, gravité, coût, plan en PR, section « semble mauvais mais volontaire »), sans rien corriger ; relancé, il marque les constats résolus et nouveaux | **par toi seulement** (`disable-model-invocation`) |

`/ship` ne se lance jamais seul : il commite, pousse et ouvre une PR. Il ne fusionne pas, c'est toujours à toi de le faire une fois la CI verte. `/merged` est son pendant, une fois la fusion faite : il ne fusionne ni ne pousse rien, et ne supprime que la branche de la PR fusionnée.

## Ce qu'ils ne font pas

- **Ils ne commitent pas et n'ouvrent pas de PR** (sauf `/ship`, à ta demande) : c'est toi qui décides.
- **Ils ne voient pas ta médiathèque.** Les tests travaillent sur des dossiers temporaires et de faux TMDB / MusicBrainz ; le comportement sur de vrais fichiers (lecteur verrouillé, NAS lent, vrais `.mkv`) reste à essayer sur place, et ils doivent le dire dans leur compte rendu.
- **Les tests sautés ne comptent pas.** Sans FFmpeg, le test du vrai encodage WAV vers FLAC (`tests/test_wav_to_flac.py`) est ignoré ; les agents doivent le signaler au lieu d'annoncer « tout passe ».
- **Les tags écrits sont un contrat.** `media_hub` lit ce que ces scripts écrivent (`MUSICBRAINZ_ALBUMID`, tag `TMDB`…) : changer un nom de tag ou son format casse le lecteur du NAS.
- Leurs consignes sont tirées de la lecture du code : si un agent applique une règle devenue fausse, corrige son fichier.

## Modifier ou ajouter un agent ou un skill

Un agent est un fichier Markdown dans `.claude/agents/` :

```markdown
---
name: exemple
description: Quand l'appeler (c'est ce texte qui sert à la délégation automatique).
tools: Read, Grep, Glob, Edit, Write, Bash
model: sonnet
---

Les consignes de l'agent, en Markdown libre.
```

- `description` : sois concret sur *quand* l'utiliser ; c'est ce que Claude lit pour choisir.
- `tools` : donne le minimum. Un relecteur n'a pas besoin de `Edit` ni de `Write`.
- `skills` : liste les skills chargés avec l'agent. `video-expert`, `music-expert` et `library-tester` chargent `ub-mode` (test d'abord, puis `crapper` / `dryer` / `mutator`, puis journal des actions) ; leurs consignes précisent que les règles du dépôt passent avant lui, et qu'ils ne commitent ni ne poussent sans demande.
- Garde les consignes courtes et vérifiables (invariants du dépôt, commandes à lancer, format du compte rendu).
- Ne mets **pas** d'autre fichier `.md` dans `.claude/agents/` : chaque fichier y est lu comme un agent. Cette documentation vit donc dans `docs/`.

Un skill est un dossier `.claude/skills/<nom>/` avec un `SKILL.md` (en-tête `name` et `description`, puis la marche à suivre). `disable-model-invocation: true` en fait un skill que toi seul peux lancer, à réserver aux actions qui sortent de la machine (commit, push, PR) et aux traitements longs et coûteux (l'audit complet).
