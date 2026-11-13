"""Fiche de montage (montage.json) : lecture, vérification, calcul de la ligne de temps et des textes.

La fiche décrit le montage en clair (plans, textes, musique). Ce module la transforme en « calcul » :
toutes les durées en images, les tailles de texte ajustées, les couleurs du thème, et la liste des
remarques (erreurs, avertissements, conseils) AVANT de lancer le moindre rendu.
Bibliothèque standard + Pillow (mesure des textes).
"""
import hashlib
import json
import math
import re
import subprocess
from pathlib import Path

KIT = Path(__file__).resolve().parent.parent            # dossier montage/
DEPOT = KIT.parent
POLICES_KIT = KIT / 'moteur' / 'polices'
POLICES_PLUGIN = DEPOT / 'plugin-visibilite' / 'visibilite' / 'assets' / 'fonts'
SONS_KIT = DEPOT / 'plugin-visibilite' / 'visibilite' / 'assets' / 'sfx'
SONS_PLUS = DEPOT / '.claude' / 'skills' / 'sound-effects' / 'sfx'      # bibliothèque libre (CC0) du skill sound-effects, quand il est installé
DROITS_MUSIQUE = {'libre': 'musique libre de droits : elle se publie avec son crédit',
                  'sous_droits': 'musique du commerce : le fichier avec musique ne va jamais en ligne',
                  'artiste': 'musique de l\'artiste pour qui on fait la vidéo (un clip) : elle reste dans la version publiée, avec son accord'}
# formats tout faits : "format": "16:9" (clip, YouTube), "9:16" (Reel, story, le défaut), "4:5" (fil Instagram), "1:1"
FORMATS = {'9:16': (1080, 1920), '16:9': (1920, 1080), '4:5': (1080, 1350), '1:1': (1080, 1080)}

# ------------------------------------------------------------------ polices disponibles (toutes libres : OFL)
# famille → liste de (fichier, poids CSS, style, axe de graisse pour la mesure)
POLICES = {
    'Barlow Condensed': [('BarlowCondensed-Black.ttf', '900', 'normal'), ('BarlowCondensed-BlackItalic.ttf', '900', 'italic'),
                         ('BarlowCondensed-ExtraBoldItalic.ttf', '800', 'italic'), ('BarlowCondensed-SemiBold.ttf', '600', 'normal')],
    'JetBrains Mono': [('JetBrainsMono.ttf', '100 800', 'normal')],
    'Anton': [('Anton-Regular.ttf', '400', 'normal')],
    'Inter': [('Inter-SemiBold.otf', '600', 'normal'), ('Inter-Bold.otf', '700', 'normal'), ('Inter-ExtraBold.otf', '800', 'normal'), ('Inter-Black.otf', '900', 'normal')],
    'Archivo Black': [('ArchivoBlack-Regular.ttf', '400', 'normal')],
    'Bebas Neue': [('BebasNeue-Regular.ttf', '400', 'normal')],
    'Caveat': [('Caveat.ttf', '400 700', 'normal')],
    'DM Serif Display': [('DMSerifDisplay-Regular.ttf', '400', 'normal'), ('DMSerifDisplay-Italic.ttf', '400', 'italic')],
    'Montserrat': [('Montserrat-ExtraBold.ttf', '800', 'normal'), ('Montserrat-Black.ttf', '900', 'normal')],
    'Poppins': [('Poppins-Bold.ttf', '700', 'normal'), ('Poppins-ExtraBold.ttf', '800', 'normal')],
}

# ------------------------------------------------------------------ thèmes
THEMES = {
    # noir, blanc, gris : le style « télémétrie » (validé le 09/11/2026)
    'telemetrie': dict(encre='#0B0B0B', clair='#E6E6E6', fort='#FFFFFF', accent='#FFFFFF', gris='#8C8C8C',
                       titre=dict(famille='Barlow Condensed', poids=900, style='italic', casse='maj', espacement=-0.01),
                       texte=dict(famille='Barlow Condensed', poids=600, style='normal'),
                       mono=dict(famille='JetBrains Mono', poids=600, style='normal', espacement=0.12, casse='maj')),
    # identité Foulées (fiche IDENTITE-VISUELLE du 08/11/2026) : rouge, blanc, anthracite
    'foulees': dict(encre='#221F20', clair='#FFFFFF', fort='#FFFFFF', accent='#FF121A', gris='#A59FA0',
                    titre=dict(famille='Anton', poids=400, style='normal', casse='maj', espacement=0.005),
                    texte=dict(famille='Inter', poids=700, style='normal'),
                    mono=dict(famille='JetBrains Mono', poids=600, style='normal', espacement=0.1, casse='maj')),
    # cinéma : clip, bande-annonce. Noir profond, blanc cassé, titre en capitales espacées
    'cinema': dict(encre='#050506', clair='#E9E6E1', fort='#F2EFEA', accent='#F2EFEA', gris='#8E8B87',
                   titre=dict(famille='Bebas Neue', poids=400, style='normal', casse='maj', espacement=0.18),
                   texte=dict(famille='Inter', poids=600, style='normal', casse='maj', espacement=0.32),
                   mono=dict(famille='JetBrains Mono', poids=600, style='normal', espacement=0.1, casse='maj')),
    # neutre : fond sombre, texte blanc, sans couleur de marque
    'neutre': dict(encre='#101012', clair='#F2F2F2', fort='#FFFFFF', accent='#FFFFFF', gris='#9A9AA0',
                   titre=dict(famille='Inter', poids=900, style='normal', casse='maj', espacement=-0.02),
                   texte=dict(famille='Inter', poids=700, style='normal'),
                   mono=dict(famille='JetBrains Mono', poids=600, style='normal', espacement=0.1, casse='maj')),
}

# ------------------------------------------------------------------ zones cachées par Instagram (Reel 1080 x 1920)
# haut : barre « Reels » ; bas : légende, compte, musique ; droite (moitié basse) : boutons j'aime, commenter, partager.
# Repère officiel de Meta pour le 9:16 : 14 % libres en haut (270 px), 35 % en bas (670 px, soit y = 1250), 6 % sur les côtés (65 px).
# Ce repère est pensé pour les publicités (bouton en plus), donc prudent : sous 1500 c'est toujours caché, entre 1250 et 1500 seulement
# quand la légende est longue. D'où deux niveaux : « bas » (toujours caché) et « bas_conseille » (à éviter pour l'essentiel).
ZONES = dict(haut=270, bas=1500, bas_conseille=1250, droite=960, droite_depuis=1000, marge=65)

TRANSITIONS = {'coupe', 'zoom', 'whipG', 'whipD', 'whipH', 'whipB', 'glitch', 'flou', 'noir', 'flash'}
# images prises par la transition : (sur le plan qui sort, sur le plan qui entre). Identique à TD dans moteur/src/Plan.jsx.
DUREE_TRANSITION = {'zoom': (4, 5), 'whipG': (3, 4), 'whipD': (3, 4), 'whipH': (3, 4), 'whipB': (3, 4), 'glitch': (2, 3), 'flou': (6, 6), 'noir': (5, 5), 'flash': (0, 5), 'coupe': (0, 0)}
# bruitage posé tout seul sur chaque transition : (nom dans le kit libre CC0, niveau en dB, calage)
SON_TRANSITION = {'zoom': ('zoom', -13, 'pic'), 'whipG': ('swish', -12, 'pic'), 'whipD': ('swish', -12, 'pic'), 'whipH': ('swish', -12, 'pic'),
                  'whipB': ('swish', -12, 'pic'), 'glitch': ('analyse', -14, 'attaque'), 'flou': ('souffle', -15, 'pic'), 'flash': ('impact', -10, 'attaque')}
