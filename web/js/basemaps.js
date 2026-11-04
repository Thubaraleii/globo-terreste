// Mapas-base. Estrutura de cada entrada: { id, label, tiles, attribution, maxzoom? }.
//
// Escolhidos pelo usuario em 2026-11-03: Escuro, Satelite e Relevo, os tres da Esri
// (os tiles publicos do CARTO "dark_all" passaram a exigir chave de API: testado, devolvem
// uma marca d'agua "API KEY REQUIRED" sobre o mapa).
// Sao servicos de terceiros: o navegador de quem abre o globo pede os tiles direto a
// eles (o IP e a regiao vista ficam visiveis para o provedor) e os termos de cada um
// valem para o seu uso — ver README ("Mapas de fundo"). A atribuicao do fundo ativo e
// sempre exibida no mapa; os textos abaixo sao constantes do codigo (nunca dados).
// "Fundo liso" (cor, sem requisicoes externas) continua disponivel. Entradas com
// `tiles: null` e sem `color` nao aparecem na interface.
export const BASEMAPS = [
  { id: 'plain', label: 'Fundo liso', tiles: null, attribution: '', color: '#1b2a44' },
  {
    id: 'dark',
    label: 'Escuro',
    tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}'],
    attribution: 'Mapa escuro © Esri, HERE, Garmin, © OpenStreetMap contributors e a comunidade de usuários do GIS',
    maxzoom: 16,
  },
  {
    id: 'relief',
    label: 'Relevo',
    tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Shaded_Relief/MapServer/tile/{z}/{y}/{x}'],
    attribution: 'Relevo © Esri, USGS, NOAA',
    maxzoom: 13,
  },
  {
    id: 'satellite',
    label: 'Satélite',
    tiles: ['https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'],
    attribution: 'Imagens © Esri, Maxar, Earthstar Geographics e a comunidade de usuários do GIS',
    maxzoom: 19,
  },
];

// Fundo inicial ao abrir o globo.
export const DEFAULT_BASEMAP_ID = 'dark';

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
      ...(basemap.maxzoom ? { maxzoom: basemap.maxzoom } : {}),
    });
    // logo acima do fundo liso e abaixo de qualquer camada de dados
    const layers = map.getStyle().layers;
    const bgIndex = layers.findIndex((l) => l.id === BG_LAYER);
    const before = layers[bgIndex + 1]?.id;
    map.addLayer({ id: RASTER_ID, type: 'raster', source: RASTER_ID }, before);
  }
}
