"""Bande-son d'un montage : musique + bruitages + voix des plans, au niveau des réseaux (-14 LUFS, crête -1 dB).

Écrit deux fichiers dans <travail>/public/audio/ :
  mix.wav          tout mélangé (ce que porte la vidéo finale)
  sons-seuls.wav   la même chose SANS la musique, pour poser une musique dans Instagram (droits respectés)
"""
import json
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from fiche import SONS_KIT, SONS_PLUS, DEPOT, DROITS_MUSIQUE, fichier_son

import ressources as RES

SR = 48000


MODELE_VOIX = DEPOT / 'plugin-visibilite' / 'visibilite' / 'assets' / 'models' / 'rnnoise-voix.rnnn'
# voix face caméra : coupe le grondement, enlève le bruit de fond (réseau de neurones rnnoise), resserre les écarts de niveau
VOIX_PROPRE = f"aresample=48000,highpass=f=80,arnndn=m='{MODELE_VOIX}':mix=0.9,acompressor=threshold=-20dB:ratio=3:attack=6:release=140:makeup=1.5"


def _charge(fichier, debut=0.0, duree=None, filtres=None):
    cmd = ['ffmpeg', '-v', 'error']
    if debut:
        cmd += ['-ss', f'{debut:.4f}']
    cmd += ['-i', str(fichier)]
    if duree:
        cmd += ['-t', f'{duree:.4f}']
    if filtres:
        cmd += ['-af', filtres]
    cmd += ['-vn', '-f', 'f32le', '-ac', '2', '-ar', str(SR), '-']
    p = subprocess.run(RES.ff(cmd), capture_output=True)
    return np.frombuffer(p.stdout, np.float32).reshape(-1, 2).copy()


def mesure(x):
    """Niveau moyen (LUFS) et crête vraie (dBTP) mesurés par ffmpeg (norme EBU R128)."""
    import soundfile as sf
    with tempfile.NamedTemporaryFile(suffix='.wav') as f:
        sf.write(f.name, x, SR, subtype='FLOAT')
        o = subprocess.run(RES.ff(['ffmpeg', '-nostats', '-i', f.name, '-af', 'ebur128=peak=true', '-f', 'null', '-']), capture_output=True, text=True).stderr
    fin = o.split('Summary:')[-1]
    try:
        lufs = float(fin.split('I:')[1].split('LUFS')[0])
        crete = float(fin.split('Peak:')[1].split('dBFS')[0])
    except (IndexError, ValueError):
        lufs, crete = -70.0, -70.0
    return lufs, crete


def limiteur(x, plafond=0.89, fenetre=0.012):
    """Limiteur avec 12 ms d'anticipation : aucune crête au-dessus du plafond, sans claquement."""
    from scipy.ndimage import minimum_filter1d, uniform_filter1d
    a = np.abs(x).max(axis=1)
    g = np.minimum(1.0, plafond / np.maximum(a, 1e-9))
    n = int(fenetre * SR)
    g = uniform_filter1d(minimum_filter1d(g, 2 * n + 1), n + 1)
    return (x * g[:, None]).astype(np.float32)


def _vers(x, cible):
    """Amène un signal à un niveau moyen donné (LUFS). Signal vide : inchangé."""
    if not len(x) or np.abs(x).max() < 1e-4:
        return x
    l, _ = mesure(x)
    return x * 10 ** ((cible - l) / 20) if l > -60 else x


_fichier_son = fichier_son      # nom du kit, fichier du projet ou son de la bibliothèque du skill sound-effects (voir fiche.py)


