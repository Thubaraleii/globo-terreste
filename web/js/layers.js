// Painel de camadas: liga/desliga, opacidade, ordem, legenda e fundo do mapa.
//
// Convencao para a Tarefa 11: as camadas MapLibre de uma camada logica `X` tem id `X`
// ou `X:alguma-coisa` (ex.: `samples:clusters`). O painel age sobre todas elas e nao
// falha se ainda nao existirem. Cada item tem um espaco para legenda:
// `[data-legend-for="X"]`.
import { LAYER_DEFS, LAYER_IDS, moveItem, raiseAbove } from './layer-defs.js';
import { BASEMAPS, DEFAULT_BASEMAP_ID, availableBasemaps, applyBasemap } from './basemaps.js';
import { LITH_COLORS, ROCK_CLASS_COLORS } from './layerstyles.js';
import { sourceOptions } from './inspector.js';

const LITH_LABELS = new Map(LITH_COLORS.map(([value, , label]) => [value, label]));
const ROCK_CLASSES = new Set(ROCK_CLASS_COLORS.map(([value]) => value));

export { LAYER_DEFS };

const OPACITY_PROPS = {
  fill: ['fill-opacity'],
  line: ['line-opacity'],
  circle: ['circle-opacity', 'circle-stroke-opacity'],
  heatmap: ['heatmap-opacity'],
  raster: ['raster-opacity'],
  symbol: ['icon-opacity', 'text-opacity'],
  'fill-extrusion': ['fill-extrusion-opacity'],
};

export function mapLayerIds(map, id) {
  const layers = map.getStyle()?.layers ?? [];
  return layers.filter((l) => l.id === id || l.id.startsWith(`${id}:`)).map((l) => l.id);
}

// Ordem de empilhamento inicial (de baixo para cima): ordem das definicoes, com as
// camadas ativas na ordem que veio da URL.
function initialOrder(activeLayers) {
  const order = LAYER_IDS.slice();
  const slots = order.map((id, i) => (activeLayers.includes(id) ? i : -1)).filter((i) => i >= 0);
  const wanted = activeLayers.filter((id) => LAYER_IDS.includes(id));
  slots.forEach((slot, k) => {
    order[slot] = wanted[k];
  });
  return order;
}

