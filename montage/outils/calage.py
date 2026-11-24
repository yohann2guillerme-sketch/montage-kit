"""Calage d'une vidéo filmée sur la musique (playback d'un clip) : à quel instant de la chanson la vidéo commence.

On compare le son de la vidéo (la chanson qui passait pendant le tournage, plus le bruit de la rue) à la musique :
spectrogrammes en échelle log (150 à 3000 Hz, pas de 10 ms), chaque bande ramenée à moyenne 0 et écart 1, corrélation par FFT
sommée sur toutes les bandes. La vidéo doit être au moins à 80 % dans la chanson. Le résultat est vérifié sur les deux moitiés
de la vidéo : si elles ne donnent pas le même décalage, le calage est annoncé « incertain ».
Méthode mesurée le 11/11/2026 sur deux vrais playbacks (moitiés d'accord à 0,01 s près). L'enveloppe des attaques et le
GCC-PHAT donnaient de faux résultats avec le bruit de la rue : ne pas les remettre.
Bibliothèque standard + numpy + scipy ; le son est lu par ffmpeg.
"""
import subprocess

import numpy as np

import ressources as RES

SR, PAS = 8000, 80          # 8 kHz, un pas = 10 ms


def lire_son(fichier, sr=SR):
    """Son d'un fichier (vidéo ou musique) en mono, `sr` Hz, nombres à virgule."""
    r = subprocess.run(RES.ff(['ffmpeg', '-v', 'error', '-i', str(fichier), '-vn', '-ac', '1', '-ar', str(sr), '-f', 'f32le', '-']), capture_output=True)
    if r.returncode != 0:
        raise ValueError(f'son illisible : {fichier} ({r.stderr.decode(errors="replace").strip()[-200:]})')
    x = np.frombuffer(r.stdout, dtype=np.float32).astype(np.float64)
    if len(x) < sr:
        raise ValueError(f'pas de son (ou moins d\'une seconde) dans {fichier}')
    return x


def spectre(x):
    from scipy.signal import stft
    f, _, Z = stft(x, fs=SR, nperseg=512, noverlap=512 - PAS, boundary=None, padded=False)
    k = (f >= 150) & (f <= 3000)
    S = np.log(np.abs(Z[k]) + 1e-5)
    S -= S.mean(1, keepdims=True)
    S /= S.std(1, keepdims=True) + 1e-9
    return S


def correler(Sm, Sv, mini=0.8):
    """Score de chaque décalage L (la vidéo commence L pas après le début de la chanson ; L < 0 : avant)."""
    nm, nv = Sm.shape[1], Sv.shape[1]
    n = 1 << (nm + nv).bit_length()
    acc = np.zeros(n)
    for b in range(Sm.shape[0]):
        acc += np.fft.irfft(np.fft.rfft(Sm[b], n) * np.conj(np.fft.rfft(Sv[b], n)), n)
    m = int(mini * min(nv, nm))
    lags = np.arange(-(nv - m), nm - m + 1)
    vals = acc[np.where(lags >= 0, lags, n + lags)]
    recouvre = np.minimum(nm, lags + nv) - np.maximum(0, lags)
    return lags, vals / (Sm.shape[0] * np.maximum(recouvre, 1))


def caler(musique, video):
    """→ dict(decalage=s, nettete=…, moities=(s, s) ou None, sur=bool). decalage : instant de la chanson où la vidéo commence."""
    Sm, Sv = spectre(lire_son(musique)), spectre(lire_son(video))
    lags, v = correler(Sm, Sv)
    i = int(np.argmax(v))
    loin = np.abs(lags - lags[i]) > 100
    second = float(v[loin].max()) if loin.any() else 0.0
    nettete = float(v[i] / max(second, 1e-6))
    moities = None
    if Sv.shape[1] > 4000:          # plus de 40 s : on vérifie avec chaque moitié
        h = Sv.shape[1] // 2
        l1, v1 = correler(Sm, Sv[:, :h]); l2, v2 = correler(Sm, Sv[:, h:])
        moities = (round(float(l1[np.argmax(v1)]) * PAS / SR, 2), round(float(l2[np.argmax(v2)] - h) * PAS / SR, 2))
    dec = round(float(lags[i]) * PAS / SR, 2)
    # vrais playbacks mesurés : netteté 1,9 à 2,1. Une vidéo sans la chanson dans son son donne 1,3 à 1,5 par hasard.
    sur = nettete >= 1.6 and (moities is None or max(abs(m - dec) for m in moities) <= 0.03)
    return dict(decalage=dec, nettete=round(nettete, 2), moities=moities, sur=sur)
