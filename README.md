# Kora

Un jeu de grande stratégie en temps réel (avec pause), du tout début de l'humanité jusqu'aux premiers villages.
Vous guidez un peuple de chasseurs-cueilleurs qui vient de maîtriser le feu : lire les saisons, trouver à manger,
passer l'hiver, se diviser en clans, rencontrer les autres peuples, apprendre des savoirs, puis fonder des villages,
cultiver, commercer, lever des troupes… et voir vos clans partir fonder leurs propres pays. Seul, ou **à plusieurs**
(jusqu'à 4 joueurs sur la même planète).

> Version de test. Merci de jouer, et de dire ce qui cloche !

---

## Installer (Windows 10 ou 11, 64 bits)

**Le plus simple : téléchargez [Kora.exe](https://github.com/luluddof/kora/releases/latest/download/Kora.exe)
et double-cliquez dessus.** Un seul fichier, rien à installer : rangez-le où vous voulez (le Bureau, par exemple).
Le lancement prend quelques secondes (le jeu se décompresse à chaque fois).

Autre possibilité, qui démarre un peu plus vite :
[Kora-windows.zip](https://github.com/luluddof/kora/releases/latest/download/Kora-windows.zip) → clic droit →
**Extraire tout…** → ouvrez le dossier `Kora` et lancez `Kora.exe`. Dans ce cas, gardez tout le dossier :
cet exe-là a besoin du dossier `_internal` posé à côté de lui.

Toutes les versions : **[Releases](https://github.com/luluddof/kora/releases)**.

### Sans l'alerte « Windows a protégé votre ordinateur »

Windows affiche cette alerte pour tout programme téléchargé avec un navigateur qui n'est pas signé (c'est le cas de
ce petit jeu). Trois façons de faire :

- **Une commande qui télécharge et lance le jeu, sans alerte.** Appuyez sur **Windows + R**, collez cette ligne, puis
  **Entrée** :

  ```
  cmd /c curl -L -o "%USERPROFILE%\Downloads\Kora.exe" https://github.com/luluddof/kora/releases/latest/download/Kora.exe && start "" "%USERPROFILE%\Downloads\Kora.exe"
  ```

  Le jeu est rangé dans votre dossier **Téléchargements** ; les fois suivantes, lancez-le de là (ou refaites la commande
  pour avoir la dernière version).
- **Débloquer le fichier téléchargé.** Clic droit sur `Kora.exe` → **Propriétés** → en bas de l'onglet **Général**,
  cochez **Débloquer** → **OK**. Ensuite, un double-clic suffit.
- **Ou laisser passer l'alerte** : **Informations complémentaires**, puis **Exécuter quand même**.

Si votre antivirus bloque le fichier, autorisez-le : les jeux faits avec Python et PyInstaller sont souvent signalés à
tort.

**Mise à jour :** téléchargez le nouveau `Kora.exe` (ou le nouveau zip) et remplacez l'ancien. Votre partie est
gardée ailleurs (voir plus bas), vous la retrouvez.

---

## Premiers pas

- Au lancement, le **menu** : *Continuer* votre partie, *Nouvelle partie*, *Multijoueur*.
- Une nouvelle partie commence par **votre peuple** : son nom (ou *Au hasard*), sa couleur, et **2 bonus de départ**
  à choisir parmi 12 (chasseurs d'aurochs, enfants du froid, conteurs, guerriers…). Ils durent **5 ans**, puis
  s'éteignent (le panneau *Tribu* dit combien de temps il leur reste).
- **Clic gauche** sur une de vos bandes (un rond à votre couleur) pour la choisir, puis **clic gauche sur la carte** pour
  qu'elle y marche. Une de vos bandes choisie, un **clic droit** sur une bande étrangère l'**attaque** (attention, les
  combats sont durs) ; un **clic gauche** sur un autre peuple ouvre sa diplomatie. Entre peuples qui connaissent la
  **diplomatie** (Dons et palabres), on ne s'attaque qu'après avoir **déclaré la guerre** (écran Peuples) : les
  pays (tributaires, confédérés) et les alliés suivent ; une trêve y met fin. La guerre a un **but** : les
  **soumettre** (prendre leur village, ou **exiger leur soumission** quand vous avez l'avantage). On ne sert qu'un
  suzerain : soumettre un tributaire, c'est le prendre à son suzerain, et la guerre est contre tout son pays (ou
  visez son suzerain : **Guerre à tout leur pays**). Un **motif** (terres disputées, silex ou sel de leurs terres,
  succession disputée, tribut refusé) permet de déclarer la guerre sans honte. Les alliances sans ennemi commun
  s'usent ; un accord commercial n'empêche pas la guerre.
- **Clic droit maintenu** (ou molette maintenue) et glisser : tourner la planète. **Molette** : zoomer.
- Le bouton **Carte** (en bas à gauche) déroule les modes de carte : relief, influence, suzerains, tournants,
  ressources, commerce.
- **Espace** : pause. **1 à 5** : vitesse du temps.
- Survolez une case pour voir ce qu'elle produit ; un clic l'épingle.
- Le **journal** (à droite) raconte ce qui arrive ; un clic sur une ligne y emmène la caméra.
- Les **cartes d'événements** apparaissent à gauche de l'écran : cliquez pour lire et choisir (ou **E**).
- Les **situations** s'affichent sous la barre du haut : des **crises** (disette, épidémie, gibier épuisé, grand hiver,
  rouille des blés, mal des bêtes, crue) et des **conjonctures** où plusieurs peuples se disputent la première place
  (grand passage des troupeaux, rassemblement des clans, grands travaux, route du sel, essor des chefferies). Elles
  naissent de ce qui se passe dans votre partie, et certaines sont rares. Un clic ouvre leur fenêtre : comment s'en
  sortir, ce que coûte chaque action, le temps qui reste. Une crise surmontée : tout redevient comme avant. Une
  conjoncture gagnée face à d'autres peuples : un bonus de quelques années. Une crise que l'on peut voir venir est
  annoncée (« Risque : … ») avec le moyen de l'éviter.
- Une **bataille** dure des jours : chaque jour on tue, on blesse, on démoralise. Le général, le terrain, les armes et
  la fortune du jour comptent ; quand une bataille vous touche, le temps passe en jours. Vous pouvez vous replier.
- Vos gens sont des **enfants, des hommes, des femmes, des anciens, des blessés** : seule une part des hommes valides
  part en guerre. Un village pris n'est pas massacré : vous le **soumettez** (il devient tributaire) ou le pillez.
- La **milice** : chaque homme du village se bat comme il vit. Les chasseurs tirent (l'arc, sinon la fronde) ou
  pistent, les gens des champs et des métiers vont à la mêlée, tirent un peu, tiennent les boucliers. On ne choisit
  pas : une levée (poignée, troupe, en masse) prend la même part de chacun, et ceux qui sont partis restent dans
  leur catégorie.
- L'**ost** : un suzerain appelle les troupes de ses tributaires (fiche de sa troupe, **Ost [H]**) ; elles le
  rejoignent et ne font plus qu'une grande troupe, qu'il mène. Dissoute, chacun rentre chez soi.
- Le **siège** : avec *Torches et brandons*, les palissades de l'ennemi ne comptent plus qu'à moitié ; avec
  *L'art du siège*, une troupe en guerre qui se tient à côté d'un village ennemi l'investit : il ne trouve plus que
  35 % de ses vivres et sa défense s'use chaque semaine.
- En cet âge, **un peuple n'a qu'un village** : les autres villages de votre civilisation sont des frères
  indépendants, ou vos tributaires. Chacun travaille selon son sexe et son métier (chasse, cueillette, champs,
  poterie, silex…) ; un soldat retourne à son travail quand la troupe est dissoute.
- Avec les villages vient la **chefferie** (écran du village, *Le chef et les familles*) : le grenier du chef (sa part
  des récoltes), les fêtes, les familles qui comptent et leurs charges ; trop prendre mène à la révolte.
- L'**influence** d'un peuple se projette autour de ses bandes et de ses villages, loin en plaine, à peine en
  montagne. Avec les villages, le **savoir-faire** (chasse, agriculture, pêche, chaque métier) grandit doucement
  quand il faut produire plus ; trop produire sans acheteurs mène à la **surproduction**, puis à l'effondrement du
  commerce chez vos partenaires.
- Les **chefs des autres peuples** ont chacun leur **approche** : conquérant, protecteur, marchand, paisible,
  méfiant, aux abois (ou, s'ils sont tributaires, soumis ou rétifs). Elle vient de leur caractère et de la situation
  de leur pays, change avec elle, et décide de leurs raids, de leurs tributs, de leurs dons, et de ce qu'ils
  répondent à vos propositions (écran *Peuples*, au survol de leur approche).
- À la fin du néolithique, les **grandes chefferies** : enceintes, festins de prestige, biens de prestige, chef des
  chefs, otages et serments pour gagner ou tenir des tributaires ; ou l'araire, le lait et la laine pour prospérer
  sans eux.
- Les **savoirs** : un arbre qu'on parcourt à la souris (**T**). Certains sont de **grands tournants** (le clan, la
  sédentarité, la domestication, la terre des ancêtres, le don et l'échange) : ils **naissent** chez le premier peuple
  qui en remplit les conditions, se **répandent** chez ses voisins (plus vite entre alliés, partenaires, pays), et
  ne s'**adoptent** que quand ils sont arrivés chez vous ; adoptés (la recherche terminée), ils ouvrent tout un pan de
  l'arbre. Le **premier peuple** du monde à en terminer la recherche en est le **berceau** : du prestige et un bonus
  pour toujours. La sédentarité
  permet de fonder un village. La **carte des tournants** (**I**) montre où ils sont nés et où ils arrivent.
- D'autres savoirs sont **tirés au sort**, une fois par partie : certains ne viennent pas à tous les peuples (le
  vôtre compris), d'autres ne naissent pas dans tous les mondes, et dans certains groupes un seul naît (les croyances,
  les tombes des morts, le calendrier). L'arbre dit leur chance et ce que le sort a décidé.
- Les **nombres** : le comptage par bâtons (l'addition), puis les nombres additifs, où vous **choisissez la base**
  de vos nombres (10 : on apprend mieux ; 12 : on vend mieux ; 20 : on compte les gens ; 60 : on mesure le grain),
  presque pour toujours (c'est une **loi** du pays : écran *Pays*, onglet *Lois*, touche **N**). Des
  **calculateurs**, un métier du village, trouvent les opérations suivantes (−, ×, ÷, fractions), chacune avec son
  effet : *Savoirs*, onglet **Les nombres**.
- L'**argent** : avec les valeurs d'échange, un **trésor** et son **budget** (écran du *Trésor*, touche **G**), réglé
  par des **curseurs** : l'impôt (et ce qu'il coûte en stabilité), la solde des troupes, les gages des gens de métier,
  les présents aux familles, la paie des bâtisseurs (les chantiers avancent plus vite), de 0 à 200 % du tarif. Le
  commerce payé en argent est une **loi** (*Pays*, *Lois*). On peut aussi offrir des **sicles** aux autres peuples
  (écran *Peuples*). Avec l'argent pesé, les **mineurs** creusent les filons des collines ; avec les droits de
  passage, les convois étrangers paient pour traverser votre pays. En **disette**, un clic sur le grenier (écran
  du village) **achète du grain** à un partenaire, un allié ou un peuple de votre pays, plus cher que le marché.
- Les **pays** : un tributaire prend une nuance claire de la couleur de son suzerain (et reprend la sienne s'il se
  libère) ; la carte des **Suzerains** (touche **U**) ne montre que les grands pays et leurs villages. Avec la
  *Confédération*, deux peuples (ou jusqu'à quatre) ne font plus qu'un pays au dehors : chacun reste maître chez
  lui, mais ils se soutiennent à la guerre et font la paix ou la guerre ensemble ; si l'un devient tributaire de
  quelqu'un, la confédération est rompue pour lui.
- Un clic sur un pays ou sur un de ses villages que vous connaissez, même dans le brouillard (sans troupe choisie),
  ouvre sa **diplomatie** ; celle de son suzerain s'il est tributaire.
- Un **pays**, c'est un suzerain, ses tributaires et ses confédérés : ils **voient** ce que chacun voit, et une guerre
  contre l'un est une guerre contre tous. Les tributaires suivent leur suzerain à la guerre, mais **n'en déclarent
  pas** eux-mêmes ; un confédéré, lui, peut entraîner tout son pays.
- Le **brouillard de guerre** garde ce que vous avez vu : les villages que vous connaissez y restent, tels que vous
  les avez laissés, et la carte ne se met à jour que quand vous y revenez.

Conseils : l'hiver tue. Faites des réserves à l'automne, cherchez les vallées, et ne laissez pas vos clans s'éloigner
trop du chef. Au bout de quelques années, les savoirs du néolithique permettent de **fonder un village** : c'est un
tournant, vos clans nomades prendront peu à peu leur indépendance.

## Les touches

| Touche | Action |
|---|---|
| **Espace** | Pause / reprendre |
| **1** à **5** | Vitesse du temps |
| **T** | Savoirs (l'arbre : glisser pour se déplacer, molette pour zoomer) |
| **B** | Votre tribu (ou vos villages) |
| **P** | Les autres peuples, la diplomatie |
| **J** | Le journal |
| **A** | L'armée (dès le premier village) |
| **M** | L'écran du commerce (dès le premier village) |
| **G** | Le trésor et le budget (avec Valeurs d'échange) |
| **N** | Le pays et ses lois (avec Valeurs d'échange ou Nombres additifs) |
| **E** | Ouvrir l'événement en attente |
| **S** | Scinder la bande choisie (former un clan) |
| **F** | Réunir les bandes proches |
| **Tab** | Bande suivante |
| **C** | Poser un campement · **K** : y déposer des vivres |
| **H** | Honorer un clan (il reste fidèle) · une troupe de suzerain : appeler l'ost |
| **V** | Fonder un village (sur un de vos campements) |
| **L** | Lever une troupe (depuis un village) |
| **Z** / **U** / **I** / **R** / **X** | Modes de carte : influence / suzerains / tournants / ressources / commerce |
| **F5** | Sauvegarder (le jeu sauvegarde aussi tout seul) |
| **Entrée** | À plusieurs : écrire aux autres joueurs |
| **Échap** | Fermer une fenêtre · menu (Reprendre, Sauvegarder, Menu principal, Quitter) |

---

## Jouer à plusieurs

Jusqu'à 4 joueurs, chacun son peuple, sur la même planète (les places libres restent aux peuples de l'IA).
**Tout le monde doit avoir la même version** de Kora.

1. **L'hôte** : *Multijoueur* → *Héberger une partie* → il crée son peuple → *Ouvrir le salon*. Le salon affiche
   **l'adresse à donner aux amis**. Si Windows demande d'autoriser Kora sur le réseau, acceptez (réseaux privés).
2. **Les amis** : *Multijoueur* → *Rejoindre une partie* → l'adresse de l'hôte, leur peuple → *Rejoindre*. Dans le
   salon, un clic sur une place libre choisit son pays de départ : la **steppe** (on y connaît le troupeau), la
   **forêt**, la **côte** (on y connaît le cabotage) ; l'hôte a la vallée. Puis *Je suis prêt*.
3. L'hôte clique *Lancer la partie*.

En partie : l'hôte tient le temps ; chacun peut mettre en pause (**Espace**) ou changer la vitesse (**1** à **5**),
pour tout le monde. Ouvrir une carte d'événement ne met plus en pause. **Entrée** pour écrire aux autres. Les
propositions entre joueurs (trêve, alliance, commerce, tribut) arrivent chez l'autre comme une carte à décider.

**Par Internet** (pas dans la même maison), au choix :
- un **réseau privé commun**, gratuit : [Radmin VPN](https://www.radmin-vpn.com/fr/),
  [ZeroTier](https://www.zerotier.com/) ou [Tailscale](https://tailscale.com/). Tous l'installent et rejoignent le
  même réseau ; les amis écrivent l'adresse de l'hôte **dans ce réseau** (Radmin l'affiche à côté de son nom) ;
- ou l'hôte **ouvre le port 45170 (TCP)** de sa box vers son PC ; les amis écrivent alors son adresse publique.

Un joueur qui part laisse son peuple en attente (ses bandes ne bougent plus) ; il revient avec **le même nom** et le
retrouve. Seul l'hôte sauvegarde la partie à plusieurs : *Multijoueur* → *Reprendre la partie à plusieurs* la rouvre
(les amis rejoignent le salon avec leur nom). Si une machine s'écarte de la partie de l'hôte, elle est recopiée
toute seule.

---

## Où est ma partie ? Un problème ?

- La partie est sauvegardée dans **`%APPDATA%\Kora\saves\kora.json`**
  (collez `%APPDATA%\Kora` dans la barre d'adresse de l'explorateur de fichiers) ; la partie à plusieurs de l'hôte
  dans `kora-multi.json`, à côté. Une nouvelle partie met l'ancienne de côté (`kora-ancienne-…json`), sans l'effacer.
- Si le jeu se ferme tout seul, il écrit ce qui s'est passé dans **`%APPDATA%\Kora\kora_erreur.txt`** :
  envoyez-moi ce fichier (et votre `kora.json` si possible). La version du jeu est écrite en bas du menu (**Échap**).

---

## Pour les développeurs

```
python -m pip install -r requirements.txt
python main.py                      # lancer le jeu
python -m pytest -q                 # les tests
python -m PyInstaller Kora.spec     # l'exe en dossier, dans dist/Kora
python -m PyInstaller Kora-unfichier.spec --distpath dist-unfichier   # l'exe en un seul fichier
```

Publier une version : mettre à jour `__version__` dans `src/kora/__init__.py`, puis
`git tag -a v0.3.0 -m "..." && git push origin v0.3.0` : GitHub construit l'exe et le met dans les Releases
(`.github/workflows/release.yml`).

La vision du jeu et les règles de travail : `docs/VISION-KORA.txt`, `CLAUDE.md`. L'identité visuelle (la charte
« Feu et ocre ») : `docs/charte-graphique.txt` ; elle est codée dans `src/kora/theme.py`.

## Crédits

- Icônes : [game-icons.net](https://game-icons.net) (Lorc, Delapouite, Caro Asercion, Guard13007, Skoll), licence
  [CC BY 3.0](https://creativecommons.org/licenses/by/3.0/) ; la liste est dans `data/icons/CREDITS.txt`.
- Polices : Alegreya SC et Alegreya Sans (The Alegreya Project Authors, Huerta Tipográfica), licence
  [SIL Open Font License](https://openfontlicense.org) ; `data/fonts/OFL.txt`.