export function mountLayerPanel(map, state, onChange) {
  const root = document.getElementById('layer-panel');
  const order = initialOrder(state.layers);
  const enabled = new Set(state.layers);
  const touchedOpacity = new Map(); // so aplica opacidade onde o usuario mexeu
  const filters = {
    classes: [...(state.filters?.classes ?? [])],
    rock: state.filters?.rock ?? null,
    sources: [...(state.filters?.sources ?? [])],
    coordSource: state.filters?.coordSource ?? null,
    lithClass: state.filters?.lithClass ?? null,
  };
  const list = root.querySelector('.layer-list');

  function currentLayers() {
    return order.filter((id) => enabled.has(id));
  }

  function applyToMap() {
    if (!map.getStyle()) return;
    applyOrder();
    for (const id of order) {
      for (const lid of mapLayerIds(map, id)) {
        const visibility = enabled.has(id) ? 'visible' : 'none';
        if (map.getLayoutProperty(lid, 'visibility') !== visibility) {
          map.setLayoutProperty(lid, 'visibility', visibility);
        }
        if (touchedOpacity.has(id)) {
          const type = map.getLayer(lid).type;
          for (const prop of OPACITY_PROPS[type] ?? []) {
            if (map.getPaintProperty(lid, prop) !== touchedOpacity.get(id)) {
              map.setPaintProperty(lid, prop, touchedOpacity.get(id));
            }
          }
        }
      }
    }
  }

  // So move se a ordem real diferir da desejada (mover dispara 'styledata').
  function applyOrder() {
    const wanted = order.flatMap((id) => mapLayerIds(map, id));
    const managed = new Set(wanted);
    const actual = map.getStyle().layers.map((l) => l.id).filter((lid) => managed.has(lid));
    if (wanted.every((lid, i) => lid === actual[i])) return;
    for (const lid of wanted) map.moveLayer(lid);
  }

  function emit() {
    onChange({ ...state, layers: currentLayers(), filters: { ...filters, classes: [...filters.classes], sources: [...filters.sources] } });
  }

  // Cada item e criado uma unica vez; reordenar so reposiciona os nos (nunca recria),
  // assim foco e conteudo das legendas sobrevivem.
  const items = new Map();

  // Filtro por litologia da unidade: definido pelo painel de detalhes ("Ver amostras
  // desta litologia"); aqui so aparece o valor ativo e o botao para limpar.
  const lithRow = document.createElement('div');
  lithRow.className = 'filter-lith';
  const lithText = document.createElement('span');
  lithText.setAttribute('role', 'status');
  const lithClear = document.createElement('button');
  lithClear.type = 'button';
  lithClear.className = 'text-btn';
  lithClear.textContent = 'Limpar filtro de litologia';
  lithClear.addEventListener('click', () => setLithClass(null));
  lithRow.append(lithText, lithClear);

  function renderLith() {
    const v = filters.lithClass;
    lithRow.hidden = v == null;
    lithText.textContent = v == null ? '' : `Litologia da unidade: ${LITH_LABELS.get(v) ?? v}`;
  }

  // Define (ou limpa, com null) o filtro por litologia. Ao definir, liga as amostras
  // e as coloca acima das unidades geologicas, para os pontos ficarem visiveis.
  function setLithClass(value) {
    filters.lithClass = typeof value === 'string' && value !== '' ? value : null;
    if (filters.lithClass !== null) {
      enabled.add('samples');
      items.get('samples').cb.checked = true;
      order.splice(0, order.length, ...raiseAbove(order, 'samples', 'geo_units'));
      layout();
    }
    applyToMap();
    renderLith();
    emit();
  }

  // Filtro por fonte: as caixas so existem depois que sources.json carrega
  // (setSources); sem sources.json o grupo fica oculto.
  const sourceBox = document.createElement('fieldset');
  sourceBox.className = 'filter-sources';
  sourceBox.hidden = true;
  const sourceLegend = document.createElement('legend');
  sourceLegend.textContent = 'Fonte';
  sourceBox.append(sourceLegend);
  const sourceChecks = new Map(); // source_id -> checkbox
  let sourcesKnown = false;

  // Recebe a lista de sources.json (ou null se falhou). Monta as caixas uma unica vez
  // e descarta do filtro as fontes que nao existem nela.
  function setSources(list) {
    if (sourcesKnown) return;
    sourcesKnown = true;
    const options = sourceOptions(list);
    for (const { value, label: text } of options) {
      const label = document.createElement('label');
      label.className = 'filter-check';
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.addEventListener('change', () => {
        filters.sources = cb.checked
          ? [...new Set([...filters.sources, value])]
          : filters.sources.filter((s) => s !== value);
        emit();
      });
      label.append(cb, document.createTextNode(` ${text}`));
      sourceChecks.set(value, cb);
      sourceBox.append(label);
    }
    sourceBox.hidden = options.length === 0;
    const valid = filters.sources.filter((s) => sourceChecks.has(s));
    const changed = valid.length !== filters.sources.length;
    filters.sources = [...new Set(valid)];
    renderFilterWidgets();
    if (changed) emit();
  }

  const classChecks = new Map(); // classe -> checkbox
  let rockInput;
  let coordSelect;

  // Sincroniza os controles com `filters`.
  function renderFilterWidgets() {
    for (const [value, cb] of classChecks) cb.checked = filters.classes.includes(value);
    for (const [value, cb] of sourceChecks) cb.checked = filters.sources.includes(value);
    if (rockInput) rockInput.value = filters.rock ?? '';
    if (coordSelect) coordSelect.value = filters.coordSource ?? '';
    renderLith();
  }

  // Limpa todos os filtros das amostras (classe, nome, fonte, coordenada, litologia).
  function clearFilters() {
    filters.classes = [];
    filters.rock = null;
    filters.sources = [];
    filters.coordSource = null;
    filters.lithClass = null;
    renderFilterWidgets();
    emit();
  }

  // Filtros das amostras: classe, nome da rocha, fonte e origem da coordenada.
  function buildSampleFilters() {
    const box = document.createElement('fieldset');
    box.className = 'layer-filters';
    const legend = document.createElement('legend');
    legend.textContent = 'Filtros das amostras';
    box.append(legend);

    filters.classes = filters.classes.filter((c) => ROCK_CLASSES.has(c));
    for (const [value, text] of [['mafic', 'Máfica'], ['ultramafic', 'Ultramáfica']]) {
      const label = document.createElement('label');
      label.className = 'filter-check';
      const cb = document.createElement('input');
      cb.type = 'checkbox';
      cb.checked = filters.classes.includes(value);
      cb.addEventListener('change', () => {
        filters.classes = cb.checked
          ? [...new Set([...filters.classes, value])]
          : filters.classes.filter((c) => c !== value);
        emit();
      });
      label.append(cb, document.createTextNode(` ${text}`));
      classChecks.set(value, cb);
      box.append(label);
    }

    const rockLabel = document.createElement('label');
    rockLabel.className = 'filter-field';
    rockLabel.append(document.createTextNode('Nome da rocha contém'));
    const rock = document.createElement('input');
    rock.type = 'search';
    rock.value = filters.rock ?? '';
    rock.autocomplete = 'off';
    rock.addEventListener('input', () => {
      filters.rock = rock.value === '' ? null : rock.value;
      emit();
    });
    rockLabel.append(rock);
    rockInput = rock;
    box.append(rockLabel, sourceBox);

    const coordLabel = document.createElement('label');
    coordLabel.className = 'filter-field';
    coordLabel.append(document.createTextNode('Origem da coordenada'));
    const coord = document.createElement('select');
    for (const [value, text] of [['', 'Todas'], ['reported', 'Reportada'], ['geocoded', 'Geocodificada']]) {
      coord.append(new Option(text, value));
    }
    coord.value = filters.coordSource ?? '';
    // valor sem opcao: o filtro tambem e descartado (controle e filtro sempre iguais)
    if (coord.value !== (filters.coordSource ?? '')) {
      coord.value = '';
      filters.coordSource = null;
    }
    coord.addEventListener('change', () => {
      filters.coordSource = coord.value === '' ? null : coord.value;
      emit();
    });
    coordLabel.append(coord);
    coordSelect = coord;

    const clear = document.createElement('button');
    clear.type = 'button';
    clear.className = 'text-btn filter-clear';
    clear.textContent = 'Limpar filtros';
    clear.addEventListener('click', clearFilters);

    box.append(coordLabel, lithRow, clear);
    renderLith();
    return box;
  }

  function buildItem(id) {
    const def = LAYER_DEFS.find((d) => d.id === id);
    const li = document.createElement('li');
    li.className = 'layer-item';
    li.dataset.layerId = id;

    const head = document.createElement('div');
    head.className = 'layer-head';

    const label = document.createElement('label');
    label.className = 'layer-toggle';
    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = enabled.has(id);
    cb.addEventListener('change', () => {
      if (cb.checked) enabled.add(id);
      else enabled.delete(id);
      applyToMap();
      emit();
    });
    label.append(cb, document.createTextNode(` ${def.label}`));

    const move = (delta) => {
      const next = moveItem(order, id, delta);
      if (next.every((x, i) => x === order[i])) return;
      order.splice(0, order.length, ...next);
      applyToMap();
      layout();
      // reposicionar o no pode tirar o foco: devolve ao mesmo botao (ou ao outro, na borda)
      const btn = delta > 0 ? up : down;
      (btn.disabled ? (delta > 0 ? down : up) : btn).focus();
      emit();
    };
    const mkBtn = (text, aria, delta) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'icon-btn';
      b.textContent = text;
      b.setAttribute('aria-label', `${aria}: ${def.label}`);
      b.addEventListener('click', () => move(delta));
      return b;
    };
    const up = mkBtn('▲', 'Subir camada', +1);
    const down = mkBtn('▼', 'Descer camada', -1);
    head.append(label, up, down);

    const opacity = document.createElement('input');
    opacity.type = 'range';
    opacity.min = '0';
    opacity.max = '1';
    opacity.step = '0.05';
    opacity.value = '1';
    opacity.className = 'layer-opacity';
    opacity.setAttribute('aria-label', `Opacidade: ${def.label}`);
    opacity.addEventListener('input', () => {
      touchedOpacity.set(id, Number(opacity.value));
      applyToMap();
    });

    const legend = document.createElement('div');
    legend.className = 'layer-legend';
    legend.dataset.legendFor = id;

    // aviso de falha de carga (preenchido por main.js via onError)
    const warning = document.createElement('p');
    warning.className = 'layer-warning';
    warning.dataset.warningFor = id;
    warning.setAttribute('role', 'status');

    li.append(head, opacity, legend, warning);
    if (id === 'samples') li.append(buildSampleFilters());
    items.set(id, { li, up, down, cb });
  }

  // Posiciona os itens existentes (topo da pilha primeiro) e atualiza os botoes.
  function layout() {
    [...order].reverse().forEach((id, k) => {
      const { li, up, down } = items.get(id);
      up.disabled = k === 0;
      down.disabled = k === order.length - 1;
      list.append(li); // append de no existente = mover
    });
  }

  // Fundo do mapa: so lista os que tem tiles (ou o liso).
  const choices = availableBasemaps();
  const sel = root.querySelector('.basemap-select');
  const basemapBox = root.querySelector('.basemap-box');
  if (sel && choices.length > 1) {
    for (const b of choices) sel.append(new Option(b.label, b.id));
    sel.addEventListener('change', () => {
      applyBasemap(map, BASEMAPS.find((b) => b.id === sel.value));
    });
    // fundo inicial (escolhido pelo usuario): aplica assim que o estilo existir
    const initial = choices.find((b) => b.id === DEFAULT_BASEMAP_ID);
    if (initial && initial.id !== sel.value) {
      sel.value = initial.id;
      const apply = () => applyBasemap(map, initial);
      if (map.getStyle()) apply();
      else map.once('style.load', apply);
    }
  } else if (basemapBox) {
    basemapBox.hidden = true;
  }

  for (const id of order) buildItem(id);
  layout();
  // camadas adicionadas depois (Tarefa 11) herdam visibilidade/opacidade/ordem
  map.on('styledata', () => {
    applyToMap();
  });
  if (map.getStyle()) applyToMap();
  return { setLithClass, setSources };
}
