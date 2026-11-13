"""Charte : les textes d'une vidéo suivent ceux d'une vidéo validée (la première d'une série).

Demande de Yohann (13/11/2026), sur les « chaussure du jour » : « tu respectes pas la même charte graphique qu'on a fait à la
première vidéo », « les textes sont pas bien alignés ». La fiche nomme la fiche validée : "charte": "../01-1080/montage.json"
(chemin depuis le dossier du projet, ou le dossier de la vidéo validée). Chaque texte (titre, mots, étiquette, compteur,
sous-titres) doit ressembler à un texte du même genre de la charte :
- même thème et même format ;
- même style : police, fond, couleur, animation, alignement ;
- même taille (à 12 % près) et même bord (x à 8 px près) : c'est ce qui aligne les textes d'une vidéo à l'autre ;
- même hauteur : sur une des places de la charte (à 40 px près ; une liste de la charte peut s'allonger d'une ligne).
Style, taille et bord : [erreur] dès la lecture de la fiche. Hauteur : contrôlée avec la garde-tête, qui passe avant la charte :
si une tête ou un autre texte occupe la place prévue, le texte se pose ailleurs et c'est dit ([attention], sans refus).
"""
import json
import statistics
from pathlib import Path

import fiche as F

GENRES = ('titre', 'mots', 'etiquette', 'compteur', 'sous-titres')
NOMS = {'titre': 'titre', 'mots': 'mots qui claquent', 'etiquette': 'étiquette', 'compteur': 'compteur', 'sous-titres': 'sous-titres'}
STYLE = {        # clés de style et leur valeur quand la fiche ne les écrit pas (comme fiche.py et calques.jsx)
    'titre': {'police': 'titre', 'fond': None, 'couleur': None, 'anim': 'pop', 'align': 'centre'},
    'mots': {'police': 'titre', 'fond': None, 'couleur': None, 'align': 'centre', 'alterne': False},
    'etiquette': {'police': 'mono', 'fond': None, 'couleur': None, 'anim': 'machine', 'align': 'centre'},
    'compteur': {'police': 'titre', 'couleur': None, 'align': 'centre'},
    'sous-titres': {'police': 'texte', 'style': None, 'couleur': None, 'couleur_active': None},
}
ECART_TAILLE = 0.12      # taille à 12 % près
ECART_X = 8              # bord à 8 px près
ECART_Y = 40             # hauteur à 40 px près (sur 1920)


def _taille(c, W):
    t = c['t']
    if t == 'titre' and c.get('tailles'):
        return max(c['tailles'])
    if t == 'sous-titres':
        return c.get('taille', round(F.TAILLE_SOUS_TITRES * W / 1080))
    return c.get('taille', {'titre': 150, 'mots': 220, 'etiquette': F.TEXTE_MINI, 'compteur': 220}[t])


def _x(c, W, zones):
    if c['t'] == 'sous-titres':
        return W / 2
    align = c.get('align', 'centre')
    return c.get('x', W / 2 if align == 'centre' else (zones['marge'] if align == 'gauche' else W - zones['marge']))


def _y(c, W, zones):
    if c['t'] == 'sous-titres' and 'y' not in c:
        return round(zones['bas_conseille'] - 2 * 1.18 * _taille(c, W))
    return c.get('y')


def _style(c):
    return {k: c.get(k, d) for k, d in STYLE[c['t']].items()}


def _v(v):
    return 'aucun' if v is None else ('oui' if v is True else 'non' if v is False else f'« {v} »' if isinstance(v, str) else f'{v:g}')


def _nom(i, c):
    t = c['t']
    ex = {'titre': ' / '.join(c.get('lignes') or [str(c.get('texte', ''))]), 'mots': str(c.get('texte', '')), 'etiquette': str(c.get('texte', '')),
          'compteur': f'{c.get("prefixe", "")}{c.get("valeur", "")}{c.get("suffixe", "")}', 'sous-titres': f'plan {c.get("plan", "")}'}[t].replace('\n', ' / ')
    ex = ex if len(ex) <= 28 else ex[:27] + '…'
    return f'calque {i + 1} ({t}{" « " + ex + " »" if ex else ""})'


def lire(fiche, projet):
    """→ (fiche validée, son chemin)."""
    f = Path(fiche['charte'])
    f = f if f.is_absolute() else Path(projet) / f
    if f.is_dir():
        f = f / 'montage.json'
    return json.loads(f.read_text(encoding='utf-8')), f.resolve()


def places(ys, taille, tol):
    """Hauteurs de la charte → intervalles permis. Des hauteurs proches (moins de 2,5 tailles d'écart) forment une liste,
    qui peut s'allonger d'une ligne vers le bas."""
    ys = sorted({round(v) for v in ys if v is not None})
    groupes = []
    for v in ys:
        if groupes and v - groupes[-1][-1] <= 2.5 * taille:
            groupes[-1].append(v)
        else:
            groupes.append([v])
    out = []
    for g in groupes:
        pas = statistics.median(b - a for a, b in zip(g, g[1:])) if len(g) > 1 else 0
        out.append((g[0] - tol, g[-1] + tol + pas))
    return out


