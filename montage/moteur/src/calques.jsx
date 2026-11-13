// Calques posés sur les images : titres, mots qui claquent, sous-titres, étiquettes, compteurs, images, carte de fin, voiles.
// Chaque calque arrive déjà « résolu » par outils/fiche.py : images de début et de fin, tailles ajustées, couleurs du thème.
import React from 'react';
import {Img, staticFile} from 'remotion';
import {clamp, lerp, eOut, eOut5, eIn, eIO, eBack, P, R, couleur, police} from './outils.js';

const GLYPHES = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#/<>';
const brouille = (texte, k, vitesse, graine) => {
  const n = Math.floor(k * vitesse);
  return texte.split('').map((ch, i) => {
    if (ch === ' ') return ' ';
    if (i < n - 3) return ch;
    if (i < n) return GLYPHES[Math.floor(R('dc', graine, k, i) * GLYPHES.length)];
    return ' ';
  }).join('');
};
const ancre = (c, W) => {
  const x = c.x ?? W / 2;
  const tr = c.align === 'gauche' ? '' : c.align === 'droite' ? 'translateX(-100%)' : 'translateX(-50%)';
  return {x, tr, ta: c.align === 'gauche' ? 'left' : c.align === 'droite' ? 'right' : 'center'};
};
// opacité de sortie : fondu de 5 images à la fin, sauf « coupe »
const fin = (c, f) => { const d = c.fondu || (c.anim === 'cinema' ? 24 : 5); return c.sortie === 'coupe' ? 1 : 1 - eIn(P(f, c.a - d, d)); };
const OMBRE = '0 4px 26px rgba(0,0,0,0.55), 0 1px 3px rgba(0,0,0,0.35)';

// ---------------------------------------------------------------- titre (une ou plusieurs lignes)
const Titre = ({c, f, cfg}) => {
  const th = cfg.theme, k = f - c.de;
  const {x, tr, ta} = ancre(c, cfg.l);
  const col = couleur(th, c.couleur, 'fort');
  const base = {...police(th, c.police || 'titre'), lineHeight: c.interligne || 0.95, whiteSpace: 'pre',
    color: c.contour ? 'transparent' : col, WebkitTextStroke: c.contour ? `${c.trait || 3}px ${col}` : undefined,
    textShadow: c.contour || c.fond || c.ombre === false ? undefined : OMBRE};
  if (c.espacement !== undefined) base.letterSpacing = `${c.espacement}em`;
  const anim = c.anim || 'pop';
  let retard = 0;
  const lignes = c.lignes.map((li, j) => {
    const d0 = retard; retard += anim === 'lettres' ? li.texte.length * 0.7 + 2 : anim === 'machine' || anim === 'decode' ? li.texte.length / 2.4 : 3;
    let contenu = li.texte, st = {};
    if (anim === 'lettres') {
      contenu = li.texte.split('').map((ch, i) => {
        const p = eOut(P(k, d0 + i * 0.7, 8));
        return <span key={i} style={{display: 'inline-block', transform: `translateY(${((1 - p) * 110).toFixed(1)}%)`}}>{ch}</span>;
      });
      st = {clipPath: 'inset(-20% -8% 0 -8%)'};
    } else if (anim === 'pop') {
      const p = eBack(P(k, d0, 7));
      st = {opacity: clamp((k - d0) / 2), transform: `scale(${lerp(1.35, 1, p).toFixed(3)})`};
    } else if (anim === 'glisse') {
      const p = eOut5(P(k, d0, 10));
      st = {opacity: clamp((k - d0) / 3), transform: `translateX(${((1 - p) * -90).toFixed(1)}px)`};
    } else if (anim === 'cinema') {
      // bande-annonce : fondu lent, lettres qui se resserrent, net qui arrive (chaque ligne un peu après la précédente)
      const p = eOut(P(k, d0 * 6, c.duree_anim || 36));
      st = {opacity: p * p, letterSpacing: `${((c.espacement ?? th[c.police || 'titre'].espacement ?? 0) + 0.22 * (1 - p)).toFixed(4)}em`,
        filter: p < 0.98 ? `blur(${(6 * (1 - p)).toFixed(2)}px)` : undefined};
    } else if (anim === 'machine') contenu = li.texte.slice(0, Math.max(0, Math.floor((k - d0) * 2.4)));
    else if (anim === 'decode') contenu = brouille(li.texte, Math.max(0, k - d0), 2, c.de + j);
    const pastille = c.fond ? {background: couleur(th, c.fond), padding: '0.06em 0.2em 0.1em', display: 'inline-block'} : {display: 'inline-block'};
    return <div key={j} style={{fontSize: li.taille, textAlign: ta, ...st}}><span style={pastille}>{contenu || ' '}</span></div>;
  });
  return (
    <div style={{position: 'absolute', left: x, top: c.y, transform: `${tr} rotate(${c.rot || 0}deg)`, opacity: fin(c, f), ...base}}>{lignes}</div>
  );
};

