"""Montage discret : pendant un montage, le Mac de Yohann (M1) reste utilisable.

Demande de Yohann (13/11/2026, 17h40) : « mettre une limite d'utilisation de gpu et ram pour le montage vidéo car mon ordi rame et je peux
rien faire à côté des montages ». Puis (18h01) : « calculer que sur le mac m1, le reste ne sert à rien », et (18h16, puis 18h31
« pilote tu peux encore utiliser un peu plus de puissance ») : 4 cœurs, et 3 Go laissés libres au lieu de 4. La limite est dans le kit,
par défaut : aucun fil n'a à y penser.

Sur le Mac, mode « discret » :
- un seul montage lourd à la fois : le deuxième attend son tour et le dit (verrou ~/.cache/montage/rendu.lock) ;
- priorité basse : nice 15 et la classe « utility » (taskpolicy -c utility) : les cœurs rapides restent aux applications de Yohann ;
- cœurs : 4 sur un M1 (autant que de cœurs performance, 4 au plus), en priorité basse donc surtout sur les cœurs économes, pour
  tout le montage : onglets du rendu, encodage x264, ffmpeg (décodage, filtres, encodage), OpenCV, détourage (onnxruntime), transcription
  (faster-whisper), calcul (numpy, Accelerate) ;
- mémoire (c'est elle qui faisait ramer le Mac de 8 Go) : un onglet de rendu tant que le Mac ne garderait pas 3 Go libres avec un de
  plus ; cache vidéo du rendu plafonné (512 Mo) ; détourage léger (isnet-general-use : 1 Go au lieu de 7 à 12 pour BiRefNet) ;
- carte graphique : Chromium garde son choix (la carte du Mac, peu chargée par un rendu) : le dessin sans elle (swangle) a été mesuré
  2,5 fois plus lent et il prend tous les cœurs (cloud, 13/11) ; MONTAGE_GL=swangle pour l'essayer quand même.
Ailleurs (machine du cloud) : rien n'est calculé, pleine vitesse comme avant.

Réglages : MONTAGE_COEURS=n fixe le nombre de cœurs ; MONTAGE_RESSOURCES=rapide retire les limites du Mac sauf le verrou (seulement
si Yohann le demande) ; MONTAGE_RESSOURCES=discret force le mode discret ailleurs (essais) ; MONTAGE_GL choisit le moteur graphique du
rendu ; MONTAGE_DETOURAGE le modèle du détourage ; MONTAGE_VERROU : chemin du verrou ; MONTAGE_ATTENTE : minutes d'attente au plus (60).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

MAC = sys.platform == 'darwin'
GO = 2 ** 30
LIBRE_VISE = 3 * GO           # mémoire que le mode discret laisse libre au Mac (4 Go jusqu'au « encore un peu plus » de 18h31)
SOCLE_RENDU = 1.5 * GO        # navigateur, Node, encodeur x264, Python (mesuré dans le cloud le 13/11 : 1,1 Go pris à la machine)
PAR_ONGLET = 0.5 * GO         # un onglet de rendu de plus (mesuré : 0,05 à 0,2 Go ; marge pour les grosses images)
PAS_ATTENTE = 5               # secondes entre deux essais du verrou
LOURDES = {'rushes', 'preparer', 'planche', 'apercu', 'final', 'tout', 'couverture', 'transcrire', 'caler', 'controle'}
BIBLIOTHEQUES = ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS')

_reglages = None
_verrou = None


def _sysctl(nom):
    try:
        r = subprocess.run(['sysctl', '-n', nom], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    v = r.stdout.strip()
    return int(v) if r.returncode == 0 and v.isdigit() else (v or None)


def machine():
    """→ dict(puce, perf (cœurs performance), coeurs (tous), memoire (octets)). Lu sur le Mac (sysctl) ; ailleurs, au plus simple."""
    if MAC:
        tous = _sysctl('hw.logicalcpu') or os.cpu_count() or 1
        puce = _sysctl('machdep.cpu.brand_string')
        return dict(puce=puce if isinstance(puce, str) else 'Mac', perf=int(_sysctl('hw.perflevel0.physicalcpu') or _sysctl('hw.physicalcpu') or tous),
                    coeurs=int(tous), memoire=int(_sysctl('hw.memsize') or 8 * GO))
    n = os.cpu_count() or 1
    try:
        m = re.search(r'MemTotal:\s+(\d+) kB', Path('/proc/meminfo').read_text())
    except OSError:
        m = None
    return dict(puce='machine du cloud', perf=n, coeurs=n, memoire=int(m.group(1)) * 1024 if m else 8 * GO)


def reglages(rafraichir=False):
    """Réglages du montage sur cette machine (calculés une fois). Clés : mode (discret, rapide, libre), coeurs (None : sans limite),
    cache (octets du cache vidéo du rendu), gl (moteur graphique du rendu), priorite, verrou, machine."""
    global _reglages
    if _reglages is not None and not rafraichir:
        return _reglages
    m = machine()
    mode = (os.environ.get('MONTAGE_RESSOURCES') or '').strip().lower()
    if mode not in ('discret', 'rapide'):
        mode = 'discret' if MAC else 'libre'
    discret = mode == 'discret'
    coeurs = max(1, min(4, m['perf'])) if discret else None
    force = (os.environ.get('MONTAGE_COEURS') or '').strip()
    if force.isdigit() and int(force) > 0:
        coeurs = min(int(force), m['coeurs'])
    _reglages = dict(mode=mode, coeurs=coeurs, machine=m, priorite=discret, verrou=mode != 'libre',
                     cache=min(512 * 2 ** 20, m['memoire'] // 16) if discret else None,
                     gl=os.environ.get('MONTAGE_GL') or None)
    return _reglages


def environnement():
    """À appeler avant numpy, OpenCV, onnxruntime et faster-whisper : plafonne les fils de leurs calculs (sans écraser un réglage déjà là)."""
    r = reglages()
    if r['coeurs']:
        for v in BIBLIOTHEQUES:
            os.environ.setdefault(v, str(r['coeurs']))
    return r


def taches(n):
    """Nombre de travaux menés en parallèle (vignettes, extraits, détection des têtes) : n, ou au plus les cœurs du mode discret."""
    c = reglages()['coeurs']
    return max(1, min(n, c)) if c else n


def fils(paralleles=1):
    """Fils de calcul d'un outil quand `paralleles` travaux tournent ensemble (None : sans limite)."""
    c = reglages()['coeurs']
    return max(1, c // max(1, paralleles)) if c else None


_globales = None


def _globales_ffmpeg(prog):
    """Options de fils des filtres que ce ffmpeg connaît (lu une fois dans son aide : elles changent d'une version à l'autre)."""
    global _globales
    if _globales is None:
        try:
            aide = subprocess.run([prog, '-hide_banner', '-h', 'full'], capture_output=True, text=True, timeout=30).stdout
        except (OSError, subprocess.SubprocessError):
            aide = ''
        _globales = [o for o in ('-filter_threads', '-filter_complex_threads') if re.search(rf'^\s*{o}\s', aide, re.M)]
    return _globales


def ff(cmd, paralleles=1):
    """Commande ffmpeg aux fils plafonnés : filtres (-filter_threads, -filter_complex_threads), décodage (-threads avant chaque -i),
    encodage (-threads avant la sortie, le dernier argument). Sans limite, la commande est rendue telle quelle."""
    n = fils(paralleles)
    cmd = [str(x) for x in cmd]
    if not n or not cmd or Path(cmd[0]).name != 'ffmpeg':
        return cmd
    n = str(n)
    out = [cmd[0]] + [x for o in _globales_ffmpeg(cmd[0]) for x in (o, n)]
    for i, a in enumerate(cmd[1:], 1):
        if a == '-i' or i == len(cmd) - 1:
            out += ['-threads', n]
        out.append(a)
    return out


def opencv(cv2, paralleles=1):
    """Fils d'OpenCV (détection des visages, netteté)."""
    n = fils(paralleles)
    if n:
        cv2.setNumThreads(n)


def detourage():
    """Modèle du détourage (texte derrière le sujet) et options d'onnxruntime → (nom, dict pour rembg.new_session).
    Sur le Mac : isnet-general-use, sans réserve de mémoire (mesuré dans le cloud le 13/11 : 1,05 Go au plus et 4 s par image, contre 7 à
    12 Go et 16 à 19 s pour BiRefNet, de quoi faire échanger un Mac de 8 Go). Ailleurs : BiRefNet, la meilleure découpe."""
    force = os.environ.get('MONTAGE_DETOURAGE')
    r = reglages()
    if r['mode'] != 'discret':
        return force or 'birefnet-general-lite', {}
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.enable_cpu_mem_arena = False
    so.enable_mem_pattern = False
    so.intra_op_num_threads = so.inter_op_num_threads = r['coeurs']
    return force or 'isnet-general-use', {'sess_opts': so}


def memoire_disponible():
    """Mémoire que la machine peut donner sans échanger sur le disque (octets), None si on ne sait pas la lire."""
    try:
        if MAC:
            vm = subprocess.run(['vm_stat'], capture_output=True, text=True, timeout=5).stdout
            page = re.search(r'page size of (\d+)', vm)
            pages = sum(int(x.group(1)) for nom in ('free', 'inactive', 'speculative', 'purgeable') if (x := re.search(rf'Pages {nom}:\s+(\d+)', vm)))
            return pages * int(page.group(1)) if page else None
        m = re.search(r'MemAvailable:\s+(\d+) kB', Path('/proc/meminfo').read_text())
        return int(m.group(1)) * 1024 if m else None
    except (OSError, subprocess.SubprocessError):
        return None


def remotion(dispo=None):
    """Options du rendu (moteur/rendu.mjs) : coeurs (onglets), fils (encodeur x264), cache (cache vidéo), gl (moteur graphique).
    Mode discret : un onglet de plus seulement si le Mac garde encore LIBRE_VISE (3 Go) libres avec lui (sauf MONTAGE_COEURS)."""
    r = reglages()
    o = {}
    if r['coeurs']:
        onglets = r['coeurs']
        if r['mode'] == 'discret' and not (os.environ.get('MONTAGE_COEURS') or '').strip().isdigit():
            dispo = memoire_disponible() if dispo is None else dispo
            if dispo:
                onglets = max(1, min(onglets, 1 + int((dispo - LIBRE_VISE - SOCLE_RENDU) // PAR_ONGLET)))
        o.update(coeurs=onglets, fils=r['coeurs'])
    if r['cache']:
        o['cache'] = r['cache']
    if r['gl']:
        o['gl'] = r['gl']
    return o


def resume():
    """Une ligne pour dire comment le montage se partage la machine."""
    r = reglages()
    m = r['machine']
    if r['mode'] == 'libre':
        return 'Pas sur le Mac : pleine vitesse (le mode discret ne sert que sur le Mac de Yohann).'
    sur = f'{m["puce"]}, {m["coeurs"]} cœurs, {m["memoire"] / GO:.0f} Go'
    if r['mode'] == 'rapide':
        return (f'Mode rapide ({sur}) : aucune limite' + (f' sauf {r["coeurs"]} cœurs' if r['coeurs'] else '')
                + ', un seul montage à la fois. Seulement si Yohann l\'a demandé.')
    return (f'Mode discret ({sur}) : {r["coeurs"]} cœur(s) pour le montage, priorité basse, un seul montage à la fois, '
            f'{LIBRE_VISE / GO:.0f} Go de mémoire laissés libres quand c\'est possible' +(f', moteur graphique « {r["gl"]} »' if r['gl'] else '') + '.')


def _priorite_basse():
    """nice 15, et sur Mac la classe « utility » : le programme repart sous taskpolicy (une fois), ses enfants en héritent."""
    if MAC and os.environ.get('MONTAGE_PRIORITE') != 'basse' and shutil.which('taskpolicy'):
        os.environ['MONTAGE_PRIORITE'] = 'basse'
        try:
            if subprocess.run(['taskpolicy', '-c', 'utility', '/usr/bin/true'], capture_output=True, timeout=10).returncode:
                raise OSError('taskpolicy -c utility refusé')         # essayé d'abord : un refus ne doit jamais bloquer le montage
            sys.stdout.flush()
            os.execvp('taskpolicy', ['taskpolicy', '-c', 'utility', sys.executable] + sys.argv)
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        os.nice(max(0, 15 - os.nice(0)))
    except OSError:
        pass


def chemin_ffmpeg(p):
    """Chemin d'un fichier dans un filtre ffmpeg (entre apostrophes) : sous Windows, barres « / » et « : » protégé (C\\:/Users/...)."""
    p = str(p)
    if os.name == 'nt':
        p = p.replace('\\', '/').replace(':', '\\:')
    return p


def chemin_verrou():
    if os.environ.get('MONTAGE_VERROU'):
        return Path(os.environ['MONTAGE_VERROU'])
    return Path(os.environ.get('MONTAGE_CACHE') or Path.home() / '.cache' / 'montage') / 'rendu.lock'


def prendre_verrou(commande, projet=None, dire=print):
    """Un seul montage lourd à la fois sur la machine. Le verrou tient jusqu'à la fin du programme (le système le rend même après un plantage)."""
    import fcntl
    global _verrou
    if _verrou is not None:
        return _verrou
    chemin = chemin_verrou()
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(chemin, os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        try:
            qui = json.loads(os.pread(fd, 4096, 0).decode() or '{}')
        except (ValueError, OSError):
            qui = {}
        de = f'« {qui.get("commande", "?")} »' + (f' sur {Path(qui["projet"]).name}' if qui.get('projet') else '') + (f', depuis {qui["depuis"]}' if qui.get('depuis') else '')
        dire(f'Un autre montage occupe déjà la machine ({de}). Un seul à la fois : j\'attends mon tour…')
        maxi = float(os.environ.get('MONTAGE_ATTENTE') or 60) * 60
        t0 = dit = time.time()
        while True:
            time.sleep(PAS_ATTENTE)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                pass
            if time.time() - t0 > maxi:
                os.close(fd)
                raise RuntimeError(f'un autre montage occupe la machine depuis plus de {maxi / 60:.0f} min ({de}). '
                                   'Je propose : attendre qu\'il finisse et relancer, ou rendre dans le cloud.')
            if time.time() - dit >= 60:
                dit = time.time()
                dire(f'… toujours en attente ({(dit - t0) / 60:.0f} min).')
        dire(f'À mon tour, après {(time.time() - t0) / 60:.1f} min d\'attente.')
    os.ftruncate(fd, 0)
    os.pwrite(fd, json.dumps(dict(pid=os.getpid(), commande=commande, projet=str(projet) if projet else None,
                                  depuis=time.strftime('%H:%M'))).encode(), 0)
    _verrou = fd
    return fd


def discret(commande, projet=None, dire=print):
    """Début d'une commande du kit : pour une commande lourde, priorité basse et verrou, et une ligne qui dit le partage de la machine."""
    r = reglages()
    if commande not in LOURDES:
        return r
    if r['priorite']:
        _priorite_basse()
    dire(resume())
    if r['verrou']:
        prendre_verrou(commande, projet, dire)
    return r
