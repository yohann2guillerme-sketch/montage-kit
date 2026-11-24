#!/usr/bin/env python3
"""Fabrique un petit projet de démonstration, sans aucun fichier de client.

Tout est dessiné ou calculé ici : deux photos, une vidéo de synthèse, une boucle de musique à 120 temps par minute.
Sert d'essai du kit après une installation, et de base aux tests automatiques.

    python3 montage/exemples/demo/fabrique.py /tmp/demo
    python3 montage/montage.py tout /tmp/demo
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

FICHE = {
    "nom": "demo",
    "note": "Projet de démonstration du kit : aucune image de client. Durées : 24 = images, \"1.5s\" = secondes, \"4t\" = 4 temps de la musique.",
    "theme": "neutre",
    "finition": {"grain": 0.06, "vignette": 0.3, "fondu_fin": 10},
    "musique": {"fichier": "sources/musique.wav", "debut": 0, "droits": "libre", "credit": "Boucle calculée par le kit de montage, aucun droit d'auteur"},
    "accents": {"tous_les": 2, "decalage": 1, "zoom": 0.02},
    "plans": [
        {"id": "A", "photo": "sources/photo1.jpg", "duree": "4t", "effets": [{"t": "kb", "a": 1.0, "b": 1.08}], "sortie": "zoom"},
        {"id": "B", "source": "sources/video1.mp4", "de": 0.2, "duree": "6t", "sortie": "whipG"},
        {"id": "C", "photo": "sources/photo2.jpg", "duree": "6t", "effets": [{"t": "kb", "a": 1.08, "b": 1.0}]}
    ],
    "calques": [
        {"t": "titre", "texte": "LE KIT\nDE MONTAGE", "y": 560, "taille": 170, "de": 2, "a": "4t", "anim": "pop"},
        {"t": "etiquette", "texte": "démonstration", "x": 72, "y": 300, "align": "gauche", "plan": "B"},
        {"t": "compteur", "valeur": 100, "suffixe": " %", "plan": "B", "y": 760, "taille": 240},
        {"t": "mots", "texte": "NET / PROPRE / CALÉ", "plan": "C", "y": 560, "taille": 220, "rythme": "1t"},
        {"t": "signature", "nom": "Démo", "ligne": "une fiche → une vidéo contrôlée", "plan": "C", "de": "3t"}
    ]
}


def _photo(fichier, c0, c1, graine):
    """Photo dessinée : dégradé en diagonale et quelques disques flous (aucune image réelle)."""
    from PIL import Image
    from scipy import ndimage
    h, w = 2880, 1620
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    t = ((x / w) * 0.45 + (y / h) * 0.55)[..., None]
    im = np.array(c0, np.float32) * (1 - t) + np.array(c1, np.float32) * t
    rng = np.random.default_rng(graine)
    hb, wb = h // 8 + 1, w // 8 + 1
    voile = np.zeros((hb, wb), np.float32)
    yy, xx = np.mgrid[0:hb, 0:wb]
    for _ in range(7):
        cx, cy, r = rng.uniform(0, wb), rng.uniform(0, hb), rng.uniform(18, 70)
        voile += ((xx - cx) ** 2 + (yy - cy) ** 2 < r * r) * rng.uniform(0.25, 0.7)
    voile = ndimage.zoom(ndimage.gaussian_filter(voile, 6), 8, order=1)[:h, :w]
    im = im + voile[..., None] * 70
    Image.fromarray(np.clip(im, 0, 255).astype(np.uint8), 'RGB').save(fichier, quality=92)


def _video(fichier):
    """Vidéo de synthèse de 5 s (dégradés qui bougent), 1080 × 1920, 30 images par seconde."""
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                    'gradients=s=1080x1920:r=30:d=5:speed=0.012:c0=0x1B2A49:c1=0xE07A2F:c2=0x0E1320:c3=0xF2C14E:x0=0:y0=0:x1=1080:y1=1920',
                    '-c:v', 'libx264', '-crf', '14', '-preset', 'veryfast', '-pix_fmt', 'yuv420p',
                    '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv', str(fichier)], check=True)


def musique(fichier, bpm=120.0, duree=12.0, decalage=0.0, sr=48000):
    """Boucle de musique calculée (grosse caisse sur chaque temps, charley sur les contretemps, basse) : aucun droit d'auteur."""
    import soundfile as sf
    n = int(duree * sr)
    x = np.zeros(n, np.float32)
    rng = np.random.default_rng(7)
    periode = 60.0 / bpm
    k = 0
    while decalage + k * periode < duree:
        i = int((decalage + k * periode) * sr)
        t = np.arange(int(0.22 * sr)) / sr
        coup = np.sin(2 * np.pi * (45 * t + (120 - 45) * 0.045 * (1 - np.exp(-t / 0.045)))) * np.exp(-t / 0.07) * np.minimum(1, (t[-1] - t) / 0.03)   # fin en douceur : pas de clic
        m = min(len(coup), n - i); x[i:i + m] += 0.9 * coup[:m]
        j = i + int(periode / 2 * sr)
        if j < n:
            th = np.arange(int(0.05 * sr)) / sr
            ch = np.diff(rng.standard_normal(len(th) + 1)) * np.exp(-th / 0.012)
            m = min(len(ch), n - j); x[j:j + m] += 0.16 * ch[:m]
        if k % 4 == 0:
            tb = np.arange(int(min(2 * periode, duree - (decalage + k * periode)) * sr)) / sr
            note = (55.0, 55.0, 65.41, 49.0)[(k // 4) % 4]
            b = np.sin(2 * np.pi * note * tb) * np.minimum(1, tb / 0.02) * np.exp(-tb / 0.6)
            x[i:i + len(b)] += 0.28 * b[:n - i]
        k += 1
    x = np.tanh(x * 1.2) * 0.7
    sf.write(fichier, np.stack([x, x], 1), sr, subtype='PCM_16')


def fabriquer(dossier, avec_video=True):
    d = Path(dossier)
    src = d / 'sources'
    src.mkdir(parents=True, exist_ok=True)
    _photo(src / 'photo1.jpg', (27, 42, 73), (224, 122, 47), 1)
    _photo(src / 'photo2.jpg', (14, 19, 32), (60, 120, 160), 2)
    if avec_video:
        _video(src / 'video1.mp4')
    musique(src / 'musique.wav')
    (d / 'montage.json').write_text(json.dumps(FICHE, ensure_ascii=False, indent=2), encoding='utf-8')
    return d


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print(__doc__); sys.exit(1)
    cible = fabriquer(sys.argv[1])
    print(f'Projet de démonstration prêt : {cible}\nSuite : python3 montage/montage.py tout {cible}')