REGARDS = {'nb', 'nbsombre', 'contraste', 'chaud', 'froid', 'doux', 'retro'}
EFFETS = {'kb', 'zr', 'punch', 'shake', 'flash', 'rgb', 'rewind'}
TYPES_CALQUE = {'titre', 'mots', 'sous-titres', 'etiquette', 'compteur', 'image', 'voile', 'signature', 'bandes', 'lumiere'}
# lisibilité sur un téléphone (barre de qualité du skill short-editing, vérifiée ici à chaque fiche) :
# aucun texte sous 34 px, sous-titres vers 84 px sur 2 lignes au plus, quelque chose qui change toutes les 2 à 4 secondes
TEXTE_MINI, TAILLE_SOUS_TITRES, SANS_CHANGEMENT = 34, 84, 4.5
CLES_PLAN = {'id', 'source', 'photo', 'de', 'duree', 'vitesse', 'zoom', 'cx', 'cy', 'effets', 'regard', 'entree', 'sortie', 'masque', 'son', 'sans_accent', 'etalonnage',
             'stabilise', 'lut', 'cadrage', 'double', 'cadre', 'garde_tete', 'note'}
CLES_FICHE = {'nom', 'format', 'theme', 'finition', 'etalonnage', 'musique', 'calage', 'accents', 'plans', 'calques', 'sons', 'sons_auto', 'charte', 'note'}


class Remarques(list):
    """Liste des remarques : ('erreur' | 'attention' | 'conseil', texte)."""
    def erreur(self, t): self.append(('erreur', t))
    def attention(self, t): self.append(('attention', t))
    def conseil(self, t): self.append(('conseil', t))
    @property
    def bloquant(self): return any(n == 'erreur' for n, _ in self)


# ------------------------------------------------------------------ outils
_UNITE = re.compile(r'^\s*(-?\d+(?:[.,]\d+)?)\s*(t|s|i)?\s*$')


def en_images(v, ips, periode=None):
    """12 ou "12i" = 12 images ; "1.5s" = secondes ; "4t" = 4 temps de la musique (demande le tempo)."""
    if isinstance(v, (int, float)):
        return float(v)
    m = _UNITE.match(str(v))
    if not m:
        raise ValueError(f'durée illisible : {v!r} (exemples : 24, "1.5s", "4t")')
    x, u = float(m.group(1).replace(',', '.')), m.group(2) or 'i'
    if u == 'i':
        return x
    if u == 's':
        return x * ips
    if periode is None:
        raise ValueError(f'« {v} » est en temps de musique, mais la fiche n\'a pas de musique ni de tempo')
    return x * periode * ips


def en_temps(v):
    """Vrai si la valeur est donnée en temps de musique ("4t")."""
    return isinstance(v, str) and v.strip().endswith('t')


VERSION_IMAGES = 1      # à changer si preparer._image_calque change : toutes les images des calques seront refaites


def nom_image(source, largeur):
    """Nom de l'image d'un calque (logo, produit) dans public/images : une clé de la source (chemin résolu, taille, date) et de la largeur
    affichée. Jamais le numéro du calque : en retirant ou en déplaçant un calque, une image restait à la place d'une autre (13/11 : la
    signature d'un Reel montrait une chaussure au lieu du logo). Source changée ou affichée plus grand : autre clé, donc image refaite."""
    p = Path(source).resolve()
    st = p.stat()
    cle = hashlib.sha1(json.dumps([VERSION_IMAGES, str(p), st.st_size, st.st_mtime_ns, round(float(largeur), 1)]).encode()).hexdigest()[:16]
    return cle + ('.jpg' if p.suffix.lower() in ('.jpg', '.jpeg') else '.png')


def sonde(fichier):
    """Largeur, hauteur (à l'endroit), images par seconde, durée, transfert (HDR ?) et présence de son d'une vidéo ou d'une image."""
    r = subprocess.run(['ffprobe', '-v', 'error', '-print_format', 'json', '-show_streams', '-show_format', str(fichier)], capture_output=True, text=True)
    if r.returncode != 0:
        raise ValueError(f'fichier illisible : {fichier} ({r.stderr.strip()[-200:]})')
    d = json.loads(r.stdout)
    v = next((s for s in d['streams'] if s['codec_type'] == 'video'), None)
    a = next((s for s in d['streams'] if s['codec_type'] == 'audio'), None)
    out = dict(audio=a is not None, duree=float(d['format'].get('duration') or 0))
    if v:
        w, h = int(v['width']), int(v['height'])
        rot = 0
        for sd in v.get('side_data_list', []):
            if 'rotation' in sd:
                rot = int(sd['rotation'])
        if 'rotate' in v.get('tags', {}):
            rot = int(v['tags']['rotate'])
        if abs(rot) % 180 == 90:
            w, h = h, w
        num, den = (v.get('avg_frame_rate') or v.get('r_frame_rate') or '30/1').split('/')
        ips = float(num) / float(den) if float(den) else 30.0
        out.update(l=w, h=h, ips=ips, transfert=v.get('color_transfer', ''), hdr=v.get('color_transfer', '') in ('arib-std-b67', 'smpte2084'),
                   images=int(v.get('nb_frames') or 0))
    return out


def fichier_son(nom, projet):
    """Fichier d'un bruitage : nom du kit libre (« swish », « impact »…), fichier du projet,
    ou son de la bibliothèque du skill sound-effects (« whoosh/fs-264777-swoosh », liste : commande « sons »)."""
    cat = json.loads((SONS_KIT / 'catalogue.json').read_text(encoding='utf-8'))
    nom = str(nom)
    if nom in cat['situations']:
        return SONS_KIT / 'kit' / (cat['situations'][nom] + '.wav')
    if nom in cat['sons']:
        return SONS_KIT / 'kit' / (nom + '.wav')
    for p in (Path(projet) / nom, Path(nom), SONS_PLUS / nom, SONS_PLUS / f'{nom}.ogg'):
        if p.is_file():
            return p
    raise ValueError(f'bruitage introuvable : « {nom} » (noms du kit : {", ".join(sorted(cat["situations"]))} ; la bibliothèque en plus : commande « sons »)')


_cache_polices = {}


def _fichier_police(famille, poids, style):
    """Fichier de police le plus proche du poids et du style demandés."""
    variantes = POLICES.get(famille)
    if not variantes:
        raise ValueError(f'police inconnue : {famille} (disponibles : {", ".join(sorted(POLICES))})')
    def ecart(v):
        f, w, s = v
        bornes = [int(x) for x in w.split()]
        dw = 0 if bornes[0] <= poids <= bornes[-1] else min(abs(poids - b) for b in bornes)
        return (s != style, dw)
    f, w, s = min(variantes, key=ecart)
    chemin = POLICES_KIT / f if (POLICES_KIT / f).exists() else POLICES_PLUGIN / f
    return f, w, s, chemin


def largeur_texte(texte, spec, taille):
    """Largeur en pixels d'une ligne de texte, mesurée avec la vraie police (pour l'ajuster à la zone visible)."""
    from PIL import ImageFont
    famille, poids, style = spec['famille'], int(spec.get('poids', 400)), spec.get('style', 'normal')
    cle = (famille, poids, style)
    if cle not in _cache_polices:
        f, w, s, chemin = _fichier_police(famille, poids, style)
        font = ImageFont.truetype(str(chemin), 200)
        if ' ' in w:
            try:
                font.set_variation_by_axes([poids])
            except Exception:
                pass
        _cache_polices[cle] = font
    font = _cache_polices[cle]
    if spec.get('casse') == 'maj':
        texte = texte.upper()
    brut = font.getlength(texte) / 200.0
    return (brut + spec.get('espacement', 0) * len(texte)) * taille


