"""Garde-tête : une tête n'est jamais coupée par le cadre ni couverte par un texte, et deux textes ne se chevauchent jamais.

Demande de Yohann (13/11/2026) : « ne jamais couper la tête avec les animations, les effets spéciaux et le texte ; toujours vérifier
que c'est bien fait, systématiquement ». Le contrôle tourne à chaque préparation (planche, aperçu, final, couverture) et dans
« verifier » dès que les plans sont prêts. Tant qu'il reste un problème, l'aperçu, la vidéo finale et la couverture sont refusés.

1. Les têtes : détecteur YuNet (celui de « cadrage: visage ») sur les images préparées de chaque plan, une image sur 4 de la vidéo.
   Une tête qui n'apparaît pas aussi sur l'image analysée d'avant ou d'après est écartée (fausse détection).
2. Le chemin de chaque image jusqu'à l'écran, recalculé comme le moteur (Plan.jsx, Moteur.jsx) : Ken Burns, rampe de zoom, punch,
   secousses, coups sur la musique, écran partagé, bandes du cinéma. Les 2 à 5 images d'une transition où toute l'image file
   (zoom, whip, glitch) ne comptent pas.
3. Chaque texte à chaque image, animations comprises (pop, glisse, cinéma, mots qui claquent, sous-titres…), comme calques.jsx.

Mesures prises sur un visage réel : le détecteur donne le visage du milieu du front au menton ; le haut du crâne est 35 à 42 %
de sa hauteur au-dessus. Tête entière = le visage + 36 % au-dessus : coupée si le cadre en retire plus de 4 % de la hauteur du
visage (une mèche, pas plus). Zone sans texte = 85 % au-dessus (le crâne, puis un vrai espace : contre-essai du 13/11 sur un
Reel Foulées, à 60 % le titre frôlait le crâne), 25 % de chaque côté, 30 % sous le menton.
"""
import bisect
import json
import math
from pathlib import Path

import fiche as F

import ressources as RES

TD = F.DUREE_TRANSITION
FILENT = {'zoom', 'whipG', 'whipD', 'whipH', 'whipB', 'glitch'}     # transitions où toute l'image file : leurs images ne comptent pas
TEXTES = {'titre', 'mots', 'sous-titres', 'etiquette', 'compteur', 'signature'}
COUVRANTS = {'titre', 'mots', 'sous-titres', 'etiquette', 'compteur', 'image'}
MOBILES = {'titre', 'mots', 'sous-titres', 'etiquette', 'compteur', 'image'}
NOMS_BORD = {'haut': 'en haut', 'bas': 'en bas', 'gauche': 'à gauche', 'droite': 'à droite'}
NOMS_EFFET = {'kb': 'Ken Burns', 'zr': 'rampe de zoom', 'punch': 'punch', 'accents': 'coups sur la musique'}

SEUIL = 0.7              # confiance du détecteur (comme cadrage.py)
PAS = 4                  # une analyse toutes les 4 images de la vidéo (7,5 par seconde)
PETIT = 0.03             # visage plus étroit que 3 % du petit côté de l'image : personne au loin, pas gardée
RELATIF = 0.35           # et au moins 35 % du plus grand visage de la même image (les passants derrière ne comptent pas)
TETE = (0.05, 0.36, 0.05, 0.0)       # tête entière autour du visage : gauche, haut, droite, bas (en fraction du visage)
ZONE = (0.25, 0.85, 0.25, 0.30)      # zone de la tête où aucun texte ne va (avec de l'air au-dessus du crâne)
TOLERANCE = 0.04         # le cadre peut rogner 4 % de la hauteur du visage (une mèche)
OPAQUE = 0.35            # un texte encore presque transparent (début ou fin de fondu) ne compte pas
CACHE = 0.55             # image cachée à plus de 55 % (carte de fin, fondu au noir) : rien à contrôler
VERSION = 1              # à monter quand la détection change : les analyses gardées en cache sont refaites
HORS = ', hors charte : sa place dans la charte est prise dans ce plan'


# ------------------------------------------------------------------ courbes, comme moteur/src/outils.js
def _c(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def _P(f, a, d):
    return _c((f - a) / max(1e-6, d))


def _lerp(a, b, t):
    return a + (b - a) * t


def _eOut(t):
    return 1 - (1 - _c(t)) ** 3


def _eOut5(t):
    return 1 - (1 - _c(t)) ** 5


def _eIn(t):
    return _c(t) ** 3


def _eIO(t):
    t = _c(t)
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def _eBack(t):
    t = _c(t)
    return 1 + 2.9 * (t - 1) ** 3 + 1.9 * (t - 1) ** 2


# ------------------------------------------------------------------ rectangles (x0, y0, x1, y1)
def _inter(a, b):
    r = (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))
    return r if r[2] > r[0] and r[3] > r[1] else None


def _aire(r):
    return (r[2] - r[0]) * (r[3] - r[1]) if r else 0.0


def _touche(a, b, jeu=2.0):
    i = _inter(a, b)
    return bool(i) and i[2] - i[0] > jeu and i[3] - i[1] > jeu


def _echelle(b, s, cx, cy):
    return (cx + (b[0] - cx) * s, cy + (b[1] - cy) * s, cx + (b[2] - cx) * s, cy + (b[3] - cy) * s)


def _decale(b, dx, dy):
    return (b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy)


def _tourne(b, deg, cx, cy):
    if not deg:
        return b
    a = math.radians(deg); co, si = math.cos(a), math.sin(a)
    pts = [(cx + (x - cx) * co - (y - cy) * si, cy + (x - cx) * si + (y - cy) * co) for x in (b[0], b[2]) for y in (b[1], b[3])]
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def _union(bs):
    bs = [b for b in bs if b]
    return (min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs)) if bs else None


# ------------------------------------------------------------------ chemin de l'image du plan jusqu'à l'écran
def etat_plan(p, k, W, H):
    """Ce qui déplace l'image du plan à son image k, comme etatPlan (moteur/src/Plan.jsx).
    → (échelle, décalage x, décalage y, amplitude des secousses en px, transition qui fait filer l'image, luminosité, facteurs)."""
    n = max(1, p['t1'] - p['t0'])
    sc, tx, ty, sec, lum = 1.0, 0.0, 0.0, 0.0, 1.0
    fac = []                                   # (nom de l'effet, facteur d'échelle, effet) : pour proposer la bonne correction
    for e in p.get('effets') or []:
        t = e.get('t')
        if t == 'kb':
            u = k / n
            f = _lerp(e.get('a', 1), e.get('b', 1.08), u)
            sc *= f; tx += (e.get('dx') or 0) * u; ty += (e.get('dy') or 0) * u
            fac.append(('kb', f, e))
        elif t == 'zr':
            f = _lerp(e.get('a', 1), e.get('b', 1), _eIO(_P(k, e.get('k0', 0), e.get('k1', n) - e.get('k0', 0))))
            sc *= f; fac.append(('zr', f, e))
        elif t == 'punch' and k >= e.get('at', 0):
            f = 1 + e.get('a', 0.08) * (1 - _P(k, e.get('at', 0), e.get('d', 8))) ** 2.2
            sc *= f; fac.append(('punch', f, e))
        elif t == 'shake' and e.get('at', 0) <= k < e.get('at', 0) + e.get('d', 6):
            sec += e.get('a', 10) * (1 - _P(k, e.get('at', 0), e.get('d', 6))) ** 1.4
        elif t == 'rewind':
            sec += 6
    file = False
    ti, to = p.get('entree'), p.get('sortie')
    if ti and TD.get(ti, (0, 0))[1] and k < TD[ti][1]:
        file |= ti in FILENT
        if ti == 'noir':
            lum *= 1 - (1 - k / TD[ti][1]) ** 2
    if to and TD.get(to, (0, 0))[0] and k >= n - TD[to][0]:
        file |= to in FILENT
        if to == 'noir':
            lum *= 1 - ((k - (n - TD[to][0]) + 1) / TD[to][0]) ** 2
    return sc, tx, ty, sec, file, lum, fac


