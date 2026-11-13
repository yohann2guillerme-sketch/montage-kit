#!/usr/bin/env python3
"""Tests automatiques du kit de montage.

    python3 montage/tests/test_kit.py            tout (le rendu réel est sauté si le moteur n'est pas installé)
    MONTAGE_TEST_RAPIDE=1 python3 montage/tests/test_kit.py     sans aucun rendu (30 secondes)

Aucun fichier de client : tout est fabriqué par exemples/demo/fabrique.py dans un dossier temporaire.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / 'outils'))
sys.path.insert(0, str(KIT / 'exemples' / 'demo'))

import fiche as F          # noqa: E402
import fabrique            # noqa: E402
import tete                # noqa: E402
import charte              # noqa: E402
import ressources as RES   # noqa: E402

TMP = None
DEMO = None


def setUpModule():
    global TMP, DEMO
    TMP = Path(tempfile.mkdtemp(prefix='montage-test-'))
    os.environ['MONTAGE_VERROU'] = str(TMP / 'rendu.lock')      # les essais n'attendent pas un vrai montage du Mac
    DEMO = fabrique.fabriquer(TMP / 'demo')


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


def resoudre(fiche, tempo=dict(periode=0.5), **kw):
    return F.resoudre(fiche, DEMO, tempo, **kw)


def fiche_demo(**modifs):
    f = json.loads(json.dumps(fabrique.FICHE))
    f.update(modifs)
    return f


def niveaux(rq, niveau):
    return [t for n, t in rq if n == niveau]


class Durees(unittest.TestCase):
    def test_unites(self):
        self.assertEqual(F.en_images(24, 30), 24)
        self.assertEqual(F.en_images('12i', 30), 12)
        self.assertEqual(F.en_images('1.5s', 30), 45)
        self.assertEqual(F.en_images('1,5s', 30), 45)
        self.assertEqual(F.en_images('4t', 30, 0.5), 60)

    def test_temps_sans_musique(self):
        with self.assertRaises(ValueError):
            F.en_images('4t', 30)
        with self.assertRaises(ValueError):
            F.en_images('bientôt', 30)


class Fiche(unittest.TestCase):
    def test_demo_sans_erreur(self):
        calcul, rq = resoudre(fiche_demo())
        self.assertEqual(niveaux(rq, 'erreur'), [])
        self.assertEqual(calcul['n'], 240)                       # 16 temps à 120 par minute = 8 s
        self.assertEqual([(q['t0'], q['t1']) for q in calcul['plans']], [(0, 60), (60, 150), (150, 240)])   # les coupes tombent sur les temps
        self.assertEqual((calcul['l'], calcul['h'], calcul['ips']), (1080, 1920, 30))

    def test_cle_inconnue_et_fichier_absent(self):
        f = fiche_demo(couleur_du_ciel='bleu')
        f['plans'][0]['photo'] = 'sources/absente.jpg'
        f['plans'][1]['vitese'] = 2
        _, rq = resoudre(f)
        self.assertTrue(rq.bloquant)
        self.assertTrue(any('absente.jpg' in t for t in niveaux(rq, 'erreur')))
        att = ' '.join(niveaux(rq, 'attention'))
        self.assertIn('couleur_du_ciel', att)
        self.assertIn('vitese', att)

    def test_texte_trop_large_reduit(self):
        f = fiche_demo()
        f['calques'] = [{'t': 'titre', 'texte': 'UN TITRE BEAUCOUP TROP LONG POUR TENIR', 'y': 600, 'taille': 200}]
        calcul, rq = resoudre(f)
        ligne = calcul['calques'][0]['lignes'][0]
        self.assertLess(ligne['taille'], 200)
        largeur = F.largeur_texte(ligne['texte'], calcul['theme']['titre'], ligne['taille'])
        self.assertLessEqual(largeur, 1080 - 2 * F.ZONES['marge'] + 1)
        self.assertTrue(any('réduit' in t for t in niveaux(rq, 'attention')))

    def test_zones_instagram(self):
        f = fiche_demo()
        f['calques'] = [
            {'t': 'etiquette', 'texte': 'trop haut', 'y': 120},
            {'t': 'etiquette', 'texte': 'trop bas', 'y': 1600},
            {'t': 'titre', 'texte': 'LIMITE', 'y': 1300, 'taille': 120},
            {'t': 'etiquette', 'texte': 'voulu', 'y': 1700, 'hors_zone': True},
            {'t': 'etiquette', 'texte': 'bien placé', 'y': 700},
        ]
        _, rq = resoudre(f)
        att = niveaux(rq, 'attention')
        self.assertTrue(any('calque 1' in t and 'barre du haut' in t for t in att))
        self.assertTrue(any('calque 2' in t and 'légende' in t for t in att))
        self.assertFalse(any('calque 4' in t or 'calque 5' in t for t in att))
        self.assertTrue(any('calque 3' in t and 'Meta' in t for t in niveaux(rq, 'conseil')))

    def test_trop_de_flashs(self):
        f = fiche_demo()
        f['plans'][1]['effets'] = [{'t': 'flash', 'at': k * 6, 'd': 3} for k in range(5)]
        _, rq = resoudre(f)
        self.assertTrue(any('flash' in t for t in niveaux(rq, 'erreur')))

    def test_texte_derriere_sans_masque(self):
        f = fiche_demo()
        f['calques'] = [{'t': 'titre', 'texte': 'DERRIÈRE', 'y': 500, 'plan': 'B', 'derriere': True}]
        _, rq = resoudre(f)
        self.assertTrue(any('masque' in t for t in niveaux(rq, 'erreur')))

    def test_sous_titres(self):
        f = fiche_demo()
        f['plans'][1]['son'] = True
        f['calques'] = [{'t': 'sous-titres', 'plan': 'B', 'mots': 'auto'}]
        mots = [[m, 0.2 + 0.3 * i, 0.2 + 0.3 * i + 0.25] for i, m in enumerate('on vous montre la chaussure du jour ici'.split())]
        calcul, rq = resoudre(f, paroles={'B': mots})
        self.assertEqual(niveaux(rq, 'erreur'), [])
        st = calcul['calques'][0]
        dits = [m['m'] for g in st['groupes'] for ligne in g['lignes'] for m in ligne]
        self.assertEqual(dits, [m[0] for m in mots])
        self.assertTrue(all(sum(len(ligne) for ligne in g['lignes']) <= 3 for g in st['groupes']))
        self.assertTrue(all(g['a'] > g['de'] for g in st['groupes']))
        self.assertFalse(any('boutons' in t for t in niveaux(rq, 'attention')))   # restent à gauche des boutons d'Instagram

    def test_texte_lisible_sur_sa_pastille(self):
        def sous_titres(theme, **plus):
            f = fiche_demo(theme=theme)
            f['plans'][1]['son'] = True
            f['calques'] = [{'t': 'sous-titres', 'plan': 'B', 'mots': [['bonjour', 0.3, 0.8]], 'style': 'pastille', **plus}]
            return resoudre(f)[0]['calques'][0]
        self.assertEqual(sous_titres('neutre')['couleur_sur_actif'], 'encre')                         # pastille blanche : mot en sombre (il était blanc sur blanc)
        self.assertEqual(sous_titres('telemetrie')['couleur_sur_actif'], 'encre')
        self.assertEqual(sous_titres('foulees')['couleur_sur_actif'], 'clair')                        # pastille rouge : mot en blanc
        self.assertEqual(sous_titres('neutre', couleur_active='#0B5FFF')['couleur_sur_actif'], 'clair')
        self.assertEqual(sous_titres('foulees', couleur_sur_actif='#000000')['couleur_sur_actif'], '#000000')   # un choix écrit dans la fiche est gardé
        f = fiche_demo()
        f['calques'] = [{'t': 'etiquette', 'texte': 'sur fond clair', 'x': 72, 'y': 300, 'align': 'gauche', 'fond': 'clair'},
                        {'t': 'etiquette', 'texte': 'sur fond sombre', 'x': 72, 'y': 400, 'align': 'gauche', 'fond': 'encre'}]
        self.assertEqual([c['couleur'] for c in resoudre(f)[0]['calques']], ['encre', 'clair'])

    def test_regles_de_lisibilite(self):
        """La barre de qualité du skill short-editing, vérifiée à chaque fiche : gros sous-titres, 2 lignes, rien sous 34 px, un changement toutes les 2 à 4 s."""
        def sous_titres(phrase, **plus):
            f = fiche_demo()
            f['plans'][1].update(son=True, duree='4.5s')
            f['calques'] = [{'t': 'sous-titres', 'plan': 'B', 'mots': [[m, 0.3 + 0.4 * i, 0.3 + 0.4 * i + 0.35] for i, m in enumerate(phrase.split())], **plus}]
            calcul, rq = resoudre(f)
            return calcul['calques'][0], calcul, rq
        st, calcul, rq = sous_titres('Aujourd’hui, on vous présente la chaussure du jour.')
        self.assertEqual(st['taille'], 84)                                                            # gros sous-titres par défaut
        self.assertLessEqual(st['y'] + 2 * 1.18 * st['taille'], calcul['zones_instagram']['bas_conseille'] + 1)   # deux lignes au-dessus de la légende
        groupes = [[[m['m'] for m in ligne] for ligne in g['lignes']] for g in st['groupes']]
        self.assertEqual(groupes, [[['Aujourd’hui,'], ['on', 'vous']], [['présente', 'la'], ['chaussure']], [['du', 'jour.']]])   # lignes égales, pas de mot seul à la fin
        self.assertTrue(all(len(g['lignes']) <= 2 for g in st['groupes']))
        st, _, _ = sous_titres('Venez l’essayer, on vous attend.')
        self.assertEqual([[m['m'] for ligne in g['lignes'] for m in ligne] for g in st['groupes']], [['Venez', 'l’essayer,'], ['on', 'vous', 'attend.']])   # coupé à la virgule
        st, _, _ = sous_titres('une paire anticonstitutionnellement confortable')
        self.assertLess(st['taille'], 84)                                                             # un mot très long : la taille baisse pour qu'il tienne
        self.assertGreaterEqual(st['taille'], 34)
        self.assertEqual(sous_titres('bonjour', taille=60, y=900)[0]['taille'], 60)                   # une taille écrite dans la fiche est gardée
        f = fiche_demo()
        f['calques'][1]['taille'] = 26
        self.assertTrue(any('trop petit' in t for t in niveaux(resoudre(f)[1], 'conseil')))
        self.assertFalse(any('trop petit' in t or 'rien ne change' in t for t in niveaux(resoudre(fiche_demo())[1], 'conseil')))
        f = fiche_demo(accents=None)
        f['plans'] = [{'id': 'A', 'source': 'sources/video1.mp4', 'de': 0, 'duree': '4.9s'}]
        f['calques'] = [{'t': 'titre', 'texte': 'UN SEUL PLAN', 'y': 560, 'de': 0, 'a': '1s'}]
        self.assertTrue(any('rien ne change' in t for t in niveaux(resoudre(f)[1], 'conseil')))

    def test_droits_de_la_musique(self):
        def remarques(**mus):
            f = fiche_demo()
            f['musique'] = {'fichier': 'sources/musique.wav', 'debut': 0, **mus}
            return resoudre(f)[1]
        parle_des_droits = lambda rq, niveau: [t for t in niveaux(rq, niveau) if 'droits' in t or 'credit' in t or 'commerce' in t]
        self.assertTrue(parle_des_droits(remarques(), 'attention'))                                   # rien n'est dit : on prévient
        self.assertTrue(parle_des_droits(remarques(droits='libre'), 'attention'))                     # libre, mais sans crédit
        rq = remarques(droits='libre', credit='Titre, auteur, source, licence')
        self.assertEqual(parle_des_droits(rq, 'attention') + parle_des_droits(rq, 'erreur'), [])
        self.assertTrue(any('sans musique' in t for t in niveaux(remarques(droits='sous_droits'), 'conseil')))
        self.assertTrue(parle_des_droits(remarques(droits='achetee'), 'erreur'))                      # valeur inconnue
        _, rq = resoudre(fiche_demo())
        self.assertEqual(parle_des_droits(rq, 'attention'), [])                                       # la démonstration est en règle

    def test_bruitage_inconnu_et_bibliotheque(self):
        rq = resoudre(fiche_demo(sons=[{'son': 'nexistepas', 'at': 10}]))[1]
        self.assertTrue(any('bruitage introuvable' in t for t in niveaux(rq, 'erreur')))               # dit dès « verifier », pas au mixage
        manifeste = F.SONS_PLUS / 'manifest.json'
        self.assertTrue(manifeste.is_file(), msg='skill sound-effects absent : le réinstaller, ou retirer sa bibliothèque du README et de montage-pro')
        sons = json.loads(manifeste.read_text(encoding='utf-8'))['bundled']
        self.assertGreaterEqual(len(sons), 50)
        for e in sons:
            self.assertTrue((F.SONS_PLUS / e['file']).is_file(), msg=e['file'])
            self.assertTrue(e['license'].startswith('CC0'), msg=f'{e["file"]} : {e["license"]}')
        nom = sons[0]['file'].rsplit('.', 1)[0]
        self.assertEqual(F.fichier_son(nom, DEMO), F.SONS_PLUS / sons[0]['file'])
        calcul, rq = resoudre(fiche_demo(sons=[{'son': nom, 'at': 10}]))
        self.assertEqual(niveaux(rq, 'erreur'), [])
        self.assertIn(nom, [s['son'] for s in calcul['_sons']])

    def test_sous_titres_de_toute_une_prise(self):
        f = fiche_demo()
        f['plans'] = [{'id': 'P01', 'source': 'sources/video1.mp4', 'de': 0.0, 'duree': '1.5s', 'son': True},
                      {'id': 'P02', 'source': 'sources/video1.mp4', 'de': 2.0, 'duree': '1.5s', 'son': True, 'zoom': 1.12}]
        f['calques'] = [{'t': 'sous-titres', 'plan': 'tous', 'mots': 'auto'}]
        mots = [['un', 0.2, 0.4], ['deux', 0.5, 0.8], ['trois', 0.9, 1.2], ['raté', 1.6, 1.9], ['quatre', 2.1, 2.5], ['cinq', 2.6, 3.0]]
        calcul, rq = resoudre(f, prises={'video1.mp4': mots})
        self.assertEqual(niveaux(rq, 'erreur'), [])
        st = [c for c in calcul['calques'] if c['t'] == 'sous-titres']
        self.assertEqual(len(st), 2)                                                                  # un calque écrit, un par plan qui parle
        dits = [[m['m'] for g in c['groupes'] for ligne in g['lignes'] for m in ligne] for c in st]
        self.assertEqual(dits, [['un', 'deux', 'trois'], ['quatre', 'cinq']])                         # le mot dit dans le silence coupé a disparu
        self.assertGreaterEqual(st[1]['groupes'][0]['de'], calcul['plans'][1]['t0'])                  # les mots du 2e plan partent avec lui
        calcul, rq = resoudre(f, paroles={'P01': [['corrigé', 0.2, 0.6]]}, prises={'video1.mp4': mots})
        self.assertEqual([m['m'] for g in calcul['calques'][0]['groupes'] for ligne in g['lignes'] for m in ligne], ['corrigé'])   # les paroles du plan passent avant
        for q in f['plans']:
            q.pop('son')
        self.assertTrue(any('tous' in t for t in niveaux(resoudre(f, prises={'video1.mp4': mots})[1], 'erreur')))

    def test_mot_a_cheval_sur_une_coupe(self):
        """Défaut du 13/11 (Reels des stands) : un mot à cheval sur une coupe s'affichait dans les deux plans (« mots en double »).
        Il ne s'affiche plus que dans le plan qui en garde la plus grande part, le premier si les parts sont égales."""
        def dits(plans, mots):
            f = fiche_demo()
            f['plans'] = [{'id': f'P{k + 1:02d}', 'source': 'sources/video1.mp4', 'de': de, 'duree': f'{d}s', 'son': True} for k, (de, d) in enumerate(plans)]
            f['calques'] = [{'t': 'sous-titres', 'plan': 'tous', 'mots': 'auto'}]
            calcul, rq = resoudre(f, prises={'video1.mp4': mots})
            self.assertEqual(niveaux(rq, 'erreur'), [])
            return [[m['m'] for g in c['groupes'] for ligne in g['lignes'] for m in ligne] for c in calcul['calques'] if c['t'] == 'sous-titres']
        mots = [['un', 0.2, 0.4], ['deux', 0.5, 0.8], ['trois', 1.2, 1.7], ['quatre', 2.1, 2.5], ['cinq', 2.9, 3.4], ['six', 3.5, 3.9]]
        # « trois » : 0,3 s dans P01, 0,1 s dans P02 ; « cinq » : 0,2 s dans P02, 0,3 s dans P03 (avant : chacun deux fois)
        self.assertEqual(dits([(0.0, 1.5), (1.6, 1.5), (3.1, 1.2)], mots), [['un', 'deux', 'trois'], ['quatre'], ['cinq', 'six']])
        mots[2] = ['trois', 1.3, 1.7]                                                                        # 0,2 s de chaque côté de la coupe
        self.assertEqual(dits([(0.0, 1.5), (1.5, 1.5)], mots), [['un', 'deux', 'trois'], ['quatre', 'cinq']])     # parts égales : le 1er plan
        self.assertEqual(dits([(0.0, 1.0), (0.0, 1.0)], mots), [['un', 'deux'], ['un', 'deux']])                 # passage répété exprès : gardé

    def test_stabilise(self):
        f = fiche_demo()
        f['plans'][1]['stabilise'] = 'beaucoup'
        _, rq = resoudre(f)
        self.assertTrue(any('stabilise' in t for t in niveaux(rq, 'erreur')))
        f['plans'][1]['stabilise'] = 2.5
        calcul, rq = resoudre(f)
        self.assertEqual(niveaux(rq, 'erreur'), [])
        self.assertEqual(calcul['plans'][1]['_stabilise'], 2.5)

    def test_cadre_style_affiche(self):
        f = fiche_demo()
        f['plans'][1]['cadre'] = {'l': 800, 'y': 1080, 'angle': -2.5, 'de': '0.5s', 'entree': 12, 'pli': 3}
        _, rq = resoudre(f)
        self.assertTrue(any('cadre, clés inconnues : pli' in t for t in niveaux(rq, 'erreur')))
        del f['plans'][1]['cadre']['pli']
        calcul, rq = resoudre(f)
        self.assertEqual(niveaux(rq, 'erreur'), [])
        g = calcul['plans'][1]['cadre']
        self.assertEqual((g['l'], g['h'], g['de'], g['entree']), (800, 800, 15, 12))
        # avant le rangement : plein écran ; après : la photo de 800 px, centrée en y = 1080, penchée de -2,5°
        g0, g1 = tete.geo_cadre(g, 0, 1080, 1920), tete.geo_cadre(g, 40, 1080, 1920)
        self.assertEqual((g0['s'], g0['cx'], g0['cy'], g0['rot']), (1.0, 540, 960, 0))
        self.assertAlmostEqual(g1['s'], 800 / 1080); self.assertAlmostEqual(g1['cy'], 1080); self.assertAlmostEqual(g1['rot'], -2.5)
        b = tete._vers_cadre((0, 0, 1080, 1920), dict(g1, rot=0), 1080, 1920)
        self.assertAlmostEqual(b[0], 140); self.assertAlmostEqual(b[2], 940)

    def test_public_sans_cles_privees(self):
        calcul, _ = resoudre(fiche_demo())
        texte = json.dumps(F.public(calcul))
        self.assertNotIn('"_', texte)
        self.assertNotIn(str(DEMO), texte)                       # aucun chemin de la machine dans ce que lit le moteur