def casse(texte, spec):
    return texte.upper() if spec.get('casse') == 'maj' else texte


def _couleur_vive(c):
    """Vrai pour une couleur très saturée (rouge, bleu vif…) : en petit, la compression des réseaux la rend baveuse."""
    if not (isinstance(c, str) and c.startswith('#') and len(c) == 7):
        return False
    r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
    mx, mn = max(r, g, b), min(r, g, b)
    return mx > 150 and (mx - mn) / mx > 0.75


def _couleur_claire(c):
    """Vrai pour une couleur claire (blanc, gris clair, jaune…) : un texte posé dessus doit être sombre pour rester lisible."""
    if not (isinstance(c, str) and c.startswith('#') and len(c) == 7):
        return False
    lin = lambda v: v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(int(c[i:i + 2], 16) / 255) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.5


# ------------------------------------------------------------------ résolution
def resoudre(fiche, projet, tempo=None, sondes=None, paroles=None, prises=None):
    """Fiche → (calcul, remarques). `tempo` : dict(periode=…) si une musique est analysée. `sondes` : cache {fichier: sonde}.
    `paroles` : {plan: [[mot, début, fin], …]} déjà transcrites (pour les sous-titres « mots: auto »).
    `prises` : {nom du fichier source: [[mot, début, fin], …]} quand toute une prise a été transcrite (face caméra)."""
    projet = Path(projet)
    rq = Remarques()
    sondes = sondes if sondes is not None else {}
    for k in fiche:
        if k not in CLES_FICHE:
            rq.attention(f'clé inconnue dans la fiche : « {k} » (ignorée)')
    fmt = fiche.get('format', {})
    if isinstance(fmt, str):
        if fmt not in FORMATS:
            rq.erreur(f'format inconnu : « {fmt} » (possibles : {", ".join(FORMATS)}, ou {{"l": 1920, "h": 1080}})'); fmt = '9:16'
        fmt = dict(zip(('l', 'h'), FORMATS[fmt]))
    W, H, ips = int(fmt.get('l', 1080)), int(fmt.get('h', 1920)), int(fmt.get('ips', 30))
    ex, ey = W / 1080, H / 1920
    if H / W >= 1.7:      # plein écran vertical (Reel, story) : l'interface d'Instagram recouvre une partie de l'image
        zones = dict(reel=True, haut=round(ZONES['haut'] * ey), bas=round(ZONES['bas'] * ey), bas_conseille=round(ZONES['bas_conseille'] * ey),
                     droite=round(ZONES['droite'] * ex), droite_depuis=round(ZONES['droite_depuis'] * ey), marge=round(ZONES['marge'] * ex))
    else:                 # publication du fil (4:5, carré) ou vidéo en largeur : rien ne recouvre l'image, il ne reste que les marges
        m = round(ZONES['marge'] * ex)
        zones = dict(reel=False, haut=m, bas=H - m, bas_conseille=H - m, droite=W, droite_depuis=H, marge=m)

    # thème
    th = fiche.get('theme', 'neutre')
    if isinstance(th, str):
        if th not in THEMES:
            rq.erreur(f'thème inconnu : {th} (disponibles : {", ".join(THEMES)})'); th = 'neutre'
        theme = json.loads(json.dumps(THEMES[th]))
    else:
        theme = json.loads(json.dumps(THEMES.get(th.get('base', 'neutre'), THEMES['neutre'])))
        for k, v in th.items():
            if k == 'base':
                continue
            theme[k] = {**theme.get(k, {}), **v} if isinstance(v, dict) else v
    familles = {theme[k]['famille'] for k in ('titre', 'texte', 'mono')}

    periode = None
    mus = fiche.get('musique')
    if mus:
        if mus.get('bpm'):
            periode = 60.0 / float(mus['bpm'])
        elif tempo and tempo.get('periode'):
            periode = float(tempo['periode'])
        if not (projet / mus['fichier']).exists():
            rq.erreur(f'musique introuvable : {mus["fichier"]}')
        # droits de la musique : à dire dans la fiche, pour qu'une musique du commerce ne parte jamais en ligne par erreur
        droits = mus.get('droits')
        if droits is None:
            rq.attention('musique : « droits » manque. Écrire "droits": "libre" avec son "credit" (titre, auteur, source, licence), '
                         'ou "droits": "sous_droits" pour une musique du commerce (seule la version sans musique ira en ligne)')
        elif droits not in DROITS_MUSIQUE:
            rq.erreur(f'musique : « droits » vaut « {droits} » (possibles : {", ".join(sorted(DROITS_MUSIQUE))})')
        elif droits == 'libre' and not str(mus.get('credit') or '').strip():
            rq.attention('musique libre : écrire son « credit » (titre, auteur, source, licence), à recopier dans la légende')
        elif droits == 'artiste' and not str(mus.get('credit') or '').strip():
            rq.attention('musique de l\'artiste : écrire son « credit » (titre, artiste), il va dans la description de la vidéo')
        elif droits == 'sous_droits':
            rq.conseil('musique du commerce : le fichier avec musique ne va jamais en ligne. Publier la version « sans musique » et ajouter le son dans Instagram.')

    def img(v, quoi):
        try:
            return en_images(v, ips, periode)
        except ValueError as e:
            rq.erreur(f'{quoi} : {e}'); return 0.0

    # calage : une source filmée sur la musique (playback d'un clip) commence à tel instant de la chanson.
    # Ses plans n'ont alors pas de « de » : il se calcule pour que les lèvres tombent pile sur les paroles.
    calage = {}
    for src_c, dec in (fiche.get('calage') or {}).items():
        try:
            calage[str((projet / src_c).resolve())] = float(dec)
        except (TypeError, ValueError):
            rq.erreur(f'calage : « {src_c} » doit valoir un nombre de secondes (instant de la chanson où la vidéo commence)')
    if calage and not mus:
        rq.erreur('« calage » demande une musique dans la fiche'); calage = {}
    calees = set()

    # ---------------- plans
    plans, t, b = [], 0, 0.0
    brut = fiche.get('plans') or []
    if not brut:
        rq.erreur('la fiche n\'a aucun plan')
    for i, p in enumerate(brut):
        pid = str(p.get('id') or f'P{i + 1}')
        for k in p:
            if k not in CLES_PLAN:
                rq.attention(f'plan {pid} : clé inconnue « {k} » (ignorée)')
        if any(q['id'] == pid for q in plans):
            rq.erreur(f'deux plans portent le nom {pid}')
        if 'duree' not in p:
            rq.erreur(f'plan {pid} : « duree » manque'); continue
        d = p['duree']
        if en_temps(d) and periode:
            b_fin = b + float(_UNITE.match(d).group(1).replace(',', '.'))
            t1 = int(round(b_fin * periode * ips))
        else:
            t1 = t + int(round(img(d, f'plan {pid}')))
            b_fin = t1 / ips / periode if periode else 0.0
        if t1 - t < 2:
            rq.erreur(f'plan {pid} : durée trop courte ({t1 - t} image)'); t1 = t + 2
        photo = 'photo' in p
        chemin = p.get('photo') or p.get('source')
        if not chemin:
            rq.erreur(f'plan {pid} : il faut « source » (vidéo) ou « photo »'); continue
        abs_src = (projet / chemin)
        de = p.get('de', 0)
        dec = None if photo else calage.get(str(abs_src.resolve()))
        if dec is not None:
            # instant de la chanson au début du plan (la musique démarre sur un temps : « debut_cale » du tempo, sinon « debut »)
            pos = float((tempo or {}).get('debut_cale', mus.get('debut', 0))) + t / ips
            if 'de' in p:
                ecart = float(p['de']) - (pos - dec)
                if abs(ecart) > 0.5 / ips:
                    rq.attention(f'plan {pid} : « de » écrit à la main sur une source calée, les paroles seront décalées de {ecart:+.2f} s (enlever « de » pour caler tout seul)')
            else:
                de = round(pos - dec, 4)
            if p.get('vitesse', 1) != 1:
                rq.erreur(f'plan {pid} : source calée sur la musique, mais « vitesse » n\'est pas 1 : les lèvres ne suivraient plus la chanson')
            calees.add(pid)
        q = dict(id=pid, t0=t, t1=t1, photo=photo, src=float(de), cale=dec is not None, vitesse=p.get('vitesse', 0 if photo else 1), effets=[], regard=p.get('regard'),
                 entree=p.get('entree'), sortie=p.get('sortie'), sans_accent=bool(p.get('sans_accent')),
                 _fichier=str(abs_src), _zoom=float(p.get('zoom', 1)), _cx=float(p.get('cx', 0.5)), _cy=float(p.get('cy', 0.5)),
                 _masque=bool(p.get('masque')), _son=p.get('son', False), _etalonnage=p.get('etalonnage', fiche.get('etalonnage', 'naturel')),
                 _stabilise=p.get('stabilise') or False, _cadrage=p.get('cadrage'), _lut=str(projet / p['lut']) if p.get('lut') else None)
        st = q['_stabilise']
        if st and st is not True and not (isinstance(st, (int, float)) and 0.2 <= st <= 6):
            rq.erreur(f'plan {pid} : « stabilise » vaut true ou une durée de lissage en secondes (0.2 à 6 ; 1.5 par défaut)'); q['_stabilise'] = True
        if q['_cadrage'] not in (None, 'fixe', 'visage'):
            rq.erreur(f'plan {pid} : « cadrage » vaut "visage" (le rognage suit le visage) ou "fixe"'); q['_cadrage'] = None
        if q['_lut'] and not Path(q['_lut']).exists():
            rq.erreur(f'plan {pid} : fichier LUT introuvable : {p["lut"]}')
        if photo:
            q['vitesse'] = 0
        # « cadre » : l'image se range dans un tirage photo blanc penché (style affiche), sur la même image floutée
        cad = p.get('cadre')
        if cad is not None:
            if cad is True:
                cad = {}
            if not isinstance(cad, dict):
                rq.erreur(f'plan {pid} : « cadre » vaut true ou un objet {{"l", "y", "angle", "de", "entree", ...}}'); cad = {}
            inconnues = set(cad) - {'x', 'y', 'l', 'ratio', 'bord', 'bas', 'angle', 'de', 'entree', 'flou', 'sombre', 'couleur'}
            if inconnues:
                rq.erreur(f'plan {pid} : cadre, clés inconnues : {", ".join(sorted(inconnues))}')
            l_ = float(cad.get('l', round(W * 0.76)))
            g = dict(x=float(cad.get('x', W / 2)), y=float(cad.get('y', round(H * 0.58))), l=l_, h=round(l_ * float(cad.get('ratio', 1.0))),
                     bord=float(cad.get('bord', 30)), bas=float(cad.get('bas', 30)), angle=float(cad.get('angle', -2.5)),
                     de=int(round(img(cad.get('de', 0), f'plan {pid}, cadre'))), entree=max(1, int(round(img(cad.get('entree', 12), f'plan {pid}, cadre')))),
                     flou=float(cad.get('flou', 34)), sombre=float(cad.get('sombre', 0.55)), couleur=cad.get('couleur', '#FAFAF7'))
            if abs(g['angle']) > 8:
                rq.attention(f'plan {pid} : cadre penché de {g["angle"]:g}° : au-delà de 8°, il paraît tomber')
            if g['l'] + 2 * g['bord'] > W:
                rq.erreur(f'plan {pid} : cadre plus large que l\'image ({g["l"] + 2 * g["bord"]:.0f} px pour {W})')
            q['cadre'] = g
        if q['regard'] and q['regard'] not in REGARDS and '(' not in str(q['regard']):
            rq.erreur(f'plan {pid} : regard inconnu « {q["regard"]} » (disponibles : {", ".join(sorted(REGARDS))})')
        for cote in ('entree', 'sortie'):
            if q[cote] and q[cote] not in TRANSITIONS:
                rq.erreur(f'plan {pid} : transition inconnue « {q[cote]} » (disponibles : {", ".join(sorted(TRANSITIONS))})'); q[cote] = None
        n = t1 - t
        zmax = 1.0
        for e in p.get('effets', []):
            if e.get('t') not in EFFETS:
                rq.erreur(f'plan {pid} : effet inconnu « {e.get("t")} » (disponibles : {", ".join(sorted(EFFETS))})'); continue
            e = dict(e)
            for k in ('at', 'd', 'k0', 'k1'):
                if k in e:
                    e[k] = int(round(img(e[k], f'plan {pid}, effet {e["t"]}')))
            if e['t'] == 'kb':
                zmax = max(zmax, e.get('a', 1), e.get('b', 1.08))
            if e['t'] == 'zr':
                zmax = max(zmax, e.get('a', 1), e.get('b', 1))
            if e['t'] == 'punch':
                e.setdefault('at', 0); e.setdefault('a', 0.08); e.setdefault('d', 8); zmax = max(zmax, 1 + e['a'])
            if e['t'] in ('shake', 'flash', 'rgb'):
                e.setdefault('at', 0); e.setdefault('d', 6); e.setdefault('a', 10)
            q['effets'].append(e)
        q['_zmax'] = min(1.6, zmax * 1.03)
        # rampe de vitesse : instants en images du plan
        if isinstance(q['vitesse'], list):
            q['vitesse'] = [[int(round(img(k, f'plan {pid}, vitesse'))), float(v)] for k, v in q['vitesse']]
        if not abs_src.exists():
            rq.erreur(f'plan {pid} : fichier introuvable : {chemin}')
        else:
            try:
                s = sondes.setdefault(str(abs_src), sonde(abs_src))
                q['_sonde'] = s
                if not photo:
                    ts = temps_sources(q, ips)
                    if min(ts) < -0.01 or max(ts) > s['duree'] + 0.05:
                        rq.erreur(f'plan {pid} : le passage demandé ({min(ts):.2f} s → {max(ts):.2f} s) sort de la vidéo (durée {s["duree"]:.2f} s)')
                    v_min = min(abs(x) for x in (vitesses(q))) if not isinstance(q['vitesse'], (int, float)) or q['vitesse'] else 1
                    if 0 < v_min < 0.75 and s['ips'] * v_min < ips * 0.6:
                        rq.attention(f'plan {pid} : ralenti à {v_min:g}× sur une vidéo à {s["ips"]:.0f} i/s : le mouvement sera fondu (filmer à 60 i/s pour un vrai ralenti)')
                    if s['l'] / q['_zoom'] < W * 0.92:
                        rq.attention(f'plan {pid} : zoom {q["_zoom"]:g} sur une vidéo de {s["l"]} px de large : image agrandie, donc moins nette')
                else:
                    besoin = W * q['_zoom'] * q['_zmax']
                    if s['l'] < besoin * 0.9 and s['h'] < H * q['_zoom'] * q['_zmax'] * 0.9:
                        rq.attention(f'plan {pid} : photo de {s["l"]}×{s["h"]} px un peu petite pour ce zoom (il faudrait {besoin:.0f} px de large) : moins nette')
            except ValueError as e:
                rq.erreur(f'plan {pid} : {e}')
        # deuxième image dans le même plan : double exposition (« superpose ») ou écran partagé (« partage »)
        d2 = p.get('double')
        if d2 and not photo:
            mode = d2.get('mode', 'superpose')
            src2 = projet / str(d2.get('source', ''))
            if mode not in ('superpose', 'partage'):
                rq.erreur(f'plan {pid} : double, « mode » vaut "superpose" (double exposition) ou "partage" (écran partagé)')
            elif not src2.exists():
                rq.erreur(f'plan {pid} : double, fichier introuvable : {d2.get("source")}')
            else:
                de2 = d2.get('de', 0)
                dec2 = calage.get(str(src2.resolve()))
                if dec2 is not None and 'de' not in d2:
                    de2 = round(float((tempo or {}).get('debut_cale', mus.get('debut', 0))) + t / ips - dec2, 4)
                q2 = dict(id=f'{pid}-2', t0=t, t1=t1, photo=False, src=float(de2), vitesse=d2.get('vitesse', 1), effets=[], regard=d2.get('regard'),
                          entree=None, sortie=None, sans_accent=True, _fichier=str(src2), _zoom=float(d2.get('zoom', 1)),
                          _cx=float(d2.get('cx', 0.5)), _cy=float(d2.get('cy', 0.5)), _masque=False, _son=False,
                          _etalonnage=d2.get('etalonnage', q['_etalonnage']), _stabilise=False, _lut=None, _cadrage=d2.get('cadrage'), _zmax=1.03)
                if isinstance(q2['vitesse'], list):
                    q2['vitesse'] = [[int(round(img(k, f'plan {pid}, double'))), float(v)] for k, v in q2['vitesse']]
                try:
                    s2 = sondes.setdefault(str(src2), sonde(src2)); q2['_sonde'] = s2
                    ts2 = temps_sources(q2, ips)
                    if min(ts2) < -0.01 or max(ts2) > s2['duree'] + 0.05:
                        rq.erreur(f'plan {pid} : double, le passage demandé ({min(ts2):.2f} s → {max(ts2):.2f} s) sort de la vidéo (durée {s2["duree"]:.2f} s)')
                except ValueError as e:
                    rq.erreur(f'plan {pid} : double, {e}')
                q['double'] = q2
                q['double_mode'] = mode
                q['double_force'] = float(d2.get('force', 0.45 if mode == 'superpose' else 1))
        plans.append(q)
        t, b = t1, b_fin
    N = t
    # transitions : la « sortie » d'un plan devient l'« entrée » du suivant
    for i, q in enumerate(plans):
        if q['sortie'] and q['sortie'] != 'coupe' and i + 1 < len(plans) and not plans[i + 1]['entree']:
            plans[i + 1]['entree'] = q['sortie']
        if i == len(plans) - 1 and q['sortie'] in ('zoom', 'whipG', 'whipD', 'whipH', 'whipB', 'glitch'):
            rq.attention(f'plan {q["id"]} : transition de sortie « {q["sortie"]} » sur le dernier plan (rien après)')
    for src_c in fiche.get('calage') or {}:
        if src_c and str((projet / src_c).resolve()) in calage and not any(q['_fichier'] == str(projet / src_c) or Path(q['_fichier']).resolve() == (projet / src_c).resolve() for q in plans):
            rq.conseil(f'calage : « {src_c} » n\'est utilisée par aucun plan')
    for q in plans:
        n = q['t1'] - q['t0']
        pris = DUREE_TRANSITION.get(q['entree'] or 'coupe', (0, 0))[1] + DUREE_TRANSITION.get(q['sortie'] or 'coupe', (0, 0))[0]
        if pris > n:
            rq.attention(f'plan {q["id"]} : {n} images seulement, les transitions en prennent {pris}')

    # flashs : jamais plus de 3 par seconde (confort et sécurité des yeux)
    flashs = sorted([q['t0'] for q in plans if q['entree'] == 'flash'] + [q['t0'] + e['at'] for q in plans for e in q['effets'] if e['t'] == 'flash'])
    for i in range(len(flashs) - 3):
        if flashs[i + 3] - flashs[i] < ips:
            rq.erreur(f'trop de flashs autour de l\'image {flashs[i]} : plus de 3 en une seconde'); break

    # ---------------- accents sur la musique
    accents = []
    ac = fiche.get('accents')
    if ac and periode:
        pas = float(ac.get('tous_les', 2)); dec = float(ac.get('decalage', 1))
        a0 = img(ac.get('de', 0), 'accents'); a1 = img(ac.get('a', N), 'accents')
        k = 0
        while True:
            at = (dec + k * pas) * periode * ips
            if at >= min(a1, N):
                break
            if at >= a0:
                accents.append(dict(at=round(at, 2), d=int(ac.get('duree', 6)), z=float(ac.get('zoom', 0.028)), sh=float(ac.get('secousse', 0)), fl=float(ac.get('flash', 0))))
            k += 1
    elif ac and not periode:
        rq.attention('« accents » demande une musique (tempo) : ignoré')

    # ---------------- calques
    calques = []
    bas_limite = []
    par_id = {q['id']: q for q in plans}
    a_poser = []
    for i, c in enumerate(fiche.get('calques') or []):
        if c.get('t') == 'sous-titres' and c.get('plan') == 'tous':      # face caméra : les mêmes sous-titres sur chaque plan qui parle
            parlants = [q['id'] for q in plans if q['_son'] and not q['photo']]
            if not parlants:
                rq.erreur(f'calque {i + 1} (sous-titres) : « plan: tous » demande au moins un plan avec "son": true')
            a_poser += [(i, {**c, 'plan': pid}) for pid in parlants]
        else:
            a_poser.append((i, c))

    def mots_st(c, pl):
        """Mots d'un calque de sous-titres : écrits dans la fiche, ou « auto » : les paroles du plan, sinon celles de toute la prise."""
        mots = c.get('mots') or []
        if mots == 'auto':
            mots = (paroles or {}).get(pl['id']) or (prises or {}).get(Path(pl['_fichier']).name, [])
        return mots
    # plans à sous-titres et la liste de mots que chacun lit : un mot à cheval sur une coupe entre deux plans qui lisent la même liste
    # ne s'affiche que dans un des deux (Reels des stands, 13/11 : « mots en double » à chaque coupe)
    sous_titres = [(par_id[c['plan']], mots_st(c, par_id[c['plan']])) for _, c in a_poser
                   if c.get('t') == 'sous-titres' and c.get('plan') in par_id and par_id[c['plan']]['vitesse'] == 1]
    for i, c in a_poser:
        nom = f'calque {i + 1} ({c.get("t")})'
        if c.get('t') not in TYPES_CALQUE:
            rq.erreur(f'{nom} : type inconnu (disponibles : {", ".join(sorted(TYPES_CALQUE))})'); continue
        r = dict(c)
        pl = par_id.get(c.get('plan')) if c.get('plan') else None
        if c.get('plan') and not pl:
            rq.erreur(f'{nom} : plan « {c["plan"]} » introuvable'); continue
        base = pl['t0'] if pl else 0
        de = base + int(round(img(c.get('de', 0), nom)))
        if 'a' in c:
            a = base + int(round(img(c['a'], nom)))
        elif 'duree' in c:
            a = de + int(round(img(c['duree'], nom)))
        else:
            a = pl['t1'] if pl else N
        r['de'], r['a'] = de, min(max(a, de + 1), N)
        r.pop('duree', None)
        if c.get('derriere'):
            if not pl:
                rq.erreur(f'{nom} : « derriere » demande « plan »'); continue
            if not pl['_masque']:
                rq.erreur(f'{nom} : texte derrière le sujet, mais le plan {pl["id"]} n\'a pas « masque: true »'); continue
        boite = None
        t_ = c['t']
        if t_ == 'titre':          # durées de l'animation et du fondu de sortie : en images, secondes ou temps
            for k_ in ('duree_anim', 'fondu'):
                if k_ in c:
                    r[k_] = max(1, int(round(img(c[k_], nom))))
        if t_ in ('titre', 'etiquette', 'compteur', 'mots'):
            spec = dict(theme[c.get('police') or ('mono' if t_ == 'etiquette' else 'titre')])
            if 'espacement' in c:
                spec['espacement'] = c['espacement']
            familles.add(spec['famille'])
            align = c.get('align', 'centre')
            x = c.get('x', W / 2 if align == 'centre' else (zones['marge'] if align == 'gauche' else W - zones['marge']))
            r['x'], r['align'] = x, align
            dispo = c.get('largeur') or (2 * min(x, W - x) - 2 * zones['marge'] if align == 'centre' else (W - x - zones['marge'] if align == 'gauche' else x - zones['marge']))
            dispo = max(120, dispo)

            def ajuste(texte, taille):
                w = largeur_texte(texte, spec, taille)
                if w > dispo:
                    taille = math.floor(taille * dispo / w); w = largeur_texte(texte, spec, taille)
                return taille, w
            if t_ == 'titre':
                lignes = c.get('lignes') or str(c.get('texte', '')).split('\n')
                if not any(lignes):
                    rq.erreur(f'{nom} : texte vide'); continue
                tailles = c.get('tailles') or [c.get('taille', 150)] * len(lignes)
                res, wmax, htot = [], 0, 0
                inter = c.get('interligne', 0.95)
                for li, ta in zip(lignes, tailles):
                    ta2, w = ajuste(li, ta)
                    if ta2 < ta * 0.6:
                        rq.attention(f'{nom} : « {li} » réduit de {ta} à {ta2} px pour tenir dans l\'image (couper le texte en deux lignes ?)')
                    res.append(dict(texte=casse(li, spec), taille=ta2)); wmax = max(wmax, w); htot += ta2 * inter
                r['lignes'] = res
                r.pop('texte', None); r.pop('tailles', None); r.pop('taille', None)
                boite = (x, c.get('y', 0), wmax, htot, align)
                petite = min(l_['taille'] for l_ in res)
            elif t_ == 'etiquette':
                ta2, w = ajuste(str(c.get('texte', '')), c.get('taille', TEXTE_MINI))
                r['texte'], r['taille'] = casse(str(c.get('texte', '')), spec), ta2
                boite = (x, c.get('y', 0), w, ta2 * 1.2, align); petite = ta2
            elif t_ == 'compteur':
                gabarit = (c.get('prefixe', '') + ('00:00' if c.get('format') == 'temps' else str(int(max(abs(c.get('valeur', 0)), abs(c.get('depuis', 0))))) + (',0' if c.get('format') == 'decimal1' else '')) + c.get('suffixe', ''))
                chasse = max(largeur_texte(ch, spec, 100) for ch in '0123456789') / 100
                ta = c.get('taille', 220)
                w = sum(chasse * ta if ch.isdigit() else largeur_texte(ch, spec, ta) for ch in gabarit)
                if w > dispo:
                    ta = math.floor(ta * dispo / w); w = dispo
                r['taille'], r['chasse'] = ta, round(chasse, 4)
                r['duree_anim'] = int(round(img(c.get('duree_anim', 24), nom)))
                boite = (x, c.get('y', 0), w, ta, align); petite = ta
            else:  # mots
                mots = c.get('mots') or [m for m in re.split(r'\s*/\s*|\n', str(c.get('texte', ''))) if m]
                pas = img(c.get('rythme', '1t' if periode else 8), nom)
                res, wmax, tmax = [], 0, 0
                for j, m in enumerate(mots):
                    if isinstance(m, dict):
                        mde, ma, txt, coul = base + img(m['de'], nom), base + img(m['a'], nom), m['m'], m.get('couleur')
                    else:
                        mde, ma, txt, coul = de + j * pas, de + (j + 1) * pas, m, None
                    ta2, w = ajuste(txt, c.get('taille', 220))
                    e = dict(m=casse(txt, spec), de=int(round(mde)), a=int(round(ma)), taille=ta2)
                    if coul or (c.get('alterne') and j % 2):
                        e['couleur'] = coul or 'accent'
                    res.append(e); wmax = max(wmax, w); tmax = max(tmax, ta2)
                if not res:
                    rq.erreur(f'{nom} : aucun mot'); continue
                r['mots'] = res
                r['de'], r['a'] = res[0]['de'], min(N, res[-1]['a'])
                r.pop('texte', None); r.pop('rythme', None)
                boite = (x, c.get('y', 0), wmax, tmax, align); petite = tmax
            coul = theme.get(c.get('couleur') or ('clair' if t_ == 'etiquette' else 'fort'), c.get('couleur'))
            if _couleur_vive(coul) and petite < 64 and not c.get('fond'):
                rq.attention(f'{nom} : texte de couleur vive en petit ({petite} px) : la compression d\'Instagram le rend baveux. Préférer blanc sur pastille de couleur (« fond »), ou plus gros.')
            if petite < TEXTE_MINI:
                rq.conseil(f'{nom} : texte de {petite} px, trop petit pour un téléphone ({TEXTE_MINI} px au moins)')
            if c.get('fond') and not c.get('couleur'):          # texte sombre sur une pastille claire, clair sur une pastille de couleur
                r['couleur'] = 'encre' if _couleur_claire(theme.get(c['fond'], c['fond'])) else 'clair'
            if 'y' not in c:
                rq.erreur(f'{nom} : « y » manque (hauteur du texte dans l\'image, entre {zones["haut"]} et {zones["bas"]})')
        elif t_ == 'sous-titres':
            spec = dict(theme[c.get('police') or 'texte']); familles.add(spec['famille'])
            ta = c.get('taille', round(TAILLE_SOUS_TITRES * ex))
            r['y'] = c.get('y', round(zones['bas_conseille'] - 2 * 1.18 * ta))       # deux lignes tiennent au-dessus de la légende d'Instagram
            if not pl:
                rq.erreur(f'{nom} : « plan » manque (les sous-titres suivent la parole d\'un plan)'); continue
            mots = mots_st(c, pl)       # seuls les mots dits pendant le plan sont gardés plus bas
            if isinstance(pl['vitesse'], list) or pl['vitesse'] != 1:
                rq.erreur(f'{nom} : le plan {pl["id"]} doit être à vitesse 1 pour des sous-titres'); continue
            conv = lambda s: pl['t0'] + (float(s) - pl['src']) * ips
            voisins = [q for q, l_ in sous_titres if l_ is mots and q is not pl]      # plans qui lisent les mêmes paroles
            lus = [dict(m=casse(str(m[0]), spec), de=conv(m[1]), a=conv(m[2])) for m in mots if mot_du_plan(m, pl, voisins, ips)]
            # en bas de l'image, les sous-titres restent à gauche des boutons d'Instagram
            larg = c.get('largeur') or (min(W - 2 * zones['marge'], 2 * (zones['droite'] - W / 2)) if r['y'] + ta * 2.4 > zones['droite_depuis'] else W - 2 * zones['marge'])
            long_ = max((largeur_texte(m['m'] + ' ', spec, ta) * 1.12 for m in lus), default=0)
            if long_ > larg - 40:                                 # un mot très long : tout le calque rétrécit pour qu'il tienne (une seule taille de sous-titres)
                ta = max(TEXTE_MINI, math.floor(ta * (larg - 40) / long_))
            r['taille'] = ta
            r['groupes'] = grouper_mots(lus, spec, ta, larg - 40, c.get('mots_max', 3), ips)
            r['de'], r['a'] = pl['t0'], pl['t1']
            if c.get('style') == 'pastille' and not c.get('couleur_sur_actif'):     # le mot prononcé reste lisible sur sa pastille
                r['couleur_sur_actif'] = 'encre' if _couleur_claire(theme.get(c.get('couleur_active') or 'accent', c.get('couleur_active'))) else 'clair'
            r.pop('mots', None)
            boite = (W / 2, r['y'], max((sum(largeur_texte(m['m'] + ' ', spec, ta) * 1.12 for m in l_) for g in r['groupes'] for l_ in g['lignes']), default=0), ta * 1.18 * 2, 'centre')
            if not mots:
                rq.attention(f'{nom} : aucun mot (lancer « transcrire » ou donner « mots »)')
        elif t_ == 'bandes':      # bandes noires du cinéma (cinémascope) : elles glissent en place, puis repartent
            ratio = float(c.get('ratio', 2.39))
            if ratio <= W / H:
                rq.erreur(f'{nom} : ratio {ratio:g} pas plus large que l\'image ({W / H:.2f}) : aucune bande'); continue
            r.update(hauteur=round((H - W / ratio) / 2), glisse=int(round(img(c.get('glisse', 12), nom))), depuis_noir=bool(c.get('depuis_noir')))
        elif t_ == 'lumiere':     # fuites de lumière de pellicule : taches chaudes qui passent sur l'image
            r.update(force=float(c.get('force', 0.5)), couleur=c.get('couleur', '#FF7A2E'), couleur2=c.get('couleur2', '#FFD08A'),
                     cote=c.get('cote', 'gauche'), fondu=int(round(img(c.get('fondu', 10), nom))))
        elif t_ == 'image':
            f_ = projet / str(c.get('fichier', ''))
            if not f_.exists():
                rq.erreur(f'{nom} : image introuvable : {c.get("fichier")}'); continue
            s = sondes.setdefault(str(f_), sonde(f_))
            l_ = float(c.get('l', 400)); h_ = l_ * s['h'] / s['l']
            if s['l'] < l_ * 0.9:
                rq.attention(f'{nom} : image de {s["l"]} px affichée sur {l_:.0f} px : agrandie, donc floue. Fournir une image plus grande.')
            r.update(l=l_, h=h_, x=c.get('x', W / 2), y=c.get('y', H / 2), _fichier=str(f_), fichier=nom_image(f_, l_))
            boite = (r['x'], r['y'] - h_ / 2, l_, h_, 'centre')
        elif t_ == 'signature':
            spec = dict(theme['titre'])
            tn = c.get('taille', 120); w = largeur_texte(c.get('nom', ''), spec, tn)
            if w > W - 2 * zones['marge']:
                tn = math.floor(tn * (W - 2 * zones['marge']) / w)
            tl = c.get('taille_ligne', 40); spec2 = dict(theme['texte'])
            for li in str(c.get('ligne', '')).split('\n'):
                w = largeur_texte(li, spec2, tl)
                if w > W - 2 * zones['marge']:
                    tl = math.floor(tl * (W - 2 * zones['marge']) / w)
            r.update(nom=casse(c.get('nom', ''), spec), taille_nom=tn, taille_ligne=tl, y_nom=c.get('y', round(860 * ey)))
            if c.get('logo'):
                f_ = projet / c['logo']
                if not f_.exists():
                    rq.erreur(f'{nom} : logo introuvable : {c["logo"]}'); continue
                s = sondes.setdefault(str(f_), sonde(f_))
                ll = float(c.get('logo_l', 300)); lh = ll * s['h'] / s['l']
                r.update(logo=nom_image(f_, ll), _fichier=str(f_), logo_l=ll, logo_h=lh, y_logo=r['y_nom'] - lh - 50)
        # zones d'Instagram
        if boite and not c.get('hors_zone'):
            bx, by, bw, bh, al = boite
            x0 = bx - bw / 2 if al == 'centre' else (bx if al == 'gauche' else bx - bw); x1 = x0 + bw; y1 = by + bh
            if by < zones['haut'] - 2:
                rq.attention((f'{nom} : commence à y={by:.0f}, caché par la barre du haut d\'Instagram (descendre à y={zones["haut"]} au moins)' if zones['reel'] else f'{nom} : trop près du haut (y={by:.0f}, marge {zones["haut"]})') + ' ; « hors_zone: true » si voulu')
            if y1 > zones['bas'] + 2:
                rq.attention((f'{nom} : descend à y={y1:.0f}, caché par la légende d\'Instagram (rester au-dessus de {zones["bas"]})' if zones['reel'] else f'{nom} : trop près du bas (y={y1:.0f}, limite {zones["bas"]})') + ' ; « hors_zone: true » si voulu')
            elif y1 > zones['bas_conseille'] + 2 and t_ in ('titre', 'mots', 'compteur', 'signature'):
                bas_limite.append(nom)
            if x0 < zones['marge'] - 2 or x1 > W - zones['marge'] + 2:
                rq.attention(f'{nom} : trop près du bord (de x={x0:.0f} à x={x1:.0f}, marge {zones["marge"]})')
            if x1 > zones['droite'] + 2 and y1 > zones['droite_depuis']:
                rq.attention(f'{nom} : passe sous les boutons de droite d\'Instagram (x>{zones["droite"]} en bas de l\'image)')
        calques.append(r)

    # ---------------- polices à charger
    polices = []
    for fam in sorted(familles):
        if fam not in POLICES:
            rq.erreur(f'police inconnue : {fam} (disponibles : {", ".join(sorted(POLICES))})'); continue
        for f, w, s in POLICES[fam]:
            polices.append([fam, f, w, s])

    # ---------------- sons
    sons = []
    if fiche.get('sons_auto', True):
        for q in plans[1:]:
            tr = q['entree']
            if tr in SON_TRANSITION:
                nom_son, db, cal = SON_TRANSITION[tr]
                sons.append(dict(son=nom_son, at=q['t0'], db=db, calage=cal, auto=True))
    for s in fiche.get('sons') or []:
        try:
            fichier_son(s.get('son', ''), projet)
        except ValueError as e:
            rq.erreur(str(e)); continue
        pl = par_id.get(s.get('plan')) if s.get('plan') else None
        at = (pl['t0'] if pl else 0) + img(s.get('at', 0), 'son')
        sons.append(dict(son=s['son'], at=round(at, 2), db=float(s.get('db', -12)), calage=s.get('calage', 'attaque'),
                         coupe=s.get('coupe'), fondu=s.get('fondu', 0.12)))

    # ---------------- remarques générales
    if N < 3 * ips:
        rq.attention(f'montage très court : {N / ips:.1f} s')
    if N > 90 * ips and zones['reel']:
        rq.attention(f'montage long : {N / ips:.0f} s (au-delà de 90 s, Instagram le montre moins)')
    if bas_limite:
        rq.conseil(f'{", ".join(bas_limite)} : entre y={zones["bas_conseille"]} et y={zones["bas"]}, caché quand la légende du Reel est longue (repère de Meta : rester au-dessus de {zones["bas_conseille"]} pour l\'essentiel)')
    textes_debut = [c for c in calques if c['t'] in ('titre', 'mots', 'compteur') and c['de'] <= ips]
    if calques and not textes_debut and zones['reel']:
        rq.conseil('aucun texte dans la première seconde : l\'accroche se joue là (un titre ou un chiffre dès le début retient mieux)')
    # quelque chose doit changer toutes les 2 à 4 secondes : une coupe, un texte qui arrive, un accent sur la musique
    instants = {0, N} | {q['t0'] for q in plans} | {int(a['at']) for a in accents}
    for c in calques:
        instants |= {c['de']} | {g['de'] for g in c.get('groupes', [])} | {m['de'] for m in c.get('mots', []) if isinstance(m, dict)}
    instants = sorted(i for i in instants if 0 <= i <= N)
    creux = max(zip(instants, instants[1:]), key=lambda ab: ab[1] - ab[0], default=None)
    if creux and creux[1] - creux[0] > SANS_CHANGEMENT * ips:
        rq.conseil(f'de {creux[0] / ips:.1f} s à {creux[1] / ips:.1f} s, rien ne change à l\'image (ni coupe, ni texte, ni accent) : l\'attention retombe après 4 secondes, prévoir un changement toutes les 2 à 4 secondes')
    if not mus:
        rq.conseil('pas de musique dans la fiche : la vidéo sortira avec les bruitages seuls (musique à poser dans Instagram)')

    fin = fiche.get('finition', {})
    calcul = dict(nom=fiche.get('nom', projet.name), l=W, h=H, ips=ips, n=N, theme=theme, polices=polices,
                  finition=dict(grain=float(fin.get('grain', 0.1)), vignette=float(fin.get('vignette', 0.35)), nettete=bool(fin.get('nettete', True))), fondu_fin=int(fin.get('fondu_fin', 0)),
                  plans=plans, calques=calques, accents=accents, zones_instagram=zones, audio=None,
                  _sons=sons, _musique=mus, _periode=periode)
    return calcul, rq


