// Moteur de montage : assemble les plans, les calques, les coups de zoom sur la musique, le grain et le son.
// Tout vient de la fiche résolue (calcul.json) passée en « inputProps » : aucune donnée de client dans ce fichier.
import React from 'react';
import {AbsoluteFill, Audio, Img, Sequence, staticFile, useCurrentFrame, delayRender, continueRender, cancelRender} from 'remotion';
import {R} from './outils.js';
import {Plan, AccentCtx} from './Plan.jsx';
import {Calque, Zones} from './calques.jsx';

// polices locales (licence libre OFL), chargées avant la première image : si une police manque, le rendu s'arrête (jamais de police de secours)
const usePolices = (polices) => {
  const [pret, setPret] = React.useState(polices.length === 0);
  const [h] = React.useState(() => (polices.length ? delayRender('polices') : null));
  React.useEffect(() => {
    if (!polices.length) return;
    Promise.all(polices.map(([fam, fichier, poids, style]) => new FontFace(fam, `url(${staticFile('polices/' + fichier)})`, {weight: poids, style}).load().then((x) => document.fonts.add(x))))
      .then(() => { setPret(true); continueRender(h); })
      .catch((e) => cancelRender(new Error('Police introuvable : ' + e.message)));
  }, []);
  return pret;
};

// coups sur la musique : petite poussée de zoom, secousse ou flash, appliqués aux images (pas aux textes)
const accentA = (accents, F) => {
  const a = {sc: 1, tx: 0, ty: 0, fl: 0};
  for (const e of accents) {
    if (F < e.at || F >= e.at + e.d) continue;
    const q = Math.pow(1 - (F - e.at) / e.d, 2);
    if (e.z) a.sc *= 1 + e.z * q;
    if (e.sh) { a.tx += (R('ax', e.at, F) * 2 - 1) * e.sh * q; a.ty += (R('ay', e.at, F) * 2 - 1) * e.sh * q; }
    if (e.fl) a.fl = Math.max(a.fl, e.fl * q);
  }
  return a;
};

export const Montage = (cfg) => {
  const F = useCurrentFrame();
  const pret = usePolices(cfg.polices || []);
  const {l: W, h: H, theme, finition = {}} = cfg;
  const plein = {position: 'absolute', left: 0, top: 0, width: W, height: H};
  if (!pret) return <AbsoluteFill style={{background: theme.encre}} />;
  const a = accentA(cfg.accents || [], F);
  const libres = (cfg.calques || []).filter((c) => !c.derriere);
  const grain = finition.grain || 0, vignette = finition.vignette || 0;
  return (
    <AbsoluteFill style={{background: theme.encre, overflow: 'hidden'}}>
      <svg width="0" height="0" style={{position: 'absolute'}}><defs>
        <filter id="chR" colorInterpolationFilters="sRGB"><feColorMatrix type="matrix" values="1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0" /></filter>
        <filter id="chG" colorInterpolationFilters="sRGB"><feColorMatrix type="matrix" values="0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 1 0" /></filter>
        <filter id="chB" colorInterpolationFilters="sRGB"><feColorMatrix type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0" /></filter>
      </defs></svg>
      <AccentCtx.Provider value={a}>
        {cfg.plans.map((p) => (
          <Sequence key={p.id} from={p.t0} durationInFrames={p.t1 - p.t0} layout="none">
            <Plan p={p} cfg={cfg} derriere={(cfg.calques || []).filter((c) => c.derriere && c.plan === p.id)} />
          </Sequence>
        ))}
      </AccentCtx.Provider>
      {libres.map((c, i) => <Calque key={i} c={c} f={F} cfg={cfg} />)}
      {a.fl > 0.01 && <div style={{...plein, background: '#fff', opacity: a.fl}} />}
      {/* finition : grain argentique (casse les dégradés en bandes) et vignette */}
      {grain > 0 && <Img src={staticFile(`fx/grain${F % 8}.png`)} style={{position: 'absolute', left: -20 + R('gnx', F) * 20, top: -20 + R('gny', F) * 20, width: W + 40, height: H + 40,
        mixBlendMode: 'overlay', opacity: grain}} />}
      {vignette > 0 && <div style={{...plein, background: `radial-gradient(ellipse 85% 70% at 50% 50%, rgba(0,0,0,0) 55%, rgba(0,0,0,${vignette}) 100%)`}} />}
      {cfg.fondu_fin > 0 && F >= cfg.n - cfg.fondu_fin && <div style={{...plein, background: '#000', opacity: Math.pow((F - (cfg.n - cfg.fondu_fin) + 1) / cfg.fondu_fin, 2)}} />}
      {cfg.zones && <Zones cfg={cfg} />}
      {cfg.audio && <Audio src={staticFile(cfg.audio)} />}
    </AbsoluteFill>
  );
};
