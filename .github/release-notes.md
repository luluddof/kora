## Nouveau dans la 0.21

- **Un tutoriel** : au menu, *Tutoriel* lance une partie guidée, en quatorze petites étapes (tourner la planète,
  choisir sa bande, la faire marcher, lancer le temps, manger, l'hiver, les savoirs, les clans, les autres
  peuples...). La fiche avance d'elle-même quand vous avez fait le geste demandé. Dans toute partie, le bouton
  **Tuto** (en bas à gauche, à côté de *Carte*) ou **F1** l'ouvre et le ferme.
- **Le jeu ne se fige plus** dans les parties avancées : la semaine se calcule par petits morceaux, entre deux
  images. Les parties avancées tournent aussi **jusqu'à 2,5 fois plus vite**, sans que rien ne change au jeu
  (la même partie, les mêmes résultats). **F3** montre ce que coûtent l'image et la semaine, et la vitesse tenue.
- Sous le capot : le code est rangé en modules plus petits (les villages, leurs bâtiments, leurs troupes ; la
  diplomatie et la guerre ; la partie à l'écran), et ses notes de travail sont désormais vérifiées.

Toutes les nouveautés, version par version : la page du projet et ses *Releases*.

## Installer (Windows 10 ou 11, 64 bits)

**Le plus simple : téléchargez `Kora.exe` ci-dessous et double-cliquez dessus.** C'est tout : un seul fichier,
rien à installer. Le lancement prend quelques secondes (il se décompresse à chaque fois).

Autre possibilité, qui démarre un peu plus vite : `Kora-windows.zip` → clic droit → **Extraire tout…** → ouvrez le
dossier `Kora` et lancez `Kora.exe` (dans ce cas, gardez tout le dossier : l'exe a besoin du dossier `_internal`
posé à côté de lui).

**Sans l'alerte « Windows a protégé votre ordinateur »** (le jeu n'est pas signé) :
- appuyez sur **Windows + R**, collez cette ligne, **Entrée** : le jeu se télécharge dans *Téléchargements* et se lance,
  sans alerte :

  ```
  cmd /c curl -L -o "%USERPROFILE%\Downloads\Kora.exe" https://github.com/luluddof/kora/releases/latest/download/Kora.exe && start "" "%USERPROFILE%\Downloads\Kora.exe"
  ```
- ou, après l'avoir téléchargé : clic droit sur `Kora.exe` → **Propriétés** → cochez **Débloquer** → **OK** ;
- ou, dans l'alerte : **Informations complémentaires** → **Exécuter quand même**.

Pour héberger une partie à plusieurs, Windows peut demander d'autoriser Kora sur le réseau : acceptez (réseaux
privés).

Mise à jour : remplacez simplement l'ancien fichier ; votre partie est gardée dans `%APPDATA%\Kora\saves`.

Les touches et les premiers pas : voir la page du projet (README).
Un problème ? Envoyez le fichier `%APPDATA%\Kora\kora_erreur.txt` (et la sauvegarde de la partie, dans
`%APPDATA%\Kora\saves`).