def vitesses(q):
    """Vitesses rencontrées dans un plan (pour les contrôles)."""
    if isinstance(q['vitesse'], (int, float)):
        return [q['vitesse']]
    return [v for _, v in q['vitesse']]


def temps_sources(q, ips):
    """Temps (en secondes dans la vidéo source) de chaque image du plan, rampes de vitesse comprises."""
    n = q['t1'] - q['t0']
    sp = q['vitesse']
    if isinstance(sp, (int, float)):
        return [q['src'] + sp * k / ips for k in range(n)]
    def v(k):
        if k <= sp[0][0]:
            return sp[0][1]
        for (a, va), (b_, vb) in zip(sp, sp[1:]):
            if a <= k <= b_:
                return va + (vb - va) * (k - a) / (b_ - a) if b_ > a else vb
        return sp[-1][1]
    out, t = [], q['src']
    for k in range(n):
        out.append(t); t += v(k) / ips
    return out


def mot_du_plan(m, q, voisins, ips):
    """Le mot m = [texte, début, fin] (temps de la source) s'affiche-t-il dans les sous-titres du plan q (vitesse 1) ? Oui s'il est dit
    pendant le plan. Mais un mot à cheval sur une coupe, dont un des `voisins` (plans à sous-titres qui lisent les mêmes paroles) montre
    aussi une part, ne s'affiche que dans le plan qui en garde la plus grande part (le premier des deux si elles sont égales)."""
    fin = lambda p: p['src'] + (p['t1'] - p['t0']) / ips
    de, a = float(m[1]), float(m[2])
    if not (a > q['src'] and de < fin(q)):
        return False                                     # pas dit pendant ce plan
    if de >= q['src'] and a <= fin(q):
        return True                                      # dit en entier dans ce plan
    part = lambda p: min(a, fin(p)) - max(de, p['src'])
    ici = part(q)
    return not any(part(p) > 0 and (part(p) > ici + 1e-6 or (abs(part(p) - ici) <= 1e-6 and p['t0'] < q['t0'])) for p in voisins)


