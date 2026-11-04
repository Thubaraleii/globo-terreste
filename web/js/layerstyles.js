// Especificacao de fontes, camadas e legendas dos dados (puro, sem DOM nem maplibre).
// Ids das camadas MapLibre: `<id>` ou `<id>:<sufixo>`, com <id> em LAYER_DEFS.

export const NEUTRAL = '#8a8f99';

// Classes litologicas (lith_class de geo_units; tabela GLIM_CLASSES do pipeline).
export const LITH_COLORS = [
  ['unconsolidated_sediments', '#e8d9a0', 'Sedimentos não consolidados'],
  ['siliciclastic_sedimentary', '#d9a566', 'Sedimentar siliciclástica'],
  ['carbonate_sedimentary', '#7fb7d6', 'Sedimentar carbonática'],
  ['mixed_sedimentary', '#c4a98a', 'Sedimentar mista'],
  ['pyroclastics', '#b06a5b', 'Piroclásticas'],
  ['acid_volcanic', '#e08a9b', 'Vulcânica ácida'],
  ['intermediate_volcanic', '#c96f8f', 'Vulcânica intermediária'],
  ['basic_volcanic', '#6b4fa0', 'Vulcânica básica'],
  ['acid_plutonic', '#f0b6a0', 'Plutônica ácida'],
  ['intermediate_plutonic', '#d98c6a', 'Plutônica intermediária'],
  ['basic_plutonic', '#4f6fb3', 'Plutônica básica'],
  ['metamorphics', '#7aa86a', 'Metamórficas'],
  ['evaporites', '#e6c6e8', 'Evaporitos'],
  ['water_bodies', '#2f5f8f', 'Corpos d’água'],
  ['ice_and_glaciers', '#dfeff7', 'Gelo e geleiras'],
];

// Classe da rocha da amostra (rock_class); null/ausente = sem classe.
export const ROCK_CLASS_COLORS = [
  ['mafic', '#e2552d', 'Máfica'],
  ['ultramafic', '#7a2be0', 'Ultramáfica'],
];

// Geologia publica (Macrostrat, CC BY 4.0). Constantes do codigo, nunca vindas de dados.
export const MACROSTRAT_TILES = 'https://tiles.macrostrat.org/carto/{z}/{x}/{y}.mvt';
export const MACROSTRAT_ATTRIBUTION = 'Geologia © <a href="https://macrostrat.org">Macrostrat</a> (CC BY 4.0) e os provedores originais dos mapas';

const VOLCANO_COLOR = '#ff5a36';
const HOTSPOT_COLOR = '#ffd23f';
// Limites de placa (PB2002): cinza claro e fino; subducao em cinza quente, um pouco mais grossa.
const PLATE_COLOR = '#d0d5dd';
const SUBDUCTION_COLOR = '#e8b08a';
const ZONE_LEGEND_COLOR = '#fb8500';

const get = (k) => ['get', k];
const flat = (table) => table.flatMap(([v, c]) => [v, c]);

// ['match', input, v1, c1, ..., default]
const matchBy = (prop, table, fallback) => ['match', get(prop), ...flat(table), fallback];

// Fontes. `base` e a pasta dos dados, com barra final (absoluta: os workers do
// MapLibre nao resolvem caminhos relativos ao documento).
export function buildSources(base) {
  return {
    volcanoes: { type: 'geojson', data: `${base}volcanoes.geojson` },
    tectonic_zones: { type: 'geojson', data: `${base}tectonic_zones.geojson` },
    plates: { type: 'geojson', data: `${base}plate_boundaries.geojson` },
    // Macrostrat: tiles remotos (CC BY 4.0), lidos direto pelo navegador do visitante
    macrostrat: {
      type: 'vector',
      tiles: [MACROSTRAT_TILES],
      minzoom: 0,
      maxzoom: 12,
      attribution: MACROSTRAT_ATTRIBUTION,
    },
    geo_units: { type: 'vector', url: `pmtiles://${base}geo_units.pmtiles` },
    samples: { type: 'vector', url: `pmtiles://${base}samples.pmtiles` },
  };
}

