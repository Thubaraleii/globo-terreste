// Camadas de dados no mapa: fontes, estilos, legendas, filtro das amostras e falhas.
// Usa os globos `maplibregl` e `pmtiles` (web/vendor).
import { buildSources, buildLayers, legendItems, legendNote } from './layerstyles.js';
import { LAYER_IDS } from './layer-defs.js';
import { buildSampleFilter } from './filters.js';

let protocolRegistered = false;
const sampleFilters = new WeakMap();

function registerPmtiles() {
  if (protocolRegistered) return;
  const protocol = new pmtiles.Protocol();
  maplibregl.addProtocol('pmtiles', protocol.tile);
  protocolRegistered = true;
}

// Filtro das amostras (as duas camadas). Guarda o valor para camadas ainda nao criadas.
export function applySampleFilter(map, filters) {
  const expr = buildSampleFilter(filters);
  sampleFilters.set(map, expr);
  for (const id of ['samples:density', 'samples:points']) {
    if (map.getLayer(id)) map.setFilter(id, expr);
  }
}

function swatch(item) {
  const el = document.createElement('span');
  el.className = `legend-swatch legend-${item.shape}`;
  el.style.setProperty('--swatch', item.color);
  el.setAttribute('aria-hidden', 'true');
  return el;
}

// Preenche o espaco de legenda de cada camada, uma unica vez (textContent apenas).
export function fillLegends(root = document) {
  for (const id of LAYER_IDS) {
    const slot = root.querySelector(`[data-legend-for="${id}"]`);
    if (!slot || slot.childElementCount > 0) continue;
    const note = legendNote(id);
    if (note) {
      const p = document.createElement('p');
      p.className = 'legend-note';
      p.textContent = note;
      slot.append(p);
    }
    const list = document.createElement('ul');
    list.className = 'legend-list';
    for (const item of legendItems(id)) {
      const li = document.createElement('li');
      const label = document.createElement('span');
      label.textContent = item.label;
      li.append(swatch(item), label);
      list.append(li);
    }
    slot.append(list);
  }
}

// Adiciona fontes e camadas. `base` e a pasta dos dados (relativa a pagina).
// `onError(layerId, err)` e chamado uma vez por camada que nao carregar; as demais seguem.
// `opts.skip`: ids de camadas logicas que nao devem ser criadas (sem os dados publicados).
const isSkipped = (id, skip) => skip.some((s) => id === s || id.startsWith(`${s}:`));

export function addDataLayers(map, base, onError, opts = {}) {
  registerPmtiles();
  const skip = opts.skip ?? [];
  const absBase = new URL(base, document.baseURI).href;
  const failed = new Set();

  map.on('error', (e) => {
    const sourceId = e?.sourceId;
    if (!sourceId || !LAYER_IDS.includes(sourceId) || failed.has(sourceId)) return;
    failed.add(sourceId);
    onError(sourceId, e.error instanceof Error ? e.error : new Error(String(e.error ?? 'erro')));
  });

  const add = () => {
    for (const [id, spec] of Object.entries(buildSources(absBase))) {
      if (!isSkipped(id, skip) && !map.getSource(id)) map.addSource(id, spec);
    }
    for (const layer of buildLayers(sampleFilters.get(map) ?? null)) {
      if (!isSkipped(layer.id, skip) && !map.getLayer(layer.id)) map.addLayer(layer);
    }
    fillLegends();
  };
  // getStyle() so existe depois do 'style.load' (isStyleLoaded() tambem fica falso enquanto
  // tiles carregam, e o evento ja teria passado se a chamada for assincrona)
  if (map.getStyle()) add();
  else map.once('style.load', add);
}
