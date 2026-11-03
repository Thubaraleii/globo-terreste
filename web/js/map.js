// Mapa-base: globo, escala, navegacao, coordenadas do cursor e estado na URL.
// Usa o global `maplibregl` (web/vendor/maplibre-gl.js).
import { encodeState } from './urlstate.js';
import { baseStyle } from './basemaps.js';
import { ATTRIBUTION_FALLBACK } from './inspector.js';

const URL_DEBOUNCE_MS = 250;
const PLACEHOLDER = 'Passe o cursor sobre o mapa';
const appStates = new WeakMap();
const timers = new WeakMap();

class CoordsControl {
  onAdd(map) {
    this.el = document.createElement('div');
    this.el.className = 'maplibregl-ctrl coords-readout';
    this.el.textContent = PLACEHOLDER;
    map.on('mousemove', (e) => {
      const { lng, lat } = e.lngLat.wrap();
      this.el.textContent = `${lat.toFixed(4)}°, ${lng.toFixed(4)}°`;
    });
    map.getCanvas().addEventListener('mouseleave', () => {
      this.el.textContent = PLACEHOLDER;
    });
    return this.el;
  }

  onRemove() {
    this.el.remove();
  }
}

// Estado completo (camera atual + camadas/filtros guardados) para gravar na URL.
export function currentState(map) {
  const c = map.getCenter().wrap();
  return { ...appStates.get(map), lng: c.lng, lat: c.lat, zoom: map.getZoom() };
}

export function writeUrl(map) {
  try {
    history.replaceState(null, '', '#' + encodeState(currentState(map)));
  } catch {
    // ambientes sem History API gravavel: segue sem atualizar a URL
  }
}

function scheduleUrlWrite(map) {
  clearTimeout(timers.get(map));
  timers.set(map, setTimeout(() => writeUrl(map), URL_DEBOUNCE_MS));
}

// Atualiza camadas/filtros guardados e regrava a URL (usado por main.js).
export function setAppState(map, state) {
  appStates.set(map, state);
  scheduleUrlWrite(map);
}

// (Re)cria o controle de atribuicao com o texto das fontes dos dados. `html` ja vem
// escapado (buildAttribution em inspector.js): o MapLibre insere como HTML.
const attributionControls = new WeakMap();

export function setDataAttribution(map, html) {
  const old = attributionControls.get(map);
  if (old) map.removeControl(old);
  const ctrl = new maplibregl.AttributionControl({ compact: false, customAttribution: html });
  attributionControls.set(map, ctrl);
  map.addControl(ctrl, 'bottom-right');
}

export function createMap(container, state) {
  const map = new maplibregl.Map({
    container,
    style: baseStyle(),
    center: [state.lng, state.lat],
    zoom: state.zoom,
    minZoom: 0,
    maxZoom: 22,
    attributionControl: false,
    hash: false,
  });
  appStates.set(map, state);

  map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-right');
  map.addControl(new maplibregl.ScaleControl({ unit: 'metric' }), 'bottom-left');
  map.addControl(new CoordsControl(), 'bottom-left');
  setDataAttribution(map, ATTRIBUTION_FALLBACK);

  map.on('style.load', () => map.setProjection({ type: 'globe' }));
  map.on('moveend', () => scheduleUrlWrite(map));
  return map;
}
