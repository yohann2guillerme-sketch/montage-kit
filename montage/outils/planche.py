"""Planches de contrôle : beaucoup d'images du montage réunies en UNE seule image à regarder.

Regarder une planche coûte bien moins cher (en temps et en tokens) que d'ouvrir 30 images une par une.
"""
import math
import subprocess
from pathlib import Path

import ressources as RES


def images_reperes(calcul, maxi=32):
    """Images à contrôler : début et milieu de chaque plan, arrivée de chaque texte. Au plus `maxi`, bien réparties."""
    N = calcul['n']
    pts = {}
    for q in calcul['plans']:
        n = q['t1'] - q['t0']
        pts[min(N - 1, q['t0'] + min(6, n // 3))] = q['id']
        pts[min(N - 1, q['t0'] + n // 2)] = q['id']
    for c in calcul['calques']:
        if c['t'] == 'voile':
            continue
        k = c['de'] + min(14, max(1, (c['a'] - c['de']) // 2))
        pts.setdefault(min(N - 1, k), c['t'])
        if c['t'] == 'mots':
            for m in c['mots'][:6]:
                pts.setdefault(min(N - 1, m['de'] + 3), 'mot')
    pts.setdefault(0, 'début'); pts.setdefault(N - 1, 'fin')
    cles = sorted(pts)
    if len(cles) > maxi:
        garde = {cles[round(i * (len(cles) - 1) / (maxi - 1))] for i in range(maxi)} | {0, N - 1}
        cles = sorted(garde)
    return [(k, pts[k]) for k in cles]


def planche(fichiers, sortie, etiquettes=None, colonnes=8, vignette=(270, 480), titre=None):
    """Assemble des images (chemins) en une planche JPEG, avec le numéro d'image sur chacune."""
    from PIL import Image, ImageDraw, ImageFont
    w, h = vignette
    lignes = math.ceil(len(fichiers) / colonnes)
    haut = 34 if titre else 0
    S = Image.new('RGB', (min(colonnes, len(fichiers)) * w, lignes * h + haut), (12, 12, 12))
    d = ImageDraw.Draw(S)
    try:
        police = ImageFont.truetype(str(Path(__file__).resolve().parent.parent / 'moteur' / 'polices' / 'JetBrainsMono.ttf'), 17)
    except OSError:
        police = ImageFont.load_default()
    if titre:
        d.text((8, 7), titre, fill=(235, 235, 235), font=police)
    for i, f in enumerate(fichiers):
        im = Image.open(f).convert('RGB')
        if im.size != (w, h):
            im = im.resize((w, h), Image.LANCZOS)
        x, y = (i % colonnes) * w, (i // colonnes) * h + haut
        S.paste(im, (x, y))
        if etiquettes:
            txt = str(etiquettes[i])
            tw = d.textlength(txt, font=police)
            d.rectangle((x, y, x + tw + 10, y + 24), fill=(0, 0, 0))
            d.text((x + 5, y + 2), txt, fill=(255, 255, 255), font=police)
    S.save(sortie, quality=86)
    return sortie


def film(video, sortie, pas_s=0.5, colonnes=12, vignette=(180, 320), titre=None):
    """Planche « film » : une image toutes les `pas_s` secondes d'une vidéo (pour juger le rythme d'un coup d'œil)."""
    import tempfile
    w, h = vignette
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(RES.ff(['ffmpeg', '-v', 'error', '-y', '-i', str(video), '-vf', f'fps={1 / pas_s:.4f},scale={w}:{h}:flags=area', '-q:v', '3', f'{tmp}/%05d.jpg']), check=True)
        fichiers = sorted(Path(tmp).glob('*.jpg'))
        etiquettes = [f'{i * pas_s:.1f}s' for i in range(len(fichiers))]
        return planche(fichiers, sortie, etiquettes, colonnes, vignette, titre)