def geo_cadre(cad, k, W, H):
    """Géométrie du « cadre » (tirage photo penché) à l'image k du plan, comme geoCadre (moteur/src/Plan.jsx)."""
    u = _eOut(_P(k, cad['de'], cad['entree']))
    bw, bh = _lerp(W, cad['l'], u), _lerp(H, cad['h'], u)
    return dict(u=u, bw=bw, bh=bh, cx=_lerp(W / 2, cad['x'], u), cy=_lerp(H / 2, cad['y'] - (cad['bas'] - cad['bord']) / 2, u),
                s=max(bw / W, bh / H), rot=cad['angle'] * u)


def _vers_cadre(b, g, W, H):
    """Rectangle de l'image du plan → rectangle à l'écran quand le plan est dans un cadre (réduit, recentré, puis penché : boîte englobante)."""
    x0, y0, x1, y1 = b
    r = (g['cx'] + (x0 - W / 2) * g['s'], g['cy'] + (y0 - H / 2) * g['s'], g['cx'] + (x1 - W / 2) * g['s'], g['cy'] + (y1 - H / 2) * g['s'])
    return _tourne(r, g['rot'], g['cx'], g['cy']) if abs(g['rot']) > 0.01 else r


def accent(accents, F_):
    """Coups sur la musique à l'image F_ (accentA, moteur/src/Moteur.jsx) → (échelle, amplitude de secousse)."""
    sc, sec = 1.0, 0.0
    for e in accents or []:
        if e['at'] <= F_ < e['at'] + e['d']:
            q = (1 - (F_ - e['at']) / e['d']) ** 2
            if e.get('z'):
                sc *= 1 + e['z'] * q
            if e.get('sh'):
                sec += e['sh'] * q
    return sc, sec


def _ecran(b, sc, tx, ty, W, H):
    """Rectangle de l'image du plan → rectangle à l'écran (échelle autour du centre, puis décalage)."""
    return _decale(_echelle(b, sc, W / 2, H / 2), tx, ty)


def _bande(c, F_, H):
    """Hauteur des bandes du cinéma à l'image F_ (Bandes, moteur/src/calques.jsx)."""
    g = max(1, c.get('glisse', 12) if c.get('glisse') is not None else 12)
    sortie = 1 if c.get('sortie') == 'coupe' else 1 - _eIn(_P(F_, c['a'] - g, g))
    if c.get('depuis_noir'):
        return round(_lerp(H / 2 + 2, c['hauteur'], _eIO(_P(F_ - c['de'], 0, g))) * sortie)
    q = _eOut(_P(F_ - c['de'], 0, g)) if c.get('sortie') == 'coupe' else min(_eOut(_P(F_ - c['de'], 0, g)), sortie)
    return round(c['hauteur'] * q)


def _fin(c, F_):
    d = c.get('fondu') or (24 if c.get('anim') == 'cinema' else 5)
    return 1.0 if c.get('sortie') == 'coupe' else 1 - _eIn(_P(F_, c['a'] - d, d))


# ------------------------------------------------------------------ place des textes, image par image (comme moteur/src/calques.jsx)
_largeurs = {}


def _larg(texte, spec, taille):
    cle = (texte, spec.get('famille'), spec.get('poids'), spec.get('style'), spec.get('espacement'), spec.get('casse'), round(taille, 2))
    if cle not in _largeurs:
        _largeurs[cle] = F.largeur_texte(texte, spec, taille)
    return _largeurs[cle]


def _spec(c, theme, defaut):
    s = dict(theme.get(c.get('police') or defaut) or theme[defaut])
    if 'espacement' in c:
        s['espacement'] = c['espacement']
    return s


def _gauche(x, w, align):
    return x if align == 'gauche' else x - w if align == 'droite' else x - w / 2


def _formate(v, fmt):
    if fmt == 'temps':
        s = max(0, int(round(v)))
        return f'{s // 60:02d}:{s % 60:02d}'
    if fmt == 'decimal1':
        return f'{v:.1f}'.replace('.', ',')
    return f'{int(round(v)):,}'.replace(',', ' ')


def _opaque_image(c, public):
    """Partie non transparente d'une image posée (fractions de l'image) : un produit détouré ne compte que là où il est."""
    try:
        from PIL import Image
        for f in ([Path(public) / 'images' / c['fichier']] if public and c.get('fichier') else []) + ([Path(c['_fichier'])] if c.get('_fichier') else []):
            if f.exists():
                im = Image.open(f)
                if im.mode in ('RGBA', 'LA', 'P'):
                    a = im.convert('RGBA').getchannel('A').point(lambda v: 255 if v > 128 else 0)
                    b = a.getbbox()
                    if b:
                        return (b[0] / im.width, b[1] / im.height, b[2] / im.width, b[3] / im.height)
                return (0, 0, 1, 1)
    except Exception:
        pass
    return (0, 0, 1, 1)


