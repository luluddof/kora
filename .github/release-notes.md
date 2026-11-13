## Nouveau dans la 0.27 : le monde sans cases

- **La carte n'a plus de cases**, à aucun zoom : les sols, la mer, les lacs, la plage le long du rivage, le
  brouillard, les zones d'influence et leurs frontières sont des courbes.
- **Les vraies distances** : une portée, une vue, un rayon sont des cercles, plus des hexagones (aller en biais
  ne coûte plus deux pas).
- **Les zones d'influence rondes**, qui suivent toujours le relief (loin en plaine, à peine en montagne) et les
  rivières.
- **Les unités glissent** le long de leur chemin au lieu de sauter de case en case ; le chemin tracé est une
  courbe.
- La fiche au survol dit le sol qu'on voit sous la souris.

Et dans la 0.26 : l'onglet **Décisions** (touche D) et la soudure (rationner, acheter du grain, manger les
semences, une razzia, piller les routes de commerce, une grande chasse) ; les villages prévoient enfin juste
leur récolte.

Et dans la 0.25 : l'âge du bronze (dix-huit savoirs, les chemins de la cité ou de la steppe, le marqueur d'âge) ; des savoirs qui n'arrivaient jamais (0.25.3) ; des clans qui fondent enfin leur village, un jeu plus rapide, les erreurs écrites dans *kora_erreur.txt* (0.25.2).

Et dans la 0.24 : les bâtiments à niveaux (les logements, le terrain, la file des chantiers, la page des bâtiments), le conseil des peuples ; le tutoriel à l'écran titre (0.24.1).

Et dans la 0.23 : la faim et les ennemis sur les jetons, Affranchir un tributaire, « dernière semaine ».

Et dans les 0.21 et 0.22 :

- **Le signe de la marche** : une unité qui marche porte une petite pointe au bord de son jeton, tournée vers où elle
  va (rouge : un repli ; pâle : une troupe qui rentre au village) ; dès l'ordre donné, et aussi sur les unités
  étrangères que vous voyez venir.
- **Se libérer d'un suzerain n'est plus un clic** : un tributaire doit **se révolter**, pas avant la fin de son
  serment (deux ans, quatre si le suzerain garde des otages), au prix de son honneur ; et tout le pays du suzerain
  lui fait la guerre pour le soumettre à nouveau. Libre pour de bon seulement s'il tient jusqu'à la paix. Les
  peuples de l'IA suivent la même règle.
- **Un tutoriel** : au menu, *Tutoriel* lance une partie guidée, en quatorze petites étapes (tourner la planète,
  choisir sa bande, la faire marcher, lancer le temps, manger, l'hiver, les savoirs, les clans, les autres
  peuples...). La fiche avance d'elle-même quand vous avez fait le geste demandé. Dans toute partie, le bouton
  **F1** rouvre sa fiche.
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
