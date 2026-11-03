import { decodeState } from './urlstate.js';
import { createMap, setAppState } from './map.js';
import { mountLayerPanel } from './layers.js';
import { addDataLayers, applySampleFilter } from './datalayers.js';

// Pasta dos dados (relativa a pagina); sem sobrescrita por URL.
const DATA_BASE = 'data/';
const WARNING = 'Camada indisponível: não foi possível carregar os dados.';

const state = decodeState(window.location.hash);
const map = createMap(document.getElementById('map'), state);

mountLayerPanel(map, state, (next) => {
  applySampleFilter(map, next.filters);
  setAppState(map, next);
});

applySampleFilter(map, state.filters);
addDataLayers(map, DATA_BASE, (layerId, err) => {
  console.warn(`Falha ao carregar a camada ${layerId}:`, err);
  const slot = document.querySelector(`[data-warning-for="${layerId}"]`);
  if (slot) slot.textContent = WARNING;
});

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
