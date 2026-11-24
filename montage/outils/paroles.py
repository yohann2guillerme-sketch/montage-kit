"""Paroles d'un plan ou de toute une prise : chaque mot avec son début et sa fin (sous-titres mot à mot, coupe des silences).

Utilise faster-whisper (gratuit, tourne sur la machine). Le résultat est gardé dans <travail>/paroles/<plan>.json
et peut être corrigé à la main (orthographe d'un nom, d'une marque) avant le rendu.
"""
import json
import os
import subprocess
from pathlib import Path

import ressources as RES


def transcrire(fichier, debut, duree, langue='fr', modele=None):
    """→ liste de [mot, début, fin] en secondes DANS LA VIDÉO SOURCE."""
    import numpy as np
    from faster_whisper import WhisperModel
    modele = modele or os.environ.get('MONTAGE_WHISPER', 'small')
    # le son est décodé ici par ffmpeg (16 kHz, mono) : pas besoin du décodeur de faster-whisper, fragile selon les versions
    brut = subprocess.run(RES.ff(['ffmpeg', '-v', 'error', '-ss', f'{debut:.3f}', '-i', str(fichier), '-t', f'{duree:.3f}',
                                  '-vn', '-ac', '1', '-ar', '16000', '-f', 'f32le', '-']), capture_output=True, check=True).stdout
    son = np.frombuffer(brut, np.float32)
    if len(son) < 1600:
        return []
    m = WhisperModel(modele, device='cpu', compute_type='int8', cpu_threads=RES.fils() or 0)      # sur le Mac : les cœurs du mode discret
    segments, _ = m.transcribe(son, language=langue, word_timestamps=True, vad_filter=True)
    return recoller([(w.word, debut + w.start, debut + w.end) for s in segments for w in (s.words or [])])


def recoller(morceaux):
    """[(texte, début, fin), …] tels que la transcription les donne → [[mot, début, fin], …] propres.
    Le français sort « qu’on », « s’assurer », « celle-ci » en deux morceaux : on les recolle, avec une vraie apostrophe."""
    mots = []
    for texte, t0, t1 in morceaux:
        t = str(texte).strip().replace("'", '’')
        if not t:
            continue
        if mots and (t[0] in '’-' or mots[-1][0][-1] in '’-' or not any(c.isalnum() for c in t)):
            mots[-1][0] += ('\u00a0' if t[0] in '!?:;»' else '') + t      # en français, une espace avant ! ? : ;
            mots[-1][2] = round(float(t1), 3)
        else:
            mots.append([t, round(float(t0), 3), round(float(t1), 3)])
    return mots


def enveloppe(fichier, pas=0.01):
    """Niveau du son d'une prise, en dB, toutes les 10 ms : (niveaux, pas). Sert à poser les coupes au bord exact de la parole."""
    import numpy as np
    brut = subprocess.run(RES.ff(['ffmpeg', '-v', 'error', '-i', str(fichier), '-vn', '-ac', '1', '-ar', '16000', '-f', 'f32le', '-']),
                          capture_output=True, check=True).stdout
    x = np.frombuffer(brut, np.float32)
    k = int(16000 * pas)
    n = len(x) // k
    return 20 * np.log10(np.sqrt((x[:n * k].reshape(n, k) ** 2).mean(1)) + 1e-9), pas


