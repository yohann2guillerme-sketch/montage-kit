"""Contrôle qualité d'une vidéo finale, avant de la montrer ou de la publier.

Vérifie le fichier (format, couleurs, son) et l'image (noir, image figée, flou, flashs), puis donne un verdict court.
Peut aussi simuler la compression d'Instagram pour voir ce que le public verra vraiment.
Bibliothèque standard + numpy/OpenCV (déjà utilisés par le projet). Outils : ffmpeg, ffprobe.
"""
import json
import re
import struct
import subprocess
from pathlib import Path

import numpy as np

import ressources as RES

OK, VOIR, ERREUR = 'ok', 'à voir', 'ERREUR'


def _probe(f):
    r = subprocess.run(['ffprobe', '-v', 'error', '-print_format', 'json', '-show_streams', '-show_format', str(f)], capture_output=True, text=True)
    if r.returncode:
        raise ValueError(f'fichier illisible : {f}')
    return json.loads(r.stdout)


def _ordre_atomes(f):
    ordre = []
    with open(f, 'rb') as fh:
        while len(ordre) < 8:
            h = fh.read(8)
            if len(h) < 8:
                break
            taille, typ = struct.unpack('>I4s', h)
            if taille == 1:
                taille = struct.unpack('>Q', fh.read(8))[0]; fh.seek(taille - 16, 1)
            elif taille < 8:
                break
            else:
                fh.seek(taille - 8, 1)
            ordre.append(typ.decode('latin1'))
    return ordre


