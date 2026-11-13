---
name: montage-pro
description: Monte une vidéo verticale (Reel, story, pub) ou un clip horizontal en playback avec une vraie finition pro à partir de rushes, de photos, d'une voix et d'une musique. Une fiche montage.json donne une vidéo HD aux normes, contrôlée, plus sa version sans musique. À utiliser dès qu'on dit « monte », « montage », « Reel », « edit », « vidéo pour Instagram », « face caméra », « sous-titres », ou quand des vidéos ou des photos arrivent avec une demande. C'est l'outil à prendre pour toute nouvelle vidéo (il remplace montage-reel).
argument-hint: "<dossier du projet> \"<demande en une phrase>\""
---

# Montage pro

Le logiciel est dans `montage/` (mode d'emploi complet : `montage/README.md`). On n'écrit **pas de code** pour une vidéo : on écrit une fiche
`montage.json`, le kit fait le reste (couleurs, son, textes ajustés, export aux normes, contrôle qualité).

`M` = `python3 montage/montage.py`

## Avant tout : le coût

Le prix d'une vidéo, c'est surtout le nombre d'actions multiplié par la longueur du fil. Donc :

1. **Un fil neuf par vidéo.** Ne jamais monter dans un fil déjà long.
2. **Une planche, pas trente images.** `rushes`, `planche` et `apercu` rangent tout dans UNE image.
3. **`verifier` avant tout rendu** (2 secondes, gratuit). `final` une seule fois, à la fin.
4. Corriger la fiche, jamais le moteur. Un effet manque vraiment ? Voir « Faire évoluer le moteur ».
5. **Un seul skill en plus à la fois**, à l'étape où il sert (voir « Les skills à charger »).

## Où monter : le cloud d'abord, le Mac en mode discret

Le Mac de Yohann (M1, 8 Go) doit rester utilisable pendant un montage (sa règle du 13/11/2026). Donc **le montage se fait dans le cloud**
dès que les rushes peuvent y aller : couper sur le Mac les extraits utiles (`ffmpeg -ss … -t … -c copy`, sans réencoder, dans un dossier
de travail), les passer au cloud avec `device_stage_files` (400 Mo par fichier au plus), monter dans le dossier de travail du fil, puis
renvoyer la vidéo finie (`device_commit_files` refuse plus de 25 Mo par fichier : morceaux de 24 Mo, recollés sur le Mac avec `cat`).
Coût pour un Reel type (700 Mo d'extraits 4K) : 3 à 5 minutes de plus, et le Mac ne fait que copier : couper et copier les extraits
(1 à 2 min), installer les outils dans un cloud neuf, une fois par fil (pip : 1 min ; moteur : 6 s), renvoyer la vidéo (1 min).
Le Mac ne monte que si c'est impossible. Le kit s'y règle alors tout seul (mode discret : un seul montage à la fois, le suivant attend et
le dit ; priorité basse ; 4 cœurs ; un 2e onglet de rendu seulement si 3 Go restent libres ; détourage léger). Ne jamais le contourner ;
`MONTAGE_RESSOURCES=rapide` seulement si Yohann le demande. Mode d'emploi : `montage/README.md`, « Sur le Mac : mode discret ».

## Déroulé

```bash
M nouveau  <dossier> --theme foulees     # crée le projet (hors du dépôt) et une fiche d'exemple
M rushes   <dossier>                     # UNE planche de toutes les sources, avec le nom et l'instant de chaque image
M transcrire <dossier> sources/prise.mov # face caméra : les phrases, les plans sans silences, les sous-titres
M sons     [famille]                     # les bruitages qu'une fiche peut nommer
M caler    <dossier> sources/prise.mov   # clip en playback : instant de la chanson où la prise commence (lèvres synchrones)
M verifier <dossier>                     # lit la fiche, dit ce qui cloche
M planche  <dossier>                     # UNE image de contrôle, zones d'Instagram en rouge
M apercu   <dossier>                     # seulement pour juger le rythme (vidéo légère + planche « film »)
M final    <dossier>                     # vidéo HD + contrôle qualité + version sans musique + crédits du son
M couverture <dossier> --image 45        # image de couverture
```

1. **Dossier.** Hors du dépôt, toujours : sur le Mac dans « SEO et GEO /clients/<client>/montages/<date>-<sujet>/ », dans le cloud dans le
   dossier de travail du fil. Les sources vont dans `<dossier>/sources/`.
2. **Regarder les sources** avec `M rushes` : lire la liste (durée, 60 i/s = ralenti possible, HDR, son) et la planche. Noter pour chaque
   plan le fichier et l'instant de départ (`de`).
3. **Écrire la fiche.** Accroche dans la première seconde (titre ou chiffre), un plan par idée, une fin avec `signature`. Durées en temps de
   musique (`"4t"`) dès qu'il y a une musique : les coupes tombent pile dessus. Musique : toujours `"droits"` (`"libre"` avec son `"credit"`,
   ou `"sous_droits"` pour une musique du commerce).
4. **`M verifier`** jusqu'à ne plus avoir de ligne `[erreur]` ni `[attention]` (ou mettre `"hors_zone": true` quand c'est voulu). Il contrôle
   aussi les textes entre eux, et les têtes dès que les plans ont été extraits une fois (après la première planche).
