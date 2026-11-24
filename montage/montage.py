#!/usr/bin/env python3
"""Kit de montage de Reels : une fiche (montage.json) → une vidéo propre, aux normes, contrôlée.

    python3 montage/montage.py nouveau   <dossier> [--theme foulees]   crée un projet avec une fiche d'exemple
    python3 montage/montage.py rushes    <projet>                      UNE planche de toutes les vidéos et photos de sources/ (pour choisir les extraits)
    python3 montage/montage.py verifier  <projet>                      lit la fiche et dit ce qui cloche (2 secondes, aucun rendu ; têtes comprises dès que les plans sont prêts)
    python3 montage/montage.py planche   <projet> [--images 0,45,90]   une seule image de contrôle, avec les zones d'Instagram
    python3 montage/montage.py apercu    <projet>                      vidéo légère pour juger le rythme + planche « film »
    python3 montage/montage.py final     <projet> [--plage 0-120]      vidéo HD aux normes + contrôle qualité + version sans musique
    python3 montage/montage.py tout      <projet>                      verifier + planche + final, d'un coup
    python3 montage/montage.py couverture <projet> --image 45          image de couverture du Reel (pleine taille)
    python3 montage/montage.py controle  <video.mp4> [--instagram]     contrôle qualité d'une vidéo (et simulation de la compression Instagram)
    python3 montage/montage.py transcrire <projet> <plan>              paroles d'un plan, mot à mot (sous-titres)
    python3 montage/montage.py transcrire <projet> sources/prise.mov   face caméra : toute la prise, phrase par phrase, avec les plans prêts à coller (silences coupés)
    python3 montage/montage.py sons      [famille]                     les bruitages qu'une fiche peut nommer (kit + bibliothèque libre du skill sound-effects)
    python3 montage/montage.py tempo     <musique> [début en s]        tempo d'une musique
    python3 montage/montage.py caler     <projet> <vidéo> [...]        clip en playback : instant de la chanson où chaque vidéo commence (lèvres synchrones)

Tout le travail va dans <projet>/.travail/ et les résultats dans <projet>/sorties/. Rien ne s'écrit dans le dépôt.
Garde-tête (outils/tete.py) : à chaque préparation, aucune tête coupée par le cadre ni couverte par un texte, aucun texte sur un autre ;
sinon l'aperçu, la vidéo finale et la couverture sont refusés, avec la correction proposée et sorties/garde-tete.jpg.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

if os.name == 'nt' and not sys.flags.utf8_mode:      # Windows : tout en UTF-8 (fiches, accents, messages), enfants compris
    os.environ['PYTHONUTF8'] = '1'
    sys.exit(subprocess.call([sys.executable, '-X', 'utf8'] + sys.argv))

KIT = Path(__file__).resolve().parent
sys.path.insert(0, str(KIT / 'outils'))

import ressources as RES  # noqa: E402
RES.environnement()       # avant numpy, OpenCV, onnxruntime : sur le Mac, leurs calculs restent sur les cœurs du mode discret
import fiche as F  # noqa: E402


def dire(*a):
    print(*a, flush=True)


def _travail(projet):
    t = Path(os.environ.get('MONTAGE_TRAVAIL') or Path(projet) / '.travail')
    t.mkdir(parents=True, exist_ok=True)
    return t


def _montre(rq):
    ordre = {'erreur': 0, 'attention': 1, 'conseil': 2}
    for n, t in sorted(rq, key=lambda x: ordre[x[0]]):
        dire(f'  [{n}] {t}')


def _empreinte(fiche, calcul, projet):
    """Signature de tout ce qui change le résultat : la fiche résolue (paroles, tempo, thème compris), l'état des fichiers sources,
    et le code du kit qui prépare les plans et le son (après une mise à jour du kit, un projet déjà préparé est refait)."""
    h = hashlib.sha1(json.dumps(calcul, sort_keys=True, default=str).encode())
    for code in ('preparer.py', 'mix.py', 'tete.py', 'cadrage.py', 'charte.py'):
        h.update((KIT / 'outils' / code).read_bytes())
    fichiers = [q['_fichier'] for q in calcul['plans']] + [c['_fichier'] for c in calcul['calques'] if c.get('_fichier')]
    if calcul.get('_charte_fichier'):
        fichiers.append(calcul['_charte_fichier'])
    if calcul.get('_musique'):
        fichiers.append(str(Path(projet) / calcul['_musique']['fichier']))
    for f in fichiers:
        try:
            st = os.stat(f)
            h.update(f'{f}|{st.st_size}|{int(st.st_mtime)}'.encode())
        except OSError:
            h.update(f'{f}|absent'.encode())
    return h.hexdigest()


def _empreinte_plans(calcul, projet):
    """Ce qui change les images extraites des plans (pas les textes, ni les effets) : si elle n'a pas bougé depuis la dernière
    préparation, « verifier » contrôle les têtes sur les images déjà extraites, sans rien refaire."""
    cles = ('id', 'photo', 'src', 'vitesse', 't0', 't1', '_fichier', '_zoom', '_cx', '_cy', '_cadrage', '_stabilise', '_lut', '_masque', '_zmax')
    net = lambda q: {k: q.get(k) for k in cles} if q else None
    h = hashlib.sha1(json.dumps([[net(q), net(q.get('double'))] for q in calcul['plans']], sort_keys=True, default=str).encode())
    for code in ('preparer.py', 'cadrage.py'):
        h.update((KIT / 'outils' / code).read_bytes())
    for f in sorted({q['_fichier'] for q in calcul['plans']} | {q['double']['_fichier'] for q in calcul['plans'] if q.get('double')}):
        try:
            st = os.stat(f)
            h.update(f'{f}|{st.st_size}|{int(st.st_mtime)}'.encode())
        except OSError:
            h.update(f'{f}|absent'.encode())
    return h.hexdigest()


def _public_manquant(calcul, ancien, travail):
    """Fichiers rangés dans public/ par la dernière préparation et qui n'y sont plus (public/images vidé à la main, plan effacé…).
    Avant, la préparation était reprise du cache sans regarder, et le rendu suivant échouait tant qu'on ne la forçait pas."""
    tous = calcul['plans'] + [q['double'] for q in calcul['plans'] if q.get('double')]
    attendus = [f'plans/{q["id"]}/meta.json' for q in tous]
    attendus += [f'masques/{q["id"]}/cle.txt' for q in calcul['plans'] if q.get('_masque')]
    attendus += ['images/' + (c['logo'] if c.get('t') == 'signature' else c['fichier']) for c in calcul['calques'] if c.get('_fichier')]
    attendus += [f'polices/{p[1]}' for p in calcul['polices']]
    attendus += ['fx/grain7.png'] if calcul['finition']['grain'] > 0 else []
    attendus += [ancien['audio'], 'audio/sons-seuls.wav'] if ancien.get('audio') else []
    public = Path(travail) / 'public'
    return [a for a in dict.fromkeys(attendus) if not (public / a).exists()]