def controler(fichier, attendu=None, journal=None):
    """→ liste de (niveau, rubrique, détail). `attendu` : dict(l, h, ips, n) si l'on connaît le montage."""
    f = Path(fichier)
    R = []
    add = lambda niveau, rubrique, detail: R.append((niveau, rubrique, detail))
    d = _probe(f)
    v = next((s for s in d['streams'] if s['codec_type'] == 'video'), None)
    a = next((s for s in d['streams'] if s['codec_type'] == 'audio'), None)
    if not v:
        return [(ERREUR, 'fichier', 'aucune piste vidéo')]
    att = attendu or {}
    W, H = int(v['width']), int(v['height'])
    num, den = v['r_frame_rate'].split('/'); ips = float(num) / float(den)
    duree = float(d['format']['duration']); poids = int(d['format']['size'])
    debit = poids * 8 / duree / 1e6
    # ---------------- fichier
    add(OK if v['codec_name'] == 'h264' and v.get('profile') == 'High' else VOIR, 'codec', f'{v["codec_name"]} {v.get("profile", "")} niveau {int(v.get("level", 0)) / 10:g}')
    lw, lh = att.get('l', 1080), att.get('h', 1920)
    add(OK if (W, H) == (lw, lh) else ERREUR, 'taille', f'{W}×{H}' + ('' if (W, H) == (lw, lh) else f' (attendu {lw}×{lh})'))
    add(OK if abs(ips - att.get('ips', 30)) < 0.01 and v.get('avg_frame_rate') == v['r_frame_rate'] else VOIR, 'cadence', f'{ips:g} images par seconde')
    coul = (v.get('pix_fmt'), v.get('color_range'), v.get('color_space'), v.get('color_primaries'), v.get('color_transfer'))
    bon = coul == ('yuv420p', 'tv', 'bt709', 'bt709', 'bt709')
    add(OK if bon else ERREUR, 'couleurs', 'yuv420p, plage limitée, BT.709' if bon else
        f'{coul[0]}, plage {coul[1]}, matrice {coul[2]}, primaires {coul[3]}, transfert {coul[4]} : hors norme (attendu yuv420p / tv / bt709 partout), contraste faux sur certains lecteurs')
    if 'n' in att and v.get('nb_frames'):
        add(OK if int(v['nb_frames']) == att['n'] else ERREUR, 'longueur', f'{v["nb_frames"]} images, {duree:.2f} s' + ('' if int(v['nb_frames']) == att['n'] else f' (attendu {att["n"]})'))
    else:
        add(OK if 3 <= duree <= 90 else VOIR, 'longueur', f'{duree:.1f} s')
    add(OK if 6 <= debit <= 45 else VOIR, 'poids', f'{poids / 1e6:.0f} Mo, {debit:.1f} Mb/s' + ('' if debit >= 6 else ' : débit faible, qualité à vérifier') + ('' if debit <= 45 else ' : lourd pour rien'))
    ordre = _ordre_atomes(f)
    rapide = 'moov' in ordre and 'mdat' in ordre and ordre.index('moov') < ordre.index('mdat')
    add(OK if rapide else VOIR, 'lecture', 'démarre tout de suite (index au début)' if rapide else 'index à la fin du fichier : démarrage lent en ligne (faststart manquant)')
    # ---------------- son
    if not a:
        add(VOIR, 'son', 'aucune piste son')
    else:
        o = subprocess.run(RES.ff(['ffmpeg', '-nostats', '-i', str(f), '-vn', '-af', 'ebur128=peak=true,silencedetect=n=-55dB:d=2', '-f', 'null', '-']), capture_output=True, text=True).stderr
        fin = o.split('Summary:')[-1]
        try:
            lufs = float(fin.split('I:')[1].split('LUFS')[0]); crete = float(fin.split('Peak:')[1].split('dBFS')[0])
        except (IndexError, ValueError):
            lufs, crete = -70.0, -70.0
        fmt = f'{a["codec_name"]} {int(a.get("sample_rate", 0)) / 1000:g} kHz'
        if lufs < -50:
            add(VOIR, 'son', f'{fmt}, piste presque muette ({lufs:.0f} LUFS)')
        else:
            add(OK if -15.5 <= lufs <= -12.5 else VOIR, 'niveau du son', f'{lufs:.1f} LUFS (cible -14), {fmt}')
            add(OK if crete <= -0.9 else ERREUR, 'crête du son', f'{crete:.1f} dB' + ('' if crete <= -0.9 else ' : au-dessus de -1 dB, risque de saturation après compression'))
        sil = re.findall(r'silence_duration: ([\d.]+)', o)
        if sil and lufs >= -50:
            add(VOIR, 'silences', f'{len(sil)} silence(s) de plus de 2 s (le plus long : {max(map(float, sil)):.1f} s)')
        if abs(float(a.get('duration', duree)) - float(v.get('duration', duree))) > 0.08:
            add(VOIR, 'synchro', f'son {float(a["duration"]):.2f} s, image {float(v["duration"]):.2f} s')
    # ---------------- image : noir, image figée
    o = subprocess.run(RES.ff(['ffmpeg', '-nostats', '-i', str(f), '-an', '-vf', 'blackdetect=d=0.4:pix_th=0.06,freezedetect=n=0.002:d=2', '-f', 'null', '-']), capture_output=True, text=True).stderr
    noirs = [(float(a_), float(b_)) for a_, b_ in re.findall(r'black_start:([\d.]+) black_end:([\d.]+)', o)]
    noirs_g = [x for x in noirs if x[1] < duree - 0.3]      # un noir tout à la fin (fondu) est normal
    add(OK if not noirs_g else VOIR, 'noir', 'aucun passage noir' if not noirs_g else 'passage(s) noir(s) : ' + ', '.join(f'{a_:.1f}→{b_:.1f} s' for a_, b_ in noirs_g[:4]))
    figes = [float(x) for x in re.findall(r'freeze_duration: ([\d.]+)', o)]
    add(OK if not figes else VOIR, 'image figée', 'aucune' if not figes else f'{len(figes)} passage(s) figé(s) de plus de 2 s (normal seulement pour une photo fixe sans mouvement)')
    # ---------------- image : première image, flou, flashs (petite taille, toutes les images)
    w2, h2 = 108, 192
    brut = subprocess.run(RES.ff(['ffmpeg', '-v', 'error', '-i', str(f), '-an', '-vf', f'scale={w2}:{h2}:flags=area', '-f', 'rawvideo', '-pix_fmt', 'gray', '-']), capture_output=True).stdout
    g = np.frombuffer(brut, np.uint8).reshape(-1, h2, w2).astype(np.float32)
    lum = g.mean(axis=(1, 2))
    add(OK if lum[0] > 18 else VOIR, 'première image', f'luminosité {lum[0]:.0f}/255' + ('' if lum[0] > 18 else ' : presque noire. Instagram montre la première image tant que la couverture n\'est pas choisie'))
    sauts = np.where(np.diff(lum) > 38)[0]
    pire = 0
    for i in sauts:
        pire = max(pire, int(((sauts >= i) & (sauts < i + ips)).sum()))
    add(OK if pire <= 3 else ERREUR, 'flashs', f'{len(sauts)} éclair(s), au plus {pire} par seconde' + ('' if pire <= 3 else ' : plus de 3 par seconde, à calmer (confort des yeux)'))
    # netteté : sur des images en pleine taille, une par seconde
    try:
        import cv2
        RES.opencv(cv2)
        net = []
        pas = max(1, int(round(ips)))
        brut = subprocess.run(RES.ff(['ffmpeg', '-v', 'error', '-i', str(f), '-an', '-vf', f"select='not(mod(n\\,{pas}))',scale=540:960:flags=area", '-vsync', '0', '-f', 'rawvideo', '-pix_fmt', 'gray', '-']),
                              capture_output=True).stdout
        G = np.frombuffer(brut, np.uint8).reshape(-1, 960, 540)
        for im in G:
            net.append(float(cv2.Laplacian(im, cv2.CV_32F).var()))
        net = np.array(net); clair = np.array([im.mean() for im in G]) > 25
        if clair.any():
            med = float(np.median(net[clair])); flous = int(((net < 0.25 * med) & clair).sum())
            add(OK if flous <= max(1, 0.15 * clair.sum()) else VOIR, 'netteté', f'indice médian {med:.0f}' + ('' if flous <= max(1, 0.15 * clair.sum()) else f' : {flous} seconde(s) nettement plus floue(s) que le reste'))
    except ImportError:
        pass
    return R


