# Kora — consignes pour chaque session

Jeu de grande stratégie (Python 3.13, pygame-ce), du feu jusqu'aux civilisations.
L'auteur est francophone : répondre en français.

## Avant toute chose
1. Lire **docs/VISION-KORA.txt** en entier : la vision, les principes non négociables,
   toutes ses demandes dans l'ordre et leur état, les règles de travail.
2. Lire la dernière spec (docs/superpowers/specs/, la plus récente) et
   docs/code/carte-du-depot.txt (où est quoi).

## Exigence de l'auteur (2026-09-25)
Il a été mécontent qu'on fasse « le minimum ». Il attend le maximum : chaque demande
livrée dans toute sa dimension (simulation + interface + IA + carte + événements +
équilibrage + sauvegarde), vérifiée **dans sa propre partie**, exe livré, notes tenues.

## Règles dures
- Ne JAMAIS modifier `%APPDATA%\Kora\saves\kora.json` : le copier dans le scratchpad.
  Les essais de l'exe se font avec un APPDATA isolé.
- Ne pas reconstruire `dist/Kora` si `Kora.exe` tourne (vérifier le processus) :
  construire à part et le dire au joueur.
- sim/world/tech/villages/goods/... n'importent jamais pygame.
- Le jeu est déterministe : `tools/empreinte.py check empreinte.json` prouve qu'une
  optimisation ne change rien ; ré-enregistrer quand le jeu change volontairement.
- Tests : `python -m pytest -q` (test_balance juge sur 4 graines).
- Dépôt git local (branche `main`) depuis le 2026-09-25 : committer à la fin d'un chantier.
  Pas encore de dépôt distant : deux comptes GitHub sont connectés (demander lequel au joueur).
  Le passage en « mode cloud » viendra plus tard, à sa demande.

## En fin de chantier
Mettre à jour docs/VISION-KORA.txt (sections 3 et 5), la spec du chantier,
docs/code/carte-du-depot.txt et la mémoire ; répondre point par point à la demande.
