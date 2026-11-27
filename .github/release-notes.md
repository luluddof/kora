## Nouveau dans la 0.33 : une revue du code, et ses corrections

Six relecteurs ont passé le jeu au crible ; voici ce qui est corrigé.

- **Vos ordres de marche ne se perdent plus** : un clic vers un lieu lointain (18 à 25 lieues) était ignoré une fois
  sur deux, sans un mot. Il part maintenant (et s'il n'y a vraiment pas de chemin, le jeu le dit).
- **Les clics ne traversent plus l'interface** : un clic droit sur la barre, la fiche d'une bande ou la colonne de
  gauche n'attaque plus l'étranger dessiné dessous ; un clic gauche ne fait plus marcher la bande.
- **La durée d'un trajet est juste**, montagne comprise (avant : « 1 semaine » annoncée pour 21).
- **Moins de faim** : la semaine de la récolte, on récolte avant de manger ; la prévision voit le creux de l'hiver
  (le rationnement, le grain, la soudure s'y fient). Sur deux ans d'une partie avancée : 3 fois moins de semaines
  de faim, 3 fois moins de morts de faim dans les villages.
- **La guerre** : plus de peuple dans les deux camps d'une bataille, plus de village soumis libéré la semaine même,
  plus de guerre entre deux peuples d'un même pays ; une seule paix, qui lie les deux pays ; on ne redéclare plus la
  guerre pendant un tribut ou une trêve ; un motif n'est pas une guerre (l'ordre d'attaque le dit).
- **Le début** : les cartes de la vie de bande sur tous les sols (jungle, savane, côte, marais, toundra, désert),
  une carte nouvelle pour la côte ; la grande chasse et les éclaireurs dès l'âge tribal.
- **Les savoirs** : un village apprend de toute sa zone, et d'un voisin qui sait ; l'arc s'apprend aussi en savane.
- **Le monde** : les grands travaux, la route du sel et l'essor des chefferies naissent enfin ; les routes de commerce
  ne s'ouvrent et ne se ferment plus en boucle.
- **La sauvegarde** s'écrit d'un coup (jamais un fichier à moitié écrit) ; un disque plein ne ferme plus le jeu ; une
  partie rechargée continue exactement comme si on ne l'avait pas quittée.
- Et une vingtaine de petites choses (des textes, l'arbre des savoirs plus fluide, la touche L dans le village…).

Et dans la 0.32 : des interfaces qui se lisent

- **Ce qui vous attend est à gauche** : les **alertes** (la faim, une disette en vue, un siège, un clan qui veut
  partir, la solde impayée, une guerre déclarée), et un clic mène où agir ; les cartes d'événements ; et, tant que
  vous n'avez pas de village, **le chemin du premier village**, étape par étape, avec ce qui manque.
- **Le grave se voit** : un gain en vert avec une pointe vers le haut, une perte en rouge avec une pointe vers le bas
  (les effets des événements en pastilles, les décisions, la stabilité d'un village). La fiche d'une bande a des
  **jauges** (les vivres, la collecte) qui rougissent quand la faim menace ; les ordres impossibles sont éteints.
- **La barre du haut** nomme vos comptes, montre s'ils montent ou baissent, rougit quand ça va mal ; leur survol
  les explique ; *Choisir un savoir* est un bouton.
- **Plus lisible** : des textes plus grands et plus contrastés, un seul style de titre, *Fermer* toujours gris
  (l'orange est pour l'action de l'écran), les distances en **lieues** ; le commerce en deux lignes par bien ; le
  journal et les nouvelles ne répètent plus « Famine : 1 morts » chaque semaine.
- Corrigé : le bas du panneau Village s'écrivait sur lui-même ; le panneau Tribu cachait la fiche de la bande ;
  l'icône d'un village couvrait son nom ; des noms d'onglets coupés.

Et dans la 0.31 : le monde sans cases, la fin

- **Toute proximité se mesure de point à point** : la vue, la collecte, les terres d'un village, le ravage, le
  siège, les renforts, les razzias… partent du point exact d'une unité ou d'un lieu, plus du centre de sa case.
- **Les batailles ont lieu à un point**, là où l'ennemi a été rejoint ; leurs marques y restent.
- **Les chemins cherchés vont aussi en biais** : le trajet choisi n'a plus le biais des cases (un lac contourné
  par où c'est vraiment plus court).
- Corrigé : la vue d'un grand rayon perdait son haut et son bas ; une désynchronisation possible à plusieurs.
- La simulation est un peu plus rapide.

Et dans la 0.30 : le monde sans cases, encore un pas

- **Les unités marchent tout droit** quand ça ne coûte pas plus cher : plus d'escalier d'un lieu à l'autre. Elles
  contournent toujours ce qui coûte (un lac, une montagne, un sol plus rude). Le chemin tracé à l'écran est celui
  qu'elles feront. En biais, un trajet de 14 lieux prend 4 semaines au lieu de 5.
- **Les rencontres à la distance** : deux bandes ennemies se battent quand elles sont à trois quarts de lieu l'une
  de l'autre, plus « dans le même lieu ». Deux troupes qui se croisent en chemin, ou une bande rattrapée par celle
  qui la poursuit, se rencontrent aussi (deux clans qui errent ne se cherchent pas). Un village reste un lieu : on
  ne l'attaque qu'en y entrant.
- **Les lieux à un point** : un camp, une cache, un village sont là où la bande s'est arrêtée, plus au centre d'un
  lieu. Une partie d'avant se charge telle quelle.

Et dans la 0.29 : la guerre qui aboutit

Avant, une guerre se déclarait puis s'éteignait sans rien : une levée ne peut pas prendre un village derrière
ses murs. Maintenant, comme au néolithique, on ruine ce qui est dehors jusqu'à ce que l'autre sorte ou plie.

- **Ravager [C]** : une troupe postée dans les champs d'un village ennemi brûle sa récolte semaine après
  semaine, peut emmener son troupeau, vit sur le pays, et fait monter **votre avantage dans la guerre**.
- **Trois fins** au lieu d'une : le village **se soumet** (tributaire), il **paie un tribut de guerre** (deux ans,
  et la guerre finit), ou, assiégé et affamé trois semaines, il **ouvre ses portes**.
- **La sortie** : un village dont on ravage les champs lève tous ses hommes et attaque la troupe en terrain
  ouvert, sans ses murs. Les autres peuples le font ; quand c'est vous, une carte vous le demande (sortir, tenir,
  ou payer pour qu'ils partent).
- **Les autres peuples font la guerre ainsi** : ils ravagent le voisin dont ils battraient la sortie, se replient
  devant plus fort, exigent la soumission ou un tribut.
- À l'écran : un **feu** sur un village ravagé ou assiégé, ses champs qui pâlissent, la fiche du village et l'écran
  des guerres qui disent ce qui est perdu, le bouton **Exiger un tribut**.
- La **razzia** (Décisions) ravage d'elle-même quand les murs sont trop forts pour un assaut.

Et dans la 0.28 : le monde sans cases, la suite

- **La carte ne scintille plus** quand le temps avance : le fond ne se redessine qu'avec la vue ; le brouillard,
  les zones d'influence et les champs se posent par-dessus.
- **Les unités sont à un point**, n'importe où (plus au centre d'une case) : elles marchent en continu, s'arrêtent
  où leur élan s'arrête (plus d'élan perdu à attendre), et vont au point exact que vous cliquez.
- **Les champs des villages** sont des surfaces dorées et sillonnées ; **les rivières** sont des courbes.
- **Même sur un même sol, l'influence porte plus ou moins loin** selon qu'il est plus ou moins rude (comme la
  marche).

Et dans la 0.27 : le monde sans cases

- **La carte n'a plus de cases**, à aucun zoom : les sols, la mer, les lacs, la plage le long du rivage, le
  brouillard, les zones d'influence et leurs frontières sont des courbes.
- **Les vraies distances** : une portée, une vue, un rayon sont des cercles, plus des hexagones (aller en biais
  ne coûte plus deux pas).
- **Les zones d'influence rondes**, qui suivent toujours le relief (loin en plaine, à peine en montagne) et les
  rivières.
- **Les unités glissent** le long de leur chemin au lieu de sauter de case en case ; le chemin tracé est une
  courbe.
- La fiche au survol dit le sol qu'on voit sous la souris.
- (0.27.1) La 0.27.0 n'a pas été publiée (un test a échoué au moment de la construction) : la 0.27.1 est la
  même, corrigée.

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