def _montre_garde(g):
    if g['ok']:
        dire(f'Garde-tête : rien à corriger (têtes suivies dans {g["plans_avec_tete"]} plan(s) : aucune coupée par le cadre ni couverte, aucun texte sur un autre'
             + (', textes à leur place dans la charte' if g.get('charte') else '') + ').')
    else:
        dire(f'Garde-tête : {g["nb"]} problème(s). L\'aperçu, la vidéo finale et la couverture sont refusés tant qu\'il en reste :')
        for l_ in g['lignes']:
            dire(f'  [erreur] {l_}')
    for l_ in g.get('notes') or []:
        dire(f'  [attention] {l_}')
    for pid in g.get('sans_garde') or []:
        dire(f'  [attention] plan {pid} : garde-tête retirée ("garde_tete": false). Seulement pour une fausse tête (affiche, mannequin) : '
             'la tête d\'une vraie personne reste toujours entière et sans texte dessus.')


def _garde(calcul, travail):
    """Garde-tête complète (têtes des plans + textes), toujours montrée. Si elle ne peut pas tourner, le rendu reste refusé."""
    import tete
    try:
        g = tete.controler(calcul, travail)
    except (RuntimeError, ImportError, OSError) as e:
        g = dict(ok=False, nb=1, plans_avec_tete=0, sans_garde=[], dessin=[], notes=[],
                 lignes=[f'contrôle impossible ({e}). Tant qu\'il ne tourne pas, le rendu reste refusé (détecteur : voir outils/cadrage.py).'])
    _montre_garde(g)
    return g


def _garde_verifier(projet, calcul):
    """« verifier » : textes l'un sur l'autre toujours ; têtes aussi quand les plans de la dernière préparation sont encore bons."""
    import tete
    travail = _travail(projet)
    ancien = travail / 'calcul.json'
    if ancien.exists():
        a = json.loads(ancien.read_text(encoding='utf-8'))
        if a.get('empreinte_plans') == _empreinte_plans(calcul, projet):
            metas = {q['id']: q for q in a['plans']}
            metas.update({q['double']['id']: q['double'] for q in a['plans'] if q.get('double')})
            tous = calcul['plans'] + [q['double'] for q in calcul['plans'] if q.get('double')]
            if all(q['id'] in metas and 'n' in metas[q['id']] for q in tous):
                for q in tous:
                    m = metas[q['id']]
                    q.update(debut=m['debut'], ips=m['ips'], n=m['n'], masques=m.get('masques'))
                return _garde(calcul, travail)['ok']
    import charte
    lignes, moments = tete.chevauchements(calcul)
    hors = charte.hors_place(calcul)
    lignes += [f'{tete._nom(j, calcul)} : hors de sa place dans la charte (y {charte.texte_places(calcul["calques"][j]["_charte"])}). '
               f'Je propose : "y": {round(y)} (vérifié avec les têtes à la préparation).' for j, y in hors]
    for l_ in lignes:
        dire(f'  [erreur] {l_}')
    dire('Garde-tête : textes contrôlés. Les têtes le seront à la préparation (planche, aperçu, final), une fois les plans extraits.')
    return not moments and not hors


def _dessine(src, dst, formes, echelle):
    """Image de contrôle : zone de la tête, tête entière, texte en cause, partie visible."""
    from PIL import Image, ImageDraw
    couleurs = {'zone': (33, 230, 255), 'tete': (255, 159, 28), 'texte': (255, 230, 0), 'visible': (60, 255, 122)}
    im = Image.open(src).convert('RGB')
    d = ImageDraw.Draw(im)
    for b, sorte in formes:
        x0, y0, x1, y1 = (v * echelle for v in b)
        d.rectangle((x0, y0, x1, y1), outline=couleurs.get(sorte, (255, 255, 255)), width=3 if sorte in ('texte', 'zone') else 2)
    im.save(dst, quality=90)
    return dst


