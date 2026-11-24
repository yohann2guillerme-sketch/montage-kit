// Petits outils du moteur de montage : courbes d'animation, hasard stable, temps source d'un plan.
import {random} from 'remotion';

export const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
export const lerp = (a, b, t) => a + (b - a) * t;
export const eOut = (t) => 1 - Math.pow(1 - clamp(t), 3);
export const eOut5 = (t) => 1 - Math.pow(1 - clamp(t), 5);
export const eIn = (t) => Math.pow(clamp(t), 3);
export const eIO = (t) => { t = clamp(t); return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; };
export const eBack = (t) => { t = clamp(t); const c1 = 1.9, c3 = c1 + 1; return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2); };
// avancement 0→1 entre l'image a et l'image a + d
export const P = (f, a, d) => clamp((f - a) / Math.max(1e-6, d));
// hasard stable : la même clé donne toujours le même nombre (rendu identique d'une fois sur l'autre)
export const R = (...k) => random(k.join('|'));
export const pad4 = (i) => String(i).padStart(4, '0');

// ---------------------------------------------------------------- vitesse et temps source d'un plan
// plan.vitesse : un nombre (1 = normal, 0.5 = ralenti, -2 = marche arrière accélérée) ou une rampe [[image, vitesse], ...]
export const vitesseA = (p, k) => {
  if (typeof p.vitesse === 'number') return p.vitesse;
  const kf = p.vitesse;
  if (k <= kf[0][0]) return kf[0][1];
  for (let i = 0; i < kf.length - 1; i++) {
    const [a, va] = kf[i], [b, vb] = kf[i + 1];
    if (k >= a && k <= b) return b > a ? va + (vb - va) * (k - a) / (b - a) : vb;
  }
  return kf[kf.length - 1][1];
};
export const tempsSource = (p, k, ips) => {
  if (typeof p.vitesse === 'number') return p.src + p.vitesse * k / ips;
  let t = p.src; const n = Math.floor(k);
  for (let j = 0; j < n; j++) t += vitesseA(p, j) / ips;
  return t + vitesseA(p, n) * (k - n) / ips;
};
// Images sources à fondre pour l'image k : flou de mouvement en accéléré, fondu entre deux images en ralenti.
export const echantillons = (p, k, ips) => {
  const cl = (i) => Math.max(0, Math.min(p.n - 1, i));
  if (p.photo || p.n <= 1) return [{i: 0, w: 1}];
  const v = vitesseA(p, k);
  const fi = (tempsSource(p, k, ips) - p.debut) * p.ips;
  if (v === 0) return [{i: cl(Math.round(fi)), w: 1}];
  if (Math.abs(v) > 8) {
    const n = 5, pas = (v / ips) * p.ips;
    return Array.from({length: n}, (_, j) => ({i: cl(Math.round(fi + j * pas / n)), w: 1 / n}));
  }
  const pas = Math.abs(v) * p.ips / ips;
  if (Math.abs(v) > 1.15 || v < 0) {
    const n = Math.max(2, Math.min(4, Math.round(pas)));
    const u = [...new Set(Array.from({length: n}, (_, j) => cl(Math.round(fi + Math.sign(v) * j * pas / n))))];
    return u.map((i) => ({i, w: 1 / u.length}));
  }
  if (Math.abs(v) < 0.999) {
    const a = Math.floor(fi), fr = fi - a;
    if (fr < 0.08) return [{i: cl(a), w: 1}];
    if (fr > 0.92) return [{i: cl(a + 1), w: 1}];
    return [{i: cl(a), w: 1 - fr}, {i: cl(a + 1), w: fr}];
  }
  return [{i: cl(Math.round(fi)), w: 1}];
};
export const plusProche = (arr, x) => arr.reduce((b, v) => (Math.abs(v - x) < Math.abs(b - x) ? v : b), arr[0]);

// couleur : nom du thème (« clair », « accent », « gris », « encre ») ou code #hex
export const couleur = (th, c, defaut = 'clair') => {
  const v = c || defaut;
  return th[v] || v;
};
// style de police : « titre », « texte » ou « mono » du thème
export const police = (th, nom) => {
  const p = th[nom] || th.texte;
  return {fontFamily: `'${p.famille}', sans-serif`, fontWeight: p.poids || 400, fontStyle: p.style || 'normal',
    letterSpacing: p.espacement ? `${p.espacement}em` : undefined, textTransform: p.casse === 'maj' ? 'uppercase' : undefined};
};