class Clip(unittest.TestCase):
    """Clip en largeur sur la chanson de l'artiste : format 16:9, playback calé sur la musique, bandes noires, titres de bande-annonce."""
    def test_format_16_9_sans_regles_d_instagram(self):
        f = fiche_demo(format='16:9')
        f['plans'] = [{'id': f'P{i}', 'source': 'sources/video1.mp4', 'de': 0, 'duree': '3s'} for i in range(32)]   # 96 s
        c, rq = resoudre(f)
        self.assertEqual((c['l'], c['h']), (1920, 1080))
        self.assertFalse(c['zones_instagram']['reel'])
        self.assertFalse(any('Instagram' in t for _, t in rq), msg=[t for _, t in rq if 'Instagram' in t])
        self.assertTrue(any('format inconnu' in t for t in niveaux(resoudre(fiche_demo(format='21:9'))[1], 'erreur')))

    def test_droits_artiste(self):
        f = fiche_demo()
        f['musique'] = {**f['musique'], 'droits': 'artiste', 'credit': ''}
        self.assertTrue(any('credit' in t for t in niveaux(resoudre(f)[1], 'attention')))
        f['musique']['credit'] = 'Titre, artiste'
        rq = resoudre(f)[1]
        self.assertFalse([t for n, t in rq if n in ('erreur', 'attention') and ('droits' in t or 'credit' in t)])

    def test_calage_d_une_source(self):
        f = fiche_demo(calage={'sources/video1.mp4': 1.5})
        f['musique'] = {**f['musique'], 'debut': 0}
        f['plans'] = [{'id': 'A', 'source': 'sources/video1.mp4', 'de': 0, 'duree': '2s'},
                      {'id': 'B', 'source': 'sources/video1.mp4', 'duree': '1s'}]
        c, rq = F.resoudre(f, DEMO, dict(periode=0.5, debut_cale=0.0))
        self.assertTrue(any('décalées' in t for t in niveaux(rq, 'attention')))     # « de » écrit à la main sur A : décalage annoncé
        b = c['plans'][1]
        self.assertTrue(b['cale'])
        self.assertAlmostEqual(b['src'], 2.0 - 1.5, places=3)                        # le plan commence à 2 s de la chanson
        c, _ = F.resoudre(f, DEMO, dict(periode=0.5, debut_cale=0.5))                # musique démarrée sur un temps, 0,5 s plus loin
        self.assertAlmostEqual(c['plans'][1]['src'], 2.5 - 1.5, places=3)
        f['plans'][1]['vitesse'] = 0.5
        self.assertTrue(any('vitesse' in t for t in niveaux(F.resoudre(f, DEMO, dict(periode=0.5))[1], 'erreur')))

    def test_bandes_et_titre_cinema(self):
        f = fiche_demo(format='16:9', theme='cinema')
        f['calques'] = [{'t': 'bandes', 'de': 0, 'a': '2s'}, {'t': 'titre', 'texte': 'LE TITRE', 'y': 430, 'anim': 'cinema', 'duree_anim': '1s', 'fondu': '0.5s', 'de': 0, 'a': '3s'}]
        c, rq = resoudre(f)
        self.assertEqual(c['calques'][0]['hauteur'], round((1080 - 1920 / 2.39) / 2))
        self.assertEqual((c['calques'][1]['duree_anim'], c['calques'][1]['fondu']), (30, 15))
        self.assertFalse(niveaux(rq, 'erreur'))
        f['calques'] = [{'t': 'bandes', 'ratio': 0.5, 'de': 0, 'a': '2s'}]
        self.assertTrue(any('aucune bande' in t for t in niveaux(resoudre(f)[1], 'erreur')))

    def test_double_exposition_et_ecran_partage(self):
        f = fiche_demo(format='16:9')
        src = 'sources/video1.mp4'
        f['calques'] = []
        f['plans'] = [{'id': 'A', 'source': src, 'de': 0, 'duree': '1s', 'double': {'source': src, 'de': 0.5}},
                      {'id': 'B', 'source': src, 'de': 0, 'duree': '1s', 'double': {'source': src, 'de': 0, 'mode': 'partage'}}]
        c, rq = resoudre(f)
        self.assertFalse(niveaux(rq, 'erreur'), msg=niveaux(rq, 'erreur'))
        a, b = c['plans'][0], c['plans'][1]
        self.assertEqual((a['double_mode'], a['double_force']), ('superpose', 0.45))
        self.assertEqual((b['double_mode'], b['double_force']), ('partage', 1.0))
        self.assertEqual((a['double']['t0'], a['double']['t1']), (a['t0'], a['t1']))   # la deuxième image dure exactement le plan
        self.assertAlmostEqual(a['double']['src'], 0.5)
        f['plans'][0]['double'] = {'source': src, 'mode': 'moitie'}
        self.assertTrue(any('mode' in t for t in niveaux(resoudre(f)[1], 'erreur')))
        f['plans'][0]['double'] = {'source': src, 'de': 9999}
        self.assertTrue(any('sort de la vidéo' in t for t in niveaux(resoudre(f)[1], 'erreur')))

    def test_lumiere_et_bandes_depuis_le_noir(self):
        f = fiche_demo(format='16:9', theme='cinema')
        f['calques'] = [{'t': 'lumiere', 'de': 0, 'a': '2s', 'force': 0.6, 'cote': 'droite'},
                        {'t': 'bandes', 'de': 0, 'a': '2s', 'depuis_noir': True}]
        c, rq = resoudre(f)
        self.assertFalse(niveaux(rq, 'erreur'), msg=niveaux(rq, 'erreur'))
        lu, ba = c['calques']
        self.assertEqual((lu['force'], lu['cote'], lu['fondu']), (0.6, 'droite', 10))
        self.assertTrue(ba['depuis_noir'])

    def test_cadrage_qui_suit_le_visage(self):
        from cadrage import chemin, commandes
        ts = np.array([0.0, 1.0, 2.0]); xs = np.array([0.2, 0.8, 0.98]); ys = np.array([0.5, 0.5, 0.5])
        x0, y0 = chemin((ts, xs, ys), 61, 30, 1920, 1080, 3840, 2160)
        self.assertEqual(len(x0), 61)
        self.assertTrue((x0 >= 0).all() and (x0 <= 3840 - 1920).all() and (y0 >= 0).all() and (y0 <= 2160 - 1080).all())
        self.assertTrue((x0 % 2 == 0).all())
        self.assertLess(np.abs(np.diff(x0)).max(), 120)                        # lissé : pas de saut d'une image à l'autre
        self.assertGreater(x0[-1], x0[0])                                       # suit le visage vers la droite
        f = commandes(x0[:2], y0[:2], 30, TMP / 'c.cmd')
        self.assertEqual(Path(f).read_text().splitlines()[1], f'0.0333 crop x {x0[1]}, crop y {y0[1]};')
        fi = fiche_demo(); fi['plans'][1]['cadrage'] = 'tete'
        self.assertTrue(any('cadrage' in t for t in niveaux(resoudre(fi)[1], 'erreur')))

    def test_caler_retrouve_le_decalage(self):
        from calage import caler
        import soundfile as sf
        rng = np.random.default_rng(7)
        sr = 16000
        t = np.arange(30 * sr) / sr
        bornes = np.sort(rng.uniform(0, 30, 90))                    # une « chanson » : des notes de durées irrégulières, plus des coups
        notes = rng.uniform(200, 1500, 91)[np.searchsorted(bornes, t)]
        coups = np.zeros(len(t)); coups[(rng.uniform(0, 30, 70) * sr).astype(int)] = 1
        chanson = np.sin(2 * np.pi * notes * t) * 0.3 + np.convolve(coups, np.exp(-np.arange(400) / 60) * rng.standard_normal(400), 'same') * 0.6
        prise = chanson[int(8.25 * sr):int(27 * sr)] * 0.5 + rng.standard_normal(int(18.75 * sr)) * 0.05   # filmée dans la rue : plus faible, du bruit
        sf.write(TMP / 'chanson.wav', chanson, sr); sf.write(TMP / 'prise.wav', prise, sr)
        r = caler(TMP / 'chanson.wav', TMP / 'prise.wav')
        self.assertAlmostEqual(r['decalage'], 8.25, delta=0.02)
        self.assertTrue(r['sur'], msg=r)
        sf.write(TMP / 'autre.wav', rng.standard_normal(15 * sr) * 0.1, sr)     # aucun lien avec la chanson
        self.assertFalse(caler(TMP / 'chanson.wav', TMP / 'autre.wav')['sur'])