def mixer(calcul, projet, travail, tempo=None, journal=print):
    ips, N = calcul['ips'], calcul['n']
    L = int(round(N / ips * SR))
    sortie = Path(travail) / 'public' / 'audio'
    sortie.mkdir(parents=True, exist_ok=True)
    musique = np.zeros((L, 2), np.float32)
    voix = np.zeros((L, 2), np.float32)
    sfx = np.zeros((L, 2), np.float32)

    # ---------- voix : le son d'origine des plans marqués « son »
    presence = np.zeros(L, np.float32)
    for q in calcul['plans']:
        if not q.get('_son') or q['photo']:
            continue
        if not q['_sonde'].get('audio'):
            journal(f'  plan {q["id"]} : « son » demandé mais la vidéo n\'a pas de piste son'); continue
        n = q['t1'] - q['t0']
        filtres = None if q['_son'] == 'brut' or not MODELE_VOIX.exists() else VOIX_PROPRE
        # le nettoyage de la voix prend une demi-seconde d'élan avant la coupe : sans lui, chaque plan commence par un souffle (bruit 4 dB plus fort pendant 0,1 s)
        elan = min(0.5, float(q['src'])) if filtres else 0.0
        x = _charge(q['_fichier'], q['src'] - elan, n / ips + elan, filtres)[int(round(elan * SR)):]
        i = int(q['t0'] / ips * SR); m = min(len(x), L - i)
        r = int(0.006 * SR)
        if m > 2 * r:
            x[:r] *= np.linspace(0, 1, r)[:, None]; x[m - r:m] *= np.linspace(1, 0, r)[:, None]
            gain = 10 ** (float(q['_son']) / 20) if isinstance(q['_son'], (int, float)) and not isinstance(q['_son'], bool) else 1.0
            voix[i:i + m] += x[:m] * gain; presence[i:i + m] = 1
    a_voix = presence.any()
    a_ecouter = []
    if a_voix:
        # personne ici ne peut entendre : on mesure la voix juste avant et juste après chaque coupe, et on donne à écouter au casque
        # les coupes où elle est encore forte (un mot entamé, un « euh » coupé net), les plus fortes d'abord
        niveau = lambda x: 20 * np.log10(np.sqrt(float((x ** 2).mean())) + 1e-9) if len(x) else -120.0
        moyenne = niveau(voix[presence > 0])
        garde, large = int(0.012 * SR), int(0.05 * SR)
        for q in calcul['plans']:
            if not q.get('_son') or q['photo'] or not q['_sonde'].get('audio'):
                continue
            i0, i1 = int(q['t0'] / ips * SR), min(L, int(q['t1'] / ips * SR))
            for bord, t, morceau in (('début', q['t0'], voix[i0 + garde:i0 + garde + large]), ('fin', q['t1'], voix[max(i0, i1 - garde - large):i1 - garde])):
                ecart = niveau(morceau) - moyenne
                if ecart > -25.0:
                    a_ecouter.append(dict(t=round(t / ips, 2), plan=q['id'], bord=bord, db=round(ecart, 1)))
        a_ecouter = sorted(a_ecouter, key=lambda e: -e['db'])[:5]
        voix = _vers(voix, -15.0)

    # ---------- musique : un seul passage continu, qui démarre sur un temps
    mus = calcul.get('_musique')
    if mus:
        debut = (tempo or {}).get('debut_cale', float(mus.get('debut', 0)))
        x = _charge(Path(projet) / mus['fichier'], debut, N / ips + 0.5)[:L]
        musique[:len(x)] = x
        musique = _vers(musique, -17.0 if a_voix else -15.0) * 10 ** (float(mus.get('gain', 0)) / 20)
        r = int(0.008 * SR); musique[:r] *= np.linspace(0, 1, r)[:, None]
        fo = int(mus.get('fondu', max(18, calcul.get('fondu_fin', 0))) / ips * SR)
        if 0 < fo < L:
            musique[L - fo:] *= (np.linspace(1, 0, fo) ** 1.5)[:, None]
        if a_voix:   # la musique s'efface sous la voix (-10 dB), en douceur
            from scipy.ndimage import uniform_filter1d
            p = uniform_filter1d(presence, int(0.25 * SR))
            musique *= (1 - 0.68 * np.clip(p, 0, 1))[:, None]

    # ---------- bruitages
    poses = 0
    for s in calcul.get('_sons', []):
        try:
            f = _fichier_son(s['son'], projet)
        except ValueError as e:
            journal(f'  {e}'); continue
        x = _charge(f)
        if not len(x):
            continue
        x = x / max(1e-6, float(np.abs(x).max()))
        if s.get('coupe'):
            x = x[:int(float(s['coupe']) * SR)].copy()
        fo = int(float(s.get('fondu', 0.12)) * SR)
        if 0 < fo < len(x):
            x[-fo:] *= np.linspace(1, 0, fo)[:, None]
        env = np.abs(x).max(axis=1)
        cal = s.get('calage', 'attaque')
        dec = int(np.argmax(env)) if cal == 'pic' else (int(np.argmax(env > 0.12)) if cal == 'attaque' else 0)
        i = int(round(s['at'] / ips * SR)) - dec
        if i < 0:
            x = x[-i:]; i = 0
        m = min(len(x), L - i)
        if m > 0:
            sfx[i:i + m] += x[:m] * 10 ** (float(s['db']) / 20); poses += 1

    # ---------- niveau final
    brut = musique + voix + sfx
    info = dict(bruitages=poses, musique=bool(mus), voix=bool(a_voix), a_ecouter=a_ecouter)
    if np.abs(brut).max() < 1e-4:
        plein, seuls = brut, brut
        info.update(lufs=None, crete=None)
    elif mus or a_voix:
        g = 1.0
        for _ in range(5):
            plein = limiteur(brut * g)
            l, c = mesure(plein)
            if abs(-14.0 - l) < 0.15:
                break
            g *= 10 ** ((-14.0 - l) / 20)
        if c > -1.0:   # crête vraie au-dessus de -1 dB : on baisse le plafond du limiteur
            plein = limiteur(brut * g, plafond=0.89 * 10 ** ((-1.0 - c) / 20)); l, c = mesure(plein)
        seuls = limiteur((voix + sfx) * g)
        info.update(lufs=round(l, 1), crete=round(c, 1))
    else:
        plein = seuls = limiteur(brut)
        l, c = mesure(plein)
        info.update(lufs=round(l, 1), crete=round(c, 1))
    import soundfile as sf
    sf.write(sortie / 'mix.wav', plein, SR, subtype='PCM_24')
    sf.write(sortie / 'sons-seuls.wav', seuls, SR, subtype='PCM_24')
    calcul['audio'] = 'audio/mix.wav'
    return info


