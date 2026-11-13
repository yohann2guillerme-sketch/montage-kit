// Un plan : images du rush (ou photo), rampes de vitesse, zooms, transitions d'entrée et de sortie.
// Repris du moteur du Reel HYROX v2 (validé « ultra propre »), rendu générique.
import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame} from 'remotion';
import {clamp, lerp, eOut, eIO, P, R, pad4, echantillons, tempsSource, plusProche} from './outils.js';
import {Calque} from './calques.jsx';

export const AccentCtx = React.createContext({sc: 1, tx: 0, ty: 0});

// durée des transitions, en images : [sur le plan qui sort, sur le plan qui entre]
export const TD = {zoom: [4, 5], whipG: [3, 4], whipD: [3, 4], whipH: [3, 4], whipB: [3, 4], glitch: [2, 3], flou: [6, 6], noir: [5, 5], flash: [0, 5], coupe: [0, 0]};

const REGARDS = {
  nb: 'grayscale(1) contrast(1.12) brightness(0.9)',
  nbsombre: 'grayscale(1) contrast(1.12) brightness(0.74)',
  contraste: 'contrast(1.14) saturate(1.06)',
  chaud: 'sepia(0.16) saturate(1.12) contrast(1.05)',
  froid: 'saturate(0.86) contrast(1.08) hue-rotate(-6deg)',
  doux: 'contrast(0.96) saturate(0.94) brightness(1.03)',
  retro: 'saturate(0.5) contrast(1.3) brightness(1.06) sepia(0.12)',
};

const etatPlan = (p, k, W, H) => {
  const n = p.t1 - p.t0;
  const st = {k, sc: 1, tx: 0, ty: 0, rot: 0, flash: 0, rgb: 0, zb: 0, hb: 0, vb: 0, flou: 0, lum: 1, glitch: 0, regard: REGARDS[p.regard] || p.regard || ''};
  for (const e of p.effets || []) {
    if (e.t === 'kb') { st.sc *= lerp(e.a ?? 1, e.b ?? 1.08, k / n); st.tx += lerp(0, e.dx || 0, k / n); st.ty += lerp(0, e.dy || 0, k / n); }
    else if (e.t === 'zr') st.sc *= lerp(e.a, e.b, eIO(P(k, e.k0, e.k1 - e.k0)));
    else if (e.t === 'punch' && k >= e.at) st.sc *= 1 + e.a * Math.pow(1 - P(k, e.at, e.d), 2.2);
    else if (e.t === 'shake' && k >= e.at && k < e.at + e.d) {
      const a = e.a * Math.pow(1 - P(k, e.at, e.d), 1.4);
      st.tx += (R('sx', p.id, k) * 2 - 1) * a; st.ty += (R('sy', p.id, k) * 2 - 1) * a; st.rot += (R('sr', p.id, k) * 2 - 1) * a * 0.05;
    }
    else if (e.t === 'flash' && k >= e.at && k < e.at + e.d) st.flash = Math.max(st.flash, Math.pow(1 - P(k, e.at, e.d), 1.5));
    else if (e.t === 'rgb' && k >= e.at && k < e.at + e.d) st.rgb = Math.max(st.rgb, e.a * (1 - P(k, e.at, e.d)));
    else if (e.t === 'rewind') { st.regard = REGARDS.retro; st.rgb = Math.max(st.rgb, 7); st.tx += (R('rw', p.id, k) - 0.5) * 12; }
  }
  const applique = (type, q, sens) => {
    if (type === 'zoom') { st.sc *= 1 + (sens === 'sortie' ? 0.45 : 0.3) * q; st.zb = Math.max(st.zb, q * (sens === 'sortie' ? 1 : 0.9)); st.lum *= 1 + 0.3 * q; }
    else if (type === 'whipG') { st.tx += (sens === 'sortie' ? -1 : 1) * W * 0.45 * q; st.hb = 70 * q; }
    else if (type === 'whipD') { st.tx += (sens === 'sortie' ? 1 : -1) * W * 0.45 * q; st.hb = 70 * q; }
    else if (type === 'whipH') { st.ty += (sens === 'sortie' ? -1 : 1) * H * 0.3 * q; st.vb = 70 * q; }
    else if (type === 'whipB') { st.ty += (sens === 'sortie' ? 1 : -1) * H * 0.3 * q; st.vb = 70 * q; }
    else if (type === 'glitch') { st.glitch = Math.max(st.glitch, q); st.rgb = Math.max(st.rgb, 22 * q); }
    else if (type === 'flou') { st.flou = Math.max(st.flou, 18 * q); st.lum *= 1 + 0.3 * q; }
    else if (type === 'noir') { st.lum *= 1 - q; }
    else if (type === 'flash' && sens === 'entree') st.flash = Math.max(st.flash, q);
  };
  const ti = p.entree, to = p.sortie;
  if (ti && TD[ti] && TD[ti][1] && k < TD[ti][1]) applique(ti, Math.pow(1 - k / TD[ti][1], ti === 'flash' ? 1.5 : 2), 'entree');
  if (to && TD[to] && TD[to][0] && k >= n - TD[to][0]) applique(to, Math.pow((k - (n - TD[to][0]) + 1) / TD[to][0], 2), 'sortie');
  return st;
};