def statique(c, cal, public=None):
    """Tout ce qui ne change pas d'une image à l'autre pour un calque (largeurs mesurées avec la vraie police)."""
    t, th, W = c['t'], cal['theme'], cal['l']
    if t == 'titre':
        spec = _spec(c, th, 'titre')
        inter, fond = c.get('interligne', 0.95), bool(c.get('fond'))
        lignes, y = [], c['y']
        for li in c['lignes']:
            ta = li['taille']
            w = _larg(li['texte'], spec, ta) + (0.4 * ta if fond else 0)
            h = (inter + (0.16 if fond else 0)) * ta
            lignes.append(dict(w=w, h=h, y=y, n=len(li['texte']), taille=ta))
            y += h
        lc = max(l_['w'] for l_ in lignes)
        x0 = _gauche(c['x'], lc, c.get('align', 'centre'))
        for l_ in lignes:
            g = _gauche(c['x'], l_['w'], c.get('align', 'centre'))
            l_['b'] = (g, l_['y'], g + l_['w'], l_['y'] + l_['h'])
            l_['centre'] = (x0 + lc / 2, l_['y'] + l_['h'] / 2)
        return dict(lignes=lignes, centre=(x0 + lc / 2, (c['y'] + y) / 2), repos=_union([l_['b'] for l_ in lignes]))
    if t == 'mots':
        spec = _spec(c, th, 'titre')
        mots = []
        for m in c['mots']:
            w = _larg(m['m'], spec, m['taille'])
            x0 = _gauche(c['x'], w, c.get('align', 'centre'))
            mots.append(dict(de=m['de'], a=m['a'], b=(x0, c['y'], x0 + w, c['y'] + m['taille'])))
        return dict(mots=mots, repos=_union([m['b'] for m in mots]))
    if t == 'sous-titres':
        spec = _spec(c, th, 'texte')
        ta, pastille = c['taille'], c.get('style') == 'pastille'
        groupes = []
        for g in c['groupes']:
            bs = []
            for j, ligne in enumerate(g['lignes']):
                w = sum(_larg(m['m'], spec, ta) + 0.2 * ta + (0.28 * ta if pastille else 0) for m in ligne)
                bs.append((W / 2 - w / 2 - 0.07 * ta, c['y'] + j * 1.18 * ta - 0.07 * ta, W / 2 + w / 2 + 0.07 * ta, c['y'] + (j + 1) * 1.18 * ta + 0.07 * ta))
            groupes.append(dict(de=g['de'], a=g['a'], bs=bs))
        return dict(groupes=groupes, repos=_union([b for g in groupes for b in g['bs']]))
    if t == 'etiquette':
        spec = _spec(c, th, 'mono')
        ta = c['taille']
        w = _larg(c['texte'], spec, ta)
        pad = c.get('fond') != 'aucun'
        lc, hc = w + (1.2 * ta if pad else 0), 1.2 * ta + (0.64 * ta if pad else 0)
        x0 = _gauche(c['x'], lc, c.get('align', 'centre'))
        b = (x0, c['y'], x0 + lc, c['y'] + hc)
        return dict(b=b, repos=b)
    if t == 'compteur':
        spec = _spec(c, th, 'titre')
        ta, chasse = c['taille'], c.get('chasse') or 0.5
        txt = (c.get('prefixe') or '') + max((_formate(v, c.get('format')) for v in (c.get('valeur', 0), c.get('depuis') or 0)), key=len) + (c.get('suffixe') or '')
        w = sum(chasse * ta if ch.isdigit() else _larg(ch, spec, ta) for ch in txt)
        x0 = _gauche(c['x'], w, c.get('align', 'centre'))
        b = (x0, c['y'], x0 + w, c['y'] + ta)
        return dict(b=b, repos=b)
    if t == 'image':
        fx0, fy0, fx1, fy1 = _opaque_image(c, public)
        x0, y0 = c['x'] - c['l'] / 2, c['y'] - c['h'] / 2
        b = (x0 + fx0 * c['l'], y0 + fy0 * c['h'], x0 + fx1 * c['l'], y0 + fy1 * c['h'])
        return dict(b=b, centre=(c['x'], c['y']), repos=b)
    if t == 'signature':
        st, sp = _spec({}, th, 'titre'), _spec({}, th, 'texte')
        wn = _larg(c['nom'], st, c['taille_nom'])
        yl = c['y_nom'] + c['taille_nom'] * 1.16 + 34
        lignes = [li for li in str(c.get('ligne') or '').split('\n') if li]
        wl = max((_larg(li, sp, c['taille_ligne']) for li in lignes), default=0)
        b_nom = (W / 2 - wn / 2, c['y_nom'], W / 2 + wn / 2, c['y_nom'] + c['taille_nom'])
        b_ligne = (W / 2 - wl / 2, yl, W / 2 + wl / 2, yl + len(lignes) * 1.25 * c['taille_ligne']) if lignes else None
        b_logo = (W / 2 - c['logo_l'] / 2, c['y_logo'], W / 2 + c['logo_l'] / 2, c['y_logo'] + c['logo_h']) if c.get('logo') else None
        return dict(nom=b_nom, ligne=b_ligne, logo=b_logo, repos=_union([b_nom, b_ligne, b_logo]))
    return None


def boites(c, s, F_):
    """Rectangles du calque à l'image F_ (animation d'entrée et fondu de sortie compris) → [(rectangle, opacité)]."""
    if s is None or not (c['de'] <= F_ < c['a']):
        return []
    t, k = c['t'], F_ - c['de']
    if t == 'titre':
        anim, retard, out = c.get('anim') or 'pop', 0.0, []
        fin = _fin(c, F_)
        for l_ in s['lignes']:
            d0 = retard
            retard += l_['n'] * 0.7 + 2 if anim == 'lettres' else l_['n'] / 2.4 if anim in ('machine', 'decode') else 3
            b, op = l_['b'], 1.0
            if anim == 'pop':
                b = _echelle(b, _lerp(1.35, 1, _eBack(_P(k, d0, 7))), *l_['centre']); op = _c((k - d0) / 2)
            elif anim == 'glisse':
                b = _decale(b, (1 - _eOut5(_P(k, d0, 10))) * -90, 0); op = _c((k - d0) / 3)
            elif anim == 'cinema':
                p = _eOut(_P(k, d0 * 6, c.get('duree_anim') or 36)); op = p * p
                plus = l_['n'] * 0.22 * (1 - p) * l_['taille']
                al = c.get('align', 'centre')
                b = (b[0] - (plus if al == 'droite' else plus / 2 if al == 'centre' else 0), b[1],
                     b[2] + (plus if al == 'gauche' else plus / 2 if al == 'centre' else 0), b[3])
            elif anim in ('lettres', 'machine', 'decode'):
                op = 1.0 if k >= d0 else 0.0
            out.append((_tourne(b, c.get('rot') or 0, *s['centre']), op * fin))
        return out
    if t == 'mots':
        for m in s['mots']:
            if m['de'] <= F_ < m['a']:
                km = F_ - m['de']
                b = m['b']
                return [(_echelle(b, _lerp(1.28, 1, _eOut5(_P(km, 0, 4))), (b[0] + b[2]) / 2, (b[1] + b[3]) / 2), _c((km + 1) / 2))]
        return []
    if t == 'sous-titres':
        for g in s['groupes']:
            if g['de'] <= F_ < g['a']:
                kg = F_ - g['de']
                dy = (1 - _eOut(_P(kg, 0, 3))) * 14
                return [(_decale(b, 0, dy), _c((kg + 1) / 2)) for b in g['bs']]
        return []
    if t == 'etiquette':
        op = _fin(c, F_) * (_c((k + 1) / 3) if c.get('anim') == 'aucune' else 1)
        return [(s['b'], op)]
    if t == 'compteur':
        b = s['b']
        return [(_echelle(b, _lerp(1.2, 1, _eBack(_P(k, 0, 7))), (b[0] + b[2]) / 2, (b[1] + b[3]) / 2), _fin(c, F_) * _c((k + 1) / 2))]
    if t == 'image':
        anim, sc, dy, op = c.get('anim') or 'pop', 1.0, 0.0, 1.0
        if anim == 'pop':
            sc = _lerp(0.6, 1, _eBack(_P(k, 0, 9))); op = _c((k + 1) / 2)
        elif anim == 'glisse':
            dy = (1 - _eOut5(_P(k, 0, 12))) * 140; op = _c((k + 1) / 3)
        elif anim == 'tombe':
            dy = -(1 - _eOut5(_P(k, 0, 10))) * 520; op = _c((k + 1) / 2)
        elif anim == 'fondu':
            op = _c((k + 1) / 8)
        if c.get('flotte'):
            dy += math.sin(k / 18) * (8 if c['flotte'] is True else c['flotte'])
        cx, cy = s['centre']
        b = _decale(_tourne(_echelle(s['b'], sc, cx, cy), c.get('rot') or 0, cx, cy), 0, dy)
        return [(b, op * _fin(c, F_))]
    if t == 'signature':
        fin = _fin(c, F_)
        out = [(_decale(s['nom'], 0, (1 - _eOut5(_P(k, 6, 10))) * 40), fin * _c((k - 5) / 3))]
        if s['ligne']:
            out.append((s['ligne'], fin * _eOut(_P(k, 12, 8))))
        if s['logo']:
            cx, cy = (s['logo'][0] + s['logo'][2]) / 2, (s['logo'][1] + s['logo'][3]) / 2
            out.append((_echelle(s['logo'], _lerp(0.7, 1, _eBack(_P(k, 2, 9))), cx, cy), fin * _c(k / 3)))
        return out
    return []