def credits(calcul, projet):
    """D'où vient chaque son d'une vidéo et ce qu'on a le droit d'en faire : texte à garder avec elle.
    Le crédit d'une musique libre se recopie dans la légende ; c'est aussi la preuve à montrer si une plateforme signale le son."""
    L = [f'Son de « {calcul["nom"]} » : sources et droits', '']
    mus = calcul.get('_musique')
    if mus:
        L.append(f'Musique : {str(mus.get("credit") or "").strip() or mus["fichier"]}')
        L.append('  Droits : ' + {
            'libre': 'libre. Recopier ce crédit dans la légende de la publication.',
            'artiste': 'musique de l\'artiste pour qui la vidéo est faite (clip). Elle reste dans la version publiée, avec son accord écrit ; mettre ce crédit dans la description.',
            'sous_droits': 'musique du commerce. Le fichier AVEC musique ne va jamais en ligne : publier la version « sans musique » et ajouter le son dans Instagram.',
        }.get(mus.get('droits'), 'NON RENSEIGNÉS. Ne pas publier le fichier avec musique avant de les avoir vérifiés.'))
    else:
        L.append('Musique : aucune dans le fichier.')
    man = SONS_PLUS / 'manifest.json'
    plus = {e['file']: e for e in json.loads(man.read_text(encoding='utf-8')).get('bundled', [])} if man.exists() else {}
    du_kit, autres = set(), {}
    for s in calcul.get('_sons', []):
        try:
            f = fichier_son(s['son'], projet).resolve()
        except ValueError:
            continue
        if SONS_KIT.resolve() in f.parents:
            du_kit.add(s['son'])
        elif SONS_PLUS.resolve() in f.parents:
            e = plus.get(f.relative_to(SONS_PLUS.resolve()).as_posix(), {})
            autres[s['son']] = ' '.join(x for x in (e.get('attribution') or 'bibliothèque du skill sound-effects', f'({e.get("license", "CC0 1.0")})', e.get('source_url', '')) if x)
        else:
            autres[s['son']] = 'fichier du projet : droits à vérifier par celui qui l\'a apporté'
    L.append('')
    if du_kit:
        source = json.loads((SONS_KIT / 'catalogue.json').read_text(encoding='utf-8')).get('source', 'kit du dépôt, CC0')
        L.append(f'Bruitages du kit ({", ".join(sorted(du_kit))}) : {source}, aucun crédit obligatoire.')
    L += [f'Bruitage {k} : {v}' for k, v in sorted(autres.items())]
    if any(q.get('_son') and not q.get('photo') for q in calcul.get('plans', [])):
        L.append('Voix : son d\'origine des plans filmés. Rappel : accord écrit de toute personne filmée.')
    return '\n'.join(L).rstrip() + '\n'
