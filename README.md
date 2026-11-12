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

1. Installe [Python](https://www.python.org/downloads/) (coche
   *Add python.exe to PATH* pendant l'installation).
2. Dans **GitHub Desktop** : *File* → *Clone repository* → onglet *URL*, colle
   `https://github.com/mjramos86/archiveRDSV` et clique *Clone*.
   (Sans GitHub Desktop : installe [Git pour Windows](https://git-scm.com/download/win)
   et clone le dépôt avec `git clone -c core.longpaths=true …`.)

**Ensuite, chaque fois que tu veux faire avancer l'archive :**

- Double-clique sur `ARCHIVER.bat` dans le dossier du dépôt (dans GitHub
  Desktop : *Repository* → *Show in Explorer*). Le script utilise le Git
  fourni avec GitHub Desktop s'il n'y en a pas d'autre.
- Si l'envoi vers GitHub échoue (connexion demandée), rien n'est perdu : les
  fichiers restent enregistrés sur l'ordinateur. Clique simplement
  *Push origin* dans GitHub Desktop de temps en temps.
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
