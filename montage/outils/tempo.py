"""Tempo d'une musique : nombre de temps par minute, durée d'un temps, et instant d'un temps de référence.

Sert à poser les coupes pile sur la musique : dans la fiche, une durée « 4t » vaut 4 temps.
"""
import json
import os
import subprocess
from pathlib import Path

import numpy as np

import ressources as RES


def _charge(fichier, sr, debut=0.0, duree=None):
    cmd = ['ffmpeg', '-v', 'error', '-ss', f'{max(0.0, debut):.3f}', '-i', str(fichier)]
    if duree:
        cmd += ['-t', f'{duree:.3f}']
    cmd += ['-vn', '-ac', '1', '-ar', str(sr), '-f', 'f32le', '-']
    brut = subprocess.run(RES.ff(cmd), capture_output=True).stdout
    return np.frombuffer(brut, np.float32).copy()


def analyser(fichier, debut=0.0, duree=75.0):
    """→ dict(bpm, periode, phase). `phase` = instant, en secondes depuis le début du FICHIER, du premier temps à partir de `debut`.

    La grille est cherchée sur TOUT le morceau (jusqu'à 5 minutes) : sur un court passage, des contretemps ou des triolets
    peuvent tromper le calage d'un tiers de temps. Puis elle est ajustée finement sur le passage utilisé."""
    import librosa
    sr, hop = 22050, 128
    y = _charge(fichier, sr, 0.0, 300.0)
    if len(y) < sr * 4:
        raise ValueError('musique trop courte pour trouver le tempo (moins de 4 secondes)')
    # attaques des percussions seulement (caisse claire, charleston) : les basses tombent souvent à côté du temps et trompent le calage
    yp = librosa.effects.percussive(y, margin=2.0)
    S = librosa.feature.melspectrogram(y=yp, sr=sr, n_fft=1024, hop_length=hop, fmin=150, fmax=11000, n_mels=64)
    # n_fft est redonné ici : sans lui, librosa recale l'enveloppe comme pour 2048 points et tous les temps sortent 23 ms trop tard
    env = librosa.onset.onset_strength(S=librosa.power_to_db(S, ref=np.max), sr=sr, hop_length=hop, n_fft=1024)
    t_env = librosa.times_like(env, sr=sr, hop_length=hop)
    bpm0 = float(np.atleast_1d(librosa.beat.beat_track(onset_envelope=env, sr=sr, hop_length=hop)[0])[0])
    while bpm0 < 78:
        bpm0 *= 2
    while bpm0 >= 178:
        bpm0 /= 2
    dur = len(y) / sr

    def note(per, ph, a=0.0, b=None):
        g = np.arange(ph % per, dur if b is None else min(dur, b), per)
        g = g[g >= a]
        return float(np.interp(g, t_env, env).mean()) if len(g) else -1.0
    # peigne : la grille de temps qui tombe le mieux sur les attaques, de plus en plus fin
    per, ph = 60.0 / bpm0, 0.0
    largeur_per, largeur_ph = 0.03, 0.5
    for passe in range(4):
        meilleur = (-1.0, per, ph)
        for per2 in np.linspace(per * (1 - largeur_per), per * (1 + largeur_per), 121):
            for ph2 in np.linspace(ph - per2 * largeur_ph, ph + per2 * largeur_ph, 49):
                s = note(per2, ph2)
                if s > meilleur[0]:
                    meilleur = (s, per2, ph2 % per2)
        _, per, ph = meilleur
        largeur_per /= 12; largeur_ph /= 6
    # Avec le tempo trouvé, on balaie tous les calages possibles (pas de 2 ms) et on garde les meilleurs (maxima bien séparés).
    def ecart(p1, p2):
        return abs(((p1 - p2 + per / 2) % per) - per / 2)
    phs = np.arange(0.0, per, 0.002)
    notes = np.array([note(per, p) for p in phs])
    n0 = float(notes.max())
    cands = []
    for i in np.argsort(notes)[::-1]:
        if notes[i] < 0.75 * n0 or len(cands) >= 5:
            break
        if all(ecart(phs[i], p) > 0.08 * per for _, p in cands):
            cands.append((float(notes[i]), float(phs[i])))
    # Les graves (grosse caisse, basse) départagent : quand un charley à contretemps trompe les aigus, la grosse caisse marque le temps.
    from scipy import signal
    yg = signal.sosfiltfilt(signal.butter(4, [30, 160], 'bandpass', fs=sr, output='sos'), y).astype(np.float32)
    grave = librosa.feature.rms(y=yg, frame_length=1024, hop_length=hop)[0]
    env_g = np.maximum(0, np.diff(grave, prepend=grave[0]))
    t_g = librosa.times_like(env_g, sr=sr, hop_length=hop)

    def appui(p):   # le grave monte un peu après l'attaque : on regarde de -10 à +40 ms autour de la grille
        return max(float(np.interp(np.arange((p + d) % per, dur, per), t_g, env_g).mean()) for d in np.arange(-0.010, 0.045, 0.004))
    graves = [appui(p) for _, p in cands]
    choisi = 0
    if len(cands) > 1 and max(graves) > 1e-6:
        j = int(np.argmax(graves))
        if j != 0 and graves[j] >= 1.5 * graves[0]:
            choisi = j
    ph = cands[choisi][1]
    # Le calage est-il sûr ? Sur un rythme en triolets, plusieurs grilles (décalées d'un tiers de temps) se valent, aigus comme graves :
    # on le dit, avec les candidats, pour vérifier à l'oreille ou fixer « premier_temps » dans la fiche.
    rivaux = [(n, p) for k, (n, p) in enumerate(cands) if k != choisi and n >= 0.93 * n0 and graves[k] >= graves[choisi] / 1.25]
    # ajustement local (au plus 12 % d'un temps) sur le passage utilisé : rattrape une légère dérive sans sauter d'un tiers de temps
    a, b = max(0.0, debut), min(dur, debut + duree)
    if b - a > 8 * per:
        cand = [(note(per, ph + d, a, b), d) for d in np.linspace(-0.12 * per, 0.12 * per, 25)]
        gain, d = max(cand)
        if gain > note(per, ph, a, b) * 1.03:
            ph = (ph + d) % per
    # l'enveloppe des attaques réagit un pas (6 ms) après le son : on l'enlève (vérifié sur des clics de synthèse, écart restant < 2 ms)
    retard = hop / sr
    ph = (ph - retard) % per
    k = np.ceil((debut - ph) / per - 1e-6)
    return dict(bpm=round(60.0 / per, 3), periode=float(per), phase=float(ph + k * per), incertain=bool(rivaux),
                candidats=[round(float((p - retard) % per + np.ceil((debut - (p - retard) % per) / per - 1e-6) * per), 3) for _, p in rivaux])