def _refuse(calcul, travail, projet):
    """Aperçu, final et couverture : refusés tant que la garde-tête trouve un problème, avec l'image de contrôle."""
    g = calcul.get('garde_tete') or {}
    if g.get('ok'):
        return False
    image = None
    if g.get('dessin'):
        from planche import planche
        d = travail / 'garde'
        d.mkdir(parents=True, exist_ok=True)
        for f in d.glob('*.jpg'):
            f.unlink()
        ech = 0.5
        try:
            _node(travail, 'images', liste=','.join(str(i) for i in sorted({x['image'] for x in g['dessin']})), echelle=ech, sortie=d)
            fichiers = [_dessine(d / f'{x["image"]:05d}.jpg', d / f'controle-{i}.jpg', x['formes'], ech) for i, x in enumerate(g['dessin'])]
            sorties = Path(projet).resolve() / 'sorties'; sorties.mkdir(exist_ok=True)
            lv = 400 if calcul['h'] > calcul['l'] else 520
            image = planche(fichiers, sorties / 'garde-tete.jpg', [x['legende'] for x in g['dessin']], colonnes=min(4, len(fichiers)),
                            vignette=(lv, round(lv * calcul['h'] / calcul['l'])), titre='bleu : tête · jaune : texte · vert : visible')
        except (SystemExit, OSError):
            image = None
    dire(f'Rendu refusé par la garde-tête : {g.get("nb", "?")} problème(s) à corriger dans la fiche (lignes [erreur] ci-dessus).'
         + (f'\nImage de contrôle : {image}' if image else ''))
    return True


def resoudre(projet, silencieux=False):
    """Lit la fiche, calcule la ligne de temps. → (fiche, calcul, remarques, tempo)."""
    projet = Path(projet).resolve()
    fi = F.charger(projet)
    travail = _travail(projet)
    tempo = None
    mus = fi.get('musique')
    if mus and (projet / mus['fichier']).exists():
        from tempo import tempo_du_projet
        tempo = tempo_du_projet(mus, projet, travail)
    paroles = {p.stem: json.loads(p.read_text(encoding='utf-8')) for p in (travail / 'paroles').glob('*.json')} if (travail / 'paroles').exists() else {}
    prises = {p.name[:-5]: json.loads(p.read_text(encoding='utf-8')) for p in (travail / 'prises').glob('*.json')} if (travail / 'prises').exists() else {}
    calcul, rq = F.resoudre(fi, projet, tempo, paroles=paroles, prises=prises)
    import tete
    import charte
    tete.annoter(fi, calcul)
    charte.controler(fi, calcul, projet, rq)
    if not silencieux:
        d = f'{calcul["n"]} images ({calcul["n"] / calcul["ips"]:.1f} s), {len(calcul["plans"])} plan(s), {len(calcul["calques"])} calque(s)'
        if tempo:
            d += f', musique {tempo["bpm"]:.1f} temps/min (départ calé à {tempo["debut_cale"]:.2f} s)'
            if tempo.get('incertain'):
                rq.attention(f'calage de la musique incertain (rythme en triolets ou à contretemps) : autres départs possibles {tempo["candidats"]} s. '
                             'Vérifier à l\'oreille, ou fixer « bpm » et « premier_temps » dans « musique ».')
        dire(f'Fiche « {calcul["nom"]} » : {d}')
        _montre(rq)
    return fi, calcul, rq, tempo


def preparer(projet):
    """Fiche → plans extraits, masques, bande-son, calcul.json. Ne refait que ce qui a changé."""
    projet = Path(projet).resolve()
    fi, calcul, rq, tempo = resoudre(projet)
    if rq.bloquant:
        dire('Fiche à corriger avant de continuer (lignes [erreur] ci-dessus).')
        sys.exit(1)
    travail = _travail(projet)
    cible = travail / 'calcul.json'
    emp = _empreinte(fi, calcul, projet)
    if cible.exists():
        ancien = json.loads(cible.read_text(encoding='utf-8'))
        if ancien.get('empreinte') == emp and 'garde_tete' in ancien:
            manque = _public_manquant(calcul, ancien, travail)
            if not manque:
                _montre_garde(ancien['garde_tete'])
                return ancien, travail
            dire(f'  {len(manque)} fichier(s) de la préparation effacé(s) depuis (dont {manque[0]}) : préparation refaite, seul ce qui manque est refait')
    t0 = time.time()
    from preparer import preparer as prep
    from mix import mixer, credits
    prep(calcul, travail, dire)
    info = mixer(calcul, projet, travail, tempo, dire)
    son = 'aucun son' if info['lufs'] is None else f'{info["lufs"]} LUFS, crête {info["crete"]} dB, {info["bruitages"]} bruitage(s)' + (', musique' if info['musique'] else '') + (', voix' if info['voix'] else '')
    dire(f'  son : {son}')
    garde = _garde(calcul, travail)
    pub = F.public(calcul)
    pub['empreinte'] = emp
    pub['empreinte_plans'] = _empreinte_plans(calcul, projet)
    pub['garde_tete'] = garde
    pub['son'] = info
    pub['credits'] = credits(calcul, projet)
    cible.write_text(json.dumps(pub, ensure_ascii=False), encoding='utf-8')
    dire(f'Préparation faite en {time.time() - t0:.0f} s')
    return pub, travail


