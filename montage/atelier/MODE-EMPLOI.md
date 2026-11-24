# Atelier montage : mode d'emploi pour le Claude qui l'installe

L'atelier est une page claude.ai très simple : on dépose une photo ou une vidéo, on choisit Story, Reel ou Post (un ou plusieurs), on répond à 3 questions (durée, objectif, contenu) et à
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

Rien n'est jamais publié : l'atelier rend un fichier et sa légende à copier, c'est tout. Aucun outil ne touche aux comptes Instagram, Facebook ou Google.

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
   Une modification peut porter un « point » {t, x, y} : l'endroit que la personne a touché sur la vidéo finie (t en secondes,
   x et y de 0 à 1 sur l'image : en 1080x1920, x*1080 et y*1920 px) et « image », l'id d'une image de cet instant avec un cercle
   rouge (outil Artifact, action read, path = cet id). La modification s'applique à cet endroit-là.
5. Monte avec le skill montage-pro : python3 montage/montage.py nouveau ~/montages/<id>, rushes, fiche montage.json d'après « duree »,
   « objectif », « contenu » et « autre », verifier jusqu'à zéro [erreur], planche, final. Livre seulement si la garde-tête dit
   « rien à corriger » et le contrôle « BON ». Une photo seule donne une vidéo courte animée, sauf si la demande parle d'une image.
   « type » (Story, Reel ou Post) donne la clé "format" de la fiche : « format » de la demande (Story et Reel : "9:16",
   Post : "4:5"). Story : 15 s conseillées, aucun texte dans le haut et le bas de l'image (zones de l'appli). Sans « type », Reel.
   Si plusieurs types sont cochés, la page crée une demande par type (mêmes fichiers) : chaque session ne fait que le sien.
   Si « identite » est rempli, mets « identite.theme » tel quel dans la clé "theme" de la fiche (identité choisie dans l'onglet
   « Identités visuelles » de la page) ; sinon choisis un thème du kit.
   Si « identite.note » est rempli, respecte-la (exemple : Arcade, police sans majuscules accentuées : textes sans accents).
6. Renvoie la vidéo finie en pleine qualité, sans la réencoder : coupe-la en morceaux de 18 Mo
   (split -b 18874368 -d -a 2 --additional-suffix=.mp4 <video> morceau-), puis, pour chaque morceau dans l'ordre :
   outil Artifact, action publish, url ATELIER, asset true, file_path = ce morceau. Note les id renvoyés, dans l'ordre.
7. ArtifactData update de demandes/<id> : statut « terminee »,
   resultat {"morceaux": ["<id1>", "<id2>", ...], "nom": "<nom>.mp4", "type": "video/mp4", "octets": <taille>},
   legende : le texte à coller sous la vidéo, écrit comme le service réseaux (ton du commerce, simple et sympa, une
   accroche, 2 à 4 phrases, un appel à venir ou à réagir, 5 hashtags au plus ; aucun prix, aucune remise, aucune promo
   qui ne soit écrite dans la demande). Story : pas de légende, mais le texte à poser sur la story et une idée de sticker
   (sondage, question, lien), en deux lignes.
   message : une ou deux phrases simples (ce que tu as fait ; les coupes « à écouter au casque » s'il y en a).
   La page recolle les morceaux quand on appuie sur « Voir la vidéo » ou « Récupérer la vidéo ».
8. Problème que tu ne peux pas régler : statut « erreur » et message qui dit en mots simples quoi faire.
Ne publie rien sur aucun réseau social. N'écris rien dans le dépôt. Ne pousse rien.
```

## Onglet « Identités visuelles »

La page montre les identités visuelles avec un aperçu : celles du logiciel (Foulées, Télémétrie, Cinéma, Neutre) et les 12 faites
pour Foulées le 9 novembre 2026 (Chrono, Carnet du coureur, Sortie, Studio épuré, Étiquette boîte kraft, Magazine, VHS, Typo cinétique,
Stop-motion papier, Nuit, Arcade, Affiche), traduites en couleurs et polices du logiciel. On y change les couleurs
(fond, titres, textes, couleur forte, gris), la police des titres et des textes, les majuscules, et on peut en créer de nouvelles. Les
changements sont gardés dans la base de la page (collection « identites ») ; « Revenir à l'origine » efface une modification. Dans le
formulaire, on choisit l'identité d'une vidéo ; la demande en emporte une copie (« identite »), que la session met dans la fiche.

Chaque identité a un vrai aperçu (affiche, duel, carnet, VHS, néons…) fait avec les photos du magasin rangées dans la base
de la page (document « reglages/fonds » : photos et paires détourées, en assets de la page). On les ajoute ou les retire dans
l'onglet Identités, « Photos du magasin ». Aucune photo n'est dans le dépôt.

## Mes vidéos : Reels, Stories, Posts

La liste des vidéos est rangée en trois onglets selon le type choisi (une ancienne demande sans type va dans Reels). Sous chaque
vidéo prête, la légende écrite par la session (« legende ») s'affiche avec un bouton « Copier » ; si elle manque, la page la fait écrire une fois par le Claude du compte (mêmes règles). Rien n'est publié par la page :
« Publier » ouvre le partage du téléphone (Instagram, Facebook…) avec la vidéo et copie la légende ; la personne valide
elle-même dans l'appli. Sur ordinateur, la vidéo est enregistrée à la place.

« Supprimer » (deux appuis) efface la demande, sa vidéo finie, ses images pointées et ses fichiers envoyés s'ils ne servent à
aucune autre vidéo. Une session de montage qui ne trouve plus sa demande s'arrête sans rien faire.

## Pointer sur la vidéo finie

Sous une vidéo prête, « Pointer sur la vidéo » met la vidéo en pause et attend qu'on touche l'endroit à changer. Un cercle s'y pose, puis
on écrit à Claude ce qu'il faut ajouter ou modifier là. La modification part avec l'instant, l'endroit et une image de contrôle.

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