def tempo_du_projet(mus, projet, travail):
    """Tempo de la musique de la fiche (gardé en cache). Si la fiche donne « bpm », on la croit ; « premier_temps » fixe le calage."""
    fichier = Path(projet) / mus['fichier']
    debut = float(mus.get('debut', 0))
    st = os.stat(fichier)
    cle = [str(fichier), st.st_size, int(st.st_mtime), debut, mus.get('bpm'), mus.get('premier_temps')]
    cache = Path(travail) / 'tempo.json'
    if cache.exists():
        d = json.loads(cache.read_text())
        if d.get('cle') == cle:
            return d
    if mus.get('bpm') and mus.get('premier_temps') is not None:
        per = 60.0 / float(mus['bpm'])
        k = np.ceil((debut - float(mus['premier_temps'])) / per - 1e-6)
        d = dict(bpm=float(mus['bpm']), periode=per, phase=float(mus['premier_temps']) + k * per)
    else:
        d = analyser(fichier, debut)
        if mus.get('bpm'):   # tempo donné, calage trouvé : on garde la phase mesurée
            d['bpm'] = float(mus['bpm']); d['periode'] = 60.0 / d['bpm']
    d['cle'] = cle
    d['debut_cale'] = d['phase']      # la musique démarre sur un temps : le premier plan commence pile dessus
    cache.write_text(json.dumps(d))
    return d


if __name__ == '__main__':
    import sys
    r = analyser(sys.argv[1], float(sys.argv[2]) if len(sys.argv) > 2 else 0.0)
    print(f'{r["bpm"]:.2f} temps par minute ; un temps = {r["periode"]:.4f} s ; premier temps à {r["phase"]:.3f} s')
    if r['incertain']:
        print('calage incertain, autres départs possibles :', r['candidats'])