def _cache_image(cal, F_):
    """Part de l'image cachée à l'image F_ (carte de fin, fondu final) : au-delà de CACHE, les têtes ne sont pas contrôlées."""
    v = 0.0
    if cal.get('fondu_fin') and F_ >= cal['n'] - cal['fondu_fin']:
        v = max(v, ((F_ - (cal['n'] - cal['fondu_fin']) + 1) / cal['fondu_fin']) ** 2)
    for c in cal['calques']:
        if c['t'] == 'signature' and c['de'] <= F_ < c['a']:
            v = max(v, (c.get('fond_force') if c.get('fond_force') is not None else 0.86) * _c((F_ - c['de'] + 1) / 8) * _fin(c, F_))
    return v


# ------------------------------------------------------------------ têtes vues dans les plans
def _indices(p, ips):
    """Images de la vidéo finale analysées dans le plan (une sur PAS, la dernière aussi) → [(k, indice de l'image préparée)]."""
    n = p['t1'] - p['t0']
    ks = sorted(set(range(0, n, PAS)) | {n - 1})
    if p.get('photo') or p.get('n', 1) <= 1:
        return [(k, 0) for k in ks]
    ts = F.temps_sources(p, ips)
    return [(k, int(_c(round((ts[k] - p['debut']) * p['ips']), 0, p['n'] - 1))) for k in ks]


def _detecter(chemins):
    """Visages de chaque image → {chemin: [[x, y, l, h, confiance], …]} en fractions de l'image."""
    import os
    os.environ.setdefault('OPENCV_LOG_LEVEL', 'ERROR')
    import cv2
    try:
        cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
    except AttributeError:
        pass
    RES.opencv(cv2, RES.taches(3))
    from cadrage import _modele
    modele, det, out = _modele(), None, {}
    for ch in chemins:
        im = cv2.imread(str(ch), cv2.IMREAD_REDUCED_COLOR_2)       # lue à demi-taille : 4 fois plus rapide, assez pour un visage de 30 px
        if im is None:
            out[str(ch)] = []
            continue
        h, w = im.shape[:2]
        if max(w, h) > 960:
            r = 960 / max(w, h)
            im = cv2.resize(im, (round(w * r), round(h * r)), interpolation=cv2.INTER_AREA)
            h, w = im.shape[:2]
        m = round(0.1 * max(w, h))                                   # bord noir : une tête à moitié sortie de l'image est encore vue
        im = cv2.copyMakeBorder(im, m, m, m, m, cv2.BORDER_CONSTANT, value=0)
        if det is None:
            det = cv2.FaceDetectorYN.create(modele, '', (w + 2 * m, h + 2 * m), SEUIL)
        else:
            det.setInputSize((w + 2 * m, h + 2 * m))
        _, faces = det.detect(im)
        out[str(ch)] = [[round((float(f[0]) - m) / w, 5), round((float(f[1]) - m) / h, 5), round(float(f[2]) / w, 5), round(float(f[3]) / h, 5),
                         round(float(f[14]), 3)] for f in (faces if faces is not None else [])]
    return out


def _iou(a, b):
    i = _aire(_inter((a[0], a[1], a[0] + a[2], a[1] + a[3]), (b[0], b[1], b[0] + b[2], b[1] + b[3])))
    return i / max(1e-9, a[2] * a[3] + b[2] * b[3] - i)


def tetes_du_plan(p, cal, travail, journal=None):
    """Têtes du plan (et de sa deuxième image en écran partagé), avec cache : {'k': [...], 'faces': [[(x, y, l, h) en px du plan], …]}."""
    W, H, ips = cal['l'], cal['h'], cal['ips']
    dossier = Path(travail) / 'public' / 'plans' / p['id']
    meta = dossier / 'meta.json'
    if not meta.exists():
        return None
    cle = f'{json.loads(meta.read_text()).get("cle")}|{VERSION}|{PAS}|{SEUIL}'
    cache = Path(travail) / 'tetes' / f'{p["id"]}.json'
    ech = _indices(p, ips)
    vus = {}
    if cache.exists():
        try:
            m = json.loads(cache.read_text())
            if m.get('cle') == cle:
                vus = {int(i): v for i, v in m['faces'].items()}
        except (ValueError, KeyError):
            vus = {}
    manque = sorted({i for _, i in ech} - set(vus))
    if manque:
        trouve = _detecter([dossier / f'{i:04d}.jpg' for i in manque])
        for i in manque:
            vus[i] = trouve[str(dossier / f'{i:04d}.jpg')]
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(dict(cle=cle, faces={str(i): v for i, v in sorted(vus.items())})))
    mini = PETIT * min(W, H)
    brut = []
    for k, i in ech:
        fs = [(f[0] * W, f[1] * H, f[2] * W, f[3] * H) for f in vus.get(i, [])]
        grand = max((f[2] for f in fs), default=0)
        brut.append([f for f in fs if f[2] >= mini and f[2] >= RELATIF * grand])
    # une tête vue sur une seule analyse, ni avant ni après, est une fausse détection (reflet, motif, affiche qui passe)
    video = not p.get('photo') and len({i for _, i in ech}) >= 3
    faces = []
    for s, fs in enumerate(brut):
        if video:
            voisins = [g for v in (s - 1, s + 1) if 0 <= v < len(brut) for g in brut[v]]
            fs = [f for f in fs if any(_iou(f, g) >= 0.2 for g in voisins)]
        faces.append(fs)
    return dict(k=[k for k, _ in ech], faces=faces)


def detecter(cal, travail, journal=None):
    """Têtes de tous les plans (en parallèle, avec cache) → {id du plan (ou id-2 pour l'écran partagé): têtes}."""
    from concurrent.futures import ThreadPoolExecutor
    a_faire = [p for p in cal['plans'] if not p.get('_sans_garde')]
    a_faire += [p['double'] for p in a_faire if p.get('double') and p.get('double_mode') == 'partage']
    with ThreadPoolExecutor(RES.taches(3)) as ex:       # sur le Mac : autant que de cœurs du mode discret
        res = list(ex.map(lambda p: (p['id'], tetes_du_plan(p, cal, travail)), a_faire))
    return {i: t for i, t in res if t}


