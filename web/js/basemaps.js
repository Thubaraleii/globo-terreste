// Mapas-base. Estrutura de cada entrada: { id, label, tiles, attribution }.
//
// Somente "Fundo liso" (cor escura, sem tiles externos; campo `color`) esta habilitado.
// Para habilitar outro fundo, preencha `tiles` com a lista de URLs de tiles raster do
// provedor ESCOLHIDO (ex.: ['https://.../{z}/{x}/{y}.png']) e `attribution` com o texto
// exigido pelos termos de uso do provedor, que precisam ser confirmados antes.
// Entradas com `tiles: null` (e sem `color`) nao aparecem na interface.
// A atribuicao do fundo ativo e sempre exibida no mapa.
export const BASEMAPS = [
  { id: 'plain', label: 'Fundo liso', tiles: null, attribution: '', color: '#1b2a44' },
  { id: 'dark', label: 'Escuro', tiles: null, attribution: '' },
  { id: 'relief', label: 'Relevo', tiles: null, attribution: '' },
  { id: 'satellite', label: 'Satélite', tiles: null, attribution: '' },
];

const hasTiles = (b) => Array.isArray(b.tiles) && b.tiles.length > 0;

// Fundos selecionaveis: o liso e qualquer um com `tiles` preenchido.
export function availableBasemaps(list = BASEMAPS) {
  return list.filter((b) => b.color || hasTiles(b));
}

const BG_LAYER = 'basemap-bg';
const RASTER_ID = 'basemap-raster';

// Estilo inicial: globo com fundo liso.
export function baseStyle(color = BASEMAPS[0].color) {
  return {
    version: 8,
    projection: { type: 'globe' },
    sources: {},
    layers: [{ id: BG_LAYER, type: 'background', paint: { 'background-color': color } }],
  };
}

// Troca o fundo ativo.
export function applyBasemap(map, basemap) {
  if (map.getLayer(RASTER_ID)) map.removeLayer(RASTER_ID);
  if (map.getSource(RASTER_ID)) map.removeSource(RASTER_ID);
  if (basemap.color) map.setPaintProperty(BG_LAYER, 'background-color', basemap.color);
  if (hasTiles(basemap)) {
    map.addSource(RASTER_ID, {
      type: 'raster',
      tiles: basemap.tiles,
      tileSize: 256,
      attribution: basemap.attribution,
    });
    // logo acima do fundo liso e abaixo de qualquer camada de dados
    const layers = map.getStyle().layers;
    const bgIndex = layers.findIndex((l) => l.id === BG_LAYER);
    const before = layers[bgIndex + 1]?.id;
    map.addLayer({ id: RASTER_ID, type: 'raster', source: RASTER_ID }, before);
  }
}