const Pile = ({p, smp, plein}) => {
  let acc = 0;
  return smp.map((x, j) => { acc += x.w; return <Img key={j} src={staticFile(`plans/${p.id}/${pad4(x.i)}.jpg`)} style={{...plein, objectFit: 'cover', opacity: x.w / acc}} />; });
};
const Separe = ({p, smp, a, plein}) => (
  <div style={{...plein, background: '#000', isolation: 'isolate'}}>
    {[['#chR', -a], ['#chG', 0], ['#chB', a]].map(([fl, dx], j) => (
      <div key={j} style={{...plein, filter: `url(${fl})`, transform: `translateX(${dx}px)`, mixBlendMode: j ? 'screen' : 'normal'}}>
        <Pile p={p} smp={smp} plein={plein} />
      </div>
    ))}
  </div>
);
const Image = ({p, smp, st, W, H, plein}) => {
  const une = smp.slice(0, 1);
  const coeur = st.rgb > 0.5 ? <Separe p={p} smp={smp} a={st.rgb} plein={plein} /> : <Pile p={p} smp={smp} plein={plein} />;
  const bords = [];
  if (st.hb > 0.5) {
    bords.push(<div key="g" style={{...plein, left: -W, transform: 'scaleX(-1)'}}><Pile p={p} smp={une} plein={plein} /></div>);
    bords.push(<div key="d" style={{...plein, left: W, transform: 'scaleX(-1)'}}><Pile p={p} smp={une} plein={plein} /></div>);
  }
  if (st.vb > 0.5) {
    bords.push(<div key="h" style={{...plein, top: -H, transform: 'scaleY(-1)'}}><Pile p={p} smp={une} plein={plein} /></div>);
    bords.push(<div key="b" style={{...plein, top: H, transform: 'scaleY(-1)'}}><Pile p={p} smp={une} plein={plein} /></div>);
  }
  const fantomes = [];
  if (st.zb > 0.05) for (let j = 1; j <= 3; j++) fantomes.push(
    <div key={'f' + j} style={{...plein, transform: `scale(${1 + 0.05 * j * st.zb})`, opacity: 0.42 * st.zb / j}}><Pile p={p} smp={une} plein={plein} /></div>);
  const tranches = [];
  if (st.glitch > 0.05) for (let b = 0; b < 7; b++) {
    const y = Math.floor(R('gy', p.id, st.k, b) * H * 0.95), h = Math.floor(18 + R('gh', p.id, st.k, b) * 150);
    const dx = (R('gx', p.id, st.k, b) * 2 - 1) * 120 * st.glitch;
    tranches.push(
      <div key={'t' + b} style={{position: 'absolute', left: 0, top: y, width: W, height: h, overflow: 'hidden'}}>
        <div style={{...plein, top: -y, transform: `translateX(${dx}px)`}}><Pile p={p} smp={une} plein={plein} /></div>
      </div>);
  }
  return <>{bords}{coeur}{fantomes}{tranches}</>;
};

