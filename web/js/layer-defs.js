// Definicao das camadas (puro, sem DOM). Ordem = ordem inicial de empilhamento, de baixo para cima.
export const LAYER_DEFS = [
  { id: 'geo_units', label: 'Unidades geológicas' },
  { id: 'tectonic_zones', label: 'Zonas tectônicas' },
  { id: 'samples', label: 'Amostras' },
  { id: 'volcanoes', label: 'Vulcões' },
];

export const LAYER_IDS = LAYER_DEFS.map((d) => d.id);
