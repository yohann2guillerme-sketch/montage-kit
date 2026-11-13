"""Préparation d'un montage : sort les images des plans (rushes et photos), les masques, les polices et le grain.

Tout est rangé dans <projet>/.travail/public/ (jamais dans le dépôt). Chaque plan déjà préparé est gardé
en cache : relancer après avoir changé un texte ne refait aucune extraction.
"""
import hashlib
import json
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fiche import POLICES_KIT, POLICES_PLUGIN, temps_sources

import hdr as HDR
import ressources as RES
from hdr import VERS_SDR  # noqa: F401  (ancien nom ; la conversion des vidéos HDR se choisit dans hdr.py)
ETALONNAGES = {
    'naturel': '',
    # réglage du Reel HYROX v2 : contraste, peau un peu moins saturée, noirs légèrement relevés
    'sport': "eq=contrast=1.12:saturation=0.92:gamma=0.95,curves=master='0/0.015 0.2/0.14 0.5/0.49 0.8/0.84 1/0.985',colorbalance=rs=-0.03:bs=0.04:rh=0.03:gh=0.01:bh=-0.03",
    'vif': "eq=contrast=1.08:saturation=1.12,curves=master='0/0 0.25/0.22 0.5/0.5 0.75/0.79 1/1'",
    'doux': 'eq=contrast=0.97:saturation=0.95:gamma=1.03',
    # mélancolie (clip) : couleurs éteintes, ombres froides, noirs à peine relevés, hautes lumières retenues
    'melancolie': "eq=contrast=1.06:saturation=0.60:gamma=0.97,colorbalance=rs=-0.035:gs=-0.005:bs=0.045:rm=-0.015:bm=0.02:rh=0.01:gh=0.0:bh=-0.015,curves=master='0/0.025 0.25/0.215 0.5/0.48 0.8/0.79 1/0.955'",
}


def cadre(z, cx, cy, W, H, ratio):
    """Rectangle de rognage (x, y, largeur, hauteur) au format voulu, zoom z, centré sur (cx, cy) en fractions de l'image."""
    cw = W / z; ch = cw / ratio
    if ch > H:
        ch = H / z; cw = ch * ratio
    x = cx * W - cw / 2; y = cy * H - ch / 2
    x = max(0, min(W - cw, x)); y = max(0, min(H - ch, y))
    return x, y, cw, ch