def dans(y, plages):
    return any(a <= y <= b for a, b in plages)


def controler(fiche, cal, projet, rq):
    """Compare chaque texte de la fiche à la charte. Style, taille et bord : erreurs dans rq. Places en hauteur : notées sur les
    calques du calcul (« _charte »), contrôlées par la garde-tête. → nombre de textes comparés."""
    if not fiche.get('charte'):
        return 0
    try:
        ref, chemin = lire(fiche, projet)
    except (OSError, ValueError) as e:
        rq.erreur(f'charte « {fiche["charte"]} » illisible ({e}) : donner le chemin de la fiche montage.json de la vidéo validée')
        return 0
    cal['_charte_fichier'] = str(chemin)
    ou = chemin.parent.name
    if json.dumps(ref.get('format', '9:16')) != json.dumps(fiche.get('format', '9:16')):
        rq.erreur(f'format {json.dumps(fiche.get("format", "9:16"))} et charte ({ou}) en {json.dumps(ref.get("format", "9:16"))} : même format que la vidéo validée')
        return 0
    if json.dumps(ref.get('theme', 'neutre'), sort_keys=True) != json.dumps(fiche.get('theme', 'neutre'), sort_keys=True):
        rq.erreur(f'thème différent de la charte ({ou}). Je propose : "theme": {json.dumps(ref.get("theme", "neutre"), ensure_ascii=False)}.')
    W, H, zones = cal['l'], cal['h'], cal['zones_instagram']
    tol = round(ECART_Y * H / 1920)
    modeles = [(i, c) for i, c in enumerate(ref.get('calques') or []) if c.get('t') in GENRES]
    par_n = {}
    for j, cc in enumerate(cal['calques']):
        par_n.setdefault(cc.get('_n'), []).append(cc)
    vus = 0
    for i, c in enumerate(fiche.get('calques') or []):
        t = c.get('t')
        if t not in GENRES:
            continue
        nom = _nom(i, c)
        cands = [(n, m) for n, m in modeles if m['t'] == t]
        if not cands:
            rq.attention(f'{nom} : aucun {NOMS[t]} dans la charte ({ou}) : ce texte n\'a pas de modèle, le montrer à Yohann')
            continue
        vus += 1
        st, ta, x, y = _style(c), _taille(c, W), _x(c, W, zones), _y(c, W, zones)

        def ecarts(m):
            sm = _style(m)
            return [k for k in st if st[k] != sm[k]]
        n, m = min(cands, key=lambda nm: (len(ecarts(nm[1])), abs(_taille(nm[1], W) - ta) / max(1, _taille(nm[1], W)),
                                          abs(_x(nm[1], W, zones) - x), abs((_y(nm[1], W, zones) or 0) - (y or 0))))
        sm, tm, xm = _style(m), _taille(m, W), _x(m, W, zones)
        props = [(k, sm[k], st[k]) for k in ecarts(m)]
        if abs(ta - tm) > ECART_TAILLE * tm:
            props.append(('taille', tm, ta))
        if abs(x - xm) > ECART_X and t != 'sous-titres':
            props.append(('x', round(xm), round(x)))
        if props:
            quoi = ', '.join(f'{k} {_v(b)} au lieu de {_v(a)}' for k, a, b in props)
            faire = [f'"{k}": {json.dumps(a, ensure_ascii=False)}' if a is not None else f'retirer « {k} »' for k, a, b in props]
            rq.erreur(f'{nom} : pas comme la charte ({quoi}). Je propose : {", ".join(faire)} (comme le calque {n + 1} de {ou}).')
        # places en hauteur : celles des textes de la charte du même genre et du même style
        meme = [mm for _, mm in modeles if mm['t'] == t and _style(mm) == sm]
        ys = [_y(mm, W, zones) for mm in meme]
        pl = places(ys, tm, tol)
        for cc in (par_n.get(i + 1, []) if pl else []):
            cc['_charte'] = dict(places=pl, ancres=sorted({round(v) for v in ys if v is not None}), ref=n + 1, ou=ou)
    return vus


def hors_place(cal):
    """Textes posés hors des places de la charte (sans les têtes) : pour « verifier » avant la préparation.
    → [(indice du calque, hauteur proposée)], un par calque de la fiche."""
    out, vus = [], set()
    for j, c in enumerate(cal['calques']):
        ch = c.get('_charte')
        if not ch or c.get('y') is None or c.get('_n') in vus or dans(c['y'], ch['places']):
            continue
        vus.add(c.get('_n'))
        out.append((j, min(ch['ancres'], key=lambda a: abs(a - c['y']))))
    return out


def texte_places(ch):
    return ' ou '.join(f'{round(a)} à {round(b)}' for a, b in ch['places'])