def _node(travail, mode, **opts):
    moteur = KIT / 'moteur'
    if not (moteur / 'node_modules' / 'remotion').exists():
        dire('Première utilisation : installation du moteur (une fois, environ 30 s)…')
        r = subprocess.run([shutil.which('npm') or 'npm', 'install', '--no-audit', '--no-fund', '--loglevel=error'], cwd=moteur, capture_output=True, text=True)
        if r.returncode:
            dire('Installation impossible :', r.stderr.strip()[-400:]); sys.exit(1)
    opts = {**RES.remotion(), **opts}           # sur le Mac : onglets, fils de l'encodeur, cache, rendu sans la carte graphique
    cmd = ['node', str(moteur / 'rendu.mjs'), str(travail), mode] + [f'{k}={v}' for k, v in opts.items() if v is not None]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=moteur)
    utile = [l for l in (r.stdout + r.stderr).splitlines() if l.strip() and not any(x in l for x in ('Memory reported', 'docker run', 'lower amount of memory', 'Detected differing'))]
    if r.returncode:
        dire('Le rendu a échoué :'); dire('\n'.join(utile[-12:])); sys.exit(1)
    return utile[-1] if utile else ''


def cmd_planche(projet, images=None, zones=True):
    calcul, travail = preparer(projet)
    from planche import images_reperes, planche
    reperes = [(int(x), '') for x in images.split(',')] if images else images_reperes(calcul)
    d = travail / 'images'
    for f in d.glob('*.jpg') if d.exists() else []:
        f.unlink()
    plein = images is not None and len(reperes) <= 4
    _node(travail, 'images', liste=','.join(str(k) for k, _ in reperes), echelle=0.5 if plein else 0.25, zones=1 if zones else None, sortie=d)
    sorties = Path(projet).resolve() / 'sorties'; sorties.mkdir(exist_ok=True)
    fichiers = [d / f'{k:05d}.jpg' for k, _ in reperes]
    if zones:                                   # zone de chaque tête (aucun texte dedans) : bleu
        import tete
        try:
            zt = tete.zones_a(calcul, travail, [k for k, _ in reperes])
        except (RuntimeError, ImportError, OSError):
            zt = {}
        for (k, _), f in zip(reperes, fichiers):
            if zt.get(k):
                _dessine(f, f, [(z, 'zone') for z, _ in zt[k]], 0.5 if plein else 0.25)
    etiq = [f'{k} {n}'.strip() for k, n in reperes]
    lv = 540 if plein else 270
    reel = calcul.get('zones_instagram', {}).get('reel', True)
    out = planche(fichiers, sorties / 'planche.jpg', etiq, colonnes=min(8, len(fichiers)), vignette=(lv, round(lv * calcul['h'] / calcul['l'])),
                  titre=f'{calcul["nom"]} · {calcul["n"]} images · ' + ('zones rouges = cachées par Instagram' if reel else 'bord rouge = marges') + ' · cadre bleu = tête (aucun texte)' if zones else calcul['nom'])
    dire(f'Planche : {out}  ({len(fichiers)} images)')
    return out


def cmd_apercu(projet, plage=None):
    calcul, travail = preparer(projet)
    if _refuse(calcul, travail, projet):
        return 1
    sorties = Path(projet).resolve() / 'sorties'; sorties.mkdir(exist_ok=True)
    out = sorties / 'apercu.mp4'
    dire(_node(travail, 'apercu', plage=plage, sortie=out))
    from planche import film
    f = film(out, sorties / 'film.jpg', pas_s=0.5, vignette=(180, round(180 * calcul['h'] / calcul['l'])), titre=f'{calcul["nom"]} · une image toutes les 0,5 s')
    dire(f'Aperçu : {out}\nPlanche film : {f}')
    return 0


def cmd_final(projet, plage=None, crf=None):
    calcul, travail = preparer(projet)
    if _refuse(calcul, travail, projet):
        return 1
    sorties = Path(projet).resolve() / 'sorties'; sorties.mkdir(exist_ok=True)
    nom = ''.join(ch if ch.isalnum() or ch in '-_' else '-' for ch in calcul['nom']).strip('-') or 'montage'
    out = sorties / f'{nom}.mp4'
    dire(_node(travail, 'final', plage=plage, sortie=out, crf=crf))
    from controle import controler, texte, verdict
    att = dict(l=calcul['l'], h=calcul['h'], ips=calcul['ips'])
    if not plage:
        att['n'] = calcul['n']
    R = controler(out, att)
    dire(texte(R, out))
    if calcul.get('son', {}).get('musique'):
        seuls = sorties / f'{nom}-sans-musique.mp4'
        subprocess.run(RES.ff(['ffmpeg', '-v', 'error', '-y', '-i', str(out), '-i', str(travail / 'public' / 'audio' / 'sons-seuls.wav'), '-map', '0:v:0', '-map', '1:a:0',
                               '-c:v', 'copy', '-c:a', 'aac', '-b:a', '320k', '-shortest', '-movflags', '+faststart', str(seuls)]), check=True)
        dire(f'Version sans musique (pour poser la musique dans Instagram) : {seuls}')
    if calcul.get('credits'):
        cr = sorties / f'{nom}-credits.txt'
        cr.write_text(calcul['credits'], encoding='utf-8')
        dire(f'Sources et droits du son : {cr}')
        if 'jamais en ligne' in calcul['credits']:
            dire('Musique du commerce : seule la version sans musique peut aller en ligne.')
    son = calcul.get('son') or {}
    if son.get('a_ecouter'):
        dire('À écouter au casque, le son du plan est encore fort au moment de la coupe : '
             + ' ; '.join(f'{e["t"]:.1f} s ({e["bord"]} du plan {e["plan"]})' for e in son['a_ecouter']))
    elif son.get('voix') and 'a_ecouter' in son:
        dire('Coupes de la voix : calmes des deux côtés. À écouter quand même une fois au casque avant de valider (le kit mesure le son, il ne l\'entend pas).')
    dire(f'Vidéo finale : {out}')
    return 1 if verdict(R) == 'À CORRIGER' else 0