// ---------------------------------------------------------------- mots qui claquent, un à la fois
const Mots = ({c, f, cfg}) => {
  const th = cfg.theme;
  const {x, tr} = ancre(c, cfg.l);
  const i = c.mots.findIndex((m) => f >= m.de && f < m.a);
  if (i < 0) return null;
  const m = c.mots[i], k = f - m.de, p = eOut5(P(k, 0, 4));
  const rot = c.secousse ? (i % 2 ? 1 : -1) * 1.4 * (1 - p) : 0;
  return (
    <div style={{position: 'absolute', left: x, top: c.y, transform: `${tr} scale(${lerp(1.28, 1, p).toFixed(3)}) rotate(${rot.toFixed(2)}deg)`,
      opacity: clamp((k + 1) / 2), ...police(th, c.police || 'titre'), fontSize: m.taille, lineHeight: 1, whiteSpace: 'pre',
      color: couleur(th, m.couleur || c.couleur, 'fort'), textShadow: OMBRE}}>{m.m}</div>
  );
};

// ---------------------------------------------------------------- sous-titres : le mot prononcé est mis en avant
const SousTitres = ({c, f, cfg}) => {
  const th = cfg.theme;
  const g = c.groupes.find((x) => f >= x.de && f < x.a);
  if (!g) return null;
  const k = f - g.de, p = eOut(P(k, 0, 3));
  const actif = couleur(th, c.couleur_active, 'accent');
  return (
    <div style={{position: 'absolute', left: 0, top: c.y, width: cfg.l, textAlign: 'center', ...police(th, c.police || 'texte'), fontSize: c.taille, lineHeight: 1.18,
      opacity: clamp((k + 1) / 2), transform: `translateY(${((1 - p) * 14).toFixed(1)}px)`}}>
      {g.lignes.map((ligne, j) => (
        <div key={j}>{ligne.map((m, i) => {
          const on = f >= m.de && f < m.a, pp = on ? eOut5(P(f, m.de, 4)) : 1;
          const st = c.style === 'pastille'
            ? {background: on ? actif : 'transparent', color: on ? couleur(th, c.couleur_sur_actif, 'clair') : couleur(th, c.couleur), borderRadius: '0.16em', padding: '0 0.14em'}
            : {color: on ? actif : couleur(th, c.couleur)};
          return <span key={i} style={{display: 'inline-block', margin: '0 0.1em', transform: on ? `scale(${lerp(1.12, 1.04, pp).toFixed(3)})` : undefined,
            textShadow: c.style === 'pastille' && on ? undefined : OMBRE, ...st}}>{m.m}</span>;
        })}</div>
      ))}
    </div>
  );
};

