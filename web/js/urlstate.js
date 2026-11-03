// Estado do app serializado no hash da URL. Modulo puro (sem DOM, sem maplibre).
import { LAYER_IDS } from './layer-defs.js';

export const ZOOM_MIN = 0;
export const ZOOM_MAX = 22;

export const DEFAULT_STATE = Object.freeze({
  lng: 0,
  lat: 20,
  zoom: 1.5,
  layers: ['tectonic_zones', 'samples', 'volcanoes'],
  filters: Object.freeze({
    classes: [],
    rock: null,
    sources: [],
    coordSource: null,
    lithClass: null,
  }),
});

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
const round = (v, n) => Number(v.toFixed(n));

function num(raw, fallback, lo, hi) {
  if (raw === null || raw.trim() === '') return fallback;
  const v = Number(raw);
  return Number.isFinite(v) ? clamp(v, lo, hi) : fallback;
}

function defaults() {
  return {
    lng: DEFAULT_STATE.lng,
    lat: DEFAULT_STATE.lat,
    zoom: DEFAULT_STATE.zoom,
    layers: [...DEFAULT_STATE.layers],
    filters: { classes: [], rock: null, sources: [], coordSource: null, lithClass: null },
  };
}

export function encodeState(state) {
  const p = new URLSearchParams();
  p.set('lng', String(round(clamp(state.lng, -180, 180), 4)));
  p.set('lat', String(round(clamp(state.lat, -90, 90), 4)));
  p.set('zoom', String(round(clamp(state.zoom, ZOOM_MIN, ZOOM_MAX), 2)));
  p.set('layers', state.layers.filter((id) => LAYER_IDS.includes(id)).join(','));
  const f = state.filters ?? {};
  for (const c of f.classes ?? []) p.append('class', c);
  if (f.rock != null) p.set('rock', f.rock);
  for (const s of f.sources ?? []) p.append('source', s);
  if (f.coordSource != null) p.set('coord', f.coordSource);
  if (f.lithClass != null) p.set('lith', f.lithClass);
  return p.toString();
}

export function decodeState(hash) {
  const out = defaults();
  if (typeof hash !== 'string') return out;
  let p;
  try {
    p = new URLSearchParams(hash.replace(/^#/, ''));
  } catch {
    return out;
  }
  out.lng = num(p.get('lng'), out.lng, -180, 180);
  out.lat = num(p.get('lat'), out.lat, -90, 90);
  out.zoom = num(p.get('zoom'), out.zoom, ZOOM_MIN, ZOOM_MAX);
  if (p.has('layers')) {
    const ids = p.get('layers').split(',').filter((id) => LAYER_IDS.includes(id));
    out.layers = [...new Set(ids)];
  }
  out.filters.classes = p.getAll('class');
  out.filters.rock = p.get('rock');
  out.filters.sources = p.getAll('source');
  out.filters.coordSource = p.get('coord');
  out.filters.lithClass = p.get('lith');
  return out;
}