def grouper_mots(mots, spec, taille, largeur, mots_max, ips):
    """Regroupe les mots prononcés en petits groupes lisibles (2 lignes au plus), sans trou d'affichage entre deux mots.
    Un groupe s'arrête à la ponctuation, à une pause, ou à `mots_max` mots ; jamais un mot seul en fin de phrase quand on peut
    l'éviter, et deux lignes de longueurs voisines plutôt qu'un mot orphelin sur la seconde."""
    large = lambda ms: sum(largeur_texte(m['m'] + ' ', spec, taille) * 1.12 for m in ms)

    def lignes_de(ms):
        if len(ms) < 2 or large(ms) <= largeur:
            return [ms]
        coupes = [(max(large(ms[:k]), large(ms[k:])), k) for k in range(1, len(ms)) if large(ms[:k]) <= largeur and large(ms[k:]) <= largeur]
        if coupes:                                       # deux lignes, les plus égales possible
            k = min(coupes)[1]
            return [ms[:k], ms[k:]]
        lignes, ligne = [], []                           # trop long pour deux lignes : une ligne après l'autre
        for m in ms:
            if ligne and large(ligne + [m]) > largeur:
                lignes.append(ligne); ligne = []
            ligne.append(m)
        return lignes + [ligne]

    paquets, pleins = [], []                             # pleins[i] : le paquet i s'est fermé parce qu'il était plein (pas sur une ponctuation ni une pause)
    cur = []
    for m in mots:
        m = dict(m=m['m'], de=int(round(m['de'])), a=int(round(m['a'])))
        if m['a'] <= m['de']:
            m['a'] = m['de'] + 1
        if cur:
            fin_ = cur[-1]['m'].rstrip(' \u00a0»"')[-1:]
            naturel = m['de'] - cur[-1]['a'] > 0.45 * ips or (fin_ and fin_ in '.!?…') or (fin_ and fin_ in ',;:' and len(cur) >= 2)
            if naturel or len(cur) >= mots_max or len(lignes_de(cur + [m])) > 2:
                paquets.append(cur); pleins.append(not naturel); cur = []
        cur.append(m)
    if cur:
        paquets.append(cur); pleins.append(False)
    for i in range(1, len(paquets)):                     # un mot seul après un paquet plein : on lui donne le dernier mot du paquet d'avant
        if len(paquets[i]) == 1 and pleins[i - 1] and len(paquets[i - 1]) >= 3 and len(lignes_de([paquets[i - 1][-1]] + paquets[i])) <= 2:
            paquets[i].insert(0, paquets[i - 1].pop())
    groupes = [dict(de=ms[0]['de'], a=ms[-1]['a'], lignes=lignes_de(ms)) for ms in paquets]
    # un mot reste allumé jusqu'au suivant ; un groupe reste affiché jusqu'au suivant si la pause est courte
    for g in groupes:
        plats = [m for l_ in g['lignes'] for m in l_]
        for m1, m2 in zip(plats, plats[1:]):
            m1['a'] = m2['de']
    for g1, g2 in zip(groupes, groupes[1:]):
        if g2['de'] - g1['a'] < 0.45 * ips:
            g1['a'] = g2['de']; g1['lignes'][-1][-1]['a'] = g2['de']
    return groupes


def charger(projet):
    """Lit la fiche montage.json d'un dossier de projet."""
    f = Path(projet) / 'montage.json'
    if not f.exists():
        raise FileNotFoundError(f'pas de fiche montage.json dans {projet}')
    try:
        return json.loads(f.read_text(encoding='utf-8'))
    except json.JSONDecodeError as e:
        raise ValueError(f'montage.json mal écrit : ligne {e.lineno}, colonne {e.colno} : {e.msg}')


def public(calcul):
    """Calcul sans les clés internes (celles qui commencent par « _ ») : c'est ce que lit le moteur."""
    def net(x):
        if isinstance(x, dict):
            return {k: net(v) for k, v in x.items() if not k.startswith('_')}
        if isinstance(x, list):
            return [net(v) for v in x]
        return x
    return net(calcul)
