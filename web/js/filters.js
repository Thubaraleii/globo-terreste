// Filtros das amostras -> expressao de filtro do MapLibre. Modulo puro.
//
// Todo texto vindo do usuario entra na expressao somente como literal (string ou
// ['literal', lista]); nunca se monta operador nem codigo a partir dele.

const text = (v) => (typeof v === 'string' ? v : null);

// Devolve a expressao de filtro, ou null quando nenhum filtro esta ativo.
export function buildSampleFilter(filters) {
  const f = filters ?? {};
  const parts = [];

  const classes = (f.classes ?? []).filter((c) => text(c) !== null);
  if (classes.length) parts.push(['in', ['get', 'rock_class'], ['literal', classes]]);

  // nome da rocha: contem, sem diferenciar maiusculas; vazio/so espacos = sem filtro
  const rock = text(f.rock)?.trim().toLowerCase();
  if (rock) {
    parts.push([
      'in', rock,
      ['downcase', ['to-string', ['coalesce', ['get', 'rock_name_original'], '']]],
    ]);
  }

  const sources = (f.sources ?? []).filter((s) => text(s) !== null);
  if (sources.length) parts.push(['in', ['get', 'source_id'], ['literal', sources]]);

  if (text(f.coordSource) !== null) parts.push(['==', ['get', 'coord_source'], f.coordSource]);
  if (text(f.lithClass) !== null) parts.push(['==', ['get', 'unit_lith_class'], f.lithClass]);

  if (parts.length === 0) return null;
  return parts.length === 1 ? parts[0] : ['all', ...parts];
}
