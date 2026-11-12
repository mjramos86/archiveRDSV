# archiveRDSV

Copie de tout ce que la Wayback Machine d'Internet Archive a conservé du
site **jeuxvideo.rds.ca** (RDS Jeux vidéo).

- `site/jeuxvideo.rds.ca/…` : les fichiers tels qu'archivés (HTML, images, CSS,
  JS…), dans leur version la plus récente sur la Wayback Machine, sans la barre
  d'outils de l'Internet Archive.
- `state/index.tsv` : toutes les adresses archivées (date de la capture, type).
- `state/done*.tsv` : adresses récupérées et fichier local correspondant
  (un fichier par machine qui a travaillé).
- `state/failed*.tsv` : adresses impossibles à récupérer (404, trop volumineuses…).

Les copies redimensionnées des images (photo-300x200.jpg, etc.) ne sont pas
téléchargées lorsque l'image originale, ou une copie plus grande, est archivée :
elles sont toutes listées dans `state/index.tsv`.

## Lancer le téléchargement sur ton ordinateur (beaucoup plus rapide)

La Wayback Machine ralentit fortement les serveurs de GitHub (environ un fichier
par minute). Depuis une connexion Internet à la maison, ça va beaucoup plus vite.

**Une seule fois :**

1. Installe [Git pour Windows](https://git-scm.com/download/win) (options par
   défaut) et [Python](https://www.python.org/downloads/) (coche
   *Add python.exe to PATH*).
2. Ouvre **PowerShell** et copie cette commande :

   ```
   git clone -c core.longpaths=true https://github.com/mjramos86/archiveRDSV.git "$HOME\archiveRDSV"
   ```

**Ensuite, chaque fois que tu veux faire avancer l'archive :**

- Double-clique sur `ARCHIVER.bat` dans le dossier `archiveRDSV` de ton
  dossier personnel. La première fois, Windows ouvre une fenêtre de connexion
  à GitHub : connecte-toi pour autoriser l'envoi des fichiers.
- Tu peux fermer la fenêtre, mettre l'ordinateur en veille ou l'éteindre
  n'importe quand. La prochaine fois, ça reprend là où ça s'est arrêté (au pire,
  les dix dernières minutes sont refaites).
- Les fichiers sont envoyés sur GitHub toutes les 10 minutes environ.

## Sur GitHub Actions

Sans ordinateur, le téléchargement continue tout seul dans GitHub Actions
(onglet **Actions** → *Wayback Machine dump*), plus lentement. Dès que
`ARCHIVER.bat` tourne sur ton ordinateur, GitHub Actions se met en pause; il
reprend automatiquement si l'ordinateur n'a rien envoyé depuis deux heures.

Les liens dans les pages pointent vers les adresses d'origine
(jeuxvideo.rds.ca); le contenu appartient à ses auteurs et à RDS / Bell Média.
Ce dépôt est destiné à un usage d'archivage personnel.
