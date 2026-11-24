# Logiciel de montage

Ce dépôt contient seulement le logiciel de montage vidéo (`montage/`) et son skill `montage-pro` (`.claude/skills/montage-pro/SKILL.md`).
Mode d'emploi du logiciel : `montage/README.md`.

Règles :
- On n'écrit jamais de code pour une vidéo : on écrit une fiche `montage.json` et on suit le skill `montage-pro`.
- Aucun fichier de client dans le dépôt (vidéo, photo, logo, musique) : les projets se montent hors du dépôt, par exemple `~/montages/`.
- Aucune clé dans le dépôt.
- `python3 montage/montage.py verifier` avant chaque rendu, jusqu'à zéro ligne `[erreur]`.
- Garde-tête : aucun texte sur ou près d'une tête ; la garde doit dire « rien à corriger » avant de livrer. On ne la contourne jamais.
- HD, rien de moche : jamais de source réduite avant le kit ; une source sous 1080 px se signale.
- Aucune musique du commerce dans un fichier livré (une musique libre avec son crédit, ou pas de musique).
- Aucun prix, aucune remise, aucune promotion inventés : seulement ce qui est écrit dans la demande.
- Rien n'est jamais publié sur un réseau social, ni aucun réglage touché sur un compte (Instagram, Facebook, Google).
- Atelier montage (page claude.ai) : `montage/atelier/MODE-EMPLOI.md`.
- Dans le skill, les passages sur le Cockpit, le service réseaux (`reseaux.py`), le Mac de Yohann et les autres fils ne s'appliquent pas ici : on les ignore.
- Moteur Remotion : gratuit pour une personne ou une entreprise de 3 personnes au plus ; au-delà, licence à prendre (remotion.dev/license).
- Sur l'ordinateur d'une personne (dossier `AtelierMontage` installé par `installeur/`) : utiliser le Python de `.venv` (`.venv/bin/python`, Windows `.venv\Scripts\python.exe`) à la place de `python3`.
