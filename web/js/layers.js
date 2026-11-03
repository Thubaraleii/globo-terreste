// Painel de camadas: liga/desliga, opacidade, ordem, legenda e fundo do mapa.
//
// Convencao para a Tarefa 11: as camadas MapLibre de uma camada logica `X` tem id `X`
// ou `X:alguma-coisa` (ex.: `samples:clusters`). O painel age sobre todas elas e nao
// falha se ainda nao existirem. Cada item tem um espaco para legenda:
// `[data-legend-for="X"]`.
import { LAYER_DEFS, LAYER_IDS } from './layer-defs.js';
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

  function render() {
    list.replaceChildren();
    // topo da pilha primeiro
    [...order].reverse().forEach((id) => {
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
        const i = order.indexOf(id);
        const j = i + delta;
        if (j < 0 || j >= order.length) return;
        [order[i], order[j]] = [order[j], order[i]];
        applyToMap();
        render();
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
      const pos = order.indexOf(id);
      const up = mkBtn('▲', 'Subir camada', +1);
      const down = mkBtn('▼', 'Descer camada', -1);
      up.disabled = pos === order.length - 1;
      down.disabled = pos === 0;
      head.append(label, up, down);

      const opacity = document.createElement('input');
      opacity.type = 'range';
      opacity.min = '0';
      opacity.max = '1';
      opacity.step = '0.05';
      opacity.value = String(touchedOpacity.get(id) ?? 1);
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
      list.append(li);
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

  render();
  // camadas adicionadas depois (Tarefa 11) herdam visibilidade/opacidade/ordem
  map.on('styledata', () => {
    applyToMap();
  });
  if (map.getStyle()) applyToMap();
}