class Paroles(unittest.TestCase):
    def test_recoller(self):
        from paroles import recoller
        m = recoller([(' ce', 1, 1.2), (' qu', 1.2, 1.3), ("'on", 1.3, 1.4), (' celle', 2, 2.2), ('-ci', 2.2, 2.4), (' !', 2.4, 2.5), (' vous,', 3, 3.2)])
        self.assertEqual([x[0] for x in m], ['ce', 'qu’on', 'celle-ci !', 'vous,'])
        self.assertEqual(m[1][1:], [1.2, 1.4])


    def test_phrases_reprises_et_plans(self):
        from paroles import phrases, reprises, plans_proposes
        def dit(texte, t):      # des mots de 0,3 s qui se suivent, à partir de t secondes
            return [[m, round(t + 0.32 * i, 2), round(t + 0.32 * i + 0.3, 2)] for i, m in enumerate(texte.split())]
        mots = (dit('Bonjour à tous.', 0.5) + dit('Aujourd’hui on vous', 2.5) + dit('Aujourd’hui on vous présente la chaussure du jour.', 5.0)
                + dit('Venez l’essayer au magasin.', 8.5))
        ph = phrases(mots)
        self.assertEqual([p['mots'] for p in ph], [3, 3, 8, 4])                                       # coupé aux silences
        self.assertEqual((ph[0]['de'], ph[0]['a']), (0.38, 1.64))                                     # petite marge avant et après
        self.assertEqual([m[0] for m in ph[0]['paroles']], ['Bonjour', 'à', 'tous.'])
        self.assertTrue(all(a['a'] <= b['de'] for a, b in zip(ph, ph[1:])))                           # jamais deux phrases qui se chevauchent
        self.assertEqual(reprises(ph), [(1, 2)])                                                      # le faux départ est repéré
        plans = plans_proposes(ph, 'sources/prise.mov', sauf={1})
        self.assertEqual([q['id'] for q in plans], ['P01', 'P03', 'P04'])
        self.assertEqual([q.get('zoom') for q in plans], [None, 1.12, None])                          # zoom un plan sur deux
        self.assertEqual(plans[1]['cy'], 0.482)                                                       # les yeux (au tiers haut) ne bougent pas
        self.assertEqual((plans[0]['de'], plans[0]['duree'], plans[0]['son']), (0.38, '1.26s', True))
        self.assertNotIn('zoom', plans_proposes(ph, 'sources/prise.mov', zoom=1)[1])                  # zoom 1 : aucun plan resserré
        self.assertEqual(plans_proposes(ph, 'sources/prise2.mov', prefixe='Q')[0]['id'], 'Q01')       # une deuxième prise garde ses propres noms
        self.assertEqual(len(phrases([['Oui.', 0, 0.3], ['Et', 0.6, 0.8]])), 2)                       # après un point, un petit silence suffit
        self.assertEqual(len(phrases([['oui', 0, 0.3], ['et', 0.6, 0.8]])), 1)
        serre = phrases([['Oui.', 0, 0.3], ['Et', 0.6, 0.8]])
        self.assertLessEqual(serre[0]['a'], serre[1]['de'])

    def _niveau(self, parle, duree=12.0, bruit=-60.0, voix=-20.0, autres=()):
        """Niveau du son d'une prise inventée, tranche de 10 ms par tranche : le bruit de la pièce, et la voix là où on parle."""
        db = np.full(int(round(duree * 100)), bruit)
        for a, b in parle:
            db[int(round(a * 100)):int(round(b * 100))] = voix
        for a, b, n in autres:
            db[int(round(a * 100)):int(round(b * 100))] = n
        return db, 0.01

    def test_coupes_sur_le_son_reel(self):
        from paroles import phrases, voix_nette
        # la transcription se trompe aux deux bouts : débuts en avance, fins en avance ou très en retard, un mot étiré sur un silence
        mots = [['Bonjour', 0.7, 1.6], ['à', 1.6, 1.9], ['tous.', 1.9, 2.75], ['On', 4.5, 4.8], ['commence', 4.8, 6.7],
                ['ici', 6.8, 7.3], ['même.', 7.3, 8.9], ['Venez', 9.2, 9.9], ['vite.', 9.9, 10.8]]
        niveau = self._niveau([(1.0, 3.0), (4.5, 6.0), (6.8, 8.0), (9.5, 11.0)])
        self.assertTrue(voix_nette(niveau))
        ph = phrases(mots, niveau=niveau)
        self.assertEqual([p['texte'] for p in ph], ['Bonjour à tous.', 'On commence', 'ici même.', 'Venez vite.'])   # le silence caché recoupe la phrase
        self.assertEqual([(p['de'], p['a']) for p in ph], [(0.88, 3.2), (4.38, 6.2), (6.68, 8.2), (9.38, 11.2)])     # bords du son réel, avec la marge
        self.assertEqual(ph[1]['paroles'][-1], ['commence', 4.8, 6.0])                                # le mot étiré s'arrête avec la voix
        self.assertEqual(ph[2]['paroles'][-1], ['même.', 7.3, 8.0])
        self.assertEqual(ph[0]['paroles'][0], ['Bonjour', 1.0, 1.6])
        recales = [m for p in ph for m in p['paroles']]
        self.assertEqual([(p['de'], p['a']) for p in phrases(recales, niveau=niveau)], [(p['de'], p['a']) for p in ph])   # relancer ne change rien
        self.assertFalse(any('a_ecouter' in p for p in ph))
        court = self._niveau([(1.0, 3.0), (4.5, 6.0), (6.8, 8.0), (9.5, 11.0)], duree=11.05)
        self.assertEqual(phrases(mots, niveau=court)[-1]['a'], 11.05)                                 # jamais plus loin que la fin de la prise
        self.assertEqual(phrases(mots, duree=10.9)[-1]['a'], 10.9)

    def test_mot_dit_tout_bas_et_bruits(self):
        from paroles import phrases, voix_nette
        # un mot dit tout bas (sous le seuil) au milieu d'une phrase : la transcription l'a entendu, on ne coupe pas dedans
        bas = self._niveau([(1.0, 2.0), (2.8, 4.0)], duree=6.0, autres=[(2.0, 2.8, -52.0)])
        mots = [['un', 1.0, 1.5], ['deux', 1.5, 2.0], ['trois', 2.1, 2.7], ['quatre', 2.8, 3.4], ['cinq.', 3.4, 4.0]]
        ph = phrases(mots, niveau=bas)
        self.assertEqual([(p['de'], p['a'], p['mots']) for p in ph], [(0.88, 4.2, 5)])
        self.assertEqual(len(phrases([m for m in mots if m[0] != 'trois'], niveau=bas)), 2)           # sans ce mot, c'est un vrai silence
        # deux claquements de 20 ms après la phrase : ce n'est pas de la parole, la coupe ne les attend pas
        clics = self._niveau([(1.0, 2.0)], duree=6.0, autres=[(2.3, 2.32, -30.0), (2.6, 2.62, -30.0)])
        ph = phrases([['oui', 0.9, 1.5], ['merci.', 1.5, 2.65]], niveau=clics)
        self.assertEqual((ph[0]['de'], ph[0]['a']), (0.88, 2.2))
        # la voix continue après le dernier mot (un « euh » collé) : coupe au moment le plus calme, et signalée
        colle = self._niveau([(1.0, 4.0)], duree=6.0, autres=[(1.9, 1.95, -35.0)])
        ph = phrases([['Bonjour.', 1.0, 1.8]], niveau=colle)
        self.assertEqual((ph[0]['a'], ph[0].get('a_ecouter')), (1.91, 'fin'))
        # trop de bruit autour de la voix : le son ne permet pas de poser les coupes
        self.assertFalse(voix_nette(self._niveau([(1.0, 3.0)], duree=6.0, bruit=-30.0)))

    def test_prise_transcrite(self):
        """La commande « transcrire <projet> <fichier> » : plans proposés, zoom selon la taille de la vidéo, mots recalés sur le son."""
        import soundfile as sf
        projet = TMP / 'prise'
        (projet / 'sources').mkdir(parents=True)
        sr = 16000
        t = np.arange(int(4.0 * sr)) / sr
        voix = np.where((t >= 0.5) & (t < 1.5) | (t >= 2.5) & (t < 3.5), 0.3 * np.sin(2 * np.pi * 220 * t), 0.0).astype(np.float32)
        sf.write(projet / 'voix.wav', voix, sr)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=gray:s=1080x1920:r=30:d=4', '-i', str(projet / 'voix.wav'),
                        '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(projet / 'sources' / 'prise.mp4')], check=True)
        cache = projet / '.travail' / 'prises' / 'prise.mp4.json'
        cache.parent.mkdir(parents=True)
        cache.write_text(json.dumps([['Bonjour.', 0.3, 1.2], ['Venez', 2.2, 3.0], ['vite.', 3.0, 3.9]]), encoding='utf-8')   # comme une transcription : bords faux
        r = subprocess.run([sys.executable, str(KIT / 'montage.py'), 'transcrire', str(projet), 'sources/prise.mp4'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, msg=r.stdout[-800:] + r.stderr[-800:])
        texte = r.stdout
        plans = [json.loads(l.strip().rstrip(',')) for l in texte.splitlines() if l.strip().startswith('{"id"')]
        self.assertEqual([q['id'] for q in plans], ['P01', 'P02'])
        self.assertAlmostEqual(plans[0]['de'], 0.38, delta=0.04)                                      # 0,12 s avant la vraie voix, pas à 0,3 s
        self.assertAlmostEqual(plans[1]['de'] + float(plans[1]['duree'][:-1]), 3.7, delta=0.05)       # 0,2 s après la vraie fin, pas à 3,9 s
        self.assertEqual(plans[1].get('zoom'), 1.08)                                                  # vidéo de 1080 px : zoom limité pour rester net
        self.assertIn('1080 px', texte)
        mots = json.loads(cache.read_text(encoding='utf-8'))
        self.assertAlmostEqual(mots[0][1], 0.5, delta=0.03)                                           # les mots suivent le son réel
        self.assertAlmostEqual(mots[2][2], 3.5, delta=0.03)
        f = {'nom': 'prise', 'plans': plans, 'calques': [{'t': 'sous-titres', 'plan': 'tous', 'mots': 'auto', 'style': 'pastille'}]}
        calcul, rq = F.resoudre(f, projet, prises={'prise.mp4': mots})
        self.assertEqual([t for t in niveaux(rq, 'erreur') + niveaux(rq, 'attention') if 'très court' not in t], [])   # la fiche proposée passe sans remarque
        self.assertEqual([[m['m'] for g in c['groupes'] for ligne in g['lignes'] for m in ligne] for c in calcul['calques']], [['Bonjour.'], ['Venez', 'vite.']])


class Tempo(unittest.TestCase):
    def _clics(self, fichier, bpm, depart, duree=20.0, sr=48000):
        import soundfile as sf
        n = int(duree * sr); x = np.zeros(n, np.float32); rng = np.random.default_rng(1); per = 60.0 / bpm; k = 0
        while depart + k * per < duree:
            i = int(round((depart + k * per) * sr)); t = np.arange(int(0.06 * sr)) / sr
            c = rng.standard_normal(len(t)) * np.exp(-t / 0.012)
            m = min(len(c), n - i); x[i:i + m] += 0.5 * c[:m]; k += 1
        sf.write(fichier, np.stack([x, x], 1), sr)

    def _ecart(self, r, per, depart):
        return abs(((r['phase'] - depart + per / 2) % per) - per / 2)

    def test_clics(self):
        from tempo import analyser
        f = TMP / 'clics.wav'
        self._clics(f, 128.0, 0.10)
        r = analyser(f)
        self.assertAlmostEqual(r['bpm'], 128.0, delta=0.1)
        self.assertLess(self._ecart(r, 60 / 128.0, 0.10), 0.008)          # moins de 8 ms : un quart d'image

    def test_contretemps(self):
        """Charley à contretemps plus aigu que la grosse caisse : le calage doit rester sur la grosse caisse."""
        from tempo import analyser
        f = TMP / 'boucle.wav'
        fabrique.musique(f, 120.0, 16.0, 0.2)
        r = analyser(f)
        self.assertAlmostEqual(r['bpm'], 120.0, delta=0.1)
        self.assertLess(self._ecart(r, 0.5, 0.2), 0.008)


class Mix(unittest.TestCase):
    def test_niveau_final(self):
        from mix import mixer, mesure, SR
        import soundfile as sf
        calcul, rq = resoudre(fiche_demo())
        self.assertFalse(rq.bloquant)
        travail = TMP / 'travail-mix'
        info = mixer(calcul, DEMO, travail, dict(periode=0.5, debut_cale=0.0), journal=lambda *a: None)
        self.assertTrue(info['musique'])
        self.assertGreaterEqual(info['bruitages'], 2)                     # un bruitage par transition
        x, sr = sf.read(travail / 'public' / 'audio' / 'mix.wav', dtype='float32')
        self.assertEqual(sr, SR)
        self.assertEqual(len(x), int(round(calcul['n'] / calcul['ips'] * SR)))
        lufs, crete = mesure(x)
        self.assertAlmostEqual(lufs, -14.0, delta=0.6)
        self.assertLessEqual(crete, -0.9)
        seuls, _ = sf.read(travail / 'public' / 'audio' / 'sons-seuls.wav', dtype='float32')
        self.assertLess(np.abs(seuls).mean(), np.abs(x).mean())           # sans la musique, il reste moins de son


    def test_coupes_a_ecouter(self):
        """Une coupe en plein mot est donnée à écouter, une coupe dans un silence non."""
        from mix import mixer
        import soundfile as sf
        projet = TMP / 'coupes'
        (projet / 'sources').mkdir(parents=True)
        sr = 48000
        t = np.arange(int(5.0 * sr)) / sr
        voix = np.where((t >= 1.0) & (t < 2.0) | (t >= 3.0) & (t < 4.0), 0.3 * np.sin(2 * np.pi * 220 * t), 0.0).astype(np.float32)
        sf.write(projet / 'voix.wav', voix, sr)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=gray:s=1080x1920:r=30:d=5', '-i', str(projet / 'voix.wav'),
                        '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-c:a', 'pcm_s16le', '-shortest', str(projet / 'sources' / 'prise.mov')], check=True)
        def a_ecouter(plans):
            calcul, rq = F.resoudre({'nom': 'coupes', 'plans': plans}, projet)
            self.assertFalse(rq.bloquant, msg=str(list(rq)))
            return mixer(calcul, projet, TMP / 'travail-coupes', None, journal=lambda *a: None)['a_ecouter']
        propre = [{'id': 'P1', 'source': 'sources/prise.mov', 'de': 0.8, 'duree': '1.4s', 'son': 'brut'},
                  {'id': 'P2', 'source': 'sources/prise.mov', 'de': 2.8, 'duree': '1.4s', 'son': 'brut'}]
        self.assertEqual(a_ecouter(propre), [])                                                       # coupes dans les silences : rien à signaler
        entame = [{'id': 'P1', 'source': 'sources/prise.mov', 'de': 0.8, 'duree': '1.0s', 'son': 'brut'},      # s'arrête à 1,8 s : en plein son
                  {'id': 'P2', 'source': 'sources/prise.mov', 'de': 2.8, 'duree': '1.4s', 'son': 'brut'}]
        liste = a_ecouter(entame)
        self.assertEqual([(e['plan'], e['bord'], e['t']) for e in liste], [('P1', 'fin', 1.0)])       # la fin du plan P1, à 1,0 s de la vidéo

    def test_credits(self):
        from mix import credits
        nom = json.loads((F.SONS_PLUS / 'manifest.json').read_text(encoding='utf-8'))['bundled'][0]['file'].rsplit('.', 1)[0]
        f = fiche_demo(sons=[{'son': 'impact', 'at': 10}, {'son': nom, 'at': 20}])
        texte = credits(resoudre(f)[0], DEMO)
        for attendu in ('Boucle calculée par le kit', 'Recopier ce crédit', 'Bruitages du kit', f'Bruitage {nom}', 'CC0'):
            self.assertIn(attendu, texte)
        f['musique'] = {'fichier': 'sources/musique.wav', 'droits': 'sous_droits'}
        self.assertIn('ne va jamais en ligne', credits(resoudre(f)[0], DEMO))
        f['musique'] = {'fichier': 'sources/musique.wav'}
        self.assertIn('NON RENSEIGNÉS', credits(resoudre(f)[0], DEMO))
        f.pop('musique'); f.pop('accents')
        self.assertIn('aucune dans le fichier', credits(resoudre(f, tempo=None)[0], DEMO))