def verdict(R):
    if any(n == ERREUR for n, _, _ in R):
        return 'À CORRIGER'
    if any(n == VOIR for n, _, _ in R):
        return 'BON, avec des points à regarder'
    return 'BON'


def texte(R, fichier):
    lignes = [f'Contrôle de {Path(fichier).name} : {verdict(R)}']
    for n, r, d in R:
        lignes.append(f'  [{n:^7}] {r} : {d}')
    return '\n'.join(lignes)


def simuler_instagram(fichier, sortie=None, debit='3500k'):
    """Recompresse la vidéo comme le fait à peu près Instagram (H.264 ~3,5 Mb/s) et mesure ce qui reste (SSIM : 1 = identique).
    Retourne (fichier simulé, ssim). À regarder avant de publier : textes fins, dégradés, grain."""
    f = Path(fichier)
    sortie = Path(sortie or f.with_name(f.stem + '-comme-instagram.mp4'))
    subprocess.run(RES.ff(['ffmpeg', '-v', 'error', '-y', '-i', str(f), '-c:v', 'libx264', '-preset', 'veryfast', '-b:v', debit, '-maxrate', debit, '-bufsize', '7000k',
                           '-pix_fmt', 'yuv420p', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv',
                           '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', str(sortie)]), check=True)
    o = subprocess.run(RES.ff(['ffmpeg', '-nostats', '-i', str(sortie), '-i', str(f), '-lavfi', 'ssim', '-f', 'null', '-']), capture_output=True, text=True).stderr
    m = re.search(r'All:([\d.]+)', o)
    return sortie, (float(m.group(1)) if m else None)


if __name__ == '__main__':
    import sys
    R = controler(sys.argv[1])
    print(texte(R, sys.argv[1]))
    sys.exit(1 if verdict(R) == 'À CORRIGER' else 0)