5. **`M planche`**, regarder l'image une fois, corriger. La zone de chaque tête y est en bleu : aucun texte dedans. Pour un détail :
   `M planche <dossier> --images 45,120 --sans-zones` (4 images au plus, en grand).
6. **`M final`.** La garde-tête doit dire « rien à corriger » et le contrôle « BON ». Sinon corriger la fiche et relancer (les plans déjà
   préparés et les têtes déjà trouvées sont gardés en cache).
7. **Livrer** : `sorties/<nom>.mp4`, `sorties/<nom>-sans-musique.mp4`, la couverture, `sorties/<nom>-credits.txt` (le crédit d'une musique
   libre se recopie dans la légende). Donner à Yohann les coupes « à écouter au casque » que `final` affiche : le kit mesure le son, personne
   ici ne l'entend, donc ne jamais écrire « le son est bon ». Noter le résultat dans le Cockpit. Rien n'est publié sans le « tu peux publier » de Yohann.
8. **Vidéo pour les réseaux d'un client** : une fois validée par Yohann, la déclarer au service réseaux avec la commande `reseaux.py livre`
   (mode d'emploi : `plugin-visibilite/visibilite/skills/service-reseaux/INTERFACE-MONTAGE.md`, partie 2). Cette commande déclare seulement
   la vidéo finie : elle ne publie rien, et rien ne part sans le dernier OK de Yohann, donné après avoir vu la vidéo.

## Ce qui fait la finition pro

- **Garde-tête (règle de Yohann, 13/11/2026 : « ne jamais couper la tête »).** Aucune tête coupée par le cadre (zoom, punch, Ken Burns,
  secousse, bandes, écran partagé), aucun texte sur une tête ni près d'elle, jamais deux textes l'un sur l'autre. Le kit le contrôle à chaque
  préparation, image par image, et refuse `apercu`, `final` et `couverture` tant qu'il reste un problème. Chaque ligne `[erreur]` donne la
  correction à recopier dans la fiche (`"y"` libre pendant tout le texte, punch ou Ken Burns plus doux, `cy`, `cx`, `zoom`, ratio des
  bandes) et `sorties/garde-tete.jpg` montre la pire image. On applique la correction, on ne contourne jamais. `"garde_tete": false` sur un
  plan seulement pour une fausse tête (affiche, mannequin), et on le dit à Yohann.
- **Charte d'une série (règle de Yohann, 13/11/2026 : « la même charte graphique qu'à la première vidéo »).** Dans une série (une
  « chaussure du jour » par jour…), chaque fiche nomme la première vidéo validée : `"charte": "../01-1080/montage.json"`. `verifier` refuse
  un texte qui n'en suit pas le style (police, fond, couleur, animation, alignement), la taille ou le bord, et le rendu est refusé tant
  qu'un texte n'est pas à une hauteur de la charte. La garde-tête passe avant : si une tête occupe la place prévue, le texte va ailleurs
  (`[attention]`, à montrer à Yohann). Mode d'emploi : `montage/README.md`, « Charte ».
- **Zones d'Instagram.** Rien d'important au-dessus de y = 270, sous y = 1500, à droite de x = 960 dans le bas, ni à moins de 65 px des bords.
  L'essentiel reste au-dessus de y = 1250 (sous ce trait, une légende longue le cache). `verifier` le dit, la planche le montre.
- **Lisibilité.** Deux polices au plus (celles du thème), une seule couleur d'accent. Texte de couleur vive seulement en gros, ou en blanc sur
  pastille (`"fond": "accent"`). Sur une image claire : `voile`. Rien sous 34 px (`verifier` le signale).
- **Rythme.** Coupes sur les temps. Trois effets différents au plus par vidéo. Jamais plus de 3 flashs par seconde (le kit refuse). Quelque
  chose change toutes les 2 à 4 secondes : `verifier` signale un creux de plus de 4,5 s.
- **Ralenti** seulement si la source est à 50 ou 60 images par seconde (le kit prévient sinon).
- **Plan filmé à la main** : `"stabilise": true` (mouvements parasites divisés par deux). Un nombre règle la durée du lissage en secondes.
- **Face caméra** : `M transcrire <dossier> sources/prise.mov` rend les plans à coller (silences et faux départs retirés, coupes posées sur
  le vrai son, un plan sur deux resserré) et le calque `{"t": "sous-titres", "plan": "tous", "mots": "auto", "style": "pastille"}`. Relire le
  fichier des paroles (noms propres). Une ligne « coupe à écouter » se dit à Yohann. Un seul plan qui parle au milieu d'un montage :
  `"son": true`, `M transcrire <dossier> <plan>`, et `"plan": "<plan>"` dans le calque.
- **Texte derrière le sujet** : `"masque": true` sur le plan, `"derriere": true` sur le titre. 8 à 19 s de calcul par image et 7 à 12 Go de
  mémoire (BiRefNet) : plans courts seulement, préparés dans le cloud (sur le Mac, le kit prend un modèle léger de 1 Go).
