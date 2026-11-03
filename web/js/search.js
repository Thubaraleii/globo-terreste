// Busca local: nomes de vulcoes e zonas, e coordenadas digitadas. Modulo puro.
// Sem geocodificador externo.

// Numero decimal simples (ponto como separador decimal; sem expoente, sem hex).
const NUM = String.raw`[+-]?(?:\d+(?:\.\d*)?|\.\d+)`;
const COORDS = new RegExp(`^\\s*(${NUM})\\s*(?:,|\\s)\\s*(${NUM})\\s*$`);

// "lat, lon" ou "lat lon" em graus decimais -> { lng, lat }, ou null.
export function parseCoords(text) {
  if (typeof text !== 'string') return null;
  const m = COORDS.exec(text);
  if (!m) return null;
  const lat = Number(m[1]);
  const lng = Number(m[2]);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
  if (lat < -90 || lat > 90 || lng < -180 || lng > 180) return null;
  return { lng, lat };
}

// Minusculas, sem acentos (NFD sem marcas combinantes), espacos aparados.
export function normalize(s) {
  return String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
}

// Prefixo antes de substring; dentro de cada grupo mantem a ordem de entrada.
export function searchIndex(items, query, limit = 8) {
  if (!Array.isArray(items) || typeof query !== 'string') return [];
  const q = normalize(query);
  if (q === '') return [];
  const prefix = [];
  const inner = [];
  for (const item of items) {
    if (typeof item?.name !== 'string') continue;
    const n = normalize(item.name);
    if (n.startsWith(q)) prefix.push(item);
    else if (n.includes(q)) inner.push(item);
  }
  return [...prefix, ...inner].slice(0, limit);
}

// Caixa [oeste, sul, leste, norte] de qualquer geometria GeoJSON; null se vazia.
function bboxOf(geometry) {
  let box = null;
  const visit = (c) => {
    if (!Array.isArray(c)) return;
    if (typeof c[0] === 'number' && typeof c[1] === 'number') {
      if (!Number.isFinite(c[0]) || !Number.isFinite(c[1])) return;
      box = box
        ? [Math.min(box[0], c[0]), Math.min(box[1], c[1]), Math.max(box[2], c[0]), Math.max(box[3], c[1])]
        : [c[0], c[1], c[0], c[1]];
      return;
    }
    c.forEach(visit);
  };
  if (geometry?.type === 'GeometryCollection') geometry.geometries?.forEach((g) => visit(g?.coordinates));
  else visit(geometry?.coordinates);
  return box;
}

function featuresOf(fc) {
  return Array.isArray(fc?.features) ? fc.features : [];
}

// Itens de busca a partir dos GeoJSON de vulcoes e zonas tectonicas.
// Cada item: { name, kind, lng, lat, bbox, layer, props }.
export function buildSearchItems(volcanoes, zones) {
  const out = [];
  const add = (f, layer, kind) => {
    const props = f?.properties ?? {};
    if (typeof props.name !== 'string' || props.name.trim() === '') return;
    const bbox = bboxOf(f?.geometry);
    if (!bbox) return;
    out.push({
      name: props.name,
      kind,
      lng: (bbox[0] + bbox[2]) / 2,
      lat: (bbox[1] + bbox[3]) / 2,
      bbox,
      layer,
      props,
    });
  };
  for (const f of featuresOf(volcanoes)) {
    add(f, 'volcanoes', f?.properties?.kind === 'hotspot' ? 'hotspot' : 'volcano');
  }
  for (const f of featuresOf(zones)) add(f, 'tectonic_zones', 'tectonic_zone');
  return out;
}
