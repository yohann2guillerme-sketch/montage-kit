"""Vidéos HDR d'iPhone (HLG, Dolby Vision) → image normale (SDR), avec ou sans le filtre zscale de ffmpeg.

Défaut vu le 13/11/2026 sur le Mac de Yohann : son ffmpeg n'a pas zscale, donc la préparation d'une vidéo HDR plantait (et la planche
des rushes perdait ses vignettes). Un seul endroit décide, pour la préparation des plans et pour la planche des rushes :
- ffmpeg a zscale (le cloud) : ffmpeg convertit, comme avant (VERS_SDR) ;
- sinon, avec avconvert (l'outil d'Apple, déjà sur le Mac) : une copie SDR de la vidéo, gardée en cache (clé : chemin, taille, date),
  vérifiée (cadence, durée, son, orientation, plus de HDR), puis traitée comme une vidéo normale ;
- ni l'un ni l'autre : arrêt avec un message clair (monter dans le cloud).

Mesuré le 13/11 sur le Mac (IMG_8631 et 8632, HLG 4K à 119,9 i/s, avconvert PresetHighestQuality, la commande du fil des stands) :
H.264 8 bits BT.709, son AAC gardé, rotation appliquée à l'image, durée à 0,05 s près, mais cadence ramenée à 30 i/s. Le rendu est à
30 i/s : à vitesse normale rien ne se perd ; un ralenti est moins fluide (la préparation le dit, plan par plan). La copie est lue avec
sa propre cadence, sinon le plan défilerait quatre fois trop vite.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

# conversion par ffmpeg : couleurs ramenées en BT.709 sans aspect délavé (tonemap mobius)
VERS_SDR = 'zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=mobius:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p'
# copie par avconvert : H.264 à la taille d'origine ; AVFoundation y ramène le HDR en SDR (BT.709) et garde la cadence, le son, l'orientation
PRESET = 'PresetHighestQuality'

_filtres = {}


def zscale(prog='ffmpeg'):
    """Vrai si ce ffmpeg a le filtre zscale (regardé une fois : ffmpeg -filters)."""
    if prog not in _filtres:
        try:
            liste = subprocess.run([prog, '-hide_banner', '-filters'], capture_output=True, text=True, timeout=30).stdout
        except (OSError, subprocess.SubprocessError):
            liste = ''
        _filtres[prog] = bool(re.search(r'^\s*\S{3}\s+zscale\s', liste, re.M))
    return _filtres[prog]


def avconvert():
    """Chemin d'avconvert (macOS), None ailleurs."""
    return shutil.which('avconvert')


def _ecart(orig, copie):
    """Ce qui distingue la copie de l'original, en trop (texte vide : rien). Une cadence ramenée à 30 i/s est admise (le rendu est
    à 30 i/s) : la copie est alors lue à sa propre cadence."""
    pb = []
    if copie.get('hdr'):
        pb.append('toujours en HDR')
    tol = max(0.05, orig['ips'] * 0.01)
    if not min(orig['ips'], 30.0) - tol <= copie.get('ips', 0) <= orig['ips'] + tol:
        pb.append(f'cadence {copie.get("ips", 0):.2f} i/s au lieu de {orig["ips"]:.2f}')
    if abs(copie.get('duree', 0) - orig['duree']) > 0.15:
        pb.append(f'durée {copie.get("duree", 0):.2f} s au lieu de {orig["duree"]:.2f}')
    if orig.get('audio') and not copie.get('audio'):
        pb.append('son perdu')
    if abs(copie.get('l', 0) - orig['l']) > 2 or abs(copie.get('h', 0) - orig['h']) > 2:
        pb.append(f'{copie.get("l")}×{copie.get("h")} au lieu de {orig["l"]}×{orig["h"]} (orientation ?)')
    return ', '.join(pb)


def source(fichier, sd, cache, dire=print):
    """Vidéo à lire, conversion des couleurs à poser dans ffmpeg, et sonde de la vidéo lue → (fichier, filtre, sonde).
    sd : sonde de l'original (fiche.sonde). Pas HDR : (fichier, '', sd) ; HDR et zscale : (fichier, VERS_SDR, sd) ; HDR sans zscale :
    (copie SDR rangée dans `cache`, '', sonde de la copie : sa cadence peut être plus basse que celle de l'original).
    RuntimeError (message clair, « Arrêt : … ») sans zscale ni avconvert, ou si la copie ne ressemble pas à l'original."""
    from fiche import sonde
    fichier = Path(fichier)
    if not sd.get('hdr'):
        return str(fichier), '', sd
    if zscale():
        return str(fichier), VERS_SDR, sd
    outil = avconvert()
    if not outil:
        raise RuntimeError(f'{fichier.name} est une vidéo HDR (iPhone) : ce ffmpeg ne sait pas la convertir (pas de filtre zscale) et avconvert '
                           'n\'est pas là pour le remplacer. Je propose : monter dans le cloud, son ffmpeg a zscale.')
    st = fichier.stat()
    chemin = str(fichier.resolve())
    groupe = f'{fichier.stem}-{hashlib.sha1(chemin.encode()).hexdigest()[:8]}'
    cle = hashlib.sha1(json.dumps([chemin, st.st_size, st.st_mtime_ns, PRESET]).encode()).hexdigest()[:12]
    cache = Path(cache)
    copie = cache / f'{groupe}-{cle}-sdr.mov'
    if copie.exists():
        return str(copie), '', sonde(copie)
    cache.mkdir(parents=True, exist_ok=True)
    tmp = cache / f'.{copie.stem}.part.mov'
    dire(f'  {fichier.name} : vidéo HDR et ffmpeg sans zscale : copie SDR par avconvert (une fois, gardée en cache)…')
    t0 = time.time()
    r = subprocess.run([outil, '--source', str(fichier), '--output', str(tmp), '--preset', PRESET, '--replace'], capture_output=True, text=True)
    if r.returncode or not tmp.exists():
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f'{fichier.name} : copie SDR par avconvert impossible ({(r.stderr or r.stdout).strip()[-300:]}). '
                           'Je propose : monter dans le cloud.')
    try:
        sc = sonde(tmp)
    except ValueError as e:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f'{fichier.name} : copie SDR par avconvert illisible ({e}). Je propose : monter dans le cloud.') from None
    ecart = _ecart(sd, sc)
    if ecart:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f'{fichier.name} : la copie SDR faite par avconvert ne ressemble pas à l\'original ({ecart}). '
                           'Je propose : monter dans le cloud.')
    os.replace(tmp, copie)
    for vieille in cache.glob(f'{groupe}-*-sdr.mov'):      # copies d'une version précédente du même fichier
        if vieille != copie:
            vieille.unlink()
    dire(f'    copie SDR faite en {time.time() - t0:.0f} s' + (f', à {sc["ips"]:.0f} i/s au lieu de {sd["ips"]:.0f} : un ralenti y sera moins fluide '
                                                      '(pour un vrai ralenti, monter dans le cloud)' if sc['ips'] < sd['ips'] - 0.5 else ''))
    return str(copie), '', sc