class Controle(unittest.TestCase):
    def _video(self, nom, extra):
        f = TMP / nom
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=s=1080x1920:r=30:d=3', '-f', 'lavfi', '-i', 'sine=f=220:d=3:r=48000',
                        '-c:v', 'libx264', '-profile:v', 'high', '-preset', 'ultrafast', '-crf', '20', '-c:a', 'aac', '-b:a', '192k', '-ac', '2',
                        '-af', 'volume=-11dB', '-shortest'] + extra + [str(f)], check=True)
        return f

    def test_bonne_et_mauvaise(self):
        from controle import controler, verdict, ERREUR
        bonne = self._video('bonne.mp4', ['-pix_fmt', 'yuv420p', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv',
                                          '-movflags', '+faststart'])
        R = controler(bonne, dict(l=1080, h=1920, ips=30, n=90))
        couleurs = [n for n, r, _ in R if r == 'couleurs']
        self.assertNotIn(ERREUR, couleurs, msg=str(R))
        self.assertFalse([d for n, r, d in R if n == ERREUR and r in ('taille', 'cadence', 'longueur', 'lecture')], msg=str(R))
        mauvaise = self._video('mauvaise.mp4', ['-pix_fmt', 'yuvj420p', '-color_range', 'pc'])
        R2 = controler(mauvaise, dict(l=1080, h=1920, ips=30, n=90))
        self.assertEqual(verdict(R2), 'À CORRIGER')
        self.assertTrue(any(r == 'couleurs' and n == ERREUR for n, r, _ in R2), msg=str(R2))


def _detecteur_et_visage():
    """Photo d'un vrai visage libre de droits (portrait d'astronaute de la NASA, livré avec scikit-image) et détecteur prêt."""
    try:
        from skimage import data
        import cv2  # noqa: F401
        from cadrage import _modele
        _modele()
        return data.astronaut()
    except Exception:
        return None


