// Definicao das camadas (puro, sem DOM). Ordem = ordem inicial de empilhamento, de baixo para cima.
export const LAYER_DEFS = [
  { id: 'geo_units', label: 'Unidades geológicas' },
  { id: 'tectonic_zones', label: 'Zonas tectônicas' },
  { id: 'samples', label: 'Amostras' },
  { id: 'volcanoes', label: 'Vulcões' },
];

export const LAYER_IDS = LAYER_DEFS.map((d) => d.id);

// Nova ordem (de baixo para cima) apos mover `id` uma posicao; direction +1 = para cima.
// Nas bordas ou com id desconhecido devolve a mesma ordem. Nao muta a entrada.
export function moveItem(order, id, direction) {
  const i = order.indexOf(id);
  const j = i + direction;
  const next = order.slice();
  if (i < 0 || j < 0 || j >= order.length) return next;
  [next[i], next[j]] = [next[j], next[i]];
  return next;
}
