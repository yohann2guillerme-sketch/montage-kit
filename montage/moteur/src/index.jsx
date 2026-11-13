// Point d'entrée Remotion : une seule composition « Montage », entièrement décrite par la fiche résolue.
import React from 'react';
import {registerRoot, Composition} from 'remotion';
import {Montage} from './Moteur.jsx';

const DEFAUT = {
  l: 1080, h: 1920, ips: 30, n: 90, plans: [], calques: [], accents: [], polices: [], audio: null, fondu_fin: 0, zones: null,
  finition: {grain: 0, vignette: 0},
  theme: {encre: '#0B0B0B', clair: '#E6E6E6', fort: '#FFFFFF', accent: '#FFFFFF', gris: '#8C8C8C',
    titre: {famille: 'sans-serif', poids: 900}, texte: {famille: 'sans-serif', poids: 600}, mono: {famille: 'monospace', poids: 600}},
};
const Racine = () => (
  <Composition id="Montage" component={Montage} width={1080} height={1920} fps={30} durationInFrames={90} defaultProps={DEFAUT}
    calculateMetadata={({props}) => ({durationInFrames: props.n, fps: props.ips, width: props.l, height: props.h})} />
);
registerRoot(Racine);