def _faces_a(t, k):
    """Têtes de l'analyse la plus proche de l'image k du plan."""
    if not t or not t['k']:
        return []
    j = bisect.bisect_left(t['k'], k)
    if j == len(t['k']) or (j > 0 and k - t['k'][j - 1] <= t['k'][j] - k):
        j -= 1
    return t['faces'][j]


# ------------------------------------------------------------------ l'analyse, image par image
def _scene(cal, tetes, F_, p, statiques):
    """Tout ce que voit l'écran à l'image F_ : têtes (entière, zone sans texte, partie visible) et rectangles des textes."""
    W, H = cal['l'], cal['h']
    k = F_ - p['t0']
    sc, tx, ty, sec, file, lum, fac = etat_plan(p, k, W, H)
    asc = 1.0
    if not p.get('sans_accent'):
        asc, asec = accent(cal.get('accents'), F_)
        sc *= asc; sec += asec
    marge = 1.8 * sec                                              # secousse : déplacement et petite rotation, au pire
    V = _inter((0, 0, W, H), _ecran((0, 0, W, H), sc, tx, ty, W, H))
    bandes = 0
    for c in cal['calques']:
        if c['t'] == 'bandes' and c['de'] <= F_ < c['a']:
            bandes = max(bandes, _bande(c, F_, H))
    if V and bandes:
        V = _inter(V, (0, bandes, W, H - bandes))
    cache = max(_cache_image(cal, F_), 1 - lum)
    textes = []
    for j, c in enumerate(cal['calques']):
        for b, op in boites(c, statiques[j], F_):
            if c.get('derriere'):                                  # texte derrière le sujet : il bouge avec l'image du plan
                b = _ecran(b, sc, tx, ty, W, H)
            textes.append((j, b, op))
    tt = []
    verif = not file and cache <= CACHE and V is not None and not p.get('_sans_garde')
    if verif:
        images = [(p['id'], 0.0, (0, 0, W, H))]
        if p.get('double') and p.get('double_mode') == 'partage':      # écran partagé : le milieu de chaque image, côte à côte
            o = _eOut(_P(k, 0, 8))
            images = [(p['id'], -W / 4 * o, (0, 0, W * (1 - 0.5 * o), H)), (p['double']['id'], W / 4 * o, (W * 0.5 * o, 0, W, H))]
        for pid, dx, clip in images:
            Vf = _inter(V, _ecran(clip, sc, tx, ty, W, H))
            if not Vf:
                continue
            for (x, y, w, h) in _faces_a(tetes.get(pid), k):
                Cp = (x - TETE[0] * w + dx, y - TETE[1] * h, x + (1 + TETE[2]) * w + dx, y + (1 + TETE[3]) * h)
                Zp = (x - ZONE[0] * w + dx, y - ZONE[1] * h, x + (1 + ZONE[2]) * w + dx, y + (1 + ZONE[3]) * h)
                C_, Z_, V_, hf = _ecran(Cp, sc, tx, ty, W, H), _ecran(Zp, sc, tx, ty, W, H), Vf, h * sc
                if p.get('cadre'):                                 # plan rangé dans un cadre : tout est réduit dans la photo
                    g = geo_cadre(p['cadre'], k, W, H)
                    C_, Z_, hf = _vers_cadre(C_, g, W, H), _vers_cadre(Z_, g, W, H), hf * g['s']
                    V_ = _inter((g['cx'] - g['bw'] / 2, g['cy'] - g['bh'] / 2, g['cx'] + g['bw'] / 2, g['cy'] + g['bh'] / 2), _vers_cadre(Vf, g, W, H))
                    if not V_:
                        continue
                tt.append(dict(C=C_, Z=Z_, V=V_, hf=hf, Cp=Cp, dx=dx, pid=pid, face=(x, y, w, h)))
    return dict(F=F_, plan=p, k=k, sc=sc, tx=tx, ty=ty, marge=marge, fac=fac, asc=asc, bandes=bandes, V=V, verif=verif, tetes=tt, textes=textes)


def _depasse(C, V, marge=0.0):
    """De combien la tête sort de la partie visible, et par quel bord."""
    d = {'gauche': V[0] - C[0], 'haut': V[1] - C[1], 'droite': C[2] - V[2], 'bas': C[3] - V[3]}
    bord = max(d, key=d.get)
    return max(0.0, d[bord] + marge), bord


def analyser(cal, tetes, public=None):
    """→ (problèmes, scènes). Un problème : dict(type='coupee'|'couverte'|'chevauche', de, a, pire, ...), groupé par moments."""
    N = cal['n']
    statiques = [statique(c, cal, public) for c in cal['calques']]
    plans = sorted(cal['plans'], key=lambda q: q['t0'])
    scenes, ev, ip = [], [], 0
    for F_ in range(N):
        while ip + 1 < len(plans) and F_ >= plans[ip]['t1']:
            ip += 1
        sc_ = _scene(cal, tetes, F_, plans[ip], statiques)
        scenes.append(sc_)
        vis = [(j, b, op) for j, b, op in sc_['textes'] if op >= OPAQUE]
        txt = [x for x in vis if cal['calques'][x[0]]['t'] in TEXTES]
        for a in range(len(txt)):
            for b in range(a + 1, len(txt)):
                (ja, ba, _), (jb, bb, _) = txt[a], txt[b]
                if ja != jb and _touche(ba, bb):
                    ev.append(('chevauche', (min(ja, jb), max(ja, jb)), F_, _aire(_inter(ba, bb)) * min(txt[a][2], txt[b][2]), dict(boites=[ba, bb])))
        for t in sc_['tetes']:
            part = _aire(_inter(t['C'], t['V'])) / max(1e-9, _aire(t['C']))
            dep, bord = _depasse(t['C'], t['V'], sc_['marge'])
            if part > 0.02 and dep > TOLERANCE * t['hf']:
                ev.append(('coupee', (sc_['plan']['id'], bord), F_, dep, dict(t=t)))
            Zc = _inter(t['Z'], t['V'])
            if not Zc:
                continue
            for j, b, op in vis:
                c = cal['calques'][j]
                if c['t'] in COUVRANTS and not c.get('derriere') and _touche(b, Zc):
                    ev.append(('couverte', (sc_['plan']['id'], j), F_, _aire(_inter(b, Zc)) * op, dict(t=t, boites=[b])))
    # images voisines du même problème : un seul moment
    moments = []
    ouverts = {}
    for typ, cle, F_, m, det in ev:
        o = ouverts.get((typ, cle))
        if o and F_ - o['a'] <= 3:
            o['a'] = F_
            if m > o['mesure']:
                o.update(pire=F_, mesure=m, det=det)
        else:
            o = dict(type=typ, cle=cle, de=F_, a=F_, pire=F_, mesure=m, det=det)
            ouverts[(typ, cle)] = o
            moments.append(o)
    for o in moments:
        o['a'] += 1
    return sorted(moments, key=lambda o: (o['de'], o['type'])), scenes