def cmd_couverture(projet, image):
    """Image de couverture du Reel, en pleine taille, sans les zones."""
    calcul, travail = preparer(projet)
    if _refuse(calcul, travail, projet):
        return 1
    d = travail / 'couverture'
    _node(travail, 'images', liste=image, echelle=1, sortie=d)
    sorties = Path(projet).resolve() / 'sorties'; sorties.mkdir(exist_ok=True)
    out = sorties / 'couverture.jpg'
    (d / f'{int(image):05d}.jpg').replace(out)
    h = calcul['h']
    dire(f'Couverture : {out}\nInstagram ne montre que le milieu de cette image (4:5 dans le fil, 3:4 dans la grille du profil) : garder le titre entre y={round(h * 0.148)} et y={round(h * 0.852)}.')
    return 0


PHOTOS = {'.jpg', '.jpeg', '.png', '.webp', '.heic'}
VIDEOS = {'.mov', '.mp4', '.m4v', '.mkv', '.webm', '.avi'}
SONS = {'.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg'}


def cmd_rushes(projet, dossier='sources'):
    """Planche de tous les fichiers sources : pour choisir les extraits (clé « de ») sans ouvrir les vidéos une par une."""
    import math
    from planche import planche
    import hdr as HDR
    projet = Path(projet).resolve()
    src = projet / dossier
    if not src.exists():
        dire(f'Dossier introuvable : {src}'); return 1
    fichiers = sorted(p for p in src.rglob('*') if p.is_file() and not p.name.startswith('.') and p.suffix.lower() in PHOTOS | VIDEOS | SONS)
    if not fichiers:
        dire(f'Aucune vidéo, photo ni musique dans {src}'); return 1
    tmp = _travail(projet) / 'rushes'
    tmp.mkdir(parents=True, exist_ok=True)
    for f in tmp.glob('*.jpg'):
        f.unlink()
    w, h = 180, 320
    paralleles = RES.taches(4)                  # vignettes faites ensemble (sur le Mac : autant que de cœurs du mode discret)
    reduit = f'scale={w}:{h}:force_original_aspect_ratio=decrease:flags=area'
    cadre = f'pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x101010'
    taches = []          # (rang, fichier, instant ou None, filtres, étiquette)
    dire(f'{len(fichiers)} fichier(s) dans {dossier}/ :')
    for f in fichiers:
        ext = f.suffix.lower()
        rel = f.relative_to(projet)
        try:
            sd = F.sonde(f)
        except ValueError:
            dire(f'  {rel} : illisible'); continue
        if ext in SONS:
            dire(f'  {rel} : musique ou son, {sd["duree"]:.1f} s'); continue
        if ext in PHOTOS:
            taches.append((len(taches), f, None, f'{reduit},{cadre}', f.stem[-12:]))
            dire(f'  {rel} : photo {sd.get("l", "?")}×{sd.get("h", "?")}')
            continue
        d = sd['duree']
        nb = min(10, max(2, math.ceil(d / 2)))
        # vidéo HDR : conversion choisie dans hdr.py (par ffmpeg, sinon copie SDR par avconvert, gardée pour la préparation)
        try:
            entree, conv, lue = HDR.source(f, sd, _travail(projet) / 'sdr', dire)
        except RuntimeError as e:
            dire(f'  {rel} : {e}'); continue
        # on réduit d'abord, on convertit les couleurs HDR ensuite : mille fois moins de points à calculer
        filtres = f'{reduit},{conv},{cadre}' if conv else f'{reduit},{cadre}'
        for i in range(nb):
            taches.append((len(taches), Path(entree), (i + 0.5) * d / nb, filtres, f.stem[-8:]))
        dire(f'  {rel} : vidéo {d:.1f} s, {sd["l"]}×{sd["h"]}, {sd["ips"]:.0f} i/s' + (', HDR' if sd.get('hdr') else '') + (', avec son' if sd.get('audio') else ', sans son')
             + (' (ralenti possible)' if lue['ips'] >= 50 else ''))

    def vignette(tache):
        rang, f, t, filtres, nom = tache
        out = tmp / f'{rang:04d}.jpg'
        if t is None:
            r = subprocess.run(RES.ff(['ffmpeg', '-v', 'error', '-y', '-i', str(f), '-frames:v', '1', '-vf', filtres, '-q:v', '3', str(out)], paralleles), capture_output=True, text=True)
            return (out, nom) if r.returncode == 0 and out.exists() else None
        # seules les images clés sont décodées (rapide, même en 4K) ; l'étiquette porte l'instant réel de l'image montrée
        r = subprocess.run(RES.ff(['ffmpeg', '-hide_banner', '-loglevel', 'info', '-y', '-skip_frame', 'nokey', '-copyts', '-ss', f'{t:.3f}', '-i', str(f), '-frames:v', '1',
                                   '-vf', filtres + ',showinfo', '-q:v', '3', str(out)], paralleles), capture_output=True, text=True)
        m = re.search(r'pts_time:([\d.]+)', r.stderr)
        return (out, f'{nom} {float(m.group(1)) if m else t:.1f}s') if r.returncode == 0 and out.exists() else None
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(paralleles) as ex:
        faits = [x for x in ex.map(vignette, taches) if x]
    vignettes, etiquettes = [x[0] for x in faits], [x[1] for x in faits]
    sorties = projet / 'sorties'; sorties.mkdir(exist_ok=True)
    par_planche = 96
    for n in range(0, len(vignettes), par_planche):
        nom = 'rushes.jpg' if len(vignettes) <= par_planche else f'rushes-{n // par_planche + 1}.jpg'
        out = planche(vignettes[n:n + par_planche], sorties / nom, etiquettes[n:n + par_planche], colonnes=12, vignette=(w, h),
                      titre=f'{projet.name} · sources · nom du fichier et instant (s) : à reporter dans « source » et « de »')
        dire(f'Planche des sources : {out}')
    return 0