export const Plan = ({p, cfg, derriere}) => {
  const k = useCurrentFrame();
  const ac = React.useContext(AccentCtx);
  const {l: W, h: H, ips, theme} = cfg;
  const plein = {position: 'absolute', left: 0, top: 0, width: W, height: H};
  const st = etatPlan(p, k, W, H);
  let smp = echantillons(p, k, ips);
  // plan détouré : on prend l'image qui a un masque, sans fondu (le masque doit coller au sujet)
  let mi = null;
  if (p.masques && p.masques.length) {
    mi = p.photo ? p.masques[0] : plusProche(p.masques, (tempsSource(p, k, ips) - p.debut) * p.ips);
    smp = [{i: mi, w: 1}];
  }
  const fid = `fd_${p.id}_${Math.round(k * 1000)}`;
  const dir = st.hb > 0.5 || st.vb > 0.5;
  const filt = [dir ? `url(#${fid})` : '', st.flou > 0.3 ? `blur(${st.flou.toFixed(1)}px)` : '',
    Math.abs(st.lum - 1) > 0.01 ? `brightness(${st.lum.toFixed(3)})` : ''].filter(Boolean).join(' ');
  const ac2 = p.sans_accent ? {sc: 1, tx: 0, ty: 0} : ac;
  const contenu = (
    <>
      {dir && <svg width="0" height="0" style={{position: 'absolute'}}><defs>
        <filter id={fid} x="-100%" y="-100%" width="300%" height="300%" colorInterpolationFilters="sRGB">
          <feGaussianBlur stdDeviation={`${st.hb.toFixed(1)} ${st.vb.toFixed(1)}`} edgeMode="duplicate" />
        </filter></defs></svg>}
      <div style={{...plein, transform: `translate(${(st.tx + ac2.tx).toFixed(1)}px,${(st.ty + ac2.ty).toFixed(1)}px) rotate(${st.rot.toFixed(3)}deg) scale(${(st.sc * ac2.sc).toFixed(4)})`,
        filter: filt || undefined}}>
        {(() => {
          const image = <div style={{...plein, filter: st.regard || undefined}}><Image p={p} smp={smp} st={st} W={W} H={H} plein={plein} /></div>;
          if (!p.double) return image;
          // deuxième image : double exposition (fondue en « screen ») ou écran partagé (le milieu de chaque image, côte à côte)
          const d = p.double, smp2 = echantillons(d, k, ips), f = p.double_force ?? 0.45;
          const deux = <div style={{...plein, filter: (d.regard ? (REGARDS[d.regard] || d.regard) : st.regard) || undefined}}><Pile p={d} smp={smp2} plein={plein} /></div>;
          if (p.double_mode === 'partage') {
            const ouvre = eOut(P(k, 0, 8));
            const moitie = (dx) => ({position: 'absolute', left: 0, top: 0, width: W, height: H, clipPath: `inset(0 ${25 * ouvre}% 0 ${25 * ouvre}%)`,
              transform: `translateX(${(dx * ouvre).toFixed(1)}px)`});
            return <>
              <div style={moitie(-W / 4)}>{image}</div>
              <div style={{...moitie(W / 4), opacity: clamp(k / 4)}}>{deux}</div>
              <div style={{position: 'absolute', left: W / 2 - 3, top: 0, width: 6, height: H, background: '#000', opacity: ouvre}} />
            </>;
          }
          return <>{image}<div style={{...plein, mixBlendMode: 'screen', opacity: f}}>{deux}</div></>;
        })()}
        {/* textes « derrière le sujet » : texte plein, puis le sujet détouré par-dessus, puis le contour du texte (facultatif) */}
        {mi !== null && derriere.map((c, i) => <Calque key={'a' + i} c={c} f={k + p.t0} cfg={cfg} />)}
        {mi !== null && <Img src={staticFile(`masques/${p.id}/${pad4(mi)}.png`)} style={{...plein, objectFit: 'cover', filter: st.regard || undefined}} />}
        {mi !== null && derriere.filter((c) => c.contour_devant).map((c, i) => <Calque key={'b' + i} c={{...c, contour: true}} f={k + p.t0} cfg={cfg} />)}
      </div>
      {st.flash > 0.01 && <div style={{...plein, background: '#fff', opacity: st.flash * 0.92}} />}
    </>
  );
  if (!p.cadre) return <AbsoluteFill style={{background: theme.encre, overflow: 'hidden'}}>{contenu}</AbsoluteFill>;
  // « cadre » : l'image plein écran se range dans un tirage photo blanc penché, sur la même image floutée et assombrie
  const g = geoCadre(p.cadre, k, W, H), cad = p.cadre;
  return (
    <AbsoluteFill style={{background: theme.encre, overflow: 'hidden'}}>
      {g.u > 0.001 && <div style={{...plein, transform: 'scale(1.12)', filter: `blur(${cad.flou}px) brightness(${cad.sombre})`}}><Pile p={p} smp={smp.slice(0, 1)} plein={plein} /></div>}
      <div style={{position: 'absolute', left: g.cx - g.bw / 2 - g.b, top: g.cy - g.bh / 2 - g.b, width: g.bw + 2 * g.b, height: g.bh + g.b + g.bb, background: cad.couleur,
        transform: `rotate(${g.rot.toFixed(3)}deg)`, transformOrigin: `${(g.bw / 2 + g.b).toFixed(1)}px ${(g.bh / 2 + g.b).toFixed(1)}px`,
        boxShadow: g.u > 0.001 ? `0 30px 70px rgba(0,0,0,${(0.5 * g.u).toFixed(3)})` : undefined}}>
        <div style={{position: 'absolute', left: g.b, top: g.b, width: g.bw, height: g.bh, overflow: 'hidden'}}>
          <div style={{position: 'absolute', left: (g.bw - W * g.s) / 2, top: (g.bh - H * g.s) / 2, width: W, height: H, overflow: 'hidden',
            transform: `scale(${g.s.toFixed(5)})`, transformOrigin: '0 0'}}>{contenu}</div>
        </div>
      </div>
    </AbsoluteFill>
  );
};

// géométrie du cadre à l'image k du plan (recopiée dans outils/tete.py, geo_cadre) : u = avancement de l'entrée,
// bw × bh = la photo (sans le bord blanc), centrée en (cx, cy), image du plan réduite de s, bord b (bb en bas), rotation rot
export const geoCadre = (cad, k, W, H) => {
  const u = eOut(P(k, cad.de, cad.entree));
  const bw = lerp(W, cad.l, u), bh = lerp(H, cad.h, u);
  return {u, bw, bh, cx: lerp(W / 2, cad.x, u), cy: lerp(H / 2, cad.y - (cad.bas - cad.bord) / 2, u), s: Math.max(bw / W, bh / H),
    b: cad.bord * u, bb: cad.bas * u, rot: cad.angle * u};
};