# ------------------------------------------------------------------ corrections proposées
def _limites(cal):
    z = cal['zones_instagram']
    return z['haut'], (z['bas_conseille'] if z['reel'] else z['bas'])


def hauteur_libre(j, cal, scenes, public=None, charte=None):
    """Décalage vertical le plus court qui libère le calque j de toute tête et de tout autre texte pendant toute sa durée.
    Avec « charte » (places et hauteurs exactes de la charte) : seulement dans ses places, au plus près de ses hauteurs."""
    c = cal['calques'][j]
    if c['t'] not in MOBILES or c.get('derriere'):
        return None
    s = statique(c, cal, public)
    haut, bas = _limites(cal)
    repos = s['repos'] if s else None
    if not repos:
        return None
    vies = []
    for sc_ in scenes[max(0, c['de']):min(len(scenes), c['a'])]:          # toutes les images : un « pop » ne dure que 2 ou 3 images
        moi = [b for jj, b, op in sc_['textes'] if jj == j and op >= OPAQUE]
        if not moi:
            continue
        obst = [b for jj, b, op in sc_['textes'] if jj != j and op >= OPAQUE and cal['calques'][jj]['t'] in TEXTES]
        if sc_['verif']:
            obst += [z for t in sc_['tetes'] for z in [_inter(t['Z'], t['V'])] if z]
        vies.append((moi, obst))
    pas = max(4, round(10 * cal['h'] / 1920))
    essais = sorted(range(-cal['h'], cal['h'] + 1, pas), key=lambda d: (abs(d), d))
    plages = charte['places'] if charte else None
    if charte:
        ancres = charte.get('ancres') or []
        essais = sorted(set(essais) | {round(a - c['y']) for a in ancres}, key=lambda d: (min((abs(c['y'] + d - a) for a in ancres), default=0), abs(d), d))
    for dy in essais:
        if repos[1] + dy < haut or repos[3] + dy > bas:
            continue
        if plages and not any(a <= c['y'] + dy <= b for a, b in plages):
            continue
        if all(not _touche(_decale(b, 0, dy), o) for moi, obst in vies for b in moi for o in obst):
            return dy
    return None


def _propose_y(j, cal, scenes, public):
    """→ ('"y": …', hors charte) ; d'abord une place de la charte si la fiche en a une, sinon la hauteur libre la plus proche."""
    c = cal['calques'][j]
    ch = c.get('_charte')
    dy = hauteur_libre(j, cal, scenes, public, ch) if ch else None
    hors = False
    if dy is None:
        dy = hauteur_libre(j, cal, scenes, public)
        hors = bool(ch)
    if dy is None:
        return None, False
    return f'"y": {round(c["y"] + dy)}', hors


def _conseil_coupe(o, cal):
    """Pourquoi la tête est coupée à cet instant, et quoi changer dans la fiche."""
    W, H = cal['l'], cal['h']
    t, p = o['det']['t'], o['det']['scene']['plan']
    sc_ = o['det']['scene']
    tol = TOLERANCE * t['hf'] / max(1e-9, sc_['sc'])
    # la plus grande échelle où la tête tient entière (avec la même secousse et les mêmes bandes)
    tient = None
    s = sc_['sc']
    while s >= 0.999:
        V = _inter((0, 0, W, H), _ecran((0, 0, W, H), s, sc_['tx'], sc_['ty'], W, H))
        if V and sc_['bandes']:
            V = _inter(V, (0, sc_['bandes'], W, H - sc_['bandes']))
        if V:
            C = _ecran((t['Cp'][0], t['Cp'][1], t['Cp'][2], t['Cp'][3]), s, sc_['tx'], sc_['ty'], W, H)
            if _depasse(C, V, sc_['marge'])[0] <= tol * s:
                tient = s
                break
        s -= 0.005
    if tient is not None and sc_['sc'] > tient + 1e-3:
        effets = [(nom, f, e) for nom, f, e in sc_['fac'] if f > 1.001]
        if sc_['asc'] > 1.001:
            effets.append(('accents', sc_['asc'], None))
        detail = ', '.join(f'{NOMS_EFFET[nom]} ×{f:.2f}' for nom, f, _ in effets)
        texte = f'zoom ×{sc_["sc"]:.2f} à cet instant ({detail}) : la tête tient entière jusqu\'à ×{tient:.2f}.'
        if effets:
            nom, f, e = max(effets, key=lambda x: x[1])
            reste = sc_['sc'] / f
            voulu = tient / reste
            if nom == 'punch':
                pk = (1 - _P(sc_['k'], e.get('at', 0), e.get('d', 8))) ** 2.2
                texte += f' Je propose : punch « a » {e.get("a", 0.08):g} → {max(0.0, math.floor((voulu - 1) / max(pk, 1e-6) * 100) / 100):g}.'
            elif nom == 'kb':
                u = sc_['k'] / max(1, p['t1'] - p['t0'])
                a0, b0 = e.get('a', 1), e.get('b', 1.08)
                if b0 >= a0 and u > 0:
                    texte += f' Je propose : Ken Burns « b » {b0:g} → {math.floor((a0 + (voulu - a0) / u) * 100) / 100:g}.'
                else:
                    texte += f' Je propose : Ken Burns « a » {a0:g} → {math.floor(voulu * 100) / 100:g}.'
            elif nom == 'zr':
                texte += f' Je propose : rampe de zoom moins forte (au plus ×{math.floor(voulu * 100) / 100:g}).'
            else:
                texte += f' Je propose : "sans_accent": true sur le plan {p["id"]}, ou « zoom » des accents plus petit.'
        return texte
    return _conseil_cadrage(o, cal, t, sc_)


def _arrondi(v, vers_bas=True):
    return (math.floor(v * 100) if vers_bas else math.ceil(v * 100)) / 100