def cmd_controle(video, instagram=False):
    from controle import controler, texte, verdict, simuler_instagram
    R = controler(video)
    dire(texte(R, video))
    if instagram:
        f, ssim = simuler_instagram(video)
        dire(f'Simulation Instagram : {f}  (ressemblance {ssim:.3f} sur 1 ; sous 0,93 la compression se verra : alléger le grain ou grossir les textes fins)')
    return 1 if verdict(R) == 'À CORRIGER' else 0


def _transcrire_prise(projet, fichier, relatif, forcer, silence, zoom, prefixe='P'):
    """Face caméra : toute une prise, phrase par phrase, avec les plans prêts à coller dans la fiche (silences et faux départs déjà retirés)."""
    from paroles import transcrire, phrases, reprises, plans_proposes, enveloppe, voix_nette
    d = _travail(projet) / 'prises'
    d.mkdir(parents=True, exist_ok=True)
    f = d / f'{fichier.name}.json'
    s = F.sonde(fichier)
    if not s.get('audio'):
        dire(f'{relatif} : pas de piste son, rien à transcrire.'); return 1
    if f.exists() and not forcer:
        mots = json.loads(f.read_text(encoding='utf-8'))
    else:
        mots = transcrire(fichier, 0.0, float(s['duree']))
        f.write_text(json.dumps(mots, ensure_ascii=False, indent=0), encoding='utf-8')
    limite = zoom is None
    if limite:                                                  # un plan sur deux resserré, tant que l'image reste nette
        try:
            large = int(json.loads((projet / 'montage.json').read_text(encoding='utf-8')).get('format', {}).get('l', 1080))
        except (OSError, ValueError, AttributeError):
            large = 1080
        net = int(s.get('l', 0) / (large * 0.92) * 100) / 100
        zoom = 1.12 if net >= 1.12 else (net if net >= 1.04 else 1)
    niveau = enveloppe(fichier)
    if voix_nette(niveau):                                      # coupes posées sur le son réel, pas sur les temps de la transcription
        ph = phrases(mots, silence, niveau=niveau, duree=s['duree'])
    else:                                                       # trop de bruit autour de la voix : la transcription seule, avec plus de marge
        ph = phrases(mots, silence, marge_avant=0.15, marge_apres=0.35, duree=s['duree'])
        dire(f'{relatif} : beaucoup de bruit autour de la voix. Les coupes suivent la transcription seule : les écouter une par une.')
    if not ph:
        dire(f'{relatif} : aucune parole trouvée.'); return 1
    recales = [m for x in ph for m in x['paroles']]             # les temps des mots suivent le son réel : sous-titres à l'heure
    if recales != mots:
        f.write_text(json.dumps(recales, ensure_ascii=False, indent=0), encoding='utf-8')
    doubles = dict(reprises(ph))
    dire(f'{relatif} : {len(mots)} mots, {len(ph)} phrases, {sum(x["a"] - x["de"] for x in ph):.1f} s de parole une fois les silences coupés.')
    for n, x in enumerate(ph):
        note = f'   ← redite en {prefixe}{doubles[n] + 1:02d} : retirée des plans (à remettre si la répétition est voulue)' if n in doubles else ''
        if x.get('a_ecouter'):
            note += f'   ← la voix continue ({x["a_ecouter"]}) : coupe à écouter'
        dire(f'  {prefixe}{n + 1:02d} {x["de"]:7.2f} → {x["a"]:7.2f} ({x["a"] - x["de"]:4.1f} s)  {x["texte"][:96]}{note}')
    plans = plans_proposes(ph, relatif, zoom, sauf=doubles, prefixe=prefixe)
    if limite and s.get('l') and zoom < 1.12 and len(plans) > 1:
        dire(f'Vidéo de {s["l"]} px de large : ' + (f'zoom limité à {zoom:g} pour rester net' if zoom > 1 else 'pas de zoom, l\'image serait floue') + ' (filmer en 4K pour un plan sur deux bien resserré).')
    dire(f'Plans à coller dans la fiche ({len(plans)}, {sum(float(q["duree"][:-1]) for q in plans):.1f} s ; enlever ceux qui ne servent pas) :')
    dire(',\n'.join('  ' + json.dumps(q, ensure_ascii=False) for q in plans))
    dire('Sous-titres de tous ces plans, en un seul calque : {"t": "sous-titres", "plan": "tous", "mots": "auto", "style": "pastille"}')
    dire(f'Paroles (à corriger à la main : noms propres, marques) : {f}')
    return 0