- **Musique.** Si `verifier` dit « calage incertain » (rythme en triolets), écouter l'aperçu et fixer `bpm` et `premier_temps` dans la fiche.
  Une musique du commerce ne va jamais en ligne dans le fichier : on publie la version sans musique et le son s'ajoute dans Instagram.
- **Bruitages** : par leur nom (`M sons`, puis `M sons whoosh`). Peu, et à leur place : un par transition suffit, le kit les pose déjà.
- **Son final** : toujours à -14 LUFS, crête sous -1 dB. Rien à régler.
- **Clip en largeur** (playback sur la chanson de l'artiste) : `"format": "16:9"`, `M caler` puis la ligne `"calage"` dans la fiche (les
  plans calés n'ont pas de `de`), `"droits": "artiste"`, `"sons_auto": false`, thème `cinema`, `"anim": "cinema"` pour le titre, calque
  `bandes` (`depuis_noir` pour une ouverture de film), calque `lumiere` (fuites de lumière), `"cadrage": "visage"` sur les plans resserrés (le rognage suit le visage),
  `double` dans un plan (double exposition ou écran partagé `"mode": "partage"`), arrêt sur image avec `"vitesse": 0`. Image d'origine sans accentuation : `"finition": {"nettete": false}`. Mode d'emploi : `montage/README.md`, « Clip en largeur ».

## Les skills à charger, au bon moment

Un skill chargé est relu à chaque action du fil : les neuf d'un coup coûtent 27 000 tokens par action. On en charge un, à son étape. Les normes
du kit passent avant les leurs (son à -14 LUFS, zones d'Instagram) ; leurs passages sur un outil payant ou sur WoopSocial sont à ignorer.

| Quand | Skill | Ce qu'on en tire |
|---|---|---|
| Quelqu'un va se filmer en parlant | `talking-head-and-piece-to-camera` | La fiche de tournage à lui donner : téléphone à hauteur des yeux, face à la fenêtre, micro près, 9:16, yeux au tiers haut, plan des idées avec la première et la dernière phrase mot pour mot, un clap entre deux essais, trois essais au plus par phrase. On ne juge jamais une prise qu'on n'a pas vue. |
| Plusieurs scènes à tourner | `scripting-and-storyboarding` | Le script en deux colonnes (ce qu'on entend, ce qu'on voit) qui devient les plans et les calques de la fiche, la liste des plans rangée par lieu, 130 à 150 mots par minute. |
| Une longue vidéo à découper | `captions-and-clipping` | Des extraits qui se comprennent seuls et commencent par leur accroche. |
| Le son porte la vidéo | `sound-effects`, puis `sound-design-film` | Le choix de chaque bruitage et de l'ambiance. Les sons viennent de `M sons`, le niveau reste celui du kit. |
| Couverture ou affiche soignée | `canvas-design` | La mise en page. `M couverture` donne l'image de départ. |
| Une commande hors du kit (convertir, extraire) | `ffmpeg` | La bonne recette. |
| Yohann demande d'essayer un autre moteur | `hyperframes` | Sur UNE vidéo d'essai, après l'avoir prévenu : il envoie des statistiques d'usage à son éditeur. |

`short-editing` ne se charge pas : ses règles (accroche lisible tout de suite, un changement toutes les 2 à 4 s, sous-titres de 84 px, rien sous
34 px, silences coupés) sont dans le kit et `verifier` les applique. Son moteur à lui ne sert pas : un seul logiciel de montage, un seul rendu.

## Pièges connus

- Les vidéos HDR d'iPhone et les photos Display P3 sont converties toutes seules. Ne pas les convertir à la main avant.
- Une source plus petite que 1080 px de large sort floue : le kit prévient, préférer une autre prise. Filmer en 4K permet de resserrer un plan.
- La première préparation est longue (rushes 4K) ; ensuite seul ce qui change est refait.
- Moteur Remotion : gratuit pour une personne ou une entreprise de 3 personnes au plus (au-delà : remotion.dev/license).
- Aucun fichier de client dans le dépôt : ni vidéo, ni photo, ni logo, ni musique.

## Faire évoluer le moteur

Le moteur est dans `montage/moteur/src/` (Remotion), la lecture de la fiche dans `montage/outils/fiche.py`. Toute évolution sert à toutes les
vidéos suivantes : l'ajouter proprement, la documenter dans `montage/README.md`, puis lancer `python3 montage/tests/test_kit.py` (69 tests, dont
un vrai rendu sur le projet de démonstration `montage/exemples/demo/fabrique.py`). Un effet ou une animation qui déplace l'image ou un
texte se recopie aussi dans `montage/outils/tete.py` (garde-tête) : l'essai `test_meme_geometrie_que_le_moteur` le rappelle. Les skills officiels de Remotion s'installent à la demande
avec `npx skills add remotion-dev/skills` (gratuit, guide : remotion.dev/docs/ai/skills) ; ils ne sont pas copiés ici car leur dépôt n'a pas de licence.
