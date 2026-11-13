# Atelier montage : mode d'emploi pour le Claude qui l'installe

L'atelier est une page claude.ai très simple : on dépose une photo ou une vidéo, on répond à 3 questions (durée, objectif, contenu) et à
une « autre demande » libre, puis « Lancer le montage ». Quelques minutes plus tard la vidéo finie apparaît dans la page, avec
« Récupérer la vidéo » et « Ajouter une modification ».

La page ne monte rien elle-même : un navigateur ne fait pas tourner ce logiciel (Python, ffmpeg, Remotion). Le bouton réveille une
**session Claude Code dans le cloud, sur le compte de la personne qui a publié la page** : c'est son abonnement Claude qui paie. Cette
session lit la demande dans la page, monte avec `montage/` (skill `montage-pro`), puis remet la vidéo dans la page.

```
Page de l'atelier ──(bouton)──> tâche programmée du compte ──> session cloud neuve (ce dépôt)
      ^                                                            │ lit la demande, monte, contrôle
      └──────────── vidéo finie + statut « Prête » <───────────────┘
```

Rien n'est jamais publié : l'atelier rend un fichier, c'est tout. Aucun outil ne touche aux comptes Instagram, Facebook ou Google.

## Ce qu'il faut avant

1. Un abonnement Claude qui donne Claude Code sur le web (claude.ai/code).
2. L'accès à ce dépôt (`montage-kit`, privé) et GitHub relié à Claude (claude.ai/connect-github, application Claude installée sur le dépôt).
3. Le connecteur **Claude Code Remote** ajouté dans claude.ai, Réglages, Connecteurs : c'est lui que le bouton utilise.
4. Licence du moteur Remotion : gratuite pour une personne seule ou une entreprise de 3 personnes au plus. Au-delà, une licence
   « Company » est à prendre (remotion.dev/license) avant le premier montage.

## Brancher l'atelier (une seule fois)

Dans une session Claude Code ouverte sur ce dépôt, écrire : « Suis montage/atelier/MODE-EMPLOI.md, partie Brancher l'atelier ».

1. **Publier la page** `montage/atelier/atelier-montage.html` avec l'outil Artifact (icône `video`), avec ces capacités :

   ```json
   {
     "db": {},
     "assets": {},
     "downloads": true,
     "sample": { "images": true },
     "mcp": { "servers": [ { "server": "Claude Code Remote", "tools": ["fire_trigger"] } ] }
   }
   ```

   Noter l'adresse de l'artefact (`https://claude.ai/...`) : c'est `ATELIER` dans la suite.

2. **Environnement cloud** : `list_environments`, prendre celui qui a le dépôt `montage-kit` (sinon en créer un avec ce dépôt).
   Noter son `environment_id`.

3. **Tâche du montage** : `create_trigger` avec
   - `name` : `Atelier montage`
   - `create_new_session_on_fire` : `true` (une session neuve et courte par montage : beaucoup moins cher)
   - ni `cron_expression` ni `run_once_at` (elle ne part que par le bouton)
   - `environment_id` : celui de l'étape 2 ; `initiation` : `human_request`
   - `prompt` : le texte « Consigne de chaque montage » ci-dessous, `ATELIER` remplacé par l'adresse de l'étape 1.

   Noter le `trigger_id` (`trig_…`).

4. **Donner la tâche à la page** : outil ArtifactData, url `ATELIER`, action `set`, collection `reglages`, document `branchement`,
   données `{"trigger_id": "trig_…", "branche_le": "<date du jour>"}`.

5. **Vérifier** : ouvrir la page. Le bandeau « pas encore branché » a disparu. Lancer un premier essai avec une photo.

## Consigne de chaque montage

À mettre tel quel dans le `prompt` de la tâche (avec `ATELIER` remplacé) :

```
Tu es l'atelier de montage. Adresse de l'atelier : ATELIER
Le message qui suit contient « DEMANDE <id> ». Fais ceci, sans poser de question, en suivant CLAUDE.md :

1. ArtifactData, action get, url ATELIER, collection « demandes », doc_id <id>.
   Puis update : statut « en_montage », message « Ton montage a commencé. ».
2. Installe les outils (README.md, partie Installation) si ce n'est pas fait.
3. Pour chaque élément de « fichiers » : outil Artifact, action read, url ATELIER, path = un id de « morceaux » (un appel par id,
   pas « paths »), dans l'ordre.
   Recolle-les avec cat dans ~/montages/<id>/sources/<nom>. Ne réencode jamais une source avant le kit.
4. Si « modifications » n'est pas vide, c'est une reprise : refais la vidéo d'après la demande et applique TOUTES les modifications de
   la liste, la dernière en priorité. Sinon c'est une première demande.
   « fiche » (s'il existe) est un premier jet écrit dans la page : un point de départ, pas un ordre.
5. Monte avec le skill montage-pro : python3 montage/montage.py nouveau ~/montages/<id>, rushes, fiche montage.json d'après « duree »,
   « objectif », « contenu » et « autre », verifier jusqu'à zéro [erreur], planche, final. Livre seulement si la garde-tête dit
   « rien à corriger » et le contrôle « BON ». Une photo seule donne une vidéo courte animée, sauf si la demande parle d'une image.
6. Si la vidéo finie dépasse 19 Mo, fais une copie pour l'atelier (ffmpeg, même taille d'image, -crf plus haut) qui passe sous 19 Mo.
   Outil Artifact, action publish, url ATELIER, asset true, file_path = ce fichier. Note l'id renvoyé.
7. ArtifactData update de demandes/<id> : statut « terminee », resultat {"asset_id": "<id>", "nom": "<nom>.mp4", "type": "video/mp4"},
   message : une ou deux phrases simples (ce que tu as fait ; les coupes « à écouter au casque » s'il y en a).
8. Problème que tu ne peux pas régler : statut « erreur » et message qui dit en mots simples quoi faire.
Ne publie rien sur aucun réseau social. N'écris rien dans le dépôt. Ne pousse rien.
```

## Si le bouton ne marche pas

Certains comptes ne laissent pas une page lancer une session : la demande reste « Pas encore parti ». Ouvrir Claude Code sur ce dépôt et
écrire : « Monte les demandes en attente de l'atelier ATELIER en suivant la consigne de montage/atelier/MODE-EMPLOI.md ». Claude fait
`list` de la collection `demandes` et prend celles au statut « a_envoyer », « en_attente » ou « modification ».

## Limites à connaître

- Les fichiers partent en pleine qualité, en morceaux de 18 Mo (la page accepte 20 Mo par fichier). Une vidéo de téléphone en 4K pèse
  des centaines de Mo : l'envoi prend du temps, garder la page ouverte pendant la barre.
- Filmer en 1080p au moins (4K, c'est mieux) : une source plus petite donne une vidéo floue.
- Compter 5 à 15 minutes par montage (installation des outils dans une session neuve comprise).
- Les formats d'iPhone (MOV, HEIC) passent : la page les envoie tels quels et le kit les convertit.
