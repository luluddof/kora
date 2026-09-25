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

Mise à jour : remplacez simplement l'ancien fichier ; votre partie est gardée dans `%APPDATA%\Kora\saves`.

Les touches et les premiers pas : voir la page du projet (README).
Un problème ? Envoyez le fichier `%APPDATA%\Kora\kora_erreur.txt` (et votre `kora.json`).
