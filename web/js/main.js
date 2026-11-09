import { decodeState } from './urlstate.js';
import { createMap, setAppState, setDataAttribution } from './map.js';
import { mountLayerPanel } from './layers.js';
import { addDataLayers, applySampleFilter } from './datalayers.js';
import {
  renderSample, renderUnit, renderMacrostratUnit, renderVolcano, renderZone, renderPlateBoundary, renderPaleoSample, renderPaleoLineament, indexSources, buildAttribution,
} from './inspector.js';
import { buildLabelSpecs, mountPlateLabels } from './platelabels.js';
import { mountPaleo } from './paleo.js';
import { mountSpin } from './spin.js';
import { parseCoords, searchIndex, buildSearchItems } from './search.js';

// Pasta dos dados (relativa a pagina); sem sobrescrita por URL.
const DATA_BASE = 'data/';
const WARNING = 'Camada indisponível: não foi possível carregar os dados.';

const state = decodeState(window.location.hash);
const map = createMap(document.getElementById('map'), state);

// Rotulos das placas (DOM): seguem a visibilidade e a opacidade da camada `plates`.
let plateLabels = null;
const platesView = { layerOn: false, opacity: 1 };

const layerPanel = mountLayerPanel(map, state, (next) => {
  applySampleFilter(map, next.filters);
  setAppState(map, next);
}, {
  onLayerApply(id, visible, opacity) {
    if (id !== 'plates') return;
    platesView.layerOn = visible;
    platesView.opacity = opacity;
    plateLabels?.update(platesView);
  },
});

// Falha de uma camada: avisa uma vez por camada; sem os limites das placas, sem os nomes.
const failedLayers = new Set();
function layerFailed(layerId, err) {
  if (failedLayers.has(layerId)) return;
  failedLayers.add(layerId);
  console.warn(`Falha ao carregar a camada ${layerId}:`, err);
  const slot = document.querySelector(`[data-warning-for="${layerId}"]`);
  if (slot) slot.textContent = WARNING;
  if (layerId === 'plates') plateLabels?.disable();
}

applySampleFilter(map, state.filters);
mountSpin(map, document.getElementById('spin-toggle'));

// Camadas que dependem de arquivos so locais (nao publicados por licenca): se o arquivo
// nao existe, a camada some do painel e nao e criada (sem erros 404 nem avisos).
const LOCAL_ONLY = { samples: 'samples.pmtiles', geo_units: 'geo_units.pmtiles' };
const missingLayers = new Set();

async function probeLocalOnly() {
  await Promise.all(Object.entries(LOCAL_ONLY).map(async ([layer, file]) => {
    try {
      const res = await fetch(`${DATA_BASE}${file}`, { method: 'HEAD' });
      if (!res.ok) missingLayers.add(layer);
    } catch {
      missingLayers.add(layer);
    }
  }));
  for (const id of missingLayers) {
    document.querySelector(`[data-layer-id="${id}"]`)?.setAttribute('hidden', '');
  }
}

