# Kit de montage de Reels

Le logiciel de montage du projet. On écrit une **fiche** (`montage.json`) qui décrit la vidéo en clair, et le kit sort une vidéo
propre, aux normes, déjà contrôlée. Le moteur est celui du Reel HYROX v2 (validé le 09/11/2026), rendu commun à toutes les vidéos.

Pourquoi : avant, chaque vidéo se réécrivait de zéro (long, cher, résultat variable). Maintenant le moteur, la finition et les
contrôles sont faits une fois pour toutes.

## En 5 commandes

```bash
python3 montage/montage.py nouveau  ~/montages/mon-reel --theme foulees   # crée le projet et une fiche d'exemple
python3 montage/montage.py rushes   ~/montages/mon-reel                   # UNE planche de toutes les sources (pour choisir les extraits)
python3 montage/montage.py verifier ~/montages/mon-reel                   # lit la fiche, dit ce qui cloche (2 s, aucun rendu ; têtes comprises)
python3 montage/montage.py planche  ~/montages/mon-reel                   # UNE image de contrôle avec les zones d'Instagram et des têtes
python3 montage/montage.py final    ~/montages/mon-reel                   # vidéo HD + contrôle qualité + version sans musique
```

Autres : `apercu` (vidéo légère + planche « film » pour juger le rythme), `tout` (planche + final), `controle video.mp4 [--instagram]`
(contrôle d'un fichier, et simulation de la compression d'Instagram), `couverture projet --image 45` (image de couverture),
`transcrire projet PLAN` (paroles d'un plan, mot à mot), `transcrire projet sources/prise.mov` (face caméra : toute une prise, voir plus
bas), `sons [famille]` (les bruitages qu'une fiche peut nommer), `tempo musique.mp3 [début]`, `caler projet sources/prise.mov` (clip en playback : instant de la chanson où commence la vidéo).

Le travail va dans `<projet>/.travail/`, les résultats dans `<projet>/sorties/`. **Rien ne s'écrit dans le dépôt** : garder les
projets hors du dépôt (les fichiers d'un client ne vont jamais dans le dépôt).

Installation : Python 3 avec Pillow, numpy, scipy, opencv, librosa, soundfile (et rembg pour le détourage, faster-whisper pour les
paroles), ffmpeg, Node 18 ou plus. Le moteur (Remotion) s'installe tout seul au premier rendu (`npm install`, environ 30 s).

## La fiche

Les durées s'écrivent : `24` (images), `"1.5s"` (secondes) ou `"4t"` (4 temps de la musique : les coupes tombent pile dessus).

```json
{
  "nom": "chaussure-du-jour",
  "theme": "foulees",
  "etalonnage": "naturel",
  "finition": {"grain": 0.1, "vignette": 0.35, "fondu_fin": 10},
  "musique": {"fichier": "sources/musique.mp3", "debut": 31.0, "droits": "libre", "credit": "Titre, auteur, site, licence"},
  "accents": {"tous_les": 2, "decalage": 1, "zoom": 0.028},
  "plans": [
    {"id": "A", "source": "sources/IMG_0001.MOV", "de": 4.2, "duree": "4t", "sortie": "zoom"},
    {"id": "B", "photo": "sources/facade.jpg", "duree": "4t", "effets": [{"t": "kb", "a": 1.0, "b": 1.08}]}
  ],
  "calques": [
    {"t": "titre", "texte": "LA CHAUSSURE\nDU JOUR", "y": 420, "taille": 170, "de": 2, "a": "4t", "anim": "pop"},
    {"t": "signature", "nom": "Foulées", "ligne": "Quincy-sous-Sénart", "plan": "B", "de": 12}
  ]
}
```

| Clé | Rôle |
|---|---|
| `format` | `"9:16"` (Reel, story : le défaut), `"16:9"` (clip, YouTube : 1920 × 1080), `"4:5"`, `"1:1"`, ou `{"l": 1920, "h": 1080}`. Hors 9:16, les zones et les conseils propres aux Reels ne s'appliquent pas (il reste les marges). |
| `theme` | `telemetrie` (noir, blanc, gris : style HYROX), `foulees` (rouge, blanc, anthracite), `cinema` (clip, bande-annonce : noir profond, blanc cassé, capitales espacées), `neutre`. Ou un objet `{"base": "foulees", "accent": "#..."}`. |
| `etalonnage` | Réglage des couleurs des rushes : `naturel`, `sport` (celui de HYROX), `vif`, `doux`, `melancolie` (couleurs éteintes, ombres froides : clip). Possible aussi par plan. |
| `finition` | `grain` (0 à 0.15), `vignette` (0 à 0.5), `fondu_fin` (images de fondu au noir à la fin), `nettete` (`false` : aucune accentuation, l'image reste telle qu'elle a été filmée). |
| `musique` | `fichier`, `debut` (s), `gain` (dB), `fondu` (images), et toujours `droits` : `"libre"` avec son `credit` (titre, auteur, site, licence), ou `"sous_droits"` (musique du commerce : seule la version sans musique va en ligne), ou `"artiste"` avec son `credit` (clip : la chanson de l'artiste pour qui on fait la vidéo, elle reste dans la version publiée, avec son accord). Le tempo est trouvé tout seul ; si le calage est annoncé « incertain », fixer `bpm` et `premier_temps`. |
| `calage` | Clip en playback : `{"sources/prise.mov": 4.02}` = la vidéo commence à 4,02 s de la chanson. Les plans de cette vidéo n'ont pas de `de` : il se calcule pour que les lèvres tombent pile sur les paroles. `montage.py caler` donne les chiffres. |
| `accents` | Petits coups de zoom sur la musique : `tous_les` (temps), `decalage`, `zoom`, `secousse`, `flash`, `de`, `a`. |
| `sons` | Bruitages en plus : `{"son": "impact", "at": "8t", "db": -10}`. Trois sources, toutes par leur nom : le kit du dépôt (swish, zoom, souffle, pop, impact, ding, montee, fin, clic…), la bibliothèque libre du skill `sound-effects` (103 sons CC0, par exemple `"whoosh/fs393811"`), ou un fichier du projet. `montage.py sons` donne la liste, `sons whoosh` une famille. Un nom inconnu est une erreur dès `verifier`. |
| `sons_auto` | `true` par défaut : un bruitage discret est posé sur chaque transition. |
| `charte` | Série (une « chaussure du jour » par jour…) : la fiche de la vidéo validée, `"../01-1080/montage.json"` (ou son dossier). Chaque texte doit en suivre le style, la taille, le bord et la hauteur (voir « Charte »). |

### Plans

`source` (vidéo) ou `photo`, `de` (début dans la vidéo, en s), `duree`, `vitesse` (1 = normal, 0.5 = ralenti, ou une rampe
`[[0, 1.3], [14, 0.3], [38, 1.6]]`), `zoom`, `cx`, `cy` (cadrage 9:16), `regard` (`nb`, `nbsombre`, `contraste`, `chaud`, `froid`,
`doux`, `retro`), `sortie` (transition vers le plan suivant), `masque: true` (détoure le sujet, pour un texte derrière lui),
`son: true` (garde le son d'origine du plan, voix nettoyée ; `"brut"` = sans nettoyage ; un nombre = réglage en dB), `cadrage: "visage"` (le rognage d'un plan resserré suit le visage, chemin lissé : la personne reste dans l'image quand elle bouge ; détecteur YuNet d'OpenCV, licence MIT, téléchargé une fois dans `~/.cache/montage`), `stabilise: true`
(plan filmé à la main : mouvements parasites divisés par deux ; un nombre = durée du lissage en secondes, 1.5 par défaut), `lut` (fichier .cube),
`garde_tete: false` (seulement pour une fausse tête : affiche, mannequin ; voir « Garde-tête »).
`double` : une deuxième vidéo dans le même plan, `{"source", "de", "vitesse", "zoom", "cx", "cy", "cadrage", "regard", "mode", "force"}`.
`"mode": "superpose"` (par défaut) = double exposition (la deuxième image en fondu « écran », `force` 0.45) ; `"mode": "partage"` = écran
partagé, une moitié chacune, qui s'ouvre en 8 images avec un trait noir au milieu. Une source calée sans `de` reste calée sur la chanson.
Arrêt sur image : `"vitesse": 0` (l'image de `de` tient tout le plan).
`cadre` : style affiche, l'image plein écran se range dans un tirage photo blanc penché, posé sur la même image floutée et assombrie
(`{"l": 800, "ratio": 1.0, "y": 1080, "angle": -2.5, "de": "1.2s", "entree": 14}` ; aussi `x`, `bord` et `bas` (bord blanc, 30 px),
`flou` (34 px), `sombre` (0.55), `couleur` du bord). `y` est le centre du tirage, `de` l'instant où il commence à se ranger, `entree` la
durée du mouvement. Les effets du plan continuent dans la photo ; la garde-tête suit la tête jusque dans le cadre.

- Transitions (`sortie`) : `coupe`, `zoom`, `whipG`, `whipD`, `whipH`, `whipB`, `glitch`, `flou`, `noir`, `flash`.
- Effets (`effets`) : `kb` (zoom lent `a`→`b`), `zr` (rampe de zoom `k0`→`k1`), `punch` (coup de zoom), `shake`, `flash`, `rgb`, `rewind`.
- Les vidéos HDR d'iPhone sont converties toutes seules ; les photos d'iPhone (Display P3) aussi. Si ffmpeg n'a pas le filtre zscale
  (celui du Mac, 13/11), le kit fait une copie SDR avec avconvert (l'outil d'Apple), vérifiée et gardée dans `.travail/sdr/`. Cette copie
  est à 30 i/s : à vitesse normale rien ne se perd, un ralenti est moins fluide (la préparation le dit ; vrai ralenti : monter dans le
  cloud). Sans zscale ni avconvert, le kit s'arrête et dit de monter dans le cloud (`outils/hdr.py`, le seul endroit qui choisit).

### Calques (ce qui se pose par-dessus)

Tous ont `de` et `a` (ou `duree`). Avec `"plan": "A"`, les temps comptent depuis le début de ce plan.

| Type | Clés principales |
|---|---|
| `titre` | `texte` (lignes séparées par `\n`), `y`, `taille` (ou `tailles`), `anim` (`pop`, `lettres`, `glisse`, `machine`, `decode`), `couleur`, `fond` (pastille), `contour`. Avec `derriere: true` + `contour_devant: true` : le texte passe derrière le sujet (plan avec `masque`). |
| `mots` | Mots qui claquent un par un : `texte: "PLUS / VITE / ENCORE"`, `rythme: "1t"`, `alterne: true`. |
| `sous-titres` | Paroles mot à mot : `plan` (un plan, ou `"tous"` pour tous les plans qui parlent), `mots: "auto"` (après `transcrire`), `style: "pastille"` (le mot prononcé sur une pastille, lisible dans tous les thèmes). 84 px, deux lignes au plus, groupes coupés à la ponctuation, posés juste au-dessus de y = 1250 et à gauche des boutons d'Instagram. Le fichier des paroles se corrige à la main (noms propres) avant le rendu. |
| `etiquette` | Petit texte technique sur plaque : `texte`, `x`, `y`, `align: "gauche"` (34 px par défaut). |
| `compteur` | Nombre qui défile : `valeur`, `depuis`, `format` (`entier`, `temps`, `decimal1`), `prefixe`, `suffixe`. |
| `image` | Logo ou produit détouré : `fichier`, `x`, `y` (centre), `l` (largeur), `anim` (`pop`, `glisse`, `tombe`, `fondu`), `flotte`. |
| `voile` | Assombrit pour la lisibilité : `cote` (`haut`, `bas`, `plein`), `force`. |
| `signature` | Carte de fin : `nom`, `ligne`, `logo`. |
| `bandes` | Bandes noires du cinéma qui glissent en place puis repartent : `ratio` (2.39 par défaut), `glisse` (durée, 12 images), `depuis_noir: true` (ouverture de film : l'image part du noir et les bandes s'écartent). |
| `lumiere` | Fuites de lumière de pellicule : taches chaudes qui passent et respirent sur l'image : `force` (0.5), `couleur`, `couleur2`, `cote` (`gauche`, `droite`), `fondu` (10 images). |

Titre de bande-annonce : `"anim": "cinema"` (fondu lent, lettres qui se resserrent, net qui arrive), `duree_anim` et `fondu` (durée du fondu
de sortie) en images, secondes ou temps.

La taille d'un texte est réduite toute seule s'il dépasse de l'image. Le kit prévient si un texte tombe dans une zone cachée, s'il fait
moins de 34 px (trop petit pour un téléphone), ou si rien ne change à l'image pendant plus de 4,5 secondes.

## Face caméra (une personne qui parle)

```bash
python3 montage/montage.py transcrire ~/montages/mon-reel sources/prise.mov
```

La commande écoute toute la prise et rend : les phrases avec leurs temps, les faux départs (une phrase recommencée : on garde la dernière),
les plans prêts à coller dans la fiche (silences coupés, un plan sur deux resserré pour que la coupe se voie comme un changement de cadre)
et le calque de sous-titres. Il reste à coller, à enlever les phrases en trop, puis `verifier`.

```json
"plans": [
  {"id": "P01", "source": "sources/prise.mov", "de": 0.81, "duree": "2.38s", "son": true},
  {"id": "P03", "source": "sources/prise.mov", "de": 7.12, "duree": "2.68s", "son": true, "zoom": 1.12, "cy": 0.482}
],
"calques": [{"t": "sous-titres", "plan": "tous", "mots": "auto", "style": "pastille"}]
```

- Les coupes suivent le son réel, pas la transcription (elle se trompe de 0,1 à 0,9 s au bout des phrases) : 0,12 s avant la voix, 0,2 s après.
- Un mot dit tout bas n'est jamais coupé ; un bruit bref (un objet posé) ne compte pas comme de la parole.
- « coupe à écouter » : la voix continue après le dernier mot (un « euh » collé, un rire). La coupe est posée au moment le plus calme.
- Trop de bruit autour de la voix (moins de 22 dB d'écart) : le kit le dit et suit la transcription seule, avec plus de marge.
- Zoom : 1.12 sur une vidéo 4K, limité à 1.08 sur une vidéo de 1080 px pour rester net ; il garde les yeux à la même hauteur (`cy`).
  `--zoom 1` : aucun zoom. `--silence 0.6` : ne couper que les silences plus longs (0.45 par défaut). `--prefixe Q` : les plans d'une
  deuxième prise s'appellent Q01, Q02… au lieu de P01.
- Une phrase recommencée est retirée des plans proposés : la remettre si la répétition était voulue.
- Les temps des mots sont recalés sur le son (`.travail/prises/<fichier>.json`, à corriger à la main pour les noms propres).
- La voix nettoyée prend une demi-seconde d'élan avant chaque coupe : pas de souffle au début des plans.
- Après `final`, le kit donne les coupes à écouter au casque (celles où la voix est encore forte). Il mesure le son, il ne l'entend pas.

## Clip en largeur (playback sur la chanson de l'artiste)

```bash
python3 montage/montage.py caler ~/montages/clip sources/prise1.mov sources/prise2.mov
```

Le kit écoute le son de chaque prise (la chanson passait pendant le tournage) et dit à quel instant de la chanson elle commence, vérifié
sur ses deux moitiés. Il rend la ligne `"calage"` à coller dans la fiche ; une prise sans la chanson dans son son est annoncée « incertain ».

```json
"format": "16:9", "theme": "cinema", "etalonnage": "melancolie", "finition": {"nettete": false, "fondu_fin": 45},
"musique": {"fichier": "sources/chanson.mp3", "droits": "artiste", "credit": "« Titre », Artiste", "bpm": 93.02, "premier_temps": 0.045},
"calage": {"sources/prise1.mov": 4.02},
"sons_auto": false,
"plans": [{"id": "A", "source": "sources/prise1.mov", "duree": "4t", "zoom": 1.5, "cx": 0.55, "cy": 0.4}]
```

- Les plans calés ne prennent ni `de` ni `vitesse` (le kit le refuse : les lèvres ne suivraient plus). `zoom`, `regard`, effets : libres.
- Un playback resserré (`zoom` 1.3 à 1.7) avec `"cadrage": "visage"` garde son visage dans l'image même quand il bouge beaucoup.
- Une prise en 4K se resserre jusqu'à `zoom` 2 sans perte en 1920 × 1080 ; une prise en 1080 reste à `zoom` 1.
- `sons_auto: false` : pas de bruitage sur les transitions, la chanson seule.
- Ouverture de film : `bandes` avec `depuis_noir` + `lumiere` + titre `cinema` sur l'intro ; fin : arrêt sur image (`vitesse` 0, `nbsombre`) et générique sur un `voile`. Refrains : `double` en `partage` pour montrer deux tenues côte à côte.
- Le calage se mesure avec le même décodeur que le mixage : refaire `caler` sur la machine qui fait le rendu (un autre ffmpeg peut décaler un mp3 de 0,05 s).

## Les zones d'Instagram (Reel 1080 × 1920)

Rien d'important au-dessus de **y = 270** (barre du haut), sous **y = 1500** (compte, légende, musique : toujours caché), à droite de
**x = 960** dans le bas de l'image (boutons), ni à moins de **65 px** des bords. L'essentiel reste au-dessus de **y = 1250** : entre 1250 et
1500, une légende longue le cache. Ces chiffres suivent le repère officiel de Meta pour le 9:16 (14 % libres en haut, 35 % en bas, 6 % sur
les côtés). La planche montre les zones en rouge et le trait de 1250 en orange ; `verifier` les signale. Ajouter `"hors_zone": true` à un
calque quand c'est voulu.

Couverture : dans la grille du profil, Instagram ne montre que le milieu de l'image (format 3:4). Garder le titre entre y = 285 et y = 1635.

## Garde-tête : jamais une tête coupée ni couverte

Règle de Yohann (13/11/2026) : aucune animation, aucun effet, aucun texte ne coupe ou ne couvre une tête, et deux textes ne se chevauchent
jamais. Le kit le vérifie tout seul, à chaque fois (`outils/tete.py`) :

- **Quand** : à chaque préparation (`planche`, `apercu`, `final`, `couverture`), et dans `verifier` dès que les plans ont été extraits une
  fois. Avant la première extraction, `verifier` contrôle déjà les textes entre eux.
- **Comment** : le détecteur de visages (celui de `cadrage: "visage"`) regarde une image sur 4 de chaque plan ; une tête vue une seule fois
  est écartée (fausse détection). Puis le kit suit chaque image jusqu'à l'écran comme le moteur (zoom du plan, Ken Burns, punch, rampe de
  zoom, secousses, coups sur la musique, écran partagé, bandes du cinéma) et chaque texte avec son animation (pop, glisse, cinéma, mots,
  sous-titres, compteur, image posée).
- **Tête coupée** : le visage et le haut du crâne restent dans la partie visible (une mèche peut être rognée : 4 % de la hauteur du
  visage). Les 2 à 5 images d'une transition où toute l'image file (zoom, whip, glitch) ne comptent pas, une tête tout entière hors champ non plus.
- **Zone de la tête**, où aucun texte ne va : le visage, 85 % de sa hauteur au-dessus (le crâne, puis de l'air), 25 % de chaque côté, 30 % sous le menton.
  La planche la montre en bleu. Un texte encore presque transparent (début ou fin de fondu) ne compte pas.
- **Refus** : tant qu'il reste un problème, `apercu`, `final` et `couverture` s'arrêtent. Chaque ligne `[erreur]` dit le moment, le plan,
  le calque et la correction à mettre dans la fiche : `"y"` libre pendant tout le texte, `punch` ou Ken Burns plus doux, `cy` / `cx` /
  `zoom` du plan, `ratio` des bandes, `"cadrage": "visage"`. `sorties/garde-tete.jpg` montre la pire image de chaque problème (bleu : zone
  de la tête, orange : tête entière, jaune : texte en cause, vert : partie visible).
- **Fausse tête** (affiche, mannequin, photo dans l'image) : `"garde_tete": false` sur ce plan, et rien d'autre. Le kit le rappelle à
  chaque préparation.
- Les têtes trouvées restent en cache (`.travail/tetes/`) : changer un texte ne refait aucune détection. La première fois, environ
  9 secondes par minute de vidéo.

## Charte : les textes de la vidéo validée

Règle de Yohann (13/11/2026) : dans une série, chaque vidéo garde la charte de la première vidéo validée, et les textes restent alignés.
La fiche nomme la fiche validée (`"charte"`), et le kit compare chaque texte (titre, mots, étiquette, compteur, sous-titres) à un texte du
même genre de la charte (`outils/charte.py`) :

- **Thème et format** : les mêmes que la vidéo validée.
- **Style** : police, fond, couleur, animation, alignement. **Taille** à 12 % près. **Bord** (`x`) à 8 px près : c'est ce qui aligne les
  textes d'une vidéo à l'autre. Un écart est une `[erreur]` dès `verifier`, avec ce qu'il faut écrire (« comme le calque 3 de 01-1080 »).
- **Hauteur** : sur une des places de la charte, à 40 px près ; une liste (des caractéristiques l'une sous l'autre) peut s'allonger d'une
  ligne. Hors de sa place : refus au rendu, avec la hauteur de la charte à reprendre.
- **La garde-tête passe avant** : quand un texte doit quitter une tête, la correction proposée vise d'abord une place de la charte. Si une
  tête ou un autre texte occupe toutes ses places dans ce plan, le texte se pose ailleurs : `[attention]`, sans refus, et à montrer à Yohann.
- Un genre de texte absent de la charte : `[attention]`, ce texte n'a pas de modèle.

## Sur le Mac : mode discret (le Mac reste utilisable)

Demande de Yohann (13/11/2026) : pendant un montage, son Mac (M1, 8 Go) doit rester utilisable. Sur le Mac, le kit se règle tout seul
(`outils/ressources.py`) : ni la fiche ni le fil n'ont à y penser. Ailleurs (machine du cloud), rien ne change : pleine vitesse.

- **Un seul montage à la fois.** Les commandes lourdes (`rushes`, `preparer`, `planche`, `apercu`, `final`, `tout`, `couverture`,
  `transcrire`, `caler`, `controle`) prennent un verrou (`~/.cache/montage/rendu.lock`). La deuxième attend son tour et le dit
  (« Un autre montage occupe déjà la machine… »), une heure au plus, puis s'arrête en proposant d'attendre ou de rendre dans le cloud.
- **Priorité basse** : nice 15 et classe « utility » de macOS (`taskpolicy -c utility`), qui passe le montage surtout par les cœurs
  économes : les cœurs rapides restent aux applications.
- **4 cœurs sur un M1** pour tout le montage : onglets du rendu, encodeur x264, ffmpeg (décodage, filtres, encodage), OpenCV, détourage,
  transcription, numpy.
- **Mémoire** (8 Go : c'est elle qui faisait ramer le Mac) : un seul onglet de rendu tant que le Mac ne garderait pas 3 Go libres avec un
  de plus ; cache vidéo plafonné à 512 Mo ; détourage avec `isnet-general-use` (1 Go au plus, contre 7 à 12 Go pour BiRefNet, mesuré le 13/11).
- **Carte graphique** : Chromium garde la sienne. Le dessin sans carte (`swangle`) a pris tous les cœurs et 2,5 fois plus de temps.

Réglages, seulement si Yohann le demande : `MONTAGE_RESSOURCES=rapide` (plus aucune limite, toujours un seul montage à la fois),
`MONTAGE_COEURS=n`, `MONTAGE_GL=swangle`, `MONTAGE_DETOURAGE=birefnet-general-lite`. Mesurer ce qu'une commande prend à la machine
(durée, cœurs, mémoire, échange sur disque, et carte graphique sur Mac) :

```bash
python3 montage/outils/charge.py -- python3 montage/montage.py final <projet> --plage 0-149
```

## Ce que le kit garantit (finition)

- Export aux normes : H.264 High 4.2, yuv420p, plage limitée, BT.709 partout, 30 i/s, AAC 48 kHz, lecture immédiate.
- Son à -14 LUFS, crête sous -1 dB, musique qui s'efface sous la voix, version « sans musique » pour poser la musique dans Instagram.
- Coupes calées sur la musique à moins de 3 ms près (vérifié sur des musiques de test). Si le rythme est ambigu, le kit le dit.
- Contrôle automatique après chaque rendu final : format, couleurs, son, passages noirs, image figée, flou, flashs (3 par seconde au plus).
- Garde-tête avant chaque rendu : aucune tête coupée ni couverte, aucun texte sur un autre (voir plus haut), sinon pas de rendu.
- Sur le Mac, le montage le laisse utilisable : un seul à la fois, priorité basse, 4 cœurs, 3 Go laissés libres quand c'est possible.
- Images des calques (logos, produits) : chacune a sa clé (source, taille, date, largeur affichée). Retirer ou déplacer un calque ne
  donne jamais l'image d'un autre ; une source changée ou affichée plus grand est refaite, nette ; celles qui ne servent plus sont effacées.
- Polices fournies (licence libre), jamais de police de secours : s'il en manque une, le rendu s'arrête.
- Droits du son : chaque rendu final écrit `sorties/<nom>-credits.txt` (musique, bruitages, voix). Le crédit d'une musique libre se recopie
  dans la légende ; une musique du commerce ne part jamais en ligne dans le fichier, le kit le rappelle et livre la version sans musique.
- Lisible sur un téléphone : sous-titres de 84 px sur deux lignes, mot prononcé lisible sur sa pastille dans tous les thèmes, rien sous 34 px sans le dire.

## Les skills qui vont avec le kit

Ce qui se vérifie par un calcul est dans le kit, pour toutes les vidéos. Le reste se charge au moment où il sert (un seul skill à la
fois, voir le skill `montage-pro`) :

| Moment | Skill | Ce que le kit fait déjà tout seul |
|---|---|---|
| Avant de filmer quelqu'un qui parle | `talking-head-and-piece-to-camera` | Coupe des silences, zoom qui garde les yeux au tiers haut |
| Plusieurs scènes à tourner | `scripting-and-storyboarding` | Rien : c'est du papier, avant le tournage |
| Une longue vidéo à découper en extraits | `captions-and-clipping` | Sous-titres mot à mot sur deux lignes |
| Choisir les bruitages, soigner le son | `sound-effects`, `sound-design-film` | Bibliothèque appelée par son nom, niveau final, crédits, coupes à écouter |
| Lisibilité et rythme | `short-editing` (ses règles, pas son moteur) | `verifier` : 34 px, 84 px, un changement toutes les 2 à 4 s |
| Une commande hors du kit | `ffmpeg` | Export aux normes, contrôle |
| Couverture ou affiche soignée | `canvas-design` | `couverture` sort l'image de départ |
| Essayer un autre moteur sur une vidéo | `hyperframes` | Rien (il envoie des statistiques d'usage à son éditeur : prévenir Yohann avant) |

## Faire une vidéo sans gaspiller (temps et tokens)

1. Un fil neuf par vidéo. Un long fil relit tout son passé à chaque action : c'est ce qui coûtait le plus cher.
2. `verifier` d'abord (gratuit), puis `planche` : une seule image à regarder au lieu de trente.
3. `apercu` seulement pour juger le rythme. `final` une seule fois, à la fin.
4. Corriger la fiche, pas le moteur. Si un effet manque vraiment, l'ajouter au moteur pour tout le monde.
5. Le détourage (`masque`) coûte de 8 à 19 s par image avec BiRefNet (et 7 à 12 Go de mémoire) : le garder pour des plans courts, et
   le faire dans le cloud.

## Essayer le kit et le tester

```bash
python3 montage/exemples/demo/fabrique.py /tmp/demo     # projet de démonstration, sans aucun fichier de client
python3 montage/montage.py tout /tmp/demo               # planche + vidéo finale contrôlée
python3 montage/tests/test_kit.py                       # 69 tests automatiques, dont de vrais rendus (2 à 3 minutes)
```

## Licences

Moteur : Remotion, gratuit pour une personne seule ou une entreprise de 3 personnes au plus (au-delà, licence payante : voir
remotion.dev/license). Polices : SIL OFL (fichiers `OFL-*.txt`). Bruitages : kit CC0 du dépôt, et bibliothèque CC0 du skill
`sound-effects` (source de chaque son dans son `sfx/manifest.json`, recopiée dans le fichier des crédits de la vidéo).
