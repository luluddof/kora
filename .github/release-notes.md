## Nouveau dans la 0.25 : l'âge du bronze

- (0.25.3) **Des savoirs qui n'arrivaient jamais arrivent** : les chiens de chasse (aussi après deux ans près du
  gibier, pas seulement par l'événement des louveteaux), les routes du sel (un peuple ami suffit, plus besoin d'un
  allié), les bœufs (150 personnes), les torches (100) et l'art du siège (200).
- (0.25.2) **Les peuples sans village en fondent enfin un** : leurs clans trouvaient une terre mais jamais le
  chemin pour y aller, et erraient des années. Le monde recommence à grandir. **Le jeu calcule plus vite** (environ
  15 % en fin de partie). Une erreur de calcul est maintenant écrite dans *kora_erreur.txt*, pour qu'on la corrige.

- **Un troisième âge dans l'arbre des savoirs**, l'âge du bronze : dix-huit savoirs, plus chers que ceux du
  néolithique (la fonte du cuivre, la roue, le bronze, les routes de l'étain...).
- **Les chemins de gameplay** : à l'entrée de l'âge, l'arbre se sépare. **La cité** (canaux, briques crues, temple,
  grenier du temple, sceaux, palais) ou **la steppe** (chariots à quatre roues, transhumance, feutre, char léger, arc
  composite, horde) : deux grands tournants qui naissent et se répandent comme les autres, mais adopter l'un **ferme
  l'autre pour tout l'âge**. L'arbre montre les deux branches côte à côte, avec un « ou » ; celle que vous n'avez pas
  prise reste visible, éteinte.
- **Le marqueur d'âge**, à côté de la saison : votre âge (à la couleur de votre voie) ; au survol, celui du monde ;
  un clic ouvre l'arbre.
- **Des événements** : « Les deux chemins » (le conseil se dispute : bâtir ou suivre les bêtes), « Le fondeur
  étranger », « Les premières rues », « Le premier grand départ ».
- Les autres peuples choisissent la voie qui va à leur façon de vivre. Vos parties continuent telles quelles.
- (0.25.1) L'onglet de la voie passe sur le bord haut des cartes de l'arbre : il ne cache plus la fin des noms.

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
