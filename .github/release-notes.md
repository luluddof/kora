## Nouveau dans la 0.2

**0.2.1** : à plusieurs, après une recopie de la partie (une machine écartée, un joueur qui revient), toutes les
machines repartent exactement de la même partie (plus de recopies à répétition).

- **Un menu de démarrage** : *Continuer* votre partie, *Nouvelle partie*, *Multijoueur*. Une nouvelle partie met
  l'ancienne de côté (elle n'est plus effacée).
- **Votre peuple** : son nom (ou *Au hasard*), sa couleur, et **2 bonus de départ parmi 12** (chasseurs d'aurochs,
  enfants du froid, conteurs, guerriers redoutés, peuple fécond…). Ils durent **5 ans**, puis s'éteignent.
- **Le multijoueur**, jusqu'à 4 joueurs sur la même planète : un joueur héberge, les autres le rejoignent par son
  adresse ; chacun son peuple (vallée, steppe, forêt, côte), les places libres restent à l'IA. Pause et vitesse pour
  tous, discussion (**Entrée**), propositions entre joueurs en cartes à décider, reprise d'une partie sauvegardée.
  Par Internet : un réseau privé commun (Radmin VPN, ZeroTier, Tailscale) ou le port 45170 ouvert chez l'hôte.
  Tout le monde doit avoir **la même version**. Le détail : la page du projet (README), *Jouer à plusieurs*.

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
Un problème ? Envoyez le fichier `%APPDATA%\Kora\kora_erreur.txt` (et votre `kora.json`).