def _conseil_cadrage(o, cal, t, sc_):
    """La tête est déjà coupée dans l'image du plan (bandes, écran partagé, zoom, cx, cy, ou la prise elle-même) :
    quoi changer dans la fiche, chiffré quand c'est possible."""
    from preparer import cadre
    W, H, ips = cal['l'], cal['h'], cal['ips']
    p = sc_['plan']
    q = p['double'] if p.get('double') and t['pid'] == p['double']['id'] else p
    ou = ' dans « double »' if q is not p else ''
    x, y, w, h = t['face']
    C0 = (x - TETE[0] * w, y - TETE[1] * h, x + (1 + TETE[2]) * w, y + (1 + TETE[3]) * h)
    vers_image = lambda X, Y: ((X - W / 2 - sc_['tx']) / sc_['sc'] + W / 2 - t['dx'], (Y - H / 2 - sc_['ty']) / sc_['sc'] + H / 2)
    V = t['V']
    Vi = (*vers_image(V[0], V[1]), *vers_image(V[2], V[3]))
    jeu = TOLERANCE * h - sc_['marge'] / sc_['sc']                  # ce que le cadre peut rogner, secousse déduite
    m = 0.03 * h                                                    # un peu de marge dans la correction proposée
    dep = dict(haut=Vi[1] - jeu - C0[1], bas=C0[3] - Vi[3] - jeu, gauche=Vi[0] - jeu - C0[0], droite=C0[2] - Vi[2] - jeu)
    trop_grand = (dep['haut'] > 0 and dep['bas'] > 0) or (dep['gauche'] > 0 and dep['droite'] > 0)
    props = []
    # bandes du cinéma : la plus grande hauteur de bande qui laisse la tête entière
    if sc_['bandes'] and o['cle'][1] in ('haut', 'bas'):
        Cs = t['C']
        hmax = min(Cs[1] + TOLERANCE * t['hf'], H - Cs[3] + TOLERANCE * t['hf']) - 2      # 2 px de marge
        ratio = W / max(1.0, H - 2 * max(0.0, hmax))
        if hmax > 4 and ratio > W / H + 0.02:
            props.append(f'« ratio » des bandes {_arrondi(ratio, False):g} (au lieu de {W / max(1.0, H - 2 * sc_["bandes"]):.2f})')
        else:
            props.append('pas de bandes sur ce plan (« de » et « a » du calque bandes)')
    fixe = q.get('photo') or q.get('_cadrage') != 'visage'
    z = q.get('_zoom', 1)
    son = q.get('_sonde') or {}
    if fixe and son.get('l') and son.get('h'):
        # cadre fixe (photo, ou vidéo sans « cadrage: visage ») : le plus petit changement de cx, cy, zoom qui garde la tête entière
        ls, hs = son['l'], son['h']
        cx0, cy0 = q.get('_cx', 0.5), q.get('_cy', 0.5)
        xc, yc, cw, ch = cadre(z, cx0, cy0, ls, hs, W / H)
        tete_src = (xc + C0[0] * cw / W, yc + C0[1] * ch / H, xc + C0[2] * cw / W, yc + C0[3] * ch / H)
        r_ = 0.06 * h - jeu                                          # la tête un peu à l'intérieur, pas au ras du bord
        A = (Vi[0] + r_, Vi[1] + r_, Vi[2] - r_, Vi[3] - r_)
        zooms = sorted({round(z + d_ * 0.05, 2) for d_ in range(-60, 61)} | {z}, key=lambda v: (abs(v - z), v))
        for z2 in (v for v in zooms if 1 <= v <= 4):
            x2, y2, cw2, ch2 = cadre(z2, cx0, cy0, ls, hs, W / H)
            lo_x, hi_x = max(0.0, tete_src[2] - A[2] * cw2 / W), min(ls - cw2, tete_src[0] - A[0] * cw2 / W)
            lo_y, hi_y = max(0.0, tete_src[3] - A[3] * ch2 / H), min(hs - ch2, tete_src[1] - A[1] * ch2 / H)
            if lo_x <= hi_x + 0.5 and lo_y <= hi_y + 0.5:
                nx, ny = _c(x2, lo_x, max(lo_x, hi_x)), _c(y2, lo_y, max(lo_y, hi_y))
                cx2, cy2 = round((nx + cw2 / 2) / ls, 3), round((ny + ch2 / 2) / hs, 3)
                ch_ = [f'« {k} » {v:g} (au lieu de {v0:g})' for k, v, v0, seuil in (('zoom', z2, z, 0.01), ('cx', cx2, cx0, 0.005), ('cy', cy2, cy0, 0.005))
                       if abs(v - v0) >= seuil]
                if ch_:
                    props.append((', '.join(ch_[:-1]) + ' et ' + ch_[-1] if len(ch_) > 1 else ch_[0]) + ou)
                break
    elif z > 1.01:
        # le cadre suit la tête : seul un zoom plus petit la fait tenir (elle rétrécit autour de son centre)
        ax, ay = x + w / 2, y + h / 2
        r = 1.0
        for bord, (a_, lim, bout) in dict(haut=(ay, Vi[1] - jeu, C0[1]), bas=(ay, Vi[3] + jeu, C0[3]),
                                           gauche=(ax, Vi[0] - jeu, C0[0]), droite=(ax, Vi[2] + jeu, C0[2])).items():
            if dep[bord] > 0 and abs(a_ - bout) > 1:
                r = min(r, abs(a_ - lim) / (abs(a_ - bout) + m))
        if z * r >= 1:
            props.append(f'« zoom » {max(1.0, _arrondi(z * r)):g}{ou} (au lieu de {z:g})')
    video = not q.get('photo')
    partage = bool(p.get('double')) and p.get('double_mode') == 'partage'
    if video and q.get('_cadrage') != 'visage' and not partage and not (sc_['bandes'] and o['cle'][1] in ('haut', 'bas')):
        # le cadre ne peut suivre la tête que s'il a de la place pour bouger dans la vidéo (zoom, ou format différent)
        place = True
        if son.get('l') and son.get('h'):
            _, _, cw, ch = cadre(z, 0.5, 0.5, son['l'], son['h'], W / H)
            place = (son['l'] - cw > 0.15 * cw) if o['cle'][1] in ('gauche', 'droite') else (son['h'] - ch > 0.15 * ch)
        props.insert(0, '"cadrage": "visage"' + (ou if ou else '') + (' (le cadre suit la tête)' if place else ' avec « zoom » 1.3 (le cadre suit la tête, il lui faut de la place)'))
    debut = (o['de'] - p['t0']) / ips
    if video and debut >= 0.5:
        props.append(f'finir le plan avant ce moment (« duree » "{_arrondi(debut):g}s")')
    if not props:
        props.append('une autre prise ou un autre passage (« de ») : la tête est coupée dans la vidéo elle-même' if video else
                     'une autre photo : la tête est coupée sur la photo elle-même')
    pourquoi = ('les bandes du cinéma rognent la tête' if sc_['bandes'] and o['cle'][1] in ('haut', 'bas') else
                'écran partagé : la tête sort de sa moitié' if partage else
                'la tête est trop grande pour le cadre' if trop_grand else 'le cadre du plan coupe la tête')
    return f'{pourquoi}. Je propose : ' + ', ou '.join(props) + '.'


def _nom(j, cal):
    c = cal['calques'][j]
    n = c.get('_n', j + 1)
    t = c['t']
    extrait = ''
    if t == 'titre':
        extrait = ' / '.join(l_['texte'] for l_ in c['lignes'])
    elif t == 'mots':
        extrait = ' / '.join(m['m'] for m in c['mots'][:3])
    elif t == 'etiquette':
        extrait = c.get('texte', '')
    elif t == 'compteur':
        extrait = f'{c.get("prefixe") or ""}{c.get("valeur", "")}{c.get("suffixe") or ""}'
    elif t == 'image':
        extrait = Path(str(c.get('_fichier') or c.get('fichier') or '')).name
    elif t == 'signature':
        extrait = c.get('nom', '')
    elif t == 'sous-titres':
        extrait = f'plan {c.get("plan")}'
    extrait = extrait if len(extrait) <= 28 else extrait[:27] + '…'
    return f'calque {n} ({t}{" « " + extrait + " »" if extrait else ""})'


