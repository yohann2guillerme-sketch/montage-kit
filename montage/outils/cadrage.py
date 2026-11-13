"""Cadrage qui suit le visage : un plan resserré (zoom) dans une vidéo plus grande garde le visage dans l'image, même quand la
personne bouge (playback d'un clip, prise filmée à la main, Reel vertical tiré d'une vidéo en largeur).

On cherche le visage environ 6 fois par seconde (détecteur YuNet d'OpenCV, licence MIT, 230 Ko, téléchargé une fois dans
~/.cache/montage), on comble les trous, on lisse le chemin (la caméra virtuelle ne doit jamais trembler), puis ffmpeg déplace le
rognage image par image (filtre sendcmd). Aucune image n'est recompressée deux fois.
"""
import os
import subprocess
import urllib.request
from pathlib import Path

import numpy as np

import ressources as RES

MODELE = Path(os.environ.get('MONTAGE_CACHE', Path.home() / '.cache' / 'montage')) / 'face_detection_yunet_2023mar.onnx'
URL = 'https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx'
LARGE = 640           # largeur des images analysées (assez pour un visage de 30 px)
CADENCE = 6.0         # analyses par seconde
YEUX = 0.40           # hauteur du visage dans le cadre (0 = haut) : un peu au-dessus du milieu


def _modele():
    if not MODELE.exists() or MODELE.stat().st_size < 100_000:
        MODELE.parent.mkdir(parents=True, exist_ok=True)
        try:
            urllib.request.urlretrieve(URL, MODELE)
        except Exception as e:
            raise RuntimeError(f'détecteur de visage introuvable ({e}). Le mettre à la main dans {MODELE}')
        if MODELE.stat().st_size < 100_000:
            MODELE.unlink()
            raise RuntimeError(f'détecteur de visage mal téléchargé. Le mettre à la main dans {MODELE}')
    return str(MODELE)


def suivre(fichier, t0, t1, l_src, h_src):
    """→ (temps, x, y) du centre du visage, en fractions de l'image source, ou None si aucun visage n'est vu."""
    import cv2
    RES.opencv(cv2)
    haut = int(round(LARGE * h_src / l_src)) // 2 * 2
    r = subprocess.run(RES.ff(['ffmpeg', '-v', 'error', '-ss', f'{t0:.4f}', '-i', str(fichier), '-t', f'{t1 - t0:.4f}',
                               '-vf', f'fps={CADENCE},scale={LARGE}:{haut},format=bgr24', '-f', 'rawvideo', '-']), capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f'cadrage : lecture impossible de {fichier}')
    images = np.frombuffer(r.stdout, np.uint8).reshape(-1, haut, LARGE, 3)
    det = cv2.FaceDetectorYN.create(_modele(), '', (LARGE, haut), 0.7)
    ts, xs, ys = [], [], []
    avant = None
    for i, im in enumerate(images):
        _, faces = det.detect(np.ascontiguousarray(im))
        if faces is None or not len(faces):
            continue
        # le plus grand visage, ou celui le plus proche du précédent quand deux ont presque la même taille
        faces = sorted(faces, key=lambda f: -f[2])
        f = faces[0]
        if avant is not None and len(faces) > 1 and faces[1][2] > 0.7 * f[2]:
            f = min(faces[:2], key=lambda g: abs(g[0] + g[2] / 2 - avant[0]) + abs(g[1] + g[3] / 2 - avant[1]))
        cx, cy = f[0] + f[2] / 2, f[1] + f[3] / 2
        avant = (cx, cy)
        ts.append(i / CADENCE); xs.append(cx / LARGE); ys.append(cy / haut)
    if len(ts) < max(2, 0.25 * len(images)):
        return None
    return np.array(ts), np.array(xs), np.array(ys)


def chemin(suivi, n, ips_sortie, cw, ch, l_src, h_src, lissage=0.7):
    """Coins (x, y) du rognage pour chacune des n images extraites (ips_sortie par seconde), lissés et gardés dans l'image."""
    from scipy.ndimage import gaussian_filter1d
    ts, xs, ys = suivi
    t = np.arange(n) / ips_sortie
    x = np.interp(t, ts, xs) * l_src
    y = np.interp(t, ts, ys) * h_src
    s = max(1.0, lissage * ips_sortie)
    x = gaussian_filter1d(x, s, mode='nearest'); y = gaussian_filter1d(y, s, mode='nearest')
    x0 = np.clip(x - cw / 2, 0, l_src - cw)
    y0 = np.clip(y - YEUX * ch, 0, h_src - ch)
    return (np.floor(x0 / 2) * 2).astype(int), (np.floor(y0 / 2) * 2).astype(int)


def commandes(x0, y0, ips_sortie, fichier):
    """Fichier sendcmd : la position du rognage change à chaque image."""
    lignes = [f'{k / ips_sortie:.4f} crop x {a}, crop y {b};' for k, (a, b) in enumerate(zip(x0, y0))]
    Path(fichier).write_text('\n'.join(lignes) + '\n')
    return fichier
