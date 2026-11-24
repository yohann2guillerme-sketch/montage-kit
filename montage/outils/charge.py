#!/usr/bin/env python3
"""Charge d'une commande sur la machine : sert à vérifier le mode discret (outils/ressources.py), avant et après, sur la vraie machine.

    python3 montage/outils/charge.py -- python3 montage/montage.py final <projet> --plage 0-149

Mesure, toutes les demi-secondes, la commande et tous les processus qu'elle lance (onglets Chromium, ffmpeg, Python) :
- durée ; cœurs occupés en moyenne et au plus fort (1,0 = un cœur plein) ;
- mémoire de la commande au plus fort (somme des mémoires résidentes : un peu plus que la réalité, la mémoire partagée compte plusieurs fois) ;
- mémoire disponible de la machine au plus bas, et ce que l'échange sur disque (swap) a pris en plus ;
- sur Mac : utilisation de la carte graphique au plus fort (ioreg, sans droits d'administrateur).
La dernière ligne reprend tout en JSON.
"""
import json
import os
import re
import resource
import subprocess
import sys
import time

MAC = sys.platform == 'darwin'
TICK = os.sysconf('SC_CLK_TCK') if hasattr(os, 'sysconf') and not MAC else 100


def _secondes(t):
    """« 1-02:03:04 », « 02:03.45 » ou « 3.21 » (ps) → secondes."""
    jours, _, t = t.rpartition('-')
    s = 0.0
    for part in t.split(':'):
        s = s * 60 + float(part)
    return s + (int(jours) * 86400 if jours else 0)


def processus():
    """→ {pid: (ppid, mémoire résidente en octets, temps de calcul cumulé en s)} de toute la machine."""
    out = {}
    if MAC:
        r = subprocess.run(['ps', '-A', '-o', 'pid=,ppid=,rss=,cputime='], capture_output=True, text=True)
        for ligne in r.stdout.splitlines():
            p = ligne.split()
            if len(p) == 4:
                try:
                    out[int(p[0])] = (int(p[1]), int(p[2]) * 1024, _secondes(p[3]))
                except ValueError:
                    pass
        return out
    page = os.sysconf('SC_PAGE_SIZE')
    for d in os.listdir('/proc'):
        if not d.isdigit():
            continue
        try:
            with open(f'/proc/{d}/stat') as f:
                st = f.read()
        except OSError:
            continue
        champs = st[st.rfind(')') + 2:].split()
        out[int(d)] = (int(champs[1]), int(champs[21]) * page, (int(champs[11]) + int(champs[12])) / TICK)
    return out


def famille(tous, racine):
    enfants = {}
    for pid, (pp, _, _) in tous.items():
        enfants.setdefault(pp, []).append(pid)
    vus, pile = set(), [racine]
    while pile:
        p = pile.pop()
        if p in vus or p not in tous:
            continue
        vus.add(p)
        pile.extend(enfants.get(p, []))
    return vus


def memoire_machine():
    """→ (mémoire disponible, échange utilisé) en octets."""
    if MAC:
        vm = subprocess.run(['vm_stat'], capture_output=True, text=True).stdout
        page = int(re.search(r'page size of (\d+)', vm).group(1))
        n = lambda nom: int(re.search(rf'{nom}:\s+(\d+)', vm).group(1)) if re.search(rf'{nom}:\s+(\d+)', vm) else 0
        dispo = (n('Pages free') + n('Pages inactive') + n('Pages speculative') + n('Pages purgeable')) * page
        sw = subprocess.run(['sysctl', '-n', 'vm.swapusage'], capture_output=True, text=True).stdout
        m = re.search(r'used = ([\d.]+)([MG])', sw)
        echange = float(m.group(1)) * (2 ** 30 if m.group(2) == 'G' else 2 ** 20) if m else 0
        return dispo, echange
    info = {}
    with open('/proc/meminfo') as f:
        for ligne in f:
            k, v = ligne.split(':')
            info[k] = int(v.split()[0]) * 1024
    return info.get('MemAvailable', 0), info.get('SwapTotal', 0) - info.get('SwapFree', 0)


def carte_graphique():
    """Mac : utilisation de la carte graphique en %, sinon None."""
    if not MAC:
        return None
    r = subprocess.run(['ioreg', '-r', '-d', '1', '-w', '0', '-c', 'IOAccelerator'], capture_output=True, text=True).stdout
    v = [int(x) for x in re.findall(r'"Device Utilization %"=(\d+)', r)]
    return max(v) if v else None


def mesurer(cmd, pas=0.5):
    dispo0, echange0 = memoire_machine()
    t0 = time.time()
    proc = subprocess.Popen(cmd)
    pointe_mem, pointe_coeurs, dispo_min, echange_max, gpu_max = 0, 0.0, dispo0, echange0, None
    avant, t_avant = {}, t0
    while proc.poll() is None:
        time.sleep(pas)
        tous = processus()
        fam = famille(tous, proc.pid)
        maintenant = time.time()
        temps = {p: tous[p][2] for p in fam}
        pointe_mem = max(pointe_mem, sum(tous[p][1] for p in fam))
        if avant:
            delta = sum(max(0.0, temps[p] - avant.get(p, 0.0)) for p in temps)
            pointe_coeurs = max(pointe_coeurs, delta / max(1e-3, maintenant - t_avant))
        avant, t_avant = temps, maintenant
        dispo, echange = memoire_machine()
        dispo_min, echange_max = min(dispo_min, dispo), max(echange_max, echange)
        g = carte_graphique()
        if g is not None:
            gpu_max = max(gpu_max or 0, g)
    duree = time.time() - t0
    ru = resource.getrusage(resource.RUSAGE_CHILDREN)
    go = 2 ** 30
    return dict(code=proc.returncode, duree_s=round(duree, 1), coeurs_moyenne=round((ru.ru_utime + ru.ru_stime) / max(duree, 1e-3), 2),
                coeurs_pointe=round(pointe_coeurs, 2), memoire_pointe_go=round(pointe_mem / go, 2), dispo_avant_go=round(dispo0 / go, 2),
                dispo_min_go=round(dispo_min / go, 2), echange_en_plus_go=round(max(0, echange_max - echange0) / go, 2), carte_graphique_pointe=gpu_max)


def texte(m):
    t = (f'Durée {m["duree_s"]:.1f} s · cœurs occupés : {m["coeurs_moyenne"]:.1f} en moyenne, {m["coeurs_pointe"]:.1f} au plus · '
         f'mémoire du montage : {m["memoire_pointe_go"]:.2f} Go au plus · mémoire disponible de la machine : {m["dispo_min_go"]:.1f} Go au plus bas '
         f'(avant : {m["dispo_avant_go"]:.1f} Go) · échange sur disque : +{m["echange_en_plus_go"]:.2f} Go')
    if m.get('carte_graphique_pointe') is not None:
        t += f' · carte graphique : {m["carte_graphique_pointe"]} % au plus'
    return t


def main():
    args = sys.argv[1:]
    if args and args[0] == '--':
        args = args[1:]
    if not args:
        print(__doc__)
        return 2
    m = mesurer(args)
    print(texte(m))
    print(json.dumps(m, ensure_ascii=False))
    return m['code']


if __name__ == '__main__':
    sys.exit(main())
