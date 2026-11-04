// Nomes das placas como rotulos DOM (maplibregl.Marker), sem camada de texto do estilo:
// o estilo nao tem servidor de glifos e nao vamos depender de um servico externo de fontes.
// As partes puras (buildLabelSpecs, labelsVisible) nao tocam o DOM nem o maplibre.

// Acima deste zoom os rotulos somem (os limites ja contam a historia e o texto atrapalha).
export const LABEL_MAX_ZOOM = 6;

const isNum = (v) => typeof v === 'number' && Number.isFinite(v);

// plate_labels.geojson -> [{ code, name, lng, lat, area }]. Um por codigo (vale o primeiro);
// nome ausente cai no codigo; geometria que nao e Point valido (lon/lat em faixa) e descartada.
export function buildLabelSpecs(fc) {
  const out = [];
  const seen = new Set();
  const features = Array.isArray(fc?.features) ? fc.features : [];
  for (const f of features) {
    const code = typeof f?.properties?.code === 'string' ? f.properties.code.trim() : '';
    const c = f?.geometry?.type === 'Point' ? f.geometry.coordinates : null;
    if (code === '' || seen.has(code) || !Array.isArray(c)) continue;
    const [lng, lat] = c;
    if (!isNum(lng) || !isNum(lat) || Math.abs(lng) > 180 || Math.abs(lat) > 90) continue;
    const name = typeof f.properties.name === 'string' && f.properties.name.trim() !== ''
      ? f.properties.name.trim() : code;
    seen.add(code);
    out.push({ code, name, lng, lat, area: isNum(f.properties.area_km2) ? f.properties.area_km2 : null });
  }
  return out;
}

// Zoom a partir do qual o nome de uma placa aparece, pela area (km2): as dez maiores desde o
// globo inteiro; as pequenas so ao aproximar, para os nomes nao se sobreporem.
export function labelMinZoom(areaKm2) {
  if (!isNum(areaKm2)) return 3.5;
  if (areaKm2 >= 1e7) return 0;
  if (areaKm2 >= 3e6) return 2.5;
  if (areaKm2 >= 1e6) return 3.5;
  if (areaKm2 >= 3e5) return 4.5;
  return 5.5;
}

export function labelsVisible(layerOn, zoom, minZoom = 0) {
  return Boolean(layerOn) && isNum(zoom) && zoom >= minZoom && zoom <= LABEL_MAX_ZOOM;
}

// Cria os marcadores uma unica vez. `failed()` tambem desliga tudo (dados que nao carregaram).
// Devolve { update({ layerOn, opacity }), destroy() }. Elementos sem eventos de ponteiro:
// nunca interceptam cliques. Rotulos do lado oculto do globo ficam invisiveis
// (`opacityWhenCovered: 0`).
export function mountPlateLabels(map, specs) {
  const markers = specs.map((s) => {
    const el = document.createElement('div');
    el.className = 'plate-label';
    el.textContent = s.name;
    el.setAttribute('aria-hidden', 'true');
    const marker = new maplibregl.Marker({ element: el, opacity: '1', opacityWhenCovered: '0' })
      .setLngLat([s.lng, s.lat])
      .addTo(map);
    return { el, marker, minZoom: labelMinZoom(s.area) };
  });
  const state = { layerOn: false, opacity: 1, disabled: false };

  function apply() {
    const zoom = map.getZoom();
    const on = !state.disabled && state.layerOn;
    for (const { el, marker, minZoom } of markers) {
      el.classList.toggle('is-off', !labelsVisible(on, zoom, minZoom));
      marker.setOpacity(String(state.opacity), '0');
    }
  }
  map.on('zoom', apply);

  return {
    update(next) {
      if (typeof next.layerOn === 'boolean') state.layerOn = next.layerOn;
      if (isNum(next.opacity)) state.opacity = Math.min(1, Math.max(0, next.opacity));
      apply();
    },
    disable() {
      state.disabled = true;
      apply();
    },
    get count() {
      return markers.length;
    },
    destroy() {
      map.off('zoom', apply);
      for (const { marker } of markers) marker.remove();
    },
  };
}