const probed = probeLocalOnly();
probed.then(() => {
  addDataLayers(map, DATA_BASE, layerFailed, { skip: [...missingLayers] });
  // Paleogeografia (opcional: so aparece se data/paleo/index.json existir).
  mountPaleo(map, DATA_BASE, document.getElementById('paleo-bar'), {
    onSelectSample: (p) => openDetails(() => renderPaleoSample(p, { source: sourceOf(p) })),
    onSelectLineament: (p) => openDetails(() => renderPaleoLineament(p)),
  });
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

async function fetchJson(name) {
  const res = await fetch(`${DATA_BASE}${name}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

// Nomes das placas: criados uma vez a partir de plate_labels.geojson.
fetchJson('plate_labels.geojson')
  .then((fc) => {
    const specs = buildLabelSpecs(fc);
    if (specs.length === 0) throw new Error('plate_labels.geojson sem rótulos válidos');
    plateLabels = mountPlateLabels(map, specs);
    if (failedLayers.has('plates')) plateLabels.disable();
    plateLabels.update(platesView);
  })
  .catch((err) => layerFailed('plates', err));

// ---------------------------------------------------------------------------
// Fontes (sources.json): carregadas uma vez; se falhar, os detalhes da fonte
// aparecem como "não informado" e o resto segue.
let sources = new Map();
const sourceOf = (props) => sources.get(props?.source_id);

// ---------------------------------------------------------------------------
// Painel de detalhes. Os renderizadores de inspector.js escapam todo dado.
const details = document.getElementById('details-panel');
const detailsBody = details.querySelector('.details-body');
const detailsStatus = details.querySelector('.details-status');
let current = null; // { render, wire } do item aberto

function paint() {
  detailsBody.innerHTML = current.render();
  current.wire?.(detailsBody);
}

function openDetails(render, wire) {
  current = { render, wire };
  detailsStatus.textContent = '';
  paint();
  details.hidden = false;
  details.scrollTop = 0;
  detailsBody.querySelector('.details-heading')?.focus();
}

function closeDetails() {
  if (details.hidden) return;
  details.hidden = true;
  detailsBody.textContent = '';
  detailsStatus.textContent = '';
  current = null;
  map.getCanvas().focus();
}

details.querySelector('.details-close').addEventListener('click', closeDetails);

// Fontes de camadas ausentes (GEOROC das amostras, GLiM das unidades) nao entram na atribuicao.
const hiddenSource = (id) => (missingLayers.has('samples') && String(id).startsWith('georoc'))
  || (missingLayers.has('geo_units') && id === 'glim');

Promise.all([fetchJson('sources.json'), probed])
  .then(([all]) => {
    const list = Array.isArray(all) ? all.filter((s) => !hiddenSource(s?.source_id)) : all;
    sources = indexSources(list);
    layerPanel.setSources(list);
    setDataAttribution(map, buildAttribution(list));
    if (current) {
      // refaz o painel aberto com os dados da fonte, mantendo o foco no titulo
      const hadFocus = detailsBody.contains(document.activeElement);
      paint();
      if (hadFocus) detailsBody.querySelector('.details-heading')?.focus();
    }
  })
  .catch((err) => {
    console.warn('Fontes indisponíveis (sources.json):', err);
    // sem sources.json: filtro por fonte oculto e descartado; atribuicao generica
    layerPanel.setSources(null);
  });

function openUnit(props) {
  openDetails(
    () => renderUnit(props, props.sample_count, { source: sourceOf(props) }),
    (root) => {
      root.querySelector('[data-action="filter-lith"]')?.addEventListener('click', () => {
        layerPanel.setLithClass(props.lith_class);
        detailsStatus.textContent = 'Filtro aplicado: as amostras mostradas são desta litologia. '
          + 'Use “Limpar filtro de litologia” no painel de camadas para remover.';
      });
    },
  );
}

// Unidade que contem o ponto (camada geo_units visivel), para a litologia original.
function unitAt(point, unitId) {
  if (unitId == null || !point || !map.getLayer('geo_units')) return null;
  const hit = map.queryRenderedFeatures(point, { layers: ['geo_units'] })
    .find((f) => String(f.properties?.unit_id) === String(unitId));
  return hit?.properties ?? null;
}

function openSample(props, point) {
  const unit = unitAt(point, props.unit_id);
  openDetails(() => renderSample(props, {
    source: sourceOf(props),
    unitLithOriginal: unit?.lith_original,
    unitSource: unit ? sourceOf(unit) : undefined,
  }));
}

function openFeature(layerId, props, point) {
  const p = props ?? {};
  if (layerId === 'samples:points') openSample(p, point);
  else if (layerId === 'geo_units') openUnit(p);
  else if (layerId === 'macrostrat') openDetails(() => renderMacrostratUnit(p));
  else if (layerId === 'volcanoes') openDetails(() => renderVolcano(p, { source: sourceOf(p) }));
  else if (layerId === 'plates') openDetails(() => renderPlateBoundary(p, { source: sourceOf(p) }));
  else if (layerId === 'tectonic_zones') openDetails(() => renderZone(p, { source: sourceOf(p) }));
}

// ---------------------------------------------------------------------------
// Clique no mapa: a feicao de cima entre as camadas interativas.
const CLICK_LAYERS = ['samples:points', 'volcanoes', 'tectonic_zones', 'plates', 'geo_units', 'macrostrat'];
const HIT_PAD = 4; // px de folga (linhas finas)

function featuresAt(point) {
  const layers = CLICK_LAYERS.filter((id) => map.getLayer(id));
  if (layers.length === 0) return [];
  const box = [[point.x - HIT_PAD, point.y - HIT_PAD], [point.x + HIT_PAD, point.y + HIT_PAD]];
  return map.queryRenderedFeatures(box, { layers });
}

map.on('click', (e) => {
  const f = featuresAt(e.point)[0];
  if (f) openFeature(f.layer.id, f.properties, e.point);
});

map.on('mousemove', (e) => {
  map.getCanvas().style.cursor = featuresAt(e.point).length ? 'pointer' : '';
});

// ---------------------------------------------------------------------------
// Busca: nomes de vulcoes e zonas (GeoJSON) e coordenadas "lat, lon".
const searchInput = document.getElementById('search-input');
const searchResults = document.getElementById('search-results');
const searchStatus = document.getElementById('search-status');
const KIND_TEXT = { volcano: 'Vulcão', hotspot: 'Hotspot', tectonic_zone: 'Zona tectônica' };
const FLY_ZOOM = { volcanoes: 7, tectonic_zones: 4 };
let searchItems = [];

Promise.allSettled([fetchJson('volcanoes.geojson'), fetchJson('tectonic_zones.geojson')])
  .then(([v, z]) => {
    searchItems = buildSearchItems(v.value ?? null, z.value ?? null);
  });

function closeResults() {
  searchResults.hidden = true;
  searchResults.textContent = '';
  searchInput.setAttribute('aria-expanded', 'false');
}

function choose(item) {
  closeResults();
  searchInput.value = item.name;
  searchStatus.textContent = '';
  map.flyTo({ center: [item.lng, item.lat], zoom: Math.max(map.getZoom(), FLY_ZOOM[item.layer] ?? 5) });
  openFeature(item.layer, item.props, null);
}

function showResults() {
  const coords = parseCoords(searchInput.value);
  const found = searchIndex(searchItems, searchInput.value);
  searchResults.textContent = '';
  for (const item of found) {
    const li = document.createElement('li');
    const btn = document.createElement('button');
    btn.type = 'button';
    const kind = document.createElement('span');
    kind.className = 'search-kind';
    kind.textContent = ` — ${KIND_TEXT[item.kind] ?? ''}`;
    btn.append(document.createTextNode(item.name), kind);
    btn.addEventListener('click', () => choose(item));
    li.append(btn);
    searchResults.append(li);
  }
  const open = found.length > 0;
  searchResults.hidden = !open;
  searchInput.setAttribute('aria-expanded', String(open));
  if (coords) searchStatus.textContent = 'Pressione Enter para ir até essas coordenadas.';
  else if (searchInput.value.trim() !== '' && !open) searchStatus.textContent = 'Nenhum resultado.';
  else searchStatus.textContent = '';
}

searchInput.addEventListener('input', showResults);

searchInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    e.preventDefault();
    const coords = parseCoords(searchInput.value);
    if (coords) {
      closeResults();
      map.flyTo({ center: [coords.lng, coords.lat], zoom: Math.max(map.getZoom(), 7) });
      searchStatus.textContent = `Indo para ${coords.lat}, ${coords.lng}.`;
      return;
    }
    const first = searchResults.querySelector('button');
    if (first) first.click();
  } else if (e.key === 'ArrowDown') {
    const first = searchResults.querySelector('button');
    if (first) {
      e.preventDefault();
      first.focus();
    }
  } else if (e.key === 'Escape' && !searchResults.hidden) {
    e.preventDefault();
    e.stopPropagation();
    closeResults();
  }
});

searchResults.addEventListener('keydown', (e) => {
  const buttons = [...searchResults.querySelectorAll('button')];
  const i = buttons.indexOf(document.activeElement);
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
    e.preventDefault();
    const j = i + (e.key === 'ArrowDown' ? 1 : -1);
    if (j < 0) searchInput.focus();
    else buttons[Math.min(j, buttons.length - 1)]?.focus();
  } else if (e.key === 'Escape') {
    e.preventDefault();
    e.stopPropagation();
    closeResults();
    searchInput.focus();
  }
});

// Fecha a lista ao clicar fora da busca.
document.addEventListener('click', (e) => {
  if (!document.getElementById('search').contains(e.target)) closeResults();
});

// Escape fecha o painel de detalhes.
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !details.hidden) closeDetails();
});

// Atalho para depuracao e para os testes de fumaca.
if (['127.0.0.1', 'localhost'].includes(window.location.hostname)) window.geoworldMap = map;