// Camadas, de baixo para cima (o painel reordena depois). `sampleFilter` e a expressao
// inicial das amostras (ou null/undefined).
export function buildLayers(sampleFilter = null) {
  const sampleOnly = sampleFilter ? { filter: sampleFilter } : {};
  return [
    {
      id: 'macrostrat',
      type: 'fill',
      source: 'macrostrat',
      'source-layer': 'units',
      paint: {
        // cor do proprio tile; texto que nao for cor valida cai no neutro
        'fill-color': ['to-color', get('color'), NEUTRAL],
        'fill-opacity': 0.4,
      },
    },
    {
      id: 'macrostrat:lines',
      type: 'line',
      source: 'macrostrat',
      'source-layer': 'lines',
      minzoom: 3,
      paint: { 'line-color': '#1d2330', 'line-opacity': 0.5, 'line-width': 0.6 },
    },
    {
      id: 'geo_units',
      type: 'fill',
      source: 'geo_units',
      'source-layer': 'geo_units',
      paint: {
        'fill-color': matchBy('lith_class', LITH_COLORS, NEUTRAL),
        'fill-opacity': 0.55,
      },
    },
    {
      id: 'geo_units:outline',
      type: 'line',
      source: 'geo_units',
      'source-layer': 'geo_units',
      minzoom: 3,
      paint: { 'line-color': '#1d2330', 'line-opacity': 0.35, 'line-width': 0.5 },
    },
    {
      // abaixo das zonas: o laranja grosso do top 30 continua por cima
      id: 'plates',
      type: 'line',
      source: 'plates',
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: {
        'line-color': ['case', ['==', get('type'), 'subduction'], SUBDUCTION_COLOR, PLATE_COLOR],
        'line-width': ['case', ['==', get('type'), 'subduction'], 1.8, 1],
        'line-opacity': 0.85,
      },
    },
    {
      id: 'tectonic_zones',
      type: 'line',
      source: 'tectonic_zones',
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: {
        // rank 1 = maior momento sismico; ausente cai no valor mais fraco
        'line-width': ['interpolate', ['linear'], ['coalesce', get('rank'), 100], 1, 4, 10, 2.5, 100, 1],
        'line-color': ['interpolate', ['linear'], ['coalesce', get('rank'), 100],
          1, '#ffb703', 10, '#fb8500', 100, '#9d4a1a'],
      },
    },
    {
      id: 'samples:density',
      type: 'heatmap',
      source: 'samples',
      'source-layer': 'samples',
      maxzoom: 8,
      ...sampleOnly,
      paint: {
        'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 0, 4, 7, 16],
        // baixa em zoom pequeno: sem agregacao no tile (fallback GDAL), todos os ~127 mil
        // pontos entram no mapa de calor e uma intensidade alta satura tudo
        'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 0, 0.01, 3, 0.03, 5, 0.15, 7, 0.6],
        'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'],
          0, 'rgba(226,85,45,0)', 0.2, 'rgba(226,85,45,0.35)', 0.5, '#e2552d', 1, '#ffe08a'],
        // some ao aproximar, quando entram os pontos individuais
        'heatmap-opacity': ['interpolate', ['linear'], ['zoom'], 5, 0.9, 8, 0],
      },
    },
    {
      id: 'samples:points',
      type: 'circle',
      source: 'samples',
      'source-layer': 'samples',
      minzoom: 5,
      ...sampleOnly,
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 5, 2.5, 12, 6],
        'circle-color': matchBy('rock_class', ROCK_CLASS_COLORS, NEUTRAL),
        // coordenada reportada: anel branco; geocodificada: sem anel e mais translucida
        'circle-stroke-width': ['match', get('coord_source'), 'geocoded', 0, 1],
        'circle-stroke-color': '#ffffff',
        'circle-opacity': ['match', get('coord_source'), 'geocoded', 0.6, 0.95],
      },
    },
    {
      id: 'volcanoes',
      type: 'circle',
      source: 'volcanoes',
      paint: {
        // hotspots: maiores, amarelos e vazados; vulcoes: vermelhos e cheios
        'circle-radius': ['match', get('kind'), 'hotspot', 6, 4],
        'circle-color': ['match', get('kind'), 'hotspot', 'rgba(0,0,0,0)', VOLCANO_COLOR],
        'circle-stroke-color': ['match', get('kind'), 'hotspot', HOTSPOT_COLOR, '#ffffff'],
        'circle-stroke-width': ['match', get('kind'), 'hotspot', 2.5, 1],
      },
    },
  ];
}

// Nota explicativa da legenda (texto fixo do codigo) ou null. Macrostrat nao tem tabela
// de classes: a cor vem de cada unidade.
export function legendNote(id) {
  if (id === 'macrostrat') {
    return 'Cores das unidades conforme o Macrostrat (em geral pela idade). A escala do mapa '
      + 'muda com o zoom: generalizado no mundo todo, mais detalhado ao aproximar, e com lacunas '
      + 'onde não há mapa compilado. Clique em uma unidade para ver os detalhes.';
  }
  return null;
}

// Itens de legenda por camada logica: { value, label, color, shape }.
export function legendItems(id) {
  const rows = (table) => table.map(([value, color, label]) => ({ value, label, color, shape: 'square' }));
  switch (id) {
    case 'geo_units':
      return rows(LITH_COLORS);
    case 'samples':
      return [
        ...rows(ROCK_CLASS_COLORS).map((i) => ({ ...i, shape: 'dot' })),
        { value: null, label: 'Sem classe', color: NEUTRAL, shape: 'dot' },
        { value: 'reported', label: 'Anel branco: coordenada reportada', color: '#ffffff', shape: 'ring' },
        { value: 'geocoded', label: 'Sem anel: coordenada geocodificada', color: NEUTRAL, shape: 'dot' },
      ];
    case 'volcanoes':
      return [
        { value: 'volcano', label: 'Vulcão', color: VOLCANO_COLOR, shape: 'dot' },
        { value: 'hotspot', label: 'Hotspot', color: HOTSPOT_COLOR, shape: 'ring' },
      ];
    case 'plates':
      return [
        { value: 'boundary', label: 'Limite de placa', color: PLATE_COLOR, shape: 'line' },
        { value: 'subduction', label: 'Subducção (linha mais grossa)', color: SUBDUCTION_COLOR, shape: 'line' },
        { value: 'zones', label: 'Laranja: zonas mais ativas (camada abaixo)', color: ZONE_LEGEND_COLOR, shape: 'line' },
      ];
    case 'tectonic_zones':
      return [
        { value: 'high', label: 'Maior momento sísmico (linha grossa)', color: '#ffb703', shape: 'line' },
        { value: 'low', label: 'Menor momento sísmico (linha fina)', color: '#9d4a1a', shape: 'line' },
      ];
    default:
      return [];
  }
}
