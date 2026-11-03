import { decodeState } from './urlstate.js';
import { createMap, setAppState } from './map.js';
import { mountLayerPanel } from './layers.js';

const state = decodeState(window.location.hash);
const map = createMap(document.getElementById('map'), state);

mountLayerPanel(map, state, (next) => setAppState(map, next));

// Painel recolhivel (em telas estreitas comeca fechado).
const panel = document.getElementById('layer-panel');
const toggle = document.getElementById('panel-toggle');
const setOpen = (open) => {
  panel.classList.toggle('is-open', open);
  toggle.setAttribute('aria-expanded', String(open));
};
setOpen(window.matchMedia('(min-width: 720px)').matches);
toggle.addEventListener('click', () => setOpen(!panel.classList.contains('is-open')));

// Atalho para depuracao e para os testes de fumaca.
window.geoworldMap = map;
