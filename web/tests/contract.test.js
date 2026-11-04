// Contrato pipeline -> web (web/js/contract.json): toda propriedade que a web le
// tem que estar no contrato da camada certa. Uma coluna renomeada falha aqui
// (lado web) e em tests/test_contract.py (lado pipeline).
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { buildLayers } from '../js/layerstyles.js';
import { buildSampleFilter } from '../js/filters.js';
import { renderSample, renderUnit, renderVolcano, renderZone, renderMacrostratUnit, renderPlateBoundary } from '../js/inspector.js';
import { buildLabelSpecs } from '../js/platelabels.js';

const CONTRACT = JSON.parse(readFileSync(new URL('../js/contract.json', import.meta.url), 'utf8'));
// fonte MapLibre -> camada do contrato (quando o nome difere)
const CONTRACT_OF = { plates: 'plate_boundaries' };
const keysOf = (layer) => new Set(Object.keys(CONTRACT[layer]));

// Todos os nomes em ['get', '<prop>'] de uma expressao (recursivo).
function getProps(expr, out = new Set()) {
  if (Array.isArray(expr)) {
    if (expr[0] === 'get' && typeof expr[1] === 'string') out.add(expr[1]);
    for (const e of expr) getProps(e, out);
  } else if (expr && typeof expr === 'object') {
    for (const v of Object.values(expr)) getProps(v, out);
  }
  return out;
}

const ALL_FILTERS = {
  classes: ['mafic'], rock: 'basalto', sources: ['georoc'], coordSource: 'reported', lithClass: 'basic_volcanic',
};

test('contrato lista as camadas da web', () => {
  assert.deepEqual(
    Object.keys(CONTRACT).filter((k) => !k.startsWith('$')).sort(),
    ['geo_units', 'macrostrat', 'plate_boundaries', 'plate_labels', 'samples', 'sources', 'tectonic_zones', 'volcanoes'],
  );
  // macrostrat e externo (tiles de terceiros): fora do pipeline e do tests/test_contract.py
  assert.deepEqual(CONTRACT.$external, ['macrostrat']);
});

test('propriedades usadas pelos estilos de cada camada estao no contrato da camada', () => {
  const layers = buildLayers(buildSampleFilter(ALL_FILTERS));
  for (const layer of layers) {
    const allowed = keysOf(CONTRACT_OF[layer.source] ?? layer.source);
    const used = getProps({ paint: layer.paint, layout: layer.layout, filter: layer.filter });
    for (const p of used) assert.ok(allowed.has(p), `${layer.id}: '${p}' fora do contrato de ${layer.source}`);
  }
  // cobertura: os estilos realmente leem propriedades
  assert.ok(getProps(layers.find((l) => l.id === 'geo_units').paint).has('lith_class'));
});

test('propriedades usadas pelo filtro das amostras estao no contrato de samples', () => {
  const used = getProps(buildSampleFilter(ALL_FILTERS));
  assert.deepEqual([...used].sort(),
    ['coord_source', 'rock_class', 'rock_name_original', 'source_id', 'unit_lith_class']);
  for (const p of used) assert.ok(keysOf('samples').has(p), p);
});

// Objeto com exatamente as chaves do contrato que registra toda leitura de chave.
const SAMPLE_VALUE = { string: 'x', integer: 1, number: 1.5 };
function probe(layer, reads) {
  const target = Object.fromEntries(Object.entries(CONTRACT[layer])
    .map(([k, t]) => [k, k === 'moment_total' ? '3.981e+19' : SAMPLE_VALUE[t]]));
  return new Proxy(target, {
    get(obj, key, recv) {
      if (typeof key === 'string') reads.push(key);
      return Reflect.get(obj, key, recv);
    },
  });
}

function assertReadsInContract(layer, reads) {
  assert.ok(reads.length > 0, `${layer}: nada lido`);
  for (const k of reads) assert.ok(keysOf(layer).has(k), `'${k}' lido mas fora do contrato de ${layer}`);
}

test('renderizadores do painel so leem propriedades do contrato', () => {
  const cases = [
    ['samples', (p, s) => renderSample(p, { source: s, unitSource: s })],
    ['geo_units', (p, s) => renderUnit(p, p.sample_count, { source: s })],
    ['volcanoes', (p, s) => renderVolcano(p, { source: s })],
    ['tectonic_zones', (p, s) => renderZone(p, { source: s })],
    ['plate_boundaries', (p, s) => renderPlateBoundary(p, { source: s })],
    ['macrostrat', (p) => renderMacrostratUnit(p)],
  ];
  for (const [layer, render] of cases) {
    const reads = [];
    const sourceReads = [];
    render(probe(layer, reads), probe('sources', sourceReads));
    assertReadsInContract(layer, reads);
    if (layer !== 'macrostrat') assertReadsInContract('sources', sourceReads);
  }
});

test('rotulos de placa so leem propriedades do contrato de plate_labels', () => {
  const props = Object.fromEntries(Object.keys(CONTRACT.plate_labels).map((k) => [k, 'x']));
  const reads = [];
  const probed = new Proxy(props, { get(o, k, r) { if (typeof k === 'string') reads.push(k); return Reflect.get(o, k, r); } });
  const specs = buildLabelSpecs({ features: [{ geometry: { type: 'Point', coordinates: [1, 2] }, properties: probed }] });
  assert.equal(specs.length, 1);
  assert.ok(reads.length > 0);
  for (const k of reads) assert.ok(keysOf('plate_labels').has(k), k);
});

test('props.<nome> lidos em main.js existem no contrato de alguma camada', () => {
  const src = readFileSync(new URL('../js/main.js', import.meta.url), 'utf8');
  const names = new Set([...src.matchAll(/props\??\.([a-z_][a-z0-9_]*)/g)].map((m) => m[1]));
  const all = new Set(Object.keys(CONTRACT).filter((k) => !k.startsWith('$')).flatMap((k) => Object.keys(CONTRACT[k])));
  assert.ok(names.size > 0);
  for (const n of names) assert.ok(all.has(n), `main.js le props.${n}, fora do contrato`);
});