def cmd_transcrire(projet, plan, forcer=False, silence=0.45, zoom=None, prefixe='P'):
    projet = Path(projet).resolve()
    if (projet / plan).is_file():
        return _transcrire_prise(projet, projet / plan, plan, forcer, silence, zoom, prefixe)
    _, calcul, rq, _ = resoudre(projet, silencieux=True)
    q = next((x for x in calcul['plans'] if x['id'] == plan), None)
    if not q:
        dire(f'Plan « {plan} » introuvable dans la fiche.'); return 1
    from paroles import paroles_du_plan
    mots, f = paroles_du_plan(q, calcul['ips'], _travail(projet), forcer)
    dire(f'{len(mots)} mots : ' + ' '.join(m[0] for m in mots)[:600])
    dire(f'Fichier (corrigeable à la main) : {f}\nDans la fiche : {{"t": "sous-titres", "plan": "{plan}", "mots": "auto"}}')
    return 0


def cmd_sons(famille=None):
    """Les bruitages qu'une fiche peut nommer : ceux du kit, et la bibliothèque libre du skill sound-effects quand il est installé."""
    cat = json.loads((F.SONS_KIT / 'catalogue.json').read_text(encoding='utf-8'))
    man = F.SONS_PLUS / 'manifest.json'
    plus = json.loads(man.read_text(encoding='utf-8')).get('bundled', []) if man.exists() else []
    if famille:
        choisis = sorted((e for e in plus if e.get('category') == famille), key=lambda e: e.get('duration_s', 0))
        if not choisis:
            dire(f'Famille « {famille} » inconnue. Familles : {", ".join(sorted({e["category"] for e in plus})) or "aucune (skill sound-effects absent)"}')
            return 1
        for e in choisis:
            dire(f'  {e["file"].rsplit(".", 1)[0]:46s} {e.get("duration_s", 0):5.2f} s')
        dire(f'Dans la fiche : {{"son": "{choisis[0]["file"].rsplit(".", 1)[0]}", "at": "8t", "db": -12}}')
        return 0
    dire('Kit du dépôt (CC0) : ' + ', '.join(sorted(cat['situations'])) + '. Dans la fiche : {"son": "impact", "at": "8t", "db": -10}')
    if plus:
        n = {}
        for e in plus:
            n[e['category']] = n.get(e['category'], 0) + 1
        dire(f'Bibliothèque libre en plus (skill sound-effects, {len(plus)} sons CC0) : ' + ', '.join(f'{k} {v}' for k, v in sorted(n.items())))
        dire('Les sons d\'une famille : « sons whoosh ».')
    else:
        dire('Bibliothèque du skill sound-effects : absente (dossier .claude/skills/sound-effects).')
    return 0


EXEMPLE = {
    "nom": "mon-reel",
    "note": "Durées : 24 = images, \"1.5s\" = secondes, \"4t\" = 4 temps de la musique. Une musique s'écrit avec ses droits : \"droits\": \"libre\" et son \"credit\", ou \"droits\": \"sous_droits\". Voir montage/README.md.",
    "theme": "neutre",
    "finition": {"grain": 0.1, "vignette": 0.35, "fondu_fin": 10},
    "plans": [
        {"id": "A", "photo": "sources/photo1.jpg", "duree": "2s", "effets": [{"t": "kb", "a": 1.0, "b": 1.08}], "sortie": "zoom"},
        {"id": "B", "source": "sources/video1.mov", "de": 0, "duree": "3s", "vitesse": 1, "sortie": "whipG"},
        {"id": "C", "photo": "sources/photo2.jpg", "duree": "2.5s", "effets": [{"t": "kb", "a": 1.08, "b": 1.0}]}
    ],
    "calques": [
        {"t": "titre", "texte": "TON ACCROCHE\nEN DEUX LIGNES", "y": 520, "taille": 150, "de": 2, "a": "2s", "anim": "pop"},
        {"t": "etiquette", "texte": "une précision", "x": 72, "y": 240, "align": "gauche", "plan": "B"},
        {"t": "signature", "nom": "TON ENSEIGNE", "ligne": "Ville · offre réelle", "plan": "C", "de": 20}
    ]
}


def cmd_caler(projet, videos):
    """Playback d'un clip : à quel instant de la chanson commence chaque vidéo. Donne la ligne « calage » à coller dans la fiche."""
    from calage import caler
    projet = Path(projet)
    mus = F.charger(projet).get('musique') or {}
    if not mus.get('fichier'):
        raise ValueError('la fiche n\'a pas de musique : écrire d\'abord "musique": {"fichier": …}')
    out, doute = {}, False
    for v in videos:
        f = projet / v if (projet / v).exists() else Path(v)
        r = caler(projet / mus['fichier'], f)
        m = f' ; moitiés {r["moities"][0]:+.2f} / {r["moities"][1]:+.2f} s' if r['moities'] else ''
        dire(f'{v} : commence à {r["decalage"]:+.2f} s de la chanson (netteté {r["nettete"]:.2f}{m})' + ('' if r['sur'] else '  ← INCERTAIN : vérifier à l\'œil sur une syllabe'))
        out[v] = r['decalage']; doute |= not r['sur']
    dire('À mettre dans la fiche (les plans de ces vidéos n\'ont alors plus besoin de « de ») :')
    dire('"calage": ' + json.dumps(out, ensure_ascii=False))
    return 1 if doute else 0