def _cle(*morceaux):
    return hashlib.sha1(json.dumps(morceaux, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _empreinte(fichier):
    st = os.stat(fichier)
    return [str(fichier), st.st_size, int(st.st_mtime)]


def _vers_srvb(im):
    """Photo d'iPhone (Display P3) → sRVB, sinon les couleurs sortent ternes. Sans profil : inchangée."""
    from PIL import ImageCms
    import io
    icc = im.info.get('icc_profile')
    if not icc:
        return im
    try:
        src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        dst = ImageCms.createProfile('sRGB')
        mode = 'RGBA' if im.mode in ('RGBA', 'LA', 'P') else 'RGB'
        im = im.convert(mode)
        return ImageCms.profileToProfile(im, src, dst, outputMode=mode)
    except Exception:
        return im


def _plan_video(q, cfg, dossier):
    if '_entree' not in q:      # appelée seule, hors de preparer() : le même choix, au même endroit (hdr.py)
        q['_entree'], q['_conv'], q['_sonde_entree'] = HDR.source(q['_fichier'], q['_sonde'], Path(dossier).parents[2] / 'sdr')
    s = q['_sonde_entree']; W, H, ips = cfg['l'], cfg['h'], cfg['ips']      # la vidéo lue : l'original, ou sa copie SDR
    ts = temps_sources(q, ips)
    marge = 3 / s['ips']
    t0 = max(0.0, min(ts) - marge); t1 = min(s['duree'] - 0.02, max(ts) + marge)
    vmax = max(abs(v) for v in ([q['vitesse']] if isinstance(q['vitesse'], (int, float)) else [v for _, v in q['vitesse']]))
    efps = 5 * ips / vmax if vmax > 8 else None       # accéléré très fort : on ne sort que les images utiles
    x, y, cw, ch = cadre(q['_zoom'], q['_cx'], q['_cy'], s['l'], s['h'], W / H)
    cw, ch, x, y = (int(v) // 2 * 2 for v in (cw, ch, x, y))
    # accentuation légère après réduction ; « finition.nettete: false » garde l'image telle qu'elle a été filmée
    net = '' if not cfg['finition'].get('nettete', True) else 'unsharp=5:5:0.45' if cw >= W * 1.5 else 'unsharp=5:5:0.3' if cw >= W else ''
    # vidéo HDR : conversion par ffmpeg ou copie SDR (avconvert), choisie dans hdr.source
    entree = q['_entree']
    sdr = q['_conv'] or 'format=yuv420p'
    trf = dossier.parent / f'{q["id"]}.trf'
    lut = f"lut3d=file='{q['_lut']}':interp=tetrahedral" if q.get('_lut') else ''
    etal = ETALONNAGES.get(q['_etalonnage'], q['_etalonnage'] or '')
    detect = None
    if q.get('_stabilise'):   # plan filmé à la main : on mesure les mouvements de la caméra, puis on les lisse (léger zoom pour cacher les bords)
        # lissage sur 1,5 s par défaut ; un nombre = durée du lissage en secondes (4 = presque comme sur un trépied).
        # Mesuré sur un plan suivi à la main : mouvements parasites réduits de moitié, les plus forts des deux tiers.
        fen = 1.5 if q['_stabilise'] is True else float(q['_stabilise'])
        detect, transf = 'shakiness=6:accuracy=15', f'smoothing={max(1, round(fen * (efps or s["ips"]) / 2))}'
        filtres = [sdr, f"vidstabtransform=input='{trf}':{transf}:zoom=1:optzoom=1:interpol=bicubic", f'crop={cw}:{ch}:{x}:{y}',
                   f'scale={W}:{H}:flags=lanczos', lut, etal, net]
    else:
        filtres = [f'crop={cw}:{ch}:{x}:{y}', sdr, f'scale={W}:{H}:flags=lanczos', lut, etal, net]
    cmd_f = None
    if q.get('_cadrage') == 'visage' and not efps:
        # le rognage suit le visage (lissé) : l'empreinte du chemin entre dans la clé du cache
        from cadrage import suivre, chemin, commandes
        cache = dossier.parent / 'suivis' / (_cle('suivi', _empreinte(q['_fichier']), round(t0, 3), round(t1, 3)) + '.json')
        if cache.exists():
            suivi = json.loads(cache.read_text())
            suivi = tuple(map(__import__('numpy').array, suivi)) if suivi else None
        else:
            suivi = suivre(entree, t0, t1, s['l'], s['h'])
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps([list(map(float, v)) for v in suivi] if suivi else None))
        if suivi is None:
            q['_avis'] = 'cadrage : aucun visage suivi, cadrage fixe gardé'
        else:
            n_img = int((t1 - t0) * s['ips']) + 3
            xs, ys = chemin(suivi, n_img, s['ips'], cw, ch, s['l'], s['h'])
            cmd_f = dossier.parent / f'{q["id"]}.cmd'
            cmd_f.parent.mkdir(parents=True, exist_ok=True)
            commandes(xs, ys, s['ips'], cmd_f)
            filtres = [f'crop={cw}:{ch}:{xs[0]}:{ys[0]}' if f.startswith('crop=') else f for f in filtres]
            filtres.insert(0, f"sendcmd=f='{cmd_f}'")
    if efps:
        filtres.insert(0, f'fps={efps:.5f}')
    vf = ','.join(f for f in filtres if f)
    cle = _cle('video', _empreinte(q['_fichier']), round(t0, 3), round(t1, 3), vf, detect, _empreinte(q['_lut']) if q.get('_lut') else None,
               cmd_f.read_text() if cmd_f else None, *([Path(entree).name] if entree != q['_fichier'] else []))     # copie SDR : son nom (sa clé) aussi
    meta_f = dossier / 'meta.json'
    if meta_f.exists():
        m = json.loads(meta_f.read_text())
        if m.get('cle') == cle:
            return m, False
    if dossier.exists():
        shutil.rmtree(dossier)
    dossier.mkdir(parents=True)
    if detect:
        # la mesure se fait sur l'image brute (pas besoin de la conversion des couleurs : deux fois plus rapide), au même rythme que l'extraction
        avant = (f'fps={efps:.5f},' if efps else '') + 'format=yuv420p'
        r = subprocess.run(RES.ff(['ffmpeg', '-v', 'error', '-y', '-ss', f'{t0:.4f}', '-i', entree, '-t', f'{t1 - t0:.4f}',
                                   '-vf', f"{avant},vidstabdetect={detect}:result='{trf}'", '-f', 'null', '-'], RES.taches(3)), capture_output=True, text=True)
        if r.returncode != 0 or not trf.exists():
            raise RuntimeError(f'plan {q["id"]} : stabilisation impossible ({r.stderr.strip()[-300:]})')
    r = subprocess.run(RES.ff(['ffmpeg', '-v', 'error', '-y', '-ss', f'{t0:.4f}', '-i', entree, '-t', f'{t1 - t0:.4f}', '-vf', vf, '-q:v', '2',
                               '-start_number', '0', str(dossier / '%04d.jpg')], RES.taches(3)), capture_output=True, text=True)
    n = len(list(dossier.glob('*.jpg')))
    if r.returncode != 0 or n == 0:
        raise RuntimeError(f'plan {q["id"]} : extraction impossible ({r.stderr.strip()[-300:]})')
    m = dict(cle=cle, debut=t0, ips=efps or s['ips'], n=n)
    meta_f.write_text(json.dumps(m))
    return m, True


def _plan_photo(q, cfg, dossier):
    from PIL import Image, ImageOps, ImageFilter
    W, H = cfg['l'], cfg['h']
    cible = (int(round(W * q['_zmax'])) // 2 * 2, int(round(H * q['_zmax'])) // 2 * 2)
    cle = _cle('photo', _empreinte(q['_fichier']), q['_zoom'], q['_cx'], q['_cy'], cible)
    meta_f = dossier / 'meta.json'
    if meta_f.exists():
        m = json.loads(meta_f.read_text())
        if m.get('cle') == cle:
            return m, False
    if dossier.exists():
        shutil.rmtree(dossier)
    dossier.mkdir(parents=True)
    im = ImageOps.exif_transpose(Image.open(q['_fichier']))
    im = _vers_srvb(im).convert('RGB')
    x, y, cw, ch = cadre(q['_zoom'], q['_cx'], q['_cy'], im.width, im.height, W / H)
    im = im.crop((int(round(x)), int(round(y)), int(round(x + cw)), int(round(y + ch))))
    reduit = im.width > cible[0]
    im = im.resize(cible, Image.LANCZOS)
    if reduit:
        im = im.filter(ImageFilter.UnsharpMask(radius=1.2, percent=35, threshold=2))
    im.save(dossier / '0000.jpg', quality=95, subsampling=0)
    m = dict(cle=cle, debut=0.0, ips=float(cfg['ips']), n=1)
    meta_f.write_text(json.dumps(m))
    return m, True


def _nettoie_masque(a):
    """Garde le sujet principal (et les morceaux proches : bras, objet tenu), adoucit le bord."""
    import numpy as np
    from scipy import ndimage
    lab, n = ndimage.label(a > 0.5)
    if n > 1:
        tailles = ndimage.sum(np.ones_like(a), lab, range(1, n + 1))
        gros = 1 + int(np.argmax(tailles))
        garde = lab == gros
        for k in range(1, n + 1):
            if k != gros and tailles[k - 1] > 0.02 * tailles[gros - 1]:
                d = ndimage.distance_transform_edt(~garde)
                if d[lab == k].min() < 40:
                    garde |= lab == k
        garde = ndimage.binary_dilation(garde, iterations=4)
        a = a * garde
    a = ndimage.grey_erosion(a, size=(3, 3))
    a = ndimage.gaussian_filter(a, 1.1)
    return np.clip(a, 0, 1)


def _masques(q, cfg, public, meta, journal):
    """Détoure le sujet (BiRefNet) sur chaque image utilisée du plan : sert au texte « derrière le sujet »."""
    import numpy as np
    from PIL import Image
    from rembg import new_session, remove
    ips = cfg['ips']
    if q['photo']:
        indices = [0]
    else:
        indices = sorted({min(meta['n'] - 1, max(0, round((t - meta['debut']) * meta['ips']))) for t in temps_sources(q, ips)})
    dossier = public / 'masques' / q['id']
    marque = dossier / 'cle.txt'
    modele, options = RES.detourage()            # sur le Mac : un modèle léger (1 Go au lieu de 7 à 12)
    cle = meta['cle'] if modele == 'birefnet-general-lite' else f'{meta["cle"]}|{modele}'
    if not (marque.exists() and marque.read_text() == cle):
        if dossier.exists():
            shutil.rmtree(dossier)
        dossier.mkdir(parents=True)
        marque.write_text(cle)
    a_faire = [i for i in indices if not (dossier / f'{i:04d}.png').exists()]
    if a_faire:
        journal(f'  détourage du plan {q["id"]} : {len(a_faire)} image(s)…' + ('' if modele == 'birefnet-general-lite' else f' (modèle {modele})'))
        session = new_session(modele, **options)
        for i in a_faire:
            im = Image.open(public / 'plans' / q['id'] / f'{i:04d}.jpg').convert('RGB')
            mk = remove(im, session=session, only_mask=True)
            a = _nettoie_masque(np.asarray(mk.convert('L')).astype(np.float32) / 255)
            rgba = np.dstack([np.asarray(im), (a * 255).astype(np.uint8)])
            Image.fromarray(rgba, 'RGBA').save(dossier / f'{i:04d}.png', compress_level=3)
    return indices


def _grain(public):
    """Huit textures de grain argentique (bruit doux), tirées toujours de la même façon."""
    import numpy as np
    from PIL import Image
    from scipy import ndimage
    d = public / 'fx'
    if (d / 'grain7.png').exists():
        return
    d.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20261109)
    for i in range(8):
        b = ndimage.gaussian_filter(rng.standard_normal((960, 540)), 0.45)
        b = b / b.std() * 38 + 127.5
        Image.fromarray(np.clip(b, 0, 255).astype(np.uint8), 'L').save(d / f'grain{i}.png')


def _image_calque(src, dst, largeur_affichee):
    """Image d'un calque en sRVB, deux fois sa largeur affichée au plus (nette à l'écran). Écrite d'un coup : un arrêt au milieu ne
    laisse jamais une image coupée que le cache reprendrait. (Changer cette fonction : changer fiche.VERSION_IMAGES.)"""
    from PIL import Image, ImageOps
    im = ImageOps.exif_transpose(Image.open(src))
    im = _vers_srvb(im)
    im = im.convert('RGBA' if (im.mode in ('RGBA', 'LA', 'P')) else 'RGB')
    maxi = int(largeur_affichee * 2)
    if im.width > maxi:
        im = im.resize((maxi, round(im.height * maxi / im.width)), Image.LANCZOS)
    tmp = dst.with_name(f'.{dst.stem}.part{dst.suffix}')
    if dst.suffix.lower() in ('.jpg', '.jpeg'):
        im.convert('RGB').save(tmp, quality=95, subsampling=0)
    else:
        im.save(tmp)
    os.replace(tmp, dst)


def images_calques(calcul, public):
    """Images des calques (logos, produits) dans public/images, nommées par fiche.nom_image (source, taille, date, largeur affichée) :
    une image absente est faite, les autres sont reprises telles quelles ; celles qu'aucun calque n'utilise plus sont effacées, comme
    les plans. Jamais tout le dossier : ce serait tout refaire pour rien. → (images des calques, images faites)."""
    dossier = Path(public) / 'images'
    dossier.mkdir(parents=True, exist_ok=True)
    gardees, faites = set(), 0
    for c in calcul['calques']:
        if not c.get('_fichier'):
            continue
        nom, largeur = (c['logo'], c.get('logo_l')) if c.get('t') == 'signature' else (c['fichier'], c.get('l'))
        if nom not in gardees and not (dossier / nom).exists():
            _image_calque(c['_fichier'], dossier / nom, largeur or 400)
            faites += 1
        gardees.add(nom)
    for f in dossier.iterdir():
        if f.name not in gardees and f.is_file():
            f.unlink()
    return len(gardees), faites


def preparer(calcul, travail, journal=print):
    """Remplit calcul['plans'] (début, cadence, nombre d'images, masques) et le dossier public. Retourne le calcul complété."""
    public = Path(travail) / 'public'
    for d in ('plans', 'masques', 'images', 'polices', 'audio', 'fx'):
        (public / d).mkdir(parents=True, exist_ok=True)
    # polices
    for fam, f, w, s in calcul['polices']:
        src = POLICES_KIT / f if (POLICES_KIT / f).exists() else POLICES_PLUGIN / f
        if not (public / 'polices' / f).exists():
            shutil.copy(src, public / 'polices' / f)
    if calcul['finition']['grain'] > 0:
        _grain(public)

    # plans : jusqu'à 3 extractions en même temps (sur le Mac : autant que de cœurs du mode discret)
    def travail_plan(q):
        d = public / 'plans' / q['id']
        return q, (_plan_photo(q, calcul, d) if q['photo'] else _plan_video(q, calcul, d))
    refaits = 0
    tous = calcul['plans'] + [q['double'] for q in calcul['plans'] if q.get('double')]     # les doubles expositions se préparent comme des plans
    # vidéos HDR : conversion choisie à un seul endroit (hdr.py), une fois par fichier, avant les extractions en parallèle
    for q in tous:
        if not q['photo']:
            q['_entree'], q['_conv'], q['_sonde_entree'] = HDR.source(q['_fichier'], q['_sonde'], Path(travail) / 'sdr', journal)
            v = q['vitesse']
            if q['_sonde_entree']['ips'] < q['_sonde']['ips'] - 0.5 and min(abs(x) for x in ([v] if isinstance(v, (int, float)) else [x for _, x in v])) < 1:
                journal(f'  plan {q["id"]} : ralenti lu sur une copie SDR à {q["_sonde_entree"]["ips"]:.0f} i/s (original à {q["_sonde"]["ips"]:.0f} i/s) : '
                        'moins fluide. Pour un vrai ralenti, monter dans le cloud.')
    with ThreadPoolExecutor(RES.taches(3)) as ex:
        for q, (m, neuf) in ex.map(travail_plan, tous):
            q.update(debut=m['debut'], ips=m['ips'], n=m['n'], _cle=m['cle'])
            refaits += neuf
    for q in calcul['plans']:
        if q.get('_avis'):
            journal(f'  plan {q["id"]} : {q["_avis"]}')
    journal(f'  plans : {len(calcul["plans"])} ({refaits} extrait(s), {len(calcul["plans"]) - refaits} repris du cache)')
    # plans disparus de la fiche : on fait le ménage
    gardes = {q['id'] for q in tous}
    for sous in ('plans', 'masques'):
        for d in (public / sous).iterdir():
            if d.is_dir() and d.name not in gardes:
                shutil.rmtree(d)
    # masques
    for q in calcul['plans']:
        q['masques'] = _masques(q, calcul, public, dict(cle=q['_cle'], debut=q['debut'], ips=q['ips'], n=q['n']), journal) if q['_masque'] else None
    # images des calques (logos, produits) : refaites seulement quand leur clé change, le reste du dossier est gardé
    n, faites = images_calques(calcul, public)
    if n:
        journal(f'  images des calques : {n} ({faites} faite(s), {n - faites} reprise(s) du cache)')
    return calcul