def _lisse(db, pas):
    """Niveau lissé sur 50 ms (médiane) : un claquement d'une tranche ne compte plus, les bords de la parole ne bougent pas."""
    import numpy as np
    from numpy.lib.stride_tricks import sliding_window_view
    k = max(1, int(round(0.05 / pas))) | 1
    return np.median(sliding_window_view(np.pad(db, k // 2, mode='edge'), k), axis=1)


def _bruit_et_voix(lisse):
    """(bruit de la pièce, voix) en dB : le niveau des moments calmes et celui des moments où on parle."""
    import numpy as np
    return float(np.percentile(lisse, 10)), float(np.percentile(lisse, 95))


def voix_nette(niveau, mini=22.0):
    """Vrai quand la voix sort d'au moins 22 dB du bruit de la pièce : en dessous, le son ne permet pas de poser les coupes
    (musique du magasin, vent, micro trop loin) et on garde les temps de la transcription."""
    bruit, voix = _bruit_et_voix(_lisse(*niveau))
    return voix - bruit >= mini


def _voix_active(lisse, pas):
    """Une case par pas, vraie quand on entend la voix. Le seuil est à 10 dB au moins au-dessus du bruit de la pièce
    (un bruit de fond varie de 8 dB d'une tranche à l'autre), entre 40 et 12 dB sous la voix. Les éclats isolés de moins
    de 40 ms (un objet posé, un clic) ne sont pas de la parole."""
    bruit, voix = _bruit_et_voix(lisse)
    actif = lisse >= min(max(bruit + max(10.0, 0.35 * (voix - bruit)), voix - 40.0), voix - 12.0)
    net = actif.copy()
    court, pres = max(1, int(round(0.04 / pas))), max(1, int(round(0.12 / pas)))
    i, n = 0, len(actif)
    while i < n:
        if not actif[i]:
            i += 1; continue
        j = i
        while j < n and actif[j]:
            j += 1
        if j - i < court and not actif[max(0, i - pres):i].any() and not actif[j:j + pres].any():
            net[i:j] = False
        i = j
    return net


def _bords_parole(actif, lisse, pas, premier, dernier, avant, apres, dehors=0.6, dedans=1.5, trou=0.12):
    """Vrai début et vraie fin de la parole d'un groupe de mots : (début, fin, à écouter).
    Les temps de la transcription sont souvent faux de 0,1 à 0,9 s aux deux bouts : coupé là, un plan commencerait sur du vide
    ou perdrait sa dernière syllabe. Quand la voix déborde, on s'écarte d'au plus `dehors` secondes ; quand il y a du vide,
    on rentre d'au plus `dedans` secondes, sans jamais entamer le premier ni le dernier mot. Si la voix continue plus loin
    que `dehors` (un « euh » collé au mot, un rire), la coupe va au moment le plus calme et elle est signalée « à écouter »."""
    n = len(actif)
    case = lambda t: min(max(int(round(float(t) / pas)), 0), n - 1)
    k = max(1, int(round(trou / pas)))                    # un trou plus court (consonne sourde) reste de la parole
    i = case(premier[1])
    j = max(i, case(dernier[2]) - 1)                      # la dernière tranche du dernier mot (sa fin est exclue)
    ecouter = []
    d = i
    if actif[d:d + 3].any():                              # on parle déjà : reculer jusqu'au vrai début
        voisin, loin = case(avant), d - int(dehors / pas)
        bas = max(voisin, loin, 0)
        while d > bas and actif[max(bas, d - k):d].any():
            d -= 1
        if d == bas and bas > 0 and actif[max(0, d - k):d].any():       # ça parle encore avant : le moment le plus calme
            d = bas + int(lisse[bas:i + 1].argmin())
            if loin >= voisin:
                ecouter.append('début')
    else:                                                 # la transcription est en avance : avancer jusqu'au premier son
        haut = min(j, d + int(dedans / pas), max(d, case(float(premier[2]) - 0.1)))
        while d < haut and not actif[d]:
            d += 1
        if not actif[d]:
            d = i                                         # rien trouvé : on garde la transcription
    f = j
    if actif[max(0, f - 2):f + 1].any():                  # on parle encore : avancer jusqu'à la vraie fin
        voisin, loin = case(apres), f + int(dehors / pas)
        haut = min(voisin, loin, n - 1)
        while f < haut and actif[f + 1:f + 1 + k].any():
            f += 1
        if f == haut and haut < n - 1 and actif[f + 1:f + 1 + k].any():  # ça parle encore après : le moment le plus calme
            f = j + int(lisse[j:haut + 1].argmin())
            if loin <= voisin:
                ecouter.append('fin')
    else:                                                 # la transcription est en retard : reculer jusqu'au dernier son
        bas = max(d, f - int(dedans / pas), min(f, case(float(dernier[1]) + 0.1)))
        while f > bas and not actif[f]:
            f -= 1
        if not actif[f]:
            f = j
    return d * pas, max(d + 1, f + 1) * pas, ecouter


def _zones_de_parole(actif, pas, t0, t1, silence, mots):
    """Entre t0 et t1, les morceaux où on parle, séparés par les vrais silences d'au moins `silence` secondes.
    Un creux où la transcription a entendu un mot entier (un mot dit tout bas) n'est pas un silence : on ne le coupe pas."""
    i0, i1 = int(round(t0 / pas)), min(len(actif), int(round(t1 / pas)))
    zones, debut, i = [], i0, i0
    while i < i1:
        if actif[i]:
            i += 1; continue
        j = i
        while j < i1 and not actif[j]:
            j += 1
        g0, g1 = i * pas, j * pas
        mot_dedans = any(g0 - 0.05 <= float(m[1]) and (float(m[1]) + float(m[2])) / 2 <= g1 for m in mots)
        if i > debut and j < i1 and g1 - g0 >= silence and not mot_dedans:
            zones.append((debut * pas, g0)); debut = j
        i = j
    return zones + [(debut * pas, t1)]


def _zone_du_mot(m, zones):
    """Le morceau où un mot est dit : celui où il commence (le début d'un mot est plus sûr que sa fin), sinon celui qu'il recouvre le plus."""
    a, b = float(m[1]), float(m[2])
    for n, (z0, z1) in enumerate(zones):
        if z0 - 0.05 <= a < z1:
            return n
    part = [min(b, z1) - max(a, z0) for z0, z1 in zones]
    if max(part) > 0:
        return part.index(max(part))
    c = (a + b) / 2
    return min(range(len(zones)), key=lambda n: min(abs(c - zones[n][0]), abs(c - zones[n][1])))


def _mots_dans(g, t0, t1):
    """Les mots d'un morceau, ramenés dans ses vrais bords : la transcription étire souvent le dernier mot sur le silence
    qui suit, et il s'afficherait alors au début du plan d'après."""
    out = []
    for m in g:
        a = min(max(float(m[1]), t0), max(t0, t1 - 0.08))
        out.append([m[0], round(a, 3), round(max(min(float(m[2]), t1), a + 0.08), 3)])
    return out


def phrases(mots, silence=0.45, marge_avant=0.12, marge_apres=0.20, niveau=None, duree=None):
    """Mots d'une prise [[mot, début, fin], …] → phrases séparées par les silences : [dict(de, a, texte, mots, paroles)].
    Une phrase s'arrête à un silence d'au moins `silence` secondes, ou de moitié moins après un point.
    Avec `niveau` (le résultat de enveloppe()), les bords sont posés sur le son réel et les vrais silences cachés
    par la transcription recoupent la phrase. `de` et `a` gardent une petite marge (le souffle, la dernière syllabe)
    sans jamais mordre sur la phrase voisine ni dépasser la fin de la prise (`duree`). `paroles` : les mots de la phrase,
    recalés dans ses bords. Une coupe incertaine porte « a_ecouter »."""
    groupes = []
    for m in mots:
        if groupes:
            vide = float(m[1]) - float(groupes[-1][-1][2])
            fin_de_phrase = str(groupes[-1][-1][0]).rstrip(' \u00a0»"').endswith(('.', '?', '!', '…'))
            if vide < (silence / 2 if fin_de_phrase else silence):
                groupes[-1].append(m); continue
        groupes.append([m])
    morceaux = []                                         # (début, fin, mots, à écouter)
    if niveau is None:
        morceaux = [(float(g[0][1]), float(g[-1][2]), g, []) for g in groupes]
    else:
        db, pas = niveau
        lisse = _lisse(db, pas)
        actif = _voix_active(lisse, pas)
        for n, g in enumerate(groupes):
            avant = morceaux[-1][1] if morceaux else 0.0
            apres = float(groupes[n + 1][0][1]) if n + 1 < len(groupes) else len(db) * pas
            t0, t1, ecouter = _bords_parole(actif, lisse, pas, g[0], g[-1], avant, max(apres, float(g[-1][2])))
            zones = _zones_de_parole(actif, pas, t0, t1, silence, g)
            paquets = [[] for _ in zones]
            for m in g:
                paquets[_zone_du_mot(m, zones)].append(m)
            gardes = [(a, b, q, []) for (a, b), q in zip(zones, paquets) if q]
            if 'début' in ecouter:
                gardes[0][3].append('début')
            if 'fin' in ecouter:
                gardes[-1][3].append('fin')
            morceaux += gardes
    if duree is None and niveau is not None:
        duree = len(niveau[0]) * niveau[1]
    out = []
    for i, (t0, t1, g, ecouter) in enumerate(morceaux):
        de = max(0.0, t0 - (0.0 if 'début' in ecouter else marge_avant))     # coupe posée au moment le plus calme : pas de marge
        a = t1 + (0.0 if 'fin' in ecouter else marge_apres)
        if duree:
            a = max(min(a, float(duree)), de + 0.04)
        if i:
            de = max(de, (morceaux[i - 1][1] + t0) / 2)
        if i + 1 < len(morceaux):
            a = min(a, (t1 + morceaux[i + 1][0]) / 2)
        p = dict(de=round(de, 2), a=round(a, 2), texte=' '.join(str(x[0]) for x in g), mots=len(g), paroles=_mots_dans(g, t0, t1))
        if ecouter:
            p['a_ecouter'] = ' et '.join(ecouter)
        out.append(p)
    return out


def reprises(ph, seuil=0.72):
    """Phrases dites deux fois (un faux départ, puis la bonne prise) : [(i, j)], la phrase i recommence en j. On garde la dernière.
    Deux phrases se ressemblent quand leurs premiers mots sont presque les mêmes."""
    import difflib
    import re
    net = lambda texte: re.sub(r'[^\w\s’\'-]', '', texte.lower()).split()
    out = []
    for i, p in enumerate(ph):
        a = net(p['texte'])
        for j in range(i + 1, min(i + 4, len(ph))):
            b = net(ph[j]['texte'])
            n = min(len(a), len(b))
            if n >= 2 and difflib.SequenceMatcher(None, a[:n], b[:n]).ratio() >= seuil:
                out.append((i, j)); break
    return out


def plans_proposes(ph, source, zoom=1.12, sauf=(), prefixe='P'):
    """Phrases → plans prêts à coller dans la fiche : un plan par phrase gardée, son d'origine, et un plan sur deux resserré
    (la coupe devient un changement de cadre voulu, pas un saut). Le zoom garde les yeux à la même hauteur quand ils sont
    au tiers haut de l'image, là où on cadre une personne qui parle."""
    out = []
    for n, p in enumerate(ph):
        if n in sauf:
            continue
        q = {'id': f'{prefixe}{n + 1:02d}', 'source': source, 'de': p['de'], 'duree': f'{round(p["a"] - p["de"], 2)}s', 'son': True}
        if zoom and zoom > 1 and len(out) % 2:
            q['zoom'] = zoom
            q['cy'] = round(1 / 3 + (1 / 2 - 1 / 3) / zoom, 3)
        out.append(q)
    return out


def paroles_du_plan(q, ips, travail, forcer=False):
    d = Path(travail) / 'paroles'
    d.mkdir(parents=True, exist_ok=True)
    f = d / f'{q["id"]}.json'
    if f.exists() and not forcer:
        return json.loads(f.read_text(encoding='utf-8')), f
    mots = transcrire(q['_fichier'], q['src'], (q['t1'] - q['t0']) / ips)
    f.write_text(json.dumps(mots, ensure_ascii=False, indent=0), encoding='utf-8')
    return mots, f