def cmd_nouveau(dossier, theme):
    d = Path(dossier)
    if (d / 'montage.json').exists():
        dire(f'{d}/montage.json existe déjà : rien n\'est écrasé.'); return 1
    (d / 'sources').mkdir(parents=True, exist_ok=True)
    ex = dict(EXEMPLE); ex['theme'] = theme; ex['nom'] = d.name
    (d / 'montage.json').write_text(json.dumps(ex, ensure_ascii=False, indent=2), encoding='utf-8')
    dire(f'Projet créé : {d}\n  1. mets tes vidéos et photos dans {d}/sources/\n  2. adapte {d}/montage.json\n  3. python3 {KIT.name}/montage.py tout {d}\n'
         f'  Quelqu\'un parle face caméra ? python3 {KIT.name}/montage.py transcrire {d} sources/<la prise> donne les plans sans silences et les sous-titres.')
    return 0


def main():
    ap = argparse.ArgumentParser(description='Kit de montage de Reels (fiche → vidéo contrôlée)')
    sp = ap.add_subparsers(dest='cmd', required=True)
    p = sp.add_parser('nouveau'); p.add_argument('dossier'); p.add_argument('--theme', default='neutre', choices=sorted(F.THEMES))
    p = sp.add_parser('rushes'); p.add_argument('projet'); p.add_argument('--dossier', default='sources')
    p = sp.add_parser('verifier'); p.add_argument('projet')
    p = sp.add_parser('preparer'); p.add_argument('projet')
    p = sp.add_parser('planche'); p.add_argument('projet'); p.add_argument('--images'); p.add_argument('--sans-zones', action='store_true')
    p = sp.add_parser('apercu'); p.add_argument('projet'); p.add_argument('--plage')
    p = sp.add_parser('final'); p.add_argument('projet'); p.add_argument('--plage'); p.add_argument('--crf')
    p = sp.add_parser('tout'); p.add_argument('projet')
    p = sp.add_parser('couverture'); p.add_argument('projet'); p.add_argument('--image', default='0')
    p = sp.add_parser('controle'); p.add_argument('video'); p.add_argument('--instagram', action='store_true')
    p = sp.add_parser('transcrire'); p.add_argument('projet'); p.add_argument('plan'); p.add_argument('--forcer', action='store_true')
    p.add_argument('--silence', type=float, default=0.45); p.add_argument('--zoom', type=float, default=None); p.add_argument('--prefixe', default='P')
    p = sp.add_parser('sons'); p.add_argument('famille', nargs='?')
    p = sp.add_parser('caler'); p.add_argument('projet'); p.add_argument('videos', nargs='+')
    p = sp.add_parser('tempo'); p.add_argument('musique'); p.add_argument('debut', nargs='?', type=float, default=0.0)
    a = ap.parse_args()
    try:
        RES.discret(a.cmd, getattr(a, 'projet', None) or getattr(a, 'video', None), dire)   # sur le Mac : priorité basse, un seul montage à la fois
        if a.cmd == 'nouveau':
            return cmd_nouveau(a.dossier, a.theme)
        if a.cmd == 'rushes':
            return cmd_rushes(a.projet, a.dossier)
        if a.cmd == 'verifier':
            _, calcul, rq, _ = resoudre(a.projet)
            bon = not rq.bloquant and _garde_verifier(Path(a.projet).resolve(), calcul)
            dire('Fiche bonne pour le rendu.' if bon else 'Fiche à corriger.')
            return 0 if bon else 1
        if a.cmd == 'preparer':
            preparer(a.projet); return 0
        if a.cmd == 'planche':
            cmd_planche(a.projet, a.images, not a.sans_zones); return 0
        if a.cmd == 'apercu':
            return cmd_apercu(a.projet, a.plage)
        if a.cmd == 'final':
            return cmd_final(a.projet, a.plage, a.crf)
        if a.cmd == 'tout':
            cmd_planche(a.projet)
            return cmd_final(a.projet)
        if a.cmd == 'couverture':
            return cmd_couverture(a.projet, a.image)
        if a.cmd == 'controle':
            return cmd_controle(a.video, a.instagram)
        if a.cmd == 'transcrire':
            return cmd_transcrire(a.projet, a.plan, a.forcer, a.silence, a.zoom, a.prefixe)
        if a.cmd == 'sons':
            return cmd_sons(a.famille)
        if a.cmd == 'caler':
            return cmd_caler(a.projet, a.videos)
        if a.cmd == 'tempo':
            from tempo import analyser
            r = analyser(a.musique, a.debut)
            dire(f'{r["bpm"]:.2f} temps par minute ; un temps = {r["periode"]:.4f} s ; premier temps à {r["phase"]:.3f} s')
            if r['incertain']:
                dire(f'Calage incertain (triolets ou contretemps). Autres départs possibles : {r["candidats"]} s')
            return 0
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        dire(f'Arrêt : {e}')
        return 1


if __name__ == '__main__':
    sys.exit(main())