class GardeTete(unittest.TestCase):
    """Garde-tête (Yohann, 13/11/2026) : jamais une tête coupée par le cadre ni couverte par un texte, jamais deux textes l'un sur l'autre."""
    def _calcul(self, calques, plans=None, **kw):
        f = fiche_demo(**kw)
        f['calques'] = calques
        if plans is not None:
            f['plans'] = plans
        c, rq = resoudre(f)
        self.assertFalse(niveaux(rq, 'erreur'), msg=niveaux(rq, 'erreur'))
        tete.annoter(f, c)
        return c

    def _tete(self, c, plan, face):
        """Une tête posée à la main sur tout un plan (x, y, largeur, hauteur du visage, en px) : la géométrie seule, sans détecteur."""
        p = next(q for q in c['plans'] if q['id'] == plan)
        ks = sorted(set(range(0, p['t1'] - p['t0'], tete.PAS)) | {p['t1'] - p['t0'] - 1})
        return {plan: dict(k=ks, faces=[[face] for _ in ks])}

    def test_textes_qui_se_chevauchent(self):
        titre = {'t': 'titre', 'texte': 'UN TITRE', 'y': 700, 'taille': 150, 'de': 0, 'a': 60}
        c = self._calcul([titre, {'t': 'etiquette', 'texte': 'une précision', 'y': 760, 'de': 10, 'a': 60}])
        lignes, moments = tete.chevauchements(c)
        self.assertEqual([o['type'] for o in moments], ['chevauche'])
        self.assertIn('calque 1', lignes[0]); self.assertIn('calque 2', lignes[0])
        y = int(re.search(r'calque 2 "y": (\d+)', lignes[0]).group(1))         # le texte arrivé en second se déplace
        c = self._calcul([titre, {'t': 'etiquette', 'texte': 'une précision', 'y': y, 'de': 10, 'a': 60}])
        self.assertEqual(tete.chevauchements(c)[1], [], msg='la hauteur proposée doit vraiment libérer le texte')
        c = self._calcul([titre, {'t': 'etiquette', 'texte': 'une précision', 'y': 760, 'de': 60, 'a': 90}])
        self.assertEqual(tete.chevauchements(c)[1], [], msg='l\'un après l\'autre : rien ne se chevauche')

    def test_texte_sur_la_tete(self):
        face = (440, 450, 200, 250)
        c = self._calcul([{'t': 'titre', 'texte': 'SUR LA TÊTE', 'y': 500, 'taille': 130, 'plan': 'B'}])
        moments, scenes = tete.analyser(c, self._tete(c, 'B', face))
        self.assertEqual([o['type'] for o in moments], ['couverte'])
        ligne = tete.conseils(moments, scenes, c)[0]
        self.assertIn('couvre la tête', ligne)
        y = int(re.search(r'"y": (\d+)', ligne).group(1))
        self.assertGreaterEqual(y, 450 + 1.2 * 250 - 10)                        # sous le menton (au-dessus, la barre d'Instagram)
        c = self._calcul([{'t': 'titre', 'texte': 'SUR LA TÊTE', 'y': y, 'taille': 130, 'plan': 'B'}])
        self.assertEqual(tete.analyser(c, self._tete(c, 'B', face))[0], [])
        # mots qui claquent et sous-titres : même règle
        c = self._calcul([{'t': 'mots', 'texte': 'VITE / FORT', 'y': 560, 'taille': 200, 'plan': 'B', 'rythme': 10}])
        self.assertEqual({o['type'] for o in tete.analyser(c, self._tete(c, 'B', face))[0]}, {'couverte'})

    def test_zoom_qui_coupe_la_tete(self):
        face = (440, 330, 200, 250)                                             # tête haute dans l'image
        plans = json.loads(json.dumps(fabrique.FICHE['plans']))
        plans[1]['effets'] = [{'t': 'punch', 'at': 10, 'a': 0.5, 'd': 8}]
        c = self._calcul([], plans=plans, accents=None)
        moments, scenes = tete.analyser(c, self._tete(c, 'B', face))
        self.assertEqual([(o['type'], o['cle']) for o in moments], [('coupee', ('B', 'haut'))])
        ligne = tete.conseils(moments, scenes, c)[0]
        a = float(re.search(r'punch « a » 0.5 → (\d+(?:\.\d+)?)', ligne).group(1))
        self.assertTrue(0 < a < 0.5)
        plans[1]['effets'][0]['a'] = a
        c = self._calcul([], plans=plans, accents=None)
        self.assertEqual(tete.analyser(c, self._tete(c, 'B', face))[0], [], msg='le punch proposé garde la tête entière')
        # transitions où toute l'image file (whip) : leurs images ne comptent pas ; tête hors champ : rien à dire
        plans[1]['effets'] = []; plans[0]['sortie'] = 'whipG'
        c = self._calcul([], plans=plans, accents=None)
        self.assertEqual(tete.analyser(c, self._tete(c, 'B', face))[0], [])
        self.assertEqual(tete.analyser(c, self._tete(c, 'B', (-900, 330, 200, 250)))[0], [])

    def test_bandes_du_cinema(self):
        face = (860, 120, 200, 250)
        c = self._calcul([{'t': 'bandes', 'ratio': 2.39}], format='16:9', accents=None)
        moments, scenes = tete.analyser(c, self._tete(c, 'B', face))
        self.assertTrue(moments and all(o['type'] == 'coupee' for o in moments))
        ratio = float(re.search(r'« ratio » des bandes (\d+(?:\.\d+)?)', tete.conseils(moments, scenes, c)[0]).group(1))
        c = self._calcul([{'t': 'bandes', 'ratio': ratio}], format='16:9', accents=None)
        self.assertEqual(tete.analyser(c, self._tete(c, 'B', face))[0], [])

    def test_garde_retiree_a_la_main(self):
        f = fiche_demo()
        f['plans'][1]['garde_tete'] = False
        c, rq = resoudre(f)
        self.assertFalse([t for t in niveaux(rq, 'attention') if 'garde_tete' in t], msg='clé connue de la fiche')
        self.assertEqual(tete.annoter(f, c), ['B'])
        self.assertTrue(c['plans'][1]['_sans_garde'])

    def test_meme_geometrie_que_le_moteur(self):
        """Les formules de outils/tete.py recopient celles du moteur : si le moteur change, la garde-tête doit changer avec lui."""
        src = KIT / 'moteur' / 'src'
        attendus = {
            'Plan.jsx': ['st.sc *= lerp(e.a ?? 1, e.b ?? 1.08, k / n)', 'st.sc *= lerp(e.a, e.b, eIO(P(k, e.k0, e.k1 - e.k0)))',
                         'st.sc *= 1 + e.a * Math.pow(1 - P(k, e.at, e.d), 2.2)', 'const a = e.a * Math.pow(1 - P(k, e.at, e.d), 1.4)',
                         'clipPath: `inset(0 ${25 * ouvre}% 0 ${25 * ouvre}%)`', 'translateX(${(dx * ouvre).toFixed(1)}px)', 'const ouvre = eOut(P(k, 0, 8))',
                         'const u = eOut(P(k, cad.de, cad.entree))', 'cad.y - (cad.bas - cad.bord) / 2', 's: Math.max(bw / W, bh / H)', 'rot: cad.angle * u'],
            'Moteur.jsx': ['const q = Math.pow(1 - (F - e.at) / e.d, 2);', 'if (e.z) a.sc *= 1 + e.z * q;'],
            'calques.jsx': ['lerp(1.35, 1, p)', '(1 - p) * -90', '0.22 * (1 - p)', 'lerp(1.28, 1, p)', 'lineHeight: 1.18', '(1 - p) * 14',
                            "padding: '0.32em 0.6em'", "padding: '0.06em 0.2em 0.1em'", 'lerp(1.2, 1, p)', 'lerp(0.6, 1, p)', 'dy = (1 - p) * 140',
                            'dy = -(1 - p) * 520', '(1 - p2) * 40', 'lineHeight: c.interligne || 0.95', "c.anim === 'cinema' ? 24 : 5"],
        }
        for fichier, bouts in attendus.items():
            texte = (src / fichier).read_text(encoding='utf-8')
            for b in bouts:
                self.assertIn(b, texte, msg=f'{fichier} a changé ({b}) : mettre outils/tete.py à jour')
        self.assertEqual(tete.TD, F.DUREE_TRANSITION)

    @unittest.skipIf(_detecteur_et_visage() is None, 'photo de test (scikit-image) ou détecteur de visage indisponible')
    def test_vraie_tete_de_la_fiche_au_refus(self):
        from PIL import Image
        d = TMP / 'tete'
        (d / 'sources').mkdir(parents=True, exist_ok=True)
        fond = Image.new('RGB', (1080, 1920), (40, 44, 52))
        fond.paste(Image.fromarray(_detecteur_et_visage()).resize((1080, 1080), Image.LANCZOS), (0, 300))
        fond.save(d / 'sources' / 'portrait.jpg', quality=92)
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-loop', '1', '-i', str(d / 'sources' / 'portrait.jpg'), '-t', '3', '-r', '30',
                        '-vf', 'format=yuv420p', '-c:v', 'libx264', '-crf', '18', '-preset', 'veryfast', str(d / 'sources' / 'prise.mp4')], check=True)
        # le détecteur trouve le visage là où il est (mesuré : x 375 à 565, y 433 à 672)
        x, y, w, h, conf = tete._detecter([d / 'sources' / 'portrait.jpg'])[str(d / 'sources' / 'portrait.jpg')][0]
        self.assertAlmostEqual(x * 1080, 375, delta=25); self.assertAlmostEqual(y * 1920, 433, delta=25)
        self.assertAlmostEqual(w * 1080, 190, delta=25); self.assertGreater(conf, 0.8)
        fiche = {'nom': 'tete', 'theme': 'foulees', 'finition': {'grain': 0, 'vignette': 0},
                 'plans': [{'id': 'A', 'source': 'sources/prise.mp4', 'duree': '2s'}, {'id': 'B', 'photo': 'sources/portrait.jpg', 'duree': '1s'}],
                 'calques': [{'t': 'titre', 'texte': 'SUR LA TÊTE', 'y': 480, 'taille': 130, 'plan': 'A'}]}
        (d / 'montage.json').write_text(json.dumps(fiche, ensure_ascii=False), encoding='utf-8')

        def lancer(*a):
            r = subprocess.run([sys.executable, str(KIT / 'montage.py')] + list(a), capture_output=True, text=True)
            return r.returncode, r.stdout + r.stderr
        code, sortie = lancer('verifier', str(d))
        self.assertEqual(code, 0, msg=sortie)
        self.assertIn('têtes le seront à la préparation', sortie)            # plans pas encore extraits
        code, sortie = lancer('preparer', str(d))
        self.assertIn('couvre la tête', sortie, msg=sortie)
        self.assertNotIn('WARN', sortie)
        code, sortie = lancer('verifier', str(d))                                # plans prêts : « verifier » voit les têtes
        self.assertEqual(code, 1, msg=sortie)
        y = int(re.search(r'"y": (\d+)', sortie).group(1))
        fiche['calques'][0]['y'] = y
        (d / 'montage.json').write_text(json.dumps(fiche, ensure_ascii=False), encoding='utf-8')
        code, sortie = lancer('verifier', str(d))
        self.assertEqual(code, 0, msg=sortie)
        self.assertIn('Garde-tête : rien à corriger (têtes suivies dans 2 plan(s)', sortie)


