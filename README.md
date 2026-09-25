# Kora

Un jeu de grande stratégie en temps réel (avec pause), du tout début de l'humanité jusqu'aux premiers villages.
Vous guidez un peuple de chasseurs-cueilleurs qui vient de maîtriser le feu : lire les saisons, trouver à manger,
passer l'hiver, se diviser en clans, rencontrer les autres peuples, apprendre des savoirs, puis fonder des villages,
cultiver, commercer, lever des troupes… et voir vos clans partir fonder leurs propres pays.

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

**Windows affiche « Windows a protégé votre ordinateur » ?** C'est normal pour un petit jeu qui n'est pas signé.
Cliquez sur **Informations complémentaires**, puis **Exécuter quand même**. Si votre antivirus bloque le fichier,
autorisez-le (c'est un jeu fait avec Python et PyInstaller, ces programmes sont souvent signalés à tort).

**Mise à jour :** téléchargez le nouveau `Kora.exe` (ou le nouveau zip) et remplacez l'ancien. Votre partie est
gardée ailleurs (voir plus bas), vous la retrouvez.

---

## Premiers pas

- **Clic gauche** sur une de vos bandes (un rond à votre couleur) pour la choisir, puis **clic gauche sur la carte** pour
  qu'elle y marche. Un clic sur une bande étrangère : un raid (attention, les combats sont durs).
- **Clic droit maintenu** (ou molette maintenue) et glisser : tourner la planète. **Molette** : zoomer.
- **Espace** : pause. **1 à 5** : vitesse du temps.
- Survolez une case pour voir ce qu'elle produit ; un clic l'épingle.
- Le **journal** (à droite) raconte ce qui arrive ; un clic sur une ligne y emmène la caméra.
- Les **cartes d'événements** apparaissent à gauche de l'écran : cliquez pour lire et choisir (ou **E**).

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
| **E** | Ouvrir l'événement en attente |
| **S** | Scinder la bande choisie (former un clan) |
| **F** | Réunir les bandes proches |
| **Tab** | Bande suivante |
| **C** | Poser un campement · **K** : y déposer des vivres |
| **H** | Honorer un clan (il reste fidèle) |
| **V** | Fonder un village (sur un de vos campements) |
| **L** | Lever une troupe (depuis un village) |
| **Z** / **R** / **X** | Modes de carte : zones d'influence / ressources / commerce |
| **F5** | Sauvegarder (le jeu sauvegarde aussi tout seul) |
| **Échap** | Fermer une fenêtre · menu |

---

## Où est ma partie ? Un problème ?

- La partie est sauvegardée dans **`%APPDATA%\Kora\saves\kora.json`**
  (collez `%APPDATA%\Kora` dans la barre d'adresse de l'explorateur de fichiers).
  Le menu (**Échap**) propose aussi une **Nouvelle partie**.
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
`git tag v0.1.1 && git push --tags` : GitHub construit l'exe et le met dans les Releases
(`.github/workflows/release.yml`).

La vision du jeu et les règles de travail : `docs/VISION-KORA.txt`, `CLAUDE.md`.
