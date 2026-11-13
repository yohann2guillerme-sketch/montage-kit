#!/usr/bin/env node
// Rendu d'un montage avec Remotion. Appelé par montage.py (à la main seulement pour dépanner) :
//   node rendu.mjs <dossier de travail> images liste=0,30,60 [echelle=0.25] [zones=1] [sortie=dossier]
//   node rendu.mjs <dossier de travail> apercu [plage=0-120] [sortie=fichier.mp4]
//   node rendu.mjs <dossier de travail> final  [plage=0-120] [sortie=fichier.mp4] [crf=17]
// Partage de la machine (montage.py les donne sur le Mac, voir outils/ressources.py) : [coeurs=1] onglets du rendu, [fils=3] fils de
// l'encodeur x264, [cache=octets] cache vidéo, [gl=swangle] moteur graphique (sans option : celui que Chromium choisit).
// Normes du fichier final : H.264 High 4.2, yuv420p, plage limitée, BT.709 partout, 30 i/s, AAC 48 kHz, lecture immédiate (faststart).
import {bundle} from '@remotion/bundler';
import {renderStill, renderMedia, selectComposition, openBrowser} from '@remotion/renderer';
import path from 'path';
import fs from 'fs';
import os from 'os';
import {fileURLToPath} from 'url';

const ici = path.dirname(fileURLToPath(import.meta.url));
const [travailArg, mode, ...reste] = process.argv.slice(2);
if (!travailArg || !['images', 'apercu', 'final'].includes(mode)) {
  console.error('usage : node rendu.mjs <dossier de travail> images|apercu|final [cle=valeur ...]');
  process.exit(2);
}
const travail = path.resolve(travailArg);
const o = Object.fromEntries(reste.map((x) => { const i = x.indexOf('='); return i < 0 ? [x, '1'] : [x.slice(0, i), x.slice(i + 1)]; }));
const cfg = JSON.parse(fs.readFileSync(path.join(travail, 'calcul.json'), 'utf8'));
const chrome = [process.env.MONTAGE_CHROME, '/opt/pw-browsers/chromium'].find((p) => p && fs.existsSync(p));
const navigateur = chrome ? {browserExecutable: chrome} : {};
const coeurs = Number(o.coeurs || process.env.MONTAGE_COEURS || os.cpus().length);
const fils = Number(o.fils || 0);                   // 0 : l'encodeur prend tous les cœurs
const cache = o.cache ? Number(o.cache) : null;     // null : la moitié de la mémoire (Remotion)
const gl = o.gl || process.env.MONTAGE_GL || null;  // null : Chromium choisit (la carte graphique sur un Mac)
const graphique = gl ? {chromiumOptions: {gl}} : {};
const silence = {logLevel: 'error'};
const t0 = Date.now();
const sec = () => ((Date.now() - t0) / 1000).toFixed(0) + ' s';

// Le paquet du moteur ne dépend que du code (les données passent en « inputProps », le dossier public est un lien) :
// on le refait seulement si le code du moteur a changé.
const sources = fs.readdirSync(path.join(ici, 'src')).sort().map((f) => { const st = fs.statSync(path.join(ici, 'src', f)); return `${f}:${st.size}:${Math.round(st.mtimeMs)}`; }).join('|');
const paquet = path.join(travail, 'bundle');
const marque = path.join(paquet, 'cle.txt');
let serveUrl = paquet;
if (!(fs.existsSync(marque) && fs.readFileSync(marque, 'utf8') === sources && fs.existsSync(path.join(paquet, 'index.html')))) {
  fs.rmSync(paquet, {recursive: true, force: true});
  serveUrl = await bundle({entryPoint: path.join(ici, 'src/index.jsx'), rootDir: ici, publicDir: path.join(travail, 'public'), outDir: paquet, symlinkPublicDir: true});
  fs.writeFileSync(marque, sources);
}
const inputProps = {...cfg, zones: o.zones === '1' ? cfg.zones_instagram : null, audio: mode === 'images' ? null : cfg.audio};
const composition = await selectComposition({serveUrl, id: 'Montage', inputProps, ...navigateur, ...graphique, ...silence});

if (mode === 'images') {
  const sortie = path.resolve(o.sortie || path.join(travail, 'images'));
  fs.mkdirSync(sortie, {recursive: true});
  const liste = (o.liste || '0').split(',').filter((x) => x !== '').map(Number).filter((x) => x >= 0 && x < cfg.n);
  const browser = await openBrowser('chrome', {...navigateur, ...graphique, ...silence});
  for (const fr of liste) {
    await renderStill({composition, serveUrl, inputProps, output: path.join(sortie, String(fr).padStart(5, '0') + '.jpg'), frame: fr, imageFormat: 'jpeg', jpegQuality: 92,
      scale: Number(o.echelle || 1), puppeteerInstance: browser, timeoutInMilliseconds: 120000, ...navigateur, ...silence});
  }
  await browser.close({silent: true});
  console.log(`IMAGES OK ${liste.length} image(s) en ${sec()} → ${sortie}`);
} else {
  const final = mode === 'final';
  const plage = o.plage ? o.plage.split('-').map(Number) : [0, cfg.n - 1];
  const sortie = path.resolve(o.sortie || path.join(travail, final ? 'final.mp4' : 'apercu.mp4'));
  let dernier = -1;
  // réglages d'encodage en plus : niveau 4.2 (lu partout) et lecture immédiate
  const surcharge = ({args}) => {
    const a = [...args];
    if (final && a.includes('libx264')) a.splice(a.length - 1, 0, '-refs', '4', '-level:v', '4.2');
    if (fils && a.includes('libx264')) {            // encodeur et décodage des images reçues : `fils` fils chacun
      a.splice(a.length - 1, 0, '-threads', String(fils));
      for (let i = a.length - 2; i >= 0; i--) if (a[i] === '-i' && a[i - 2] !== '-threads') a.splice(i, 0, '-threads', String(fils));
    }
    if (a[a.length - 1].endsWith('.mp4') && !a.includes('+faststart')) a.splice(a.length - 1, 0, '-movflags', '+faststart');
    return a;
  };
  await renderMedia({composition, serveUrl, inputProps, codec: 'h264', outputLocation: sortie, concurrency: coeurs, frameRange: plage,
    pixelFormat: 'yuv420p', colorSpace: 'bt709', audioCodec: 'aac', timeoutInMilliseconds: 120000, ffmpegOverride: surcharge, ...navigateur, ...graphique, ...silence,
    ...(cache ? {offthreadVideoCacheSizeInBytes: cache, mediaCacheSizeInBytes: cache, offthreadVideoThreads: 1} : {}),
    ...(final
      ? {imageFormat: 'png', crf: Number(o.crf || 17), x264Preset: 'slow', audioBitrate: '320k'}
      : {imageFormat: 'jpeg', jpegQuality: 80, scale: 0.5, crf: 24, x264Preset: 'veryfast', audioBitrate: '192k'}),
    onProgress: ({progress}) => { const p = Math.floor(progress * 10); if (p !== dernier) { dernier = p; if (p > 0 && p < 10) console.log(`rendu ${p * 10} % (${sec()})`); } }});
  console.log(`${final ? 'FINAL' : 'APERCU'} OK ${plage[1] - plage[0] + 1} images en ${sec()} → ${sortie}`);
}
