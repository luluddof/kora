# Kora — consignes pour chaque session

Jeu de grande stratégie (Python 3.13, pygame-ce), du feu jusqu'aux civilisations.
L'auteur est francophone : répondre en français.

## Avant toute chose
0. `python tools/notes.py status` (le crochet de début de session l'affiche déjà) : la
   **vraie date du jour**, la version, la dernière spec, et si une note ment. Un problème
   signalé se corrige AVANT le reste.
1. Lire **docs/VISION-KORA.txt** en entier : la vision, les principes non négociables,
   toutes ses demandes dans l'ordre et leur état, les règles de travail, les pistes ouvertes.
2. Lire la dernière spec (celle que donne `notes.py status`) et
   docs/code/carte-du-depot.txt (où est quoi, qui appelle qui).
3. Avant d'ajouter ou de changer une fonctionnalité : docs/code/ajouter-un-systeme.txt
   (la recette, et toutes les règles du code par thème ; tests/test_architecture.py les vérifie).

## Exigence de l'auteur (2026-09-25)
Il a été mécontent qu'on fasse « le minimum ». Il attend le maximum : chaque demande
livrée dans toute sa dimension (simulation + interface + IA + carte + événements +
équilibrage + sauvegarde), vérifiée **dans sa propre partie**, exe livré, notes tenues.
(2026-10-16) Il aime ajouter des fonctionnalités et veut continuer ; pas de fin de partie
pour l'instant ; il garde Python.

## Règles dures
- Ne JAMAIS modifier ses parties (`%APPDATA%\Kora\saves\` : `partie-*.json`, `kora.json`) :
  les copier dans le scratchpad. Les essais de l'exe se font avec un APPDATA isolé.
- Ne pas reconstruire `dist/Kora` si `Kora.exe` tourne (vérifier le processus) :
  construire à part et le dire au joueur.
- La simulation (tout sauf l'interface) n'importe jamais pygame.
- Le jeu est déterministe : `tools/empreinte.py check empreinte.json` prouve qu'une
  optimisation ne change rien ; ré-enregistrer quand le jeu change volontairement.
- Le Python du projet : `.venv/Scripts/python.exe` (pygame-ce ; celui du système a un autre
  pygame). Tests : `.venv/Scripts/python.exe -m pytest -q` (test_balance juge sur 4 graines ;
  test_notes juge les notes).
- **Les dates se lisent, elles ne s'inventent pas** : le jour de la machine (`notes.py status`),
  le passé dans git. Jamais « un jour de plus par chantier » (des sessions avaient daté leur
  travail du 9 au 11 octobre jusqu'au 18 octobre).
- Dépôt git (branche `main`) : **github.com/luluddof/kora** (public depuis le 2026-09-25, pour que
  des amis testent). Committer et pousser à la fin d'un chantier, en tant que `luluddof` (identité
  git locale : l'adresse privée GitHub de luluddof ; ne jamais publier d'e-mail ni de chemin
  personnel). Deux comptes gh sont connectés : pour pousser, `gh auth switch --user luluddof`,
  `git -c credential.helper= -c "credential.helper=!gh auth git-credential" push`, puis revenir au
  compte actif habituel (son nom est dans la mémoire locale, pas dans ce dépôt public).
- Publier une version pour les testeurs : `__version__` dans `src/kora/__init__.py`, commit, puis
  `git tag -a vX.Y.Z -m "..."` et pousser l'étiquette : GitHub Actions (`.github/workflows/release.yml`)
  teste, construit l'exe et met `Kora.exe` (un seul fichier, `Kora-unfichier.spec`) et `Kora-windows.zip` (le dossier) dans les Releases. Si rien ne démarre :
  `gh workflow run release.yml -R luluddof/kora --ref vX.Y.Z`.
- Le passage en « mode cloud » viendra plus tard, à sa demande.

## En fin de chantier
Mettre à jour docs/VISION-KORA.txt (sections 3 et 5), la spec du chantier (datée du jour),
docs/code/ajouter-un-systeme.txt (une règle nouvelle : section 4, à son thème),
docs/code/carte-du-depot.txt (ses parties écrites à la main ; les docstrings des modules
touchés pour le reste), le README si le joueur voit un changement, et la mémoire ; puis
`python tools/notes.py write` et `python tools/notes.py check` (0 problème) ; répondre point
par point à la demande.