class Charte(unittest.TestCase):
    """Charte (Yohann, 13/11/2026) : les textes suivent ceux de la vidéo validée (style, taille, bord, hauteur)."""
    REF = [{'t': 'titre', 'texte': 'MODÈLE', 'y': 1000, 'taille': 110, 'fond': 'accent', 'anim': 'pop'},
           {'t': 'etiquette', 'texte': 'poids 250 g', 'x': 72, 'align': 'gauche', 'y': 1100, 'taille': 44},
           {'t': 'etiquette', 'texte': 'drop 8 mm', 'x': 72, 'align': 'gauche', 'y': 1160, 'taille': 44}]

    def _controle(self, calques, **kw):
        d = Path(tempfile.mkdtemp(dir=TMP))
        (d / 'v1').mkdir()
        (d / 'v1' / 'montage.json').write_text(json.dumps(dict(nom='v1', theme='neutre', calques=self.REF)), encoding='utf-8')
        f = fiche_demo(charte='v1', **kw)
        f['calques'] = calques
        c, rq = resoudre(f)
        tete.annoter(f, c)
        charte.controler(f, c, d, rq)
        return c, rq

    def test_style_taille_bord(self):
        calques = [{'t': 'titre', 'texte': 'AUTRE', 'y': 1000, 'taille': 80, 'anim': 'glisse', 'plan': 'B'},
                   {'t': 'etiquette', 'texte': 'amorti', 'x': 90, 'align': 'gauche', 'y': 1100, 'taille': 44, 'plan': 'B'}]
        c, rq = self._controle(calques)
        err = niveaux(rq, 'erreur')
        self.assertEqual(len(err), 2, msg=err)
        self.assertIn('Je propose : "fond": "accent", "anim": "pop", "taille": 110 (comme le calque 1 de v1)', err[0])
        self.assertIn('Je propose : "x": 72', err[1])                                 # le bord de la liste : les textes s'alignent
        calques[0].update(fond='accent', anim='pop', taille=110)
        calques[1]['x'] = 72
        self.assertEqual(niveaux(self._controle(calques)[1], 'erreur'), [])
        self.assertTrue(any('thème différent de la charte' in e for e in niveaux(self._controle(calques, theme='foulees')[1], 'erreur')))

    def test_place_en_hauteur(self):
        titre = {'t': 'titre', 'texte': 'MODÈLE', 'y': 600, 'taille': 110, 'fond': 'accent', 'plan': 'B'}
        ligne = {'t': 'etiquette', 'texte': 'amorti', 'x': 72, 'align': 'gauche', 'y': 1220, 'taille': 44, 'plan': 'C'}
        c, rq = self._controle([titre, ligne])
        self.assertEqual(niveaux(rq, 'erreur'), [])
        self.assertEqual(charte.hors_place(c), [(0, 1000)])                          # la liste s'allonge d'une ligne ; le titre revient à 1000
        c, rq = self._controle([titre, dict(ligne, y=1290)])
        self.assertEqual(charte.hors_place(c), [(0, 1000), (1, 1160)])               # deux lignes de plus : non
        # avec les têtes : la place de la charte d'abord, si elle est libre
        c, rq = self._controle([titre])
        moments, scenes = tete.analyser(c, {})
        erreurs, notes = tete.places_charte(moments, scenes, c)
        self.assertIn('"y": 1000', erreurs[0])
        face = (440, 450, 200, 250)                                                    # le titre à 600 couvre la tête ; 1000 est libre
        moments, scenes = tete.analyser(c, GardeTete._tete(self, c, 'B', face))
        self.assertIn('Je propose : "y": 1000 (libre', tete.conseils(moments, scenes, c)[0])
        # la tête occupe la place de la charte : la garde-tête passe avant, le titre reste ailleurs, et c'est dit sans refus
        face = (440, 960, 200, 250)
        moments, scenes = tete.analyser(c, GardeTete._tete(self, c, 'B', face))
        self.assertEqual(moments, [])
        erreurs, notes = tete.places_charte(moments, scenes, c)
        self.assertEqual(erreurs, [])
        self.assertIn('hors charte', notes[0])


FAUX_AVCONVERT = '''#!/usr/bin/env python3
"""Faux avconvert pour les essais : même interface que celui du Mac, copie SDR faite par ffmpeg ; il note chacun de ses passages."""
import os, subprocess, sys
a = sys.argv[1:]
src, out = a[a.index('--source') + 1], a[a.index('--output') + 1]
if a[a.index('--preset') + 1] != 'PresetHighestQuality' or '--replace' not in a:
    sys.exit('options inattendues : ' + ' '.join(a))
with open(os.environ['FAUX_COMPTE'], 'a') as f:
    f.write(src + '\\n')
vf = ['-vf', 'fps=' + os.environ['FAUX_IPS']] if os.environ.get('FAUX_IPS') else []
son = ['-an'] if os.environ.get('FAUX_SANS_SON') else ['-c:a', 'aac']
sys.exit(subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', src, *vf, '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p',
                         '-color_trc', 'bt709', '-color_primaries', 'bt709', '-colorspace', 'bt709', *son, out]).returncode)
'''


class VideosHDR(unittest.TestCase):
    """Vidéos HDR d'iPhone sur un ffmpeg sans zscale (défaut du 13/11 sur le Mac de Yohann : la préparation plantait). Un seul endroit
    choisit (hdr.py) : zscale (le cloud), rien ne change ; sinon copie SDR par avconvert, vérifiée et gardée en cache ; sinon arrêt clair."""

    @classmethod
    def setUpClass(cls):
        import hdr
        cls.HDR = hdr
        cls.dossier = Path(tempfile.mkdtemp(dir=TMP))
        cls.video = cls.dossier / 'IMG_0001.MOV'          # marquée HLG comme une vidéo d'iPhone, 60 i/s, avec son
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=s=540x960:r=60:d=5', '-f', 'lavfi', '-i', 'sine=d=5',
                        '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-color_trc', 'arib-std-b67', '-color_primaries', 'bt2020',
                        '-colorspace', 'bt2020nc', '-c:a', 'aac', '-shortest', str(cls.video)], check=True)
        cls.faux = cls.dossier / 'avconvert'
        cls.faux.write_text(FAUX_AVCONVERT, encoding='utf-8')
        cls.faux.chmod(0o755)

    def setUp(self):
        self.vrais = self.HDR.zscale, self.HDR.avconvert
        self.compte = Path(tempfile.mkdtemp(dir=TMP)) / 'passages.txt'
        os.environ['FAUX_COMPTE'] = str(self.compte)
        os.environ['FAUX_IPS'] = '30'                    # comme sur le Mac : avconvert ramène la cadence à 30 i/s

    def tearDown(self):
        self.HDR.zscale, self.HDR.avconvert = self.vrais
        for v in ('FAUX_COMPTE', 'FAUX_IPS', 'FAUX_SANS_SON'):
            os.environ.pop(v, None)

    def _sans_zscale(self, avec_avconvert=True):
        self.HDR.zscale = lambda prog='ffmpeg': False
        self.HDR.avconvert = (lambda: str(self.faux)) if avec_avconvert else (lambda: None)

    def _passages(self):
        return len(self.compte.read_text().splitlines()) if self.compte.exists() else 0

    def test_avec_zscale_rien_ne_change(self):
        sd = F.sonde(self.video)
        self.assertTrue(sd['hdr'])
        self.assertTrue(self.HDR.zscale(), msg='le ffmpeg du cloud a zscale')
        self.assertIn('ffmpeg', self.HDR._filtres, msg='regardé une fois, gardé ensuite')
        self.assertEqual(self.HDR.source(self.video, sd, self.dossier / 'sdr'), (str(self.video), self.HDR.VERS_SDR, sd))
        normale = DEMO / 'sources' / 'video1.mp4'
        sn = F.sonde(normale)
        self.assertEqual(self.HDR.source(normale, sn, self.dossier / 'sdr'), (str(normale), '', sn))
        self.assertEqual(self._passages(), 0)

    def test_sans_zscale_copie_par_avconvert_gardee(self):
        self._sans_zscale()
        sd, cache, dit = F.sonde(self.video), Path(tempfile.mkdtemp(dir=TMP)), []
        entree, conv, sc = self.HDR.source(self.video, sd, cache, dit.append)
        self.assertEqual((conv, Path(entree).parent), ('', cache))
        self.assertFalse(F.sonde(entree)['hdr'])
        self.assertAlmostEqual(sc['ips'], 30, places=1, msg='la copie se lit à sa propre cadence')
        self.assertTrue(any('avconvert' in t for t in dit) and any('30 i/s' in t and 'ralenti' in t for t in dit), dit)
        # cache : la même copie, sans repasser par avconvert
        self.assertEqual(self.HDR.source(self.video, sd, cache, dit.append)[0], entree)
        self.assertEqual(self._passages(), 1)
        # la source change (même nom) : nouvelle copie, l'ancienne est effacée
        os.utime(self.video, ns=(self.video.stat().st_atime_ns, self.video.stat().st_mtime_ns + 2_000_000_000))
        neuve = self.HDR.source(self.video, F.sonde(self.video), cache)[0]
        self.assertNotEqual(neuve, entree)
        self.assertEqual([f.name for f in cache.iterdir()], [Path(neuve).name])
        self.assertEqual(self._passages(), 2)

    def test_sans_zscale_ni_avconvert_arret_clair(self):
        self._sans_zscale(avec_avconvert=False)
        with self.assertRaisesRegex(RuntimeError, 'zscale.*cloud'):
            self.HDR.source(self.video, F.sonde(self.video), Path(tempfile.mkdtemp(dir=TMP)))

    def test_copie_douteuse_refusee(self):
        self._sans_zscale()
        os.environ['FAUX_SANS_SON'] = '1'
        cache = Path(tempfile.mkdtemp(dir=TMP))
        with self.assertRaisesRegex(RuntimeError, 'son perdu'):
            self.HDR.source(self.video, F.sonde(self.video), cache)
        self.assertEqual(list(cache.iterdir()), [], msg='aucune copie douteuse gardée')
        o = dict(ips=119.94, duree=12.113, audio=True, l=2160, h=3840, hdr=True)
        mac = dict(ips=30.0, duree=12.167, audio=True, l=2160, h=3840, hdr=False)      # la copie d'IMG_8632 faite sur le Mac le 13/11
        self.assertEqual(self.HDR._ecart(o, mac), '')
        self.assertIn('orientation', self.HDR._ecart(o, {**mac, 'l': 3840, 'h': 2160}))
        self.assertIn('HDR', self.HDR._ecart(o, {**mac, 'hdr': True}))
        self.assertIn('cadence', self.HDR._ecart(o, {**mac, 'ips': 24.0}))
        self.assertIn('durée', self.HDR._ecart(o, {**mac, 'duree': 11.5}))

    def test_preparation_avec_la_copie(self):
        import preparer as PR
        self._sans_zscale()
        projet = fabrique.fabriquer(Path(tempfile.mkdtemp(dir=TMP)) / 'hdr')
        shutil.copy(self.video, projet / 'sources' / 'IMG_0001.MOV')
        f = fiche_demo()
        f['plans'][1].update(source='sources/IMG_0001.MOV', vitesse=0.5)
        calcul, rq = F.resoudre(f, projet, dict(periode=0.5))
        self.assertFalse(niveaux(rq, 'erreur'))
        dit = []
        PR.preparer(calcul, projet / '.travail', dit.append)
        b = next(q for q in calcul['plans'] if q['id'] == 'B')
        self.assertAlmostEqual(b['ips'], 30, places=1, msg='images lues à la cadence de la copie, sinon le plan défile trop vite')
        self.assertGreater(b['n'], 0)
        self.assertTrue(any('ralenti' in t and 'cloud' in t for t in dit), dit)
        avant = len(dit)
        PR.preparer(calcul, projet / '.travail', dit.append)        # deuxième préparation : copie et plan repris
        self.assertEqual(self._passages(), 1)
        self.assertTrue(any('plans :' in t and '0 extrait(s)' in t for t in dit[avant:]), dit[avant:])

    def test_un_seul_endroit(self):
        """La préparation et la planche des rushes passent par hdr.source ; zscale n'est écrit nulle part ailleurs."""
        codes = {p: p.read_text(encoding='utf-8') for p in list((KIT / 'outils').glob('*.py')) + [KIT / 'montage.py']}
        self.assertEqual([p.name for p, t in codes.items() if 'zscale' in t], ['hdr.py'])
        self.assertIn('HDR.source(', codes[KIT / 'outils' / 'preparer.py'])
        self.assertIn('HDR.source(', codes[KIT / 'montage.py'])