def _temps(f, ips):
    return f'{f / ips:.1f}'.replace('.', ',') + ' s'


def conseils(moments, scenes, cal, public=None):
    """Une ligne par problème, avec la correction proposée (au plus 12 lignes : la suite se voit après correction)."""
    ips = cal['ips']
    lignes = []
    for o in moments:
        sc_ = scenes[o['pire']]
        o['det']['scene'] = sc_
        quand = f'{_temps(o["de"], ips)} → {_temps(o["a"], ips)}'
        if o['type'] == 'coupee':
            pid, bord = o['cle']
            o['texte'] = f'{quand}, plan {pid} : tête coupée {NOMS_BORD[bord]} ; {_conseil_coupe(o, cal)}'
        elif o['type'] == 'couverte':
            pid, j = o['cle']
            prop, hors = _propose_y(j, cal, scenes, public)
            fin = f'Je propose : {prop} (libre pendant tout le texte{HORS if hors else ""}).' if prop else 'Aucune hauteur libre pendant tout ce texte : le raccourcir (« a »), réduire « taille », ou le poser sur un plan plus large.'
            o['texte'] = f'{quand}, plan {pid} : le {_nom(j, cal)} couvre la tête. {fin}'
        else:
            ja, jb = o['cle']
            ca, cb = cal['calques'][ja], cal['calques'][jb]
            bouge = jb if (cb['de'], jb) >= (ca['de'], ja) else ja
            autre = ja if bouge == jb else jb
            prop, hors = _propose_y(bouge, cal, scenes, public)
            if prop is None:
                bouge, autre = autre, bouge
                prop, hors = _propose_y(bouge, cal, scenes, public)
            fin = f'Je propose : {_nom(bouge, cal).split(" (")[0]} {prop}{" (" + HORS[2:] + ")" if hors else ""}.' if prop else 'Aucune place libre : décaler l\'un des deux dans le temps (« de », « a »).'
            o['texte'] = f'{quand} : le {_nom(ja, cal)} et le {_nom(jb, cal)} se chevauchent. {fin}'
        lignes.append(o['texte'])
    if len(lignes) > 12:
        lignes = lignes[:12] + [f'… et {len(lignes) - 12} autre(s) : corriger ceux-là d\'abord, puis relancer']
    return lignes


def controler(cal, travail, journal=None):
    """Le contrôle complet : têtes des plans (cache), puis toutes les images. → dict(ok, lignes, moments, nb_tetes, sans_garde)."""
    tetes = detecter(cal, travail, journal)
    public = Path(travail) / 'public'
    moments, scenes = analyser(cal, tetes, public)
    lignes = conseils(moments, scenes, cal, public)
    hors, notes = places_charte(moments, scenes, cal, public)
    lignes += hors
    vus = sum(1 for p in cal['plans'] if any(tetes.get(p['id'], {}).get('faces') or []))
    sans = [p['id'] for p in cal['plans'] if p.get('_sans_garde')]
    dessin = []
    for o in moments[:8]:                      # pour l'image de contrôle : la pire image de chaque problème
        sc_ = o['det']['scene']
        it = [(t['Z'], 'zone') for t in sc_['tetes']] + [(t['C'], 'tete') for t in sc_['tetes']]
        it += [(b, 'texte') for b in o['det'].get('boites', [])]
        if o['type'] == 'coupee' and sc_['V']:
            it.append((sc_['V'], 'visible'))
        dessin.append(dict(image=o['pire'], legende=f'{_temps(o["pire"], cal["ips"])} ' + {'coupee': 'tête coupée', 'couverte': 'texte sur la tête', 'chevauche': 'textes l\'un sur l\'autre'}[o['type']],
                           formes=[(list(map(float, b)), sorte) for b, sorte in it]))
    return dict(ok=not moments and not hors, lignes=lignes, nb=len(moments) + len(hors), plans_avec_tete=vus, sans_garde=sans, dessin=dessin,
                notes=notes, charte=any(c.get('_charte') for c in cal['calques']))


def places_charte(moments, scenes, cal, public=None):
    """Textes hors de leur place dans la charte (voir outils/charte.py). La garde-tête passe avant : si une tête ou un autre texte
    occupe toutes les places de la charte pendant ce texte, il reste où il est, et c'est seulement dit. → (erreurs, notes)."""
    from charte import dans, texte_places
    deja = {o['cle'][1] for o in moments if o['type'] == 'couverte'} | {j for o in moments if o['type'] == 'chevauche' for j in o['cle']}
    erreurs, notes, vus = [], [], set()
    for j, c in enumerate(cal['calques']):
        ch = c.get('_charte')
        if not ch or c.get('y') is None or j in deja or c.get('_n') in vus or dans(c['y'], ch['places']):
            continue
        vus.add(c.get('_n'))
        dy = hauteur_libre(j, cal, scenes, public, ch)
        if dy is not None:
            erreurs.append(f'{_nom(j, cal)} : hors de sa place dans la charte (y {texte_places(ch)}, comme le calque {ch["ref"]} de {ch["ou"]}). '
                           f'Je propose : "y": {round(c["y"] + dy)} (libre pendant tout le texte).')
        else:
            notes.append(f'{_nom(j, cal)} : sa place dans la charte (y {texte_places(ch)}) est prise par une tête ou un autre texte dans ce plan : '
                         f'gardé à y {c["y"]}, hors charte.')
    return erreurs, notes


def chevauchements(cal):
    """Textes l'un sur l'autre, sans les têtes (rien à préparer) : pour « verifier » avant toute extraction."""
    moments, scenes = analyser(cal, {})
    moments = [o for o in moments if o['type'] == 'chevauche']
    return conseils(moments, scenes, cal), moments


def zones_a(cal, travail, images):
    """Zones des têtes aux images demandées (pour les planches) → {image: [(zone sans texte, tête entière)]}."""
    tetes = detecter(cal, travail)
    statiques = [None] * len(cal['calques'])
    plans = sorted(cal['plans'], key=lambda q: q['t0'])
    out = {}
    for F_ in images:
        p = next((q for q in plans if q['t0'] <= F_ < q['t1']), None)
        if p is None:
            continue
        sc_ = _scene(cal, tetes, F_, p, statiques)
        out[F_] = [(t['Z'], t['C']) for t in sc_['tetes']]
    return out


def annoter(fiche, cal):
    """Numéro de chaque calque dans la fiche (les sous-titres « plan: tous » sont recopiés plan par plan) et plans sans garde."""
    parlants = [q['id'] for q in cal['plans'] if q.get('_son') and not q.get('photo')]
    nums = []
    for i, c in enumerate(fiche.get('calques') or []):
        nums += [i + 1] * (len(parlants) if c.get('t') == 'sous-titres' and c.get('plan') == 'tous' else 1)
    if len(nums) == len(cal['calques']):
        for c, n in zip(cal['calques'], nums):
            c['_n'] = n
    sans = {str(p.get('id')) for p in fiche.get('plans') or [] if p.get('garde_tete') is False}
    for q in cal['plans']:
        if q['id'] in sans:
            q['_sans_garde'] = True
    return sorted(sans)
