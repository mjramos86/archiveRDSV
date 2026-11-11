# archiveRDSV

Copie privée de tout ce que la Wayback Machine d'Internet Archive a conservé du
site **jeuxvideo.rds.ca** (RDS Jeux vidéo).

- `site/jeuxvideo.rds.ca/…` : les fichiers tels qu'archivés (HTML, images, CSS,
  JS…), dans leur version la plus récente sur la Wayback Machine, sans la barre
  d'outils de l'Internet Archive.
- `state/index.tsv` : toutes les adresses archivées (date de la capture, type).
- `state/done.tsv` : adresses récupérées et fichier local correspondant.
- `state/failed.tsv` : adresses impossibles à récupérer (404, trop volumineuses…).

Le téléchargement tourne dans GitHub Actions (onglet **Actions** →
*Wayback Machine dump*). Chaque exécution s'arrête avant la limite de six heures
et en relance une autre jusqu'à ce qu'il ne reste plus rien.

Les liens dans les pages pointent vers les adresses d'origine
(jeuxvideo.rds.ca); le contenu appartient à ses auteurs et à RDS / Bell Média.
Ce dépôt est destiné à un usage d'archivage personnel.
