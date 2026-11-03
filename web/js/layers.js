// Painel de camadas: liga/desliga, opacidade, ordem, legenda e fundo do mapa.
//
// Convencao para a Tarefa 11: as camadas MapLibre de uma camada logica `X` tem id `X`
// ou `X:alguma-coisa` (ex.: `samples:clusters`). O painel age sobre todas elas e nao
// falha se ainda nao existirem. Cada item tem um espaco para legenda:
// `[data-legend-for="X"]`.
import { LAYER_DEFS, LAYER_IDS, moveItem } from './layer-defs.js';
import { BASEMAPS, availableBasemaps, applyBasemap } from './basemaps.js';

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
    onChange({ ...state, layers: currentLayers() });
  }

  // Cada item e criado uma unica vez; reordenar so reposiciona os nos (nunca recria),
  // assim foco e conteudo das legendas sobrevivem.
  const items = new Map();

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

    li.append(head, opacity, legend);
    items.set(id, { li, up, down });
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
}