// ---------------------------------------------------------------- étiquette (petit texte technique, avec ou sans pastille)
const Etiquette = ({c, f, cfg}) => {
  const th = cfg.theme, k = f - c.de;
  const {x, tr} = ancre(c, cfg.l);
  const anim = c.anim || 'machine';
  const texte = anim === 'machine' ? c.texte.slice(0, Math.max(0, Math.floor(k * 2.4))) : anim === 'decode' ? brouille(c.texte, k, 2, c.de) : c.texte;
  const fond = c.fond === 'aucun' ? {textShadow: '0 2px 12px rgba(0,0,0,0.65)'}
    : {background: c.fond ? couleur(th, c.fond) : 'rgba(8,8,8,0.5)', padding: '0.32em 0.6em', borderRadius: c.arrondi ?? 6};
  return (
    <div style={{position: 'absolute', left: x, top: c.y, transform: tr, opacity: fin(c, f) * (anim === 'aucune' ? clamp((k + 1) / 3) : 1), ...police(th, c.police || 'mono'),
      fontSize: c.taille, lineHeight: 1.2, whiteSpace: 'pre', color: couleur(th, c.couleur), ...fond}}>{texte || ' '}</div>
  );
};

// ---------------------------------------------------------------- compteur (nombre ou temps qui défile)
const formate = (v, format) => {
  if (format === 'temps') { const s = Math.max(0, Math.round(v)); return String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0'); }
  if (format === 'decimal1') return v.toFixed(1).replace('.', ',');
  return String(Math.round(v)).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
};
const Compteur = ({c, f, cfg}) => {
  const th = cfg.theme, k = f - c.de;
  const {x, tr} = ancre(c, cfg.l);
  const v = lerp(c.depuis || 0, c.valeur, eOut5(P(k, 0, c.duree_anim || 24)));
  const txt = (c.prefixe || '') + formate(v, c.format) + (c.suffixe || '');
  const p = eBack(P(k, 0, 7));
  return (
    <div style={{position: 'absolute', left: x, top: c.y, transform: `${tr} scale(${lerp(1.2, 1, p).toFixed(3)})`, opacity: fin(c, f) * clamp((k + 1) / 2),
      ...police(th, c.police || 'titre'), fontSize: c.taille, lineHeight: 1, whiteSpace: 'pre', color: couleur(th, c.couleur, 'fort'), textShadow: OMBRE}}>
      {txt.split('').map((ch, i) => <span key={i} style={{display: 'inline-block', textAlign: 'center', width: /\d/.test(ch) ? `${c.chasse || 0.5}em` : undefined}}>{ch}</span>)}
    </div>
  );
};

// ---------------------------------------------------------------- image posée (logo, produit détouré, pictogramme)
const ImagePosee = ({c, f, cfg}) => {
  const k = f - c.de;
  const anim = c.anim || 'pop';
  let sc = 1, dx = 0, dy = 0, op = 1;
  if (anim === 'pop') { const p = eBack(P(k, 0, 9)); sc = lerp(0.6, 1, p); op = clamp((k + 1) / 2); }
  else if (anim === 'glisse') { const p = eOut5(P(k, 0, 12)); dy = (1 - p) * 140; op = clamp((k + 1) / 3); }
  else if (anim === 'tombe') { const p = eOut5(P(k, 0, 10)); dy = -(1 - p) * 520; op = clamp((k + 1) / 2); }
  else if (anim === 'fondu') op = clamp((k + 1) / 8);
  if (c.flotte) dy += Math.sin(k / 18) * (c.flotte === true ? 8 : c.flotte);
  return (
    <Img src={staticFile(`images/${c.fichier}`)} style={{position: 'absolute', left: c.x - c.l / 2, top: c.y - c.h / 2, width: c.l, height: c.h, objectFit: 'contain',
      opacity: op * fin(c, f), transform: `translate(${dx.toFixed(1)}px,${dy.toFixed(1)}px) scale(${sc.toFixed(3)}) rotate(${c.rot || 0}deg)`,
      filter: c.ombre === false ? undefined : 'drop-shadow(0 22px 34px rgba(0,0,0,0.5))'}} />
  );
};

// ---------------------------------------------------------------- voile de lisibilité
const Voile = ({c, f, cfg}) => {
  const k = f - c.de, op = clamp((k + 1) / 6) * fin(c, f), a = c.force ?? 0.5, W = cfg.l, H = cfg.h;
  if (c.cote === 'haut') return <div style={{position: 'absolute', left: 0, top: 0, width: W, height: 460, opacity: op, background: `linear-gradient(to bottom, rgba(0,0,0,${a}), rgba(0,0,0,0))`}} />;
  if (c.cote === 'bas') return <div style={{position: 'absolute', left: 0, top: H * 0.45, width: W, height: H * 0.55, opacity: op,
    background: `linear-gradient(to bottom, rgba(0,0,0,0) 0%, rgba(0,0,0,${a * 0.7}) 30%, rgba(0,0,0,${a}) 100%)`}} />;
  return <div style={{position: 'absolute', left: 0, top: 0, width: W, height: H, opacity: op * a, background: cfg.theme.encre}} />;
};

// ---------------------------------------------------------------- bandes noires du cinéma (cinémascope)
const Bandes = ({c, f, cfg}) => {
  const W = cfg.l, g = Math.max(1, c.glisse ?? 12);
  const q = c.sortie === 'coupe' ? eOut(P(f - c.de, 0, g)) : Math.min(eOut(P(f - c.de, 0, g)), 1 - eIn(P(f, c.a - g, g)));
  // « depuis_noir » : l'image s'ouvre comme un rideau, depuis le noir complet jusqu'aux bandes du cinéma
  const h = c.depuis_noir ? Math.round(lerp(cfg.h / 2 + 2, c.hauteur, eIO(P(f - c.de, 0, g))) * (c.sortie === 'coupe' ? 1 : 1 - eIn(P(f, c.a - g, g)))) : Math.round(c.hauteur * q);
  if (h < 1) return null;
  const b = {position: 'absolute', left: 0, width: W, height: h, background: '#000'};
  return <><div style={{...b, top: 0}} /><div style={{...b, top: cfg.h - h}} /></>;
};

// ---------------------------------------------------------------- fuites de lumière (pellicule) : taches chaudes qui passent et respirent
const Lumiere = ({c, f, cfg}) => {
  const W = cfg.l, H = cfg.h, k = f - c.de, n = c.a - c.de, g = Math.max(1, c.fondu ?? 10);
  const op = Math.min(eOut(P(k, 0, g)), 1 - eIn(P(f, c.a - g, g))) * (c.force ?? 0.5);
  if (op < 0.005) return null;
  const u = k / Math.max(1, n), sens = c.cote === 'droite' ? -1 : 1;
  const x1 = (c.cote === 'droite' ? 1.05 : -0.05) * W + sens * u * W * 0.55, y1 = H * (0.25 + 0.2 * Math.sin(k / 23));
  const x2 = (c.cote === 'droite' ? 0.75 : 0.25) * W + sens * u * W * 0.3, y2 = H * (0.8 - 0.15 * Math.cos(k / 31));
  const souffle = 0.75 + 0.25 * Math.sin(k / 9 + R('lu', c.de) * 6);
  return <div style={{position: 'absolute', left: 0, top: 0, width: W, height: H, mixBlendMode: 'screen', opacity: op * souffle,
    background: `radial-gradient(ellipse ${W * 0.45}px ${H * 0.7}px at ${x1}px ${y1}px, ${c.couleur} 0%, ${c.couleur}88 35%, transparent 70%),` +
      `radial-gradient(ellipse ${W * 0.3}px ${H * 0.45}px at ${x2}px ${y2}px, ${c.couleur2}cc 0%, transparent 70%)`}} />;
};

// ---------------------------------------------------------------- carte de fin (logo, nom, ligne)
const Signature = ({c, f, cfg}) => {
  const th = cfg.theme, k = f - c.de, W = cfg.l, H = cfg.h;
  const p1 = eBack(P(k, 2, 9)), p2 = eOut5(P(k, 6, 10)), p3 = eOut(P(k, 12, 8));
  return (
    <div style={{position: 'absolute', left: 0, top: 0, width: W, height: H, opacity: fin(c, f)}}>
      <div style={{position: 'absolute', left: 0, top: 0, width: W, height: H, background: th.encre, opacity: (c.fond_force ?? 0.86) * clamp((k + 1) / 8)}} />
      {c.logo && <Img src={staticFile(`images/${c.logo}`)} style={{position: 'absolute', left: W / 2 - c.logo_l / 2, top: c.y_logo, width: c.logo_l, height: c.logo_h, objectFit: 'contain',
        opacity: clamp(k / 3), transform: `scale(${lerp(0.7, 1, p1).toFixed(3)})`}} />}
      <div style={{position: 'absolute', left: 0, top: c.y_nom, width: W, textAlign: 'center', ...police(th, 'titre'), fontSize: c.taille_nom, lineHeight: 1, color: couleur(th, c.couleur, 'fort'),
        opacity: clamp((k - 5) / 3), transform: `translateY(${((1 - p2) * 40).toFixed(1)}px)`, whiteSpace: 'pre'}}>{c.nom}</div>
      <div style={{position: 'absolute', left: W / 2 - 120 * p3, top: c.y_nom + c.taille_nom * 1.16, width: 240 * p3, height: 6, background: couleur(th, 'accent')}} />
      {c.ligne && <div style={{position: 'absolute', left: 0, top: c.y_nom + c.taille_nom * 1.16 + 34, width: W, textAlign: 'center', ...police(th, 'texte'), fontSize: c.taille_ligne,
        lineHeight: 1.25, color: couleur(th, 'clair'), opacity: p3, whiteSpace: 'pre'}}>{c.ligne}</div>}
    </div>
  );
};

const TYPES = {titre: Titre, mots: Mots, 'sous-titres': SousTitres, etiquette: Etiquette, compteur: Compteur, image: ImagePosee, voile: Voile, signature: Signature, bandes: Bandes, lumiere: Lumiere};
export const Calque = ({c, f, cfg}) => {
  if (f < c.de || f >= c.a) return null;
  const T = TYPES[c.t];
  return T ? <T c={c} f={f} cfg={cfg} /> : null;
};

// ---------------------------------------------------------------- zones d'Instagram (contrôle seulement, jamais dans la vidéo finale)
export const Zones = ({cfg}) => {
  const z = cfg.zones, W = cfg.l, H = cfg.h;
  const rouge = {position: 'absolute', background: 'repeating-linear-gradient(135deg, rgba(255,0,60,0.34) 0 10px, rgba(255,0,60,0.08) 10px 26px)', outline: '3px dashed rgba(255,0,60,0.9)', outlineOffset: -3};
  const txt = {position: 'absolute', fontFamily: 'sans-serif', fontSize: 30, fontWeight: 700, color: '#fff', textShadow: '0 2px 6px #000'};
  return (
    <div style={{position: 'absolute', left: 0, top: 0, width: W, height: H}}>
      <div style={{...rouge, left: 0, top: 0, width: W, height: z.haut}} />
      <div style={{...rouge, left: 0, top: z.bas, width: W, height: H - z.bas}} />
      <div style={{...rouge, left: z.droite, top: z.droite_depuis, width: W - z.droite, height: z.bas - z.droite_depuis}} />
      <div style={{position: 'absolute', left: z.marge, top: z.haut, width: W - 2 * z.marge, height: z.bas - z.haut, outline: '2px dashed rgba(255,255,255,0.55)'}} />
      {z.reel && z.bas_conseille < z.bas && <div style={{position: 'absolute', left: 0, top: z.bas_conseille, width: W, height: 0, borderTop: '3px dashed rgba(255,170,0,0.95)'}} />}
      {z.reel && z.bas_conseille < z.bas && <div style={{...txt, left: 24, top: z.bas_conseille + 8, color: '#FFC24D'}}>sous ce trait : caché si la légende est longue</div>}
      {z.reel && <div style={{...txt, left: 24, top: z.haut - 44}}>haut : barre Instagram</div>}
      {z.reel && <div style={{...txt, left: 24, top: z.bas + 12}}>bas : légende, compte, musique</div>}
    </div>
  );
};