class ImagesCalques(unittest.TestCase):
    """Images des calques (défaut du 13/11, Reel « choix de la chaussure ») : nommées par numéro de calque, une image restait à la place
    d'une autre quand on retirait un calque (la signature montrait une chaussure au lieu du logo), et restait trop petite, donc floue,
    quand on l'affichait plus grand. Maintenant : une clé par image (source, taille, date, largeur affichée)."""
    COULEURS = dict(chaussure=(30, 60, 200), produit=(30, 160, 60), logo=(220, 30, 30))

    @classmethod
    def setUpClass(cls):
        from PIL import Image
        cls.dossier = DEMO / 'calques-essai'
        cls.dossier.mkdir(exist_ok=True)
        for nom, rgb in cls.COULEURS.items():
            Image.new('RGBA', (2000, 1000), rgb + (255,)).save(cls.dossier / f'{nom}.png')

    @staticmethod
    def _image(nom, **kw):
        return {'t': 'image', 'fichier': f'calques-essai/{nom}.png', 'plan': 'B', 'l': 300, 'y': 700, **kw}

    def _preparer(self, calques, public):
        import preparer as PR
        calcul, rq = resoudre(fiche_demo(calques=calques))
        self.assertFalse(niveaux(rq, 'erreur'))
        PR.images_calques(calcul, public)
        return [c for c in calcul['calques'] if c.get('_fichier')]

    @staticmethod
    def _couleur(public, nom):
        from PIL import Image
        with Image.open(public / 'images' / nom) as im:
            return im.convert('RGB').getpixel((im.width // 2, im.height // 2))

    @staticmethod
    def _largeur(public, nom):
        from PIL import Image
        with Image.open(public / 'images' / nom) as im:
            return im.width

    def test_calque_retire(self):
        public = Path(tempfile.mkdtemp(dir=TMP))
        signature = {'t': 'signature', 'nom': 'Démo', 'ligne': 'essai', 'plan': 'C', 'logo': 'calques-essai/logo.png'}
        avant = self._preparer([self._image('chaussure'), self._image('produit', y=1100), signature], public)
        dates = {c.get('fichier') or c['logo']: (public / 'images' / (c.get('fichier') or c['logo'])).stat().st_mtime_ns for c in avant}
        # on retire le premier calque : avant, le produit prenait l'image de la chaussure et la signature celle du produit
        produit, sig = self._preparer([self._image('produit', y=1100), signature], public)
        self.assertEqual(self._couleur(public, produit['fichier']), self.COULEURS['produit'])
        self.assertEqual(self._couleur(public, sig['logo']), self.COULEURS['logo'])
        # ménage : l'image de la chaussure, qui ne sert plus, est effacée ; les deux autres sont reprises sans être refaites
        self.assertEqual(sorted(f.name for f in (public / 'images').iterdir()), sorted([produit['fichier'], sig['logo']]))
        for nom in (produit['fichier'], sig['logo']):
            self.assertEqual((public / 'images' / nom).stat().st_mtime_ns, dates[nom], msg='image refaite pour rien')
        # deux calques image, le premier retiré (la demande du Pilote, mot pour mot)
        public2 = Path(tempfile.mkdtemp(dir=TMP))
        self._preparer([self._image('logo'), self._image('chaussure', y=1100)], public2)
        seul, = self._preparer([self._image('chaussure', y=1100)], public2)
        self.assertEqual(self._couleur(public2, seul['fichier']), self.COULEURS['chaussure'])

    def test_largeur_et_source_changees(self):
        from PIL import Image
        public = Path(tempfile.mkdtemp(dir=TMP))
        petit, = self._preparer([self._image('produit', l=200)], public)
        self.assertEqual(self._largeur(public, petit['fichier']), 400)     # deux fois la largeur affichée
        grand, = self._preparer([self._image('produit', l=800)], public)
        self.assertNotEqual(grand['fichier'], petit['fichier'])
        self.assertEqual(self._largeur(public, grand['fichier']), 1600, msg='image gardée trop petite : floue')
        self.assertEqual([f.name for f in (public / 'images').iterdir()], [grand['fichier']])
        # la même source changée (même nom de fichier) : image refaite
        source = self.dossier / 'change.png'
        Image.new('RGB', (2000, 1000), (200, 200, 0)).save(source)
        avant, = self._preparer([{**self._image('change'), 'l': 400}], public)
        Image.new('RGB', (2000, 1000), (0, 200, 200)).save(source)
        os.utime(source, ns=(source.stat().st_atime_ns, source.stat().st_mtime_ns + 2_000_000_000))
        apres, = self._preparer([{**self._image('change'), 'l': 400}], public)
        self.assertNotEqual(apres['fichier'], avant['fichier'])
        self.assertEqual(self._couleur(public, apres['fichier']), (0, 200, 200))


class PreparationReprise(unittest.TestCase):
    """Défaut du 13/11 (Reels des stands) : public/images vidé après la planche, le rendu suivant échouait tant que la préparation
    n'était pas forcée (elle était reprise du cache sans regarder si ses fichiers étaient encore là)."""
    def test_fichiers_effaces_refaits(self):
        import contextlib
        import io
        sys.path.insert(0, str(KIT))
        import montage as M
        from PIL import Image
        projet = fabrique.fabriquer(Path(tempfile.mkdtemp(dir=TMP)) / 'reprise', avec_video=False)
        Image.new('RGBA', (800, 400), (200, 30, 30, 255)).save(projet / 'sources' / 'produit.png')
        Image.new('RGBA', (600, 600), (30, 30, 200, 255)).save(projet / 'sources' / 'logo.png')
        fiche = {'nom': 'reprise', 'theme': 'neutre',
                 'plans': [{'id': 'A', 'photo': 'sources/photo1.jpg', 'duree': '1s'}, {'id': 'C', 'photo': 'sources/photo2.jpg', 'duree': '1s'}],
                 'calques': [{'t': 'image', 'fichier': 'sources/produit.png', 'plan': 'A', 'l': 300, 'y': 700},
                             {'t': 'signature', 'nom': 'Démo', 'ligne': 'essai', 'plan': 'C', 'logo': 'sources/logo.png'}]}
        (projet / 'montage.json').write_text(json.dumps(fiche, ensure_ascii=False), encoding='utf-8')

        def preparer():
            with contextlib.redirect_stdout(io.StringIO()) as s:
                M.preparer(projet)
            return s.getvalue()
        preparer()
        public = projet / '.travail' / 'public'
        images = sorted(f.name for f in (public / 'images').iterdir())
        self.assertEqual(len(images), 2)
        for f in (public / 'images').iterdir():          # public/images vidé après la planche
            f.unlink()
        shutil.rmtree(public / 'plans' / 'C')            # et un plan effacé
        dit = preparer()
        self.assertIn('effacé', dit)
        self.assertEqual(sorted(f.name for f in (public / 'images').iterdir()), images)
        self.assertTrue((public / 'plans' / 'C' / 'meta.json').exists())
        self.assertIn('1 extrait(s), 1 repris du cache', dit)                # seul ce qui manquait est refait
        self.assertNotIn('Préparation faite', preparer())                    # tout est là : le cache est repris, rien n'est refait


class Moteur(unittest.TestCase):
    """Le moteur (JavaScript) et la fiche (Python) doivent dire la même chose."""
    def test_durees_des_transitions(self):
        src = (KIT / 'moteur' / 'src' / 'Plan.jsx').read_text(encoding='utf-8')
        td = dict((k, (int(a), int(b))) for k, a, b in re.findall(r'(\w+): \[(\d+), (\d+)\]', re.search(r'export const TD = \{(.*?)\};', src).group(1)))
        self.assertEqual(td, F.DUREE_TRANSITION)
        self.assertEqual(set(td), F.TRANSITIONS)

    def test_regards_et_calques(self):
        plan = (KIT / 'moteur' / 'src' / 'Plan.jsx').read_text(encoding='utf-8')
        bloc = re.search(r'const REGARDS = \{(.*?)\};', plan, re.S).group(1)
        self.assertEqual(set(re.findall(r'^\s*(\w+):', bloc, re.M)), F.REGARDS)
        calques = (KIT / 'moteur' / 'src' / 'calques.jsx').read_text(encoding='utf-8')
        types = re.search(r'const TYPES = \{(.*?)\};', calques, re.S).group(1)
        connus = set(re.findall(r"'([\w-]+)':|\b(\w+):", types))
        connus = {a or b for a, b in connus}
        self.assertTrue(F.TYPES_CALQUE <= connus, msg=f'types sans rendu : {F.TYPES_CALQUE - connus}')

    def test_polices_presentes(self):
        for famille, variantes in F.POLICES.items():
            for fichier, _, _ in variantes:
                self.assertTrue((F.POLICES_KIT / fichier).exists() or (F.POLICES_PLUGIN / fichier).exists(), msg=f'police absente : {fichier}')

    def test_bruitages_des_transitions(self):
        cat = json.loads((F.SONS_KIT / 'catalogue.json').read_text(encoding='utf-8'))
        for tr, (nom, _, _) in F.SON_TRANSITION.items():
            cible = cat['situations'].get(nom, nom)
            self.assertTrue((F.SONS_KIT / 'kit' / f'{cible}.wav').exists(), msg=f'bruitage absent pour {tr} : {nom}')


class Ressources(unittest.TestCase):
    """Mode discret (demande de Yohann du 13/11) : sur le Mac M1, le montage laisse la machine utilisable ; ailleurs, pleine vitesse."""
    M1 = dict(puce='Apple M1', perf=4, coeurs=8, memoire=8 * 2 ** 30)
    VARIABLES = ('MONTAGE_RESSOURCES', 'MONTAGE_COEURS', 'MONTAGE_GL', 'MONTAGE_DETOURAGE')

    def setUp(self):
        self.env = {v: os.environ.pop(v) for v in self.VARIABLES if v in os.environ}
        self.mac, self.machine = RES.MAC, RES.machine

    def tearDown(self):
        for v in self.VARIABLES:
            os.environ.pop(v, None)
        os.environ.update(self.env)
        RES.MAC, RES.machine = self.mac, self.machine
        RES.reglages(rafraichir=True)

    def _sur(self, mac=True, **env):
        RES.MAC = mac
        RES.machine = lambda: dict(self.M1) if mac else dict(puce='machine du cloud', perf=4, coeurs=4, memoire=16 * 2 ** 30)
        for v in self.VARIABLES:
            os.environ.pop(v, None)
        os.environ.update(env)
        return RES.reglages(rafraichir=True)

    def test_m1_discret(self):
        r = self._sur()
        self.assertEqual((r['mode'], r['coeurs'], r['priorite'], r['verrou'], r['gl']), ('discret', 4, True, True, None))
        self.assertEqual(r['cache'], 512 * 2 ** 20)
        self.assertEqual((RES.taches(3), RES.taches(6), RES.fils(), RES.fils(3)), (3, 4, 4, 1))
        go = 2 ** 30
        self.assertEqual(RES.remotion(dispo=2.3 * go), dict(coeurs=1, fils=4, cache=512 * 2 ** 20))     # Mac chargé : un seul onglet
        # un 2e onglet dès que 3 Go resteraient libres (rendu à 2 onglets : 2 Go), puis un de plus par demi-Go, 4 au plus
        self.assertEqual([RES.remotion(dispo=d * go)['coeurs'] for d in (4.9, 5, 5.5, 6, 7)], [1, 2, 3, 4, 4])
        self.assertIn('Mode discret (Apple M1, 8 cœurs, 8 Go) : 4 cœur(s)', RES.resume())
        self.assertIn('3 Go de mémoire laissés libres', RES.resume())
        try:
            import onnxruntime  # noqa: F401
        except ImportError:
            return
        modele, options = RES.detourage()
        self.assertEqual(modele, 'isnet-general-use')
        self.assertFalse(options['sess_opts'].enable_cpu_mem_arena)
        self.assertEqual(options['sess_opts'].intra_op_num_threads, 4)

    def test_ailleurs_pleine_vitesse(self):
        r = self._sur(mac=False)
        self.assertEqual((r['mode'], r['coeurs'], r['priorite'], r['verrou'], r['cache']), ('libre', None, False, False, None))
        cmd = ['ffmpeg', '-v', 'error', '-i', 'a.mp4', '-f', 'null', '-']
        self.assertEqual(RES.ff(cmd), cmd)
        self.assertEqual((RES.taches(3), RES.fils(), RES.remotion()), (3, None, {}))
        self.assertEqual(RES.detourage(), ('birefnet-general-lite', {}))
        self.assertIn('Pas sur le Mac', RES.resume())

    def test_reglages_a_la_main(self):
        r = self._sur(MONTAGE_COEURS='2')
        self.assertEqual(r['coeurs'], 2)
        self.assertEqual(RES.remotion(dispo=1 * 2 ** 30)['coeurs'], 2, msg='MONTAGE_COEURS fixe aussi les onglets')
        r = self._sur(MONTAGE_RESSOURCES='rapide')
        self.assertEqual((r['mode'], r['coeurs'], r['priorite'], r['verrou']), ('rapide', None, False, True))
        self.assertIn('Seulement si Yohann', RES.resume())
        self._sur(MONTAGE_GL='swangle')
        self.assertEqual(RES.remotion(dispo=8 * 2 ** 30)['gl'], 'swangle')
        self._sur(mac=False, MONTAGE_RESSOURCES='discret')
        self.assertEqual(RES.reglages()['mode'], 'discret')

    def test_ffmpeg_plafonne(self):
        self._sur(MONTAGE_COEURS='2')
        cmd = RES.ff(['ffmpeg', '-v', 'error', '-ss', '1', '-i', 'a.mp4', '-i', 'b.wav', '-f', 'null', '-'])
        self.assertEqual(cmd[-3:], ['-threads', '2', '-'])
        self.assertEqual([cmd[i - 2:i] for i, x in enumerate(cmd) if x == '-i'], [['-threads', '2'], ['-threads', '2']])
        deux = RES.ff(['ffmpeg', '-i', 'a', 'b'], paralleles=2)            # deux travaux ensemble : un fil chacun
        self.assertEqual({deux[i + 1] for i, x in enumerate(deux) if x == '-threads'}, {'1'})
        vrai = RES.ff(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=320x240:d=1', '-vf', 'scale=160:120',
                       '-c:v', 'libx264', '-f', 'null', '-'])
        r = subprocess.run(vrai, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, msg=f'ffmpeg refuse les options de fils : {r.stderr[-300:]}')

    def test_un_seul_montage_a_la_fois(self):
        verrou = TMP / 'essai-verrou.lock'
        env = dict(os.environ, MONTAGE_VERROU=str(verrou), PYTHONPATH=str(KIT / 'outils'))
        prendre = "import ressources as R, sys, time; R.PAS_ATTENTE = 0.2; R.prendre_verrou(sys.argv[1], sys.argv[2]); print('PRIS', flush=True); time.sleep(float(sys.argv[3]))"
        premier = subprocess.Popen([sys.executable, '-c', prendre, 'final', '/x/projet-a', '2'], env=env, stdout=subprocess.PIPE, text=True)
        self.assertEqual(premier.stdout.readline().strip(), 'PRIS')
        r = subprocess.run([sys.executable, '-c', prendre, 'apercu', '/x/projet-b', '0'], env=env, capture_output=True, text=True, timeout=60)
        premier.wait()
        self.assertIn('Un autre montage occupe déjà la machine (« final » sur projet-a', r.stdout)
        self.assertIn('À mon tour', r.stdout)
        self.assertTrue(r.stdout.strip().endswith('PRIS'))
        premier = subprocess.Popen([sys.executable, '-c', prendre, 'final', '/x/projet-a', '3'], env=env, stdout=subprocess.PIPE, text=True)
        self.assertEqual(premier.stdout.readline().strip(), 'PRIS')
        r = subprocess.run([sys.executable, '-c', prendre, 'final', '/x/projet-c', '0'], env=dict(env, MONTAGE_ATTENTE='0.01'),
                           capture_output=True, text=True, timeout=60)
        premier.wait()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('occupe la machine depuis plus de', r.stderr)

    def test_le_kit_passe_par_les_limites(self):
        """Toute commande ffmpeg du kit passe par RES.ff, et montage.py règle les fils avant d'importer numpy."""
        fichiers = [KIT / 'montage.py'] + [f for f in (KIT / 'outils').glob('*.py') if f.name not in ('ressources.py', 'charge.py')]
        for f in fichiers:
            t = f.read_text(encoding='utf-8')
            self.assertNotRegex(t, r"subprocess\.run\(\s*\[\s*'ffmpeg'", msg=f'{f.name} : ffmpeg sans RES.ff')
            if "cmd = ['ffmpeg'" in t:
                self.assertNotRegex(t, r"subprocess\.run\(cmd\b", msg=f'{f.name} : commande ffmpeg sans RES.ff')
            self.assertNotRegex(t, r"ThreadPoolExecutor\(\d", msg=f'{f.name} : travaux en parallèle sans RES.taches')
        m = (KIT / 'montage.py').read_text(encoding='utf-8')
        self.assertLess(m.index('RES.environnement()'), m.index('import fiche as F'))
        self.assertIn('RES.discret(a.cmd', m)
        js = (KIT / 'moteur' / 'rendu.mjs').read_text(encoding='utf-8')
        for cle in ('o.coeurs', 'o.fils', 'offthreadVideoCacheSizeInBytes', 'chromiumOptions'):
            self.assertIn(cle, js)


class Skill(unittest.TestCase):
    """Le mode d'emploi court (skill montage-pro) : même texte aux deux endroits, et seulement des commandes qui existent."""
    PLUGIN = KIT.parent / 'plugin-visibilite' / 'visibilite' / 'skills' / 'montage-pro' / 'SKILL.md'
    DIRECT = KIT.parent / '.claude' / 'skills' / 'montage-pro' / 'SKILL.md'

    def test_meme_texte_aux_deux_endroits(self):
        self.assertEqual(self.PLUGIN.read_text(encoding='utf-8'), self.DIRECT.read_text(encoding='utf-8'),
                         msg='recopier plugin-visibilite/visibilite/skills/montage-pro/SKILL.md dans .claude/skills/montage-pro/')

    def test_commandes_citees_existent(self):
        connues = set(re.findall(r"add_parser\('(\w+)'\)", (KIT / 'montage.py').read_text(encoding='utf-8')))
        citees = set(re.findall(r'\bM (\w+)', self.PLUGIN.read_text(encoding='utf-8')))
        self.assertTrue(citees, msg='aucune commande trouvée dans le skill')
        self.assertTrue(citees <= connues, msg=f'commandes citées mais inconnues : {citees - connues}')

    @unittest.skipUnless((KIT.parent / 'SKILLS-PAR-MODULE.md').exists(), 'dépôt du logiciel seul : pas de SKILLS-PAR-MODULE.md')
    def test_skills_du_montage(self):
        """Les skills de la ligne « Montage » de SKILLS-PAR-MODULE.md sont installés, et le mode d'emploi dit quand charger chacun."""
        regle = (KIT.parent / 'SKILLS-PAR-MODULE.md').read_text(encoding='utf-8')
        section = regle.split('## Montage', 1)[1].split('\n## ', 1)[0]
        installes = {d.name for d in (KIT.parent / '.claude' / 'skills').iterdir() if (d / 'SKILL.md').is_file()}
        du_montage = set(re.findall(r'`([a-z][a-z0-9-]+)`', section)) - {'main'}
        self.assertGreaterEqual(len(du_montage), 10, msg='la section Montage ne nomme plus ses skills entre accents graves')
        self.assertEqual(du_montage - installes, set(), msg='skills nommés mais absents de .claude/skills')
        mode_emploi = self.PLUGIN.read_text(encoding='utf-8')
        oublies = {n for n in du_montage if f'`{n}`' not in mode_emploi and n != 'montage-pro'}
        self.assertEqual(oublies, set(), msg='skills de la ligne Montage que montage-pro ne place à aucune étape')


@unittest.skipIf(os.environ.get('MONTAGE_TEST_RAPIDE') or not (KIT / 'moteur' / 'node_modules' / 'remotion').exists(),
                 'rendu réel sauté (moteur non installé, ou MONTAGE_TEST_RAPIDE)')
class Rendu(unittest.TestCase):
    """Le vrai chemin, de la fiche à la vidéo contrôlée, sur le projet de démonstration."""
    def _montage(self, *args):
        r = subprocess.run([sys.executable, str(KIT / 'montage.py')] + list(args), capture_output=True, text=True)
        return r.returncode, r.stdout + r.stderr

    def test_1_planche(self):
        from PIL import Image
        code, sortie = self._montage('planche', str(DEMO))
        self.assertEqual(code, 0, msg=sortie[-800:])
        im = np.asarray(Image.open(DEMO / 'sorties' / 'planche.jpg').convert('L'))
        self.assertGreater(im.mean(), 20, msg='planche presque noire')

    def test_2_final_controle(self):
        code, sortie = self._montage('final', str(DEMO), '--plage', '0-74')
        self.assertEqual(code, 0, msg=sortie[-1200:])
        video = DEMO / 'sorties' / 'demo.mp4'
        self.assertTrue(video.exists())
        p = json.loads(subprocess.run(['ffprobe', '-v', 'error', '-print_format', 'json', '-show_streams', str(video)], capture_output=True, text=True).stdout)
        v = next(s for s in p['streams'] if s['codec_type'] == 'video')
        self.assertEqual((v['pix_fmt'], v.get('color_range'), v.get('color_space'), v.get('color_primaries'), v.get('color_transfer')),
                         ('yuv420p', 'tv', 'bt709', 'bt709', 'bt709'))
        self.assertEqual((v['width'], v['height'], v['r_frame_rate']), (1080, 1920, '30/1'))
        self.assertIn('BON', sortie)
        self.assertTrue((DEMO / 'sorties' / 'demo-sans-musique.mp4').exists())
        self.assertIn('Recopier ce crédit', (DEMO / 'sorties' / 'demo-credits.txt').read_text(encoding='utf-8'))

    def test_3_rendu_discret(self):
        """Le rendu accepte les limites du Mac (onglets, fils de l'encodeur, cache), ici forcées sur la machine d'essai."""
        r = subprocess.run([sys.executable, str(KIT / 'montage.py'), 'final', str(DEMO), '--plage', '0-29'], capture_output=True, text=True,
                           env=dict(os.environ, MONTAGE_RESSOURCES='discret', MONTAGE_COEURS='2'))
        sortie = r.stdout + r.stderr
        self.assertEqual(r.returncode, 0, msg=sortie[-1200:])
        self.assertIn('Mode discret', sortie)
        self.assertIn('FINAL OK 30 images', sortie)


if __name__ == '__main__':
    unittest.main(verbosity=2)
